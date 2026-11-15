"""Look-dev: compare a render against a reference frame.

Writes a side-by-side JPEG (each image scaled to 960 wide) and returns simple
numbers to steer by: dominant palettes, how far the reference's main colours
are from the render's, and brightness / contrast (mean / std of luminance).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from .analyze import _palette

W, H = 960, 540


def _load(path: Path) -> np.ndarray:
    """Decode to (H, W, 3) sRGB 0..1 at the comparison size."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={W}:{H}",
                          "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.float32) / 255


def _hex_rgb(h: str) -> np.ndarray:
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255


def _luma(a: np.ndarray) -> np.ndarray:
    return a @ np.array([0.2126, 0.7152, 0.0722], np.float32)


def palette_distance(pal_render: list[dict], pal_ref: list[dict], top: int = 5) -> float:
    """Mean distance from each of the reference's ``top`` colours to the nearest render colour."""
    ref = sorted(pal_ref, key=lambda p: -p["share"])[:top]
    ren = np.array([_hex_rgb(p["hex"]) for p in pal_render])
    return float(np.mean([np.linalg.norm(ren - _hex_rgb(p["hex"]), axis=1).min() for p in ref]))


def compare(render: Path, ref: Path, out: Path) -> dict:
    a, b = _load(render), _load(ref)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sbs = (np.concatenate([a, b], 1) * 255 + 0.5).astype(np.uint8)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{2 * W}x{H}",
                    "-i", "-", "-q:v", "3", str(out)], input=sbs.tobytes(), check=True)
    pa, pb = _palette(a), _palette(b)
    la, lb = _luma(a), _luma(b)
    return {"palette_render": pa, "palette_ref": pb, "palette_distance": round(palette_distance(pa, pb), 4),
            "brightness_render": float(la.mean()), "brightness_ref": float(lb.mean()),
            "contrast_render": float(la.std()), "contrast_ref": float(lb.std())}


def grade_still(src: Path, out: Path, cfg: dict) -> Path:
    """Apply the video's post grade (without temporal grain) to one still."""
    from . import post
    w, h = cfg["render"]["resolution"]
    pc = {**cfg["post"], "grain": 0}
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", post.filtergraph(pc, w, h),
                    "-map", "[vout]", "-pix_fmt", "rgb24", str(out)], check=True)
    return out
