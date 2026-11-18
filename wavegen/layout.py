"""Floor-plan arithmetic for things placed in the room: where the walls and the pool are.

Pure Python, so presets can be checked (and ``config.mutate`` can keep things in
place) without Blender.
"""
from __future__ import annotations

import math

Y0 = -3.5                       # the front wall; the room runs from here to Y0 + depth


def room_box(cfg: dict) -> tuple[float, float, float, float]:
    """(x0, x1, y0, y1) of the room's inner walls."""
    room = cfg["room"]
    return -room["width"] / 2, room["width"] / 2, Y0, Y0 + room["depth"]


def _rect_gap(x, y, x0, x1, y0, y1) -> float:
    return math.hypot(max(x0 - x, 0.0, x - x1), max(y0 - y, 0.0, y - y1))


def pool_gap(cfg: dict, x: float, y: float) -> float:
    """How far (x, y) is from the pool's coping; 0 on the coping or over the water.
    The notch (a step of floor in the far-left corner) is floor, not pool."""
    pool = cfg["pool"]
    (px0, px1), (py0, py1), c = pool["x"], pool["y"], pool["coping"]
    nw, nd = pool.get("notch") or (0.0, 0.0)
    # the water is two overlapping rectangles; the coping is a square-cornered band around each
    return min(_rect_gap(x, y, px0 + nw - c, px1 + c, py0 - c, py1 + c),
               _rect_gap(x, y, px0 - c, px1 + c, py0 - c, py1 - nd + c))


def check_spot(cfg: dict, what: str, x: float, y: float, r: float) -> None:
    """Refuse a round footprint of radius ``r`` at (x, y) that is in the pool or through a wall."""
    if pool_gap(cfg, x, y) < r:
        raise ValueError(f"{what} at ({x}, {y}) is in the pool; move it onto the floor")
    x0, x1, y0, y1 = room_box(cfg)
    if not (x0 + r <= x <= x1 - r and y0 + r <= y <= y1 - r):
        raise ValueError(f"{what} at ({x}, {y}) is outside the room; move it inside the walls")


def check_plants(cfg: dict) -> None:
    pl = cfg["nature"]["plants"]
    for i, (x, y, _) in enumerate(pl["spots"]):
        check_spot(cfg, f"plant {i}", x, y, pl["pot_radius"])


def check_tree_columns(cfg: dict) -> None:
    tc = cfg["nature"]["tree_columns"]
    for i, (x, y) in enumerate(tc["spots"]):
        check_spot(cfg, f"tree column {i}", x, y, tc["trunk_radius"] * 1.35)    # the flared foot


def reach_inside(cfg: dict, x: float, y: float, angle: float, reach: float, margin: float) -> float:
    """How far from (x, y) toward ``angle`` (radians) a branch may reach and still stay
    ``margin`` inside the walls: ``reach``, or less near a wall."""
    x0, x1, y0, y1 = room_box(cfg)
    dx, dy = math.cos(angle), math.sin(angle)
    for d, lo, hi, p in ((dx, x0, x1, x), (dy, y0, y1, y)):
        if d > 1e-9:
            reach = min(reach, (hi - margin - p) / d)
        elif d < -1e-9:
            reach = min(reach, (lo + margin - p) / d)
    return max(0.0, reach)


def fits(cfg: dict, x: float, y: float, r: float) -> bool:
    try:
        check_spot(cfg, "", x, y, r)
    except ValueError:
        return False
    return True


def _refit(old: dict, new: dict, spots: list, r: float) -> list[int]:
    """Indices of ``spots`` kept after moving them in place: each is scaled with the
    room from ``old`` to ``new``, and dropped if it then lands in the pool or a wall."""
    sx = new["room"]["width"] / old["room"]["width"]
    sy = new["room"]["depth"] / old["room"]["depth"]
    keep = []
    for i, (x, y, *rest) in enumerate(spots):
        x, y = round(x * sx, 3), round(Y0 + (y - Y0) * sy, 3)
        spots[i] = [x, y, *rest]
        if fits(new, x, y, r):
            keep.append(i)
    return keep


def refit_nature(old: dict, new: dict) -> None:
    """After ``new`` has redrawn the room and pool of ``old`` (``config.mutate``), move the
    natural features' spots with it so none ends up in the pool or through a wall."""
    pl = (new.get("nature") or {}).get("plants")
    if pl:
        keep = _refit(old, new, pl["spots"], pl["pot_radius"])
        kinds = pl["kinds"]
        pl["kinds"] = [kinds[i % len(kinds)] for i in keep] or kinds   # each plant keeps its kind
        pl["spots"] = [pl["spots"][i] for i in keep]
    tc = (new.get("nature") or {}).get("tree_columns")
    if tc:
        keep = _refit(old, new, tc["spots"], tc["trunk_radius"] * 1.35)
        tc["spots"] = [tc["spots"][i] for i in keep]


FLOOR_PATTERNS = ("square", "hex")


def check(cfg: dict) -> None:
    """Refuse a layout that cannot be built, before any slow (or destructive) work starts."""
    pattern = cfg["room"].get("floor_pattern", "square")
    if pattern not in FLOOR_PATTERNS:
        raise ValueError(f"unknown floor_pattern {pattern!r} (have: {', '.join(FLOOR_PATTERNS)})")
    nat = cfg.get("nature") or {}
    if nat.get("plants", {}).get("enabled"):
        check_plants(cfg)
    if nat.get("tree_columns", {}).get("enabled"):
        check_tree_columns(cfg)
