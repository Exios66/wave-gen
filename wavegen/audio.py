"""Procedural ambient soundtrack (numpy only).

Recipe derived from the reference clip's audio: a quiet, sustained pad whose
spectral peaks sit on a G-major-9 voicing (G3 B3 D4 + C/D/G an octave up),
every partial ~2.5 % flat -> the classic "slowed + reverb" vaporwave trick.
Layers:
  * warm detuned pad (additive, soft harmonics, slow attack/release)
  * sparse glassy FM bells (the twinkle of the screensaver)
  * pool-room bed: filtered noise "water lap" + rare drips
  * tape wow + hiss, then a long synthetic room reverb (tiled room = long RT60)
"""
from __future__ import annotations

import math
import random
import wave
from pathlib import Path

import numpy as np

NOTE_INDEX = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6,
              "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}


def note_hz(name: str) -> float:
    pitch, octave = name[:-1], int(name[-1])
    midi = 12 * (octave + 1) + NOTE_INDEX[pitch]
    return 440.0 * 2 ** ((midi - 69) / 12)


def _env(n, sr, attack, release):
    e = np.ones(n)
    a, r = min(int(attack * sr), n // 2), min(int(release * sr), n // 2)
    if a:
        e[:a] = np.sin(np.linspace(0, math.pi / 2, a)) ** 2
    if r:
        e[-r:] *= np.cos(np.linspace(0, math.pi / 2, r)) ** 2
    return e


def _pad_voice(f, n, sr, rng):
    t = np.arange(n) / sr
    out = np.zeros(n)
    for detune in (-0.0045, 0.0, 0.0052):            # chorus-ish unison
        ff = f * (1 + detune)
        vib = 1 + 0.0018 * np.sin(2 * math.pi * rng.uniform(0.15, 0.3) * t + rng.uniform(0, 6))
        phase = 2 * math.pi * np.cumsum(ff * vib) / sr
        for h in range(1, 7):                        # soft, rounded harmonics
            if ff * h > sr / 2.2:
                break
            out += np.sin(h * phase + rng.uniform(0, 6)) / (h ** 1.8)
    return out / 3


def _bell(f, sr, dur, rng):
    n = int(dur * sr)
    t = np.arange(n) / sr
    mod = np.sin(2 * math.pi * f * 3.5 * t) * 1.2 * np.exp(-t * 3.0)
    tone = np.sin(2 * math.pi * f * t + mod) * np.exp(-t * rng.uniform(1.2, 2.2))
    tone += 0.3 * np.sin(2 * math.pi * f * 2.0 * t) * np.exp(-t * 4.0)
    return tone * _env(n, sr, 0.004, 0.2)


def _fft_lowpass(x, cutoff, sr, slope=2.0):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    X *= 1 / (1 + (f / cutoff) ** (2 * slope)) ** 0.5
    return np.fft.irfft(X, len(x))


def _reverb_ir(sr, seconds, rng_np):
    n = int(seconds * sr)
    t = np.arange(n) / sr
    decay = np.exp(-6.9 * t / seconds)               # -60 dB at `seconds`
    irs = []
    for _ in range(2):                                # decorrelated L/R
        noise = rng_np.standard_normal(n) * decay
        noise = _fft_lowpass(noise, 5200, sr, 1.0)    # tiles are bright, air is not
        noise[: int(0.012 * sr)] *= np.linspace(0, 1, int(0.012 * sr))  # pre-delay softening
        irs.append(noise / np.sqrt(np.sum(noise ** 2)))
    return irs


def _convolve(x, ir):
    n = len(x) + len(ir) - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]


def synthesize(cfg: dict, seconds: float | None = None) -> tuple[np.ndarray, int]:
    ac = cfg["audio"]
    sr = int(ac["sample_rate"])
    seconds = seconds or cfg["render"]["seconds"]
    n = int(seconds * sr)
    rng = random.Random(cfg["seed"])
    rng_np = np.random.default_rng(cfg["seed"])
    slow = ac["tempo_slow"]
    L = np.zeros(n)
    R = np.zeros(n)

    # --- pad --------------------------------------------------------------
    chord_len = ac["chord_seconds"]
    overlap = 2.5
    k = 0
    start = 0.0
    while start < seconds:
        chord = ac["chords"][k % len(ac["chords"])]
        s0 = int(start * sr)
        dur = min(chord_len + overlap, seconds - start + overlap)
        m = min(int(dur * sr), n - s0)
        if m <= 0:
            break
        env = _env(m, sr, 2.2, min(3.0, m / sr * 0.45))
        for i, name in enumerate(chord):
            v = _pad_voice(note_hz(name) * slow, m, sr, rng) * env
            pan = 0.5 + 0.35 * math.sin(i * 2.1 + k)
            gain = ac["pad_level"] / len(chord) * (1.15 if i == 0 else 1.0)
            L[s0:s0 + m] += v * gain * math.cos(pan * math.pi / 2)
            R[s0:s0 + m] += v * gain * math.sin(pan * math.pi / 2)
        start += chord_len
        k += 1
    # gentle breathing filter on the pad
    t = np.arange(n) / sr
    L = _fft_lowpass(L, 1800, sr) * (0.85 + 0.15 * np.sin(2 * math.pi * 0.07 * t))
    R = _fft_lowpass(R, 1800, sr) * (0.85 + 0.15 * np.sin(2 * math.pi * 0.07 * t + 1.0))

    # --- bells (pentatonic over the current chord root) --------------------
    scale = ["D5", "E5", "G5", "A5", "B5", "D6", "E6", "G6"]
    tt = rng.uniform(0.5, 1.5)
    while tt < seconds - 1.0:
        f = note_hz(rng.choice(scale)) * slow
        b = _bell(f, sr, 3.0, rng) * ac["bell_level"] * rng.uniform(0.4, 1.0)
        s0 = int(tt * sr)
        m = min(len(b), n - s0)
        pan = rng.uniform(0.15, 0.85)
        L[s0:s0 + m] += b[:m] * math.cos(pan * math.pi / 2)
        R[s0:s0 + m] += b[:m] * math.sin(pan * math.pi / 2)
        tt += rng.expovariate(ac["bell_density"]) + 0.25

    # --- water: lapping (band-limited noise, slow swell) + rare drips ---------
    for ch, phase in ((L, 0.0), (R, 1.7)):
        noise = rng_np.standard_normal(n)
        lap = _fft_lowpass(noise, 420, sr, 1.5) - _fft_lowpass(noise, 90, sr, 1.5)
        swell = 0.55 + 0.45 * np.sin(2 * math.pi * 0.11 * t + phase) * np.sin(2 * math.pi * 0.047 * t + 2 * phase)
        lap *= swell / (np.std(lap) + 1e-9)
        ch += lap * ac["water_level"] * 0.25
    tt = rng.uniform(1, 4)
    while tt < seconds - 0.5:
        dn = int(0.18 * sr)
        dt = np.arange(dn) / sr
        f0 = rng.uniform(900, 1500)
        drip = np.sin(2 * math.pi * (f0 * dt + 1800 * dt ** 2)) * np.exp(-dt * 38) * ac["water_level"] * 0.5
        s0 = int(tt * sr)
        m = min(dn, n - s0)
        pan = rng.uniform(0.2, 0.8)
        L[s0:s0 + m] += drip[:m] * (1 - pan)
        R[s0:s0 + m] += drip[:m] * pan
        tt += rng.uniform(3.5, 9.0)

    # --- reverb ---------------------------------------------------------------
    irL, irR = _reverb_ir(sr, ac["reverb_seconds"], rng_np)
    mix = ac["reverb_mix"]
    wetL, wetR = _convolve(L, irL), _convolve(R, irR)
    L = L * (1 - mix) + wetL * mix * 2.2
    R = R * (1 - mix) + wetR * mix * 2.2

    # --- tape wow (time-warp) + hiss -----------------------------------------
    warp = t + ac["wow_depth"] * np.sin(2 * math.pi * 0.55 * t) / (2 * math.pi * 0.55) \
             + ac["wow_depth"] * 0.4 * np.sin(2 * math.pi * 3.1 * t) / (2 * math.pi * 3.1)
    L = np.interp(warp, t, L)
    R = np.interp(warp, t, R)
    hiss = _fft_lowpass(rng_np.standard_normal((2, n)).reshape(-1), 7000, sr).reshape(2, n)
    L += hiss[0] * ac["hiss_level"]
    R += hiss[1] * ac["hiss_level"]

    out = np.stack([L, R], axis=1)
    out *= _env(n, sr, 1.5, 2.5)[:, None]                 # fade in / out
    peak = np.max(np.abs(out)) + 1e-9
    out *= 0.79 / peak                                      # ~-2 dBFS peak
    return out.astype(np.float32), sr


def write_wav(path: str | Path, data: np.ndarray, sr: int) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def render(cfg: dict, out: str | Path, seconds: float | None = None) -> Path:
    data, sr = synthesize(cfg, seconds)
    return write_wav(out, data, sr)
