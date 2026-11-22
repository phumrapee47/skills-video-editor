"""Measure a folder of reference edits (the clips a user likes) so a genre's editing grammar comes from numbers plus a
look at the frames, not from memory.

Usage: python -I study_refs.py <folder> <out_dir> [--strip 12]
Per clip -> <out_dir>/study.json and one line in the printed table:
  cuts       hard cuts (histogram jump or every pixel changing) and dissolves (several frames of moderate change)
  shot_s     median / 10th / 90th percentile shot length; cuts per 10 s
  on_beat    beat sync of the cuts (phase concentration on the beat or half-beat grid): 1 = every cut at the same point
             of the beat, ~0 = random; next to it the level random cuts rarely pass (1.5/sqrt(cuts)); tempo from spectral
             flux as in music_beats.py
  talk       share of 1 s windows that look like speech (energy in the voice band that rises and falls 3-8 times a second)
  lufs       integrated loudness; aspect; resolution
  strip      <out_dir>/<name>.jpg: --strip frames across the clip, time stamped (look at them: titles, transitions,
             speed ramps and colour cannot be measured here)
Limits: fast whip pans and flashes read as cuts; slow cross-fades under ~8 frames read as cuts; talk is a guess (singing
reads as talk). Use the numbers to compare clips, then check by eye.
"""
import argparse, json, pathlib, re, subprocess, sys
import numpy as np

AW = 160; FPS = 25; SR = 16000


def frames(path):
    p = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                                   "-of", "json", str(path)], capture_output=True, text=True).stdout)
    w, h = p["streams"][0]["width"], p["streams"][0]["height"]; ah = max(2, round(AW * h / w / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps={FPS},scale={AW}:{ah}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    n = len(raw) // (AW * ah * 3)
    return np.frombuffer(raw[:n * AW * ah * 3], np.uint8).reshape(n, ah, AW, 3).astype(np.float32), w, h, float(p["format"]["duration"])


def cuts_of(fr):
    hd = []; pdf = []
    for i in range(1, len(fr)):
        a = np.histogram(fr[i - 1], 32, (0, 256))[0]; b = np.histogram(fr[i], 32, (0, 256))[0]
        hd.append(0.5 * np.abs(a / a.sum() - b / b.sum()).sum()); pdf.append(float(np.abs(fr[i] - fr[i - 1]).mean()))
    hd, pdf = np.array(hd), np.array(pdf); base = np.median(pdf) + 1e-6
    hard = [(i + 1) / FPS for i in range(len(hd)) if (hd[i] > 0.15 or pdf[i] > max(25, 8 * base))
            and (i == 0 or not (hd[i - 1] > 0.15 or pdf[i - 1] > max(25, 8 * base)))]
    mod = (pdf > 3 * base) & (pdf < max(25, 8 * base)) & (hd < 0.15)             # moderate change, frame after frame
    diss, k = [], 0
    while k < len(mod):
        if mod[k]:
            j = k
            while j < len(mod) and mod[j]: j += 1
            if j - k >= 4 and not any(abs(h - (k + j) / 2 / FPS) < 0.5 for h in hard):   # >= 0.4 s of blending
                diss.append(round((k + j) / 2 / FPS, 2))
            k = j
        k += 1
    return hard, diss


def audio(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def beat_grid(x, dur):
    hop, nfft = 512, 2048
    if len(x) < SR * 5: return None
    n = 1 + (len(x) - nfft) // hop; fr = np.lib.stride_tricks.as_strided(x, (n, nfft), (x.strides[0] * hop, x.strides[0])) * np.hanning(nfft)
    mag = np.log1p(np.abs(np.fft.rfft(fr, axis=1))); fl = np.maximum(0, np.diff(mag, axis=0)).sum(axis=1)
    fl = np.maximum(fl - np.convolve(fl, np.ones(16) / 16, "same"), 0); fps = SR / hop
    ac = np.correlate(fl, fl, "full")[len(fl) - 1:]; lags = np.arange(len(ac)) / fps; ok = (lags >= 60 / 180) & (lags <= 60 / 70)
    k = int(np.argmax(np.where(ok, ac, 0))); period = lags[k]; strength = ac[k] / (np.median(ac[ok]) + 1e-9)
    if 0 < k < len(ac) - 1:                                             # fractional lag: whole lags give only a few tempos
        y0, y1, y2 = ac[k - 1], ac[k], ac[k + 1]; period = (k + 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2 + 1e-9)) / fps
    step = period * fps; best, phase = -1, 0
    for ph in np.arange(0, step, 0.5):
        idx = (ph + np.arange(0, len(fl) - ph, step)).astype(int); sc = fl[idx].sum()
        if sc > best: best, phase = sc, ph
    return {"bpm": round(60 / period, 1), "period": period, "first": phase / fps + hop / SR, "strength": round(float(strength), 1)}


def talk_share(x):
    """Share of 2 s windows that look like speech: voice-band loudness that swings (gaps between words; music is steady:
    log-std 0.3-0.5 on music-only promos, 0.9-1.1 on talking vlogs) and pulses at syllable rate (3-8 Hz)."""
    if len(x) < 2 * SR: return 0.0
    hop = SR // 100; n = len(x) // hop; fr = x[:n * hop].reshape(n, hop) * np.hanning(hop)
    f = np.abs(np.fft.rfft(fr, axis=1)) ** 2; fq = np.fft.rfftfreq(hop, 1 / SR)
    env = np.sqrt(f[:, (fq > 300) & (fq < 3400)].sum(axis=1)); hits = 0; wins = n // 200
    for w in range(wins):
        sg = env[w * 200:(w + 1) * 200]
        if sg.max() < 1e-3: continue
        sp = np.abs(np.fft.rfft(sg - sg.mean())); mf = np.fft.rfftfreq(200, 0.01)
        if np.std(np.log(sg + 1e-3)) > 0.7 and sp[(mf >= 3) & (mf <= 8)].sum() > 0.2 * sp[1:].sum(): hits += 1
    return round(hits / max(1, wins), 2)


def lufs(path):
    out = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-vn", "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", out); return float(m[-1]) if m else None


def strip(path, dur, out, n):
    from PIL import Image, ImageDraw
    tiles = []
    for k in range(n):
        t = dur * (k + 0.5) / n
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=-2:200", "-f", "image2pipe",
                              "-vcodec", "png", "-"], capture_output=True).stdout
        if not raw: continue
        import io
        im = Image.open(io.BytesIO(raw)).convert("RGB"); ImageDraw.Draw(im).text((4, 4), f"{t:.1f}s", fill=(255, 255, 0)); tiles.append(im)
    if not tiles: return
    W = sum(t.width for t in tiles[:6]); rows = (len(tiles) + 5) // 6
    sheet = Image.new("RGB", (W, 200 * rows))
    for k, t in enumerate(tiles): sheet.paste(t, (sum(x.width for x in tiles[k // 6 * 6:k]), 200 * (k // 6)))
    sheet.save(out, quality=80)


def study(path, out_dir, n_strip):
    fr, w, h, dur = frames(path); hard, diss = cuts_of(fr)
    edges = [0.0] + hard + [dur]; shots = np.diff(edges)
    x = audio(path); bg = beat_grid(x, dur); on = chance = None
    if bg and hard and bg["strength"] >= 1.6:
        def sync(per):                                                  # phase concentration: 1 = all cuts at one point of the beat
            ph = np.array([(t - 1 / FPS / 2) / per for t in hard]) * 2 * np.pi        # any fixed offset counts (reaction delay)
            return float(np.abs(np.mean(np.exp(1j * ph))))
        on = round(max(sync(bg["period"]), sync(bg["period"] / 2)), 2); chance = round(float(1.5 / np.sqrt(len(hard))), 2)   # random cuts stay under ~1.5/sqrt(n)
    r = {"file": path.name, "dur": round(dur, 1), "size": f"{w}x{h}", "aspect": "9:16" if h > w * 1.3 else ("1:1" if abs(h - w) < 0.1 * w else "16:9"),
         "cuts": len(hard), "dissolves": len(diss), "cuts_per_10s": round(10 * len(hard) / dur, 1),
         "shot_med": round(float(np.median(shots)), 2), "shot_p10": round(float(np.percentile(shots, 10)), 2), "shot_p90": round(float(np.percentile(shots, 90)), 2),
         "bpm": bg and bg["bpm"], "beat_strength": bg and bg["strength"], "on_beat": on, "on_beat_chance": chance,
         "talk": talk_share(x), "lufs": lufs(path), "cut_times": [round(t, 2) for t in hard], "dissolve_times": diss}
    strip(path, dur, out_dir / (path.stem + ".jpg"), n_strip)
    return r


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder"); ap.add_argument("out_dir"); ap.add_argument("--strip", type=int, default=12)
    a = ap.parse_args()
    out = pathlib.Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in pathlib.Path(a.folder).rglob("*") if p.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv"))
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(6) as ex: res = list(ex.map(study, files, [out] * len(files), [a.strip] * len(files)))
    json.dump(res, open(out / "study.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{'file':42s} {'dur':>6s} {'asp':>5s} {'cuts/10s':>8s} {'shot med':>8s} {'p10-p90':>11s} {'diss':>4s} {'bpm':>6s} {'on beat':>12s} {'talk':>5s} {'LUFS':>6s}")
    for r in res:
        ob = f"{r['on_beat']:.2f} ({r['on_beat_chance']:.2f})" if r["on_beat"] is not None else "-"
        print(f"{r['file'][:42]:42s} {r['dur']:6.1f} {r['aspect']:>5s} {r['cuts_per_10s']:8.1f} {r['shot_med']:8.2f} {r['shot_p10']:5.2f}-{r['shot_p90']:<5.2f} {r['dissolves']:4d} "
              f"{str(r['bpm'] or '-'):>6s} {ob:>12s} {r['talk']:5.2f} {str(r['lufs']):>6s}")
