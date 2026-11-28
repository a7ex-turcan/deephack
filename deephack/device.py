"""Driver for the DeepCool MYSTIQUE LCD (USB 3633:0009, WinUSB vendor interface).

Protocol reverse engineered from the official DeepCool app (v1.2.15) by hooking its USB layer.

Command frame (48 bytes, OUT ep 0x01 or 0x02, reply on the matching IN ep 0x81 / 0x82):

    AA 2E <cmd> <payload, zero padded to 39 bytes> 'H' 'I' 'D' 'C' <sum16 LE of bytes 0..45>

Reply is the same layout with 0x55 as first byte; payload[0] is a status byte (0 = ok).

Image upload (to on-device flash, addressed by a 32 char id; re-using an id overwrites in place):

    cmd 0x0F                       "start download", acked
    64 byte header                 "DCLd" type size:u32 sum16(data):u32 0*7 id[32] 0*10 sum16(header[:62]):u16
    raw JPEG in 64 byte packets    480x640 baseline JPEG, 4:2:0
    "dcldfinish" padded to 55      no reply; device commits to flash
    cmd 0x08 <type> <index>        show slot (type 0 = jpg, 1 = gif)

Animations ("GIFs") are a sequence of JPEG frames: one start command, then header + JPEG per frame with
type 2 and frame_count:u16 total_duration_ms:u16 frame_index:u16 at header offset 13, then one finish.
"""
from __future__ import annotations

import argparse
import io
import struct
import sys
import time

import libusb_package
import usb.core
import usb.util

VID, PID = 0x3633, 0x0009
WIDTH, HEIGHT = 480, 640

CMD_SENSORS = 0x01          # periodic sensor values (ep 2)
CMD_OPTIONS = 0x02          # device options: <?> <?> <?> <light source> <brightness>
CMD_MODE = 0x03             # display mode
CMD_SITUATION_MODE = 0x04
CMD_RECORDER_MODE = 0x05
CMD_REFRESH_RECORDER = 0x06
CMD_MOTION_MODE = 0x07      # <duration> <animation>
CMD_SHOW_SLOT = 0x08        # <type> <index>
CMD_DELETE_SLOT = 0x09      # <type> <index>
CMD_SET_TIME = 0x0A         # year:u16 month day hour minute second (ep 2)
CMD_START_DOWNLOAD = 0x0F
CMD_ROTATE_QUERY = 0x10
CMD_GET_UUID = 0x12
CMD_FACTORY_RESET = 0x13    # reboots, erases every stored image (cmd 12 returns junk until a power cycle)
CMD_DELETE_ALL = 0x14       # erases every stored image, no reboot

CMD_DIRECT = 0x20           # <size:u32> <sum16:u16>: show a JPEG without storing it. Not in the stock firmware:
                            # only one patched with tools/fw/patch.py has it (the stock one answers status 0)
DIRECT_GO, DIRECT_LATER, DIRECT_REFUSED, DIRECT_NO_PAGE = 0x10, 0x11, 0x12, 0x13
DIRECT_PARTS = 3            # the version of the patch from which a part of the picture can be drawn by itself
DIRECT_FAST = 9             # ... and from which the cooler takes a frame's bytes as fast as USB carries them
DIRECT_EVERY_TURN = 12      # ... and from which a frame is on the glass at the panel's next turn (see TURN)
TURN = 0.01805              # seconds from one picture on the cooler's panel to the next: 55.4 a second. Until
SLOW_TURN = 2 * TURN        # patch 12 a redraw took two of them: 27.7 pictures a second at the most
CMD_PEEK = 0x21             # <address:u32> <count:u8>: read memory. The patch's, from its version 4
PEEK_VERSION, PEEK_MOST = 4, 39
CMD_POKE = 0x22             # <address:u32> <count:u8> <value:u32>: write a word, read back. From its version 10
POKE_VERSION = 10
CMD_RELEASE = 0x23          # give the frame buffers back to the heap: an upload needs the room. From its version 15,
RELEASE_VERSION = 15        # answered as CMD_DIRECT is: DIRECT_GO when none is held, DIRECT_LATER when it is being done
CMD_LIGHT = 0x24            # the colours of the 14 lights on the pump head, which the cooler fades to. From its
LIGHT_VERSION = 16          # version 16; see light_packet
LIGHTS = 14                 # seven up the left side of the screen, then seven down the right
LIGHT_STEP = 0.016          # seconds between two steps of the cooler's fade
LIGHT_KEEP = 3.0            # seconds without the command after which the cooler picks the colours itself again
WRITABLE = ((0x2000_0000, 0x2001_0000), (0x8000_0000, 0x8080_0000))      # what poke may be asked for: RAM
READABLE = ((0x0000_0000, 0x0008_0000), (0x2000_0000, 0x2001_0000), (0x8000_0000, 0x8080_0000))
                            # what peek may be asked for: the chip's flash, its RAM, the SDRAM. An address
                            # that is not memory stops the cooler until it is switched off and on
PART_STEP = 16              # a part is so many pixels wide and high, or a multiple: whole blocks of a 4:2:0 JPEG
DIRECT_MAX = 128 * 1024     # bytes of JPEG the patched firmware takes for one frame
DIRECT_ASK = 0.004          # seconds between two asks while it says "later": it needs some 50 ms for a frame, and
                            # asking every 2 ms was 120 commands a second for 18 frames

TYPE_JPG, TYPE_GIF = 0, 1   # slot type in the show / delete commands
FILE_JPG, FILE_GIF = 1, 2   # file type in the upload header
FILE_FIRMWARE = 0           # ... and what the firmware takes for a firmware update: it stores the data as
                            # FW_update.bin and reboots into its bootloader. upload_header refuses it
MAX_GIF_DURATION_MS = 0xFFFF
MAX_STILLS = 9              # the firmware indexes nine stills (and nine animations). A tenth upload gets no
                            # error but is written without being indexed: never send one. Asking for a
                            # still that is not there does nothing. Webcam and docs/firmware-analysis.md.
MODE_SITUATIONAL = 1        # the firmware's own sensor dashboard, fed by CMD_SENSORS
MODE_MOTION = 2             # the mode in which stored images are displayed
MODE_RECORDER = 3           # the firmware's CPU clock / temperature recorder

# CMD_SENSORS payload: 3-byte fields, each <integer part:u16 LE> <fraction:u8> (the fraction byte is
# printed as-is after the decimal point). Confirmed with photos of the device: cpu_temp, ram_usage, the
# every named field below. The official app only ever filled the first seven in our captures (its fan
# and pump readouts were always zero); fan_rpm and pump_rpm were found by probing. field_9 / field_10
# have not shown up on any layout.
SENSOR_FIELDS = {"cpu_temp": 0, "cpu_load": 3, "ram_usage": 6, "v3_3": 9, "v5": 12, "v12": 15, "cpu_freq": 18,
                 "fan_rpm": 21, "pump_rpm": 24, "field_9": 27, "field_10": 30}
DASH_FREQUENCY, DASH_TIME, DASH_PUMP, DASH_FAN, DASH_FAN_PUMP, DASH_TEMPERATURE = range(6)
STRIP_VOLTAGE, STRIP_SYSTEM, STRIP_CORE = 0, 1, 2   # bottom strip of the dashboard
ANIMATION_NONE, ANIMATION_SLIDE, ANIMATION_FADE = 0, 1, 2
# What drives the light strip on the side of the pump head (fourth byte of CMD_OPTIONS; the app calls it
# rgbOptical): the motherboard's ARGB signal through the cooler's own ARGB cable, the cooler's fixed
# temperature warning colour, or the colours at the edges of the picture on screen, picked by the
# firmware whenever a stored image or animation is shown.
LIGHT_MOTHERBOARD, LIGHT_WARNING, LIGHT_SCREEN = 0, 1, 2


def sum16(data: bytes) -> int:
    return sum(data) & 0xFFFF


def frame(cmd: int, payload: bytes = b"") -> bytes:
    if len(payload) > 39:
        raise ValueError("payload too long")
    b = bytearray(48)
    b[0], b[1], b[2] = 0xAA, 0x2E, cmd
    b[3:3 + len(payload)] = payload
    b[42:46] = b"HIDC"
    struct.pack_into("<H", b, 46, sum16(b[:46]))
    return bytes(b)


def light_packet(colours, pace: int = 0, on: bool = True) -> bytes:
    """Command 24 of the patched firmware: where the 14 lights go, as one packet of 64 bytes. The command's
    own 48 hold 13 lights; the 14th, `on` and `pace` follow them. `colours`: 14 of (red, green, blue),
    0 to 255, as the lights are to show them (they are not gamma corrected by anyone after this). In the
    cooler's order: 0 at the bottom of the screen's left side, 6 at its top, 7 at the top of the right
    side, 13 at its bottom. `pace`: how much of the way that is left the lights cover every LIGHT_STEP,
    in 256ths (0: all of it at once). `on` False: the cooler picks the colours itself again."""
    flat = bytes(max(0, min(255, round(c))) for colour in colours for c in colour)
    if len(flat) != LIGHTS * 3:
        raise ValueError(f"need {LIGHTS} colours of three values")
    if not 0 <= pace <= 255:
        raise ValueError("the pace is 0 to 255")
    return frame(CMD_LIGHT, flat[:39]) + flat[39:] + bytes([1 if on else 0, pace]) + bytes(11)


def light_pace(seconds: float) -> int:
    """The pace at which the lights have covered two thirds of the way to a new colour after `seconds`
    (63 %: the fade is a share of what is left with every step, so it has no end to name)."""
    if seconds <= LIGHT_STEP:
        return 0
    return max(1, min(255, round(256 * LIGHT_STEP / seconds)))


def sensor_payload(**values: float) -> bytes:
    payload = bytearray(39)
    for key, value in values.items():
        hundredths = round(value * 100)
        if not 0 <= hundredths <= 0xFFFF * 100 + 99:
            raise ValueError(f"{key} out of range")
        struct.pack_into("<HB", payload, SENSOR_FIELDS[key], hundredths // 100, hundredths % 100)
    return bytes(payload)


def upload_header(file_id: str, data: bytes, ftype: int = FILE_JPG, frame_count: int = 0, duration_ms: int = 0,
                  frame_index: int = 0) -> bytes:
    """Header that precedes every uploaded JPEG. The three frame fields are zero for stills."""
    fid = file_id.encode("ascii")
    if len(fid) != 32:
        raise ValueError("file id must be exactly 32 ASCII characters")
    if ftype == FILE_FIRMWARE:
        raise ValueError("file type 0 is a firmware update, not a picture: the cooler would try to flash the data")
    h = bytearray(64)
    h[0:4] = b"DCLd"
    h[4] = ftype
    struct.pack_into("<I", h, 5, len(data))
    struct.pack_into("<I", h, 9, sum16(data))
    struct.pack_into("<HHH", h, 13, frame_count, duration_ms, frame_index)
    h[20:52] = fid
    struct.pack_into("<H", h, 62, sum16(h[:62]))
    return bytes(h)


class DeviceBusy(RuntimeError):
    pass


class Mystique:
    def __init__(self, timeout_ms: int = 2000):
        self.timeout = timeout_ms
        self.dev = libusb_package.find(idVendor=VID, idProduct=PID)
        if self.dev is None:
            raise RuntimeError("MYSTIQUE (3633:0009) not found on USB")
        try:
            usb.util.claim_interface(self.dev, 0)
        except (usb.core.USBError, NotImplementedError) as e:
            raise DeviceBusy(
                "could not claim the MYSTIQUE USB interface - is the DeepCool app still running? "
                f"It holds the device exclusively; quit it first. ({e})"
            ) from e

    def close(self) -> None:
        try:
            usb.util.release_interface(self.dev, 0)
        finally:
            usb.util.dispose_resources(self.dev)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- low level -------------------------------------------------------
    def command(self, cmd: int, payload: bytes = b"", ep: int = 1, reply: bool = True) -> bytes | None:
        self.dev.write(ep, frame(cmd, payload), self.timeout)
        return self._read_reply(cmd, ep) if reply else None

    def _read_reply(self, cmd: int, ep: int = 1) -> bytes:
        r = bytes(self.dev.read(0x80 | ep, 64, self.timeout))
        if len(r) != 48 or r[0] != 0x55 or r[2] != cmd:
            raise RuntimeError(f"unexpected reply to cmd {cmd:#04x}: {r.hex()}")
        if sum16(r[:46]) != struct.unpack_from("<H", r, 46)[0]:
            raise RuntimeError(f"bad checksum in reply to cmd {cmd:#04x}: {r.hex()}")
        return r[3:42]

    def _recover_image_upload(self, image: bytes, sent: int, cause: BaseException) -> None:
        # Imported lazily: firmware imports this module for the USB protocol helpers.
        from . import firmware

        if not firmware.end_upload(self, image, sent):
            raise RuntimeError(
                "the picture upload failed and the cooler could not be told that it is over; "
                "if it is still connected, switch it off and on before the next upload"
            ) from cause

    def _start_image_upload(self, first_image: bytes) -> None:
        # A start command that does not go out is the caller's error as it is: if it arrived all the
        # same, the firmware waits six seconds for a header and then gives up by itself. No marker is
        # sent after it: with no upload on, the firmware takes that packet and no command after it.
        packet = frame(CMD_START_DOWNLOAD)
        written = self.dev.write(1, packet, self.timeout)
        if written != len(packet):
            raise usb.core.USBError(f"short write of the upload-start command ({written}/{len(packet)} bytes)")
        try:
            self._read_reply(CMD_START_DOWNLOAD)
        except BaseException as error:
            self._recover_image_upload(first_image, 0, error)
            raise

    def _send_image_file(self, header: bytes, image: bytes) -> None:
        sent = 0
        try:
            written = self.dev.write(1, header, self.timeout)
            if written != len(header):
                raise usb.core.USBError(f"short upload-header write ({written}/{len(header)} bytes)")
            for offset in range(0, len(image), 64):
                packet = image[offset:offset + 64]
                written = self.dev.write(1, packet, self.timeout)
                if isinstance(written, int):
                    sent += max(0, min(written, len(packet)))
                if written != len(packet):
                    raise usb.core.USBError(f"short image-data write ({written}/{len(packet)} bytes)")
        except BaseException as error:
            # The last USB packet may have arrived even when the host saw an error. end_upload
            # checks both sent and sent + 64 before deciding that dcldfinish is safe.
            self._recover_image_upload(image, sent, error)
            raise

    def _finish_image_upload(self) -> None:
        # A marker whose write fails may have arrived all the same, and is not sent again: a second one
        # would come after the upload has ended, and the firmware takes no command after such a packet.
        finish = b"dcldfinish".ljust(55, b"\0")
        written = self.dev.write(1, finish, self.timeout)
        if written != len(finish):
            raise usb.core.USBError(f"short write of the final upload marker ({written}/{len(finish)} bytes)")

    # -- high level ------------------------------------------------------
    def uuid(self) -> str:
        return self.command(CMD_GET_UUID)[1:33].decode("ascii", "replace").rstrip("\0")

    def set_options(self, brightness: int = 70, light: int = LIGHT_WARNING) -> None:
        """Backlight brightness, 0 (off) to 100, and the light strip's source (LIGHT_*). The first three bytes
        are sent as the official app sends them (its names: noLoadScreen, gyroStatus, screenRotate); they
        showed no visible effect."""
        self.command(CMD_OPTIONS, bytes([1, 1, 0, light, max(0, min(100, brightness))]))

    def set_brightness(self, percent: int) -> None:
        self.set_options(percent)

    def set_mode(self, mode: int) -> None:
        self.command(CMD_MODE, bytes([mode]))

    def send_sensors(self, **values: float) -> None:
        """Feed live values to the firmware's sensor dashboard (not stored, so no flash wear). Keys: SENSOR_FIELDS.

        Values are sent with two decimals; which of them are visible depends on the dashboard layout
        selected on the cooler.
        """
        self.command(CMD_SENSORS, sensor_payload(**values), ep=2)

    def set_dashboard(self, main: int, style: int = 0, strip: int = STRIP_VOLTAGE, byte2: int = 0) -> None:
        """Layout of the sensor dashboard. main: DASH_* (0 frequency, 1 time, 2 pump, 3 CPU fan, 4 CPU fan +
        pump, 5 temperature). style (frequency only): 0 normal, 1 ring, 2 stopwatch. strip is the row at
        the bottom: voltage (3.3 / 5 / 12 V), system (frequency, CPU load, RAM) or core (frequency, RAM).
        byte2 sits between style and strip on the wire; 1 changed nothing visible."""
        self.command(CMD_SITUATION_MODE, bytes([main, style, byte2, strip]))

    def set_recorder(self, frequency_only: int = 0) -> None:
        """Graphs of the recorder mode: CPU frequency and temperature (0) or frequency only (1)."""
        self.command(CMD_RECORDER_MODE, bytes([1 if frequency_only else 0]))

    def set_slideshow(self, enabled: bool) -> None:
        """Cycle through all stored images (fade transition) or keep the selected one on screen.

        Payload is <duration> <animation>; animation 0 = none, 1 = slide, 2 = fade (names from the official UI).
        """
        self.command(CMD_MOTION_MODE, bytes([0, ANIMATION_FADE if enabled else ANIMATION_NONE]))

    def show_slot(self, index: int, ftype: int = TYPE_JPG) -> None:
        self.command(CMD_SHOW_SLOT, bytes([ftype, index]))

    def delete_slot(self, index: int, ftype: int = TYPE_JPG) -> None:
        self.command(CMD_DELETE_SLOT, bytes([ftype, index]))

    def set_time(self, t: time.struct_time | None = None) -> None:
        t = t or time.localtime()
        self.command(CMD_SET_TIME, struct.pack("<HBBBBB", t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec), ep=2)

    def upload_jpeg(self, file_id: str, jpeg: bytes) -> None:
        """Store a 480x640 baseline JPEG under file_id (overwrites if the id already exists)."""
        if jpeg[:2] != b"\xff\xd8" or jpeg[-2:] != b"\xff\xd9":
            raise ValueError("not a JPEG")
        # Build the header before announcing an upload: invalid ids must not leave the cooler waiting.
        header = upload_header(file_id, jpeg)
        self.make_room()
        self._start_image_upload(jpeg)
        self._send_image_file(header, jpeg)
        self._finish_image_upload()
        time.sleep(1.0)  # device writes to flash; the official app also waits here

    def upload_gif(self, file_id: str, frames: list[bytes], duration_ms: int) -> None:
        """Store an animation: a list of 480x640 JPEG frames that loops over duration_ms in total."""
        if not frames or not 0 < duration_ms <= MAX_GIF_DURATION_MS:
            raise ValueError("need at least one frame and a duration of 1..65535 ms")
        if len(frames) > 0xFFFF:
            raise ValueError("an animation cannot have more than 65535 frames")

        # Validate and build every frame header before CMD_START_DOWNLOAD. A bad later frame must
        # not strand the cooler midway through an animation.
        files = []
        for i, jpeg in enumerate(frames):
            if jpeg[:2] != b"\xff\xd8" or jpeg[-2:] != b"\xff\xd9":
                raise ValueError("not a JPEG")
            header = upload_header(file_id, jpeg, FILE_GIF, len(frames), duration_ms, i)
            files.append((header, jpeg))

        self.make_room()
        self._start_image_upload(files[0][1])
        for header, jpeg in files:
            self._send_image_file(header, jpeg)
        self._finish_image_upload()
        time.sleep(1.0)

    # -- direct drawing (patched firmware only) ---------------------------
    def _ask_direct(self, size: int, checksum: int, box: tuple[int, int, int, int] | None = None) -> tuple[int, int]:
        """Ask to send a frame; the firmware's answer (DIRECT_*, or 0 from a stock firmware) and the byte
        after it, which is the version of the patch (0 from the first one and from a stock firmware).
        `box`: (x, y, width, height) of a part. Without it the four are zeros, which says "the whole page"."""
        payload = struct.pack("<IH", size, checksum) + (struct.pack("<4H", *box) if box else b"")
        self.dev.write(1, frame(CMD_DIRECT, payload), self.timeout)
        r = bytes(self.dev.read(0x81, 64, self.timeout))
        if len(r) != 48 or r[0] != 0x55 or sum16(r[:46]) != struct.unpack_from("<H", r, 46)[0]:
            raise RuntimeError(f"unexpected reply to cmd {CMD_DIRECT:#04x}: {r.hex()}")
        return r[3], r[4]

    def _direct(self, size: int, checksum: int, box: tuple[int, int, int, int] | None = None) -> int:
        return self._ask_direct(size, checksum, box)[0]

    def draw_version(self) -> int:
        """Which direct drawing patch the cooler's firmware has: 0 for none (DeepCool's firmware), else the
        patch's version (tools/fw/patch.py, CHANGES). Asks for an impossible frame: a patched firmware
        refuses it, the stock one says 'ok' as it does to anything it does not know."""
        status, version = self._ask_direct(0, 0)
        return max(1, version) if status == DIRECT_REFUSED else 0

    def make_room(self, patience: float = 1.0) -> bool:
        """Have a patched firmware give its three frame buffers back to the heap, before an upload. The
        stock firmware puts an upload (a picture, or a firmware) into 2 MiB of its heap in one piece, after
        its "Loading" screen has taken nearly 3 MB of it, and gives the upload up without a word when no
        such piece is left: with the patch's buffers and a stored picture of 60 KB there was none.

        True when no buffer is held any more (the next frame makes them again; if a drawn picture was on
        show, the cooler shows deephack's own in its place). False from a firmware without the command:
        the stock one, or one patched before RELEASE_VERSION. Patch 15 and later also do this by
        themselves when an upload is announced, for other programs; asking first leaves nothing to the
        order in which the firmware does things."""
        for _ in range(max(1, round(patience / DIRECT_ASK))):
            self.dev.write(1, frame(CMD_RELEASE), self.timeout)
            r = bytes(self.dev.read(0x81, 64, self.timeout))
            if len(r) != 48 or r[0] != 0x55 or sum16(r[:46]) != struct.unpack_from("<H", r, 46)[0]:
                raise RuntimeError(f"unexpected reply to cmd {CMD_RELEASE:#04x}: {r.hex()}")
            if r[3] != DIRECT_LATER:
                return r[3] == DIRECT_GO
            time.sleep(DIRECT_ASK)
        return False

    def peek(self, address: int, count: int) -> bytes:
        """`count` bytes of the cooler's memory from `address` (patch version 4). Only its flash and RAM:
        READABLE. Raises ValueError for anything else, RuntimeError on a firmware without the command."""
        if not any(low <= address and address + count <= high for low, high in READABLE) or count < 0:
            raise ValueError(f"{count} bytes at {address:#x} are not all memory the cooler can be asked for")
        out = b""
        while len(out) < count:
            n = min(PEEK_MOST, count - len(out))
            self.dev.write(1, frame(CMD_PEEK, struct.pack("<IB", address + len(out), n)), self.timeout)
            r = bytes(self.dev.read(0x81, 64, self.timeout))
            if len(r) != 48 or r[0] != 0x55 or r[2] != CMD_PEEK or sum16(r[:46]) != struct.unpack_from("<H", r, 46)[0]:
                raise RuntimeError("this firmware cannot be asked for its memory" if len(r) == 48 and r[2] == 0
                                   else f"unexpected reply to cmd {CMD_PEEK:#04x}: {r.hex()}")
            out += r[3:3 + n]
        return out

    def poke(self, address: int, value: int) -> int:
        """Write a 32-bit word into the cooler's RAM (patch version 10) and return what is there after.
        For trying a setting on the running firmware; it lasts until the cooler starts again. Raises
        ValueError for an address that is not RAM: a wrong word in the wrong place stops the cooler."""
        if not any(low <= address and address + 4 <= high for low, high in WRITABLE):
            raise ValueError(f"{address:#x} is not RAM the cooler can be told to write")
        self.dev.write(1, frame(CMD_POKE, struct.pack("<IBI", address, 4, value & 0xFFFFFFFF)), self.timeout)
        r = bytes(self.dev.read(0x81, 64, self.timeout))
        if len(r) != 48 or r[0] != 0x55 or r[2] != CMD_POKE or sum16(r[:46]) != struct.unpack_from("<H", r, 46)[0]:
            raise RuntimeError("this firmware cannot be told to write its memory" if len(r) == 48 and r[2] == 0
                               else f"unexpected reply to cmd {CMD_POKE:#04x}: {r.hex()}")
        return struct.unpack_from("<I", r, 3)[0]

    def set_light(self, colours, pace: int = 0) -> bool:
        """Have the 14 lights on the pump head go to these colours (see light_packet), which they show for
        as long as this is sent again within LIGHT_KEEP seconds and the cooler's light follows the screen
        (set_options with LIGHT_SCREEN). False from a firmware without the command: the stock one, or one
        patched before LIGHT_VERSION."""
        return self._light(light_packet(colours, pace))

    def release_light(self) -> bool:
        """The cooler picks the lights' colours itself again, at once."""
        return self._light(light_packet([(0, 0, 0)] * LIGHTS, on=False))

    def _light(self, packet: bytes) -> bool:
        self.dev.write(1, packet, self.timeout)
        r = bytes(self.dev.read(0x81, 64, self.timeout))
        if len(r) != 48 or r[0] != 0x55 or sum16(r[:46]) != struct.unpack_from("<H", r, 46)[0]:
            raise RuntimeError(f"unexpected reply to cmd {CMD_LIGHT:#04x}: {r.hex()}")
        return r[3] == DIRECT_GO and r[4] >= LIGHT_VERSION

    def can_draw(self) -> bool:
        """True when the cooler runs a firmware that draws without storing."""
        return self.draw_version() > 0

    def draw_jpeg(self, jpeg: bytes, patience: float = 0.5, at: tuple[int, int] | None = None) -> None:
        """Show a 480x640 baseline JPEG now, without storing it: no flash write. Needs the patched firmware
        and the image mode with a stored still on show (the frame replaces it on screen until the next
        show_slot). Raises TimeoutError when the cooler is still busy with the last frame after `patience`
        seconds, RuntimeError on a firmware that cannot do this (nothing is sent to it then).

        `at`: (x, y), and the JPEG is **a part of the picture**: it is put there, on top of the page that
        was drawn last, and stays until the next part or page (patch version DIRECT_PARTS or later; ask
        draw_version()). Its width and height are multiples of PART_STEP. Raises NoPage when the page under
        it is not one that was drawn (a stored picture is on show, or nothing was drawn yet): draw the
        page, then the part."""
        box = None
        if at is None:
            if jpeg_size(jpeg) != (WIDTH, HEIGHT):
                raise ValueError(f"need a {WIDTH}x{HEIGHT} baseline JPEG")
        else:
            box = part_box(jpeg, at)
        if len(jpeg) > DIRECT_MAX:
            raise ValueError(f"frame too large: {len(jpeg)} bytes, the firmware takes {DIRECT_MAX}")
        for _ in range(max(1, round(patience / DIRECT_ASK))):
            status = self._direct(len(jpeg), sum16(jpeg), box)
            if status == DIRECT_GO:
                break
            if status == DIRECT_NO_PAGE:
                raise NoPage("the page under the part is not one that was drawn")
            if status != DIRECT_LATER:
                raise RuntimeError("this firmware cannot draw without storing" if status == 0
                                   else f"the cooler refused the frame (status {status:#04x})")
            time.sleep(DIRECT_ASK)
        else:
            raise TimeoutError("the cooler did not take the frame")
        self.dev.write(1, jpeg, self.timeout)       # the host controller cuts it into 64 byte packets


class NoPage(RuntimeError):
    """A part of the picture was to be drawn, and the page under it is not one that was drawn."""


def part_box(jpeg: bytes, at: tuple[int, int]) -> tuple[int, int, int, int]:
    """(x, y, width, height) of a part that is this JPEG, put at `at`. Raises ValueError for one the cooler
    must not be sent. The size is read from the JPEG itself, because the cooler decodes what the JPEG says
    into the place the command names: a JPEG larger than its command would be written over what follows
    the frame buffer in the cooler's memory."""
    size = jpeg_size(jpeg)
    if size is None:
        raise ValueError("need a baseline JPEG")
    (x, y), (width, height) = at, size
    if width % PART_STEP or height % PART_STEP or not width or not height:
        raise ValueError(f"a part is a multiple of {PART_STEP} pixels wide and high, not {width}x{height}")
    if x < 0 or y < 0 or x + width > WIDTH or y + height > HEIGHT:
        raise ValueError(f"a part of {width}x{height} at {x}, {y} is not inside the screen")
    return x, y, width, height


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) of a baseline JPEG, None for anything else (progressive, truncated, not a JPEG)."""
    if data[:2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9":
        return None
    at = 2
    while at + 9 <= len(data) and data[at] == 0xFF:
        marker, length = data[at + 1], struct.unpack_from(">H", data, at + 2)[0]
        if marker == 0xC0:
            height, width = struct.unpack_from(">HH", data, at + 5)
            return width, height
        if marker == 0xDA or 0xC1 <= marker <= 0xCF and marker not in (0xC4, 0xCC):
            return None                              # the picture starts, or another kind of JPEG
        at += 2 + length
    return None


def encode_jpeg(image, quality: int = 92, part: bool = False, tuned: bool = False) -> bytes:
    """Encode a PIL image the way the official app does: 480x640, baseline, 4:2:0, default Huffman tables.
    `part`: the image is a part of the picture and keeps its size (see Mystique.draw_jpeg).

    `tuned`: with Huffman tables made for this picture instead of the default ones. The same pixels in
    fewer bytes: 3 to 15 % fewer for a busy picture, a quarter for one with flat areas, 60 % for an empty
    screen (which is 2 KB then, not 5.4). The cooler's decoder is programmed from the file's tables, and
    gives byte for byte the same frame buffer for either (read back from the cooler for 21 pictures at
    several qualities and ten parts, 24 Nov 2026). It costs half a millisecond more to encode. For
    pictures that are drawn; what is stored on the cooler stays as DeepCool's app would write it."""
    from PIL import Image

    if image.size != (WIDTH, HEIGHT) and not part:
        image = image.resize((WIDTH, HEIGHT), Image.LANCZOS)
    buf = io.BytesIO()
    image.convert("RGB").save(buf, "JPEG", quality=quality, subsampling="4:2:0", optimize=tuned, progressive=False)
    return buf.getvalue()


def _main() -> int:
    ap = argparse.ArgumentParser(prog="python -m deephack.device", description="DeepCool MYSTIQUE LCD tool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info", help="print device UUID")
    p = sub.add_parser("upload", help="upload an image file to a slot id and show it")
    p.add_argument("image")
    p.add_argument("--id", required=True, help="32 character file id")
    p.add_argument("--index", type=int, help="slot index to show afterwards")
    p = sub.add_parser("show", help="show a stored slot")
    p.add_argument("index", type=int)
    p.add_argument("--gif", action="store_true")
    p = sub.add_parser("delete", help="delete a stored slot")
    p.add_argument("index", type=int)
    p.add_argument("--gif", action="store_true")
    p = sub.add_parser("probe-sensors", help="show the firmware's sensor dashboard fed with one recognisable number per field")
    p.add_argument("--seconds", type=int, default=120)
    p.add_argument("--mode", type=int, default=MODE_SITUATIONAL, choices=(MODE_SITUATIONAL, MODE_RECORDER))
    p = sub.add_parser("map-dashboards", help="step through the sensor dashboard layouts with test values (beeps at each step)")
    p.add_argument("--hold", type=int, default=15, help="seconds per layout")
    a = ap.parse_args()

    with Mystique() as m:
        if a.cmd == "map-dashboards":
            import winsound

            probe = {"cpu_load": 22, "ram_usage": 63, "v3_3": 3.33, "v5": 5.05, "v12": 12.12, "cpu_freq": 4.44,
                     "fan_rpm": 1111, "pump_rpm": 2222, "field_9": 3333, "field_10": 4444}
            steps = [  # (main, style, strip, byte2); cpu_temp is fed as 10 + step to tell photos apart
                (DASH_TEMPERATURE, 0, STRIP_VOLTAGE, 0), (DASH_TEMPERATURE, 0, STRIP_SYSTEM, 0),
                (DASH_TEMPERATURE, 0, STRIP_CORE, 0), (DASH_FREQUENCY, 0, STRIP_SYSTEM, 0),
                (DASH_TIME, 0, STRIP_SYSTEM, 0), (DASH_FAN_PUMP, 0, STRIP_SYSTEM, 0),
            ]
            print("feeding:", probe)
            m.set_time()
            m.set_mode(MODE_SITUATIONAL)
            try:
                for n, step in enumerate(steps, 1):
                    m.set_dashboard(*step)
                    print(f"step {n:2d}/{len(steps)}: main={step[0]} style={step[1]} strip={step[2]} byte2={step[3]}", flush=True)
                    for i in range(a.hold):
                        m.send_sensors(cpu_temp=10 + n, **probe)
                        if i == 1:
                            winsound.Beep(1200 if n % 2 else 900, 180)   # the layout has settled: photo time
                        time.sleep(1)
            finally:
                m.set_dashboard(DASH_TEMPERATURE, 1)    # the layout the cooler had before
                m.set_mode(MODE_MOTION)
                winsound.Beep(600, 500)
            return 0
        if a.cmd == "probe-sensors":
            probe = {"cpu_temp": 51, "cpu_load": 22, "ram_usage": 63, "v3_3": 3.33, "v5": 5.05, "v12": 12.12, "cpu_freq": 4.44,
                     "fan_rpm": 1111, "pump_rpm": 2222}
            print("feeding:", probe)
            m.set_mode(a.mode)
            try:
                for _ in range(a.seconds):
                    m.send_sensors(**probe)
                    time.sleep(1)
            finally:
                m.set_mode(MODE_MOTION)
            return 0
        if a.cmd == "info":
            print("uuid:", m.uuid())
        elif a.cmd == "upload":
            from PIL import Image

            jpeg = encode_jpeg(Image.open(a.image))
            t = time.time()
            m.upload_jpeg(a.id, jpeg)
            print(f"uploaded {len(jpeg)} bytes in {time.time() - t:.2f}s")
            if a.index is not None:
                m.show_slot(a.index)
        elif a.cmd == "show":
            m.show_slot(a.index, TYPE_GIF if a.gif else TYPE_JPG)
        elif a.cmd == "delete":
            m.delete_slot(a.index, TYPE_GIF if a.gif else TYPE_JPG)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(_main())
    except DeviceBusy as e:
        sys.exit(f"error: {e}")
