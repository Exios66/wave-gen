# Poolrooms rebuild: match the reference space

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Rebuild the poolroom geometry, composition and camera so the render reads like the reference clip (`docs/ref/ref_t*.jpg`). Keep the bouncing WAVE GEN screensaver readable and the loop seamless.

**Why:** The 1080p grade on 2026-11-15 scored 0.60/1, with layout 0.01/1. Colour and brightness were close; the space itself was wrong:

- No pier or tiled bay behind the CRT.
- Shallow beige alcoves with one centre glow.
- Almost no tile.
- Dark, mirror-like pool.
- The CRT too small and too far away.
- No camera move.

The owner chose a **parallax sweep**: a slow eased drift that keeps the CRT in the foreground while the space shifts behind it.

**Spec:** `docs/superpowers/specs/2026-11-14-poolrooms-v2-design.md`. This plan revises its look targets from the reference frames.

## Global constraints

- Every motion completes whole cycles per loop: `wavegen loopcheck` must pass.
- The CRT screen stays fully in frame on every frame, and the emblem stays readable.
- Keep the purple accent light and the approved WAVE GEN screensaver.
- Tests: `.venv/bin/python -m pytest -q`. Commits use the repo's git identity, with no co-author trailers.

## Reference framing (fractions of the frame, x from left, y from top; t03/t22 average)

| element | x | y |
|---|---|---|
| CRT body | 0.01–0.35 | 0.36–0.88 |
| CRT screen | 0.17–0.32 | 0.42–0.68 |
| pier behind CRT | 0.11–0.27 | 0.00–0.40 (visible above the CRT) |
| tiled bay, left of the pier | 0.00–0.10 | 0.20–0.45 |
| back-wall arches (left, centre) | 0.37–0.46, 0.52–0.75 | top ≈ 0.30, floor ≈ 0.65 |
| keyboard | 0.11–0.46 | 0.80–0.97 |
| pool, near edge | 0.42–1.0 | 0.68 |

## Tasks

### Task R1: Framing probe + composition test
- Create `wavegen/scene/framing.py` with `project_bounds(name: str, frame: int = 1) -> tuple[float, float, float, float]`: x0, x1, y0, y1 in frame fractions, y from top.
- Test `test_reference_framing` (tests/test_scene.py): CRT body, screen and pier fall within ±0.06 of the table at frame 1.
- Tune `camera.*`, `computer.*`, `desk.*` and `room.column_xy` until it passes.

### Task R2: Pier and tiled bay behind the CRT
- Replace the round column with a full-height **pier**: a rectangle with a semicircular front, `room.pier = {xy, width, depth}`, in plaster.
- Left of the pier, build a lit **tiled bay**: an inward box open toward the camera.
  - Tile wainscot up to 1.9 m, plaster above, and a barrel-vault ceiling.
  - A plaster front wall with an arch cut.
  - A warm area light inside.
- Test `test_pier_and_bay_exist`: the objects exist, and the bay light is inside the bay.

### Task R3: Deep alcoves with tile wainscot and twin sconces
- Add `M.wainscot(name, tile, grout, plaster, size, grout_w, height)`: white tile below `height`, plaster above (world Z).
- Alcove interiors use it. `palette.alcove_tile` becomes white tile with grey grout.
- Each alcove gets **two** sconces at x = centre ± (width/2 − 0.35), height `spring*0.6`, each with its own wall-washer at half power.
- Test `test_twin_sconces`: two sconce objects and two alcove lights per arch.

### Task R4: Floor tile and pool water
- Add `room.floor_tile_size` (0.30 m) with a separate FloorTile material.
- Pool depth 0.9 m. Lighten the water absorption so the tiled pool floor shows.
- Test `test_floor_uses_large_tiles` (material wiring).

### Task R5: Parallax sweep camera
- Add `camera.sweep = {amplitude: [x, y, z], target_amplitude: [...], cycles: 1}`: an eased single-cycle path (a two-sine `periodic_expr`) layered on the drift.
- Test `test_sweep_keeps_screen_in_frame`: sample 12 frames across the loop. The CRT screen stays inside [0.02, 0.98], and the camera moves at least 0.3 m peak-to-peak.
- `loopcheck` passes.

### Task R6: Dust
- The dust reads as blurry blobs. Shrink its size, cut its count and strength, and use no motion blur on the dust. The reference shows only a few tiny sparkles.

### Task R7: Grade and seam check
- 1080p still vs all references (contact sheet + scores).
- A 480×270 seam clip across the loop point.
- Send both to the owner.
