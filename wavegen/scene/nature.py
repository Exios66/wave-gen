"""Natural features: sun through a skylight under a swaying leaf canopy.

Everything here is off by default (``cfg["nature"]``), so presets that do not ask
for it render exactly as before.
"""
from __future__ import annotations

import math

import bpy

from . import materials as M
from ..frames import loop_frame_count
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


def build(cfg: dict, bounds) -> None:
    nat = cfg.get("nature") or {}
    if nat.get("skylight", {}).get("enabled"):
        _skylight(cfg, bounds)
