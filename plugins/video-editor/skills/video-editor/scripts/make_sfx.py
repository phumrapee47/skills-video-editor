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


KIT = {"whoosh": lambda r: whoosh(r), "swish": lambda r: whoosh(r, 0.28, 900, 6000, 0.4, (0.4, -0.4)), "pop": pop,
       "riser": riser, "impact": impact, "hit": hit, "chime": chime}


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
