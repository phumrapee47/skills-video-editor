"""Sound of the place first (travel, vlog, event montages): the viewer should feel they are standing there. A waterfall
on screen is heard as a waterfall; the music steps back for it.

Usage: python -I place_sound.py <plan.json> [--library DIR] [--moments 3] [--dry]
For every footage clip of the plan:
  1. hear its own sound with YAMNet (audio_tags.py, AudioSet classes grouped): water (waterfall, rapids, surf, rain),
     birds/insects/frogs, people (talk, crowd, market), street (traffic, footsteps), wind (on the mic), music, bells,
     fireworks, train, quiet; plus its level. Held-out check on 35 place recordings: 26 right, most of the rest arguable
     (a city recording full of talk reads as people). Without the model: hand rules, far weaker (6 of 32)
  2. look at the picture: water, greenery, city, night (colour layout of 3 frames)
  3. decide:
     moment  a sound worth hearing (water, birds, bells, fireworks, a busker, a busy market; ranked in that order, longer
             clips first, a bonus when the picture agrees): the clip's own sound comes up to the reference level and the
             music ducks under it (--moments clips, at least 6 s apart). The sound decides, the colour rules for the
             picture are weaker: Claude checks the sheet
     bed     usable sound: kept 15 dB under the music
     replace wind, rumble or silence over a picture we recognise: muted, and a matching place sound from the library
             (sound_library.py) is laid under the whole run of such clips with fades
Writes volumes, `speech`/`talk` (to duck music on moments) and ambience items into the plan; music_mix gap -3 dB /
under -14 dB. Claude cannot hear: the classes come from numbers; check one moment on the preview and say so.
"""
import argparse, json, pathlib, subprocess, sys
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SR = 16000
REF = -20.0            # dBFS the clip sound of a moment is brought to (music sits 3 dB under it outside moments)
WANT = {"water": {"water"}, "green": {"birds", "water", "people"}, "city": {"people", "music", "bells", "train"}, "night": {"people", "music", "birds", "fireworks"},
        "other": {"water", "birds", "people", "music", "bells", "fireworks", "train"}}   # picture unsure: a clear sound still counts
AMB = {"water": ["waves", "waterfall", "river"], "green": ["birds", "forest", "wind"], "city": ["city", "crowd", "market"], "night": ["city", "crowd"],
       "other": ["cafe", "city"], "indoor": ["cafe", "indoor"]}             # first type preferred; a night city wants city, not crickets


SCENE = {"cafe": "indoor", "indoor": "indoor", "beach": "water", "water": "water", "nature": "green", "city": "city", "night": "night"}


def clip_audio(src, a, b):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{max(0.2, b - a):.3f}", "-i", str(src), "-vn", "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def features(x):
    """Numbers that tell place sounds apart (16 kHz mono)."""
    hop = SR // 50; n = len(x) // hop; fr = x[:n * hop].reshape(n, hop) * np.hanning(hop)
    sp = np.abs(np.fft.rfft(fr, axis=1)) ** 2 + 1e-12; fq = np.fft.rfftfreq(hop, 1 / SR); tot = sp.sum(axis=1)
    band = lambda lo, hi: float(np.median(sp[:, (fq >= lo) & (fq < hi)].sum(axis=1) / tot))
    envdb = 10 * np.log10(tot); w = max(1, n // 25)                                    # 0.5 s windows: swells, gusts, steadiness
    slow = np.array([envdb[i:i + 25].mean() for i in range(0, n - 24, 25)]) if n >= 50 else envdb
    # harmonic lines: in 0.13 s windows a held note is a narrow peak; noise (water, traffic, wind) is smooth.
    # Median over windows, so a changing melody still counts (a 10 s average smears the notes away)
    L = 2048; m_ = len(x) // L
    if m_ >= 2:
        seg = x[: m_ * L].reshape(m_, L) * np.hanning(L); av = np.log(np.abs(np.fft.rfft(seg, axis=1)) ** 2 + 1e-12); f2 = np.fft.rfftfreq(L, 1 / SR)
        sel = (f2 > 150) & (f2 < 4000); k = np.ones(15) / 15
        prom = [np.percentile((row - np.convolve(row, k, "same"))[sel], 99) for row in av]
        tonal = float(np.median(prom))
    else: tonal = 0.0
    vlow = float(np.median(sp[:, fq < 120].sum(axis=1) / tot))
    sylls = 0.0
    if n >= 100:
        e = envdb - envdb.mean(); spec = np.abs(np.fft.rfft(e)); ff = np.fft.rfftfreq(len(e), 1 / 50)
        sylls = float(spec[(ff >= 3) & (ff <= 8)].sum() / (spec[1:].sum() + 1e-9))
    return {"vlow": vlow, "low": band(0, 250), "voice": band(300, 3400), "high": band(2500, 8000), "tonal": tonal,
            "swell": float(np.std(slow)), "flutter": float(np.std(np.diff(envdb))), "sylls": sylls}


def hear(x):
    """(class, level dBFS, evidence) of a clip's own sound: YAMNet (audio_tags.py) when its model is there, else the rules."""
    lvl = round(float(20 * np.log10(np.sqrt(np.mean(np.square(x))) + 1e-9)), 1) if len(x) else -90.0
    try:
        import audio_tags
        g, sc, top = audio_tags.place_class(x)
        return ("birds" if g == "insects" else g), lvl, {"yamnet": top[:3], "score": sc}
    except FileNotFoundError:
        return hear_rules(x)


def hear_rules(x):
    """Fallback without the model: hand rules (held-out check 2026-11-22: only 6 of 32 place recordings right)."""
    if len(x) < SR * 0.5: return "quiet", -90.0, {}
    lvl = round(float(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)), 1)
    if lvl < -48: return "quiet", lvl, {}
    f = features(x)
    # thresholds measured 2026-11-22 on known audio: surf/street noise "tonal" 2.07-2.16, music 3.1-5.0, speech 2.6
    if lvl < -38 and f["high"] < 0.02: cls = "quiet"                                      # faint rumble: nothing to hear
    elif f["voice"] > 0.45 and (f["flutter"] > 4.5 or f["sylls"] > 0.27) and f["tonal"] < 3.2: cls = "people"   # talk, chatter, a market
    elif f["tonal"] > 2.8: cls = "music"                                                    # held notes: a busker, a band, music in the footage
    elif f["high"] > 0.10 and f["tonal"] > 2.3 and f["flutter"] > 2.5: cls = "birds"      # chirps: high, short, tonal
    elif f["vlow"] > 0.75 and f["flutter"] > 4.5: cls = "wind"                              # rumble in gusts: wind on the microphone
    elif f["high"] > 0.08 and f["swell"] < 3.0 and f["tonal"] < 2.5: cls = "water"         # steady hiss across the band: surf, rapids, rain
    elif f["low"] > 0.45: cls = "street"                                                    # traffic, footsteps, the city's hum
    else: cls = "mixed"
    return cls, lvl, {k: round(v, 2) for k, v in f.items()}


def look(src, a, b, crop=None):
    """water / green / city / night / other from 3 small frames. Rules measured on graded footage (2026-11-22): a teal
    grade makes a whole city "blue", so water also needs a smooth lower half; cities are full of edges."""
    votes = []
    for t in (a + (b - a) * f for f in (0.2, 0.5, 0.8)):
        vf = (f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}," if crop else "") + "scale=64:36"
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        if len(raw) != 64 * 36 * 3: continue
        px = np.frombuffer(raw, np.uint8).astype(np.float32).reshape(36, 64, 3); r, g, b_ = px[..., 0], px[..., 1], px[..., 2]
        lum = px.mean(axis=2); lower = slice(18, 36)
        blue_low = float((((b_ > r + 12) & (b_ >= g - 8)) | ((lum > 200) & (px.max(axis=2) - px.min(axis=2) < 25)))[lower].mean())
        edges = float(np.abs(np.diff(lum, axis=1)).mean() + np.abs(np.diff(lum, axis=0)).mean()); edges_low = float(np.abs(np.diff(lum[lower], axis=1)).mean())
        green = float(((g > r + 8) & (g > b_ + 4)).mean())
        if np.median(lum) < 70 or (lum < 50).mean() > 0.35: votes.append("night")
        elif blue_low > 0.45 and edges_low < 10: votes.append("water")
        elif green > 0.3: votes.append("green")
        elif edges > 28: votes.append("city")
        else: votes.append("other")
    return max(set(votes), key=votes.count) if votes else "other"


def library_ambience(kind, lib):
    p = lib / "library.json"
    if not p.exists(): return []
    want = AMB.get(kind, [])
    got = [a for a in json.load(open(p, encoding="utf-8")).get("ambience", []) if a.get("type") in want and (lib / a["file"]).exists() and (a.get("seconds") or 0) >= 20]
    return sorted(got, key=lambda a: want.index(a["type"]))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan"); ap.add_argument("--library"); ap.add_argument("--moments", type=int, default=3); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    import sound_library
    lib = pathlib.Path(a.library) if a.library else sound_library.library_dir()
    pp = pathlib.Path(a.plan).resolve(); plan = json.load(open(pp, encoding="utf-8"))
    from edit_plan import build_timeline
    for c in plan["clips"]:
        if not c.get("card") and not pathlib.Path(c["src"]).is_absolute(): c["_abs"] = str((pp.parent / c["src"]).resolve())
    tl, total = build_timeline(plan)
    info = []
    for c, t in zip(plan["clips"], tl):
        if c.get("card"): info.append(None); continue
        src = c.get("_abs", c["src"]); x = clip_audio(src, c["in"], c["out"])
        cls, lvl, _ = hear(x)
        vis = SCENE.get(plan.get("scene"), None) or look(src, c["in"], c["out"], c.get("crop"))   # Claude's scene hint beats the colour rules
        info.append({"cls": cls, "lvl": lvl, "vis": vis, "start": t["start"], "end": t["end"], "dur": t["end"] - t["start"]})
    # a file whose shots are mostly "music" carries an added soundtrack (timelapses, stock clips): not the place's sound
    by_src = {}
    for c, f in zip(plan["clips"], info):
        if f: by_src.setdefault(c.get("_abs", c["src"]), []).append(f)
    for src, fs in by_src.items():
        if len(fs) >= 2 and sum(f["cls"] == "music" for f in fs) >= 0.6 * len(fs):
            print(f"  {pathlib.Path(src).name[:40]}: soundtrack in the footage -> muted, library place sounds instead")
            for f in fs: f["cls"] = "soundtrack"
    # moments: sound worth hearing that matches the picture, longest first, spread out
    worth = {"water": 3, "birds": 3, "bells": 2.5, "fireworks": 2.5, "music": 2, "people": 1.5, "train": 1.5}   # what makes a place feel present
    cand = sorted([i for i, f in enumerate(info) if f and f["cls"] in worth and f["dur"] >= 1.2],
                  key=lambda i: -(worth[info[i]["cls"]] + min(3.0, info[i]["dur"]) + (1 if info[i]["cls"] in WANT.get(info[i]["vis"], set()) else 0)))
    moments = []
    for i in cand:
        if len(moments) >= a.moments: break
        if all(abs(info[i]["start"] - info[j]["start"]) > 6 for j in moments): moments.append(i)
    plan["audio"] = [x for x in plan.get("audio", []) if not x.get("place")]
    runs, cur = [], None                                                 # runs of clips that need a library place sound
    for i, (c, f) in enumerate(zip(plan["clips"], info)):
        c.pop("_abs", None)
        if not f: continue
        if i in moments:
            c["volume_db"] = round(max(-12.0, min(12.0, REF - f["lvl"])), 1); c["speech"] = True; c["talk"] = [[0, round(f["dur"], 2)]]
            role = "MOMENT"
        elif f["cls"] in ("wind", "quiet", "soundtrack") or (f["cls"] == "street" and f["vis"] in ("water", "green")):
            c["volume_db"] = -90; c["speech"] = False; c.pop("talk", None); role = "replace"
        else:
            c["volume_db"] = round(max(-40.0, min(6.0, REF - 15 - f["lvl"])), 1); c["speech"] = False; c.pop("talk", None); role = "bed"
        need = role == "replace"
        kind = AMB.get(f["vis"], AMB["other"])[0]
        if f["vis"] == "indoor": kind = "cafe"                     # one continuous layer while the same kind of place sound fits
        if need and cur and cur["kind"] == kind and abs(cur["end"] - f["start"]) < 0.6: cur["end"] = f["end"]
        elif need: cur = {"vis": f["vis"], "kind": kind, "start": f["start"], "end": f["end"]}; runs.append(cur)
        print(f"  {f['start']:6.2f}s  sound {f['cls']:8s} {f['lvl']:6.1f} dBFS  picture {f['vis']:6s} -> {role}")
    added = 0
    for r in runs:
        opts = library_ambience(r["vis"] if r["vis"] in AMB else "other", lib)
        if not opts: print(f"  {r['start']:.1f}-{r['end']:.1f}s {r['vis']}: no library place sound (run sound_library.py fetch/index)"); continue
        top = [o for o in opts if o["type"] == opts[0]["type"]]; amb = top[int(r["start"] * 7) % len(top)]; d = r["end"] - r["start"] + 0.6
        off = max(0.0, min(float(amb.get("seconds") or 0) - d, 5.0))
        plan["audio"].append({"src": str((lib / amb["file"]).resolve()), "role": "sfx", "start": round(max(0, r["start"] - 0.3), 2), "in": round(off, 2),
                              "out": round(off + d, 2), "fade_in": 0.4, "fade_out": 0.6, "rel_db": -15, "place": True, "why": f"{r['vis']}: {amb['title'][:40]}"})
        added += 1
    plan["music_mix"] = {"gap_db": -3, "under_db": -14}
    print(f"{len(moments)} sound moments (music ducks), {added} library place sounds over {len(runs)} runs")
    if not a.dry: json.dump(plan, open(pp, "w", encoding="utf-8"), indent=1, ensure_ascii=False); print("wrote", pp.name)
