"""Platform safe zones for vertical video: where TikTok, Instagram Reels and YouTube Shorts draw their own interface
(tabs, the like/comment/share column, caption and music text), and a check that titles and captions stay clear of it.

Usage: python -I safe_zones.py <video.mp4> <file.ass> [<file.ass> ...] [--platform all|tiktok|reels|shorts] [--sheet out.jpg]
  Reads text positions from the ASS tracks the edit burned in (edit_plan.py keeps them as <out>.titles.ass and the
  captions file), prints every title or caption that sits in a covered area, and with --sheet draws the zones over
  frames of the video. edit_plan.py runs it automatically for 9:16 outputs.
Zones are fractions of the frame, measured from the apps' layouts at 1080x1920 (late 2026) and kept a little
generous; "all" is their union, the safe choice when one edit goes to every platform.
"""
import argparse, json, pathlib, re, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
ZONES = {   # (x0, y0, x1, y1) as fractions of width / height
    "tiktok": [("top tabs", 0.0, 0.0, 1.0, 0.075), ("right buttons", 0.85, 0.38, 1.0, 0.84), ("caption + music", 0.0, 0.80, 1.0, 1.0)],
    "reels":  [("top bar", 0.0, 0.0, 1.0, 0.07), ("right buttons", 0.86, 0.45, 1.0, 0.86), ("caption + audio", 0.0, 0.82, 1.0, 1.0)],
    "shorts": [("top bar", 0.0, 0.0, 1.0, 0.07), ("right buttons", 0.84, 0.45, 1.0, 0.88), ("title + channel", 0.0, 0.85, 1.0, 1.0)],
}
ZONES["all"] = ZONES["tiktok"] + ZONES["reels"] + ZONES["shorts"]


def ass_time(t):
    h, m, s = t.split(":"); return int(h) * 3600 + int(m) * 60 + float(s)


def ass_boxes(path):
    """Text boxes (start, end, x0, y0, x1, y1, text) of every Dialogue with text (drawings and empty events skipped)."""
    from edit_plan import text_width
    txt = open(path, encoding="utf-8").read()
    W = int(re.search(r"PlayResX:\s*(\d+)", txt)[1]); H = int(re.search(r"PlayResY:\s*(\d+)", txt)[1])
    styles = {}
    for m in re.finditer(r"^Style:\s*([^,]+),([^,]+),(\d+),(?:[^,]*,){15}(\d+),", txt, re.M): styles[m[1]] = (int(m[3]), int(m[4]))
    boxes = []
    for line in txt.splitlines():
        if not line.startswith("Dialogue:"): continue
        parts = line.split(",", 9); s, e, style, text = ass_time(parts[1]), ass_time(parts[2]), parts[3], parts[9]
        tags = "".join(re.findall(r"\{([^}]*)\}", text))
        if re.search(r"\\p[1-9]", tags): continue                      # vector drawing (underline, dim): not text
        plain = re.sub(r"\{[^}]*\}", "", text)
        if not plain.strip(): continue
        fs, an = styles.get(style, (60, 5))
        m = re.findall(r"\\fs(\d+)", tags); fs = int(m[-1]) if m else fs
        m = re.findall(r"\\an(\d)", tags); an = int(m[-1]) if m else an
        pos = re.search(r"\\pos\((-?[\d.]+),(-?[\d.]+)\)", tags) or re.search(r"\\move\([^)]*?,[^)]*?,(-?[\d.]+),(-?[\d.]+)", tags)
        lines = plain.split("\\N"); w = max(text_width(l, fs) for l in lines); h = fs * 1.1 * len(lines)
        if pos: x, y = float(pos[1]), float(pos[2])
        else: x, y = W / 2, (H * 0.09 + h / 2 if an in (7, 8, 9) else H / 2)
        x0 = x - (0 if an in (1, 4, 7) else (w if an in (3, 6, 9) else w / 2))
        y0 = y - (h if an in (1, 2, 3) else (0 if an in (7, 8, 9) else h / 2))
        boxes.append({"start": s, "end": e, "x0": x0 / W, "y0": y0 / H, "x1": (x0 + w) / W, "y1": (y0 + h) / H, "text": plain.replace("\\N", " ")[:40]})
    return boxes


def check(boxes, platform="all", min_overlap=0.15):
    """[(zone, box)] where a text box is covered by more than min_overlap of its area."""
    hits = []
    for b in boxes:
        area = max(1e-9, (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]))
        for name, x0, y0, x1, y1 in ZONES[platform]:
            ix = max(0, min(b["x1"], x1) - max(b["x0"], x0)); iy = max(0, min(b["y1"], y1) - max(b["y0"], y0))
            if ix * iy / area > min_overlap: hits.append((name, b)); break
    return hits


def sheet(video, out, platform="all", n=6):
    """Frames of the video with the covered areas shaded red (to look at before posting)."""
    from PIL import Image, ImageDraw
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video], capture_output=True, text=True).stdout)
    tiles = []
    for k in range(n):
        t = d * (k + 0.5) / n
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", "scale=270:480", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        im = Image.frombytes("RGB", (270, 480), raw).convert("RGBA"); ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); dr = ImageDraw.Draw(ov)
        for _, x0, y0, x1, y1 in ZONES[platform]: dr.rectangle((x0 * 270, y0 * 480, x1 * 270, y1 * 480), fill=(255, 0, 0, 70), outline=(255, 0, 0, 200))
        tiles.append(Image.alpha_composite(im, ov).convert("RGB"))
    sh = Image.new("RGB", (270 * n, 480))
    for k, im in enumerate(tiles): sh.paste(im, (k * 270, 0))
    sh.save(out, quality=85)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video"); ap.add_argument("ass", nargs="+"); ap.add_argument("--platform", choices=list(ZONES), default="all"); ap.add_argument("--sheet")
    a = ap.parse_args()
    boxes = [b for p in a.ass if pathlib.Path(p).exists() for b in ass_boxes(p)]
    hits = check(boxes, a.platform)
    for name, b in hits[:12]: print(f"  {b['start']:6.2f}s  in {name:15s} '{b['text']}'")
    print(f"{len(hits)} of {len(boxes)} text events reach a covered area ({a.platform})")
    if a.sheet: sheet(a.video, a.sheet, a.platform); print("sheet", a.sheet)
    sys.exit(1 if hits else 0)
