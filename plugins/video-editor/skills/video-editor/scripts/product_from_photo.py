"""Turn the user's product photo into a 3D product for blender_product_ad.py (product.json + textures).

Usage: python -I product_from_photo.py front.jpg --out prod_dir [--back back.jpg] [--shape auto|bottle|lathe|box|pouch]
       [--height-mm 212] [--depth-mm 60] [--name kaze]
Best input: the product straight on, centred, on a plain background (a cut-out PNG with alpha is used as is).
  1. cut-out: the photo's alpha; a plain background (studio shot) by its colour; a busy one with rembg and a model
     already on disk (bria-rmbg / u2net; never downloads), else the border colour
  2. shape guess (print it; Claude checks the photo and passes --shape when wrong): wide -> bar; fills its box ->
     box; a neck in the top third -> bottle; else round (lathe: can, jar) or pouch (--shape pouch)
  3. round products: the silhouette's width per row = the radius profile (mm from --height-mm), the cap above the
     neck becomes its own part (cap_from_mm); every row's visible arc is unwrapped (asin) into one texture, the photo's
     shading divided out, the hidden back filled from --back or the row's own colour
  4. box / pouch: the front picture (and --back) on the faces, size from the photo's proportions
  5. the product's own colours -> "set" (floor, wall) for the studio
Writes <out>/product.json, texture png(s), check.jpg (outline, profile, unwrapped texture). Real photos have
perspective: shoot from far with a long lens; a strong top/bottom ellipse shows as a bulge at the ends.
"""
import argparse, json, pathlib, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

DEF_H = {"bottle": 212.0, "lathe": 115.7, "box": 270.0, "pouch": 250.0, "bar": 120.0}


def cutout(img):
    if img.mode in ("RGBA", "LA") and np.asarray(img.getchannel("A")).min() < 250:
        return np.asarray(img.getchannel("A")) > 128, "alpha"
    rgb = img.convert("RGB"); a = np.asarray(rgb).astype(float)
    border = np.concatenate([a[:6].reshape(-1, 3), a[-6:].reshape(-1, 3), a[:, :6].reshape(-1, 3), a[:, -6:].reshape(-1, 3)])
    plain = border.std(0).max() < 8                                        # a studio shot on a plain background: no model needed
    home = pathlib.Path.home() / ".rembg" / "models"
    for name in (() if plain else ("bria-rmbg", "u2net", "isnet-general-use")):
        if (home / name / f"{name}.onnx").exists() or (pathlib.Path.home() / ".u2net" / f"{name}.onnx").exists():
            try:
                from rembg import new_session, remove
                m = np.asarray(remove(rgb, session=new_session(name), only_mask=True)) > 128
                if m.mean() > 0.02: return m, name
            except Exception as e: print("rembg failed, using the background colour:", str(e)[:80])
    bg = np.median(border, 0); d = np.sqrt(((a - bg) ** 2).sum(-1))
    m = d > max(18, np.percentile(np.sqrt(((border - bg) ** 2).sum(-1)), 99) * 1.5)
    mi = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MedianFilter(5))
    return np.asarray(mi) > 128, "background colour"


def largest_blob(m):
    """Keep rows/cols of the main object: crop to the bounding box of the mask after dropping specks."""
    ys, xs = np.nonzero(m)
    y0, y1 = np.percentile(ys, [0.2, 99.8]).astype(int); x0, x1 = np.percentile(xs, [0.2, 99.8]).astype(int)
    return y0, y1 + 1, x0, x1 + 1


def row_spans(m):
    L, R = [], []
    for row in m:
        xs = np.nonzero(row)[0]
        L.append(xs[0] if len(xs) else -1); R.append(xs[-1] if len(xs) else -1)
    return np.array(L), np.array(R)


def guess_shape(m):
    H, W = m.shape; L, R = row_spans(m); w = np.where(L >= 0, R - L + 1, 0).astype(float)
    if W / H > 2.0: return "bar", w
    if m.mean() > 0.94: return "box", w
    top = w[int(H * 0.03):int(H * 0.35)]
    if len(top) and top.min() < 0.62 * w.max(): return "bottle", w
    return "lathe", w


def smooth(x, k=5): return np.convolve(np.pad(x, k // 2, mode="edge"), np.ones(k) / k, "valid")


def palette(rgb, m, k=4):
    px = rgb[m].reshape(-1, 3).astype(float)
    if len(px) > 20000: px = px[np.random.default_rng(0).choice(len(px), 20000, replace=False)]
    c = px[np.random.default_rng(1).choice(len(px), k, replace=False)]
    for _ in range(12):
        lab = ((px[:, None] - c[None]) ** 2).sum(-1).argmin(1)
        c = np.array([px[lab == i].mean(0) if (lab == i).any() else c[i] for i in range(k)])
    cnt = np.bincount(lab, minlength=k); order = np.argsort(-cnt)
    return [tuple(int(v) for v in c[i]) for i in order], cnt[order] / cnt.sum()


def hexc(c): return "#%02X%02X%02X" % tuple(int(max(0, min(255, v))) for v in c)


def studio_set(cols):
    """Wall = the most colourful of the main colours; floor = a light tint of it."""
    sat = lambda c: (max(c) - min(c)) / (max(c) + 1)
    main = max(cols[:3], key=sat)
    wall = tuple(v * 0.75 for v in main); floor = tuple(v + (255 - v) * 0.6 for v in main)
    return [hexc(floor), hexc(wall)]


def unwrap(rgb, m, L, R, rows, back=None, tw=1024, th_max=np.radians(76)):
    """Each row's visible half-cylinder -> texture columns by asin; u = 0.5 at the front, increasing to the right."""
    H = len(rows); tex = np.zeros((H, tw, 3)); vis = np.zeros(tw, bool)
    th = (np.arange(tw) / tw - 0.5) * 2 * np.pi; vis = np.abs(th) <= th_max
    for k, y in enumerate(rows):
        l, r = L[y], R[y]
        if l < 0: continue
        c = (l + r) / 2; rad = max(1.0, (r - l) / 2)
        x = np.clip(c + rad * np.sin(np.clip(th, -th_max, th_max)), 0, rgb.shape[1] - 1)
        x0 = np.floor(x).astype(int); x1 = np.minimum(x0 + 1, rgb.shape[1] - 1); f = (x - x0)[:, None]
        tex[k] = rgb[y, x0] * (1 - f) + rgb[y, x1] * f
    lum = tex.mean(-1) + 1; rowmed = np.median(lum[:, vis], 1, keepdims=True)
    shade = smooth(np.median(lum / rowmed, 0), 31); shade[~vis] = 1
    tex = tex / np.clip(shade, 0.75, 1.35)[None, :, None]                 # the photo's light, divided out
    if back is not None:
        bt = unwrap(*back)
        tex[:, ~vis] = np.roll(bt, tw // 2, axis=1)[:, ~vis]
    else:                                                                  # the hidden back: the row's own colour
        edge = np.median(tex[:, vis], 1)
        tex[:, ~vis] = edge[:, None, :]
        bl = np.clip(1 - (np.abs(th) - th_max * 0.85) / (th_max * 0.15), 0, 1)
        tex = tex * bl[None, :, None] + edge[:, None, :] * (1 - bl[None, :, None])
    return np.clip(tex, 0, 255)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo"); ap.add_argument("--out", required=True); ap.add_argument("--back")
    ap.add_argument("--shape", default="auto", choices=["auto", "bottle", "lathe", "box", "pouch"])
    ap.add_argument("--height-mm", type=float); ap.add_argument("--depth-mm", type=float); ap.add_argument("--name", default="product")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    img = Image.open(a.photo); m, how = cutout(img); rgb = np.asarray(img.convert("RGB")).astype(float)
    y0, y1, x0, x1 = largest_blob(m); m = m[y0:y1, x0:x1]; rgb = rgb[y0:y1, x0:x1]
    shape, w = guess_shape(m); guessed = shape
    if a.shape != "auto": shape = a.shape
    H, W = m.shape; hmm = a.height_mm or DEF_H.get(shape, 150.0); mmpx = hmm / H
    cols, share = palette(rgb, m); spec = {"shape": shape, "name": a.name, "height_mm": round(hmm, 1), "set": studio_set(cols),
                                           "colors": [hexc(c) for c in cols], "source": pathlib.Path(a.photo).name}
    print(f"cut-out: {how}; {W}x{H} px; shape guess: {guessed}" + (f" (using --shape {shape})" if shape != guessed else "") + f"; {mmpx:.3f} mm/px")
    L, R = row_spans(m)
    if shape in ("bottle", "lathe"):
        rows = np.arange(H)[::-1]                                         # bottom -> top
        rad = smooth(np.where(L >= 0, (R - L + 1) / 2, 0).astype(float), 5)[::-1] * mmpx
        step = max(1, H // 90); idx = list(range(0, H, step)) + [H - 1]
        prof = [[0.0, 0.0]] + [[round(float(rad[i]), 2), round(i * mmpx, 2)] for i in idx] + [[0.0, round((H - 1) * mmpx, 2)]]
        spec["profile"] = prof
        if shape == "bottle":                                             # cap: above the narrowest point in the top third
            top = rad[int(H * 0.65):]; neck = int(H * 0.65) + int(np.argmin(top[: int(len(top) * 0.85)]))
            above = rad[neck:]
            if len(above) > 4 and above.max() > rad[neck] * 1.04:
                cap0 = neck + int(np.argmax(above > rad[neck] + (above.max() - rad[neck]) * 0.5))
                spec["cap_from_mm"] = round(cap0 * mmpx, 2)
        back = None
        if a.back:
            bi = Image.open(a.back); bm, _ = cutout(bi); brgb = np.asarray(bi.convert("RGB")).astype(float)
            b0, b1, c0, c1 = largest_blob(bm); bm = bm[b0:b1, c0:c1]; brgb = np.asarray(Image.fromarray(brgb[b0:b1, c0:c1].astype(np.uint8)).resize((W, H))).astype(float)
            bm = np.asarray(Image.fromarray((bm * 255).astype(np.uint8)).resize((W, H))) > 128; bL, bR = row_spans(bm)
            back = (brgb, bm, bL, bR, np.arange(H)[::-1])
        tex = unwrap(rgb, m, L, R, np.arange(H)[::-1], back)
        Image.fromarray(tex[::-1].astype(np.uint8)).resize((1024, min(1024, H))).save(out / "texture.png")   # top row = top
        spec["texture"] = "texture.png"; spec["front"] = 0.5
    else:
        flat = rgb.copy()                                                  # outside the outline: the row's own edge colour,
        for y in range(H):                                                 # never a neighbour from the photo
            if L[y] >= 0: flat[y, :L[y]] = rgb[y, L[y]]; flat[y, R[y] + 1:] = rgb[y, R[y]]
        crop = Image.fromarray(flat.astype(np.uint8)); crop.save(out / "front.png"); spec["front_tex"] = "front.png"
        d = a.depth_mm or (0.32 if shape == "box" else 0.3) * W * mmpx
        spec["size_mm"] = [round(W * mmpx, 1), round(hmm, 1), round(d, 1)]
        edge = np.median(np.concatenate([rgb[:, :4].reshape(-1, 3), rgb[:, -4:].reshape(-1, 3)]), 0); spec["side"] = hexc(edge)
        if a.back:
            bi = Image.open(a.back).convert("RGB"); bm, _ = cutout(Image.open(a.back)); b0, b1, c0, c1 = largest_blob(bm)
            bi.crop((c0, b0, c1, b1)).save(out / "back.png"); spec["back_tex"] = "back.png"
    json.dump(spec, open(out / "product.json", "w", encoding="utf-8"), indent=1)
    # check sheet: the photo with its outline and profile, and the texture
    vis = Image.fromarray(rgb.astype(np.uint8)).convert("RGB"); dr = ImageDraw.Draw(vis)
    for y in range(0, H, max(1, H // 60)):
        if L[y] >= 0: dr.line([(L[y], y), (R[y], y)], fill=(255, 0, 180), width=1)
    if "cap_from_mm" in spec:
        cy = H - 1 - int(spec["cap_from_mm"] / mmpx); dr.line([(0, cy), (W, cy)], fill=(0, 200, 255), width=3)
    parts = [vis.resize((int(W * 600 / H), 600))]
    if (out / "texture.png").exists(): parts.append(Image.open(out / "texture.png").resize((1000, 600)))
    elif (out / "front.png").exists(): parts.append(Image.open(out / "front.png").resize((int(W * 600 / H), 600)))
    sheet = Image.new("RGB", (sum(p.width for p in parts) + 10 * len(parts), 600), (30, 30, 30)); x = 0
    for p in parts: sheet.paste(p, (x, 0)); x += p.width + 10
    sheet.save(out / "check.jpg", quality=88)
    print(f"wrote {out / 'product.json'}: {shape}, {spec.get('height_mm')} mm, set {spec['set']}" + (f", cap from {spec['cap_from_mm']} mm" if 'cap_from_mm' in spec else ""))
    print(f"look at {out / 'check.jpg'} (pink = the outline per row, blue = where the cap starts)")


if __name__ == "__main__":
    main()
