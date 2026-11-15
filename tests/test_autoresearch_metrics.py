import importlib.util
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("ar_eval", Path(__file__).parent.parent / "autoresearch" / "eval.py")
ar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ar)


def _scene(seed=0):
    rng = np.random.default_rng(seed)
    a = np.zeros((270, 480, 3), np.float32)
    a[:] = (0.55, 0.85, 0.92)
    a[100:200, 150:330] = (0.95, 0.84, 0.64)                      # warm alcove
    a[::12] *= 0.85                                              # tile lines
    return np.clip(a + rng.normal(0, 0.01, a.shape), 0, 1).astype(np.float32)


def test_identical_images_score_one():
    a = _scene()
    assert ar.score(ar.components(a, a)) > 0.99


def test_unlike_image_scores_lower():
    a = _scene()
    b = 1 - a[:, ::-1]
    assert ar.score(ar.components(b, a)) < ar.score(ar.components(a, a)) - 0.3


def test_reference_bezel_is_ignored():
    a = _scene()
    framed = np.zeros((300, 480, 3), np.float32)
    framed[30:] = a
    assert ar.score(ar.components(a, framed)) > 0.95


def test_unknown_preset_keys_are_reported():
    base = {"render": {"samples": 1}, "palette": {"water": [0, 0, 0]}}
    assert ar.unknown_keys({"name": "x", "render": {"samples": 2, "bogus": 1}, "nope": 1}, base) == \
        ["render.bogus", "nope"]
