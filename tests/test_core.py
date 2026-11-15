"""Fast tests that need no Blender (config, audio, post graph)."""
import numpy as np
import pytest

from wavegen import config, post


def test_presets_load_and_merge():
    names = config.list_presets()
    assert {"poolrooms", "poolrooms_dusk", "poolrooms_night"} <= set(names)
    for n in names:
        cfg = config.load(n)
        assert cfg["name"] == n
        assert len(cfg["render"]["resolution"]) == 2
    dusk = config.load("poolrooms_dusk")
    assert dusk["palette"]["plaster"] != config.DEFAULTS["palette"]["plaster"]
    assert dusk["room"] == config.DEFAULTS["room"]  # untouched sections inherited


def test_dotted_overrides_parse_json():
    cfg = config.load(None, ["render.samples=8", "render.resolution=[320,180]", "name=x", "camera.drift.period=[1,2,3]"])
    assert cfg["render"]["samples"] == 8
    assert cfg["render"]["resolution"] == [320, 180]
    assert cfg["name"] == "x"
    assert cfg["camera"]["drift"]["period"] == [1, 2, 3]
    with pytest.raises(ValueError):
        config.set_dotted(cfg, "nonsense")


def test_mutate_is_deterministic_and_valid():
    base = config.load("poolrooms")
    a, b, c = config.mutate(base, 7), config.mutate(base, 7), config.mutate(base, 8)
    assert a == b and a != c
    for v in (a, c):
        r, p = v["room"], v["pool"]
        assert sum(r["back_arches"]) + 0.6 * (len(r["back_arches"]) + 1) < r["width"]
        assert -r["width"] / 2 < p["x"][0] < p["x"][1] < r["width"] / 2
        assert p["y"][1] < -3.5 + r["depth"] - 1.0
        assert r["spring_height"] < r["height"] - 2.0 + 1e-9
    assert base == config.load("poolrooms")  # mutate does not touch its input


def test_post_filtergraph_variants():
    cfg = config.load("poolrooms")
    g = post.filtergraph(cfg["post"], 1920, 1080)
    assert g.startswith("[0:v]") and g.endswith("[vout]") and "blend=all_mode=screen" in g
    pc = dict(cfg["post"], halation=0, grade=False, crt_on_tv=True)
    g2 = post.filtergraph(pc, 1280, 720)
    assert "nullsink" in g2 and "lenscorrection" in g2 and "pad=1280:720" in g2


def test_mutate_layouts_always_fit():
    base = config.load("poolrooms")
    for seed in range(500):
        c = config.mutate(base, seed)
        r = c["room"]
        assert config.min_wall_for(r["back_arches"]) <= r["width"], seed
        assert config.min_wall_for(r["side_arches"]) <= r["depth"] - 6.0, seed


def test_resolve_focus():
    import pytest
    from wavegen.scene.focus import resolve_focus
    assert resolve_focus("computer", False) == ("target", None)
    assert resolve_focus("computer", True) == ("object", None)
    assert resolve_focus("target", True) == ("target", None)
    assert resolve_focus(2.5, False) == ("distance", 2.5)
    assert resolve_focus("2.5", False) == ("distance", 2.5)
    with pytest.raises(ValueError, match="computer"):
        resolve_focus("banana", True)


def test_resolve_engine():
    import pytest
    from wavegen.scene.engine import resolve_engine
    assert resolve_engine("eevee", (5, 3, 0)) == "BLENDER_EEVEE"
    assert resolve_engine("cycles", (5, 3, 0)) == "CYCLES"
    assert resolve_engine("CYCLES", (5, 3, 0)) == "CYCLES"
    assert resolve_engine("BLENDER_EEVEE_NEXT", (5, 3, 0)) == "BLENDER_EEVEE"
    with pytest.raises(RuntimeError, match="Blender 5"):
        resolve_engine("cycles", (4, 2, 0))
    with pytest.raises(ValueError):
        resolve_engine("luxcore", (5, 3, 0))




def test_set_dotted_list_index():
    cfg = config.load("poolrooms", ["audio.layers.4.density=0.3"])
    assert cfg["audio"]["layers"][4]["type"] == "bells" and cfg["audio"]["layers"][4]["density"] == 0.3
