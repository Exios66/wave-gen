"""Preset / configuration handling.

A preset is a JSON file of nested sections. Every preset is deep-merged on
top of ``DEFAULTS`` so a preset only has to list what it changes. Values can be
overridden from the CLI with dotted keys, e.g. ``--set render.samples=32``.
"""
from __future__ import annotations

import copy
import json
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
        "grout": [0.34, 0.42, 0.46],
        "alcove_tile": [0.95, 0.84, 0.64],     # warm cream tiles inside the lit alcoves
        "plaster": [0.56, 0.86, 0.93],
        "ceiling": [0.42, 0.80, 0.92],
        "pool_tile": [0.16, 0.72, 0.76],
        "water": [0.45, 0.95, 0.90],
        "water_absorb": [0.25, 0.80, 0.78],
        "beige": [0.66, 0.56, 0.50],
        "key_cap": [0.72, 0.64, 0.58],
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
        "width": 15.0,
        "depth": 20.0,
        "height": 6.4,
        "wall_thickness": 0.45,
        "tile_size": 0.13,
        "grout_width": 0.022,       # wide enough to resolve at 1080p across the room
        "bevel": 0.05,
        "spring_height": 3.6,       # height where an arch starts curving
        "alcove_depth": 3.2,
        "arch_surround": {"width": 0.22, "depth": 0.12},   # moulded reveal around each arch
        "back_arches": [2.8, 4.6, 2.8],   # widths, left -> right
        "side_arches": [3.2],             # per side wall
        "ceiling_tray": {"inset": 2.0, "steps": 3, "step_height": 0.28},
        "column": True,             # big rounded column on the near-left
        "column_xy": [-1.9, 2.7],   # sits just behind the computer, as in the reference
    },
    "pool": {
        "x": [-2.6, 6.2],
        "y": [3.6, 13.0],
        "depth": 1.35,
        "water_level": -0.10,
        "coping": 0.30,             # width of the raised tiled lip
        "wave_scale": 1.6,
        "wave_strength": 0.18,
        "wave_cycles": 1,           # ripple evolutions per loop (whole number)
    },
    "computer": {
        "enabled": True,
        "location": [-1.0, 0.32, 0.86],    # sits on the desk
        "rotation_z": 55.0,                # degrees
        "scale": 1.0,
        "screen_strength": 2.4,
        "scanlines": 240,
        "screensaver": "emblem",           # emblem | starfield | mystify | flower
        "emblem": {
            "text": "WAVE GEN",
            "shape": "sun",                # sun | triangle | orb
            "font": None,                  # path to a .ttf/.otf; None = Blender's built-in font
            "scale": 0.34,                 # emblem width as a fraction of the screen width
            "speed": 0.12,                 # screen widths per second (rounded to whole bounces per loop)
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
    "desk": {"enabled": True, "size": [1.5, 1.05, 0.06], "top": 0.86, "center": [-1.04, 0.30]},
    "lights": {
        "alcove_type": "SPOT",       # SPOT (wall-wash hotspot) | AREA
        "alcove_power": 260.0,
        "alcove_radius": 0.08,
        "alcove_fill": 120.0,        # soft warm point light filling each alcove
        "sconces": True,
        "cove_power": 2200.0,
        "accent_power": 2400.0,
        "accent_size": 4.5,
        "accent_location": [-3.4, -0.2, 1.9],
        "world_strength": 0.35,
    },
    "atmosphere": {
        "haze_density": 0.0012,      # 0 disables the volume (much faster)
        "haze_anisotropy": 0.35,
        "dust_count": 220,
        "dust_size": [0.002, 0.006],
        "dust_strength": [1.0, 3.0],
        "dust_speed": 0.06,
    },
    "camera": {
        "location": [-0.5, -1.02, 1.05],
        "target": [0.8, 12.0, 2.3],
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
        "grain": 5,
        "vignette": 0.30,
        "chroma_shift": 2,
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


def list_presets() -> list[str]:
    return sorted(p.stem for p in PRESET_DIR.glob("*.json"))


def load(preset: str | None = None, overrides: list[str] | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if preset:
        path = Path(preset)
        if not path.exists():
            path = PRESET_DIR / f"{preset}.json"
        if not path.exists():
            raise FileNotFoundError(f"preset '{preset}' not found (have: {', '.join(list_presets())})")
        cfg = deep_merge(cfg, json.loads(path.read_text()))
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

    Deterministic for a given seed, so a good variant can be re-rendered.
    """
    rng = random.Random(seed)
    c = copy.deepcopy(cfg)
    c["seed"] = seed
    c["name"] = f"{cfg['name']}-v{seed}"
    s = strength
    room = c["room"]
    room["width"] *= 1 + rng.uniform(-0.15, 0.2) * s
    room["depth"] *= 1 + rng.uniform(-0.15, 0.25) * s
    room["height"] *= 1 + rng.uniform(-0.1, 0.2) * s
    room["spring_height"] = min(room["height"] - 2.0, room["spring_height"] * (1 + rng.uniform(-0.1, 0.15) * s))
    n_back = rng.choice([3, 3, 4, 5])
    widths = [round(rng.uniform(2.0, 3.0), 2) for _ in range(n_back)]
    widths[n_back // 2] = round(rng.uniform(3.4, 4.6), 2)
    room["back_arches"] = _fit(widths, room["width"])
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
