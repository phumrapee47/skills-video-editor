"""Callouts that point at a real feature of the product, designed per mood and animated in order
(references/ad-craft.md: marker, then the line draws, then the text; they leave before the next beat).

Looks (the mood family picks one; brief "callout_style" overrides):
  dot       clean    a dot pops on the feature, a thin straight line, medium sans text fades in
  hairline  luxury   a ring grows round the feature, a hairline elbow leader, serif italic text wiped in slowly
  tech      tech     corner brackets close in on the feature, a glowing elbow leader with an end tick, spaced caps
                     scanned in behind a bright bar
  hand      fresh    a hand-drawn curved arrow drawn from the words to the feature, an arrowhead, handwritten text
                     (Mali, Thai + Latin) written left to right

The tip follows the feature every frame ("track": [[t, x, y], ...] in plan seconds and 0-1 screen coordinates, from
Blender's per-frame feature tracks); the label stays still so it can be read. Everything is drawn by libass (Thai is
shaped there): lines are real outline polygons (libass drops zero-area strokes), drawn per frame so a moving tip and a
growing line need no tricks. Used by edit_plan.py for titles with "style": "callout".
"""
import math, random, re

import fonts as _fonts

LOOKS = {"fresh": "hand", "luxury": "hairline", "tech": "tech", "clean": "dot"}
THAI = re.compile("[฀-๿]")
# per look: line width, text size (x H), timings in s: marker in, line start, line dur, text start, text dur, exit
SPEC = {"dot":      dict(w=0.0021, size=0.027, mk=0.18, l0=0.06, ld=0.26, t0=0.26, td=0.24, out=0.30),
        "hairline": dict(w=0.0012, size=0.034, mk=0.40, l0=0.15, ld=0.60, t0=0.55, td=0.55, out=0.45),
        "tech":     dict(w=0.0016, size=0.023, mk=0.22, l0=0.08, ld=0.22, t0=0.22, td=0.30, out=0.24),
        "hand":     dict(w=0.0034, size=0.042, mk=0.00, l0=0.00, ld=0.50, t0=0.28, td=0.60, out=0.30)}


def _font_for(look, text):
    """(ASS family, file) for the look; Thai text in a look whose font has no Thai goes to Kanit SemiBold."""
    thai = bool(THAI.search(text))
    if look == "hand":
        fam, path = _fonts.font("hand")
        return (fam, path) if "Mali" in fam or not thai else _fonts.font("sans")
    if look == "hairline" and not thai: return _fonts.font("serif_italic")
    if look == "tech": return _fonts.font("sans")
    return _fonts.font("sans_semibold")


def measure(text, path, size):
    """Rendered width in pixels at libass size `size` (libass sizes by ascent + descent)."""
    try:
        from PIL import ImageFont
        f = ImageFont.truetype(path, 100); asc, desc = f.getmetrics()
        return ImageFont.truetype(path, max(1, int(size * 100 / (asc + desc)))).getlength(text)
    except Exception:
        return 0.55 * size * len(text)


# ------------------------------------------------------------------ geometry (pixels)
def _area(p): return sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p))) / 2


def _path(polys):
    """ASS drawing (\\p3: quarter pixels) from closed polygons; outer ones are made the same winding so overlaps
    add up (libass fills non-zero); a polygon flagged as a hole is reversed."""
    out = []
    for poly, hole in polys:
        if len(poly) < 3: continue
        if (_area(poly) < 0) != hole: poly = poly[::-1]
        q = [(round(x * 4), round(y * 4)) for x, y in poly]
        out.append("m %d %d " % q[0] + " ".join("l %d %d" % p for p in q[1:]))
    return " ".join(out)


def stroke(pts, w, cap=True):
    """Outline polygon of a polyline of width w (mitred joins, limited), with small round-ish caps."""
    pts = [p for i, p in enumerate(pts) if i == 0 or math.dist(p, pts[i - 1]) > 0.3]
    if len(pts) < 2: return []
    h = w / 2; L, R = [], []
    for i, (x, y) in enumerate(pts):
        ns = []
        segs = ([(pts[i - 1], (x, y))] if i > 0 else []) + ([((x, y), pts[i + 1])] if i < len(pts) - 1 else [])
        for a, b in segs:
            dx, dy = b[0] - a[0], b[1] - a[1]; l = math.hypot(dx, dy) or 1; ns.append((-dy / l, dx / l))
        nx, ny = sum(n[0] for n in ns), sum(n[1] for n in ns); l = math.hypot(nx, ny) or 1; nx, ny = nx / l, ny / l
        k = 1.0 if len(ns) < 2 else min(2.5, 1 / max(0.4, ns[0][0] * nx + ns[0][1] * ny))
        L.append((x + nx * h * k, y + ny * h * k)); R.append((x - nx * h * k, y - ny * h * k))
    if cap:                                                                # half-round ends
        def arc(p, q):                                                     # round the end p, going from +n to -n through
            dx, dy = p[0] - q[0], p[1] - q[1]; l = math.hypot(dx, dy) or 1; dx, dy = dx / l, dy / l   # the outward direction
            nx, ny = -dy, dx
            return [(p[0] + h * (math.cos(a) * nx + math.sin(a) * dx), p[1] + h * (math.cos(a) * ny + math.sin(a) * dy))
                    for a in (math.pi / 4, math.pi / 2, 3 * math.pi / 4)]
        return L + arc(pts[-1], pts[-2]) + R[::-1] + arc(pts[0], pts[1])
    return L + R[::-1]


def circle(cx, cy, r, n=40): return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def partial(pts, f):
    """The first fraction f (by length) of a polyline."""
    if f >= 1: return pts
    if f <= 0 or len(pts) < 2: return pts[:1]
    seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]; want = sum(seg) * f; out = [pts[0]]
    for i, s in enumerate(seg):
        if want <= s:
            t = want / s if s else 0; a, b = pts[i], pts[i + 1]; out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)); return out
        want -= s; out.append(pts[i + 1])
    return out


def bezier(p0, p1, p2, p3, n=28):
    return [tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t ** 3 * d for a, b, c, d in zip(p0, p1, p2, p3))
            for t in (k / n for k in range(n + 1))]


def track_at(track, t):
    """(x, y) on a [[t, x, y], ...] track, linear between samples, held at the ends."""
    if len(track) == 1 or t <= track[0][0]: return track[0][1], track[0][2]
    for a, b in zip(track, track[1:]):
        if t <= b[0]:
            u = (t - a[0]) / max(1e-6, b[0] - a[0]); return a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u
    return track[-1][1], track[-1][2]


def _ease(x): x = min(1.0, max(0.0, x)); return 1 - (1 - x) ** 3
def _back(x): x = min(1.0, max(0.0, x)); c = 1.7; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def _cs(t): return int(round(t * 100))
def _ts(cs): return "%d:%02d:%02d.%02d" % (cs // 360000, cs // 6000 % 60, cs // 100 % 60, cs % 100)


# ------------------------------------------------------------------ the callout
def _wrap(text, fpath, size, room, sp):
    """One line if it fits, else two lines split at the space nearest the middle (Thai without spaces stays one)."""
    wid = lambda t: measure(t, fpath, size) + sp * len(t)
    if wid(text) <= room or " " not in text.strip(): return [text]
    words = text.split(); best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:]); m = max(wid(a), wid(b))
        if best is None or m < best[0]: best = (m, [a, b])
    return best[1]


def layout(it, W, H):
    """Where the text goes and how big: the leader ends in a shelf and the text sits on it (dot, hairline, tech), or
    the text sits at the start of the arrow (hand). Wraps to two lines before it shrinks."""
    look = it.get("look", "dot"); P = SPEC.get(look, SPEC["dot"]); text = str(it["text"]); thai = bool(THAI.search(text))
    if look == "tech" and not thai: text = text.upper()
    fam, fpath = _font_for(look, text); size = int(it.get("size") or round(H * P["size"]))
    sp = max(2, size // 6) if (look == "tech" and not thai) else 0      # spaced caps; never space Thai (marks drift off)
    right = it.get("side", "right") == "right"
    track = it.get("track") or [[float(it["start"])] + list(it.get("at", [0.5, 0.5]))]
    tx0, ty0 = track_at(track, (float(it["start"]) + float(it["end"])) / 2)
    lx, ly = it.get("label") or (tx0 + (1 if right else -1) * float(it.get("length", 0.14)), ty0 - 0.06)
    Kx, Ky = W * lx, H * ly
    pad = round(H * 0.008)
    lim_r = W * float(it.get("limit_r", 0.84 if H > W else 0.97)); lim_l = W * 0.04
    room = (lim_r - Kx - pad) if right else (Kx - pad - lim_l)
    lines = _wrap(text, fpath, size, room, sp)
    tw = max(measure(l, fpath, size) + sp * len(l) for l in lines)
    min_size = round(H * 0.019)
    if tw > room > 0:                                                    # still too wide: smaller, but not unreadable
        size = max(min_size, int(size * room / tw)); sp = max(2, size // 6) if sp else 0
        tw = max(measure(l, fpath, size) + sp * len(l) for l in lines)
    return dict(look=look, P=P, text=text, lines=lines, fam=fam, size=size, sp=sp, right=right, track=track,
                Kx=Kx, Ky=Ky, pad=pad, tw=tw, fits=tw <= max(room, 1) * 1.02)


def events(it, W, H, accent="FFD200"):
    """ASS Dialogue lines for one callout item: {"text", "look", "track" | "at", "side", "label", "start", "end",
    "fps", "size", "limit_r", "accent"}. "label" is the knee of the leader (where the shelf starts) for dot/hairline/
    tech, the start of the arrow for hand. Returns a list of strings."""
    Lo = layout(it, W, H); look, P = Lo["look"], Lo["P"]; right = Lo["right"]; sg = 1 if right else -1
    s, e = float(it["start"]), float(it["end"]); fps = float(it.get("fps", 30))
    accent = str(it.get("accent", accent)).lstrip("#").upper(); acc = accent[4:6] + accent[2:4] + accent[0:2]   # BGR
    Kx, Ky, pad, tw, size, track = Lo["Kx"], Lo["Ky"], Lo["pad"], Lo["tw"], Lo["size"], Lo["track"]
    nl = len(Lo["lines"]); lh = size * (0.92 if look == "hand" else 1.02)   # our own leading (libass's is loose)
    w = max(1.2, H * P["w"]); dark = max(1.5, H / 700)                   # line width, dark edge for contrast
    k = min(1.0, max(0.35, (e - s - P["out"] - 0.4) / max(0.3, P["t0"] + P["td"])))   # short window: everything faster
    mk, l0, ld, t0, td, out = P["mk"] * k, P["l0"] * k, P["ld"] * k, P["t0"] * k, P["td"] * k, min(P["out"], (e - s) * 0.25)
    shelf = tw + 2 * pad
    rnd = random.Random(sum(map(ord, Lo["text"])))
    wob = [rnd.uniform(-1, 1) for _ in range(6)]                         # the hand arrow's own wobble, the same every frame
    rows = []

    def row(layer, a, b, tags, draw):
        if draw: rows.append(f"Dialogue: {layer},{_ts(a)},{_ts(b)},S,,0,0,0,,{{\\an7\\pos(0,0)\\bord0\\shad0{tags}\\p3}}{draw}")

    def line(a, b, pts, color, width, layer, alpha="00", glow=False):
        if len(pts) < 2: return
        row(layer, a, b, f"\\1c&H000000&\\1a&H{'A8' if look == 'hairline' else '90'}&\\blur{3 if look == 'hairline' else 1.5}",
            _path([(stroke(pts, width + 2 * dark), False)]))
        if glow: row(layer, a, b, f"\\1c&H{acc}&\\1a&H70&\\blur7", _path([(stroke(pts, width * 2.5), False)]))
        row(layer + 1, a, b, f"\\1c&H{color}&\\1a&H{alpha}&", _path([(stroke(pts, width), False)]))

    frames = max(1, int(round((e - s) * fps)))
    for fi in range(frames):
        t = s + fi / fps; a, b = _cs(t), _cs(min(e, s + (fi + 1) / fps))
        if b <= a: continue
        u = t - s; g = 1.0 if t < e - out else max(0.0, (e - t) / out)      # g: 1 while shown, -> 0 on the way out
        x, y = track_at(track, t); X, Y = W * x, H * y
        if look != "hand":
            r0 = {"dot": H * 0.0062, "hairline": H * 0.016, "tech": H * 0.022}[look]
            if look == "dot":                                              # a dot pops on the feature
                rr = r0 * (_back(u / mk) if mk else 1.0) * g
                if rr > 0.5:
                    row(2, a, b, "\\1c&H000000&\\1a&H70&\\blur1", _path([(circle(X, Y, rr + dark * 1.5), False)]))
                    row(3, a, b, f"\\1c&H{acc}&", _path([(circle(X, Y, rr), False)]))
                cut = r0 + w
            elif look == "hairline":                                       # a ring grows round it, a fine centre point
                sc = _ease(u / mk) * g; rr = r0 * (0.4 + 0.6 * _ease(u / mk))
                if sc > 0.02:
                    al = "%02X" % int(255 * (1 - sc))
                    row(2, a, b, "\\1c&H000000&\\1a&HA8&\\blur3", _path([(circle(X, Y, rr + w + dark), False), (circle(X, Y, max(1, rr - w - dark)), True)]))
                    row(3, a, b, f"\\1c&HFFFFFF&\\1a&H{al}&", _path([(circle(X, Y, rr + w / 2), False), (circle(X, Y, rr - w / 2), True)]))
                    row(3, a, b, f"\\1c&HFFFFFF&\\1a&H{al}&", _path([(circle(X, Y, max(1.2, H * 0.0024)), False)]))
                cut = rr + w
            else:                                                          # tech: corner brackets close in, glowing
                sc = _ease(u / mk); half = r0 * (2.0 - sc); arm = r0 * 0.55; al = "%02X" % int(255 * (1 - sc * g))
                br = [[(X + cx * half, Y + cy * half - cy * arm), (X + cx * half, Y + cy * half), (X + cx * half - cx * arm, Y + cy * half)]
                      for cx, cy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                if sc * g > 0.02:
                    row(2, a, b, f"\\1c&H{acc}&\\1a&H60&\\blur6", _path([(stroke(p_, w * 2.4), False) for p_ in br]))
                    row(3, a, b, f"\\1c&H{acc}&\\1a&H{al}&", _path([(stroke(p_, w * 1.4), False) for p_ in br]))
                    row(3, a, b, f"\\1c&HFFFFFF&\\1a&H{al}&", _path([(circle(X, Y, max(1.5, H * 0.0022)), False)]))
                cut = H * 0.012
            path = [(X, Y), (Kx, Ky), (Kx + sg * shelf, Ky)]                 # leader -> knee -> shelf under the text
            d0 = math.dist(path[0], path[1])
            path = ([(X + (Kx - X) * cut / d0, Y + (Ky - Y) * cut / d0)] if d0 > cut else []) + path[1:]
            f = (_ease((u - l0) / ld) if ld else 1.0) * g
            if f > 0.01:
                p = partial(path, f)
                line(a, b, p, acc if look == "tech" else "FFFFFF", w, 4, glow=look == "tech")
                if look == "tech" and f >= 0.999:                           # an end tick
                    ex = Kx + sg * shelf; line(a, b, [(ex, Ky - size * 0.32), (ex, Ky + size * 0.32)], acc, w * 1.4, 4, glow=True)
        else:                                                              # hand: a curved arrow from the words to the feature
            Sx, Sy = Kx - sg * pad * 0.5, Ky + size * 0.25
            dx, dy = X - Sx, Y - Sy; dist = math.hypot(dx, dy) or 1; ux, uy = dx / dist, dy / dist
            Tx, Ty = X - ux * H * 0.014, Y - uy * H * 0.014                 # stop just short of the feature
            nx, ny = -uy, ux
            if ny > 0: nx, ny = -nx, -ny                                     # bulge upward
            bend = 0.3 * dist
            c1 = (Sx + dx * 0.25 + nx * bend * (1 + 0.1 * wob[0]), Sy + dy * 0.25 + ny * bend * (1 + 0.1 * wob[1]))
            c2 = (Sx + dx * 0.80 + nx * bend * 0.45 * (1 + 0.1 * wob[2]), Sy + dy * 0.80 + ny * bend * 0.45)
            curve = bezier((Sx, Sy), c1, c2, (Tx, Ty))
            curve = [(px + math.sin(i * 0.9 + wob[3] * 3) * H * 0.0009, py + math.cos(i * 0.7 + wob[4] * 3) * H * 0.0009) for i, (px, py) in enumerate(curve)]
            f = 1.0 if g < 1 else (_ease((u - l0) / ld) if ld else 1.0)
            al = "%02X" % int(255 * (1 - g))
            line(a, b, partial(curve, f), "FFFFFF", w, 4, alpha=al)
            if f >= 0.999:                                                 # the arrowhead
                hx, hy = curve[-1]; px_, py_ = curve[-4]; d = math.hypot(hx - px_, hy - py_) or 1; vx, vy = (hx - px_) / d, (hy - py_) / d
                hl = H * 0.020 * (min(1.0, _back((u - l0 - ld) / 0.12)) if g >= 1 else 1.0)
                for ang in (0.5, -0.5):
                    ca, sa = math.cos(ang), math.sin(ang)
                    if hl > 1: line(a, b, [(hx - hl * (vx * ca - vy * sa), hy - hl * (vx * sa + vy * ca)), (hx, hy)], "FFFFFF", w, 4, alpha=al)
    # the text: placed once; on the shelf (dot/hairline/tech) or at the arrow's start (hand); revealed from the knee
    s_t, e_t = s + t0, e
    if e_t - s_t > 0.1:
        ys = []
        if look == "hand":
            tx, ty = Kx + sg * pad, Ky; an = 4 if right else 6
            x0, x1 = (tx, tx + tw) if right else (tx - tw, tx); y0, y1 = ty - nl * lh / 2 - size * 0.5, ty + nl * lh / 2 + size * 0.5
            ys = [ty + (j - (nl - 1) / 2) * lh for j in range(nl)]
        else:
            tx, ty = Kx + sg * pad, Ky - pad * 0.6; an = 1 if right else 3
            x0, x1 = (tx, tx + tw) if right else (tx - tw, tx); y0, y1 = ty - nl * lh - size * 0.3, ty + 6
            ys = [ty - (nl - 1 - j) * lh for j in range(nl)]
        x0, x1, y0, y1 = int(x0) - 6, int(x1) + 8, int(y0), int(y1)
        if right or look == "hand": c0, c1 = f"\\clip({x0},{y0},{x0 + 1},{y1})", f"\\clip({x0},{y0},{x1},{y1})"   # wipe from the left
        else: c0, c1 = f"\\clip({x1 - 1},{y0},{x1},{y1})", f"\\clip({x0},{y0},{x1},{y1})"                         # from the knee
        ms = int(td * 1000); bord = max(2, round(H / 640)); shad = max(1, round(H / 960))
        base = (f"\\an{an}\\pos({int(tx)},@Y@)\\fn{Lo['fam']}\\fs{size}\\fsp{Lo['sp']}\\b0\\bord{bord}\\shad{shad}"
                f"\\3c&H000000&\\4c&H000000&\\4a&H80&\\1c&HFFFFFF&\\q2")
        tail = f"\\fad(0,{int(out * 1000)})"
        if look == "hand": base += "\\frz2" if right else "\\frz-2"
        if look == "hairline": base += f"\\bord{max(1, bord // 2)}\\blur0.6" + ("\\i1" if "Playfair" in Lo["fam"] else "")
        if look == "tech":
            for ln, yj in zip(Lo["lines"], ys): rows.append(f"Dialogue: 6,{_ts(_cs(s_t))},{_ts(_cs(e_t))},T,,0,0,0,,{{{base.replace('@Y@', str(int(yj)))}\\1c&H{acc}&\\3c&H{acc}&\\1a&HA0&\\3a&HA0&\\blur6{c0}\\t(0,{ms},{c1}){tail}}}{ln}")
            n_bar = int(td * fps) + 1
            for fi in range(n_bar):                                        # the scan bar ahead of the reveal
                t = s_t + fi / fps; v = _ease(fi / max(1, n_bar - 1)); bx = x0 + (x1 - x0) * v if right else x1 - (x1 - x0) * v
                bar = [(bx - w, y0 + 4), (bx + w, y0 + 4), (bx + w, y1 - 4), (bx - w, y1 - 4)]
                rows.append(f"Dialogue: 8,{_ts(_cs(t))},{_ts(_cs(t + 1 / fps))},S,,0,0,0,,{{\\an7\\pos(0,0)\\bord0\\shad0\\1c&H{acc}&\\blur2\\p3}}{_path([(bar, False)])}")
        for ln, yj in zip(Lo["lines"], ys):
            rows.append(f"Dialogue: 7,{_ts(_cs(s_t))},{_ts(_cs(e_t))},T,,0,0,0,,{{{base.replace('@Y@', str(int(yj)))}{c0}\\t(0,{ms},{c1}){tail}}}{ln}")
    return rows
