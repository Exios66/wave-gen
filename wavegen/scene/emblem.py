"""The "WAVE GEN" screensaver emblem: chrome italic lettering over a sunset disc.

Rendered once with Blender into a cache folder (keyed by a hash of the emblem
settings), then used as an image texture on the CRT screen:

* ``emblem_<hash>.png``: RGBA chrome lettering (transparent background), 1024x512
* ``emblem_<hash>_mask.png``: greyscale disc mask (sun / triangle / orb), same frame

The disc is tinted in the screen shader so its colour can step on each bounce.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from pathlib import Path

import numpy as np

W, H = 1024, 512
EMBLEM_VERSION = 4


def cache_dir() -> Path:
    return Path(os.environ.get("WAVEGEN_CACHE", Path.home() / ".cache" / "wavegen")) / "emblem"


def _key(ec: dict) -> str:
    keep = {k: ec.get(k) for k in ("text", "shape", "font")}
    keep["v"] = EMBLEM_VERSION
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:12]


def disc_mask(shape: str, w: int = W, h: int = H, ss: int = 3) -> np.ndarray:
    """Anti-aliased mask (h, w) in 0..1 for the backing shape, centred in the frame."""
    ys, xs = np.mgrid[0:h * ss, 0:w * ss]
    x = (xs + 0.5) / ss - w / 2
    y = h / 2 - (ys + 0.5) / ss                 # +y up
    r = 0.44 * h
    if shape == "sun":
        m = (x * x + y * y) <= r * r
        # five horizontal slits through the lower half, thicker toward the bottom
        for i in range(5):
            yc = -r * (0.12 + 0.18 * i)
            half = r * (0.018 + 0.012 * i)
            m &= ~((y > yc - half) & (y < yc + half))
    elif shape == "triangle":
        top, base = r * 1.05, -r * 0.8
        m = (y >= base) & (y <= top) & (np.abs(x) <= (top - y) / (top - base) * r * 1.1)
    elif shape == "orb":
        d = np.sqrt(x * x + y * y) / r
        m = np.clip((1.0 - d) * 6, 0, 1) * (0.55 + 0.45 * np.clip(1 - d, 0, 1))
    else:
        raise ValueError(f"computer.emblem.shape={shape!r}; use sun, triangle or orb")
    m = np.asarray(m, np.float32)
    return m.reshape(h, ss, w, ss).mean((1, 3))


def _save_grey(path: Path, a: np.ndarray) -> None:
    import bpy
    h, w = a.shape
    img = bpy.data.images.new(path.stem, w, h, alpha=False, float_buffer=False)
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :3] = a[::-1, :, None]            # Blender images are stored bottom-up
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def _render_text(ec: dict, path: Path) -> None:
    """Chrome lettering, lit only by an 80s 'sunset horizon' environment."""
    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.render.film_transparent = True
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"

    curve = bpy.data.curves.new("EmblemText", "FONT")
    curve.body = ec.get("text", "WAVE GEN")
    if ec.get("font"):
        curve.font = bpy.data.fonts.load(ec["font"])  # else Blender's built-in font
    curve.align_x, curve.align_y = "CENTER", "CENTER"
    curve.shear = 0.28                               # italic
    curve.size = 1.0
    curve.extrude = 0.07
    curve.bevel_depth = 0.022
    curve.bevel_resolution = 4
    curve.space_character = 1.06
    txt = bpy.data.objects.new("EmblemText", curve)
    sc.collection.objects.link(txt)
    txt.rotation_euler = (math.radians(90), 0, 0)    # face -Y (the camera)

    mat = bpy.data.materials.new("Chrome")
    nt = mat.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.95, 0.95, 1.0, 1)
    p.inputs["Metallic"].default_value = 1.0
    p.inputs["Roughness"].default_value = 0.07
    # Classic airbrushed chrome on the letter faces: sky -> bright horizon line ->
    # warm ground across the letter height. Bevels keep real metallic reflections.
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sepz = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Generated"], sepz.inputs[0])
    face = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(sepz.outputs["Y"], face.inputs[0])   # text is upright in its local XY
    fr = face.color_ramp
    # violet ground -> pink near the horizon, dark horizon line, white flash, cyan sky -> violet-blue
    fstops = [(0.0, (0.42, 0.16, 0.78)), (0.40, (1.0, 0.62, 0.92)), (0.47, (0.16, 0.05, 0.30)),
              (0.53, (1.0, 1.0, 1.0)), (0.75, (0.50, 0.85, 1.0)), (1.0, (0.30, 0.25, 0.85))]
    fr.elements[0].position, fr.elements[0].color = fstops[0][0], (*fstops[0][1], 1)
    fr.elements[1].position, fr.elements[1].color = fstops[-1][0], (*fstops[-1][1], 1)
    for pos, c in fstops[1:-1]:
        fr.elements.new(pos).color = (*c, 1)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(face.outputs["Color"], em.inputs["Color"])
    em.inputs["Strength"].default_value = 1.0
    facing = nt.nodes.new("ShaderNodeLayerWeight")
    facing.inputs["Blend"].default_value = 0.15
    mixs = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(facing.outputs["Facing"], mixs.inputs["Fac"])
    nt.links.new(em.outputs[0], mixs.inputs[1])
    nt.links.new(p.outputs[0], mixs.inputs[2])
    nt.links.new(mixs.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    curve.materials.append(mat)

    world = bpy.data.worlds.new("Horizon")
    sc.world = world
    wn = world.node_tree.nodes
    bg = wn["Background"]
    coord = wn.new("ShaderNodeTexCoord")
    sep = wn.new("ShaderNodeSeparateXYZ")
    ramp = wn.new("ShaderNodeValToRGB")
    world.node_tree.links.new(coord.outputs["Generated"], sep.inputs[0])
    world.node_tree.links.new(sep.outputs["Z"], ramp.inputs[0])
    world.node_tree.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.6
    cr = ramp.color_ramp
    stops = [(0.0, (0.10, 0.02, 0.18)), (0.47, (0.55, 0.12, 0.45)), (0.5, (1.0, 0.92, 0.98)),
             (0.53, (0.35, 0.75, 1.0)), (1.0, (0.05, 0.10, 0.45))]
    cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1)
    cr.elements[1].position, cr.elements[1].color = stops[-1][0], (*stops[-1][1], 1)
    for pos, c in stops[1:-1]:
        e = cr.elements.new(pos)
        e.color = (*c, 1)

    cam_data = bpy.data.cameras.new("EmblemCam")
    cam_data.type = "ORTHO"
    bpy.context.view_layer.update()
    dims = txt.dimensions
    cam_data.ortho_scale = max(dims.x * 1.16, dims.y * 2 * 2.2)
    cam = bpy.data.objects.new("EmblemCam", cam_data)
    sc.collection.objects.link(cam)
    cam.location = (0, -10, 0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    sc.camera = cam
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def _dilate(a: np.ndarray, r: int) -> np.ndarray:
    out = a.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                out = np.maximum(out, np.roll(np.roll(a, dy, 0), dx, 1))
    return out


def _outline(path: Path, color=(0.04, 0.03, 0.16), width: int = 5, shadow=(7, -7)) -> None:
    """Give the lettering a dark outline + drop shadow so it reads on any disc colour."""
    import bpy
    img = bpy.data.images.load(str(path))
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    a = px[..., 3]
    ring = _dilate(a, width)
    shad = np.roll(np.roll(ring, shadow[1], 0), shadow[0], 1) * 0.6
    under_a = np.maximum(ring, shad)
    out = np.empty_like(px)
    out[..., 3] = a + under_a * (1 - a)
    rgb_under = np.array(color, np.float32)
    out[..., :3] = (px[..., :3] * a[..., None] + rgb_under * (under_a * (1 - a))[..., None]) / \
        np.maximum(out[..., 3:4], 1e-6)
    img.pixels.foreach_set(out.ravel())
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def render_emblem(cfg: dict, cache: Path | None = None) -> tuple[Path, Path]:
    """Return ``(lettering_png, mask_png)``, rendering them only if not cached.

    Resets the Blender session (call it before building the main scene).
    """
    ec = cfg["computer"]["emblem"]
    cache = Path(cache) if cache else cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    key = _key(ec)
    text_png, mask_png = cache / f"emblem_{key}.png", cache / f"emblem_{key}_mask.png"
    tag = f"{os.getpid()}.{uuid.uuid4().hex[:8]}"        # per-writer temp names: concurrent renders are safe
    if not text_png.exists():
        tmp = text_png.with_name(f"{text_png.stem}.{tag}.tmp.png")
        try:
            _render_text(ec, tmp)
            _outline(tmp)
            tmp.replace(text_png)                         # atomic publish
        finally:
            tmp.unlink(missing_ok=True)
    if not mask_png.exists():
        tmp = mask_png.with_name(f"{mask_png.stem}.{tag}.tmp.png")
        try:
            _save_grey(tmp, disc_mask(ec.get("shape", "sun")))
            tmp.replace(mask_png)
        finally:
            tmp.unlink(missing_ok=True)
    return text_png, mask_png
