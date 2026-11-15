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

BODY_W, BODY_D, BODY_H = 0.34, 0.36, 0.40
SCREEN = {"x": (-0.118, 0.118), "z": (0.185, 0.345), "bulge": 0.012}


def _parent(child, parent):
    child.parent = parent
    child.matrix_parent_inverse = Matrix.Identity(4)


def _body(col, mat):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.transform(Matrix.Diagonal((BODY_W, BODY_D, BODY_H, 1)) @ Matrix.Translation((0, 0, 0.5)))
    # taper the back like a CRT housing
    for v in bm.verts:
        if v.co.y > 0:
            v.co.x *= 0.82
            v.co.z = v.co.z * 0.86 + 0.01
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
                   col, M.plastic("DeskLaminate", pal["desk"], 0.3, 0.0))
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
    body = _body(col, beige)
    _parent(body, rig)
    (xa, xb), (za, zb) = SCREEN["x"], SCREEN["z"]
    m_in = 0.016                                        # glass -> recess edge
    recess = box("ScreenRecessCut", (xa - m_in, -BODY_D / 2 - 0.05, za - m_in),
                 (xb + m_in, -BODY_D / 2 + 0.04, zb + m_in), col)
    _parent(recess, rig)
    boolean_cut(body, recess)
    # shadow notch along the base so the unit sits on a recessed foot, not flat on the desk
    notch = box("BaseNotchCut", (-BODY_W / 2 - 0.05, -BODY_D / 2 - 0.05, -0.01),
                (BODY_W / 2 + 0.05, -BODY_D / 2 + 0.035, 0.014), col)
    _parent(notch, rig)
    boolean_cut(body, notch)
    bevel(body, 0.022, 4, 30)
    smooth_shade(body)

    # thick rounded frame standing proud around the glass (the "deep bezel" look)
    fy0 = -BODY_D / 2
    frame = box("Computer.bezel", (xa - m_in - 0.024, fy0 - 0.014, za - m_in - 0.024),
                (xb + m_in + 0.024, fy0 + 0.004, zb + m_in + 0.024), col, beige)
    _parent(frame, rig)
    hole = box("BezelHoleCut", (xa - m_in, fy0 - 0.05, za - m_in), (xb + m_in, fy0 + 0.05, zb + m_in), col)
    _parent(hole, rig)
    boolean_cut(frame, hole)
    bevel(frame, 0.009, 4, 30)
    smooth_shade(frame)

    screen_mat = M.crt_screen("CRT", pal["screen"], pal["screen_glow"], cc["screen_strength"], cc["scanlines"])
    screen, front_y = _screen(col, screen_mat)
    _parent(screen, rig)

    slot_mat = M.dark("SlotDark", (0.035, 0.032, 0.036), 0.75)
    fy = -BODY_D / 2
    slot = box("Computer.floppy", (0.03, fy - 0.004, 0.105), (0.135, fy + 0.004, 0.113), col, slot_mat)
    _parent(slot, rig)
    for i in range(11):  # front-left vent grille
        x = -0.148 + i * 0.0085
        v = box(f"Computer.vent.{i}", (x, fy - 0.003, 0.035), (x + 0.0045, fy + 0.004, 0.098), col, slot_mat)
        _parent(v, rig)
    led = box("Computer.led", (-0.03, fy - 0.003, 0.09), (-0.024, fy + 0.002, 0.096), col,
              M.emission("LED", (0.6, 1.0, 0.7), 3.0))
    _parent(led, rig)

    kb = box("Keyboard.base", (-0.235, -0.09, 0.0), (0.235, 0.09, 0.034), col, beige)
    bevel(kb, 0.01, 3)
    keys = _keys(col, M.plastic("KeyCaps", pal["key_cap"], 0.5, 0.02))
    _parent(keys, kb)
    keys.location = (0.0, 0.0, 0.030)
    kb_rig = bpy.data.objects.new("Keyboard.rig", None)
    col.objects.link(kb_rig)
    _parent(kb_rig, rig)
    kb_rig.location = (0.07, -0.42, 0.0)
    kb_rig.rotation_euler = (math.radians(4), 0, math.radians(-6))
    _parent(kb, kb_rig)

    from . import screensaver
    if cc.get("screensaver", "emblem") == "flower":
        out["icon"] = _icon(col, pal, rig, (0, front_y - 0.012, (za + zb) / 2), cc, cfg["render"]["fps"],
                            loop_frame_count(cfg))
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
