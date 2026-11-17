"""The preset catalog: a family tree and one entry per preset, kept in step with the library."""
import json
from pathlib import Path

from wavegen import catalog, config

ROOT = Path(__file__).resolve().parents[1]


def _write(d, name, body):
    (d / f"{name}.json").write_text(json.dumps(body))


def test_family_tree_shows_who_builds_on_whom(tmp_path, monkeypatch):
    monkeypatch.setenv("WAVEGEN_PRESET_PATH", str(tmp_path))
    _write(tmp_path, "rose", {"extends": "poolrooms", "description": "pink"})
    _write(tmp_path, "rose_dusk", {"extends": "rose", "description": "pink at dusk"})
    tree = catalog.tree(catalog.entries())
    lines = tree.splitlines()
    i = lines.index("poolrooms")
    assert any(ln.endswith("rose") and ln.startswith(("├── ", "└── ")) for ln in lines[i + 1:])
    assert any(ln.endswith("rose_dusk") and ln.startswith(("│   ", "    ")) for ln in lines[i + 1:])


def test_each_entry_says_what_the_preset_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("WAVEGEN_PRESET_PATH", str(tmp_path))
    _write(tmp_path, "rose", {"extends": "poolrooms", "description": "pink", "tags": ["pink"],
                              "palette": {"water": [1, 0, 0], "plaster": [1, 1, 1]}, "render": {"samples": 3}})
    e = {x["name"]: x for x in catalog.entries()}["rose"]
    assert e["lineage"] == ["rose", "poolrooms"] and e["changes"] == {"palette": 2, "render": 1}
    md = catalog.markdown([e], "presets")
    assert "## rose" in md and "pink" in md and "palette (2)" in md and "![rose](presets/rose.jpg)" in md
    assert "`poolrooms`" in md


def test_the_committed_catalog_matches_the_bundled_library(monkeypatch):
    monkeypatch.delenv("WAVEGEN_PRESET_PATH", raising=False)
    ents = catalog.entries()
    assert [e["name"] for e in ents] == config.list_presets()
    doc = (ROOT / "docs" / "PRESETS.md").read_text()
    assert doc == catalog.markdown(ents, "presets"), "run `wavegen presets catalog` to regenerate docs/PRESETS.md"
    for e in ents:
        assert (ROOT / "docs" / "presets" / f"{e['name']}.jpg").is_file(), f"missing thumbnail for {e['name']}"


def test_new_designs_build_on_the_library():
    for name in ("rose_natatorium", "lavender_hall"):
        info = config.preset_info(name)
        assert info["extends"] == "poolrooms" and info["description"] and info["tags"]
        assert config.load(name)["room"]["pier"] == config.load("poolrooms")["room"]["pier"]
    assert config.load("lavender_hall")["room"]["back_arches"] == [8.4]


def test_catalog_command_writes_the_page(tmp_path, monkeypatch, capsys):
    from wavegen import cli
    monkeypatch.delenv("WAVEGEN_PRESET_PATH", raising=False)
    cli.main(["presets", "catalog", "--out", str(tmp_path), "--no-render"])
    doc = (tmp_path / "PRESETS.md").read_text()
    assert doc == catalog.markdown(catalog.entries(), "presets")
    assert "PRESETS.md" in capsys.readouterr().out
