# Poolrooms rebuild: match the reference space

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Rebuild the poolroom geometry, composition and camera so the render reads like the reference clip (frames of the video itself in `docs/ref/video/`; the older `docs/ref/ref_t*.jpg` are phone photos of a TV and only a rough guide). Keep the bouncing WAVE GEN screensaver readable and the loop seamless.

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

## Reference framing (measured on the clean video frames `docs/ref/video/v25.jpg`; x from left, y from top)

The TV-photo refs (`docs/ref/ref_t*.jpg`) are skewed by the bezel and the phone glare. The clean frames from the source video are now the ground truth, and the autoresearch target scores against them.

| element | x | y |
|---|---|---|
| CRT body | 0.04–0.36 | 0.31–0.82 |
| CRT screen | 0.205–0.335 | 0.36–0.58 |
| pier behind CRT | 0.17–0.30 | top of frame to 0.32 |
| tiled side passage (left of pier) | 0.04–0.17 | 0.15–0.40 |
| back-wall arches | 0.39–0.47, 0.52–0.72, 0.78–0.89 | tops ≈ 0.27, base ≈ 0.57 |
| keyboard | 0.12–0.47 | 0.73–0.94 |
| pool | 0.43–1.0 | 0.60–0.85 |

## Video study (source video, frames at 25/50/75% plus the thumbnail)

- **Palette (sRGB medians).**
  - Walls: cyan (0.42, 0.71, 0.78).
  - Ceiling: teal (0.32, 0.62, 0.66).
  - Alcove tile: warm off-white (0.66, 0.66, 0.60).
  - Water: (0.36, 0.56, 0.58).
  - Desk and near floor: lavender (0.44–0.51, 0.49–0.53, 0.67–0.69). The purple lives in the foreground.
- **Alcoves.** They are deep and lit warm.
  - The back wall is white square tile up to about two-thirds of the opening, with plaster above.
  - Each back wall has two wall sconces.
  - The far side arches show sconces on their side walls too.
- **Space.** The back wall is far: the arches are small in frame, and a tiled walkway runs between the pool and the back wall.
  - The pool is long, bright and shallow, and its tiled floor shows through the water.
  - The pool outline steps in at the far end.
- **Behind the CRT.** A tall white pier with a rounded front; left of it, a white-tiled side passage lit from inside.
- **Camera.** The framing differs between the 25%, 50% and 75% frames, so the camera moves slowly through the space. The thumbnail is a closer push-in. This confirms the parallax sweep.
- **Atmosphere.** Light haze, soft bloom on the sconces, and a few tiny dust specks.

## Tasks

### Task R1: Framing probe + composition test
- Create `wavegen/scene/framing.py` with `project_bounds(name: str, frame: int = 1) -> tuple[float, float, float, float]`: x0, x1, y0, y1 in frame fractions, y from top.
- Test `test_reference_framing` (tests/test_scene.py): CRT body, screen and pier fall within ±0.06 of the table at frame 1.
- Tune `camera.*`, `computer.*`, `desk.*` and `room.column_xy` until it passes.

### Task R2: Pier and tiled bay behind the CRT
- Replace the round column with a full-height **pier**: a rectangle with a semicircular front, `room.pier = {xy, width, depth}`, in plaster.
- Left of the pier, build a lit **tiled bay**: an inward box open toward the camera.
  - Tile wainscot up to 1.9 m, plaster above, and a flat plaster ceiling (as built; a barrel vault was considered and dropped).
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
