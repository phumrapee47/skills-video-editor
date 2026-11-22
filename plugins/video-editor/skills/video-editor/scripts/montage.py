"""Music montage from raw footage (travel film, promo, event recap): picks the best moments, orders them as a story,
cuts them to the music, and writes an edit plan for edit_plan.py.

Usage: python -I montage.py <out_plan.json> --src a.mp4 [b.mp4 ...] --music track.mp3 [--style film|promo]
         [--length 45] [--size 1920x1080] [--title "CAPE TOWN"] [--sub "South Africa"] [--end "See you soon"]
         [--pin "Strand Street"] [--lines "line one" "line two"] [--grade warm] [--ambience -20]
Rules from references/vlog-travel.md:
  - moments: find_shots.py scores (sharp, steady, well lit), long one-take footage cut into 3-4 s moments
  - never two alike in a row (colour layout of the frames), at least 12 s apart in the same source
  - story order: brighter and cooler first, warmer and darker towards the end (golden hour, night); the opener is a wide,
    calm view (sky in the top third, little motion: the references open on arrival / establishing shots)
  - lengths in beats of the music: promo 2 beats (some 1 and 4), film 4 beats (some 2 and 8); cuts land on the beat grid
    (the reference films follow phrases more than beats, so lengths vary instead of a fixed grid)
  - promo: hard cuts; film: a 0.5 s dissolve every 3rd-4th cut
  - titles: place name in spaced capitals at the start (with --sub under it), pin on the first landmark, poem lines
    (--lines) spread through the middle, closing title on the last shot
  - sound: the place first (place_sound.py: the footage's own sound comes up on 2-3 moments and the music ducks, bad
    sound is replaced by a matching library place sound); music chosen by the pictures (--music auto); -16 LUFS
Look at the sheet edit_plan.py writes, then move, swap or drop clips in the plan by hand.
"""
import argparse, json, pathlib, subprocess, sys
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def beat(music):
    tmp = pathlib.Path(music).with_suffix(".beats.json")
    subprocess.run([sys.executable, "-I", str(HERE / "music_beats.py"), str(music), "--dur", "90", "--json", str(tmp)], capture_output=True)
    b = json.load(open(tmp)); tmp.unlink(missing_ok=True); return b


def thumb(src, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", "-vf", "scale=16:9", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).astype(np.float32).reshape(-1) if len(raw) == 16 * 9 * 3 else None


def picture_area(src):
    """[x, y, w, h] without letterbox/pillarbox bars (ffmpeg cropdetect on a few points of the file)."""
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout or 0)
    found = []
    for f in (0.2, 0.5, 0.8):
        out = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{dur * f:.1f}", "-t", "4", "-i", str(src), "-vf", "cropdetect=24:2:0", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        import re
        m = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", out)
        if m: found.append(tuple(map(int, m[-1])))
    if not found: return None
    w, h, x, y = max(found, key=lambda c: c[0] * c[1])                  # the largest area seen (dark scenes read smaller)
    return [x, y, w, h]


def window(area, aspect, logo=None):
    """Output-aspect window inside the picture area; pushed to the side away from a burned-in logo corner."""
    x, y, w, h = area
    cw, ch = (min(w, round(h * aspect)), h) if w / h > aspect else (w, min(h, round(w / aspect)))
    if logo and len(logo) == 2 and w / h > aspect: cw = min(cw, int(w * 0.85)); ch = min(h, round(cw / aspect))   # room to step away from the logo
    cx = x + (w - cw) // 2; cy = y + (h - ch) // 2
    if logo in ("b", "t"):                                              # a band of overlays (logo + subscribe pop-ups)
        ch = int(h * 0.82); cw = min(w, round(ch * aspect)); ch = round(cw / aspect)
        cx = x + (w - cw) // 2; cy = y if logo == "b" else y + h - ch
    elif logo:
        cx = x if "r" in logo else x + w - cw
        cy = y if "b" in logo else y + h - ch
    return [cx // 2 * 2, cy // 2 * 2, cw // 2 * 2, ch // 2 * 2]


def coarse(v):
    """8x4 block layout of a 16x9 thumbnail: the same view stays the same when people walk through it."""
    return v.reshape(9, 16, 3)[:8].reshape(4, 2, 8, 2, 3).mean(axis=(1, 3))


def moments(src, work):
    pre = work / (pathlib.Path(src).stem + "_shots")
    if not pathlib.Path(str(pre) + ".json").exists():
        subprocess.run([sys.executable, "-I", str(HERE / "find_shots.py"), str(src), str(pre), "--window", "3.5", "--min", "2"], check=True, capture_output=True)
    shots = json.load(open(str(pre) + ".json"))["shots"]
    for s in shots:
        s["src"] = str(src); v = thumb(src, s["best"]); s["_v"] = v
        if v is not None:                                               # a frozen stretch (a still inside stock footage) is not a shot
            a_, b_ = thumb(src, s["start"] + 0.2), thumb(src, max(s["start"] + 0.3, s["end"] - 0.2))
            if a_ is not None and b_ is not None and np.abs(a_ - b_).mean() < 0.8 and np.abs(a_ - v).mean() < 0.8: s["_v"] = None
        if v is not None:
            px = v.reshape(-1, 3); s["warm"] = float((px[:, 0] - px[:, 2]).mean()); s["luma"] = float(px.mean())
            top = v.reshape(9, 16, 3)[:3].reshape(-1, 3)                  # a wide view shows sky or horizon up top
            s["sky"] = float(((top[:, 2] > top[:, 0] + 10) & (top.mean(axis=1) > 110)).mean())
    return [s for s in shots if s.get("_v") is not None and s.get("luma", 99) > 22]   # a fade to black is not a shot


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out"); ap.add_argument("--src", nargs="+", required=True); ap.add_argument("--music", default="auto", help="music file, or auto = best match for the pictures from the sound library (sound_library.py); audition alternatives with music_audition.py")
    ap.add_argument("--style", choices=["film", "promo"], default="film"); ap.add_argument("--length", type=float, default=45)
    ap.add_argument("--size", default="1920x1080"); ap.add_argument("--title"); ap.add_argument("--sub"); ap.add_argument("--end")
    ap.add_argument("--pin"); ap.add_argument("--lines", nargs="*", default=[]); ap.add_argument("--grade")
    ap.add_argument("--ambience", type=float, default=-20, help="dB of the footage's own sound under the music (-90 = off)")
    ap.add_argument("--logo", nargs="*", default=[], help="burned-in logo per source: corner br/bl/tr/tl (the frame steps away), b/t = drop that whole band (logo + pop-ups), - = none")
    ap.add_argument("--credit", help="footage credit shown small at the end (CC BY footage needs it; music credits go in <out>.credits.txt)")
    ap.add_argument("--lufs", type=float, default=-16.0, help="loudness: music-led travel films sit around -15 to -23 LUFS (references); -14 felt too loud")
    ap.add_argument("--skip", nargs="*", default=[], help="source ranges never to use: a-b (first source) or N:a-b (source N, from 1), e.g. a title card at 0-5.5")
    ap.add_argument("--scene", choices=["city", "night", "beach", "nature", "cafe", "indoor", "product"], help="what the footage shows, set after LOOKING at the frames (beats the colour rules for music and place sounds)")
    ap.add_argument("--no-place", action="store_true", help="skip place_sound.py (the footage's own sound first, library place sounds where it is bad)")
    a = ap.parse_args()
    out = pathlib.Path(a.out).resolve(); work = out.parent / (out.stem + "_work"); work.mkdir(parents=True, exist_ok=True)
    W, H = map(int, a.size.split("x"))
    skips = {}
    for sk in a.skip:
        n, rng = (sk.split(":", 1) if ":" in sk else ("1", sk)); lo, hi = map(float, rng.split("-"))
        skips.setdefault(str(pathlib.Path(a.src[int(n) - 1]).resolve()), []).append((lo, hi))
    cand = [m for s in a.src for m in moments(pathlib.Path(s).resolve(), work)
            if not any(m["start"] < hi and m["end"] > lo for lo, hi in skips.get(str(pathlib.Path(s).resolve()), []))]
    if not cand: sys.exit("no usable moments found")
    if a.music == "auto":                                               # the pictures choose the music (feels, genre, tempo)
        import music_mood, sound_library
        lib = sound_library.library_dir(); lp = lib / "library.json"
        if not lp.exists(): sys.exit("no sound library yet: sound_library.py fetch (ask the user first) and index, or pass --music file")
        tracks = [t for t in json.load(open(lp, encoding="utf-8"))["tracks"] if (lib / t["file"]).exists()]
        top = sorted(cand, key=lambda s: -s["score"])[:16]
        probe_plan = {"clips": [{"src": m["src"], "in": m["start"], "out": m["end"]} for m in top], **({"scene": a.scene} if a.scene else {})}
        tg = music_mood.picture_target(probe_plan, out.parent, pace=0.9 if a.style == "promo" else 2.6)
        tg["recent"] = music_mood.recent(lib)
        best = sorted(tracks, key=lambda t: -music_mood.picture_score(t, tg))[0]; music_mood.mark_used(lib, best.get("id") or best["file"])
        a.music = str((lib / best["file"]).resolve())
        print(f"music by picture {tg['scene']}: {best['title']} [{best.get('genre')}] {', '.join(best.get('feels') or [])}")
    b = beat(a.music); per = b["period"]
    print(f"music {b['bpm']:.0f} BPM (beat {per:.2f} s, first {b['first']:.2f} s, strength {b['strength']})")
    pattern = [2, 2, 1, 2, 4, 2, 2, 1] if a.style == "promo" else [4, 4, 2, 4, 8, 4, 2, 4]
    lens, t = [], 0.0
    last = (4 if a.style == "promo" else 8) * per                       # the closing shot holds the end title
    while t < a.length - last - 0.5:
        n = pattern[len(lens) % len(pattern)]; lens.append(n * per); t += n * per
    lens.append(last)
    picked = []                                                         # best first, unlike neighbours, spread in time
    for s in sorted(cand, key=lambda s: -s["score"]):
        if len(picked) >= len(lens): break
        if any(p["src"] == s["src"] and abs(p["best"] - s["best"]) < 12 for p in picked): continue
        if any(np.abs(p["_v"] - s["_v"]).mean() < 18 or np.abs(coarse(p["_v"]) - coarse(s["_v"])).mean() < 12 for p in picked): continue   # same view again
        picked.append(s)
    if len(picked) < len(lens):                                         # not enough distinct views: allow closer ones
        for s in sorted(cand, key=lambda s: -s["score"]):
            if len(picked) >= len(lens): break
            if s not in picked and all(not (p["src"] == s["src"] and abs(p["best"] - s["best"]) < 5) for p in picked): picked.append(s)
    if len(picked) < len(lens) and picked:                             # too few distinct views: longer shots, still whole beats
        beats = max(len(picked), round(a.length / per)); n = len(picked); base = beats // n; extra = beats - base * n
        lens = [(base + (1 if i < extra else 0)) * per for i in range(n - 1)] + [max(base, 4) * per]
        print(f"only {n} distinct views: {base}-{base + 1} beats per shot to fill {a.length:.0f} s")
    lens = lens[:len(picked)]
    # story order: bright and cool first, warm and dark late; opener = sharpest of the brightest third
    arc = lambda s: (s["warm"] / 40) - (s["luma"] / 120)
    order = sorted(picked, key=arc)
    third = max(1, len(order) // 2)                                     # opener: a wide, calm, sharp view from the bright half
    opener = max(order[:third], key=lambda s: s["score"] + 0.6 * s["sky"] - 0.004 * s.get("motion", 0)); order.remove(opener); order.insert(0, opener)
    for i in range(1, len(order) - 1):                                  # break up look-alike neighbours
        if np.abs(order[i]["_v"] - order[i - 1]["_v"]).mean() < 22: order[i], order[i + 1] = order[i + 1], order[i]
    crops = {}
    for i, src in enumerate(a.src):                                     # bars off, step away from a logo
        key = str(pathlib.Path(src).resolve()); area = picture_area(key); logo = a.logo[i] if i < len(a.logo) and a.logo[i] != "-" else None
        full = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", key], capture_output=True, text=True).stdout.strip().split(",")
        fw, fh = int(full[0]), int(full[1]); area = area or [0, 0, fw, fh]
        if logo or area != [0, 0, fw, fh]: crops[key] = window(area, W / H, logo); print(f"  {pathlib.Path(src).name[:30]}: picture {area}, frame {crops[key]}")
    clips, t = [], 0.0
    for k, (s, d) in enumerate(zip(order, lens)):
        mid = s["best"]; a0 = max(s["start"], min(mid - d / 2, s["end"] - d)); a0 = max(0.0, a0)
        c = {"src": str(pathlib.Path(s["src"])), "in": round(a0, 3), "out": round(a0 + d, 3), "fit": "crop", "speech": False, "volume_db": a.ambience,
             **({"crop": crops[s["src"]]} if crops.get(s["src"]) else {}),
             "why": f"score {s['score']} warm {s['warm']:.0f} luma {s['luma']:.0f}"}
        if a.style == "film" and k and k % 4 == 3: c["transition"] = {"type": "fade", "dur": 0.5}
        clips.append(c)
    # timeline times (dissolves overlap, shorten the timeline)
    starts, t = [], 0.0
    for c in clips:
        td = c.get("transition", {}).get("dur", 0.0); starts.append(t - td); t += (c["out"] - c["in"]) - td
    total = t; titles = []
    if a.title:
        titles.append({"text": a.title, "start": 0.4, "end": min(total, 0.4 + 4 * per * 2), "style": "spaced", "pos": "center", "size": round(H * 0.11)})
        if a.sub: titles.append({"text": a.sub, "start": 0.9, "end": min(total, 0.4 + 4 * per * 2), "style": "poem", "y": 0.6, "size": round(H * 0.045)})
    if a.pin and len(clips) > 2: titles.append({"text": a.pin, "start": starts[2] + 0.2, "end": starts[2] + min(3.0, clips[2]["out"] - clips[2]["in"]), "style": "pin"})
    for i, line in enumerate(a.lines):                                  # poem lines spread through the middle
        k = min(len(clips) - 2, 3 + i * max(1, (len(clips) - 5) // max(1, len(a.lines))))
        s0 = starts[k] + 0.2; titles.append({"text": line, "start": round(s0, 2), "end": round(min(total, s0 + max(2.5, 3 * per * 2)), 2), "style": "poem"})
    if a.end: titles.append({"text": a.end, "start": round(starts[-1] + 0.3, 2), "end": round(total - 0.1, 2), "style": "spaced", "pos": "center", "size": round(H * 0.075)})
    if a.credit: titles.append({"text": a.credit, "start": round(starts[-1] + 0.6, 2), "end": round(total - 0.1, 2), "style": "poem", "y": 0.93, "size": round(H * 0.022)})
    plan = {"output": {"path": out.stem + ".mp4", "size": [W, H], "fps": 30, "target": "youtube" if W > H else "shorts", "fit": "crop", "lufs": a.lufs},
            "clips": clips, "titles": titles,
            "audio": [{"src": str(pathlib.Path(a.music).resolve()), "role": "music", "start": 0, "in": round(b["first"], 3), "end": round(total, 3), "fade_in": 0.3, "fade_out": 2.5}],
            "music_mix": {"gap_db": 0, "under_db": 0}}
    if a.grade: plan["grade"] = a.grade
    if a.scene: plan["scene"] = a.scene
    json.dump(plan, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{len(clips)} shots from {len(cand)} moments, {total:.1f} s; style {a.style}; wrote {out.name}")
    if not a.no_place:                                                  # the place first: its own sound, music ducks on moments
        subprocess.run([sys.executable, "-I", str(HERE / "place_sound.py"), str(out)], check=True)
    for c, s0 in zip(clips, starts): print(f"  {s0:6.2f}s  {pathlib.Path(c['src']).name[:28]:28s} {c['in']:7.2f}-{c['out']:7.2f}  {c['why']}{'  dissolve' if c.get('transition') else ''}")
