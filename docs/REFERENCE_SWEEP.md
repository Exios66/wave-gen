# Reference sweep: what still differs, and what else the toolkit can render

Swept 2026-11-15 against `docs/ref/video/v25.jpg`, `v50.jpg`, `v75.jpg` and
`thumb_closeup.jpg`, with a 1280×720 graded render of the `poolrooms` preset at
frame 1 beside them. Autoresearch score at the time: 0.7912.

## Remaining enhancements, largest visible gap first

### Composition
1. **The CRT is too small and too low.** In the reference it fills about a third
   of the frame width and its top reaches 30% from the top of the frame; ours
   fills about a fifth. Move the camera closer and lower the horizon
   (`camera.location`, `camera.lens`, `computer.location`).
2. **We see the wrong side of the CRT.** The reference shows the screen plus the
   housing's left flank, turned toward the pool; ours is turned the other way
   and the keyboard runs off the left edge. Re-pose with `computer.rotation_z`
   and the keyboard offset so the whole keyboard is in frame.

### Architecture
3. **Alcove tile stops at 2.4 m.** In the reference the square white tile runs
   up to the arch, with visible grout, and the sconces sit on tile. Raise
   `room.alcove_wainscot` (or add a full-height option).
4. **Arch shape.** The reference arches are flatter, with a wide rounded-corner
   centre opening and a second, smaller arched recess inside it. Ours are plain
   semicircles. Needs an arch-profile option and a nested recess.
5. **Left of frame.** The reference has a bright tiled passage with a warm lamp
   behind the rounded pier. Ours shows a plain plaster niche there. The bay
   exists (`room.bay`) but is not lit or tiled enough to read.
6. **Ceiling.** The reference tray has a round medallion and a brighter cyan
   glow in the cove. Ours has the tray but no medallion and a weaker glow.
7. **Pool far corner.** The reference pool has a stepped notch at the far-left
   corner and a raised kerb of turquoise tile. Ours is a plain rectangle.

### Materials and light
8. **Floor colour.** Still the worst-matched surface (colour error 0.09): the
   reference floor is a pale lavender white with soft lamp reflections; ours is
   cooler and bluer.
9. **Water.** The reference water is paler and milkier, with large soft
   reflections of each lamp. Ours is more saturated and shows the pool-floor
   tile through it. Raise absorption/tint and soften the reflections.
10. **Desk.** The reference desk is near-white with a pink cast; ours is a
    saturated periwinkle.
11. **Lamp glow.** The reference lamps bloom into a wide warm halo that lights
    the tile around them. Ours are small hot spots. Needs stronger sconce
    emission against a wider, softer wall wash.
12. **Small ceiling downlights.** The reference has a few bright points high on
    the right wall and ceiling. We have none.

### Camera and finish
13. **Film softness.** The reference is soft, slightly hazy and low-contrast,
    with visible dust sparkles near the camera. Ours is crisp. Options: a touch
    more haze, a light diffusion pass in post, larger and brighter dust.
14. **CRT model.** The reference housing is taller with a tilt foot, a rounded
    bezel and a darker, visibly curved glass. Ours is boxier with a floppy slot.
15. **Screen background.** The reference screen is near-black; ours is bright
    blue, which draws the eye. A darker blue would keep the purple emblem
    readable and sit closer to the reference.

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
