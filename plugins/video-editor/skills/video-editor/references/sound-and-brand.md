# Sound design, brand kit, music by mood (1.7.0), sound library and place sound (1.8.0)

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

## Sound library (1.8.0): `scripts/sound_library.py`
User asked for "all the free sounds in the skill" after a travel test where 10 local tracks gave music that did not fit.
- Catalogue `assets/sound_catalog.json` (ships with the skill, 1.3 MB): 1,443 Kevin MacLeod tracks (incompetech.com,
  CC BY 4.0, the composer's own tags: feel, genre, instruments, BPM, description), 267 Scott Buckley tracks
  (scottbuckley.com.au, CC BY 4.0, cinematic/orchestral, no tags: measured), 53 hand-picked place recordings from
  Wikimedia Commons (CC0 / public domain / CC BY only: waterfall and rapids, surf, streams, rain, thunder, dawn birds,
  cicadas and frogs, wind in a forest, city streets and malls, markets, a restaurant, crowds, temple bells and gongs,
  trains, an engine, fireworks).
- Audio lives in `~/.video-editor/sounds` (or `VIDEO_EDITOR_SOUNDS`), shared by every copy of the skill, never in git.
  `fetch --set starter|balanced|all` (ask first: names, sources, sizes); the balanced set = 400 MacLeod tracks spread
  over every feel and genre (no Holiday/Polka/Ren Faire, 20 s-7 min, the moods most edits need first) + all Scott
  Buckley + all place sounds, ~4.7 GB. `index` measures what is there into `library.json` (tags + tempo + mood).
- Speeds seen 2026-11-22: incompetech ~40 KB/s per connection (3 polite connections, ~4-5 h for 400 tracks),
  Scott Buckley ~3 MB/s, Commons fine; big Commons WAV/FLAC come as Commons' own MP3 when one exists.
- Not fetched by the skill: kenney.nl CC0 effect packs (the site asks AI tools not to fetch; download by hand into
  `<library>/sfx/kenney`), OpenGameArt (blocks AI agents), freepd.com (closed), Freesound/Pixabay (account or no
  redistribution). Every CC BY sound needs its credit: edit_plan.py writes `<out>.credits.txt` for each render.

## Music that fits the pictures: `music_mood.py pick --by-picture`, `scripts/music_audition.py`
The first Cape Town montage used "Carefree", which its composer tags *Humorous*: comedy music under a city walk. Now:
- `--by-picture` reads the footage (water / greenery / city / night share, median shot length) and asks for feels and
  genres: fast cutting -> Driving, Bright, Grooving; slow -> Calming, Relaxed, Mystical; city -> Grooving +
  Electronica/Funk/Pop/Jazz/Urban; water or green -> Calming + World/Contemporary/Cinematic; night -> Mysterious +
  Electronica/Jazz; never Humorous, Eerie, Unnerving, Aggressive, Suspenseful, nor Holiday/Polka/Horror/Stings/Musical.
- `music_audition.py plan.json --top 4` renders the same 20 s with 4 different shortlisted tracks (one per genre),
  labelled A-D with title, genre and feels, so the person chooses by ear; then `music_mood.py pick plan.json --apply
  --track <id>`. Claude cannot hear: never present a single automatic pick as final for a music-led edit.
- `montage.py --music auto` uses the top pick and `--lufs -16` (the first montage at -14 LUFS was "too loud";
  the reference travel films sit at -15 to -23).

## The place first: `scripts/place_sound.py` (+ `scripts/audio_tags.py`)
The user: in travel edits the viewer should feel present; a waterfall on screen should be heard, louder. Per clip:
1. **Hear** its own sound with YAMNet (AudioSet classes, Qualcomm AI Hub ONNX export 13.9 MB, MIT, in
   `~/.video-editor/models`; onnxruntime): water, birds/insects/frogs, people, street, wind, music, bells,
   fireworks, train, quiet. Held-out check on 35 place recordings: 26 right, most misses arguable (city recordings
   full of talk read as people; a market recording full of pigeons reads as birds). Hand rules without the model got
   6 of 32: they had been tuned on 10 clips and failed on new ones.
2. **Look** at the picture (colour rules: water, greenery, city, night) - weaker than the hearing: the rocky sea shot
   read as "city". Claude checks the sheet and fixes a run by hand when it matters.
3. **Decide**: up to 3 *moments* (water, birds, bells, fireworks, a busker, a busy market; >= 1.2 s; 6 s apart) where
   the clip's sound comes up to -20 dBFS and the music ducks 11 dB under it (`speech` + `talk` on the clip,
   music_mix gap -3 / under -14); usable sound stays as a *bed* 15 dB under; wind, silence, or street noise over
   water/greenery is *replaced*: muted, with a matching library place sound laid over the whole run of clips with fades.
