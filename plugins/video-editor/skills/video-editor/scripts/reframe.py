"""Subject-aware reframing for vertical (or square) exports: per clip of an edit plan, find where the person is and add
a "crop" so the 9:16 frame follows them instead of the centre. No model download: it looks for skin-coloured pixels
that move (people talk and gesture; sets, shelves and tables stay still). A wide shot (two people alike, or a small person)
keeps the whole frame over a blurred fill (fit "blur") instead of guessing.

Usage: python -I reframe.py <plan.json> [--out plan_reframed.json] [--aspect 9:16] [--fps 3] [--sheet check.jpg]
                            [--stack] [--speaker order|cut --words words.json] [--punch 1.3 --every 3]
  --speaker   two-shots follow who is talking (speaker_turns: lower-face motion per speech turn, a question hands the turn
              over): order = split screen, speaker in the lower panel; cut = full-height close-up of the speaker
  Only clips without a "crop" of their own are changed. Writes the plan with crops and a check sheet: every clip's
  middle frame with the chosen window drawn in. Look at it; move a wrong crop by hand (crop = [x, y, w, h] in source px).
Limits: a person standing still in front of a moving screen or crowd can lose to the motion; dark or strongly
coloured lighting can hide skin. Then set the crop by hand.
"""
import argparse, json, pathlib, subprocess, sys
import numpy as np

SW = 192                                     # analysis width
WINDOW = 0.32                                # crop width as a share of the source width (9:16 from 16:9); set from --aspect


def probe(path):
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", path],
                                  capture_output=True, text=True).stdout)["streams"][0]
    return s["width"], s["height"]


def frames(path, t0, t1, fps, w, h):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t0), "-t", str(max(0.2, t1 - t0)), "-i", path, "-vf", f"fps={fps},scale={w}:{h}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    return np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3).astype(np.float32)


def skin(f):
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b; cb = 128 - 0.169 * r - 0.331 * g + 0.5 * b; cr = 128 + 0.5 * r - 0.419 * g - 0.081 * b
    return (cr > 135) & (cr < 180) & (cb > 85) & (cb < 135) & (y > 40)


def subject_x(fr):
    """Horizontal centre (0..1) of the moving, skin-coloured subject; None if nothing found."""
    if len(fr) < 2: return None
    sk = np.mean([skin(f) for f in fr], axis=0)                          # how often a pixel is skin
    mv = np.mean(np.abs(np.diff(fr.mean(axis=3), axis=0)), axis=0)        # how much it changes
    score = sk * (0.3 + np.minimum(mv, 30) / 30)
    col = score.sum(axis=0); col = np.convolve(col, np.ones(9) / 9, "same")
    if col.max() < 1.0: return None
    # slide a window as wide as the vertical crop; crop only if one position holds most of the subject
    n = len(col); win = max(1, int(round(n * WINDOW))); cs = np.concatenate([[0.0], np.cumsum(col)])
    held = cs[win:] - cs[:-win]; k = int(np.argmax(held)); share = held[k] / cs[-1]
    if share < 0.65: return "wide"                 # two people apart, or a group: keep the whole frame
    seg = col[k:k + win]; xs = np.arange(k, k + win)
    return float((xs * seg).sum() / seg.sum() / n)


def faces(fr, W, H):
    """(cx, head top) in source px of the person in the left half and in the right half of a two-shot; None if one is missing."""
    sk = np.mean([skin(f) for f in fr], axis=0); mv = np.mean(np.abs(np.diff(fr.mean(axis=3), axis=0)), axis=0)
    score = sk * (0.3 + np.minimum(mv, 30) / 30); h, w = score.shape; out = []
    for x0, x1 in ((0, w // 2), (w // 2, w)):
        part = score[:, x0:x1]; tot = part.sum()
        if tot < 1: return None
        ys, xs = np.mgrid[0:h, x0:x1]; cx = (xs * part).sum() / tot / w * W
        rows = part.sum(axis=1); cum = np.cumsum(rows) / rows.sum()
        out.append((cx, float(np.searchsorted(cum, 0.08)) / h * H))   # top of the skin mass = the face (hands sit lower)
    return out


def panel(face, W, H, OW, OH, top):
    """Crop for one split-screen panel (aspect W : H/2) around a face; the top panel holds the head lower, clear of a headline."""
    pa = OW / (OH / 2); cw = min(W / 2, H * pa) * 0.9; ch = cw / pa       # a bit tighter than half the frame
    cx, head = face; lift = 0.40 if top else 0.18
    X = int(min(max(0, cx - cw / 2), W - cw)) // 2 * 2; Y = int(min(max(0, head - ch * lift), H - ch)) // 2 * 2
    return [X, Y, int(cw) // 2 * 2, int(ch) // 2 * 2]


def two_people(fr, W, H, OW, OH):
    """Split screen for a two-shot: one crop per person (left person on top, right person below)."""
    f = faces(fr, W, H)
    return [panel(f[0], W, H, OW, OH, True), panel(f[1], W, H, OW, OH, False)] if f else None


def words_q(words, a, b):
    """True when the speech span a..b ends on a question."""
    inside = [w for w in words if a <= w["start"] and w["end"] <= b + 0.01]
    return bool(inside) and inside[-1]["text"].strip().endswith("?")


def speaker_turns(src, t0, t1, fcs, W, H, words):
    """Who is speaking when, in a two-shot: [(start, end, person 0|1)], no model. Per speech turn (word gaps >= 0.5 s or
    a sentence end; 1 s steps without words) compare how much each person's lower face (mouth, jaw) moves. Raw values:
    both faces are the same size in a two-shot. Tried and dropped on the Royal Society interview: scaling each person by
    their own normal motion (a very still listener won on any twitch) and taking off upper-face motion (a speaker who
    moves the whole head lost). Frames across a cut and the first 0.6 s of a shot are left out, spikes are capped.
    Right after a question the other person is taken to answer unless the faces clearly disagree. Turns under 1 s or
    without a clear winner keep the speaker. Tested on 7 two-shots: the main speaker right in all 7; answers shorter
    than ~1.5 s at the very end of a shot are missed."""
    aw = 384; ah = round(aw * H / W); fr = frames(src, t0, t1, 10, aw, ah)
    if len(fr) < 4: return []
    g = fr.mean(axis=3); d = np.abs(np.diff(g, axis=0)); s = aw / W
    fw = 0.075 * aw                                                             # face width ~7.5% of a two-shot
    whole = d.mean(axis=(1, 2)); ok = whole < max(12.0, 5 * np.median(whole))   # a camera cut or flash changes every pixel: not talking
    ok &= np.arange(len(whole)) >= 6                                            # the first 0.6 s of a shot (dissolve, camera settling) moves every face
    m = []
    for cx, head in fcs:
        x0, x1 = int(max(0, cx * s - fw)), int(min(aw, cx * s + fw)); y = head * s
        m.append(d[:, int(y + 0.9 * fw):int(y + 1.9 * fw), x0:x1].mean(axis=(1, 2)) * ok)   # mouth and jaw: under the eyes
    cap = np.percentile(np.concatenate(m)[np.concatenate([ok, ok])], 95) + 1e-3      # a nod or a hand is one spike: capped
    m = [np.minimum(v, cap) for v in m]
    ts = t0 + (np.arange(len(m[0])) + 1) / 10
    spans = []
    if words:
        cur = None
        for w in words:
            if w["end"] < t0 or w["start"] > t1: continue
            if cur and w["start"] - cur[1] < 0.5 and not cur[2]: cur[1] = w["end"]; cur[2] = w["text"].strip().endswith(("?", ".", "!"))   # a question and its answer often have no pause between them
            else:
                if cur: spans.append(cur)
                cur = [w["start"], w["end"], w["text"].strip().endswith(("?", ".", "!"))]
        if cur: spans.append(cur)
        spans = [[x[0], x[1], words_q(words, x[0], x[1])] for x in spans]
    else:
        spans = [[a, min(a + 1, t1), False] for a in np.arange(t0, t1, 1.0)]
    turns, who = [], None
    asked = False
    for a, b, q in spans:
        sel = (ts >= a) & (ts <= b) & ok
        if sel.sum() < 3: continue
        s0, s1 = float(m[0][sel].mean()), float(m[1][sel].mean())
        p = 0 if s0 > 1.15 * s1 else 1 if s1 > 1.15 * s0 else who
        if p is None: p = int(s1 > s0)
        if asked and p == who and max(s0, s1) < 1.5 * min(s0, s1): p = 1 - who   # after a question the other person answers, unless the faces clearly disagree
        asked = q and b - a >= 1.0
        if turns and (p == turns[-1][2] or b - a < 1.0): turns[-1][1] = b   # short or same: no switch
        else: turns.append([a, b, p])
        who = turns[-1][2]
    if turns: turns[0][0] = t0; turns[-1][1] = t1
    for x, y in zip(turns, turns[1:]): x[1] = y[0] = round((x[1] + y[0]) / 2, 2)   # switch in the pause between turns
    return [(round(a, 2), round(b, 2), p) for a, b, p in turns]


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan"); ap.add_argument("--out"); ap.add_argument("--aspect"); ap.add_argument("--fps", type=float, default=3)
    ap.add_argument("--sheet")
    ap.add_argument("--stack", action="store_true", help="two-shots become a top/bottom split screen instead of the blur fit")
    ap.add_argument("--punch", type=float, default=0.0, help="alternate normal and this zoom (e.g. 1.3) inside close-ups, one camera = something changes every few seconds")
    ap.add_argument("--every", type=float, default=3.0, help="target seconds between punch-in changes (cut at the nearest pause in speech)")
    ap.add_argument("--speaker", choices=["order", "cut"], help="two-shots follow who is talking (needs --words for turns): order = split screen with the speaker in the lower panel, cut = full close-up of the speaker")
    ap.add_argument("--words", help="word timings (transcribe_whisper.py / Scribe JSON) so punch cuts land in pauses, never inside a word")
    a = ap.parse_args()
    pp = pathlib.Path(a.plan).resolve(); plan = json.load(open(pp, encoding="utf-8"))
    OW, OH = plan["output"].get("size", [1080, 1920]); asp = eval(a.aspect.replace(":", "/")) if a.aspect else OW / OH
    tiles = []
    new = []                                   # split clips at camera cuts inside them (multi-camera interviews)
    for c in plan["clips"]:
        if c.get("crop") or c.get("card"): new.append(c); continue
        src = str((pp.parent / c["src"]).resolve()); W, H = probe(src); sh = round(SW * H / W)
        fr = frames(src, c["in"], c["out"], 6, SW, sh); cuts = []
        pd = [float(np.abs(fr[i] - fr[i - 1]).mean()) for i in range(1, len(fr))]; base = float(np.median(pd)) if pd else 0.0
        for i in range(1, len(fr)):
            h0 = np.histogram(fr[i - 1], 32, (0, 256))[0]; h1 = np.histogram(fr[i], 32, (0, 256))[0]
            # a cut measured 0.275 histogram change against a 0.006 baseline; close-ups of two people in one studio have
            # alike colours (0.13) but every pixel changes (mean difference 50 against a baseline of 2)
            if 0.5 * np.abs(h0 / h0.sum() - h1 / h1.sum()).sum() > 0.15 or pd[i - 1] > max(25.0, 8 * base):
                cuts.append(round(c["in"] + i / 6, 2))
        edges = [c["in"]] + [t for t in cuts if t - c["in"] > 0.5 and c["out"] - t > 0.5] + [c["out"]]
        for j, (t0, t1) in enumerate(zip(edges, edges[1:])):
            part = dict(c); part["in"], part["out"] = t0, t1
            if j: part.pop("transition", None); part.pop("titles", None)
            new.append(part)
    if len(new) != len(plan["clips"]): print(f"split at camera cuts: {len(plan['clips'])} -> {len(new)} clips")
    plan["clips"] = new
    for k, c in enumerate(plan["clips"]):
        if c.get("crop") or c.get("card"): continue
        src = str((pp.parent / c["src"]).resolve()); W, H = probe(src); sh = round(SW * H / W)
        cw = min(W, round(H * asp / 2) * 2); fr = frames(src, c["in"], c["out"], a.fps, SW, sh)
        globals()["WINDOW"] = cw / W
        x = subject_x(fr)
        if x == "wide" and a.speaker:      # two people: follow whoever is talking
            fcs = faces(fr, W, H)
            if fcs:
                words_all = json.load(open(a.words, encoding="utf-8"))["words"] if a.words else []
                turns = speaker_turns(src, c["in"], c["out"], fcs, W, H, words_all); parts = []
                for j, (t0, t1, p) in enumerate(turns):
                    part = dict(c); part["in"], part["out"] = t0, t1; part.pop("crop", None); part["speaker"] = p
                    if j: part.pop("transition", None); part.pop("titles", None)
                    if a.speaker == "order":
                        part["fit"] = "stack"; part["stack"] = [panel(fcs[1 - p], W, H, OW, OH, True), panel(fcs[p], W, H, OW, OH, False)]
                    else:
                        ch = int(H * 0.75) // 2 * 2; cw2 = int(ch * asp) // 2 * 2           # a two-shot is wide: closer than full height
                        X = int(min(max(0, fcs[p][0] - cw2 / 2), W - cw2)) // 2 * 2; Y = int(min(max(0, fcs[p][1] - ch * 0.25), H - ch)) // 2 * 2
                        part["fit"] = "crop"; part["crop"] = [X, Y, cw2, ch]
                    parts.append(part)
                c["_parts"] = parts
                print(f"clip {k + 1}: {c['in']:.1f}-{c['out']:.1f}s two-shot, speaker turns " + ", ".join(f"{t0:.1f}-{t1:.1f} {'LR'[p]}" for t0, t1, p in turns) + f" -> {a.speaker}")
                continue
        if x == "wide" and a.stack:        # two people: split screen, one above the other
            st = two_people(fr, W, H, OW, OH)
            if st:
                c["fit"] = "stack"; c["stack"] = st; c.pop("crop", None)
                print(f"clip {k + 1}: {c['in']:.1f}-{c['out']:.1f}s two-shot -> split screen {st}"); continue
        if x == "wide":                    # keep the whole frame over a blurred fill rather than crop between people
            c["fit"] = "blur"; print(f"clip {k + 1}: {c['in']:.1f}-{c['out']:.1f}s wide shot -> blur fit"); continue
        cx = (x if x is not None else 0.5) * W
        X = int(min(max(0, cx - cw / 2), W - cw)) // 2 * 2
        c["crop"] = [X, 0, cw, H]; c["fit"] = "crop"
        print(f"clip {k + 1}: {c['in']:.1f}-{c['out']:.1f}s subject at {('%.2f' % x) if x is not None else 'not found (centre)'} -> crop x={X}")
        if a.sheet and len(fr):
            from PIL import Image, ImageDraw
            im = Image.fromarray(fr[len(fr) // 2].astype(np.uint8)).resize((384, round(384 * H / W))); d = ImageDraw.Draw(im); s = 384 / W
            d.rectangle((X * s, 0, (X + cw) * s, im.height - 1), outline=(255, 40, 40), width=3); d.text((4, 2), f"clip {k + 1}", fill=(255, 255, 0))
            tiles.append(im)
    plan["clips"] = [q for c in plan["clips"] for q in (c.pop("_parts", None) or [c])]
    if a.punch > 1.0:                        # punch-in: split close-ups at pauses, every other piece zoomed in
        words = json.load(open(a.words, encoding="utf-8"))["words"] if a.words else []
        gaps = sorted(((w1["end"] + w2["start"]) / 2) for w1, w2 in zip(words, words[1:]) if w2["start"] - w1["end"] >= 0.12)
        new, n_punch = [], 0
        for c in plan["clips"]:
            if not c.get("crop") or c.get("card") or c.get("fit") == "blur" or c["out"] - c["in"] < 2 * a.every * 0.8:
                new.append(c); continue
            cuts, t = [], c["in"] + a.every
            while t < c["out"] - a.every * 0.6:
                near = [g for g in gaps if abs(g - t) < a.every * 0.4 and c["in"] + 1.2 < g < c["out"] - 1.2]
                cut = min(near, key=lambda g: abs(g - t)) if near else (t if not words else None)
                if cut: cuts.append(round(cut, 3)); t = cut + a.every
                else: t += 0.5
            edges = [c["in"]] + cuts + [c["out"]]
            x, y, w, h = c["crop"]
            for j, (t0, t1) in enumerate(zip(edges, edges[1:])):
                part = dict(c); part["in"], part["out"] = t0, t1
                if j: part.pop("transition", None); part.pop("titles", None)
                if j % 2 == 1:                       # zoomed piece: same centre line
                    w2, h2 = int(w / a.punch) // 2 * 2, int(h / a.punch) // 2 * 2
                    part["crop"] = [x + (w - w2) // 2 // 2 * 2, y, w2, h2]; n_punch += 1   # anchored at the top: the face moves down, away from a headline
                new.append(part)
        plan["clips"] = new; print(f"punch-in: {n_punch} zoomed pieces at x{a.punch}, {len(new)} clips")
    out = a.out or str(pp.with_name(pp.stem + "_reframed.json"))
    json.dump(plan, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1); print("wrote", out)
    if tiles:
        from PIL import Image
        cols = 4; rows = (len(tiles) + cols - 1) // cols; th = tiles[0].height; sheet = Image.new("RGB", (cols * 384, rows * th))
        for k, im in enumerate(tiles): sheet.paste(im, (k % cols * 384, k // cols * th))
        sheet.save(a.sheet, quality=85); print("sheet", a.sheet)
