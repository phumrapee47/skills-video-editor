# 🎬 video-editor — Claude Code skill

[English](#english) · [ภาษาไทย](#ภาษาไทย)

## English

A Claude Code skill that edits video with ffmpeg and Python: finding the best moments in a livestream or long video, making vertical Shorts with subtitles, placing background music at the right moments, and building 2.5D animations from real photos synced to a narration.

Every rule in the skill comes from real experiments and a viewer's scores, not guesswork. The latest test clip scored **9.5/10**.

### 📦 Install

```
/plugin marketplace add phumrapee47/video-editor
/plugin install video-editor@video-editor
```

Update to the latest version:

```
/plugin marketplace update video-editor
```

**Manual install (personal skill):** copy `plugins/video-editor/skills/video-editor` to `~/.claude/skills/`, then call it with `/video-editor`.

### Requirements

Check a machine in one step: `python -I scripts/doctor.py` (it reports what is missing and how to fix it; it installs nothing). `pip install -r requirements.txt` covers the Python side. Titles and captions use bundled open-licence fonts (`assets/fonts`: Kanit, Playfair Display, Anton, SIL OFL), so edits look the same on Windows, macOS and Linux. Regression tests: `python -I tests/run_tests.py` (generated media only, ~20 s); they also run on every push (GitHub Actions).

- **ffmpeg** (tested with 9.0.1), runnable from the command line
- **Python 3.11** with `numpy` and `Pillow`
- **yt-dlp** to fetch video metadata and subtitles from YouTube
- **rembg** (`pip install "rembg[cpu]"`) to remove photo backgrounds (downloads its model on first use)
- **faster-whisper** (optional) for English transcription with word timestamps. For Thai use ElevenLabs Scribe through the **Creative Claw** plugin (paid credits, about 2 credits per 2 minutes)

### What it does

**1. 2.5D animation from a narration**
- Storyboards the narration with a shot change about every 3 seconds, landing visuals on key words
- Finds freely licensed real photos on Wikimedia Commons, removes backgrounds, and keeps the credits
- Layers images in depth, grades every photo to one look, and adds real moving atmosphere (clouds, smoke, ash)
- Camera shake and sound effects only where the story is tense or exciting; explainer diagrams and call-outs; whip-pan transitions
- Checks that the hero subject is never cropped (`scripts/check_cutout.py`) and sends a preview before the full render
- Narration from the user's own recording or an AI voice (ElevenLabs through the Creative Claw plugin, or free edge-tts), one file per line, with Thai years and numbers written out so the voice reads them right
- Swaps the voice of a finished edit without re-tuning it: `scripts/retime.py` maps every visual, effect and music cue from the old voice's timing onto the new one

**2. Highlights from livestreams or long videos, cut into short clips**
- Keeps storytelling, interaction with people, showing something, and punchlines; drops dead air and aimless walking
- Uses the transcript, loudness, and YouTube's replay heatmap to find candidates, then checks the frames
- Makes 9:16 vertical clips with subtitles and loudness set per style

**3. Music and sound**
- Narrated documentaries and 2.5D animations: a soft music bed under the whole narration, about 11 dB below the voice, changing with the mood
- Vlogs and streams: no music while people talk; music fades in only during scenery or whatever the camera is showing, and fades out before speech returns (ducked on subtitle timestamps)
- Picks the music genre from the setting, and always runs a level calibration before asking a listener to judge

**4. Basic editing**
- Cut, join, crop, speed change, subtitles, loudness, export
- Orders several clips by their recording timestamps (`scripts/order_clips.py`), then asks the user to confirm
- One JSON edit plan renders a whole footage edit: clips, transitions, Thai-safe titles, voice, ducked music, effects, subtitles, loudness (`scripts/edit_plan.py`, `--preview` first)
- Checks every video before it is sent: format and colour range, loudness and true peak, black or frozen picture, silence, subtitle timing and width, plus a contact sheet (`scripts/qa_check.py`)
- Renders photo-animation frames on all CPU cores, about 6x faster (`scripts/render_frames.py`)

**5. Podcast and interview Shorts (one command)**
- `scripts/podcast_short.py`: long talk -> vertical Short, stopping at three approval gates (picked lines, B-roll downloads, preview)
- Picks a self-contained, on-topic answer from the transcript (skips the host's questions and sign-offs), cuts on word edges
- Topic card intro, persistent headline, reframing that follows the speaker, split screen for two-shots, punch-in every ~3 s
- Word-stack captions in mixed type (key word big, bold italic serif, colour per phrase; numbers in red)
- Huge key words behind the person (person mask per frame), B-roll with the speaker in a circle bubble
- Key words and B-roll found automatically (`pick_moments.py`, `find_broll.py`: free-licence Wikimedia Commons only, downloads only after approval)
- Several Shorts from one long video: `scripts/podcast_batch.py` picks the best separate threads; titles and approvals for every clip live in one `batch.json`
- Platform safe zones: every vertical render is checked against the TikTok / Reels / Shorts interface (top tabs, right-hand buttons, bottom caption area) with a shaded check sheet (`scripts/safe_zones.py`)
- Thai word-stack captions: `scripts/thai_words.py` cuts Scribe's Thai characters into timed words (pythainlp), then the same stack style as English (lines packed by visible width, split names kept together)
- Follows whoever is talking in a two-shot (`reframe.py --speaker order|cut`, no model: mouth and jaw motion per speech turn): split screen with the speaker in the lower panel, or a close-up of the speaker
- Sound design: synthesised effect kit (whoosh, pop, riser, impact...; no downloads) placed where the picture changes, levels set against the speech (`scripts/sound_design.py`)
- Brand kit: one `brand.json` for fonts, accent colours, grade, corner logo, end card and effect level (`scripts/brand.py`)
- Music by mood: scan a music folder once, read the edit's mood from its words and titles, pick the closest track (`scripts/music_mood.py`)
- Free sound library: catalogue of 1,700+ CC BY / CC0 tracks and place recordings (Kevin MacLeod, Scott Buckley, Wikimedia Commons) with tags and credits; audio fetched on request into `~/.video-editor/sounds`, credits written for every render (`scripts/sound_library.py`)
- Travel and vlog montages from raw footage (`scripts/montage.py`): best moments, story order, cuts in beats, travel titles (pin, poem, spaced, stamp); the place's own sound first (YAMNet hears waterfalls, waves, birds, markets: `scripts/place_sound.py`), soft music chosen from the pictures and auditioned by ear (`scripts/music_audition.py`), -16 LUFS
- Built from a study of 21 reference podcast Shorts (`references/podcast-shorts.md`), version by version (v2 -> v10)

**6. Other genres**
- Product/ad: best moments by picture (`find_shots.py`), cuts on the music's bar grid (`music_beats.py`)
- Screen-recording tutorials: zoom to the action, fast-forward waiting (`screen_focus.py`)
- Animated titles (pop, punch, slide, word by word), accent words, topic cards, text-only cards

### Test results

| What was tested | Result |
|---|---|
| Animation v1 (geometric shapes in Blender) | Rejected: "not pretty at all", use real photos |
| Animation v2 (real photo cut-outs, layered) | 6/10: whole clip shook, too much empty space |
| Animation v3 (mood-based shake, layered temples, mood sound) | 8/10, passed: the sky was still generated, not a photo |
| Animation with the v4 rules (Pompeii clip) | **9.5/10**: "understands the mood and context"; minus 0.5 for cropping the hero subject |
| Ducking music under speech | Subtitle-timestamp ducking beat a sidechain compressor in a listening test |
| Audible music level under speech | 20 dB below speech: inaudible; 10-15 dB: audible |
| Highlight finder | "Good enough" |

### Demos

The videos in `demos/` are real results from the tests. In the Pompeii and Roro Jonggrang demos **the narration and subtitles were removed** because the narration belongs to the original creator; what remains is the picture, on-screen text, and sound effects. The Ayutthaya demo has its own script, an AI voice, a music bed and Thai subtitles.

- [`demos/pompeii_demo.mp4`](demos/pompeii_demo.mp4): Pompeii, bodies frozen in time (85 s)
- [`demos/roro_jonggrang_demo.mp4`](demos/roro_jonggrang_demo.mp4): the legend of Roro Jonggrang (81 s)
- [`demos/ayutthaya_demo.mp4`](demos/ayutthaya_demo.mp4): the Buddha head in the tree roots, Wat Mahathat, Ayutthaya (137 s, AI narration in Thai)

Credits for every photo, footage clip, sound, and music track are in [`demos/CREDITS.md`](demos/CREDITS.md). The demo videos are released under CC BY-SA 4.0, as required by the source photos.

### Limits

- Claude cannot hear. Music fit, mix balance, and humor need a human listener.
- Whisper small cannot transcribe Thai. ElevenLabs Scribe (Creative Claw `transcribe`) can: on a 130 s Thai recording it found all 17 script lines within 0.08 s of hand-tuned times, and `scripts/align_script.py` turns that into line timing and subtitles. It costs credits; YouTube Thai auto captions remain the free fallback (2-3 s chunks).
- YouTube videos may include an AI-dubbed audio track; choose the original track (see `references/ffmpeg-recipes.md`).
- Other people's audio or video is for local testing only. Publishing it needs permission; credit alone is not enough.

---

## ภาษาไทย

Skill สำหรับ Claude Code ที่ตัดต่อวิดีโอด้วย ffmpeg และ Python ตั้งแต่หาช่วงเด็ดในไลฟ์หรือคลิปยาว ทำ Shorts แนวตั้งพร้อมซับ วางเพลงประกอบให้ถูกจังหวะ ไปจนถึงสร้างแอนิเมชัน 2.5D จากภาพจริงตามเสียงบรรยาย

กฎทุกข้อใน skill มาจากการทดลองจริงและการให้คะแนนของคนดู ไม่ได้มาจากการเดา คลิปทดสอบล่าสุดได้ **9.5/10**

### 📦 ติดตั้ง

```
/plugin marketplace add phumrapee47/video-editor
/plugin install video-editor@video-editor
```

อัปเดตเป็นเวอร์ชันล่าสุด:

```
/plugin marketplace update video-editor
```

**ติดตั้งแบบ manual (personal skill):** คัดลอกโฟลเดอร์ `plugins/video-editor/skills/video-editor` ไปไว้ที่ `~/.claude/skills/` แล้วเรียกด้วย `/video-editor`

### สิ่งที่ต้องมี

ตรวจเครื่องในคำสั่งเดียว: `python -I scripts/doctor.py` (บอกว่าขาดอะไรและแก้อย่างไร ไม่ติดตั้งอะไรเอง) ฝั่ง Python ใช้ `pip install -r requirements.txt` ตัวหนังสือในคลิปใช้ฟอนต์ลิขสิทธิ์เปิดที่แนบมา (`assets/fonts`: Kanit, Playfair Display, Anton, SIL OFL) หน้าตาจึงเหมือนกันทั้ง Windows, macOS และ Linux ชุดทดสอบ: `python -I tests/run_tests.py` (ใช้วิดีโอที่สร้างขึ้นเอง ราว 20 วินาที) และรันอัตโนมัติทุก push บน GitHub Actions

- **ffmpeg** (ทดสอบกับ 9.0.1) สั่งรันจาก command line ได้
- **Python 3.11** พร้อม `numpy` และ `Pillow`
- **yt-dlp** สำหรับดึงข้อมูลคลิปและซับจาก YouTube
- **rembg** (`pip install "rembg[cpu]"`) สำหรับตัดฉากหลังของภาพ (โหลดโมเดลครั้งแรกที่ใช้)
- **faster-whisper** (ไม่บังคับ) ถอดเสียงภาษาอังกฤษพร้อมเวลาระดับคำ ส่วนภาษาไทยใช้ ElevenLabs Scribe ผ่านปลั๊กอิน **Creative Claw** (ใช้เครดิต ราว 2 เครดิตต่อ 2 นาที)

### ทำอะไรได้บ้าง

#### 1. แอนิเมชัน 2.5D จากเสียงบรรยาย
- วางสตอรีบอร์ดตามเสียงบรรยาย เปลี่ยนช็อตทุกราว 3 วินาที ผูกภาพกับคำสำคัญ
- หาภาพจริงที่ใช้ได้ตามลิขสิทธิ์จาก Wikimedia Commons ตัดฉากหลัง และเก็บเครดิตให้
- ซ้อนชั้นมีมิติ ปรับสีชุดเดียวทั้งคลิป ใส่บรรยากาศเคลื่อนไหวจริง (เมฆ ควัน เถ้า)
- ภาพสั่นและเสียงประกอบเฉพาะช่วงที่มีอารมณ์ มีแผนภาพอธิบายและเส้นชี้ เปลี่ยนฉากแบบกวาดกล้อง
- ตรวจว่าวัตถุหลักไม่ถูกครอปขาด (`scripts/check_cutout.py`) และส่งพรีวิวก่อนเรนเดอร์เต็ม
- เสียงบรรยายใช้ได้ทั้งเสียงที่ผู้ใช้อัดเองและเสียง AI (ElevenLabs ผ่านปลั๊กอิน Creative Claw หรือ edge-tts ที่ฟรี) ทำทีละบรรทัด และเขียนปีหรือตัวเลขเป็นคำอ่านให้เสียงอ่านถูก
- เปลี่ยนเสียงพากย์ของคลิปที่ทำเสร็จแล้วได้โดยไม่ต้องจูนใหม่: `scripts/retime.py` แปลงเวลาของภาพ เอฟเฟกต์ และเพลงจากเสียงเดิมไปตามเสียงใหม่

#### 2. หาช่วงเด็ดจากไลฟ์หรือคลิปยาว แล้วทำคลิปสั้น
- เก็บเฉพาะการเล่าเรื่อง ปฏิสัมพันธ์ การโชว์ของ และมุก ตัดช่วงเงียบและการเดินเรื่อยๆ
- ใช้บทพูด ความดังเสียง และ heatmap ของ YouTube หาจุดเริ่ม แล้วดูภาพยืนยัน
- ทำแนวตั้ง 9:16 พร้อมซับ และปรับระดับเสียงตามสไตล์

#### 3. เพลงและเสียง
- สารคดีหรือแอนิเมชัน 2.5D ที่มีเสียงบรรยาย: ใส่เพลงเบาๆ ใต้เสียงบรรยายตลอดคลิป เบากว่าเสียงพูดราว 11 dB และเปลี่ยนตามอารมณ์
- vlog และไลฟ์: ไม่มีเพลงตอนคนพูด เพลงค่อยๆ เข้ามาเฉพาะตอนโชว์วิวหรือสิ่งที่กล้องชี้ แล้วลดลงก่อนเสียงพูดกลับมา (ลดตามเวลาของซับ)
- เลือกแนวเพลงตามสถานที่ และทดสอบระดับเสียงก่อนให้คนฟังตัดสินทุกครั้ง

#### 4. งานตัดต่อพื้นฐาน
- ตัด ต่อ ครอป เร่งความเร็ว ใส่ซับ ปรับความดัง export
- เรียงหลายคลิปตาม timestamp ในไฟล์ (`scripts/order_clips.py`) แล้วให้ผู้ใช้ยืนยัน
- ไฟล์แผนตัดต่อ JSON ไฟล์เดียวเรนเดอร์ได้ทั้งคลิป: คลิป ทรานซิชัน หัวข้อภาษาไทยที่วรรณยุกต์ครบ เสียงพากย์ เพลงที่ลดตอนพูด เอฟเฟกต์ ซับ และความดัง (`scripts/edit_plan.py` ทำ `--preview` ก่อน)
- ตรวจทุกคลิปก่อนส่ง: รูปแบบไฟล์และช่วงสี ความดังและเสียงแตก จอดำหรือภาพนิ่ง เสียงเงียบ เวลาและความกว้างของซับ พร้อมภาพสรุปทั้งคลิป (`scripts/qa_check.py`)
- เรนเดอร์ภาพแอนิเมชันพร้อมกันทุกคอร์ เร็วขึ้นราว 6 เท่า (`scripts/render_frames.py`)

#### 5. คลิปสั้นจากพอดแคสต์และสัมภาษณ์ (คำสั่งเดียว)
- `scripts/podcast_short.py`: คลิปยาว → Short แนวตั้ง หยุดถาม 3 จุด (ช่วงที่เลือก, ไฟล์ B-roll ที่จะดาวน์โหลด, ตัวอย่าง)
- เลือกคำตอบที่จบในตัวและตรงหัวข้อจาก transcript (ข้ามคำถามและคำปิดของพิธีกร) ตัดตรงขอบคำ
- การ์ด topic ตอนเปิด, หัวข้อค้างทั้งคลิป, ครอปตามคนพูด, แบ่งจอบน-ล่างสำหรับสองคน, ซูมเข้า-ออกทุกราว 3 วินาที
- ซับแบบกองคำ ตัวอักษรผสม (คำเด่นใหญ่ serif ตัวหนาเอียง สีเปลี่ยนตามวลี ตัวเลขสีแดง)
- คำใหญ่อยู่หลังคน (ตัดคนออกทุกเฟรม), B-roll พร้อมหน้าคนพูดในวงกลม
- หาคำสำคัญและ B-roll อัตโนมัติ (`pick_moments.py`, `find_broll.py`: ใช้เฉพาะไฟล์ลิขสิทธิ์เปิดจาก Wikimedia Commons ดาวน์โหลดหลังอนุมัติเท่านั้น)
- หลายคลิปจากวิดีโอยาวเดียว: `scripts/podcast_batch.py` เลือกช่วงที่ดีที่สุดหลายช่วงที่ไม่ซ้อนกัน ชื่อคลิปและการอนุมัติทุกคลิปอยู่ใน `batch.json` ไฟล์เดียว
- ขอบปลอดภัยของแพลตฟอร์ม: ทุกคลิปแนวตั้งถูกเช็กว่าข้อความไม่ทับแท็บบน ปุ่มขวา และแถบข้อความล่างของ TikTok / Reels / Shorts พร้อมภาพแรเงาให้ดู (`scripts/safe_zones.py`)
- ซับไทยแบบกองคำ: `scripts/thai_words.py` ตัดคำไทยจากผลถอดเสียง Scribe พร้อมเวลา (pythainlp) แล้วใช้สไตล์กองคำแบบเดียวกับภาษาอังกฤษ (จัดบรรทัดตามความกว้างจริง ชื่อที่ถูกตัดเป็นชิ้นอยู่บรรทัดเดียวกัน)
- ตามคนพูดในภาพสองคน (`reframe.py --speaker order|cut` ไม่ใช้โมเดล ดูการขยับปากและกรามในแต่ละช่วงพูด): แบ่งจอโดยให้คนพูดอยู่จอล่าง หรือตัดไปภาพใกล้ของคนพูด
- เสียงประกอบอัตโนมัติ: สังเคราะห์เสียง whoosh, pop, riser, impact เอง (ไม่ต้องดาวน์โหลด) วางตรงจุดที่ภาพเปลี่ยน ระดับเสียงเทียบกับเสียงพูด (`scripts/sound_design.py`)
- Brand kit: ไฟล์ `brand.json` ไฟล์เดียวกำหนดฟอนต์ สี โทนภาพ โลโก้มุมจอ การ์ดปิดท้าย และระดับเสียงเอฟเฟกต์ (`scripts/brand.py`)
- เลือกเพลงตามอารมณ์: วิเคราะห์คลังเพลงครั้งเดียว อ่านอารมณ์คลิปจากคำพูดและหัวข้อ แล้วเลือกเพลงที่ใกล้ที่สุด (`scripts/music_mood.py`)
- คลังเสียงฟรี: รายชื่อเพลงและเสียงสถานที่กว่า 1,700 รายการ (CC BY / CC0 จาก Kevin MacLeod, Scott Buckley, Wikimedia Commons) พร้อมแท็กและเครดิต ดาวน์โหลดเมื่อต้องใช้ และเขียนเครดิตให้ทุกคลิป (`scripts/sound_library.py`)
- คลิปท่องเที่ยว/vlog จากฟุตเทจดิบ (`scripts/montage.py`): คัดช่วงดี เรียงเรื่องเล่า ตัดตามจังหวะเพลง ตัวหนังสือแบบท่องเที่ยว ให้เสียงสถานที่มาก่อน (YAMNet ฟังเสียงน้ำตก คลื่น นก ตลาด) เลือกเพลงนุ่มๆ จากภาพแล้วให้คนเลือกด้วยหูจาก audition ความดัง -16 LUFS
- สร้างจากการศึกษาคลิปพอดแคสต์ตัวอย่าง 21 คลิป (`references/podcast-shorts.md`) ทีละเวอร์ชัน (v2 → v10)

#### 6. แนวอื่น
- โฆษณาสินค้า: หาช่วงภาพที่ดีที่สุด (`find_shots.py`) ตัดตามห้องเพลง (`music_beats.py`)
- สอนอัดหน้าจอ: ซูมไปยังจุดที่ทำงาน ข้ามช่วงรอ (`screen_focus.py`)
- หัวข้อเคลื่อนไหว (pop, punch, slide, ทีละคำ), คำเน้นสี, การ์ด topic, การ์ดข้อความ

### ผลการทดสอบ

| สิ่งที่ทดสอบ | ผล |
|---|---|
| แอนิเมชัน v1 (รูปทรงเรขาคณิตใน Blender) | ไม่ผ่าน: "ไม่สวยเลย" ให้ใช้ภาพจริง |
| แอนิเมชัน v2 (ภาพจริงตัดขอบซ้อนชั้น) | 6/10: ภาพสั่นทั้งคลิป พื้นที่ว่างเยอะ |
| แอนิเมชัน v3 (สั่นตามอารมณ์ วิหารซ้อนหลายชั้น เสียงตามอารมณ์) | 8/10 ผ่าน: ท้องฟ้ายังเป็นภาพที่สร้างเอง |
| แอนิเมชันตามกฎ v4 (คลิปปอมเปอี) | **9.5/10**: "เข้าถึงอารมณ์ เข้าใจบริบททุกอย่าง" หัก 0.5 เพราะครอปวัตถุหลักขาด |
| วิธีลดเสียงเพลงตอนพูด | ลดตามเวลาซับ ชนะ sidechain compressor ในการฟังเทียบ |
| ระดับเพลงที่ได้ยินใต้เสียงพูด | ต่ำกว่า 20 dB ไม่ได้ยิน, 10-15 dB ได้ยิน |
| ตัวหาช่วงเด็ด | "พอใช้ได้" |

### เดโม

วิดีโอใน `demos/` เป็นผลงานจริงจากการทดสอบ เดโมปอมเปอีกับ Roro Jonggrang **ตัดเสียงบรรยายและซับออก** เพราะเสียงบรรยายเป็นลิขสิทธิ์ของเจ้าของช่อง จึงเหลือภาพ ข้อความ และเสียงประกอบ ส่วนเดโมอยุธยาใช้บทที่เขียนเอง พากย์ด้วยเสียง AI มีเพลงประกอบและซับไทย

- [`demos/pompeii_demo.mp4`](demos/pompeii_demo.mp4): ปอมเปอี ร่างที่หยุดเวลา (85 วินาที)
- [`demos/roro_jonggrang_demo.mp4`](demos/roro_jonggrang_demo.mp4): ตำนาน Roro Jonggrang (81 วินาที)
- [`demos/ayutthaya_demo.mp4`](demos/ayutthaya_demo.mp4): เศียรพระในรากไม้ วัดมหาธาตุ อยุธยา (137 วินาที พากย์ไทยด้วยเสียง AI)

เครดิตภาพ ฟุตเทจ เสียง และเพลงทั้งหมดอยู่ใน [`demos/CREDITS.md`](demos/CREDITS.md) วิดีโอเดโมเผยแพร่ภายใต้ CC BY-SA 4.0 ตามเงื่อนไขของภาพต้นฉบับ

### ข้อจำกัด

- Claude ฟังเสียงไม่ได้ ความเข้ากันของเพลง ความสมดุลเสียง และความตลก ต้องให้คนฟังตัดสิน
- Whisper รุ่น small ถอดเสียงภาษาไทยไม่ได้ แต่ ElevenLabs Scribe (Creative Claw `transcribe`) ทำได้: เสียงไทย 130 วินาที เจอครบ 17 บรรทัด คลาดจากเวลาที่จูนเองไม่เกิน 0.08 วินาที และ `scripts/align_script.py` แปลงเป็นเวลาบรรทัดกับซับให้ ใช้เครดิต ส่วนซับอัตโนมัติของ YouTube ยังเป็นทางเลือกฟรี (ช่วงละ 2-3 วินาที)
- คลิปจาก YouTube อาจมีแทร็กเสียงพากย์อัตโนมัติ ต้องเลือกแทร็กเสียงต้นฉบับให้ถูก (วิธีอยู่ใน `references/ffmpeg-recipes.md`)
- เสียงหรือคลิปของคนอื่นใช้ทดลองในเครื่องเท่านั้น ถ้าจะเผยแพร่ต้องได้รับอนุญาต การใส่เครดิตอย่างเดียวไม่พอ
