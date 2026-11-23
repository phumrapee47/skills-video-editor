"""Regression tests for the video-editor skill. No downloads, no copyrighted media: every fixture is generated with
ffmpeg (test patterns, tones, flite speech when the build has it). Each test guards a bug that cost a render round.

Usage: python -I tests/run_tests.py [-k name] [--keep]
Exit code 1 if any test fails. About a minute on a laptop.
"""
import argparse, json, pathlib, re, shutil, subprocess, sys, tempfile, time, traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent; SC = ROOT / "scripts"
sys.path.insert(0, str(SC))
PY = [sys.executable, "-I"]
TESTS = []


def test(fn): TESTS.append(fn); return fn


def ff(*args): subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def probe(path, entries="format=duration"):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", str(path)], capture_output=True, text=True).stdout
    return json.loads(out)


def has_flite():
    return "enable-libflite" in subprocess.run(["ffmpeg", "-hide_banner", "-buildconf"], capture_output=True, text=True).stdout


def make_clip(path, dur, color="testsrc2", size="1280x720", speech=None):
    """A test-pattern video with sound: flite speech if available, else a tone that pulses like speech."""
    a = (f"flite=text='{speech}':voice=slt" if speech and has_flite() else
         f"sine=f=220:d={dur},volume='if(lt(mod(t,1),0.6),1,0.05)':eval=frame")
    ff("-f", "lavfi", "-i", f"{color}=s={size}:r=25:d={dur}", "-f", "lavfi", "-i", a, "-t", dur, "-shortest" if not speech else "-t", dur,
       "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", path)


# ---------------------------------------------------------------------------------------------------------------
@test
def fonts_resolve(tmp):
    from fonts import font, ROLES
    for r in ROLES:
        fam, path = font(r); assert pathlib.Path(path).exists(), f"{r}: {path} missing"


@test
def no_control_characters(tmp):
    """No hidden control characters in the code: a typed backslash-b once became a real backspace inside a regex,
    and the sign-off filter silently never matched."""
    bad = []
    for f in list((ROOT / "scripts").glob("*.py")) + list((ROOT / "tests").glob("*.py")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if any(ord(ch) < 32 and ch not in "	" for ch in line): bad.append(f"{f.name}:{n}")
    assert not bad, bad


@test
def retime_roundtrip(tmp):
    """retime.py: the map is monotonic and to_new(to_old(t)) == t at every anchor."""
    from retime import _interp
    new = [0, 1.4, 8.7, 9.5, 17.2, 30]; old = [0, 1.4, 7.8, 8.7, 14.3, 25]
    for t in new: assert abs(_interp(_interp(t, new, old), old, new) - t) < 1e-6
    assert all(_interp(a, new, old) <= _interp(b, new, old) for a, b in zip(new, new[1:]))


@test
def music_beats_bpm(tmp):
    """music_beats.py finds 120 BPM in a click track."""
    wav = tmp / "click.wav"
    ff("-f", "lavfi", "-i", "aevalsrc='if(lt(mod(t,0.5),0.02),sin(2*PI*1000*t),0)':s=44100:d=20", wav)
    out = subprocess.run(PY + [SC / "music_beats.py", wav, "--dur", "20"], capture_output=True, text=True, check=True).stdout
    bpm = float(re.search(r"([\d.]+) BPM", out)[1]); assert abs(bpm - 120) < 2.5 or abs(bpm - 60) < 1.5, out


@test
def edit_plan_render(tmp):
    """edit_plan.py: cuts, xfade after concat (the timebase bug), Thai title, card, still B-roll with bubble, music;
    output length == timeline, limited range, loudness on target, QA PASS."""
    for k, c in enumerate(("testsrc2", "smptebars", "rgbtestsrc")): make_clip(tmp / f"c{k}.mp4", 4, c, speech="This is a test of the editor.")
    ff("-f", "lavfi", "-i", "mandelbrot=s=1600x900", "-frames:v", "1", tmp / "still.jpg")
    ff("-f", "lavfi", "-i", "sine=f=330:d=30", tmp / "music.wav")
    plan = {"output": {"path": "out.mp4", "size": [720, 1280], "fps": 25, "target": "shorts"},
            "clips": [{"src": "c0.mp4", "in": 0, "out": 3, "titles": [{"text": "ที่นี่ **น้ำท่วม**", "start": 0.2, "end": 2.5, "anim": "pop", "underline": True}]},
                      {"src": "c1.mp4", "in": 0.5, "out": 3.5},
                      {"src": "c2.mp4", "in": 0, "out": 3, "transition": {"type": "fade", "dur": 0.4},
                       "broll": [{"src": "still.jpg", "start": 0.5, "end": 2.0}]},
                      {"card": {"text": "Card **text**"}, "in": 0, "out": 2.0, "transition": {"type": "fade", "dur": 0.3}}],
            "headline": {"text": "Headline\n**two lines**"}, "audio": [{"src": "music.wav", "role": "music", "start": 0}],
            "music_mix": {"gap_db": -8, "under_db": -20}}
    json.dump(plan, open(tmp / "plan.json", "w", encoding="utf-8"), ensure_ascii=False)
    r = subprocess.run(PY + [SC / "edit_plan.py", tmp / "plan.json"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    tl = json.load(open(tmp / "out.mp4.timeline.json"))["duration"]
    d = float(probe(tmp / "out.mp4")["format"]["duration"]); assert abs(d - tl) < 0.25, (d, tl)
    v = probe(tmp / "out.mp4", "stream=pix_fmt,color_range")["streams"][0]; assert v["pix_fmt"] == "yuv420p", v
    qa = json.load(open(tmp / "out.mp4.qa.json"))
    fails = [x for x in qa["results"] if x["status"] == "FAIL"]; assert not fails, fails
    loud = next(x for x in qa["results"] if x["check"] == "loudness"); assert loud["status"] == "PASS", loud


@test
def qa_flags_full_range(tmp):
    """qa_check.py warns about full-range (yuvj420p) video, the bug every early render had."""
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=2", "-f", "lavfi", "-i", "sine=d=2", "-pix_fmt", "yuvj420p", "-c:v", "libx264", "-c:a", "aac", "-shortest", tmp / "full.mp4")
    out = subprocess.run(PY + [SC / "qa_check.py", tmp / "full.mp4"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    assert "full-range" in out, out


@test
def thai_marks_drawn(tmp):
    """libass with the bundled font draws the tone mark on an upper vowel: 'ที่' must differ from 'ที'."""
    from edit_plan import titles_ass, ass_fontsdir
    imgs = []
    for k, txt in enumerate(("ที่", "ที")):
        titles_ass([{"text": txt, "start": 0, "end": 2, "pos": "center", "size": 300}], 400, 400, tmp / f"t{k}.ass")
        ff("-f", "lavfi", "-i", "color=black:s=400x400:d=2", "-ss", "1", "-vf", f"ass='{(tmp / f't{k}.ass').as_posix().replace(':', chr(92) + ':')}'{ass_fontsdir()}",
           "-frames:v", "1", "-pix_fmt", "gray", "-f", "rawvideo", tmp / f"t{k}.raw")
        imgs.append((tmp / f"t{k}.raw").read_bytes())
    diff = sum(1 for a, b in zip(*imgs) if abs(a - b) > 60); assert diff > 300, f"only {diff} pixels differ: tone mark missing"


@test
def word_captions_fit(tmp):
    """word_captions.py --style stack --type mix: no line runs off a 9:16 frame (the 'dangerous' overflow)."""
    make_clip(tmp / "s.mp4", 6, speech="x")
    words = {"words": [{"text": t, "start": 0.3 + i * 0.45, "end": 0.3 + i * 0.45 + 0.4, "type": "word"}
                       for i, t in enumerate("Some extraordinarily dangerous incomprehensible places nevertheless".split())]}
    json.dump(words, open(tmp / "w.json", "w"))
    plan = {"output": {"size": [1080, 1920]}, "clips": [{"src": "s.mp4", "in": 0, "out": 6}]}
    json.dump(plan, open(tmp / "p.json", "w"))
    subprocess.run(PY + [SC / "word_captions.py", tmp / "w.json", tmp / "p.json", tmp / "c.ass", "--style", "stack", "--type", "mix"], check=True, capture_output=True)
    from word_captions import width_font
    from fonts import font
    for line in open(tmp / "c.ass", encoding="utf-8"):
        if not line.startswith("Dialogue"): continue
        x = int(re.search(r"\\pos\((-?\d+),", line)[1]); fs = int(re.search(r"\\fs(\d+)", line)[1]); txt = line.rsplit("}", 1)[1].strip()
        path = font("serif_italic")[1] if "\\fn" in line else font("sans")[1]
        assert x >= -2 and x + width_font(txt, fs, path) <= 1080 + 4, (x, fs, txt)


@test
def align_script_lines(tmp):
    """align_script.py finds every script line in a character-timed transcript and keeps them in order."""
    lines = ["the first line here", "and then a second one", "finally the third"]
    t, words = 0.5, []
    for ln in lines:
        for ch in ln.replace(" ", ""):
            words.append({"text": ch, "start": round(t, 2), "end": round(t + 0.08, 2), "type": "word"}); t += 0.08
        t += 0.6
    json.dump({"words": words}, open(tmp / "tr.json", "w")); json.dump(lines, open(tmp / "lines.json", "w"))
    subprocess.run(PY + [SC / "align_script.py", tmp / "tr.json", tmp / "lines.json", tmp / "al"], check=True, capture_output=True)
    tm = json.load(open(tmp / "al_timing.json", encoding="utf-8"))
    assert len(tm) == 3 and all(a["end"] <= b["start"] for a, b in zip(tm, tm[1:])), tm


@test
def screen_focus_zoom(tmp):
    """screen_focus.py: a box that moves in the top-right quarter -> a crop there; a still stretch -> fast-forward."""
    ff("-f", "lavfi", "-i", "color=c=0xe8e8e8:s=1280x720:d=12:r=25",
       "-vf", "drawbox=x='900+40*sin(t*3)':y=120:w=160:h=90:color=red:t=fill:enable='lt(t,5)'", "-c:v", "libx264", "-pix_fmt", "yuv420p", tmp / "scr.mp4")
    subprocess.run(PY + [SC / "screen_focus.py", tmp / "scr.mp4", tmp / "f"], check=True, capture_output=True)
    clips = json.load(open(tmp / "f_clips.json"))["clips"]
    act = [c for c in clips if c["speed"] == 1.0]; idle = [c for c in clips if c["speed"] > 1.0]
    assert act and idle, clips
    x, y, w, h = act[0]["crop"]; assert x + w / 2 > 640 and y + h / 2 < 360, act[0]["crop"]


@test
def find_shots_prefers_sharp(tmp):
    """find_shots.py scores a sharp, steady moment above a blurred one."""
    ff("-f", "lavfi", "-i", "testsrc2=s=640x360:d=6:r=25", "-vf", "gblur=sigma=12:enable='gte(t,3)'",
       "-c:v", "libx264", "-pix_fmt", "yuv420p", tmp / "sh.mp4")
    subprocess.run(PY + [SC / "find_shots.py", tmp / "sh.mp4", tmp / "shots", "--window", "1.5", "--min", "1"], check=True, capture_output=True)
    shots = json.load(open(tmp / "shots.json"))["shots"]
    early = max(s["score"] for s in shots if s["end"] <= 3.1); late = max(s["score"] for s in shots if s["start"] >= 3)
    assert early > late, (early, late)


@test
def safe_zones_flag(tmp):
    """safe_zones.py flags a title under the apps' top tabs and passes the vertical defaults (headline below them)."""
    from edit_plan import titles_ass
    from safe_zones import ass_boxes, check
    titles_ass([{"text": "Top title", "start": 0, "end": 2, "pos": "top", "margin": 0.02, "size": 80}], 1080, 1920, tmp / "bad.ass")
    titles_ass([{"text": "Top title", "start": 0, "end": 2, "pos": "top", "margin": 0.085, "size": 80}], 1080, 1920, tmp / "ok.ass")
    assert check(ass_boxes(tmp / "bad.ass")), "title in the top tabs was not flagged"
    assert not check(ass_boxes(tmp / "ok.ass")), check(ass_boxes(tmp / "ok.ass"))


@test
def picker_skips_host_and_overlap(tmp):
    """podcast_short.pick_segments: no host question, no sign-off, several picks that never overlap."""
    from podcast_short import pick_segments
    from word_captions import STOP
    talk = []
    def say(text, t):
        for w in text.split():
            talk.append({"text": w, "start": round(t, 2), "end": round(t + 0.3, 2), "type": "word"}); t += 0.35
        return t + 0.8
    t = 0.0
    for k in range(6):
        t = say(f"What happens to rivers number {k}?", t)                              # host question
        for j in range(5): t = say(f"Floodwater{k} erodes riverbanks{j} quickly during monsoon{k} season{j}.", t)
    t = say("Thank you so much for joining us today.", t)
    picks = pick_segments(talk, 12, STOP, (), count=3)
    assert len(picks) >= 2, picks
    flat = [x for p in picks for x in p]
    assert not any(x[2].endswith("?") or "Thank you" in x[2] for x in flat), flat
    spans = sorted((p[0][0], p[-1][1]) for p in picks)
    assert all(a[1] < b[0] for a, b in zip(spans, spans[1:])), spans


@test
def thai_word_stack(tmp):
    """thai_words.py cuts Scribe-style Thai characters into timed words; the word stack keeps a split name (อู่ | ทอง)
    on one line and nothing runs off a 9:16 frame. Skipped when pythainlp is not installed."""
    try:
        import pythainlp  # noqa: F401
    except ImportError:
        print("      (pythainlp not installed: skipped)"); return
    text = "ที่นี่คือวัดมหาธาตุ พระเจ้าอู่ทองสถาปนากรุงศรีอยุธยา"
    chars, t = [], 0.3
    for c in text:
        if c == " ": t += 0.6; continue
        chars.append({"text": c, "start": round(t, 3), "end": round(t + 0.07, 3), "type": "word"}); t += 0.08
    json.dump({"words": chars}, open(tmp / "scribe.json", "w", encoding="utf-8"), ensure_ascii=False)
    subprocess.run(PY + [SC / "thai_words.py", tmp / "scribe.json", tmp / "w.json"], check=True, capture_output=True)
    words = json.load(open(tmp / "w.json", encoding="utf-8"))["words"]
    assert "".join(w["text"] for w in words) == text.replace(" ", ""), [w["text"] for w in words]
    assert all(b["start"] >= a["start"] for a, b in zip(words, words[1:])), words
    make_clip(tmp / "s.mp4", 6, speech="x")
    json.dump({"output": {"size": [1080, 1920]}, "clips": [{"src": "s.mp4", "in": 0, "out": 6}]}, open(tmp / "p.json", "w"))
    subprocess.run(PY + [SC / "word_captions.py", tmp / "w.json", tmp / "p.json", tmp / "c.ass", "--style", "stack", "--type", "mix"], check=True, capture_output=True)
    from word_captions import width_font
    from fonts import font
    ys = {}
    for line in open(tmp / "c.ass", encoding="utf-8"):
        if not line.startswith("Dialogue"): continue
        x, y = map(int, re.search(r"\\pos\((-?\d+),(-?\d+)\)", line).groups()); fs = int(re.search(r"\\fs(\d+)", line)[1])
        txt = line.rsplit("}", 1)[1].strip(); ys[txt] = (line.split(",")[1], y)
        assert x >= -2 and x + width_font(txt, fs, font("sans")[1]) <= 1080 + 4, (x, fs, txt)
    if "อู่" in ys and "ทอง" in ys: assert ys["อู่"][1] == ys["ทอง"][1], ys     # same line (each word appears as it is said)


@test
def speaker_turns_follow_mouth(tmp):
    """reframe.speaker_turns: two synthetic faces, the left one's mouth moves while it asks, then the right one's."""
    import numpy as np
    from reframe import faces, frames, speaker_turns
    W, H, fps = 640, 360, 30; rng = np.random.default_rng(1)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
                          "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "12", str(tmp / "two.mp4")], stdin=subprocess.PIPE)
    for k in range(8 * fps):
        f = np.full((H, W, 3), (40, 60, 120), np.uint8)
        for who, cx in ((0, 170), (1, 470)):
            f[80:210, cx - 35:cx + 35] = (220, 170, 140)                        # face and neck, skin colour
            if (who == 0) == (k / fps < 4.0):                                     # talking: the jaw area changes
                f[125:170, cx - 25:cx + 25] = (220, 170, 140) - rng.integers(0, 90, 3)
        p.stdin.write(f.tobytes())
    p.stdin.close(); p.wait()
    ws = []
    for text, t in (("Do you like rivers?", 0.5), ("Yes I love rivers very much.", 4.3)):
        for w in text.split(): ws.append({"text": w, "start": t, "end": t + 0.5}); t += 0.6
    fcs = faces(frames(str(tmp / "two.mp4"), 0, 8, 3, 192, 108), W, H)
    assert fcs and fcs[0][0] < W / 2 < fcs[1][0], fcs
    turns = speaker_turns(str(tmp / "two.mp4"), 0, 8, fcs, W, H, ws)
    assert [x[2] for x in turns] == [0, 1] and 3.0 < turns[0][1] < 4.6, turns


def two_clip_plan(tmp, extra=None):
    for k, c in enumerate(("testsrc2", "smptebars")): make_clip(tmp / f"c{k}.mp4", 3, c, speech="Testing the sound.")
    plan = {"output": {"path": "out.mp4", "size": [640, 360], "fps": 25, "target": "youtube"},
            "clips": [{"src": "c0.mp4", "in": 0, "out": 3, "titles": [{"text": "Hello", "start": 0.2, "end": 2}]},
                      {"src": "c1.mp4", "in": 0, "out": 3, "transition": {"type": "fade", "dur": 0.5}}], "audio": []}
    plan.update(extra or {}); json.dump(plan, open(tmp / "plan.json", "w", encoding="utf-8"))
    return tmp / "plan.json"


@test
def sound_design_places_effects(tmp):
    """make_sfx.py kit + sound_design.py: a pop on the title, a whoosh on the 0.5 s fade, levels set against speech;
    the render still matches its timeline."""
    pp = two_clip_plan(tmp)
    r = subprocess.run(PY + [SC / "sound_design.py", pp], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-500:]
    sd = [a for a in json.load(open(pp, encoding="utf-8"))["audio"] if a.get("sd")]
    kinds = {pathlib.Path(a["src"]).stem for a in sd}
    assert {"pop", "whoosh"} <= kinds and all("rel_db" in a for a in sd), sd
    w = [a for a in sd if pathlib.Path(a["src"]).stem == "whoosh"][0]; assert 2.3 < w["start"] + 0.3 < 2.9, w   # peaks in the fade
    r = subprocess.run(PY + [SC / "edit_plan.py", pp, "--no-qa"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-500:]
    assert abs(float(probe(tmp / "out.mp4")["format"]["duration"]) - 5.5) < 0.3


@test
def brand_kit_render(tmp):
    """brand.json: logo drawn in its corner, end card added, grade and accent applied without breaking the render."""
    from PIL import Image
    Image.new("RGBA", (200, 200), (255, 0, 0, 255)).save(tmp / "logo.png")
    json.dump({"accent": "2EC4B6", "grade": "warm", "logo": {"src": "logo.png", "pos": "top-left", "size": 0.15, "opacity": 1.0},
               "end_card": {"text": "Bye **now**", "sub": "@test", "dur": 1.5}}, open(tmp / "brand.json", "w"))
    pp = two_clip_plan(tmp, {"brand": "brand.json"})
    r = subprocess.run(PY + [SC / "edit_plan.py", pp, "--no-qa"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-500:]
    assert abs(float(probe(tmp / "out.mp4")["format"]["duration"]) - (5.5 + 1.5 - 0.3)) < 0.3      # end card with its fade
    ff("-ss", "1", "-i", tmp / "out.mp4", "-frames:v", "1", "-vf", "crop=60:40:30:25", "-pix_fmt", "rgb24", "-f", "rawvideo", tmp / "lg.raw")
    px = (tmp / "lg.raw").read_bytes(); r_, g_ = sum(px[0::3]) / (len(px) / 3), sum(px[1::3]) / (len(px) / 3)
    assert r_ > 180 and g_ < 90, (r_, g_)                                                           # the red logo is there


@test
def music_mood_pick(tmp):
    """music_mood.py: listener tags win; sad words pick the sad track, an excited music-led ad the playful one; Thai words count."""
    import music_mood
    assert music_mood.clip_mood([{"text": "สงครามและการล้อมเมือง", "start": 0, "end": 2}])[2].get("epic")
    d = tmp / "lib"; d.mkdir()
    ff("-f", "lavfi", "-i", "sine=f=220:d=12", d / "slow.wav"); ff("-f", "lavfi", "-i", "sine=f=880:d=12", d / "fast.wav")
    subprocess.run(PY + [SC / "music_mood.py", "scan", d], check=True, capture_output=True)
    lib = json.load(open(d / "library.json"))
    for t in lib["tracks"]: t["moods"] = ["sad"] if t["file"] == "slow.wav" else ["playful"]
    json.dump(lib, open(d / "library.json", "w"))
    make_clip(tmp / "s.mp4", 4, speech="x")
    words = [{"text": t, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, t in enumerate("we lost everything and she died in grief".split())]
    json.dump({"words": words}, open(tmp / "w.json", "w"))
    json.dump({"output": {"path": "o.mp4"}, "clips": [{"src": "s.mp4", "in": 0, "out": 4}], "audio": []}, open(tmp / "p.json", "w"))
    subprocess.run(PY + [SC / "music_mood.py", "pick", tmp / "p.json", "--library", d, "--words", tmp / "w.json", "--apply"], check=True, capture_output=True)
    assert json.load(open(tmp / "p.json"))["audio"][0]["src"].endswith("slow.wav")
    json.dump({"output": {"path": "o.mp4"}, "clips": [{"src": "s.mp4", "in": 0, "out": 4, "titles": [{"text": "So fun! We won!", "start": 0, "end": 2}]}],
               "audio": []}, open(tmp / "p2.json", "w"))
    subprocess.run(PY + [SC / "music_mood.py", "pick", tmp / "p2.json", "--library", d, "--no-talk", "--apply"], check=True, capture_output=True)
    assert json.load(open(tmp / "p2.json"))["audio"][0]["src"].endswith("fast.wav")


@test
def sound_catalog_balanced(tmp):
    """assets/sound_catalog.json: every item has a licence and a credit; the balanced set covers every feel, no Holiday/Polka."""
    import sound_library
    cat = json.load(open(sound_library.CATALOG, encoding="utf-8"))
    assert len(cat) > 1500 and all(e.get("license") and e.get("credit") and e.get("url") for e in cat)
    assert not [e for e in cat if e["source"] == "commons" and any(x in e["license"].upper() for x in ("SA", "NC", "ND"))]
    pick = sound_library.balanced(cat, 400)
    assert len(pick) == 400 and not [e for e in pick if e["genre"] in ("Holiday", "Polka")]
    feels = {f for e in cat if e["source"] == "incompetech" for f in e.get("feels", [])} - {"Ren Faire", "Medieval"}
    got = {f for e in pick for f in e.get("feels", [])}
    assert feels <= got, feels - got


@test
def music_by_picture_avoids_comedy(tmp):
    """music_mood.picture_score: for a fast city edit a Bright/Grooving electronica track beats a Humorous one and an Eerie one."""
    import music_mood
    tg = {"feels": {"Bright": 1.5, "Grooving": 2.2, "Uplifting": 1.0, "Driving": 1.5}, "genres": {"Electronica": 1, "Funk": 1}, "bpm": (100, 135), "pace": 0.9}
    good = {"feels": ["Bright", "Grooving"], "genre": "Electronica", "bpm": 118}
    funny = {"feels": ["Bright", "Humorous", "Bouncy"], "genre": "Unclassifiable", "bpm": 120}
    eerie = {"feels": ["Eerie", "Mysterious"], "genre": "Horror", "bpm": 110}
    assert music_mood.picture_score(good, tg) > music_mood.picture_score(funny, tg) > music_mood.picture_score(eerie, tg)


@test
def place_sound_moments_and_replace(tmp):
    """place_sound.py: steady surf-like noise becomes a moment (music ducks), a silent clip is muted; music_mix set."""
    import numpy as np, wave
    def wav(path, x):
        with wave.open(str(path), "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    rng = np.random.default_rng(3); t = np.arange(16000 * 4) / 16000
    surf = rng.standard_normal(len(t)) * 0.12 * (0.8 + 0.2 * np.sin(2 * np.pi * 0.15 * t))
    wav(tmp / "surf.wav", surf); wav(tmp / "silent.wav", np.zeros(len(t)))
    for name in ("surf", "silent"):
        ff("-f", "lavfi", "-i", "color=c=0x2060a0:s=320x180:d=4", "-i", tmp / f"{name}.wav", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", tmp / f"{name}.mp4")
    json.dump({"output": {"path": "o.mp4", "size": [320, 180]}, "clips": [{"src": "surf.mp4", "in": 0, "out": 3.5}, {"src": "silent.mp4", "in": 0, "out": 3.5}],
               "audio": []}, open(tmp / "p.json", "w"))
    r = subprocess.run(PY + [SC / "place_sound.py", tmp / "p.json", "--library", tmp / "nolib"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-400:]
    p = json.load(open(tmp / "p.json")); c0, c1 = p["clips"]
    assert c1["volume_db"] == -90, c1                                          # nothing to hear: muted
    assert p["music_mix"]["under_db"] < p["music_mix"]["gap_db"]
    if "MOMENT" in r.stdout: assert c0.get("speech") and c0.get("talk"), c0  # the surf is a moment when the classifier hears water


@test
def yamnet_tags_speech_and_music(tmp):
    """audio_tags.py (YAMNet): a tone chord reads as music-ish, white noise not as speech. Skipped without the model."""
    import audio_tags, numpy as np
    if not (audio_tags.MODEL_DIR / "yamnet_onnx" / "yamnet.onnx").exists(): print("      (YAMNet model not installed: skipped)"); return
    t = np.arange(16000 * 3) / 16000
    chord = sum(np.sin(2 * np.pi * f * t) for f in (261.6, 329.6, 392.0)) * 0.15 * (1 + 0.3 * np.sin(2 * np.pi * 2 * t))
    sc, labels = audio_tags.scores(chord.astype(np.float32)); g = audio_tags.groups(sc, labels)
    assert g["music"] > g["people"], g
    noise = np.random.default_rng(1).standard_normal(16000 * 3).astype(np.float32) * 0.1
    sc, labels = audio_tags.scores(noise); g = audio_tags.groups(sc, labels)
    assert g["people"] < 0.3, g


@test
def ad_concept_board(tmp):
    """ad_concept.py: a yuzu can leads with the fruit split and pays off with the can opening; a filled bar leads with
    its own snap; a bottle gets the cap twist and never a can-only shot; unbuilt ideas stay marked TO BUILD; every shot
    named in the catalogue exists in blender_product_ad.py."""
    import ad_concept
    c = ad_concept.concept("yuzu sparkling can", flavours=3)
    beats = {b[0]: b[1] for b in c["board"]}
    assert c["product"] == "can" and c["fruit"] == "yuzu", c
    assert beats["hook"] == "split" and beats["payoff"] == "open" and "trio" in c["shots"], beats
    c = ad_concept.concept("caramel chocolate bar", family="luxury")
    assert c["board"][0][1] == "snap", c["board"][0]                             # the product's own action leads
    c = ad_concept.concept("green tea bottle")
    assert "twist" in c["shots"] and not {"open", "toppop", "drops"} & set(c["shots"]), c["shots"]   # no can-only shots on a bottle
    c = ad_concept.concept("lip balm stick")
    assert c["board"][0][1].startswith("TO BUILD"), c["board"][0]                # unbuilt ideas stay visible
    src = (SC / "blender_product_ad.py").read_text(encoding="utf-8")
    lens = set(re.findall(r'"(\w+)": \d+', re.search(r"LEN = \{[^}]*\}", src).group(0)))
    named = {x["shot"] for g in ("products", "ingredients") for e in ad_concept.CAT[g].values()
             for x in e.get("actions", []) + e.get("events", []) if x.get("shot")}
    assert named <= lens, named - lens


@test
def sfx_kit_levels(tmp):
    """Every synthesised effect (incl. slash and splash) has a level, a peak time and a rank in sound_design.py."""
    import make_sfx, sound_design
    for k in make_sfx.KIT: assert k in sound_design.LEVEL and k in sound_design.PEAK and k in sound_design.RANK, k
    p = make_sfx.make(tmp / "kit", only=["slash", "splash"])
    assert all(v.stat().st_size > 10000 for v in p.values()), p


@test
def ad_pipeline_beats_and_gates(tmp):
    """ad_pipeline.py: every shot lasts whole beats, each physical event lands on a beat (its sound placed on it),
    titles stay inside their shot and leave before the end card, the music starts on its first beat; --approve is
    refused until a stage has been shown."""
    import ad_pipeline as AP
    per, fps = 0.5, 24
    st = {"stage": "board", "approved": [], "fps": fps, "size": "1080x1920", "brief": "fresh",
          "product": {"label": "x.png", "set": ["#FFC21C", "#FF8A1E"]},
          "music": {"src": str(tmp / "m.wav"), "in": 1.25, "bpm": 120, "period": per},
          "card": {"text": "Hi", "bg": "0xFF9A1E", "beats": 3},
          "shots": [{"id": "s1_split", "type": "split", "beats": 5, "event_beat": 2, "title": {"text": "One", "at": 0.3},
                     "sfx": [{"sound": "slash", "at": "event", "offset": 0.0, "rel_db": -11}]},
                    {"id": "s2_hero_low", "type": "hero_low", "beats": 4, "title": [{"text": "Two", "at": 0.2}, {"text": "45 THB", "at": 1.0}], "sfx": []}]}
    sp = AP.derived(st)
    for s, x in zip(st["shots"], sp): assert abs(x["base"] / fps - s["beats"] * per) <= 1 / fps, x
    assert abs((sp[0]["event"] - 1) / fps - 2 * per) <= 1 / fps, sp[0]
    fd = tmp / "f"; fd.mkdir()
    for x in sp: ff("-f", "lavfi", "-i", f"color=c=orange:s=108x192:r={fps}:d={x['frames'] / fps}", "-pix_fmt", "yuv420p", fd / f"{x['id']}.mp4")
    ff("-f", "lavfi", "-i", "sine=f=440:d=12", tmp / "m.wav")
    plan = json.load(open(AP.make_plan(st, tmp, fd, "o.mp4"), encoding="utf-8"))
    slash = next(e for e in plan["audio"] if e["src"].endswith("slash.wav"))
    assert abs(slash["start"] - 2 * per) <= 1 / fps, slash
    music = next(e for e in plan["audio"] if e.get("role") == "music"); assert music["in"] == 1.25
    shot_end = sum(x["frames"] for x in sp) / fps
    assert len(plan["titles"]) == 3 and all(t["end"] <= shot_end - 0.35 + 1e-6 for t in plan["titles"]), plan["titles"]
    json.dump(st, open(tmp / "shots.json", "w"))
    r = subprocess.run(PY + [SC / "ad_pipeline.py", "run", tmp, "--approve"], capture_output=True, text=True)
    assert r.returncode != 0 and "nothing shown yet" in (r.stderr + r.stdout), r.stderr


@test
def product_from_photo_round_trip(tmp):
    """product_from_photo.py on a drawn bottle (known profile, cap, front mark) and a drawn box: the shape guess, the
    radius profile in mm, where the cap starts, and the unwrapped texture keeps the front mark in its middle."""
    import numpy as np
    from PIL import Image, ImageDraw
    W, H = 600, 1300; im = Image.new("RGB", (W, H), (255, 255, 255)); d = ImageDraw.Draw(im)
    cx = W // 2; body_r, neck_r, cap_r = 150, 60, 72                       # px; height 1200 px = 240 mm -> 0.2 mm/px
    d.rectangle([cx - body_r, 400, cx + body_r, 1250], fill=(120, 200, 90))    # body
    d.polygon([(cx - body_r, 400), (cx + body_r, 400), (cx + neck_r, 230), (cx - neck_r, 230)], fill=(120, 200, 90))
    d.rectangle([cx - neck_r, 160, cx + neck_r, 230], fill=(200, 230, 200))   # neck
    d.rectangle([cx - cap_r, 50, cx + cap_r, 160], fill=(30, 110, 40))        # cap
    d.rectangle([cx - 30, 700, cx + 30, 900], fill=(220, 20, 20))             # a red mark on the front
    im.save(tmp / "bottle.png")
    r = subprocess.run(PY + [SC / "product_from_photo.py", tmp / "bottle.png", "--out", tmp / "b", "--height-mm", "240"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]
    p = json.load(open(tmp / "b" / "product.json"))
    assert p["shape"] == "bottle", p["shape"]
    mid = [rz for rz in p["profile"] if 100 < rz[1] < 140]
    assert mid and all(abs(rr - 30) < 1.5 for rr, _ in mid), mid[:3]              # 150 px x 0.2 mm = 30 mm radius
    assert abs(p["cap_from_mm"] - (1250 - 160) * 0.2) < 4, p["cap_from_mm"]
    tex = np.asarray(Image.open(tmp / "b" / p["texture"]).convert("RGB")).astype(int); th, tw = tex.shape[:2]
    centre = tex[int(th * (1 - 450 / 1200)), tw // 2]; side = tex[int(th * (1 - 450 / 1200)), int(tw * 0.62)]
    assert centre[0] > 180 and centre[1] < 80 and side[1] > 150, (centre, side)  # red in the middle, green beside it
    box = Image.new("RGB", (800, 1000), (250, 250, 250)); ImageDraw.Draw(box).rectangle([200, 150, 600, 850], fill=(40, 90, 160)); box.save(tmp / "box.png")
    subprocess.run(PY + [SC / "product_from_photo.py", tmp / "box.png", "--out", tmp / "x"], check=True, capture_output=True)
    q = json.load(open(tmp / "x" / "product.json")); assert q["shape"] == "box" and abs(q["size_mm"][0] / q["size_mm"][1] - 400 / 700) < 0.03, q


@test
def ad_design_rules(tmp):
    """ad_design.py: no two neighbouring shots share a camera move or a shot size, every ad gets a signature move, only
    moves that suit each shot's action, no transition into a shot whose event comes in its first 0.4 s, variants
    differ; with transitions the next shot still starts on its beat (the outgoing shot is extended)."""
    import ad_design as AD, ad_pipeline as AP
    types = ["split", "drops", "toppop", "zerog", "hero_low"]
    for fam in ("fresh", "luxury", "tech", "clean"):
        seen = set()
        for v in range(1, 6):
            st = {"brief": fam, "fps": 24, "music": {"period": 0.5}, "shots": [{"id": f"s{i}_{t}", "type": t, "beats": 5} for i, t in enumerate(types)]}
            st["shots"][1]["event_beat"] = 0                                 # an event right at the start
            AD.design(st, v); sh = st["shots"]
            for a, b in zip(sh, sh[1:]):
                assert a["move"] != b["move"] or a["move"] == "native", (fam, v, a["move"])
            assert any(AD.MOVES[x["move"]]["sig"] for x in sh), (fam, v)
            assert all(x["move"] in AD.ALLOWED[x["type"]] for x in sh)
            assert sh[1]["transition_in"] == "cut", sh[1]
            seen.add(tuple(x["move"] for x in sh))
        assert len(seen) >= 2, (fam, seen)                                   # variants really vary
    st = {"brief": "fresh", "fps": 24, "music": {"period": 0.5, "src": "m.wav", "in": 0}, "size": "1080x1920", "card": {"text": "x"},
          "shots": [{"id": "a", "type": "hero", "beats": 4, "transition_in": "cut"}, {"id": "b", "type": "split", "beats": 6, "event_beat": 2,
                     "transition_in": "zoom", "sfx": [{"sound": "slash", "at": "event", "offset": 0, "rel_db": -11}]}]}
    sp = AP.derived(st)
    assert sp[0]["frames"] - sp[0]["base"] == round(0.3 * 24), sp[0]         # extended by the zoom transition
    fd = tmp / "f"; fd.mkdir()
    for x in sp: ff("-f", "lavfi", "-i", f"color=c=orange:s=108x192:r=24:d={x['frames'] / 24}", "-pix_fmt", "yuv420p", fd / f"{x['id']}.mp4")
    ff("-f", "lavfi", "-i", "sine=f=440:d=12", tmp / "m.wav")
    plan = json.load(open(AP.make_plan(st, tmp, fd, "o.mp4"), encoding="utf-8"))
    assert plan["clips"][1]["transition"]["type"] == "zoomin"
    slash = next(e for e in plan["audio"] if e["src"].endswith("slash.wav"))
    assert abs(slash["start"] - (4 * 0.5 + 2 * 0.5)) <= 1 / 24, slash          # shot b starts on beat 4, its event on beat 2 after


@test
def ad_finish_keeps_colour(tmp):
    """The finishing pass (glow, fringe, vignette, grain, grade) keeps the product's colour: an orange stays orange in
    every mood family (a screen blend done in YUV turned it pink), and the centre keeps its brightness."""
    import colorsys
    import ad_pipeline as AP
    from PIL import Image
    Image.new("RGB", (432, 768), (230, 120, 30)).save(tmp / "o.png")
    for fam in AP.FINISH:
        ff("-i", tmp / "o.png", "-filter_complex", AP.finish_filter(fam, 432), "-frames:v", 1, tmp / f"{fam}.png")
        r, g, b = Image.open(tmp / f"{fam}.png").convert("RGB").resize((1, 1), box=(166, 334, 266, 434)).getpixel((0, 0))
        h, l, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        assert 0.04 < h < 0.11 and sat > 0.5 and 0.3 < l < 0.7, (fam, (r, g, b), round(h, 3))


@test
def ad_sells_structure_abcd(tmp):
    """1.14: the performance structure puts benefit, proof, demo, name + offer + a mid call to action on the right shots;
    the first voiceover line says the brand; the ABCD check flags a missing voiceover and passes the rest; callouts
    go where there is room beside the product (or nowhere); the sonic logo is the same for the same brand."""
    import numpy as np, ad_pipeline as AP, make_sfx
    shots = [{"id": f"s{i}", "type": t, "beats": b} for i, (t, b) in enumerate([("split", 6), ("drops", 4), ("zerog", 4), ("open", 4), ("hero_low", 6)])]
    shots[0]["event_beat"] = 2
    copy = {"hook": "Sunshine", "benefit": "real yuzu", "proof": "4.8/5 rating", "demo": "crack it", "name": "LUMA | YUZU", "offer": "2 for 79",
            "cta": "Order now", "callouts": ["real yuzu", "zero sugar"]}
    AP.copy_titles(shots, ["hook", "detail", "detail", "payoff", "hero"], copy, "fresh", "performance")
    roles = [s["role"] for s in shots]; assert roles == ["hook", "benefit", "proof", "demo", "name"], roles
    hero = AP.titles_of(shots[-1]); assert [t["text"] for t in hero] == ["LUMA | YUZU", "2 for 79", "Order now"] and shots[-1]["callouts"], hero
    st = {"fps": 24, "music": {"period": 0.5, "src": str(tmp / "m.wav"), "in": 0}, "size": "1080x1920", "card": {"text": "Order now", "beats": 3},
          "shots": shots, "brief": "fresh", "structure": "performance", "copy": copy, "brand_name": "LUMA", "vo": {"lines": {"hook": "Sunshine in a can."}}}
    assert AP.vo_lines(st)[0][1].startswith("LUMA."), AP.vo_lines(st)
    st["vo"] = None; rows = {r[1].strip(): r[0] for r in AP.abcd(st, tmp)}
    assert rows["B  brand said by 5 s (voiceover)"] == "WARN" and rows["A  product on screen by 3 s"] == "PASS", rows
    assert rows["D  call to action before the card too"] == "PASS" and rows["S  proof on screen"] == "PASS", rows
    fd = tmp / "fr"; fd.mkdir()
    wide = {"1": {"left": [0.2, 0.6, 5], "right": [0.8, 0.6, 5], "label": [0.5, 0.6, 5]}}                 # fills the frame: no room
    roomy = {"1": {"left": [0.4, 0.5, 5], "right": [0.6, 0.5, 5], "label": [0.5, 0.5, 5]}}
    for s, an in zip(shots, [roomy, wide, wide, wide, wide]): json.dump(an, open(fd / f"{s['id']}_anchors.json", "w"))
    sp = AP.derived(st); starts = list(np.cumsum([0] + [x["base"] / 24 for x in sp])[:-1])
    assert AP.place_callouts(st, sp, starts, fd) == []                      # the only roomy shot is the hook: skipped
    json.dump(roomy, open(fd / "s3_anchors.json", "w")); co = AP.place_callouts(st, sp, starts, fd)
    assert len(co) == 2 and co[0]["side"] == "left" and abs(co[0]["start"] - (starts[3] + sp[3]["base"] / 24 * 0.45)) < 0.01, co
    a1, a2 = make_sfx.sonic_logo("LUMA", "fresh"), make_sfx.sonic_logo("LUMA", "fresh")
    assert np.allclose(a1, a2) and not np.allclose(a1, make_sfx.sonic_logo("VOLT", "fresh"))


def blender_exe():
    import glob, os, shutil
    return os.environ.get("BLENDER") or shutil.which("blender") or next(iter(sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender *\blender.exe"))[::-1]), None)


@test
def blender_fruit_cut_faces(tmp):
    """Real 3D fruit: after the split the cut faces show bright flesh, not black (a generated image loses its pixels if
    its colour space is set after writing). Skipped without Blender."""
    exe = blender_exe()
    if not exe: print("  (skipped: no Blender)"); return
    ff("-f", "lavfi", "-i", "color=c=orange:s=256x256", "-frames:v", "1", tmp / "label.png")
    subprocess.run([exe, "-b", "--python-exit-code", "1", "-P", SC / "blender_product_ad.py", "--", "--label", tmp / "label.png", "--fruit", "yuzu", "--out", tmp / "o",
                    "--shots", "split", "--still", "--frame", "75", "--size", "270x480", "--samples", "4"], check=True, capture_output=True, timeout=600)
    ff("-i", tmp / "o" / "split_still.png", "-vf", "crop=50:120:0:150,scale=1:1", "-pix_fmt", "rgb24", "-f", "rawvideo", tmp / "px.raw")
    r, g, b = (tmp / "px.raw").read_bytes()[:3]
    assert r > 150 and g > 110, (r, g, b)                                     # left half's cut face: yellow flesh


@test
def blender_cut_and_crown(tmp):
    """1.15: the split shows a blade, a seam of light that is gone once the halves part, juice films hooked between the
    faces; the camera shakes on the cut; the set is one seamless sweep with a contact shadow; the crown splash rises
    and falls back into a pool while the can settles into the liquid. Skipped without Blender."""
    exe = blender_exe()
    if not exe: print("  (skipped: no Blender)"); return
    ff("-f", "lavfi", "-i", "color=c=orange:s=256x128", "-frames:v", "1", tmp / "label.png")
    base = ["--label", str(tmp / "label.png"), "--fruit", "yuzu", "--out", str(tmp / "o"), "--still", "--frame", "1", "--size", "54x96", "--samples", "1"]
    code = (f"import sys, bpy; sys.path.insert(0, r'{SC}')\n"
            f"src = open(r'{SC / 'blender_product_ad.py'}', encoding='utf-8').read()\n"
            f"sys.argv = ['b', '--'] + {base!r} + ['--shots', 'split']; exec(src, {{'__name__': '__main__', '__file__': r'{SC / 'blender_product_ad.py'}'}})\n"
            "sc = bpy.context.scene; O = bpy.data.objects; F = 30\n"
            "vis = lambda o, f: (sc.frame_set(f), not o.hide_render)[1]\n"
            "def at(f): sc.frame_set(f); return sc.camera.matrix_world.translation.copy()\n"
            "jerk = lambda f: (at(f) - (at(f - 1) + at(f + 1)) / 2).length          # bend of the camera path at frame f\n"
            "films = [o for o in O if o.name.startswith('film') and o.type == 'MESH']\n"
            "print('SPLIT', 'blade' in O, vis(O['seam'], F - 3), vis(O['seam'], F + 4), len(films), all(any(m.type == 'HOOK' for m in f.modifiers) for f in films),\n"
            "      'cyclorama' in O, 'contact_shadow' in O, not any(o.name == 'Plane' for o in O), round(max(jerk(F + k) for k in range(1, 4)) / max(1e-6, jerk(F + 20)), 1))\n"
            f"sys.argv = ['b', '--'] + {base!r} + ['--shots', 'crown']; exec(src, {{'__name__': '__main__', '__file__': r'{SC / 'blender_product_ad.py'}'}})\n"
            "sc = bpy.context.scene; O = bpy.data.objects; cr = O['crown']; zs = []\n"
            "for f in range(1, 85, 3): sc.frame_set(f); zs.append(cr.scale.z)\n"
            "sc.frame_set(84); can = O['can']; dg = bpy.context.evaluated_depsgraph_get()\n"
            "from mathutils import Vector\n"
            "low = min((o.evaluated_get(dg).matrix_world @ Vector(c)).z for o in [can] + list(can.children_recursive) if o.type == 'MESH' for c in o.evaluated_get(dg).bound_box)\n"
            "print('CROWN', round(max(zs), 3), round(zs[-1], 3), 'pool' in O, round(low, 3), O['pool'].location.z)\n")
    r = subprocess.run([exe, "-b", "--python-exit-code", "1", "--python-expr", code], capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    sp = next((l.split()[1:] for l in out.splitlines() if l.startswith("SPLIT")), None); cw = next((l.split()[1:] for l in out.splitlines() if l.startswith("CROWN")), None)
    assert sp and cw, out[-4000:]
    assert sp[:3] == ["True", "True", "False"], sp                         # blade; seam lit at the cut, gone after
    assert int(sp[3]) >= 3 and sp[4] == "True", sp                         # juice films hooked to the halves
    assert sp[5:8] == ["True", "True", "True"], sp                         # seamless sweep, contact shadow, no flat floor plane
    assert float(sp[8]) > 5, sp                                            # the camera jolts on the cut, far more than its glide later
    zmax, zend, pool, low, zp = float(cw[0]), float(cw[1]), cw[2], float(cw[3]), float(cw[4])
    assert zmax > 0.4 and zend < zmax * 0.6 and pool == "True", cw         # the crown rises and falls back
    assert low < zp, cw                                                    # the can sits in the liquid, not on top of it


@test
def blender_can_blueprint(tmp):
    """ad_can.py: the can matches a 330 ml blueprint (66 mm wide, ~116 mm tall, scene unit 100 mm), the body is closed
    (no holes in the lathe), the lid panel sits below the seam rim, and condensation makes hundreds of beads on the
    label only. Skipped without Blender."""
    exe = blender_exe()
    if not exe: print("  (skipped: no Blender)"); return
    code = (f"import sys, bpy, bmesh; sys.path.insert(0, r'{SC}'); import ad_can as C\n"
            "bpy.ops.wm.read_factory_settings(use_empty=True)\n"
            "me = C.body_mesh('t'); ob = bpy.data.objects.new('t', me); bpy.context.scene.collection.objects.link(ob)\n"
            "lab = bpy.data.materials.new('lab'); me.materials.append(lab); me.materials.append(bpy.data.materials.new('m'))\n"
            "bm = bmesh.new(); bm.from_mesh(me); holes = sum(1 for e in bm.edges if e.is_boundary)\n"
            "xs = [v.co.x for v in me.vertices]; zs = [v.co.z for v in me.vertices]\n"
            "C.condensation(ob, lab); dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg)\n"
            "n = sum(1 for i in dg.object_instances if i.is_instance and i.parent and i.parent.original == ob)\n"
            "rim = max(zs); print('CANCHECK', max(xs) - min(xs), rim - min(zs), holes, n, C.LIDZ < rim - 0.02)\n")
    out = subprocess.run([exe, "-b", "--python-expr", code], capture_output=True, text=True, timeout=300).stdout
    line = next(l for l in out.splitlines() if l.startswith("CANCHECK")).split()
    width, height, holes, beads, recessed = float(line[1]), float(line[2]), int(line[3]), int(line[4]), line[5] == "True"
    assert abs(width - 0.66) < 0.005 and abs(height - 1.157) < 0.01, (width, height)
    assert holes == 0 and recessed and beads > 500, (holes, beads, recessed)


# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); ap.add_argument("-k"); ap.add_argument("--keep", action="store_true"); a = ap.parse_args()
    base = pathlib.Path(tempfile.mkdtemp(prefix="ve_tests_")); failed = 0
    for fn in TESTS:
        if a.k and a.k not in fn.__name__: continue
        d = base / fn.__name__; d.mkdir(); t0 = time.time()
        try:
            import os; cwd = os.getcwd(); os.chdir(d); fn(d); os.chdir(cwd)
            print(f"PASS  {fn.__name__:26s} {time.time() - t0:5.1f}s")
        except Exception as e:
            os.chdir(cwd); failed += 1
            print(f"FAIL  {fn.__name__:26s} {time.time() - t0:5.1f}s  {type(e).__name__}: {str(e)[:300]}")
            if a.keep: traceback.print_exc()
    if not a.keep: shutil.rmtree(base, ignore_errors=True)
    else: print("fixtures kept in", base)
    print(f"\n{len([f for f in TESTS if not a.k or a.k in f.__name__]) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
