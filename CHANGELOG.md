# Changelog

What changed in each release of deephack, newest first. The notes of a GitHub release are its section
here: the release workflow takes them from this file, and does not build a version that has no section.
What is on `main` and in no release yet is under "Unreleased", which gets the version's heading when
the release is cut.

"Patch" is the direct drawing patch for the cooler's firmware. The app carries it and installs it from
Settings; a newer one is offered there when the cooler has an older one.

## Unreleased

- **Scene and Claude Pet each at their own pace on DeepCool's firmware.** The cooler plays whatever is
  stored in an animation's place at the pace of the first one stored there, so whichever of the two came
  second ran at the other's: Scene a sixth too fast, or Claude Pet a fifth too slow. Each has a place of
  its own now. The animation an older deephack stored stays on the cooler; the README says how to
  remove it. A cooler with the direct drawing firmware stores no animations and is not touched by this.
- **An animation whose first upload broke off is stored at the next try.** The cooler did not take it
  again until it had been switched off and on. deephack now sends it in a way the cooler takes.

## 0.19.2 (2026-11-28)

- **An upload that breaks off no longer takes the next one with it.** When a picture or an animation
  stopped on its way to the cooler, the cooler went on waiting for the rest and took the next upload for
  it, which was lost. deephack now tells it that the upload is over. By MastahKillah.
- **Memory of video scalers is freed more surely.** The clean-up added in 0.18.0 could be skipped when
  Python happened to be tidying up at the same moment, and then waited for the next video of a new size.
  It is asked for again now until it has run.

## 0.19.1 (2026-11-27)

- **Sensor readings with DeepCool's app 1.2.16.** That version hands the readings out in another shape,
  and deephack found none in it: Live, System and Game Cover's temperatures were all nought. Both shapes
  are read now. Found and fixed by MastahKillah, the project's first contribution from outside.
- **Claude Code's plan limits without a plugin.** One line as Claude Code's status line saves what Claude
  Code tells it, and deephack reads the limits from that: the README has the line, also for in front of
  a status line you have. The claude-hud plugin's snapshot is still read.

## 0.19.0 (2026-11-27)

- **deephack updates itself.** It asks GitHub once a day whether there is a newer release and says so in
  Settings, with what is new, and once in the tray. **Install** there fetches it, checks it and puts it in
  this one's place, settings untouched. A version that does not start leaves the old one running.
- **Only when you say so.** Nothing is fetched before the button is pressed, and "Look for new versions"
  switches the daily look off. A deephack that runs from source is told, and updated as it was installed.
- **A newer firmware patch is said in the tray**, once, when the app carries one the cooler does not have.
  It was a dot on the Settings button only. Installing it is still a button in Settings, and yours to press.
- **Coming from 0.18.0 or older:** those cannot update themselves, so this version is one more download by
  hand: quit deephack and put the new folder in the old one's place. Your settings are kept. From here on
  the app does it.

## 0.18.0 (2026-11-27)

- **Game Cover: temperatures while you play.** With the direct drawing firmware a strip along the bottom of
  the cover shows the CPU's and the GPU's temperature and load, new every second, for as long as the game
  runs. A setting leaves the cover alone. On DeepCool's own firmware the mode is as it was.
- **Game Cover: the lights as two temperature meters** (firmware 16): the CPU's up the left side, the GPU's
  up the right, blue through green and yellow to red, and a side that pulses red when it is hot. Or the
  cover's colours, as before: a setting.
- **Auto** hands on the lights of the mode that has the screen. Until now the Claude Code page's fire and a
  game's team colours were only shown with that mode picked itself, not when Auto showed it.
- **TikTok and Now Playing no longer take more memory by the hour.** What scales a video of a new size, and
  what listens for the place in a music video, was dropped but not freed: 22 MB an hour with TikTok, a
  megabyte with every silence while a music video was looked for. It is freed within seconds now.

## 0.17.0 (2026-11-26)

- **The lights as a mode's own.** With the direct drawing firmware 16 a mode can say what the 14 lights on
  the pump head show, in place of the colours of its picture's edge. The window's preview shows them too.
- **Visualizer:** the lights are two level meters in the look's colours, the left side's for the low notes
  and the right side's for the high ones, as the spectrum has them.
- **Claude Code:** a fire up both sides while a session works, higher the more tokens a minute burn, each
  light flickering; and amber that breathes while a session waits for you.
- **NBA:** while your team's game is on, each side in the colour of the team whose score stands on it, and
  the side that is behind dimmer.

## 0.16.0 (2026-11-26)

- **Claude Code: a live page.** With the direct drawing firmware the numbers no longer wait for a refresh:
  today's tokens and requests are shown in full and count up as requests are logged, and the limit bars
  move when the limits do. On DeepCool's own firmware the mode is as it was.
- **What burns.** A flame and a number for the tokens a minute that the last sixty seconds took, all
  sessions together, with the output tokens among them and the last half hour as a small graph. The flame
  has five sizes, the largest from three million tokens a minute, and goes out when nothing is asked.
- **Who is at it.** A line for each session that is working, with its name and how long it has been busy,
  and one in amber for each that waits for you, with what it waits for. Claude Code's own record of its
  sessions says which they are, so a session that thinks for minutes without writing anything still counts.
- Measured on the cooler: eight pictures a second while a session works, 7 % of a processor core for the
  whole app. When no session works the page stands still.
- **The cooler's light, picked by deephack.** DeepCool's firmware gives each of the 14 lights on the pump
  head the colour of one pixel near the screen's edge, and jumps from one colour to the next. With the
  direct drawing firmware 16, each light gets a share of the whole edge of the picture and fades to it.
- **What a light sees.** A coloured shape counts for more than the dark page or the white text around
  it, and a dark picture still glows. A new setting, Light brightness, dims the light. Stored pictures
  and older firmware are as before.
- **Direct drawing firmware 16**, offered in Settings: a command for the lights' colours, and the fade,
  sixty steps a second, done on the cooler.
- **The lights in the window.** The preview of the screen has the glow of the 14 lights beside it, as the
  cooler shows them for that picture: with their fade where deephack picks the colours, and the cooler's
  own one pixel a light where it picks them itself. No cooler is needed to see it.

## 0.15.0 (2026-11-25)

- **Photo Frame: "Fill and move across".** A new choice under Fit. A photo that is wider or taller than
  the screen fills it and moves slowly from one side to the other while it is up, every other photo the
  other way. It needs the direct drawing firmware; without it the photo fills the screen and stands.
- How often the cooler gets a picture goes by how fast the photo moves: 27 a second for a photo that is
  up 15 seconds, 5 a second for one that is up 5 minutes, one every two or three seconds for an hour.
- **Photo Frame: Next and Previous.** Two buttons on the mode's page, and two keys that work whatever
  window is in front (Ctrl+Alt+PgDown and Ctrl+Alt+PgUp unless you set others). Previous goes back
  through the photos that were up, also after deephack was started again, and Next comes forward the
  same way before it picks new ones.
- **Photo Frame: a photo changes when its time is up.** The next photo is loaded a few seconds ahead.
  On the cooler the change began 350 to 480 ms after its time before, and begins within 6 ms of it now:
  a photo that moves across no longer stands at the end of its way.
- **Video: Pause, and ten seconds back or forward.** Buttons on the mode's page, and keys for them if
  you set some there. Pause holds picture and sound; a jump takes a second or two for a link, as the
  video is opened anew at the other place. TikTok gets Pause as well.
- **Ticker: Next.** A button, and a key (Ctrl+Alt+PgDown unless you set another): one symbol at a time,
  large and with its chart, and after the last one the list again.
- **Keys that belong to no mode.** Settings has a new section, Keys: one for the next mode, one for the
  previous mode, and one that switches drawing on the cooler off and on. None is set until you set it.
  They work whatever window is in front and whatever mode is on the cooler.
- When two settings ask for the same key, the page says which of them has it. The keys in Settings come
  before a mode's own.
- **Now Playing: music videos that are longer than the track.** Most are: a scene before the song, a
  pause in it, credits after it. Such a video plays now too, from where the song is: deephack finds
  that place by the video's sound. It appears once the place is known, some sixteen to eighteen seconds
  into the track; until then the cover shows, and the mode's line says that it is listening.
- Of fifty well-known tracks, 16 had a video that could be played before. In a trial of the 37 that
  have a video on the artist's channel, with an upload of the track standing in for the player, 29 were
  followed through half the track or more; where a second way of looking knew the place, this one had
  it right for 5,566 of 5,742 seconds.
- A video whose song is another recording (a live cut, another mix) is not shown: played against
  another track's video, 4,479 looks believed nothing.
- **Videos of the track's own length are put right too.** They turned out to be half a second to two
  seconds off, and two of them a third of a percent slower than their track. They still play at once,
  and move to their place when it has been heard.
- **What it listens to:** the PC's sound output, as the Visualizer does (Windows hands a program a copy
  of it; no microphone), while a track with a video plays and the Music video setting is on. It is
  compared on the PC and not kept. The video's sound is read from YouTube once when the track starts:
  three to six seconds.

## 0.14.0 (2026-11-24)

- **Photo Frame: one photo fades into the next.** With the direct drawing firmware a change is a
  crossfade of one second, 27 pictures a second on the cooler. "A cut" in the mode's settings switches
  it off.
- **Photo Frame: a new photo as often as every 15 seconds** with the direct drawing firmware, where
  nothing is written to the cooler's flash. On DeepCool's own firmware the shortest stays 15 minutes.

## 0.13.1 (2026-11-24)

- **A firmware update is sent only when the cooler has room for it.** The app asks the cooler first (a
  patch from 4 on can be asked). One without room is sent nothing, and the app says so within a second.
  Before, the file was sent whole and the cooler threw it away without a word.
- **An update that found no room waits for the cooler's next start.** A patch before 15 keeps 384 KB
  from the first picture it draws until the cooler loses power. The app remembers the update and sends
  it by itself the next time it starts on a cooler that has just been switched on, before it draws
  anything. Settings shows that it is waiting, and has a button to call it off.
- Before an update from a patch older than 15, the app puts its own plain picture on the cooler's
  screen: with a large stored picture on show the cooler was short of room by 36 KB.

## 0.13.0 (2026-11-24)

- **Firmware patch 15: a new picture at every refresh of the panel.** The cooler's panel refreshes 55
  times a second, and a drawn frame took two refreshes: 27 pictures a second at the most. The patch
  leaves out a copy the cooler made of every frame, and has it redraw at once. 55 pictures a second
  reach the glass.
- **Smooth video.** A video of 30 pictures a second is shown 30 times a second (it was 27), and the NBA
  highlights play at 30. The Visualizer runs at 41 pictures a second.
- **Updates and uploads that were dropped without a word.** The cooler needs 2 MiB of its memory in one
  piece for an upload. With patches 3 to 14 holding their frame buffers there could be 36 KB too little:
  a firmware update was sent whole and the cooler went on as before, unchanged and unharmed. Patch 15
  gives its buffers back before an upload.
- Updating *to* patch 15 from an older patch can still be dropped that way, and the app says so when it
  is. The cooler has the most room right after the PC was switched on, before anything was drawn.
- The patch can be told to write a word of the cooler's memory (patch 10), for trying a setting on the
  running firmware.
- Patches 10 to 14 were steps on the way and are in no release.

## 0.12.0 (2026-11-24)

- **Firmware patch 9: frames arrive faster.** The cooler takes a frame's bytes at 997 KB a second,
  whatever the frame's size. Patches 3 to 6 took frames over 26 KB at 540: a frame of 40 KB every 100 ms,
  now every 55. A frame of up to 33 KB is on the glass at the panel's next refresh (it was 26 KB).
- **Sharper video at the same rate.** With patch 9 on the cooler, Video and TikTok let a frame be 32 KB
  where they kept it to 22, and go up to JPEG quality 80 where they stopped at 65. The NBA highlights
  play at quality 65 and more, 27 pictures a second.
- Patches 7 and 8 were tries on the way and are in no release.

## 0.11.1 (2026-11-24)

- **Smaller frames.** Every drawn picture carries Huffman tables made for it. The cooler shows the same
  pixels from fewer bytes: 3 to 5 % fewer for a busy picture, 25 to 45 % for a page with flat areas, 61 %
  for a screen of one colour.
- `tools/screen.py`: the cooler's screen read back over USB, pixel for pixel (needs patch 4 or later).

## 0.11.0 (2026-11-23)

- **Firmware patch 6: deephack's own start screen.** While the PC starts, the cooler shows deephack's
  logo where DeepCool's was, from the first moment until an app takes the screen over.
- The patch can be asked for the cooler's memory (patch 4). `tools/fw/dump.py` reads the bootloader out
  with it.

## 0.10.0 (2026-11-23)

- **Firmware patch 3: a part of the picture drawn by itself.** When only one rectangle of a picture
  changes, the page is sent once and after that only the rectangle. The NBA highlights use it: 21 KB a
  frame where the whole page was 29.
- For modes: return `Part(page, picture, at)`. A cooler with an older patch gets whole pictures.

## 0.9.0 (2026-11-23)

- **NBA: the highlights of your team's game**, once it is over: found on YouTube, played once between
  the final score and the points per quarter, with a button and a key to play them again. Off unless
  switched on.
- **Now Playing: the track's music video**, in step with the music, in the cover's place or over the
  whole screen. Off unless switched on.
- Scene: Chișinău's City Gates are wider.

## 0.8.0 (2026-11-23)

- **More pictures a second.** The cooler had been waiting for the app, not the other way round. A
  YouTube video of 25 a second gets 25 (16 before), TikTok 24 to 27, the dancing pet and the Visualizer
  26, Mirror 19 to 26. Video and TikTok lower the JPEG quality before they drop pictures.

## 0.7.1 (2026-11-23)

- Fixed: Video kept some thirty idle threads for every size of video it had played (#53).

## 0.7.0 (2026-11-23)

- Claude Pet: the title and artist of the song it dances to, above it, and the album's cover behind the
  dance (which can be switched off).

## 0.6.0 (2026-11-23)

- **Mirror**: a window or a part of the screen on the cooler, live.
- **Scene: real cities**, drawn by their landmarks: Chișinău, Paris, London, New York, Tokyo.
- Countdown: a Christmas look.
- Settings: a newer yt-dlp can be fetched from the app, for when YouTube links stop working.
- `tools/longrun.py`, for runs of hours on the cooler, and `docs/reversing.md`, how the cooler's screen
  was reverse engineered.

## 0.5.0 (2026-11-22)

- **A Settings page**: what belongs to the app, the cooler and its firmware is there now, off the mode
  pages.
- Video and TikTok: sound from the PC, in time with the picture.
- The MIT licence, and a list of what the standalone app carries.

## 0.4.0 (2026-11-20)

- **TikTok**: random videos without an account, with Next and Previous as buttons and as keys.

## 0.3.0 (2026-11-20)

- **Video**: a YouTube link or a video file plays on the cooler. Needs the direct drawing firmware.

## 0.2.0 (2026-11-20)

- **The app installs the direct drawing firmware** on the cooler, and DeepCool's own again, from its
  window.
- Firmware patch 2: frames are taken after a fast animation has played, and the patch says which version
  it is.

## 0.1.0 (2026-11-20)

The first release.

- Modes: Now Playing, Weather, Claude Code usage, Claude Pet, NBA, Countdown, Photo Frame, Game Cover,
  Ticker, System, Live (the cooler's own sensor screens), GitHub, Calendar, Scene, Visualizer, and Auto,
  which shows whatever has something to show.
- **Direct drawing**: a patch for the cooler's firmware that shows a picture straight from USB, without
  storing it. With it every mode is drawn live: a progress bar in Now Playing, a city with moving cars,
  a pet that dances to the beat.
- The cooler's side light and, through OpenRGB, the PC's other lights follow the screen.
- An emulator that runs the cooler's firmware (`tools/emu`), which is where the patch was written.
- Releases built by GitHub: the standalone app, the wheel and the source archive.
