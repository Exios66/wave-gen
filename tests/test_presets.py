"""The preset library: presets build on one another with ``extends``, and a preset
that names a key the config does not have is refused instead of silently ignored."""
import json

import pytest

from wavegen import config
from wavegen.frames import config_hash


def _write(d, name, body):
    p = d / f"{name}.json"
    p.write_text(json.dumps(body))
    return p


def test_a_preset_can_build_on_another(tmp_path):
    _write(tmp_path, "base", {"palette": {"water": [0.1, 0.2, 0.3]}, "render": {"samples": 11}})
    child = _write(tmp_path, "child", {"extends": "base", "render": {"samples": 22}})
    cfg = config.load(str(child))
    assert cfg["palette"]["water"] == [0.1, 0.2, 0.3]           # inherited from the parent
    assert cfg["render"]["samples"] == 22                       # the child wins
    assert cfg["render"]["fps"] == config.DEFAULTS["render"]["fps"]   # the rest still comes from DEFAULTS


def test_extends_chains_through_several_generations(tmp_path):
    _write(tmp_path, "a", {"render": {"samples": 1, "fps": 24}})
    _write(tmp_path, "b", {"extends": "a", "render": {"samples": 2}})
    c = _write(tmp_path, "c", {"extends": "b", "palette": {"water": [0, 0, 1]}})
    cfg = config.load(str(c))
    assert (cfg["render"]["samples"], cfg["render"]["fps"], cfg["palette"]["water"]) == (2, 24, [0, 0, 1])
    assert config.lineage(str(c)) == ["c", "b", "a"]


def test_a_parent_can_be_a_bundled_preset(tmp_path):
    child = _write(tmp_path, "mine", {"extends": "poolrooms", "palette": {"water": [0, 0, 1]}})
    mine, base = config.load(str(child)), config.load("poolrooms")
    assert mine["palette"]["water"] == [0, 0, 1]
    mine["palette"]["water"] = base["palette"]["water"]
    mine["name"] = base["name"]
    assert mine == base


def test_a_loop_of_parents_is_refused(tmp_path):
    _write(tmp_path, "a", {"extends": "b"})
    _write(tmp_path, "b", {"extends": "a"})
    with pytest.raises(ValueError, match="a -> b -> a"):
        config.load(str(tmp_path / "a.json"))


def test_a_missing_parent_names_the_preset_that_asked_for_it(tmp_path):
    child = _write(tmp_path, "child", {"extends": "no_such_preset"})
    with pytest.raises(FileNotFoundError, match="child.*no_such_preset"):
        config.load(str(child))


def test_a_misspelt_key_is_refused_with_its_full_path(tmp_path):
    p = _write(tmp_path, "typo", {"render": {"sampels": 4}, "palete": {}})
    with pytest.raises(ValueError, match=r"palete.*render\.sampels|render\.sampels.*palete"):
        config.load(str(p))


def test_a_misspelt_key_in_a_parent_is_refused_too(tmp_path):
    _write(tmp_path, "base", {"lights": {"cove_powr": 1.0}})
    child = _write(tmp_path, "child", {"extends": "base"})
    with pytest.raises(ValueError, match=r"base.*lights\.cove_powr"):
        config.load(str(child))


def test_library_notes_never_reach_the_config_or_the_frame_hash(tmp_path):
    body = {"extends": "poolrooms", "description": "first", "tags": ["pool"], "_comment": "x"}
    p = _write(tmp_path, "noted", body)
    cfg = config.load(str(p))
    assert not {"extends", "description", "tags", "_comment"} & set(cfg)
    h = config_hash(cfg)
    _write(tmp_path, "noted", {**body, "description": "reworded", "tags": ["pool", "pink"]})
    assert config_hash(config.load(str(p))) == h


def test_a_preset_without_a_name_is_named_after_its_file(tmp_path):
    _write(tmp_path, "base", {"name": "the_base"})
    child = _write(tmp_path, "my_room", {"extends": "base"})
    assert config.load(str(child))["name"] == "my_room"
    assert config.load(str(tmp_path / "base.json"))["name"] == "the_base"


def test_preset_info_reports_the_library_notes(tmp_path):
    _write(tmp_path, "base", {"description": "parent", "tags": ["a"]})
    child = _write(tmp_path, "kid", {"extends": "base", "description": "a pink room", "tags": ["pink", "dusk"]})
    info = config.preset_info(str(child))
    assert info == {"name": "kid", "extends": "base", "description": "a pink room", "tags": ["pink", "dusk"],
                    "path": str(child)}
    assert config.preset_info(str(tmp_path / "base.json"))["extends"] is None


def test_every_bundled_preset_loads_and_describes_itself():
    for name in config.list_presets():
        cfg = config.load(name)
        assert cfg["name"] == name
        info = config.preset_info(name)
        assert info["description"], f"{name} has no description"


def test_the_mood_presets_build_on_the_matched_poolrooms():
    base = config.load("poolrooms")
    for mood in ("poolrooms_dusk", "poolrooms_night"):
        assert config.preset_info(mood)["extends"] == "poolrooms"
        cfg = config.load(mood)
        assert cfg["room"] == base["room"] and cfg["pool"]["notch"] == base["pool"]["notch"]   # same room
        assert cfg["computer"]["tilt"] == base["computer"]["tilt"]
        assert cfg["palette"]["plaster"] != base["palette"]["plaster"]                         # its own mood


DOORWAY = {"location": [-0.5, -2.4, 1.75], "lens": (22.0, 24.0)}


def test_the_nature_rooms_keep_the_house_view_and_their_doorway_twins_look_down():
    house = config.load("poolrooms")["camera"]
    for room in ("palm_solarium", "lotus_court", "moonlit_conservatory"):
        cfg = config.load(room)
        assert cfg["camera"] == house, f"{room} keeps the house camera"
        twin = config.load(f"{room}_doorway")
        info = config.preset_info(f"{room}_doorway")
        assert info["extends"] == room and "doorway" in info["description"]
        assert twin["camera"]["location"] == DOORWAY["location"] and twin["camera"]["lens"] in DOORWAY["lens"]
        twin.pop("camera"), cfg.pop("camera")
        assert twin.pop("name") == f"{room}_doorway" and cfg.pop("name") == room
        assert twin == cfg, f"{room}_doorway changes only the camera"
