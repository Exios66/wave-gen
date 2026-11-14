"""Audio layer registry and the built-in layers.

A layer is one function ``fn(cfg, layer, n, sr, rng) -> ndarray (m, 2)``.
``n`` is the loop length in samples. A layer may return more than ``n`` samples
(a release tail, a bell still ringing): the engine folds anything past ``n``
back onto the start, so the loop stays seamless. Continuous layers should be
periodic over ``n`` (use :func:`dsp.periodic_lfo` and circular filters).

Add a layer (rain, vinyl crackle, distant traffic) with::

    from wavegen.audio import layers

    @layers.register("rain")
    def rain(cfg, layer, n, sr, rng):
        ...
        return stereo

and a preset entry ``{"type": "rain", "stem": "room", "level": 0.1}``.
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np

from ..loop import cycles_for
from . import dsp

LayerFn = Callable[[dict, dict, int, int, np.random.Generator], np.ndarray]
REGISTRY: dict[str, LayerFn] = {}

NOTE_INDEX = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6,
              "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}


def note_hz(name: str) -> float:
    pitch, octave = name[:-1], int(name[-1])
    midi = 12 * (octave + 1) + NOTE_INDEX[pitch]
    return 440.0 * 2 ** ((midi - 69) / 12)


def register(name: str):
    def deco(fn: LayerFn) -> LayerFn:
        REGISTRY[name] = fn
        return fn
    return deco


def get(name: str) -> LayerFn:
    try:
        return REGISTRY[name]
    except KeyError:
        raise ValueError(f"unknown audio layer type {name!r} (have: {', '.join(sorted(REGISTRY))})") from None


def _loop_s(n: int, sr: int) -> float:
    return n / sr


def _rms_norm(x: np.ndarray, rms: float = 0.25) -> np.ndarray:
    r = float(np.sqrt(np.mean(x ** 2)))
    return x * (rms / r) if r > 0 else x


# --- room ---------------------------------------------------------------------

@register("room_tone")
def room_tone(cfg, layer, n, sr, rng):
    """Low air rumble of a big tiled room + faint tape hiss. Periodic over the loop."""
    L = _loop_s(n, sr)
    noise = rng.standard_normal((n, 2))
    air = dsp.lowpass(noise, layer.get("cutoff", 380), sr, 1.0)
    air = _rms_norm(air) * (0.85 + 0.15 * dsp.periodic_lfo(n, cycles_for(23, L), 0.4))[:, None]
    hiss = _rms_norm(dsp.bandpass(rng.standard_normal((n, 2)), 2500, 9000, sr), 0.25)
    return air + hiss * layer.get("hiss", 0.12)


@register("water")
def water(cfg, layer, n, sr, rng):
    """Pool lapping: band-limited noise with slow, loop-periodic swells."""
    L = _loop_s(n, sr)
    out = np.zeros((n, 2))
    for ch, ph in ((0, 0.0), (1, 1.7)):
        lap = dsp.bandpass(rng.standard_normal(n), 90, 420, sr)
        swell = 0.55 + 0.45 * dsp.periodic_lfo(n, cycles_for(9, L), ph) * dsp.periodic_lfo(n, cycles_for(21, L), 2 * ph)
        out[:, ch] = _rms_norm(lap) * swell
    return out


@register("drips")
def drips(cfg, layer, n, sr, rng):
    """Occasional drips, scheduled on the loop timeline."""
    count = int(round(layer.get("per_minute", 8) * _loop_s(n, sr) / 60))
    dn = int(0.18 * sr)
    out = np.zeros((n + dn, 2))
    dt = np.arange(dn) / sr
    for s0 in sorted(rng.integers(0, n, count)):
        f0 = rng.uniform(900, 1500)
        drip = np.sin(2 * math.pi * (f0 * dt + 1800 * dt ** 2)) * np.exp(-dt * 38) * rng.uniform(0.5, 1.0)
        out[s0:s0 + dn] += dsp.pan(drip, rng.uniform(0.2, 0.8))
    return out


# --- crt ----------------------------------------------------------------------

def _loop_freq(f: float, n: int, sr: int) -> float:
    """Nearest frequency with a whole number of cycles in the loop (seamless sine)."""
    L = n / sr
    return max(1, round(f * L)) / L


@register("crt_hum")
def crt_hum(cfg, layer, n, sr, rng):
    """Soft mains hum with a few harmonics, plus the faint line-scan whine."""
    t = np.arange(n) / sr
    hum = np.zeros(n)
    base = layer.get("hum_hz", 60)
    for h, g in ((1, 1.0), (2, 0.45), (3, 0.25), (5, 0.1)):
        f = _loop_freq(base * h, n, sr)
        if f < sr / 2:
            hum += g * np.sin(2 * math.pi * f * t + rng.uniform(0, 6))
    hum = _rms_norm(hum, 0.25) * (0.9 + 0.1 * dsp.periodic_lfo(n, cycles_for(7, n / sr)))
    whine_f = layer.get("whine_hz", 15734)
    out = np.stack([hum, hum * 0.92], 1)
    if whine_f < sr / 2 * 0.95:
        f = _loop_freq(whine_f, n, sr)
        whine = 0.08 * np.sin(2 * math.pi * f * t)
        out += np.stack([whine, whine], 1)
    return out


# --- music --------------------------------------------------------------------

def _bell(f, sr, dur, rng):
    m = int(dur * sr)
    t = np.arange(m) / sr
    mod = np.sin(2 * math.pi * f * 3.5 * t) * 1.2 * np.exp(-t * 3.0)
    tone = np.sin(2 * math.pi * f * t + mod) * np.exp(-t * rng.uniform(1.2, 2.2))
    tone += 0.3 * np.sin(2 * math.pi * f * 2.0 * t) * np.exp(-t * 4.0)
    return tone * dsp.env(m, sr, 0.004, 0.2)


@register("bells")
def bells(cfg, layer, n, sr, rng):
    """Sparse glassy FM bells on a pentatonic set, the screensaver's twinkle."""
    density = float(layer.get("density", 0.55))
    dur = 3.0
    out = np.zeros((n + int(dur * sr), 2))
    count = int(round(density * _loop_s(n, sr)))
    if density <= 0 or count == 0:
        return out[:n]
    slow = cfg["audio"]["tempo_slow"]
    scale = layer.get("scale", ["D5", "E5", "G5", "A5", "B5", "D6", "E6", "G6"])
    # evenly spread with jitter, so bells never clump at the loop point
    slots = (np.arange(count) + rng.uniform(0.1, 0.9, count)) * n / count
    for s0 in slots.astype(int):
        b = _bell(note_hz(scale[rng.integers(len(scale))]) * slow, sr, dur, rng) * rng.uniform(0.4, 1.0)
        out[s0:s0 + len(b)] += dsp.pan(b, rng.uniform(0.15, 0.85))
    return out


def _pad_voice(f, m, sr, rng):
    t = np.arange(m) / sr
    out = np.zeros(m)
    for detune in (-0.0045, 0.0, 0.0052):            # chorus-ish unison
        ff = f * (1 + detune)
        vib = 1 + 0.0018 * np.sin(2 * math.pi * rng.uniform(0.15, 0.3) * t + rng.uniform(0, 6))
        phase = 2 * math.pi * np.cumsum(ff * vib) / sr
        for h in range(1, 7):                        # soft, rounded harmonics
            if ff * h > sr / 2.2:
                break
            out += np.sin(h * phase + rng.uniform(0, 6)) / (h ** 1.8)
    return out / 3


@register("pad")
def pad(cfg, layer, n, sr, rng):
    """Slowed maj9/m9 pad: one pass through the progression per loop, with slow
    filter and voicing movement so it evolves rather than cycles, plus tape wow."""
    ac = cfg["audio"]
    chords = layer.get("chords", ac["chords"])
    slow = ac["tempo_slow"]
    L = _loop_s(n, sr)
    chord_n = n // len(chords)
    overlap = int(min(2.5, chord_n / sr * 0.4) * sr)
    tail = overlap + int(1.0 * sr)
    out = np.zeros((n + tail, 2))
    voice_cycles = cycles_for(L / 1.5, L)
    for k, chord in enumerate(chords):
        s0 = k * chord_n
        m = chord_n + overlap
        e = dsp.env(m, sr, min(2.2, m / sr * 0.35), min(3.0, m / sr * 0.45))
        idx = (s0 + np.arange(m)) % n
        for i, name in enumerate(chord):
            # each voice swells in and out on its own loop-periodic curve (voicing movement)
            lvl = 0.75 + 0.25 * np.sin(2 * math.pi * voice_cycles * idx / n + i * 1.9)
            v = _pad_voice(note_hz(name) * slow, m, sr, rng) * e * lvl
            p = 0.5 + 0.35 * math.sin(i * 2.1 + k)
            gain = (1.15 if i == 0 else 1.0) / len(chord)
            out[s0:s0 + m] += dsp.pan(v * gain, p)
    x = dsp.fold_tail(out, n)
    # slow filter sweep: crossfade a dark and a bright version on a periodic curve
    sweep = (0.5 + 0.5 * dsp.periodic_lfo(n, cycles_for(L / 2, L), -math.pi / 2))[:, None]
    x = dsp.lowpass(x, 900, sr) * (1 - sweep) + dsp.lowpass(x, 2400, sr) * sweep
    return _wow(x, sr, ac.get("wow_depth", 0.0025))


def _wow(x: np.ndarray, sr: int, depth: float) -> np.ndarray:
    """Periodic tape wow (time warp), wrapping around the loop."""
    if depth <= 0:
        return x
    n = len(x)
    L = n / sr
    t = np.arange(n) / sr
    c1, c2 = cycles_for(1 / 0.55, L), cycles_for(1 / 3.1, L)
    w1, w2 = 2 * math.pi * c1 / L, 2 * math.pi * c2 / L
    warp = t + depth * np.sin(w1 * t) / w1 + depth * 0.4 * np.sin(w2 * t) / w2
    return np.stack([np.interp(warp, t, x[:, c], period=L) for c in range(x.shape[1])], 1)
