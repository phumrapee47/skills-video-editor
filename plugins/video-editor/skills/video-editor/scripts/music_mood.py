"""Choose background music by mood: measure a music folder once, read the mood of the edit from its words, put the
closest track into the plan.

Usage:
  python -I music_mood.py scan <music_dir>                    -> <music_dir>/library.json (features + mood per track)
  python -I music_mood.py pick <plan.json> --library <dir|library.json> [--words words.json] [--mood calm] [--apply]
Track features (numpy, first 120 s): tempo (spectral-flux autocorrelation, as music_beats.py), loudness and how busy it
is (onsets per second), brightness (spectral centroid), major/minor (chroma vs Krumhansl key profiles), dynamics.
They give each track two numbers, valence (sad/dark -1 ... +1 happy/bright) and arousal (calm -1 ... +1 driving), and a
mood word: playful, upbeat, calm, warm, reflective, sad, tense, epic. A "moods" list you write into library.json for a
track wins over the measured one (a person can hear; the numbers only guess).
The edit's mood: word lists (English + Thai) for happy / sad / tense / calm / wonder topics, exclamations and questions,
and the speaking pace from the word timings, plus the plan's titles, headline and cards (an ad without speech is
read from its titles; music-led edits start from upbeat). Talk needs a bed that does not fight the voice, so for speech the target
arousal is pulled toward calm. --mood overrides; a brand kit's "music" list limits the choice to the channel's tracks.
--apply replaces the plan's music (role "music") with the pick, starting after the track's quiet intro.
Credit the composer as the track's licence asks (library.json keeps the folder's CREDITS.md next to each track).
"""
import argparse, json, pathlib, re, subprocess, sys
import numpy as np

SR, HOP, NFFT = 22050, 512, 2048
MOODS = {"playful": (0.7, 0.6), "upbeat": (0.6, 0.35), "warm": (0.45, -0.3), "calm": (0.1, -0.6), "reflective": (-0.2, -0.45),
         "sad": (-0.65, -0.4), "tense": (-0.55, 0.45), "epic": (-0.05, 0.75), "wonder": (0.3, -0.05)}
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def decode(path, start=0, dur=120):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def features(path):
    x = decode(path); n = 1 + (len(x) - NFFT) // HOP; fps = SR / HOP
    fr = np.lib.stride_tricks.as_strided(x, (n, NFFT), (x.strides[0] * HOP, x.strides[0])) * np.hanning(NFFT)
    spec = np.abs(np.fft.rfft(fr, axis=1)); freqs = np.fft.rfftfreq(NFFT, 1 / SR)
    mag = np.log1p(spec); flux = np.maximum(0, np.diff(mag, axis=0)).sum(axis=1)
    fl = np.maximum(flux - np.convolve(flux, np.ones(16) / 16, "same"), 0)
    ac = np.correlate(fl, fl, "full")[len(fl) - 1:]; lags = np.arange(len(ac)) / fps; ok = (lags >= 60 / 180) & (lags <= 60 / 70)
    k = int(np.argmax(np.where(ok, ac, 0))); bpm = 60 / lags[k]; strength = float(ac[k] / (np.median(ac[ok]) + 1e-9))
    thr = np.median(fl) + 2 * fl.std(); onsets = int(((fl[1:-1] > thr) & (fl[1:-1] >= fl[:-2]) & (fl[1:-1] >= fl[2:])).sum()) / (len(x) / SR)
    rms = np.sqrt(np.mean(fr ** 2, axis=1)) + 1e-9; db = 20 * np.log10(rms); loud = db > db.max() - 40
    centroid = float((spec[loud] * freqs).sum(axis=1).mean() / (spec[loud].sum(axis=1).mean() + 1e-9))
    pc = np.zeros(12); band = (freqs > 60) & (freqs < 2000)
    midi = 69 + 12 * np.log2(freqs[band] / 440); e = (spec[loud][:, band] ** 2).sum(axis=0)
    for m, v in zip(np.round(midi).astype(int) % 12, e): pc[m] += v
    pc /= pc.sum() + 1e-9
    maj = max(np.corrcoef(pc, np.roll(MAJOR, i))[0, 1] for i in range(12)); mnr = max(np.corrcoef(pc, np.roll(MINOR, i))[0, 1] for i in range(12))
    dyn = float(np.percentile(db[loud], 90) - np.percentile(db[loud], 20))
    intro = float(np.argmax(db > np.median(db[loud]) - 6) / fps)              # quiet intro to skip
    return {"bpm": round(float(bpm), 1), "beat_strength": round(strength, 2), "onsets_per_s": round(onsets, 2),
            "brightness_hz": round(centroid), "major_minus_minor": round(float(maj - mnr), 3), "dynamics_db": round(dyn, 1),
            "loud_db": round(float(np.percentile(db[loud], 75)), 1), "intro_s": round(intro, 2)}


def place(f):
    """Valence and arousal (-1..1) from features. Weights fitted by eye on 10 Kevin MacLeod tracks with known moods."""
    clip = lambda v: float(np.clip(v, -1, 1))
    tempo = (f["bpm"] - 105) / 45 if f["beat_strength"] >= 1.6 else -0.3             # no steady beat: ambient
    arousal = clip(0.45 * tempo + 0.35 * (f["onsets_per_s"] - 2.0) / 2.0 + 0.25 * (f["loud_db"] + 18) / 8)
    valence = clip(4.0 * f["major_minus_minor"] + 0.35 * (f["brightness_hz"] - 1800) / 1200 + 0.15 * tempo)
    return round(valence, 2), round(arousal, 2)


def mood_of(v, a):
    return min(MOODS, key=lambda m: (MOODS[m][0] - v) ** 2 + (MOODS[m][1] - a) ** 2)


WORDS = {   # topic words -> (valence, arousal); English and Thai
 "happy":  ((0.6, 0.4),  "fun funny laugh love happy great amazing awesome win won celebrate joy best excited enjoy brilliant "
                         "สนุก ตลก ขำ ดีใจ มีความสุข สุดยอด เยี่ยม ชนะ ฉลอง ชอบ รัก เล่น มาแล้ว ใหม่ ว้าว"),
 "sad":    ((-0.6, -0.4), "sad loss lost died death grief alone miss missed tragic tragedy cry pain hurt sorry victims "
                         "เศร้า เสียใจ สูญเสีย ตาย เสียชีวิต ร้องไห้ เจ็บ ทุกข์ เหงา โศก"),
 "tense":  ((-0.5, 0.5),  "danger dangerous risk threat warning crisis fear afraid scary attack disaster flood floods storm emergency "
                         "อันตราย เสี่ยง ภัย วิกฤต กลัว น่ากลัว โจมตี หายนะ น้ำท่วม พายุ ฉุกเฉิน"),
 "epic":   ((-0.1, 0.7),  "war battle army siege empire kingdom fought fight conquer destroyed burned fire legendary "
                         "สงคราม รบ กองทัพ ล้อม อาณาจักร ราชธานี ทำลาย เผา ไฟ ยิ่งใหญ่ ตำนาน"),
 "calm":   ((0.2, -0.6),  "calm peace peaceful quiet relax gentle slow nature garden morning breathe rest "
                         "สงบ เงียบ ผ่อนคลาย ธรรมชาติ ช้า พักผ่อน ร่มรื่น"),
 "wonder": ((0.25, -0.15), "history ancient mystery mysterious secret discover discovered imagine beautiful wonder roots temple "
                         "ประวัติศาสตร์ โบราณ ลึกลับ ปริศนา ค้นพบ สวย มหัศจรรย์ วัด พระ เศียร ราก"),
}


def clip_mood(words, talk=True, extra=""):
    """Target (valence, arousal) and the words that decided it, from word timings ({"words": [...]}) plus on-screen text."""
    text = (" ".join(w["text"] for w in words) + " " + extra).lower(); toks = re.findall(r"[a-z']+", text)
    hits = {}
    for cat, (_, lex) in WORDS.items():
        n = 0
        for term in lex.split():
            n += toks.count(term) if term.isascii() else text.count(term)   # Thai has no spaces: count substrings
        if n: hits[cat] = n
    v, a, tot = (0.2, -0.2, 1.0) if talk else (0.4, 0.3, 1.0)               # prior: talk = light bed; music-led = upbeat
    for cat, n in hits.items(): (cv, ca), _ = WORDS[cat]; v += cv * n; a += ca * n; tot += n
    v, a = v / tot, a / tot
    if words:
        dur = max(1.0, words[-1]["end"] - words[0]["start"]); pace = len(words) / dur
        if all(w["text"].strip().isascii() for w in words[:50]): a += 0.25 * np.clip((pace - 2.6) / 1.0, -1, 1)   # fast talk: more energy
    bang = text.count("!"); a += min(0.4, 0.1 * bang); v += min(0.2, 0.05 * bang)   # exclamations: energy
    if bang: hits["!"] = bang
    if talk: a = 0.6 * a - 0.15                                               # under a voice: a bed, not a show
    return round(float(v), 2), round(float(a), 2), hits


def track_point(t):
    if t.get("moods"): pts = [MOODS[m] for m in t["moods"] if m in MOODS]; return tuple(np.mean(pts, axis=0)) if pts else (t["valence"], t["arousal"])
    return t["valence"], t["arousal"]


def scan(folder):
    folder = pathlib.Path(folder); lib_p = folder / "library.json"
    old = {t["file"]: t for t in json.load(open(lib_p, encoding="utf-8"))["tracks"]} if lib_p.exists() else {}
    credits = (folder / "CREDITS.md").read_text(encoding="utf-8").strip() if (folder / "CREDITS.md").exists() else ""
    tracks = []
    for p in sorted(folder.glob("*")):
        if p.suffix.lower() not in (".mp3", ".wav", ".m4a", ".ogg", ".flac"): continue
        f = features(p); v, a = place(f)
        t = {"file": p.name, "measured_mood": mood_of(v, a), "valence": v, "arousal": a, **f}
        if p.name in old:                                                     # keep what a person wrote
            for k in ("moods", "moods_by", "credit", "avoid"):
                if k in old[p.name]: t[k] = old[p.name][k]
        t.setdefault("credit", credits)
        tracks.append(t); print(f"{p.name[:30]:30s} measured {t['measured_mood']:10s} v{v:+.2f} a{a:+.2f}  tagged {t.get('moods', '-')}")
    json.dump({"tracks": tracks, "note": "moods = what a listener hears (wins); measured_mood = a guess from the numbers"},
              open(lib_p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("wrote", lib_p); return lib_p


AVOID_FEELS = {"Humorous", "Eerie", "Unnerving", "Aggressive", "Suspenseful", "Ren Faire", "Medieval"}
AVOID_GENRES = {"Holiday", "Polka", "Horror", "Silent Film Score", "Stings", "Musical"}


def picture_target(plan, base, pace=None):
    """What the footage asks for: feels and genres to look for, from what the clips show and how fast they change."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); import place_sound
    clips = [c for c in plan["clips"] if not c.get("card") and c.get("src")]
    kinds = []
    for c in clips[:: max(1, len(clips) // 16)]:
        src = c["src"] if pathlib.Path(c["src"]).is_absolute() else str((pathlib.Path(base) / c["src"]).resolve())
        kinds.append(place_sound.look(src, c["in"], c["out"], c.get("crop")))
    share = {k: kinds.count(k) / max(1, len(kinds)) for k in ("water", "green", "city", "night", "other")}
    scene = plan.get("scene")                                           # set by Claude after looking at the frames: beats colour rules
    if scene: share = {"cafe": {"other": 1.0}, "indoor": {"other": 1.0}, "beach": {"water": 1.0}, "water": {"water": 1.0}, "nature": {"green": 1.0},
                       "city": {"city": 1.0}, "night": {"night": 0.6, "city": 0.4}}.get(scene, share)
    durs = sorted((c["out"] - c["in"]) / c.get("speed", 1.0) for c in clips)
    pace = pace or (durs[len(durs) // 2] if durs else 2.0)            # a montage passes its planned shot length
    want_f, want_g = {"Uplifting": 1.0}, {}
    if pace < 1.3: want_f.update({"Driving": 1.5, "Bright": 1.5, "Grooving": 1.2, "Bouncy": 0.6}); bpm = (100, 135)
    else:                                                               # travel films and vlogs: soft, smooth beds (user: v3 "Lobby Time",
        want_f.update({"Relaxed": 1.6, "Calming": 1.5, "Grooving": 0.8, "Bright": 0.3}); bpm = (60, 115)   # calm jazz, "easy to keep watching")
        for f in ("Driving", "Bouncy", "Action", "Intense", "Epic"): want_f[f] = want_f.get(f, 0) - 1.0
    share = {k: share.get(k, 0.0) for k in ("water", "green", "city", "night", "other")}
    if share["city"] > 0.3: want_f["Grooving"] = want_f.get("Grooving", 0) + 0.8; want_g.update({"Jazz": 1.2, "Electronica": 0.6, "Urban": 0.5, "Funk": 0.4, "Latin": 0.4})
    if share["water"] + share["green"] > 0.3: want_f["Calming"] = want_f.get("Calming", 0) + 0.8; want_g.update({"World": 1, "Contemporary": 0.8, "Cinematic": 1, "Soundtrack": 0.6, "Classical": 0.5})
    if share.get("night", 0) > 0.3: want_f["Mysterious"] = 1.0; want_g.update({"Electronica": 1, "Jazz": 1})
    if scene in ("cafe", "indoor"): want_g.update({"Jazz": 1.5, "Latin": 1.2, "Contemporary": 0.8, "World": 0.6}); want_f["Relaxed"] = want_f.get("Relaxed", 0) + 0.8; bpm = (60, 110)
    return {"feels": want_f, "genres": want_g, "bpm": bpm, "pace": round(pace, 2), "scene": scene or {k: round(v, 2) for k, v in share.items() if v}}


def recent(lib):
    """Tracks used by the last edits (newest last), so every city clip does not get the same song."""
    p = pathlib.Path(lib) / "used.json"
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return []


def mark_used(lib, track_id, keep=8):
    p = pathlib.Path(lib) / "used.json"; u = [x for x in recent(lib) if x != track_id] + [track_id]
    json.dump(u[-keep:], open(p, "w", encoding="utf-8"))


def picture_score(t, tg):
    feels = set(t.get("feels") or []); sc = sum(w for f, w in tg["feels"].items() if f in feels)
    if t.get("id") in tg.get("recent", []): sc -= 2.0                     # used in a recent edit: let another fitting track win
    sc += tg["genres"].get(t.get("genre") or "", 0)
    sc -= 3 * len(feels & AVOID_FEELS) + (5 if t.get("genre") in AVOID_GENRES else 0)
    bpm = t.get("bpm") or t.get("bpm_measured") or 0; lo, hi = tg["bpm"]
    sc += 0.8 if lo <= bpm <= hi or lo <= bpm * 2 <= hi or lo <= bpm / 2 <= hi else -0.5
    if not feels:                                                       # untagged (Scott Buckley): measured mood, a little less trusted
        v, a = t.get("valence", 0), t.get("arousal", 0); sc += 1.5 - 1.2 * ((v - 0.35) ** 2 + (a - (0.3 if tg["pace"] < 1.3 else -0.2)) ** 2) ** 0.5
    return round(sc, 2)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) > 2 and sys.argv[1] == "_features":
        for p in sys.argv[2:]:
            f = features(p); v, a = place(f); print(f"{pathlib.Path(p).stem[:24]:24s} {mood_of(v, a):10s} v{v:+.2f} a{a:+.2f}  {f}")
        sys.exit(0)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["scan", "pick"]); ap.add_argument("target")
    ap.add_argument("--library"); ap.add_argument("--words"); ap.add_argument("--mood", choices=list(MOODS))
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--no-talk", action="store_true", help="music-led edit (montage, no speech)")
    ap.add_argument("--by-picture", action="store_true", help="choose from what the footage shows and its pace (montages, travel)")
    ap.add_argument("--top", type=int, default=3); ap.add_argument("--choose", type=int, default=1, help="with --apply: use the n-th of the ranking (after an audition)")
    ap.add_argument("--track", help="with --apply: this track (id or part of the file name) instead of the ranking")
    a = ap.parse_args()
    if a.cmd == "scan": scan(a.target); sys.exit(0)
    pp = pathlib.Path(a.target).resolve(); plan = json.load(open(pp, encoding="utf-8"))
    if not a.library:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); import sound_library; a.library = str(sound_library.library_dir())
    lib = pathlib.Path(a.library); lib_p = lib if lib.suffix == ".json" else lib / "library.json"
    if not lib_p.exists(): lib_p = scan(lib)
    tracks = json.load(open(lib_p, encoding="utf-8"))["tracks"]
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); import brand
    B = brand.load(plan, pp.parent)
    if B.get("music"): tracks = [t for t in tracks if t["file"] in B["music"]] or tracks
    tracks = [t for t in tracks if not t.get("avoid")]
    tg = None
    if a.by_picture:
        tg = picture_target(plan, pp.parent); tg["recent"] = recent(lib_p.parent); tv = ta = 0.0; hits = {}
        print(f"picture: scene {tg['scene']}, median shot {tg['pace']} s -> feels {tg['feels']}, genres {tg['genres']}, BPM {tg['bpm']}")
    elif a.mood: tv, ta = MOODS[a.mood]; hits = {"--mood": a.mood}
    else:
        words = []
        if a.words:
            from edit_plan import build_timeline
            allw = [w for w in json.load(open(a.words, encoding="utf-8"))["words"] if w.get("type", "word") == "word"]
            tl, _ = build_timeline(plan)
            words = [w for w in allw if any(c.get("src") and not c.get("card") and c["in"] <= w["start"] < c["out"] for c in plan["clips"])] or allw
        shown = [t.get("text", "") for t in plan.get("titles", [])] + [t.get("text", "") for c in plan["clips"] for t in c.get("titles", [])]
        shown += [c["card"].get("text", "") for c in plan["clips"] if c.get("card")] + [(plan.get("headline") or {}).get("text", "")]
        tv, ta, hits = clip_mood(words, talk=not a.no_talk and bool(words), extra=" ".join(map(str, shown)).replace("*", ""))
    if tg:
        ranked = sorted(tracks, key=lambda t: -picture_score(t, tg))
    else:
        print(f"edit mood: valence {tv:+.2f}, arousal {ta:+.2f} -> {mood_of(tv, ta)}   (topic words: {hits or 'none'})")
        ranked = sorted(tracks, key=lambda t: (track_point(t)[0] - tv) ** 2 + (track_point(t)[1] - ta) ** 2 + (2 if set(t.get("feels") or []) & AVOID_FEELS else 0))
    for k, t in enumerate(ranked[:a.top]):
        v, ar = track_point(t)
        tags = ", ".join(t.get("feels") or []) or (t.get("measured_mood", "?") + " (measured)")
        print(f"  {k + 1}. {t.get('title', t['file'])[:34]:34s} [{t.get('genre') or '-'}] {tags[:40]:40s} {t.get('bpm')} BPM" + (f"  score {picture_score(t, tg)}" if tg else ""))
    if a.apply and ranked:
        t = ranked[min(len(ranked), max(1, a.choose)) - 1]
        if a.track: t = next((x for x in tracks if a.track in (x.get("id") or "") or a.track.lower() in x["file"].lower()), t)
        src = (lib_p.parent / t["file"]).resolve(); mark_used(lib_p.parent, t.get("id") or t["file"])
        try: rel = str(src.relative_to(pp.parent)).replace("\\", "/")
        except ValueError: rel = str(src).replace("\\", "/")
        old = [x for x in plan.get("audio", []) if x.get("role") == "music"]
        keep = {k: old[0][k] for k in ("start", "end", "fade_in", "fade_out", "loop") if old and k in old[0]}
        plan["audio"] = [x for x in plan.get("audio", []) if x.get("role") != "music"] + [{"src": rel, "role": "music", "in": t.get("intro_s", 0), **keep, "mood_pick": True}]
        json.dump(plan, open(pp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(f"music -> {t['file']} (from {t.get('intro_s', 0)} s); credit: {t.get('credit', '')[:90]}")
