"""Several Shorts from one long talk/podcast: pick the N best self-contained threads, then run podcast_short.py for
each, with every approval collected in one editable file (<workdir>/batch.json).

Usage: python -I podcast_batch.py <source.mp4> <workdir> [--count 5] [--length 40] [--words words.json] [--lang en]
                                  [--music bed.mp3] [--context topic] [--platform all|tiktok|reels|shorts]
Run 1  picks the threads (best first, never overlapping) and writes batch.json; prints each one's lines.
       Write a title (and 2-3 topics, a context word) for each clip you want, in batch.json - or ask Claude to draft
       them from the lines; drop a clip with "skip": true.
Run 2+ runs every clip with a title one step further and prints where each one waits:
         B-roll  -> set "broll_pick": ["1a", "2b"] (or "no_broll": true) for that clip in batch.json, rerun
         preview -> look at clipN/short_preview_0-12.mp4, set "final": true, rerun
       Finished clips are clipN/short.mp4 with their QA and safe-zone sheets.
"""
import argparse, json, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source"); ap.add_argument("workdir"); ap.add_argument("--count", type=int, default=5); ap.add_argument("--length", type=float, default=40)
    ap.add_argument("--words"); ap.add_argument("--lang", default="en"); ap.add_argument("--music"); ap.add_argument("--context", default="")
    ap.add_argument("--platform", default="all")
    a = ap.parse_args()
    wd = pathlib.Path(a.workdir).resolve(); wd.mkdir(parents=True, exist_ok=True); src = pathlib.Path(a.source).resolve()
    bp = wd / "batch.json"
    saved = json.load(open(bp, encoding="utf-8")) if bp.exists() else {}
    words_path = pathlib.Path(a.words).resolve() if a.words else pathlib.Path(saved.get("words", wd / "words.json"))   # reruns reuse the saved transcript
    if not words_path.exists():
        print("transcript (Whisper medium, local)")
        subprocess.run([sys.executable, "-I", str(HERE / "transcribe_whisper.py"), str(src), str(wd / "words"), "--lang", a.lang], check=True)
    if not bp.exists():
        from podcast_short import pick_segments, clean
        from word_captions import STOP
        words = [w for w in json.load(open(words_path, encoding="utf-8"))["words"] if w.get("type", "word") == "word"]
        topic = tuple(clean(x)[:5] for x in a.context.split() if len(clean(x)) > 3)
        threads = pick_segments(words, a.length, STOP, topic, count=a.count)
        threads.sort(key=lambda t: t[0][0])
        batch = {"source": str(src), "words": str(words_path), "music": a.music, "platform": a.platform,
                 "clips": [{"id": k + 1, "segments": [f"{s}-{e}" for s, e, _ in t], "seconds": round(sum(e - s for s, e, _ in t), 1),
                            "lines": [x for _, _, x in t], "title": "", "tag": "", "topics": [], "context": a.context} for k, t in enumerate(threads)]}
        json.dump(batch, open(bp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        for c in batch["clips"]:
            print(f"\nclip {c['id']}  ({c['seconds']} s, {c['segments'][0].split('-')[0]} s into the source)")
            for x in c["lines"]: print("   ", x[:110])
        print(f"\n[batch gate] write a title (and topics) for each clip in {bp}, or ask Claude to draft them; then rerun"); sys.exit(0)
    batch = json.load(open(bp, encoding="utf-8")); status = []
    for c in batch["clips"]:
        if c.get("skip") or not c.get("title"): status.append((c["id"], "no title yet" if not c.get("skip") else "skipped")); continue
        cw = wd / f"clip{c['id']}"
        cmd = [sys.executable, "-I", str(HERE / "podcast_short.py"), batch["source"], str(cw), "--title", c["title"], "--tag", c.get("tag", ""),
               "--context", c.get("context", ""), "--words", batch["words"], "--segments", *c["segments"]]
        if c.get("topics"): cmd += ["--topics", *c["topics"]]
        if batch.get("music"): cmd += ["--music", batch["music"]]
        if c.get("no_broll"): cmd += ["--no-broll"]
        elif c.get("broll_pick") is not None: cmd += ["--broll-pick", *c["broll_pick"]]
        if c.get("final"): cmd += ["--final"]
        if (cw / "short.mp4").exists() and c.get("final"): status.append((c["id"], f"done: {cw / 'short.mp4'}")); continue
        print(f"\n===== clip {c['id']}: {c['title'].splitlines()[0]}")
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"); out = r.stdout + r.stderr
        print("\n".join(l for l in out.splitlines() if l.startswith(("[gate", "   ", "[final", "done", "RESULT", "WARN", "FAIL")) or "covered area" in l)[-2500:])
        if r.returncode: status.append((c["id"], "ERROR (see output above)"))
        elif "[gate 2]" in out: status.append((c["id"], 'waiting: B-roll - set "broll_pick" or "no_broll"'))
        elif "[gate 3]" in out: status.append((c["id"], f'waiting: preview {cw / "short_preview_0-12.mp4"} - set "final": true'))
        elif "done:" in out: status.append((c["id"], f"done: {cw / 'short.mp4'}"))
        else: status.append((c["id"], "check output"))
    print("\n== batch status ==")
    for i, s in status: print(f"  clip {i}: {s}")
