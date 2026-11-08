"""
Day 8 · Utopia
The prompt: A map of something which could be.

What I'm mapping: Waterloo Bridge, Lancaster Place and the Strand with the cars gone,
people wandering from Waterloo station to Covent Garden, one signalled lane for bikes
and bus convoys.

Run it from the project folder:
    python days/08-utopia/map.py
It saves map.html next to this file (self-contained: the trips are inlined).
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import mapping
from shapely.ops import unary_union

from agents import LOOP_S, PULSES, bus_trips, cyclist_trips, to_deck_json, walker_trips, wrap_loop
from geometry import CRS, WALK_ROUTES, load_corridor
from render import render

HERE = Path(__file__).parent
N_WALKERS, N_CYCLISTS, N_BUSES_PER_PULSE = 1200, 90, 6

# The intro fly-through: river -> bridge -> Lancaster Place -> Strand east -> back west
# -> Covent Garden piazza -> overview. About 40 s.
TOUR: list[dict] = [
    {"center": [-0.11600, 51.50700], "zoom": 15.4, "pitch": 50, "bearing": -25, "duration_ms": 3000},
    {"center": [-0.11635, 51.50795], "zoom": 18.3, "pitch": 62, "bearing": -30, "duration_ms": 7000},
    {"center": [-0.11895, 51.51080], "zoom": 18.0, "pitch": 60, "bearing": -35, "duration_ms": 6000},
    {"center": [-0.11660, 51.51240], "zoom": 17.8, "pitch": 60, "bearing": 60, "duration_ms": 7000},
    {"center": [-0.12030, 51.51200], "zoom": 17.6, "pitch": 58, "bearing": -60, "duration_ms": 7000},
    {"center": [-0.12220, 51.51180], "zoom": 18.1, "pitch": 55, "bearing": -100, "duration_ms": 5000},
    {"center": [-0.11800, 51.50960], "zoom": 15.9, "pitch": 55, "bearing": -25, "duration_ms": 6000},
]


def _geojson(geom) -> dict:
    wgs = gpd.GeoSeries([geom.simplify(0.5)], crs=CRS).to_crs("EPSG:4326")[0]
    return {"type": "Feature", "properties": {}, "geometry": mapping(wgs)}


def _lights(c) -> list[dict]:
    """Traffic lights at both ends of the single lane: dir is the way they let buses in."""
    lane = c.routes[c.lane_routes[0]]
    ends = gpd.GeoSeries([lane.interpolate(3), lane.interpolate(lane.length - 3)], crs=CRS).to_crs("EPSG:4326")
    return [{"pos": [round(ends[0].x, 6), round(ends[0].y, 6)], "dir": 1},
            {"pos": [round(ends[1].x, 6), round(ends[1].y, 6)], "dir": -1}]


def main() -> None:
    rng = np.random.default_rng(8)
    c = load_corridor()
    trips = (walker_trips(c, N_WALKERS, rng) + cyclist_trips(c, N_CYCLISTS, rng)
             + bus_trips(c, N_BUSES_PER_PULSE, rng))
    reach = unary_union([c.routes[n].buffer(20) for n in WALK_ROUTES + c.lane_routes])
    extras = {
        "loop_s": LOOP_S,
        "pulses": PULSES,
        "plaza": _geojson(c.walkable.intersection(reach)),
        "lane": _geojson(c.lane),
        "lights": _lights(c),
    }
    out = HERE / "map.html"
    render(to_deck_json(wrap_loop(trips)), out, tour=TOUR, extras=extras)
    print(f"Saved {out} ({out.stat().st_size / 1e6:.1f} MB, {len(trips)} trips)")


if __name__ == "__main__":
    main()
