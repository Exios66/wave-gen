# Poolrooms v2: look-match, seamless loop, sound stems, GPU + Modal rendering

Status: draft for approval · 2026-11-14

## Intent and why

The user is building an idealised environment and soundscape. The first
product is a **seamless looping ambience video for YouTube** that matches the
look of their reference clip (`IMG_4290.mov`; see `docs/ANALYSIS.md`) as closely
as possible: a cyan tiled pool room, warm gold alcoves, a beige CRT computer,
drifting dust and a soft pastel grade. Viewers will watch it for long stretches,
often with lofi or other ambience layered on top. The environment should be
something they can keep extending (more moods, more rooms) rather than a
one-off.

v1 (this repo, commit `97ce087`) builds the scene procedurally, but it renders
**muted and flat** next to the reference. The comparison is in
`out/compare_ref_vs_v1.jpg`.

## Goals

1. **Look-match.** At 1080p, a still of the default preset reads as "the same
   place, same light" when put side by side with reference frame 5 (`docs/ref/ref_f05.jpg`, to be
   committed). The specific gaps to close, all observed in the comparison:
   1. Warm/cool contrast. The alcoves are creamy gold with bright lamp hotspots
      on their back walls, against cyan plaster. In v1 they are white-grey.
   2. Front-to-back sharpness. v1's depth of field (f/5.6 focused on the screen) blurs the
      room. The reference is sharp everywhere, so DOF is off by default.
   3. The tile grid reads clearly on the floor, pool walls, pool floor, coping and
      alcoves. The reference's tiles look ~12–15 cm with clearly visible
      light-grey grout.
   4. The pool is bright turquoise, with the tiled pool floor visible through the water,
      crisp gold reflections of the alcove lamps and a distinct tiled coping edge.
   5. A lavender/pink wash from the left on the computer and desk, fading
      across the frame (reference: lavender foreground, `#a598ab`).
   6. The computer reads as a detailed late-80s beige all-in-one: deeper
      front bezel with a thick rounded frame around the glass, a visible
      darker vent grille, a chunkier keyboard with legible key rows, and the
      body showing its left flank. Generic only: **no logos or brand-specific
      details**.
   7. The camera stays anchored: the computer remains in the lower-left
      third the whole time. Measured reference drift is ≤ ~4 % of frame width.
   8. Architectural depth: thicker arch surrounds (moulded reveals), deeper
      alcoves, a stepped coffered ceiling with visible shading between steps,
      and the near-left column visible in frame as in the reference.
   9. Value range: a high-key image (reference mean brightness ≈ 0.70) that
      still has shading. Darker reveals, under-arch shadow, and lamp
      hotspots that bloom.
2. **Perfect loop.** The rendered loop (default 60 s at 30 fps, configurable)
   plays end-to-start with no visible or audible seam. Every animated thing
   (camera, look-at target, dust, water, screensaver icon, CRT flicker if any)
   is periodic over the loop length.
3. **Sound as stems.** Each layer is exported as its own loop-seamless WAV of the
   same length as the video, plus a full mix:
   - `room` (water lapping, drips, air/room tone): the default bed under lofi
   - `crt` (very soft CRT hum/whine)
   - `bells` (glassy screensaver twinkles)
   - `pad` (the slowed maj9 chord pad)
   - `mix` (all of the above, balanced)

   The video's default audio track is `room` + `crt` only, so it never clashes
   with music laid on top. A flag selects `mix` instead.
4. **YouTube-ready outputs.** An MP4 loop at 1080p (default) or 2160p, graded,
   at a high-quality encode. An optional "extend" step concatenates the loop to a
   target duration (e.g. 1 h or 3 h) with stream copy, so it needs no re-encode.
5. **Render anywhere, same command.** The same CLI renders locally on the
   user's RTX 4070 (Cycles + OptiX) and on Modal cloud GPUs in parallel
   chunks, producing identical frames for the same config.

## Non-goals

- Real-time or interactive versions (Unreal, WebGL).
- New environments beyond the existing three presets (the structure must keep
  allowing them).
- Uploading to YouTube or any automated publishing.
- Writing lofi music. Users bring their own.

## Anti-goals (failure even if it "works")

- A visible jump, pop or audio click at the loop point.
- The default audio track containing tonal music that clashes with overlaid lofi.
- Branded or trademark-like details on the computer (logos, badges, a recognisable product silhouette).
- Default 1080p settings that can't render a 60 s loop overnight (~8 h) on an
  RTX 4070, i.e. a target of ≤ ~15 s per 1080p frame on that card.
- The cloud path silently spending money. It must show an estimate and ask
  for confirmation (or require `--yes`).

## Constraints

- Blender 5.x API (bpy pip module 5.3 on CPython 3.13 here; desktop Blender
  4.2+ must keep working via `scripts/blender_run.py`).
- This dev environment is **CPU-only** (≈3 min per 720p frame at 40 samples).
  Look-dev happens here on small stills (≈960×540). Full-quality renders run
  on the user's 4070 or Modal.
- Modal cannot be exercised for real from this environment (no credentials).
  The Modal app must be testable locally: chunking, orchestration and
  assembly are unit-tested with the Modal calls stubbed. The first real run is
  done by the user, following the README.
- Animation stays driver-based (simple expressions) so frames are independent,
  resumable and splittable across machines.

## Approaches considered (rendering side)

| | Approach | Trade-off |
|---|---|---|
| **A (chosen)** | One pipeline, two backends: local GPU, plus a Modal runner that renders frame chunks on N cloud GPUs in parallel and assembles the result | More to build now. No wall later for 4K or more environments. ~5–8 h per 1080p 60 s loop on the 4070, or <1 h on ~10 cloud GPUs (~$5–15) |
| B | Local 4070 only, cloud later | Less to build. 4K renders tie up the PC for a day or more |
| C | Generic container for any provider | Most portable, most setup and ops. Overkill until a switch is needed |

The user picked **A**, with the Modal integration built now.

## Decided design

### Look-match (scene + grade)

Changes to the existing modules (`wavegen/scene/*`, `config.py`, `post.py`):

- **Lighting.** The alcove lamps become the brightest sources in frame: warm
  (≈2700–3000 K) wall-washers aimed at the alcove back walls with a visible
  hotspot falloff (spot or area lights), plus brighter emissive sconce
  domes. The main room keeps the cool cyan cove light. The world/ambient level is lowered
  so shading appears. The lavender accent is reworked into a large soft
  source at frame-left whose influence clearly tints the computer, desk and
  near floor.
- **Camera.** DOF off by default (kept as an option). Drift amplitudes are
  reduced so the computer's screen-space position varies by ≤ 4 % of frame
  width. The look-at target drift is reduced accordingly.
- **Tiles.** Tile size ≈ 0.13 m, with grout wide enough to resolve at 1080p
  across the room (≈ 2.5–3 cm in world units is acceptable if needed for
  legibility). The grid shader extends to the pool floor and walls and the coping.
- **Water.** Brighter and more saturated turquoise. Lower absorption so the
  pool-floor tiles show. Smoother, lower-amplitude ripples so reflections stay
  crisp.
- **Architecture.** Arch openings get a moulded surround (an extruded profile
  frame around each arch). Alcoves get deeper. Coffered ceiling steps get
  a stronger depth/shade. The near-left column is positioned to appear in the
  default framing.
- **Computer.** Remodelled to goal 1.6 (still procedural, still generic).
- **Grade.** Tuned against the reference. The look-dev loop compares stills
  side by side with `ref_f05.jpg` and also checks the k-means palette of the
  render against the reference palette in `docs/ANALYSIS.md`. The user's eye is
  the final judge; the palette numbers are a sanity check, not a gate.

### Perfect loop

- New config `render.loop_seconds` (default 60). `render.seconds` is replaced by it
  for loop renders. Frames rendered: `1 … loop_seconds × fps`, and frame
  `N+1` must equal frame `1`.
- Every periodic motion uses an **integer number of cycles per loop**. Drift
  helpers take a cycle count instead of a period, and the drift expressions are
  built so that phase(frame 1) = phase(frame N+1).
- Dust: drift is purely periodic (the v1 linear "settle" term is removed or
  replaced by a periodic one).
- Water ripples: must be seamless over the loop. The technique is the builder's
  choice. A suggested option is two noise layers whose sample coordinates
  travel around closed circular paths with integer revolutions per loop.
- Screensaver icon: integer spins/tumbles per loop.
- Seam check: a test (or CLI `wavegen loopcheck`) that evaluates the scene at
  frame 1 and frame N+1 and asserts all driven transforms and node values match.
  An optional pixel diff of two rendered low-res frames must be at noise level.

### Sound stems

- `audio.py` produces each stem as a separate buffer, then the mix.
- Loop-seamless audio: synthesise `loop + tail` (tail = reverb length) and
  fold the tail back onto the start, so reverb and pad releases wrap around.
  Anything event-based (bells, drips) is scheduled on the loop timeline.
- Chord progression timing divides the loop length (e.g. 4 chords × 15 s).
- New `crt` stem: a very soft hum (≈60 Hz and harmonics) and a faint
  high whine, at a low level.
- CLI: `wavegen audio --stems` writes `room.wav`, `crt.wav`, `bells.wav`,
  `pad.wav` and `mix.wav`. `post` muxes `room+crt` by default and `mix` with
  `--audio-mix full`.

### Outputs

- `post` encodes the loop (H.264 high-quality CRF, yuv420p; 2160p optional).
  The grade must avoid banding on the large smooth gradients: fine grain is kept
  for that reason.
- `wavegen extend LOOP.mp4 --duration 1h -o long.mp4` concatenates the loop with
  stream copy.

### Rendering backends

- **Local GPU.** Cycles with OptiX auto-selected, a sample count and denoiser tuned
  to the ≤ 15 s per 1080p frame budget on a 4070, persistent data on,
  resumable frame ranges (already supported).
- **Modal** (`wavegen/cloud/modal_app.py`, plus `wavegen cloud …` CLI):
  - Image: Debian + the **official Blender Linux build** (for proven GPU
    support), ffmpeg and this package. The Blender version is pinned in config.
  - `render_chunk(config_json, frame_list) → frames` runs on a GPU function
    (default GPU type L4, configurable) and writes frames to a Modal Volume
    under `runs/<run_id>/frames/`.
  - The orchestrator splits the frame range into chunks (configurable size),
    fans them out with `.map()`, skips frames already present (resumable), then
    runs `assemble` (CPU: grade + encode + mux audio stems) in the cloud.
  - `wavegen cloud render --preset … --gpu L4 --workers 10` prints a cost/time
    estimate first and needs confirmation or `--yes`.
    `wavegen cloud fetch <run_id>` downloads the outputs.
  - Auth is the user's own Modal token on their machine. No secrets in the repo.

## Left to the builder

- Exact light types, powers and colours, as long as the look-match goals hold.
- Exact moulding profiles and computer modelling details, within goal 1.6.
- Water-loop technique.
- Default sample count and denoiser settings, within the 4070 budget.
  These are estimated from CPU timing, since no 4070 is available here; this is stated in the README.
- Chunk size, retry policy and Volume layout details for the Modal runner.
- Test structure, as long as loop seam, stems and cloud orchestration are covered.
