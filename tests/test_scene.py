"""Scene-graph tests; skipped automatically when bpy is unavailable."""
from pathlib import Path

import numpy as np
import pytest

bpy = pytest.importorskip("bpy")

from wavegen import config  # noqa: E402
from wavegen.scene import build_scene  # noqa: E402


@pytest.fixture
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
              "Keyboard.keys", "CoveLight", "AccentLight"):
        assert n in names, n
    n_back = len(scene[0]["room"]["back_arches"])
    assert sum(1 for o in names if o.startswith("AlcoveLight.back")) == n_back
    assert sum(1 for o in names if o.startswith("Dust.")) == 12


def test_animation_moves_camera_emblem_and_water(scene):
    cfg, sc = scene
    cam = bpy.data.objects["Camera"]
    loc = bpy.data.materials["CRT"].node_tree.nodes["emblem_map"].inputs["Location"]
    waves = bpy.data.materials["Water"].node_tree.nodes["waves"].inputs["W"]
    sc.frame_set(1)
    c1, e1, w1 = cam.matrix_world.translation.copy(), tuple(loc.default_value), waves.default_value
    sc.frame_set(200)
    c2, e2, w2 = cam.matrix_world.translation.copy(), tuple(loc.default_value), waves.default_value
    assert (c2 - c1).length > 0.01
    assert abs(e2[0] - e1[0]) > 0.05 and abs(e2[1] - e1[1]) > 0.05
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


def test_emblem_rendered_and_wired(scene):
    nt = bpy.data.materials["CRT"].node_tree
    imgs = [n.image for n in nt.nodes if n.bl_idname == "ShaderNodeTexImage" and n.image]
    paths = [Path(bpy.path.abspath(i.filepath)) for i in imgs]
    assert any(p.name.startswith("emblem_") and not p.stem.endswith("_mask") for p in paths)
    assert any(p.stem.endswith("_mask") for p in paths)
    assert all(p.exists() and p.stat().st_size > 1024 for p in paths)
    ad = bpy.data.materials["CRT"].node_tree.animation_data
    driven = {(fc.data_path, fc.array_index) for fc in ad.drivers}
    assert ('nodes["emblem_map"].inputs["Location"].default_value', 0) in driven
    assert ('nodes["emblem_map"].inputs["Location"].default_value', 1) in driven
    assert any("emblem_hits" in d for d, _ in driven)


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


def test_emblem_builtin_font(tmp_path):
    from wavegen.scene.emblem import render_emblem
    cfg = config.load("poolrooms", ["computer.emblem.font=null"])
    text, mask = render_emblem(cfg, tmp_path)
    assert text.stat().st_size > 1024 and mask.stat().st_size > 1024


def _aim_at_screen(sc, tmp):
    import mathutils
    bpy.context.view_layer.update()                  # evaluate parent transforms first
    scr = bpy.data.objects["Computer.screen"]
    mw = scr.matrix_world
    centre = mw @ (sum((mathutils.Vector(c) for c in scr.bound_box), mathutils.Vector()) / 8)
    normal = (mw.to_3x3() @ mathutils.Vector((0, -1, 0))).normalized()
    cam = bpy.data.objects.new("ScreenCam", bpy.data.cameras.new("ScreenCam"))
    cam.data.lens = 50
    sc.collection.objects.link(cam)
    cam.location = centre + normal * 0.35
    cam.rotation_euler = (-normal).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 64, 48, 100
    sc.cycles.samples = 4
    sc.cycles.device = "CPU"
    sc.render.image_settings.file_format = "PNG"


def _render_screen(sc, frame, path):
    import subprocess
    sc.frame_set(frame)
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(48, 64, 3).astype(np.float32) / 255


def test_screen_pixels_change_over_loop(tmp_path):
    cfg = config.load("poolrooms", ["render.seconds=4", "render.fps=15", "atmosphere.dust_count=0",
                                    "atmosphere.haze_density=0", "render.bloom.strength=0"])
    build_scene(cfg)
    sc = bpy.context.scene
    _aim_at_screen(sc, tmp_path)
    a = _render_screen(sc, 1, tmp_path / "a.png")
    b = _render_screen(sc, 13, tmp_path / "b.png")      # mid-trip on both axes
    c = _render_screen(sc, 61, tmp_path / "c.png")
    assert np.abs(a - c).mean() < 2 / 255             # seamless at the loop point
    moved = (np.abs(a - b).max(-1) > 0.15).mean()
    assert moved > 0.01                                # the emblem visibly moved mid-loop


# ---- v2 look-match + smoothness ---------------------------------------------

@pytest.fixture(scope="module")
def look():
    """Fresh default build (earlier tests rebuild the session and invalidate ``scene``)."""
    cfg = config.load("poolrooms", ["atmosphere.dust_count=12"])
    build_scene(cfg)
    return cfg, bpy.context.scene


def _project(sc, obj_or_point):
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector
    p = obj_or_point if isinstance(obj_or_point, Vector) else obj_or_point.matrix_world.translation
    return world_to_camera_view(sc, sc.camera, p)


def test_dof_off_by_default(look):
    cfg, sc = look
    assert cfg["camera"]["dof"] is False
    assert not sc.camera.data.dof.use_dof


def test_look_config_keys(look):
    cfg, _ = look
    assert cfg["room"]["tile_size"] == pytest.approx(0.13)
    assert cfg["room"]["grout_width"] >= 0.02
    assert cfg["room"]["alcove_depth"] >= 3.2
    assert cfg["room"]["arch_surround"] == {"width": 0.22, "depth": 0.12}
    assert cfg["lights"]["alcove_type"] in ("SPOT", "AREA")
    assert cfg["lights"]["accent_size"] >= 4.0


def test_computer_screen_anchor(look):
    _, sc = look
    body = bpy.data.objects["Computer.body"]
    xs, ys = [], []
    for f in np.linspace(1, sc.frame_end, 30).astype(int):
        sc.frame_set(int(f))
        v = _project(sc, body)
        xs.append(v.x)
        ys.append(v.y)
    sc.frame_set(1)
    assert 0.08 <= min(xs) and max(xs) <= 0.38, (min(xs), max(xs))
    assert max(xs) - min(xs) <= 0.04
    assert max(ys) <= 0.5


def test_column_in_frame(look):
    cfg, sc = look
    from mathutils import Vector
    col = bpy.data.objects["Column"]
    bb = [col.matrix_world @ Vector(c) for c in col.bound_box]
    centre = sum(bb, Vector()) / 8
    sc.frame_set(1)
    v = _project(sc, Vector((centre.x, centre.y, cfg["room"]["height"] / 2)))
    assert 0 <= v.x <= 1 and v.z > 0, tuple(v)


def test_arch_surrounds_exist(look):
    cfg, _ = look
    n_arches = len(cfg["room"]["back_arches"]) + 2 * len(cfg["room"]["side_arches"])
    assert sum(1 for o in bpy.data.objects if o.name.startswith("ArchSurround.")) == n_arches


def _per_m2(light):
    d = light.data
    if d.type == "AREA":
        area = d.size * (d.size_y if d.shape in ("RECTANGLE", "ELLIPSE") else d.size)
    else:
        area = 3.14159 * max(d.shadow_soft_size, 1e-3) ** 2
    return d.energy / area


def test_alcove_lights_brightest(look):
    cove = _per_m2(bpy.data.objects["CoveLight"])
    alc = [o for o in bpy.data.objects if o.name.startswith("AlcoveLight.")]
    assert alc and all(_per_m2(o) > cove for o in alc)


def test_motion_blur_and_stable_noise(look):
    cfg, sc = look
    assert cfg["render"]["motion_blur"] > 0
    assert sc.render.use_motion_blur
    assert sc.render.motion_blur_shutter == pytest.approx(cfg["render"]["motion_blur"])
    assert not sc.cycles.use_animated_seed          # grain stays put, no frame-to-frame boil


def test_emblem_images_packed_into_blend(look):
    imgs = [bpy.data.materials["CRT"].node_tree.nodes[n].image for n in ("emblem_text", "emblem_mask")]
    assert all(i.packed_file is not None for i in imgs)


def test_spread_handles_walls_with_no_openings():
    from wavegen.scene.architecture import _spread
    assert _spread(0.2, []) == []                    # _fit returns [] for walls this short
    assert _spread(5.0, []) == []
