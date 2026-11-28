"""Persistent settings, stored as JSON in %APPDATA%\\deephack\\config.json."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from . import APP_NAME

# Fixed id of our image slot on the device; uploading to the same id overwrites in place.
SLOT_ID = "0de3b4c4" + "0" * 23 + "1"
GIF_SLOT_ID = "0de3b4c4" + "0" * 23 + "2"     # the one animation deephack stored until 0.19.2: see gif_id


def gif_id(frame_ms: int, attempt: int = 0) -> str:
    """File id of deephack's animation whose frames are on for that long each.

    An id that is on the cooler has its frames replaced and nothing else: the firmware writes how many
    frames there are and how long the loop is when it makes the animation's folder, and plays whatever is
    stored under that id later at the first one's pace. So there is an id for each pace, and what is stored
    again under it has that pace. (Issue #66; docs/firmware-analysis.md, "Upload and storage".)

    `attempt`: a first upload that breaks off leaves a folder which the firmware does not list, and into
    which the same id goes without being listed either, until the cooler was off and on (#67). So the next
    try has another id."""
    return "0de3b4c4" + "0" * 16 + f"a{attempt & 0xFFF:03x}{frame_ms & 0xFFFF:04x}"



def book_id(i: int) -> str:
    """File id of frame i of the flipbook (a set of stills a mode flips through, see modes.base.Flipbook)."""
    return "0de3b4c4" + "0" * 20 + f"b{i:03x}"


DEFAULTS = {
    "enabled": True,
    "mode": "now_playing",
    "slideshow": False,        # False: keep our image on screen. True: cooler cycles through all stored images.
    "close_to_tray": True,
    "ytdlp_current": False,    # True: look for a newer yt-dlp once a day and when a link will not open (ytdlp.py)
    "update_check": True,      # True: ask GitHub once a day whether there is a newer deephack (update.py). It is
                               # said, not installed: that is a button in Settings
    "light": "screen",         # the pump head's light strip: screen (edge colours) | motherboard | warning
    "light_level": 100,        # ... how bright, percent, when it follows the screen and deephack picks its colours
                               # (direct drawing firmware, patch 16; light.py)
    "brightness": 70,          # screen backlight, percent (70 is what the official app sends)
    "slot_index": None,        # index of our image among the JPGs stored on the device
    "ground": False,           # True: that image is the plain one frames are drawn over (direct drawing firmware)
    "gif_slot_index": None,    # index of the animation stored under GIF_SLOT_ID (until 0.19.2), if there is one:
                               # it stays where it is, and what is stored now goes after it
    "gif_slots": {},           # our animations on the device, by ms a frame: {"250": {"index": among the GIFs
                               # there, "attempt": of gif_id, "stored": True once one was stored whole}}
    "restore_index": 0,        # JPG shown when deephack is paused or quits
    "book": None,              # the flipbook stored on the device: {"key", "first" (index of frame 0), "count"}
    "firmware_wanted": None,   # "direct" | "stock": a firmware update the cooler had no room for, to be sent when it
                               # is found freshly started (engine.py, _send_wanted)
    "key_next_mode": "",       # keys that work in any window, whatever mode is on the cooler (hotkeys.py; as Qt
    "key_previous_mode": "",   # writes a key, "Ctrl+Alt+Right"; empty: none): the next and the previous mode ...
    "key_draw": "",            # ... and "enabled" off and on
    "modes": {},               # per-mode settings, keyed by mode id
}


def config_dir() -> Path:
    d = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


class Config:
    def __init__(self, path: Path | None = None):
        self.path = path or config_dir() / "config.json"
        self._lock = threading.Lock()
        self.data = json.loads(json.dumps(DEFAULTS))
        try:
            self.data.update(json.loads(self.path.read_text(encoding="utf8")))
        except (OSError, ValueError):
            pass

    def get(self, key: str):
        with self._lock:
            return self.data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value) -> None:
        with self._lock:
            self.data[key] = value
            self._save()

    def mode_settings(self, mode_id: str) -> dict:
        with self._lock:
            return dict(self.data["modes"].get(mode_id, {}))

    def set_mode_setting(self, mode_id: str, key: str, value) -> None:
        with self._lock:
            self.data["modes"].setdefault(mode_id, {})[key] = value
            self._save()

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf8")
        tmp.replace(self.path)
