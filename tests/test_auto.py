import asyncio
from datetime import datetime, timedelta, timezone

from PIL import Image

from deephack import engine
from deephack.config import Config
from deephack.modes import auto, nba
from deephack.modes.base import Animation, Dashboard, Mode, parse_order


class Fake(Mode):
    """A mode whose activity and frames the test controls."""

    def __init__(self, mode_id, colour):
        super().__init__()
        self.id, self.title, self.colour = mode_id, mode_id.title(), colour
        self.pending = Image.new("RGB", (480, 640), colour)

    async def frame(self):
        img, self.pending = self.pending, None
        return img


def make(order="a,b,-c", fallback="weather"):
    a = auto.Auto({"order": "", "fallback": "weather"})
    a.order = [i for i, on in parse_order(order, ["a", "b", "c"]) if on]
    a.fallback = fallback
    a.children = {"a": Fake("a", "red"), "b": Fake("b", "green"), "c": Fake("c", "blue"), fallback: Fake(fallback, "gray")}
    return a


def step(a, clock, monkeypatch, seconds=1.0):
    clock[0] += seconds
    monkeypatch.setattr(auto.time, "monotonic", lambda: clock[0])
    return asyncio.run(a.frame())


def colour(img):
    return img.getpixel((0, 0)) if img is not None else None


def test_parse_order():
    ids = ["x", "y", "z"]
    assert parse_order("y,-x", ids) == [("y", True), ("x", False), ("z", False)]
    assert parse_order("bogus, z ,z,-y", ids) == [("z", True), ("y", False), ("x", False)]
    assert parse_order("", ids) == [("x", False), ("y", False), ("z", False)]


def test_fallback_until_a_mode_has_something(monkeypatch):
    a, clock = make(), [0.0]
    assert colour(step(a, clock, monkeypatch)) == (128, 128, 128) and a.chosen == "weather"
    assert step(a, clock, monkeypatch) is None                       # nothing new: no write


def test_priority_order_and_linger(monkeypatch):
    a, clock = make(), [0.0]
    step(a, clock, monkeypatch)
    a.children["b"].active = True
    assert colour(step(a, clock, monkeypatch)) == (0, 128, 0)       # b has something
    a.children["a"].active = True
    assert colour(step(a, clock, monkeypatch)) == (255, 0, 0)       # a ranks higher
    a.children["a"].active = False
    assert step(a, clock, monkeypatch, auto.LINGER - 5) is None      # a lingers on
    assert colour(step(a, clock, monkeypatch, 10)) == (0, 128, 0)   # then b, still active, takes over
    a.children["b"].active = False
    step(a, clock, monkeypatch, auto.LINGER + 1)
    assert a.chosen == "weather"


def test_switched_off_modes_and_frameless_modes_never_win(monkeypatch):
    a, clock = make(), [0.0]
    a.children["c"].active = True                                    # "-c": not in the rotation
    a.children["a"].active = True
    a.children["a"].pending = None                                   # active, but nothing drawn yet
    step(a, clock, monkeypatch)
    assert a.chosen == "weather"


def test_new_frames_of_the_chosen_mode_pass_through(monkeypatch):
    a, clock = make(), [0.0]
    a.children["a"].active = True
    step(a, clock, monkeypatch)
    a.children["a"].pending = Image.new("RGB", (480, 640), "yellow")
    a.children["b"].pending = Image.new("RGB", (480, 640), "white")  # b is not showing: ignored
    assert colour(step(a, clock, monkeypatch)) == (255, 255, 0)
    assert step(a, clock, monkeypatch) is None


# ------------------------------------------------------------------ drawn pictures (the direct drawing firmware)
def test_drawn_auto_gives_the_screen_up_after_seconds(monkeypatch):
    a, clock = make(), [0.0]
    a.direct = True
    a.children["a"].active = True
    assert colour(step(a, clock, monkeypatch)) == (255, 0, 0)
    a.children["a"].active = False
    assert step(a, clock, monkeypatch, auto.LINGER_DRAWN - 1) is None and a.chosen == "a"      # against flicker
    assert step(a, clock, monkeypatch, 2) is not None and a.chosen == "weather"
    assert auto.LINGER_DRAWN < auto.LINGER / 10


def test_drawn_auto_fades_from_one_mode_to_the_next(monkeypatch):
    a, clock = make(), [0.0]
    a.direct = True
    assert colour(step(a, clock, monkeypatch)) == (128, 128, 128) and a.tick is None            # the first: no fade
    assert step(a, clock, monkeypatch) is None
    a.children["a"].active = True
    reds = []
    while (img := step(a, clock, monkeypatch, auto.FADE_TICK)) is not None:
        reds.append(colour(img)[0])
        assert a.tick == auto.FADE_TICK or colour(img) == (255, 0, 0)
    assert reds[0] > 128 and reds == sorted(reds) and reds[-1] == 255 and len(set(reds)) >= 8   # grey into red, in steps
    assert abs(len(reds) * auto.FADE_TICK - auto.FADE) <= auto.FADE_TICK and a.tick is None      # and done
    # the mode fading in keeps moving; the one fading out is the picture it left
    a.children["a"].active = False
    step(a, clock, monkeypatch, auto.LINGER_DRAWN + 1)
    first = step(a, clock, monkeypatch, auto.FADE_TICK)
    a.children["weather"].pending = Image.new("RGB", (480, 640), "blue")
    second = step(a, clock, monkeypatch, auto.FADE_TICK)
    assert colour(first)[2] < colour(second)[2] and colour(second)[0] > 0                        # blue coming, red going
    # a switch while it fades goes on from the mixed picture, not from a clean one
    a.children["a"].active = True
    third = step(a, clock, monkeypatch, auto.FADE_TICK)
    assert a.chosen == "a" and 0 < colour(third)[2] < colour(second)[2]
    last = [img for img in (step(a, clock, monkeypatch, auto.FADE_TICK) for _ in range(12)) if img is not None][-1]
    assert colour(last) == (255, 0, 0)


def test_no_fade_on_stock_firmware_or_with_a_sensor_screen(monkeypatch):
    a, clock = make(), [0.0]
    step(a, clock, monkeypatch)
    a.children["a"].active = True
    assert colour(step(a, clock, monkeypatch)) == (255, 0, 0) and a.tick is None                # stored: at once, whole
    a, clock = make(), [0.0]
    a.direct = True
    gauges = Dashboard("dashboard", (0, 0, 0), {}, Image.new("RGB", (480, 640), "white"))
    a.children["weather"].pending = gauges                                                       # e.g. Live as the fallback
    assert step(a, clock, monkeypatch) is gauges
    a.children["a"].active = True
    assert colour(step(a, clock, monkeypatch)) == (255, 0, 0) and a.tick is None                # nothing of ours to fade from
    a.children["a"].active = False
    assert step(a, clock, monkeypatch, auto.LINGER_DRAWN + 1) is gauges and a.tick is None      # nor to


def test_auto_builds_children_with_their_own_settings():
    seen = []
    a = auto.Auto({"order": "nba,-game_cover", "fallback": "ticker"}, lambda mode_id: seen.append(mode_id) or {})
    assert list(a.children) == ["nba", "ticker"] and seen == ["nba", "ticker"]


def test_nba_claims_around_the_picked_teams_games():
    now = datetime(2026, 11, 20, 1, 0, tzinfo=timezone.utc)

    def game(hours, state):
        g = nba.parse_event({"date": (now + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%MZ"), "status": {"type": {"state": state}},
                             "competitions": [{"competitors": [{"homeAway": "home", "team": {"abbreviation": "GS"}},
                                                               {"homeAway": "away", "team": {"abbreviation": "MEM"}}]}]})
        return g

    m = nba.Nba({"team": "GS"})
    assert not m.claiming(now)                                       # nothing fetched yet
    m._games = ([game(-30, "post")], [game(5, "pre")], None)
    assert not m.claiming(now)
    m._games = ([game(-30, "post")], [game(0.5, "pre")], None)
    assert m.claiming(now)                                           # tip-off within the hour
    m._games = ([game(-3, "post")], [game(40, "pre")], None)
    assert m.claiming(now)                                           # final not long ago
    m._games = ([game(-4, "post")], [game(40, "pre")], None)
    assert not m.claiming(now)
    assert not nba.Nba({"team": "all"}).claiming(now)


# ------------------------------------------------------------------ engine: no upload for an image already stored
def _engine(tmp_path, monkeypatch):
    config = Config(tmp_path / "config.json")
    config.set("slot_index", 1)                       # the model holds one still of the official app before ours
    monkeypatch.setattr(engine, "_stored_count", lambda kind: {"jpg": 1, "gif": 0}[kind])     # ... and no animation
    eng = engine.Engine(config)
    clock = [1000.0]
    monkeypatch.setattr(engine.time, "monotonic", lambda: clock[0])
    return eng, config, clock


def test_engine_skips_uploads_of_stored_images(tmp_path, monkeypatch, cooler):
    eng, _, clock = _engine(tmp_path, monkeypatch)

    def show(frame, wait=engine.MIN_UPLOAD_INTERVAL + 1):
        clock[0] += wait
        eng._frame, eng._frame_seq = frame, eng._frame_seq + 1
        before = cooler.flash_writes
        eng._device_step(True)
        return cooler.flash_writes - before, cooler.screen

    still = Image.new("RGB", (480, 640), "red")
    pet = Animation([Image.new("RGB", (480, 640), c) for c in ("blue", "green")], 1000)
    assert show(still) == (1, ("jpg", 1))
    assert show(pet) == (2, ("gif", 0))                                   # an animation: a write per frame
    assert show(Image.new("RGB", (480, 640), "red"), wait=0) == (0, ("jpg", 1))   # back to the same still: no write, no wait
    assert show(Animation([Image.new("RGB", (480, 640), c) for c in ("blue", "green")], 1000), wait=0) == (0, ("gif", 0))
    assert show(Image.new("RGB", (480, 640), "white"), wait=0) == (0, ("gif", 0))  # new content waits for the rate limit
    assert cooler.still(1).getpixel((10, 10))[0] > 200 and len(cooler.stills) == 2
    assert engine.digest(still) != engine.digest(pet)


def test_preview_never_reaches_the_cooler_and_is_promoted_when_shown(tmp_path, monkeypatch, cooler):
    class Still(Mode):
        id, title = "still", "Still"
        builds = 0

        def __init__(self, values=None):
            super().__init__(values)
            Still.builds += 1
            self.pending = Image.new("RGB", (480, 640), "orange")

        async def frame(self):
            img, self.pending = self.pending, None
            return img

    monkeypatch.setitem(engine.BY_ID, "still", Still)
    eng, config, clock = _engine(tmp_path, monkeypatch)
    previews, lives = [], []
    eng.previewChanged.connect(lambda mode_id, frames, ms, placeholder: previews.append((mode_id, placeholder)))
    eng.frameChanged.connect(lambda frames, ms, placeholder: lives.append(placeholder))
    eng._make_mode()                                   # the configured mode (the first one) is live
    eng._make_preview("still")
    asyncio.run(eng._preview_step())
    assert previews == [("still", True), ("still", False)]
    eng._device_step(True)
    assert cooler.flash_writes == 0 and len(cooler.stills) == 1      # the preview's image is not sent
    assert asyncio.run(eng._preview_step()) is None and len(previews) == 2

    config.set("mode", "still")
    eng._make_mode()                                   # "Show on cooler": the running preview takes over
    assert Still.builds == 1 and eng._preview is None and isinstance(eng._mode, Still)
    assert lives[-1] is False                          # with the frame it already drew, no placeholder
    clock[0] += engine.MIN_UPLOAD_INTERVAL + 1
    eng._device_step(True)
    assert cooler.flash_writes == 1 and cooler.screen == ("jpg", 1) and cooler.still(1).getpixel((5, 5))[0] > 200


def test_the_chosen_modes_own_lights_are_autos(monkeypatch):
    a, clock = make(), [0.0]
    step(a, clock, monkeypatch)
    assert a.lights is None and a.lights_fade is None        # the fallback says nothing: the picture's edge
    own = [(1, 2, 3)] * 14
    a.children["b"].lights, a.children["b"].lights_fade = own, 0.25
    step(a, clock, monkeypatch)
    assert a.lights is None                                  # b is not on screen: its lights are nobody's
    a.children["b"].active = True
    step(a, clock, monkeypatch)
    assert a.chosen == "b" and a.lights == own and a.lights_fade == 0.25
    a.children["b"].active = False
    step(a, clock, monkeypatch, auto.LINGER + 1)
    assert a.chosen == "weather" and a.lights is None and a.lights_fade is None
