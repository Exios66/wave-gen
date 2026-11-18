"""Preset / configuration handling.

A preset is a JSON file of nested sections that lists only what it changes.
``"extends": "<preset>"`` builds it on another preset (which may itself extend
one); the chain ends on ``DEFAULTS``. Values can be overridden from the CLI
with dotted keys, e.g. ``--set render.samples=32``.

Library notes (``extends``, ``description``, ``tags`` and any ``_``-prefixed
key) describe a preset and never reach the config, so rewording them does not
invalidate rendered frames. Any other key the config does not have is refused.
"""
from __future__ import annotations

import copy
import json
import os
import random
from pathlib import Path

PRESET_DIR = Path(__file__).parent / "presets"

# Colors are linear-ish RGB in 0..1 (Blender takes scene-linear values).
DEFAULTS: dict = {
    "name": "poolrooms",
    "seed": 4290,
    "render": {
        "engine": "cycles",          # cycles | eevee
        "device": "AUTO",            # AUTO | CPU | GPU  (Cycles only)
        "resolution": [1920, 1080],
        "percentage": 100,
        "fps": 30,
        "seconds": 60.0,            # loop length; every motion completes whole cycles
        "samples": 96,
        "denoise": True,
        "max_bounces": 6,
        "view_transform": "AgX",
        "look": "AgX - Medium High Contrast",
        "exposure": -1.3,
        "gamma": 1.0,
        "motion_blur": 0.5,          # shutter in frames; 0 disables (smooth dust / camera motion)
        "bloom": {"threshold": 1.4, "strength": 0.4, "size": 0.7},   # only lamps bloom; no milky veil
        "lens": {"distortion": -0.012, "dispersion": 0.012},
        "format": "PNG",             # PNG frames -> post.py assembles MP4
    },
    "palette": {
        "tile": [0.90, 0.93, 0.94],
        "tile_jitter": 0.035,
        "floor_tile": None,                    # None = same as tile
        "grout": [0.34, 0.42, 0.46],
        "alcove_tile": [0.92, 0.91, 0.88],     # white square tile inside the alcoves (lit warm)
        "alcove_grout": [0.55, 0.56, 0.58],
        "alcove_plaster": [0.94, 0.91, 0.86],  # warm white above the alcove tile
        "plaster": [0.56, 0.86, 0.93],
        "ceiling": [0.42, 0.80, 0.92],
        "pool_tile": [0.16, 0.72, 0.76],
        "water": [0.45, 0.95, 0.90],
        "water_absorb": [0.25, 0.80, 0.78],
        "beige": [0.70, 0.50, 0.34],
        "key_cap": [0.70, 0.57, 0.45],
        "desk": [0.74, 0.70, 0.86],
        "screen": [0.02, 0.04, 0.30],
        "screen_glow": [0.06, 0.12, 0.62],
        "warm_light": [1.0, 0.72, 0.42],
        "cool_light": [0.52, 0.88, 1.0],
        "accent_light": [0.82, 0.42, 1.0],
        "world": [0.38, 0.72, 0.92],
        "haze": [0.78, 0.90, 1.0],
        "dust": [1.0, 0.97, 0.95],
        "icon": [[1.0, 0.45, 0.65], [1.0, 0.85, 0.35], [0.45, 1.0, 0.65],
                 [0.40, 0.75, 1.0], [0.75, 0.50, 1.0], [1.0, 0.60, 0.40]],
    },
    "room": {
        "width": 16.0,
        "depth": 26.0,
        "height": 6.4,
        "wall_thickness": 0.45,
        "tile_size": 0.13,
        "floor_tile_size": 0.30,    # big square floor tiles, as in the video
        "grout_width": 0.022,       # wide enough to resolve at 1080p across the room
        "bevel": 0.05,
        "spring_height": 3.6,       # height where an arch starts curving
        "alcove_depth": 3.2,
        "alcove_tile_size": None,   # None = same as tile_size; the clip's alcove tiles are larger
        "alcove_wainscot": 2.4,     # alcove walls: tile below this height, plaster above
        "arch_corner_radius": None,  # None = round-topped arches; a radius gives flat tops with rounded corners
        "arch_surround": {"width": 0.22, "depth": 0.12},   # moulded reveal around each arch
        # a second, smaller arch set inside one back alcove: {"arch": index into back_arches,
        # "inset": m narrower per side, "drop": m lower, "depth": m behind the wall, "thickness": m, "color": optional plaster colour}
        "nested_arch": None,
        "back_arches": [3.0, 5.4, 3.0],   # widths, left -> right
        "side_arches": [3.2, 3.2],       # per side wall
        "ceiling_tray": {"inset": 2.0, "steps": 3, "step_height": 0.28},
        "column": True,             # the pier + tiled passage behind the computer
        "pier": {"xy": [-3.0, 6.2], "width": 1.1, "depth": 1.0},   # rounded front faces the camera
        # lit passage left of the pier; sconce_power > 0 adds a visible wall lamp on its back wall
        "bay": {"width": 2.2, "depth": 3.4, "height": 3.0, "wainscot": 1.9, "sconce_power": 0.0, "sconce_at": 0.5,
                "sconce_height": None},   # sconce_at: 0..1 across the back wall; height None = alcove lamp height
    },
    "pool": {
        "x": [-2.6, 6.2],
        "y": [3.6, 18.5],          # long pool; a tiled walkway runs on to the back wall
        "depth": 0.9,
        "water_level": -0.10,
        "coping": 0.30,             # width of the raised tiled lip
        "kerb": {"height": 0.05, "pool_tile": False},   # lip height; pool_tile = clad it in the pool's tile
        "notch": None,              # [width, depth] of a step filling the far-left corner; None = plain rectangle
        "wave_scale": 1.6,
        "wave_strength": 0.18,
        "wave_cycles": 1,           # ripple evolutions per loop (whole number)
        "caustics": {"scale": 1.8, "strength": 0.9, "color": [0.80, 1.0, 0.97]},   # light lines on the pool floor
    },
    "computer": {
        "enabled": True,
        "location": [-1.0, 0.32, 0.86],    # sits on the desk
        "rotation_z": 55.0,                # degrees
        "scale": 1.0,
        "depth": 0.48,                     # housing depth (m); the front stays put, the tube grows back
        "tilt": 0.0,                       # degrees the monitor head leans back on its foot
        "keyboard": {"offset": [-0.10, -0.44], "yaw": -10.0},   # in the computer's own frame: x right, y back (m, degrees)
        "screen_strength": 2.4,
        "scanlines": 240,
        "screensaver": "emblem",           # emblem | flower
        "emblem": {
            "text": "WAVE GEN",
            "shape": "sun",                # sun | triangle | orb
            "font": None,                  # path to a .ttf/.otf; None = Blender's built-in font
            "scale": 0.56,                 # emblem width as a fraction of the screen width (the text spans it)
            "speed": 0.06,                 # screen widths per second (rounded to whole bounces per loop)
            "margin": 0.04,                # keep clear of the bezel (fraction of the screen)
            "palette": [                   # disc gradient [top, bottom]; steps on every wall hit.
                [[1.0, 0.45, 0.72], [0.52, 0.26, 0.95]],   # pink -> violet
                [[0.40, 0.88, 1.0], [0.58, 0.34, 1.0]],    # cyan -> purple
                [[1.0, 0.70, 0.55], [0.78, 0.32, 0.88]],   # peach -> magenta-purple
                [[0.80, 0.66, 1.0], [0.40, 0.30, 0.90]],   # lavender -> indigo
            ],
        },
        "icon_spin_period": 5.0,           # flower mode: seconds per turn
        "icon_tumble_period": 7.5,
    },
    "desk": {"enabled": True, "size": [1.5, 1.30, 0.06], "top": 0.86, "center": [-1.04, 0.175],
             "roughness": 0.3, "coat": 0.0},      # laminate gloss; the clip's desk is a polished top
    "lights": {
        "alcove_type": "SPOT",       # SPOT (wall-wash hotspot) | AREA
        "alcove_power": 260.0,
        "alcove_radius": 0.08,
        "alcove_height": 0.6,        # sconce height as a fraction of room.spring_height
        "alcove_fill": 120.0,        # soft warm point light filling each alcove
        "sconces": True,
        "halo_radius": 0.0,          # > 0: a soft glow disc of this radius on the wall behind each alcove lamp
        "halo_strength": 4.0,
        # small bright discs in the flat ceiling over the right walkway; span = where the row
        # starts and ends as fractions of the room's depth
        "downlights": {"count": 0, "radius": 0.06, "strength": 25.0, "span": [0.3, 0.9]},
        "cove_power": 2200.0,
        "accent_power": 2400.0,
        "accent_size": 4.5,
        "accent_location": [-3.4, -0.2, 1.9],
        "world_strength": 0.35,
    },
    "atmosphere": {
        "haze_density": 0.0022,      # 0 disables the volume (much faster)
        "haze_anisotropy": 0.35,
        "dust_count": 220,
        "dust_size": [0.002, 0.006],
        "dust_strength": [1.0, 3.0],
        "dust_speed": 0.06,
    },
    "camera": {
        "location": [-0.5, -1.02, 1.05],
        "target": [-0.4, 12.0, 1.6],
        "lens": 26.0,
        "dof": False,               # the reference is sharp front to back
        "fstop": 5.6,
        "focus_on": "computer",       # computer | target | <distance in m>
        "drift": {                      # slow "floating" camera
            "amplitude": [0.04, 0.025, 0.012],
            "period": [26.0, 17.0, 11.0],
            "target_amplitude": [0.13, 0.08, 0.05],
            "target_period": [31.0, 19.0, 13.0],
        },
        # one slow swing per loop: the camera slides sideways while its target pans with it, so the
        # nearby CRT stays put and the pier, arches and pool slide past behind it
        "sweep": {"amplitude": [0.22, 0.10, 0.02], "target_amplitude": [-1.6, 0.0, 0.15], "cycles": 1},
    },
    "audio": {
        "enabled": True,
        "sample_rate": 48000,
        "tempo_slow": 0.975,          # the source audio is ~2.5% "slowed"
        "chords": [                   # one pass per loop: each chord lasts loop / len(chords)
            ["G2", "D3", "F#3", "B3", "A4", "D5"],
            ["E2", "B2", "G3", "D4", "F#4", "B4"],
            ["C3", "G3", "B3", "E4", "F#4", "D5"],
            ["D2", "A2", "E3", "F#3", "C4", "G4"],
        ],
        "reverb_seconds": 4.8,
        "reverb_mix": 0.45,
        "wow_depth": 0.0025,
        # Each layer renders into a stem. Add your own with wavegen.audio.layers.register.
        "layers": [
            {"type": "room_tone", "stem": "room", "level": 0.10, "hiss": 0.12},
            {"type": "water", "stem": "room", "level": 0.16},
            {"type": "drips", "stem": "room", "level": 0.10, "per_minute": 8},
            {"type": "crt_hum", "stem": "crt", "level": 0.03, "hum_hz": 60, "whine_hz": 15734},
            {"type": "bells", "stem": "bells", "level": 0.15, "density": 0.55},
            {"type": "pad", "stem": "pad", "level": 0.55},
        ],
    },
    "post": {
        "grade": True,
        "halation": 0.22,
        "diffusion": 0.0,             # 0..1 mist-filter softness: mixes in a wide blur of the whole frame
        "grain": 5,
        "vignette": 0.30,
        "chroma_shift": 2,
        # left-side tint, strength 0 = off; peak > 0 moves the strongest tint in from the edge, where it is `edge`
        "pink_wash": {"strength": 0.0, "color": [1.0, 0.80, 0.92], "extent": 0.45, "peak": 0.0, "edge": 0.0},
        "crt_on_tv": False,           # re-photograph look (moire/scan + bezel)
        "crf": 16,
    },
}


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


LIBRARY_KEYS = ("extends", "description", "tags")


def library_dirs() -> list[Path]:
    """Where presets are looked up: the folders in ``WAVEGEN_PRESET_PATH`` (your own
    library, searched first), then the bundled presets."""
    extra = [Path(p).expanduser() for p in os.environ.get("WAVEGEN_PRESET_PATH", "").split(os.pathsep) if p]
    return extra + [PRESET_DIR]


def list_presets() -> list[str]:
    names: list[str] = []
    for d in library_dirs():
        names += [p.stem for p in d.glob("*.json") if p.stem not in names]
    return sorted(names)


def find_preset(ref: str, near: Path | None = None) -> Path:
    """Path of preset ``ref``: a path as given, else ``<ref>.json`` beside the preset that
    asked for it (``near``), else in your library folders, else a bundled preset."""
    path = Path(ref)
    if path.suffix == ".json" and path.exists():
        return path
    for d in ([Path(near)] if near else []) + library_dirs():
        cand = d / (ref if ref.endswith(".json") else f"{ref}.json")
        if cand.exists():
            return cand
    if path.exists():
        return path
    raise FileNotFoundError(f"preset '{ref}' not found (have: {', '.join(list_presets())})")


def diff_config(cfg: dict, base: dict) -> dict:
    """The smallest override that turns ``base`` into ``cfg``: nested keys whose values
    differ (lists and non-dict values are compared and kept whole)."""
    out = {}
    for k, v in cfg.items():
        if k not in base:
            out[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and isinstance(base[k], dict):
            sub = diff_config(v, base[k])
            if sub:
                out[k] = sub
        elif v != base[k]:
            out[k] = copy.deepcopy(v)
    return out


def _read(path: Path) -> dict:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"preset {path} must be a JSON object")
    return data


def _chain(ref: str, near: Path | None = None) -> list[tuple[Path, dict]]:
    """``[(path, body), ...]`` from the named preset back to its root ancestor."""
    out: list[tuple[Path, dict]] = []
    seen: list[str] = []
    child = None
    while ref is not None:
        try:
            path = find_preset(ref, near)
        except FileNotFoundError:
            if child is None:
                raise
            raise FileNotFoundError(f"preset '{child.stem}' extends '{ref}', which was not found "
                                    f"(have: {', '.join(list_presets())})") from None
        key = str(path.resolve())
        if key in seen:
            names = [p.stem for p, _ in out] + [path.stem]
            raise ValueError(f"presets extend each other in a loop: {' -> '.join(names)}")
        seen.append(key)
        body = _read(path)
        out.append((path, body))
        child, near, ref = path, path.parent, body.get("extends")
    return out


def unknown_keys(over: dict, base: dict, path: str = "") -> list[str]:
    """Dotted keys in ``over`` that ``base`` does not define (library notes excepted)."""
    bad = []
    for k, v in over.items():
        p = f"{path}{k}"
        if str(k).startswith("_") or (not path and k in LIBRARY_KEYS):
            continue
        if k not in base:
            bad.append(p)
        elif isinstance(v, dict) and isinstance(base[k], dict):
            bad += unknown_keys(v, base[k], p + ".")
    return bad


def _strip_notes(node):
    if isinstance(node, dict):
        return {k: _strip_notes(v) for k, v in node.items() if not str(k).startswith("_")}
    return node


def lineage(preset: str) -> list[str]:
    """Names from ``preset`` back to its root ancestor, e.g. ``["dusk", "poolrooms"]``."""
    return [p.stem for p, _ in _chain(preset)]


def preset_info(preset: str) -> dict:
    """The library notes of one preset (not its parents')."""
    path, body = _chain(preset)[0]
    return {"name": body.get("name", path.stem), "extends": body.get("extends"),
            "description": body.get("description", ""), "tags": list(body.get("tags", [])), "path": str(path)}


def load(preset: str | None = None, overrides: list[str] | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if preset:
        chain = _chain(preset)
        for path, body in chain:
            bad = unknown_keys(body, DEFAULTS)
            if bad:
                raise ValueError(f"preset '{path.stem}' sets keys the config does not have: {', '.join(bad)}")
        for path, body in reversed(chain):          # root ancestor first, the named preset last
            over = {k: v for k, v in _strip_notes(body).items() if k not in LIBRARY_KEYS}
            cfg = deep_merge(cfg, over)
        leaf_path, leaf = chain[0]
        cfg["name"] = leaf.get("name", leaf_path.stem)
    for item in overrides or []:
        set_dotted(cfg, item)
    return cfg


def set_dotted(cfg: dict, assignment: str) -> None:
    """Apply ``a.b.c=value``; value is parsed as JSON when possible."""
    key, _, raw = assignment.partition("=")
    if not _:
        raise ValueError(f"override must look like key=value, got {assignment!r}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    node = cfg
    parts = key.split(".")
    for p in parts[:-1]:
        node = node[int(p)] if isinstance(node, list) else node.setdefault(p, {})
    if isinstance(node, list):
        node[int(parts[-1])] = value
    else:
        node[parts[-1]] = value


def min_wall_for(widths: list[float], pier: float = 0.6) -> float:
    """Shortest wall that fits openings of ``widths`` with ``pier`` between/around them."""
    return sum(widths) + pier * (len(widths) + 1)


def _fit(widths: list[float], wall: float, pier: float = 0.6, margin: float = 0.05) -> list[float]:
    """Drop arches, then shrink the rest proportionally, until they fit ``wall`` with full
    piers. A wall too short for one opening between two piers gets none (``[]``)."""
    widths = list(widths)
    while len(widths) > 1 and sum(widths) * 0.6 + pier * (len(widths) + 1) > wall:
        widths.pop(0 if len(widths) % 2 == 0 else -1)  # keep the wide centre arch
    room = wall - pier * (len(widths) + 1) - margin
    if room <= 0.1:
        # one opening at most; none if even a 0.1 m opening can't sit between two full piers
        w = round(wall - 2 * pier - margin, 2)
        return [w] if w >= 0.1 else []
    if sum(widths) > room:
        k = room / sum(widths)
        widths = [round(w * k - 0.005, 2) for w in widths]
    return widths


def _jitter(rng: random.Random, color, amount):
    return [min(1.0, max(0.0, c + rng.uniform(-amount, amount))) for c in color]


def mutate(cfg: dict, seed: int, strength: float = 1.0) -> dict:
    """Make a 'parallel version' of a scene: same language, new layout/colors.

    Deterministic for a given seed, so a good variant can be re-rendered. ``strength``
    scales the continuous changes (sizes, colours, camera); the layout choices (arch
    count, pool position, lens) are redrawn at any strength above zero, and zero
    returns the scene unchanged apart from its seed and name.
    """
    rng = random.Random(seed)
    c = copy.deepcopy(cfg)
    c["seed"] = seed
    c["name"] = f"{cfg['name']}-v{seed}"
    s = strength
    if s <= 0:
        return c
    room = c["room"]
    room["width"] *= 1 + rng.uniform(-0.15, 0.2) * s
    room["depth"] *= 1 + rng.uniform(-0.15, 0.25) * s
    room["height"] *= 1 + rng.uniform(-0.1, 0.2) * s
    room["spring_height"] = min(room["height"] - 2.0, room["spring_height"] * (1 + rng.uniform(-0.1, 0.15) * s))
    n_back = rng.choice([3, 3, 4, 5])
    widths = [round(rng.uniform(2.0, 3.0), 2) for _ in range(n_back)]
    widths[n_back // 2] = round(rng.uniform(3.4, 4.6), 2)
    room["back_arches"] = _fit(widths, room["width"])
    if room.get("nested_arch"):                 # keep the nested arch in the wide opening of the new layout
        room["nested_arch"]["arch"] = room["back_arches"].index(max(room["back_arches"]))
    side = [round(rng.uniform(2.4, 3.6), 2) for _ in range(rng.choice([1, 1, 2]))]
    room["side_arches"] = _fit(side, room["depth"] - 6.0)
    room["column"] = rng.random() < 0.75
    pool = c["pool"]
    w = room["width"]
    pool["x"] = [round(-w * rng.uniform(0.12, 0.22), 2), round(w * rng.uniform(0.3, 0.42), 2)]
    pool["y"] = [round(rng.uniform(3.2, 4.4), 2), round(room["depth"] * rng.uniform(0.6, 0.72), 2)]
    pal = c["palette"]
    for k in ("plaster", "ceiling", "pool_tile", "water", "world", "cool_light"):
        pal[k] = _jitter(rng, pal[k], 0.06 * s)
    pal["warm_light"] = _jitter(rng, pal["warm_light"], 0.05 * s)
    pal["accent_light"] = _jitter(rng, pal["accent_light"], 0.12 * s)
    c["lights"]["cove_power"] *= rng.uniform(0.8, 1.25)
    c["lights"]["alcove_power"] *= rng.uniform(0.8, 1.3)
    cam = c["camera"]
    cam["location"] = [cam["location"][0] + rng.uniform(-0.4, 0.4) * s,
                       cam["location"][1] + rng.uniform(-0.3, 0.3) * s,
                       cam["location"][2] + rng.uniform(-0.1, 0.2) * s]
    cam["lens"] = rng.choice([22.0, 24.0, 24.0, 28.0])
    c["computer"]["rotation_z"] = rng.uniform(18, 36)
    c["audio"]["chords"] = rng.sample(cfg["audio"]["chords"], len(cfg["audio"]["chords"]))
    return c
