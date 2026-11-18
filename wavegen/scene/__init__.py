"""Blender scene construction. Importing this package requires ``bpy``
(either the ``bpy`` pip module or Blender's bundled Python)."""
from __future__ import annotations

from pathlib import Path


def build_scene(cfg: dict, blend_path: str | Path | None = None) -> dict:
    import bpy

    from . import architecture, atmosphere, camera, nature, props, render, screensaver

    emblem_images = None
    cc = cfg.get("computer", {})
    if cc.get("enabled", True):
        screensaver.check_mode(cfg)              # refuse an unknown mode before any slow work
    if cc.get("enabled", True) and cc.get("screensaver", "emblem") == "emblem":
        from .emblem import render_emblem
        emblem_images = render_emblem(cfg)       # cached; resets the session, so do it first

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.name = cfg["name"]
    render.configure(cfg)
    arch = architecture.build(cfg)
    pr = props.build(cfg, emblem_images)
    atmosphere.build(cfg, arch["bounds"])
    nature.build(cfg, arch["bounds"])
    focus = pr.get("icon") or pr.get("screen")
    cam = camera.build(cfg, focus)
    if blend_path:
        Path(blend_path).parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(blend_path).resolve()))
    return {"camera": cam, **arch, **pr}


def render_frames(out_dir: str | Path, cfg: dict, frames: list[int] | None = None,
                  overwrite: bool = False) -> list[Path]:
    """Render ``frames`` (``None`` = the whole loop, ``[]`` = nothing) as numbered images.

    Frames already on disk are reused only if the folder's manifest matches this
    config; otherwise :class:`wavegen.frames.StaleFramesError` is raised.
    """
    import bpy

    from ..frames import loop_frame_count, part_path, prepare_frames_dir, usable_frame

    sc = bpy.context.scene
    out_dir = Path(out_dir).resolve()
    prepare_frames_dir(out_dir, cfg, overwrite)
    if frames is None:
        frames = list(range(1, loop_frame_count(cfg) + 1))
    written = []
    ext = {"PNG": "png", "JPEG": "jpg", "OPEN_EXR": "exr"}.get(sc.render.image_settings.file_format, "png")
    for f in frames:
        path = out_dir / f"frame_{f:05d}.{ext}"
        if usable_frame(path):  # resumable: manifest already proved these match
            written.append(path)
            continue
        part = part_path(path)                  # an interrupted render never leaves a half-written frame
        sc.frame_set(f)
        sc.render.filepath = str(part)
        try:
            bpy.ops.render.render(write_still=True)
            part.replace(path)
        finally:
            part.unlink(missing_ok=True)
        written.append(path)
        print(f"[wavegen] frame {f} -> {path.name}", flush=True)
    return written
