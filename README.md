# deephack

Custom content for the LCD on the **DeepCool MYSTIQUE** liquid cooler: the album art of whatever you are
listening to, the weather, and whatever comes next.

![deephack window](docs/screenshot.png)

The official DeepCool app can show sensor readouts and images you upload by hand. deephack talks to the
cooler directly over USB and keeps one image slot up to date with content it renders itself.

## Modes

| Mode | What it shows |
| --- | --- |
| **Auto** | Whatever has something to show right now, by a priority order you set: the game you are playing, the music that is on, Claude Pet while Claude Code works, your NBA team around its games, a countdown on its last day. Otherwise a fallback mode such as Weather. On DeepCool's own firmware a mode keeps the screen for two minutes after it goes quiet, so a paused song does not flip the display (every flip is a flash write). With the [direct drawing firmware](#protocol) a switch costs nothing: a mode has the screen the moment it has something to show, gives it up five seconds after it went quiet, and one picture fades into the next. |
| **Now Playing** | Cover, title and artist of the current track. Uses Windows' system media controls, so it works with Spotify, anything playing in a browser, foobar2000 and so on. With the [direct drawing firmware](#protocol) on the cooler it also shows how far into the track the player is, every second, and a new track fades in the moment the player announces it. **Music video** (a setting, off unless you switch it on): the track's own video from YouTube plays where the cover is, or over the whole screen, without its sound and in step with the music, also after a pause or a jump in the track. Only a video on the artist's own channel is taken. deephack listens to what the PC plays (the sound output's own copy, as the Visualizer uses; no microphone) and finds where in the video the song is: a video of the track's length plays at once and is put right by the half second or two it is off, a longer one (a scene before the song, a pause in it, credits after it) appears once its place is known, some sixteen to eighteen seconds into the track, and one whose song is another recording does not appear. Of fifty well-known tracks, sixteen had a video of their own length; in a trial with uploads of the tracks standing in for the player, 29 of 37 were followed through half the track or more. The others keep their cover. The artist and title go to YouTube's search for it, once per track. |
| **Weather** | Current conditions and a three day outlook for a city you pick, from [Open-Meteo](https://open-meteo.com) (no account or key). |
| **Calendar** | The next event with a countdown, and the four after it, from one or more .ics calendar links (Google Calendar's "secret address in iCal format", Outlook.com's published ICS link, iCloud) or an exported .ics file. Recurring events and time zones included. On DeepCool's own firmware the countdown moves in coarse steps (days, hours, half hours, ten minutes), about ten writes per event. With the [direct drawing firmware](#protocol) it goes by the minute and by the second in the last one, an event that is going on has a bar for how far it has run and says how long it has left, and when it ends the next one slides up. In Auto it takes the screen from 15 minutes before an event until it ends. |
| **NBA** | The last two results and the next two games, with team logos, for one team or the whole league. From ESPN's public feed; tip-off times in your local time zone. While your team plays, a big scoreboard with points per quarter takes over, updated every few minutes. With the [direct drawing firmware](#protocol) it can play **the game's highlights** once it is over (a setting, off unless you switch it on): the ten minutes of the whole game from YouTube, between the final score and the points per quarter, with sound if you want it, and then the scores again. They are looked for every ten minutes (they are up half an hour to an hour after the final) and only a video that names both teams and the day is taken, so no other game's are played; in a week of 43 games 39 were found. A button and a key of your choice play the last game's again, or end them. |
| **Claude Code** | Plan limits (5-hour and weekly) and today's tokens, requests, hourly activity and model split. All from local files, see below. With the [direct drawing firmware](#protocol) the page is live: the counts count up as requests are logged, a flame and a number show how many tokens a minute are burning (with the last half hour as a small graph), each session that is working has its line with how long it has been at it, and one that waits for you says so in amber. |
| **Claude Pet** | An animated pixel pet with your plan limit percentages. It works along while Claude Code is busy, dances while music plays, sleeps at night and celebrates or sulks after your NBA team's games; you pick which of these count and which wins. Otherwise its mood follows the fullest limit: happy, fine, stressed, exhausted. With the [direct drawing firmware](#protocol) on the cooler it is drawn anew whenever it moves, and nothing is stored: it dances to the music itself (a step and a hop for every beat, and the background and the cooler's light pulse with the bass) under the song's title and artist and in front of the album's cover (in large pixels, darkened, the bass's flashes over it; a setting gives the pet its own colours back), starts and stops within a second or two, blinks and waves now and then, yawns before it sleeps, and the percentages follow the usage snapshot within seconds. |
| **Scene** | A little pixel-art city under your real sky: dawn, day, dusk and night follow the sunrise and sunset, and clouds, fog, rain, snow or a thunderstorm follow the current weather in the Weather page's city. Windows light up in the evening, street lamps glow, cars drive by. A few real cities are drawn by their landmarks: **Chișinău** (the Triumphal Arch, the cathedral and its bell tower, Romanița, the City Gates), **Paris** (the Eiffel Tower over its zinc roofs, Sacré-Cœur), **London** (Big Ben and Parliament, the Eye, the Shard, the Gherkin), **New York** (the Empire State and Chrysler buildings, One World Trade Center) and **Tokyo** (Tokyo Tower, the Skytree, Mount Fuji behind them). When the Weather page's city is one of them the scene is that city by itself; any other place gets a city of its own, and the "City" setting picks one whatever the weather is from. The landmarks are pale by day and floodlit at night. With the [direct drawing firmware](#protocol) on the cooler it is the city as it is right now, drawn anew and never stored: the sky's colours, the sun and the moon move all the time, windows come on one by one through dusk and go out as the night goes on, clouds drift, lightning strikes at odd moments, rain and snow fall without repeating, and cars, taxis, vans and buses pass at odd times, more of them at rush hour, gliding by a pixel of the screen at a time. On DeepCool's own firmware it is an 8-frame animation, rewritten only when the time of day or the kind of weather changes. Also a fallback for Auto. |
| **Visualizer** | Whatever the PC is playing, as a picture. With the [direct drawing firmware](#protocol) on the cooler it is a spectrum: a bar for each of 24 pitches, bass on the left, treble on the right, with a mark where each last peaked, drawn anew some forty times a second (twenty-six with a patch before version 12), and nothing is stored. Or an orb that pulses with the bass, which is also what DeepCool's own firmware gets: there it is a flipbook, up to seven frames from silence to full blast stored once, the mode saying which one to show, which wears nothing but trails the music by a quarter of a second. The sound is read from the PC's output (nothing is recorded or sent anywhere). |
| **Video** | A YouTube link (most other video sites work too) or a video file on the PC, playing on the cooler. Needs the [direct drawing firmware](#protocol): the video is read as it plays, nothing is downloaded first and nothing is stored, and the cooler shows every picture of a video of 25 a second and some 27 of one of 30, in time with the clock (a video that is all movement is shown a little less sharp, not in fewer pictures). It fills the screen with the middle of a wide picture, or shows the whole picture with bars. It starts again at its end, and stops reading while another mode has the screen. **Sound** is off until you switch it on (the mode's page, Sound): it then comes from the PC's speakers in time with the picture, as loud as you set it there, which is deephack's own volume in Windows and leaves the rest of the PC alone. **Pause**, **ten seconds back** and **ten seconds forward** are buttons on the page, as is **Mute**; each can have a key that works whatever window is in front, if you give it one there (a jump takes a second or two for a link: the video is opened anew at the other place). Only the mode that is on the cooler sounds. On DeepCool's own firmware it is one picture of the video, without sound. YouTube changes how its videos are handed out now and then, and links stop working. yt-dlp, which finds the stream behind a link, follows within days: **Settings, YouTube links, Update now** fetches the newest from PyPI and uses it instead of the one deephack came with (the switch next to it does that by itself, once a day and when a link will not open; it is off unless you turn it on, since it is code from the net that deephack then runs). A newer deephack brings a newer yt-dlp too. |
| **TikTok** | Random popular videos from TikTok, one after the other, without an account: they are the ones TikTok's Explore page shows somebody who is not logged in, for everything or for one of its topics (comedy, animals, sports, food ...). **Next** and **Previous** are buttons on the mode's page and two keys that work whatever window is in front (Ctrl+Alt+PgDown and Ctrl+Alt+PgUp unless you set others; the page says so when Windows will not hand a key over). A video filmed upright fills the screen with its top and bottom cut off, or is shown whole with bars. Sound, Pause and Mute as in Video: off until switched on, and Next or Previous cuts it at once. Needs the [direct drawing firmware](#protocol), like Video. This talks to TikTok the way its own web page does, which is written down nowhere: it can stop working any day. |
| **Mirror** | A window, or a part of the PC's screen, on the cooler as it is right now: a chat, a game's map, a film that plays in the browser. **A part of the screen** is dragged out on it (the mode's page, "Choose a part of the screen…"; Shift keeps the cooler's shape) and shown as it looks, whatever is there. **A window** is picked from the list of open ones; it is followed when it moves, shown while other windows cover it, and found again when its program is started anew. Not while it is minimised: Windows does not draw a minimised window, and the cooler says so. The picture fills the screen with its middle or is shown whole with bars, and can lie on its side, which suits a wide window on the upright screen. Nineteen to twenty-six pictures a second, the more the calmer the picture is, a tenth of a second behind the PC's screen; a window in which nothing moves is sent once. Video that is protected against copying (Netflix and the like) comes out black, as in any screenshot, and so does a part of the screen while the PC is locked. Needs the [direct drawing firmware](#protocol), like Video. |
| **Countdown** | Days until a date you set, with a title. On the last day it counts hours, then minutes. With the [direct drawing firmware](#protocol) on the cooler it ticks: days over a clock of hours, minutes and seconds, a new picture every second, on the last day the clock alone, large, and confetti for ten minutes when it reaches zero. **Look: Christmas** puts it in a winter night, with a string of lights along the top and firs in the snow, one of them lit: with the direct drawing firmware the lights glow and fade and snow falls, ten pictures a second. With no date set that look counts to the next 25 December, and on the day it says "Merry Christmas" until midnight. |
| **Photo Frame** | Pictures from a folder you pick, changing every 15 minutes to once a day, shuffled or by file name. Portrait photos fill the screen, wider ones are shown whole. With the direct drawing firmware one photo fades into the next, they can change as often as every 15 seconds, and a photo that is wider or taller than the screen can fill it and move slowly across while it is up. **Next** and **Previous** are buttons on the mode's page and two keys (Ctrl+Alt+PgDown and Ctrl+Alt+PgUp unless you set others): Previous goes back through the photos that were up. |
| **Game Cover** | The cover art of the game you are playing, for games started through Steam (Steam notes the running game in the registry; covers come from its image server). With the [direct drawing firmware](#protocol) a strip along the bottom of the cover shows the CPU's and the GPU's temperature and load while the game runs, new every second: the cooler is the one screen still in view during a full-screen game. The readings are the System mode's, and only the strip is sent, 5 KB a second. When the game ends the cover is left alone; a setting leaves it alone all the time. |
| **Ticker** | Up to five stocks, indices, currency pairs or coins with price, change and a sparkline for today, five days or a month. From Yahoo Finance's public chart feed (no account or key). **Next** (a button, and Ctrl+Alt+PgDown unless you set another key) shows one of them at a time, large and with its chart, and after the last one the list again. |
| **System** | CPU and GPU temperature, load and power, memory, and pump and fan speeds, with graphs of the last half hour to three hours. Readings are taken every 10 seconds; the screen is redrawn every few minutes, since each redraw is a flash write. With the [direct drawing firmware](#protocol) the page is live instead: a reading and a redraw every second, a clock with seconds, and graphs that can show the last minute or the last five. Temperatures and fans come from DeepCool's own sensor service (see [Protocol](#protocol)); without it only CPU load and memory are shown. |
| **Live** | The cooler's own built-in screens (a big CPU temperature, frequency, fan and pump speed, a clock, or a 7 minute graph of frequency and temperature) fed with real readings every second. The cooler draws these itself and stores nothing, so on DeepCool's own firmware this is the one mode that updates every second without wearing the flash. A good fallback for Auto. |
| **GitHub** | Your contribution heatmap for the last four months, then the CI status and open pull requests of a repository you pick (or your own open pull requests anywhere). One GraphQL request per refresh, redrawn only when something changed. The token is borrowed from the [GitHub CLI](https://cli.github.com) (`gh auth login` once); deephack stores none. In Auto it can take the screen while the repository's build runs or fails. |

Clicking a mode opens its page with a live preview and leaves the cooler alone; **Show on cooler** (or a
double-click on the mode) puts it on the display. A green dot marks the mode that is on it. A mode's page
has that mode's own settings and nothing else.

**Settings**, under the list of modes, is the page for what belongs to no mode: starting with Windows and
closing to the tray, the cooler's light and its screen's brightness, a newer yt-dlp for YouTube links,
the cooler's firmware, and which deephack this is. The **Draw on the cooler** switch below it is there on every page: off, the cooler
shows your own stored image again.

**Keys** (in Settings) are three keys that work whatever window is in front and whatever mode is on the
cooler: the next mode, the previous mode, and drawing on the cooler off and on. None is set until you set
it. A mode's own keys (the next photo, pause) are on that mode's page and work while it is on the cooler,
which is why Ctrl+Alt+PgDown can be Next in each of them. When two settings ask for the same key, the
page says which of them has it; the keys in Settings come first.

**Cooler light** (in Settings) picks what drives the light strip on the side of the pump head: the colours at the edges
of the picture on screen (ambilight style, see below), the motherboard's ARGB effects
(needs the cooler's ARGB cable on a motherboard header) or the cooler's fixed warning colour.

The strip is 14 lights, seven along each long side of the screen. DeepCool's firmware gives each the colour of
one pixel near the edge and switches from one colour to the next. With the [direct drawing firmware](#protocol)
(16 or newer) deephack picks the colours for the pictures it draws: each light gets a share of a strip a quarter
of the picture wide, a coloured shape counts for more than the dark page or the white text around it, dark
pictures still glow, and the cooler fades from one colour to the next. **Light brightness** dims it.
The window shows the lights beside its preview of the screen, as the cooler has them for that picture:
deephack's colours and their fade, or the cooler's own one pixel a light on a firmware that picks itself.

Some modes say what the lights show themselves (with that firmware; everywhere else the lights are as
above): the **Visualizer** makes them two level meters in its colours, the left side for the low notes and
the right side for the high ones; the **Claude Code** page a fire up both sides while a session works,
higher the more tokens a minute burn, and amber that breathes while a session waits for you; **NBA**, while
your team's game is on, each side in the colour of the team whose score stands there, the one behind dimmer;
**Game Cover**, while a game runs, two temperature meters, the CPU's up the left side and the GPU's up the
right: one light at 30 °C and all seven when it is hot, blue through green and yellow to red on the way, and
a side that pulses red from there (a setting gives the lights back to the cover's colours). In **Auto** the
lights are those of the mode that has the screen.

**Keep on screen** (in Settings) decides whether the cooler stays on deephack's image or cycles through every image
stored on it (the cooler's own slideshow).

## Install and run

Windows 10/11.

**The app, ready to run:** download `deephack-<version>-windows-x64.zip` from the
[latest release](https://github.com/a7ex-turcan/deephack/releases/latest), unpack it anywhere and start
`deephack.exe`. It needs no Python. It is not signed, so Windows may ask before it runs it the first time
("More info", then "Run anyway").

**From source,** with Python 3.11+:

```powershell
git clone https://github.com/a7ex-turcan/deephack
cd deephack
python -m venv .venv
.\.venv\Scripts\pip install -e .
.\.venv\Scripts\deephack.exe
```

The window closes to the system tray; quit from the tray menu. "Start with Windows" in Settings adds a per-user
autostart entry.

**Updates.** deephack asks GitHub once a day whether there is a newer release (one request to its public
list of releases, no account; "Look for new versions" in Settings switches that off) and says so in
Settings, with what is new in it, and once in the tray. Nothing is fetched until you press **Install**
there. The app that was unpacked from the zip then fetches the new one, checks it against the release's
`SHA256SUMS.txt`, and has it take the old one's place: the folder stays where it is, so autostart and
shortcuts still lead to it, and your settings are not touched. A new version that does not start leaves
the old one running, and says why. The check guards against a broken download, not against a bad
release: the app is not signed, so what you trust is this GitHub account, as with a download by hand.
A deephack that runs from source is told of a new release and updated the way it was installed
(`git pull`). The cooler's firmware is never touched by an update of the app: when a new deephack
carries a newer patch than the cooler has, the tray says so once and Settings offers it, as before.
How it is done is at the head of [`deephack/update.py`](deephack/update.py).

### Things to know

- **Quit the DeepCool app first.** It holds the cooler's USB interface exclusively. deephack shows a banner
  with a button for that. The DeepCool app starts with Windows by default, so disable its autostart if you
  want deephack to own the display after a reboot. Fan control is a separate Windows service and keeps
  working, and so does the sensor service the System and Live modes read.
- **On DeepCool's own firmware every update is a write to the cooler's flash**, except in Live, which
  uses the cooler's own sensor screens, and in Visualizer, which flips between pictures stored once: that
  firmware has no way to show a picture without storing it first. With the direct drawing firmware (see
  [Protocol](#protocol)) deephack draws its pictures straight from USB instead, and Claude Pet
  and Scene, which are stored animations otherwise, are drawn anew whenever something in them moves:
  nothing is stored but one plain black picture, once, for the frames to go over.
  The "Firmware" section of the Settings page says which firmware the cooler runs and can install
  that one, or DeepCool's own again (Video and TikTok, which need it, say so on their pages and lead there). **Read what it says first: a firmware update that goes wrong can
  leave the cooler's screen dead for good.**
  A slide show of the stored pictures is the exception: with that switched on, ours is stored as before.
  Where it does store, deephack rate-limits
  writes (at most one every 8 seconds, tracks have to settle before they are drawn), but the flash
  endurance of the device is unknown. "Cover only" writes once per album instead
  of once per track. Showing an image the cooler already holds again (Auto switching back to it) costs
  no write.
- **deephack adds files the DeepCool app does not know about:** one image (a black one on the direct
  drawing firmware), one animation once you use
  Claude Pet or Scene on DeepCool's own firmware, and up to seven more images once you use Visualizer there
  (the cooler keeps about nine in all, so it takes whatever room your own pictures leave). They are stored after the JPGs / GIFs you uploaded with the official app. If you later add
  files there, its numbering will be off by one. `python -m deephack.device delete <index>` (add `--gif`
  for the animation) removes them; the indexes are `slot_index` and `gif_slot_index` in
  `%APPDATA%\deephack\config.json`.
- Only the MYSTIQUE (USB `3633:0009`, 480x640 portrait) is supported. The MYSTIQUE PLUS appears to share
  much of the protocol but is untested.

### Claude Code mode

Nothing leaves your machine and no credentials are read.

- **Today's numbers** are summed from Claude Code's session logs in `~/.claude/projects`.
- **What burns** (the live page) is every token of the requests logged in the last sixty seconds, read from
  the cache or not, in all sessions together; the output tokens among them are named next to it. A request is
  logged when its answer is complete, so the number moves in steps and is counted up to.
- **Which sessions work or wait** (the live page) comes from the small file Claude Code keeps for each
  running session in `~/.claude/sessions`: its name, and whether it is busy, idle or waiting for you. Claude
  Code describes that file nowhere; it was seen with 2.1.330. Without it, a session whose log was written in
  the last half minute counts as working. The names show on the cooler and nowhere else.
- **Plan limits** are handed out by Claude Code in one place only: the input of its status line command
  (`rate_limits`, in its [status line's documentation](https://code.claude.com/docs/en/statusline)). So the
  status line saves that input where deephack reads it, `%APPDATA%\deephack\claude-usage.json`. One line
  in `~/.claude/settings.json` does it, with no plugin and no other program:

  ```json
  { "statusLine": { "type": "command",
      "command": "IFS= read -r -d '' j; printf '%s' \"$j\" > \"$APPDATA/deephack/claude-usage.json\"" } }
  ```

  If you have a status line already, it goes behind that, fed the same input (`your-command` is what
  your setting says now):

  ```json
  { "statusLine": { "type": "command",
      "command": "IFS= read -r -d '' j; printf '%s' \"$j\" > \"$APPDATA/deephack/claude-usage.json\"; your-command <<< \"$j\"" } }
  ```

  Claude Code runs the command in Git Bash on Windows, and the line uses nothing but bash itself: it
  starts no program, where a `tee` in its place took 200 ms of every run here. The file then holds the
  whole of what the status line was told by the session that wrote last, its folder and model among it,
  and stays on this PC. A snapshot written by the [claude-hud](https://github.com/jarrodwatts/claude-hud)
  plugin (`display.externalUsageWritePath` in its `config.json`, set to that file) is read as well.

  The file only changes while a Claude Code session is open. Only the windows your plan has are drawn
  (some plans have no 5-hour window); without the file the limits card is left out.

## Adding a mode

A mode is a class that returns a 480x640 Pillow image whenever the display should change:

```python
# deephack/modes/hello.py
from .. import render
from .base import Mode

class Hello(Mode):
    id, title, description, glyph = "hello", "Hello", "Says hello", ""

    async def frame(self):
        if getattr(self, "_done", False):
            return None            # nothing changed, no flash write
        self._done = True
        return render.message("Hello", "from the cooler")
```

Add it to `MODES` in `deephack/modes/__init__.py`. Declare `settings` on the class and the UI builds the
form for you (see `weather.py`). `python -m deephack --no-device` runs the UI without touching the cooler.
The tests run the real driver against a model of the cooler (`tests/cooler.py`) that knows the protocol's
rules (complete uploads with matching checksums, 480x640 JPEGs, existing slots, image mode before showing
a stored image, never the erase commands) and fails any test that breaks one. To run them:
`pip install -e .[dev]`, then `python -m pytest`. GitHub runs them on every pull request and on every
push to `main` (`.github/workflows/tests.yml`). The tests that run DeepCool's firmware in the emulator
are skipped where its image is not installed, which is everywhere but a PC with DeepCool's app.

To let Auto pick the mode, set `claims` to a few words saying when it has something to show
(`claims = "music playing"`), keep `self.active` up to date in `frame()`, and add the class to
`CANDIDATES` in `auto.py`.

A mode that is of little use without the direct drawing firmware sets `needs_direct = True`: on a cooler
with DeepCool's own firmware its page then says so and leads to the firmware in Settings.

## Releasing

Releases are built by GitHub (`.github/workflows/release.yml`): the tests run, then the standalone app is
built with PyInstaller (`packaging/deephack.spec`), started once to see that it comes up, and published
with the wheel, the source archive and their checksums. To make one, set `__version__` in
`deephack/__init__.py` (the only place the version is written), write what changed under a heading for
that version in [`CHANGELOG.md`](CHANGELOG.md) (what has gathered under "Unreleased" there gets that
heading), commit, and push a tag of that version:

```powershell
git tag v0.2.0
git push origin v0.2.0
```

The release's notes are the version's section of the changelog (`packaging/release_notes.py`). A
version without one, or a tag that does not match the version, fails the run before anything is built. "Run workflow" on the
repository's Actions page is a trial run: the same tests and builds, kept with the run, nothing published.
To build the app on your own PC: `pip install -e .[package]`, then
`pyinstaller --noconfirm packaging/deephack.spec` makes `dist\deephack\`.

An installed deephack finds a release by its tag, its zip by the name's end (`-windows-x64.zip`, one
folder with `deephack.exe` in it) and its checksum in `SHA256SUMS.txt`, and an older one starts a
newer one with `--apply-update` (see `deephack/update.py`): a release that changes any of these is
one the app cannot update itself to.

## Protocol

Reverse engineered from the official app (v1.2.15, Electron) by attaching to its debug port and logging
its USB transfers; the tooling is in [`tools/`](tools). How it was done, from the first logged transfer to
the patched firmware, is told in short in [docs/reversing.md](docs/reversing.md). Tested against one device. It came with firmware
2.71 (USB `bcdDevice` `0x0247`: the low byte is the minor version as a number, 0x47 = 71) and has since
been downgraded to 2.70, the only version DeepCool gives out; the protocol is the same on both.

The cooler is a full-speed vendor-class device with two bulk endpoint pairs (`0x01/0x81` for commands and
uploads, `0x02/0x82` for the periodic sensor feed).

**Command frame**, 48 bytes, answered with the same layout starting with `55`:

```
AA 2E <cmd> <payload, zero padded to 39 bytes> 'H' 'I' 'D' 'C' <sum16 LE of bytes 0..45>
```

| cmd | meaning | payload |
| --- | --- | --- |
| `01` | sensor values (ep 2, once a second) | 3-byte fields, see below |
| `02` | device options | five bytes, the official app sends `01 01 00 01 46`. The fourth picks the side light's source: `0` the motherboard's ARGB signal, `1` a fixed warning colour (the app switches to it at 90 °C), `2` the colours at the edges of the picture shown: one pixel a light, picked by the firmware ten times a second (it follows frames drawn with command `20` as well; with the patched firmware's command `24` the host says the colours and the cooler fades to them, see [docs/firmware-analysis.md](docs/firmware-analysis.md)). The fifth is the backlight brightness in percent (0 turns the screen off). The first three showed no visible effect (the app's names: noLoadScreen, gyroStatus, screenRotate) |
| `03` | display mode | `mode` (1 = sensor dashboard, 2 = stored images, 3 = recorder) |
| `05` | recorder layout | `0` frequency + temperature graphs, `1` frequency graph only |
| `07` | slideshow | `duration` `animation` (0 none, 1 slide, 2 fade) |
| `08` | show stored image | `type` (0 jpg, 1 gif) `index` |
| `09` | delete stored image | `type` `index` |
| `0A` | set clock (ep 2) | `year:u16` `month` `day` `hour` `minute` `second` |
| `0F` | start upload | none |
| `12` | get UUID | reply: status byte + 32 ASCII characters |
| `13` | **factory reset** | none. Reboots and erases every stored image. `12` returns junk until the next power cycle |
| `14` | **delete all stored images** | none |

Commands `0B`, `0C`, `0D`, `0E` and `11` are acknowledged but did nothing visible with an empty payload.
`18` to `30` are answered with command byte `00`, which looks like "unknown command". `13` and `14` were
found the hard way; `tools/restore_originals.py` re-uploads what the official app had stored.

**Recorder mode** (`03` = 3) plots the last seven minutes of the CPU frequency and temperature you feed
with command `01`, as live line graphs. Like the dashboard it is not stored, so it costs no flash writes.
Command `05` picks the graphs: `00` frequency and temperature, `01` frequency only.

**Sensor values** (command `01`) feed the firmware's own dashboard and are not stored, so they can change
every second without wearing the flash. The payload is a row of 3-byte fields, `integer:u16` `fraction:u8`;
the fraction byte is printed as-is after the decimal point.

| offset | field | status |
| --- | --- | --- |
| 0 | CPU temperature | confirmed on the device |
| 3 | CPU load % | confirmed on the device |
| 6 | RAM usage % | confirmed on the device |
| 9, 12, 15 | 3.3 V, 5 V, 12 V rails | confirmed on the device |
| 18 | CPU frequency (GHz) | confirmed on the device |
| 21 | CPU fan RPM | confirmed on the device (the official app left it at zero) |
| 24 | pump RPM | confirmed on the device (the official app left it at zero) |
| 27 and up | unknown | not shown on any layout seen so far |

Command `04` picks the dashboard layout with four bytes: `main` (0 frequency, 1 time, 2 pump, 3 CPU fan,
4 CPU fan + pump, 5 temperature), `style` (frequency only: 0 plain, 1 a ring around the number, 2 a gauge
whose arc fills with the value, full at about 6 GHz), one byte with no visible effect, and `strip`
for the row at the bottom (0 voltage rails, 1 frequency / CPU load / RAM, 2 frequency / RAM). The labels
and units on every layout are fixed in the firmware; only the numbers are yours.

`python -m deephack.device probe-sensors` shows the dashboard with test values, and `map-dashboards` steps
through layouts.

The Live mode drives both screens with real readings: `0A` sets the clock, `03` switches to the
dashboard (1) or recorder (3), `04` or `05` picks the layout, then `01` follows once a second. Before
showing a stored image again deephack switches back with `03 02` and re-sends the slideshow setting (`07`).
Confirmed on the device, switching both ways.

**Image upload**

1. command `0F`, wait for the reply
2. 64 byte header: `"DCLd"`, type (1), size `u32`, sum16 of the data as `u32`, 7 zero bytes, 32 character
   file id, 10 zero bytes, sum16 of the first 62 header bytes as `u16`
3. the JPEG in 64 byte packets: 480x640, baseline, 4:2:0
4. `"dcldfinish"` zero padded to 55 bytes; no reply, the device then writes to flash (wait about a second)
5. command `08` to show it

Uploading with an id that already exists replaces that image in place.

The cooler keeps **nine stills** (and nine animations). A tenth upload gets no error, but according to the
firmware it is written to storage without being added to the index, so it can never be shown (and stays
there as dead weight). `08` with an index that does not exist does nothing: the screen stays as it was.
Seen with the webcam and in the firmware ([docs/firmware-analysis.md](docs/firmware-analysis.md)).

**How fast the screen can change without a flash write** (measured with a webcam at 30 fps):

- `08` (show a stored still) is answered in 0.3 ms and the picture is on screen about 0.1 s later, all at
  once, whatever the JPEG's size (5 to 42 KB tried). Ten switches a second all show; from about twelve a
  second the firmware starts dropping them. `Flipbook` frames use this on DeepCool's firmware. It is
  still slow for music: the Visualizer ends up 0.2 to 0.3 s behind the beat that way, which looks
  wrong. Direct drawing (below) is what it is meant for.
- The sensor screens redraw about twice a second: values sent faster than that are skipped.

The image is only displayed once it is committed: after the data without `dcldfinish` the screen shows
"Loading…" until the marker arrives. There is no preview of uncommitted data, and experimenting with
unfinished uploads hung the firmware once (no endpoint accepted data until the PC was powered off).

**Animations** (what the official app calls GIFs) are a sequence of JPEG frames, stored separately from the
stills and shown with type 1. One `0F` command, then a header + JPEG for every frame, then one
`dcldfinish`. The frame headers use type 2 and fill three `u16` fields at offset 13: frame count, total
loop duration in milliseconds, and the frame's index.

A mode can see whether its pictures cost anything: the engine sets `direct` on it while they are drawn
straight from USB (the direct drawing firmware, below). Then a picture may come every tick, and a mode
may set its own `tick` for a moment to animate (see `now_playing.py`: the progress bar, and the fade to
a new track).

A mode returns an `Animation(frames, duration_ms)` instead of an image to use this (see `tamagotchi.py`).
Every frame is written to flash, so keep them few. (On the direct drawing firmware the engine plays the
animation itself instead, drawing each frame when it is due, and stores none.) For real-time changes a mode returns a
`Flipbook(key, frames, index)` and a short `tick`: only `index` decides which frame shows (see
`visualizer.py`). On the direct drawing firmware the engine draws that frame from USB and stores
nothing; otherwise it stores as many of the frames as fit, once, as stills, and shows those, ten a
second at most.

**Drawing without storing** is not something the stock firmware can do. `tools/fw/patch.py` builds a
firmware that can: one new command (`20`, size and sum16, then the JPEG) puts a frame on screen straight
from RAM, and the driver has `draw_version()` and `draw_jpeg()` for it. The app installs it from the
"Firmware" section of its Settings page (`deephack/firmware.py`: the patch as a table of 13 KB, 2 KB of code and the picture for the start screen, put on DeepCool's
v2.70 image, which is read from the installed DeepCool app and checked by its hash; deephack does not
carry DeepCool's firmware). It runs in the emulator
(`python tools/emu/bench.py --firmware ...`, and `tests/test_direct_draw.py`) and, since 19 Nov 2026,
**on one cooler**: `tools/fw/flash.py patched` sent it through the cooler's update channel, the cooler
was off the bus for 12 seconds and came back drawing. Measured there with the patch's first versions
(what the later ones changed is under "How fast" below), from the host
(`tools/drawbench.py`): the cooler takes a frame's bytes at 820 KB a second, which is USB at full speed,
and is ready for the next some 6 ms after the last byte: a 26 KB frame 27 times a second, a 40 KB one
16 to 19 times, a 90 KB one 9 times. (The first numbers here, 16 a second at 41 KB and 20 at 8 KB, were
the app's own pace, not the cooler's: see "How many pictures a second" in docs/firmware-analysis.md.) The engine uses it for every picture a
mode returns (one frame of 27 to 68 KB, on screen 36 to 88 ms after it was ready; nothing is stored and
there is no wait between two; the System page is redrawn every second that way, 39 to 44 KB a frame,
for 2 % of one CPU core), for Scene (a frame of 17 to 25 KB: up to thirty a second while a car passes, twenty
while rain or snow falls, a few otherwise; 2.6 % of one CPU core over a clear day, 3.5 % in rain), for
Claude Pet (a frame of 15 to 19 KB whenever it moves: four a second for 2 % of one CPU core,
twenty-six a second while it dances for 8 %) and for the Visualizer, which gets twenty-six a second (the spectrum 20 to 37 KB each, drawn and encoded in a millisecond; 9 % of one CPU core, half of it the USB traffic).
A picture over the firmware's 128 KiB is sent at a lower JPEG quality. Drawn pictures carry Huffman
tables made for them, which the cooler's decoder turns into the same pixels as the standard ones (read
back from its frame buffer and compared): an empty screen is 2 KB that way and not 5, a page with flat
areas a quarter to a half smaller, a busy one a twentieth.

**A part of the picture** (version 3 of the patch): when only one rectangle of a picture changes, a video
on a page that stands still, the page is sent once and after that only the rectangle, a JPEG of its
own that the cooler puts in its place. The NBA mode's highlights are 21 KB a frame that way where the
whole page was 29, and sharper for it. Up to version 11 the cooler showed a picture every 36 ms and no
faster, however small it was, and what a part bought was reaching those 27 a second; since version 12
it is every turn of the panel, and a part is what keeps a page with a video in it at the video's 30. A
cooler with an older version of the patch gets whole pictures; Settings says when a newer one can be put on.

**How fast** (version 9 of the patch): a frame's bytes arrive at 997 KB a second, which is all USB at
full speed carries; earlier versions took 540 to 820. A frame of up to 33 KB is on the glass at the
panel's next turn, so a video keeps its 27 pictures a second at a higher JPEG quality than before (up
to 80, where it stopped at 65 and fell to 45 for a busy picture). **From version 12 on those 27 are no
longer the ceiling:** the cooler made a copy of every frame and redrew when its timer came round, two
turns of the panel a picture; without the copy and with a redraw at once, a picture is on the glass at
the panel's next turn, 55 a second. A video of 30 pictures a second is shown 30 times a second, the
Visualizer runs at 41, Scene at 28 to 43. In ten hours of that in one go (26 Nov 2026: video, TikTok,
Scene) the cooler took 778,000 pictures and 400,000 commands for its lights and refused none.

**Its own start screen** (version 6 of the patch): while the PC starts, the cooler shows deephack's logo
where DeepCool's was, from the first moment until deephack takes the screen over. DeepCool's logo is a
picture in a file on the cooler that nothing reaches over USB; the patch carries its own (11 KB, in the
flash that is free behind the firmware) and puts it on top before anything is drawn. The patch can also
be asked for the cooler's memory, which is how its bootloader was read: see `docs/firmware-analysis.md`.

Two things the engine works around, both seen on the cooler:

- To get a stored picture back after drawing, `08` (show) is not enough for the slot that is already
  selected: the drawn frame stays. Showing a different slot works, and so does leaving the image screen
  (mode `1`, 0.15 s, mode `2`), which is what the engine does.
- Frames are drawn over a stored **still**. Over an animation the next animation frame takes the screen
  back. And with the first version of the patch, once a fast animation had been on the image screen the
  firmware took one frame and answered "later" to every one after it, also when a still was shown
  again: the still keeps the animation's frame time as its timer, the firmware's task loop never comes
  round, and the patch was only called from there. Version 2 of the patch is also called from inside
  that loop, and takes its frames after the same animation on the cooler. Leaving the image screen and coming back clears it on either, so the engine still does
  that every time before it starts to draw.

The patch has a version, which the cooler reports in its answer to `20` (`draw_version()`; the first
patch reports none and counts as 1). The app offers an update when it carries a newer one. Later versions
added: a part of the picture drawn by itself (3), `21` to read the cooler's memory (4), deephack's own
start screen (5 and 6), bytes at USB's full speed (9), `22` to write a word of memory (10), a new picture
at every refresh of the panel, 55 a second (11 to 13), and `23`, with which the patch gives its frame
buffers back to the firmware's heap before an upload (15: without that an upload, a firmware update
among them, could be dropped by the cooler without a word. `make_room()`, which the driver calls by
itself), and `24`, with which the host says what the 14 lights on the pump head show and how quickly
they fade there (16: `set_light()`; DeepCool's firmware gives each light the colour of one pixel at the
picture's edge, ten times a second, with nothing in between).

A firmware update is sent only to a cooler that has room for it: after announcing the upload the
sender walks the cooler's heap with `21` and looks for the 2 MiB the firmware will ask for
(`firmware.upload_room`). A cooler on a patch before 15 that has none is sent nothing; the app
remembers the update and sends it by itself when it next starts on a cooler that has just been
switched on, before it draws anything.

**A flash that goes wrong cannot be undone from USB.** That it worked on one cooler (four times: both
images twice, the last two from the app, 19 seconds each) says nothing certain about another unit: read "Which firmware" and "Direct drawing" in
[docs/firmware-analysis.md](docs/firmware-analysis.md) first. A cooler that reports 2.71 would be
downgraded by it, and there is no 2.71 image to go back to. What can be tested without a cooler is: the
sender against the stock firmware in the emulator (the image arrives byte for byte and the firmware
restarts; an image that arrives damaged or short is not stored, and "dcldfinish" calls such an upload
off), and the app's part against a model of the cooler. What cannot be is the bootloader, which does
the flashing: it is not in the update file.

`python -m deephack.device --help` exposes the driver on the command line.

**DeepCool's sensor service.** The DeepCool app installs a Windows service, "JZFS Sensor Bridge Service",
that reads the hardware through HWiNFO and answers on the named pipe `\\.\pipe\jzfs_sensor_bridge_v2`,
also to programs without admin rights, and keeps running when the app is closed. Requests are JSON in a
small binary frame (`"DCS2"`, kind, length, sequence, CRC-32); `HELLO` and then `GET_SENSOR_SNAPSHOT`
return the readings by name (`"CPU Temperature"`, `"Gpu usage"`, `"Fan list"`, ...). The System and Live
modes read it. [docs/deepcool-services.md](docs/deepcool-services.md) has the frame layout, every field,
the fan control and display services next to it, and how all this was found.

## Licence

[MIT](LICENSE): use it, change it, pass it on, keep the notice. The standalone app also carries other
people's work under their own licences (Qt, FFmpeg, yt-dlp and more): [THIRD-PARTY.md](THIRD-PARTY.md)
lists them, and both files are in the zip next to `deephack.exe`.

## Disclaimer

Not affiliated with or endorsed by DeepCool. This talks to your hardware in ways the vendor did not
document; use it at your own risk.
