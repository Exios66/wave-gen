"""Analyse a reference video so a scene can be matched to it.

Produces (in an output folder):
  contact.jpg       4x4 contact sheet across the clip
  frame_XX.jpg      a few full frames
  analysis.json     metadata, palette, camera motion, audio notes
  palette_preset.json   a preset fragment you can merge (--preset path)

Needs only ffmpeg/ffprobe + numpy (no Blender).
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import numpy as np

from .post import _ffmpeg

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def _frames(path: Path, fps: float, w: int, h: int) -> np.ndarray:
    raw = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale={w}:{h}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3).astype(np.float32) / 255.0


def _kmeans(px: np.ndarray, k: int, seed: int = 0, iters: int = 25):
    rng = np.random.default_rng(seed)
    c = px[rng.choice(len(px), k, replace=False)]
    for _ in range(iters):
        lab = ((px[:, None] - c[None]) ** 2).sum(-1).argmin(1)
        c = np.array([px[lab == i].mean(0) if np.any(lab == i) else c[i] for i in range(k)])
    counts = np.bincount(lab, minlength=k)
    order = np.argsort(-counts)
    return c[order], counts[order] / counts.sum()


def _palette(px: np.ndarray, k: int = 7, cap: int = 200_000, seed: int = 0) -> list[dict]:
    """Dominant colours of ``px`` (N x 3, sRGB 0..1). Empty input -> []."""
    px = np.asarray(px, np.float32).reshape(-1, 3)
    if len(px) == 0:
        return []
    rng = np.random.default_rng(seed)
    if len(px) > cap:
        px = px[rng.choice(len(px), cap, replace=False)]
    k = min(k, len(np.unique(px, axis=0)))
    centers, share = _kmeans(px, k, seed)
    return [{"hex": "#%02x%02x%02x" % tuple(int(round(float(v) * 255)) for v in c), "share": round(float(p), 3),
             "linear": [round(float(x), 3) for x in _srgb_to_linear(c)]} for c, p in zip(centers, share) if p > 0]


def _motion_path(shifts: list[tuple[float, float]]) -> np.ndarray:
    """Cumulative camera path, starting at the origin."""
    steps = np.array(shifts, dtype=float).reshape(-1, 2)
    return np.vstack([np.zeros((1, 2)), np.cumsum(steps, axis=0)])


def _spectrum_windows(n: int, seg: int) -> list[tuple[int, int]]:
    """Half-overlapping analysis windows; a clip shorter than ``seg`` gets one short window."""
    if n <= seg:
        return [(0, n)] if n > 0 else []
    starts = list(range(0, n - seg + 1, seg // 2))
    if starts[-1] + seg < n:
        starts.append(n - seg)
    return [(i, i + seg) for i in starts]


def _phase_shift(a: np.ndarray, b: np.ndarray):
    """Global translation between two grey frames (phase correlation)."""
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    A, B = np.fft.fft2(a * win), np.fft.fft2(b * win)
    R = A * np.conj(B)
    r = np.fft.ifft2(R / (np.abs(R) + 1e-9)).real
    y, x = np.unravel_index(np.argmax(r), r.shape)
    if y > a.shape[0] // 2:
        y -= a.shape[0]
    if x > a.shape[1] // 2:
        x -= a.shape[1]
    return float(x), float(y)


def _srgb_to_linear(c):
    c = np.asarray(c)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _hz_to_note(f: float) -> str:
    midi = 69 + 12 * math.log2(f / 440.0)
    m = round(midi)
    cents = round((midi - m) * 100)
    return f"{NOTES[m % 12]}{m // 12 - 1}{cents:+d}c"


def _audio(path: Path, sr: int = 16000) -> dict | None:
    try:
        raw = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", str(sr),
                              "-f", "s16le", "-"], capture_output=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    if len(a) < sr // 4:
        return None
    rms_db = 20 * math.log10(float(np.sqrt(np.mean(a ** 2))) + 1e-12)
    # long-window spectrum -> sustained tonal peaks
    seg = 1 << 15
    spec = np.zeros(seg // 2 + 1)
    for i, j in _spectrum_windows(len(a), seg):
        chunk = a[i:j] * np.hanning(j - i)
        spec += np.abs(np.fft.rfft(chunk, n=seg))  # zero-pad short windows to a fixed grid
    f = np.fft.rfftfreq(seg, 1 / sr)
    band = (f > 60) & (f < 2000)
    s, fb = spec[band], f[band]
    peaks = [i for i in range(1, len(s) - 1) if s[i] > s[i - 1] and s[i] > s[i + 1]]
    peaks = sorted(peaks, key=lambda i: -s[i])[:10]
    tones = sorted({round(float(fb[i]), 1) for i in peaks})
    cents = [69 + 12 * math.log2(t / 440.0) for t in tones]
    detune = float(np.median([(c - round(c)) * 100 for c in cents])) if cents else 0.0
    centroid = float((f * spec).sum() / (spec.sum() + 1e-9))
    return {"rms_dbfs": round(rms_db, 1), "tonal_peaks_hz": tones,
            "notes": [_hz_to_note(t) for t in tones], "median_detune_cents": round(detune, 1),
            "suggested_tempo_slow": round(2 ** (detune / 1200), 4),
            "spectral_centroid_hz": round(centroid)}


def analyze(video: str | Path, out_dir: str | Path) -> dict:
    video, out_dir = Path(video), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = _probe(video)
    dur = float(meta["format"]["duration"])
    vs = next(s for s in meta["streams"] if s["codec_type"] == "video")
    ff = _ffmpeg()
    subprocess.run([ff, "-y", "-v", "error", "-i", str(video), "-vf",
                    f"fps={16 / dur:.4f},scale=480:-2,tile=4x4", "-frames:v", "1", str(out_dir / "contact.jpg")], check=True)
    subprocess.run([ff, "-y", "-v", "error", "-i", str(video), "-vf", f"fps={4 / dur:.4f},scale=1280:-2",
                    str(out_dir / "frame_%02d.jpg")], check=True)

    fr = _frames(video, 2.0, 256, 144)
    px = fr[:, ::2, ::2].reshape(-1, 3)
    lit = px[px.sum(1) > 0.12]                      # ignore black letterbox/bezel
    palette = _palette(lit if len(lit) else px)
    lum = fr.mean(-1)
    shifts = [_phase_shift(lum[i], lum[i + 1]) for i in range(len(lum) - 1)]
    path = _motion_path(shifts)
    flicker = float(np.std(lum.mean((1, 2)))) if lum.size else 0.0
    mean_rgb = fr.reshape(-1, 3).mean(0) if fr.size else np.zeros(3)
    result = {
        "file": video.name,
        "duration_s": round(dur, 2),
        "resolution": [vs.get("width"), vs.get("height")],
        "fps": vs.get("r_frame_rate"),
        "palette": palette,
        "mean_rgb": [round(float(v), 3) for v in mean_rgb],
        "brightness": round(float(lum.mean()), 3) if lum.size else 0.0,
        "camera_motion": {
            "sample_rate_hz": 2.0,
            "max_excursion_px_at_256w": [round(float(np.ptp(path[:, 0])), 1), round(float(np.ptp(path[:, 1])), 1)],
            "mean_speed_px_per_s": round(float(np.mean(np.linalg.norm(np.array(shifts), axis=1)) * 2.0), 2) if shifts else 0.0,
            "note": "small, slow, continuous drift => floating dolly, not a cut or pan",
        },
        "luma_flicker_std": round(flicker, 4),
        "audio": _audio(video),
    }
    (out_dir / "analysis.json").write_text(json.dumps(result, indent=2))
    # preset fragment: map the dominant colours onto scene slots by hue/brightness
    lin = [np.array(p["linear"]) for p in palette] or [np.zeros(3)]
    bright = sorted(lin, key=lambda c: -c.sum())
    cyan = sorted(lin, key=lambda c: -(c[2] + c[1] - 2 * c[0]))
    frag = {"palette": {"plaster": bright[0].round(3).tolist(), "ceiling": cyan[0].round(3).tolist(),
                        "world": cyan[min(1, len(cyan) - 1)].round(3).tolist()}}
    if result["audio"]:
        frag["audio"] = {"tempo_slow": result["audio"]["suggested_tempo_slow"]}
    (out_dir / "palette_preset.json").write_text(json.dumps(frag, indent=2))
    return result
