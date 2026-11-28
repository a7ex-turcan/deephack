"""The firmware update sender (deephack.firmware, which tools/fw/flash.py and the app use) against the
emulated stock firmware: the image must arrive as FW_update.bin, byte for byte, and the firmware must
then restart; an update that arrives damaged or not at all must leave nothing behind. What the
bootloader does with the file is beyond the emulator. Nothing here touches a real cooler."""
import os
import struct
import sys
import time
from pathlib import Path

import pytest

from deephack import device, firmware

pytest.importorskip("unicorn")
pytest.importorskip("keystone")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "emu"))
sys.path.insert(0, str(ROOT / "tools" / "fw"))
import bench  # noqa: E402
import boot  # noqa: E402
import flash  # noqa: E402
import patch  # noqa: E402

pytestmark = pytest.mark.skipif(not boot.DEFAULT_IMAGE.exists(), reason="DeepCool's firmware image is not installed")
WDT_CR = 0x400A0808
UPLOAD_STATE = 0x200006D4                # the firmware's upload state machine: 0 waits for a header, 1 takes data


@pytest.fixture(scope="module", autouse=True)
def quiet_emulator():
    import faulthandler

    was_on = faulthandler.is_enabled()
    faulthandler.disable()
    yield
    if was_on:
        faulthandler.enable()


@pytest.fixture(scope="module")
def stock() -> bytes:
    return boot.DEFAULT_IMAGE.read_bytes()


def test_version_is_read_the_way_deepcool_counts():
    assert flash.version(0x0246) == "2.70" and flash.version(0x0247) == "2.71"


def test_header_is_an_upload_header_of_type_0(stock):
    header = flash.update_header(stock)
    assert header[:5] == b"DCLd\0" and len(header) == 64
    assert struct.unpack_from("<II", header, 5) == (len(stock), device.sum16(stock))
    assert struct.unpack_from("<H", header, 62)[0] == device.sum16(header[:62])


def test_images_that_cannot_be_firmware_are_refused(stock):
    flash.check_image(stock)
    flash.check_image(patch.build(stock))
    with pytest.raises(ValueError, match="vector table"):
        flash.check_image(b"\xff\xd8" + bytes(200_000))                    # a picture
    with pytest.raises(ValueError, match="size"):
        flash.check_image(stock[:4096])
    eaten = bytearray(stock)
    eaten[64 * 100:64 * 100 + 2] = b"\xaa\x2e"
    with pytest.raises(ValueError, match="AA 2E"):
        flash.check_image(bytes(eaten))


@pytest.mark.parametrize("which", ["short", "stock", "patched"])
def test_the_firmware_stores_the_image_and_restarts(stock, which):
    """The whole images take over a minute each in the emulator: DEEPHACK_FULL_FLASH_TEST=1 runs them
    (both passed on 19 Nov 2026). Otherwise the first 96 KiB of the stock image stand in."""
    if which != "short" and not os.environ.get("DEEPHACK_FULL_FLASH_TEST"):
        pytest.skip("set DEEPHACK_FULL_FLASH_TEST=1 to send a whole image")
    image = {"short": stock[:96 * 1024], "stock": stock}.get(which) or patch.build(stock)
    cooler = bench.EmulatedCooler()
    driver = cooler.driver()
    real_sleep, time.sleep = time.sleep, lambda seconds: cooler.run_for(seconds)
    try:
        flash.send_update(driver, image)
    finally:
        time.sleep = real_sleep
    cooler.run_for(1.0)
    files = {name.lower(): content for name, content in cooler.files().items()}
    assert files == {"fw_update.bin": image}
    assert any(value & 1 for value in cooler.machine.writes[WDT_CR])       # the watchdog that restarts the chip


def test_an_update_that_goes_wrong_is_not_flashed_and_can_be_called_off(stock):
    """Three updates that go wrong, on one cooler, and a picture upload after them. In each case nothing
    may be stored and nothing may restart; "dcldfinish" must end the upload, or the firmware would take
    the next upload for the rest of the file (it did, when this was tried without)."""
    image = stock[:68 * 1024]
    cooler = bench.EmulatedCooler()
    driver, machine = cooler.driver(), cooler.machine
    driver.set_mode(device.MODE_MOTION)

    def send(header: bytes, data: bytes) -> None:
        driver.command(device.CMD_START_DOWNLOAD)
        driver.dev.write(1, header)
        for at in range(0, len(data), 64):
            driver.dev.write(1, data[at:at + 64])
        cooler.run_for(1.0)

    def untouched() -> bool:
        return not cooler.files() and not any(value & 1 for value in machine.writes[WDT_CR])

    def call_off() -> None:
        assert machine.uc.mem_read(UPLOAD_STATE, 1)[0] == 1          # it is still waiting for the file
        driver.dev.write(1, firmware.FINISH)
        cooler.run_for(0.5)
        assert machine.uc.mem_read(UPLOAD_STATE, 1)[0] == 0 and untouched()

    wrong = bytearray(firmware.update_header(image))                 # 1. the header announces another sum
    struct.pack_into("<I", wrong, 9, (device.sum16(image) + 1) & 0xFFFF)
    struct.pack_into("<H", wrong, 62, device.sum16(wrong[:62]))
    send(bytes(wrong), image)
    assert untouched()
    call_off()

    damaged = bytearray(image)                                       # 2. one byte changes on the way
    damaged[40_000] ^= 0x10
    send(firmware.update_header(image), bytes(damaged))
    assert untouched()
    call_off()

    def stop_half_way(sent: int) -> None:                            # 3. the sender stops: it calls the upload off itself
        if sent >= len(image) // 2:
            raise InterruptedError("enough")

    real_sleep, time.sleep = time.sleep, lambda seconds: cooler.run_for(seconds)
    try:
        with pytest.raises(firmware.SendFailed) as failed:
            firmware.send_update(driver, image, stop_half_way)
    finally:
        time.sleep = real_sleep
    cooler.run_for(0.5)
    assert failed.value.ended and 0 <= failed.value.sent - len(image) // 2 < 0x1000
    assert machine.uc.mem_read(UPLOAD_STATE, 1)[0] == 0 and untouched()

    from PIL import Image

    picture = device.encode_jpeg(Image.new("RGB", (480, 640), "#106060"))
    driver.upload_jpeg("f" * 32, picture)                            # and the next upload is a picture again
    cooler.run_for(1.0)
    assert {name.lower(): content for name, content in cooler.files().items()} == {f"img/000_{'f' * 32}/angle_0.jpg": picture}
    assert not any(value & 1 for value in machine.writes[WDT_CR])


class Breaks:
    """The emulated cooler's USB with one write that goes wrong: the data packet `at` of an upload (the
    headers, the commands and the marker are not counted)."""

    def __init__(self, usb, at: int):
        self.usb, self.at, self.data = usb, at, 0

    def write(self, endpoint, data, timeout=None):
        data = bytes(data)
        if not (len(data) == 64 and data[:4] == b"DCLd" or data[:2] == b"\xaa\x2e" or data.startswith(b"dcldfinish")):
            self.data += 1
            if self.data == self.at:
                raise OSError("the write goes wrong")
        return self.usb.write(endpoint, data, timeout)

    def read(self, endpoint, size, timeout=None):
        return self.usb.read(endpoint, size, timeout)


def test_a_picture_upload_that_breaks_off_is_called_off_by_the_driver():
    """The driver's own way out of an upload that stops (issue #19), with the firmware itself: a still,
    then an animation in its second frame. The firmware must be back to waiting for a header each time,
    answer commands, and store the next upload. An animation's frames are written as they arrive: the
    one that came whole stays in a folder without a config.cfg, which the firmware removes at power-on."""
    from PIL import Image

    red, blue, green = (device.encode_jpeg(Image.new("RGB", (480, 640), colour)) for colour in ("red", "blue", "#106060"))
    cooler = bench.EmulatedCooler()
    driver, machine = cooler.driver(), cooler.machine
    real = driver.dev
    driver.set_mode(device.MODE_MOTION)

    def card(of=None) -> dict:
        return {name.lower(): content for name, content in (of or cooler).files().items()}

    driver.dev = Breaks(real, 3)
    with pytest.raises(OSError, match="goes wrong"):
        driver.upload_jpeg("1" * 32, red)
    driver.dev = real
    cooler.run_for(1.0)
    assert machine.uc.mem_read(UPLOAD_STATE, 1)[0] == 0 and card() == {}
    assert driver.uuid() is not None                                 # it takes commands
    driver.upload_jpeg("2" * 32, green)
    cooler.run_for(1.0)
    still = {f"img/000_{'2' * 32}/angle_0.jpg": green}
    assert card() == still

    driver.dev = Breaks(real, -(-len(red) // 64) + 3)                # the first frame whole, the second not
    with pytest.raises(OSError, match="goes wrong"):
        driver.upload_gif("3" * 32, [red, blue], 1000)
    driver.dev = real
    cooler.run_for(1.0)
    left = {f"gif/000_{'3' * 32}/angle_0/index000.jpg": red}
    assert machine.uc.mem_read(UPLOAD_STATE, 1)[0] == 0 and card() == still | left
    driver.upload_gif("4" * 32, [blue, red], 1000)                   # the next animation is one: number 000 again,
    cooler.run_for(1.0)                                              # for the firmware has none in its list
    whole = {f"gif/000_{'4' * 32}/angle_0/index000.jpg": blue, f"gif/000_{'4' * 32}/angle_0/index001.jpg": red}
    stored = card()
    assert stored.pop(f"gif/000_{'4' * 32}/config.cfg") == b"gifrate=2\r\ngifalltime=1000\r\n"
    assert stored == still | left | whole

    again = bench.EmulatedCooler(files=cooler.files())               # off and on: what was left behind is gone
    after = card(again)
    assert after.pop(f"gif/000_{'4' * 32}/config.cfg") and after == still | whole


def test_an_animation_sent_under_an_id_that_is_there_keeps_the_first_ones_pace():
    """Issues #66 and #67, with the firmware itself. It writes an animation's frame count and loop time
    (config.cfg, and its list in memory) when it makes the folder; for an id whose folder is there it
    replaces the frames and nothing else. Its player counts the frames by their files and takes the time
    of each from the list: the new frames, at the first animation's pace. Another id has its own."""
    from PIL import Image
    from unicorn import UC_HOOK_BLOCK
    from unicorn.arm_const import UC_ARM_REG_R1

    from deephack.config import gif_id

    red, blue, green = (device.encode_jpeg(Image.new("RGB", (480, 640), colour)) for colour in ("red", "blue", "#106060"))
    f_open, one, other = 0x40ED8, "5" * 32, gif_id(200)

    def reads(cooler) -> list:
        """(the firmware's ms, name) of every frame file it opens from now on."""
        seen, machine = [], cooler.machine

        def opened(uc, address, size, data):
            path = bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_R1), 100)).split(b"\0")[0].decode("latin1")
            if "/index" in path:
                seen.append((machine.ticks, path.rsplit("/", 2)[0][-32:] + path[-7:-4]))

        machine.uc.hook_add(UC_HOOK_BLOCK, opened, begin=f_open, end=f_open)
        return seen

    def played(cooler, seen: list, index: int, seconds: float) -> tuple:
        """Which frames it showed of the animation of that number, and the ms from each to the next."""
        del seen[:]
        cooler.driver().show_slot(index, device.TYPE_GIF)
        cooler.run_for(seconds)
        return [name[-3:] for at, name in seen], {b[0] - a[0] for a, b in zip(seen[1:], seen[2:])}

    def near(gaps: set, ms: int) -> bool:
        return bool(gaps) and all(abs(gap - ms) <= 3 for gap in gaps)

    cooler = bench.EmulatedCooler()
    driver, seen = cooler.driver(), reads(cooler)
    driver.set_mode(device.MODE_MOTION)
    driver.upload_gif(one, [red, blue], 1000)
    driver.upload_gif(one, [green, red, blue], 600)                  # 200 ms a frame, were it a new one
    folder = f"gif/000_{one}"
    card = {name.lower(): content for name, content in cooler.files().items()}
    assert card == {f"{folder}/config.cfg": b"gifrate=2\r\ngifalltime=1000\r\n", f"{folder}/angle_0/index000.jpg": green,
                    f"{folder}/angle_0/index001.jpg": red, f"{folder}/angle_0/index002.jpg": blue}
    frames, gaps = played(cooler, seen, 0, 2.6)
    assert set(frames) == {"000", "001", "002"} and near(gaps, 500)  # all three, at the two frames' pace

    driver.upload_gif(other, [green, red, blue], 600)                # under an id of its own
    card = {name.lower(): content for name, content in cooler.files().items()}
    assert card[f"gif/001_{other}/config.cfg"] == b"gifrate=3\r\ngifalltime=600\r\n"
    frames, gaps = played(cooler, seen, 1, 1.5)
    assert set(frames) == {"000", "001", "002"} and near(gaps, 200)

    again = bench.EmulatedCooler(files=cooler.files())               # off and on: it reads config.cfg, and nothing changes
    again.driver().set_mode(device.MODE_MOTION)
    seen = reads(again)
    frames, gaps = played(again, seen, 0, 2.6)
    assert set(frames) == {"000", "001", "002"} and near(gaps, 500)
    frames, gaps = played(again, seen, 1, 1.5)
    assert set(frames) == {"000", "001", "002"} and near(gaps, 200)


def test_the_patched_firmware_takes_an_update_too(stock, tmp_path):
    """An update of the patch, or the way back to DeepCool's image, goes to a cooler that runs the patched
    firmware and has drawn frames."""
    from PIL import Image

    running = tmp_path / "patched.bin"
    running.write_bytes(patch.build(stock))
    cooler = bench.EmulatedCooler(firmware=running)
    driver = cooler.driver()
    driver.set_mode(device.MODE_MOTION)
    driver.upload_jpeg("0" * 32, device.encode_jpeg(Image.new("RGB", (480, 640), "#203060")))
    cooler.run_for(1.0)
    driver.show_slot(0)
    cooler.run_for(0.5)
    version, uc = driver.draw_version(), cooler.machine.uc
    assert firmware.fresh(driver, version) is True                   # nothing drawn yet: the patch has made no buffer
    driver.draw_jpeg(device.encode_jpeg(Image.new("RGB", (480, 640), "#802020")))
    cooler.run_for(0.3)
    assert firmware.fresh(driver, version) is False
    image = stock[:68 * 1024]

    def blocks() -> list:
        out, at = [], firmware.HEAP
        while at < firmware.HEAP + firmware.HEAP_SIZE:
            word = struct.unpack("<I", bytes(uc.mem_read(at, 4)))[0]
            out.append((at, word & 1, word >> 1))
            at += 4 + (word >> 1)
        return out

    # A cooler without room: all but 1500 KB of the largest free block is made a block in use. The firmware
    # would take the header, fail to get its 2 MiB and throw the file away; the sender asks first and sends
    # nothing (on a real cooler this was the patch's buffers and a stored picture: 2012 KB free).
    at, _, size = max((b for b in blocks() if not b[1]), key=lambda b: b[2])
    keep = 1500 * 1024
    uc.mem_write(at, struct.pack("<I", keep << 1))
    uc.mem_write(at + 4 + keep, struct.pack("<I", (size - keep - 4) << 1 | 1))
    real_sleep, time.sleep = time.sleep, lambda seconds: cooler.run_for(seconds)
    try:
        with pytest.raises(firmware.NoRoom) as none:
            firmware.send_update(driver, image)
        cooler.run_for(1.0)
        assert none.value.free < firmware.STAGING and not {name.lower() for name in cooler.files()} & {"fw_update.bin"}
        assert uc.mem_read(UPLOAD_STATE, 1)[0] == 0 and not any(value & 1 for value in cooler.machine.writes[WDT_CR])
        assert struct.unpack("<I", bytes(uc.mem_read(firmware.UPLOAD_WAIT, 4)))[0] == 0      # it has stopped waiting
        assert (at + 4 + keep, 1, size - keep - 4) in blocks()
        uc.mem_write(at + 4 + keep, struct.pack("<I", (size - keep - 4) << 1))               # the room is there again
        firmware.send_update(driver, image)          # asked again, and this time sent: the asking leaves the file whole
    finally:
        time.sleep = real_sleep
    cooler.run_for(1.0)
    files = {name.lower(): content for name, content in cooler.files().items()}
    assert files.get("fw_update.bin") == image
    assert any(value & 1 for value in cooler.machine.writes[WDT_CR])
