"""Concept planner for 3D product ads: what the product can DO and what its ingredient can DO -> a beat board.

Usage: python -I ad_concept.py --product "yuzu soda can" [--ingredient yuzu] [--family fresh] [--flavours 3] [--json]
       python -I ad_concept.py --list
Reads assets/ad_concepts.json (product affordances: a can opens with a fizz, a bag tears, a filled bar snaps and its
filling stretches; ingredient events: citrus is split, beans crack, milk crowns). Prints:
  - every action the product and ingredient can do, with its sound and camera, marked BUILT (a shot of
    blender_product_ad.py) or TO BUILD (with how to build it);
  - a beat board: hook (the strongest physical event), detail, payoff (what the product does), hero, range, end card;
  - the render command for the built shots.
Claude still reads the brief and the product photos: this is the checklist of what is possible, not the taste.
"""
import argparse, json, pathlib, sys

CAT = json.loads((pathlib.Path(__file__).resolve().parent.parent / "assets" / "ad_concepts.json").read_text(encoding="utf-8"))
LEN_S = {"pour": 4.0, "clink": 2.8, "crown": 2.8, "twist": 2.8, "tear": 2.8, "snap": 3.2, "split": 4.0, "open": 2.5, "toppop": 2.5, "drops": 2.4, "zerog": 3.2, "hero_low": 3.0, "burst": 2.5, "macro": 2.0, "hero": 2.5, "trio": 3.2, "reveal": 2.5}


def find(group, words):
    """Match a free description ("yuzu soda can") to a catalogue entry by its name or aka words."""
    words = (words or "").lower()
    best, score, word = None, 0, None
    for name, e in CAT[group].items():
        for w in [name.replace("_", " ")] + e.get("aka", []):
            if w in words and len(w) > score: best, score, word = name, len(w), w
    return best, (word if best else None)


def concept(product, ingredient=None, family="fresh", flavours=1):
    p, _ = find("products", product); ing, ing_word = find("ingredients", ingredient or product)
    shape = CAT["products"].get(p, {}).get("shape") or "can"; needs = CAT.get("shot_needs", {})
    avoid = CAT.get("shot_avoid", {})                                      # e.g. a mug does not drop into a pool (crown)
    fits = lambda x: not x.get("shot") or (needs.get(x["shot"], shape) == shape and shape not in avoid.get(x["shot"], []))
    acts = [dict(a, of=p) for a in CAT["products"].get(p, {}).get("actions", [])]
    evs = [dict(e, of=ing) for e in CAT["ingredients"].get(ing, {}).get("events", [])]
    for x in acts + evs:
        if not fits(x): x["build"] = (f"shot '{x['shot']}' is built for a {needs[x['shot']]} only" if x["shot"] in needs else f"shot '{x['shot']}' does not suit a {shape}"); x["shot"] = None
    built = lambda xs, beat: [x for x in xs if x["beat"] == beat and x.get("shot")]
    board = []
    hooks = [x for x in acts + evs if x["beat"] == "hook"]                                   # the product's own action first
    hook = (built(evs, "hook") or built(acts, "hook") or hooks or [None])[0]                 # an unbuilt hook is still the idea
    board.append(("hook", (hook.get("shot") or f"TO BUILD:{hook['id']}") if hook else "reveal",
                  hook["do"] if hook else "the product flies in spinning", hook["sound"] if hook else "whoosh"))
    dets = (built(acts, "detail") + built(evs, "detail"))[:2]
    if not any(d["shot"] == "drops" for d in dets):                         # drops is already the label macro
        board.append(("detail", "macro", "camera glides over the label, shallow focus", "none (music)"))
    for det in dets:                                                       # what the product shows close up, then the ingredient
        if det["shot"] not in [b[1] for b in board]: board.append(("detail", det["shot"], det["do"], det["sound"]))
    pay = (built(acts, "payoff") or [x for x in acts if x["beat"] == "payoff"] or [None])[0]
    if pay and pay is not hook and pay.get("shot") not in [b[1] for b in board]: board.append(("payoff", pay.get("shot") or f"TO BUILD:{pay['id']}", pay["do"], pay["sound"]))
    board.append(("hero", "hero_low", "the product settles still, logo to the lens, low angle, name on screen", "soft thud"))
    if flavours > 1: board.append(("range", "trio", f"{flavours} flavours line up", "pops on the names"))
    board.append(("end", "card", "line + handle on the brand colour", "chime"))
    todo = [x for x in acts + evs if not x.get("shot")]
    return {"product": p, "shape": shape, "ingredient": ing, "fruit": ing_word if CAT["ingredients"].get(ing, {}).get("fruit") else None,
            "liquid": CAT["ingredients"].get(ing, {}).get("liquid"), "props": CAT["ingredients"].get(ing, {}).get("props"), "family": family, "family_rules": CAT["families"].get(family),
            "actions": acts, "events": evs, "board": board, "to_build": todo,
            "shots": [b[1] for b in board if b[1] != "card" and not b[1].startswith("TO BUILD")], "seconds": round(sum(LEN_S.get(b[1], 2.4) for b in board), 1)}


def show(c):
    print(f"product: {c['product'] or '? (not in the catalogue: add it to assets/ad_concepts.json)'}   ingredient: {c['ingredient'] or '-'}   family: {c['family']}")
    if c["family_rules"]: print(f"  {c['family']}: {c['family_rules']['pace']}; {c['family_rules']['light']}")
    print("\nwhat it can do:")
    for x in c["actions"] + c["events"]:
        tag = f"BUILT shot '{x['shot']}'" if x.get("shot") else "TO BUILD"
        print(f"  [{x['of']}] {x['id']:<15} {x['beat']:<7} {tag:<20} {x['do']}  (sound: {x['sound']})")
        if not x.get("shot") and x.get("build"): print(f"  {'':<34}how: {x['build']}")
    print(f"\nbeat board (~{c['seconds']} s):")
    for i, (beat, shot, do, snd) in enumerate(c["board"], 1): print(f"  {i}. {beat:<7} {shot:<6} {do}  [{snd}]")
    if any(b[1].startswith("TO BUILD") for b in c["board"]):
        print("  TO BUILD beats are the concept: build them (see 'how') before rendering, or say which beat is missing")
    fruit = f" --fruit {c['fruit'] if c['fruit'] not in (None, 'citrus', 'mandarin') else 'orange'}" if c["fruit"] else ""
    print(f"\nrender: blender -b -P blender_product_ad.py -- --label label.png{fruit} --shots {' '.join(dict.fromkeys(c['shots']))} --out shots")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--product"); ap.add_argument("--ingredient"); ap.add_argument("--family", default="fresh", choices=list(CAT["families"]))
    ap.add_argument("--flavours", type=int, default=1); ap.add_argument("--json", action="store_true"); ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    if a.list or not a.product:
        for g in ("products", "ingredients"):
            print(g + ":"); [print(f"  {k:<12} {', '.join(v.get('aka', []))}") for k, v in CAT[g].items()]
        sys.exit(0)
    c = concept(a.product, a.ingredient, a.family, a.flavours)
    if a.json: print(json.dumps(c, ensure_ascii=False, indent=1))
    else: show(c)
