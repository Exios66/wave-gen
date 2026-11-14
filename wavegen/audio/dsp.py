"""DSP building blocks for the loop-aware audio engine (numpy only).

Everything that filters works circularly (FFT) on the loop length, so filtered
noise wraps around the loop point with no seam.
"""
from __future__ import annotations

import math

import numpy as np


def env(n: int, sr: int, attack: float, release: float) -> np.ndarray:
    e = np.ones(n)
    a, r = min(int(attack * sr), n // 2), min(int(release * sr), n // 2)
    if a:
        e[:a] = np.sin(np.linspace(0, math.pi / 2, a)) ** 2
    if r:
        e[-r:] *= np.cos(np.linspace(0, math.pi / 2, r)) ** 2
    return e


def lowpass(x: np.ndarray, cutoff: float, sr: int, slope: float = 2.0) -> np.ndarray:
    """Circular FFT low-pass (Butterworth-like magnitude) along axis 0."""
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(x.shape[0], 1 / sr)
    g = 1 / np.sqrt(1 + (f / max(cutoff, 1e-6)) ** (2 * slope))
    return np.fft.irfft(X * (g[:, None] if x.ndim == 2 else g), x.shape[0], axis=0)


def bandpass(x: np.ndarray, lo: float, hi: float, sr: int, slope: float = 1.5) -> np.ndarray:
    return lowpass(x, hi, sr, slope) - lowpass(x, lo, sr, slope)


def fold_tail(x: np.ndarray, n: int) -> np.ndarray:
    """Wrap everything past ``n`` samples back onto the start (repeatedly)."""
    out = np.array(x[:n], dtype=float, copy=True)
    for i in range(n, len(x), n):
        chunk = x[i:i + n]
        out[: len(chunk)] += chunk
    return out


def pan(mono: np.ndarray, p: float) -> np.ndarray:
    """Equal-power pan, ``p`` in 0 (left) .. 1 (right)."""
    return np.stack([mono * math.cos(p * math.pi / 2), mono * math.sin(p * math.pi / 2)], 1)


def periodic_lfo(n: int, cycles: int, phase: float = 0.0) -> np.ndarray:
    """A sine with exactly ``cycles`` periods over ``n`` samples (loop-safe)."""
    return np.sin(2 * math.pi * cycles * np.arange(n) / n + phase)


def _reverb_ir(sr: int, seconds: float, rng: np.random.Generator) -> np.ndarray:
    n = max(1, int(seconds * sr))
    t = np.arange(n) / sr
    decay = np.exp(-6.9 * t / seconds)                     # -60 dB at `seconds`
    ir = rng.standard_normal((n, 2)) * decay[:, None]      # decorrelated L/R
    # darker as it decays: blend a low-passed copy in over time (tiles bright, air not)
    dark = lowpass(ir, 2600, sr, 1.0)
    w = np.clip(t / (0.5 * seconds), 0, 1)[:, None]
    ir = ir * (1 - w) + dark * w
    pre = int(0.012 * sr)
    ir[:pre] *= np.linspace(0, 1, pre)[:, None]
    # early reflections off a hard room
    for delay, gain in ((0.011, 0.5), (0.019, 0.38), (0.027, 0.3), (0.041, 0.22)):
        i = int(delay * sr)
        if i < n:
            ir[i] += gain * np.array([1.0, 0.8]) if i % 2 else gain * np.array([0.8, 1.0])
    return ir / np.sqrt(np.sum(ir ** 2, axis=0, keepdims=True))


def reverb(x: np.ndarray, sr: int, seconds: float, mix: float, rng: np.random.Generator) -> np.ndarray:
    """Convolution room reverb. Returns ``len(x) + tail`` samples (fold for loops)."""
    if mix <= 0 or seconds <= 0:
        return x.copy()
    ir = _reverb_ir(sr, seconds, rng)
    n = len(x) + len(ir) - 1
    size = 1 << (n - 1).bit_length()
    wet = np.fft.irfft(np.fft.rfft(x, size, axis=0) * np.fft.rfft(ir, size, axis=0), size, axis=0)[:n]
    out = wet * mix * 2.2
    out[: len(x)] += x * (1 - mix)
    return out


def circular_reverb(x: np.ndarray, sr: int, seconds: float, mix: float, rng: np.random.Generator) -> np.ndarray:
    """Reverb whose tail wraps onto the loop start (output length == input length)."""
    return fold_tail(reverb(x, sr, seconds, mix, rng), len(x))


# --- loudness (ITU-R BS.1770-4) ----------------------------------------------

def _k_weight_response(f: np.ndarray, sr: int) -> np.ndarray:
    """Complex frequency response of the two K-weighting biquads at sample rate ``sr``."""
    # stage 1: high shelf (+4 dB above ~1.5 kHz)
    f0, G, Q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    K = math.tan(math.pi * f0 / sr)
    Vh, Vb = 10 ** (G / 20), (10 ** (G / 20)) ** 0.4996667741545416
    a0 = 1 + K / Q + K * K
    b1 = [(Vh + Vb * K / Q + K * K) / a0, 2 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0]
    a1 = [1.0, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
    # stage 2: high pass (~38 Hz)
    f0, Q = 38.13547087602444, 0.5003270373238773
    K = math.tan(math.pi * f0 / sr)
    a0 = 1 + K / Q + K * K
    b2 = [1.0, -2.0, 1.0]
    a2 = [1.0, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
    z = np.exp(-2j * np.pi * f / sr)

    def h(b, a):
        return (b[0] + b[1] * z + b[2] * z * z) / (a[0] + a[1] * z + a[2] * z * z)

    return h(b1, a1) * h(b2, a2)


def lufs(x: np.ndarray, sr: int) -> float:
    """Integrated loudness (LUFS) with BS.1770 K-weighting and gating."""
    x = np.atleast_2d(np.asarray(x, float).T).T
    n = len(x)
    f = np.fft.rfftfreq(n, 1 / sr)
    y = np.fft.irfft(np.fft.rfft(x, axis=0) * _k_weight_response(f, sr)[:, None], n, axis=0)
    block, hop = int(0.4 * sr), int(0.1 * sr)
    if n < block:
        block = hop = n
    ms = np.array([np.mean(y[i:i + block] ** 2, axis=0).sum() for i in range(0, n - block + 1, hop)])
    loud = -0.691 + 10 * np.log10(ms + 1e-20)
    gated = ms[loud > -70]
    if not len(gated):
        return -math.inf
    rel = -0.691 + 10 * math.log10(gated.mean()) - 10
    gated = ms[(loud > -70) & (loud > rel)]
    return float(-0.691 + 10 * math.log10(gated.mean()))


def true_peak_db(x: np.ndarray, sr: int, oversample: int = 4) -> float:
    """Approximate true peak via circular FFT oversampling."""
    x = np.asarray(x, float)
    n = len(x)
    X = np.fft.rfft(x, axis=0)
    up = np.fft.irfft(X, n * oversample, axis=0) * oversample
    return float(20 * math.log10(np.max(np.abs(up)) + 1e-20))


def normalize(x: np.ndarray, sr: int, target_lufs: float, ceiling_dbtp: float = -1.0) -> np.ndarray:
    """Gain to ``target_lufs``; if that would exceed the ceiling, soft-limit the peaks."""
    cur = lufs(x, sr)
    if not math.isfinite(cur):
        return x.copy()
    y = x * 10 ** ((target_lufs - cur) / 20)
    ceiling = 10 ** (ceiling_dbtp / 20)
    for _ in range(4):
        tp = 10 ** (true_peak_db(y, sr) / 20)
        if tp <= ceiling * 0.999:
            break
        # smooth knee limiter above 70% of the ceiling, then re-match loudness
        knee = 0.7 * ceiling
        a = np.abs(y)
        over = a > knee
        y = np.where(over, np.sign(y) * (knee + (ceiling * 0.97 - knee) * np.tanh((a - knee) / (ceiling * 0.97 - knee))), y)
        y *= 10 ** ((target_lufs - lufs(y, sr)) / 20)
    tp = 10 ** (true_peak_db(y, sr) / 20)
    if tp > ceiling:
        y *= ceiling * 0.999 / tp
    return y
