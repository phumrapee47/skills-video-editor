"""Design pass for a 3D product ad: decide HOW every shot is filmed and dressed before anything is rendered.

Usage: python -I ad_design.py <ad dir> [--variant 2] [--lock s3_zerog=orbit ...] [--background haze_glints]
       [--decor gold_dust] [--motion smooth] [--print]
Reads <dir>/shots.json (ad_pipeline.py init), writes the design into it, prints the design with the reason for each
choice. ad_pipeline.py runs it before the storyboard; the storyboard sheet then shows the design for approval.
Per shot:  camera move (from MOVES, only moves that suit that shot's action), shot size, lens, transition into it.
Per ad:    animated background, decoration in depth layers, motion style, the signature move.
Rules (variety is the point - the user asked for camera work that is not the same every time):
  - neighbours never share a move or a shot size; a move used before costs more
  - at least one signature move (orbit, spiral, crane, dolly zoom, whip) per ad
  - the mood family steers the choice (fresh: whips, spirals, dolly zoom; luxury: slow orbits, cranes, rack focus;
    tech: dolly zoom, whip, truck; clean: slow dolly, top-down, crane)
  - no transition over a shot whose physical event comes in its first 0.4 s (it would hide the event)
  - --variant N reshuffles the choices inside the same rules; --lock keeps a choice
"""
import argparse, json, pathlib, random, sys

MOVES = {   # size: what the frame shows; sig: a signature move
    "native":      {"size": None, "sig": False, "says": "the shot's own staged camera"},
    "dolly_in":    {"size": "medium", "sig": False, "says": "pushes in toward the product"},
    "dolly_out":   {"size": "wide", "sig": False, "says": "pulls back to reveal the scene"},
    "orbit":       {"size": "medium", "sig": True, "says": "circles round the product"},
    "spiral":      {"size": "medium", "sig": True, "says": "circles and rises at once"},
    "crane_down":  {"size": "wide", "sig": True, "says": "comes down from high to eye level"},
    "crane_up":    {"size": "medium", "sig": False, "says": "rises past the product"},
    "truck":       {"size": "medium", "sig": False, "says": "slides sideways past the product"},
    "low_hero":    {"size": "medium", "sig": False, "says": "low angle push: the product looks big"},
    "top_down":    {"size": "close", "sig": False, "says": "straight down, drifting"},
    "macro_slide": {"size": "macro", "sig": False, "says": "close slide along the surface"},
    "rack_focus":  {"size": "close", "sig": False, "says": "focus pulls from the foreground to the product"},
    "dolly_zoom":  {"size": "medium", "sig": True, "says": "dolly in while zooming out: the background stretches"},
    "whip_in":     {"size": "medium", "sig": True, "says": "whips in from the side and lands on the product"},
    "push_tilt":   {"size": "close", "sig": False, "says": "pushes in and tilts down onto the top"},
}
NATIVE_SIZE = {"split": "wide", "drops": "macro", "toppop": "close", "open": "close", "zerog": "wide", "hero_low": "medium",
               "hero": "medium", "macro": "macro", "burst": "wide", "reveal": "medium", "trio": "wide", "twist": "close",
               "tear": "medium", "snap": "close"}
ALLOWED = {  # moves that keep each shot's action readable (the first is its own staging)
    "split": ["native", "dolly_in", "crane_down", "spiral", "low_hero"], "drops": ["native", "macro_slide", "rack_focus"],
    "toppop": ["native", "top_down"], "open": ["native", "push_tilt"], "zerog": ["native", "orbit", "dolly_zoom", "spiral", "dolly_in"],
    "hero_low": ["native", "low_hero", "orbit", "crane_down", "dolly_out"], "hero": ["native", "orbit", "truck", "dolly_zoom"],
    "macro": ["native", "macro_slide", "rack_focus"], "burst": ["native", "dolly_out", "orbit"], "reveal": ["native", "whip_in", "crane_down"],
    "trio": ["native", "truck", "crane_down", "orbit"], "twist": ["native", "push_tilt", "crane_up"],
    "tear": ["native", "dolly_in", "low_hero", "truck"], "snap": ["native", "truck", "dolly_in", "rack_focus"]}
FAMILY = {
    "fresh":  {"moves": {"whip_in": 3, "dolly_zoom": 2.5, "spiral": 2.5, "dolly_in": 2, "truck": 1.5, "low_hero": 1.5, "crane_down": 1},
               "transitions": ["whip", "flash", "cut", "zoom", "slide"], "background": "gradient_bokeh", "decor": "droplets", "motion": "bouncy"},
    "luxury": {"moves": {"orbit": 3, "crane_down": 2.5, "rack_focus": 2.5, "low_hero": 2, "dolly_in": 1.5, "spiral": 1},
               "transitions": ["dissolve", "dip", "cut", "light_sweep"], "background": "haze_glints", "decor": "gold_dust", "motion": "smooth"},
    "tech":   {"moves": {"dolly_zoom": 3, "whip_in": 3, "truck": 2.5, "orbit": 2, "push_tilt": 1.5, "low_hero": 1.5},
               "transitions": ["glitch", "whip", "cut", "slice"], "background": "neon_grid", "decor": "light_specks", "motion": "snappy"},
    "clean":  {"moves": {"dolly_in": 2.5, "crane_down": 2.5, "top_down": 2, "truck": 2, "rack_focus": 2, "orbit": 1.5},
               "transitions": ["dissolve", "cut", "slide"], "background": "window_light", "decor": "soft_dust", "motion": "smooth"},
}
TRANSITIONS = {  # name -> ffmpeg xfade type, seconds, effect sound
    "cut": (None, 0.0, None), "whip": ("hblur", 0.22, "swish"), "flash": ("fadewhite", 0.2, None), "zoom": ("zoomin", 0.3, "whoosh"),
    "slide": ("smoothup", 0.3, "swish"), "dissolve": ("fade", 0.45, None), "dip": ("fadeblack", 0.4, None),
    "light_sweep": ("smoothright", 0.35, None), "glitch": ("pixelize", 0.2, None), "slice": ("hlslice", 0.25, "swish")}
BACKGROUNDS = {"gradient_bokeh": "soft light blobs drift across the wall, bokeh discs float behind the product",
               "haze_glints": "thin haze drifts through the light, gold glints twinkle, a dark glossy floor",
               "neon_grid": "a glowing grid floor, neon strips slide across the wall",
               "window_light": "window-frame shadows slide slowly across a soft white wall",
               "plain": "the colour set, no movement"}
DECOR = {"droplets": "clear droplets float in front of and behind the product (out of focus near the lens)",
         "gold_dust": "gold motes drift in the light", "light_specks": "small glowing specks drift", "soft_dust": "soft white dust drifts",
         "none": "nothing extra"}
MOTION = {"bouncy": "settles with a small overshoot", "smooth": "slow in, slow out, never stops dead", "snappy": "fast out, hard stop",
          "auto": "Blender's default ease"}
EVENT_EARLY = 0.4


def design(st, variant=1, lock=None, background=None, decor=None, motion=None):
    """Fill st["design"] and every shot's "move" and "transition_in"; returns the reasons."""
    fam = st.get("brief", "fresh"); F = FAMILY.get(fam, FAMILY["fresh"]); rnd = random.Random(1000 + variant)
    lock = lock or {}; per = st["music"]["period"]; shots = st["shots"]; why = []; used = {}; prev_move = prev_size = None
    for i, s in enumerate(shots):
        typ = s["type"]; cand = ALLOWED.get(typ, ["native"])
        if s["id"] in lock: choice = lock[s["id"]]
        else:
            best, bs = None, -1e9
            for m in cand:
                size = MOVES[m]["size"] or NATIVE_SIZE.get(typ, "medium")
                if m == prev_move and m != "native": continue
                sc = F["moves"].get(m, 0.6 if m != "native" else 1.0) - 2.0 * used.get(m, 0) - (1.5 if size == prev_size else 0) + rnd.uniform(0, 2.4)
                if typ in ("split", "snap", "tear", "twist", "toppop", "open") and m == "native": sc += 0.8   # staged action: own framing is safe
                if sc > bs: best, bs = m, sc
            choice = best
        s["move"] = choice; size = MOVES[choice]["size"] or NATIVE_SIZE.get(typ, "medium"); s["size"] = size
        used[choice] = used.get(choice, 0) + 1; prev_move, prev_size = choice, size
        why.append(f"{s['id']}: {choice} ({size}) - {MOVES[choice]['says']}")
    if not any(MOVES[s["move"]]["sig"] for s in shots):                   # at least one signature move
        opts = [(s, m) for s in shots if s["id"] not in lock for m in ALLOWED.get(s["type"], []) if MOVES[m]["sig"]]
        if opts:
            s, m = max(opts, key=lambda o: F["moves"].get(o[1], 0) + rnd.uniform(0, 1)); s["move"] = m; s["size"] = MOVES[m]["size"]
            why.append(f"{s['id']}: switched to {m} so the ad has a signature move")
    prev_t = None
    for i, s in enumerate(shots):                                         # transitions into each shot
        if i == 0: s["transition_in"] = "cut"; continue
        ev = s.get("event_beat"); early = ev is not None and ev * per < EVENT_EARLY + 0.05
        pal = [t for t in F["transitions"] if t != prev_t or t == "cut"]
        t = "cut" if early else pal[rnd.randrange(len(pal))]
        if shots[i - 1]["move"] == "whip_in" or s["move"] == "whip_in": t = "whip" if "whip" in F["transitions"] else t
        s["transition_in"] = t; prev_t = t
        why.append(f"{s['id']}: in by {t}" + (" (its event is early: a transition would hide it)" if early else ""))
    sig = next((s["id"] for s in shots if MOVES[s["move"]]["sig"]), None)
    st["design"] = {"family": fam, "variant": variant, "background": background or F["background"], "decor": decor or F["decor"],
                    "motion": motion or F["motion"], "signature": sig}
    return why


def show(st, why):
    D = st["design"]
    print(f"design ({D['family']}, variant {D['variant']}):")
    print(f"  background: {D['background']} - {BACKGROUNDS.get(D['background'], '')}")
    print(f"  decor:      {D['decor']} - {DECOR.get(D['decor'], '')}")
    print(f"  motion:     {D['motion']} - {MOTION.get(D['motion'], '')}")
    print(f"  signature:  {D['signature']}")
    for w in why: print("  " + w)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir"); ap.add_argument("--variant", type=int, default=1); ap.add_argument("--lock", nargs="*", default=[])
    ap.add_argument("--background", choices=list(BACKGROUNDS)); ap.add_argument("--decor", choices=list(DECOR)); ap.add_argument("--motion", choices=list(MOTION))
    a = ap.parse_args(); p = pathlib.Path(a.dir) / "shots.json"; st = json.load(open(p, encoding="utf-8"))
    lock = dict(x.split("=", 1) for x in a.lock)
    bad = [f"{k}={v}" for k, v in lock.items() if v not in MOVES]
    if bad: sys.exit(f"unknown move: {bad}; moves: {', '.join(MOVES)}")
    why = design(st, a.variant, lock, a.background, a.decor, a.motion); show(st, why)
    if st.get("stage") not in ("board", None): print("note: the ad is past the storyboard; rerun its stages to see the new design")
    json.dump(st, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False); print("wrote", p)
