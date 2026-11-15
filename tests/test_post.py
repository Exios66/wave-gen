"""post.assemble with stems, and extend (needs ffmpeg)."""
import shutil
import subprocess

import numpy as np
import pytest

from wavegen import audio, config, post

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg missing")


def _cfg():
    return config.load("poolrooms", ["render.fps=30", "render.seconds=2", "render.resolution=[64,36]",
                                     "audio.sample_rate=16000", "post.halation=0", "post.grain=0"])


@pytest.fixture(scope="module")
def loop(tmp_path_factory):
    d = tmp_path_factory.mktemp("loop")
    cfg = _cfg()
    (d / "frames").mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=64x36:r=30:d=2",
                    str(d / "frames" / "frame_%05d.png")], check=True)
    audio.write_stems(cfg, d / "stems")
    mp4 = post.assemble(d / "frames", d / "loop.mp4", cfg, stems_dir=d / "stems")
    return cfg, d, mp4


def _probe(path, entries, stream="a:0"):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", entries,
                           "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout.strip()


def _decode(path, sr=16000):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def _read_wav_mono(path):
    import wave
    with wave.open(str(path)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32).reshape(-1, 2) / 32768
    return x.mean(1)


def test_assemble_default_bed(loop):
    cfg, d, mp4 = loop
    dur = float(_probe(mp4, "stream=duration"))
    assert dur == pytest.approx(2.0, abs=0.05)
    got, ref = _decode(mp4), _read_wav_mono(d / "stems" / "bed.wav")
    m = min(len(got), len(ref))
    # AAC delay is trimmed by ffmpeg; allow a small lag search
    best = max(np.corrcoef(got[k:m], ref[:m - k])[0, 1] for k in range(0, 1200, 8))
    assert best > 0.9


def test_assemble_full_mix_differs(loop):
    cfg, d, _ = loop
    full = post.assemble(d / "frames", d / "full.mp4", cfg, stems_dir=d / "stems", audio_mix="full")
    ref = _read_wav_mono(d / "stems" / "mix.wav")
    got = _decode(full)
    m = min(len(got), len(ref))
    assert max(np.corrcoef(got[k:m], ref[:m - k])[0, 1] for k in range(0, 1200, 8)) > 0.9


def test_extend_duration_and_no_reencode(loop, tmp_path):
    cfg, d, mp4 = loop
    out = post.extend(mp4, d / "stems", 7.0, tmp_path / "long.mp4")
    fmt = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                         capture_output=True, text=True, check=True).stdout
    assert float(fmt) == pytest.approx(7.0, abs=0.1)
    assert _probe(out, "stream=codec_name,profile,width,height", "v:0") == \
        _probe(mp4, "stream=codec_name,profile,width,height", "v:0")
    x = _decode(out)
    typical = np.percentile(np.abs(np.diff(x)), 99.9)
    for join in (2.0, 4.0, 6.0):
        i = int(join * 16000)
        assert np.abs(np.diff(x[i - 40:i + 40])).max() <= 1.5 * typical, join  # no click at the join


def test_parse_duration():
    assert post.parse_duration("1h30m") == 5400
    assert post.parse_duration("90s") == 90
    assert post.parse_duration("45m") == 2700
    assert post.parse_duration("1h") == 3600
    assert post.parse_duration("120") == 120
    with pytest.raises(ValueError):
        post.parse_duration("x")


def test_grade_keeps_high_key_contrast(tmp_path):
    """The vapor grade must not wash a bright room out (no milky veil from halation)."""
    rng = np.random.default_rng(0)
    h, w = 180, 320
    img = np.repeat(np.repeat(rng.uniform(0.5, 0.95, (h // 20, w // 20, 1)), 20, 0), 20, 1)
    img = np.repeat(img, 3, 2)
    raw = (img * 255).astype(np.uint8).tobytes()
    cfg = _cfg()
    pc = {**cfg["post"], "grain": 0, "chroma_shift": 0, "vignette": 0, "crt_on_tv": False, "halation": 0.22}
    out = subprocess.run(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-i", "-",
                          "-filter_complex", post.filtergraph(pc, w, h), "-map", "[vout]", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         input=raw, capture_output=True, check=True).stdout
    got = np.frombuffer(out, np.uint8).reshape(h, w, 3).astype(np.float32).mean(2) / 255
    src = img.mean(2)
    assert got.mean() <= src.mean() + 0.03
    assert got.std() >= 0.9 * src.std()
