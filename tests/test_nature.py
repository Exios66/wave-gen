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


PLANTS = ["nature.plants.enabled=true", "nature.plants.spots=[[7.1,9.0,2.2],[-5.0,15.0,0.9]]",
          'nature.plants.kinds=["palm","fern"]']


def _top_and_bottom(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    zs = [(ev.matrix_world @ v.co).z for v in ev.data.vertices]
    return max(zs), min(zs)


def test_plants_are_off_by_default():
    _build()
    assert not any(n.startswith(("Plant.", "Planter.")) for n in bpy.data.objects.keys())


def test_each_spot_gets_a_potted_plant_of_the_asked_height():
    _build(*PLANTS)
    for i, (x, y, h) in enumerate([(7.1, 9.0, 2.2), (-5.0, 15.0, 0.9)]):
        plant, pot = bpy.data.objects[f"Plant.{i}"], bpy.data.objects[f"Planter.{i}"]
        assert len(plant.data.polygons) > 200                  # real fronds, not a token
        top, _ = _top_and_bottom(plant)
        assert math.isclose(top, h, rel_tol=0.05)
        _, base = _top_and_bottom(pot)
        assert abs(base) < 0.02                               # standing on the floor
        assert math.isclose(pot.location.x, x, abs_tol=1e-5) and math.isclose(pot.location.y, y, abs_tol=1e-5)


def test_palms_and_ferns_differ():
    _build(*PLANTS)
    palm, fern = (bpy.data.objects[f"Plant.{i}"] for i in (0, 1))
    assert palm.get("kind") == "palm" and fern.get("kind") == "fern"


def test_plants_sway_and_the_loop_still_closes():
    cfg = _build(*PLANTS)
    from wavegen.scene.loopcheck import driven_values
    assert any(k.startswith("Plant.0:rotation_euler") for k in driven_values(1))
    assert loop_mismatches(cfg) == []


def test_a_plant_in_the_pool_is_refused():
    with pytest.raises(ValueError, match="in the pool"):
        _build("nature.plants.enabled=true", "nature.plants.spots=[[1.0,10.0,2.0]]")
