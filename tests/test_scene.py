"""Scene-graph tests; skipped automatically when bpy is unavailable."""
import pytest

bpy = pytest.importorskip("bpy")

from wavegen import config  # noqa: E402
from wavegen.scene import build_scene  # noqa: E402


@pytest.fixture(scope="module")
def scene():
    cfg = config.load("poolrooms", ["atmosphere.dust_count=12"])
    build_scene(cfg)
    return cfg, bpy.context.scene


def test_frame_range_and_camera(scene):
    cfg, sc = scene
    assert sc.frame_end == round(cfg["render"]["seconds"] * cfg["render"]["fps"])
    assert sc.camera is not None and sc.camera.name == "Camera"


def test_expected_objects(scene):
    names = set(bpy.data.objects.keys())
    for n in ("Water", "PoolBasin", "Wall.back", "Ceiling", "Computer.body", "Computer.screen",
              "Keyboard.keys", "Icon.pivot", "CoveLight", "AccentLight"):
        assert n in names, n
    n_back = len(scene[0]["room"]["back_arches"])
    assert sum(1 for o in names if o.startswith("AlcoveLight.back")) == n_back
    assert sum(1 for o in names if o.startswith("Dust.")) == 12


def test_animation_moves_camera_icon_and_water(scene):
    cfg, sc = scene
    cam, icon = bpy.data.objects["Camera"], bpy.data.objects["Icon.pivot"]
    waves = bpy.data.materials["Water"].node_tree.nodes["waves"].inputs["W"]
    sc.frame_set(1)
    c1, r1, w1 = cam.matrix_world.translation.copy(), icon.rotation_euler.copy(), waves.default_value
    sc.frame_set(200)
    c2, r2, w2 = cam.matrix_world.translation.copy(), icon.rotation_euler.copy(), waves.default_value
    assert (c2 - c1).length > 0.01
    assert abs(r2[1] - r1[1]) > 0.5
    assert abs(w2 - w1) > 1e-3
    # drift is gentle: never more than ~half a metre from the preset location
    for f in range(1, sc.frame_end + 1, 37):
        sc.frame_set(f)
        d = cam.matrix_world.translation - __import__("mathutils").Vector(cfg["camera"]["location"])
        assert d.length < 0.5


def test_walls_have_arch_booleans(scene):
    wall = bpy.data.objects["Wall.back"]
    assert any(m.type == "BOOLEAN" for m in wall.modifiers)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = wall.evaluated_get(dg)
    assert len(ev.data.vertices) > 8 * 10  # boolean actually cut the arches



def test_loop_seam_all_drivers():
    from wavegen.scene.loopcheck import loop_mismatches
    cfg = config.load("poolrooms", ["render.seconds=8", "render.fps=15", "atmosphere.dust_count=10"])
    build_scene(cfg)
    assert bpy.context.scene.frame_end == 120
    assert loop_mismatches(cfg) == []


def _all_objects(col):
    yield from col.objects
    for ch in col.children:
        yield from _all_objects(ch)


def test_cutters_hidden_in_viewport(scene):
    cut = bpy.data.collections["Cutters"]
    objs = list(_all_objects(cut))
    assert objs
    assert all(o.hide_viewport for o in objs)
    dg = bpy.context.evaluated_depsgraph_get()
    assert len(bpy.data.objects["Wall.back"].evaluated_get(dg).data.vertices) > 80


def test_scene_builds_without_computer_and_dof():
    cfg = config.load("poolrooms", ["atmosphere.dust_count=2", "computer.enabled=false", "camera.dof=true"])
    build_scene(cfg)
    cam = bpy.data.objects["Camera"]
    assert cam.data.dof.use_dof and cam.data.dof.focus_object.name == "Camera.target"


def test_bloom_zero_bypasses_glare():
    cfg = config.load("poolrooms", ["atmosphere.dust_count=2", "render.bloom.strength=0"])
    build_scene(cfg)
    ng = bpy.context.scene.compositing_node_group
    assert not any(n.bl_idname == "CompositorNodeGlare" for n in ng.nodes)


def test_loopcheck_flags_non_looping_driver():
    from wavegen.scene.loopcheck import loop_mismatches
    from wavegen.scene.util import drive
    cfg = config.load("poolrooms", ["render.seconds=4", "render.fps=15", "atmosphere.dust_count=2"])
    build_scene(cfg)
    drive(bpy.data.objects["Camera.target"], "location", "frame*0.01", 0)
    assert any("Camera.target" in m for m in loop_mismatches(cfg))
