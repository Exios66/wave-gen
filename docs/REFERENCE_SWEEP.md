# Reference sweep: what still differs, and what else the toolkit can render

Swept 2026-11-15 against `docs/ref/video/v25.jpg`, `v50.jpg`, `v75.jpg` and
`thumb_closeup.jpg`, with a 1280×720 graded render of the `poolrooms` preset at
frame 1 beside them. Autoresearch score at the time: 0.7912.

## Remaining enhancements, largest visible gap first

### Composition
1. **Monitor size and position: already matched.** Measured after the sweep,
   the housing and screen sit within 0.03 of the reference's frame position
   (`test_reference_framing`). An earlier draft of this list called the monitor
   too small and turned the wrong way; the measurement shows that was wrong.
   What reads as "smaller" is the housing shape (item 14).
2. **Keyboard left the frame during the camera sweep** (4% off the left edge,
   3% off the bottom). Fixed: the keyboard now sits further right and back
   (`computer.keyboard`), matching the reference position, and a test checks
   the whole loop.

### Architecture
3. **Alcove tile stopped at 2.4 m (fixed).** In the reference the square white tile runs
   up to the arch, with visible grout, and the sconces sit on tile. Raise
   `room.alcove_wainscot` (or add a full-height option).
4. **Arch shape (fixed).** The arches are flat-topped with rounded corners and
   end level (`room.arch_corner_radius`), and the wide centre opening has a
   smaller warm-white arch set inside it (`room.nested_arch`).
5. **Left of frame (mostly fixed).** The passage behind the pier is tall, wider,
   tiled to the top like the alcoves, and has a visible warm wall lamp
   (`room.bay.sconce_power`). Still different: the reference's passage tile
   reads warm white with a strong glow; ours sits under the pink left-side wash
   (`post.pink_wash`), which covers more of the frame than the reference's
   narrow lavender strip.
6. **Ceiling (open).** The reference tray has a round medallion and a brighter
   cyan glow in the cove. A stepped medallion at the tray centre was built and
   dropped: our camera never sees the tray centre, and it shadowed the cove
   light (score 0.820 to 0.816). The real gap is framing: the reference's tray
   sits lower and nearer the camera than ours.
7. **Pool far corner.** The reference pool has a stepped notch at the far-left
   corner and a raised kerb of turquoise tile. Ours is a plain rectangle.

### Materials and light
8. **Floor colour (improved).** The floor now has its own lavender tile
   (`palette.floor_tile`); its colour error fell from 0.13 to 0.09 at matched
   brightness. Still missing: the soft lamp reflections on it.
9. **Water (improved).** Paler pool tile and absorption cut the water's colour
   error from 0.06 to 0.03, and the lamp halos (item 11) now reflect in it
   as large soft patches. Still missing: the reference's milkiness.
10. **Desk.** The reference desk is near-white with a pink cast; ours is a
    saturated periwinkle.
11. **Lamp glow (fixed).** Each alcove lamp now has a soft glow disc on the
    wall behind it (`lights.halo_radius`, `lights.halo_strength`), which also
    gives the large soft lamp reflections in the water. Global fixes were tried
    first and rejected: a lower bloom threshold or doubled bloom strength hazed
    the whole frame (score 0.82 to 0.78 and 0.80), and stronger lamp washers
    lowered the score (0.813 and 0.804).
12. **Small ceiling downlights.** The reference has a few bright points high on
    the right wall and ceiling. We have none.

### Camera and finish
13. **Film softness.** The reference is soft, slightly hazy and low-contrast,
    with visible dust sparkles near the camera. Ours is crisp. Options: a touch
    more haze, a light diffusion pass in post, larger and brighter dust.
14. **CRT model.** The reference housing is taller with a tilt foot, a rounded
    bezel and a darker, visibly curved glass. Ours is boxier with a floppy slot.
15. **Screen background (improved).** Darkened to a deep navy
    (`palette.screen_glow`), closer to the reference's near-black, with the
    purple emblem standing out more.

## Other poolscapes the same toolkit can render

Each is a preset: a JSON file of overrides on `wavegen/config.py`. Presets
`poolrooms_dusk` and `poolrooms_night` already exist.

### Possible today, with config values only
- **Rose Natatorium.** Blush plaster, cream tile, peach lamps, lilac water. The
  pink end of the reference's palette taken room-wide.
- **Midnight Lap Pool.** Indigo walls, dim cove, strong warm alcoves and a
  bright CRT; the screen becomes the main light. Extends `poolrooms_night`.
- **Long Gallery.** A narrow, deep room (`room.width` 9, `room.depth` 40) with
  four or five arches per side wall and a lap-lane pool, for a vanishing-point
  shot.
- **Mint Bathhouse.** Seafoam plaster, white tile, pale gold lamps, low ceiling
  with a deeper tray. A 1930s public-bath feel.
- **Lavender Hall.** High ceiling, a single very wide back arch, violet cove
  light and purple accent, matched to the WAVE GEN emblem palette.
- **Seeded parallels.** `wavegen variants --seeds …` already mutates any preset
  into near-relatives for a series.

### Need one new feature each
- **Skylight Atrium.** A roof opening with daylight shafts through the haze.
  Needs a ceiling cut-out and a sun lamp.
- **Glowing Pool.** Underwater lights so the water lights the room from below.
  Needs emissive fixtures in the basin.
- **Sunken Grotto.** A round or L-shaped pool with steps. Needs a non-rectangular
  pool outline.
- **Colonnade.** Free-standing columns around the pool instead of wall arches.
  Reuses the pier builder in a loop.
- **Window Wall.** Tall arched windows onto a gradient dusk sky. Needs glazed
  openings and a sky world.
