"""Scene-graph tests; skipped automatically when bpy is unavailable."""
from pathlib import Path

import math

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
    assert sum(1 for o in names if o.startswith("AlcoveLight.back")) == 2 * n_back          # twin sconces
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
    assert max(xs) - min(xs) <= 0.10          # the parallax sweep lets the CRT breathe a little
    assert max(ys) <= 0.5


def test_pier_behind_crt_matches_reference(look):
    from wavegen.scene.framing import project_bounds
    x0, x1, _, y1 = project_bounds("Pier", 1)
    assert abs(x0 - 0.17) <= 0.06 and abs(x1 - 0.30) <= 0.06, (x0, x1)
    assert y1 > 0.32                                  # runs down behind the CRT


def test_side_bay_is_lit_from_inside(look):
    from mathutils import Vector
    bay = bpy.data.objects["Bay"]
    bb = [bay.matrix_world @ Vector(c) for c in bay.bound_box]
    lo = [min(v[i] for v in bb) for i in range(3)]
    hi = [max(v[i] for v in bb) for i in range(3)]
    p = bpy.data.objects["BayLight"].matrix_world.translation
    assert all(lo[i] < p[i] < hi[i] for i in range(3)), (lo, hi, tuple(p))
    assert bay.data.materials[0].name == "BayTile"
    pier = bpy.data.objects["Pier"].matrix_world.translation
    assert hi[0] <= pier.x                            # the passage opens left of the pier


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


# Reference framing, measured on docs/ref/video/v25.jpg: x0, x1, y0, y1, y from top.
REF_FRAMING = {
    "Computer.body": (0.04, 0.36, 0.31, 0.82),
    "Computer.screen": (0.205, 0.335, 0.36, 0.58),
}


def test_reference_framing(look):
    from wavegen.scene.framing import project_bounds
    off = {}
    for name, ref in REF_FRAMING.items():
        got = project_bounds(name, 1)
        off[name] = [round(g - r, 3) for g, r in zip(got, ref)]
    assert all(abs(d) <= 0.06 for ds in off.values() for d in ds), off


def test_twin_sconces_per_alcove(look):
    cfg, _ = look
    n = len(cfg["room"]["back_arches"]) + 2 * len(cfg["room"]["side_arches"])
    sconces = [o for o in bpy.data.objects if o.name.startswith("Sconce.")]
    lights = [o for o in bpy.data.objects if o.name.startswith("AlcoveLight.")]
    assert len(sconces) == 2 * n and len(lights) == 2 * n


def test_alcoves_have_tile_wainscot(look):
    mat = bpy.data.materials["AlcoveTile"]
    assert any(n.type == "MIX_SHADER" for n in mat.node_tree.nodes)


def test_floor_uses_large_tiles(look):
    cfg, _ = look
    assert cfg["room"]["floor_tile_size"] >= 2 * cfg["room"]["tile_size"]
    assert bpy.data.objects["Floor.0"].data.materials[0].name == "FloorTile"
    assert cfg["pool"]["depth"] <= 1.0                  # shallow: the tiled pool floor shows through


def _driven(mat, node):
    ad = mat.node_tree.animation_data
    return ad is not None and any(f'nodes["{node}"]' in d.data_path for d in ad.drivers)


def test_water_has_swell_and_fine_ripples(look):
    water = bpy.data.materials["Water"]
    assert _driven(water, "waves") and _driven(water, "ripples")


def test_pool_floor_has_looping_caustics(look):
    pool = bpy.data.materials["PoolTile"]
    assert "caustics" in pool.node_tree.nodes and _driven(pool, "caustics")


def test_sweep_keeps_screen_in_frame(look):
    from wavegen.scene.framing import project_bounds
    _, sc = look
    cam = bpy.data.objects["Camera"]
    xs, bounds = [], []
    for f in np.linspace(1, sc.frame_end, 12).astype(int):
        b = project_bounds("Computer.screen", int(f))
        xs.append(cam.matrix_world.translation.x)
        bounds.append(b)
    sc.frame_set(1)
    assert max(xs) - min(xs) >= 0.3, (min(xs), max(xs))
    assert all(0.02 <= b[0] and b[1] <= 0.98 and 0.02 <= b[2] and b[3] <= 0.98 for b in bounds), bounds


def test_pier_outline_rejects_depth_too_shallow_for_its_round_front():
    from wavegen.scene.architecture import _pier_outline
    pts = _pier_outline(1.1, 1.0)
    assert max(y for _, y in pts) == pytest.approx(0.5)
    with pytest.raises(ValueError, match="depth"):
        _pier_outline(1.1, 0.4)  # the half-round front (r=0.55) would poke out of the back


def test_pier_outline_has_no_coincident_points_at_minimum_depth():
    from wavegen.scene.architecture import _pier_outline
    pts = _pier_outline(1.1, 0.55)  # depth == width/2: the round front meets the back corners
    assert all(math.dist(a, b) > 1e-9 for a, b in zip(pts, pts[1:] + pts[:1]))


def test_crt_housing_is_deep_and_cream(look):
    cfg, _ = look
    body = bpy.data.objects["Computer.body"]
    ys = [v.co.y for v in body.data.vertices]
    depth = max(ys) - min(ys)
    assert depth == pytest.approx(cfg["computer"]["depth"], abs=0.03)
    assert cfg["computer"]["depth"] >= 1.25 * 0.34          # deeper than it is wide, like the reference
    r, g, b = cfg["palette"]["beige"]
    assert r > g > b and r - b >= 0.2                        # warm cream, not lilac, under the cool lights


def test_crt_front_face_stays_put_when_depth_changes():
    from wavegen.scene.framing import project_bounds
    shallow = config.load("poolrooms", ["atmosphere.dust_count=0", "computer.depth=0.36"])
    build_scene(shallow)
    a = project_bounds("Computer.screen", 1)
    deep = config.load("poolrooms", ["atmosphere.dust_count=0", "computer.depth=0.5"])
    build_scene(deep)
    assert project_bounds("Computer.screen", 1) == pytest.approx(a, abs=1e-6)


def _world_verts(o):
    return [o.matrix_world @ v.co for v in o.data.vertices]


def test_everything_on_the_desk_rests_on_it_without_overhang(scene):
    """Every vertex of the computer and keyboard sits over the desk top, clear of its edges, and none sinks into it."""
    cfg, sc = scene
    sc.frame_set(1)
    desk = bpy.data.objects["Desk"]
    dv = _world_verts(desk)
    x0, x1 = min(v.x for v in dv), max(v.x for v in dv)
    y0, y1 = min(v.y for v in dv), max(v.y for v in dv)
    top = max(v.z for v in dv)
    margin = 0.03
    problems = {}
    for o in bpy.data.objects:
        if o.type != "MESH" or o.hide_render or not o.name.startswith(("Computer.", "Keyboard.")):
            continue
        vs = _world_verts(o)
        bad = {
            "x": (min(v.x for v in vs) < x0 + margin) or (max(v.x for v in vs) > x1 - margin),
            "y": (min(v.y for v in vs) < y0 + margin) or (max(v.y for v in vs) > y1 - margin),
            "sinks": min(v.z for v in vs) < top - 1e-3,
        }
        if any(bad.values()):
            problems[o.name] = [k for k, v in bad.items() if v]
    assert not problems, problems


def test_crt_depth_shallower_than_the_screen_recess_is_rejected():
    from wavegen.scene import props
    shallow = config.load("poolrooms", ["atmosphere.dust_count=0", f"computer.depth={props.RECESS_D}"])
    with pytest.raises(ValueError, match="depth"):
        build_scene(shallow)


def test_alcove_fill_lights_never_show_up_in_reflections(scene):
    fills = [o for o in bpy.data.objects if o.name.startswith("AlcoveFill.")]
    assert fills
    assert all(not o.visible_glossy and not o.visible_transmission for o in fills)   # mirror and refraction


def test_desk_laminate_is_glossy_with_a_clear_coat(scene):
    dc = config.load("poolrooms")["desk"]
    p = bpy.data.materials["DeskLaminate"].node_tree.nodes["Principled BSDF"]
    assert p.inputs["Roughness"].default_value == pytest.approx(dc["roughness"])
    assert p.inputs["Coat Weight"].default_value == pytest.approx(dc["coat"])
    assert dc["roughness"] <= 0.2 and dc["coat"] > 0


def test_alcove_lamps_hang_at_the_configured_height():
    cfg = config.load("poolrooms", ["atmosphere.dust_count=0", "lights.alcove_height=0.5"])
    build_scene(cfg)
    want = 0.5 * cfg["room"]["spring_height"]
    sconces = [o for o in bpy.data.objects if o.name.startswith("Sconce.")]
    lamps = [o for o in bpy.data.objects if o.name.startswith("AlcoveLight.")]
    assert sconces and lamps
    assert all(o.location.z == pytest.approx(want) for o in sconces + lamps)


def test_keyboard_stays_in_frame_through_the_whole_sweep(scene):
    from wavegen.scene.framing import project_bounds
    _, sc = scene
    bs = np.array([project_bounds("Keyboard.base", int(f)) for f in np.linspace(1, sc.frame_end, 121)])   # every half second
    sc.frame_set(1)
    assert bs[:, 0].min() >= 0.0 and bs[:, 1].max() <= 1.0, bs.round(3)      # left / right edges
    assert bs[:, 2].min() >= 0.0 and bs[:, 3].max() <= 1.0, bs.round(3)      # top / bottom edges
