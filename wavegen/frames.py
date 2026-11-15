"""Frame bookkeeping: which frames make up the loop, which are selected, and
whether frames already on disk were rendered from the same scene config.

Pure Python (no bpy) so it is usable from the CLI, post and the cloud runner.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Bump whenever scene code changes what pixels a given config produces.
SCENE_VERSION = 2

_NON_PIXEL_KEYS = ("post", "audio")


class StaleFramesError(RuntimeError):
    """Frames on disk were rendered from a different config/scene version."""


def loop_frame_count(cfg: dict) -> int:
    rc = cfg["render"]
    return max(1, round(float(rc["seconds"]) * int(rc["fps"])))


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


def config_hash(cfg: dict) -> str:
    pixel_cfg = {k: v for k, v in cfg.items() if k not in _NON_PIXEL_KEYS}
    blob = json.dumps(pixel_cfg, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def manifest_for(cfg: dict) -> dict:
    return {"config_hash": config_hash(cfg), "scene_version": SCENE_VERSION, "n_frames": loop_frame_count(cfg)}


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
    existing = json.loads(mpath.read_text()) if mpath.exists() else None
    if overwrite:
        for p in frame_files(out_dir):
            p.unlink()
    else:
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
