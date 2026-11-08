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
N_WALKERS, N_CYCLISTS, N_BUSES_PER_PULSE = 1200, 150, 6

TOUR: list[dict] = []  # filled in Task 6


def _geojson(geom) -> dict:
    wgs = gpd.GeoSeries([geom.simplify(0.5)], crs=CRS).to_crs("EPSG:4326")[0]
    return {"type": "Feature", "properties": {}, "geometry": mapping(wgs)}


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
    }
    out = HERE / "map.html"
    render(to_deck_json(wrap_loop(trips)), out, tour=TOUR, extras=extras)
    print(f"Saved {out} ({out.stat().st_size / 1e6:.1f} MB, {len(trips)} trips)")


if __name__ == "__main__":
    main()
