"""Render a whole footage edit from one JSON edit plan: clips, transitions, titles, voice, music with ducking,
sound effects, subtitles, loudness, export, then run qa_check.py. The format is described in references/edit-plan.md.

Usage: python -I edit_plan.py <plan.json> [--preview A B] [--no-qa]
  --preview A B   render only timeline seconds A..B at half size (fast check before the full render)
Writes the output, <output>.timeline.json (where every clip, title and sound landed) and the QA report.

Design notes
- Video is assembled by one ffmpeg filter graph (trim, speed, fit, xfade/concat, title overlays, subtitles).
- Audio is mixed in numpy on the same timeline (clip sound, voice, music, effects), because ducking from known speech
  times beat a sidechain compressor in a listening test (references/music-rules.md).
- Titles are an ASS track burned with libass: ffmpeg drawtext and Pillow without raqm drop Thai tone marks that sit
  on an upper vowel (ที่ became ทีนี).
- Everything is encoded H.264 yuv420p limited range (scale=out_range=tv), AAC 192k, faststart.
"""
import argparse, json, pathlib, re, subprocess, sys, tempfile, wave
import numpy as np

SR = 48000
HERE = pathlib.Path(__file__).parent
TARGETS = {"youtube": -14.0, "shorts": -14.0, "doc": -18.5, "master": -23.0}
FONT = "C:/Windows/Fonts/LeelaUIb.ttf"


# ---------- timeline -------------------------------------------------------------------------------------------
def build_timeline(plan):
    t, out = 0.0, []
    for k, c in enumerate(plan["clips"]):
        speed = float(c.get("speed", 1.0)); d = (float(c["out"]) - float(c["in"])) / speed
        tr = c.get("transition") if k else None; td = float(tr.get("dur", 0.5)) if tr else 0.0
        start = t - td
        out.append({"i": k, "start": round(start, 3), "end": round(start + d, 3), "dur": d, "speed": speed, "trans": tr, "tdur": td, **c})
        t = start + d
    return out, t


def srt_spans(path, offset=0.0):
    txt = open(path, encoding="utf-8-sig").read()
    def s(x): h, m, r = x.replace(",", ".").split(":"); return int(h) * 3600 + int(m) * 60 + float(r)
    return [(s(a) + offset, s(b) + offset) for a, b in re.findall(r"(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)", txt)]


# ---------- titles (libass) -----------------------------------------------------------------------------------
def ass_time(t):
    t = max(0.0, t); return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def titles_ass(titles, W, H, path):
    """Titles as an ASS track: libass shapes Thai correctly (Pillow without raqm and ffmpeg drawtext drop stacked marks)."""
    head = "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: T,Leelawadee UI,{round(H * 0.07)},&H00DCF0FA,&H000000FF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,0,"
        f"{max(2, H // 300)},8,40,40,{round(H * 0.09)},1", "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"])
    rows = []
    for it in titles:
        an = {"top": 8, "center": 5, "bottom": 2}[it.get("pos", "top")]; fi = int(float(it.get("fade", 0.3)) * 1000)
        tags = "\\an%d\\fad(%d,%d)" % (an, fi, fi)
        if "size" in it: tags += "\\fs%d" % int(it["size"])
        if "color" in it: r, g, b = it["color"]; tags += "\\c&H%02X%02X%02X&" % (b, g, r)
        mv = round(H * float(it.get("margin", 0.09)))
        text = str(it["text"]).replace("\n", "\\N")
        rows.append(f"Dialogue: 0,{ass_time(it['start'])},{ass_time(it['end'])},T,,0,0,{mv},,{{{tags}}}{text}")
    open(path, "w", encoding="utf-8").write(head + "\n" + "\n".join(rows) + "\n")


# ---------- video ----------------------------------------------------------------------------------------------
def fit_filter(fit, W, H):
    if fit == "crop": return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    if fit == "pad": return f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black"
    # blur: whole frame over a blurred, filled copy of itself (9:16 from 16:9 footage)
    return (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=30,eq=brightness=-0.08[bg];"
            f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")


def render_video(plan, tl, total, W, H, fps, tmp, a0, a1):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]; fg = []; n = 0
    for c in tl:
        cmd += ["-ss", f"{c['in']}", "-t", f"{c['out'] - c['in']:.3f}", "-i", c["src"]]
        fit = c.get("fit", plan["output"].get("fit", "crop"))
        fg.append(f"[{n}:v]setpts=(PTS-STARTPTS)/{c['speed']},{fit_filter(fit, W, H)},fps={fps},format=yuv420p,setsar=1[v{n}]"); n += 1
    acc = "v0"; acc_len = tl[0]["dur"]
    for c in tl[1:]:
        k = c["i"]; out = f"x{k}"
        if c["trans"]:
            ty = c["trans"].get("type", "fade")
            fg.append(f"[{acc}][v{k}]xfade=transition={ty}:duration={c['tdur']:.3f}:offset={acc_len - c['tdur']:.3f}[{out}]")
            acc_len += c["dur"] - c["tdur"]
        else:
            fg.append(f"[{acc}][v{k}]concat=n=2:v=1:a=0[{out}]"); acc_len += c["dur"]
        acc = out
    titles = []
    for c in tl:                                            # titles given per clip use clip time
        for it in c.get("titles", []): titles.append({**it, "start": c["start"] + it["start"], "end": c["start"] + it["end"]})
    titles += plan.get("titles", [])
    warn = [f"title '{it['text'][:20]}' ends at {it['end']:.2f} s, after the {total:.2f} s timeline" for it in titles if it["end"] > total + 0.01]
    for w in warn: print("WARNING", w)
    tail = []
    if titles:
        ap_ = tmp / "titles.ass"; titles_ass(titles, W, H, ap_)
        tail.append(f"ass='{ap_.resolve().as_posix().replace(':', chr(92) + ':')}'")
    sub = plan.get("subtitles")
    if sub:
        p = pathlib.Path(sub["src"]).resolve().as_posix().replace(":", r"\:")
        style = sub.get("style", f"FontName=Leelawadee UI,FontSize={16 if W >= H else 11},Bold=1,Outline=1.2,Shadow=1,MarginV={22 if W >= H else 60}")
        tail.append(f"subtitles='{p}':force_style='{style}'")
    if a0 is not None: tail.append(f"trim={a0}:{a1},setpts=PTS-STARTPTS,scale=iw/2:-2")
    tail.append("scale=out_range=tv,format=yuv420p")
    fg.append(f"[{acc}]{','.join(tail)}[vout]")
    out = tmp / "video.mp4"
    subprocess.run(cmd + ["-filter_complex", ";".join(fg), "-map", "[vout]", "-c:v", "libx264", "-crf", str(plan["output"].get("crf", 19)),
                          "-preset", "medium", "-color_range", "tv", "-an", str(out)], check=True)
    return out


# ---------- audio ----------------------------------------------------------------------------------------------
def decode(src, ss=None, t=None, speed=1.0):
    cmd = ["ffmpeg", "-v", "error"] + (["-ss", str(ss)] if ss is not None else []) + (["-t", str(t)] if t is not None else []) + ["-i", src]
    af = []
    s = speed
    while s > 2.0: af.append("atempo=2.0"); s /= 2.0
    while s < 0.5: af.append("atempo=0.5"); s /= 0.5
    if abs(s - 1) > 1e-6: af.append(f"atempo={s}")
    r = subprocess.run(cmd + (["-af", ",".join(af)] if af else []) + ["-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.float32).reshape(-1, 2).astype(np.float64) if r.stdout else np.zeros((0, 2))


def db(x): return 10 ** (x / 20)
def rms(x): return float(np.sqrt(np.mean(x ** 2)) + 1e-9) if len(x) else 1e-9


def place(bus, x, start, gain=1.0, fin=0.0, fout=0.0):
    i = int(round(start * SR)); x = x * gain
    if fin > 0: k = min(len(x), int(fin * SR)); x[:k] *= np.linspace(0, 1, k)[:, None]
    if fout > 0: k = min(len(x), int(fout * SR)); x[len(x) - k:] *= np.linspace(1, 0, k)[:, None]
    if i < 0: x = x[-i:]; i = 0
    j = min(len(bus), i + len(x)); bus[i:j] += x[: j - i]


def render_audio(plan, tl, total, tmp):
    N = int(total * SR) + 1; speech = np.zeros((N, 2)); other = np.zeros((N, 2))
    talk = []
    for c in tl:                                            # clip sound, with the same overlap as the picture transition
        g = db(float(c.get("volume_db", 0))); x = decode(c["src"], c["in"], c["out"] - c["in"], c["speed"])
        edge = max(0.01, c["tdur"]); nxt = next((d for d in tl if d["i"] == c["i"] + 1), None)
        fout = max(0.01, nxt["tdur"]) if nxt else 0.01
        place(speech if c.get("speech", True) else other, x, c["start"], g, edge, fout)
        if c.get("speech", False) and c.get("talk"): talk += [(c["start"] + a, c["start"] + b) for a, b in c["talk"]]
    music_items = []
    for a in plan.get("audio", []):
        role = a.get("role", "sfx")
        if role == "music": music_items.append(a); continue
        x = decode(a["src"], a.get("in"), (a["out"] - a.get("in", 0)) if "out" in a else None)
        place(speech if role == "voice" else other, x, float(a["start"]), db(float(a.get("volume_db", 0))), float(a.get("fade_in", 0.01)), float(a.get("fade_out", 0.01)))
        if role == "voice": talk.append((float(a["start"]), float(a["start"]) + len(x) / SR))
    if plan.get("subtitles", {}).get("duck_from", True) and plan.get("subtitles"): talk += srt_spans(plan["subtitles"]["src"])
    if not talk and np.abs(speech).max() > 0:              # no speech times given: detect them from the clip/voice sound
        hop = int(0.1 * SR); e = np.sqrt(np.mean(speech[: len(speech) // hop * hop].reshape(-1, hop, 2) ** 2, axis=(1, 2))) + 1e-9
        lev = 20 * np.log10(e); thr = max(-45.0, np.percentile(lev, 90) - 18); on = lev > thr; k = 0
        while k < len(on):
            if on[k]:
                j = k
                while j < len(on) and on[j:j + 5].any(): j += 1          # bridge gaps under 0.5 s
                if j - k >= 3: talk.append((k * 0.1, j * 0.1))
                k = j
            k += 1
    mask = np.zeros(N)
    for a, b in talk: mask[max(0, int((a - 0.5) * SR)): min(N, int((b + 1.5) * SR))] = 1   # lower 0.5 s before speech, back 1.5 s after
    if mask.any():
        k = int(0.4 * SR); c = np.concatenate([[0.0], np.cumsum(mask)]); idx = np.arange(N)
        mask = (c[np.clip(idx + k // 2, 0, N)] - c[np.clip(idx - k // 2, 0, N)]) / k
    sp_level = rms(speech[mask > 0.5]) if (mask > 0.5).any() else db(-20)
    music = np.zeros((N, 2))
    for m in music_items:
        x = decode(m["src"], m.get("in")); s0 = float(m.get("start", 0)); e0 = float(m.get("end", total))
        need = int((e0 - s0) * SR)
        if len(x) and m.get("loop", True) and len(x) < need: x = np.tile(x, (need // len(x) + 1, 1))
        x = x[:need]; x = x / rms(x) * sp_level
        place(music, x, s0, 1.0, float(m.get("fade_in", 1.5)), float(m.get("fade_out", 2.5)))
    mm = (plan.get("music_mix") or {})
    gap_db = float(mm.get("gap_db", -8)); under_db = float(mm.get("under_db", -30))   # vlog default: off under speech
    env = db(under_db) * mask + db(gap_db) * (1 - mask)
    mix = speech + other + music * env[:, None]
    peak = np.abs(mix).max()
    if peak > 0.95: mix *= 0.95 / peak
    path = tmp / "mix.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())
    return path, talk


def loudnorm_filter(wav, lufs, ss=None, t=None):
    """Two-pass loudnorm: measure the mix, then apply a linear gain to hit the target (single pass landed ~1.5 dB low)."""
    cmd = ["ffmpeg", "-hide_banner", "-nostats"] + (["-ss", str(ss), "-t", str(t)] if ss is not None else []) + ["-i", str(wav),
           "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"]
    e = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    m = json.loads(e[e.rindex("{"): e.rindex("}") + 1])
    return (f"loudnorm=I={lufs}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
            f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")


# ---------- main -----------------------------------------------------------------------------------------------
if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan"); ap.add_argument("--preview", nargs=2, type=float); ap.add_argument("--no-qa", action="store_true")
    a = ap.parse_args()
    plan_path = pathlib.Path(a.plan).resolve(); base = plan_path.parent
    plan = json.load(open(plan_path, encoding="utf-8"))
    def rp(p): return str((base / p).resolve()) if p else p
    for c in plan["clips"]: c["src"] = rp(c["src"])
    for x in plan.get("audio", []): x["src"] = rp(x["src"])
    if plan.get("subtitles"): plan["subtitles"]["src"] = rp(plan["subtitles"]["src"])
    o = plan["output"]; W, H = o.get("size", [1920, 1080]); fps = o.get("fps", 30)
    target = o.get("target", "youtube"); lufs = float(o.get("lufs", TARGETS[target]))
    out = rp(o["path"]) if not a.preview else rp(str(pathlib.Path(o["path"]).with_name(pathlib.Path(o["path"]).stem + f"_preview_{a.preview[0]:g}-{a.preview[1]:g}.mp4")))
    tl, total = build_timeline(plan)
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        a0, a1 = (a.preview if a.preview else (None, None))
        video = render_video(plan, tl, total, W, H, fps, tmp, a0, a1)
        mix, talk = render_audio(plan, tl, total, tmp)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
        cmd += (["-ss", str(a0), "-t", str(a1 - a0)] if a.preview else []) + ["-i", str(mix)]
        subprocess.run(cmd + ["-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", loudnorm_filter(mix, lufs, a0, (a1 - a0) if a.preview else None), "-ar", "48000",
                              "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)
    json.dump({"duration": round(total, 3), "clips": [{k: c[k] for k in ("i", "src", "in", "out", "start", "end", "speed")} for c in tl],
               "speech": [[round(x, 2), round(y, 2)] for x, y in sorted(talk)]},
              open(out + ".timeline.json", "w", encoding="utf-8"), indent=1)
    print(f"wrote {out} ({total:.2f} s timeline)")
    if not a.no_qa:
        qa = [sys.executable, "-I", str(HERE / "qa_check.py"), out, "--target", target, "--sheet", out + ".sheet.jpg", "--json", out + ".qa.json"]
        if plan.get("subtitles") and not a.preview: qa += ["--subs", plan["subtitles"]["src"]]
        subprocess.run(qa)
