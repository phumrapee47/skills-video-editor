"""Lifestyle backdrops for 3D product ads: CC0 HDRIs from Poly Haven (https://polyhaven.com, no attribution required),
fetched on request into a local cache (~/.video-editor/hdri, or VIDEO_EDITOR_HDRI), never bundled with the skill.

  python -I hdri.py list
  python -I hdri.py fetch beach [garden interior bar] [--res 2k]     (ask the user first: file names and sizes below)

The ad uses them as `background: "hdri:<name>"`: the product stands on a tabletop, the place is the light and the
blurred backdrop (ad_look.hdri_scene).
"""
import argparse, json, os, pathlib, sys, urllib.request

HDRIS = {   # name: (Poly Haven slug, what it is, mood families, tabletop, world z rotation in degrees, strength)
            # rotation: the lens sees the panorama at u = 0.75 - rot / 360 (beach: the sea; garden: the pergola path; interior: the window)
    "beach":    ("spiaggia_di_mondello", "sunny beach, morning; cold drinks, summer", ["fresh"], "wood_light", 120, 0.9),
    "garden":   ("symmetrical_garden_02", "green garden, partly cloudy; fresh, natural", ["fresh", "clean"], "stone", 97, 1.0),
    "interior": ("cayley_interior", "warm room, lamp, window to a balcony; cafe, home", ["clean", "luxury"], "wood_dark", 90, 1.3),
    "bar":      ("colorful_studio", "lounge with a bar, warm lights; evening", ["luxury"], "marble_dark", 0, 1.2),
}
SIZES_MB = {"1k": 1.7, "2k": 6.8, "4k": 27}
UA = "skills-video-editor (https://github.com/phumrapee47/skills-video-editor)"


def cache():
    return pathlib.Path(os.environ.get("VIDEO_EDITOR_HDRI") or pathlib.Path.home() / ".video-editor" / "hdri")


def path(name):
    """The cached file for a name (any resolution, the largest first), or None."""
    if name not in HDRIS: return None
    slug = HDRIS[name][0]
    for r in ("4k", "2k", "1k"):
        p = cache() / f"{slug}_{r}.hdr"
        if p.exists(): return p
    return None


def fetch(name, res="2k"):
    slug = HDRIS[name][0]; out = cache() / f"{slug}_{res}.hdr"; out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists(): return out
    url = f"https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/{res}/{slug}_{res}.hdr"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r, open(out, "wb") as f: f.write(r.read())
    if open(out, "rb").read(10)[:2] != b"#?": out.unlink(); raise RuntimeError(f"not an HDR file: {url}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0]); ap.add_argument("cmd", choices=["list", "fetch"])
    ap.add_argument("names", nargs="*"); ap.add_argument("--res", default="2k", choices=list(SIZES_MB))
    a = ap.parse_args()
    if a.cmd == "list":
        for k, (slug, what, fams, top, rot, s) in HDRIS.items():
            p = path(k); print(f"{k:9s} {slug:24s} {'cached' if p else f'~{SIZES_MB[a.res]} MB at {a.res}':14s} {what}  [{', '.join(fams)}]")
        print(f"cache: {cache()}  (CC0, Poly Haven)"); sys.exit(0)
    for n in a.names or []:
        if n not in HDRIS: sys.exit(f"unknown HDRI {n}; one of {list(HDRIS)}")
        p = fetch(n, a.res); print(f"{n}: {p} ({p.stat().st_size / 1e6:.1f} MB, CC0 Poly Haven)")
