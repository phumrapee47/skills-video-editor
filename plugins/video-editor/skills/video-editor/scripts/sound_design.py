"""Automatic sound design for an edit plan: put whooshes, pops, risers and impacts where the picture already changes.

Usage: python -I sound_design.py <plan.json> [--kit sfx_dir] [--level 0] [--punch] [--dry]
  --kit    folder with the sound files (default: <plan dir>/sfx, made by make_sfx.py if missing; your own files with
           the same names - whoosh, swish, pop, riser, impact, hit, chime .wav - replace the generated ones)
  --level  dB added to every effect (-3 = quieter); --punch also marks punch-in zooms with a faint swish
  --dry    print the events, change nothing
  A brand kit in the plan ("brand") adds its "sfx_level" and its end card's chime; "sfx": false turns effects off.
Writes the effects into plan["audio"] as role "sfx" with "rel_db" (level against the speech, see edit_plan.py) and
"sd": true, so a rerun replaces only its own events. Rules (podcast/reference study + common short-form practice):
  topic card: riser into the first answer, a pop as each item lands; titles and the headline: a pop on entrance;
  transition (xfade): whoosh peaking on the middle; B-roll: whoosh in, swish out; word behind the person: impact;
  text card: hit; last card: chime (dissolves under 0.3 s only smooth a cut: silent). Effects under speech are 4 dB
  lower; at most one effect per 0.8 s (pops of a list: 0.35 s)
  (impact > riser > hit > whoosh > chime > pop > swish).
"""
import argparse, json, pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from edit_plan import build_timeline
import make_sfx

LEVEL = {"clink": -15, "slash": -12, "splash": -9, "fizz": -10, "whoosh": -13, "swish": -20, "pop": -17, "riser": -13, "impact": -9, "hit": -11, "chime": -15}   # RMS vs speech
PEAK = {"clink": 0.0, "slash": 0.18, "splash": 0.02, "fizz": 0.0, "whoosh": 0.30, "swish": 0.11, "pop": 0.0, "riser": 1.6, "impact": 0.0, "hit": 0.0, "chime": 0.0}  # s from file start to its hit
RANK = ["splash", "slash", "fizz", "clink", "impact", "riser", "hit", "whoosh", "chime", "pop", "swish"]


def events(plan):
    tl, total = build_timeline(plan); ev = []
    def add(kind, t, why): ev.append({"kind": kind, "t": round(t, 3), "why": why})
    for it in plan.get("titles", []):
        s = float(it["start"])
        if "items" in it:
            add("pop", s + 0.25, "topic card heading")
            for i, _ in enumerate(it["items"]): add("pop", s + 0.55 + i * float(it.get("stagger", 0.45)) + 0.2, f"topic item {i + 1}")
            add("riser", float(it["end"]), "into the first answer")
        else: add("pop", s, "title")
    hl = plan.get("headline")
    if hl: add("pop", float(hl.get("start", 0.0)) + 0.05, "headline")
    for k, c in enumerate(tl):
        if c.get("tdur", 0) >= 0.3 and k:                      # a 0.1 s dissolve only smooths a cut: no sound
            tr = c.get("trans"); add("whoosh", c["start"] + c["tdur"] / 2, f"transition {tr.get('type') if isinstance(tr, dict) else tr}")
        if c.get("card"):
            add("chime" if k == len(tl) - 1 else "hit", c["start"] + (1.0 if k == len(tl) - 1 else 0.0), "card")   # chime after the fade whoosh
            continue
        for it in c.get("titles", []): add("pop", c["start"] + float(it["start"]), "clip title")
        for b in c.get("broll", []):
            add("whoosh", c["start"] + float(b["start"]), "B-roll in")
            if float(b["end"]) < c["end"] - c["start"] - 0.2: add("swish", c["start"] + float(b["end"]), "B-roll out")
        for b in c.get("behind", []): add("impact", c["start"] + float(b["start"]) + 0.05, f"behind word {b['text']}")
    return ev, tl, total


def talk_spans(plan, tl):
    """Speech in timeline time from the plan's subtitles (.ass/.srt) when present."""
    sub = (plan.get("subtitles") or {}).get("src")
    if not sub: return []
    p = pathlib.Path(plan["_dir"]) / sub
    if not p.exists(): return []
    txt = p.read_text(encoding="utf-8", errors="replace"); out = []
    def sec(x): h, m, r = x.replace(",", ".").split(":"); return int(h) * 3600 + int(m) * 60 + float(r)
    for a, b in re.findall(r"Dialogue: \d+,(\d+:\d+:\d+\.\d+),(\d+:\d+:\d+\.\d+)", txt): out.append((sec(a), sec(b)))
    for a, b in re.findall(r"(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)", txt): out.append((sec(a), sec(b)))
    return out


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan"); ap.add_argument("--kit"); ap.add_argument("--level", type=float, default=0.0)
    ap.add_argument("--punch", action="store_true"); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    pp = pathlib.Path(a.plan).resolve(); plan = json.load(open(pp, encoding="utf-8")); plan["_dir"] = str(pp.parent)
    plan["audio"] = [x for x in plan.get("audio", []) if not x.get("sd")]
    import brand
    B = brand.load(plan, pp.parent)
    if B.get("sfx") is False: print("brand kit: no sound effects"); json.dump({k: v for k, v in plan.items() if k != "_dir"}, open(pp, "w", encoding="utf-8"), indent=1, ensure_ascii=False); sys.exit(0)
    a.level += float(B.get("sfx_level", 0))
    probe = json.loads(json.dumps(plan)); brand.apply_end_card(probe, B)   # the end card edit_plan.py will add gets its chime
    ev, tl, total = events(probe)
    if a.punch:
        full = max((c["crop"][2] for c in tl if c.get("crop")), default=0)
        for c in tl:
            if c.get("crop") and c["crop"][2] < 0.9 * full: ev.append({"kind": "swish", "t": c["start"], "why": "punch-in"})
    talk = talk_spans(plan, tl)
    kept = []                                                 # one effect per 0.8 s, the stronger kind wins
    for e in sorted(ev, key=lambda e: (RANK.index(e["kind"]), e["t"])):
        gap = lambda k: 0.35 if e["kind"] == k["kind"] == "pop" else 0.8     # topic items pop 0.45 s apart
        if 0 <= e["t"] <= total and all(abs(e["t"] - k["t"]) >= gap(k) for k in kept): kept.append(e)
    kept.sort(key=lambda e: e["t"])
    kit = pathlib.Path(a.kit).resolve() if a.kit else pp.parent / "sfx"
    files = make_sfx.make(kit) if not a.dry else {}
    for e in kept:
        under = any(s - 0.1 <= e["t"] <= t + 0.1 for s, t in talk)
        e["rel_db"] = LEVEL[e["kind"]] + a.level - (4 if under else 0)
        print(f"{e['t']:7.2f}s  {e['kind']:7s} {e['rel_db']:+5.0f} dB{'  (under speech)' if under else ''}  {e['why']}")
        if a.dry: continue
        start = max(0.0, e["t"] - PEAK[e["kind"]])
        cut = PEAK[e["kind"]] - (e["t"] - start)                  # an effect at the very start loses its lead-in
        item = {"src": str(pathlib.Path(files[e["kind"]]).resolve().relative_to(pp.parent)) if pathlib.Path(files[e["kind"]]).resolve().is_relative_to(pp.parent) else str(files[e["kind"]]),
                "role": "sfx", "start": round(start, 3), "rel_db": e["rel_db"], "sd": True, "why": e["why"]}
        if cut > 0.005: item["in"] = round(cut, 3)
        plan["audio"].append(item)
    print(f"{len(kept)} effects ({len(ev) - len(kept)} dropped as too close) over {total:.1f} s")
    plan.pop("_dir", None)
    if not a.dry: json.dump(plan, open(pp, "w", encoding="utf-8"), indent=1, ensure_ascii=False); print("wrote", pp.name)
