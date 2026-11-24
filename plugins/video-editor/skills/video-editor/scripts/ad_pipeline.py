"""3D product ad from one shot list, with approval gates: concept -> storyboard -> animatic -> preview -> final.

Usage:
  python -I ad_pipeline.py init <dir> --brief-file brief.json          (everything from the brief, see below)
  python -I ad_pipeline.py init <dir> --product "yuzu sparkling can" (--label label.png | --photo front.jpg [--back b.jpg]
         | --product-json product.json | --shape bottle|pouch|box|bar) [--label-front 0.25] [--alt a.png b.png]
         [--fruit yuzu] [--set "#FFC21C" "#FF8A1E"] [--brief fresh] [--track happy-alley] [--fps 24] [--length 15]
         [--card "Taste the bright side" --handle @brand]
  then Claude checks the copy and adjusts the shots in <dir>/shots.json (titles, beats, camera paths, cold)
brief.json: {"product": "what it is", "photo": "front.jpg", "back": "back.jpg", "shape": "auto", "family": "fresh",
  "length_s": 15, "fps": 24, "fruit": "yuzu", "audience": "...", "usp": "...", "platforms": ["tiktok", "reels"],
  "copy": {"hook": "Sunshine", "details": ["ice cold", "crack it open"], "payoff": "...", "name": "LUMA | YUZU",
  "price": "45 THB", "cta": "Taste the bright side"}, "handle": "@brand", "track": "happy-alley",
  "board": ["split", "macro", "crown", "hero_low"]}   (optional: pick the shots; default: the concept's board)
  Only the user's approved claims go into "copy"; the storyboard shows every line for approval.
  python -I ad_pipeline.py run <dir>              run the next stage; it stops at its gate
  python -I ad_pipeline.py run <dir> --approve    the user approved what the last stage showed: go on
  python -I ad_pipeline.py status <dir>

Stages (each gate needs the user's yes, passed on with --approve):
  board     one still per shot at its key frame -> board.jpg with shot, length in beats, event, title, sound
  animatic  every shot small and fast (360x640, 4 samples), cut to the music with titles and sound -> animatic.mp4
  preview   full size EEVEE -> preview.mp4 + QA + safe zones
  final     first a one-frame Cycles test -> time estimate (gate); then Cycles on the GPU, resumable -> final.mp4
Timing: the music is chosen at init (mood family brief, or --track), its beat grid measured (music_beats.py); every shot
lasts a whole number of beats ("beats") and its physical event (the slash, the tab snap, the burst) lands on a beat
("event_beat", counted from the shot start). The music starts on a beat. Change those numbers and rerun the stage.
shots.json per shot: id, type, beats, event_beat, cold, camera ({"from","to","look","look_to","lens","fstop"}),
title ({"text","style",...,"at": s from the shot start}), sfx ([{"sound","at": "event"|"start","offset","rel_db"}]).
"""
import argparse, glob, json, math, os, pathlib, shutil, subprocess, sys, time

SC = pathlib.Path(__file__).resolve().parent; ROOT = SC.parent
sys.path.insert(0, str(SC))
PY = [sys.executable, "-I"]
STAGES = ["board", "animatic", "preview", "final_test", "final", "done"]
SECONDS = {"crown": 2.8, "twist": 2.8, "tear": 2.8, "snap": 3.2, "split": 4.0, "open": 2.5, "toppop": 2.5, "drops": 2.4, "zerog": 3.2, "hero_low": 3.0, "burst": 2.5, "macro": 2.0,
           "hero": 2.5, "trio": 3.2, "reveal": 2.5}
EVENT_S = {"crown": 0.8, "twist": 1.0, "tear": 0.92, "snap": 1.0, "split": 1.0, "open": 0.73, "toppop": 0.73, "drops": 0.6, "burst": 0.07}         # when the physical event happens
COLD = {"drops", "zerog", "hero_low"}
SFX = {"crown": [("whoosh", "event", -0.5, -16), ("splash", "event", 0.0, -8)], "twist": [("twist", "event", -0.45, -11), ("fizz", "event", 0.0, -13)], "tear": [("rip", "event", -0.25, -9)], "snap": [("snap", "event", 0.0, -8)],
       "split": [("slash", "event", -0.33, -11), ("splash", "event", -0.02, -8)], "open": [("fizz", "event", -0.03, -7)],
       "toppop": [("fizz", "event", -0.03, -7)], "burst": [("splash", "event", 0.0, -10)],
       "zerog": [("clink", "start", 0.45, -15), ("clink", "start", 1.6, -18)], "hero_low": [("hit", "start", 1.6, -17)]}


def blender_exe():
    return os.environ.get("BLENDER") or shutil.which("blender") or next(iter(sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender *\blender.exe"))[::-1]), None)


def load(d): return json.load(open(pathlib.Path(d) / "shots.json", encoding="utf-8"))


def save(d, st): json.dump(st, open(pathlib.Path(d) / "shots.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def run(cmd, **kw):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode: sys.exit(f"failed: {' '.join(map(str, cmd))[:200]}\n{(r.stderr or r.stdout)[-1500:]}")
    return r.stdout


# ---------------------------------------------------------------- init
SHOT_NEEDS = {"open": "can", "toppop": "can", "drops": "can", "trio": "can", "twist": "bottle", "tear": "pouch", "snap": "bar"}
STYLE = {   # title look per mood family and beat role (references/ad-3d.md)
    "fresh":  {"hook": {"style": "echo", "y": 0.24, "repeat": 2, "size": 260, "dir": "up", "at": 1.2}, "detail": {"style": "spaced", "y": 0.16, "size": 92, "at": 0.25},
               "payoff": {"style": "spaced", "y": 0.1, "size": 76, "at": 0.8}, "name": {"style": "split", "y": 0.15, "size": 190, "at": 0.4}},
    "luxury": {"hook": {"style": "spaced", "y": 0.2, "size": 64, "at": 1.0}, "detail": {"style": "spaced", "y": 0.14, "size": 56, "at": 0.4},
               "payoff": {"style": "spaced", "y": 0.12, "size": 56, "at": 0.8}, "name": {"style": "spaced", "y": 0.15, "size": 110, "at": 0.5}},
    "tech":   {"hook": {"style": "big", "y": 0.18, "size": 220, "anim": "pop", "at": 0.6}, "detail": {"style": "spaced", "y": 0.14, "size": 70, "at": 0.25},
               "payoff": {"style": "big", "y": 0.12, "size": 160, "anim": "pop", "at": 0.6}, "name": {"style": "big", "y": 0.15, "size": 200, "anim": "pop", "at": 0.4}},
    "clean":  {"hook": {"style": "spaced", "y": 0.18, "size": 70, "at": 1.0}, "detail": {"style": "spaced", "y": 0.14, "size": 60, "at": 0.4},
               "payoff": {"style": "spaced", "y": 0.12, "size": 60, "at": 0.8}, "name": {"style": "spaced", "y": 0.15, "size": 100, "at": 0.5}}}
PRESETS = {"bottle": {"shape": "bottle", "liquid": "#9CB84A", "cap": "#2E6B30", "fill": 0.9}, "pouch": {"shape": "pouch", "size_mm": [180, 250, 70]},
           "box": {"shape": "box", "size_mm": [190, 270, 60]}, "bar": {"shape": "bar", "size_mm": [120, 32, 18], "coating": "#4A2615", "filling": "#C8741E"}}


def emboss_image(d, word, blocks=4):
    """White letters on black, once per block of the bar (the bar's top UV runs along its length)."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = 2048, 512; im = Image.new("L", (W, H), 0); dr = ImageDraw.Draw(im)
    fonts = sorted((ROOT / "assets" / "fonts").glob("Anton*.ttf")); f = ImageFont.truetype(str(fonts[0]), 200) if fonts else ImageFont.load_default()
    for b in range(blocks):
        cx = (b + 0.5) * W / blocks; dr.text((cx, H / 2), word.upper()[:8], fill=255, font=f, anchor="mm")
    from PIL import ImageFilter
    im = im.filter(ImageFilter.GaussianBlur(4))                            # soft edges: a moulded letter, not a cut-out
    out = d / "emboss.png"; im.save(out); return out


def from_brief(a):
    """Fill the init arguments from a brief file (the brief wins over defaults, flags win over the brief)."""
    b = json.load(open(a.brief_file, encoding="utf-8")); base = pathlib.Path(a.brief_file).resolve().parent
    rel = lambda x: str((base / x).resolve()) if x and not os.path.isabs(x) else x
    if b.get("label_metal") and not getattr(a, "label_metal", None): a.label_metal = b["label_metal"]
    for k, attr in (("product", "product"), ("photo", "photo"), ("back", "back"), ("label", "label"), ("fruit", "fruit"), ("track", "track"),
                    ("handle", "handle"), ("set", "set"), ("family", "brief"), ("fps", "fps"), ("length_s", "length"), ("product_json", "product_json"),
                    ("label_front", "label_front")):
        if b.get(k) is not None and getattr(a, attr) in (None, "", ap_defaults.get(attr)):
            setattr(a, attr, rel(b[k]) if k in ("photo", "back", "label", "product_json") else b[k])
    if b.get("shape") and b["shape"] != "auto" and not a.shape: a.shape = b["shape"]
    if (b.get("copy") or {}).get("cta") and a.card == ap_defaults["card"]: a.card = b["copy"]["cta"]
    if b.get("structure") and b["structure"] not in STRUCTURES: sys.exit(f"structure must be one of {list(STRUCTURES)}")
    return b


EXTRA = {"proof": {"style": "spaced", "y": 0.7, "size": 60, "at": 0.4}, "offer": {"style": "big", "anim": "pop", "size": 170, "at": 0.6},
         "cta_mid": {"style": "spaced", "y": 0.37, "size": 62, "at": 1.0}}   # between the offer and the product's top
STRUCTURES = {   # which line each beat carries (references/ad-3d.md 1.14)
    "brand":       "hook -> details -> payoff -> name (+ price) -> card line",
    "performance": "hook -> benefit -> proof -> demo -> name + offer + call to action -> card call to action",
}


def copy_titles(shots, roles, copy, family, structure="brand"):
    """Put the brief's lines on the shots by beat role, in the family's type style.
    brand: hook, details, payoff, name (+ price). performance (sells): hook, benefit, proof (a number, a rating, a
    review), demo on the product's own action, then name + offer + a call to action already on the hero shot; the card
    repeats the call to action. Also tags each shot with its role (voiceover lines follow the roles)."""
    st = STYLE.get(family, STYLE["fresh"]); dets = list(copy.get("details") or []); perf = structure == "performance"
    if perf:
        dets = [x for x in [copy.get("benefit")] + dets if x]
        extra = [("proof", copy.get("proof"))] if copy.get("proof") else []
    seen_detail = 0
    for s, role in zip(shots, roles):
        r = role
        if role == "detail":
            seen_detail += 1
            r = "benefit" if perf and seen_detail == 1 else ("proof" if perf and seen_detail == 2 and copy.get("proof") else "detail")
        if role == "payoff": r = "demo" if perf else "payoff"
        if role in ("hero", "range"): r = "name"
        s["role"] = r
        line = {"hook": copy.get("hook"), "payoff": copy.get("payoff"), "demo": copy.get("demo") or copy.get("payoff"), "name": copy.get("name"),
                "proof": copy.get("proof")}.get(r)
        if r in ("detail", "benefit") and dets: line = dets.pop(0)
        if not line: continue
        look = dict(EXTRA["proof"] if r == "proof" else st["name" if r == "name" else "payoff" if r == "demo" else r if r in st else "detail"])
        if look.get("style") == "split" and "|" not in line: look.update({"style": "big", "anim": "pop"})
        t = [dict(look, text=line)]
        if r == "name":
            off = copy.get("offer") or copy.get("price")
            if off: t.append(dict(EXTRA["offer"], text=off, pos="center", y=look["y"] + 0.12, color=[255, 255, 255]))
            if perf and (copy.get("cta_mid") or copy.get("cta")): t.append(dict(EXTRA["cta_mid"], text=copy.get("cta_mid") or copy["cta"]))
            if copy.get("callouts"): s["callouts"] = list(copy["callouts"])[:2]
        s["title"] = t if len(t) > 1 else t[0]
    if perf and copy.get("proof") and not any(x.get("role") == "proof" for x in shots):   # no second detail shot: proof on the demo
        tgt = next((x for x in shots if x.get("role") == "demo"), None) or (shots[1] if len(shots) > 1 else None)
        if tgt: tgt["title"] = titles_of(tgt) + [dict(EXTRA["proof"], text=copy["proof"])]


def init(a):
    import ad_concept
    d = pathlib.Path(a.dir); d.mkdir(parents=True, exist_ok=True)
    brief = from_brief(a) if a.brief_file else {}
    ref = None
    if brief.get("reference"):                                             # a still the user likes -> palette, set, light, mood
        import ref_style
        rp = pathlib.Path(brief["reference"]); rp = rp if rp.is_absolute() else pathlib.Path(a.brief_file).resolve().parent / rp
        ref = ref_style.analyse(rp); ref_style.show(ref)
        if not brief.get("set"): a.set = ref["set"]
        if not brief.get("family"): a.brief = ref["family"]
    if not a.product: sys.exit("init needs --product (what it is) or a brief file with \"product\"")
    prod_json, shape = None, "can"
    if a.photo:                                                            # the user's photo -> product.json + textures
        cmd = PY + [SC / "product_from_photo.py", a.photo, "--out", d / "product"] + (["--back", a.back] if a.back else []) + (["--shape", a.shape] if a.shape else [])
        print(run(cmd).strip()); prod_json = d / "product" / "product.json"
    elif a.product_json: prod_json = pathlib.Path(a.product_json).resolve()
    elif a.shape and a.shape != "can":
        spec = dict(PRESETS[a.shape])
        if a.shape == "bar":                                               # the brand name raised on the blocks
            spec["emboss_tex"] = str(emboss_image(d, (a.product or "BRAND").split()[0]).resolve())
        prod_json = d / "product.json"; json.dump(spec, open(prod_json, "w"), indent=1)
    if prod_json:
        prod_json = pathlib.Path(prod_json).resolve()                     # Blender may run from another folder
        pj = json.load(open(prod_json, encoding="utf-8")); shape = {"lathe": "bottle", "jar": "bottle"}.get(pj["shape"], pj["shape"])
        if not a.set: a.set = pj.get("set")
    elif not a.label: sys.exit("the can needs --label (a 2:1 label image), or give --photo / --product-json / --shape")
    a.set = a.set or ["#FFC21C", "#FF8A1E"]
    c = ad_concept.concept(a.product, family=a.brief, flavours=1 + len(a.alt))
    fruit = a.fruit or c.get("fruit")
    if brief.get("board"):                                                 # the brief picks the shots, e.g. a crown splash instead of the opening
        known = {b[1]: b for b in c["board"]}; acts = {x["shot"]: x for x in c["actions"] + c["events"] if x.get("shot")}
        c["board"] = [known.get(t) or ((acts[t]["beat"], t, acts[t]["do"], acts[t]["sound"]) if t in acts else ("detail", t, t, "none"))
                      for t in brief["board"]] + [b for b in c["board"] if b[1] == "card"]
    stub = d / "_music.json"
    json.dump({"output": {"path": "x.mp4"}, "clips": [], "audio": []}, open(stub, "w"))
    cmd = PY + [SC / "music_mood.py", "pick", stub, "--brief", a.brief, "--apply"] + (["--track", a.track] if a.track else [])
    print(run(cmd).strip().splitlines()[-1])
    mus = json.load(open(stub))["audio"][0]; stub.unlink()
    src = (d / mus["src"]).resolve() if not os.path.isabs(mus["src"]) else pathlib.Path(mus["src"])
    bj = d / "_beats.json"
    run(PY + [SC / "music_beats.py", src, "--start", mus.get("in", 0), "--dur", 60, "--json", bj])
    beats = json.load(open(bj)); bj.unlink()
    shots, todo, roles = [], [], []
    for k, (beat, typ, do, snd) in enumerate(c["board"], 1):
        if typ == "card" or typ.startswith("TO BUILD"):
            if typ.startswith("TO BUILD"): todo.append(typ)
            continue
        if SHOT_NEEDS.get(typ, shape) != shape: todo.append(f"{typ} (built for a {SHOT_NEEDS[typ]})"); continue
        if typ in [x["type"] for x in shots]: continue
        roles.append(beat)
        nb = max(2, round(SECONDS.get(typ, 2.5) / beats["period"]))
        sh = {"id": f"s{len(shots) + 1}_{typ}", "type": typ, "beats": nb, "cold": typ in COLD, "camera": None, "title": None,
              "does": do, "sfx": [{"sound": s, "at": at, "offset": o, "rel_db": db} for s, at, o, db in SFX.get(typ, [])]}
        if typ in EVENT_S: sh["event_beat"] = max(1, round(EVENT_S[typ] / beats["period"]))
        shots.append(sh)
    if brief.get("structure") == "performance" and shots:                 # the hero carries name + offer + call to action
        shots[-1]["beats"] += 2
    if a.length:                                                           # fit the brief's length: scale the beats
        want = max(len(shots) * 2, round(a.length / beats["period"]) - 3); have = sum(x["beats"] for x in shots)
        for x in shots:
            x["beats"] = max(2, round(x["beats"] * want / have))
            if "event_beat" in x: x["event_beat"] = min(x["event_beat"], x["beats"] - 1)
    structure = brief.get("structure", "brand")
    if brief.get("copy"): copy_titles(shots, roles, brief["copy"], a.brief, structure)
    else:
        for s_, r_ in zip(shots, roles): s_["role"] = r_
    bname = brief.get("brand_name") or ((brief.get("copy") or {}).get("name") or a.product).split("|")[0].strip().split()[0]
    bkit = None
    if brief.get("brand"):
        bkit = str((pathlib.Path(a.brief_file).resolve().parent / brief["brand"]).resolve()) if not os.path.isabs(brief["brand"]) else brief["brand"]
    st = {"stage": "board", "approved": [], "fps": a.fps, "size": "1080x1920", "brief": a.brief, "brief_file": brief or None,
          "product": {"desc": a.product, "label": str(pathlib.Path(a.label).resolve()) if a.label else None, "label_front": a.label_front,
                      "label_metal": getattr(a, "label_metal", None),
                      "json": str(prod_json) if prod_json else None, "shape": shape,
                      "alt": [str(pathlib.Path(x).resolve()) for x in a.alt], "fruit": fruit, "set": a.set, "liquid": c.get("liquid")},
          "music": {"src": str(src), "in": beats["first"], "bpm": beats["bpm"], "period": beats["period"], "strength": beats["strength"]},
          "shots": shots, "card": {"text": a.card + (f"\n**{a.handle}**" if a.handle else ""), "bg": "0x" + a.set[1].lstrip("#"), "beats": 3},
          "to_build": todo, "timings": {}, "reference": ref, "props": c.get("props"), "structure": structure, "copy": brief.get("copy") or {}, "vo": brief.get("vo"),
          "brand_name": bname, "brand": bkit, "sonic_logo": brief.get("sonic_logo", True), "length": a.length}
    save(d, st)
    print(f"music: {src.name} {beats['bpm']} BPM (beat {beats['period']} s, strength {beats['strength']}), starts on the beat at {beats['first']:.2f} s")
    for s in shots: print(f"  {s['id']:<14} {s['beats']} beats = {s['beats'] * beats['period']:.2f} s" + (f", event on beat {s['event_beat']}" if 'event_beat' in s else "") + f"  {s['does'][:70]}")
    if todo: print("not built yet (the concept still wants them):", ", ".join(todo))
    for s_ in shots:
        if s_.get("title"): print(f"  title on {s_['id']}: " + " / ".join(x["text"] for x in (s_["title"] if isinstance(s_["title"], list) else [s_["title"]])))
    print(f"\nnext: check or write the copy in {d / 'shots.json'}, then: python -I ad_pipeline.py run {d}")


# ---------------------------------------------------------------- derived spec
def tdur(s):
    """Seconds of the transition into shot s (ad_design.py), 0 for a cut."""
    import ad_design
    return ad_design.TRANSITIONS.get(s.get("transition_in") or "cut", (None, 0.0, None))[1]


def derived(st):
    """Per shot render spec. A shot followed by a transition gets that many extra frames, so the next shot still
    starts on its beat (the two overlap for the transition); 'base' is the frame count on the beat grid."""
    fps, per = st["fps"], st["music"]["period"]; out = []; D = st.get("design") or {}; shots = st["shots"]
    for i, s in enumerate(shots):
        base = max(8, round(s["beats"] * per * fps))
        nxt = tdur(shots[i + 1]) if i + 1 < len(shots) else 0.3            # the end card fades in over 0.3 s
        n = base + round(nxt * fps)
        sp = {"id": s["id"], "type": s["type"], "frames": n, "base": base, "cold": s.get("cold", False)}
        if "event_beat" in s: sp["event"] = min(base - 4, max(2, round(s["event_beat"] * per * fps) + 1))
        sp["key"] = min(base, sp["event"] + round(0.45 * fps)) if "event" in sp else round(base * 0.6)
        if s.get("camera"): sp["camera"] = s["camera"]
        if s.get("move"): sp["move"] = s["move"]
        for k_, v_ in (("bg", D.get("background")), ("decor", D.get("decor")), ("motion", D.get("motion")), ("family", D.get("family") or st.get("brief")),
                       ("key_side", (st.get("reference") or {}).get("key_side")), ("palette", [h for h, _ in (st.get("reference") or {}).get("palette", [])][:4] or None)):
            if v_: sp[k_] = v_
        out.append(sp)
    return out


def blender(st, d, out, size, samples, still=False, engine="eevee", only=None):
    spec = d / f"_spec_{out.name}.json"; json.dump({"shots": derived(st)}, open(spec, "w"), indent=1)
    p = st["product"]
    if not still:                                                          # resume only frames of an unchanged shot
        import hashlib
        for x in derived(st):
            if only and x["id"] not in only: continue
            fp = hashlib.sha1(json.dumps([x, p, st["fps"], size, samples, engine], sort_keys=True).encode()).hexdigest()
            sd = pathlib.Path(out) / x["id"]; mark = sd / ".spec"
            if sd.exists() and (not mark.exists() or mark.read_text() != fp): shutil.rmtree(sd)
            sd.mkdir(parents=True, exist_ok=True); mark.write_text(fp)
    pj = p.get("json")
    if pj and not pathlib.Path(pj).is_absolute():                          # states written by older versions: relative paths
        pj = next((str(c.resolve()) for c in (pathlib.Path(pj), d / pathlib.Path(pj).name, d.parent / pj) if c.exists()), pj)
    cmd = [blender_exe(), "-b", "--python-exit-code", "1", "-P", SC / "blender_product_ad.py", "--"] + (["--label", p["label"]] if p.get("label") else []) + (["--product", pj] if pj else []) + [
           "--label-front", p.get("label_front", 0.5),
           "--set", *p["set"], "--out", out, "--size", size, "--fps", st["fps"], "--samples", samples, "--spec", spec, "--engine", engine]
    if p.get("alt"): cmd += ["--alt", *p["alt"]]
    if p.get("label_metal"): cmd += ["--label-metal", p["label_metal"]]
    if p.get("fruit"): cmd += ["--fruit", p["fruit"]]
    if p.get("liquid"): cmd += ["--liquid", p["liquid"]]                    # the crown pool: milk, coffee, berry juice...
    if still: cmd += ["--still"]
    if only: cmd += ["--shots", *only]
    t0 = time.time(); out = run(cmd); blender.log = out; return time.time() - t0


FINISH = {   # glow (opacity), chromatic aberration (px at 1080), vignette angle, grain, grade in RGB, grade in YUV - per mood family
    "fresh":  (0.22, 1.0, 0.4, 3, None, "eq=saturation=1.1:contrast=1.03"),
    "luxury": (0.38, 1.5, 0.75, 6, "colorbalance=rs=0.04:bs=-0.04:rh=0.03", "eq=contrast=1.08:saturation=0.95"),
    "tech":   (0.45, 2.5, 0.7, 4, "colorbalance=bs=0.06:rh=0.04:bh=0.03", "eq=contrast=1.1"),
    "clean":  (0.14, 0.0, 0.35, 2, None, "eq=brightness=0.012:saturation=0.95:contrast=0.98"),
}


def finish_filter(family, width):
    """The last look of a render: highlights glow, a hint of lens fringing, vignette, film grain, the family's grade -
    what separates a photographed product from a clean render. Same for EEVEE and Cycles (done here, in ffmpeg).
    The glow is blended in planar RGB: a screen blend in YUV also blends the colour planes and turns orange pink."""
    f = FINISH.get(family)
    if not f: return None
    glow, ca, vig, grain, rgb_g, yuv_g = f; k = width / 1080; cpx = int(round(ca * k)); sig = max(2, 14 * k)
    return (f"format=gbrp,split[a][b];[b]curves=all='0/0 0.72/0 1/1',gblur=sigma={sig:.1f}[g];[a][g]blend=all_mode=screen:all_opacity={glow}"
            + (f",rgbashift=rh=-{cpx}:bh={cpx}" if cpx else "") + (f",{rgb_g}" if rgb_g else "")
            + f",format=yuv444p,vignette=angle={vig},noise=alls={grain}:allf=t" + (f",{yuv_g}" if yuv_g else ""))


def encode(st, frames_dir, sid):
    mp4 = frames_dir / f"{sid}.mp4"; fam = (st.get("design") or {}).get("family") or st.get("brief")
    first = next(iter(sorted((frames_dir / sid).glob("*.png"))), None)
    from PIL import Image
    w = Image.open(first).size[0] if first else 1080
    fc = finish_filter(fam, w)
    run(["ffmpeg", "-v", "error", "-y", "-framerate", st["fps"], "-i", frames_dir / sid / "%04d.png"] + (["-filter_complex", fc] if fc else [])
        + ["-c:v", "libx264", "-crf", 16, "-pix_fmt", "yuv420p", mp4])
    return mp4


def titles_of(s):
    t = s.get("title")
    return [x for x in (t if isinstance(t, list) else [t]) if x]


VOICES = {"th": "th-TH-PremwadeeNeural", "en": "en-US-AndrewNeural"}


def vo_lines(st):
    """Voiceover lines by role. "vo": {"lines": {"hook": ..., "benefit": ..., "name": ..., "cta": ...}, "voice": ...} or
    "vo": true (lines from the copy). The brand name is said in the first line (YouTube ABCD: say the brand early)."""
    vo = st.get("vo")
    if not vo: return []
    cp = st.get("copy") or {}; b = st.get("brand_name") or ""
    lines = dict(vo.get("lines") or {}) if isinstance(vo, dict) else {}
    if not lines:
        lines = {"hook": cp.get("hook"), "benefit": cp.get("benefit") or (cp.get("details") or [None])[0], "proof": cp.get("proof"),
                 "name": (cp.get("name") or "").replace("|", " ") + (". " + (cp.get("offer") or cp.get("price") or "") if (cp.get("offer") or cp.get("price")) else ""),
                 "cta": cp.get("cta")}
    order = ["hook", "benefit", "proof", "demo", "name", "cta"]
    out = [(r, str(lines[r]).strip()) for r in order if lines.get(r)]
    if out and b and b.lower() not in out[0][1].lower(): out[0] = (out[0][0], f"{b}. {out[0][1]}")
    return out


def synth_vo(d, text, voice):
    import hashlib
    vd = d / "vo"; vd.mkdir(exist_ok=True); f = vd / (hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:12] + ".mp3")
    for attempt in range(3):                                               # the TTS service sometimes returns a broken file
        if not f.exists(): run([sys.executable, "-m", "edge_tts", "--voice", voice, "--text", text, "--write-media", f])
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip(): return f.resolve(), float(r.stdout.strip())   # absolute: edit_plan reads it from the plan's folder
        f.unlink(missing_ok=True); time.sleep(1.5)
    sys.exit(f"voiceover failed for: {text!r} (edge-tts needs the internet); remove \"vo\" from the brief or try again")


def anchors_of(frames_dir, sid):
    f = pathlib.Path(frames_dir) / f"{sid}_anchors.json"
    return json.load(open(f)) if f.exists() else None


CALLOUT_LOOK = {"fresh": "hand", "luxury": "hairline", "tech": "tech", "clean": "dot"}   # callouts.py looks per mood
FEATURE_ORDER = ["logo", "detail", "top", "base"]                          # what a callout points at, in this order
ABOVE_MIN_Y = 0.44                                                         # callouts placed above the product stay below the titles


def place_callouts(st, sp, starts, frames_dir):
    """Callouts that point at real features of the product (Blender's per-frame tracks: logo, detail, top, base) on
    the shot (not the hook) with the most free room beside the settled product, on the roomier side; the right edge
    stops at the apps' button column (0.84). Each points at a feature that faces the lens all through its window,
    they enter one after another and leave together before the cut; the look follows the mood family (brief
    "callout_style" overrides). Copy items may be {"text", "at": "<feature>", "look"}."""
    shots = st["shots"]; raw = next((s["callouts"] for s in shots if s.get("callouts")), None)
    if not raw or not frames_dir: return []
    items = [x if isinstance(x, dict) else {"text": str(x)} for x in raw][:3]
    fps = st["fps"]; best = above = None
    for i, (s, x) in enumerate(zip(shots, sp)):
        an = anchors_of(frames_dir, s["id"])
        if not an or s.get("role") == "hook" or i == 0: continue
        fr_keys = [k for k in an if k.isdigit()]
        if not fr_keys: continue
        last = an[str(max(map(int, fr_keys)))]; lx, rx = last["left"][0], last["right"][0]
        room_l, room_r = lx - 0.05, 0.84 - rx; side = "left" if room_l >= room_r else "right"; room = max(room_l, room_r)
        if 0 < lx < rx < 1 and (best is None or room > best[0]): best = (room, i, side, last, an)
        top_room = last.get("top", [0, 0])[1] - ABOVE_MIN_Y                  # free space between the title band and the product
        if 0 < lx < rx < 1 and top_room > 0.1 and (above is None or top_room > above[0]): above = (top_room, i, "above", last, an)
    if not best or best[0] < 0.2:                                           # sides full (a 9:16 hero fills the width): above it,
        if not above: return []                                             # or no callouts rather than squeezed ones
        best = above
    room, i, side, last, an = best; x = sp[i]; t0 = starts[i]; base = x["base"]
    look = (st.get("brief_file") or {}).get("callout_style") or CALLOUT_LOOK.get(st.get("brief"), "dot")
    tr = an.get("tracks") or {}; tsec = lambda fr: t0 + (fr - 1) / fps
    gap = {"hairline": 0.5, "hand": 0.45}.get(look, 0.35); end = round(t0 + base / fps - 0.15, 2)
    first = t0 + base * 0.45 / fps
    gap = max(0.12, min(gap, (end - first - 0.8) / max(1, len(items) - 1)))   # a short shot: tighter stagger, all still readable
    out, used = [], set()
    for k, it in enumerate(items):
        start = round(t0 + base * 0.45 / fps + gap * k, 2)
        if end - start < 0.6: break
        c = {"text": it["text"], "style": "callout", "look": it.get("look", look), "side": side, "start": start, "end": end, "fps": fps}
        if side == "above": c["side"] = "right"                              # set per label below
        if tr.get("frames"):
            win = [j for j, fr in enumerate(tr["frames"]) if start - 0.1 <= tsec(fr) <= end + 0.1]
            cand = [it["at"]] if it.get("at") in tr else [f for f in FEATURE_ORDER if f in tr and f not in used]
            def ready(f):                                                  # first moment the feature faces the lens (0.15: seen,
                ok = [tr[f][j][2] > 0.15 for j in win]                       # if at a slant) and keeps facing it to the end
                for q in range(len(ok)):
                    if all(ok[q:]): return q
                return None
            got = [(ready(f), n_, f) for n_, f in enumerate(cand) if win]
            got = [g_ for g_ in got if g_[0] is not None and end - tsec(tr["frames"][win[g_[0]]]) >= 0.6]
            if not got: continue                                           # nothing of the product faces the lens for it
            q, _, feat = min(got); win = win[q:]                           # wait for it rather than skip it
            c["start"] = round(max(start, tsec(tr["frames"][win[0]])), 2)
            used.add(feat); c["feature"] = feat
            c["track"] = [[round(tsec(tr["frames"][j]), 3), tr[feat][j][0], tr[feat][j][1]] for j in win]
        else:                                                              # older anchors: a still point at the edge
            pt_x = last["left" if side == "left" else "right"][0]; yc = min(0.66, max(0.32, last["label"][1]))
            c["at"] = [round(pt_x, 3), round(yc + (k - 0.5) * 0.09, 3)]
        out.append(c)
    mid = lambda c: (c["track"][len(c["track"]) // 2][2] if c.get("track") else c["at"][1])
    midx = lambda c: (c["track"][len(c["track"]) // 2][1] if c.get("track") else c["at"][0])
    if side == "above":                                                     # a vertical leader up to a shelf over the product
        y = last["top"][1] - 0.05
        for k, c in enumerate(out):                                         # copy order: the first line gets the space;
            tx = midx(c); right = (tx < 0.5) if k == 0 else not out[0]["side"] == "right"   # the next shelf turns the other way
            kx = min(0.8, max(0.16, tx + (0.025 if right else -0.025)))      # so leaders never cross a shelf
            c["side"] = "right" if right else "left"
            c["label"] = [round(kx, 3), round(max(ABOVE_MIN_Y, y), 3)]; y -= 0.085
        return [c for c in out if c["label"][1] > ABOVE_MIN_Y - 0.001 or len(out) == 1]
    # the shelves: just outside the product, above their points, stacked so they never overlap
    edge = last["right"][0] if side == "right" else last["left"][0]
    kx = round(min(0.70, edge + 0.04), 3) if side == "right" else round(max(0.30, edge - 0.04), 3)
    lift = 0.09 if look == "hand" else 0.06
    ys = sorted(range(len(out)), key=lambda n_: mid(out[n_])); prev = None
    for n_ in ys:
        ly = min(0.76, max(0.16, mid(out[n_]) - lift))
        if prev is not None and ly < prev + 0.085: ly = prev + 0.085
        out[n_]["label"] = [kx, round(ly, 3)]; prev = ly
    return out


def layout(st, d, frames_dir=None):
    """The ad's timeline before anything is cut: shot starts on the beat grid, titles, callouts on the product,
    physical sounds, voiceover lines placed by role, the end card. make_plan and the ABCD check both use it."""
    import ad_design
    fps, per = st["fps"], st["music"]["period"]; sp = derived(st); shots = st["shots"]
    starts, t = [], 0.0
    for x in sp: starts.append(t); t += x["base"] / fps
    card0 = t; cdur = st["card"].get("beats", 3) * per + 0.3
    titles, sfx, callouts = [], [], []
    for i, (s, x) in enumerate(zip(shots, sp)):
        t0 = starts[i]; base = x["base"] / fps
        for tt in titles_of(s):
            ti = {k: v for k, v in tt.items() if k not in ("at", "dur")}
            ti["start"] = round(t0 + tt.get("at", 0.3), 2); ti["end"] = round(min(t0 + base - 0.15, ti["start"] + tt.get("dur", 99)), 2)
            if ti["end"] - ti["start"] > 0.3: titles.append(ti)
        for e in s.get("sfx", []):
            at = t0 + ((x.get("event", 1) - 1) / fps if e.get("at") == "event" else 0) + e.get("offset", 0)
            sfx.append({"src": f"sfx/{e['sound']}.wav", "role": "sfx", "start": round(max(0, at), 3), "rel_db": e.get("rel_db", -12), "why": f"{s['id']} {e['sound']}"})
        ty, td, snd = ad_design.TRANSITIONS.get(s.get("transition_in") or "cut", (None, 0.0, None))
        if ty and i and snd: sfx.append({"src": f"sfx/{snd}.wav", "role": "sfx", "start": round(max(0, t0 - 0.05), 3), "rel_db": -16, "why": f"{s['id']} transition"})
    callouts += place_callouts(st, sp, starts, frames_dir)
    vo = []; prev = 0.0; roles = {s.get("role"): starts[i] for i, s in enumerate(shots) if s.get("role")}
    for r, text in vo_lines(st):
        voice = (st.get("vo") or {}).get("voice") if isinstance(st.get("vo"), dict) else None
        voice = voice or (VOICES["th"] if any("\u0e00" <= ch <= "\u0e7f" for ch in text) else VOICES["en"])
        f, dur = synth_vo(d, text, voice)
        at = card0 + 0.1 if r == "cta" else roles.get("name" if r == "name" else r, roles.get("payoff", prev)) + 0.15
        at = max(at, prev + 0.1); vo.append({"role": r, "text": text, "src": str(f), "start": round(at, 2), "dur": round(dur, 2)}); prev = at + dur
    return {"starts": starts, "card": card0, "card_dur": cdur, "total": card0 + cdur - 0.3 + 0.3, "titles": titles + callouts, "sfx": sfx, "vo": vo, "sp": sp}


def make_plan(st, d, frames_dir, out_name):
    """Edit plan from layout(): shots back to back (extended under their outgoing transition), the end card, titles and
    callouts, the music from its first beat, voiceover ducking the music, sound design, each shot's physical sounds
    and the brand's sonic logo on the card."""
    import ad_design, make_sfx
    fps = st["fps"]; Lo = layout(st, d, frames_dir); clips = []
    for i, (s, x) in enumerate(zip(st["shots"], Lo["sp"])):
        c = {"src": os.path.relpath(frames_dir / f"{x['id']}.mp4", d).replace("\\", "/"), "in": 0, "out": round(x["frames"] / fps, 3), "speech": False, "volume_db": -90}
        ty, td, _ = ad_design.TRANSITIONS.get(s.get("transition_in") or "cut", (None, 0.0, None))
        if ty and i: c["transition"] = {"type": ty, "dur": td}
        clips.append(c)
    card = st["card"]
    clips.append({"card": {"text": card["text"], "bg": card.get("bg", "0xFF9A1E"), "size": card.get("size", 128)}, "in": 0, "out": round(Lo["card_dur"], 3),
                  "transition": {"type": "fade", "dur": 0.3}})
    m = st["music"]; vo = Lo["vo"]
    plan = {"output": {"path": out_name, "size": list(map(int, st["size"].split("x"))), "fps": fps, "target": "shorts", "lufs": -14},
            "clips": clips, "titles": Lo["titles"], "master": {"glue": True, "limit": 0.56},
            "music_mix": {"gap_db": 0, "under_db": -9 if vo else 0},       # the voice sits on top of the music
            "audio": [{"src": os.path.relpath(m["src"], d).replace("\\", "/") if os.path.splitdrive(m["src"])[0] == os.path.splitdrive(str(d.resolve()))[0] else m["src"],
                       "role": "music", "in": round(m["in"], 3), "start": 0, "end": round(Lo["total"], 2), "fade_in": 0.05, "fade_out": 1.5, "mood_pick": True}]
                     + [{"src": v["src"], "role": "voice", "start": v["start"]} for v in vo]}
    if st.get("brand"): plan["brand"] = st["brand"]
    pp = d / (pathlib.Path(out_name).stem + ".json"); json.dump(plan, open(pp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    make_sfx.make(d / "sfx")
    run(PY + [SC / "sound_design.py", pp])
    plan = json.load(open(pp, encoding="utf-8")); sfx = list(Lo["sfx"])
    if st.get("sonic_logo", True) and st.get("brand_name"):              # the brand's sound on the card, instead of a chime
        fam = (st.get("design") or {}).get("family") or st.get("brief"); sw = d / "sfx" / "sonic.wav"
        make_sfx.write(sw, make_sfx.sonic_logo(st["brand_name"], fam))
        plan["audio"] = [x for x in plan["audio"] if not (x.get("sd") and "chime" in str(x.get("src")))]
        sfx.append({"src": "sfx/sonic.wav", "role": "sfx", "start": round(Lo["card"] + 0.1, 2), "rel_db": -5, "why": "sonic logo"})
    plan["audio"] += sfx
    json.dump(plan, open(pp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return pp


def abcd(st, d, frames_dir=None):
    """Score the ad against the platforms' own creative guidance before it is rendered (YouTube ABCD: Attract, Brand,
    Connect, Direct; TikTok: the proposition in the first 3 s, the hook in 6 s, captions, 5-10 words a second at
    most). Returns rows (PASS / WARN / INFO, rule, detail)."""
    Lo = layout(st, d, frames_dir); fps = st["fps"]; sp = Lo["sp"]; shots = st["shots"]; rows = []
    b = (st.get("brand_name") or "").lower()
    first_title = min((t["start"] for t in Lo["titles"]), default=99)
    prod_t = ((sp[0].get("event", 1) - 1) / fps) if shots and shots[0]["type"] == "split" else 0.0
    rows.append(("PASS" if prod_t <= 3 else "WARN", "A  product on screen by 3 s", f"{prod_t:.1f} s"))
    rows.append(("PASS" if min(first_title, prod_t + 0.5) <= 3 else "WARN", "A  hook lands by 3 s (TikTok: proposition in 3 s, hook in 6 s)", f"first line at {first_title:.1f} s"))
    brand_title = min((t["start"] for t in Lo["titles"] if b and b in str(t.get("text", "")).lower()), default=99)
    rows.append(("PASS" if min(prod_t, brand_title) <= 5 else "WARN", "B  brand seen by 5 s (packshot or name)", f"product {prod_t:.1f} s, name {brand_title if brand_title < 99 else '-'}"))
    said = min((v["start"] for v in Lo["vo"] if b and b in v["text"].lower()), default=None)
    rows.append(("PASS" if said is not None and said <= 5 else "WARN", "B  brand said by 5 s (voiceover)", f"{said:.1f} s" if said is not None else "no voiceover"))
    rows.append(("INFO", "C  connect", f"mood family {st.get('brief')}, music {pathlib.Path(st['music']['src']).stem}, story: {st.get('structure', 'brand')}"))
    rows.append(("PASS" if st["card"].get("text") else "WARN", "D  call to action on the end card", st["card"].get("text", "").replace("\n", " ")))
    if st.get("structure") == "performance":
        cta = (st.get("copy") or {}).get("cta_mid") or (st.get("copy") or {}).get("cta") or ""
        early = min((t["start"] for t in Lo["titles"] if cta and t.get("text") == cta), default=None)
        rows.append(("PASS" if early is not None and early < Lo["card"] else "WARN", "D  call to action before the card too", f"{early:.1f} s" if early is not None else "none"))
        for k in ("benefit", "proof"):
            rows.append(("PASS" if any(s.get("role") == k for s in shots) or any((st.get("copy") or {}).get(k) == t.get("text") for t in Lo["titles"]) else "WARN",
                         f"S  {k} on screen", (st.get("copy") or {}).get(k) or "missing in the brief"))
    dense = [t for t in Lo["titles"] if len(str(t.get("text", "")).split()) / max(0.3, t["end"] - t["start"]) > 4 or len(str(t.get("text", "")).split()) > 8]
    rows.append(("PASS" if not dense else "WARN", "   text readable (<= 8 words, <= 4 words/s on screen)", ", ".join(t["text"] for t in dense) or "ok"))
    rows.append(("PASS" if any(s.get("title") for s in shots[:1]) and any(s.get("role") == "name" and s.get("title") for s in shots) else "WARN",
                 "   works muted (hook and name in text)", ""))
    if st.get("length"): rows.append(("PASS" if abs(Lo["total"] - st["length"]) <= 1.5 else "WARN", "   length", f"{Lo['total']:.1f} s for {st['length']} s"))
    vo_end = max((v["start"] + v["dur"] for v in Lo["vo"]), default=0)
    if Lo["vo"]: rows.append(("PASS" if vo_end <= Lo["total"] - 0.2 else "WARN", "   voiceover fits", f"ends {vo_end:.1f} s of {Lo['total']:.1f} s"))
    return rows


def abcd_text(rows):
    return "ABCD check:\n" + "\n".join(f"  {a:<5} {b}  {c}" for a, b, c in rows)


def render_edit(pp, check_safe=True):
    out = run(PY + [SC / "edit_plan.py", pp])
    qa = [l for l in out.splitlines() if l.startswith(("PASS", "FAIL", "WARN", "RESULT"))]
    mp4 = pp.parent / json.load(open(pp, encoding="utf-8"))["output"]["path"]
    if check_safe and (mp4.parent / (mp4.name + ".titles.ass")).exists():
        qa.append(run(PY + [SC / "safe_zones.py", mp4, mp4.parent / (mp4.name + ".titles.ass")]).strip().splitlines()[-1])
    return mp4, qa


# ---------------------------------------------------------------- board sheet
def glyph(dr, move, x, y, s=70):
    """A small drawing of the camera move on the storyboard frame (white on a dark disc)."""
    dr.ellipse([x, y, x + s, y + s], fill=(0, 0, 0), outline=(255, 255, 255), width=3)   # ringed: visible on dark sets too
    c = (x + s / 2, y + s / 2); w = (255, 255, 255); r = s * 0.32
    def arrow(p0, p1):
        dr.line([p0, p1], fill=w, width=4); ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        for da in (2.6, -2.6): dr.line([p1, (p1[0] + 12 * math.cos(ang + da), p1[1] + 12 * math.sin(ang + da))], fill=w, width=4)
    cx, cy = c
    if move in ("orbit", "spiral"):
        dr.arc([cx - r, cy - r * 0.6, cx + r, cy + r * 0.6], 200, 340, fill=w, width=4); arrow((cx + r * 0.75, cy - r * 0.4), (cx + r, cy))
        if move == "spiral": arrow((cx, cy + r * 0.6), (cx, cy - r * 0.2))
    elif move in ("dolly_in", "push_tilt", "low_hero"): dr.rectangle([cx - 8, cy - 8, cx + 8, cy + 8], outline=w, width=3); arrow((cx - r, cy + r), (cx - 10, cy + 10))
    elif move == "dolly_out": dr.rectangle([cx - 8, cy - 8, cx + 8, cy + 8], outline=w, width=3); arrow((cx - 10, cy + 10), (cx - r, cy + r))
    elif move in ("crane_down", "crane_up"): arrow((cx, cy - r), (cx, cy + r)) if move == "crane_down" else arrow((cx, cy + r), (cx, cy - r))
    elif move in ("truck", "macro_slide"): arrow((cx - r, cy), (cx + r, cy))
    elif move == "whip_in": arrow((cx - r, cy - 6), (cx + r, cy - 6)); dr.line([(cx - r, cy + 8), (cx + r * 0.6, cy + 8)], fill=w, width=2)
    elif move == "dolly_zoom": arrow((cx - r, cy), (cx - 4, cy)); arrow((cx + 4, cy), (cx + r, cy))
    elif move == "top_down": dr.ellipse([cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5], outline=w, width=3); dr.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=w)
    elif move == "rack_focus": dr.ellipse([cx - r, cy - 6, cx - r + 12, cy + 6], outline=w, width=2); arrow((cx - r + 16, cy), (cx + r * 0.6, cy)); dr.ellipse([cx + r * 0.6, cy - 8, cx + r * 0.6 + 16, cy + 8], fill=w)
    else: dr.rectangle([cx - r * 0.6, cy - r * 0.4, cx + r * 0.6, cy + r * 0.4], outline=w, width=3)



def board_sheet(st, d, stills_dir, name="board.jpg"):
    from PIL import Image, ImageDraw, ImageFont
    sp = derived(st); per = st["music"]["period"]; fps = st["fps"]
    fonts = sorted((ROOT / "assets" / "fonts").glob("Kanit*.ttf"))
    f1 = ImageFont.truetype(str(fonts[0]), 24) if fonts else ImageFont.load_default()
    D = st.get("design") or {}; TOP = 60 if D else 0
    W, H, CAP, cols = 432, 768, 184, min(4, len(sp)); rows = math.ceil(len(sp) / cols)
    sheet = Image.new("RGB", (cols * (W + 16) + 16, rows * (H + CAP + 16) + 16 + TOP), (24, 24, 26)); dr = ImageDraw.Draw(sheet)
    if D: dr.text((16, 16), f"design: {D.get('family')} | background {D.get('background')} | decor {D.get('decor')} | motion {D.get('motion')} | "
                            f"signature {D.get('signature')} | variant {D.get('variant')}", fill=(255, 210, 120), font=f1)
    for i, (s, x) in enumerate(zip(st["shots"], sp)):
        X, Y = 16 + (i % cols) * (W + 16), 16 + TOP + (i // cols) * (H + CAP + 16)
        im = stills_dir / f"{x['id']}_still.png"
        if im.exists(): sheet.paste(Image.open(im).convert("RGB").resize((W, H)), (X, Y))
        if s.get("move"): glyph(dr, s["move"], X + W - 86, Y + 14)
        lens = (s.get("camera") or {}).get("lens")
        lines = [f"{i + 1}. {s['type']}  {x['base'] / fps:.2f}s = {s['beats']} beats" + (f"  {lens}mm" if lens else ""),
                 (f"camera: {s['move']} ({s.get('size', '')})  in: {s.get('transition_in', 'cut')}" if s.get("move") else ""),
                 (f"event on beat {s['event_beat']} (frame {x['event']})" if "event" in x else s.get("does", "")[:40]),
                 "title: " + (" / ".join(x.get("text", "").replace("\n", " ") for x in titles_of(s))[:34] or "-"),
                 "sound: " + (", ".join(e["sound"] for e in s.get("sfx", [])) or "music")]
        for k, ln in enumerate([l for l in lines if l]): dr.text((X + 6, Y + H + 8 + k * 34), ln, fill=(235, 235, 235), font=f1)
    out = d / name; sheet.save(out, quality=88); return out


# ---------------------------------------------------------------- stages
def stage(d, st):
    s = st["stage"]; fr = st["fps"]; nfr = sum(x["frames"] for x in derived(st))
    if s == "board":
        if not st.get("design"):                                           # design before anything is rendered
            import ad_design; why = ad_design.design(st); ad_design.show(st, why)
        sec = blender(st, d, d / "board", "432x768", 8, still=True)
        fc = finish_filter((st.get("design") or {}).get("family") or st.get("brief"), 432)
        if fc:                                                             # the board shows the finished look too
            for x in derived(st):
                im = d / "board" / f"{x['id']}_still.png"; tmp = im.with_name(im.stem + "_f.png")
                if im.exists(): run(["ffmpeg", "-v", "error", "-y", "-i", im, "-filter_complex", fc, "-frames:v", 1, tmp]); tmp.replace(im)
        out = board_sheet(st, d, d / "board"); st["timings"]["board_s"] = round(sec)
        rows = abcd(st, d, d / "board"); st["abcd"] = rows; print(abcd_text(rows))
        return (f"[gate: design + storyboard] look at {out}: one frame per shot with its camera move, transition, background, decor "
                f"and motion ({nfr / fr:.1f} s + card). Approve the concept, the design and the copy; another design: "
                f"python -I ad_design.py {d} --variant 2 (or --lock <shot>=<move>), then rerun")
    if s == "animatic":
        fd = d / "animatic"; sec = blender(st, d, fd, "360x640", 4)
        for x in derived(st): encode(st, fd, x["id"])
        mp4, qa = render_edit(make_plan(st, d, fd, "animatic.mp4"), check_safe=False); st["timings"]["animatic_s_per_frame"] = round(sec / nfr, 2)
        return f"[gate: animatic] watch {mp4} (rough look, real timing, music, titles, sound). Approve timing and moves\n  " + "\n  ".join(qa)
    if s == "preview":
        fd = d / "preview"; sec = blender(st, d, fd, st["size"], 16)
        for x in derived(st): encode(st, fd, x["id"])
        mp4, qa = render_edit(make_plan(st, d, fd, "preview.mp4")); st["timings"]["preview_s_per_frame"] = round(sec / nfr, 2)
        rows = abcd(st, d, fd); st["abcd"] = rows
        return f"[gate: preview] watch {mp4} (full size, EEVEE). Approve the look before the long final render\n  " + "\n  ".join(qa) + "\n" + abcd_text(rows)
    if s == "final_test":                                                  # one Cycles frame per shot at half size: look + cost
        W, H = map(int, st["size"].split("x")); fd = d / "final_test"
        blender(st, d, fd, f"{W // 2}x{H // 2}", 128, still=True, engine="cycles")
        rs = {l.split()[1]: float(l.split()[2]) for l in blender.log.splitlines() if l.startswith("RENDER_S ")}
        est = {x["id"]: rs.get(x["id"], max(rs.values() or [20])) * 4 * x["frames"] for x in derived(st)}   # x4 pixels at full size
        st["timings"]["cycles_s_per_frame"] = {k: round(v * 4, 1) for k, v in rs.items()}
        final_sheet = board_sheet(st, d, fd, "final_test.jpg")
        lines = "\n  ".join(f"{k}: ~{rs.get(k, 0) * 4:.0f} s/frame -> {v / 60:.0f} min" for k, v in est.items())
        return (f"[gate: final cost] Cycles look per shot: {final_sheet}\n  {lines}\n  total ~{sum(est.values()) / 3600:.1f} h "
                f"for {nfr} frames (resumable). Approve to start the final render")
    if s == "final":
        fd = d / "final"; blender(st, d, fd, st["size"], 128, engine="cycles")
        for x in derived(st): encode(st, fd, x["id"])
        mp4, qa = render_edit(make_plan(st, d, fd, "final.mp4"))
        return f"[done] {mp4}\n  " + "\n  ".join(qa)
    return "all stages done"


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["init", "run", "status", "variants"]); ap.add_argument("dir")
    ap.add_argument("--n", type=int, default=3, help="variants: how many openings in all (the preview is #1)")
    ap.add_argument("--source", default="preview", choices=["preview", "animatic"], help="variants: build on the preview (final look) or the animatic (fast)")
    ap.add_argument("--product"); ap.add_argument("--label"); ap.add_argument("--label-front", type=float, default=0.5)
    ap.add_argument("--alt", nargs="*", default=[]); ap.add_argument("--fruit"); ap.add_argument("--set", nargs=2)
    ap.add_argument("--brief", default="fresh"); ap.add_argument("--track"); ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--card", default="Available now"); ap.add_argument("--handle", default="")
    ap.add_argument("--photo"); ap.add_argument("--back"); ap.add_argument("--product-json"); ap.add_argument("--shape", choices=["can", "bottle", "lathe", "pouch", "box", "bar"])
    ap.add_argument("--label-metal", help="auto or a mask image: where the can's print leaves bare metal")
    ap.add_argument("--brief-file"); ap.add_argument("--length", type=float, help="target seconds (shots scaled in whole beats)")
    ap.add_argument("--approve", action="store_true", help="the user approved the last gate")
    ap_defaults = {x.dest: x.default for x in ap._actions}
    a = ap.parse_args(); d = pathlib.Path(a.dir)
    if a.cmd == "init":
        init(a); sys.exit(0)
    st = load(d)
    if a.cmd == "variants":                                                # other openings for testing, the rest shared
        import copy as _copy, ad_design
        fd = d / a.source; size, samples = (st["size"], 16) if a.source == "preview" else ("360x640", 4)
        if not (fd / f"{st['shots'][0]['id']}.mp4").exists(): sys.exit(f"render the {a.source} first (run until its gate)")
        hooks = list((st.get("copy") or {}).get("hooks") or []); s0 = st["shots"][0]; outs = []
        moves = [m for m in ad_design.ALLOWED.get(s0["type"], ["native"]) if m != s0.get("move")]
        for k in range(2, a.n + 1):
            st2 = _copy.deepcopy(st); h = st2["shots"][0]; h["id"] = f"{s0['id']}_h{k}"
            h["move"] = moves[(k - 2) % len(moves)] if moves else h.get("move")
            if len(hooks) >= k - 1 and titles_of(h):
                tt = titles_of(h); tt[0] = dict(tt[0], text=hooks[k - 2]); h["title"] = tt if len(tt) > 1 else tt[0]
            blender(st2, d, fd, size, samples, only=[h["id"]]); encode(st2, fd, h["id"])
            mp4, qa = render_edit(make_plan(st2, d, fd, f"{a.source}_hook{k}.mp4")); outs.append(f"{mp4}  ({h['move']}" + (f", '{hooks[k - 2]}'" if len(hooks) >= k - 1 else "") + ")")
        print("hook variants (the same ad after the opening):\n  " + "\n  ".join(outs)); sys.exit(0)
    if a.cmd == "status":
        print("stage:", st["stage"], " approved:", ", ".join(st["approved"]) or "-", " timings:", st.get("timings")); sys.exit(0)
    if a.approve:
        if st.get("shown") != st["stage"]: sys.exit(f"nothing shown yet for '{st['stage']}': run without --approve first")
        st["approved"].append(st["stage"]); st["stage"] = STAGES[STAGES.index(st["stage"]) + 1]; st.pop("shown", None)
    if st["stage"] == "done": print("all stages done"); sys.exit(0)
    if not blender_exe(): sys.exit("Blender not found: install Blender 4.2+ or set BLENDER=<path to blender>")
    msg = stage(d, st); st["shown"] = st["stage"]
    if st["stage"] == "final": st["approved"].append("final"); st["stage"] = "done"; st.pop("shown", None)
    save(d, st); print(msg)
