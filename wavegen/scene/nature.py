"""Natural features: sun through a skylight under a swaying leaf canopy, potted plants, tree columns, lily pads.

Everything here is off by default (``cfg["nature"]``), so presets that do not ask
for it render exactly as before.
"""
from __future__ import annotations

import math

import bpy

from . import materials as M
from ..frames import loop_frame_count
from ..layout import check_plants, check_tree_columns, reach_inside
from ..loop import circle_expr
from .util import box, collection, drive, look_at_matrix


def sun_direction(elevation: float, azimuth: float) -> tuple[float, float, float]:
    """Unit vector from the scene toward the sun. Azimuth 0 puts the sun behind the
    camera (-y), 180 beyond the far wall (+y), 90 to the right (+x)."""
    e, a = math.radians(elevation), math.radians(azimuth)
    return (math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))


def canopy_material(name, leaf, coverage, scale, sway, n_frames):
    """Leaves with sky between them: opaque where a noise field passes ``coverage``,
    transparent elsewhere, so the sun casts dappled light. The field drifts round a
    small circle once per loop, so the dapples sway and return exactly."""
    mat, nt, out = M._new(name)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.name = "sway"
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    for axis, idx in (("sin", 0), ("cos", 1)):
        drive(nt, 'nodes["sway"].inputs["Location"].default_value', circle_expr(sway, 1, n_frames, axis), idx)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 6.0
    noise.inputs["Roughness"].default_value = 0.62
    nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    # leaf-sized cells break the clusters into separate leaves and small sun-flecks
    fine = nt.nodes.new("ShaderNodeTexVoronoi")
    fine.feature = "F1"
    fine.inputs["Scale"].default_value = scale * 14.0
    nt.links.new(mapping.outputs["Vector"], fine.inputs["Vector"])
    leafy = M._math(nt, "MULTIPLY", fine.outputs["Distance"], value_b=0.35)
    field = M._math(nt, "SUBTRACT", noise.outputs["Fac"], leafy)
    edge = nt.nodes.new("ShaderNodeMapRange")       # a crisp leaf edge around the coverage threshold
    edge.inputs["From Min"].default_value = 0.88 - coverage - 0.02
    edge.inputs["From Max"].default_value = 0.88 - coverage + 0.02
    nt.links.new(field, edge.inputs["Value"])
    # leaves vary from deep to sunny green, and glow when the sun is behind them
    tint = nt.nodes.new("ShaderNodeTexNoise")
    tint.inputs["Scale"].default_value = scale * 3.0
    nt.links.new(mapping.outputs["Vector"], tint.inputs["Vector"])
    vary = nt.nodes.new("ShaderNodeMix")
    vary.data_type = "RGBA"
    vary.inputs["A"].default_value = M._rgb([c * 0.55 for c in leaf])
    vary.inputs["B"].default_value = M._rgb([min(1.0, c * 1.5 + 0.05) for c in leaf])
    nt.links.new(tint.outputs["Fac"], vary.inputs["Factor"])
    leaves = M.principled(nt, leaf, 0.5)
    nt.links.new(vary.outputs["Result"], leaves.inputs["Base Color"])
    glow = nt.nodes.new("ShaderNodeBsdfTranslucent")
    nt.links.new(vary.outputs["Result"], glow.inputs["Color"])
    leafy = nt.nodes.new("ShaderNodeMixShader")
    leafy.inputs["Fac"].default_value = 0.45
    nt.links.new(leaves.outputs[0], leafy.inputs[1])
    nt.links.new(glow.outputs[0], leafy.inputs[2])
    leaves = leafy
    clear = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(edge.outputs[0], mix.inputs["Fac"])
    nt.links.new(clear.outputs[0], mix.inputs[1])
    nt.links.new(leaves.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return mat


def _skylight(cfg: dict, bounds) -> None:
    sky, pal, room = cfg["nature"]["skylight"], cfg["palette"], cfg["room"]
    H = bounds[4]
    top = H + room["ceiling_tray"]["steps"] * room["ceiling_tray"]["step_height"] + 0.3
    (cx, cy), (w, d) = sky["center"], sky["size"]
    s = sun_direction(sky["sun_elevation"], sky["sun_azimuth"])
    cz = top + sky["canopy"]["height"]
    # the canopy sits up-sun of the opening, wide enough to shade every ray that reaches it
    lift = (cz - H) / max(math.tan(math.radians(sky["sun_elevation"])), 0.2)
    flat = math.hypot(s[0], s[1])
    ox, oy = (cx + s[0] / flat * lift, cy + s[1] / flat * lift) if flat > 1e-9 else (cx, cy)
    span = 2 * lift + 2 * max(w, d)
    col = collection("Nature")
    can = box("Canopy", (ox - span / 2, oy - span / 2, cz), (ox + span / 2, oy + span / 2, cz + 0.01), col,
              canopy_material("Canopy", pal["leaf"], sky["canopy"]["coverage"], sky["canopy"]["scale"],
                              sky["canopy"]["sway"], loop_frame_count(cfg)))
    can.visible_camera = True
    L = bpy.data.lights.new("Sun", "SUN")
    L.energy = sky["sun_strength"]
    L.color = pal["sun"]
    L.angle = math.radians(sky["sun_angle"])
    so = bpy.data.objects.new("Sun", L)
    so.location = (cx, cy, cz + 3.0)
    so.rotation_euler = look_at_matrix(so.location, tuple(so.location[k] - s[k] for k in range(3))).to_euler()
    collection("Lights").objects.link(so)




# ---- plants ----------------------------------------------------------------------

def leaf_material(name, leaf):
    """Waxy leaves that glow a little when lit from behind; large-scale colour variation."""
    mat, nt, out = M._new(name)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    tint = nt.nodes.new("ShaderNodeTexNoise")
    tint.inputs["Scale"].default_value = 3.0
    nt.links.new(coord.outputs["Object"], tint.inputs["Vector"])
    vary = nt.nodes.new("ShaderNodeMix")
    vary.data_type = "RGBA"
    vary.inputs["A"].default_value = M._rgb([c * 0.7 for c in leaf])
    vary.inputs["B"].default_value = M._rgb([min(1.0, c * 1.3 + 0.03) for c in leaf])
    nt.links.new(tint.outputs["Fac"], vary.inputs["Factor"])
    waxy = M.principled(nt, leaf, 0.38)
    waxy.inputs["Coat Weight"].default_value = 0.15
    nt.links.new(vary.outputs["Result"], waxy.inputs["Base Color"])
    glow = nt.nodes.new("ShaderNodeBsdfTranslucent")
    nt.links.new(vary.outputs["Result"], glow.inputs["Color"])
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = 0.3
    nt.links.new(waxy.outputs[0], mix.inputs[1])
    nt.links.new(glow.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return mat


def _frond(bm, base, heading: float, length: float, rise: float, droop: float,
           pairs: int, leaflet: float, width: float, rng, hang: float = 0.25) -> None:
    """One pinnate frond: a rachis arching out along ``heading`` (radians about Z), with
    ``pairs`` of tapered leaflets angled forward and down, longest mid-frond."""
    from mathutils import Vector
    h = Vector((math.cos(heading), math.sin(heading), 0.0))
    up = Vector((0, 0, 1))
    b = Vector(base)

    def at(t):
        return b + h * (length * t * math.cos(rise)) + up * (length * (t * math.sin(rise) - droop * t * t))

    side = h.cross(up).normalized()
    for i in range(1, pairs + 1):
        t = i / (pairs + 1)
        p, q = at(t), at(min(1.0, t + 0.02))
        tang = (q - p).normalized()
        ll = leaflet * math.sin(math.pi * t) ** 0.6 * rng.uniform(0.85, 1.1)
        for sgn in (-1, 1):
            d = (side * sgn * 0.85 + tang * 0.45 - up * rng.uniform(hang * 0.6, hang * 1.4)).normalized()
            n = tang.cross(d).normalized()
            tip, mid = p + d * ll, p + d * (ll * 0.45)
            w = ll * width
            fold = n * (w * 0.25)                  # a slight V along the leaflet's midrib
            vs = [bm.verts.new(v) for v in (p, mid + tang * w + fold, tip, mid - tang * w + fold)]
            bm.faces.new(vs)
    # the rachis: a thin strip under the leaflets
    prev = None
    for i in range(0, 13):
        t = i / 12
        p = at(t)
        a, c = bm.verts.new(p + side * 0.008), bm.verts.new(p - side * 0.008)
        if prev:
            bm.faces.new((prev[0], prev[1], c, a))
        prev = (a, c)


def _grow(kind: str, height: float, rng):
    """Foliage bmesh for one plant, origin at the soil, top scaled to ``height``."""
    import bmesh
    from mathutils import Matrix
    bm = bmesh.new()
    if kind == "palm":
        # an areca clump: a few slender canes, each crowned with arching fronds
        for c in range(rng.randint(3, 5)):
            ang = rng.uniform(0, 2 * math.pi)
            foot = (math.cos(ang) * rng.uniform(0.03, 0.09), math.sin(ang) * rng.uniform(0.03, 0.09), 0.0)
            lean = rng.uniform(0.08, 0.26)
            cane = rng.uniform(0.6, 1.0)
            top = (foot[0] + math.cos(ang) * math.sin(lean) * cane, foot[1] + math.sin(ang) * math.sin(lean) * cane,
                   math.cos(lean) * cane)
            ring = bmesh.ops.create_cone(bm, cap_ends=False, segments=6, radius1=0.016, radius2=0.009, depth=cane)
            bmesh.ops.transform(bm, verts=ring["verts"],
                                matrix=Matrix.Translation(((foot[0] + top[0]) / 2, (foot[1] + top[1]) / 2, top[2] / 2)) @
                                Matrix.Rotation(lean, 4, _lean_axis(ang)))
            for f in range(rng.randint(3, 5)):
                _frond(bm, top, ang + rng.uniform(-1.6, 1.6), rng.uniform(0.8, 1.15),
                       math.radians(rng.uniform(58, 82)), rng.uniform(0.85, 1.15),
                       pairs=rng.randint(24, 30), leaflet=0.3, width=0.055, rng=rng, hang=0.5)
    elif kind == "fern":
        # a Boston fern: many short fronds spilling out and over the pot rim
        for f in range(rng.randint(26, 32)):
            _frond(bm, (0, 0, 0.02), rng.uniform(0, 2 * math.pi), rng.uniform(0.45, 0.7),
                   math.radians(rng.uniform(25, 70)), rng.uniform(0.6, 1.0),
                   pairs=rng.randint(20, 26), leaflet=0.055, width=0.2, rng=rng)
    else:
        raise ValueError(f"unknown plant kind {kind!r} (have: palm, fern)")
    top = max(v.co.z for v in bm.verts)
    s = height / max(top, 1e-6)
    bmesh.ops.scale(bm, vec=(s, s, s), verts=bm.verts)
    return bm


def _lean_axis(angle: float):
    """Horizontal axis perpendicular to the direction ``angle``: tilting about it leans that way."""
    from mathutils import Vector
    return Vector((-math.sin(angle), math.cos(angle), 0.0))


def _plants(cfg: dict) -> None:
    import random

    import bmesh

    from ..loop import cycles_for, periodic_expr
    from .util import obj_from_bmesh
    pl, pal = cfg["nature"]["plants"], cfg["palette"]
    col = collection("Nature")
    leaves = leaf_material("Leaf", pal["leaf"])
    pot_mat = M.plastic("Planter", pal["planter"], roughness=0.3, sss=0.0, coat=0.4)
    soil = M.dark("Soil", (0.06, 0.045, 0.035), 0.9)
    n = loop_frame_count(cfg)
    cyc = cycles_for(pl["sway_period"], cfg["render"]["seconds"])
    r = pl["pot_radius"]
    check_plants(cfg)
    for i, (x, y, hgt) in enumerate(pl["spots"]):
        kind = pl["kinds"][i % len(pl["kinds"])]
        rng = random.Random(cfg["seed"] * 131 + i)
        pot_h = 0.5 if kind == "palm" else 0.42
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=r * 0.72, radius2=r, depth=pot_h)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, pot_h / 2))
        pot = obj_from_bmesh(f"Planter.{i}", bm, col, pot_mat, smooth=True)
        pot.location = (x, y, 0.0)
        bm = bmesh.new()
        bmesh.ops.create_circle(bm, cap_ends=True, segments=32, radius=r * 0.94)
        dirt = obj_from_bmesh(f"Soil.{i}", bm, col, soil)
        dirt.location = (x, y, pot_h - 0.04)
        plant = obj_from_bmesh(f"Plant.{i}", _grow(kind, hgt - pot_h + 0.04, rng), col, leaves)
        plant.location = (x, y, pot_h - 0.04)
        plant.rotation_euler.z = rng.uniform(0, 2 * math.pi)
        plant["kind"] = kind
        if pl["sway"] > 0:
            for axis in (0, 1):
                drive(plant, "rotation_euler",
                      periodic_expr(0.0, pl["sway"], cyc + axis, rng.uniform(0, 6.28), n), axis)


# ---- tree columns ------------------------------------------------------------------

def ceiling_z(cfg: dict, x: float, y: float) -> float:
    """Height of the ceiling's underside above (x, y): the flat ceiling, or the floor of
    the deepest tray step that covers the point."""
    from .architecture import Y0
    room = cfg["room"]
    W, D, H = room["width"], room["depth"], room["height"]
    t = room["ceiling_tray"]
    z = H
    for i in range(t["steps"]):
        ins = t["inset"] + i * 0.45
        if -W / 2 + ins < x < W / 2 - ins and Y0 + ins + 1.0 < y < Y0 + D - ins:
            z = H + (i + 1) * t["step_height"]
    return z


def _bezier(p0, p1, p2, n: int):
    return [tuple((1 - t) ** 2 * p0[k] + 2 * (1 - t) * t * p1[k] + t * t * p2[k] for k in range(3))
            for t in (i / n for i in range(n + 1))]


def _tube(bm, pts, radius) -> None:
    """A smooth tube through ``pts``; ``radius(t)`` gives the radius along it (t in 0..1)."""
    from mathutils import Vector
    rings, seg = [], 14
    for i, p in enumerate(pts):
        a, b = Vector(pts[max(i - 1, 0)]), Vector(pts[min(i + 1, len(pts) - 1)])
        tan = (b - a).normalized()
        ref = Vector((0, 0, 1)) if abs(tan.z) < 0.95 else Vector((1, 0, 0))
        u = ref.cross(tan).normalized()
        v = tan.cross(u)
        r = radius(i / (len(pts) - 1))
        rings.append([bm.verts.new(Vector(p) + (u * math.cos(2 * math.pi * j / seg) +
                                                v * math.sin(2 * math.pi * j / seg)) * r) for j in range(seg)])
    for r0, r1 in zip(rings, rings[1:]):
        for j in range(seg):
            bm.faces.new((r0[j], r0[(j + 1) % seg], r1[(j + 1) % seg], r1[j]))


def _tree_columns(cfg: dict) -> None:
    import random

    import bmesh

    from .util import obj_from_bmesh, smooth_shade
    tc, pal, room = cfg["nature"]["tree_columns"], cfg["palette"], cfg["room"]
    H = room["height"]
    col = collection("Nature")
    mat = M.plaster("TreeColumn", pal.get("column") or pal["plaster"])
    r0, reach = tc["trunk_radius"], tc["spread"]
    check_tree_columns(cfg)
    edge = r0 * 0.72 * 1.5 + 0.08              # the capital's flare, plus a little air before the wall
    for i, (x, y) in enumerate(tc["spots"]):
        rng = random.Random(cfg["seed"] * 977 + i)
        bm = bmesh.new()
        node = (x, y, tc["split"] * H)
        # the trunk, flaring a little at its foot
        _tube(bm, _bezier((x, y, 0.0), (x, y, node[2] / 2), node, 12),
              lambda t: r0 * (1.0 + 0.35 * (1 - t) ** 4 - 0.2 * t))
        joints = [(node, r0 * 0.8)]
        tips = []
        spin = rng.uniform(0, 2 * math.pi)
        r1 = r0 * 0.72
        for k in range(tc["branches"]):
            th = spin + 2 * math.pi * k / tc["branches"] + rng.uniform(-0.15, 0.15)
            lim = reach_inside(cfg, x, y, th, reach * 0.42, edge)        # a limb near a wall stays short
            mx, my = x + math.cos(th) * lim, y + math.sin(th) * lim
            mz = node[2] + (ceiling_z(cfg, mx, my) - node[2]) * 0.5
            mid = (mx, my, mz)
            _tube(bm, _bezier(node, (x + (mx - x) * 0.25, y + (my - y) * 0.25, (node[2] + mz) / 2), mid, 10),
                  lambda t: r0 * 0.8 + (r1 - r0 * 0.8) * t)
            joints.append((mid, r1))
            for fork in (-0.42, 0.42):
                a = th + fork + rng.uniform(-0.08, 0.08)
                far = reach_inside(cfg, x, y, a, reach, edge)
                tx, ty = x + math.cos(a) * far, y + math.sin(a) * far
                tip = (tx, ty, ceiling_z(cfg, tx, ty) + 0.05)
                ctrl = (mx + (tx - mx) * 0.3, my + (ty - my) * 0.3, mz + (tip[2] - mz) * 0.7)
                # thinning toward the ceiling, then spreading into a small capital where it meets it
                _tube(bm, _bezier(mid, ctrl, tip, 12),
                      lambda t: r1 * (1 - 0.35 * t) * (1 + 1.2 * max(0.0, t - 0.82) / 0.18))
                tips.append(tip)
        for p, r in joints:
            ball = bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=r)
            bmesh.ops.translate(bm, verts=ball["verts"], vec=p)
        obj = obj_from_bmesh(f"TreeColumn.{i}", bm, col, mat, smooth=True)
        smooth_shade(obj, 60.0)
        obj["tips"] = [v for t in tips for v in t]


# ---- lily pads ---------------------------------------------------------------------

def place_pads(cfg: dict, rng) -> list[tuple[float, float, float]]:
    """(x, y, radius) for each pad: loose clusters inside the pool, none overlapping."""
    lp, pool = cfg["nature"]["lily_pads"], cfg["pool"]
    (x0, x1), (y0, y1) = pool["x"], pool["y"]
    lo, hi = lp["size"]
    nw, nd = pool.get("notch") or (0.0, 0.0)
    m = hi + 0.1
    centres = [(rng.uniform(x0 + m, x1 - m), rng.uniform(y0 + m, y1 - m)) for _ in range(max(1, lp["clusters"]))]
    pads: list[tuple[float, float, float]] = []
    for _ in range(20000):
        if len(pads) == lp["count"]:
            return pads
        cx, cy = rng.choice(centres)
        r = rng.uniform(lo, hi)
        x, y = rng.gauss(cx, 1.1), rng.gauss(cy, 1.1)
        if not (x0 + r + 0.05 < x < x1 - r - 0.05 and y0 + r + 0.05 < y < y1 - r - 0.05):
            continue
        if nw and nd:                            # the notch's step is floor, not water
            qx, qy = min(max(x, x0), x0 + nw), min(max(y, y1 - nd), y1)
            if math.hypot(x - qx, y - qy) < r + 0.05:
                continue
        if all(math.hypot(x - px, y - py) >= r + pr + 0.02 for px, py, pr in pads):
            pads.append((x, y, r))
    raise ValueError(f"only {len(pads)} of {lp['count']} lily pads fit on the pool; ask for fewer or smaller")


def _pad_mesh(r: float):
    """A round pad with a V notch to its centre and a slightly upturned rim."""
    import bmesh
    bm = bmesh.new()
    notch, seg = 0.16, 30
    centre = bm.verts.new((0, 0, 0))
    inner, outer = [], []
    for k in range(seg + 1):
        a = notch + (2 * math.pi - 2 * notch) * k / seg
        inner.append(bm.verts.new((0.82 * r * math.cos(a), 0.82 * r * math.sin(a), 0.0015)))
        outer.append(bm.verts.new((r * math.cos(a), r * math.sin(a), 0.006)))
    for k in range(seg):
        bm.faces.new((centre, inner[k], inner[k + 1]))
        bm.faces.new((inner[k], outer[k], outer[k + 1], inner[k + 1]))
    return bm


def _flower_mesh(size: float):
    """Two rings of eight pointed petals opening upward."""
    import bmesh
    from mathutils import Vector
    bm = bmesh.new()
    for layer, (tilt, length, twist) in enumerate(((0.55, size, 0.0), (1.05, size * 0.8, math.pi / 8))):
        for k in range(8):
            a = twist + 2 * math.pi * k / 8
            out = Vector((math.cos(a) * math.cos(tilt), math.sin(a) * math.cos(tilt), math.sin(tilt)))
            side = Vector((-math.sin(a), math.cos(a), 0.0))
            base = Vector((0, 0, 0.004 * layer))
            w = length * 0.28
            pts = (base, base + out * (length * 0.45) + side * w, base + out * length,
                   base + out * (length * 0.45) - side * w)
            bm.faces.new([bm.verts.new(v) for v in pts])
    return bm


def _lily_pads(cfg: dict) -> None:
    import random

    import bmesh

    from ..loop import cycles_for, periodic_expr
    from .util import obj_from_bmesh
    lp, pal, pool = cfg["nature"]["lily_pads"], cfg["palette"], cfg["pool"]
    rng = random.Random(cfg["seed"] * 389 + 5)
    col = collection("Nature")
    pad_mat = leaf_material("LilyPad", pal["lily_pad"])
    petal = M.plastic("LilyPetal", pal["lily_flower"], roughness=0.45, sss=0.25)
    heart = M.emission("LilyHeart", (1.0, 0.82, 0.3), 0.6)
    n = loop_frame_count(cfg)
    cyc = cycles_for(7.0, cfg["render"]["seconds"])
    z0 = pool["water_level"] + 0.002
    for i, (x, y, r) in enumerate(place_pads(cfg, rng)):
        pad = obj_from_bmesh(f"LilyPad.{i}", _pad_mesh(r), col, pad_mat, smooth=True)
        pad.location = (x, y, z0)
        turn = rng.uniform(0, 2 * math.pi)
        pad.rotation_euler.z = turn
        pad["radius"] = r
        if lp["bob"] > 0:
            drive(pad, "location", periodic_expr(z0, lp["bob"], cyc, rng.uniform(0, 6.28), n), 2)
            drive(pad, "rotation_euler", periodic_expr(turn, 0.04, cyc, rng.uniform(0, 6.28), n), 2)
        if rng.random() < lp["flowers"]:
            f = obj_from_bmesh(f"LilyFlower.{i}", _flower_mesh(min(0.11, r * 0.45)), col, petal, smooth=True)
            f.parent = pad
            f.location = (r * 0.25, 0.0, 0.008)
            bm = bmesh.new()
            bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.018)
            c = obj_from_bmesh(f"LilyHeart.{i}", bm, col, heart, smooth=True)
            c.parent = f
            c.location = (0, 0, 0.012)


def build(cfg: dict, bounds) -> None:
    nat = cfg.get("nature") or {}
    if nat.get("skylight", {}).get("enabled"):
        _skylight(cfg, bounds)
    if nat.get("plants", {}).get("enabled"):
        _plants(cfg)
    if nat.get("tree_columns", {}).get("enabled"):
        _tree_columns(cfg)
    if nat.get("lily_pads", {}).get("enabled"):
        _lily_pads(cfg)
