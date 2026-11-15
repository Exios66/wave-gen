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
