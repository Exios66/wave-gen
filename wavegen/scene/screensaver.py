"""What plays on the CRT. Each mode composites onto the phosphor colour of the
``CRT`` material, before the scanlines, so scanlines, glow and glass sit on top.

Modes: ``emblem`` (the default: bouncing chrome WAVE GEN disc), ``starfield``,
``mystify`` and ``flower`` (the v1 spinning petals). Everything loops exactly.
"""
from __future__ import annotations

import bpy

from ..bounce import choose_trips, hits_expr, tri_expr
from ..frames import loop_frame_count
from .util import drive

SCREEN_ASPECT = 0.236 / 0.160          # props.SCREEN width / height
EMBLEM_ASPECT = 2.0                    # emblem.W / emblem.H


def _insert(nt, color_socket):
    """Route ``color_socket`` into the scanline stage in place of the bare phosphor."""
    nt.links.new(color_socket, nt.nodes["scanlines"].inputs["A"])


def _mix(nt, a, b, fac, name=None):
    m = nt.nodes.new("ShaderNodeMix")
    m.data_type = "RGBA"
    if name:
        m.name = name
    nt.links.new(fac, m.inputs["Factor"])
    for sock, v in (("A", a), ("B", b)):
        if isinstance(v, (tuple, list)):
            m.inputs[sock].default_value = (*v[:3], 1.0)
        else:
            nt.links.new(v, m.inputs[sock])
    return m.outputs["Result"]


def _ramp(nt, fac, colors, name):
    r = nt.nodes.new("ShaderNodeValToRGB")
    r.name = name
    cr = r.color_ramp
    cr.interpolation = "CONSTANT"
    p = len(colors)
    cr.elements[0].position, cr.elements[0].color = 0.0, (*colors[0], 1)
    cr.elements[1].position, cr.elements[1].color = 1 / p, (*colors[1 % p], 1)
    for i in range(2, p):
        cr.elements.new(i / p).color = (*colors[i], 1)
    nt.links.new(fac, r.inputs["Fac"])
    return r.outputs["Color"]


def emblem(cfg: dict, mat: bpy.types.Material, images: tuple) -> dict:
    """Bounce the emblem across the screen; the disc colour steps on each wall hit."""
    ec = cfg["computer"]["emblem"]
    nt = mat.node_tree
    n = loop_frame_count(cfg)
    fps = cfg["render"]["fps"]
    palette = ec["palette"]
    p = len(palette)

    sx = ec["scale"]
    sy = sx * SCREEN_ASPECT / EMBLEM_ASPECT
    m = ec["margin"]
    fx, fy = 1 - 2 * m - sx, 1 - 2 * m - sy           # free travel range
    if fx <= 0 or fy <= 0:
        raise ValueError("computer.emblem.scale/margin leave no room to bounce")
    tx, ty = choose_trips(n, fps, ec["speed"], p, span=fx)

    uv = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.name = "emblem_map"
    mp.vector_type = "POINT"
    mp.inputs["Scale"].default_value = (1 / sx, 1 / sy, 1)
    nt.links.new(uv.outputs["UV"], mp.inputs["Vector"])
    # emblem UV = (screen UV - offset) / size; offset = margin + free * triangle(frame)
    base = 'nodes["emblem_map"].inputs["Location"].default_value'
    drive(nt, base, f"-({m}+{fx:.6f}*({tri_expr(tx, n)}))/{sx:.6f}", 0)
    drive(nt, base, f"-({m}+{fy:.6f}*({tri_expr(ty, n)}))/{sy:.6f}", 1)

    text_img, mask_img = images
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.name = "emblem_text"
    tex.image = text_img
    tex.extension = "CLIP"
    tex.interpolation = "Cubic"
    nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
    msk = nt.nodes.new("ShaderNodeTexImage")
    msk.name = "emblem_mask"
    msk.image = mask_img
    mask_img.colorspace_settings.name = "Non-Color"
    msk.extension = "CLIP"
    nt.links.new(mp.outputs["Vector"], msk.inputs["Vector"])

    hits = nt.nodes.new("ShaderNodeValue")
    hits.name = "emblem_hits"
    drive(nt, 'nodes["emblem_hits"].outputs[0].default_value', hits_expr(tx, ty, n, p))
    idx = nt.nodes.new("ShaderNodeMath")
    idx.operation = "MULTIPLY_ADD"                     # (hits + 0.5) / p
    nt.links.new(hits.outputs[0], idx.inputs[0])
    idx.inputs[1].default_value = 1 / p
    idx.inputs[2].default_value = 0.5 / p
    top = _ramp(nt, idx.outputs[0], [c[0] for c in palette], "emblem_top")
    bottom = _ramp(nt, idx.outputs[0], [c[1] for c in palette], "emblem_bottom")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(mp.outputs["Vector"], sep.inputs[0])
    disc = _mix(nt, bottom, top, sep.outputs["Y"])
    phos = nt.nodes["phosphor"].outputs["Result"]
    with_disc = _mix(nt, phos, disc, msk.outputs["Color"])
    final = _mix(nt, with_disc, tex.outputs["Color"], tex.outputs["Alpha"], name="emblem_over")
    _insert(nt, final)
    return {"trips": (tx, ty)}


def build(cfg: dict, mat: bpy.types.Material, images: tuple | None = None) -> dict:
    mode = cfg["computer"].get("screensaver", "emblem")
    if mode == "emblem":
        if images is None:
            raise ValueError("emblem screensaver needs the rendered emblem images")
        return emblem(cfg, mat, images)
    if mode == "flower":
        return {}                                      # props builds the 3D petals
    raise ValueError(f"computer.screensaver={mode!r}; use emblem, starfield, mystify or flower")
