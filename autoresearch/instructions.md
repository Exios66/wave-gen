# Autoresearch: poolscape look

You are tuning how a wave-gen scene looks, one change at a time. Keep a change only if it scores better against the reference frames and no guard breaks.

## System context

wave-gen builds a Blender scene from a config dict: `wavegen/config.py` `DEFAULTS` with a preset JSON deep-merged on top. It renders that scene with Cycles and grades it with ffmpeg (`post.*`). `autoresearch/eval.py`:

1. Renders one still of the target preset at 480x270 with 24 samples and a fixed seed, so it is deterministic.
2. Applies the same post grade the video gets.
3. Scores the graded still against every reference frame of the target and averages the results.

## Constrained file

**Only edit the target's preset JSON**: `autoresearch/targets.json` → `<target>.preset`. For Round 1 that is `wavegen/presets/poolrooms.json`.

The preset may set any key that already exists in `DEFAULTS`, and only those. The eval reports a CRASH on unknown keys. Read `wavegen/config.py` DEFAULTS for each value's meaning and current setting. The levers, by section:

- `palette.*`: colours of plaster, ceiling, tiles, grout, water, lights.
  - Exception: `accent_light` must stay purple/violet. The owner wants those purple hues.
- `render.look`, `render.exposure`, `render.bloom.*`: the overall tone curve and glow.
- `lights.*`: powers, sizes, positions and spot/area types of the alcove, cove, fill and accent lights.
- `atmosphere.*`: haze density and dust.
- `room.*` (geometry):
  - `tile_size`, `grout_width`
  - `arch_surround.*`
  - `alcove_depth`
  - `spring_height`
  - `column_xy`
- `camera.location`, `camera.target`, `camera.lens`: composition. See the guard below.
- `post.*`: grade saturation/contrast, vignette, halation, chroma shift. Not `post.grain`: stills render without grain.

## Frozen (do not touch)

- Every `.py` file, the tests, `autoresearch/eval.py` and `autoresearch/targets.json`.
- These preset keys:
  - `render.samples`, `resolution`, `percentage`, `fps`, `seconds`, `device`, `motion_blur`. The eval overrides the first three anyway, and changing the others can only fake gains or break the video.
  - `computer.emblem.*` and `computer.screensaver`: the screensaver design is approved.
  - Anything that sets loop timing: drift periods or `*_period` keys. Amplitudes are fine.
- Reference frames in `docs/ref/`.

## Eval

```
.venv/bin/python autoresearch/eval.py --target poolrooms          # add --device GPU on an NVIDIA box
```

The eval prints each component, then these lines:

- `RENDER_SECONDS: …`
- `LOOPCHECK: PASS|FAIL`
- `SBS: <path>`: a side-by-side, render left and reference right
- `SCORE: X.XXXX`

## Metric

SCORE is a weighted mean of six 0..1 components. Each component is averaged over the target's reference frames.

| component | weight | what it rewards |
|---|---|---|
| palette | 0.25 | the reference's 5 main colours are present in the render |
| histogram | 0.20 | overall colour distribution (8³-bin RGB intersection) |
| layout | 0.20 | where light and dark sit: an 8x5 grid luma correlation |
| detail | 0.15 | edge density close to the reference's (tile lines, mouldings) |
| brightness | 0.10 | mean luma |
| contrast | 0.10 | luma spread |

- Baseline: see the config line in `autoresearch.jsonl`.
- **Min delta: 0.003.** The eval is deterministic, so anything smaller is too slight to matter visually.

## Guards (discard on any failure, status `guard_fail`)

1. `LOOPCHECK: PASS`.
2. `RENDER_SECONDS` ≤ 1.5 × the baseline's render seconds. Don't buy score with slower renders.
3. On every tentative keep, run `.venv/bin/python -m pytest -q tests/test_scene.py`, and it must pass. This keeps the CRT screen anchored in frame, the column in frame, the alcoves the brightest, and so on.
4. **Visual veto.** Open the `SBS` image on every tentative keep. Discard it if the render looks worse to a person, even when the score rose. Examples: blown-out walls, muddy colours, the purple accent gone, the computer cut off. The metric is a proxy, and you are the guard against gaming it.

## Loop

1. Make one focused change to the preset. Change one lever, or two that clearly belong together.
2. Run the eval and parse `SCORE`.
3. If score > best + 0.003 and guards 1–2 pass, run guard 3, then look at the SBS (guard 4).
   - **Keep:** `git add <preset> && git commit -m "look(autoresearch): <what changed> (+<delta>)"`. The repo's git identity is already set to the owner's, so add no co-author trailers.
   - **Otherwise discard:** `git checkout -- <preset>`.
4. Append a result line to `autoresearch/autoresearch.jsonl` and regenerate `autoresearch/autoresearch_dashboard.md`.

## Strategy (in order)

1. **Quick wins: global tone.** Try `render.exposure` in steps of ±0.1, then `render.look` (the AgX looks). Then try `post` saturation and contrast. Watch the brightness and contrast components: contrast is currently the weakest, 0.108 vs 0.159.
2. **Colour.** Nudge the `palette` entries toward the reference's dominant colours. The eval's JSON in `out/autoresearch/` doesn't list palettes, so run `python -m wavegen lookdev` once to see the hex values. Plaster, ceiling and water cover the most pixels.
3. **Light layout.** Work on `lights.alcove_power`/`alcove_fill`, `cove_power` and accent power/size. In the reference the alcoves glow warm and the far wall is bright.
4. **Detail.** Try `room.tile_size`, `grout_width` and the palette's grout contrast. The reference walls and floor read as fine white tile.
5. **Composition (last; riskiest).** Make small camera moves. The CRT must stay large on the left (guard 3).
6. **Plateau.** After 5 discards in a row in one area, move to the next area. After 8 in a row overall, stop and write the report.

## Do NOT

- Delete `out/autoresearch/` mid-run: the baseline images are there.
- Bump samples or resolution, or edit the eval to raise the score.
- Change several unrelated levers at once: you lose which one helped.
- Push. The owner reviews and pushes.

## Resuming

If you lose context, read `autoresearch/autoresearch.jsonl` (the config header plus every iteration) and `autoresearch/autoresearch_dashboard.md`. Continue from the last iteration number.

## Final report

Write `autoresearch/report.md` with:

- baseline vs best, with the component breakdown
- what helped, ranked by delta
- what didn't help, which saves the next round's budget
- whether the plateau is parametric or architectural. Missing geometry, such as tiled walls, needs code: that is Round 2, which unfreezes `wavegen/scene/materials.py`/`architecture.py` and adds the full test suite as a guard.
- recommended next steps, including which values to port to the other poolscape presets
