"""Fast tests that need no Blender (config, audio, post graph)."""
import numpy as np
import pytest

from wavegen import audio, config, post


def test_presets_load_and_merge():
    names = config.list_presets()
    assert {"poolrooms", "poolrooms_dusk", "poolrooms_night"} <= set(names)
    for n in names:
        cfg = config.load(n)
        assert cfg["name"] == n
        assert len(cfg["render"]["resolution"]) == 2
    dusk = config.load("poolrooms_dusk")
    assert dusk["palette"]["plaster"] != config.DEFAULTS["palette"]["plaster"]
    assert dusk["room"] == config.DEFAULTS["room"]  # untouched sections inherited


def test_dotted_overrides_parse_json():
    cfg = config.load(None, ["render.samples=8", "render.resolution=[320,180]", "name=x", "camera.drift.period=[1,2,3]"])
    assert cfg["render"]["samples"] == 8
    assert cfg["render"]["resolution"] == [320, 180]
    assert cfg["name"] == "x"
    assert cfg["camera"]["drift"]["period"] == [1, 2, 3]
    with pytest.raises(ValueError):
        config.set_dotted(cfg, "nonsense")


def test_mutate_is_deterministic_and_valid():
    base = config.load("poolrooms")
    a, b, c = config.mutate(base, 7), config.mutate(base, 7), config.mutate(base, 8)
    assert a == b and a != c
    for v in (a, c):
        r, p = v["room"], v["pool"]
        assert sum(r["back_arches"]) + 0.6 * (len(r["back_arches"]) + 1) < r["width"]
        assert -r["width"] / 2 < p["x"][0] < p["x"][1] < r["width"] / 2
        assert p["y"][1] < -3.5 + r["depth"] - 1.0
        assert r["spring_height"] < r["height"] - 2.0 + 1e-9
    assert base == config.load("poolrooms")  # mutate does not touch its input


def test_note_hz():
    assert audio.note_hz("A4") == pytest.approx(440.0)
    assert audio.note_hz("G3") == pytest.approx(196.0, rel=1e-3)
    assert audio.note_hz("F#3") == pytest.approx(185.0, rel=1e-3)


def test_audio_synth_shape_level_and_pitch():
    cfg = config.load("poolrooms", ["audio.sample_rate=16000"])
    data, sr = audio.synthesize(cfg, seconds=8.0)
    assert sr == 16000 and data.shape == (8 * 16000, 2)
    assert np.isfinite(data).all()
    assert 0.5 < np.abs(data).max() <= 0.8
    # the strongest partials must sit on chord tones (or harmonics) pitched down by tempo_slow
    seg = data[2 * sr: 5 * sr, 0]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    f = np.fft.rfftfreq(len(seg), 1 / sr)
    slow = cfg["audio"]["tempo_slow"]
    targets = [audio.note_hz(n) * slow * h for n in cfg["audio"]["chords"][0] for h in (1, 2, 3)]
    band = (f > 80) & (f < 1200)
    top = f[band][np.argsort(spec[band])[-5:]]
    for peak in top:
        assert min(abs(peak - t) for t in targets) < 3, peak
    # and NOT on the un-slowed pitch
    unslowed = [audio.note_hz(n) * h for n in cfg["audio"]["chords"][0] for h in (1, 2, 3)]
    for peak in top:
        assert min(abs(peak - t) for t in targets) < min(abs(peak - t) for t in unslowed), peak


def test_post_filtergraph_variants():
    cfg = config.load("poolrooms")
    g = post.filtergraph(cfg["post"], 1920, 1080)
    assert g.startswith("[0:v]") and g.endswith("[vout]") and "blend=all_mode=screen" in g
    pc = dict(cfg["post"], halation=0, grade=False, crt_on_tv=True)
    g2 = post.filtergraph(pc, 1280, 720)
    assert "nullsink" in g2 and "lenscorrection" in g2 and "pad=1280:720" in g2
