"""Tests for day 8 (Utopia): corridor geometry, agent trips, rendering."""

import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

DAY = Path(__file__).resolve().parent.parent / "days" / "08-utopia"
sys.path.insert(0, str(DAY))

from geometry import CRS, build_cycle, build_lane, build_walkable, load_corridor  # noqa: E402


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


def test_cycle_track_beside_lane_not_on_it():
    route = LineString([(0, 0), (100, 0)])
    centre, track = build_cycle(route)
    lane = build_lane({"r": route}, ["r"])
    assert abs(centre.interpolate(50).y - 4.25) < 0.01  # left of travel
    assert track.contains(Point(50, 4.25))
    assert track.intersection(lane).area < 1e-6


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
        cycle=box(X0, Y0 + 2.75, X0 + 600, Y0 + 5.75),
        cycle_route=LineString([(X0, Y0 + 4.25), (X0 + 600, Y0 + 4.25)]),
    )


@pytest.fixture
def crossing(corridor):
    """The lane plus a footpath that has to cross it, square on, half way along."""
    xs = X0 + 300
    corridor.walkable = unary_union([corridor.walkable, box(xs - 6, Y0 - 200, xs + 6, Y0 + 200)])
    corridor.routes = {"r": corridor.routes["r"], "x": LineString([(xs, Y0 - 200), (xs, Y0 + 200)])}
    return corridor


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
    both_sides = {np.sign(np.array(t.path)[0, 1] - Y0) for t in trips}
    assert both_sides == {-1.0, 1.0}


def test_walkers_never_on_lane_or_cycle_track(corridor):
    # alongside the lane, walkers keep to their own side
    from agents import walker_trips
    road = unary_union([corridor.lane, corridor.cycle]).buffer(-0.2)
    lines = [LineString(t.path) for t in walker_trips(corridor, 200, np.random.default_rng(3))]
    assert sum(line.intersection(road).length for line in lines) < 1.0


def test_walkers_cross_the_lane_between_buses(crossing):
    from agents import LOOP_S, bus_trips, walker_trips
    rng = np.random.default_rng(8)
    buses = bus_trips(crossing, 6, rng)
    walkers = walker_trips(crossing, 300, rng, buses=buses)
    lane = crossing.lane.buffer(-0.2)  # on the carriageway itself, not the kerb beside it
    crossed = 0
    for w in walkers:
        line = LineString(w.path)
        d = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(np.array(w.path), axis=0).T))])
        for s in np.arange(0, line.length, 0.5):
            p = line.interpolate(s)
            if not lane.contains(p):
                continue
            crossed += 1
            t = float(np.interp(s, d, w.timestamps)) % LOOP_S
            for b in buses:
                if b.timestamps[0] <= t <= b.timestamps[-1]:
                    bd = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(np.array(b.path), axis=0).T))])
                    q = LineString(b.path).interpolate(float(np.interp(t, b.timestamps, bd)))
                    assert p.distance(q) > 10, f"walker hit by a bus at t={t:.0f}"
    assert crossed > 50  # some people really do cross


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


def test_cyclists_on_cycle_track_and_fast(corridor):
    from agents import cyclist_trips
    track = corridor.cycle.buffer(0.3)
    for t in cyclist_trips(corridor, 50, np.random.default_rng(6)):
        assert all(track.contains(Point(p)) for p in t.path)
        assert not LineString(t.path).intersects(corridor.lane)
        assert 3.5 <= _speeds(t) <= 7.0
        assert t.kind == "bike"


def test_cyclists_keep_left(corridor):
    # two-way track: each direction rides its own (UK, left) half
    from agents import cyclist_trips
    for t in cyclist_trips(corridor, 50, np.random.default_rng(9)):
        p = np.array(t.path)
        forward = p[-1, 0] > p[0, 0]
        y = p[:, 1].mean() - (Y0 + 4.25)
        assert (y > 0) == forward


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


# ── Procedural animated cyclist ─────────────────────────────────────────────
import json as _json  # noqa: E402
import struct as _struct  # noqa: E402


def _gltf(glb: bytes) -> dict:
    assert glb[:4] == b"glTF" and _struct.unpack("<I", glb[4:8])[0] == 2
    n = _struct.unpack("<I", glb[12:16])[0]
    return _json.loads(glb[20:20 + n])


def test_cyclist_glb_has_one_second_pedalling_animation():
    from models import cyclist_glb
    g = _gltf(cyclist_glb())
    (anim,) = g["animations"]
    animated = {g["nodes"][c["target"]["node"]]["name"] for c in anim["channels"]}
    assert {"wheel_front", "wheel_rear", "crank", "thigh_L", "shin_L", "thigh_R", "shin_R"} <= animated
    for s in anim["samplers"]:
        assert g["accessors"][s["input"]]["max"] == [1.0]


def test_cyclist_feet_stay_on_the_pedals():
    from models import CRANK_R, cyclist_pose
    for theta in np.linspace(0, 2 * np.pi, 17):
        pose = cyclist_pose(theta)
        for side in ("L", "R"):
            foot, pedal = np.array(pose["foot_" + side]), np.array(pose["pedal_" + side])
            assert np.linalg.norm(foot - pedal) < 0.02, (theta, side)
        assert abs(np.linalg.norm(np.array(pose["pedal_L"]) - np.array(pose["bb"])) - CRANK_R) < 1e-6


# ── Greenery: packed MegaKit models, planters on the bridge ─────────────────
MEGAKIT = DAY / "data" / "megakit" / "glTF"


@pytest.mark.skipif(not MEGAKIT.exists(), reason="Quaternius MegaKit not downloaded")
def test_pack_gltf_is_small_self_contained_glb():
    from models import pack_gltf
    glb = pack_gltf(MEGAKIT / "CommonTree_5.gltf", max_texture=512)
    g = _gltf(glb)
    assert len(glb) < 400_000
    assert all("uri" not in im for im in g.get("images", []))
    for mesh in g["meshes"]:
        for prim in mesh["primitives"]:
            assert "TANGENT" not in prim["attributes"]
    assert all("normalTexture" not in m for m in g["materials"])


def test_planters_sit_on_the_deck_and_walkers_avoid_them(corridor):
    from agents import walker_trips
    from geometry import place_planters
    planters = place_planters(corridor.routes["r"], corridor.walkable, offset=6.0, spacing=40.0)
    assert len(planters) >= 20  # both sides of a 600 m deck
    for p in planters:
        assert corridor.walkable.contains(p)
        assert not p.intersects(corridor.lane)
    corridor.walkable = corridor.walkable.difference(unary_union(planters).buffer(0.4))
    hits = sum(any(p.contains(Point(q)) for p in planters)
               for t in walker_trips(corridor, 150, np.random.default_rng(11)) for q in t.path)
    assert hits == 0


def test_real_cyclists_never_touch_bus_lane():
    # the Aldwych bend is tight: coarse sampling used to cut the corner across the lane
    from agents import cyclist_trips
    try:
        c = load_corridor()
    except Exception as e:  # offline and no cache
        pytest.skip(f"corridor unavailable: {e}")
    lane = c.lane.buffer(-0.3)
    for t in cyclist_trips(c, 40, np.random.default_rng(1)):
        assert not LineString(t.path).intersects(lane)


# ── Walker: rigid jointed figure (deck's ScenegraphLayer plays node animations, not skins) ──
def test_walker_glb_animates_legs_and_arms_without_skins():
    from models import walker_glb
    g = _gltf(walker_glb())
    assert "skins" not in g
    (anim,) = g["animations"]
    animated = {g["nodes"][c["target"]["node"]]["name"] for c in anim["channels"]}
    assert {"thigh_L", "thigh_R", "shin_L", "shin_R", "arm_L", "arm_R", "body"} <= animated
    for s in anim["samplers"]:
        assert g["accessors"][s["input"]]["max"] == [1.0]


def test_walker_glb_shirt_colour():
    from models import walker_glb
    g = _gltf(walker_glb(shirt=(0.1, 0.2, 0.3, 1)))
    shirts = [m for m in g["materials"] if m["name"] == "shirt"]
    assert shirts[0]["pbrMetallicRoughness"]["baseColorFactor"] == [0.1, 0.2, 0.3, 1]


def test_walker_always_has_a_foot_on_the_ground_and_steps():
    from models import walker_pose
    phases = np.linspace(0, 1, 33)
    poses = [walker_pose(p) for p in phases]
    for p in poses:
        assert abs(min(p["foot_L"][1], p["foot_R"][1])) < 1e-6
    # feet take turns being in front: legs swing in opposite phase
    lead = [np.sign(p["foot_R"][0] - p["foot_L"][0]) for p in poses]
    assert {-1.0, 1.0} <= set(lead)
    span = max(abs(p["foot_R"][0] - p["foot_L"][0]) for p in poses)
    assert 0.5 < span < 1.0  # a natural step, not a shuffle or a split


def test_striped_walker_has_hat_glasses_and_stripes():
    from models import walker_glb
    g = _gltf(walker_glb(striped=True))
    names = {n.get("name") for n in g["nodes"]}
    assert {"bobble", "hat", "glasses"} <= names
    stripes = [n for n in names if n and n.startswith("stripe")]
    assert len(stripes) >= 6
    colours = {m["name"]: m["pbrMetallicRoughness"]["baseColorFactor"] for m in g["materials"]}
    assert {"red", "white", "jeans"} <= set(colours)
    (anim,) = g["animations"]  # still walks
    assert len(anim["channels"]) >= 7


def test_tour_ends_close_on_the_bridge():
    # finish at street zoom (figures draw from zoom 17) in the middle of Waterloo Bridge
    from map import TOUR
    last = TOUR[-1]
    assert last["zoom"] >= 19.5
    lon, lat = last["center"]
    assert -0.1170 < lon < -0.1135 and 51.5055 < lat < 51.5085


def test_tour_captions_explain_the_change():
    from map import TOUR
    assert all(k.get("caption") for k in TOUR)
    text = " ".join(k["caption"] for k in TOUR).lower()
    for phrase in ("four lanes", "pedestrian", "two-way cycle", "bus lane", "one direction at a time"):
        assert phrase in text, phrase
    assert all(len(k["caption"]) <= 140 for k in TOUR)  # readable mid-flight
