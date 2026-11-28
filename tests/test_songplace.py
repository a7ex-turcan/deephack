"""Where in a music video the song is, by its sound (songplace.py). The "music" is made here: notes at
random, four a second, so that no stretch of it is like another. Nothing is played and nothing is heard:
the samples go straight in."""
import math
import random
import threading
import time
from fractions import Fraction

import pytest

from deephack import audio, songplace as sp

av = pytest.importorskip("av")
RATE = 8000
TONES = [110 * 2 ** (k / 6) for k in range(30)]              # 110 Hz to 3.1 kHz


def music(seed: int, seconds: float) -> list[float]:
    rnd, out, n = random.Random(seed), [], RATE // 4
    for _ in range(round(seconds * 4)):
        tones = [2 * math.pi * rnd.choice(TONES) / RATE for _ in range(rnd.randint(1, 3))]
        loud = rnd.uniform(0.1, 0.5) / len(tones)
        out += [loud * min(1.0, i / 80, (n - i) / 80) * sum(math.sin(tone * i) for tone in tones) for i in range(n)]
    return out


def rows_of(samples: list[float]) -> list[list[float]]:
    loudness, rows = sp.Loudness(rate=RATE), []
    for start in range(0, len(samples), 800):                # as it is captured: a tenth of a second at a time
        rows += loudness.hear(samples[start:start + 800])
    return rows + loudness.end()


def test_a_loudness_that_is_done_with_has_its_filters_freed_soon(monkeypatch, collector):
    """Its graph of filters is not freed with it (the graph and its filters hold each other), and the Ear
    makes a new one after every silence: 1.1 MB each until Python's collector comes by (#58)."""
    import gc

    from deephack import filters

    def graphs() -> int:
        return sum(type(thing) is av.filter.Graph for thing in gc.get_objects())

    monkeypatch.setattr(filters, "AFTER", 0.05)
    collector.now()
    others = graphs()
    gc.disable()
    try:
        ear = sp.Ear()
        for n in range(5):                       # five pieces of sound with silence between them
            ear.hear([0.1] * 800, RATE, n * 10.0)
        assert graphs() - others == 5
        assert collector.run()                   # (held until here: counting them is in the collector's way)
        assert graphs() - others == 1            # the one that is listening
    finally:
        gc.enable()


@pytest.fixture(scope="module")
def song():
    """Forty seconds of a song: its samples, and its rows as the PC would have played them."""
    samples = music(1, 40)
    return samples, rows_of(samples)


@pytest.fixture(scope="module")
def video(song):
    """Its video: a scene of seven seconds, then the song."""
    return sp.Whole(rows_of(music(2, 7) + song[0]))


def piece(rows, until: float):
    """What was heard in the WINDOW seconds before `until`."""
    end = round(until * sp.PER)
    return rows[end - round(sp.WINDOW * sp.PER):end]


def test_loudness_is_fifty_rows_a_second_of_eight_bands_in_step_with_the_sound():
    quiet = [0.0] * RATE * 2
    tone = [0.5 * math.sin(2 * math.pi * 1000 * i / RATE) for i in range(RATE // 10)]       # a tenth of a second of 1 kHz
    rows = rows_of(quiet + tone + quiet)
    assert abs(len(rows) - 4.1 * sp.PER) <= 2 and all(len(row) == sp.BANDS for row in rows)
    edges = [sp.LOW * (sp.HIGH / sp.LOW) ** (i / sp.BANDS) for i in range(sp.BANDS + 1)]
    band = next(i for i in range(sp.BANDS) if edges[i] <= 1000 < edges[i + 1])
    loudest = max(range(len(rows)), key=lambda i: rows[i][band])
    assert 2.0 <= loudest / sp.PER <= 2.2                    # where the tone is, to within the 6 Hz it is smoothed by
    assert rows[loudest][band] > 3 and abs(rows[50][band]) < 0.01      # a level is the logarithm less the second before


def test_a_piece_that_was_heard_is_found_where_it_is_in_the_video(song, video):
    samples, rows = song
    assert abs(video.seconds - 47) < 0.1
    at, alike, other = video.everywhere(piece(rows, 22.0))   # the song from 10 to 22 s: in the video from 17 s
    assert abs(at / sp.PER - 17.0) <= 0.04 and alike > 0.9 and alike - other > sp.OVER
    assert video.around(piece(rows, 22.0), at, 50)[:2] == (at, alike)                     # looked for near there: the same
    late = video.around(piece(rows, 22.0), at + 400, 50)     # ... and not where it is not
    assert late[1] < sp.KEEP
    assert video.around(piece(rows, 22.0), 10 ** 6, 50) is None and sp.Whole(rows[:100]).everywhere(piece(rows, 22.0)) is None
    silence = [[0.0] * sp.BANDS] * round(sp.WINDOW * sp.PER)
    assert video.everywhere(silence)[1] == 0.0               # nothing to go by is like nothing


def test_the_place_counts_once_three_looks_say_the_same_and_is_followed_from_there(song, video):
    samples, rows = song
    follower = sp.Follower(video)
    assert follower.look(piece(rows, 12.0), 12.0) is None    # one look is not believed yet,
    assert follower.look(piece(rows, 14.0), 14.0) is None    # nor two: their pieces are ten seconds the same
    assert abs(follower.look(piece(rows, 16.0), 16.0) - 7.0) <= 0.04
    for at in range(18, 40, 2):
        assert abs(follower.look(piece(rows, at), float(at)) - 7.0) <= 0.04
    # the player's clock is half a second off for a moment: the lead is what the video is ahead of that clock
    assert abs(follower.look(piece(rows, 30.0), 30.5) - 6.5) <= 0.04

    apart = sp.Follower(video)                               # looks that do not say the same place start the count anew
    assert apart.look(piece(rows, 12.0), 12.0) is None and apart.look(piece(rows, 14.0), 20.0) is None
    assert apart.look(piece(rows, 16.0), 16.0) is None and apart.look(piece(rows, 18.0), 18.0) is None
    assert abs(apart.look(piece(rows, 20.0), 20.0) - 7.0) <= 0.04


def test_the_song_is_looked_for_only_where_the_videos_length_lets_it_be(song, video):
    samples, rows = song                                     # the video is 47 s for a track of 40: the song begins in
    follower = sp.Follower(video, 40.0)                      # its first 7 s, give or take SLACK
    assert abs(follower._leads[0] + sp.SLACK) < 0.01 and abs(follower._leads[1] - 7.0 - sp.SLACK) < 0.1
    for at in (12.0, 14.0, 16.0):
        lead = follower.look(piece(rows, at), at)
    assert abs(lead - 7.0) <= 0.04
    short = sp.Follower(video, 70.0)                         # were the track 70 s, the song could not begin 7 s in ...
    assert short._leads == (-sp.SLACK, sp.SLACK)
    far = sp.Follower(sp.Whole(rows_of(music(2, 30) + samples)), 68.0)       # ... and here it begins 30 s in, where a
    assert all(far.look(piece(rows, at), at) is None for at in (12.0, 14.0, 16.0, 18.0))     # video 2 s longer cannot have it
    at, alike, other = video.everywhere(piece(rows, 22.0), 0, 400)           # looked for in the first 8 s only: not there
    assert alike < sp.ALIKE and video.everywhere(piece(rows, 22.0), 5000, None) is None


def test_a_scene_put_into_the_video_is_followed_and_another_recording_is_not_believed(song):
    samples, rows = song
    cut = sp.Whole(rows_of(music(2, 7) + samples[:20 * RATE] + music(3, 3) + samples[20 * RATE:]))    # three seconds put in
    follower, leads = sp.Follower(cut), []
    for at in range(12, 40, 2):
        leads.append(follower.look(piece(rows, at), float(at)))
    assert leads[:2] == [None, None] and all(abs(lead - 7.0) <= 0.04 for lead in leads[2:5])  # up to 20 s: 7 s ahead
    assert all(abs(lead - 10.0) <= 0.04 for lead in leads[-3:])                               # in the end: 10
    assert all(lead is not None and min(abs(lead - 7.0), abs(lead - 10.0)) <= 0.04 for lead in leads[2:])   # and never elsewhere

    other = sp.Follower(sp.Whole(rows_of(music(4, 47))))     # the same length, another song
    assert all(other.look(piece(rows, at), float(at)) is None for at in range(12, 40, 2))


def test_the_ear_keeps_the_last_seconds_and_a_silence_breaks_them_off():
    ear, samples, now = sp.Ear(), music(5, 16), 500.0
    assert ear.last() is None
    for start in range(0, 11 * RATE, 160):                   # eleven seconds, a fiftieth at a time, each as it is played
        now += 0.02
        ear.hear(samples[start:start + 160], RATE, now)
    assert ear.last() is None and ear.last(10.0) is not None                # not twelve seconds in one stretch yet
    for start in range(11 * RATE, 13 * RATE, 160):
        now += 0.02
        ear.hear(samples[start:start + 160], RATE, now)
    rows, when = ear.last()
    assert len(rows) == round(sp.WINDOW * sp.PER)
    assert 0.0 <= now - when < 0.5                           # the newest rows are of a moment ago: the filters take that long
    at, alike, other = sp.Whole(rows_of(samples)).everywhere(rows)
    assert abs(at / sp.PER - (when - 500.0 - sp.WINDOW)) <= 0.04 and alike > 0.95        # and `when` is when they were heard
    ear.hear([], RATE, now + 1.0)                            # a read that brought nothing changes nothing
    assert ear.last()[1] == when
    now += 5.0                                               # the player was paused: what comes now is a new stretch
    ear.hear(samples[:160], RATE, now)
    assert ear.last() is None and ear.last(0.0) is not None


def test_the_ear_taps_the_listener_and_keeps_it_listening():
    class Listener:
        def __init__(self):
            self.taps, self.asked = [], 0

        def ask(self):
            self.asked += 1

    listener = Listener()
    ear = sp.Ear(listener)
    ear.ask()
    ear.ask()
    assert listener.taps == [ear.hear] and listener.asked == 2
    assert audio.LISTENER.taps == []                         # no test has made the real one listen


def test_the_listener_hands_every_read_to_its_taps():
    class Capture:
        rate = 48000

        def read(self):
            return [0.25] * 960

        def close(self):
            pass

    def broken(samples, rate, now):
        raise ValueError("a tap that trips")

    listener, got = audio.Listener(Capture), []
    listener.taps += [broken, lambda samples, rate, now: got.append((len(samples), rate))]
    listener.ask()
    for _ in range(100):
        if len(got) >= 2:
            break
        time.sleep(0.02)
    assert listener.levels()[1] > 0 and broken not in listener.taps          # it is left out, and the listening goes on
    listener._asked = float("-inf")                          # nobody asks any more: its thread ends
    listener._thread.join(2.0)
    assert got[:2] == [(960, 48000), (960, 48000)] and not listener._thread.is_alive()


def test_the_time_of_what_is_heard_holds_when_the_sound_cards_clock_is_not_the_pcs():
    rnd = random.Random(7)
    ear, now = sp.Ear(), 100.0
    for _ in range(60 * 50):                                 # a minute of sound from a card that runs 1 % slow:
        now += 0.0202                                        # 20 ms of samples take 20.2 ms
        ear.hear([rnd.uniform(-0.3, 0.3) for _ in range(160)], RATE, now)
    rows, when = ear.last()
    assert 0.2 < now - when < 0.5                            # the newest row is a third of a second old, as ever (and
                                                             # not that plus the 0.6 s the card has fallen behind)


def test_a_place_reads_the_videos_sound_and_then_looks_at_what_is_heard(song, video):
    samples, rows = song
    heard = {"until": 12.0}

    class Ear:
        asked = 0

        def ask(self):
            Ear.asked += 1

        def last(self):
            heard["until"] += sp.EVERY                       # every look, two seconds more of the song have played
            return (piece(rows, heard["until"]), 1000.0 + heard["until"]) if heard["until"] <= 40 else None

    def pause(seconds):
        time.sleep(0.0005)                                   # (no waiting here: the next look comes at once)

    place = sp.Place("link", lambda when: when - 1000.0, 40.0, Ear(), lambda link: video, pause)
    for _ in range(400):
        if place.lead is not None and heard["until"] >= 24:
            break
        time.sleep(0.01)
    assert place.state == "listening" and abs(place.lead - 7.0) <= 0.04
    assert Ear.asked > heard["until"] / sp.EVERY             # asked between the looks too: the listener must not stop
    place.close()
    place._thread.join(2.0)
    assert not place._thread.is_alive()

    def no_sound(link):
        raise OSError("no net\nand a second line")

    failed = sp.Place("link", lambda when: 0.0, 40.0, Ear(), no_sound, pause)
    failed._thread.join(2.0)
    assert failed.state == "failed" and failed.error == "no net" and failed.lead is None

    paused = sp.Place("link", lambda when: None, None, Ear(), lambda link: video, pause) # the music's place is not known
    time.sleep(0.2)
    paused.close()
    paused._thread.join(2.0)
    assert paused.lead is None and threading.active_count() >= 1


def test_the_sound_of_a_file_is_read_whole(tmp_path, song):
    samples, rows = song
    path = tmp_path / "sound.wav"
    with av.open(str(path), "w") as out:
        stream = out.add_stream("pcm_s16le", rate=RATE, layout="mono")
        for start in range(0, 15 * RATE, RATE):
            frame = av.AudioFrame(format="s16", layout="mono", samples=RATE)
            frame.planes[0].update(b"".join(round(v * 32767).to_bytes(2, "little", signed=True) for v in samples[start:start + RATE]))
            frame.sample_rate, frame.pts, frame.time_base = RATE, start, Fraction(1, RATE)
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    read = sp.rows_of(str(path))
    assert abs(len(read) - 15 * sp.PER) <= 2
    at, alike, other = sp.Whole(read).everywhere(rows[100:400])              # the song from 2 to 8 s is in it at 2 s
    assert abs(at - 100) <= 2 and alike > 0.9
    silent = tmp_path / "silent.mp4"
    with av.open(str(silent), "w") as out:
        stream = out.add_stream("mpeg4", rate=10)
        stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
        for packet in stream.encode(av.VideoFrame(64, 48, "yuv420p")):
            out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    with pytest.raises(ValueError, match="no sound"):
        sp.rows_of(str(silent))
