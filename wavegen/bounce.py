"""Bounce maths for the CRT screensaver (pure Python).

The emblem moves like the classic bouncing logo: constant speed, mirror at each
wall. Each axis is a triangle wave. ``trips`` counts *round* trips (wall, far
wall, back) per loop, so both axes are back in the starting corner exactly
at the loop point. The colour changes on every wall hit. The total hits per
loop are a multiple of the palette length, so the colour also matches at the seam.
"""
from __future__ import annotations

import math


def choose_trips(n_frames: int, fps: int, speed: float, palette_len: int) -> tuple[int, int]:
    """Integer round trips ``(tx, ty)`` per loop closest to ``speed`` (screen widths
    per second): distinct, coprime, with ``(tx + ty) % palette_len == 0``."""
    loop_s = n_frames / fps
    want_x = max(1.0, speed * loop_s / 2)           # one round trip = 2 widths of travel
    want_y = want_x * 0.78                          # a different rhythm vertically
    best, best_cost = None, math.inf
    hi = int(want_x * 2 + 2 * palette_len + 4)
    for tx in range(1, hi):
        for ty in range(1, hi):
            if tx == ty or (tx + ty) % palette_len or math.gcd(tx, ty) != 1:
                continue
            cost = abs(tx - want_x) / want_x + abs(ty - want_y) / want_y
            if cost < best_cost:
                best, best_cost = (tx, ty), cost
    return best


def _phase(frame: float, n_frames: int, trips: int) -> float:
    return trips * (frame - 1) / n_frames


def position(frame: float, n_frames: int, trips: int) -> float:
    """Triangle wave in [0, 1]: 0 on frame 1 and on frame ``n_frames + 1``."""
    u = _phase(frame, n_frames, trips)
    return 1 - abs(2 * (u - math.floor(u)) - 1)


def hit_index(frame: float, n_frames: int, tx: int, ty: int) -> int:
    """Wall hits so far (two per round trip per axis)."""
    return math.floor(2 * _phase(frame, n_frames, tx) + 1e-9) + math.floor(2 * _phase(frame, n_frames, ty) + 1e-9)


def tri_expr(trips: int, n_frames: int) -> str:
    u = f"({trips}*(frame-1)/{n_frames})"
    return f"1-abs(2*({u}-floor({u}))-1)"


def hits_expr(tx: int, ty: int, n_frames: int, palette_len: int) -> str:
    h = f"(floor(2*{tx}*(frame-1)/{n_frames}+1e-9)+floor(2*{ty}*(frame-1)/{n_frames}+1e-9))"
    return f"({h}-{palette_len}*floor({h}/{palette_len}))"
