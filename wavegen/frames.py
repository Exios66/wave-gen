"""Frame bookkeeping: which frames make up the loop, which are selected, and
whether frames already on disk were rendered from the same scene config.

Pure Python (no bpy) so it is usable from the CLI, post and the cloud runner.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Bump whenever scene code changes what pixels a given config produces.
SCENE_VERSION = 4

_NON_PIXEL_KEYS = ("post", "audio")


class StaleFramesError(RuntimeError):
    """Frames on disk were rendered from a different config/scene version."""


def loop_fps(cfg: dict) -> int:
    """The frame rate as a whole number; video, audio and the frame count all share it."""
    fps = float(cfg["render"]["fps"])
    if not fps.is_integer() or fps < 1:
        raise ValueError(f"render.fps={cfg['render']['fps']!r} must be a positive whole number")
    return int(fps)


def loop_frame_count(cfg: dict) -> int:
    return max(1, round(float(cfg["render"]["seconds"]) * loop_fps(cfg)))


def parse_frames(spec: str | None, n: int) -> list[int] | None:
    """Parse ``"1-120"`` / ``"1,30,60"`` into sorted unique frames within 1..n.

    ``None`` means "all frames" and is returned unchanged.
    """
    if spec is None:
        return None
    out: set[int] = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, b = (int(x) for x in part.split("-", 1))
            else:
                a = b = int(part)
        except ValueError:
            raise ValueError(f"bad frame spec {part!r} (use e.g. 1-120 or 1,30,60)") from None
        if a > b:
            raise ValueError(f"reversed frame range {part!r}")
        if a < 1 or b > n:
            raise ValueError(f"frames {part!r} outside the loop's 1-{n}")
        out.update(range(a, b + 1))
    if not out:
        raise ValueError(f"frame spec {spec!r} selects no frames")
    return sorted(out)


def _drop_notes(node):
    """Remove ``_comment``-style keys at any depth: notes never change pixels."""
    if isinstance(node, dict):
        return {k: _drop_notes(v) for k, v in node.items() if not str(k).startswith("_")}
    if isinstance(node, list):
        return [_drop_notes(v) for v in node]
    return node


def config_hash(cfg: dict) -> str:
    pixel_cfg = _drop_notes({k: v for k, v in cfg.items() if k not in _NON_PIXEL_KEYS})
    blob = json.dumps(pixel_cfg, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def manifest_for(cfg: dict) -> dict:
    return {"config_hash": config_hash(cfg), "scene_version": SCENE_VERSION, "n_frames": loop_frame_count(cfg)}


def usable_frame(path: Path) -> bool:
    """A frame counts only if it exists and is not empty (an interrupted write leaves a 0-byte file)."""
    try:
        return Path(path).stat().st_size > 0
    except OSError:
        return False


def read_manifest(out_dir: Path) -> dict | None:
    mpath = Path(out_dir) / "manifest.json"
    return json.loads(mpath.read_text()) if mpath.exists() else None


def frame_files(out_dir: Path) -> list[Path]:
    return sorted(Path(out_dir).glob("frame_*.*"))


def check_manifest(existing: dict | None, cfg: dict, where: str = "") -> None:
    if not existing:
        return
    want = manifest_for(cfg)
    if any(existing.get(k) != want[k] for k in want):
        raise StaleFramesError(
            f"frames{(' in ' + where) if where else ''} were rendered from config "
            f"{existing.get('config_hash')} (scene v{existing.get('scene_version')}, "
            f"{existing.get('n_frames')} frames) but this run is {want['config_hash']} "
            f"(scene v{want['scene_version']}, {want['n_frames']} frames). "
            f"Use a new output folder or pass --overwrite.")


def prepare_frames_dir(out_dir: Path, cfg: dict, overwrite: bool) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mpath = out_dir / "manifest.json"
    if overwrite:
        for p in frame_files(out_dir):
            p.unlink()
    else:
        existing = read_manifest(out_dir)
        if existing is None and frame_files(out_dir):
            raise StaleFramesError(f"{out_dir} has frames but no manifest; pass --overwrite to replace them")
        check_manifest(existing, cfg, str(out_dir))
    mpath.write_text(json.dumps(manifest_for(cfg), indent=2))


def missing_frames(out_dir: Path, n: int) -> list[int]:
    have = set()
    for p in frame_files(out_dir):
        try:
            have.add(int(p.stem.split("_")[-1]))
        except ValueError:
            pass
    return [i for i in range(1, n + 1) if i not in have]
