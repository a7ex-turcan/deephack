"""Firmware updates from the app (deephack.firmware and the engine's part), against the cooler model.

The images here are made up: DeepCool's is not in the repository. What the real firmware does with an
update is in test_flash.py (the emulator); the tests at the end run only where DeepCool's image is.
"""
import hashlib
import io
import json
import struct
import sys
from pathlib import Path

import pytest
import usb.core
from PIL import Image

from deephack import device, engine, firmware, firmware_patch
from deephack.config import Config

ROOT = Path(__file__).resolve().parents[1]
STOCK = struct.pack("<II", 0x2000B418, 0xE33D) + bytes(range(7, 250)) * 300     # passes for an image: a vector table
DIRECT = STOCK + b"the patch" * 40
RED = Image.new("RGB", (480, 640), "#a02020")
_big = io.BytesIO()
Image.effect_noise((480, 640), 40).convert("RGB").save(_big, "JPEG", quality=30)
BIG = _big.getvalue()                          # a stored picture of 69 KB: with it on show the cooler had no room


def held(cooler, patch, on_show: bytes = b"", ground: bytes | None = None) -> None:
    """The cooler runs this patch and has drawn a picture since it started (it has made its buffers); the
    stored still of index 0 is this file, and it is on show. `ground`: a second still, deephack's plain one."""
    cooler.direct, cooler.buffers = patch, True
    cooler.stills[0][1] = on_show
    if ground is not None:
        cooler.stills.append(["ground", ground])
    cooler.mode, cooler.shown = device.MODE_MOTION, ("jpg", 0)


def announced(cooler) -> int:
    return len([e for e in cooler.log if e[:2] == ("cmd", device.CMD_START_DOWNLOAD)])


@pytest.fixture
def images(monkeypatch, tmp_path, cooler):
    """Made-up images in place of DeepCool's, and a cooler that takes them."""
    monkeypatch.setattr(firmware, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(firmware, "_app_folders", lambda: [tmp_path / "DeepCool"])
    monkeypatch.setattr(firmware, "STOCK_SHA256", hashlib.sha256(STOCK).hexdigest())
    monkeypatch.setattr(firmware, "direct_image", lambda stock: DIRECT)
    monkeypatch.setattr(firmware, "on_bus", cooler.look)
    cooler.firmwares = {DIRECT: firmware.PATCH_VERSION, STOCK: False}
    app_copy = tmp_path / "DeepCool" / firmware.IN_APP
    app_copy.parent.mkdir(parents=True)
    app_copy.write_bytes(STOCK)
    return cooler


def _engine(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "_stored_count", lambda kind: 1)
    monkeypatch.setattr(engine, "DRAW_SETTLE", 0.0)
    monkeypatch.setattr(engine, "FLASH_SETTLE", 0.0)
    eng = engine.Engine(Config(tmp_path / "config.json"))
    eng._make_mode()
    eng._device_step(True)
    return eng


# ---- the pieces
def test_version_is_read_the_way_deepcool_counts():
    assert firmware.version(0x0246) == "2.70" and firmware.version(0x0247) == "2.71"
    assert set(firmware.KNOWN) == {0x0246, 0x0247}


def test_header_is_an_upload_header_of_type_0():
    header = firmware.update_header(STOCK)
    assert header[:5] == b"DCLd\0" and len(header) == 64
    assert struct.unpack_from("<II", header, 5) == (len(STOCK), device.sum16(STOCK))
    assert struct.unpack_from("<H", header, 62)[0] == device.sum16(header[:62])
    with pytest.raises(ValueError):
        device.upload_header("0" * 32, STOCK, device.FILE_FIRMWARE)        # the picture upload never makes one


def test_images_that_cannot_be_firmware_are_refused():
    firmware.check_image(STOCK)
    with pytest.raises(ValueError, match="vector table"):
        firmware.check_image(b"\xff\xd8" + bytes(200_000))                 # a picture
    with pytest.raises(ValueError, match="size"):
        firmware.check_image(STOCK[:4096])
    eaten = bytearray(STOCK)
    eaten[64 * 100:64 * 100 + 2] = b"\xaa\x2e"
    with pytest.raises(ValueError, match="AA 2E"):
        firmware.check_image(bytes(eaten))


def test_the_patch_goes_on_deepcools_image_only():
    with pytest.raises(ValueError, match="not DeepCool's"):
        firmware.direct_image(STOCK)
    assert firmware.PATCH_VERSION == firmware_patch.VERSION == max(firmware_patch.CHANGES)
    assert firmware_patch.STOCK_SIZE + len(firmware_patch.CODE) <= 0x72000 and all(len(bytes.fromhex(j)) == 4 for j in firmware_patch.JUMPS.values())


def test_deepcools_image_is_found_checked_and_kept(images, tmp_path):
    assert firmware.have_stock() and firmware.read_stock() == STOCK
    assert firmware.kept_stock().read_bytes() == STOCK                     # deephack's own copy, for the way back
    (tmp_path / "DeepCool" / firmware.IN_APP).unlink()                    # the DeepCool app is uninstalled
    assert firmware.read_stock() == STOCK
    other = tmp_path / "other.bin"
    other.write_bytes(STOCK[:-1] + b"!")
    with pytest.raises(ValueError, match="is not DeepCool's"):
        firmware.read_stock(other)
    firmware.kept_stock().write_bytes(b"damaged")                         # a damaged copy is not used
    with pytest.raises(ValueError, match="was not found"):
        firmware.read_stock()
    assert not firmware.have_stock()
    picked = tmp_path / "picked.bin"
    picked.write_bytes(STOCK)
    assert firmware.read_stock(picked) == STOCK and firmware.have_stock()   # ... and replaced by a good one


def test_dcldfinish_is_only_sent_where_it_cannot_complete_the_file():
    image = STOCK
    assert firmware.finish_is_safe(image, 0) and firmware.finish_is_safe(image, len(image) - 56)
    assert firmware.finish_is_safe(image, len(image))                      # nothing missing: nothing to complete
    for left in range(1, 56):                                              # it would complete the file ...
        tail = firmware.FINISH[:left]
        same_sum = image[:-left] + tail                                    # ... rightly only if the sums agree
        assert not firmware.finish_is_safe(same_sum, len(same_sum) - left)
        assert firmware.finish_is_safe(image, len(image) - left) == (device.sum16(image[-left:]) != device.sum16(tail))


def test_image_upload_finish_marker_is_safe_at_every_packet_boundary():
    images = [
        device.encode_jpeg(RED),
        device.encode_jpeg(Image.new("RGB", (480, 640), "blue")),
    ]
    for image in images:  # still and GIF frame data take the same firmware path
        for sent in range(0, len(image), 64):
            for possible in (sent, min(sent + 64, len(image))):
                assert firmware.finish_is_safe(image, possible)


def test_end_upload_reports_a_short_marker_write_as_failure():
    class Device:
        def write(self, ep, data, timeout=None):
            return len(data) - 1

    class Driver:
        dev = Device()

    assert not firmware.end_upload(Driver(), STOCK, 0)


def test_waiting_for_the_restart():
    def looks(*seen):
        seen = list(seen)
        return lambda: seen.pop(0) if len(seen) > 1 else seen[0]

    ticks = iter(range(10_000))
    clock = lambda: next(ticks) * 0.5                                      # noqa: E731
    reports = []
    assert firmware.wait_for_restart(looks(0x246, None, None, 0x246), lambda s, state: reports.append(state),
                                     clock=clock) == ("back", 0x246)
    assert reports == ["waiting", "off", "off", "back"]
    assert firmware.wait_for_restart(looks(0x246), clock=clock, off_bus=5.0) == ("stayed", 0x246)
    assert firmware.wait_for_restart(looks(None), clock=clock, patience=8.0) == ("gone", None)


# ---- against the cooler model
def test_an_update_arrives_whole_and_restarts_the_cooler(images):
    progress = []
    with device.Mystique() as m:
        firmware.send_update(m, DIRECT, progress.append)
    assert images.updates == 1 and images.direct == firmware.PATCH_VERSION
    assert progress[0] == 0 and progress == sorted(progress) and len(DIRECT) - progress[-1] > 0x1000
    assert firmware.wait_for_restart() == ("back", 0x0246)


def test_an_update_that_is_stopped_is_called_off(images):
    def stop_half_way(sent):
        if sent > len(DIRECT) // 2:
            raise InterruptedError("enough")

    with device.Mystique() as m:
        with pytest.raises(firmware.SendFailed) as failed:
            firmware.send_update(m, DIRECT, stop_half_way)
        assert failed.value.ended and 0 < failed.value.sent < len(DIRECT)
        assert images.updates == 0 and images.log[-1] == ("update given up", failed.value.sent + len(firmware.FINISH))
        m.upload_jpeg("f" * 32, device.encode_jpeg(RED))                   # the next upload is a picture again
    assert images.updates == 0 and len(images.stills) == 2


def test_an_update_that_breaks_off_is_called_off_if_the_cooler_still_listens(images, monkeypatch):
    real_write, count = images.write, [0]

    def write(ep, data, timeout=None):
        count[0] += 1
        if count[0] == 400:
            raise usb.core.USBTimeoutError("timed out")
        return real_write(ep, data, timeout)

    monkeypatch.setattr(images, "write", write)
    with device.Mystique() as m:
        with pytest.raises(firmware.SendFailed) as failed:
            firmware.send_update(m, STOCK)
    assert failed.value.ended and images.updates == 0 and images.log[-1][0] == "update given up"


# ---- room for the file (the firmware puts it into 2 MiB of its heap in one piece, or throws it away)
def test_a_cooler_without_room_is_sent_nothing(images):
    held(images, 9, BIG)
    assert images.free_for_upload() < firmware.STAGING
    with device.Mystique() as m:
        assert firmware.fresh(m, 9) is False
        with pytest.raises(firmware.NoRoom) as none:
            firmware.send_update(m, DIRECT)
    assert none.value.free == images.free_for_upload() and "2048" in str(none.value)
    assert images.updates == 0 and images.log[-1] == ("upload called off", "header")     # not even the header went out


def test_a_cooler_with_room_is_asked_and_then_sent_the_update(images):
    held(images, 9, device.encode_jpeg(RED))             # the same cooler with a small picture on show
    with device.Mystique() as m:
        firmware.send_update(m, DIRECT)
    asked = [struct.unpack_from("<I", e[2])[0] for e in images.log if e[:2] == ("cmd", device.CMD_PEEK)]
    assert asked.count(firmware.UPLOAD_WAIT) > 1 and firmware.HEAP in asked      # it waited for the firmware's wait, then walked
    assert images.updates == 1 and images.direct == firmware.PATCH_VERSION and not images.buffers


def test_patch_15_gives_its_buffers_back_and_has_room(images):
    held(images, 15, BIG)
    with device.Mystique() as m:
        firmware.send_update(m, DIRECT)
    assert images.updates == 1


@pytest.mark.parametrize("patch", [False, 3])
def test_a_firmware_that_cannot_be_asked_is_sent_the_update_unasked(images, patch):
    images.direct = patch
    with device.Mystique() as m:
        assert firmware.fresh(m, int(patch)) is None
        firmware.send_update(m, DIRECT)
    assert images.updates == 1 and not [e for e in images.log if e[:2] == ("cmd", device.CMD_PEEK)]


def test_the_heap_is_walked_block_by_block():
    class Memory:
        def __init__(self, blocks):
            self.words, at = {}, firmware.HEAP
            for used, size in blocks:
                self.words[at] = size << 1 | used
                at += 4 + size

        def peek(self, address, count):
            return struct.pack("<I", self.words.get(address, 0))

    rest = firmware.HEAP_SIZE - (4 + 1000) - (4 + 5000) - (4 + 3000) - 4
    assert firmware.largest_free(Memory([(1, 1000), (0, 5000), (0, 3000), (1, rest)])) == 5000     # (two free blocks side
    assert firmware.largest_free(Memory([(1, 1000), (1, 5000), (1, 3000), (1, rest)])) == 0        # by side are two)
    assert firmware.largest_free(Memory([(1, 1000), (0, 5000)])) is None        # not a heap from end to end: no verdict
    assert firmware.keeps_buffers(3) and firmware.keeps_buffers(14) and not firmware.keeps_buffers(15) and not firmware.keeps_buffers(0)


# ---- the engine
def _config(tmp_path, **values) -> None:
    (tmp_path / "config.json").write_text(json.dumps(values), encoding="utf8")


def _started(tmp_path, states: list):
    """deephack starts again: a new engine with the same settings, and its first look at the cooler."""
    eng = engine.Engine(Config(tmp_path / "config.json"))
    eng.stateChanged.connect(states.append)
    eng._make_mode()
    eng._device_step(True)
    return eng


def test_an_update_the_cooler_has_no_room_for_waits_for_its_next_start(images, tmp_path, monkeypatch):
    import cooler as model

    monkeypatch.setattr(model, "FREE_FOR_UPLOAD", 2_400_000)         # a cooler with 100 KB less than ours: with the
    held(images, 9, device.encode_jpeg(RED))                         # buffers there is no room whatever is on show
    _config(tmp_path, slot_index=0, ground=True)
    eng = _engine(tmp_path, monkeypatch)
    eng._flash_firmware("direct", None)
    message = eng._flash["message"]
    assert eng._flash["stage"] == "failed" and "no room" in message and "nothing was sent" in message and "by itself" in message
    assert images.updates == 0 and announced(images) == 1 and eng.config.get("firmware_wanted") == "direct"
    eng._next_open = 0.0
    eng._device_step(True)                                           # the cooler is opened again: not tried twice in a run
    eng._emit_state(True)
    assert announced(images) == 1 and eng._last_state["flash_wanted"] == "direct" and not eng._last_state["flash_remembered"]

    again = _started(tmp_path, [])                                   # deephack starts again, the cooler was not off:
    assert announced(images) == 1 and again._flash is None           # it still has its buffers, so nothing is tried
    again._set_frame(RED)
    for _ in range(3):
        again._device_step(True)
    assert images.draws > 0 and again.config.get("firmware_wanted") == "direct"

    images.buffers, images.drawn, drawn = False, None, images.draws  # the PC was off: the cooler has just started
    states = []
    fresh = _started(tmp_path, states)
    assert images.updates == 1 and images.draws == drawn             # sent before anything was drawn
    assert [s["flash"]["stage"] for s in states][0] == "sending" and states[-1]["flash"]["stage"] == "checking"
    assert all(s["flash_remembered"] for s in states)
    fresh._device_step(True)
    assert fresh._flash["stage"] == "done" and fresh._firmware["patch"] == firmware.PATCH_VERSION
    assert fresh.config.get("firmware_wanted") is None


def test_deephacks_plain_still_goes_on_show_before_an_update_from_an_old_patch(images, tmp_path, monkeypatch):
    held(images, 9, BIG, ground=device.encode_jpeg(Image.new("RGB", (480, 640))))
    assert images.free_for_upload() < firmware.STAGING               # with the user's picture on show: no room
    _config(tmp_path, slot_index=1, ground=True)
    eng = _engine(tmp_path, monkeypatch)
    images.shown = ("jpg", 0)
    eng._flash_firmware("direct", None)
    shows = [i for i, e in enumerate(images.log) if e[:2] == ("cmd", device.CMD_SHOW_SLOT) and tuple(e[2][:2]) == (device.TYPE_JPG, 1)]
    sent = [i for i, e in enumerate(images.log) if e[:2] == ("cmd", device.CMD_START_DOWNLOAD)]
    assert shows and sent and shows[-1] < sent[0] and images.updates == 1 and eng._flash["stage"] == "checking"


def test_a_patch_that_cannot_be_asked_is_tried_once_each_time_deephack_starts(images, tmp_path, monkeypatch):
    import cooler as model

    monkeypatch.setattr(model, "FREE_FOR_UPLOAD", 2_400_000)
    held(images, 3, device.encode_jpeg(RED))
    _config(tmp_path, slot_index=0, ground=True)
    ticks = iter(range(1_000_000))
    monkeypatch.setattr(firmware.time, "monotonic", lambda: next(ticks) * 0.5)
    eng = _engine(tmp_path, monkeypatch)
    eng._flash_firmware("direct", None)                              # sent whole, and thrown away by the cooler
    assert eng._flash == {"which": "direct", "stage": "checking", "restarted": False}
    eng._device_step(True)
    assert eng._flash["stage"] == "failed" and "did not restart" in eng._flash["message"] and "by itself" in eng._flash["message"]
    assert eng.config.get("firmware_wanted") == "direct" and announced(images) == 1 and images.updates == 0
    assert len(images.violations) == 1 and "no room" in images.violations.pop()      # the model says so too
    eng._next_open = 0.0
    eng._device_step(True)
    assert announced(images) == 1                                    # not again in this run

    again = _started(tmp_path, [])                                   # the next start, the cooler still with its buffers:
    assert announced(images) == 2 and images.updates == 0            # tried, for it cannot be asked, and thrown away again
    assert len(images.violations) == 1 and "no room" in images.violations.pop()
    again._device_step(True)
    assert again._flash["stage"] == "failed" and again.config.get("firmware_wanted") == "direct"

    images.buffers = False                                           # and after the PC was off
    fresh = _started(tmp_path, [])
    assert images.updates == 1
    fresh._device_step(True)
    assert fresh._flash["stage"] == "done" and fresh.config.get("firmware_wanted") is None


def test_an_update_that_waits_can_be_called_off_and_lapses_when_the_cooler_runs_something_else(images, tmp_path, monkeypatch):
    held(images, 9)
    _config(tmp_path, firmware_wanted="direct")
    eng = _engine(tmp_path, monkeypatch)                             # (the cooler has its buffers: nothing is tried)
    assert announced(images) == 0 and eng.config.get("firmware_wanted") == "direct"
    eng.forget_firmware()
    eng._commands.get_nowait()()
    assert eng.config.get("firmware_wanted") is None

    images.direct, images.buffers = firmware.PATCH_VERSION, False    # it was updated some other way meanwhile
    _config(tmp_path, firmware_wanted="direct")
    again = _started(tmp_path, [])
    assert announced(images) == 0 and again.config.get("firmware_wanted") is None

    images.direct = 9                                                # the other firmware is asked for: the wish goes
    _config(tmp_path, firmware_wanted="direct")
    other = _started(tmp_path, [])                                   # (fresh: it is sent at once)
    assert images.updates == 1 and images.direct == firmware.PATCH_VERSION
    other._device_step(True)
    other.config.set("firmware_wanted", "direct")
    other._flash_firmware("stock", None)
    assert other.config.get("firmware_wanted") is None and images.updates == 2 and images.direct is False


def test_the_engine_knows_what_the_cooler_runs(images, tmp_path, monkeypatch):
    states = []
    eng = _engine(tmp_path, monkeypatch)
    eng.stateChanged.connect(states.append)
    eng._emit_state(True)
    assert states[-1]["firmware"] == {"bcd": 0x0246, "version": "2.70", "patch": 0} and states[-1]["flash"] is None


@pytest.mark.parametrize("which, runs", [("direct", firmware.PATCH_VERSION), ("stock", 0)])
def test_the_engine_flashes_and_sees_the_cooler_come_back(images, tmp_path, monkeypatch, which, runs):
    images.direct = False if which == "direct" else 1
    states = []
    eng = _engine(tmp_path, monkeypatch)
    eng.stateChanged.connect(states.append)
    eng._flash_firmware(which, None)
    stages = [s["flash"]["stage"] for s in states]
    assert stages[0] == "sending" and "restarting" in stages and stages[-1] == "checking"
    assert states[-1]["device"] == "missing" and states[-1]["firmware"] is None
    sent = [s["flash"]["progress"] for s in states if s["flash"]["stage"] == "sending"]
    assert sent[0] == 0.0 and sent == sorted(sent) and 0.8 < sent[-1] < 1.0
    assert any(s["flash"].get("off") for s in states)                      # it was seen leaving the bus
    eng._device_step(True)
    eng._emit_state(True)
    assert states[-1]["flash"]["stage"] == "done" and states[-1]["firmware"]["patch"] == runs
    assert images.updates == 1
    eng._set_frame(RED)                                                    # and the engine goes on with it
    for _ in range(3):
        eng._device_step(True)
    assert (images.draws > 0) == (which == "direct")


def test_nothing_is_sent_to_a_firmware_that_is_not_known(images, tmp_path, monkeypatch):
    images.bcdDevice = 0x0250
    eng = _engine(tmp_path, monkeypatch)
    eng._flash_firmware("direct", None)
    assert eng._flash["stage"] == "failed" and "2.80" in eng._flash["message"] and "Nothing was sent" in eng._flash["message"]
    assert images.updates == 0 and not [e for e in images.log if e[:2] == ("cmd", device.CMD_START_DOWNLOAD)]


def test_nothing_is_sent_without_deepcools_image(images, tmp_path, monkeypatch):
    (tmp_path / "DeepCool" / firmware.IN_APP).unlink()
    eng = _engine(tmp_path, monkeypatch)
    eng._flash_firmware("direct", None)
    assert eng._flash["stage"] == "failed" and "was not found" in eng._flash["message"]
    (tmp_path / "picture.jpg").write_bytes(device.encode_jpeg(RED))
    eng._flash_firmware("direct", str(tmp_path / "picture.jpg"))           # a file that is something else
    assert eng._flash["stage"] == "failed" and "is not DeepCool's" in eng._flash["message"]
    assert images.updates == 0 and not [e for e in images.log if e[:2] == ("cmd", device.CMD_START_DOWNLOAD)]


def test_a_cooler_that_did_not_restart_is_reported_as_unchanged(images, tmp_path, monkeypatch):
    images.firmwares = {}                                                  # this cooler takes nothing
    monkeypatch.setattr(images, "_flashed", lambda image: setattr(images, "_upload", None))
    ticks = iter(range(100_000))
    monkeypatch.setattr(firmware.time, "monotonic", lambda: next(ticks) * 0.5)
    eng = _engine(tmp_path, monkeypatch)
    eng._flash_firmware("direct", None)
    assert eng._flash == {"which": "direct", "stage": "checking", "restarted": False}
    eng._device_step(True)
    assert eng._flash["stage"] == "failed" and "did not restart" in eng._flash["message"]


def test_a_cooler_that_does_not_come_back_is_said_so(images, tmp_path, monkeypatch):
    ticks = iter(range(100_000))
    monkeypatch.setattr(firmware.time, "monotonic", lambda: next(ticks) * 0.5)
    eng = _engine(tmp_path, monkeypatch)
    monkeypatch.setattr(firmware, "on_bus", lambda: None)
    eng._flash_firmware("stock", None)
    assert eng._flash["stage"] == "failed" and eng._flash["sent"] and "has not come back" in eng._flash["message"]


def test_closing_deephack_calls_the_update_off(images, tmp_path, monkeypatch):
    eng = _engine(tmp_path, monkeypatch)
    eng.stateChanged.connect(lambda state: state["flash"] and state["flash"].get("progress", 0) > 0.3 and eng.stop())
    eng._flash_firmware("direct", None)
    assert eng._flash["stage"] == "failed" and "nothing was flashed" in eng._flash["message"]
    assert images.updates == 0 and images.log[-1][0] == "update given up"


# ---- with DeepCool's image, where it is installed
REAL = Path("C:/DeepCool") / firmware.IN_APP
needs_image = pytest.mark.skipif(not REAL.exists(), reason="DeepCool's firmware image is not installed")


@needs_image
def test_the_table_makes_the_image_the_source_builds():
    stock = REAL.read_bytes()
    image = firmware.direct_image(stock)
    assert hashlib.sha256(image).hexdigest() == firmware_patch.SHA256 and len(stock) == firmware_patch.STOCK_SIZE
    firmware.check_image(stock)
    firmware.check_image(image)
    for whole in (stock, image):                                           # calling an upload off is safe wherever it stops
        assert all(firmware.finish_is_safe(whole, got) for got in range(len(whole) - 64, len(whole) + 1))
    pytest.importorskip("keystone")
    sys.path.insert(0, str(ROOT / "tools" / "fw"))
    import patch

    assert patch.build(stock) == image
    assert patch.table(stock) == (ROOT / "deephack" / "firmware_patch.py").read_text(encoding="utf8"), \
        "run: python tools/fw/patch.py --table"
