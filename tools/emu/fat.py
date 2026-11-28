"""Build a FAT16 disk image from a dict of files, for the emulated cooler's serial flash and SD card.

Just enough of FAT for FatFs to mount and read: one volume without a partition table ("superfloppy"),
a root directory and one level of subdirectories, 8.3 names plus long file names where needed.

    image = build({"ui.bin": b"...", "SynwitManifest.cfg": b"...", "IMG/001_x/angle_0.jpg": jpeg})
"""
from __future__ import annotations

import struct

SECTOR = 512


def _short_name(name: str, taken: set[bytes]) -> tuple[bytes, bool]:
    """(11-byte 8.3 name, whether a long-name entry is needed too)."""
    stem, _, ext = name.rpartition(".") if "." in name else (name, "", "")
    plain = (len(stem) <= 8 and len(ext) <= 3 and name == name.upper() and name.isascii()
             and all(c.isalnum() or c in "_-~" for c in stem + ext))
    if plain:
        return stem.ljust(8).encode() + ext.ljust(3).encode(), False
    clean = "".join(c for c in stem.upper() if c.isalnum() or c in "_-") or "FILE"
    ext8 = "".join(c for c in ext.upper() if c.isalnum())[:3]
    for n in range(1, 1000):
        tail = f"~{n}"
        short = (clean[:8 - len(tail)] + tail).ljust(8).encode() + ext8.ljust(3).encode()
        if short not in taken:
            return short, True
    raise ValueError(name)


def _entries(name: str, taken: set[bytes], attr: int, cluster: int, size: int) -> bytes:
    short, long_needed = _short_name(name, taken)
    taken.add(short)
    out = b""
    if long_needed:
        checksum = 0
        for b in short:
            checksum = ((checksum >> 1) | ((checksum & 1) << 7)) + b & 0xFF
        units = name.encode("utf-16-le") + b"\x00\x00"
        units += b"\xff" * (-len(units) % 26)
        parts = [units[i:i + 26] for i in range(0, len(units), 26)]
        for i in range(len(parts), 0, -1):
            p = parts[i - 1]
            seq = i | (0x40 if i == len(parts) else 0)
            out += bytes([seq]) + p[0:10] + bytes([0x0F, 0, checksum]) + p[10:22] + b"\x00\x00" + p[22:26]
    out += short + bytes([attr]) + bytes(8) + struct.pack("<H", cluster >> 16) + struct.pack("<HHHI", 0, 0x5A21, cluster & 0xFFFF, size)
    return out


def read(image: bytes) -> dict[str, bytes]:
    """The files on a FAT16 volume, as {path: content} (the reverse of build; long names are used
    where a file has one).

    A short name is in capitals on the disk, with two bits beside it that say its stem or its ending is
    in small letters: that is how the firmware's FatFs writes "index000.jpg". They are read here, since
    the firmware cares: it counts an animation's frames by their names, and with INDEX000.JPG it counts
    none and shows the first frame for ever (seen 28 Nov 2026, with a card built from what this gave)."""
    sector, cluster_sectors, reserved, fats, root_entries = struct.unpack_from("<HBHBH", image, 11)
    fat_sectors = struct.unpack_from("<H", image, 22)[0]
    root_start = (reserved + fats * fat_sectors) * sector
    data_start = root_start + root_entries * 32
    cluster_bytes = cluster_sectors * sector
    table = reserved * sector

    def chain(cluster: int) -> bytes:
        out = bytearray()
        while 2 <= cluster < 0xFFF8 and len(out) < len(image):
            start = data_start + (cluster - 2) * cluster_bytes
            out += image[start:start + cluster_bytes].ljust(cluster_bytes, b"\0")
            cluster = struct.unpack_from("<H", image, table + 2 * cluster)[0]
        return bytes(out)

    files: dict[str, bytes] = {}

    def walk(raw: bytes, prefix: str) -> None:
        long_parts: list[bytes] = []
        for i in range(0, len(raw) - 31, 32):
            e = raw[i:i + 32]
            if e[0] == 0:
                break
            if e[0] == 0xE5:
                long_parts = []
                continue
            if e[11] == 0x0F:
                long_parts.insert(0, e[1:11] + e[14:26] + e[28:32])
                continue
            name = b"".join(long_parts).decode("utf-16-le", "replace").split("\0")[0] if long_parts else ""
            long_parts = []
            if not name:
                stem, ext = e[0:8].decode("latin1").rstrip(), e[8:11].decode("latin1").rstrip()
                stem, ext = stem.lower() if e[12] & 0x08 else stem, ext.lower() if e[12] & 0x10 else ext
                name = f"{stem}.{ext}" if ext else stem
            if e[11] & 0x08 or name in (".", ".."):
                continue
            cluster, size = struct.unpack_from("<HI", e, 26)
            if e[11] & 0x10:
                walk(chain(cluster), f"{prefix}{name}/")
            else:
                files[prefix + name] = chain(cluster)[:size]

    walk(image[root_start:data_start], "")
    return files


def build(files: dict[str, bytes], megabytes: int = 16, cluster_sectors: int = 4, label: str = "DEEPHACK") -> bytes:
    total = megabytes * 1024 * 1024 // SECTOR
    reserved, root_entries = 1, 512
    root_sectors = root_entries * 32 // SECTOR
    clusters = (total - reserved - root_sectors) // cluster_sectors
    fat_sectors = (clusters * 2 + 4 + SECTOR - 1) // SECTOR
    clusters = (total - reserved - root_sectors - 2 * fat_sectors) // cluster_sectors
    assert 4085 <= clusters < 65525, "not a FAT16 volume: change megabytes or cluster_sectors"
    data_start = reserved + 2 * fat_sectors + root_sectors
    fat = [0xFFF8, 0xFFFF] + [0] * clusters
    data: dict[int, bytes] = {}
    next_free = [2]
    cluster_bytes = cluster_sectors * SECTOR

    def store(content: bytes) -> int:
        if not content:
            return 0
        count = (len(content) + cluster_bytes - 1) // cluster_bytes
        first = next_free[0]
        for i in range(count):
            c = first + i
            fat[c] = c + 1 if i < count - 1 else 0xFFFF
            data[c] = content[i * cluster_bytes:(i + 1) * cluster_bytes].ljust(cluster_bytes, b"\0")
        next_free[0] += count
        return first

    tree: dict = {}
    for path, content in files.items():
        node = tree
        parts = path.replace("\\", "/").strip("/").split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = content

    def directory(node: dict, parent: int, is_root: bool) -> bytes | int:
        taken: set[bytes] = set()
        body = b""
        me = 0 if is_root else next_free[0]
        if not is_root:
            next_free[0] += 1                      # one cluster per subdirectory is plenty here
            body += b".          " + bytes([0x10]) + bytes(14) + struct.pack("<HI", me, 0)
            body += b"..         " + bytes([0x10]) + bytes(14) + struct.pack("<HI", parent, 0)
        for name, content in node.items():
            if isinstance(content, dict):
                body += _entries(name, taken, 0x10, directory(content, me, False), 0)
            else:
                body += _entries(name, taken, 0x20, store(content), len(content))
        if is_root:
            return body
        assert len(body) <= cluster_bytes, "directory too large"
        fat[me] = 0xFFFF
        data[me] = body.ljust(cluster_bytes, b"\0")
        return me

    root = directory(tree, 0, True)
    assert len(root) <= root_entries * 32
    boot = bytearray(SECTOR)
    boot[0:3] = b"\xEB\x3C\x90"
    boot[3:11] = b"MSDOS5.0"
    struct.pack_into("<HBHBHHBHHHII", boot, 11, SECTOR, cluster_sectors, reserved, 2, root_entries,
                     total if total < 0x10000 else 0, 0xF8, fat_sectors, 63, 255, 0, total if total >= 0x10000 else 0)
    boot[36:39] = bytes([0x80, 0, 0x29])
    struct.pack_into("<I", boot, 39, 0xDEE9AC00)
    boot[43:54] = label.ljust(11).encode()[:11]
    boot[54:62] = b"FAT16   "
    boot[510:512] = b"\x55\xAA"
    image = bytearray(total * SECTOR)
    image[0:SECTOR] = boot
    fat_raw = struct.pack(f"<{len(fat)}H", *fat).ljust(fat_sectors * SECTOR, b"\0")[:fat_sectors * SECTOR]
    for copy in range(2):
        start = (reserved + copy * fat_sectors) * SECTOR
        image[start:start + len(fat_raw)] = fat_raw
    start = (reserved + 2 * fat_sectors) * SECTOR
    image[start:start + len(root)] = root
    for cluster, chunk in data.items():
        start = (data_start + (cluster - 2) * cluster_sectors) * SECTOR
        image[start:start + len(chunk)] = chunk
    return bytes(image)
