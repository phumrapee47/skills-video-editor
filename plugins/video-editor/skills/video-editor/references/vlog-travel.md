# Vlog and travel edits (study of 22 reference clips, 2026-11-22)

Source: 22 finished clips in the user's reference folder (8 tourism promos of 30 s, 9 cinematic travel films of
1-7 min, 5 talking vlogs of 3-8 min; Creative Commons or press-kit downloads, local study only). Measured with
`scripts/study_refs.py` (cuts, dissolves, shot length, beat sync, talk share, loudness) plus a 12-frame strip of each.

## Two families
| | Cinematic travel film / promo | Talking vlog (day in the life, food, family trip) |
|---|---|---|
| talk share | 0-0.17 (music-led, maybe a few spoken or written lines) | 0.54-0.93 |
| shot length (median) | promo 30 s: 0.6-0.9 s; film 1-7 min: 2.0-3.6 s | 1.0-1.5 s while talking (jump cuts), 4-5.5 s in long takes |
| cuts / 10 s | promo 8-17; film 2.6-4.5 | 1.2-6.7 |
| dissolves | promos 0-3; slow films 9-43 (one every ~10 s) | 3-65 (time skips) |
| loudness | promos -7 LUFS (very loud ads); films -15 to -23 | -10 to -22 |
| text | place pin small lower-left, short chapter line, end title | pin fixed in a top corner, time stamps, dish/place labels, big outlined reaction words, subtitles, subscribe end screen |

## Shape of a cinematic travel film
1. **Arrival**: transport or a sign (train with "LONDON" on it, a car window, a finger on a map, a city sign), often
   with the place name as the opening title.
2. **Wide landmarks**, then **details** (hands, food, faces, textures), people of the place (musicians, cooks).
3. **Light arc**: golden hour and night come late; the end is an aerial or a sunset with a big title
   ("SIEM REAP / MORE THAN TIME" in a teal serif) or a logo card.
4. Text treatments: poetic lines small and centred low ("As you wash away, calm"), questions in a gold serif centred,
   words revealed one by one ("WHAT KIND..."), small spaced capitals on black ("THERE'S ALWAYS A MOMENT BEFORE THE
   JOURNEY BEGINS"), location pins with a pin icon, a music credit lower-left.
5. A strong, consistent grade (teal/orange, warm film), photo-frame inserts (a still on white), black end.

## Beat sync
Cuts of these films were **not** measurably locked to the beat: phase concentration of cuts on the beat or half-beat
grid stayed at the level random cuts reach in 17 of 19 clips with music (only 2 of the 30 s promos were slightly above).
The editors follow the music's phrases and energy, not every beat. The skill still cuts on beats for montages
(harmless and tidy), but keeps shot lengths varied (2, 4 or 8 beats) instead of a fixed beat grid.

## What the skill does with this
- `scripts/montage.py`: raw footage + music -> an edit plan: best shots (sharp, steady, well lit), never two alike in
  a row, story order (wide/arrival -> details -> brightest/golden -> darkest/night), lengths in beats, hard cuts for a
  promo, dissolves every few shots for a film, opening place title and closing title.
- Title styles for travel in edit plans: `pin` (location with a pin mark), `poem` (small line, centred low),
  `spaced` (small spaced capitals), `stamp` (time of day, lower-left).
- Planned, not built yet: `jumpcut.py` for talking vlogs (remove pauses and repeated takes from word timings).

## Sound (user feedback on the first montages, 2026-11-22)
"The music does not fit the scenes at all, and it is too loud" and "travel edits should make us feel we are there:
if there is a waterfall, boost the waterfall". So for travel and event montages:
- the place's own sound first: `place_sound.py` (moments where the music ducks, a bed, library place sounds where the
  footage sound is bad), run by `montage.py` automatically;
- music chosen from the pictures and shortlisted, then **auditioned** by the person (`music_audition.py`);
- -16 LUFS for music-led films instead of -14.
- User verdict on Cape Town v3 (43 s, "Lobby Time", Jazz: Calming/Grooving/Relaxed, waves up on the opener, -16 LUFS):
  liked: "comfortable to the ear, easy to keep watching, smooth". Travel vlogs mostly use soft, pleasant background
  music. The audition's brighter picks (Pop, Funk, Disco) lost. So for travel/vlog edits the picker now asks for
  Relaxed + Calming + Grooving (jazz/lounge for cities) and marks down Driving, Bouncy, Action, Intense, Epic; only a
  fast promo (median shot < 1.3 s) asks for energy.
- Two more passed (2026-11-22): Osaka (16:9, 38 s, city time-lapse, "Groove Grove" soft jazz, the footage's own added
  soundtrack muted and replaced by city/restaurant ambience) and Slow Morning (9:16 Reels, 26 s, coffee footage,
  "Gymnopedie No. 2", cafe ambience, warm grade). Fixed on the way: a teal-graded city read as water and coffee beans
  as city -> Claude looks at the frames and passes `--scene` (cafe, city, beach, nature, night); footage whose shots
  are mostly music carries an added soundtrack -> muted, never a "moment"; spaced titles shrink to fit 9:16; frozen
  stretches of stock footage are skipped; a track used in the last edits is marked down so every city clip does not
  get the same song.
