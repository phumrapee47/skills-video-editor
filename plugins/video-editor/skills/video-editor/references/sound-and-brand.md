# Sound design, brand kit, music by mood (1.7.0)

## Sound effects: `scripts/make_sfx.py` + `scripts/sound_design.py`
`python -I scripts/sound_design.py plan.json [--level -3] [--punch]` puts effects where the picture already changes and
writes them into the plan (role `sfx`, `"sd": true`, so a rerun replaces only its own). The kit is made by
`make_sfx.py` from noise and tones (numpy): no download, no credits, no licence. Put your own `whoosh.wav`, `pop.wav`...
in the kit folder (`<plan dir>/sfx`) to replace any of them.

| Where | Effect | Level vs speech RMS |
|---|---|---|
| topic card heading and each item | pop (items 0.45 s apart) | -17 dB |
| into the first answer after a topic card | riser (ends on the cut) | -13 dB |
| transition of 0.3 s or more | whoosh peaking mid-fade | -13 dB |
| B-roll in / out | whoosh / swish | -13 / -20 dB |
| huge word behind the person | impact | -9 dB |
| text card / last card | hit / chime (1 s in, after the fade's whoosh) | -11 / -15 dB |
| title, headline | pop | -17 dB |
Under speech every effect is 4 dB lower; at most one effect per 0.8 s (pops of a list 0.35 s), the stronger kind wins.
Dissolves under 0.3 s only smooth a cut and get no sound. `"rel_db"` in an audio item sets its level against the speech
(loudest 100 ms), so effects sit the same in every clip whatever the file's own level.
Measured on the podcast Short (v11): effects 14-20 dB under the speech in a 200 ms window, the rest of the mix unchanged
(difference -56 dB). User: "ดี" (A/B v10 vs v11).

## Brand kit: `scripts/brand.py`, plan `"brand": "brand.json"`
```json
{"name": "Flood Lab", "fonts": {"sans": "fonts/Brand-Bold.ttf"}, "accent": "2EC4B6",
 "palette": ["2EC4B6", "FFB703", "FB5607"], "grade": "teal-orange",
 "logo": {"src": "logo.png", "pos": "top-left", "size": 0.11, "opacity": 0.9},
 "end_card": {"text": "Follow for more\n**flood science**", "sub": "@floodlab", "dur": 2.6, "bg": "0B1F2A"},
 "sfx_level": -2, "music": ["Track_A.mp3", "Track_B.mp3"]}
```
- `fonts` replace the bundled fonts per role (sans, serif_italic, heavy) in titles and captions; use fonts you may use.
- `grade`: `clean`, `warm`, `teal-orange`, `film`, `bw` or any ffmpeg chain; applied to the picture before titles and
  captions, so text keeps its exact colours.
- `logo`: hidden while a card or topic card is up; drawn large above the text on the end card. Vertical: top corners sit
  under the apps' top tabs; keep it off the right edge (button column).
- `end_card` is added unless the plan already ends on a card (sound design gives it a chime).
- `music`: the channel's tracks; `music_mood.py` picks only among them. `"sfx": false` turns effects off.
Read by `edit_plan.py`, `word_captions.py`, `sound_design.py`, `podcast_short.py --brand`, `podcast_batch.py --brand`.
Bug found on the way: a word-by-word card split `**flood science**` across words and showed the stars; accent marks may
now span words.

## Music by mood: `scripts/music_mood.py`
`scan <dir>` measures every track once (tempo, onsets per second, loudness, brightness, major/minor, quiet intro) into
`<dir>/library.json`; `pick plan.json --library <dir> --words words.json [--apply]` reads the edit's mood and puts the
closest track in (starting after its quiet intro). `--mood calm` overrides; `--no-talk` for music-led edits.
- Edit mood: topic word lists in English and Thai (happy, sad, tense, epic, calm, wonder), exclamation marks, speaking
  pace, and the plan's titles, headline and cards (an ad without speech is read from its titles). Under talk the target
  energy is pulled down: music is a bed, not a show.
- Track mood: **a listener's tags win** (`"moods": ["warm", "calm"]` in library.json). Measured guesses alone matched only
  about half of 10 Kevin MacLeod tracks (a pizzicato "sneaky" track and an epic track both read as sad; minor/major from
  a chroma profile is weak), so tag a library by ear once; the numbers are the fallback.
- Check against earlier human choices: the product ad (Carefree) and the flood Short (Lost Time) got the same tracks the
  edits already used; the Ayutthaya narration got Dreamer, with Ishikari Lore (used in v1.1) second; a speechless screen
  tutorial got Local Forecast (light, steady).
- `podcast_short.py --music-lib <dir>` / `podcast_batch.py --music-lib <dir>` pick per clip when `--music` is not given.
Credit the composer as the track's licence asks; `scan` copies the folder's CREDITS.md into each track.
