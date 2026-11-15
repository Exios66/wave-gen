"""The poolroom: tiled floor, sunken pool, arched walls with lit alcoves,
stepped tray ceiling, a big rounded column.

World layout (Blender, Z up): the camera sits near y=-1 looking down +Y.
Interior spans x in [-W/2, W/2], y in [Y0, Y0 + D], floor at z = 0.
"""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix

from . import materials as M
from ..frames import loop_frame_count
from .util import (arch_profile, bevel, box, boolean_cut_collection, collection,
                   cutter_collection_union, extruded_profile, look_at_matrix, obj_from_bmesh, smooth_shade)

Y0 = -3.5


def _spread(total: float, widths: list[float]) -> list[float]:
    """Centres for openings of ``widths`` spaced with equal piers on a wall."""
    if not widths:
        return []                                    # a wall too short for any opening
    gap = (total - sum(widths)) / (len(widths) + 1)
    if gap < 0.6:
        raise ValueError(f"arches ({sum(widths):.1f} m) do not fit a {total:.1f} m wall")
    centres, x = [], -total / 2 + gap
    for w in widths:
        centres.append(x + w / 2)
        x += w + gap
    return centres


def _horseshoe(width: float, spring: float, band: float, segments: int = 24):
    """Outline of an arch-shaped band ``band`` wide around an opening (u, v)."""
    outer = arch_profile(width + 2 * band, spring, segments, bottom=0.0)
    inner = arch_profile(width, spring, segments, bottom=0.0)
    # outer goes CCW from bottom-left; walk it from bottom-right up and over, then the inner back
    o = [outer[1], outer[2], *outer[3:], outer[0]]          # (R,0) -> (R,s) -> arc -> (-R,s) -> (-R,0)
    i = [inner[0], inner[-1], *reversed(inner[3:-1]), inner[2], inner[1]]
    return o + i


def build(cfg: dict) -> dict:
    room, pool, pal = cfg["room"], cfg["pool"], cfg["palette"]
    W, D, H, T = room["width"], room["depth"], room["height"], room["wall_thickness"]
    Y1 = Y0 + D
    col = collection("Architecture")
    cut_col = collection("Cutters")

    mats = {
        "tile": M.tiles("Tile", pal["tile"], pal["grout"], room["tile_size"], room["grout_width"], pal["tile_jitter"]),
        "pool_tile": M.tiles("PoolTile", pal["pool_tile"], pal["grout"], room["tile_size"], room["grout_width"], 0.02, 0.08),
        "plaster": M.plaster("Plaster", pal["plaster"]),
        "ceiling": M.plaster("Ceiling", pal["ceiling"], 0.7),
        "water": M.water("Water", pal["water"], pal["water_absorb"], pool["wave_scale"],
                         pool["wave_strength"], pool["wave_cycles"], loop_frame_count(cfg)),
        "alcove": M.tiles("AlcoveTile", pal.get("alcove_tile", pal["tile"]), pal["grout"], room["tile_size"],
                          room["grout_width"], pal["tile_jitter"]),
        "sconce": M.emission("Sconce", pal["warm_light"], 30.0),
    }

    # ---- floor (flat tiled pieces around the pool hole) -------------------
    px0, px1 = pool["x"]
    py0, py1 = pool["y"]
    x0, x1 = -W / 2, W / 2
    for i, (mn, mx) in enumerate([
        ((x0, Y0), (px0, Y1)), ((px1, Y0), (x1, Y1)),
        ((px0, Y0), (px1, py0)), ((px0, py1), (px1, Y1)),
    ]):
        box(f"Floor.{i}", (mn[0], mn[1], -0.01), (mx[0], mx[1], 0.0), col, mats["tile"],
            skip=("-x", "+x", "-y", "+y", "-z"))

    # ---- pool basin, coping lip, water -------------------------------------
    depth = pool["depth"]
    box("PoolBasin", (px0, py0, -depth), (px1, py1, 0.0), col, mats["pool_tile"], inward=True, skip=("+z",))
    c = pool["coping"]
    lip_h = 0.05
    for i, (mn, mx) in enumerate([
        ((px0 - c, py0 - c), (px1 + c, py0)), ((px0 - c, py1), (px1 + c, py1 + c)),
        ((px0 - c, py0), (px0, py1)), ((px1, py0), (px1 + c, py1)),
    ]):
        lip = box(f"Coping.{i}", (mn[0], mn[1], 0.0), (mx[0], mx[1], lip_h), col, mats["tile"])
        bevel(lip, 0.018, 3)
    e = 0.004
    box("Water", (px0 + e, py0 + e, -depth + e), (px1 - e, py1 - e, pool["water_level"]), col, mats["water"])

    # ---- walls --------------------------------------------------------------
    walls = {
        "back": box("Wall.back", (x0 - T, Y1, 0), (x1 + T, Y1 + T, H), col, mats["plaster"]),
        "left": box("Wall.left", (x0 - T, Y0, 0), (x0, Y1, H), col, mats["plaster"]),
        "right": box("Wall.right", (x1, Y0, 0), (x1 + T, Y1, H), col, mats["plaster"]),
        "front": box("Wall.front", (x0 - T, Y0 - T, 0), (x1 + T, Y0, H), col, mats["plaster"]),
    }
    lights = []
    sw, sd = room["arch_surround"]["width"], room["arch_surround"]["depth"]

    def arch(wall: str, centre: float, width: float):
        spring = min(room["spring_height"], H - 0.6 - width / 2)
        top = spring + width / 2
        ad = room["alcove_depth"]
        if wall == "back":
            m = Matrix.Translation((centre, Y1 + T / 2, 0))
            alc = box(f"Alcove.back.{centre:.1f}", (centre - width / 2 - 0.35, Y1 + T - 0.01, 0),
                      (centre + width / 2 + 0.35, Y1 + T + ad, top + 0.45), col, mats["alcove"],
                      inward=True, skip=("-y",))
            lamp = (centre, Y1 + T + ad - 0.06, spring * 0.62)
            sconce_rot = (math.radians(90), 0, 0)
            face = Matrix.Translation((centre, Y1 - sd / 2 + 0.01, 0))
            into = (0, 1, 0)                      # from the room toward the alcove's back wall
        else:
            sign = -1 if wall == "left" else 1
            xw = (x0 - T / 2) if wall == "left" else (x1 + T / 2)
            m = Matrix.Translation((xw, centre, 0)) @ Matrix.Rotation(math.radians(90), 4, "Z")
            xa = x0 - T + 0.01 if wall == "left" else x1 + T - 0.01
            xb = xa + sign * ad
            alc = box(f"Alcove.{wall}.{centre:.1f}", (min(xa, xb), centre - width / 2 - 0.35, 0),
                      (max(xa, xb), centre + width / 2 + 0.35, top + 0.45), col, mats["alcove"],
                      inward=True, skip=("+x",) if wall == "left" else ("-x",))
            lamp = (xb - sign * 0.06, centre, spring * 0.62)
            sconce_rot = (math.radians(90), 0, math.radians(90))
            xf = x0 + sd / 2 - 0.01 if wall == "left" else x1 - sd / 2 + 0.01
            face = Matrix.Translation((xf, centre, 0)) @ Matrix.Rotation(math.radians(90), 4, "Z")
            into = (sign, 0, 0)
        cutter = extruded_profile(f"ArchCut.{wall}.{centre:.1f}", arch_profile(width, spring), T + 0.4, cut_col, m)
        # moulded reveal: a horseshoe band standing proud of the wall around the opening
        sur = extruded_profile(f"ArchSurround.{wall}.{centre:.1f}", _horseshoe(width, spring, sw), sd, col, face,
                               mats["plaster"])
        bevel(sur, min(0.035, sd * 0.3), 3, 30)
        # warm wall-washer: a small glowing dome + a soft point light in front
        if cfg["lights"]["sconces"]:
            bm = bmesh.new()
            bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=0.09)
            s = obj_from_bmesh(f"Sconce.{wall}.{centre:.1f}", bm, col, mats["sconce"], smooth=True)
            s.location = lamp
            s.rotation_euler = sconce_rot
            s.scale = (1, 1, 0.45)
        # wall-washer: a light just in front of the lamp, aimed back at the wall -> bright halo
        li = cfg["lights"]
        kind = li.get("alcove_type", "SPOT")
        L = bpy.data.lights.new(f"AlcoveLight.{wall}.{centre:.1f}", kind)
        L.energy = li["alcove_power"]
        L.color = pal["warm_light"]
        if kind == "SPOT":
            L.spot_size = math.radians(150)
            L.spot_blend = 1.0
            L.shadow_soft_size = li["alcove_radius"]
        else:
            L.shape = "DISK"
            L.size = 2 * li["alcove_radius"]
        lo = bpy.data.objects.new(L.name, L)
        lo.location = tuple(lamp[k] - into[k] * 0.55 for k in range(3))
        lo.rotation_euler = look_at_matrix(lo.location, lamp).to_euler()
        collection("Lights").objects.link(lo)
        lights.append(lo)
        # soft warm fill so the whole alcove glows gold, not just the halo
        F = bpy.data.lights.new(f"AlcoveFill.{wall}.{centre:.1f}", "POINT")
        F.energy = li.get("alcove_fill", 0.0)
        F.color = pal["warm_light"]
        F.shadow_soft_size = 0.6
        fo = bpy.data.objects.new(F.name, F)
        fo.location = tuple(lamp[k] - into[k] * (ad * 0.5) for k in range(2)) + (top * 0.75,)
        collection("Lights").objects.link(fo)
        return cutter

    back_cutters = [arch("back", cx, w) for cx, w in zip(_spread(W, room["back_arches"]), room["back_arches"])]
    side_span = D - 6.0
    side_cutters = {"left": [], "right": []}
    for wall in ("left", "right"):
        centres = _spread(side_span, room["side_arches"])
        for cy, w in zip(centres, room["side_arches"]):
            side_cutters[wall].append(arch(wall, Y0 + 3.0 + side_span / 2 + cy, w))

    for wall, cutters in (("back", back_cutters), ("left", side_cutters["left"]), ("right", side_cutters["right"])):
        if cutters:
            group = cutter_collection_union(f"Cut.{wall}", cutters, cut_col)
            boolean_cut_collection(walls[wall], group)
        bevel(walls[wall], room["bevel"], 4, 30)
    cut_col.hide_render = True

    # crown moulding: two stacked soft ledges where wall meets ceiling
    for i, (h, out) in enumerate([(0.18, 0.08), (0.10, 0.16)]):
        z0 = H - 0.18 - i * 0.12
        for name, mn, mx in [
            ("b", (x0, Y1 - out, z0), (x1, Y1, z0 + h)),
            ("l", (x0, Y0, z0), (x0 + out, Y1, z0 + h)),
            ("r", (x1 - out, Y0, z0), (x1, Y1, z0 + h)),
        ]:
            mo = box(f"Moulding.{i}.{name}", mn, mx, col, mats["plaster"])
            bevel(mo, 0.03, 3)

    # ---- stepped tray ceiling with a hidden cool cove light ------------------
    tray = room["ceiling_tray"]
    steps, sh = tray["steps"], tray["step_height"]
    slab = box("Ceiling", (x0 - T, Y0 - T, H), (x1 + T, Y1 + T, H + steps * sh + 0.3), col, mats["ceiling"])
    tray_cutters = []
    for i in range(steps):
        ins = tray["inset"] + i * 0.45
        tray_cutters.append(box(f"TrayCut.{i}", (x0 + ins, Y0 + ins + 1.0, H - 0.2),
                                (x1 - ins, Y1 - ins, H + (i + 1) * sh), cut_col))
    boolean_cut_collection(slab, cutter_collection_union("Cut.tray", tray_cutters, cut_col))
    bevel(slab, 0.03, 3, 30)
    ins = tray["inset"] + (steps - 1) * 0.45
    cove = bpy.data.lights.new("CoveLight", "AREA")
    cove.shape = "RECTANGLE"
    cove.size = (x1 - ins) - (x0 + ins) - 0.2
    cove.size_y = (Y1 - ins) - (Y0 + ins + 1.0) - 0.2
    cove.energy = cfg["lights"]["cove_power"]
    cove.color = pal["cool_light"]
    co = bpy.data.objects.new("CoveLight", cove)
    co.location = (0, (Y0 + ins + 1.0 + Y1 - ins) / 2, H + steps * sh - 0.02)
    co.visible_camera = False
    collection("Lights").objects.link(co)

    # ---- big rounded column, near left ---------------------------------------
    if room["column"]:
        (cx, cy), r = room.get("column_xy", (x0 + 1.25, Y0 + 4.6)), 0.5
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=r, radius2=r, depth=H,
                              matrix=Matrix.Translation((cx, cy, H / 2)))
        colm = obj_from_bmesh("Column", bm, col, mats["plaster"])
        smooth_shade(colm)
        for name, z, rr, hh in (("base", 0.12, r + 0.12, 0.24), ("cap", H - 0.45, r + 0.16, 0.3)):
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=rr, radius2=rr, depth=hh,
                                  matrix=Matrix.Translation((cx, cy, z)))
            ring = obj_from_bmesh(f"Column.{name}", bm, col, mats["plaster"])
            bevel(ring, 0.05, 4)
            smooth_shade(ring)

    return {"materials": mats, "lights": lights, "bounds": (x0, x1, Y0, Y1, H)}
