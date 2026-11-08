# Day 8 — Utopia: a car-free Waterloo Bridge to Covent Garden

## Intent

Tom loves cycling and walking. The theme is "Utopia: a map of something which could be."
The map re-imagines one central London corridor with the cars gone: Waterloo Bridge and
the Strand fully pedestrianised, people flowing from Waterloo station across the Thames,
up past the Strand and into Covent Garden. Oxford Circus pedestrianisation is "just the
start"; this is the next step, and it should read as plausible and joyful, not as a
fantasy or an empty render.

The hook is movement: you see people walking, the road surface itself is now theirs.

## Scope of this build

Utopia only. One map, one scenario. The "now" version and the before/after comparison
are a later extension (see below), but this build must not paint itself into a corner.

## The corridor

Waterloo station (concourse exits / Waterloo Road) → Waterloo Bridge → Lancaster Place →
Strand (including the Aldwych / St Mary le Strand stretch, already car-free since 2022)
→ Wellington Street / Southampton Street → Covent Garden piazza.
Exact bounding box and side streets included: builder's call, keep it tight to that route.

## What the viewer sees

- **3D city**: MapLibre basemap with extruded buildings (OSM building heights), tilted
  view. The former carriageway on the bridge and Strand should visibly be walkable space,
  not a road (e.g. restyle or overlay the road surface as plaza). How: builder's call.
- **People everywhere on the road surface**: walkers move in all directions along the
  corridor and zigzag across the full width of the former road, not confined to
  pavements or crossings. Not "crossing the road" — drifting over it diagonally, the way
  people use a plaza. They must never walk through buildings or into the river.
- **Cyclists**: present and distinct from walkers (colour, speed, straighter lines).
  (Claude's call: cyclists keep a loose clear lane down the middle of the bridge and
  Strand so it reads as a working city, not a festival.)
- **Zoom behaviour**: zoomed out (below ~zoom 17), people render as glowing animated
  trails (deck.gl TripsLayer). Zoomed in (~17+), they render as little 3D walking
  figures (deck.gl ScenegraphLayer with an animated glTF, e.g. Khronos CesiumMan, walk
  cycle playing). Both driven from the same trip data so they agree.
- **Camera**: opens with a scripted fly-through (high over the river → down onto the
  bridge → along the Strand → into the Covent Garden piazza), roughly 30–45s, with a
  Skip button. Then the viewer explores freely. A Replay tour button stays available.
- Animation loops seamlessly.

## How it gets made

- Lives in `map-challenge-2026` as day 8: `python new_day.py 8` → `days/08-utopia/`
  with `map.py`, `notes.md`, `sources.toml`, `data/`.
- Python (`map.py`) does all data work: pulls the street/plaza geometry for the corridor
  from OSM, builds the walkable area, generates synthetic agent trips (paths +
  timestamps) for walkers and cyclists, and writes `map.html`.
- Rendering: deck.gl + MapLibre GL JS from a CDN, exact pinned versions. A small
  hand-written JS block runs the animation clock, layer switching by zoom, and the tour.
  pydeck's static export can't animate, so the HTML is templated from Python.
- **Constraint**: `build.py` copies only `map.html` into the site, so `map.html` must be
  self-contained: trip data inlined as JSON. External assets allowed only from CDNs
  (JS libs, basemap tiles/style, glTF model URL) — no extra local files.
- Free, key-less basemap (e.g. OpenFreeMap or CARTO) that provides building heights.
- New Python deps (e.g. osmnx, shapely) are fine locally; they go in `requirements.txt`,
  not `requirements-site.txt`.
- `notes.md`: title + reasoning (why this corridor, Strand Aldwych 2022 as precedent,
  Oxford Circus as "the start"). `sources.toml`: OSM, basemap, glTF model credit,
  deck.gl/MapLibre.

## Numbers

Agent volumes are illustrative, labelled as such in notes. Enough people to feel like a
busy, pleasant Saturday, not a stampede. Exact counts: builder's call, bounded by
performance (smooth on a laptop; keep `map.html` reasonably small, a few MB at most).

## Calls made after review (Claude's calls, override freely)

- **Extent**: starts at the Waterloo station forecourt / Waterloo Road outside the
  station. No station interior (OSM is poor there). Ends in the Covent Garden piazza.
- **Basemap buildings**: prefer vector-tile building heights. If coverage along the
  Strand / Covent Garden is patchy, ship corridor building footprints with heights inline
  (Overture or OSM), within the size budget.
- **Model fallback**: if the glTF fails to load, keep showing trails at every zoom. The
  page must never break.
- **Thumbnail**: a committed hand-made `thumb.png` screenshot is fine.
- **Loop**: two bus pulses, one each way (~7 simulated minutes, sped up on screen), with
  walker/cyclist trips staggered across it (no sync).

## Buses: pulsed convoys (Tom's idea)

No cars, but buses survive in pulses: about 3 minutes with no buses, then a short convoy
(~30s) crosses Waterloo Bridge and runs along the Strand, then quiet again. Think of the
bridge as a gate that opens for buses at intervals, like a level crossing.
The bridge is wide, so one central lane is shared by buses and bikes. It is a **single
lane with traffic lights at each end** (Tom's call): each pulse runs in one direction
only, and the next pulse runs the other way, like a signal-controlled roadworks lane.
(Claude's calls:) cyclists ride both ways in the lane. Walkers already keep loosely out of
that lane, so walker paths don't need to change over time. Cyclists in the lane during a
pulse slow down or pull to the edge. Buses get a simple distinct model or extruded box,
plus a subtle "bus gate" marker at each end of the bridge. The notes frame this as a
stated assumption: other routes divert via Blackfriars/Westminster, and the convoy is
what's left.
- **Mobile**: desktop-first. On phones, cap agent counts and allow trails-only.

## Later extension (not this build)

- A "now" version: cars on the carriageway, pedestrians squeezed onto pavements, ideally
  with volumes scaled from real counts (DfT traffic counts for Waterloo Bridge, TfL cycle
  counts).
- A side-by-side swipe: two synced maps (now / utopia) with a draggable vertical divider,
  dragging reveals more of one or the other.
- Design implication now: keep scenario generation parameterised (geometry + agent
  rules in, trips out) so "now" is a second scenario, not a rewrite.

## Goals

- A delightful, moving 3D map that makes a car-free Waterloo Bridge–Strand–Covent Garden
  feel real.
- Trails zoomed out, 3D people zoomed in; fly-through then free explore.
- Ships as a normal challenge day on the site.

## Non-goals

- Real pedestrian simulation / crowd physics.
- The "now" scenario and comparison slider (extension).
- Accurate pedestrian counts.

## Anti-goals (failure even if it works)

- People walking through buildings, in the river, or in neat lanes like it's still a road.
- Looking empty or like a festival crush.
- A map that stutters, or breaks the site build / blows up page weight.

## Left to the builder

Bounding box details, OSM extraction method, walkable-area construction, path wander
algorithm, agent counts, colours (should fit the site theme), tour keyframes, cyclist
model (glTF if a free one exists, otherwise a simple distinct marker), thumbnail approach
if headless Chrome can't render WebGL for `build.py --thumbs`.
