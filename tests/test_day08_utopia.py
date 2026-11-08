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
