"""lookdev.compare: side-by-side + palette distance (needs ffmpeg)."""
import shutil
import subprocess

import pytest

from wavegen import lookdev

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg missing")


@pytest.fixture(scope="module")
def imgs(tmp_path_factory):
    d = tmp_path_factory.mktemp("ld")
    src, inv = d / "src.png", d / "inv.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0xb0e0f0:s=320x180",
                    "-vf", "drawbox=x=0:y=120:w=320:h=60:c=0x40a0c0:t=fill", "-frames:v", "1", str(src)],
                   check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", "negate", str(inv)], check=True)
    return d, src, inv


def _width(p):
    return int(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width", "-of", "csv=p=0", str(p)],
                              capture_output=True, text=True, check=True).stdout)


def test_self_compare_is_close(imgs):
    d, src, _ = imgs
    r = lookdev.compare(src, src, d / "self.jpg")
    assert r["palette_distance"] < 0.02
    assert r["brightness_render"] == pytest.approx(r["brightness_ref"], abs=1e-6)


def test_inverted_is_far_and_sbs_written(imgs):
    d, src, inv = imgs
    out = d / "inv.jpg"
    r = lookdev.compare(inv, src, out)
    assert r["palette_distance"] > 0.3
    assert out.exists() and _width(out) == 1920
    assert {"palette_render", "palette_ref", "contrast_render", "contrast_ref"} <= set(r)


def test_grade_still_uses_render_percentage(imgs, tmp_path):
    from wavegen import config
    _, src, _ = imgs                                   # 320x180 = 50 % of 640x360
    cfg = config.load("poolrooms", ["render.resolution=[640,360]", "render.percentage=50", "post.crt_on_tv=true"])
    out = lookdev.grade_still(src, tmp_path / "g.png", cfg)
    assert _width(out) == 320


def test_default_still_frame_fits_short_loop():
    from wavegen import config
    from wavegen.cli import _default_frame
    assert _default_frame(None, config.load("poolrooms", ["render.fps=30", "render.seconds=2"])) <= 60
    assert _default_frame(7, config.load("poolrooms", [])) == 7


def test_lookdev_runs_post_effects_with_grade_off(imgs, tmp_path, monkeypatch):
    """post.grade=false only drops the colour grade; cmd_lookdev still grades the still
    (vignette etc.) before comparing."""
    import argparse
    import shutil as sh
    from wavegen import cli
    _, src, _ = imgs
    monkeypatch.setattr(cli, "cmd_still", lambda a: sh.copy(src, a.out))
    calls = []
    real = lookdev.grade_still
    monkeypatch.setattr(lookdev, "grade_still", lambda s, o, c: calls.append(c["post"]["grade"]) or real(s, o, c))
    args = argparse.Namespace(preset="poolrooms", ref=str(src), out=str(tmp_path / "ld"), frame=1,
                              set=["post.grade=false", "post.vignette=0.8", "render.resolution=[320,180]"],
                              preview=False, seconds=None, seed=None)
    cli.cmd_lookdev(args)
    assert calls == [False]
    assert (tmp_path / "ld_graded.png").exists() and (tmp_path / "ld.json").exists()


def test_grade_still_applies_vignette_with_grade_off(imgs, tmp_path):
    import numpy as np
    from wavegen import config
    _, src, _ = imgs
    cfg = config.load("poolrooms", ["render.resolution=[320,180]", "post.grade=false", "post.vignette=0.8",
                                    "post.crt_on_tv=false"])
    a = lookdev._load(src)
    b = lookdev._load(lookdev.grade_still(src, tmp_path / "v.png", cfg))
    assert b[:20, :20].mean() < a[:20, :20].mean() - 0.05          # corners darkened
