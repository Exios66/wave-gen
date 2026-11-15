"""Autoresearch eval: render a preset's look and score it against reference frames.

    .venv/bin/python autoresearch/eval.py                       # target "poolrooms"
    .venv/bin/python autoresearch/eval.py --target poolrooms --device GPU

Prints ``SCORE: X.XXXX`` (higher is better, 0..1) plus guard lines. Targets live in
``autoresearch/targets.json``: preset file, reference frames, frame to render.

Deterministic: Cycles runs with a fixed seed, so the same preset gives the same score.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wavegen import config, lookdev  # noqa: E402
from wavegen.analyze import _palette  # noqa: E402

HERE = Path(__file__).resolve().parent
EVAL_SETS = ["render.resolution=[480,270]", "render.percentage=100", "render.samples=24"]
WEIGHTS = {"palette": 0.25, "histogram": 0.20, "layout": 0.20, "detail": 0.15,
           "brightness": 0.10, "contrast": 0.10}
FREE_KEYS = {"name", "_comment"}


# ---------- metrics (pure numpy; tested in tests/test_autoresearch_metrics.py) ----------

def crop_dark_border(a: np.ndarray, thresh: float = 0.08) -> np.ndarray:
    """Drop near-black rows/columns at the edges (a TV bezel in the reference)."""
    l = lookdev._luma(a)
    rows = np.where(l.mean(1) > thresh)[0]
    cols = np.where(l.mean(0) > thresh)[0]
    if len(rows) < a.shape[0] // 2 or len(cols) < a.shape[1] // 2:
        return a
    return a[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]


def _resize(a: np.ndarray, w: int, h: int) -> np.ndarray:
    """Area-average when shrinking (no aliasing from skipped pixels); nearest sample when enlarging."""
    if a.shape[:2] == (h, w):
        return a
    for axis, n in ((0, h), (1, w)):
        size = a.shape[axis]
        if n < size:
            edges = np.arange(n + 1) * size // n
            sums = np.add.reduceat(a, edges[:-1], axis=axis)
            shape = [1] * a.ndim
            shape[axis] = n
            a = sums / np.diff(edges).reshape(shape)
        elif n > size:
            a = np.take(a, (np.arange(n) * size / n).astype(int), axis=axis)
    return a


def sbs_path(out_dir: Path, target: str, i: int) -> Path:
    """Side-by-side image against reference ``i``; the first keeps the plain name."""
    return Path(out_dir) / (f"{target}_sbs.jpg" if i == 0 else f"{target}_sbs_{i + 1}.jpg")


def _grid(l: np.ndarray, gx: int = 8, gy: int = 5) -> np.ndarray:
    h, w = l.shape
    return np.array([[l[j * h // gy:(j + 1) * h // gy, i * w // gx:(i + 1) * w // gx].mean()
                      for i in range(gx)] for j in range(gy)]).ravel()


def _hist(a: np.ndarray, bins: int = 8) -> np.ndarray:
    q = np.minimum((a * bins).astype(int), bins - 1)
    idx = q[..., 0] * bins * bins + q[..., 1] * bins + q[..., 2]
    hgram = np.bincount(idx.ravel(), minlength=bins ** 3).astype(np.float64)
    return hgram / hgram.sum()


def _edge_density(l: np.ndarray) -> float:
    gx = np.abs(np.diff(l, axis=1)).mean()
    gy = np.abs(np.diff(l, axis=0)).mean()
    return float(gx + gy)


def components(render: np.ndarray, ref: np.ndarray) -> dict:
    """Each component in 0..1, 1 = matches the reference."""
    ref = crop_dark_border(ref)
    a, b = _resize(render, 480, 270), _resize(ref, 480, 270)
    la, lb = lookdev._luma(a), lookdev._luma(b)
    pd = lookdev.palette_distance(_palette(a), _palette(b))
    ga, gb = _grid(la), _grid(lb)
    if ga.std() > 1e-6 and gb.std() > 1e-6:
        corr = float(np.corrcoef(ga, gb)[0, 1])
    else:  # a flat grid has no correlation; identical flat grids still match exactly
        corr = 1.0 if np.allclose(ga, gb, atol=1e-6) else 0.0
    ea, eb = _edge_density(la), _edge_density(lb)
    return {
        "palette": max(0.0, 1 - pd / 0.5),
        "histogram": float(np.minimum(_hist(a), _hist(b)).sum()),
        "layout": max(0.0, corr),
        "detail": max(0.0, 1 - abs(np.log((ea + 1e-6) / (eb + 1e-6))) / np.log(3)),
        "brightness": max(0.0, 1 - abs(la.mean() - lb.mean()) / 0.25),
        "contrast": max(0.0, 1 - abs(la.std() - lb.std()) / 0.1),
    }


def score(comp: dict) -> float:
    return float(sum(WEIGHTS[k] * comp[k] for k in WEIGHTS))


# ---------- harness ----------

def unknown_keys(over: dict, base: dict, path: str = "") -> list[str]:
    """Keys in a preset that DEFAULTS doesn't define (set_dotted would accept them silently)."""
    bad = []
    for k, v in over.items():
        p = f"{path}{k}"
        if not path and k in FREE_KEYS:
            continue
        if k not in base:
            bad.append(p)
        elif isinstance(v, dict) and isinstance(base[k], dict):
            bad += unknown_keys(v, base[k], p + ".")
    return bad


def run(target: str, device: str, out_dir: Path) -> dict:
    t = json.loads((HERE / "targets.json").read_text())[target]
    preset = ROOT / t["preset"]
    bad = unknown_keys(json.loads(preset.read_text()), config.DEFAULTS)
    if bad:
        raise SystemExit(f"CRASH: preset sets keys DEFAULTS does not have: {bad}")
    out_dir = Path(out_dir).resolve()  # the render runs with cwd=ROOT
    out_dir.mkdir(parents=True, exist_ok=True)
    still = out_dir / f"{target}.png"
    sets = EVAL_SETS + ([f"render.device={json.dumps(device)}"] if device else [])
    cmd = [sys.executable, "-m", "wavegen", "still", "--preset", str(preset), "--frame", str(t.get("frame", 1)),
           "-o", str(still)] + sum((["--set", s] for s in sets), [])
    t0 = time.time()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    secs = time.time() - t0
    if p.returncode:
        raise SystemExit(f"CRASH: render failed\n{p.stderr[-2000:]}")
    cfg = config.load(str(preset), sets)
    graded = lookdev.grade_still(still, out_dir / f"{target}_graded.png", cfg)
    img = lookdev._load(graded)
    per_ref = []
    for r in t["refs"]:
        per_ref.append(components(img, lookdev._load(ROOT / r)))
    comp = {k: float(np.mean([c[k] for c in per_ref])) for k in WEIGHTS}
    sbs = [sbs_path(out_dir, target, i) for i in range(len(t["refs"]))]
    for r, path in zip(t["refs"], sbs):                 # one per reference, so each can be eyeballed
        lookdev.compare(graded, ROOT / r, path)
    return {"score": score(comp), "components": comp, "render_seconds": secs,
            "sbs": str(sbs[0]), "sbs_all": [str(s) for s in sbs]}


def loopcheck(target: str) -> bool:
    t = json.loads((HERE / "targets.json").read_text())[target]
    p = subprocess.run([sys.executable, "-m", "wavegen", "loopcheck", "--preset", str(ROOT / t["preset"]),
                        "--set", "render.resolution=[160,90]"], cwd=ROOT, capture_output=True, text=True)
    return p.returncode == 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="poolrooms")
    ap.add_argument("--device", default="", help="CPU or GPU (default: config's)")
    ap.add_argument("--out", default=str(ROOT / "out" / "autoresearch"))
    ap.add_argument("--no-loopcheck", action="store_true")
    a = ap.parse_args()
    r = run(a.target, a.device, Path(a.out))
    for k, v in r["components"].items():
        print(f"  {k:<10} {v:.4f}")
    print(f"RENDER_SECONDS: {r['render_seconds']:.1f}")
    if not a.no_loopcheck:
        print(f"LOOPCHECK: {'PASS' if loopcheck(a.target) else 'FAIL'}")
    print(f"SBS: {' '.join(r['sbs_all'])}")
    print(f"SCORE: {r['score']:.4f}")


if __name__ == "__main__":
    main()
