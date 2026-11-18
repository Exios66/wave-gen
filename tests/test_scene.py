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
    bpy.context.view_layer.update()        # world matrices are stale until the first update
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
    x0, x1, y0, y1 = project_bounds("Pier", 1)
    assert abs(x0 - 0.17) <= 0.06 and abs(x1 - 0.30) <= 0.06, (x0, x1)
    assert y0 < 0.1 and y1 > 0.32, (y0, y1)           # in frame from the top, running down behind the CRT


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
        if name == "Computer.body":                # the reference outline is the whole unit: head and foot
            foot = project_bounds("Computer.foot", 1)
            got = (min(got[0], foot[0]), max(got[1], foot[1]), min(got[2], foot[2]), max(got[3], foot[3]))
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


def test_alcove_tile_size_is_its_own_setting():
    cfg = config.load("poolrooms", ["atmosphere.dust_count=0", "room.alcove_tile_size=0.31"])
    build_scene(cfg)
    size = lambda name: bpy.data.materials[name].node_tree.nodes["tile_cell"].inputs[1].default_value[0]
    assert size("AlcoveTile") == pytest.approx(0.31)
    assert size("Tile") == pytest.approx(cfg["room"]["tile_size"])


def test_arch_profile_default_is_a_semicircle():
    from wavegen.scene.util import arch_profile
    pts = arch_profile(3.0, 2.0)
    assert max(v for _, v in pts) == pytest.approx(2.0 + 1.5)
    assert sum(1 for _, v in pts if v == pytest.approx(3.5)) == 1          # a single crown point


def test_arch_profile_with_corner_radius_has_a_flat_top():
    from wavegen.scene.util import arch_profile
    pts = arch_profile(5.0, 2.0, corner_radius=1.0)
    top = [u for u, v in pts if v == pytest.approx(3.0)]
    assert max(v for _, v in pts) == pytest.approx(3.0)                    # spring + radius, not spring + width/2
    assert min(top) == pytest.approx(-1.5) and max(top) == pytest.approx(1.5)   # flat between the two corners
    assert all(abs(u) <= 2.5 + 1e-9 for u, _ in pts)


def test_arch_corner_radius_is_capped_at_half_the_width():
    from wavegen.scene.util import arch_profile
    assert arch_profile(2.0, 2.0, corner_radius=5.0) == arch_profile(2.0, 2.0)


def test_arch_profile_with_zero_corner_radius_is_a_plain_rectangle():
    from wavegen.scene.util import arch_profile
    pts = arch_profile(4.0, 2.0, corner_radius=0.0)
    assert len(set(pts)) == len(pts)            # no coincident points, so no zero-length edges
    assert pts == [(-2.0, -0.05), (2.0, -0.05), (2.0, 2.0), (-2.0, 2.0)]


def test_arch_tops_line_up_when_a_corner_radius_is_set():
    cfg = config.load("poolrooms", ["atmosphere.dust_count=0", "room.arch_corner_radius=1.2"])
    build_scene(cfg)
    tops = {round(max((o.matrix_world @ v.co).z for v in o.data.vertices), 3)
            for o in bpy.data.objects if o.name.startswith("ArchSurround.")}
    assert len(tops) == 1, tops                                             # wide and narrow arches end level


def test_bay_is_tiled_like_the_alcoves():
    cfg = config.load("poolrooms", ["atmosphere.dust_count=0", "room.alcove_tile_size=0.31"])
    build_scene(cfg)
    assert bpy.data.materials["BayTile"].node_tree.nodes["tile_cell"].inputs[1].default_value[0] == pytest.approx(0.31)


def test_bay_light_never_shows_up_as_a_disc_in_the_tiles(scene):
    assert not bpy.data.objects["BayLight"].visible_glossy


def _world_bounds(o):
    from mathutils import Vector
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return [min(p[k] for p in pts) for k in range(3)], [max(p[k] for p in pts) for k in range(3)]


def test_no_nested_arch_by_default():
    cfg = config.load(None, ["atmosphere.dust_count=0"])
    assert cfg["room"]["nested_arch"] is None
    build_scene(cfg)
    assert not [o for o in bpy.data.objects if o.name.startswith("NestedArch")]


def test_poolrooms_centre_alcove_has_a_nested_arch_set_inside_it(scene):
    """The reference's wide centre opening shows a second, smaller arch further in."""
    from mathutils import Vector
    cfg, _ = scene
    na = cfg["room"]["nested_arch"]
    inner = [o for o in bpy.data.objects if o.name.startswith("NestedArch")]
    assert len(inner) == 1
    o = inner[0]
    bpy.context.view_layer.update()
    lo, hi = _world_bounds(o)
    _, wall_hi = _world_bounds(bpy.data.objects["Wall.back"])
    assert lo[1] >= wall_hi[1] + 0.3                       # set back inside the alcove, behind the wall
    assert hi[1] < wall_hi[1] + cfg["room"]["alcove_depth"]  # but in front of the lamps on its back wall
    width = cfg["room"]["back_arches"][na["arch"]]
    cx = (lo[0] + hi[0]) / 2
    inv = o.matrix_world.inverted()

    def blocked(x, z):
        hit, *_ = o.ray_cast(inv @ Vector((x, lo[1] - 1.0, z)), inv.to_3x3() @ Vector((0, 1, 0)))
        return hit

    assert not blocked(cx, 1.5)                            # open in the middle
    assert blocked(cx + width / 2 - na["inset"] / 2, 1.5)  # narrower than the outer opening
    assert blocked(cx, hi[2] - 0.1)                        # and closed above its own arch


def test_no_passage_sconce_by_default():
    cfg = config.load(None, ["atmosphere.dust_count=0"])
    assert cfg["room"]["bay"]["sconce_power"] == 0.0
    build_scene(cfg)
    assert "BaySconce" not in bpy.data.objects and "BaySconceLight" not in bpy.data.objects


def test_poolrooms_passage_has_a_visible_wall_lamp(scene):
    """The reference shows a warm lamp glowing on the tile behind the pier."""
    cfg, _ = scene
    by, power = cfg["room"]["bay"], cfg["room"]["bay"]["sconce_power"]
    assert power > 0
    bpy.context.view_layer.update()
    dome, lamp = bpy.data.objects["BaySconce"], bpy.data.objects["BaySconceLight"]
    assert dome.active_material.name == "Sconce" and dome.visible_camera
    lo, hi = _world_bounds(bpy.data.objects["Bay"])
    assert hi[1] - dome.location.y < 0.15                  # mounted on the passage's back wall
    assert lo[0] < dome.location.x < hi[0] and 2.0 < dome.location.z < by["height"] - 0.5
    assert lamp.data.energy == power
    assert lamp.location.y < dome.location.y               # the washer sits in front and aims back at the wall


def _tile_colour(name):
    return tuple(bpy.data.materials[name].node_tree.nodes["tile_base"].outputs[0].default_value)[:3]


def test_floor_tile_follows_the_wall_tile_unless_given_its_own_colour():
    build_scene(config.load(None, ["atmosphere.dust_count=0"]))
    assert _tile_colour("FloorTile") == pytest.approx(_tile_colour("Tile"))
    build_scene(config.load(None, ["atmosphere.dust_count=0", "palette.floor_tile=[0.9,0.5,0.7]"]))
    assert _tile_colour("FloorTile") == pytest.approx((0.9, 0.5, 0.7))
    assert _tile_colour("Tile") != pytest.approx((0.9, 0.5, 0.7))


def test_no_lamp_halos_by_default():
    cfg = config.load(None, ["atmosphere.dust_count=0"])
    assert cfg["lights"]["halo_radius"] == 0.0
    build_scene(cfg)
    assert not [o for o in bpy.data.objects if o.name.startswith("SconceHalo")]


def test_poolrooms_alcove_lamps_have_a_soft_wall_halo(scene):
    """The reference lamps bloom into a wide warm glow on the tile around them."""
    cfg, _ = scene
    radius = cfg["lights"]["halo_radius"]
    assert radius >= 0.4
    bpy.context.view_layer.update()
    sconces = [o for o in bpy.data.objects if o.name.startswith("Sconce.")]
    halos = [o for o in bpy.data.objects if o.name.startswith("SconceHalo.")]
    assert len(halos) == len(sconces) > 0
    for h in halos:
        lamp = bpy.data.objects[h.name.replace("SconceHalo.", "Sconce.")]
        assert (h.location - lamp.location).length < 0.1            # centred on its lamp, against the wall
        assert max(h.dimensions) == pytest.approx(2 * radius, rel=0.05)
        assert not h.visible_shadow                                  # a glow must not block the lamp's light
    nt = halos[0].active_material.node_tree
    src = lambda sock: sock.links[0].from_node              # the node feeding a socket
    out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    add = src(out.inputs["Surface"])
    assert {src(i).bl_idname for i in add.inputs} == {"ShaderNodeBsdfTransparent", "ShaderNodeEmission"}
    em = next(src(i) for i in add.inputs if src(i).bl_idname == "ShaderNodeEmission")
    scale = src(em.inputs["Strength"])                      # strength x falloff
    assert scale.operation == "MULTIPLY" and scale.inputs[1].default_value == pytest.approx(cfg["lights"]["halo_strength"])
    power = src(scale.inputs[0])
    assert power.operation == "POWER" and power.inputs[1].default_value > 1     # soft, not a hard-edged disc
    grad = src(power.inputs[0])
    assert grad.bl_idname == "ShaderNodeTexGradient" and grad.gradient_type == "SPHERICAL"   # 1 at the centre, 0 at the rim
    assert grad.inputs["Vector"].links[0].from_socket.name == "Object"


def test_emblem_cache_key_changes_when_the_font_file_is_replaced(tmp_path):
    import os
    from wavegen.scene.emblem import _key
    font = tmp_path / "f.ttf"
    font.write_bytes(b"one")
    ec = {"text": "WAVE GEN", "shape": "sun", "font": str(font)}
    k1 = _key(ec)
    assert _key(ec) == k1
    font.write_bytes(b"another font")
    os.utime(font, (1, 1))
    assert _key(ec) != k1
    assert _key({**ec, "font": None}) == _key({**ec, "font": None})


def test_unsupported_screensaver_is_refused_up_front_and_names_the_real_modes():
    from wavegen.scene import screensaver
    assert screensaver.MODES == ("emblem", "flower")
    cfg = config.load("poolrooms", ["computer.screensaver=starfield"])
    with pytest.raises(ValueError, match="use emblem or flower"):
        build_scene(cfg)


def test_alcove_boxes_never_overlap_across_a_minimum_pier():
    from wavegen.scene.architecture import _alcove_pad
    assert _alcove_pad(16.0, [3.0, 5.4, 3.0]) == 0.35           # roomy piers keep the full return
    pad = _alcove_pad(3 * 3.0 + 4 * 0.6, [3.0, 3.0, 3.0])       # piers at the 0.6 m minimum
    assert 0 < 2 * pad < 0.6


def test_frame_range_follows_the_shared_loop_length():
    from wavegen.frames import loop_frame_count
    from wavegen.scene import render
    cfg = config.load("poolrooms", ["render.seconds=2.02", "render.fps=30.0"])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    render.configure(cfg)
    assert bpy.context.scene.frame_end == loop_frame_count(cfg) == 61


def _local_bounds(name):
    """Bounds of an object's raw mesh in the computer rig's frame."""
    bpy.context.view_layer.update()
    o = bpy.data.objects[name]
    inv = bpy.data.objects["Computer.rig"].matrix_world.inverted()
    vs = [inv @ (o.matrix_world @ v.co) for v in o.data.vertices]
    return [(min(v[i] for v in vs), max(v[i] for v in vs)) for i in range(3)]


def test_monitor_head_overhangs_a_narrower_foot(scene):
    (hx0, hx1), (hy0, _), (_, hz1) = _local_bounds("Computer.body")
    (fx0, fx1), (fy0, _), (fz0, fz1) = _local_bounds("Computer.foot")
    assert fz0 == pytest.approx(0.0, abs=1e-4) and 0.05 <= fz1 <= 0.1      # a low pedestal on the desk
    assert fx0 > hx0 + 0.015 and fx1 < hx1 - 0.015                         # narrower than the head
    assert fy0 >= hy0 + 0.05                                               # set back: the head overhangs it
    assert hz1 > 0.40 > hx1 - hx0                                          # taller than it is wide


def test_monitor_front_is_plain_with_vents_on_the_side_of_the_foot(scene):
    names = [o.name for o in bpy.data.objects]
    assert not any(n.startswith(("Computer.floppy", "Computer.led", "Computer.vent.")) for n in names)
    vents = [n for n in names if n.startswith("Computer.sidevent.")]
    assert len(vents) >= 8
    (fx0, _), _, (_, fz1) = _local_bounds("Computer.foot")
    for n in vents:
        (x0, x1), _, (_, z1) = _local_bounds(n)
        assert x0 < fx0 < x1 and x0 > fx0 - 0.005 and z1 < fz1             # slots in the foot's left face


def test_monitor_glass_is_curved_and_framed_by_a_rounded_bezel(scene):
    _, sc = scene
    _, (y0, y1), _ = _local_bounds("Computer.screen")
    assert y1 - y0 >= 0.018                                                # visibly bulged glass
    bezel = bpy.data.objects["Computer.bezel"]
    hole = bpy.data.objects["BezelHoleCut"]
    dg = bpy.context.evaluated_depsgraph_get()
    assert len(hole.evaluated_get(dg).data.vertices) > 40                  # the opening has rounded corners
    assert len(bezel.evaluated_get(dg).data.vertices) > 150


def test_monitor_head_tilts_back_only_when_asked():
    cfg = config.load(None, ["atmosphere.dust_count=0"])
    build_scene(cfg)
    assert cfg["computer"]["tilt"] == 0.0
    flat = _local_bounds("Computer.screen")[1]
    build_scene(config.load(None, ["atmosphere.dust_count=0", "computer.tilt=5"]))
    (_, _), (y0, y1), _ = _local_bounds("Computer.screen")
    assert y1 - y0 > (flat[1] - flat[0]) + 0.005                           # the top of the glass leans back
    assert bpy.data.objects["Computer.screen"].parent.name == "Computer.head"


# ---- pool kerb and corner notch ----------------------------------------------

def _kerbs():
    return [o for o in bpy.data.objects if o.name.startswith("Coping.")]


def test_default_pool_is_a_plain_rectangle_with_a_low_white_lip():
    cfg = config.load(None, ["atmosphere.dust_count=0"])
    assert cfg["pool"]["notch"] is None and cfg["pool"]["kerb"] == {"height": 0.05, "pool_tile": False}
    build_scene(cfg)
    bpy.context.view_layer.update()
    assert "PoolNotch" not in bpy.data.objects and len(_kerbs()) == 4
    for o in _kerbs():
        assert o.material_slots[0].material.name == "Tile"
        assert abs(_world_bounds(o)[1][2] - 0.05) < 1e-4


def test_kerb_can_be_a_raised_course_of_pool_tile():
    cfg = config.load("poolrooms", ["atmosphere.dust_count=0", "pool.kerb.height=0.13", "pool.kerb.pool_tile=true"])
    build_scene(cfg)
    bpy.context.view_layer.update()
    mat = bpy.data.materials["KerbTile"]
    assert "caustics" not in mat.node_tree.nodes                        # it is above the water: no light lines
    assert len(_kerbs()) == 6
    for o in _kerbs():
        assert o.material_slots[0].material == mat
        assert abs(_world_bounds(o)[1][2] - 0.13) < 1e-4


def test_poolrooms_pool_has_a_stepped_notch_in_its_far_left_corner(scene):
    cfg, _ = scene
    bpy.context.view_layer.update()
    pool = cfg["pool"]
    w, d = pool["notch"]
    (px0, px1), (py0, py1) = pool["x"], pool["y"]
    assert 0 < w < (px1 - px0) / 2 and 0 < d < (py1 - py0) / 4
    lo, hi = _world_bounds(bpy.data.objects["PoolNotch"])
    assert np.allclose(lo, (px0, py1 - d, -pool["depth"]), atol=1e-4)
    assert np.allclose(hi, (px0 + w, py1, 0.0), atol=1e-4)
    assert bpy.data.objects["PoolNotch"].material_slots[0].material.name == "PoolTile"
    top_lo, top_hi = _world_bounds(bpy.data.objects["Floor.notch"])     # walkable floor over the step
    assert np.allclose(top_lo[:2], lo[:2], atol=1e-4) and np.allclose(top_hi[:2], hi[:2], atol=1e-4)


def test_poolrooms_kerb_follows_the_notched_edge_and_never_sits_on_the_water(scene):
    cfg, _ = scene
    bpy.context.view_layer.update()
    pool = cfg["pool"]
    w, d = pool["notch"]
    (px0, px1), (py0, py1) = pool["x"], pool["y"]
    c = pool["coping"]

    def wet(x, y):                                  # open water: the rectangle less the notch
        return px0 < x < px1 and py0 < y < py1 and not (x < px0 + w and y > py1 - d)

    rects = [(lo[0], lo[1], hi[0], hi[1]) for lo, hi in map(_world_bounds, _kerbs())]
    for x0, y0, x1, y1 in rects:
        for x in np.linspace(x0 + 1e-3, x1 - 1e-3, 9):
            for y in np.linspace(y0 + 1e-3, y1 - 1e-3, 9):
                assert not wet(x, y), (x0, y0, x1, y1)

    def kerbed(x, y):
        return any(x0 - 1e-4 <= x <= x1 + 1e-4 and y0 - 1e-4 <= y <= y1 + 1e-4 for x0, y0, x1, y1 in rects)

    h = c / 2                                       # just outside every stretch of the water's edge
    assert kerbed(px0 + w / 2, py1 - d + h)         # the step's near edge
    assert kerbed(px0 + w - h, py1 - d / 2)         # the step's side
    assert kerbed((px0 + w + px1) / 2, py1 + h)     # the rest of the far edge
    assert kerbed(px0 - h, (py0 + py1 - d) / 2) and kerbed(px1 + h, (py0 + py1) / 2)
    assert kerbed((px0 + px1) / 2, py0 - h)
    assert not kerbed(px0 + w / 2 - c, py1 + h)     # no kerb left stranded behind the step


# ---- ceiling downlights --------------------------------------------------------

def _downlights():
    return sorted((o for o in bpy.data.objects if o.name.startswith("Downlight.")), key=lambda o: o.name)


def test_no_ceiling_downlights_by_default():
    cfg = config.load(None, ["atmosphere.dust_count=0"])
    assert cfg["lights"]["downlights"]["count"] == 0
    build_scene(cfg)
    assert not _downlights()


def test_poolrooms_has_a_row_of_small_downlights_over_the_right_walkway(scene):
    cfg, sc = scene
    bpy.context.view_layer.update()
    room, dl = cfg["room"], cfg["lights"]["downlights"]
    lamps = _downlights()
    assert len(lamps) == dl["count"] >= 3
    x1, inset = room["width"] / 2, room["ceiling_tray"]["inset"]
    ys = [o.matrix_world.translation.y for o in lamps]
    assert ys == sorted(ys) and len(set(round(y, 3) for y in ys)) == len(ys)
    for o in lamps:
        x, y, z = o.matrix_world.translation
        assert x1 - inset < x < x1                              # on the flat margin beside the tray
        assert 0 < room["height"] - z < 0.02                    # flush under the ceiling
        assert -3.5 < y < -3.5 + room["depth"]
        lo, hi = _world_bounds(o)
        assert hi[0] - lo[0] <= 0.3                             # small points, not panels
        em = o.material_slots[0].material.node_tree.nodes["Emission"]
        assert em.inputs["Strength"].default_value >= 5
        assert o.material_slots[0].material.cycles.emission_sampling == "NONE"   # a glow, not a light to sample
    sc.frame_set(1)
    seen = [p for p in (_project(sc, o) for o in lamps) if 0 < p.x < 1 and 0 < p.y < 1 and p.z > 0]
    assert len(seen) >= 2 and all(p.x > 0.6 and p.y > 0.7 for p in seen)   # bright points high on the right


def test_poolrooms_ceiling_tray_reaches_close_to_the_walls(scene):
    """In the clip the tray's stepped edge sits just inside the walls, with a narrow flat margin for the downlights."""
    cfg, _ = scene
    bpy.context.view_layer.update()
    room = cfg["room"]
    inset = room["ceiling_tray"]["inset"]
    assert 0.4 <= inset <= 0.8
    lo, hi = _world_bounds(bpy.data.objects["TrayCut.0"])
    assert abs(lo[0] - (-room["width"] / 2 + inset)) < 1e-3 and abs(hi[0] - (room["width"] / 2 - inset)) < 1e-3
    r = cfg["lights"]["downlights"]["radius"]
    for o in _downlights():                                    # the lamps still fit on the margin
        assert room["width"] / 2 - inset + r < o.matrix_world.translation.x < room["width"] / 2 - r


def test_catenary_arch_rises_as_asked_and_follows_a_hanging_chain():
    from wavegen.scene.util import arch_profile
    pts = arch_profile(3.0, 2.0, catenary=0.9)                  # rise = 0.9 x width = 2.7 m
    assert max(v for _, v in pts) == pytest.approx(2.0 + 2.7)
    assert (1.5, 2.0) in pts and (-1.5, 2.0) in pts
    arc = [(u, v) for u, v in pts[3:-1]]
    crown = 2.0 + 2.7
    cs = [(abs(u), crown - v) for u, v in arc if abs(u) > 1e-6]
    # every arc point lies on y = a (cosh(x / a) - 1) for one shared a
    import math as m
    lo, hi = 1e-3, 1e3
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if mid * (m.cosh(1.5 / mid) - 1) > 2.7 else (lo, mid)
    for x, drop in cs:
        assert drop == pytest.approx(lo * (m.cosh(x / lo) - 1), abs=1e-6)


def test_catenary_arches_shape_the_room():
    cfg = config.load("poolrooms", ["atmosphere.dust_count=0", "room.catenary=0.6", "room.nested_arch=null",
                                    "room.spring_height=2.0"])
    build_scene(cfg)
    w = cfg["room"]["back_arches"][1]
    cut = next(o for o in bpy.data.objects if o.name.startswith("ArchCut.back") and
               o.dimensions.x == pytest.approx(w, abs=1e-3))
    top = max((cut.matrix_world @ v.co).z for v in cut.data.vertices)
    assert top == pytest.approx(2.0 + 0.6 * w, abs=1e-3)


def test_catenary_shapes_the_bay_passage_arch_too():
    cfg = config.load("poolrooms", ["atmosphere.dust_count=0", "room.catenary=0.6"])
    build_scene(cfg)
    from wavegen.scene.util import arch_profile
    bw, bh = cfg["room"]["bay"]["width"] - 0.1, cfg["room"]["bay"]["height"]
    cut = bpy.data.objects["BayArchCut"]
    top = max((cut.matrix_world @ v.co).z for v in cut.data.vertices)
    assert top == pytest.approx(bh, abs=1e-3)                    # the crown stays where it was
    want = sorted(round(v, 3) for _, v in arch_profile(bw, bh - 0.6 * bw, catenary=0.6))
    got = sorted({round((cut.matrix_world @ v.co).z, 3) for v in cut.data.vertices})
    assert set(want) <= set(got)                                 # every height of the chain curve
