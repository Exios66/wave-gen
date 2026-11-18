"""Procedural materials: grid tiles, plaster, water, beige plastic, CRT glass."""
from __future__ import annotations

import bpy

from ..loop import circle_expr
from .util import drive


def _new(name):
    mat = bpy.data.materials.get(name)
    if mat:
        bpy.data.materials.remove(mat)
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True  # always on in 5.x (deprecated), needed on 4.x
    except Exception:
        pass
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (900, 0)
    return mat, nt, out


def _math(nt, op, a=None, b=None, value_b=None, clamp=False):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    for i, src in enumerate((a, b)):
        if src is None:
            continue
        if isinstance(src, (int, float)):
            n.inputs[i].default_value = src
        else:
            nt.links.new(src, n.inputs[i])
    if value_b is not None:
        n.inputs[1].default_value = value_b
    return n.outputs[0]


def _rgb(c):
    return (c[0], c[1], c[2], 1.0)


def principled(nt, color, roughness=0.4, **extra):
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = _rgb(color)
    p.inputs["Roughness"].default_value = roughness
    for k, v in extra.items():
        key = k.replace("_", " ")
        if key in p.inputs:
            p.inputs[key].default_value = _rgb(v) if isinstance(v, (list, tuple)) else v
    return p


def tile_grid(nt, size: float, grout: float):
    """World-space square tile grid that works on any axis-aligned surface.

    Returns (grout_mask, cell_vector). For each axis we measure the distance to
    the nearest tile line, but only count axes lying in the surface plane
    (weighted by 1-|normal|), so walls, floors and pool sides all tile cleanly.
    """
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep_p = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep_n = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sep_p.inputs[0])
    nt.links.new(geo.outputs["Normal"], sep_n.inputs[0])
    mask = None
    for axis in range(3):
        p = sep_p.outputs[axis]
        u = _math(nt, "DIVIDE", p, size)
        f = _math(nt, "FRACT", u)
        edge = _math(nt, "MINIMUM", f, _math(nt, "SUBTRACT", 1.0, f))
        dist = _math(nt, "MULTIPLY", edge, size)            # metres to line
        # soft-edged line (anti-aliased, and gives the grout a rounded profile for the bump)
        line = nt.nodes.new("ShaderNodeMapRange")
        line.interpolation_type = "SMOOTHSTEP"
        nt.links.new(dist, line.inputs["Value"])
        line.inputs["From Min"].default_value = grout * 0.5 + grout * 0.25
        line.inputs["From Max"].default_value = grout * 0.5 - grout * 0.25
        line = line.outputs["Result"]
        n_abs = _math(nt, "ABSOLUTE", sep_n.outputs[axis])
        weight = _math(nt, "LESS_THAN", n_abs, 0.5)
        term = _math(nt, "MULTIPLY", line, weight)
        mask = term if mask is None else _math(nt, "MAXIMUM", mask, term)
    cell = nt.nodes.new("ShaderNodeVectorMath")
    cell.name = "tile_cell"
    cell.operation = "SNAP"
    nt.links.new(geo.outputs["Position"], cell.inputs[0])
    cell.inputs[1].default_value = (size, size, size)
    return mask, cell.outputs[0]


def hex_grid(nt, size: float, grout: float):
    """World-space honeycomb on horizontal surfaces (x, y), ``size`` flat-to-flat.

    Each point is matched to the nearer of two offset rectangular lattices of hexagon
    centres; its offset from that centre gives both the distance to the cell's edge
    (for the grout) and the cell itself (for per-tile variation). Returns
    (grout_mask, cell_vector) like :func:`tile_grid`.
    """
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    scale = nt.nodes.new("ShaderNodeMath")
    scale.name = "hex_scale"
    scale.operation = "DIVIDE"
    nt.links.new(sep.outputs[0], scale.inputs[0])
    scale.inputs[1].default_value = size
    # offset far from the origin so the truncating modulo never sees a negative value
    px = _math(nt, "ADD", scale.outputs[0], 1000.0)
    py = _math(nt, "ADD", _math(nt, "DIVIDE", sep.outputs[1], size), 1000.0 * 1.7320508)
    rx, ry = 1.0, 1.7320508

    def local(ox, oy):
        lx = _math(nt, "SUBTRACT", _math(nt, "MODULO", _math(nt, "SUBTRACT", px, ox), rx), rx / 2)
        ly = _math(nt, "SUBTRACT", _math(nt, "MODULO", _math(nt, "SUBTRACT", py, oy), ry), ry / 2)
        return lx, ly, _math(nt, "ADD", _math(nt, "MULTIPLY", lx, lx), _math(nt, "MULTIPLY", ly, ly))

    ax, ay, da = local(0.0, 0.0)
    bx, by, db = local(rx / 2, ry / 2)
    pick = _math(nt, "LESS_THAN", da, db)                      # 1 where lattice a's centre is nearer
    gx = _math(nt, "ADD", bx, _math(nt, "MULTIPLY", pick, _math(nt, "SUBTRACT", ax, bx)))
    gy = _math(nt, "ADD", by, _math(nt, "MULTIPLY", pick, _math(nt, "SUBTRACT", ay, by)))
    ux, uy = _math(nt, "ABSOLUTE", gx), _math(nt, "ABSOLUTE", gy)
    hexd = _math(nt, "MAXIMUM", ux, _math(nt, "ADD", _math(nt, "MULTIPLY", ux, 0.5), _math(nt, "MULTIPLY", uy, 0.8660254)))
    dist = _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", 0.5, hexd), size)     # metres to the cell's edge
    line = nt.nodes.new("ShaderNodeMapRange")
    line.interpolation_type = "SMOOTHSTEP"
    nt.links.new(dist, line.inputs["Value"])
    line.inputs["From Min"].default_value = grout * 0.5 + grout * 0.25
    line.inputs["From Max"].default_value = grout * 0.5 - grout * 0.25
    cell = nt.nodes.new("ShaderNodeCombineXYZ")
    cell.name = "hex_cell"
    nt.links.new(_math(nt, "SUBTRACT", px, gx), cell.inputs[0])
    nt.links.new(_math(nt, "SUBTRACT", py, gy), cell.inputs[1])
    return line.outputs["Result"], cell.outputs[0]


def tiles(name, color, grout_color, size, grout, jitter=0.03, roughness=0.12, pattern="square"):
    mat, nt, out = _new(name)
    if pattern not in ("square", "hex"):
        raise ValueError(f"unknown floor_pattern {pattern!r} (have: square, hex)")
    mask, cell = (hex_grid if pattern == "hex" else tile_grid)(nt, size, grout)
    noise = nt.nodes.new("ShaderNodeTexWhiteNoise")
    noise.noise_dimensions = "3D"
    nt.links.new(cell, noise.inputs["Vector"])
    # per-tile brightness variation
    var = _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", noise.outputs["Value"], 0.5), jitter * 2)
    base = nt.nodes.new("ShaderNodeRGB")
    base.name = "tile_base"
    base.outputs[0].default_value = _rgb(color)
    tint = nt.nodes.new("ShaderNodeMix")
    tint.data_type = "RGBA"
    tint.blend_type = "ADD"
    tint.inputs["Factor"].default_value = 1.0
    nt.links.new(base.outputs[0], tint.inputs["A"])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    for i in range(3):
        nt.links.new(var, comb.inputs[i])
    nt.links.new(comb.outputs[0], tint.inputs["B"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    nt.links.new(mask, mix.inputs["Factor"])
    nt.links.new(tint.outputs["Result"], mix.inputs["A"])
    mix.inputs["B"].default_value = _rgb(grout_color)
    p = principled(nt, color, roughness)
    nt.links.new(mix.outputs["Result"], p.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(mask, rough.inputs["Value"])
    rough.inputs["To Min"].default_value = roughness
    rough.inputs["To Max"].default_value = 0.7
    nt.links.new(rough.outputs[0], p.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.002
    nt.links.new(_math(nt, "SUBTRACT", 1.0, mask), bump.inputs["Height"])
    nt.links.new(bump.outputs[0], p.inputs["Normal"])
    p.inputs["Coat Weight"].default_value = 0.25
    p.inputs["Coat Roughness"].default_value = 0.05
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    return mat


def plaster(name, color, roughness=0.55):
    """Smooth painted plaster with very faint large-scale mottling."""
    mat, nt, out = _new(name)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.6
    noise.inputs["Detail"].default_value = 3.0
    ramp = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Value"])
    ramp.inputs["To Min"].default_value = 0.96
    ramp.inputs["To Max"].default_value = 1.03
    base = nt.nodes.new("ShaderNodeRGB")
    base.outputs[0].default_value = _rgb(color)
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(base.outputs[0], mul.inputs["A"])
    nt.links.new(ramp.outputs[0], mul.inputs["B"])
    p = principled(nt, color, roughness)
    nt.links.new(mul.outputs["Result"], p.inputs["Base Color"])
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    return mat


def wainscot(name, tile_color, grout_color, plaster_color, size, grout, height, jitter=0.03):
    """Tile below world height ``height``, painted plaster above (bathhouse wainscot)."""
    mat = tiles(name, tile_color, grout_color, size, grout, jitter)
    nt = mat.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    tile_bsdf = out.inputs["Surface"].links[0].from_socket
    top = principled(nt, plaster_color, 0.55)
    pos = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(pos.outputs["Position"], sep.inputs[0])
    above = _math(nt, "GREATER_THAN", sep.outputs["Z"], height)
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(above, mix.inputs["Fac"])
    nt.links.new(tile_bsdf, mix.inputs[1])
    nt.links.new(top.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return mat


def plastic(name, color, roughness=0.42, sss=0.05, coat=0.0):
    """Aged beige ABS plastic: soft, slightly translucent, faint speckle."""
    mat, nt, out = _new(name)
    p = principled(nt, color, roughness)
    p.inputs["Subsurface Weight"].default_value = sss
    p.inputs["Subsurface Radius"].default_value = (0.02, 0.015, 0.01)
    p.inputs["Specular IOR Level"].default_value = 0.4
    p.inputs["Coat Weight"].default_value = coat
    p.inputs["Coat Roughness"].default_value = 0.04
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 400.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.04
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs[0], p.inputs["Normal"])
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    return mat


def emission(name, color, strength=1.0):
    mat, nt, out = _new(name)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = _rgb(color)
    e.inputs["Strength"].default_value = strength
    nt.links.new(e.outputs[0], out.inputs["Surface"])
    return mat


def halo(name, color, strength=1.0, falloff=2.5):
    """Additive glow for a disc of unit radius: full at the centre, fading to nothing at the rim."""
    mat, nt, out = _new(name)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "SPHERICAL"
    nt.links.new(coord.outputs["Object"], grad.inputs["Vector"])
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = _rgb(color)
    nt.links.new(_math(nt, "MULTIPLY", _math(nt, "POWER", grad.outputs["Fac"], falloff), strength), e.inputs["Strength"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(nt.nodes.new("ShaderNodeBsdfTransparent").outputs[0], add.inputs[0])
    nt.links.new(e.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return mat


def dark(name, color=(0.05, 0.05, 0.06), roughness=0.6):
    mat, nt, out = _new(name)
    p = principled(nt, color, roughness)
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    return mat


def water(name, color, absorb, wave_scale, wave_strength, wave_cycles, n_frames):
    """Transmissive water surface + absorption volume.

    The ripples evolve by moving the 4D noise around a circle in its (W, z)
    plane, ``wave_cycles`` times per loop, so the water returns exactly to its
    first state at the loop point without visibly sliding sideways.
    """
    mat, nt, out = _new(name)
    p = principled(nt, color, 0.015)
    p.inputs["Transmission Weight"].default_value = 1.0
    p.inputs["IOR"].default_value = 1.333
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.name = "waves"
    noise.noise_dimensions = "4D"
    noise.inputs["Scale"].default_value = wave_scale
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.55
    radius = 0.6
    drive(nt, f'nodes["{noise.name}"].inputs["W"].default_value', circle_expr(radius, wave_cycles, n_frames, "cos"))
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.name = "waves_map"
    nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    drive(nt, 'nodes["waves_map"].inputs["Location"].default_value',
          circle_expr(radius / max(wave_scale, 1e-3), wave_cycles, n_frames, "sin"), 2)
    # fine wind ripples riding on the slow swell; twice the evolutions per loop, still whole cycles
    rip = nt.nodes.new("ShaderNodeTexNoise")
    rip.name = "ripples"
    rip.noise_dimensions = "4D"
    rip.inputs["Scale"].default_value = wave_scale * 6.0
    rip.inputs["Detail"].default_value = 2.0
    rip.inputs["Roughness"].default_value = 0.5
    nt.links.new(coord.outputs["Generated"], rip.inputs["Vector"])
    drive(nt, f'nodes["{rip.name}"].inputs["W"].default_value', circle_expr(0.4, 2 * wave_cycles, n_frames, "sin"))
    height = _math(nt, "ADD", noise.outputs["Fac"], _math(nt, "MULTIPLY", rip.outputs["Fac"], 0.3))
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = wave_strength
    bump.inputs["Distance"].default_value = 0.02
    nt.links.new(height, bump.inputs["Height"])
    nt.links.new(bump.outputs[0], p.inputs["Normal"])
    # Shadow rays pass straight through, so lamps light the tiled pool floor directly
    # (bright turquoise basin, visible tiles) without slow, noisy refractive caustics.
    lp = nt.nodes.new("ShaderNodeLightPath")
    clear = nt.nodes.new("ShaderNodeBsdfTransparent")
    clear.inputs["Color"].default_value = _rgb(absorb)
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Shadow Ray"], mix.inputs["Fac"])
    nt.links.new(p.outputs[0], mix.inputs[1])
    nt.links.new(clear.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    vol = nt.nodes.new("ShaderNodeVolumeAbsorption")
    vol.inputs["Color"].default_value = _rgb(absorb)
    vol.inputs["Density"].default_value = 0.35
    nt.links.new(vol.outputs[0], out.inputs["Volume"])
    try:  # Eevee: screen-space/raytraced refraction
        mat.surface_render_method = "DITHERED"
        mat.use_raytrace_refraction = True
    except Exception:
        pass
    return mat


def add_caustics(mat, color, scale, strength, cycles, n_frames):
    """Bright rippling light lines on a pool basin (cheap stand-in for refractive caustics).

    A 4D Voronoi edge pattern in world space whose W walks a circle ``cycles`` times per
    loop, so the pattern drifts and returns exactly to its first state at the loop point.
    """
    nt = mat.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.name = "caustics"
    vor.voronoi_dimensions = "4D"
    vor.feature = "DISTANCE_TO_EDGE"
    vor.inputs["Scale"].default_value = scale
    nt.links.new(geo.outputs["Position"], vor.inputs["Vector"])
    drive(nt, f'nodes["{vor.name}"].inputs["W"].default_value', circle_expr(0.5, cycles, n_frames, "cos"))
    edge = nt.nodes.new("ShaderNodeMapRange")              # thin bright lines along the cell edges
    nt.links.new(vor.outputs["Distance"], edge.inputs["Value"])
    edge.inputs["From Min"].default_value = 0.0
    edge.inputs["From Max"].default_value = 0.08
    edge.inputs["To Min"].default_value = 1.0
    edge.inputs["To Max"].default_value = 0.0
    lines = _math(nt, "POWER", edge.outputs[0], 2.0)
    p.inputs["Emission Color"].default_value = _rgb(color)
    nt.links.new(_math(nt, "MULTIPLY", lines, strength), p.inputs["Emission Strength"])
    return mat


def crt_screen(name, base, glow, strength, scanlines):
    """CRT phosphor: radial glow, scanlines, a little glass reflection."""
    mat, nt, out = _new(name)
    tex = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tex.outputs["UV"], sep.inputs[0])
    # radial falloff from screen centre (UV 0.5, 0.5)
    dx = _math(nt, "SUBTRACT", sep.outputs[0], 0.5)
    dy = _math(nt, "SUBTRACT", sep.outputs[1], 0.5)
    r = _math(nt, "SQRT", _math(nt, "ADD", _math(nt, "MULTIPLY", dx, dx), _math(nt, "MULTIPLY", dy, dy)))
    fall = _math(nt, "SUBTRACT", 1.0, _math(nt, "MULTIPLY", r, 1.35), clamp=True)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.name = "phosphor"          # screensavers composite on top of this
    mix.data_type = "RGBA"
    nt.links.new(fall, mix.inputs["Factor"])
    mix.inputs["A"].default_value = _rgb(base)
    mix.inputs["B"].default_value = _rgb(glow)
    # scanlines
    lines = _math(nt, "SINE", _math(nt, "MULTIPLY", sep.outputs[1], scanlines * 3.14159))
    # brightness 0.65..1.0 across each line
    lines = _math(nt, "ADD", _math(nt, "MULTIPLY", _math(nt, "ABSOLUTE", lines), 0.35), 0.65)
    shade = nt.nodes.new("ShaderNodeMix")
    shade.name = "scanlines"
    shade.data_type = "RGBA"
    shade.blend_type = "MULTIPLY"
    shade.inputs["Factor"].default_value = 1.0
    nt.links.new(mix.outputs["Result"], shade.inputs["A"])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    for i in range(3):
        nt.links.new(lines, comb.inputs[i])
    nt.links.new(comb.outputs[0], shade.inputs["B"])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(shade.outputs["Result"], em.inputs["Color"])
    em.inputs["Strength"].default_value = strength
    glass = nt.nodes.new("ShaderNodeBsdfGlossy")
    glass.inputs["Roughness"].default_value = 0.12
    fres = nt.nodes.new("ShaderNodeFresnel")
    fres.inputs["IOR"].default_value = 1.5
    add = nt.nodes.new("ShaderNodeMixShader")
    # keep the glass reflection subtle so the room doesn't wash the phosphor out
    nt.links.new(_math(nt, "MULTIPLY", fres.outputs[0], 0.3), add.inputs["Fac"])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(glass.outputs[0], add.inputs[2])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return mat


def volume_haze(name, color, density, anisotropy):
    mat, nt, out = _new(name)
    v = nt.nodes.new("ShaderNodeVolumePrincipled")
    v.inputs["Color"].default_value = _rgb(color)
    v.inputs["Density"].default_value = density
    v.inputs["Anisotropy"].default_value = anisotropy
    nt.links.new(v.outputs[0], out.inputs["Volume"])
    return mat
