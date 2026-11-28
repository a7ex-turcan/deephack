"""Sending for Python's collector when a filter graph was dropped (filters.py). The graphs themselves are
in test_video.py and test_songplace.py; here it is the collector that is in the way."""
import gc
import threading
import time

from deephack import filters


class Garbage:
    """Something only the collector frees: it holds itself."""

    freed = 0

    def __init__(self):
        self.me = self

    def __del__(self):
        Garbage.freed += 1


class Slow:
    """Garbage whose end takes a while, with other threads free to run meanwhile: a collection that is held up."""

    def __init__(self, seconds: float):
        self.me, self.seconds = self, seconds

    def __del__(self):
        time.sleep(self.seconds)


def test_a_run_that_python_did_not_make_is_asked_for_again(monkeypatch):
    """Python lets one thread collect at a time, and gives a second that asks meanwhile nothing, without
    a word. A graph dropped while another collection was at work stayed until the next drop."""
    monkeypatch.setattr(filters, "AFTER", 0.05)
    monkeypatch.setattr(filters, "AGAIN", 0.05)
    gc.collect()
    gc.disable()
    try:
        Slow(0.8)
        other = threading.Thread(target=gc.collect)
        other.start()
        time.sleep(0.2)                                      # the other collection is inside Slow's end now
        before = Garbage.freed
        Garbage()
        assert filters.collect_now() is False and Garbage.freed == before      # sent away with nothing done
        filters.dropped()
        until = time.monotonic() + 5
        while Garbage.freed == before and time.monotonic() < until:
            time.sleep(0.02)
        assert Garbage.freed == before + 1                   # ... and asked again until it was
        other.join()
    finally:
        gc.enable()


def test_a_run_of_its_own_says_so():
    before = Garbage.freed
    Garbage()
    assert filters.collect_now() is True and Garbage.freed == before + 1


def test_drops_close_together_are_one_run(monkeypatch):
    runs = []
    monkeypatch.setattr(filters, "AFTER", 0.1)
    monkeypatch.setattr(filters, "collect_now", lambda: runs.append(time.monotonic()) or True)
    for _ in range(5):
        filters.dropped()
    time.sleep(0.4)
    assert len(runs) == 1
    filters.dropped()                                        # after the run: the next one's
    time.sleep(0.3)
    assert len(runs) == 2
