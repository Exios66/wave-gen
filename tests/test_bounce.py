import math

import pytest

from wavegen.bounce import choose_trips, hit_index, hits_expr, position, tri_expr
from wavegen.loop import eval_expr


@pytest.mark.parametrize("n", [1800, 240, 1799])
@pytest.mark.parametrize("p", [3, 4])
def test_choose_trips_properties(n, p):
    tx, ty = choose_trips(n, 30, 0.12, p)
    assert tx != ty and tx >= 1 and ty >= 1
    assert (tx + ty) % p == 0
    assert math.gcd(tx, ty) == 1   # the path sweeps the screen instead of retracing a short loop


def test_choose_trips_tracks_speed():
    slow = choose_trips(1800, 30, 0.05, 4)
    fast = choose_trips(1800, 30, 0.3, 4)
    assert sum(fast) > sum(slow)


@pytest.mark.parametrize("t", [1, 2, 5])
def test_position_seam_and_corner(t):
    n = 240
    assert position(1, n, t) == 0
    assert position(n + 1, n, t) == pytest.approx(0, abs=1e-9)
    vals = [position(1 + i * n / 1000, n, t) for i in range(1001)]
    assert min(vals) >= 0 and max(vals) <= 1
    assert max(vals) == pytest.approx(1, abs=0.01)


@pytest.mark.parametrize("p", [3, 4])
def test_hits_seam(p):
    n = 1800
    tx, ty = choose_trips(n, 30, 0.12, p)
    assert hit_index(n + 1, n, tx, ty) % p == hit_index(1, n, tx, ty) % p
    assert hit_index(n + 1, n, tx, ty) == 2 * (tx + ty)
    # the colour index steps once per wall hit
    hits = [hit_index(f, n, tx, ty) for f in range(1, n + 2)]
    assert all(0 <= b - a <= 2 for a, b in zip(hits, hits[1:]))


def test_expr_matches_python():
    for f in range(1, 242):
        assert eval_expr(tri_expr(3, 240), f) == pytest.approx(position(f, 240, 3), abs=1e-9)
        assert eval_expr(hits_expr(1, 3, 240, 4), f) == pytest.approx(hit_index(f, 240, 1, 3) % 4, abs=1e-9)
