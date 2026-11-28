"""The model itself: the real driver passes it, and it catches what is known to go wrong."""
import io
import struct

import pytest
import usb.core
from PIL import Image

from deephack import device
from deephack.config import GIF_SLOT_ID, SLOT_ID

JPEG = device.encode_jpeg(Image.new("RGB", (480, 640), "red"))


def test_the_driver_speaks_the_protocol(cooler):
    with device.Mystique() as m:
        assert m.uuid() == cooler.uuid
        m.set_mode(device.MODE_MOTION)
        m.upload_jpeg(SLOT_ID, JPEG)
        m.show_slot(1, device.TYPE_JPG)
        m.upload_gif(GIF_SLOT_ID, [JPEG, device.encode_jpeg(Image.new("RGB", (480, 640), "blue"))], 1000)
        m.show_slot(0, device.TYPE_GIF)
        m.upload_jpeg(SLOT_ID, device.encode_jpeg(Image.new("RGB", (480, 640), (0, 255, 0))))  # same id: in place
        m.set_options(70, device.LIGHT_SCREEN)
        m.send_sensors(cpu_temp=55)
        m.set_time()
    assert len(cooler.stills) == 2 and cooler.still(1).getpixel((10, 10))[1] > 200        # replaced, not added
    assert len(cooler.gifs) == 1 and len(cooler.gifs[0][1]) == 2 and cooler.gifs[0][2] == 1000
    assert cooler.screen == ("gif", 0) and cooler.flash_writes == 4 and cooler.light == device.LIGHT_SCREEN
    assert cooler.sensors[:3] == bytes([55, 0, 0]) and cooler.clock[0] >= 2026


def _violations(cooler, action):
    with device.Mystique() as m:
        try:
            action(m)
        except RuntimeError:
            pass                                    # the driver also notices some of these
    found, cooler.violations[:] = list(cooler.violations), []
    return found


def test_it_catches_an_unfinished_upload(cooler):
    def unfinished(m):
        m.command(device.CMD_START_DOWNLOAD)
        m.dev.write(1, device.upload_header(SLOT_ID, JPEG), 1000)
        m.dev.write(1, JPEG[:64], 1000)
        m.set_mode(device.MODE_MOTION)              # a command before dcldfinish
    assert any("before dcldfinish" in v for v in _violations(cooler, unfinished))


def test_a_failed_upload_header_is_called_off_and_the_next_upload_works(cooler, monkeypatch):
    real_write = cooler.write
    failed = [False]

    def interrupted_write(ep, data, timeout=None):
        up = cooler._upload
        if (not failed[0] and up is not None and up["stage"] == "header" and
                len(data) == 64 and data[:4] == b"DCLd"):
            failed[0] = True
            raise RuntimeError("simulated upload-header failure")
        return real_write(ep, data, timeout)

    monkeypatch.setattr(cooler, "write", interrupted_write)
    with device.Mystique() as m:
        with pytest.raises(RuntimeError, match="simulated upload-header failure"):
            m.upload_jpeg("f" * 32, JPEG)
        assert cooler._upload is None
        assert cooler.log[-1] == ("upload called off", "header")

        monkeypatch.setattr(cooler, "write", real_write)
        m.upload_jpeg("g" * 32, JPEG)

    assert [slot[0] for slot in cooler.stills] == ["app-still-0", "g" * 32]
    assert cooler.flash_writes == 1


def test_a_start_reply_read_error_is_recovered_before_the_next_upload(cooler, monkeypatch):
    real_read = cooler.read
    failed = [False]

    def failed_start_reply_read(ep, size, timeout=None):
        if (not failed[0] and cooler.log and cooler.log[-1][0] == "cmd" and
                cooler.log[-1][1] == device.CMD_START_DOWNLOAD):
            failed[0] = True
            real_read(ep, size, timeout)  # consume the reply before simulating a transport error
            raise RuntimeError("simulated start-reply read error")
        return real_read(ep, size, timeout)

    monkeypatch.setattr(cooler, "read", failed_start_reply_read)
    with device.Mystique() as m:
        with pytest.raises(RuntimeError, match="simulated start-reply read error"):
            m.upload_jpeg("h" * 32, JPEG)
        assert cooler._upload is None
        assert cooler.log[-1] == ("upload called off", "header")

        monkeypatch.setattr(cooler, "read", real_read)
        m.upload_jpeg("i" * 32, JPEG)

    assert [slot[0] for slot in cooler.stills] == ["app-still-0", "i" * 32]
    assert cooler.flash_writes == 1


def test_an_interrupted_still_upload_is_called_off_and_the_next_upload_works(cooler, monkeypatch):
    real_write = cooler.write
    data_packets = [0]

    def interrupted_write(ep, data, timeout=None):
        up = cooler._upload
        if (up is not None and up["stage"] == "data" and
                up.get("current", {}).get("type") == device.FILE_JPG and not data.startswith(b"dcldfinish")):
            data_packets[0] += 1
            if data_packets[0] == 3:
                raise RuntimeError("simulated interrupted image transfer")
        return real_write(ep, data, timeout)

    monkeypatch.setattr(cooler, "write", interrupted_write)
    with device.Mystique() as m:
        with pytest.raises(RuntimeError, match="simulated interrupted image transfer"):
            m.upload_jpeg("a" * 32, JPEG)
        assert cooler._upload is None
        assert cooler.log[-1] == ("upload called off", "data")

        monkeypatch.setattr(cooler, "write", real_write)
        m.upload_jpeg("b" * 32, JPEG)

    assert [slot[0] for slot in cooler.stills] == ["app-still-0", "b" * 32]
    assert cooler.flash_writes == 1


def test_an_interrupted_gif_upload_is_no_animation_but_leaves_its_whole_frames(cooler, monkeypatch):
    """The firmware writes each frame as it arrives: calling the upload off lists no animation, and the
    frames that came whole stay on the card until the cooler is switched on again (tests/test_flash.py).
    The same animation sent again goes into that folder and is not listed either: the model says so."""
    real_write = cooler.write
    second_frame_packets = [0]
    second = device.encode_jpeg(Image.new("RGB", (480, 640), "blue"))

    def interrupted_write(ep, data, timeout=None):
        up = cooler._upload
        current = up.get("current", {}) if up is not None else {}
        if (up is not None and up["stage"] == "data" and current.get("type") == device.FILE_GIF and
                current.get("index") == 1 and not data.startswith(b"dcldfinish")):
            second_frame_packets[0] += 1
            if second_frame_packets[0] == 3:
                raise RuntimeError("simulated second-frame interruption")
        return real_write(ep, data, timeout)

    monkeypatch.setattr(cooler, "write", interrupted_write)
    with device.Mystique() as m:
        with pytest.raises(RuntimeError, match="simulated second-frame interruption"):
            m.upload_gif("c" * 32, [JPEG, second], 1000)
        assert cooler._upload is None
        assert cooler.gifs == [] and cooler.left_behind == {"c" * 32: 1}
        assert cooler.log[-1] == ("upload called off", "data")

        monkeypatch.setattr(cooler, "write", real_write)
        m.upload_jpeg("d" * 32, JPEG)
        assert [slot[0] for slot in cooler.stills] == ["app-still-0", "d" * 32]
        assert cooler.gifs == [] and cooler.flash_writes == 2 and not cooler.violations

    again = _violations(cooler, lambda m: m.upload_gif("c" * 32, [JPEG, second], 1000))
    assert cooler.gifs == [] and any("after half of it was left" in v for v in again)


def test_an_animation_stored_under_an_id_that_is_there_keeps_the_first_ones_pace(cooler):
    """The firmware writes the frame count and the loop's time when it makes the folder, and for an id that
    is there it replaces the frames and nothing else (#66)."""
    blue = device.encode_jpeg(Image.new("RGB", (480, 640), "blue"))
    with device.Mystique() as m:
        m.upload_gif("7" * 32, [JPEG, blue], 1000)                        # 500 ms a frame
        m.upload_gif("7" * 32, [blue, JPEG, blue, JPEG], 2000)            # the same pace: nothing wrong
    assert len(cooler.gifs) == 1 and len(cooler.gifs[0][1]) == 4 and cooler.gifs[0][2] == 2000
    seen = _violations(cooler, lambda m: m.upload_gif("7" * 32, [JPEG, blue, JPEG], 600))
    assert any("keeps the pace" in v for v in seen)
    assert len(cooler.gifs[0][1]) == 3 and cooler.gifs[0][2] == 1500      # three frames, at 500 ms each
    with device.Mystique() as m:
        m.set_mode(device.MODE_MOTION)
        m.delete_slot(0, device.TYPE_GIF)                                 # gone, folder and all: the id is new again
        m.upload_gif("7" * 32, [JPEG, blue, JPEG], 600)
    assert cooler.gifs[0][2] == 600


def test_a_short_write_is_an_error_of_usb_and_the_upload_is_called_off(cooler, monkeypatch):
    """The engine lets go of the cooler on usb.core.USBError and RuntimeError and on nothing else: a write
    that took fewer bytes than it was given must be one of them."""
    real_write = cooler.write
    packets = [0]

    def short_write(ep, data, timeout=None):
        up = cooler._upload
        if up is not None and up["stage"] == "data" and not bytes(data).startswith(b"dcldfinish"):
            packets[0] += 1
            if packets[0] == 3:
                return len(data) - 1
        return real_write(ep, data, timeout)

    monkeypatch.setattr(cooler, "write", short_write)
    with device.Mystique() as m:
        with pytest.raises(usb.core.USBError, match="short image-data write"):
            m.upload_jpeg("a" * 32, JPEG)
        assert cooler._upload is None and cooler.log[-1] == ("upload called off", "data")


def test_an_upload_that_is_interrupted_from_the_keyboard_is_called_off_and_stays_an_interrupt(cooler, monkeypatch):
    real_write = cooler.write
    packets = [0]

    def interrupted_write(ep, data, timeout=None):
        up = cooler._upload
        if up is not None and up["stage"] == "data" and not bytes(data).startswith(b"dcldfinish"):
            packets[0] += 1
            if packets[0] == 3:
                raise KeyboardInterrupt
        return real_write(ep, data, timeout)

    monkeypatch.setattr(cooler, "write", interrupted_write)
    with device.Mystique() as m:
        with pytest.raises(KeyboardInterrupt):
            m.upload_jpeg("a" * 32, JPEG)
        assert cooler._upload is None and cooler.log[-1] == ("upload called off", "data")


@pytest.mark.parametrize("error", [usb.core.USBError("unplugged"), KeyboardInterrupt()])
def test_a_start_command_that_does_not_go_out_is_the_error_it_was_and_no_marker_follows(cooler, monkeypatch, error):
    """With no upload on, the firmware takes one stray packet and no command after it (seen in the
    emulator): the marker that calls an upload off must not be sent when none was begun."""
    real_write = cooler.write
    sent = []

    def no_start(ep, data, timeout=None):
        data = bytes(data)
        if len(data) == 48 and data[2] == device.CMD_START_DOWNLOAD:
            raise error
        sent.append(data)
        return real_write(ep, data, timeout)

    monkeypatch.setattr(cooler, "write", no_start)
    with device.Mystique() as m:
        with pytest.raises(type(error)) as raised:
            m.upload_jpeg("a" * 32, JPEG)
    assert raised.value is error
    assert not any(data.startswith(b"dcldfinish") for data in sent) and not cooler.violations


def test_a_bad_later_gif_frame_is_rejected_before_upload_starts(cooler):
    with device.Mystique() as m:
        with pytest.raises(ValueError, match="not a JPEG"):
            m.upload_gif("e" * 32, [JPEG, b"not a JPEG"], 1000)

    assert not [entry for entry in cooler.log if entry[:2] == ("cmd", device.CMD_START_DOWNLOAD)]
    assert cooler._upload is None


def test_it_catches_bad_headers_and_data(cooler):
    def bad_sum(m):
        m.command(device.CMD_START_DOWNLOAD)
        header = bytearray(device.upload_header(SLOT_ID, JPEG))
        struct.pack_into("<I", header, 9, 1234)     # wrong data sum, header checksum fixed up
        struct.pack_into("<H", header, 62, device.sum16(header[:62]))
        m.dev.write(1, bytes(header), 1000)
        for off in range(0, len(JPEG), 64):
            m.dev.write(1, JPEG[off:off + 64], 1000)
        m.dev.write(1, b"dcldfinish".ljust(55, b"\0"), 1000)
    assert any("sum16" in v for v in _violations(cooler, bad_sum))

    def bad_header(m):
        m.command(device.CMD_START_DOWNLOAD)
        header = bytearray(device.upload_header(SLOT_ID, JPEG))
        header[62] ^= 1
        m.dev.write(1, bytes(header), 1000)
    assert any("header checksum" in v for v in _violations(cooler, bad_header))
    cooler._upload = None


def test_it_catches_wrong_pictures_and_slots(cooler):
    buf = io.BytesIO()
    Image.new("RGB", (240, 320), "red").save(buf, "JPEG")           # encode_jpeg would scale it to fit
    small = buf.getvalue()
    assert any("480x640" in v for v in _violations(cooler, lambda m: m.upload_jpeg(SLOT_ID, small)))
    assert any("only 2 are stored" in v for v in _violations(cooler, lambda m: (m.set_mode(device.MODE_MOTION), m.show_slot(5))))
    assert any("image mode" in v for v in _violations(cooler, lambda m: (m.set_mode(device.MODE_SITUATIONAL), m.show_slot(0))))


def test_it_catches_the_destructive_commands(cooler):
    assert any("erases" in v for v in _violations(cooler, lambda m: m.command(device.CMD_DELETE_ALL)))
    assert any("erases" in v for v in _violations(cooler, lambda m: m.command(device.CMD_FACTORY_RESET)))


def test_unknown_commands_are_refused_like_the_firmware_does(cooler):
    with device.Mystique() as m:
        try:
            m.command(0x20)
        except RuntimeError as e:
            assert "unexpected reply" in str(e)
        else:
            raise AssertionError("expected the driver to reject the reply")
