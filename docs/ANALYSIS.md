# Reference analysis: `IMG_4290.mov`

**Source:** a 26 s, 1920×1080, 30 fps clip shot on an iPhone. It is a phone
recording *of a TV* playing a 3D-rendered loop. A black band at the top is the
TV bezel, and screen moiré shows in the flat areas. The numbers below come from
`python -m wavegen analyze` plus manual frame inspection.

## 1. What's in the frame

| Layer | Observation | How wave-gen reproduces it |
|---|---|---|
| **Space** | An indoor "poolroom" (liminal / dreamcore architecture). Long rectangular pool sunk into a white-tiled floor, round-topped arches on the back and side walls, each opening into a shallow tiled alcove. Big rounded column on the near left. Stepped tray/coffered ceiling with a crown moulding. | `scene/architecture.py`: wall slabs with boolean arch cutters, inward-facing alcove boxes, pool basin + coping lip, 3-step tray ceiling, column with base and capital rings. |
| **Surfaces** | Small square glossy tiles (~15 cm) with light grout on the floor, pool and alcoves. Smooth, slightly glossy cyan plaster on the upper walls and ceiling. Everything is soft-edged (no hard corners). | `materials.tiles()`: world-space grid shader that works on any wall orientation, with per-tile brightness jitter, grout bump and a clearcoat. `materials.plaster()`. Bevel modifiers on all hard geometry. |
| **Water** | Still, clear, turquoise. Mirror-like reflections of the warm alcove lights, with a slow ripple. | Transmissive Principled BSDF (IOR 1.333) + absorption volume. Normal comes from 4D noise whose W is driven by `frame` (slow evolving ripples). |
| **Hero prop** | Beige late-80s all-in-one CRT computer in the lower-left foreground, turned ~3/4 to camera, with a keyboard in front. Vents and floppy slot on the front. | `scene/props.py`: a generic beige all-in-one (tapered CRT back, recessed bezel, curved glass, vents, slot, LED; no logos). Procedural keyboard with ~90 keycaps. |
| **Screen** | Deep blue CRT with a soft centre glow. A small multi-coloured "flower/star" icon spins and tumbles (a 3D screensaver). A few faint specks. | `materials.crt_screen()`: radial phosphor glow + scanlines + Fresnel glass reflection. Six emissive pastel petals on a pivot that spins around the screen normal and tumbles on two axes (driver-animated). |
| **Light** | Three moods mixed: (1) cool cyan ambient flooding from the ceiling tray, (2) warm 2700 K-ish wall-washers glowing inside each alcove, (3) a pink/lavender wash from off-screen left that tints the computer and desk. Highlights bloom softly. | `CoveLight` area light hidden in the tray, warm point lights + glowing sconce domes in every alcove, a lavender `AccentLight` disc, pale-cyan world. Compositor Bloom. |
| **Atmosphere** | Milky haze (raised blacks, low contrast). Tiny bright dust motes drift slowly across the frame. | Low-density Principled Volume box, ~220 emissive motes on smooth incommensurate-sine drift drivers with a slow settle. AgX view transform + post halation. |
| **Camera** | Locked framing with a very slow floating drift: max ~11 px horizontal / 6 px vertical at 256 px width (~4% of frame), ~1.6 px/s. No cuts. | `scene/camera.py`: camera and look-at target both drift on sums of incommensurate sines (26 s / 17 s / 11 s periods), so the move never visibly loops. |
| **Grade** | Pastel, low-contrast, cyan-dominant. Lavender in the shadows, cream in the highlights. Slight chromatic fringing, soft glow, fine grain. | `post.py` ffmpeg graph: `colorbalance` (lavender lift, warm gain), screen-blended blur (halation), `chromashift`, temporal `noise`, `vignette`. Optional `crt_on_tv` reproduces the "filmed off a TV" artefacts. |

### Measured palette (k-means, sRGB)

| Hex | Share | Role |
|---|---|---|
| `#a0c7e7` | 36% | cyan plaster walls / ceiling |
| `#85b2cc` | 24% | water, shaded walls |
| `#b1b8cc` | 19% | haze, tiles in cool light |
| `#a598ab` | 14% | lavender foreground (computer, desk) |
| `#d7d8d5` | — | warm-lit alcove tile |
| `#405191` | 4% | CRT blue |

Mean frame brightness is 0.70: a high-key image with almost no true blacks
besides the TV bezel.

## 2. The sound

Very quiet (−40 dBFS RMS on the phone mic). It's a sustained ambient pad with no
percussion. Its strongest tonal peaks are:

```
170 Hz  190 Hz  247 Hz  287 Hz  510 Hz  572 Hz  765 Hz
F3-47c  F#3+50c B3      D4-42c  C5-43c  D5-45c  G5-43c
```

Nearly every partial is **~43 cents flat**, which is a ×0.976 speed factor. That
is the signature "slowed + reverb" vaporwave treatment applied to a pad voiced
around **G major 9 / G7** (G B D F, plus C/D/G above). `audio.py` rebuilds it
from that recipe:

- a detuned additive pad on a slow maj9/m9 progression, every pitch × `tempo_slow = 0.975`
- sparse FM "glass" bells (the screensaver twinkle)
- band-limited noise "water lap" with slow swells, plus rare drips
- a 4.8 s synthetic room reverb (a tiled pool room is very live)
- tape wow, a little hiss, and fades

## 3. Brainstorm: ways to replicate it

1. **Blender + Python, procedural (chosen).** Every element is generated from a
   JSON preset, so a seed or edit gives a "parallel version" of the room rather
   than a copy. Cycles gives true glass/water refraction and soft GI, which is
   what sells this look. Eevee is supported for fast GPU previews. Blender is
   free, scriptable headless, and matches the quality bar.
2. **Unreal Engine 5 (Lumen).** Real-time and gorgeous for this kind of scene,
   but much heavier to script and version-control. A good next target if you
   want an interactive walk-through: the same layout data could be exported.
3. **Three.js / WebGL.** Real-time in a browser, but convincing refraction,
   soft GI and volumetric haze are far harder to get. Best for an interactive
   companion piece, not the hero video.
4. **AI video (img2vid).** Fast moodboards, but no control, no consistency and
   no "parallel versions" by parameter. It could be used for ideation only.

### Ideas for going further

- **Seamless loop:** pick drift periods that divide the clip length (e.g. 26 s, 13 s, 6.5 s) and set `wave_speed` so W wraps. That gives an infinite YouTube "ambience" loop.
- **Room generator:** chain rooms through the arches (a "backrooms" crawl) with a dolly that slowly travels from one to the next.
- **Caustics:** enable Cycles refractive caustics with a light under the water, or project an animated caustic texture onto the pool floor.
- **Screen content:** feed a rendered image sequence (old OS desktop, 3D pipes, starfield) into the CRT material via an Image Texture node.
- **Audio-reactive:** drive the bloom or screen brightness from the pad's envelope; `audio.synthesize` already returns the buffer.
