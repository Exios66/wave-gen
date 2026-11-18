"""Small bpy/bmesh helpers shared by the scene builders."""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix, Vector


def collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)
    return col


def obj_from_bmesh(name: str, bm: bmesh.types.BMesh, col: bpy.types.Collection,
                   material=None, smooth: bool = False) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    if smooth:
        for p in mesh.polygons:
            p.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)
    if material is not None:
        mesh.materials.append(material)
    return obj


def box(name, mn, mx, col, material=None, inward=False, skip=()) -> bpy.types.Object:
    """Axis-aligned box from min/max corners.

    ``inward`` flips normals (a room shell). ``skip`` removes faces by side
    name: '-x', '+x', '-y', '+y', '-z', '+z' (used for open alcoves).
    """
    bm = bmesh.new()
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    v = [bm.verts.new(p) for p in [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]]
    faces = {
        "-z": (v[0], v[3], v[2], v[1]), "+z": (v[4], v[5], v[6], v[7]),
        "-y": (v[0], v[1], v[5], v[4]), "+y": (v[2], v[3], v[7], v[6]),
        "-x": (v[3], v[0], v[4], v[7]), "+x": (v[1], v[2], v[6], v[5]),
    }
    for side, f in faces.items():
        if side in skip:
            continue
        bm.faces.new(f)
    if inward:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    return obj_from_bmesh(name, bm, col, material)


def catenary_a(half: float, rise: float) -> float:
    """The ``a`` of the hanging chain ``y = a (cosh(x / a) - 1)`` that drops ``rise``
    over a half-span of ``half``."""
    lo, hi = half / 700.0, half * 1e4                  # the drop falls as a grows
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if mid * (math.cosh(half / mid) - 1) > rise else (lo, mid)
    return (lo + hi) / 2


def arch_profile(width: float, spring: float, segments: int = 24, bottom: float = -0.05,
                 corner_radius: float | None = None, catenary: float | None = None):
    """2D outline (u, v) of an arch opening, counter-clockwise.

    Round-topped by default. A ``corner_radius`` smaller than half the width gives a
    flat top with rounded corners (a basket-handle arch) that rises only ``corner_radius``
    above the spring line; a radius of zero or less gives a plain rectangle.
    ``catenary`` instead gives an inverted hanging chain, the shape Gaudi built with,
    rising ``catenary`` x ``width`` above the spring line.
    """
    r = width / 2
    pts = [(-r, bottom), (r, bottom), (r, spring)]
    if catenary:
        rise = catenary * width
        a = catenary_a(r, rise)
        for i in range(1, segments):
            u = r * math.cos(math.pi * i / segments)          # denser near the springs and the crown
            pts.append((u, spring + rise - a * (math.cosh(u / a) - 1)))
    elif corner_radius is None or corner_radius >= r:
        for i in range(1, segments):
            a = math.pi * i / segments
            pts.append((r * math.cos(a), spring + r * math.sin(a)))
    else:
        rc, cx = max(corner_radius, 0.0), r - max(corner_radius, 0.0)
        half = max(2, segments // 2) if rc > 0 else 0     # no radius: a plain rectangular top
        for i in range(1, half + 1):                      # right corner, up to the flat top
            a = math.pi / 2 * i / half
            pts.append((cx + rc * math.cos(a), spring + rc * math.sin(a)))
        for i in range(half):                             # left corner, down from the flat top
            a = math.pi / 2 + math.pi / 2 * i / half
            pts.append((-cx + rc * math.cos(a), spring + rc * math.sin(a)))
    pts.append((-r, spring))
    return pts


def extruded_profile(name, pts, depth, col, matrix: Matrix, material=None):
    """Extrude a 2D (u,v) outline along local +Y by ``depth`` (centered)."""
    bm = bmesh.new()
    verts = [bm.verts.new((u, -depth / 2, v)) for u, v in pts]
    face = bm.faces.new(verts)
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=moved, vec=(0, depth, 0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.transform(matrix)
    return obj_from_bmesh(name, bm, col, material)


def boolean_cut(target, cutter, solver="EXACT"):
    mod = target.modifiers.new(f"cut_{cutter.name}", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    mod.solver = solver
    cutter.hide_render = True
    cutter.hide_viewport = True
    cutter.display_type = "WIRE"
    return mod


def cutter_collection_union(name, cutters, col):
    """Group many cutters behind one boolean (faster than N modifiers)."""
    sub = bpy.data.collections.new(name)
    col.children.link(sub)
    for c in cutters:
        for uc in list(c.users_collection):
            uc.objects.unlink(c)
        sub.objects.link(c)
        c.hide_render = True
        c.hide_viewport = True
        c.display_type = "WIRE"
    sub.hide_render = True
    return sub


def boolean_cut_collection(target, cutter_col, solver="EXACT"):
    mod = target.modifiers.new(f"cut_{cutter_col.name}", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.operand_type = "COLLECTION"
    mod.collection = cutter_col
    mod.solver = solver
    return mod


def bevel(obj, width=0.03, segments=3, angle=40.0):
    mod = obj.modifiers.new("bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(angle)
    mod.harden_normals = False
    return mod


def smooth_shade(obj, angle=35.0):
    for p in obj.data.polygons:
        p.use_smooth = True
    try:  # 4.1+: smooth-by-angle is a modifier node group; fall back silently
        obj.data.set_sharp_from_angle(angle=math.radians(angle))
    except Exception:
        pass


def look_at_matrix(loc, target) -> Matrix:
    d = Vector(target) - Vector(loc)
    rot = d.to_track_quat("-Z", "Y")
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()


# --- drivers -------------------------------------------------------------
# Drivers using Blender's "simple expression" subset (frame, sin, cos, ...)
# evaluate without enabling Python auto-execution, so they are safe for
# headless renders and for sharing .blend files.

def drive(id_owner, data_path: str, expr: str, index: int = -1):
    fc = id_owner.driver_add(data_path, index) if index >= 0 else id_owner.driver_add(data_path)
    fc.driver.type = "SCRIPTED"
    fc.driver.expression = expr
    return fc
