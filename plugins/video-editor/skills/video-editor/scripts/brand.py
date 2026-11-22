"""Brand kit: one brand.json gives every clip of a channel the same look (the reference channels all keep one grade,
one type pair, accent colours and a small logo in a corner).

Plan: "brand": "brand.json" (path relative to the plan). Read by edit_plan.py, word_captions.py --brand, sound_design.py
--brand and podcast_short.py --brand. Every field is optional; paths are relative to brand.json:
{
 "name": "Flood Lab",
 "fonts":   {"sans": "fonts/Brand-Bold.ttf", "serif_italic": "...", "heavy": "..."},  // own fonts (licence: yours to use)
 "accent":  "2EC4B6",                        // underline, **marked** words, the key word of pop captions
 "palette": ["2EC4B6", "FFB703", "FB5607"],  // key-word colour per phrase in mixed-type captions
 "grade":   "teal-orange",                   // preset (see GRADES) or any ffmpeg filter chain
 "logo":    {"src": "logo.png", "pos": "top-left", "size": 0.11, "opacity": 0.9, "margin": 0.035},
 "end_card": {"text": "Follow for more\\n**flood science**", "sub": "@floodlab", "dur": 2.6, "bg": "0B1F2A"},
 "sfx_level": -2                              // dB on every sound-design effect; "sfx": false = none
}
The logo is hidden while a card or topic card is on screen and drawn large above the text on the end card.
Vertical outputs: "top-left" sits under the apps' top tabs (safe_zones.py); avoid "*-right" (the button column).
"""
import json, pathlib, shutil, tempfile

GRADES = {   # applied to the whole picture before titles and captions, so text keeps its exact colours
    "clean":       "eq=contrast=1.05:saturation=1.08",
    "warm":        "colorbalance=rs=0.04:gs=0.01:bs=-0.05:rh=0.03:bh=-0.03,eq=saturation=1.08",
    "teal-orange": "colorbalance=rs=-0.06:gs=0.0:bs=0.07:rm=0.04:bm=-0.03:rh=0.06:gh=0.01:bh=-0.06,eq=contrast=1.06:saturation=1.12",
    "film":        "curves=all='0/0.05 0.5/0.48 1/0.95',eq=saturation=0.9,colorbalance=rh=0.03:bs=0.03",
    "bw":          "hue=s=0,eq=contrast=1.12",
}


def load(plan, base):
    """The plan's brand as a dict with absolute paths (or {} when the plan has none)."""
    ref = plan.get("brand")
    if not ref: return {}
    p = (pathlib.Path(base) / ref).resolve() if isinstance(ref, str) else None
    b = json.load(open(p, encoding="utf-8")) if p else dict(ref)
    root = p.parent if p else pathlib.Path(base)
    for k, v in list((b.get("fonts") or {}).items()): b["fonts"][k] = str((root / v).resolve())
    if b.get("logo", {}).get("src"): b["logo"]["src"] = str((root / b["logo"]["src"]).resolve())
    b["_path"] = str(p) if p else None
    return b


def load_file(path):
    return load({"brand": pathlib.Path(path).name}, pathlib.Path(path).resolve().parent)


def grade(b):
    g = b.get("grade")
    return GRADES.get(g, g) if g else None


def use_fonts(b):
    """Put the brand's fonts first for their roles; libass gets one folder holding the bundled and the brand fonts."""
    import fonts
    fm = b.get("fonts") or {}
    if not fm: return
    d = pathlib.Path(tempfile.mkdtemp(prefix="ve_brand_fonts_"))
    for f in fonts.FONT_DIR.glob("*.[ot]tf"): shutil.copy(f, d)
    from PIL import ImageFont
    for role, path in fm.items():
        shutil.copy(path, d); fam = ImageFont.truetype(path, 20).getname()[0]
        fonts.ROLES[role].insert(0, (fam, d / pathlib.Path(path).name))
    fonts.FONT_DIR = d


def end_card(b):
    """Clip for the plan's end, or None."""
    e = b.get("end_card")
    if not e: return None
    text = e.get("text", b.get("name", "")) + (("\n" + e["sub"]) if e.get("sub") else "")
    card = {"text": text, "bg": "0x" + e.get("bg", "000000").lstrip("#"), "size": e.get("size", 96), "anim": e.get("anim", "words")}
    if b.get("accent"): card["accent"] = b["accent"]
    return {"card": card, "in": 0, "out": float(e.get("dur", 2.6)), "transition": {"type": "fade", "dur": 0.3}, "brand_end": True}


def apply_end_card(plan, b):
    """Add the brand's end card unless the plan already ends on a card (same rule in every script)."""
    if b.get("end_card") and not (plan["clips"] and plan["clips"][-1].get("card")): plan["clips"].append(end_card(b))


def logo_filters(b, inp, src_label, out_label, W, H, hide, end_span):
    """Filter lines that put the logo on the picture: small in a corner, hidden during `hide` spans, large over the end card."""
    lg = b.get("logo") or {}
    if not lg.get("src"): return []
    size = float(lg.get("size", 0.11)); m = float(lg.get("margin", 0.035)); op = float(lg.get("opacity", 0.9))
    lw = int(W * size if W < H else W * size * 0.6) // 2 * 2; mx = int(W * m); my = int(H * (0.075 if H > W else m))   # vertical: under the apps' top tabs
    pos = lg.get("pos", "top-left")
    x = mx if "left" in pos else f"W-w-{mx}"; y = my if "top" in pos else f"H-h-{int(H * (0.2 if H > W else m))}"
    off = "+".join(f"between(t,{a:.2f},{z:.2f})" for a, z in hide) or "0"
    head = f"[{inp}:v]format=rgba,colorchannelmixer=aa={op}"
    if not end_span:
        return [f"{head},scale={lw}:-1[lgs]", f"[{src_label}][lgs]overlay={x}:{y}:enable='not({off})'[{out_label}]"]
    big = int(W * (0.34 if H > W else 0.16)) // 2 * 2; a, z = end_span
    return [f"{head},split=2[lgA][lgB];[lgA]scale={lw}:-1[lgs];[lgB]scale={big}:-1[lgb]",
            f"[{src_label}][lgs]overlay={x}:{y}:enable='not({off})'[lgo]",
            f"[lgo][lgb]overlay=(W-w)/2:H*0.30-h:enable='between(t,{a:.2f},{z:.2f})'[{out_label}]"]
