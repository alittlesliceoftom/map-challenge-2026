"""
Day 8 · Utopia
The prompt: A map of something which could be.

What I'm mapping: Waterloo Bridge, Lancaster Place and the Strand with the cars gone,
people wandering from Waterloo station to Covent Garden, a two-way cycle track,
and one signalled lane for bus convoys.

Run it from the project folder:
    python days/08-utopia/map.py
It saves map.html next to this file (self-contained: the trips are inlined).
"""

import base64
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import mapping
from shapely.ops import unary_union

from agents import LOOP_S, PULSES, bus_trips, cyclist_trips, to_deck_json, walker_trips, wrap_loop
from geometry import CRS, WALK_ROUTES, load_corridor, place_planters
from models import cyclist_glb, walker_glb, walker_stride

# three walker variants, one per animation phase group on the page
SHIRTS = [(0.93, 0.47, 0.20, 1), (0.16, 0.55, 0.60, 1), (0.85, 0.70, 0.25, 1)]
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
    # and back down onto the middle of the bridge, close enough to see people walking
    {"center": [-0.11520, 51.50680], "zoom": 20.2, "pitch": 65, "bearing": -30, "duration_ms": 7000},
]


def _data_uri(glb: bytes) -> str:
    return "data:model/gltf-binary;base64," + base64.b64encode(glb).decode()


def _geojson(geom) -> dict:
    wgs = gpd.GeoSeries([geom.simplify(0.5)], crs=CRS).to_crs("EPSG:4326")[0]
    return {"type": "Feature", "properties": {}, "geometry": mapping(wgs)}


def _lights(c) -> list[dict]:
    """Traffic lights at both ends of the single lane: dir is the way they let buses in."""
    lane = c.routes[c.lane_routes[0]]
    ends = gpd.GeoSeries([lane.interpolate(3), lane.interpolate(lane.length - 3)], crs=CRS).to_crs("EPSG:4326")
    return [{"pos": [round(ends[0].x, 6), round(ends[0].y, 6)], "dir": 1},
            {"pos": [round(ends[1].x, 6), round(ends[1].y, 6)], "dir": -1}]


def _greenery(planters, rng) -> list[dict]:
    """One tree per planter, with flowering bushes and plants around it.
    m = model, p = [lon, lat], y = yaw (deg), s = scale."""
    items = []
    for k, rect in enumerate(planters):
        xs, ys = rect.exterior.coords.xy
        c = rect.centroid
        ax = np.array([xs[1] - xs[0], ys[1] - ys[0]])
        ax = ax / np.linalg.norm(ax)                    # along the planter
        def at(d):
            return c.x + d * ax[0], c.y + d * ax[1]
        items.append(("CommonTree_3" if k % 3 else "CommonTree_5", at(0), rng.uniform(0, 360), rng.uniform(0.85, 1.1)))
        for d in (-2.0, 2.0):
            kind = "Bush_Common_Flowers" if rng.random() < 0.6 else "Flower_4_Group"
            items.append((kind, at(d + rng.uniform(-0.3, 0.3)), rng.uniform(0, 360), rng.uniform(0.6, 0.8)))
        items.append(("Plant_7_Big", at(rng.uniform(-1.2, 1.2)), rng.uniform(0, 360), 1.0))
    pts = gpd.GeoSeries([gpd.points_from_xy([i[1][0]], [i[1][1]])[0] for i in items], crs=CRS).to_crs("EPSG:4326")
    return [{"m": m, "p": [round(p.x, 7), round(p.y, 7)], "y": round(y), "s": round(s, 2)}
            for (m, _, y, s), p in zip(items, pts)]


def main() -> None:
    rng = np.random.default_rng(8)
    c = load_corridor()
    # planters and trees down both sides of the bridge; walkers route around them
    planters = place_planters(c.bridge, c.walkable, offset=8.0, spacing=26.0) if c.bridge else []
    c.walkable = c.walkable.difference(unary_union(planters).buffer(0.4))
    buses = bus_trips(c, N_BUSES_PER_PULSE, rng)
    # walkers keep off the lane, and time any crossing to miss the buses
    walkers = walker_trips(c, N_WALKERS, rng, buses=buses)
    trips = walkers + cyclist_trips(c, N_CYCLISTS, rng) + buses
    # one walker in a striped jumper and bobble hat: the longest walk, so (wrapped round the
    # loop) he is always somewhere; an id divisible by 3 keeps him on the thinned mobile page
    spotter = max((i for i in range(len(walkers)) if i % 3 == 0),
                  key=lambda i: walkers[i].timestamps[-1] - walkers[i].timestamps[0])
    reach = unary_union([c.routes[n].buffer(20) for n in WALK_ROUTES + c.lane_routes])
    extras = {
        "loop_s": LOOP_S,
        "pulses": PULSES,
        "plaza": _geojson(c.walkable.intersection(reach)),
        "lane": _geojson(c.lane),
        "cycle": _geojson(c.cycle),
        "lights": _lights(c),
        "planters": {"type": "FeatureCollection", "features": [_geojson(p) for p in planters]},
        "greenery": _greenery(planters, np.random.default_rng(9)),
        "walker_stride": round(walker_stride(), 3),
        "striped": spotter,
        "models": {"cyclist": _data_uri(cyclist_glb()),
                   **{f"walker_{k}": _data_uri(walker_glb(shirt)) for k, shirt in enumerate(SHIRTS)},
                   "striped": _data_uri(walker_glb(striped=True)),
                   **{f.stem: _data_uri(f.read_bytes()) for f in sorted((HERE / "models").glob("*.glb"))}},
    }
    out = HERE / "map.html"
    render(to_deck_json(wrap_loop(trips)), out, tour=TOUR, extras=extras)
    print(f"Saved {out} ({out.stat().st_size / 1e6:.1f} MB, {len(trips)} trips)")


if __name__ == "__main__":
    main()
