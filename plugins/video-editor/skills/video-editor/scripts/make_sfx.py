"""Make the editing sound effects (whoosh, swish, pop, riser, impact, hit, chime) from noise and tones, numpy only:
no download, no credits, no licence to check, and the same kit on every machine.

Usage: python -I make_sfx.py <out_dir> [--only whoosh pop ...] [--seed 7]
Writes 48 kHz stereo WAVs peak-normalised to -1 dBFS; sound_design.py sets their level against the speech.
  whoosh  0.55 s band-passed noise sweeping up then down, panned across: B-roll in, transitions
  swish   0.28 s short airy sweep: B-roll out, punch-in (subtle)
  pop     0.09 s pitch-dropping blip with a click: a title, headline or topic item appearing
  riser   1.6 s noise + tone rising to a cut-off: into the hook / the first answer after a topic card
  impact  0.9 s low thump with a noise burst: a huge word behind the person, a text card
  hit     0.35 s short punchy thud: a hard cut to a card, a number
  chime   0.8 s two soft bell partials: an ending card, a list item ticked
"""
import argparse, pathlib, wave
import numpy as np

SR = 48000


def env(n, a, d, curve=2.0):
    """Attack fraction a, then decay to 0 by the end (curve > 1 = faster fall)."""
    t = np.linspace(0, 1, n); e = np.where(t < a, t / max(a, 1e-6), 1 - (t - a) / max(1 - a, 1e-6))
    e = np.clip(e, 0, 1); return np.where(t < a, e, e ** curve) * d


def bandsweep(noise, f_lo, f_hi, bw, frac_peak=0.5, frames=64):
    """Time-varying band-pass of noise: centre frequency goes f_lo -> f_hi (at frac_peak) -> f_lo, done per short block in
    the frequency domain with overlap-add (numpy only)."""
    n = len(noise); hop = n // frames; win = 2 * hop; out = np.zeros(n + win); w = np.hanning(win)
    freqs = np.fft.rfftfreq(win, 1 / SR)
    for k in range(frames + 1):
        s = k * hop; seg = np.zeros(win); part = noise[s:s + win]; seg[:len(part)] = part
        x = k / frames; pos = x / frac_peak if x < frac_peak else (1 - x) / (1 - frac_peak)
        fc = f_lo * (f_hi / f_lo) ** pos; g = np.exp(-0.5 * ((np.log(freqs + 1) - np.log(fc)) / bw) ** 2)
        out[s:s + win] += np.fft.irfft(np.fft.rfft(seg * w) * g, win)
    return out[:n]


def stereo(x, pan_from=0.0, pan_to=0.0):
    p = np.linspace(pan_from, pan_to, len(x)); l = np.cos((p + 1) * np.pi / 4); r = np.sin((p + 1) * np.pi / 4)
    return np.stack([x * l, x * r], axis=1)


def whoosh(rng, dur=0.55, lo=300, hi=4200, peak=0.55, pan=(-0.6, 0.6)):
    n = int(dur * SR); x = bandsweep(rng.standard_normal(n), lo, hi, 0.55, peak)
    x *= env(n, peak, 1.0, 1.6); return stereo(x, *pan)


def pop(rng, dur=0.09):
    n = int(dur * SR); t = np.arange(n) / SR; f = 950 * np.exp(-t * 18) + 280       # pitch drops fast: a bubble pop
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 45)
    x[:int(0.002 * SR)] += rng.standard_normal(int(0.002 * SR)) * 0.4                # the click at the start
    return stereo(x)


def riser(rng, dur=1.6):
    n = int(dur * SR); t = np.arange(n) / SR
    x = bandsweep(rng.standard_normal(n), 400, 7000, 0.7, 0.999) * 0.8
    f = 180 * (2 ** (3 * t / dur)); ph = 2 * np.pi * np.cumsum(f) / SR               # tone: a 3-octave climb
    x += 0.35 * sum(np.sin(k * ph) / k for k in (1, 2, 3, 4, 5)) * (t / dur) ** 2        # few harmonics: a square wave aliases
    x *= (t / dur) ** 2.2; x[-int(0.01 * SR):] *= np.linspace(1, 0, int(0.01 * SR))   # crescendo, sharp stop on the cut
    return stereo(x, -0.3, 0.3)


def impact(rng, dur=0.9):
    n = int(dur * SR); t = np.arange(n) / SR; f = 95 * np.exp(-t * 6) + 42
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5.5)
    burst = bandsweep(rng.standard_normal(n), 120, 2500, 0.8, 0.02) * np.exp(-t * 22) * 0.6
    return stereo(np.tanh(1.6 * (x + burst)))                                          # a little saturation: weight


def hit(rng, dur=0.35):
    n = int(dur * SR); t = np.arange(n) / SR; f = 160 * np.exp(-t * 25) + 60
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 14)
    x += bandsweep(rng.standard_normal(n), 800, 5000, 0.6, 0.02) * np.exp(-t * 40) * 0.5
    return stereo(np.tanh(2 * x))


def chime(rng, dur=0.8):
    n = int(dur * SR); t = np.arange(n) / SR; x = np.zeros(n)
    for f, a, d in ((1318.5, 1.0, 4.0), (1975.5, 0.55, 5.5), (2637.0, 0.25, 7.0)):    # E6, B6, E7: bright, consonant
        x += a * np.sin(2 * np.pi * f * t) * np.exp(-t * d)
    x *= np.minimum(1, t / 0.004); return stereo(x, -0.2, 0.2)


def fizz(rng, dur=1.1):
    """A can opening: a click, a hiss that falls away, a few bubbles."""
    n = int(dur * SR); t = np.arange(n) / SR
    hiss = bandsweep(rng.standard_normal(n), 3500, 9000, 0.5, 0.02) * np.exp(-t * 3.2) * 0.9
    click = np.zeros(n); click[:int(0.004 * SR)] = rng.standard_normal(int(0.004 * SR)) * 1.5
    pops = np.zeros(n)
    for _ in range(40):
        i = int(rng.uniform(0.05, dur * 0.9) * SR); f = rng.uniform(1800, 4200); m = int(0.012 * SR)
        if i + m < n: pops[i:i + m] += np.sin(2 * np.pi * f * np.arange(m) / SR) * np.exp(-np.arange(m) / (0.003 * SR)) * rng.uniform(0.05, 0.25)
    return stereo(hiss + click + pops, -0.1, 0.1)


def slash(rng, dur=0.32):
    """A blade cutting the air: a fast bright sweep and a thin metallic ring (the light-blade cut in a 3D ad)."""
    n = int(dur * SR); t = np.arange(n) / SR
    air = bandsweep(rng.standard_normal(n), 1500, 9000, 0.35, 0.55) * np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 3
    ring = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((3520, 0.25), (5230, 0.15))) * np.exp(-np.maximum(t - dur * 0.55, 0) * 18) * (t > dur * 0.55)
    return stereo(air + ring, -0.7, 0.5)


def splash(rng, dur=1.3):
    """Juice bursting out of cut fruit: a soft wet thump, a spray of noise, then droplets falling (bright blips that
    drop in pitch and thin out)."""
    n = int(dur * SR); t = np.arange(n) / SR
    thump = np.sin(2 * np.pi * np.cumsum(120 * np.exp(-t * 18) + 55) / SR) * np.exp(-t * 14) * 0.8
    spray = bandsweep(rng.standard_normal(n), 600, 7000, 0.7, 0.05) * np.exp(-t * 4.5) * 0.7
    drops = np.zeros(n)
    for _ in range(70):
        s = rng.uniform(0.03, dur * 0.85); i = int(s * SR); m = int(0.03 * SR)
        if i + m >= n: continue
        f0 = rng.uniform(900, 2600); tt = np.arange(m) / SR
        drops[i:i + m] += np.sin(2 * np.pi * np.cumsum(f0 * (1 + 2.5 * np.exp(-tt * 120))) / SR) * np.exp(-tt * 140) * rng.uniform(0.1, 0.4) * np.exp(-s * 1.8)
    return stereo(np.tanh(1.3 * (thump + spray + drops)), 0.3, -0.3)


def clink(rng, dur=0.6):
    """Ice touching ice or glass: a bright inharmonic ping with a fast tick on the attack."""
    n = int(dur * SR); t = np.arange(n) / SR; x = np.zeros(n)
    for f, a, d in ((2950, 1.0, 9.0), (4710, 0.6, 12.0), (6380, 0.35, 16.0), (8120, 0.2, 22.0)):
        x += a * np.sin(2 * np.pi * f * rng.uniform(0.98, 1.02) * t) * np.exp(-t * d)
    tick = np.zeros(n); m = int(0.003 * SR); tick[:m] = rng.standard_normal(m) * 0.8
    return stereo(x * np.minimum(1, t / 0.0015) + tick, 0.2, 0.1)


def twist(rng, dur=0.9):
    """A plastic cap unscrewing: quick ratchet clicks (the seal ring breaking) speeding up, then the gas hiss."""
    n = int(dur * SR); t = np.arange(n) / SR; x = np.zeros(n); m = int(0.006 * SR)
    for k in range(9):
        i = int((0.04 + 0.42 * (k / 9) ** 0.8) * SR)
        if i + m < n: x[i:i + m] += rng.standard_normal(m) * np.exp(-np.arange(m) / (0.0012 * SR)) * rng.uniform(0.5, 0.9)
    hiss = bandsweep(rng.standard_normal(n), 2500, 8000, 0.6, 0.02) * np.exp(-np.maximum(t - 0.5, 0) * 5) * (t > 0.5) * 0.7
    return stereo(x + hiss, -0.15, 0.15)


def rip(rng, dur=0.55):
    """A foil/plastic bag tearing: a crackling noise burst that rises in pitch, many tiny crinkles."""
    n = int(dur * SR); t = np.arange(n) / SR
    body = bandsweep(rng.standard_normal(n), 1200, 7000, 0.5, 0.7) * np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 0.7
    crack = np.zeros(n)
    for _ in range(90):
        i = int(rng.uniform(0.0, dur * 0.95) * SR); m = int(0.002 * SR)
        if i + m < n: crack[i:i + m] += rng.standard_normal(m) * rng.uniform(0.2, 0.8)
    return stereo(np.tanh(1.5 * (body + crack)), -0.5, 0.5)


def snap(rng, dur=0.5):
    """Chocolate breaking: one sharp dry crack, a short woody knock, a few crumbs ticking."""
    n = int(dur * SR); t = np.arange(n) / SR
    crack = bandsweep(rng.standard_normal(n), 2000, 9000, 0.5, 0.01) * np.exp(-t * 80)
    knock = np.sin(2 * np.pi * np.cumsum(900 * np.exp(-t * 30) + 400) / SR) * np.exp(-t * 45) * 0.5
    ticks = np.zeros(n)
    for _ in range(12):
        i = int(rng.uniform(0.05, dur * 0.9) * SR); m = int(0.003 * SR)
        if i + m < n: ticks[i:i + m] += rng.standard_normal(m) * rng.uniform(0.05, 0.2)
    return stereo(np.tanh(2 * (crack + knock + ticks)), -0.1, 0.1)


def sonic_logo(name, family="fresh", dur=1.5):
    """A brand's sound signature for the end card: three notes and a held chord taken from the brand name (the same
    name always gives the same motif), timbre by mood family - fresh: bright plucks; luxury: low warm piano-like
    tones with a pad; tech: synth saw with a glide; clean: soft bells."""
    import hashlib
    h = int(hashlib.sha1(name.upper().encode()).hexdigest(), 16)
    scales = {"fresh": [72, 74, 76, 79, 81, 84], "luxury": [57, 60, 62, 64, 67, 69], "tech": [64, 67, 69, 71, 74, 76], "clean": [72, 76, 79, 81, 83, 88]}
    sc = scales.get(family, scales["fresh"]); notes = [sc[(h >> (4 * i)) % len(sc)] for i in range(3)]
    notes[-1] = max(notes[-1], sc[3])                                      # end high: a rise, not a sigh
    n = int(dur * SR); t = np.arange(n) / SR; x = np.zeros(n); step = 0.13 if family in ("fresh", "tech") else 0.17
    hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)
    def tone(f, t0, length, kind):
        i0 = int(t0 * SR); m = min(n - i0, int(length * SR)); tt = np.arange(m) / SR
        if kind == "saw": w = sum(np.sin(2 * np.pi * f * k * tt * (1 + 0.004 * np.exp(-tt * 20))) / k for k in range(1, 7))
        elif kind == "bell": w = np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(2 * np.pi * f * 2.76 * tt) * np.exp(-tt * 6)
        else: w = np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt) + 0.12 * np.sin(2 * np.pi * 3 * f * tt)
        dec = {"saw": 3.5, "bell": 2.2, "pluck": 6.0, "piano": 2.8}[kind]
        x[i0:i0 + m] += w * np.exp(-tt * dec) * np.minimum(1, tt / 0.004)
    kind = {"fresh": "pluck", "luxury": "piano", "tech": "saw", "clean": "bell"}.get(family, "pluck")
    for i, m_ in enumerate(notes): tone(hz(m_), 0.05 + i * step, 0.6, kind)
    t_ch = 0.05 + 3 * step
    for m_ in (notes[-1], notes[-1] - 5, notes[-1] - 12): tone(hz(m_), t_ch, dur - t_ch, kind)   # the held chord
    if family == "luxury": x += 0.25 * np.sin(2 * np.pi * hz(notes[-1] - 24) * t) * np.minimum(1, t / 0.3) * np.exp(-np.maximum(t - 0.8, 0) * 3)
    return stereo(x * np.minimum(1, (dur - t) / 0.08), -0.15, 0.15)


KIT = {"whoosh": lambda r: whoosh(r), "swish": lambda r: whoosh(r, 0.28, 900, 6000, 0.4, (0.4, -0.4)), "pop": pop,
       "riser": riser, "impact": impact, "hit": hit, "chime": chime, "fizz": fizz, "slash": slash, "splash": splash, "clink": clink, "twist": twist, "rip": rip, "snap": snap}


def write(path, x):
    x = x / (np.abs(x).max() + 1e-9) * 10 ** (-1 / 20)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((x * 32767).astype("<i2").tobytes())


def make(out_dir, only=None, seed=7):
    out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True); paths = {}
    for name, fn in KIT.items():
        if only and name not in only: continue
        p = out / f"{name}.wav"
        if not p.exists(): write(p, fn(np.random.default_rng(seed)))
        paths[name] = p
    return paths


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir"); ap.add_argument("--only", nargs="*"); ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    for k, p in make(a.out_dir, a.only, a.seed).items(): print(f"{k:7s} {p}")
