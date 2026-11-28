"""The emulator's own building blocks that need no emulator: the FAT image, ui.bin, the USB controller."""
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "emu"))
import fat  # noqa: E402
import uibin  # noqa: E402
import usbdev  # noqa: E402


def test_fat_image_reads_back_what_was_put_in():
    files = {
        "ui.bin": bytes(range(256)) * 40,                       # several clusters
        "SynwitManifest.cfg": b"hello\n",                       # needs a long name
        "IMG/000_0123456789abcdef0123456789abcdef/angle_0.jpg": b"\xff\xd8 picture \xff\xd9",
        "EMPTY.TXT": b"",
    }
    assert fat.read(fat.build(files)) == files


def test_a_short_name_in_small_letters_is_read_as_it_was_written():
    """The firmware's FatFs writes "index000.jpg" as INDEX000.JPG and two bits. Its player counts the
    frames of an animation by their names, so a card built from the names in capitals plays one frame."""
    image = bytearray(fat.build({"INDEX000.JPG": b"a frame", "CONFIG.CFG": b"x"}))
    image[image.index(b"INDEX000JPG") + 12] = 0x18                 # stem and ending in small letters
    image[image.index(b"CONFIG  CFG") + 12] = 0x10                 # the ending only
    assert fat.read(bytes(image)) == {"index000.jpg": b"a frame", "CONFIG.cfg": b"x"}
    assert fat.read(fat.build(fat.read(bytes(image)))) == fat.read(bytes(image))


def test_fat_image_is_a_fat16_volume():
    image = fat.build({"A.TXT": b"a"}, megabytes=16)
    assert len(image) == 16 * 1024 * 1024
    assert image[510:512] == b"\x55\xaa" and image[54:59] == b"FAT16"


def test_ui_bin_header_points_at_its_tables():
    ui = uibin.build({1: uibin.screen(), 0x2C: uibin.screen(children=[uibin.label(0x4A2, "hi", (5, 6, 70, 8))])}, start=1)
    assert ui[:9] == b"SynwitUI\0"
    assert struct.unpack_from("<II", ui, 0x10) == uibin.FORMAT
    screen_table, widgets, resources = struct.unpack_from("<III", ui, 0x1C)
    assert struct.unpack_from("<III", ui, screen_table) == (2, 1, 0x2C)
    assert struct.unpack_from("<H", ui, widgets + 0x0A)[0] == 1                 # the screen to start with
    count, first_id, first_offset, second_id, second_offset = struct.unpack_from("<IIIII", ui, widgets + 12)
    assert (count, first_id, second_id) == (2, 1, 0x2C)
    assert ui[resources:resources + 6] == b"RESLD\0"
    # a widget: size, type, id; then its strings and its children
    size, kind, wid = struct.unpack_from("<IB3xI", ui, first_offset)
    assert (size, uibin.TYPES[kind], wid) == (0x60, "screen", 1)
    size, kind, wid = struct.unpack_from("<IB3xI", ui, second_offset)
    children_at = second_offset + size + 8                                      # no strings on a screen
    assert struct.unpack_from("<I", ui, children_at)[0] == 1
    child = struct.unpack_from("<I", ui, children_at + 4)[0]
    size, kind, wid = struct.unpack_from("<IB3xI", ui, child)
    assert (size, uibin.TYPES[kind], wid) == (0x130, "label", 0x4A2)
    assert struct.unpack_from("<BB", ui, child + 0x45) == (1, 1)                # visible, enabled
    assert struct.unpack_from("<4h", ui, child + 0x48) == (5, 6, 70, 8)         # left, top, width, height
    assert struct.unpack_from("<II", ui, child + size) == (1, 0)                # one string
    assert ui[child + size + 12:child + size + 15] == b"hi\0"


def test_stock_ui_has_every_screen_the_firmware_registers():
    ui = uibin.stock()
    screen_table = struct.unpack_from("<I", ui, 0x1C)[0]
    count = struct.unpack_from("<I", ui, screen_table)[0]
    assert struct.unpack_from(f"<{count}I", ui, screen_table + 4) == uibin.SCREENS and count == 32


@pytest.fixture
def usb():
    device = usbdev.UsbDevice(0x40005000)
    device.write(usbdev.DEVIE, 0x49, 4)
    device.write(usbdev.EPIE, 0x70007, 4)
    return device


def test_usb_out_packet_waits_until_the_firmware_arms_the_endpoint(usb):
    usb.send(1, b"\xaa\x2e" + bytes(46))
    assert not usb.interrupt() and usb.events                                   # NAK
    usb.write(usbdev.OUTEP + 0x10, usbdev.READY, 4)
    assert usb.interrupt()
    assert usb.read(usbdev.EPIF) == 1 << 17
    assert usb.read(usbdev.RXSR) == 48 << 22 | 1 << 16 | usbdev.SUCC | usbdev.DONE
    assert bytes(usb.mem[usbdev.RXBUF:usbdev.RXBUF + 2]) == b"\xaa\x2e"
    usb.write(usbdev.RXSR, usbdev.DONE, 4)                                      # what the handler does
    assert usb.read(usbdev.EPIF) == 0 and usb.read(usbdev.RXSR) & usbdev.SUCC
    usb.send(1, b"next")
    assert not usb.interrupt()                                                  # not armed again yet


def test_usb_in_packet_is_what_the_firmware_put_in_the_buffer(usb):
    for i, word in enumerate(struct.unpack("<2I", b"\x55\x2e\x12\x00abcd")):
        usb.write(usbdev.TXBUF + 0x400 + 4 * i, word, 4)
    usb.write(usbdev.INEP + 0x10 + 0xC, 8, 4)                                   # TXTRSZ
    usb.write(usbdev.INEP + 0x10, usbdev.READY, 4)                              # TXCR
    assert usb.read(usbdev.EPIF) == 1 << 1 and usb.interrupt()
    usb.write(usbdev.INEP + 0x10 + 4, 0xA, 4)                                   # the handler clears TXSR
    assert usb.read(usbdev.EPIF) == 0
    assert usb.take(1) == b"\x55\x2e\x12\x00abcd" and usb.take(1) is None


def test_usb_setup_packet_stands_until_its_status_is_cleared(usb):
    usb.reset()
    usb.setup(bytes([0x80, 6, 0, 1, 0, 0, 18, 0]))
    assert usb.interrupt() and usb.read(usbdev.DEVIF) == usbdev.IF_RST
    usb.write(usbdev.DEVIF, usbdev.IF_RST, 4)
    assert usb.interrupt() and usb.read(usbdev.DEVIF) == usbdev.IF_SETUP
    assert bytes(usb.mem[usbdev.SETUPD1:usbdev.SETUPD1 + 8]) == bytes([0x80, 6, 0, 1, 0, 0, 18, 0])
    usb.write(usbdev.SETUPSR, usbdev.DONE, 4)
    assert usb.read(usbdev.DEVIF) == 0 and not usb.interrupt()


class Ram:
    """Stands in for the machine's memory helper: memory(address, count) reads, memory(address, bytes) writes."""

    def __init__(self, base: int, size: int):
        self.base, self.data = base, bytearray(size)

    def __call__(self, address: int, data):
        at = address - self.base
        if isinstance(data, int):
            return bytes(self.data[at:at + data])
        self.data[at:at + len(data)] = data
        return None


def _jpeg(size=(16, 8), colour=(255, 0, 0)) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, "JPEG", quality=95, subsampling="4:2:0")
    return buf.getvalue()


def test_jpeg_decoder_puts_the_picture_where_the_firmware_asked():
    import jpegdec

    ram = Ram(0x80000000, 0x10000)
    decoder = jpegdec.JpegDecoder(0x4000B000, ram)
    file = _jpeg()
    scan = file.index(b"\xff\xda")
    scan += 2 + struct.unpack_from(">H", file, scan + 2)[0]                     # the data after the scan header
    ram(0x80001000, file)
    out, stride_words = 0x80008000, 10                                          # lines 40 bytes apart, 32 used
    for offset, value in ((jpegdec.IMGSIZ, 7 << 16 | 15), (jpegdec.CSBASE, 0x80001000 + scan),
                          (jpegdec.CODLEN, len(file) - scan - 2), (jpegdec.RGBASE, out), (jpegdec.IMGSTR, stride_words)):
        decoder.write(offset, value, 4)
    decoder.write(jpegdec.CR, 0x21, 4)
    assert decoder.errors == [] and decoder.decoded == [(out, 16, 8)]
    assert decoder.read(jpegdec.SR) == 0
    for row in (0, 7):
        line = ram(out + row * 40, 40)
        red, = struct.unpack_from("<H", line, 0)
        assert red >> 11 >= 30 and red & 0x7FF < 0x100                          # red, in RGB565
        assert line[32:] == bytes(8)                                            # the gap between lines is left alone


def test_jpeg_decoder_reports_a_file_it_cannot_decode():
    import jpegdec

    ram = Ram(0x80000000, 0x10000)
    decoder = jpegdec.JpegDecoder(0x4000B000, ram)
    decoder.write(jpegdec.CSBASE, 0x80001000, 4)
    decoder.write(jpegdec.CODLEN, 64, 4)
    decoder.write(jpegdec.CR, 0x21, 4)
    assert decoder.decoded == [] and "no JPEG header" in decoder.errors[0]
