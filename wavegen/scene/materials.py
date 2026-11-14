"""Procedural materials: grid tiles, plaster, water, beige plastic, CRT glass."""
from __future__ import annotations

import bpy

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
        line = _math(nt, "LESS_THAN", dist, grout * 0.5)
        n_abs = _math(nt, "ABSOLUTE", sep_n.outputs[axis])
        weight = _math(nt, "LESS_THAN", n_abs, 0.5)
        term = _math(nt, "MULTIPLY", line, weight)
        mask = term if mask is None else _math(nt, "MAXIMUM", mask, term)
    cell = nt.nodes.new("ShaderNodeVectorMath")
    cell.operation = "SNAP"
    nt.links.new(geo.outputs["Position"], cell.inputs[0])
    cell.inputs[1].default_value = (size, size, size)
    return mask, cell.outputs[0]


def tiles(name, color, grout_color, size, grout, jitter=0.03, roughness=0.12):
    mat, nt, out = _new(name)
    mask, cell = tile_grid(nt, size, grout)
    noise = nt.nodes.new("ShaderNodeTexWhiteNoise")
    noise.noise_dimensions = "3D"
    nt.links.new(cell, noise.inputs["Vector"])
    # per-tile brightness variation
    var = _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", noise.outputs["Value"], 0.5), jitter * 2)
    base = nt.nodes.new("ShaderNodeRGB")
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


def plastic(name, color, roughness=0.42, sss=0.05):
    """Aged beige ABS plastic: soft, slightly translucent, faint speckle."""
    mat, nt, out = _new(name)
    p = principled(nt, color, roughness)
    p.inputs["Subsurface Weight"].default_value = sss
    p.inputs["Subsurface Radius"].default_value = (0.02, 0.015, 0.01)
    p.inputs["Specular IOR Level"].default_value = 0.4
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


def dark(name, color=(0.05, 0.05, 0.06), roughness=0.6):
    mat, nt, out = _new(name)
    p = principled(nt, color, roughness)
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    return mat


def water(name, color, absorb, wave_scale, wave_strength, wave_speed, fps):
    """Transmissive water surface + absorption volume, waves animated by driver."""
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
    drive(nt, f'nodes["{noise.name}"].inputs["W"].default_value', f"frame*{wave_speed / fps:.6f}")
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = wave_strength
    bump.inputs["Distance"].default_value = 0.02
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs[0], p.inputs["Normal"])
    nt.links.new(p.outputs[0], out.inputs["Surface"])
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
    mix.data_type = "RGBA"
    nt.links.new(fall, mix.inputs["Factor"])
    mix.inputs["A"].default_value = _rgb(base)
    mix.inputs["B"].default_value = _rgb(glow)
    # scanlines
    lines = _math(nt, "SINE", _math(nt, "MULTIPLY", sep.outputs[1], scanlines * 3.14159))
    # brightness 0.65..1.0 across each line
    lines = _math(nt, "ADD", _math(nt, "MULTIPLY", _math(nt, "ABSOLUTE", lines), 0.35), 0.65)
    shade = nt.nodes.new("ShaderNodeMix")
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
