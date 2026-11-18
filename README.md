# wave-gen

A procedural toolkit for **retro vaporwave / liminal "poolrooms"** scenes. It
builds the whole scene in Blender from a JSON preset and renders it. It also
synthesizes a matching slowed, reverb-heavy ambient soundtrack and grades and
encodes the final video.

It was built by reverse-engineering a reference clip: a beige CRT computer
glowing beside a turquoise indoor pool under arched, tiled alcoves. See
[`docs/ANALYSIS.md`](docs/ANALYSIS.md) for the shot-by-shot breakdown,
measured palette, audio analysis and design notes.

```
reference video ──► analyze ──► preset (JSON) ──► Blender scene ──► frames ─┐
                                    │                                        ├─► post (grade) ──► MP4
                                    └────────────► audio synth ──► WAV ──────┘
```

## Install

wave-gen needs **Blender 5.x** (5.3 tested); older versions stop with a clear error.

Option A uses Blender as a Python module (headless, good for servers or CI):

```bash
python3.13 -m venv .venv && . .venv/bin/activate   # bpy 5.x wheels are built for CPython 3.13
pip install -e '.[blender,dev]'
# Linux without a GPU also needs software EGL: apt install libegl1 libgl1-mesa-dri
```

Option B uses desktop Blender 5.x — 5.3 is the tested version (best for GPU rendering and for opening the result):

```bash
blender -b -P scripts/blender_run.py -- make --preset poolrooms -o out/poolrooms
```

You also need `ffmpeg` on your PATH for `analyze` and `post`.

## Use

```bash
python -m wavegen still   --preset poolrooms --frame 120 -o out/still.png   # one frame
python -m wavegen make    --preset poolrooms -o out/poolrooms               # full 26 s video + .blend + wav
python -m wavegen make    --preset poolrooms --preview -o out/draft         # fast draft
python -m wavegen build   --preset poolrooms_night --blend out/night.blend  # open & tweak in Blender
python -m wavegen variants --seeds 11 12 13 -o out/variants                 # "parallel versions"
python -m wavegen analyze my_reference.mov -o out/ref                       # palette / motion / pitch
python -m wavegen audio   --preset poolrooms_dusk -o out/dusk.wav
python -m wavegen post    out/poolrooms/frames --stems out/poolrooms/stems -o out/final.mp4   # --audio-mix full adds pad + bells
python -m wavegen extend  out/final.mp4 --stems out/poolrooms/stems --duration 1h -o out/final_1h.mp4
```

You can override any value without editing files:

```bash
python -m wavegen still --set camera.lens=18 --set palette.water=[0.7,0.9,1.0] \
                        --set room.back_arches=[2,2,5,2,2] --set post.crt_on_tv=true
```

### Presets

| preset | mood |
|---|---|
| `poolrooms` | faithful parallel of the reference: cyan tray light, warm alcoves, lavender foreground |
| `poolrooms_dusk` | builds on `poolrooms`: peach plaster, rose water, sweeter and slower pad |
| `poolrooms_night` | builds on `poolrooms`: after hours, deep blue, magenta neon, thick haze, long reverb |
| `rose_natatorium` | builds on `poolrooms`: blush plaster, cream tile, peach lamps, lilac water |
| `lavender_hall` | builds on `poolrooms`: a tall violet room with one wide back arch, in the emblem's purples |
| `palm_solarium` | builds on `poolrooms`: an ivory greenhouse, sun shafts through a leaf canopy into the haze, palms, ferns, lilies |
| `catenary_nave` | builds on `poolrooms`: Gaudí's poolroom, hanging-chain arches, branching tree columns, a honeycomb floor, sandstone and teal |
| `lotus_court` | builds on `poolrooms_dusk`: a dusk water garden, lily pads in bloom, ferns, honeycomb floor |
| `moonlit_conservatory` | builds on `poolrooms_night`: pale moonbeams slanting through the canopy into the haze, palms in the dark |
| `palm_solarium_doorway`, `lotus_court_doorway`, `moonlit_conservatory_doorway` | the same three rooms from the doorway: higher and looking down, so the pool floor's sun dapples and the lily pads show |

[`docs/PRESETS.md`](docs/PRESETS.md) shows every preset with a thumbnail and its family tree.

Presets build on one another. A new design names its parent and lists only
what it changes:

```json
{
  "extends": "poolrooms",
  "description": "Rose natatorium: blush plaster, cream tile, lilac water.",
  "tags": ["pink", "day"],
  "palette": {"plaster": [0.92, 0.70, 0.76], "water": [0.80, 0.78, 0.98]}
}
```

Everything else, from the room geometry to the grade, comes from the parent,
so improvements to `poolrooms` reach every preset built on it. A parent is
looked up beside the child first, then among the bundled presets. A key the
config does not have (a typo) is refused at load time. `description`, `tags`
and `_`-prefixed notes never change the render, so rewording them does not
invalidate frames you have already rendered.

### Your preset library

Set `WAVEGEN_PRESET_PATH` to one or more folders (separated like `PATH`) to
keep your own designs beside the bundled ones. Your folders are searched first,
and `presets save` writes to the first one.

```bash
export WAVEGEN_PRESET_PATH=~/poolroom-library
python -m wavegen presets                                  # every preset, its parent, tags, description
python -m wavegen presets show poolrooms_night --lineage   # poolrooms_night -> poolrooms
python -m wavegen presets show poolrooms_night --resolved  # the full config it renders with
# keep a tweak as a new design that lists only what it changes
python -m wavegen presets save rose_room --from poolrooms \
    --set palette.plaster=[0.92,0.70,0.76] --set palette.water=[0.80,0.78,0.98] \
    --description "Blush plaster, lilac water" --tags pink,day
# keep a seeded variant you liked
python -m wavegen variants --preset rose_room --seeds 3 -o out/variants
python -m wavegen presets save rose_room_tall --from rose_room --config out/variants/rose_room-v3/config.json
```

After adding or changing presets, refresh the catalog page and its thumbnails
(`--out` picks another folder, `--no-render` rewrites only the page):

```bash
python -m wavegen presets catalog          # docs/PRESETS.md + docs/presets/<name>.jpg
```

A saved preset is checked before it is kept: it must rebuild exactly the
config it was saved from, and a key the config does not have is refused.
`save` will not overwrite a preset, or hide a bundled one under the same name,
unless you pass `--force`.

`variants` derives new rooms from any preset by seed. It changes arch count and
widths, room proportions, pool footprint, lighting balance, palette, lens and
chord order, and the result is deterministic for a given seed.

## What's generated

- **Architecture:** tiled floor, sunken pool with coping, arched walls (boolean-cut; round, flat-topped, or Gaudi-style catenary with `room.catenary`) and lit tiled alcoves, a 3-step tray ceiling with a hidden cove light, crown mouldings, a rounded pier with a lit tiled passage beside it.
- **Materials:** a world-space tile shader (any orientation, per-tile jitter, grout bump, clearcoat; a honeycomb floor with `room.floor_pattern="hex"`), plaster, refractive water with animated 4D-noise ripples and absorption, aged beige plastic, and a CRT phosphor with scanlines, glow and glass.
- **Props:** a generic beige all-in-one CRT computer, keyboard and desk, plus a spinning, tumbling pastel screensaver icon.
- **Nature** (off unless a preset asks): a skylight with sun falling through a swaying leaf canopy,
  casting dappled light across walls and water (`nature.skylight`). With
  `nature.skylight.beams` a haze confined to the sun's shaft turns its path into
  god rays that stand out of the room's own glow. The room's lights are unlinked
  from it (Cycles light linking); bounced light and the sky still reach it, faintly.
  Potted areca palms and Boston ferns grown from the seed, swaying gently (`nature.plants`).
  Tree columns that branch into the ceiling like a forest nave (`nature.tree_columns`).
  Water lilies drifting in loose clusters on the pool, some in flower (`nature.lily_pads`).
- **Atmosphere:** volumetric haze, drifting dust motes, a floating camera with independent look-at drift, and depth of field focused on the screen.
- **Look:** AgX tone mapping, compositor bloom and lens dispersion, then an ffmpeg grade (lavender lift, halation, chroma shift, grain, vignette). An optional `crt_on_tv` mode adds the "filmed off a TV" look.
- **Sound:** a detuned maj9 pad slowed ×0.975, FM glass bells, water lapping and drips, a 4.8 s room reverb, tape wow and hiss.

All animation is driven by Blender *simple-expression drivers* (`frame`,
`sin`). Every frame is computed independently, so renders are resumable and can
be split across machines with `--frames 1-300`, `--frames 301-600` and so on.
No Python auto-run is needed to open the `.blend`.

## Render cost

Defaults are 1920×1080, Cycles, 96 samples with OIDN denoising, and haze on. On
a modern GPU that is roughly 5–20 s per frame. On a 4-core CPU it takes several
minutes per frame, so use `--preview` or `--engine eevee` (GPU) for
iteration. Setting `atmosphere.haze_density=0` is the biggest single speed-up.

## Tests

```bash
pytest            # config / audio / post tests; scene tests run when bpy is importable
```
