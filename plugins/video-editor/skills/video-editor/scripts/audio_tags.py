"""What is heard in a piece of audio: YAMNet (AudioSet, 521 classes) through onnxruntime, grouped into the place sounds an
editor cares about. Claude cannot hear; this is how the skill knows a waterfall from traffic.

Usage: python -I audio_tags.py <media> [--start 0] [--dur 10] [--top 8]
Model: ~/.video-editor/models/yamnet/yamnet-onnx-float (Qualcomm AI Hub ONNX export, MIT; ask the user before downloading:
yamnet-onnx-float.zip 13.9 MB from qaihub-public-assets.s3.us-west-2.amazonaws.com, class names in labels.txt).
Front end as published with YAMNet: 16 kHz mono, 25 ms Hann window every 10 ms, 512-point FFT magnitude, 64 mel bands
125-7500 Hz (HTK mel), log(mel + 0.001), 0.96 s patches every 0.48 s; scores are averaged over the patches.
"""
import argparse, os, pathlib, subprocess, sys
import numpy as np

SR = 16000
MODEL_DIR = pathlib.Path(os.environ.get("VIDEO_EDITOR_MODELS") or pathlib.Path.home() / ".video-editor" / "models") / "yamnet" / "yamnet-onnx-float"
GROUPS = {   # AudioSet display names -> place-sound group (first match wins per class)
    "water": ["Waterfall", "Stream", "Waves, surf", "Ocean", "Rain", "Raindrop", "Rain on surface", "Water", "Splash, splatter", "Gurgling",
              "Drip", "Pour", "Trickle, dribble", "Boat, Water vehicle", "Rowboat, canoe, kayak", "Thunderstorm", "Thunder"],
    "birds": ["Bird", "Bird vocalization, bird call, bird song", "Chirp, tweet", "Squawk", "Pigeon, dove", "Coo", "Crow", "Caw", "Owl", "Hoot",
              "Gull, seagull", "Bird flight, flapping wings", "Duck", "Quack", "Goose", "Honk", "Rooster", "Chicken, rooster", "Wild animals"],
    "insects": ["Insect", "Cricket", "Mosquito", "Fly, housefly", "Buzz", "Bee, wasp, etc.", "Frog", "Croak", "Snake", "Rattle"],
    "people": ["Speech", "Crowd", "Chatter", "Hubbub, speech noise, speech babble", "Children shouting", "Children playing", "Laughter",
               "Applause", "Cheering", "Conversation", "Narration, monologue", "Shout", "Yell", "Child speech, kid speaking", "Babbling"],
    "street": ["Traffic noise, roadway noise", "Vehicle", "Car", "Motor vehicle (road)", "Car passing by", "Bus", "Truck", "Motorcycle",
               "Vehicle horn, car horn, honking", "Engine", "Idling", "Accelerating, revving, vroom", "Tire squeal", "Skidding", "Footsteps", "Walk, footsteps",
               "Air brake", "Reversing beeps", "Siren", "Police car (siren)", "Ambulance (siren)", "Emergency vehicle"],
    "wind": ["Wind", "Wind noise (microphone)", "Rustling leaves", "Howl (wind)", "Rustle"],
    "bells": ["Bell", "Church bell", "Jingle bell", "Bicycle bell", "Tubular bells", "Chime", "Wind chime", "Gong", "Tibetan singing bowl", "Change ringing (campanology)"],
    "fireworks": ["Fireworks", "Firecracker", "Explosion", "Burst, pop", "Boom"],
    "train": ["Train", "Train whistle", "Train horn", "Rail transport", "Railroad car, train wagon", "Train wheels squealing", "Subway, metro, underground"],
    "music": ["Music"],
    "quiet": ["Silence"],
}
_S = None; _L = None


def model():
    global _S, _L
    if _S is None:
        f = MODEL_DIR / "yamnet_onnx" / "yamnet.onnx"
        if not f.exists(): raise FileNotFoundError(f"YAMNet model missing at {f} (see the docstring; ask the user before downloading)")
        try: import onnxruntime as ort
        except ImportError as ex: raise FileNotFoundError("onnxruntime is not installed (pip install onnxruntime; ask the user first)") from ex
        _S = ort.InferenceSession(str(f), providers=["CPUExecutionProvider"])
        _L = [l.strip() for l in open(MODEL_DIR / "labels.txt", encoding="utf-8")]
    return _S, _L


def mel_matrix():
    hz = np.linspace(0, SR / 2, 257); mel = 1127.0 * np.log1p(hz / 700.0)
    edges = np.linspace(1127.0 * np.log1p(125 / 700.0), 1127.0 * np.log1p(7500 / 700.0), 64 + 2)
    lo, ce, hi = edges[:-2], edges[1:-1], edges[2:]
    w = np.maximum(0, np.minimum((mel[:, None] - lo) / (ce - lo), (hi - mel[:, None]) / (hi - ce)))
    w[0, :] = 0.0                                                         # TF leaves the DC bin out
    return w


MEL = mel_matrix()


def patches(x):
    if len(x) < 400 + 160 * 95: x = np.pad(x, (0, 400 + 160 * 95 - len(x)))
    n = 1 + (len(x) - 400) // 160
    win = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(400) / 400)          # periodic Hann, as tf.signal.hann_window
    fr = np.lib.stride_tricks.as_strided(x, (n, 400), (x.strides[0] * 160, x.strides[0])) * win
    mag = np.abs(np.fft.rfft(fr, n=512, axis=1))
    logmel = np.log(mag @ MEL + 0.001).astype(np.float32)
    return [logmel[i:i + 96] for i in range(0, n - 95, 48)]


def scores(x):
    s, labels = model()
    ps = patches(np.asarray(x, np.float32))
    out = np.array([s.run(None, {"audio": p[None, None]})[0][0] for p in ps])
    return (1 / (1 + np.exp(-np.clip(out, -50, 50)))).mean(axis=0), labels                  # the export gives logits: probabilities per patch, averaged


def groups(sc, labels):
    idx = {l: i for i, l in enumerate(labels)}; res = {}
    for g, names in GROUPS.items():
        v = [sc[idx[n]] for n in names if n in idx]
        res[g] = float(max(v)) if v else 0.0
    return res


def decode(path, start=0.0, dur=10.0):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def place_class(x):
    """(group, its score, top labels) for place-sound decisions; 'quiet' when nothing scores."""
    sc, labels = scores(x); g = groups(sc, labels)
    top = [(labels[i], round(float(sc[i]), 2)) for i in np.argsort(-sc)[:5]]
    best = max(g, key=g.get)
    idx = {l: i for i, l in enumerate(labels)}
    specific = max(sc[idx[n]] for n in ("Car", "Traffic noise, roadway noise", "Car passing by", "Motor vehicle (road)", "Bus", "Truck", "Motorcycle",
                                          "Vehicle horn, car horn, honking", "Footsteps", "Walk, footsteps") if n in idx)
    if best == "street" and specific < 0.15 and g["water"] >= 0.12: best = "water"   # surf and rapids roar like a generic "Vehicle"
    if g[best] < 0.10: best = "quiet" if top and top[0][0] == "Silence" or np.sqrt(np.mean(np.square(x))) < 0.003 else "mixed"
    return best, round(g.get(best, 0.0), 2), top


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("media"); ap.add_argument("--start", type=float, default=0); ap.add_argument("--dur", type=float, default=10); ap.add_argument("--top", type=int, default=8)
    a = ap.parse_args()
    x = decode(a.media, a.start, a.dur); sc, labels = scores(x)
    for i in np.argsort(-sc)[:a.top]: print(f"{sc[i]:.3f}  {labels[i]}")
    print("groups:", {k: round(v, 2) for k, v in sorted(groups(sc, labels).items(), key=lambda kv: -kv[1])})
