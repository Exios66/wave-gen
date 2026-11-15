import shutil
import subprocess

import pytest

from wavegen import config
from wavegen.frames import (StaleFramesError, config_hash, loop_frame_count, missing_frames,
                            parse_frames, prepare_frames_dir)

ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg missing")


def test_parse_frames_ranges():
    assert parse_frames("1-3,5", 10) == [1, 2, 3, 5]
    assert parse_frames("5,1-2,2", 10) == [1, 2, 5]
    assert parse_frames(None, 10) is None
    for bad in ("10-1", "0-3", "8-12", "", "a"):
        with pytest.raises(ValueError):
            parse_frames(bad, 10)


def test_loop_frame_count():
    assert loop_frame_count({"render": {"seconds": 59.97, "fps": 30}}) == 1799
    assert loop_frame_count({"render": {"seconds": 0.01, "fps": 30}}) == 1


def test_config_hash_ignores_post_and_audio():
    a = config.load("poolrooms")
    b = config.load("poolrooms", ["post.grain=9", "audio.bell_level=0.5"])
    c = config.load("poolrooms", ["palette.water=[0.1,0.2,0.3]"])
    assert config_hash(a) == config_hash(b)
    assert config_hash(a) != config_hash(c)
    assert len(config_hash(a)) == 16


def test_manifest_mismatch_refuses(tmp_path):
    a = config.load("poolrooms")
    b = config.load("poolrooms", ["palette.water=[0.1,0.2,0.3]"])
    prepare_frames_dir(tmp_path, a, overwrite=False)
    (tmp_path / "frame_00001.png").write_bytes(b"x")
    prepare_frames_dir(tmp_path, a, overwrite=False)  # same config: fine
    with pytest.raises(StaleFramesError, match="--overwrite"):
        prepare_frames_dir(tmp_path, b, overwrite=False)
    prepare_frames_dir(tmp_path, b, overwrite=True)
    assert not (tmp_path / "frame_00001.png").exists()


def test_missing_frames(tmp_path):
    for i in (1, 2, 4):
        (tmp_path / f"frame_{i:05d}.png").write_bytes(b"x")
    assert missing_frames(tmp_path, 4) == [3]


def _make_frames(d, idx):
    d.mkdir(parents=True, exist_ok=True)
    for i in idx:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x36",
                        "-frames:v", "1", str(d / f"frame_{i:05d}.png")], check=True)


def _tiny_cfg(n):
    return config.load("poolrooms", ["render.fps=30", f"render.seconds={n / 30}",
                                     "render.resolution=[64,36]", "post.halation=0"])


@ffmpeg
def test_assemble_refuses_incomplete(tmp_path):
    from wavegen.post import IncompleteLoopError, assemble
    _make_frames(tmp_path / "f", (1, 2, 4))
    with pytest.raises(IncompleteLoopError, match="3"):
        assemble(tmp_path / "f", tmp_path / "o.mp4", _tiny_cfg(4))


@ffmpeg
def test_assemble_complete_loop_encodes_n_frames(tmp_path):
    from wavegen.post import assemble
    _make_frames(tmp_path / "f", (1, 2, 3, 4, 5))  # an extra frame beyond N must be ignored
    out = assemble(tmp_path / "f", tmp_path / "o.mp4", _tiny_cfg(4))
    n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", str(out)],
                       capture_output=True, text=True, check=True).stdout.strip()
    assert int(n) == 4


def test_overwrite_replaces_damaged_manifest(tmp_path):
    cfg = config.load("poolrooms", ["render.fps=2", "render.seconds=1"])
    (tmp_path / "frame_00001.png").write_bytes(b"x")
    (tmp_path / "manifest.json").write_text("")
    prepare_frames_dir(tmp_path, cfg, overwrite=True)
    assert not (tmp_path / "frame_00001.png").exists()
    assert (tmp_path / "manifest.json").read_text().strip().startswith("{")


def test_config_hash_ignores_comment_keys():
    a = config.load("poolrooms")
    b = config.load("poolrooms")
    b["_comment"] = "reworded"
    b["room"]["_note"] = "notes are not pixels"
    assert config_hash(a) == config_hash(b)


def test_assemble_refuses_frames_rendered_from_another_config(tmp_path):
    from wavegen.post import assemble
    _make_frames(tmp_path / "f", range(1, 5))
    import json
    from wavegen.frames import manifest_for
    (tmp_path / "f" / "manifest.json").write_text(json.dumps(manifest_for(_tiny_cfg(4))))
    other = _tiny_cfg(4)
    other["room"]["width"] += 1.0
    with pytest.raises(StaleFramesError):
        assemble(tmp_path / "f", tmp_path / "o.mp4", other)


def test_fractional_fps_is_rejected_instead_of_silently_truncated():
    cfg = config.load("poolrooms", ["render.fps=29.97"])
    with pytest.raises(ValueError, match="whole number"):
        loop_frame_count(cfg)
    assert loop_frame_count(config.load("poolrooms", ["render.fps=30.0", "render.seconds=2"])) == 60


def test_an_empty_frame_file_does_not_count_as_rendered(tmp_path):
    from wavegen.frames import usable_frame
    p = tmp_path / "frame_00001.png"
    assert not usable_frame(p)
    p.write_bytes(b"")
    assert not usable_frame(p)
    p.write_bytes(b"\x89PNG")
    assert usable_frame(p)


def test_assemble_treats_an_empty_frame_as_missing(tmp_path):
    from wavegen.post import IncompleteLoopError, assemble
    _make_frames(tmp_path / "f", range(1, 5))
    (tmp_path / "f" / "frame_00003.png").write_bytes(b"")
    with pytest.raises(IncompleteLoopError, match="3"):
        assemble(tmp_path / "f", tmp_path / "o.mp4", _tiny_cfg(4))
