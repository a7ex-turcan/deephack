"""A model of the MYSTIQUE for tests: what we know about its USB protocol and firmware, as rules.

It stands in for the pyusb device, so the real driver (deephack.device) runs against it byte for byte.
It keeps the state the firmware keeps (display mode, stored stills and animations by index, what is on
screen, options, clock, sensor screens) and records a violation for everything known to be unsafe or
wrong, from the README's protocol notes and docs/firmware-analysis.md. The `cooler` fixture fails a test
that leaves any violation behind.
"""
from __future__ import annotations

import io
import struct

import usb.core
from PIL import Image

from deephack import device

FINISH = b"dcldfinish".ljust(55, b"\0")
# The heap, as an upload finds it (seen on the cooler, 24 Nov 2026; docs/firmware-analysis.md). The firmware
# puts an upload into STAGING bytes in one piece. While it waits for the upload's header the largest free
# piece was 2 510 372 bytes with a stored still of 4 KB on show, 2 454 040 with one of 60 KB, and 393 276
# less with the three buffers a patch makes for its first drawn picture.
HEAP, HEAP_END, STAGING = 0x8000_0000, 0x8080_0000, 0x200000
FREE_FOR_UPLOAD, BUFFERS_TAKE = 2_514_000, 393_276
UPLOAD_WAIT = 0x2000_0C2C               # counts while the firmware waits for a header: 0 at other times
BUFFERS = 0x2000_F004                   # the patch's three buffers
WAIT_BEGINS = 2                         # the wait begins a moment after 0F: this many looks at it see 0 first
NO_EFFECT = {0x05, 0x06, 0x0B, 0x0C, 0x0D, 0x0E, 0x10, 0x11, 0x15, 0x16, 0x17}   # answered, nothing to model


class CoolerModel:
    def __init__(self, stored_stills: int = 1, stored_gifs: int = 0, uuid: str = "0123456789ABCDEF0123456789ABCDEF"):
        self.uuid = uuid
        self.bcdDevice = 0x0246                 # what USB reports of the firmware: 2.70
        self.firmwares: dict[bytes, object] = {}    # the images a firmware update may bring: image -> `direct` with it
        self.updates = 0                        # firmware updates taken; each restarts the cooler
        self.off_bus = 0                        # ... which takes it off the bus for this many looks (`look`)
        self.direct = False                     # the direct drawing firmware (tools/fw/patch.py), command 20: True
                                                # or 1 for the first patch, 2 and up for that version of it
        self.drawn: bytes | None = None         # the JPEG drawn from USB that is on screen in place of the stored still
        self.draws = 0
        self.buffers = False                    # the patch has made its frame buffers: with its first drawn picture, and
                                                # they stay until the cooler restarts (from patch 15: until an upload)
        self.part: tuple[int, int, bytes] | None = None     # (x, y, JPEG) of the part drawn on top of it (patch 3)
        self.lights: tuple[list, int] | None = None         # (14 colours, pace) the host has the lights go to (patch
                                                            # 16); None: the cooler picks them itself
        self.light_commands = 0
        self.parts = 0
        self._drawing: dict | None = None       # a frame that is coming in
        self._animated = False                  # an animation has been on the image screen since it was entered
        self.stuck = False                      # ... and a frame was drawn after: no further frame is taken (patch 1)
        self.mode: int | None = None            # device.MODE_*; None until the first CMD_MODE
        self.stills = [[f"app-still-{i}", b""] for i in range(stored_stills)]       # [file id, jpeg] by index
        self.gifs = [[f"app-gif-{i}", [], 1000] for i in range(stored_gifs)]       # [file id, frames, ms]
        self.left_behind = {}                   # file id: frames on the card of an animation that was called off
        self.shown: tuple[str, int] | None = None   # ("jpg" | "gif", index) picked with CMD_SHOW_SLOT
        self.options: tuple[int, ...] | None = None
        self.slideshow: tuple[int, int] | None = None
        self.dashboard: tuple[int, ...] | None = None
        self.recorder: int | None = None
        self.sensors: bytes | None = None
        self.clock: tuple[int, ...] | None = None
        self.flash_writes = 0                   # JPEG files committed to flash (an animation counts each frame)
        self.log: list[tuple] = []              # what happened, in order: ("cmd", name, payload) / ("stored", kind, index)
        self.violations: list[str] = []
        self._replies: dict[int, list[bytes]] = {0x81: [], 0x82: []}
        self._upload: dict | None = None

    # ---- what the firmware shows
    @property
    def screen(self):
        if self.mode == device.MODE_SITUATIONAL:
            return ("dashboard", self.dashboard)
        if self.mode == device.MODE_RECORDER:
            return ("recorder", self.recorder)
        if self.drawn is not None:
            return ("drawn", self.drawn)
        return self.shown

    @property
    def light(self) -> int | None:
        return self.options[3] if self.options else None

    def still(self, index: int) -> Image.Image:
        return Image.open(io.BytesIO(self.stills[index][1]))

    def _violate(self, why: str) -> None:
        self.violations.append(why)

    def look(self) -> int | None:
        """What deephack.firmware.on_bus sees: bcdDevice, or None while the cooler restarts."""
        if self.off_bus:
            self.off_bus -= 1
            return None
        return self.bcdDevice

    # ---- the pyusb surface the driver uses
    def write(self, ep: int, data, timeout=None) -> int:
        if self.off_bus:
            raise usb.core.USBError("the cooler is restarting")
        data = bytes(data)
        more = b""
        if len(data) == 64 and data[:3] == bytes([0xAA, 0x2E, device.CMD_LIGHT]):
            data, more = data[:48], data[48:]       # the lights: one packet, of which the first 48 bytes are the command
        is_command = len(data) == 48 and data[:2] == b"\xaa\x2e"
        if self._drawing is not None:           # while a frame is coming in, everything on endpoint 1 is picture data
            self._draw_data(ep, data)
        elif self._upload is not None and not (is_command and data[42:46] == b"HIDC"):
            self._upload_packet(data)
        elif is_command:
            # While the firmware waits for an upload's header, the patch answers "read memory" from the USB
            # interrupt and the waiting loop drops the packet as "not a header". After the header the packet
            # would be counted as the file's data.
            waiting = self._upload is not None and self._upload["stage"] == "header" and not self._upload["files"]
            if self._upload is not None and self._upload["stage"] == "refused":
                self._upload = None             # it found no room, waited six seconds more for a header, and gave up
            if self._upload is not None and not (waiting and data[2] == device.CMD_PEEK and self._peeks()):
                self._violate(f"command {data[2]:#04x} before dcldfinish: an unfinished upload hung the firmware once")
                self._upload = None
            self._command(ep, data, more)
        else:
            self._violate(f"{len(data)} stray bytes on endpoint {ep:#x} outside an upload")
        return len(data)

    def read(self, ep: int, size: int, timeout=None):
        queue = self._replies.get(ep)
        if not queue:
            raise usb.core.USBTimeoutError("no reply waiting")
        return queue.pop(0)

    # ---- memory, as far as anything here looks at it (command 21, patch 4)
    def _peeks(self) -> bool:
        return int(self.direct) >= device.PEEK_VERSION

    def free_for_upload(self) -> int:
        """The largest free piece of the heap while the firmware waits for an upload's header. The file of
        the still on show is in the heap, and the patch's buffers if it has made them."""
        on_show = len(self.stills[self.shown[1]][1]) if self.shown and self.shown[0] == "jpg" and self.shown[1] < len(self.stills) else 0
        return (FREE_FOR_UPLOAD - on_show - (BUFFERS_TAKE if self.buffers else 0)) & ~3      # (blocks are whole words)

    def _memory(self, address: int, count: int) -> bytes:
        free, first = self.free_for_upload(), 0x400000
        words = {HEAP: first << 1 | 1, HEAP + 4 + first: free << 1}                      # three blocks: in use, free, in use
        words[HEAP + 8 + first + free] = (HEAP_END - (HEAP + 8 + first + free) - 4) << 1 | 1
        for i in range(3):
            words[BUFFERS + 4 * i] = 0x802BAB64 + 0x20014 * i if self.buffers else 0
        up = self._upload
        if up is not None and up["stage"] == "header" and not up["files"]:
            up["looks"] = up.get("looks", 0) + (address == UPLOAD_WAIT)
            words[UPLOAD_WAIT] = 1000 * max(0, up["looks"] - WAIT_BEGINS)
        out = bytearray()
        for at in range(address, address + count):
            out.append(struct.pack("<I", words.get(at & ~3, 0))[at & 3])
        return bytes(out)

    # ---- commands
    def _reply(self, ep: int, cmd: int, payload: bytes = b"", known: bool = True) -> None:
        b = bytearray(48)
        b[0], b[1], b[2] = 0x55, 0x2E, cmd if known else 0x00    # unknown commands come back as command 00
        b[3:3 + len(payload)] = payload
        b[42:46] = b"HIDC"
        struct.pack_into("<H", b, 46, device.sum16(b[:46]))
        self._replies[0x80 | ep].append(bytes(b))

    def _command(self, ep: int, data: bytes, more: bytes = b"") -> None:
        if data[42:46] != b"HIDC" or device.sum16(data[:46]) != struct.unpack_from("<H", data, 46)[0]:
            self._violate(f"malformed command frame {data.hex()}")
            return
        cmd, payload = data[2], data[3:42]
        self.log.append(("cmd", cmd, payload))
        if cmd in (device.CMD_FACTORY_RESET, device.CMD_DELETE_ALL):
            self._violate(f"command {cmd:#04x} erases every stored image")
        on_ep2 = cmd in (device.CMD_SENSORS, device.CMD_SET_TIME)
        if on_ep2 != (ep == 2):
            self._violate(f"command {cmd:#04x} sent on endpoint {ep}")
        reply = b"\x00"
        if cmd == device.CMD_SENSORS:
            self.sensors = payload
        elif cmd == device.CMD_SET_TIME:
            self.clock = struct.unpack_from("<HBBBBB", payload)
        elif cmd == device.CMD_OPTIONS:
            self.options = tuple(payload[:5])
            if payload[3] not in (device.LIGHT_MOTHERBOARD, device.LIGHT_WARNING, device.LIGHT_SCREEN):
                self._violate(f"unknown light source {payload[3]}")
        elif cmd == device.CMD_MODE:
            if payload[0] not in (device.MODE_SITUATIONAL, device.MODE_MOTION, device.MODE_RECORDER):
                self._violate(f"unknown display mode {payload[0]}")
            if payload[0] != self.mode:
                self.drawn = self.part = None               # the image screen loads its stored picture when it is entered
                self._animated = self.stuck = False
            self.mode = payload[0]
        elif cmd == device.CMD_SITUATION_MODE:
            self.dashboard = tuple(payload[:4])
        elif cmd == device.CMD_RECORDER_MODE:
            self.recorder = payload[0]
        elif cmd == device.CMD_MOTION_MODE:
            self.slideshow = (payload[0], payload[1])
        elif cmd == device.CMD_SHOW_SLOT:
            kind, index = payload[0], payload[1]
            slots = self.stills if kind == device.TYPE_JPG else self.gifs
            if index >= len(slots):
                self._violate(f"show {'gif' if kind else 'jpg'} {index}, but only {len(slots)} are stored")
            if self.mode != device.MODE_MOTION:
                self._violate("show a stored image without switching back to image mode first (deephack's rule)")
            shown = ("gif" if kind == device.TYPE_GIF else "jpg", index)
            if shown != self.shown:
                self.drawn = self.part = None               # "show" for the slot already selected leaves a drawn frame up
            self._animated = self._animated or kind == device.TYPE_GIF
            self.shown = shown
        elif cmd == device.CMD_DELETE_SLOT:
            slots = self.stills if payload[0] == device.TYPE_JPG else self.gifs
            if payload[1] < len(slots):
                slots.pop(payload[1])
            else:
                self._violate(f"delete slot {payload[1]}, which does not exist")
        elif cmd == device.CMD_START_DOWNLOAD:
            self._upload = {"stage": "header", "files": []}
            if int(self.direct) >= device.RELEASE_VERSION:      # patch 15 gives its buffers back for any upload
                self._release()
        elif cmd == device.CMD_RELEASE and int(self.direct) >= device.RELEASE_VERSION:
            self._release()
            reply = bytes([device.DIRECT_GO, int(self.direct)])
        elif cmd == device.CMD_LIGHT and int(self.direct) >= device.LIGHT_VERSION:
            # 13 lights in the command, the 14th, "on" and the pace after it; a plain command of 48 bytes has
            # zeros there, which says "pick them yourself"
            flat, (on, pace) = payload + more[:3], (more[3:5] or b"\0\0")
            self.lights = ([tuple(flat[i:i + 3]) for i in range(0, 42, 3)], pace) if on else None
            self.light_commands += 1
            if on and self.light != device.LIGHT_SCREEN:
                self._violate("the lights' colours sent while the light does not follow the screen: they would not show")
            reply = bytes([device.DIRECT_GO, int(self.direct)])
        elif cmd == device.CMD_PEEK and self._peeks():
            address, count = struct.unpack_from("<IB", payload)
            reply = self._memory(address, min(count, device.PEEK_MOST))
        elif cmd == device.CMD_GET_UUID:
            reply = b"\x00" + self.uuid.encode()
        elif cmd == device.CMD_DIRECT and self.direct:
            size, total, x, y, width, height = struct.unpack_from("<IH4H", payload)
            box = (x, y, width, height) if width and int(self.direct) >= device.DIRECT_PARTS else None    # (an older
            if not 0 < size <= device.DIRECT_MAX:                                # patch does not look at those bytes)
                status = device.DIRECT_REFUSED
            elif self.stuck:
                status = device.DIRECT_LATER
            elif box and self.screen[0] != "drawn":
                status = device.DIRECT_NO_PAGE      # a part goes on a page that was drawn, and only while that is on show
            else:
                self._drawing = {"size": size, "sum": total, "data": b"", "box": box}
                status = device.DIRECT_GO
            reply = bytes([status, int(self.direct) if int(self.direct) > 1 else 0])    # the first patch: no version
        elif cmd not in NO_EFFECT and cmd not in (device.CMD_FACTORY_RESET, device.CMD_DELETE_ALL):
            self._reply(ep, cmd, known=False)
            return
        self._reply(ep, cmd, reply)

    def _release(self) -> None:
        """The patch's buffers go back to the heap (patch 15). A picture that was in one of them is not on show
        any more: the firmware shows deephack's own in its place."""
        if self.buffers:
            self.buffers, self.drawn, self.part = False, None, None

    # ---- direct drawing: 20 with size and sum16, then the JPEG; it replaces the stored still on screen
    def _draw_data(self, ep: int, data: bytes) -> None:
        frame = self._drawing
        self.buffers = True
        frame["data"] += data
        if ep != 1 or len(frame["data"]) > frame["size"]:
            self._violate("a drawn frame's data on the wrong endpoint, or more of it than announced")
        if len(frame["data"]) < frame["size"]:
            return
        self._drawing = None
        # Patch 1, seen on the cooler: after an animation one frame is taken, then "later" for good (the
        # frame is never shown, issue #22). Patch 2 shows frames in that state too.
        self.stuck = self._animated and int(self.direct) < 2
        if device.sum16(frame["data"]) != frame["sum"]:
            self._violate("a drawn frame does not match its sum16: the firmware does not show it")
        elif frame["box"]:
            x, y, width, height = frame["box"]
            if device.jpeg_size(frame["data"]) != (width, height):
                self._violate("a part whose JPEG is not the size its command said: the decoder would write past its place")
            elif width % 16 or height % 16 or x + width > device.WIDTH or y + height > device.HEIGHT:
                self._violate(f"a part of {width}x{height} at {x}, {y}: not whole blocks, or not inside the screen")
            elif self.screen[0] != "drawn":
                self._violate("a part with no drawn page under it any more")
            else:
                self.part, self.parts = (x, y, frame["data"]), self.parts + 1
        elif device.jpeg_size(frame["data"]) != (device.WIDTH, device.HEIGHT):
            self._violate(f"drew something that is not a {device.WIDTH}x{device.HEIGHT} baseline JPEG")
        elif self.mode != device.MODE_MOTION or self.shown is None or self.shown[0] != "jpg":
            self._violate("a frame drawn with no stored still on show: it is dropped, or an animation takes the screen back")
        else:
            self.drawn, self.draws, self.part = frame["data"], self.draws + 1, None     # a new page: the part is gone

    # ---- uploads: 0F, then a 64 byte header and the data in 64 byte packets per file, then dcldfinish
    def _upload_packet(self, data: bytes) -> None:
        up = self._upload
        cur = up.get("current") if up["stage"] == "data" else None
        if cur is not None and cur["type"] == device.FILE_FIRMWARE and data.startswith(b"dcldfinish"):
            # A firmware update that is given up. The firmware counts the packet as data first (seen in the
            # emulator): with under 55 bytes missing it completes the file, and a matching sum flashes it.
            cur["data"] += data[:cur["size"] - len(cur["data"])]
            if len(cur["data"]) == cur["size"] and device.sum16(cur["data"]) == cur["sum"] & 0xFFFF:
                self._flashed(cur["data"])
            else:
                self._upload = None
                self.log.append(("update given up", len(cur["data"])))
        elif data.startswith(b"dcldfinish"):
            if up["stage"] == "data":
                # The firmware counts the 55-byte marker as data before checking it. If those
                # bytes complete the current file and its sum matches, that file is accepted;
                # otherwise the unfinished upload is discarded and the staging buffer is freed.
                missing = max(0, cur["size"] - len(cur["data"]))
                cur["data"] += data[:missing]
                if len(cur["data"]) == cur["size"] and device.sum16(cur["data"]) == cur["sum"] & 0xFFFF:
                    up["files"].append(cur)
                    up["stage"] = "header"
            self._finish(data)
        elif up["stage"] == "refused":
            pass                                            # thrown away, and nothing is said
        elif len(data) > 64:
            self._violate(f"{len(data)} byte packet in an upload (at most 64)")
        elif up["stage"] == "header":
            if len(data) != 64 or data[:4] != b"DCLd":
                self._violate("upload data where a DCLd header belongs")
                return
            if device.sum16(data[:62]) != struct.unpack_from("<H", data, 62)[0]:
                self._violate("upload header checksum is wrong")
            ftype, size, total = data[4], *struct.unpack_from("<II", data, 5)
            count, duration, index = struct.unpack_from("<HHH", data, 13)
            up["current"] = {"type": ftype, "size": size, "sum": total, "count": count, "duration": duration,
                             "index": index, "id": data[20:52].decode("ascii", "replace"), "data": b""}
            up["stage"] = "data"
            if self.free_for_upload() < STAGING:            # malloc(2 MiB) fails: the firmware waits on for a header,
                up["stage"] = "refused"                     # and takes every packet of the file for something that is not one
                self.log.append(("upload refused", ftype, self.free_for_upload()))
                self._violate("an upload to a cooler whose heap has no room for it: the firmware throws it away without a word")
        else:
            cur = up["current"]
            cur["data"] += data
            if len(cur["data"]) > cur["size"]:
                self._violate("more upload data than the header announced")
            if len(cur["data"]) >= cur["size"]:
                if device.sum16(cur["data"]) != cur["sum"] & 0xFFFF:
                    self._violate("upload data does not match the header's sum16: the firmware waits forever")
                elif cur["type"] == device.FILE_FIRMWARE:      # stored and restarted at once, without dcldfinish
                    self._flashed(cur["data"])
                    return
                up["files"].append(cur)
                up["stage"] = "header"

    def _flashed(self, image: bytes) -> None:
        """A whole firmware image with the right sum: the firmware stores it and restarts into its bootloader."""
        self._upload = None
        if image not in self.firmwares:
            self._violate("a firmware update with an image that is not a known one: that can kill the cooler for good")
            return
        self.direct = self.firmwares[image]
        self.updates, self.off_bus = self.updates + 1, 3
        self.mode = self.shown = self.drawn = self._drawing = None
        self.buffers, self.lights = False, None
        self._animated = self.stuck = False
        self.left_behind.clear()                            # at power-on the firmware removes folders without a config.cfg
        self.log.append(("flashed", len(image)))

    def _finish(self, data: bytes) -> None:
        up, self._upload = self._upload, None
        self.drawn = self.part = None                       # the firmware leaves its upload screen and loads the stored picture
        if data != FINISH:
            self._violate("malformed dcldfinish")
        files = up["files"]
        short = bool(files) and files[0]["type"] == device.FILE_GIF and len(files) != files[0]["count"]
        if short:
            # The firmware writes each frame to its card as it arrives. An animation that is called off is
            # not listed and gets no config.cfg, but the frames that came whole stay in its folder until
            # the cooler is switched on the next time (seen in the emulator, tests/test_flash.py).
            self.left_behind[files[0]["id"]] = len(files)
            self.flash_writes += len(files)
        if up["stage"] in ("refused", "data") or not files or short:
            self.log.append(("upload called off", up["stage"]))
            return
        for f in files:
            try:
                img = Image.open(io.BytesIO(f["data"]))
                img.load()
                if img.size != (device.WIDTH, device.HEIGHT) or img.format != "JPEG":
                    self._violate(f"stored a {img.format} of {img.size}, the screen is {device.WIDTH}x{device.HEIGHT} JPEG")
            except OSError:
                self._violate("stored something that is not a readable image")
        file_id = files[0]["id"]
        if any(f["id"] != file_id for f in files):
            self._violate("one upload with several file ids")
        if all(f["type"] == device.FILE_JPG for f in files):
            if len(files) != 1:
                self._violate("several stills in one upload")
            self._store(self.stills, file_id, [file_id, files[-1]["data"]], "jpg")
        elif all(f["type"] == device.FILE_GIF for f in files) and file_id in self.left_behind:
            self._violate("an animation sent again after half of it was left on the card: its frames go into the "
                          "folder that is there, and the firmware lists it only after the cooler was off and on")
        elif all(f["type"] == device.FILE_GIF for f in files):
            if [f["index"] for f in files] != list(range(len(files))) or any(f["count"] != len(files) for f in files):
                self._violate("animation frames missing or out of order")
            if len({f["duration"] for f in files}) != 1:
                self._violate("animation frames disagree on the loop duration")
            self._store(self.gifs, file_id, [file_id, [f["data"] for f in files], files[0]["duration"]], "gif")
        else:
            self._violate("stills and animation frames mixed in one upload")
        self.flash_writes += len(files)

    def _store(self, slots: list, file_id: str, entry: list, kind: str) -> None:
        for i, slot in enumerate(slots):
            if slot[0] == file_id:                 # an id that exists is replaced in place
                slots[i] = entry
                self.log.append(("stored", kind, i))
                return
        if kind == "jpg" and len(slots) >= device.MAX_STILLS:
            self._violate(f"one still too many: the cooler keeps {device.MAX_STILLS} and drops the rest without a word")
            return
        slots.append(entry)
        self.log.append(("stored", kind, len(slots) - 1))
