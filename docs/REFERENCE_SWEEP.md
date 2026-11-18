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
   (`room.bay.sconce_power`). The pink left-side wash now peaks a little in from the
   edge (`post.pink_wash.peak`, `.edge`), as measured in the clip, which cut
   the left-side pink error from 0.053 to 0.048. Still different: the
   reference's passage tile reads warm white with a strong glow. A stronger
   reshaping matched the pink better (0.042) but cost a point of score.
   A brighter passage lamp (`room.bay.sconce_power` 220 and 400) and a weaker
   wash (0.8) were also measured and scored lower (0.841, 0.842, 0.841 against
   0.847), so the passage is unchanged. Larger and brighter dust made no
   difference beyond run-to-run noise.
6. **Ceiling (improved).** The tray now reaches close to the walls
   (`room.ceiling_tray.inset` 2.0 to 0.6), so its stepped edge and cove glow
   sit where the reference frames them. This was the largest single gain of
   the sweep (score 0.828 to 0.847); insets of 1.6, 1.3 and 0.9 scored 0.828,
   0.831 and 0.840. A lower ceiling scored worse (0.811 at 5.8 m) and a taller
   one made no difference beyond noise. Still open: the reference's round
   medallion at the tray centre, which our camera never sees.
7. **Pool far corner (fixed).** The pool now has the reference's stepped notch
   in its far-left corner (`pool.notch`), with the lip following the step.
   The turquoise band at the reference's pool edge is the basin wall above
   the water, which we already show. A raised kerb clad in pool tile was
   built and measured (`pool.kerb`): it lowered the score (0.8247 to 0.8185)
   because it adds a turquoise strip along the near edge that the reference
   lacks, so the preset keeps the low white lip. The option stays for other
   presets.

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
12. **Small ceiling downlights (fixed).** A row of small warm discs now sits in
    the flat ceiling over the right walkway (`lights.downlights`), giving the
    reference's bright points high on the right. They are glowing discs only,
    with no lamp behind them, so they add no render time or noise.

### Where single settings stop helping
After the tray change (score 0.847), each of these was measured on its own and
none helped: a near-white or lavender-white desk (0.803, 0.817; the desk
covers a large part of the frame, so a colour that looks closer by eye moves
the whole palette), brighter alcove lamps or fill (0.840, 0.841), a stronger
vignette (0.811), and more or less haze (0.847, 0.845). Region by region the
render is now within about 0.1 of the references. What remains is the back
alcoves reading a little dark and the floor a little bright, which no single
setting fixes without costing elsewhere.

### Camera and finish
13. **Film softness (improved).** A light mist-filter pass in post
    (`post.diffusion`) mixes a wide blur of the frame back in, softening edges
    and lifting shadows. Measured: 0.1 raised the score (0.825 to 0.828); 0.2
    and above lowered it (0.818, 0.806) as tile detail washed out. Still open:
    the reference's dust sparkles near the camera are larger and brighter.
14. **CRT model (fixed).** The monitor is now a head overhanging a narrower,
    set-back foot, leaning back 4 degrees (`computer.tilt`). The front is plain
    (the floppy slot, LED and front grille are gone; cooling slots sit in the
    side of the foot), the bezel opening has rounded corners and the glass
    bulges more. The screen stays where the reference frames it.
15. **Screen background (improved).** Darkened to a deep navy
    (`palette.screen_glow`), closer to the reference's near-black, with the
    purple emblem standing out more.

## Other poolscapes the same toolkit can render

Each is a preset: a JSON file of overrides on `wavegen/config.py`. Presets
`poolrooms_dusk`, `poolrooms_night`, `rose_natatorium`, `lavender_hall`,
`palm_solarium`, `catenary_nave`, `lotus_court` and `moonlit_conservatory`
already exist; see [`PRESETS.md`](PRESETS.md) for thumbnails.

### Possible today, with config values only
- **Rose Natatorium** (`rose_natatorium`, done). Blush plaster, cream tile, peach
  lamps, lilac water. The pink end of the reference's palette taken room-wide.
- **Midnight Lap Pool.** Indigo walls, dim cove, strong warm alcoves and a
  bright CRT; the screen becomes the main light. Extends `poolrooms_night`.
- **Long Gallery.** A narrow, deep room (`room.width` 9, `room.depth` 40) with
  four or five arches per side wall and a lap-lane pool, for a vanishing-point
  shot.
- **Mint Bathhouse.** Seafoam plaster, white tile, pale gold lamps, low ceiling
  with a deeper tray. A 1930s public-bath feel.
- **Lavender Hall** (`lavender_hall`, done). High ceiling, a single very wide back arch, violet cove
  light and purple accent, matched to the WAVE GEN emblem palette.
- **Seeded parallels.** `wavegen variants --seeds …` already mutates any preset
  into near-relatives for a series.

### Nature and biomimicry (the `nature` section, now built)
- **Palm Solarium** (`palm_solarium`, done). Sun from beyond the far wall
  slants through a swaying leaf canopy as god rays (`nature.skylight.beams`)
  and dapples the pool floor; areca palms and ferns, lily pads on sea-green
  water. The camera stands back in the doorway, higher and looking down, so
  the water shows its floor instead of mirroring the room.
- **Catenary Nave** (`catenary_nave`, done). Gaudí's poolroom: hanging-chain
  (`room.catenary`) arches, tree columns that branch into the ceiling like the
  Sagrada Família's, a honeycomb floor (`room.floor_pattern: "hex"`).
- **Lotus Court** (`lotus_court`, done). The dusk room as a water garden,
  seen from the same doorway camera: clustered lily pads in bloom, ferns,
  honeycomb floor.
- **Moonlit Conservatory** (`moonlit_conservatory`, done). The night room with
  pale moonbeams slanting through the canopy into the haze.

Why the beams need their own haze: the room's haze is lit by the cove and
alcove lights everywhere, which lifts it as much as the sun lifts the shaft,
so no beam shows however thick it is. The beams get a second haze that the
room's lights are unlinked from (Cycles light linking). Bounced light and the
sky can't be unlinked, so they still reach it, and it fills only the sun's
shaft, the opening swept down-sun to the floor: there the sun outshines that
faint fill (about 3.5/255 with the sun off, on `palm_solarium`), and the rest
of the room stays clear. Beams read best looking toward the sun (azimuth ~155,
forward-scattering anisotropy 0.75).

### Need one new feature each
- **Glowing Pool.** Underwater lights so the water lights the room from below.
  Needs emissive fixtures in the basin.
- **Sunken Grotto.** A round or L-shaped pool with steps. Needs a non-rectangular
  pool outline.
- **Colonnade.** Free-standing columns around the pool instead of wall arches.
  Reuses the pier builder in a loop.
- **Window Wall.** Tall arched windows onto a gradient dusk sky. Needs glazed
  openings and a sky world.
