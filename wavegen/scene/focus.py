"""Depth-of-field focus resolution (no bpy, so it is unit-testable)."""
from __future__ import annotations

import math

FOCUS_OPTIONS = ("computer", "target", "<distance in metres>")


def resolve_focus(focus: str | float, has_focus_obj: bool) -> tuple[str, float | None]:
    """Return ``("object"|"target"|"distance", distance_or_None)``.

    ``"computer"`` falls back to the look-at target when there is no computer.
    """
    if focus == "computer":
        return ("object", None) if has_focus_obj else ("target", None)
    if focus == "target":
        return ("target", None)
    try:
        dist = float(focus)
    except (TypeError, ValueError):
        dist = math.nan
    if not (math.isfinite(dist) and dist > 0):
        raise ValueError(f"camera.focus_on={focus!r}; expected one of {', '.join(FOCUS_OPTIONS)} (above zero)")
    return ("distance", dist)
