"""Free sound library for the skill: music, place sounds (ambience) and effects from licensed sources, with tags and
credits, kept in one local folder that every edit can use.

Library folder: ~/.video-editor/sounds (or VIDEO_EDITOR_SOUNDS). The catalogue of everything that can be fetched (address,
licence, credit, tags) ships with the skill: assets/sound_catalog.json. The audio itself is not in the skill's git repo.

Usage:
  python -I sound_library.py catalog [--commons picks.json]   rebuild the catalogue (incompetech + Scott Buckley lists;
                                                               Commons place sounds come from a hand-checked picks file)
  python -I sound_library.py fetch --set balanced|starter|all  download a set (ASK THE USER FIRST: names, sources, size)
  python -I sound_library.py fetch --ids incompetech:carefree ...   single items (the pickers do this for an approved set)
  python -I sound_library.py index                            measure what is downloaded -> <library>/library.json, the
                                                               file music_mood.py and place_sound.py read
  python -I sound_library.py credits plan.json                credit lines for every library sound a plan uses
Sources (checked 2026-11-22; robots.txt allows these fetches):
  incompetech.com   Kevin MacLeod, 1,443 tracks, CC BY 4.0, human tags: feel, genre, instruments, BPM, description
  scottbuckley.com.au  Scott Buckley, 267 cinematic/orchestral/ambient tracks, CC BY 4.0 (no per-track tags: measured)
  commons.wikimedia.org  53 hand-picked place recordings (waterfall, waves, birds, night insects, city, market, cafe,
                    temple bells, trains, fireworks, rain...), CC0 / public domain / CC BY only (no ShareAlike, no NC)
Not fetched automatically: kenney.nl (CC0 effect packs; the site asks AI tools not to fetch it: download by hand and put
the folder in <library>/sfx/kenney), OpenGameArt (blocks AI agents), freepd.com (closed), Freesound / Pixabay (need an
account or forbid redistribution).
Every CC BY sound needs its credit in the video description: `credits` prints them, edit_plan.py writes <out>.credits.txt.
"""
import argparse, json, os, pathlib, re, subprocess, sys, time, urllib.parse, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
CATALOG = HERE.parent / "assets" / "sound_catalog.json"
UA = "Mozilla/5.0 (compatible; video-editor-skill; +https://github.com/phumrapee47/skills-video-editor)"
FEEL_MOOD = {"Bright": "upbeat", "Uplifting": "upbeat", "Grooving": "upbeat", "Driving": "epic", "Bouncy": "playful", "Humorous": "playful",
             "Relaxed": "warm", "Calming": "calm", "Mysterious": "wonder", "Mystical": "wonder", "Epic": "epic", "Action": "epic", "Intense": "tense",
             "Aggressive": "tense", "Suspenseful": "tense", "Eerie": "tense", "Unnerving": "tense", "Dark": "tense", "Somber": "sad"}


def library_dir():
    return pathlib.Path(os.environ.get("VIDEO_EDITOR_SOUNDS") or pathlib.Path.home() / ".video-editor" / "sounds")


def get(url, binary=False):
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120)
    return r.read() if binary else r.read().decode("utf-8", "replace")


def slug(t): return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:60]


def secs(l):
    try: h, m, s = map(int, str(l).split(":")); return h * 3600 + m * 60 + s
    except Exception: return 0


def build_catalog(commons_file=None):
    old = json.load(open(CATALOG, encoding="utf-8")) if CATALOG.exists() else []
    cat = [e for e in old if e["source"] == "commons"]
    if commons_file:
        cat = []
        for i in json.load(open(commons_file, encoding="utf-8")):
            name = i["title"][5:]
            cat.append({"id": "commons:" + slug(name), "source": "commons", "kind": "ambience", "type": i["type"], "title": name, "url": i["url"],
                        "page": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(i["title"].replace(" ", "_")), "license": i["license"],
                        "credit": f"\"{name}\" by {i['artist'] or 'unknown'} via Wikimedia Commons ({i['license']})", "seconds": round(i["dur"] or 0), "bytes": i["bytes"]})
    genres = {g["id"]: g["genre"] for g in json.loads(get("https://incompetech.com/music/royalty-free/genre.json"))}
    for p in json.loads(get("https://incompetech.com/music/royalty-free/pieces.json")):
        feels = [f.strip() for f in (p.get("feel") or "").split(",") if f.strip()]
        cat.append({"id": "incompetech:" + slug(p["title"]), "source": "incompetech", "kind": "music", "title": p["title"],
                    "url": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/" + urllib.parse.quote(p["filename"]),
                    "page": "https://incompetech.com/music/royalty-free/music.html", "license": "CC BY 4.0",
                    "credit": f"\"{p['title']}\" Kevin MacLeod (incompetech.com), Licensed under Creative Commons: By Attribution 4.0 License",
                    "feels": feels, "moods": sorted({FEEL_MOOD[f] for f in feels if f in FEEL_MOOD}), "genre": genres.get(int(p["genre"]) if str(p.get("genre", "")).isdigit() else -1, ""),
                    "instruments": p.get("instruments"), "description": (p.get("description") or "")[:240], "bpm": float(p["bpm"]) if str(p.get("bpm", "")).replace(".", "").isdigit() else None,
                    "seconds": secs(p.get("length"))})
    sb, pg = {}, 1
    while pg < 40:
        try: h = get("https://www.scottbuckley.com.au/library/" + (f"page/{pg}/" if pg > 1 else ""))
        except Exception: break
        new = 0
        for u in re.findall(r'https?://[^"\' ]+\.mp3', h):
            if u in sb: continue
            name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", pathlib.Path(urllib.parse.unquote(u)).stem).replace("_", " ").replace("-", " ").strip()
            sb[u] = name; new += 1
        if not new: break
        pg += 1; time.sleep(1.5)
    for u, name in sb.items():
        cat.append({"id": "scottbuckley:" + slug(name), "source": "scottbuckley", "kind": "music", "title": name, "url": u,
                    "page": "https://www.scottbuckley.com.au/library/", "license": "CC BY 4.0", "genre": "Cinematic",
                    "credit": f"\"{name}\" by Scott Buckley (www.scottbuckley.com.au), released under Creative Commons Attribution 4.0", "feels": [], "moods": []})
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    json.dump(cat, open(CATALOG, "w", encoding="utf-8"), indent=0, ensure_ascii=False)
    print(f"catalogue: {sum(e['source'] == 'incompetech' for e in cat)} incompetech, {sum(e['source'] == 'scottbuckley' for e in cat)} Scott Buckley, "
          f"{sum(e['source'] == 'commons' for e in cat)} Commons place sounds -> {CATALOG}")


def balanced(cat, n_mac):
    """MacLeod tracks spread over every feel and genre: round robin by feel, a new genre first within each feel."""
    skip_g = {"Holiday", "Polka"}
    mac = [e for e in cat if e["source"] == "incompetech" and e["genre"] not in skip_g and 20 <= (e.get("seconds") or 0) <= 420
           and not {"Ren Faire", "Medieval"} & set(e.get("feels", []))]
    by_feel = {}
    for e in sorted(mac, key=lambda e: (abs((e.get("seconds") or 150) - 150), e["title"])):   # 1-4 min first: easiest to edit with
        for f in e.get("feels", []) or ["-"]: by_feel.setdefault(f, []).append(e)
    pick, ids, used_genre = [], set(), {}
    while len(pick) < n_mac and any(by_feel.values()):
        for f, lst in by_feel.items():
            if len(pick) >= n_mac: break
            while lst:
                lst.sort(key=lambda e: used_genre.get((f, e["genre"]), 0)); e = lst.pop(0)
                if e["id"] not in ids:
                    ids.add(e["id"]); pick.append(e); used_genre[(f, e["genre"])] = used_genre.get((f, e["genre"]), 0) + 1; break
    return pick


def select(cat, which):
    if which == "all": return cat
    n_mac, n_sb = (400, 10 ** 6) if which == "balanced" else (150, 40)
    sb = [e for e in cat if e["source"] == "scottbuckley"][:n_sb]
    return balanced(cat, n_mac) + sb + [e for e in cat if e["source"] == "commons"]


def dest(e):
    ext = pathlib.Path(urllib.parse.urlparse(e["url"]).path).suffix.lower() or ".mp3"
    p = library_dir() / e["kind"] / e["source"] / (slug(e["title"]) + ext)
    if not p.exists() and p.with_suffix(".mp3").exists(): return p.with_suffix(".mp3")   # big wav/flac fetched as Commons' mp3
    return p


def fetch(entries):
    """Fast sources first (place sounds, Scott Buckley), then incompetech: it serves ~40 KB/s per connection, so it gets
    3 polite parallel connections (~4-5 h for 400 tracks). Files appear one by one; `index` can run any time."""
    from concurrent.futures import ThreadPoolExecutor
    import threading
    order = {"commons": 0, "scottbuckley": 1, "incompetech": 2}; lock = threading.Lock(); stats = {"ok": 0, "fail": 0, "bytes": 0, "n": 0}
    def one(e):
        d = dest(e)
        if d.exists() and d.stat().st_size > 1000:
            with lock: stats["ok"] += 1; stats["n"] += 1
            return
        d.parent.mkdir(parents=True, exist_ok=True); tmp = d.with_suffix(d.suffix + ".part")
        url = e["url"]
        if e["source"] == "commons" and (e.get("bytes") or 0) > 15e6 and d.suffix in (".wav", ".flac", ".oga"):
            name = url.split("/")[-1]; url = url.replace("/commons/", "/commons/transcoded/") + f"/{name}.mp3"   # Commons' own mp3 of a big wav/flac
            d = d.with_suffix(".mp3"); tmp = d.with_suffix(".mp3.part")
            if d.exists() and d.stat().st_size > 1000:
                with lock: stats["ok"] += 1; stats["n"] += 1
                return
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=600); size = 0
            with open(tmp, "wb") as fh:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk: break
                    fh.write(chunk); size += len(chunk)
            tmp.replace(d)
            with lock: stats["ok"] += 1; stats["bytes"] += size
        except Exception as ex:
            tmp.unlink(missing_ok=True)
            with lock: stats["fail"] += 1
            print(f"FAIL {e['id']}: {ex}", flush=True)
        with lock:
            stats["n"] += 1
            if stats["n"] % 20 == 0: print(f"  {stats['n']}/{len(entries)} done, {stats['bytes'] / 1e9:.2f} GB new", flush=True)
        time.sleep(1.5 if e["source"] == "commons" else 0.5)
    first = {"Bright": 3, "Uplifting": 3, "Grooving": 3, "Relaxed": 2.5, "Calming": 2.5, "Driving": 2, "Bouncy": 1, "Mystical": 1, "Epic": 1}
    useful = lambda e: sum(first.get(f, 0) for f in e.get("feels", [])) - 3 * len(set(e.get("feels", [])) & {"Humorous", "Eerie", "Unnerving", "Dark", "Aggressive"})
    def source(src, workers):
        part = sorted([e for e in entries if e["source"] == src], key=lambda e: -useful(e))   # the moods most edits need arrive first
        if not part: return
        print(f"{src}: {len(part)} items, {workers} connection(s)", flush=True)
        with ThreadPoolExecutor(workers) as ex: list(ex.map(one, part))
    th = [threading.Thread(target=source, args=sw) for sw in (("commons", 1), ("scottbuckley", 2), ("incompetech", 3))]   # sources side by side
    for t in th: t.start()
    for t in th: t.join()
    print(f"fetched: {stats['ok']} ok, {stats['fail']} failed, {stats['bytes'] / 1e9:.2f} GB new in {library_dir()}", flush=True)


def index():
    sys.path.insert(0, str(HERE)); import music_mood
    lib = library_dir(); cat = {str(dest(e)): e for e in json.load(open(CATALOG, encoding="utf-8"))}
    lp = lib / "library.json"; old = {t["file"]: t for t in json.load(open(lp, encoding="utf-8"))["tracks"]} if lp.exists() else {}
    tracks, amb = [], []
    for path, e in cat.items():
        p = pathlib.Path(path)
        if not p.exists(): continue
        rel = p.relative_to(lib).as_posix()
        if e["kind"] == "music":
            if rel in old and "bpm_measured" in old[rel]: tracks.append({**old[rel], "moods": old[rel].get("moods") or e.get("moods")}); continue
            try: f = music_mood.features(p)
            except Exception as ex: print("skip", rel, ex); continue
            v, a = music_mood.place(f)
            tracks.append({"file": rel, "id": e["id"], "title": e["title"], "source": e["source"], "genre": e.get("genre"), "feels": e.get("feels", []),
                           "moods": e.get("moods", []), "description": e.get("description", ""), "instruments": e.get("instruments"),
                           "measured_mood": music_mood.mood_of(v, a), "valence": v, "arousal": a, "bpm_measured": f["bpm"],
                           **{k: f[k] for k in ("bpm", "beat_strength", "onsets_per_s", "brightness_hz", "loud_db", "intro_s")},
                           "credit": e["credit"], "license": e["license"]})
            if len(tracks) % 50 == 0: print(f"  indexed {len(tracks)} tracks", flush=True)
        else:
            amb.append({"file": rel, "id": e["id"], "type": e.get("type"), "title": e["title"], "seconds": e.get("seconds"), "credit": e["credit"], "license": e["license"]})
    json.dump({"tracks": tracks, "ambience": amb, "note": "built by sound_library.py index; moods from the composers' own tags where they exist"},
              open(lp, "w", encoding="utf-8"), indent=0, ensure_ascii=False)
    print(f"library: {len(tracks)} music tracks, {len(amb)} place sounds -> {lp}")


def credits(plan_path):
    plan = json.load(open(plan_path, encoding="utf-8")); base = pathlib.Path(plan_path).resolve().parent; lib = library_dir().resolve()
    cat = {str(dest(e).resolve()).lower(): e for e in json.load(open(CATALOG, encoding="utf-8"))}
    lines = []
    for a in plan.get("audio", []):
        p = str((base / a["src"]).resolve()).lower()
        if p in cat and cat[p]["credit"] not in lines: lines.append(cat[p]["credit"])
    return lines


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["catalog", "fetch", "index", "credits", "size"]); ap.add_argument("plan", nargs="?")
    ap.add_argument("--commons"); ap.add_argument("--set", choices=["starter", "balanced", "all"]); ap.add_argument("--ids", nargs="*")
    a = ap.parse_args()
    if a.cmd == "catalog": build_catalog(a.commons); sys.exit(0)
    if a.cmd == "index": index(); sys.exit(0)
    if a.cmd == "credits": print("\n".join(credits(a.plan))); sys.exit(0)
    cat = json.load(open(CATALOG, encoding="utf-8"))
    ent = select(cat, a.set) if a.set else [e for e in cat if e["id"] in set(a.ids or [])]
    est = sum(e.get("bytes") or (e.get("seconds") or 200) * 36000 for e in ent)   # ~288 kbps when the size is unknown
    print(f"{len(ent)} items: {sum(e['kind'] == 'music' for e in ent)} music, {sum(e['kind'] != 'music' for e in ent)} place sounds, ~{est / 1e9:.1f} GB")
    if a.cmd == "fetch": fetch(ent)
