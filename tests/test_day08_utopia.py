"""Tests for day 8 (Utopia): corridor geometry, agent trips, rendering."""

import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, box

DAY = Path(__file__).resolve().parent.parent / "days" / "08-utopia"
sys.path.insert(0, str(DAY))

from geometry import CRS, build_lane, build_walkable, load_corridor  # noqa: E402


def test_build_walkable_subtracts_buildings():
    streets = gpd.GeoDataFrame({"highway": ["primary"]}, geometry=[LineString([(0, 0), (100, 0)])], crs=CRS)
    bldg = gpd.GeoDataFrame(geometry=[box(40, -20, 60, 20)], crs=CRS)
    w = build_walkable(streets, bldg)
    assert w.contains(Point(10, 9))
    assert not w.contains(Point(50, 0))
    assert not w.contains(Point(10, 11))


def test_build_walkable_keeps_bridges_over_buildings():
    # Waterloo Bridge (layer 2) passes over the BFI: the deck stays walkable
    streets = gpd.GeoDataFrame({"highway": ["primary"], "layer": ["2"]},
                               geometry=[LineString([(0, 0), (100, 0)])], crs=CRS)
    bldg = gpd.GeoDataFrame(geometry=[box(40, -20, 60, 20)], crs=CRS)
    assert build_walkable(streets, bldg).contains(Point(50, 0))


def test_build_lane_width():
    lane = build_lane({"r": LineString([(0, 0), (100, 0)])}, ["r"])
    assert lane.contains(Point(50, 1.9))
    assert not lane.contains(Point(50, 2.1))


def test_routes_inside_walkable():
    try:
        c = load_corridor()
    except Exception as e:  # offline and no cache
        pytest.skip(f"corridor unavailable: {e}")
    for name, line in c.routes.items():
        outside = line.difference(c.walkable.buffer(1))
        assert outside.length < 1, f"{name}: {outside.length:.1f} m outside walkable"


# ── Task 2: walkers and cyclists ────────────────────────────────────────────
import numpy as np  # noqa: E402

from geometry import Corridor  # noqa: E402

X0, Y0 = 530800.0, 180500.0


@pytest.fixture
def corridor():
    return Corridor(
        walkable=box(X0, Y0 - 10, X0 + 600, Y0 + 10),
        lane=box(X0, Y0 - 2, X0 + 600, Y0 + 2),
        routes={"r": LineString([(X0, Y0), (X0 + 600, Y0)])},
        lane_routes=["r"],
    )


def _speeds(trip):
    p = np.array(trip.path)
    d = np.hypot(*np.diff(p, axis=0).T).sum()
    return d / (trip.timestamps[-1] - trip.timestamps[0])


def test_walkers_inside_walkable(corridor):
    from agents import walker_trips
    area = corridor.walkable.buffer(0.5)
    for t in walker_trips(corridor, 200, np.random.default_rng(1)):
        assert all(area.contains(Point(p)) for p in t.path)


def test_walkers_zigzag(corridor):
    from agents import walker_trips
    trips = walker_trips(corridor, 200, np.random.default_rng(2))
    lateral = np.concatenate([np.array(t.path)[:, 1] - Y0 for t in trips])
    assert lateral.std() > 3.0
    long = [t for t in trips if abs(t.path[-1][0] - t.path[0][0]) > 100]
    crossers = [t for t in long if len(set(np.sign(np.array(t.path)[:, 1] - Y0))) > 1]
    assert len(crossers) >= 0.5 * len(long)


def test_walkers_mostly_avoid_lane(corridor):
    from agents import walker_trips
    pts = [Point(p) for t in walker_trips(corridor, 200, np.random.default_rng(3)) for p in t.path]
    assert sum(corridor.lane.contains(p) for p in pts) / len(pts) < 0.10


def test_walkers_both_directions(corridor):
    from agents import walker_trips
    trips = walker_trips(corridor, 400, np.random.default_rng(4))
    east = sum(t.path[-1][0] > t.path[0][0] for t in trips) / len(trips)
    assert 0.35 < east < 0.65


def test_walker_speeds(corridor):
    from agents import walker_trips
    for t in walker_trips(corridor, 200, np.random.default_rng(5)):
        assert np.all(np.diff(t.timestamps) > 0)
        assert 1.0 <= _speeds(t) <= 1.7
        assert t.kind == "walk"


def test_cyclists_in_lane_and_fast(corridor):
    from agents import cyclist_trips
    lane = corridor.lane.buffer(0.5)
    for t in cyclist_trips(corridor, 50, np.random.default_rng(6)):
        assert all(lane.contains(Point(p)) for p in t.path)
        assert 3.5 <= _speeds(t) <= 7.0
        assert t.kind == "bike"
