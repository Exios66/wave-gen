"""The poolroom: tiled floor, sunken pool, arched walls with lit alcoves,
stepped tray ceiling, a rounded pier with a lit tiled passage beside it.

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
from ..layout import Y0
from .util import (arch_profile, bevel, box, boolean_cut_collection, collection,
                   cutter_collection_union, extruded_profile, look_at_matrix, obj_from_bmesh, smooth_shade)



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


def _alcove_pad(total: float, widths: list[float], pad: float = 0.35) -> float:
    """How far an alcove runs past each side of its opening: ``pad``, or less on narrow
    piers so neighbouring alcoves never overlap (overlapping faces render as speckle)."""
    if not widths:
        return pad
    gap = (total - sum(widths)) / (len(widths) + 1)
    return max(0.01, min(pad, gap / 2 - 0.005))


def _horseshoe(width: float, spring: float, band: float, segments: int = 24, corner_radius: float | None = None,
               catenary: float | None = None):
    """Outline of an arch-shaped band ``band`` wide around an opening (u, v)."""
    outer_r = None if corner_radius is None else corner_radius + band
    outer_c = None if not catenary else (catenary * width + band) / (width + 2 * band)
    outer = arch_profile(width + 2 * band, spring, segments, bottom=0.0, corner_radius=outer_r, catenary=outer_c)
    inner = arch_profile(width, spring, segments, bottom=0.0, corner_radius=corner_radius, catenary=catenary)
    # outer goes CCW from bottom-left; walk it from bottom-right up and over, then the inner back
    o = [outer[1], outer[2], *outer[3:], outer[0]]          # (R,0) -> (R,s) -> arc -> (-R,s) -> (-R,0)
    i = [inner[0], inner[-1], *reversed(inner[3:-1]), inner[2], inner[1]]
    return o + i


def _rise(width: float, room: dict) -> float:
    """How far an arch of ``width`` climbs above its spring line."""
    if room.get("catenary"):
        return room["catenary"] * width
    rc = room.get("arch_corner_radius")
    return width / 2 if rc is None else min(rc, width / 2)


def _pier_outline(width: float, depth: float, segments: int = 16) -> list[tuple[float, float]]:
    """Plan outline of a pier: square back (+y), semicircular front facing the camera (-y)."""
    r = width / 2
    if depth < r:
        raise ValueError(f"pier depth {depth} must be at least half its width ({r}) to fit the round front")
    cy = -depth / 2 + r
    front = [(r * math.cos(math.pi + math.pi * i / segments), cy - r * math.sin(math.pi * i / segments))
             for i in range(segments + 1)]                 # from (-r, cy) round the front to (r, cy)
    if depth / 2 - cy < 1e-9:  # minimum depth: the round front already ends on the back corners
        return front
    return front + [(r, depth / 2), (-r, depth / 2)]


def _prism(name, outline, z0, z1, col, material):
    """Vertical extrusion of a plan outline (local XY, counter-clockwise) between z0 and z1."""
    bm = bmesh.new()
    verts = [bm.verts.new((x, y, z0)) for x, y in outline]
    face = bm.faces.new(verts)
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(bm, verts=[v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)],
                        vec=(0, 0, z1 - z0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = obj_from_bmesh(name, bm, col, material)
    smooth_shade(obj)
    return obj


def _kerb_rects(px, py, c: float, nw: float = 0.0, nd: float = 0.0):
    """Plan rectangles ``((x0, y0), (x1, y1))`` of the kerb, ``c`` wide, around the water's edge.
    With a notch (``nw`` by ``nd`` in the far-left corner) the kerb steps in around it."""
    (px0, px1), (py0, py1) = px, py
    rects = [((px0 - c, py0 - c), (px1 + c, py0)), ((px1, py0), (px1 + c, py1))]
    if not (nw and nd):
        return rects + [((px0 - c, py1), (px1 + c, py1 + c)), ((px0 - c, py0), (px0, py1))]
    return rects + [
        ((px0 + nw, py1), (px1 + c, py1 + c)),                  # the far edge right of the step
        ((px0 + nw - c, py1 - nd), (px0 + nw, py1 + c)),        # the step's side
        ((px0 - c, py1 - nd), (px0 + nw - c, py1 - nd + c)),    # the step's near edge
        ((px0 - c, py0), (px0, py1 - nd)),                      # the left edge up to the step
    ]


def build(cfg: dict) -> dict:
    room, pool, pal = cfg["room"], cfg["pool"], cfg["palette"]
    W, D, H, T = room["width"], room["depth"], room["height"], room["wall_thickness"]
    Y1 = Y0 + D
    col = collection("Architecture")
    cut_col = collection("Cutters")

    mats = {
        "tile": M.tiles("Tile", pal["tile"], pal["grout"], room["tile_size"], room["grout_width"], pal["tile_jitter"]),
        "pool_tile": M.tiles("PoolTile", pal["pool_tile"], pal["grout"], room["tile_size"], room["grout_width"], 0.02, 0.08),
        "kerb_tile": M.tiles("KerbTile", pal["pool_tile"], pal["grout"], room["tile_size"], room["grout_width"], 0.02, 0.08),
        "floor": M.tiles("FloorTile", pal.get("floor_tile") or pal["tile"], pal["grout"], room["floor_tile_size"], room["grout_width"],
                         pal["tile_jitter"]),
        "plaster": M.plaster("Plaster", pal["plaster"]),
        "ceiling": M.plaster("Ceiling", pal["ceiling"], 0.7),
        "water": M.water("Water", pal["water"], pal["water_absorb"], pool["wave_scale"],
                         pool["wave_strength"], pool["wave_cycles"], loop_frame_count(cfg)),
        "alcove": M.wainscot("AlcoveTile", pal.get("alcove_tile", pal["tile"]), pal.get("alcove_grout", pal["grout"]),
                             pal.get("alcove_plaster", pal["plaster"]), room.get("alcove_tile_size") or room["tile_size"],
                             room["grout_width"],
                             room["alcove_wainscot"],
                             pal["tile_jitter"]),
        "sconce": M.emission("Sconce", pal["warm_light"], 30.0),
        "halo": M.halo("SconceHalo", pal["warm_light"], cfg["lights"].get("halo_strength", 4.0)),
    }

    ca = pool.get("caustics")
    if ca and ca["strength"] > 0:
        M.add_caustics(mats["pool_tile"], ca["color"], ca["scale"], ca["strength"], pool["wave_cycles"],
                       loop_frame_count(cfg))

    # ---- floor (flat tiled pieces around the pool hole) -------------------
    px0, px1 = pool["x"]
    py0, py1 = pool["y"]
    x0, x1 = -W / 2, W / 2
    for i, (mn, mx) in enumerate([
        ((x0, Y0), (px0, Y1)), ((px1, Y0), (x1, Y1)),
        ((px0, Y0), (px1, py0)), ((px0, py1), (px1, Y1)),
    ]):
        box(f"Floor.{i}", (mn[0], mn[1], -0.01), (mx[0], mx[1], 0.0), col, mats["floor"],
            skip=("-x", "+x", "-y", "+y", "-z"))

    # ---- pool basin, coping lip, water -------------------------------------
    depth = pool["depth"]
    box("PoolBasin", (px0, py0, -depth), (px1, py1, 0.0), col, mats["pool_tile"], inward=True, skip=("+z",))
    c = pool["coping"]
    kerb = pool["kerb"]
    nw, nd = pool["notch"] or (0.0, 0.0)
    if nw and nd:                               # a step filling the far-left corner, walkable on top
        box("PoolNotch", (px0, py1 - nd, -depth), (px0 + nw, py1, 0.0), col, mats["pool_tile"],
            skip=("-x", "+y", "-z", "+z"))
        box("Floor.notch", (px0, py1 - nd, -0.01), (px0 + nw, py1, 0.0), col, mats["floor"],
            skip=("-x", "+x", "-y", "+y", "-z"))
    for i, (mn, mx) in enumerate(_kerb_rects((px0, px1), (py0, py1), c, nw, nd)):
        lip = box(f"Coping.{i}", (mn[0], mn[1], 0.0), (mx[0], mx[1], kerb["height"]), col,
                  mats["kerb_tile"] if kerb["pool_tile"] else mats["tile"])
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

    def arch(wall: str, centre: float, width: float, pad: float = 0.35):
        rc = room.get("arch_corner_radius")               # None = round-topped; else a flat top with rounded corners
        cat = room.get("catenary")                        # or a hanging-chain arch
        rise = _rise(width, room)
        spring = min(room["spring_height"], H - 0.6 - rise)
        # sconces line up at one height in every alcove, whatever the arch width
        lamp_z = cfg["lights"]["alcove_height"] * room["spring_height"]
        top = spring + rise
        ad = room["alcove_depth"]
        off = width / 2 - 0.35                     # two sconces, one toward each side of the alcove
        if wall == "back":
            m = Matrix.Translation((centre, Y1 + T / 2, 0))
            alc = box(f"Alcove.back.{centre:.1f}", (centre - width / 2 - pad, Y1 + T - 0.01, 0),
                      (centre + width / 2 + pad, Y1 + T + ad, top + 0.45), col, mats["alcove"],
                      inward=True, skip=("-y",))
            lamps = [(centre + k, Y1 + T + ad - 0.06, lamp_z) for k in (-off, off)]
            sconce_rot = (math.radians(90), 0, 0)
            face = Matrix.Translation((centre, Y1 - sd / 2 + 0.01, 0))
            into = (0, 1, 0)                      # from the room toward the alcove's back wall
        else:
            sign = -1 if wall == "left" else 1
            xw = (x0 - T / 2) if wall == "left" else (x1 + T / 2)
            m = Matrix.Translation((xw, centre, 0)) @ Matrix.Rotation(math.radians(90), 4, "Z")
            xa = x0 - T + 0.01 if wall == "left" else x1 + T - 0.01
            xb = xa + sign * ad
            alc = box(f"Alcove.{wall}.{centre:.1f}", (min(xa, xb), centre - width / 2 - pad, 0),
                      (max(xa, xb), centre + width / 2 + pad, top + 0.45), col, mats["alcove"],
                      inward=True, skip=("+x",) if wall == "left" else ("-x",))
            lamps = [(xb - sign * 0.06, centre + k, lamp_z) for k in (-off, off)]
            sconce_rot = (math.radians(90), 0, math.radians(90))
            xf = x0 + sd / 2 - 0.01 if wall == "left" else x1 - sd / 2 + 0.01
            face = Matrix.Translation((xf, centre, 0)) @ Matrix.Rotation(math.radians(90), 4, "Z")
            into = (sign, 0, 0)
        cutter = extruded_profile(f"ArchCut.{wall}.{centre:.1f}", arch_profile(width, spring, corner_radius=rc, catenary=cat), T + 0.4, cut_col, m)
        # moulded reveal: a horseshoe band standing proud of the wall around the opening
        sur = extruded_profile(f"ArchSurround.{wall}.{centre:.1f}", _horseshoe(width, spring, sw, corner_radius=rc, catenary=cat), sd, col, face,
                               mats["plaster"])
        bevel(sur, min(0.035, sd * 0.3), 3, 30)
        # two warm wall-washers per alcove: a small glowing dome + a light just in front, aimed back at the wall
        li = cfg["lights"]
        kind = li.get("alcove_type", "SPOT")
        for tag, lamp in zip("ab", lamps):
            if li["sconces"]:
                bm = bmesh.new()
                bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=0.09)
                s = obj_from_bmesh(f"Sconce.{wall}.{centre:.1f}.{tag}", bm, col, mats["sconce"], smooth=True)
                s.location = lamp
                s.rotation_euler = sconce_rot
                s.scale = (1, 1, 0.45)
                if li.get("halo_radius", 0.0) > 0:
                    bm = bmesh.new()
                    bmesh.ops.create_circle(bm, cap_ends=True, segments=48, radius=1.0)
                    h = obj_from_bmesh(f"SconceHalo.{wall}.{centre:.1f}.{tag}", bm, col, mats["halo"])
                    h.location = tuple(lamp[k] + into[k] * 0.04 for k in range(3))   # between the lamp and its wall
                    h.rotation_euler = sconce_rot
                    h.scale = (li["halo_radius"], li["halo_radius"], 1)
                    h.visible_shadow = False
            L = bpy.data.lights.new(f"AlcoveLight.{wall}.{centre:.1f}.{tag}", kind)
            L.energy = li["alcove_power"] / 2
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
        fo.visible_glossy = fo.visible_transmission = False   # a fill, not a lamp: no glowing orb in or on the water
        mid = (sum(p[0] for p in lamps) / 2, sum(p[1] for p in lamps) / 2)
        fo.location = tuple(mid[k] - into[k] * (ad * 0.5) for k in range(2)) + (top * 0.75,)
        collection("Lights").objects.link(fo)
        return cutter

    back_pad = _alcove_pad(W, room["back_arches"])
    back_cutters = [arch("back", cx, w, back_pad) for cx, w in zip(_spread(W, room["back_arches"]), room["back_arches"])]
    na = room.get("nested_arch")
    if na:
        # a plaster screen across the alcove with a smaller arch in it, as in the clip's wide centre opening
        cx, w = _spread(W, room["back_arches"])[na["arch"]], room["back_arches"][na["arch"]]
        rc = room.get("arch_corner_radius")
        rise = _rise(w, room)
        spring = min(room["spring_height"], H - 0.6 - rise)
        iw, half = w - 2 * na["inset"], w / 2 + back_pad
        irc = None if rc is None else max(rc - na["inset"], 0.0)
        inner = arch_profile(iw, spring - na["drop"], bottom=0.0, corner_radius=irc,
                             catenary=room.get("catenary"))
        frame = [inner[1], (half, 0.0), (half, spring + rise + 0.45), (-half, spring + rise + 0.45), (-half, 0.0),
                 inner[0], *reversed(inner[2:])]
        th = na.get("thickness", 0.3)
        screen = extruded_profile(f"NestedArch.back.{cx:.1f}", frame, th, col,
                                  Matrix.Translation((cx, Y1 + T + na["depth"] + th / 2, 0)),
                                  M.plaster("NestedArchPlaster", na["color"]) if na.get("color") else mats["plaster"])
        bevel(screen, min(room["bevel"], th * 0.3), 3, 30)
    side_span = D - 6.0
    side_cutters = {"left": [], "right": []}
    for wall in ("left", "right"):
        centres = _spread(side_span, room["side_arches"])
        for cy, w in zip(centres, room["side_arches"]):
            side_cutters[wall].append(arch(wall, Y0 + 3.0 + side_span / 2 + cy, w, _alcove_pad(side_span, room["side_arches"])))

    for wall, cutters in (("back", back_cutters), ("left", side_cutters["left"]), ("right", side_cutters["right"])):
        if cutters:
            group = cutter_collection_union(f"Cut.{wall}", cutters, cut_col)
            boolean_cut_collection(walls[wall], group)
        bevel(walls[wall], room["bevel"], 4, 30)

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
    sky = cfg.get("nature", {}).get("skylight", {})
    if sky.get("enabled"):                         # an opening right through the slab, up to the canopy
        (sx, sy), (sw_, sd_) = sky["center"], sky["size"]
        tray_cutters.append(box("SkylightCut", (sx - sw_ / 2, sy - sd_ / 2, H - 0.3),
                                (sx + sw_ / 2, sy + sd_ / 2, H + steps * sh + 0.6), cut_col))
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

    # ---- small downlights in the flat ceiling over the right walkway ----------
    dl = cfg["lights"]["downlights"]
    if dl["count"] > 0:
        spot = M.emission("Downlight", pal["warm_light"], dl["strength"])
        spot.cycles.emission_sampling = "NONE"     # seen and reflected, but never sampled as a light
        a, b = dl["span"]
        for i in range(dl["count"]):
            t = a + (b - a) * (i + 0.5) / dl["count"]
            bm = bmesh.new()
            bmesh.ops.create_circle(bm, cap_ends=True, segments=24, radius=dl["radius"])
            d = obj_from_bmesh(f"Downlight.{i}", bm, col, spot)
            d.location = (x1 - tray["inset"] / 2, Y0 + D * t, H - 0.004)
            d.rotation_euler = (math.pi, 0, 0)          # face the floor
            d.visible_shadow = False

    # ---- pier behind the computer, and the lit tiled passage to its left -----
    if room["column"]:
        pr = room["pier"]
        (px, py), pw, pd = pr["xy"], pr["width"], pr["depth"]
        pier = _prism("Pier", _pier_outline(pw, pd), 0.0, H, col, mats["plaster"])
        pier.location = (px, py, 0.0)
        for name, z, grow, hh in (("base", 0.0, 0.1, 0.22), ("cap", H - 0.5, 0.14, 0.3)):
            ring = _prism(f"Pier.{name}", _pier_outline(pw + 2 * grow, pd + grow), z, z + hh, col, mats["plaster"])
            ring.location = (px, py + grow / 2, 0.0)
            bevel(ring, 0.04, 3)
        by = room["bay"]
        bw, bd, bh = by["width"], by["depth"], by["height"]
        bx1 = px - pw / 2                                    # the passage opens just left of the pier
        bay_mat = M.wainscot("BayTile", pal.get("alcove_tile", pal["tile"]), pal.get("alcove_grout", pal["grout"]),
                             pal["plaster"], room.get("alcove_tile_size") or room["tile_size"], room["grout_width"],
                             by["wainscot"])
        box("Bay", (bx1 - bw, py, 0.0), (bx1, py + bd, bh), col, bay_mat,
            inward=True, skip=("+x", "-y", "-z"))
        # plaster front wall through the pier's middle; the passage arch springs off the pier
        front = box("Bay.front", (bx1 - bw - 1.2, py - 0.15, 0.0), (bx1, py + 0.15, H), col, mats["plaster"])
        spring = bh - (bw - 0.1) / 2
        cut = extruded_profile("BayArchCut", arch_profile(bw - 0.1, spring), 0.7, cut_col,
                               Matrix.Translation((bx1 - bw / 2, py, 0.0)))
        boolean_cut_collection(front, cutter_collection_union("Cut.bay", [cut], cut_col))
        bevel(front, room["bevel"], 4, 30)
        BL = bpy.data.lights.new("BayLight", "AREA")
        BL.shape = "DISK"
        BL.size = 0.8
        BL.energy = cfg["lights"]["alcove_power"] * 0.8
        BL.color = pal["warm_light"]
        blo = bpy.data.objects.new("BayLight", BL)
        blo.visible_glossy = False                         # a soft fill: no glowing disc mirrored in the glossy tile
        blo.location = (bx1 - bw / 2, py + bd - 0.4, bh * 0.7)
        blo.rotation_euler = look_at_matrix(blo.location, (bx1 - bw / 2, py, bh * 0.5)).to_euler()
        collection("Lights").objects.link(blo)
        lights.append(blo)
        if by.get("sconce_power", 0.0) > 0:
            # a visible wall lamp on the passage's back wall, with a washer for its halo on the tile
            lamp = (bx1 - bw + bw * by.get("sconce_at", 0.5), py + bd - 0.06,
                    min(by.get("sconce_height") or cfg["lights"]["alcove_height"] * room["spring_height"], bh - 0.8))
            bm = bmesh.new()
            bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=0.09)
            dome = obj_from_bmesh("BaySconce", bm, col, mats["sconce"], smooth=True)
            dome.location, dome.rotation_euler, dome.scale = lamp, (math.radians(90), 0, 0), (1, 1, 0.45)
            SL = bpy.data.lights.new("BaySconceLight", "SPOT")
            SL.energy, SL.color = by["sconce_power"], pal["warm_light"]
            SL.spot_size, SL.spot_blend = math.radians(150), 1.0
            SL.shadow_soft_size = cfg["lights"]["alcove_radius"]
            so = bpy.data.objects.new("BaySconceLight", SL)
            so.location = (lamp[0], lamp[1] - 0.55, lamp[2])
            so.rotation_euler = look_at_matrix(so.location, lamp).to_euler()
            collection("Lights").objects.link(so)
            lights.append(so)

    cut_col.hide_render = True
    return {"materials": mats, "lights": lights, "bounds": (x0, x1, Y0, Y1, H)}
