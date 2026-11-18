"""Natural features: skylight sun and leaf canopy, plants, lily pads, organic structure.
Skipped automatically when bpy is unavailable."""
import math

import pytest

bpy = pytest.importorskip("bpy")

from mathutils import Vector  # noqa: E402

from wavegen import config  # noqa: E402
from wavegen.scene import build_scene  # noqa: E402
from wavegen.scene.loopcheck import loop_mismatches  # noqa: E402

LIGHT = ["atmosphere.dust_count=0", "atmosphere.haze_density=0", "computer.enabled=false"]
SKY = ["nature.skylight.enabled=true", "nature.skylight.center=[1.5,15.0]", "nature.skylight.size=[3.0,4.0]"]


def _build(*sets):
    cfg = config.load("poolrooms", LIGHT + list(sets))
    build_scene(cfg)
    return cfg


def _up(x, y, z):
    dg = bpy.context.evaluated_depsgraph_get()
    hit, _, _, _, obj, _ = bpy.context.scene.ray_cast(dg, Vector((x, y, z)), Vector((0, 0, 1)))
    return obj.name if hit else None


def test_nature_is_off_by_default():
    _build()
    names = set(bpy.data.objects.keys())
    assert not any(n.startswith(("Sun", "Canopy", "Skylight")) for n in names)


def test_skylight_opens_the_ceiling_to_a_leaf_canopy():
    cfg = _build(*SKY)
    H = cfg["room"]["height"]
    assert _up(1.5, 15.0, H - 0.3) == "Canopy"            # through the opening to the leaves
    assert _up(-4.0, 6.0, H - 0.3) == "Ceiling"           # elsewhere the ceiling is closed
    assert bpy.data.objects["Sun"].data.type == "SUN"


def test_sun_shines_down_and_toward_the_camera_from_the_far_side():
    _build(*SKY, "nature.skylight.sun_elevation=60", "nature.skylight.sun_azimuth=180")
    bpy.context.view_layer.update()
    d = bpy.data.objects["Sun"].matrix_world.to_3x3() @ Vector((0, 0, -1))
    assert d.z < 0 and d.y < 0 and abs(d.x) < 1e-6
    assert math.isclose(math.degrees(math.asin(-d.z)), 60, abs_tol=1e-4)


def test_the_canopy_sways_and_still_loops():
    cfg = _build(*SKY)
    from wavegen.scene.loopcheck import driven_values
    assert any('nodes["sway"]' in k for k in driven_values(1))          # the leaves move
    assert loop_mismatches(cfg) == []
