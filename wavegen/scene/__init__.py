"""Blender scene construction. Importing this package requires ``bpy``
(either the ``bpy`` pip module or Blender's bundled Python)."""
from __future__ import annotations

from pathlib import Path


def build_scene(cfg: dict, blend_path: str | Path | None = None) -> dict:
    import bpy

    from . import architecture, atmosphere, camera, props, render

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.name = cfg["name"]
    render.configure(cfg)
    arch = architecture.build(cfg)
    pr = props.build(cfg)
    atmosphere.build(cfg, arch["bounds"])
    focus = pr.get("icon")
    cam = camera.build(cfg, focus)
    if blend_path:
        Path(blend_path).parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(blend_path).resolve()))
    return {"camera": cam, **arch, **pr}


def render_frames(out_dir: str | Path, frames: list[int] | None = None) -> list[Path]:
    """Render the given frames (default: the whole range) as numbered images."""
    import bpy

    sc = bpy.context.scene
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = frames or list(range(sc.frame_start, sc.frame_end + 1))
    written = []
    ext = {"PNG": "png", "JPEG": "jpg", "OPEN_EXR": "exr"}.get(sc.render.image_settings.file_format, "png")
    for f in frames:
        path = out_dir / f"frame_{f:05d}.{ext}"
        if path.exists():  # resumable: skip frames already on disk
            written.append(path)
            continue
        sc.frame_set(f)
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        written.append(path)
        print(f"[wavegen] frame {f} -> {path.name}", flush=True)
    return written
