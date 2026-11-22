"""Product ad / UGC ad from raw product footage: hook -> product name -> features -> price -> call to action.
Built on montage.py (best moments, cuts in beats, music chosen from the pictures), then the ad layer on top.

Usage: python -I product_ad.py <out_plan.json> --src a.mp4 [b.mp4] --name "LENS | RENT" --hook "Your next shoot starts here"
         [--features "Fast prime lens@0.45,0.55" "Weather sealed@0.62,0.7"] [--price "from 299 THB / day"]
         [--cta "Book now"] [--handle "@lensrent"] [--size 1080x1920] [--length 20] [--music auto|file] [--logo b]
         [--scene indoor] [--grade clean] [--brand brand.json] [--sub-lines "line" ...]
Structure from the ad study (references/ad-ugc.md): a striking product shot under a big hook line in the first 2 s;
the name as a split title (WORD | WORD with an accent bar); features as callouts (a thin line from the part of the
product to a spaced label; Claude sets each point after LOOKING at the frames: "text@x,y" as fractions of the frame);
price big in the accent colour; an end card with the CTA and handle (or the brand kit's end card). Promo cutting
(1-2 beats), effects by sound_design.py (pops on titles, whoosh into the card), -14 LUFS (ads run loud).
Use only the user's own product and brand names; never present another company's product as theirs.
"""
import argparse, json, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out"); ap.add_argument("--src", nargs="+", required=True); ap.add_argument("--name", required=True); ap.add_argument("--hook", required=True)
    ap.add_argument("--features", nargs="*", default=[]); ap.add_argument("--price"); ap.add_argument("--cta", default="Shop now"); ap.add_argument("--handle", default="")
    ap.add_argument("--size", default="1920x1080"); ap.add_argument("--length", type=float, default=20); ap.add_argument("--music", default="auto")
    ap.add_argument("--logo", nargs="*", default=[]); ap.add_argument("--scene"); ap.add_argument("--grade", default="clean"); ap.add_argument("--brand")
    ap.add_argument("--style", choices=["promo", "film"], default="promo", help="promo: 1-2 beat cuts (most ads); film: slower, for premium products")
    ap.add_argument("--lufs", type=float, default=-14.0); ap.add_argument("--skip", nargs="*", default=[], help="source ranges to leave out (title cards, talk): a-b or N:a-b")
    a = ap.parse_args()
    out = pathlib.Path(a.out).resolve(); W, H = map(int, a.size.split("x")); vert = H > W
    card = 2.6
    cmd = [sys.executable, "-I", str(HERE / "montage.py"), str(out), "--src", *a.src, "--style", a.style, "--length", str(a.length - card + 0.3),
           "--size", a.size, "--music", a.music, "--grade", a.grade, "--lufs", str(a.lufs), "--no-place"]
    if a.logo: cmd += ["--logo", *a.logo]
    cmd += ["--scene", a.scene or "product"]
    if a.skip: cmd += ["--skip", *a.skip]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode: sys.exit(r.stderr[-800:])
    print("\n".join(l for l in r.stdout.splitlines() if "music" in l or "shots from" in l))
    plan = json.load(open(out, encoding="utf-8"))
    clips = plan["clips"]; starts, t = [], 0.0
    for c in clips:
        td = c.get("transition", {}).get("dur", 0.0); starts.append(t - td); t += (c["out"] - c["in"]) - td
    for c in clips: c["volume_db"] = -90                                  # product b-roll sound is handling noise: music and effects carry the ad
    titles = [{"text": a.hook, "start": 0.15, "end": min(2.4, starts[min(2, len(starts) - 1)] + 0.2), "pos": "center", "y": 0.42 if vert else 0.45,
               "anim": "punch", "size": round(H * (0.06 if vert else 0.095))}]
    k = min(2, len(clips) - 1); s0 = starts[k] + 0.1
    titles.append({"text": a.name, "style": "split", "start": round(s0, 2), "end": round(s0 + 2.2, 2), "y": 0.3 if vert else 0.25,
                   "size": round(H * (0.08 if vert else 0.12))})
    sides = [(0.42, 0.58), (0.6, 0.66), (0.4, 0.72), (0.58, 0.5)]
    last = len(clips) - 1                                                # the last shot carries the price, nothing else
    slots = [j for j in range(k + 1, last) if clips[j]["out"] - clips[j]["in"] >= 0.9][::2] or list(range(k + 1, last))
    for i, f in enumerate(a.features):                                   # one feature per shot, between the name and the price
        if i >= len(slots): break
        text, at = (f.rsplit("@", 1) + [None])[:2]
        pt = [float(v) for v in at.split(",")] if at else list(sides[i % len(sides)])
        j = slots[i]; s1 = starts[j] + 0.1; d = max(1.0, min(1.8, clips[j]["out"] - clips[j]["in"] - 0.15))   # short: the product moves
        titles.append({"text": text.strip(), "style": "callout", "at": pt, "start": round(s1, 2), "end": round(s1 + d, 2), "clip": j})
    if a.price:
        s2 = starts[last] + 0.1
        titles.append({"text": a.price, "start": round(s2, 2), "end": round(t - 0.05, 2), "pos": "center", "y": 0.62 if vert else 0.72, "anim": "pop",
                       "size": round(H * (0.045 if vert else 0.065)), "color": [255, 210, 0]})
    plan["titles"] = titles
    plan["clips"].append({"card": {"text": f"{a.cta}" + (f"\n**{a.handle}**" if a.handle else ""), "bg": "0x0c0c0c", "size": round(H * (0.065 if vert else 0.095))},
                          "in": 0, "out": card, "transition": {"type": "fade", "dur": 0.3}})
    if a.brand: plan["brand"] = str(pathlib.Path(a.brand).resolve())
    for m in plan["audio"]:
        if m.get("role") == "music": m["end"] = round(t + card - 0.3, 2); m["fade_out"] = 1.2
    json.dump(plan, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    subprocess.run([sys.executable, "-I", str(HERE / "sound_design.py"), str(out)], check=True, capture_output=True)
    print(f"ad plan: {len(clips)} shots + end card, {t + card - 0.3:.1f} s, {len(a.features)} callouts -> {out.name}")
    for ti in titles:                                                    # Claude looks at these frames and sets each callout point ("at")
        if ti.get("style") == "callout":
            c = clips[ti["clip"]]; mid = c["in"] + (ti["start"] + ti["end"]) / 2 - starts[ti["clip"]]
            print(f"  callout '{ti['text']}' {ti['start']}-{ti['end']} s: shot {ti['clip']} source {pathlib.Path(c['src']).name[:30]} at {mid:.2f} s (check the point)")
