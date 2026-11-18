"""Floor-plan arithmetic for things placed in the room: where the pool and the walls are."""
import math

import pytest

from wavegen import config, layout


def _cfg(*sets):
    return config.load("poolrooms", list(sets))


def test_gap_to_the_pool_is_round_at_its_corners():
    cfg = _cfg("pool.notch=null")
    (_, x1), (y0, _), c = cfg["pool"]["x"], cfg["pool"]["y"], cfg["pool"]["coping"]
    # 0.25 m right of and 0.30 m in front of the coping's corner: 0.39 m away, not 0.25
    assert layout.pool_gap(cfg, x1 + c + 0.25, y0 - c - 0.30) == pytest.approx(math.hypot(0.25, 0.30))
    assert layout.pool_gap(cfg, x1 + c + 0.25, (y0 + 10) / 2) == pytest.approx(0.25)
    assert layout.pool_gap(cfg, x1 - 1.0, y0 + 2.0) == 0.0                       # in the water


def test_the_notch_is_floor_not_pool():
    cfg = _cfg()                                     # poolrooms has a 2.6 x 1.3 step in the far-left corner
    (x0, _), (_, y1), c = cfg["pool"]["x"], cfg["pool"]["y"], cfg["pool"]["coping"]
    nw, nd = cfg["pool"]["notch"]
    x, y = x0 + 1.0, y1 - 0.3
    assert layout.pool_gap(cfg, x, y) == pytest.approx(min(nd - 0.3, nw - 1.0) - c)
    assert layout.pool_gap(_cfg("pool.notch=null"), x, y) == 0.0


def test_a_plant_off_a_pool_corner_is_allowed_but_not_one_in_it():
    cfg = _cfg("pool.notch=null", "nature.plants.enabled=true")
    (_, x1), (y0, _), c = cfg["pool"]["x"], cfg["pool"]["y"], cfg["pool"]["coping"]
    cfg["nature"]["plants"]["spots"] = [[x1 + c + 0.25, y0 - c - 0.30, 1.0]]     # pot radius 0.32
    layout.check_plants(cfg)
    cfg["nature"]["plants"]["spots"] = [[1.0, 10.0, 2.0]]
    with pytest.raises(ValueError, match="plant 0 .* in the pool"):
        layout.check_plants(cfg)


def test_a_plant_through_a_wall_is_refused():
    cfg = _cfg("nature.plants.enabled=true")
    cfg["nature"]["plants"]["spots"] = [[cfg["room"]["width"] / 2 - 0.1, 10.0, 2.0]]
    with pytest.raises(ValueError, match="plant 0 .* outside the room"):
        layout.check_plants(cfg)


def test_variants_keep_the_plants_on_the_floor():
    cfg = _cfg("nature.plants.enabled=true")
    kept = 0
    for seed in range(40):
        v = config.mutate(cfg, seed=seed)
        layout.check_plants(v)                       # every pot in the room, none in the pool
        kept += len(v["nature"]["plants"]["spots"])
    assert kept > 40 * len(cfg["nature"]["plants"]["spots"]) * 0.7   # most survive the new layout


def test_a_tree_column_may_stand_on_the_notch():
    cfg = _cfg("nature.tree_columns.enabled=true")
    (x0, _), (_, y1) = cfg["pool"]["x"], cfg["pool"]["y"]
    cfg["nature"]["tree_columns"]["spots"] = [[x0 + 1.0, y1 - 0.3]]     # on the step of floor
    layout.check_tree_columns(cfg)
    cfg["nature"]["tree_columns"]["spots"] = [[1.0, 10.0]]
    with pytest.raises(ValueError, match="tree column 0 .* in the pool"):
        layout.check_tree_columns(cfg)


def test_variants_keep_the_tree_columns_on_the_floor():
    cfg = _cfg("nature.tree_columns.enabled=true")
    kept = 0
    for seed in range(40):
        v = config.mutate(cfg, seed=seed)
        layout.check_tree_columns(v)
        kept += len(v["nature"]["tree_columns"]["spots"])
    assert kept > 40 * len(cfg["nature"]["tree_columns"]["spots"]) * 0.7
