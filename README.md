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
python -m wavegen post    out/poolrooms/frames -a out/poolrooms/ambience.wav -o out/final.mp4
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
| `poolrooms_dusk` | peach plaster, rose water, sweeter and slower pad |
| `poolrooms_night` | after hours: deep blue, magenta neon, thick haze, long reverb |

`variants` derives new rooms from any preset by seed. It changes arch count and
widths, room proportions, pool footprint, lighting balance, palette, lens and
chord order, and the result is deterministic for a given seed.

## What's generated

- **Architecture:** tiled floor, sunken pool with coping, arched walls (boolean-cut) and lit tiled alcoves, a 3-step tray ceiling with a hidden cove light, crown mouldings and a rounded column.
- **Materials:** a world-space tile shader (any orientation, per-tile jitter, grout bump, clearcoat), plaster, refractive water with animated 4D-noise ripples and absorption, aged beige plastic, and a CRT phosphor with scanlines, glow and glass.
- **Props:** a generic beige all-in-one CRT computer, keyboard and desk, plus a spinning, tumbling pastel screensaver icon.
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
