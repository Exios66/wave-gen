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


def test_identical_flat_images_score_one():
    flat = np.full((270, 480, 3), 0.5, np.float32)
    assert ar.components(flat, flat)["layout"] == 1.0


def test_relative_out_dir_is_resolved_before_render(tmp_path, monkeypatch):
    seen = {}

    def fake_run(cmd, cwd=None, **kw):
        seen["out"] = cmd[cmd.index("-o") + 1]
        raise SystemExit("stop after capturing the render command")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ar.subprocess, "run", fake_run)
    try:
        ar.run("poolrooms", "", Path("rel_out"))
    except SystemExit:
        pass
    assert Path(seen["out"]).is_absolute() and Path(seen["out"]).parent == tmp_path / "rel_out"


def test_downsizing_averages_instead_of_picking_single_pixels():
    a = np.zeros((8, 8, 3))
    a[::2, ::2] = 1.0
    a[1::2, 1::2] = 1.0                           # one-pixel checkerboard
    small = ar._resize(a, 4, 4)
    assert small.shape == (4, 4, 3) and np.allclose(small, 0.5)


def test_resize_to_the_same_size_changes_nothing():
    a = np.random.default_rng(0).random((6, 9, 3))
    assert np.array_equal(ar._resize(a, 9, 6), a)


def test_every_reference_gets_its_own_side_by_side():
    from pathlib import Path
    paths = [ar.sbs_path(Path("o"), "poolrooms", i) for i in range(3)]
    assert paths[0] == Path("o/poolrooms_sbs.jpg") and len(set(paths)) == 3
