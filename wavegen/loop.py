"""Loop-periodic driver expressions.

Every animated value in a wave-gen scene is built from these helpers. Each one
has a period of exactly ``n_frames`` frames, so frame ``n_frames + 1`` equals
frame ``1`` and the rendered video loops with no seam.
Pure Python: usable from tests without Blender.
"""
from __future__ import annotations

import math

TAU = 2 * math.pi


def cycles_for(period_s: float, loop_s: float) -> int:
    """Whole number of cycles closest to ``period_s`` that fits the loop (at least 1)."""
    return max(1, round(loop_s / period_s))


def _w(cycles: int, n_frames: int) -> str:
    return f"{TAU * cycles / n_frames:.12g}"


def periodic_expr(base: float, amp: float, cycles: int, phase: float, n_frames: int, harmonic: int = 2) -> str:
    """Smooth two-sine drift with period ``n_frames``; the second term runs at ``harmonic`` x cycles."""
    w1, w2 = _w(cycles, n_frames), _w(cycles * harmonic, n_frames)
    return (f"{base:.6f} + {amp:.6f}*(0.75*sin((frame-1)*{w1}+{phase:.5f})"
            f" + 0.25*sin((frame-1)*{w2}+{phase * 2.3:.5f}))")


def circle_expr(radius: float, cycles: int, n_frames: int, axis: str) -> str:
    """One coordinate of a circular path (``axis`` = ``"cos"`` or ``"sin"``)."""
    if axis not in ("cos", "sin"):
        raise ValueError("axis must be 'cos' or 'sin'")
    return f"{radius:.6f}*{axis}((frame-1)*{_w(cycles, n_frames)})"


def spin_expr(turns: int, n_frames: int, sign: int = 1) -> str:
    """Continuous rotation: ``turns`` full turns per loop (value grows by turns*2pi)."""
    return f"{sign}*(frame-1)*{_w(turns, n_frames)}"


def eval_expr(expr: str, frame: float) -> float:
    """Evaluate a driver expression the way Blender's simple-expression engine would."""
    names = {k: getattr(math, k) for k in ("sin", "cos", "tan", "asin", "acos", "atan", "atan2", "floor",
                                            "ceil", "fmod", "sqrt", "pi", "radians", "degrees")}
    names.update(frame=frame, abs=abs, min=min, max=max)
    return float(eval(expr, {"__builtins__": {}}, names))  # noqa: S307 - our own expressions
