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


def test_assemble_rejects_mixed_extensions(tmp_path):
    cfg = config.load("poolrooms", ["render.fps=2", "render.seconds=2", "render.resolution=[64,36]"])
    d = tmp_path / "frames"
    d.mkdir()
    for i, ext in ((1, "png"), (2, "png"), (3, "jpg"), (4, "jpg")):
        (d / f"frame_{i:05d}.{ext}").write_bytes(b"x")
    with pytest.raises(post.IncompleteLoopError):
        post.assemble(d, tmp_path / "o.mp4", cfg)


def test_extend_handles_apostrophe_in_path(loop, tmp_path):
    cfg, d, mp4 = loop
    odd = tmp_path / "Alice's room"
    odd.mkdir()
    src = odd / "loop.mp4"
    shutil.copy(mp4, src)
    out = post.extend(src, d / "stems", 3.0, odd / "long.mp4")
    assert out.exists()


def _grade_flat(pc, h=90, w=160, level=0.6):
    raw = (np.full((h, w, 3), level) * 255).astype(np.uint8).tobytes()
    out = subprocess.run(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-i", "-",
                          "-filter_complex", post.filtergraph(pc, w, h), "-map", "[vout]", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         input=raw, capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(h, w, 3).astype(np.float32) / 255


def test_pink_wash_tints_the_left_of_frame_only():
    """The reference carries a pink-lavender wash over its left side that fades out toward the middle."""
    pc = {**_cfg()["post"], "grade": False, "halation": 0, "grain": 0, "chroma_shift": 0, "vignette": 0,
          "crt_on_tv": False, "pink_wash": {"strength": 1.0, "color": [1.0, 0.78, 0.92], "extent": 0.5}}
    img = _grade_flat(pc)
    w = img.shape[1]
    left, right = img[:, : w // 10].mean((0, 1)), img[:, -w // 10:].mean((0, 1))
    assert left[0] - left[1] >= 0.08                 # red over green: pink
    assert abs(right[0] - right[1]) <= 0.01          # the right side is untouched
    assert left.mean() <= right.mean() + 0.01       # a tint, not a light: it never brightens


def test_pink_wash_off_by_default_is_identity():
    pc = {**config.DEFAULTS["post"], "grade": False, "halation": 0, "grain": 0, "chroma_shift": 0, "vignette": 0, "crt_on_tv": False}
    img = _grade_flat(pc)
    assert np.ptp(img[..., 0] - img[..., 1]) <= 0.01


def test_tile_wav_repeats_the_loop_and_cuts_to_length(tmp_path):
    import wave
    sr = 8000
    x = np.stack([np.linspace(-0.5, 0.5, 100), np.linspace(0.5, -0.5, 100)], 1)
    src = audio.write_wav(tmp_path / "loop.wav", x, sr)
    dst = post.tile_wav(src, tmp_path / "long.wav", 250, chunk_frames=64)
    with wave.open(str(src)) as w:
        one = np.frombuffer(w.readframes(100), "<i2").reshape(-1, 2)
    with wave.open(str(dst)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getnframes()) == (sr, 2, 250)
        got = np.frombuffer(w.readframes(250), "<i2").reshape(-1, 2)
    assert np.array_equal(got, np.tile(one, (3, 1))[:250])


def test_tile_wav_rejects_a_source_whose_audio_is_cut_short(tmp_path):
    import wave
    src = audio.write_wav(tmp_path / "loop.wav", np.zeros((100, 2)), 8000)
    raw = src.read_bytes()
    src.write_bytes(raw[:-400])                    # header still promises 100 frames; the payload is gone
    with wave.open(str(src)) as w:
        w.readframes(100)
        assert w.readframes(1) == b""
    src.write_bytes(raw[:44])                      # header only: every read comes back empty
    with pytest.raises(ValueError, match="no audio"):
        post.tile_wav(src, tmp_path / "long.wav", 250, chunk_frames=64)
