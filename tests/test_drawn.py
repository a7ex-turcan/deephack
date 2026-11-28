"""The engine on a cooler with the direct drawing firmware: a mode's pictures are drawn from USB, not stored."""
import random

import pytest
from PIL import Image

from deephack import device, engine
from deephack.config import GIF_SLOT_ID, SLOT_ID, Config, gif_id
from deephack.modes.base import Animation, Part

RED, BLUE = Image.new("RGB", (480, 640), "#a02020"), Image.new("RGB", (480, 640), "#2040b0")


def _drawn(picture):
    return ("drawn", engine.frame_jpeg(picture))


def _engine(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "_stored_count", lambda kind: 1)          # the official app's one still, one animation
    monkeypatch.setattr(engine, "DRAW_SETTLE", 0.0)
    eng = engine.Engine(Config(tmp_path / "config.json"))
    eng._make_mode()
    return eng


def _show(eng, frame, steps=2, enabled=True):
    eng._set_frame(frame)
    for _ in range(steps):
        eng._device_step(enabled)


def _is_black(picture):
    return sum(picture.resize((1, 1)).getpixel((0, 0))) < 12


def test_pictures_are_drawn_and_only_the_ground_is_stored(tmp_path, monkeypatch, cooler):
    cooler.direct = True
    eng = _engine(tmp_path, monkeypatch)
    states = []
    eng.stateChanged.connect(states.append)
    _show(eng, RED)
    assert cooler.screen == _drawn(RED) and cooler.shown == ("jpg", 1)
    assert cooler.flash_writes == 1 and _is_black(cooler.still(1))        # what the frames are drawn over
    assert eng.config.get("ground") and eng.config.get("slot_index") == 1
    _show(eng, BLUE, steps=1)                                             # at once: no wait between two pictures
    assert cooler.screen == _drawn(BLUE) and cooler.flash_writes == 1 and cooler.draws == 2
    eng._emit_state(True)
    assert states[-1]["drawn"] and not states[-1]["pending"] and states[-1]["last_upload"]

    again = _engine(tmp_path, monkeypatch)                                # after a restart nothing is stored at all
    _show(again, RED)
    assert cooler.screen == _drawn(RED) and cooler.flash_writes == 1


def test_a_picture_left_in_our_slot_is_replaced_by_the_ground(tmp_path, monkeypatch, cooler):
    cooler.direct = True
    cooler.stills.append([SLOT_ID, device.encode_jpeg(RED)])              # stored by an earlier deephack
    eng = _engine(tmp_path, monkeypatch)
    eng.config.set("slot_index", 1)
    _show(eng, BLUE)
    assert len(cooler.stills) == 2 and _is_black(cooler.still(1)) and cooler.flash_writes == 1
    assert cooler.screen == _drawn(BLUE)


def test_an_unchanged_picture_is_sent_again_now_and_then(tmp_path, monkeypatch, cooler):
    cooler.direct = True
    eng = _engine(tmp_path, monkeypatch)
    _show(eng, RED, steps=4)
    assert cooler.draws == 1
    monkeypatch.setattr(engine, "REDRAW_STILL", 0.0)
    eng._device_step(True)
    assert cooler.draws == 2 and cooler.screen == _drawn(RED)


def test_a_picture_too_large_for_the_firmware_is_drawn_at_a_lower_quality(tmp_path, monkeypatch, cooler):
    noise = Image.frombytes("RGB", (480, 640), random.Random(1).randbytes(480 * 640 * 3))
    assert len(device.encode_jpeg(noise, quality=92)) > device.DIRECT_MAX
    assert len(engine.frame_jpeg(noise)) <= device.DIRECT_MAX
    assert engine.frame_jpeg(RED) == device.encode_jpeg(RED, quality=92, tuned=True)   # as good as a stored one when it fits
    cooler.direct = True
    eng = _engine(tmp_path, monkeypatch)
    _show(eng, noise)
    assert cooler.screen == _drawn(noise)


def _played(picture):
    return ("drawn", engine.frame_jpeg(picture, engine.PLAY_QUALITY))


def test_an_animation_is_played_from_here_frame_by_frame(tmp_path, monkeypatch, cooler):
    cooler.direct = True
    clock = [5000.0]
    monkeypatch.setattr(engine.time, "monotonic", lambda: clock[0])
    eng = _engine(tmp_path, monkeypatch)
    _show(eng, Animation([RED, BLUE, BLUE, RED], 400))                    # a tenth of a second per frame
    assert cooler.screen == _played(RED) and cooler.flash_writes == 1 and not cooler.gifs
    assert eng._again == pytest.approx(0.1)                               # when the next frame is due

    def later(seconds):
        clock[0] += seconds
        eng._device_step(True)
        return cooler.screen, cooler.draws

    assert later(0.1) == (_played(BLUE), 2)
    assert later(0.1) == (_played(BLUE), 2)                               # the same picture again: not sent
    assert later(0.04) == (_played(BLUE), 2) and eng._again == pytest.approx(0.06)
    assert later(0.06) == (_played(RED), 3)
    assert later(0.1) == (_played(RED), 3)                                # round to the first frame, the same picture
    assert later(0.1) == (_played(BLUE), 4)
    eng._emit_state(True)
    assert eng._last_state["drawn"] and not eng._last_state["pending"]
    assert cooler.flash_writes == 1 and cooler.shown == ("jpg", 1)        # over the ground still, never an animation

    _show(eng, RED, steps=1)                                              # a picture after it: no detour needed
    assert cooler.screen == _drawn(RED)


def test_deepcools_own_firmware_gets_its_animations_stored(tmp_path, monkeypatch, cooler):
    cooler.gifs.append(["app-gif-0", [], 1000])
    eng = _engine(tmp_path, monkeypatch)
    _show(eng, Animation([RED, BLUE], 400))
    assert cooler.screen == ("gif", 1) and cooler.flash_writes == 2 and cooler.draws == 0 and eng._again is None


def test_an_animation_of_another_pace_is_stored_beside_the_first_not_over_it(tmp_path, monkeypatch, cooler):
    """The firmware settles an animation's pace when it makes its folder: what is stored under that id
    later plays at the first one's (#66; the model says so when it is done). So each pace has an id."""
    monkeypatch.setattr(engine, "MIN_UPLOAD_INTERVAL", 0.0)
    cooler.gifs.append(["app-gif-0", [], 1000])
    eng = _engine(tmp_path, monkeypatch)
    _show(eng, Animation([RED, BLUE], 400))                               # 200 ms a frame
    _show(eng, Animation([RED, BLUE, BLUE], 900))                         # 300
    assert cooler.screen == ("gif", 2)
    assert [(slot[0], len(slot[1]), slot[2]) for slot in cooler.gifs[1:]] == [(gif_id(200), 2, 400), (gif_id(300), 3, 900)]
    _show(eng, Animation([BLUE, RED, RED, BLUE], 800))                    # 200 again, and other frames: over the first
    assert cooler.screen == ("gif", 1) and len(cooler.gifs) == 3 and cooler.flash_writes == 9
    assert (cooler.gifs[1][0], len(cooler.gifs[1][1]), cooler.gifs[1][2]) == (gif_id(200), 4, 800)
    assert eng.config.get("gif_slots") == {"200": {"index": 1, "attempt": 0, "stored": True},
                                           "300": {"index": 2, "attempt": 0, "stored": True}}
    again = engine.Engine(Config(tmp_path / "config.json"))               # the app, started again: it knows where they are
    again._make_mode()
    _show(again, Animation([RED, RED, BLUE], 900))
    assert cooler.screen == ("gif", 2) and len(cooler.gifs) == 3


def test_the_animation_of_an_older_deephack_stays_and_the_next_goes_after_it(tmp_path, monkeypatch, cooler):
    """Until 0.19.2 there was one, under one id, and what pace its folder has is not known."""
    cooler.gifs += [["app-gif-0", [], 1000], [GIF_SLOT_ID, [b"an older one"], 2400]]
    config = Config(tmp_path / "config.json")
    config.set("gif_slot_index", 1)
    eng = _engine(tmp_path, monkeypatch)
    _show(eng, Animation([RED, BLUE], 400))
    assert cooler.screen == ("gif", 2) and cooler.gifs[1] == [GIF_SLOT_ID, [b"an older one"], 2400]
    assert cooler.gifs[2][0] == gif_id(200) and eng.config.get("gif_slot_index") == 1


def test_a_first_upload_that_breaks_off_is_not_tried_under_its_id_again(tmp_path, monkeypatch, cooler):
    """It leaves a folder the firmware does not list, and what is sent into that later is not listed
    either, until the cooler was off and on (#67; the model says so when it is done)."""
    monkeypatch.setattr(engine, "MIN_UPLOAD_INTERVAL", 0.0)
    monkeypatch.setattr(engine, "REOPEN_INTERVAL", 0.0)
    cooler.gifs.append(["app-gif-0", [], 1000])
    eng = _engine(tmp_path, monkeypatch)
    whole, packets = cooler.write, [0]

    def breaks(ep, data, timeout=None):
        current = (cooler._upload or {}).get("current", {})
        if current.get("index") == 1 and not bytes(data).startswith(b"dcldfinish"):
            packets[0] += 1
            if packets[0] == 3:                                           # the second frame's third packet
                raise RuntimeError("the cable")
        return whole(ep, data, timeout)

    monkeypatch.setattr(cooler, "write", breaks)
    _show(eng, Animation([RED, BLUE], 400), steps=1)
    assert eng._dev is None and cooler.left_behind == {gif_id(200): 1} and len(cooler.gifs) == 1
    assert eng.config.get("gif_slots") == {"200": {"index": 1, "attempt": 1, "stored": False}}

    monkeypatch.setattr(cooler, "write", whole)
    for _ in range(3):
        eng._device_step(True)
    assert cooler.screen == ("gif", 1) and cooler.gifs[1][0] == gif_id(200, 1) != gif_id(200)
    assert eng.config.get("gif_slots") == {"200": {"index": 1, "attempt": 1, "stored": True}}

    monkeypatch.setattr(cooler, "write", breaks)                          # one that is there: the same id heals it
    packets[0] = 0
    _show(eng, Animation([BLUE, RED], 400), steps=1)
    assert eng._dev is None and eng.config.get("gif_slots") == {"200": {"index": 1, "attempt": 1, "stored": True}}
    monkeypatch.setattr(cooler, "write", whole)
    for _ in range(3):
        eng._device_step(True)
    assert cooler.screen == ("gif", 1) and cooler.gifs[1][0] == gif_id(200, 1) and len(cooler.gifs) == 2


def test_a_picture_that_cannot_be_drawn_yet_is_tried_again_soon(tmp_path, monkeypatch, cooler):
    cooler.direct = True
    eng = _engine(tmp_path, monkeypatch)
    monkeypatch.setattr(engine, "DRAW_SETTLE", 60.0)
    _show(eng, RED)
    assert cooler.draws == 0 and eng._again == engine.DRAW_RETRY          # not left until the mode's next turn
    monkeypatch.setattr(engine, "DRAW_SETTLE", 0.0)
    eng._draw_from = 0.0
    eng._device_step(True)
    assert cooler.screen == _drawn(RED) and eng._again is None


def test_during_a_slide_show_pictures_are_stored_as_before(tmp_path, monkeypatch, cooler):
    cooler.direct = True
    eng = _engine(tmp_path, monkeypatch)
    eng.config.set("slideshow", True)
    _show(eng, RED)
    assert cooler.screen == ("jpg", 1) and cooler.draws == 0 and cooler.flash_writes == 1
    assert not eng.config.get("ground") and not _is_black(cooler.still(1))
    eng.config.set("slideshow", False)    # switched off: drawn from here on, over the ground
    for _ in range(3):
        eng._device_step(True)
    assert cooler.screen == _drawn(RED) and cooler.flash_writes == 2 and _is_black(cooler.still(1))


def test_paused_shows_the_users_picture_and_resumed_draws_again(tmp_path, monkeypatch, cooler):
    cooler.direct = True
    eng = _engine(tmp_path, monkeypatch)
    _show(eng, RED)
    eng._device_step(False)
    assert cooler.screen == ("jpg", 0)    # not the drawn frame: the engine left the image screen and came back
    for _ in range(2):
        eng._device_step(True)
    assert cooler.screen == _drawn(RED) and cooler.flash_writes == 1


def test_deepcools_own_firmware_gets_its_pictures_stored(tmp_path, monkeypatch, cooler):
    eng = _engine(tmp_path, monkeypatch)
    _show(eng, RED)
    assert cooler.screen == ("jpg", 1) and cooler.flash_writes == 1 and cooler.draws == 0
    assert not eng.config.get("ground") and not _is_black(cooler.still(1))
    eng._emit_state(True)
    assert not eng._last_state["drawn"]


@pytest.mark.parametrize("quality", engine.STILL_QUALITIES)
def test_every_quality_gives_a_frame_the_driver_takes(quality):
    assert device.jpeg_size(device.encode_jpeg(RED, quality=quality)) == (device.WIDTH, device.HEIGHT)


def test_pictures_that_come_many_a_second_are_sent_smaller(tmp_path, monkeypatch, cooler):
    cooler.direct = True
    eng = _engine(tmp_path, monkeypatch)
    noisy = Image.radial_gradient("L").resize((480, 640)).convert("RGB")
    eng._mode.tick = 0.05                                                 # a mode that draws twenty times a second
    _show(eng, noisy)
    fast = cooler.screen[1]
    assert fast == engine.frame_jpeg(noisy, engine.DRAW_QUALITY)
    eng._mode.tick = None
    _show(eng, noisy, steps=1)
    assert cooler.screen[1] == engine.frame_jpeg(noisy) and len(fast) < len(cooler.screen[1])


def test_the_version_of_the_patch_is_read_from_the_cooler(cooler):
    with device.Mystique() as m:
        assert m.draw_version() == 0 and not m.can_draw()     # DeepCool's firmware
        cooler.direct = True
        assert m.draw_version() == 1 and m.can_draw()         # the first patch says nothing about itself
        cooler.direct = 2
        assert m.draw_version() == 2 and m.can_draw()


def test_only_the_first_patch_stops_taking_frames_after_an_animation(cooler):
    cooler.gifs.append(["loop", [device.encode_jpeg(RED)], 300])
    jpeg = device.encode_jpeg(BLUE)
    for version, taken in ((1, 1), (2, 3)):
        cooler.direct, cooler.draws = version, 0
        with device.Mystique() as m:
            m.set_mode(device.MODE_SITUATIONAL)
            m.set_mode(device.MODE_MOTION)
            m.show_slot(0, device.TYPE_GIF)
            m.show_slot(0)
            for _ in range(3):
                try:
                    m.draw_jpeg(jpeg, patience=0.01)
                except TimeoutError:
                    pass
        assert cooler.draws == taken


# ---------------------------------------------------------------- a part of the picture (patch 3)
def _part(page, colour, at=(0, 176), size=(480, 288)):
    return Part(page, Image.new("RGB", size, colour), at)


def _part_jpeg(part, quality=engine.DRAW_QUALITY):
    return device.encode_jpeg(part.picture, quality=quality, part=True, tuned=True)


def test_a_picture_of_which_a_part_changes_is_sent_once_and_then_only_the_part(tmp_path, monkeypatch, cooler):
    cooler.direct = 3
    eng = _engine(tmp_path, monkeypatch)
    shown = []
    eng.frameChanged.connect(lambda frames, ms, placeholder: shown.append(frames[0]))
    first = _part(RED, "#ffffff")
    _show(eng, first, steps=3)                                            # the ground, the page, the part
    assert cooler.screen == _drawn(RED) and cooler.draws == 1
    assert cooler.part == (0, 176, _part_jpeg(first)) and cooler.parts == 1
    assert shown[-1].pixelColor(240, 300).red() == 255 and shown[-1].pixelColor(240, 100).red() == 160      # the window: all of it
    for colour in ("#00ff00", "#0000ff", "#ffff00"):
        part = _part(RED, colour)
        _show(eng, part, steps=1)                                         # at once, and the page is not sent again
        assert cooler.part == (0, 176, _part_jpeg(part))
    assert cooler.draws == 1 and cooler.parts == 4 and cooler.flash_writes == 1 and not cooler.violations
    sizes = [len(_part_jpeg(first)), len(engine.frame_jpeg(first.whole, engine.DRAW_QUALITY))]
    assert sizes[0] < sizes[1] * 0.6                                      # which is what it is for
    assert eng._mode.sent_bytes == len(_part_jpeg(part))                  # a mode fits its quality to what is sent

    other = _part(BLUE, "#ffffff")                                        # another page: that first, whole
    _show(eng, other, steps=2)
    assert cooler.screen == _drawn(BLUE) and cooler.draws == 2 and cooler.part == (0, 176, _part_jpeg(other))
    _show(eng, RED, steps=1)                                              # a whole picture: the part is gone
    assert cooler.screen == _drawn(RED) and cooler.part is None and not cooler.violations


def test_a_part_is_sent_whole_to_a_cooler_that_cannot_place_it_and_when_it_does_not_fit(tmp_path, monkeypatch, cooler):
    cooler.direct = 2                                                     # the patch before parts
    eng = _engine(tmp_path, monkeypatch)
    part = _part(RED, "#ffffff")
    _show(eng, part)
    assert cooler.screen == _drawn(part.whole) and cooler.parts == 0 and not cooler.violations

    cooler.direct = 3
    eng = _engine(tmp_path, monkeypatch)
    odd = _part(RED, "#ffffff", size=(480, 270))                          # not whole blocks of a JPEG
    outside = _part(RED, "#ffffff", at=(0, 400))
    assert not odd.fits and not outside.fits and part.fits
    for picture in (odd, outside):
        _show(eng, picture)
        assert cooler.screen == _drawn(picture.whole) and cooler.parts == 0 and not cooler.violations

    cooler.direct = False                                                 # DeepCool's firmware: stored, whole
    eng = _engine(tmp_path, monkeypatch)
    _show(eng, part)
    assert cooler.shown == ("jpg", 1) and cooler.still(1).size == (480, 640) and not cooler.violations


def test_the_page_is_sent_again_when_the_cooler_has_lost_it(tmp_path, monkeypatch, cooler):
    cooler.direct = 3
    eng = _engine(tmp_path, monkeypatch)
    _show(eng, _part(RED, "#ffffff"), steps=3)
    assert cooler.parts == 1
    cooler.drawn = cooler.part = None                                     # its own firmware showed a stored picture
    part = _part(RED, "#00ff00")
    _show(eng, part, steps=3)                                             # "no page": the page, then the part
    assert cooler.screen == _drawn(RED) and cooler.draws == 2 and cooler.part == (0, 176, _part_jpeg(part))
    assert not cooler.violations

    eng._on_screen = None                                                 # and when the engine starts over
    _show(eng, _part(RED, "#0000ff"), steps=3)
    assert cooler.draws == 3 and cooler.parts == 3 and not cooler.violations


def test_the_driver_sends_a_part_only_as_the_cooler_can_take_it(cooler):
    cooler.direct = 3
    cooler.mode, cooler.shown = device.MODE_MOTION, ("jpg", 0)
    dev = device.Mystique()
    page = device.encode_jpeg(RED)
    part = device.encode_jpeg(Image.new("RGB", (160, 96), "#ffffff"), part=True)
    with pytest.raises(device.NoPage):
        dev.draw_jpeg(part, at=(16, 32))                                  # nothing was drawn yet
    dev.draw_jpeg(page)
    dev.draw_jpeg(part, at=(16, 32))
    assert cooler.part == (16, 32, part) and device.part_box(part, (320, 544)) == (320, 544, 160, 96)
    for bad, at in ((part, (321, 0)), (part, (0, 545)), (part, (-16, 0)),                  # not inside the screen
                    (device.encode_jpeg(Image.new("RGB", (100, 96)), part=True), (0, 0)),   # not whole blocks
                    (b"not a JPEG", (0, 0))):
        with pytest.raises(ValueError):
            dev.draw_jpeg(bad, at=at)
    assert cooler.parts == 1 and not cooler.violations
    assert device.encode_jpeg(Image.new("RGB", (160, 96))) != part and device.jpeg_size(device.encode_jpeg(Image.new("RGB", (160, 96)))) == (480, 640)


def test_drawn_pictures_have_huffman_tables_of_their_own_and_stored_ones_do_not(tmp_path, monkeypatch, cooler):
    """The cooler decodes either to the same pixels (seen on the cooler), and the tuned ones are smaller."""
    import io

    picture = Image.new("RGB", (480, 640), "#203040")
    plain, tuned = device.encode_jpeg(picture, quality=85), device.encode_jpeg(picture, quality=85, tuned=True)
    assert len(tuned) < len(plain) * 0.5 and device.jpeg_size(tuned) == (480, 640)       # an empty screen: 2 KB, not 5.4
    assert Image.open(io.BytesIO(tuned)).tobytes() == Image.open(io.BytesIO(plain)).tobytes()      # the same picture
    assert engine.frame_jpeg(picture, 85) == tuned

    cooler.direct = 3
    eng = _engine(tmp_path, monkeypatch)
    _show(eng, picture)
    assert cooler.screen == ("drawn", device.encode_jpeg(picture, quality=engine.STILL_QUALITIES[0], tuned=True))
    _show(eng, _part(picture, "#ffffff"), steps=3)
    assert cooler.part[2] == device.encode_jpeg(Image.new("RGB", (480, 288), "#ffffff"), quality=engine.DRAW_QUALITY, part=True, tuned=True)

    cooler.direct = False                                                 # stored: as DeepCool's app writes it
    eng = _engine(tmp_path, monkeypatch)
    _show(eng, picture)
    assert cooler.stills[1][1] == device.encode_jpeg(picture) and not cooler.violations


def test_a_mode_is_told_when_the_cooler_takes_bytes_at_full_speed(tmp_path, monkeypatch, cooler):
    """Patch 9 makes the USB endpoint ready before it copies a packet: 997 KB a second where it was 540 to
    823. A mode that fits its pictures to the cooler (Video) may make them larger then."""
    for patch, fast, turn in ((2, False, device.SLOW_TURN), (8, False, device.SLOW_TURN), (9, True, device.SLOW_TURN),
                              (11, True, device.SLOW_TURN), (12, True, device.TURN)):
        cooler.direct = patch
        eng = _engine(tmp_path, monkeypatch)
        _show(eng, RED)
        assert eng._fast is fast and eng._drawing, patch                  # (the main loop hands these to the mode)
        assert eng._turn == turn, patch                                   # from patch 12: a picture every turn of the panel
    assert 54 < 1 / device.TURN < 56 and device.SLOW_TURN == 2 * device.TURN
