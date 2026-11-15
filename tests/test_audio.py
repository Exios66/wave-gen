"""Audio engine: layers, stems, loop seam, loudness (no Blender)."""
import numpy as np
import pytest

from wavegen import audio, config
from wavegen.audio import dsp, layers

STEMS = {"room", "crt", "bells", "pad", "bed", "mix"}


def _cfg(seconds=8, *extra):
    return config.load("poolrooms", ["audio.sample_rate=16000", "render.fps=30",
                                     f"render.seconds={seconds}", *extra])


@pytest.fixture(scope="module")
def stems20():
    return audio.render_stems(_cfg(20))


def test_note_hz():
    assert audio.note_hz("A4") == pytest.approx(440.0)
    assert audio.note_hz("G3") == pytest.approx(196.0, rel=1e-3)
    assert audio.note_hz("F#3") == pytest.approx(185.0, rel=1e-3)


def test_fold_tail():
    np.testing.assert_array_equal(dsp.fold_tail(np.arange(10.0), 4), [0 + 4 + 8, 1 + 5 + 9, 2 + 6, 3 + 7])
    x = np.ones((7, 2))
    assert dsp.fold_tail(x, 3).shape == (3, 2)


def test_stems_lengths_and_keys():
    st = audio.render_stems(_cfg(8))
    assert set(st) == STEMS
    for k, v in st.items():
        assert v.shape == (8 * 16000, 2), k
        assert np.isfinite(v).all(), k


def test_loop_seamless(stems20):
    for k, x in stems20.items():
        if not np.any(x):
            continue
        step = np.median(np.abs(np.diff(x, axis=0)))
        assert np.max(np.abs(x[0] - x[-1])) <= 4 * step + 1e-6, k


def test_loudness_targets(stems20):
    sr = 16000
    assert dsp.lufs(stems20["bed"], sr) == pytest.approx(-20, abs=1)
    assert dsp.lufs(stems20["mix"], sr) == pytest.approx(-16, abs=1)
    for k in ("bed", "mix"):
        assert dsp.true_peak_db(stems20[k], sr) <= -1.0 + 1e-3, k


def test_lufs_reference_tone():
    # BS.1770: a 997 Hz full-scale sine in both channels reads about -0.0 LUFS (+3 dB for stereo sum).
    sr = 48000
    t = np.arange(sr * 3) / sr
    s = np.sin(2 * np.pi * 997 * t) * 10 ** (-23 / 20)
    x = np.stack([s, s], 1)
    assert dsp.lufs(x, sr) == pytest.approx(-23 + 3.01 - 3.01, abs=0.3)


def test_custom_layer_registration():
    @layers.register("test_tone")
    def _tone(cfg, layer, n, sr, rng):
        t = np.arange(n) / sr
        s = np.sin(2 * np.pi * 440 * t)
        return np.stack([s, s], 1)

    cfg = _cfg(8)
    cfg["audio"]["layers"] = [{"type": "test_tone", "stem": "room", "level": 0.5}]
    room = audio.render_stems(cfg)["room"][:, 0]
    f = np.fft.rfftfreq(len(room), 1 / 16000)
    assert abs(f[np.argmax(np.abs(np.fft.rfft(room)))] - 440) < 2


def test_disabled_layer_silent():
    cfg = _cfg(8)
    for layer in cfg["audio"]["layers"]:
        layer["enabled"] = layer["type"] == "crt_hum"
    st = audio.render_stems(cfg)
    assert not np.any(st["pad"])
    assert np.any(st["crt"])


def test_unknown_layer_type_errors():
    cfg = _cfg(8)
    cfg["audio"]["layers"] = [{"type": "nope", "stem": "room", "level": 1}]
    with pytest.raises(ValueError, match="nope"):
        audio.render_stems(cfg)


def test_pad_on_slowed_chord_tones(stems20):
    cfg = _cfg(20)
    sr = 16000
    seg = stems20["pad"][int(1.5 * sr): int(4.5 * sr), 0]   # chord 0 spans 0-5 s
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    f = np.fft.rfftfreq(len(seg), 1 / sr)
    slow = cfg["audio"]["tempo_slow"]
    chord = cfg["audio"]["chords"][0]
    targets = [audio.note_hz(n) * slow * h for n in chord for h in (1, 2, 3)]
    unslowed = [audio.note_hz(n) * h for n in chord for h in (1, 2, 3)]
    band = (f > 80) & (f < 1200)
    for peak in f[band][np.argsort(spec[band])[-5:]]:
        assert min(abs(peak - t) for t in targets) < 3, peak
        assert min(abs(peak - t) for t in targets) < min(abs(peak - t) for t in unslowed), peak


def test_audio_reproducible():
    a = audio.render_stems(_cfg(4))["mix"]
    b = audio.render_stems(_cfg(4))["mix"]
    np.testing.assert_array_equal(a, b)


def test_bells_zero_density():
    cfg = _cfg(4)
    for layer in cfg["audio"]["layers"]:
        if layer["type"] == "bells":
            layer["density"] = 0
    assert not np.any(audio.render_stems(cfg)["bells"])


def test_synthesize_compat_and_write_stems(tmp_path):
    data, sr = audio.synthesize(_cfg(4))
    assert sr == 16000 and data.shape == (4 * 16000, 2)
    paths = audio.write_stems(_cfg(4), tmp_path)
    assert set(paths) == STEMS and all(p.exists() for p in paths.values())


def test_true_peak_keeps_even_length_nyquist():
    x = np.array([1.3, 0.7, -0.7, 0.7])
    assert dsp.true_peak_db(x, 4) >= 20 * np.log10(1.3) - 1e-6


def test_reverb_ir_shorter_than_pre_ramp():
    ir = dsp._reverb_ir(16000, 0.01, np.random.default_rng(0))
    assert len(ir) == 160 and np.all(np.isfinite(ir)) and np.abs(ir).max() > 0
