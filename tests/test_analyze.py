import shutil
import subprocess
import time

import numpy as np
import pytest

from wavegen import analyze as A


def test_spectrum_windows():
    assert A._spectrum_windows(16000, 32768) == [(0, 16000)]
    assert A._spectrum_windows(32768, 32768) == [(0, 32768)]
    w = A._spectrum_windows(50000, 32768)
    assert w[0] == (0, 32768) and w[-1][1] == 50000


def test_palette_small_and_empty():
    assert A._palette(np.zeros((0, 3), np.float32)) == []
    p = A._palette(np.array([[0.1, 0.2, 0.3], [0.9, 0.9, 0.9], [0.5, 0.5, 0.1]], np.float32))
    assert 1 <= len(p) <= 3
    assert abs(sum(x["share"] for x in p) - 1) < 0.01


def test_palette_large_is_capped_and_deterministic():
    px = np.random.default_rng(1).random((1_000_000, 3), dtype=np.float32)
    t = time.time()
    a = A._palette(px)
    assert time.time() - t < 5
    assert a == A._palette(px)


def test_motion_path_starts_at_origin():
    path = A._motion_path([(2, 0)])
    assert np.ptp(path[:, 0]) == 2


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg missing")
def test_analyze_black_clip(tmp_path):
    clip = tmp_path / "black.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:d=2",
                    "-f", "lavfi", "-i", "sine=f=440:d=2", "-shortest", "-c:v", "libx264", "-c:a", "aac",
                    str(clip)], check=True)
    res = A.analyze(clip, tmp_path / "out")
    assert (tmp_path / "out" / "analysis.json").exists()
    assert res["audio"]["tonal_peaks_hz"]
