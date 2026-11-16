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


def test_choose_trips_measures_speed_over_the_real_travel_span():
    """A large emblem has less room to travel, so it needs more round trips to hold the same speed."""
    wide = choose_trips(1800, 30, 0.12, 4, span=1.0)
    narrow = choose_trips(1800, 30, 0.12, 4, span=0.36)
    assert narrow[0] > wide[0]
    actual = 2 * narrow[0] * 0.36 / 60                      # screen widths per second actually covered
    assert actual == pytest.approx(0.12, rel=0.15)


def test_default_emblem_keeps_its_reviewed_pace():
    """The on-screen motion was checked by eye at five by three round trips per minute; keep it."""
    from wavegen import config
    cfg = config.load("poolrooms")
    ec = cfg["computer"]["emblem"]
    span = 1 - 2 * ec["margin"] - ec["scale"]
    n = round(cfg["render"]["seconds"] * cfg["render"]["fps"])
    tx, ty = choose_trips(n, cfg["render"]["fps"], ec["speed"], len(ec["palette"]), span=span)
    assert (tx, ty) == (5, 3)
    assert 2 * tx * span / cfg["render"]["seconds"] == pytest.approx(ec["speed"], rel=0.5)   # the setting means what it says


def test_a_sliver_of_travel_room_does_not_stall_the_trip_search():
    import time
    t = time.perf_counter()
    tx, ty = choose_trips(1800, 30, 0.12, 4, span=1e-5)
    assert time.perf_counter() - t < 1.0
    assert tx != ty and (tx + ty) % 4 == 0 and math.gcd(tx, ty) == 1
    assert abs(tx - 360000) < 20


def test_the_bounded_search_picks_what_the_full_search_did():
    def full(n, fps, speed, p, span):
        want_x = max(1.0, speed * (n / fps) / (2 * span))
        want_y = want_x * 0.78
        best, cost = None, math.inf
        for tx in range(1, int(want_x * 2 + 2 * p + 4)):
            for ty in range(1, int(want_x * 2 + 2 * p + 4)):
                if tx == ty or (tx + ty) % p or math.gcd(tx, ty) != 1:
                    continue
                c = abs(tx - want_x) / want_x + abs(ty - want_y) / want_y
                if c < cost:
                    best, cost = (tx, ty), c
        return best
    for n in (300, 1800, 5400):
        for speed in (0.02, 0.12, 0.3, 0.7):
            for p in (2, 4, 5, 7):
                for span in (1.0, 0.36, 0.08):
                    assert choose_trips(n, 30, speed, p, span=span) == full(n, 30, speed, p, span)
