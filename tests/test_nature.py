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


def test_a_plant_just_off_a_pool_corner_is_built():
    cfg = config.load("poolrooms", LIGHT + ["pool.notch=null", "nature.plants.enabled=true"])
    (_, x1), (y0, _), c = cfg["pool"]["x"], cfg["pool"]["y"], cfg["pool"]["coping"]
    cfg["nature"]["plants"]["spots"] = [[x1 + c + 0.25, y0 - c - 0.30, 1.0]]
    build_scene(cfg)
    assert "Planter.0" in bpy.data.objects


TREES = ["nature.tree_columns.enabled=true", "nature.tree_columns.spots=[[-5.5,12.0]]",
         "nature.tree_columns.branches=4"]


def test_ceiling_height_follows_the_tray_steps():
    from wavegen.scene.nature import ceiling_z
    cfg = config.load("poolrooms")
    room, t = cfg["room"], cfg["room"]["ceiling_tray"]
    H = room["height"]
    assert ceiling_z(cfg, -room["width"] / 2 + 0.1, 10.0) == pytest.approx(H)            # beside the wall
    assert ceiling_z(cfg, 0.0, 12.0) == pytest.approx(H + t["steps"] * t["step_height"])  # in the deepest step


def test_tree_columns_are_off_by_default():
    _build()
    assert not any(n.startswith("TreeColumn") for n in bpy.data.objects.keys())


def test_a_tree_column_stands_on_the_floor_and_its_branches_meet_the_ceiling():
    from wavegen.scene.nature import ceiling_z
    cfg = _build(*TREES)
    col = bpy.data.objects["TreeColumn.0"]
    zs = [(col.matrix_world @ v.co).z for v in col.data.vertices]
    assert min(zs) == pytest.approx(0.0, abs=0.02)
    tips = [tuple(col["tips"][i:i + 3]) for i in range(0, len(col["tips"]), 3)]
    assert len(tips) == 4 * 2                                   # each limb forks once more
    for x, y, z in tips:
        assert z == pytest.approx(ceiling_z(cfg, x, y) + 0.05, abs=1e-4)
    spread = max(math.hypot(x + 5.5, y - 12.0) for x, y, _ in tips)
    assert 0.8 < spread <= cfg["nature"]["tree_columns"]["spread"] + 1e-6


def test_a_tree_column_in_the_pool_is_refused():
    with pytest.raises(ValueError, match="in the pool"):
        _build("nature.tree_columns.enabled=true", "nature.tree_columns.spots=[[1.0,10.0]]")


LILIES = ["nature.lily_pads.enabled=true", "nature.lily_pads.count=14", "nature.lily_pads.flowers=0.3"]


def _pads():
    return sorted((o for o in bpy.data.objects if o.name.startswith("LilyPad.")), key=lambda o: o.name)


def test_lily_pads_are_off_by_default():
    _build()
    assert not _pads()


def test_lily_pads_float_on_the_water_inside_the_pool_without_overlapping():
    cfg = _build(*LILIES)
    pool = cfg["pool"]
    pads = _pads()
    assert len(pads) == 14
    (x0, x1), (y0, y1) = pool["x"], pool["y"]
    for p in pads:
        r = p["radius"]
        assert x0 < p.location.x - r and p.location.x + r < x1 and y0 < p.location.y - r and p.location.y + r < y1
        assert abs(p.location.z - pool["water_level"]) < 0.02
    for i, a in enumerate(pads):
        for b in pads[i + 1:]:
            d = math.hypot(a.location.x - b.location.x, a.location.y - b.location.y)
            assert d >= a["radius"] + b["radius"] - 1e-6


def test_some_pads_carry_flowers():
    _build(*LILIES)
    flowers = [o for o in bpy.data.objects if o.name.startswith("LilyFlower.")]
    assert 1 <= len(flowers) <= 14
    for f in flowers:
        assert f.parent is not None and f.parent.name.startswith("LilyPad.")


def test_lily_pads_bob_and_the_loop_still_closes():
    cfg = _build(*LILIES)
    from wavegen.scene.loopcheck import driven_values
    assert any(k.startswith("LilyPad.0:location") for k in driven_values(1))
    assert loop_mismatches(cfg) == []


def test_lily_pads_keep_off_the_notch_step():
    import random
    from wavegen.scene.nature import place_pads
    cfg = config.load("poolrooms", ["nature.lily_pads.count=40", "nature.lily_pads.clusters=1",
                                    "nature.lily_pads.size=[0.15,0.3]"])
    (x0, _), (_, y1) = cfg["pool"]["x"], cfg["pool"]["y"]
    nw, nd = cfg["pool"]["notch"]
    for seed in range(25):
        for x, y, r in place_pads(cfg, random.Random(seed)):
            # nearest point of the step's rectangle to the pad centre
            qx, qy = min(max(x, x0), x0 + nw), min(max(y, y1 - nd), y1)
            assert math.hypot(x - qx, y - qy) >= r, (seed, x, y, r)


def test_tree_branches_stay_inside_the_walls():
    cfg = _build("nature.tree_columns.enabled=true")              # the default spots stand 0.75 m off the right wall
    W = cfg["room"]["width"]
    for i in range(len(cfg["nature"]["tree_columns"]["spots"])):
        col = bpy.data.objects[f"TreeColumn.{i}"]
        xs = [(col.matrix_world @ v.co).x for v in col.data.vertices]
        assert -W / 2 < min(xs) and max(xs) < W / 2


BEAMS = SKY + ["nature.skylight.beams.density=0.05"]


def test_no_sunbeam_haze_unless_asked():
    _build(*SKY)
    assert "Sunbeams" not in bpy.data.objects


def test_sunbeam_haze_fills_the_room_and_only_the_sun_lights_it():
    cfg = _build(*BEAMS)
    beams = bpy.data.objects["Sunbeams"]
    vol = beams.active_material.node_tree.nodes["Principled Volume"]
    assert vol.inputs["Density"].default_value == pytest.approx(0.05)
    assert vol.inputs["Anisotropy"].default_value == pytest.approx(cfg["nature"]["skylight"]["beams"]["anisotropy"])
    sun = bpy.data.objects["Sun"]
    assert sun.light_linking.receiver_collection is None            # the sun lights everything
    others = [o for o in bpy.data.objects if o.type == "LIGHT" and o is not sun]
    assert others
    for o in others:                                                # every other light skips the beams
        rc = o.light_linking.receiver_collection
        entry = next(e for ob, e in zip(rc.objects, rc.collection_objects) if ob is beams)
        assert entry.light_linking.link_state == "EXCLUDE"
    assert beams.visible_shadow is False
