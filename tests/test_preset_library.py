"""Library commands: list, show and save presets, including in a private library folder."""
import json

import pytest

from wavegen import cli, config


@pytest.fixture
def lib(tmp_path, monkeypatch):
    d = tmp_path / "library"
    d.mkdir()
    monkeypatch.setenv("WAVEGEN_PRESET_PATH", str(d))
    return d


def _run(capsys, *argv):
    cli.main(list(argv))
    return capsys.readouterr().out


def test_diff_keeps_only_what_changed():
    base = {"a": {"b": 1, "c": [1, 2]}, "d": 2, "e": {"f": 1}}
    cfg = {"a": {"b": 1, "c": [1, 3]}, "d": 5, "e": {"f": 1}}
    assert config.diff_config(cfg, base) == {"a": {"c": [1, 3]}, "d": 5}
    assert config.diff_config(base, base) == {}


def test_save_writes_only_the_changes_on_top_of_its_parent(lib, capsys):
    _run(capsys, "presets", "save", "rose", "--from", "poolrooms", "--set", "palette.water=[0.8,0.78,0.98]",
         "--set", "lights.cove_power=3000", "--description", "blush room", "--tags", "pink,day")
    body = json.loads((lib / "rose.json").read_text())
    assert body == {"name": "rose", "extends": "poolrooms", "description": "blush room", "tags": ["pink", "day"],
                    "palette": {"water": [0.8, 0.78, 0.98]}, "lights": {"cove_power": 3000}}
    want = config.load("poolrooms", ["palette.water=[0.8,0.78,0.98]", "lights.cove_power=3000"])
    got = config.load("rose")                                   # found by name in the private library
    assert got.pop("name") == "rose" and want.pop("name") == "poolrooms" and got == want


def test_a_variant_can_be_kept_as_a_preset(lib, tmp_path, capsys):
    variant = config.mutate(config.load("poolrooms"), seed=7)
    src = tmp_path / "config.json"
    src.write_text(json.dumps(variant, indent=2))               # what `variants` and `make` write
    _run(capsys, "presets", "save", "keeper", "--from", "poolrooms", "--config", str(src))
    body = json.loads((lib / "keeper.json").read_text())
    assert body["extends"] == "poolrooms" and "room" in body and "render" not in body   # only what the seed changed
    got = config.load("keeper")
    got["name"] = variant["name"]
    assert got == variant


def test_save_refuses_to_overwrite_or_shadow_without_force(lib, capsys):
    _run(capsys, "presets", "save", "mine", "--from", "poolrooms")
    with pytest.raises(SystemExit, match="exists"):
        _run(capsys, "presets", "save", "mine", "--from", "poolrooms")
    with pytest.raises(SystemExit, match="poolrooms_dusk.*exists"):
        _run(capsys, "presets", "save", "poolrooms_dusk", "--from", "poolrooms")   # would hide the bundled one
    _run(capsys, "presets", "save", "mine", "--from", "poolrooms", "--set", "render.samples=5", "--force")
    assert config.load("mine")["render"]["samples"] == 5


def test_save_refuses_a_key_the_config_does_not_have(lib, capsys):
    with pytest.raises(SystemExit, match="lights.cove_powr"):
        _run(capsys, "presets", "save", "typo", "--from", "poolrooms", "--set", "lights.cove_powr=1")
    assert not (lib / "typo.json").exists()


def test_save_into_a_chosen_folder_names_a_parent_there_by_name(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("WAVEGEN_PRESET_PATH", raising=False)
    d = tmp_path / "elsewhere"
    _run(capsys, "presets", "save", "one", "--from", "poolrooms", "--dir", str(d), "--set", "render.samples=3")
    _run(capsys, "presets", "save", "two", "--from", str(d / "one.json"), "--dir", str(d), "--set", "render.fps=24")
    assert json.loads((d / "two.json").read_text())["extends"] == "one"
    cfg = config.load(str(d / "two.json"))
    assert (cfg["render"]["samples"], cfg["render"]["fps"]) == (3, 24)


def test_list_shows_bundled_and_private_presets_with_their_notes(lib, capsys):
    _run(capsys, "presets", "save", "rose", "--from", "poolrooms_dusk", "--description", "blush room", "--tags", "pink")
    out = _run(capsys, "presets", "list")
    lines = {ln.split()[0]: ln for ln in out.splitlines() if ln.strip() and not ln.startswith(("NAME", "-"))}
    assert {"poolrooms", "poolrooms_dusk", "poolrooms_night", "rose"} <= set(lines)
    assert "poolrooms_dusk" in lines["rose"] and "blush room" in lines["rose"] and "pink" in lines["rose"]
    assert sorted(_run(capsys, "presets", "list", "--names").split()) == sorted(config.list_presets())
    assert "rose" in config.list_presets()
    assert _run(capsys, "presets") == _run(capsys, "presets", "list")    # bare `presets` still lists


def test_show_prints_the_preset_or_everything_it_resolves_to(capsys):
    own = json.loads(_run(capsys, "presets", "show", "poolrooms_night"))
    assert own["extends"] == "poolrooms" and "room" not in own
    full = json.loads(_run(capsys, "presets", "show", "poolrooms_night", "--resolved"))
    assert full == config.load("poolrooms_night")
    assert "poolrooms_night -> poolrooms" in _run(capsys, "presets", "show", "poolrooms_night", "--lineage")


def test_shadowing_a_bundled_preset_points_at_the_bundled_file(lib, capsys):
    # the new lib/poolrooms.json must not name itself as its parent
    _run(capsys, "presets", "save", "poolrooms", "--from", "poolrooms", "--force",
         "--set", "palette.water=[0.8,0.78,0.98]")
    body = json.loads((lib / "poolrooms.json").read_text())
    assert body["extends"] == str((config.PRESET_DIR / "poolrooms.json").resolve())
    assert config.load("poolrooms")["palette"]["water"] == [0.8, 0.78, 0.98]


def test_a_save_that_cannot_reload_leaves_nothing_behind(lib, capsys, monkeypatch):
    def broken(*a, **k):
        raise ValueError("presets extend each other in a loop: x -> x")
    real = config.load
    monkeypatch.setattr(config, "load", lambda p=None, o=None: broken() if str(p).endswith("x.json") else real(p, o))
    with pytest.raises(SystemExit, match="nothing saved"):
        _run(capsys, "presets", "save", "x", "--from", "poolrooms")
    assert not (lib / "x.json").exists()


def test_save_never_replaces_a_file_that_appears_meanwhile(lib, capsys, monkeypatch):
    # another save writes the same name between our check and our write
    real = config.find_preset

    def racing(ref, near=None):
        if near is not None:                    # the parent lookup runs after the exists-check
            (lib / "rose.json").write_text('{"extends": "poolrooms"}\n')
        return real(ref, near)
    monkeypatch.setattr(config, "find_preset", racing)
    with pytest.raises(SystemExit, match="already exists"):
        _run(capsys, "presets", "save", "rose", "--from", "poolrooms", "--set", "render.samples=3")
    assert (lib / "rose.json").read_text() == '{"extends": "poolrooms"}\n'
