"""Loop-seamless ambient soundtrack, built from configurable layers.

The recipe comes from the reference clip: a quiet, sustained pad on a
G-major-9 voicing, every partial ~2.5 % flat (the "slowed + reverb" trick),
over a tiled pool room. Each entry of ``audio.layers`` renders one sound
(see :mod:`wavegen.audio.layers`) into a stem (``room``, ``crt``, ``bells``,
``pad``). Stems get room reverb whose tail wraps around the loop, then:

* ``bed`` = room + crt at about -20 LUFS (the default video soundtrack),
* ``mix`` = every stem at about -16 LUFS,

both with a -1 dBTP ceiling. Every buffer is exactly one loop long, so it tiles.
"""
from __future__ import annotations

import wave
import zlib
from pathlib import Path

import numpy as np

from ..frames import loop_frame_count
from . import dsp, layers
from .layers import note_hz

__all__ = ["note_hz", "render_stems", "write_stems", "synthesize", "write_wav", "render", "STEMS"]

STEMS = ("room", "crt", "bells", "pad")
STEM_REVERB = {"room": 0.8, "crt": 0.3, "bells": 1.0, "pad": 1.0}   # x audio.reverb_mix
BED_LUFS, MIX_LUFS, CEILING_DBTP = -20.0, -16.0, -1.0


def loop_samples(cfg: dict) -> int:
    rc = cfg["render"]
    return int(round(loop_frame_count(cfg) / rc["fps"] * int(cfg["audio"]["sample_rate"])))


def _seed(cfg: dict) -> int:
    """NumPy takes only non-negative seeds; wrap negatives so every integer seed works."""
    return int(cfg["seed"]) % 2 ** 64


def _layer_rng(cfg: dict, i: int, layer: dict) -> np.random.Generator:
    return np.random.default_rng([_seed(cfg), i, zlib.crc32(layer["type"].encode())])


def render_stems(cfg: dict) -> dict[str, np.ndarray]:
    ac = cfg["audio"]
    sr = int(ac["sample_rate"])
    n = loop_samples(cfg)
    stems = {s: np.zeros((n, 2)) for s in STEMS}
    for i, layer in enumerate(ac["layers"]):
        fn = layers.get(layer["type"])
        if not layer.get("enabled", True):
            continue
        stem = layer.get("stem", "room")
        if stem not in stems:
            raise ValueError(f"audio layer {layer['type']!r}: unknown stem {stem!r} (use {', '.join(STEMS)})")
        buf = np.asarray(fn(cfg, layer, n, sr, _layer_rng(cfg, i, layer)), float)
        stems[stem] += dsp.fold_tail(buf, n) * float(layer.get("level", 1.0))
    verb_rng = np.random.default_rng([_seed(cfg), 9999])
    for s in STEMS:
        if np.any(stems[s]):
            stems[s] = dsp.circular_reverb(stems[s], sr, ac["reverb_seconds"], ac["reverb_mix"] * STEM_REVERB[s],
                                           verb_rng)
    full = sum(stems.values())
    mix = dsp.normalize(full, sr, MIX_LUFS, CEILING_DBTP)
    cur = dsp.lufs(full, sr)
    gain = 10 ** ((MIX_LUFS - cur) / 20) if np.isfinite(cur) else 1.0
    out = {s: np.clip(stems[s] * gain, -0.999, 0.999) for s in STEMS}
    out["bed"] = dsp.normalize(stems["room"] + stems["crt"], sr, BED_LUFS, CEILING_DBTP)
    out["mix"] = mix
    return {k: v.astype(np.float32) for k, v in out.items()}


def write_wav(path: str | Path, data: np.ndarray, sr: int) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(data, -1, 1) * 32767).round().astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def write_stems(cfg: dict, out_dir: str | Path) -> dict[str, Path]:
    sr = int(cfg["audio"]["sample_rate"])
    return {k: write_wav(Path(out_dir) / f"{k}.wav", v, sr) for k, v in render_stems(cfg).items()}


def synthesize(cfg: dict, seconds: float | None = None) -> tuple[np.ndarray, int]:
    """Compatibility wrapper: the full ``mix`` for a loop of ``seconds`` (default: render.seconds)."""
    if seconds is not None:
        cfg = {**cfg, "render": {**cfg["render"], "seconds": seconds}}
    return render_stems(cfg)["mix"], int(cfg["audio"]["sample_rate"])


def render(cfg: dict, out: str | Path, seconds: float | None = None) -> Path:
    data, sr = synthesize(cfg, seconds)
    return write_wav(out, data, sr)
