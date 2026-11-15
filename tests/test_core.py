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


def test_fit_never_returns_non_positive_widths():
    from wavegen.config import _fit
    for wall in (0.2, 1.0, 1.5, 3.0):
        assert all(w > 0 for w in _fit([3.2, 4.0, 3.2], wall)), wall


def test_fit_layout_always_spreads_with_full_piers():
    """Every _fit layout leaves >= 0.6 m piers (what architecture._spread requires); walls too
    short for even one opening get none."""
    from wavegen.config import _fit, min_wall_for
    for wall in (0.2, 1.0, 1.25, 1.5, 3.0, 8.0):
        widths = _fit([3.2, 4.0, 3.2], wall)
        assert all(w > 0 for w in widths), wall
        assert not widths or min_wall_for(widths) <= wall + 1e-9, (wall, widths)
    assert _fit([3.2], 1.0) == []


def test_poolrooms_light_and_surface_hues_match_the_reference():
    """Hues measured from the clean video frames: walls, ceiling and water are aqua (186-189 deg),
    not green-teal; the foreground carries a periwinkle cast; the CRT flank sits in shade."""
    import colorsys
    cfg = config.load("poolrooms")
    pal, li = cfg["palette"], cfg["lights"]
    hue = lambda c: colorsys.rgb_to_hsv(*c)[0] * 360
    for k in ("cool_light", "plaster", "ceiling"):
        assert 184 <= hue(pal[k]) <= 200, (k, round(hue(pal[k])))
    assert 220 <= hue(pal["tile"]) <= 250, round(hue(pal["tile"]))
    assert li["accent_power"] <= 300


def test_poolrooms_carries_the_reference_pink_wash():
    cfg = config.load("poolrooms")
    wash = cfg["post"]["pink_wash"]
    r, g, b = wash["color"]
    assert wash["strength"] > 0 and r > b > g            # pink-lavender: red leads, green lowest
    assert 0.3 <= wash["extent"] <= 0.7                   # the left of frame, fading out before the right


def test_poolrooms_water_is_calm_and_only_lamps_glow():
    cfg = config.load("poolrooms")
    pool, bloom = cfg["pool"], cfg["render"]["bloom"]
    assert pool["wave_strength"] <= 0.1                  # a near-mirror surface reflects the arches, as in the clip
    assert pool["caustics"]["strength"] <= 0.5            # faint light lines, not a net over the pool floor
    assert bloom["strength"] > 0                         # zero strength would bypass the glare node
    assert bloom["threshold"] >= 2.0 and bloom["size"] >= 0.9   # big soft halos on lamps, walls never bloom


def test_poolrooms_sconces_sit_in_the_upper_part_of_the_arch():
    cfg = config.load("poolrooms")
    z = cfg["lights"]["alcove_height"] * cfg["room"]["spring_height"]
    assert 2.6 <= z <= 3.3                               # metres: about two-thirds up the opening, as in the clip


def test_emblem_is_large_enough_to_read_its_lettering():
    em = config.load("poolrooms")["computer"]["emblem"]
    assert 0.5 <= em["scale"] <= 0.7      # the text spans the emblem; under half the screen it blurs at 1080p


def test_poolrooms_alcoves_are_tiled_to_the_top_in_large_tile():
    room = config.load("poolrooms")["room"]
    assert room["alcove_wainscot"] >= room["height"]            # tile runs up behind the sconces, no plaster band
    assert room["alcove_tile_size"] >= 1.5 * room["tile_size"]  # large enough for the grid to read across the pool


def test_poolrooms_arches_are_flat_topped_with_rounded_corners():
    room = config.load("poolrooms")["room"]
    rc = room["arch_corner_radius"]
    assert rc is not None and rc < min(room["back_arches"]) / 2       # every arch gets a flat top
    assert room["spring_height"] + rc <= room["height"] - 0.6           # and still clears the ceiling tray


def test_poolrooms_passage_behind_the_pier_is_tall_and_fully_tiled():
    room = config.load("poolrooms")["room"]
    bay = room["bay"]
    assert bay["height"] >= 5.0                    # the opening runs out of the top of the frame, as in the clip
    assert bay["wainscot"] >= bay["height"]        # tile all the way up, no plaster band


def test_poolrooms_floor_is_lavender_and_the_pool_is_pale():
    """Measured against the clip: its floor reads lavender, its water paler than ours was."""
    pal = config.load("poolrooms")["palette"]
    r, g, b = pal["floor_tile"]
    assert b - max(r, g) >= 0.2 and abs(r - g) < 0.06
    assert pal["pool_tile"][0] >= 0.3 and pal["water_absorb"][0] >= 0.4


def test_mutate_keeps_the_nested_arch_in_the_widest_opening():
    base = config.load("poolrooms")
    seen = set()
    for seed in range(40):
        room = config.mutate(base, seed)["room"]
        widths = room["back_arches"]
        seen.add(len(widths))
        assert widths[room["nested_arch"]["arch"]] == max(widths)
    assert seen > {3}                                       # layouts with more than three arches were covered
