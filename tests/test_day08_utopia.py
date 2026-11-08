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
    lines = [LineString(t.path) for t in walker_trips(corridor, 200, np.random.default_rng(3))]
    in_lane = sum(line.intersection(corridor.lane).length for line in lines)
    assert in_lane / sum(line.length for line in lines) < 0.10  # share of distance walked


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


# ── Task 3: bus pulses, loop wrap, JSON ─────────────────────────────────────
def test_buses_enter_on_green_and_clear_before_the_other_way(corridor):
    # The gate is green for a pulse's entry window; every bus must be off the
    # single lane before the opposite pulse's window opens.
    from agents import LOOP_S, PULSES, bus_trips
    starts = [s for s, _, _ in PULSES]
    for t in bus_trips(corridor, 6, np.random.default_rng(7)):
        i = [k for k, (s, e, _) in enumerate(PULSES) if s <= t.timestamps[0] <= e]
        assert len(i) == 1
        next_start = starts[i[0] + 1] if i[0] + 1 < len(starts) else LOOP_S
        assert t.timestamps[-1] <= next_start
        assert t.kind == "bus"


def test_buses_one_way_per_pulse(corridor):
    from agents import PULSES, bus_trips
    trips = bus_trips(corridor, 6, np.random.default_rng(8))
    route = corridor.routes["r"]
    signs = []
    for s, e, d in PULSES:
        mine = [t for t in trips if s - 1e-6 <= t.timestamps[0] <= e]
        assert len(mine) == 6
        moves = {np.sign(route.project(Point(t.path[-1])) - route.project(Point(t.path[0]))) for t in mine}
        assert moves == {d}
        signs.append(d)
    assert signs[0] == -signs[1]


def test_buses_on_lane(corridor):
    from agents import bus_trips
    lane = corridor.lane.buffer(0.5)
    for t in bus_trips(corridor, 6, np.random.default_rng(9)):
        assert all(lane.contains(Point(p)) for p in t.path)


def test_wrap_loop_duplicates_boundary_trips():
    from agents import LOOP_S, Trip, wrap_loop
    a = Trip("walk", [(0, 0), (10, 0)], [LOOP_S - 10, LOOP_S + 10])
    b = Trip("walk", [(0, 0), (10, 0)], [10, 20])
    out = wrap_loop([a, b])
    assert len(out) == 3
    assert any(t.timestamps == [-10, 10] for t in out)


def test_wrap_loop_long_trips_cover_every_loop():
    from agents import LOOP_S, Trip, wrap_loop
    long = Trip("walk", [(0, 0), (10, 0)], [100, 100 + 2.5 * LOOP_S])
    out = wrap_loop([long])
    # visible at every moment of the loop: some copy spans t for every t in [0, LOOP_S)
    for t in np.linspace(0, LOOP_S - 1, 50):
        assert any(c.timestamps[0] <= t <= c.timestamps[-1] for c in out)


def test_to_deck_json_wgs84_and_rounding(corridor):
    from agents import to_deck_json, walker_trips
    rows = to_deck_json(walker_trips(corridor, 5, np.random.default_rng(10)))
    for r in rows:
        assert set(r) == {"i", "k", "p", "t"} and r["k"] == "w"
        for lon, lat in r["p"]:
            assert -0.13 < lon < -0.10 and 51.50 < lat < 51.52
            assert round(lon, 6) == lon and round(lat, 6) == lat
        assert all(round(x, 1) == x for x in r["t"])


# ── Task 4: rendering ───────────────────────────────────────────────────────
import re  # noqa: E402


def test_render_self_contained(tmp_path):
    from render import render
    render([{"k": "w", "p": [[-0.117, 51.508], [-0.118, 51.509]], "t": [0, 10]}],
           tmp_path / "m.html", tour=[], extras={"loop_s": 420})
    html = (tmp_path / "m.html").read_text()
    assert "/*__TRIPS__*/" not in html and '"k":"w"' in html
    assert "/*__EXTRAS__*/" not in html and '"loop_s":420' in html
    assert "@latest" not in html
    assert re.search(r"deck\.gl@\d+\.\d+\.\d+", html)
    assert re.search(r"maplibre-gl@\d+\.\d+\.\d+", html)


# ── Final review fixes: loop seam ───────────────────────────────────────────
def test_wrap_loop_copies_trails_still_fading_at_the_seam():
    # a trip that ended 10 s before the loop end still shows a fading tail at
    # t = LOOP_S; its copy must show the same tail at t = 0
    from agents import LOOP_S, TRAIL_S, Trip, wrap_loop
    ending = Trip("walk", [(0, 0), (10, 0)], [LOOP_S - 60, LOOP_S - 10])
    out = wrap_loop([ending])
    assert any(t.timestamps[-1] == -10 for t in out)
    stale = Trip("walk", [(0, 0), (10, 0)], [10, LOOP_S - TRAIL_S - 5])
    assert len(wrap_loop([stale])) == 1


def test_mobile_subset_is_closed_under_wrapping():
    # the page thins trips by id % 3 on phones: a trip and its wrapped copies
    # must share an id so they are kept or dropped together
    from agents import LOOP_S, Trip, to_deck_json, wrap_loop
    trips = [Trip("walk", [(530800.0 + i, 180500.0), (530810.0 + i, 180500.0)],
                  [LOOP_S - 5, LOOP_S + 600]) for i in range(7)]
    rows = to_deck_json(wrap_loop(trips))
    ids = [r["i"] for r in rows]
    assert sorted(set(ids)) == list(range(7))
    assert all(ids.count(i) == len(rows) // 7 for i in range(7))


# ── The shared lane never doubles back on itself ────────────────────────────
def test_lane_route_does_not_double_back():
    try:
        c = load_corridor()
    except Exception as e:
        pytest.skip(f"corridor unavailable: {e}")
    route = c.routes[c.lane_routes[0]]
    pts = np.array([route.interpolate(s).coords[0] for s in np.arange(0, route.length, 10.0)])
    chords = pts[2:] - pts[:-2]  # 20 m chords
    unit = chords / np.linalg.norm(chords, axis=1, keepdims=True)
    turns = (unit[:-2] * unit[2:]).sum(axis=1)  # cos of the turn over ~20 m
    assert turns.min() > -0.3, f"lane turns back on itself (cos {turns.min():.2f})"


def test_drop_loops_cuts_out_and_back_spurs():
    from geometry import drop_loops
    # north 100 m, then a 60 m detour east and back, then north again
    spur = LineString([(0, 0), (0, 100), (60, 100), (2, 102), (0, 200)])
    out = drop_loops(spur)
    assert out.length < 215  # the 120 m detour is gone
    assert out.coords[0] == (0, 0) and out.coords[-1] == (0, 200)
    straight = LineString([(0, 0), (0, 100), (50, 150)])
    assert drop_loops(straight).equals(straight)
