# Edit plan: one JSON file per footage edit

`scripts/edit_plan.py plan.json` renders a whole edit (vlog, Short, interview cut, highlight reel, product clip) from one
file, so an edit is reproducible, easy to change, and needs no new code per genre. 2.5D photo animations keep their own
Pillow compositor (render it with `scripts/render_frames.py`) and can then be used as a clip in a plan.

Always: `--preview A B` first (half size, only A..B s), show it, then the full render. The script runs `qa_check.py`
on the result and writes `<out>.timeline.json`, `<out>.sheet.jpg` and `<out>.qa.json`; read the sheet before sending.

## Format
Paths are relative to the plan file. Times in seconds.

```json
{
 "output": {"path": "out.mp4", "size": [1080, 1920], "fps": 30, "target": "shorts", "fit": "blur", "crf": 19},
 "clips": [
  {"src": "a.mp4", "in": 2, "out": 12, "fit": "crop", "speed": 1.0, "volume_db": 0, "speech": true,
   "titles": [{"text": "เกียวโตยามค่ำ", "start": 0.3, "end": 3.0, "pos": "top", "size": 110}]},
  {"src": "b.mp4", "in": 5, "out": 13, "transition": {"type": "fade", "dur": 0.5}}
 ],
 "titles": [{"text": "line one\nline two", "start": 20, "end": 22.5, "pos": "center", "fade": 0.3, "color": [250, 240, 220]}],
 "audio": [
  {"src": "music.mp3", "role": "music", "start": 0, "end": 60, "in": 0, "loop": true, "fade_in": 1.5, "fade_out": 2.5},
  {"src": "vo/line01.mp3", "role": "voice", "start": 0.4},
  {"src": "whoosh.wav", "role": "sfx", "start": 9.4, "in": 0, "out": 1.2, "volume_db": -12}
 ],
 "music_mix": {"gap_db": -8, "under_db": -30},
 "subtitles": {"src": "subs.srt", "style": "FontName=Leelawadee UI,FontSize=16,...", "duck_from": true}
}
```

| Field | Meaning |
|---|---|
| `output.target` | loudness target: `youtube`/`shorts` -14 LUFS, `doc` -18.5, `master` -23 (or set `lufs`) |
| `output.fit` / `clip.fit` | `crop` (fill), `pad` (letterbox), `blur` (whole frame over a blurred fill; 16:9 footage in 9:16) |
| `clip.in/out` | source seconds; `speed` changes picture and sound (atempo keeps pitch) |
| `clip.transition` | on the incoming clip: any ffmpeg xfade name (`fade`, `dissolve`, `slideleft`, `wipeup`, `circleopen`...); omitted = hard cut |
| `clip.titles` | times relative to the clip; top-level `titles` use timeline time |
| `clip.speech` | `false` for ambience-only clips (their sound is not treated as speech); `talk: [[a, b], ...]` marks speech inside a clip |
| `audio.role` | `voice` (ducks music), `music` (looped, loudness-matched to speech, ducked), `sfx` (placed as is) |
| `music_mix` | `gap_db` music level in gaps vs speech; `under_db` while speech plays. Vlog/stream: -8 / -30 (music off under talk). Narrated documentary: -8 / -11 (soft bed under the voice). See `music-rules.md` |

Speech times for ducking come from, in order: subtitle cues, voice tracks, clip `talk` spans; if none are given they are
detected from the clip and voice sound (100 ms energy, gaps under 0.5 s bridged). Music lowers 0.5 s before speech and
recovers 1.5 s after.

## Rendering rules it enforces (learned the hard way)
- Titles are an ASS track drawn by libass. ffmpeg `drawtext` and Pillow without raqm (`PIL.features.check("raqm")` is
  False on this machine) drop a Thai tone mark that sits on an upper vowel: ที่นี่ became ทีนี, นั่ง became นัง.
- Video is H.264 yuv420p **limited range** (`scale=out_range=tv`). Frames from JPEG/PNG are full range; encoded as is
  they come out `yuvj420p/pc`, which some players and uploads show washed out.
- Loudness is two-pass (measure, then linear gain); single-pass loudnorm landed 1.6 dB under target on a 21 s Short.
- A title that ends after the timeline is reported as a WARNING.

## Speed (24-core machine)
Footage plan, 21 s vertical Short with 3 clips, 2 transitions, 2 titles, music, sfx: 14 s including QA.
