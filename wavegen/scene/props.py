"""Foreground props: white desk, generic beige all-in-one CRT computer,
keyboard, and the little tumbling pastel 'screensaver' icon.

The computer is a generic late-80s beige all-in-one silhouette (no logos or
branded details). Everything is parented to a rig empty so the whole
workstation can be moved/rotated from the preset.
"""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import materials as M
from ..frames import loop_frame_count
from ..loop import cycles_for, periodic_expr, spin_expr
from .util import bevel, box, boolean_cut, collection, drive, obj_from_bmesh, smooth_shade

BODY_W, BODY_D, BODY_H = 0.34, 0.36, 0.42        # BODY_H is the top of the monitor head above the desk
RECESS_D = 0.04                      # how far the screen recess cuts into the front face
SCREEN = {"x": (-0.118, 0.118), "z": (0.185, 0.345), "bulge": 0.02}   # where the reference frames it
FOOT = {"half_w": 0.14, "setback": 0.07, "h": 0.06}     # pedestal the head overhangs
HEAD_LIP = 0.075                     # height of the head's front bottom edge; its underside slopes back to the foot


def _parent(child, parent):
    child.parent = parent
    child.matrix_parent_inverse = Matrix.Identity(4)


def _body(col, mat, depth=BODY_D):
    """Monitor head. The front face stays at -BODY_D/2 whatever the depth; extra depth goes out the back.

    The underside slopes from the front lip down into the foot, so the head overhangs its pedestal."""
    if depth <= RECESS_D:
        raise ValueError(f"computer.depth {depth} must exceed the {RECESS_D} m screen recess")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.transform(Matrix.Diagonal((BODY_W, BODY_D, BODY_H, 1)) @ Matrix.Translation((0, 0, 0.5)))
    for v in bm.verts:
        low = v.co.z < BODY_H / 2
        if v.co.y > 0:                                  # taper the back like a CRT housing
            v.co.y = -BODY_D / 2 + depth
            v.co.x *= 0.82
            v.co.z = FOOT["h"] - 0.015 if low else BODY_H * 0.86 + 0.01
        elif low:
            v.co.z = HEAD_LIP
    return obj_from_bmesh("Computer.body", bm, col, mat)


def _screen(col, mat):
    nx, nz = 24, 18
    (xa, xb), (za, zb) = SCREEN["x"], SCREEN["z"]
    y_face = -BODY_D / 2 + 0.024
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    grid = []
    for j in range(nz + 1):
        row = []
        for i in range(nx + 1):
            u, v = i / nx, j / nz
            x, z = xa + (xb - xa) * u, za + (zb - za) * v
            bulge = SCREEN["bulge"] * (1 - (2 * u - 1) ** 2) * (1 - (2 * v - 1) ** 2)
            row.append(bm.verts.new((x, y_face - bulge, z)))
        grid.append(row)
    for j in range(nz):
        for i in range(nx):
            f = bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
            for loop, (du, dv) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
                loop[uv].uv = ((i + du) / nx, (j + dv) / nz)
    obj = obj_from_bmesh("Computer.screen", bm, col, mat, smooth=True)
    return obj, y_face - SCREEN["bulge"]


def _keys(col, mat, rows=5, cols=14, pitch=0.0255, size=0.021, h=0.011):
    bm = bmesh.new()
    x_start = -cols * pitch / 2 - 0.04
    for r in range(rows):
        stagger = (0, 0.006, 0.011, 0.017, 0)[r % 5]
        for c in range(cols):
            w = size
            if r == rows - 1 and 3 <= c <= 9:   # spacebar row
                if c != 3:
                    continue
                w = 7 * pitch - (pitch - size)
            cx = x_start + c * pitch + stagger + (w - size) / 2
            cy = -(r - rows / 2) * pitch
            ret = bmesh.ops.create_cube(bm, size=1.0)
            vs = ret["verts"]
            bmesh.ops.transform(bm, verts=vs, matrix=Matrix.Translation((cx, cy, h / 2)) @ Matrix.Diagonal((w, size, h, 1)))
            for v in vs:
                if v.co.z > h * 0.75:
                    v.co.x = cx + (v.co.x - cx) * (1 - 0.003 / w * 2)
                    v.co.y = cy + (v.co.y - cy) * 0.82
    # numeric pad
    for r in range(rows):
        for c in range(4):
            cx = cols * pitch / 2 - 0.02 + c * pitch
            cy = -(r - rows / 2) * pitch
            ret = bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.transform(bm, verts=ret["verts"], matrix=Matrix.Translation((cx, cy, h / 2)) @ Matrix.Diagonal((size, size, h, 1)))
    obj = obj_from_bmesh("Keyboard.keys", bm, col, mat)
    bevel(obj, 0.0025, 2, 60)
    return obj


def _icon(col, pal, parent, pivot_loc, cfg_c, fps, n_frames):
    """Six emissive petals that spin and tumble like an old 3D screensaver."""
    pivot = bpy.data.objects.new("Icon.pivot", None)
    pivot.empty_display_size = 0.02
    col.objects.link(pivot)
    _parent(pivot, parent)
    pivot.location = pivot_loc
    loop_s = n_frames / fps
    spin = cycles_for(cfg_c["icon_spin_period"], loop_s)
    tumble = cycles_for(cfg_c["icon_tumble_period"], loop_s)
    drive(pivot, "rotation_euler", spin_expr(spin, n_frames), 1)                     # around screen normal
    drive(pivot, "rotation_euler", periodic_expr(0.0, 1.2, tumble, 0.0, n_frames), 2)  # tumble left/right
    drive(pivot, "rotation_euler", periodic_expr(0.0, 0.67, max(1, round(tumble * 0.61)), 1.1, n_frames), 0)
    colors = pal["icon"]
    for i, c in enumerate(colors):
        mat = M.emission(f"IconPetal.{i}", c, 4.0)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=1.0)
        petal = obj_from_bmesh(f"Icon.petal.{i}", bm, col, mat, smooth=True)
        _parent(petal, pivot)
        a = 2 * math.pi * i / len(colors)
        petal.location = (0.0075 * math.cos(a), 0, 0.0075 * math.sin(a))
        petal.rotation_euler = (0, -a, 0)
        petal.scale = (0.0085, 0.0022, 0.0042)
    return pivot


def build(cfg: dict, emblem_images: tuple | None = None) -> dict:
    pal, cc, dc = cfg["palette"], cfg["computer"], cfg["desk"]
    col = collection("Props")
    out: dict = {}
    if dc["enabled"]:
        sx, sy, sz = dc["size"]
        cx, cy = dc["center"]
        desk = box("Desk", (cx - sx / 2, cy - sy / 2, dc["top"] - sz), (cx + sx / 2, cy + sy / 2, dc["top"]),
                   col, M.plastic("DeskLaminate", pal["desk"], dc["roughness"], 0.0, dc["coat"]))
        bevel(desk, 0.012, 3)
        # a single slab leg block so the desk doesn't float
        box("Desk.leg", (cx - sx / 2 + 0.05, cy - sy / 2 + 0.1, 0), (cx + sx / 2 - 0.05, cy + sy / 2 - 0.05, dc["top"] - sz),
            col, M.plastic("DeskBody", [v * 0.96 for v in pal["desk"]], 0.45, 0.0))
    if not cc["enabled"]:
        return out

    rig = bpy.data.objects.new("Computer.rig", None)
    col.objects.link(rig)
    rig.location = cc["location"]
    rig.rotation_euler = (0, 0, math.radians(cc["rotation_z"]))
    rig.scale = (cc["scale"],) * 3

    beige = M.plastic("BeigePlastic", pal["beige"])
    fy0 = -BODY_D / 2
    depth = cc.get("depth", BODY_D)
    # the head leans back about its front bottom edge; everything on it rides this empty
    head = bpy.data.objects.new("Computer.head", None)
    head.empty_display_size = 0.05
    col.objects.link(head)
    _parent(head, rig)
    pivot = Vector((0.0, fy0, HEAD_LIP))
    head.location = pivot
    head.rotation_euler = (-math.radians(cc.get("tilt", 0.0)), 0, 0)

    def on_head(o):
        o.parent = head
        o.matrix_parent_inverse = Matrix.Translation(-pivot)   # keep coordinates in the rig's frame

    body = _body(col, beige, depth)
    on_head(body)
    (xa, xb), (za, zb) = SCREEN["x"], SCREEN["z"]
    m_in = 0.016                                        # glass -> recess edge (hidden behind the bezel)
    recess = box("ScreenRecessCut", (xa - m_in, fy0 - 0.05, za - m_in),
                 (xb + m_in, fy0 + RECESS_D, zb + m_in), col)
    on_head(recess)
    boolean_cut(body, recess)
    bevel(body, 0.022, 4, 30)
    smooth_shade(body)

    # pedestal: narrower than the head and set back, so the head overhangs it as in the reference
    foot = box("Computer.foot", (-FOOT["half_w"], fy0 + FOOT["setback"], 0.0),
               (FOOT["half_w"], fy0 + max(depth - 0.04, FOOT["setback"] + 0.05), FOOT["h"]), col, beige)
    _parent(foot, rig)
    bevel(foot, 0.008, 3, 30)
    smooth_shade(foot)

    # bezel: a shallow frame whose rounded opening runs back to the glass
    lip = 0.003                                         # the opening overlaps the glass edge, so no gap shows
    frame = box("Computer.bezel", (xa - 0.036, fy0 - 0.008, za - 0.036),
                (xb + 0.036, fy0 + 0.024, zb + 0.036), col, beige)
    on_head(frame)
    hole = box("BezelHoleCut", (xa + lip, fy0 - 0.06, za + lip), (xb - lip, fy0 + 0.08, zb - lip), col)
    on_head(hole)
    bevel(hole, 0.022, 6)                               # rounded corners, like a CRT mask
    boolean_cut(frame, hole)
    bevel(frame, 0.007, 4, 30)
    smooth_shade(frame)

    screen_mat = M.crt_screen("CRT", pal["screen"], pal["screen_glow"], cc["screen_strength"], cc["scanlines"])
    screen, front_y = _screen(col, screen_mat)
    on_head(screen)

    slot_mat = M.dark("SlotDark", (0.035, 0.032, 0.036), 0.75)
    fx = -FOOT["half_w"]
    for i in range(10):  # cooling slots in the left side of the foot; the front stays plain
        y = fy0 + FOOT["setback"] + 0.03 + i * 0.0095
        v = box(f"Computer.sidevent.{i}", (fx - 0.002, y, 0.014), (fx + 0.004, y + 0.005, FOOT["h"] - 0.014),
                col, slot_mat)
        _parent(v, rig)

    kb = box("Keyboard.base", (-0.235, -0.09, 0.0), (0.235, 0.09, 0.034), col, beige)
    bevel(kb, 0.01, 3)
    keys = _keys(col, M.plastic("KeyCaps", pal["key_cap"], 0.5, 0.02))
    _parent(keys, kb)
    keys.location = (0.0, 0.0, 0.030)
    kb_rig = bpy.data.objects.new("Keyboard.rig", None)
    col.objects.link(kb_rig)
    _parent(kb_rig, rig)
    kb_tilt = math.radians(4)
    kc = cc["keyboard"]
    kx, ky = kc["offset"]
    kb_rig.location = (kx, ky, 0.09 * math.sin(kb_tilt) + 0.001)  # tilted up at the back; front edge rests on the desk
    kb_rig.rotation_euler = (kb_tilt, 0, math.radians(kc["yaw"]))
    _parent(kb, kb_rig)

    from . import screensaver
    if cc.get("screensaver", "emblem") == "flower":
        out["icon"] = _icon(col, pal, rig, (0, front_y - 0.012, (za + zb) / 2), cc, cfg["render"]["fps"],
                            loop_frame_count(cfg))
        out["icon"].parent = head
        out["icon"].matrix_parent_inverse = Matrix.Translation(-pivot)
    imgs = None
    if emblem_images:
        imgs = tuple(bpy.data.images.load(str(p), check_existing=True) for p in emblem_images)
        for img in imgs:                       # embed, so a saved .blend survives a cleared cache
            if img.packed_file is None:
                img.pack()
    out["screensaver"] = screensaver.build(cfg, screen_mat, imgs)
    out["screen"] = screen
    out["rig"] = rig
    return out
