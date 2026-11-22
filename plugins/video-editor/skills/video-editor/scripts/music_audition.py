"""Music audition: the same stretch of an edit with the top few tracks, one after another, labelled A, B, C, D, so a
person chooses by ear (Claude cannot hear; tags and numbers only shortlist).

Usage: python -I music_audition.py <plan.json> [--top 4] [--seconds 20] [--start 0] [--by-picture | --words w.json] [--library DIR]
  -> <plan stem>_audition.mp4 (half size) and <plan stem>_audition.json (A -> track). Then:
     python -I music_mood.py pick plan.json --apply --track <id of the liked letter, in the .json>
Each candidate gets the whole edit's sound design (place sounds, ducking, loudness), so it is judged as it will be heard.
"""
import argparse, json, pathlib, shutil, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan"); ap.add_argument("--top", type=int, default=4); ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--start", type=float, default=0); ap.add_argument("--by-picture", action="store_true"); ap.add_argument("--brief"); ap.add_argument("--words"); ap.add_argument("--library")
    a = ap.parse_args()
    import music_mood, sound_library
    from fonts import font
    pp = pathlib.Path(a.plan).resolve(); plan = json.load(open(pp, encoding="utf-8"))
    lib = pathlib.Path(a.library) if a.library else sound_library.library_dir()
    tracks = json.load(open(lib / "library.json", encoding="utf-8"))["tracks"]
    tracks = [t for t in tracks if (lib / t["file"]).exists()]
    if a.brief:
        tg = dict(music_mood.BRIEFS[a.brief]); tg["recent"] = music_mood.recent(lib); ranked = sorted(tracks, key=lambda t: -music_mood.picture_score(t, tg))
        print(f"mood brief: {a.brief}")
    elif a.by_picture or not a.words:
        tg = music_mood.picture_target(plan, pp.parent); ranked = sorted(tracks, key=lambda t: -music_mood.picture_score(t, tg))
        print(f"picture: {tg['scene']}, median shot {tg['pace']} s")
    else:
        words = json.load(open(a.words, encoding="utf-8"))["words"]; tv, ta, _ = music_mood.clip_mood(words)
        ranked = sorted(tracks, key=lambda t: (music_mood.track_point(t)[0] - tv) ** 2 + (music_mood.track_point(t)[1] - ta) ** 2)
    picks, seen = [], set()
    for t in ranked:                                                     # one per genre where possible: a real choice
        if len(picks) >= a.top: break
        if t.get("genre") in seen and len(ranked) > a.top * 3: continue
        seen.add(t.get("genre")); picks.append(t)
    fontfile = font("sans")[1].replace("\\", "/").replace(":", "\\:")
    parts, legend = [], {}
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        for k, t in enumerate(picks):
            L = "ABCDEFGH"[k]; p2 = json.loads(json.dumps(plan))
            old = [x for x in p2.get("audio", []) if x.get("role") == "music"]
            keep = {key: old[0][key] for key in ("start", "end", "fade_in", "fade_out") if old and key in old[0]}
            p2["audio"] = [x for x in p2.get("audio", []) if x.get("role") != "music"] + [{"src": str((lib / t["file"]).resolve()), "role": "music", "in": t.get("intro_s", 0), **keep}]
            for c in p2["clips"]:
                if not c.get("card") and not pathlib.Path(c["src"]).is_absolute(): c["src"] = str((pp.parent / c["src"]).resolve())
            for x in p2["audio"]:
                if not pathlib.Path(x["src"]).is_absolute(): x["src"] = str((pp.parent / x["src"]).resolve())
            if p2.get("subtitles") and not pathlib.Path(p2["subtitles"]["src"]).is_absolute(): p2["subtitles"]["src"] = str((pp.parent / p2["subtitles"]["src"]).resolve())
            if isinstance(p2.get("brand"), str): p2["brand"] = str((pp.parent / p2["brand"]).resolve())
            p2["output"]["path"] = str(td / f"{L}.mp4"); q = td / f"{L}.json"; json.dump(p2, open(q, "w", encoding="utf-8"))
            r = subprocess.run([sys.executable, "-I", str(HERE / "edit_plan.py"), str(q), "--preview", str(a.start), str(a.start + a.seconds), "--no-qa"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            prev = td / f"{L}_preview_{a.start:g}-{a.start + a.seconds:g}.mp4"
            if r.returncode or not prev.exists(): print("FAIL", t["title"], r.stderr[-300:]); continue
            tags = (", ".join(t.get("feels") or []) or t.get("measured_mood", ""))[:40]
            label = f"{L}  {t['title'][:30]}  [{t.get('genre') or '-'}] {tags}".replace(":", " ").replace("'", "")
            out = td / f"{L}_lab.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(prev), "-vf", f"drawtext=fontfile='{fontfile}':text='{label}':fontsize=h/22:fontcolor=white:borderw=3:x=20:y=20",
                            "-c:v", "libx264", "-crf", "23", "-c:a", "aac", "-b:a", "160k", str(out)], check=True)
            parts.append(out); legend[L] = {"rank": k + 1, "id": t.get("id"), "title": t["title"], "file": t["file"], "genre": t.get("genre"), "feels": t.get("feels"), "credit": t.get("credit")}
            print(f"  {L}: {t['title']} [{t.get('genre')}] {tags}")
        lst = td / "list.txt"; lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
        out = pp.with_name(pp.stem + "_audition.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], check=True)
    json.dump(legend, open(pp.with_name(pp.stem + "_audition.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"wrote {out.name}: {len(parts)} versions of {a.seconds:g} s; after a choice: music_mood.py pick {pp.name} --apply --track <id>")
    for L, v in legend.items(): print(f"    {L} = {v['id']}")
