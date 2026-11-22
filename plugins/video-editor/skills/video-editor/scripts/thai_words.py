"""Thai words with timings, for word captions (Thai has no spaces between words).

Usage: python -I thai_words.py <transcript.json> <out_words.json> [--script lines.json|lines.txt] [--engine newmm]
  transcript.json  Scribe diarization JSON (Creative Claw `transcribe`, one Thai character per entry) or any
                   {"words": [{text, start, end}]} with character or syllable timings
  --script         the known text (correct spelling): it is cut into words and timed against the transcript
                   characters (align_script.py's matcher); without it the transcript's own text is cut into words
Writes {"words": [{"text", "start", "end", "type": "word", "line"}]} - the format word_captions.py, pick_moments.py and
edit plans read. Needs pythainlp (pip install pythainlp: ask first); newmm needs no model download.
"""
import argparse, difflib, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def char_times(tr):
    out = []
    for w in tr["words"]:
        if w.get("type", "word") != "word": continue
        t = w["text"].replace(" ", ""); n = len(t)
        for k, c in enumerate(t): out.append((c, w["start"] + (w["end"] - w["start"]) * k / n, w["start"] + (w["end"] - w["start"]) * (k + 1) / n))
    return out


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript"); ap.add_argument("out"); ap.add_argument("--script"); ap.add_argument("--engine", default="newmm")
    a = ap.parse_args()
    from pythainlp.tokenize import word_tokenize
    ch = char_times(json.load(open(a.transcript, encoding="utf-8"))); hyp = "".join(c for c, _, _ in ch)
    if a.script:
        p = pathlib.Path(a.script)
        lines = json.load(open(p, encoding="utf-8")) if p.suffix == ".json" else [l.strip() for l in open(p, encoding="utf-8") if l.strip()]
    else:
        lines = [hyp]
    ref, pos = "", []                                       # every non-space script character -> (line, word, char)
    toks = []
    for li, line in enumerate(lines):
        words = [w for w in word_tokenize(line, engine=a.engine, keep_whitespace=False) if w.strip()]
        toks.append(words)
        for wi, w in enumerate(words):
            for ci, c in enumerate(w):
                if c != " ": ref += c; pos.append((li, wi))
    t_of = {}
    for x, y, n in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_matching_blocks():
        for k in range(n): t_of.setdefault(pos[x + k], []).append(ch[y + k][1:])
    out, last = [], 0.0
    for li, words in enumerate(toks):
        for wi, w in enumerate(words):
            tt = t_of.get((li, wi))
            if tt: s, e = min(t[0] for t in tt), max(t[1] for t in tt)
            else: s = e = last                             # not heard: zero length right after the previous word (filled below)
            out.append({"text": w, "start": round(s, 3), "end": round(e, 3), "type": "word", "line": li}); last = e
    for k, w in enumerate(out):                             # give unheard words a share of the gap to the next heard word
        if w["end"] <= w["start"]:
            nxt = next((x["start"] for x in out[k + 1:] if x["end"] > x["start"]), w["start"] + 0.2)
            w["end"] = round(min(nxt, w["start"] + 0.25), 3)
    json.dump({"language": "th", "words": out}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"{len(out)} words from {len(lines)} line(s); first: " + " | ".join(f"{w['text']} {w['start']:.2f}" for w in out[:8]))
