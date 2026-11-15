import pytest

from wavegen.loop import circle_expr, cycles_for, eval_expr, periodic_expr


@pytest.mark.parametrize("n", [1800, 1799, 240])
@pytest.mark.parametrize("cycles", [1, 3])
def test_periodic_expr_seam(n, cycles):
    e = periodic_expr(1.5, 0.3, cycles, 0.7, n)
    assert eval_expr(e, 1) == pytest.approx(eval_expr(e, n + 1), abs=1e-9)
    assert abs(eval_expr(e, n / 4 + 1) - eval_expr(e, 1)) > 1e-3


@pytest.mark.parametrize("axis", ["cos", "sin"])
def test_circle_expr_seam(axis):
    e = circle_expr(0.7, 2, 1799, axis)
    assert eval_expr(e, 1) == pytest.approx(eval_expr(e, 1800), abs=1e-9)
    assert abs(eval_expr(e, 1 + 1799 / 8) - eval_expr(e, 1)) > 0.1


def test_cycles_for():
    assert cycles_for(26, 60) == 2
    assert cycles_for(200, 8) == 1
    assert cycles_for(17, 60) == 4
