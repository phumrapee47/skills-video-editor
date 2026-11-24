"""Read a reference image the user likes into design choices for a 3D product ad (references/ad-craft.md: "read the
user's reference images: palette, light direction, contrast, props -> the design").

  python -I ref_style.py ref.jpg [--json style.json]

What it measures (numpy + Pillow only, nothing downloaded):
  palette     6 colours by k-means, with their share of the picture
  set         the floor colour (bottom band) and the wall colour (top band) -> the studio sweep
  accent      the most saturated palette colour that is not the set
  light       which side the light comes from (where the highlights sit against the subject) and how high
  brightness  mean luminance; contrast = p95 - p5; saturation = mean chroma of the brighter half
  family      fresh | luxury | tech | clean from those numbers, with the reasons
ad_pipeline.py takes a brief "reference": "ref.jpg" and uses set, family and accent unless the brief sets them.
"""
import argparse, colorsys, json, sys

import numpy as np


def _hex(c): return "#%02X%02X%02X" % tuple(int(round(max(0, min(1, x)) * 255)) for x in c)


def kmeans(px, k=6, iters=14, seed=3):
    rnd = np.random.default_rng(seed); cen = px[rnd.choice(len(px), k, replace=False)]
    for _ in range(iters):
        d = ((px[:, None, :] - cen[None]) ** 2).sum(-1); lab = d.argmin(1)
        for j in range(k):
            sel = px[lab == j]
            if len(sel): cen[j] = sel.mean(0)
    share = np.bincount(lab, minlength=k) / len(px)
    order = np.argsort(-share); return cen[order], share[order]


def analyse(path):
    from PIL import Image
    im = Image.open(path).convert("RGB"); im.thumbnail((240, 240)); a = np.asarray(im, dtype=float) / 255.0
    H, W, _ = a.shape; px = a.reshape(-1, 3)
    lum = a @ np.array([0.2126, 0.7152, 0.0722]); mx, mn = a.max(-1), a.min(-1); chroma = mx - mn
    cen, share = kmeans(px.copy())
    band = max(2, H // 9)
    floor = np.median(a[-band:].reshape(-1, 3), 0); wall = np.median(a[:band].reshape(-1, 3), 0)
    bright = lum > np.median(lum); sat = float(chroma[bright].mean()); mean_l = float(lum.mean())
    contrast = float(np.percentile(lum, 95) - np.percentile(lum, 5))
    # the subject: pixels far from both set colours; the light side: highlights inside the subject vs its centre
    dset = np.minimum(((a - floor) ** 2).sum(-1), ((a - wall) ** 2).sum(-1)); subj = dset > 0.02
    side, elev = "front", "mid"
    if subj.sum() > 0.02 * H * W:
        ys, xs = np.nonzero(subj); cx, cy = xs.mean(), ys.mean(); sl = lum[subj]
        hi = subj & (lum >= np.percentile(sl, 92))
        if hi.sum():
            hy, hx = np.nonzero(hi); dx, dy = (hx.mean() - cx) / max(1, xs.std()), (hy.mean() - cy) / max(1, ys.std())
            side = "left" if dx < -0.25 else ("right" if dx > 0.25 else "front"); elev = "high" if dy < -0.35 else ("low" if dy > 0.35 else "mid")
    pal = [(_hex(c), round(float(s), 3)) for c, s in zip(cen, share)]
    def hsv(c): return colorsys.rgb_to_hsv(*c)
    acc = max(cen, key=lambda c: (hsv(c)[1] * hsv(c)[2]) - 2 * min(((c - floor) ** 2).sum(), ((c - wall) ** 2).sum()) ** 0.5 * 0)
    cands = [c for c in cen if min(((c - floor) ** 2).sum(), ((c - wall) ** 2).sum()) > 0.03] or list(cen)
    acc = max(cands, key=lambda c: hsv(c)[1] * hsv(c)[2])
    why = []
    vivid = (chroma > 0.3) & (mx > 0.45)                                 # neon lines are thin: count pixels, not clusters
    r_, g_, b_ = a[..., 0], a[..., 1], a[..., 2]
    hue = np.where(mx == r_, ((g_ - b_) / np.maximum(chroma, 1e-6)) % 6, np.where(mx == g_, (b_ - r_) / np.maximum(chroma, 1e-6) + 2,
                   (r_ - g_) / np.maximum(chroma, 1e-6) + 4)) / 6
    neon = float((vivid & (((hue > 0.42) & (hue < 0.7)) | ((hue > 0.78) & (hue < 0.96)))).mean())
    if mean_l < 0.3 and neon > 0.004: fam = "tech"; why.append(f"dark set (mean luminance {mean_l:.2f}) with cyan/blue/magenta light ({neon:.1%} of the picture)")
    elif mean_l < 0.38: fam = "luxury"; why.append(f"low-key: mean luminance {mean_l:.2f}, contrast {contrast:.2f}")
    elif mean_l > 0.62 and sat < 0.09: fam = "clean"; why.append(f"high-key and near-neutral: luminance {mean_l:.2f}, saturation {sat:.2f}")
    elif mean_l > 0.62 and sat < 0.3: fam = "fresh"; why.append(f"pastel and playful: high-key ({mean_l:.2f}) with a clear hue (saturation {sat:.2f})")
    elif sat > 0.3: fam = "fresh"; why.append(f"bright and saturated: luminance {mean_l:.2f}, saturation {sat:.2f}")
    else: fam = "clean"; why.append(f"soft colours: saturation {sat:.2f}")
    why.append(f"light from the {side}" + ("" if elev == "mid" else f", {elev}") + "; set from the bottom and top bands of the picture")
    return {"source": str(path), "palette": pal, "set": [_hex(floor), _hex(wall)], "accent": _hex(acc), "family": fam,
            "key_side": side, "key_height": elev, "brightness": round(mean_l, 3), "contrast": round(contrast, 3),
            "saturation": round(sat, 3), "why": why}


def show(r):
    print(f"reference {r['source']}")
    print("  palette  " + "  ".join(f"{h} {s:.0%}" for h, s in r["palette"]))
    print(f"  set      floor {r['set'][0]}  wall {r['set'][1]}   accent {r['accent']}")
    print(f"  light    from the {r['key_side']} ({r['key_height']})   brightness {r['brightness']}  contrast {r['contrast']}  saturation {r['saturation']}")
    print(f"  family   {r['family']}: " + "; ".join(r["why"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0]); ap.add_argument("image"); ap.add_argument("--json")
    a = ap.parse_args(); r = analyse(a.image); show(r)
    if a.json: json.dump(r, open(a.json, "w", encoding="utf-8"), indent=1)
