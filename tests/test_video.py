"""The Video mode, with a small video made here. Nothing is fetched from the net: the one test about a
link gives yt-dlp's place to a stand-in."""
import asyncio
from pathlib import Path
import sys
import time
import types

import pytest
from PIL import Image

from deephack import device, engine
from deephack.config import Config
from deephack.modes import BY_ID, video
from deephack.modes.video import Player, Video

av = pytest.importorskip("av")
FPS, SECONDS, SIZE = 20, 2, (320, 180)


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """Two seconds of video, wider than tall: red on the left, blue on the right, and brighter as it goes on."""
    path = tmp_path_factory.mktemp("video") / "A clip.mp4"
    with av.open(str(path), "w") as out:
        stream = out.add_stream("mpeg4", rate=FPS)
        stream.width, stream.height, stream.pix_fmt = *SIZE, "yuv420p"
        for i in range(FPS * SECONDS):
            level = 60 + 4 * i
            img = Image.new("RGB", SIZE, (level, 0, 0))
            img.paste((0, 0, level), (SIZE[0] // 2, 0, *SIZE))
            for packet in stream.encode(av.VideoFrame.from_image(img)):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    return path


def run(coroutine):
    return asyncio.run(coroutine)


def play(player, seconds):
    """Ask for frames for a while, as the mode does; the numbers of the frames seen and where the video was."""
    seen, until = [], time.monotonic() + seconds
    while time.monotonic() < until:
        player.ask()
        seq, frame = player.latest()
        if frame is not None and (not seen or seen[-1][0] != seq):
            seen.append((seq, player.position))
        time.sleep(0.01)
    return seen


def test_times_are_written_as_a_player_writes_them():
    assert video.clock_text(0) == "0:00" and video.clock_text(754.9) == "12:34" and video.clock_text(3725) == "1:02:05"


def test_a_frame_fills_the_screen_or_is_shown_whole(clip):
    with av.open(str(clip)) as container:
        frame = next(container.decode(video=0))
    fill, fit = video.picture(frame, "fill"), video.picture(frame, "fit")
    assert fill.size == fit.size == (480, 640)
    r, g, b = fill.getpixel((100, 320))
    assert r > 40 and b < 30                                   # the middle of the picture: red left of it ...
    assert fill.getpixel((380, 320))[2] > 40 and fill.getpixel((240, 5))[0] + fill.getpixel((240, 5))[2] > 40   # ... to the edge
    assert fit.getpixel((240, 20)) == (0, 0, 0) and fit.getpixel((240, 620)) == (0, 0, 0)      # bars above and below
    assert fit.getpixel((20, 320))[0] > 40 and fit.getpixel((460, 320))[2] > 40                 # and all of its width


def test_the_player_keeps_time_and_starts_again_at_the_end(clip):
    player = Player(str(clip))
    started = time.monotonic()
    seen = play(player, 1.2)
    assert player.state == "playing" and player.title == "A clip" and 1.8 < player.duration < 2.2
    assert len(seen) >= 12                                     # 20 a second: every one of them was there to be had
    first_at = seen[0][1]
    assert abs((seen[-1][1] - first_at) - (time.monotonic() - started)) < 0.45     # the video moves as the clock does
    seen += play(player, 1.6)
    assert player.opened == 2 and seen[-1][1] < 1.0            # past its end: opened again, from the beginning
    player.stop()


def test_the_player_stops_when_nobody_asks_and_goes_on_where_it_was(clip, monkeypatch):
    monkeypatch.setattr(video, "IDLE", 0.25)
    player = Player(str(clip))
    play(player, 0.8)
    left_at = player.position
    assert 0.4 < left_at < 1.1
    time.sleep(0.7)                                            # another mode has the screen
    assert player.state == "idle" and not player._thread.is_alive()
    seen = play(player, 0.4)
    assert player.opened == 2 and left_at - 0.1 <= seen[0][1] <= left_at + 0.3       # not from the beginning
    player.stop()


def test_a_video_that_will_not_open_is_tried_again(clip, monkeypatch):
    monkeypatch.setattr(video, "RETRY", 0.2)
    answers = [RuntimeError("ERROR: [youtube] abc: Video unavailable\nmore"), (str(clip), {}, "From the net")]

    def resolve(source):
        answer = answers.pop(0) if len(answers) > 1 else answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    player = Player("https://example.invalid/watch", resolve)
    play(player, 0.15)
    assert player.state == "failed" and player.error == "abc: Video unavailable"
    play(player, 0.8)
    assert player.state == "playing" and player.title == "From the net" and not player.error
    player.stop()


def test_a_link_is_asked_of_yt_dlp_for_a_stream_of_the_right_size(monkeypatch):
    asked = {}

    class Stand:
        def __init__(self, options):
            asked.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, link, download):
            asked["link"], asked["download"] = link, download
            return {"url": "https://stream.invalid/video", "title": "A title", "http_headers": {"User-Agent": "x", "Accept": "*/*"}}

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=Stand))
    address, options, title, sound = video.resolve("https://www.youtube.com/watch?v=abc", video.LINES["fit"])
    assert sound is None and "bestaudio" not in asked["format"]            # no sound unless asked for (test_sound.py)
    assert (address, title) == ("https://stream.invalid/video", "A title")
    assert options["headers"] == "User-Agent: x\r\nAccept: */*\r\n" and options["reconnect"] == "1"
    assert asked["download"] is False and asked["noplaylist"] and "height<=480" in asked["format"] and "720" not in asked["format"]


def test_a_file_is_its_own_address(clip):
    assert video.resolve(str(clip)) == (str(clip), {}, "A clip", None)
    assert not video.is_file("https://www.youtube.com/watch?v=abc") and not video.is_file(str(clip) + ".nothing")


# ---- the mode
def test_without_a_video_the_mode_says_what_it_wants():
    mode = Video({})
    assert run(mode.frame()) is None and mode.placeholder == ("Video", "Paste a YouTube link or choose a file")
    assert BY_ID["video"] is Video and Video.quality == video.QUALITY


def test_the_mode_plays_when_pictures_are_drawn(clip):
    async def watch():
        mode = Video({"source": f'"{clip}"', "fit": "fit"})        # as "Copy as path" gives it
        mode.direct = True
        pictures, until = [], time.monotonic() + 1.0
        while time.monotonic() < until:
            img = await mode.frame()
            if img is not None:
                pictures.append(img)
            await asyncio.sleep(mode.tick)
        await mode.close()
        return mode, pictures

    mode, pictures = run(watch())
    assert mode.tick == video.TICK and 14 <= len(pictures) <= 21     # every one of the clip's twenty a second
    assert all(p.size == (480, 640) for p in pictures)
    assert pictures[-1].getpixel((20, 320))[0] > pictures[0].getpixel((20, 320))[0] + 20      # it moved on
    assert mode.status.startswith("A clip · 0:0") and mode.status.endswith(" of 0:02")


def test_a_cooler_that_stores_gets_one_picture_and_the_reason(clip):
    async def watch():
        mode = Video({"source": str(clip)})
        pictures = []
        for _ in range(40):
            img = await mode.frame()
            if img is not None:
                pictures.append(img)
            await asyncio.sleep(0.02)
        return mode, pictures

    mode, pictures = run(watch())
    assert len(pictures) == 1 and pictures[0].size == (480, 640) and mode.tick is None
    assert "direct drawing" in mode.status
    assert not mode._player._wanted()                          # and the reading has been stopped


def test_a_video_that_cannot_be_played_says_why(tmp_path):
    async def watch():
        broken = tmp_path / "broken.mp4"
        broken.write_bytes(b"this is no video at all" * 100)
        mode = Video({"source": str(broken)})
        mode.direct = True
        for _ in range(30):
            assert await mode.frame() is None
            await asyncio.sleep(0.02)
        await mode.close()
        return mode

    mode = run(watch())
    assert mode.status.startswith("Cannot play it: ") and mode.placeholder[0] == "broken"


def test_the_engine_draws_a_modes_pictures_at_the_quality_it_asks_for(tmp_path, monkeypatch, cooler):
    cooler.direct = 2
    monkeypatch.setattr(engine, "_stored_count", lambda kind: 1)
    monkeypatch.setattr(engine, "DRAW_SETTLE", 0.0)
    qualities, real = [], device.encode_jpeg
    monkeypatch.setattr(device, "encode_jpeg", lambda img, quality=92, **how: (qualities.append(quality), real(img, quality, **how))[1])
    eng = engine.Engine(Config(tmp_path / "config.json"))
    eng.config.set("mode", "video")
    eng._make_mode()
    picture = Image.effect_noise((480, 640), 40).convert("RGB")
    for _ in range(3):
        eng._set_frame(picture)
        eng._device_step(True)
    assert cooler.draws >= 1 and qualities[-1] == video.QUALITY       # (the black ground before it is stored at 92)


# ------------------------------------------------------------------ threads (issue #53)
def native_threads() -> int:
    """Threads of this process, Python's and everybody else's. Windows only."""
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("thread", wintypes.DWORD), ("process", wintypes.DWORD),
                    ("base", wintypes.LONG), ("delta", wintypes.LONG), ("flags", wintypes.DWORD)]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    snapshot = ctypes.c_void_p(kernel32.CreateToolhelp32Snapshot(0x4, 0))
    entry, me, count = Entry(ctypes.sizeof(Entry)), kernel32.GetCurrentProcessId(), 0
    more = kernel32.Thread32First(snapshot, ctypes.byref(entry))
    while more:
        count += entry.process == me
        more = kernel32.Thread32Next(snapshot, ctypes.byref(entry))
    kernel32.CloseHandle(snapshot)
    return count


@pytest.mark.skipif(sys.platform != "win32", reason="counts threads the way Windows does")
def test_videos_of_many_sizes_leave_no_threads_behind():
    """ffmpeg gives a chain of filters a thread for every core unless told not to, and deephack keeps a
    chain for each size of video it has seen: on a PC with 32 cores that was 210 idle threads after seven
    sizes, and TikTok's videos come in many."""
    import av

    with video._graphs_lock:
        video._graphs.clear()
    before = native_threads()
    for width, height in ((320, 568), (360, 640), (540, 960), (576, 1024), (720, 1280), (640, 360), (854, 480)):
        frame = av.VideoFrame(width, height, "yuv420p")
        for plane in frame.planes:
            plane.update(bytes(plane.buffer_size))
        assert video.picture(frame, "fill").size == (480, 640) and video.picture(frame, "fit").size == (480, 640)
    assert len(video._graphs) >= 5 and all(graph.threads == 1 for (graph,) in video._graphs.values())
    assert native_threads() - before <= 4                    # (a thread or two of Python's own may come and go)


def test_filters_that_are_dropped_are_freed_soon_not_whenever_python_gets_to_it(monkeypatch, collector):
    """A graph of filters and its filters hold each other, so one that is dropped waits for Python's
    collector, and one that has lived for a while waits long: 66 MB of them after three hours of TikTok,
    0.7 MB a graph (#58). The collector is sent for."""
    import gc

    import av

    from deephack import filters

    def graphs() -> int:
        return sum(type(thing) is av.filter.Graph for thing in gc.get_objects())

    def see(sizes) -> None:
        for width, height in sizes:
            frame = av.VideoFrame(width, height, "yuv420p")
            for plane in frame.planes:
                plane.update(bytes(plane.buffer_size))
            video.picture(frame, "fill")

    monkeypatch.setattr(filters, "AFTER", 0.05)
    with video._graphs_lock:
        video._graphs.clear()
    collector.now()
    others = graphs()                            # (of other tests, should they still be about)
    gc.disable()                                 # nothing but the run that is sent for: by itself the collector may
    try:                                         # happen to come by in a test, which it did not in a night of TikTok
        see((320 + 16 * n, 640) for n in range(9))
        assert graphs() - others == 9
        see([(640, 320)])                        # one more than are kept: the nine are dropped
        assert len(video._graphs) == 1
        assert graphs() - others == 10           # they wait for the collector, which was sent for ...
        assert collector.run()                   # ... (and held until here: counting them is in its way)
        assert graphs() - others == 1
    finally:
        gc.enable()


def test_a_video_is_decoded_by_a_few_threads_not_one_for_every_core(clip, monkeypatch):
    import av

    counts, real = [], av.open

    def opening(*args, **kwargs):
        container = real(*args, **kwargs)
        decode = container.decode

        def decoding(*streams, **more):                      # as the player begins to decode: what did it set?
            counts.extend(stream.thread_count for stream in streams if stream.type == "video")
            return decode(*streams, **more)

        try:
            container.decode = decoding
        except AttributeError:                               # a container that takes no such thing: ask it now
            counts.extend(stream.thread_count for stream in container.streams.video)
        return container

    monkeypatch.setattr(av, "open", opening)
    player = Player(str(clip))
    play(player, 0.4)
    player.stop()
    assert player.latest()[1] is not None                    # it plays
    assert video.DECODERS <= 4
    with real(str(clip)) as container:                       # and the name deephack sets is one PyAV has
        stream = container.streams.video[0]
        stream.thread_count = video.DECODERS
        assert stream.thread_count == video.DECODERS
    assert "video.thread_count = DECODERS" in Path(video.__file__).read_text(encoding="utf8")


# ------------------------------------------------------------------ as many pictures as the video has (issue #47)
def test_a_picture_may_be_as_large_as_the_cooler_takes_in_a_frames_time():
    assert video.TICK < 1 / video.MOST_A_SECOND                       # asked more often than any video has a picture
    assert 20_000 < video.room_for(30) < 24_000 < video.room_for(25) < 30_000
    assert video.room_for(60) == video.room_for(30) == video.room_for(0)      # 60 a second is not tried; unknown: as 30


def test_the_quality_gives_way_before_the_number_of_pictures_does():
    room = video.room_for(30)
    assert video.quality_for(65, room * 2, 30) == 62                  # too large: a little less sharp
    assert video.quality_for(65, room, 30) == 65 == video.quality_for(65, 0, 30)      # it fits (or nothing was sent yet)
    assert video.quality_for(50, room // 2, 30) == 51                 # room again: a little sharper
    assert video.quality_for(video.QUALITY, 1000, 30) == video.QUALITY                # never more than the best
    quality = video.QUALITY
    for _ in range(40):
        quality = video.quality_for(quality, room * 3, 30)
    assert quality == video.LEAST_QUALITY                             # ... nor less than the least
    assert video.quality_for(65, room * 1.2, 25) == 65                # a video of 25 a second has more room
    # the patch from version 9 takes the bytes faster, and then the panel's turn of 36 ms is what counts
    assert video.room_for(30, fast=True) == video.room_for(25, fast=True) == video.FAST_ROOM > room * 1.4
    assert video.quality_for(60, room * 1.1, 30, fast=True) == 61 and video.quality_for(60, room * 1.1, 30) == 57
    assert video.quality_for(60, video.FAST_ROOM * 1.1, 30, fast=True) == 57
    assert video.quality_for(video.QUALITY, 1000, 30, fast=True) == video.QUALITY + 1            # and sharper than before,
    assert video.quality_for(video.FAST_QUALITY, 1000, 30, fast=True) == video.FAST_QUALITY      # up to a point
    assert video.quality_for(video.FAST_QUALITY, 1000, 30) == video.FAST_QUALITY                 # (never pulled down for room)
    # from version 12 a picture is on the glass every turn of the panel: a frame has all the time its video gives it
    every = device.TURN
    assert 27_000 < video.room_for(30, True, every) < 29_000 and 33_000 < video.room_for(25, True, every) < 35_000
    assert video.room_for(60, True, every) == video.room_for(30, True, every)                    # 60 a second is still not tried
    assert 14_000 < video.room_for(55.4, True, every, most=55.4) < 16_000                         # ... unless it is asked for
    assert video.room_for(25, True, device.SLOW_TURN) == video.FAST_ROOM and video.room_for(25, False, every) == video.room_for(25)


def test_the_engine_tells_a_mode_how_large_its_picture_was(tmp_path, monkeypatch, cooler):
    cooler.direct = 2
    monkeypatch.setattr(engine, "_stored_count", lambda kind: 1)
    monkeypatch.setattr(engine, "DRAW_SETTLE", 0.0)
    eng = engine.Engine(Config(tmp_path / "config.json"))
    eng.config.set("mode", "video")
    eng._make_mode()
    assert eng._mode.sent_bytes == 0
    picture = Image.effect_noise((480, 640), 40).convert("RGB")
    for _ in range(3):
        eng._set_frame(picture)
        eng._device_step(True)
    assert cooler.draws >= 1
    assert eng._mode.sent_bytes == len(device.encode_jpeg(picture, quality=video.QUALITY, tuned=True))     # the JPEG as it went out


def test_the_mode_makes_its_pictures_smaller_when_they_are_too_large(clip):
    async def watch():
        mode = Video({"source": str(clip)})
        mode.direct = True
        seen = []
        until = time.monotonic() + 0.8
        while time.monotonic() < until:
            if await mode.frame() is not None:
                mode.sent_bytes = 90_000                              # as the engine would say of a busy picture
                seen.append(mode.quality)
            await asyncio.sleep(mode.tick)
        await mode.close()
        return mode, seen

    mode, seen = run(watch())
    assert len(seen) > 5 and seen[-1] < seen[0] <= video.QUALITY and seen[-1] >= video.LEAST_QUALITY
    assert Video.quality == video.QUALITY                             # the next video starts at its best again
    assert mode._player.rate == pytest.approx(FPS)


# ---- Pause, and ten seconds back or forward
def test_a_paused_player_holds_its_picture_and_goes_on_from_there(clip):
    player = Player(str(clip))
    play(player, 0.5)
    player.pause(True)
    time.sleep(0.1)
    held = player.position
    assert 0.2 < held < 0.9
    assert play(player, 0.4)[-1][1] == held                  # asked for all the while: it stands
    player.pause(False)
    after = play(player, 0.4)
    assert held + 0.2 < after[-1][1] < held + 0.7            # on from where it stood, not from where it would be
    player.stop()


def test_the_mode_pauses_and_jumps(clip):
    async def frames(mode, seconds):
        pictures, until = [], time.monotonic() + seconds
        while time.monotonic() < until:
            img = await mode.frame()
            if img is not None:
                pictures.append(img)
            await asyncio.sleep(mode.tick)
        return pictures

    async def watch():
        mode = Video({"source": str(clip)})
        mode.direct = True
        assert dict(Video.actions)["pause"] == "Pause" and {"back", "forward"} <= set(dict(Video.actions))
        assert {s.action: s.default for s in Video.settings if s.kind == "shortcut"} == {
            "pause": "", "back": "", "forward": "", "mute": ""}           # keys for them where they are set
        mode.act("forward")                                  # nothing plays yet: nothing to jump in
        assert len(await frames(mode, 0.5)) >= 5
        mode.act("pause")
        await frames(mode, 0.15)
        held = mode._player.position
        assert await frames(mode, 0.4) == [] and mode._player.position == held and mode.status.endswith(" · paused")
        mode.act("forward")                                  # a clip of two seconds: to a second before its end
        there = await frames(mode, 1.0)
        assert len(there) == 1 and 0.95 <= mode._player.position <= 1.1 and "paused" in mode.status      # and it stays paused
        assert there[0].getpixel((20, 320))[0] > 130         # (the clip is brighter as it goes on: 60 at first, 140 there)
        mode.act("pause")
        assert len(await frames(mode, 0.4)) >= 4 and mode._player.position > 1.2 and "paused" not in mode.status
        mode.act("back")
        await frames(mode, 0.4)
        assert mode._player.position < 0.6                   # ten seconds back from there: its beginning
        await mode.close()

    run(watch())
