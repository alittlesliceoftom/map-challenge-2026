"""Synthetic trips for walkers, cyclists and buses (all in metres, seconds).

These are illustrative, not counts: enough people to feel like a busy, pleasant
Saturday on a car-free Waterloo Bridge and Strand.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, unary_union

from geometry import Corridor

LOOP_S = 420.0
# Single signalled lane: (green from s, green until s, direction along the route).
# Buses enter while green and must be clear before the other way turns green.
PULSES = [(0.0, 30.0, 1), (210.0, 240.0, -1)]

STEP_M = 10.0          # distance between walker waypoints
CAST_M = 14.0          # how far either side of the route a walker may drift
DRIFT = 0.35           # max sideways metres per metre forward (a gentle diagonal)
MIN_TRIP_M = 150.0


TRAIL_S = 40.0  # longest trail drawn on the page (template.html trailLength)
KERB_M = 0.5           # walkers keep this far off the bus lane and cycle track
PARALLEL_M = 12.0      # a road cross-section wider than this means the route crosses it square on
BUS_CLEAR_M = 10.0     # half a bus plus room to spare


@dataclass
class Trip:
    kind: Literal["walk", "bike", "bus"]
    path: list[tuple[float, float]]
    timestamps: list[float]
    id: int = -1  # shared by a trip and its wrapped copies


def _timed(kind, pts: np.ndarray, speed: float, start: float) -> Trip:
    d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
    keep = np.concatenate([[True], np.diff(d) > 1e-6])  # no zero-length steps
    pts, d = pts[keep], d[keep]
    return Trip(kind, [tuple(p) for p in pts.round(2)], list(start + d / speed))


def _chaikin(pts: np.ndarray) -> np.ndarray:
    q = 0.75 * pts[:-1] + 0.25 * pts[1:]
    r = 0.25 * pts[:-1] + 0.75 * pts[1:]
    out = np.empty((2 * len(q), 2))
    out[0::2], out[1::2] = q, r
    return np.vstack([pts[:1], out, pts[-1:]])


def _frame(route: LineString, s: float) -> tuple[np.ndarray, np.ndarray]:
    """Point on the route at distance s, and the unit normal (left of travel)."""
    p = np.array(route.interpolate(s).coords[0])
    a = np.array(route.interpolate(max(s - 2, 0)).coords[0])
    b = np.array(route.interpolate(min(s + 2, route.length)).coords[0])
    t = (b - a) / (np.linalg.norm(b - a) or 1)
    return p, np.array([-t[1], t[0]])


def _span(geom, p: np.ndarray, n: np.ndarray, reach: float) -> tuple[float, float] | None:
    """Offsets [a, b] along n of the piece of geom (cut by a cross-section) containing p."""
    cut = LineString([p - reach * n, p + reach * n]).intersection(geom)
    pieces = getattr(cut, "geoms", [cut])
    best = None
    for g in pieces:
        if g.is_empty or g.geom_type != "LineString":
            continue
        offs = [float(np.dot(np.array(c) - p, n)) for c in g.coords]
        lo, hi = min(offs), max(offs)
        if lo - 0.5 <= 0 <= hi + 0.5:
            return lo, hi
        if best is None or min(abs(lo), abs(hi)) < min(abs(best[0]), abs(best[1])):
            best = (lo, hi)
    return best


def _inside(geom, pts: np.ndarray) -> np.ndarray:
    out = pts.copy()
    for i, p in enumerate(pts):
        pt = Point(p)
        if not geom.contains(pt):
            out[i] = nearest_points(geom, pt)[0].coords[0]
    return out


def _pick_route(c: Corridor, names: list[str], rng) -> LineString:
    lengths = np.array([c.routes[n].length for n in names])
    return c.routes[names[rng.choice(len(names), p=lengths / lengths.sum())]]


def _side(walk, road, side) -> tuple[float, float]:
    """The strip of walkable width on one side (-1 / +1) of the road, or all of it."""
    if road is None or road[1] - road[0] > PARALLEL_M:
        return walk
    lo, hi = (walk[0], road[0] - KERB_M) if side < 0 else (road[1] + KERB_M, walk[1])
    return (lo, hi) if hi > lo else (lo, lo) if side > 0 else (hi, hi)


class _BusClock:
    """Where every bus is, second by second, to check a walker's crossing against."""

    def __init__(self, buses: list[Trip], loop_s: float = LOOP_S):
        self.loop = int(loop_s)
        self.at: list[list[np.ndarray]] = [[] for _ in range(self.loop)]
        for b in buses:
            p = np.array(b.path)
            for s in range(int(np.ceil(b.timestamps[0])), int(b.timestamps[-1]) + 1):
                xy = [np.interp(s, b.timestamps, p[:, k]) for k in (0, 1)]
                self.at[s % self.loop].append(np.array(xy))

    def clear(self, pts: np.ndarray, times: np.ndarray) -> bool:
        for p, t in zip(pts, times):
            for s in (int(np.floor(t)), int(np.ceil(t))):
                for q in self.at[s % self.loop]:
                    if np.hypot(*(p - q)) < BUS_CLEAR_M:
                        return False
        return True


def _sample(trip: Trip, every_s: float = 0.25) -> tuple[np.ndarray, np.ndarray]:
    p, t = np.array(trip.path), np.array(trip.timestamps)
    ts = np.arange(t[0], t[-1], every_s)
    return np.column_stack([np.interp(ts, t, p[:, 0]), np.interp(ts, t, p[:, 1])]), ts


def _time_crossings(trip: Trip, lane, clock: _BusClock, rng) -> Trip | None:
    """Shift a walker's start until every moment it spends on the bus lane is bus-free."""
    pts, ts = _sample(trip)
    on = shapely.contains_xy(lane, pts[:, 0], pts[:, 1])
    if not on.any():
        return trip
    pts, ts = pts[on], ts[on] - trip.timestamps[0]
    for _ in range(60):
        t0 = rng.uniform(0, LOOP_S)
        if clock.clear(pts, ts + t0):
            return Trip(trip.kind, trip.path, [x - trip.timestamps[0] + t0 for x in trip.timestamps])
    return None


def walker_trips(c: Corridor, n: int, rng: np.random.Generator, buses: list[Trip] | None = None) -> list[Trip]:
    """People wandering the full width, but only ever on their own side of the bus lane
    and cycle track. Where a route has to cross the lane, they cross between buses."""
    names = list(c.routes)
    # lane + kerb + cycle track as one strip (closing the narrow kerb gap between them)
    road_geom = unary_union([g for g in (c.lane, c.cycle) if g is not None]).buffer(1).buffer(-1)
    clock = _BusClock(buses) if buses else None
    lane_zone = c.lane.buffer(KERB_M) if clock else None
    trips = []
    for _ in range(n):
        route = _pick_route(c, names, rng)
        L = route.length
        span = min(L, MIN_TRIP_M)
        s0 = rng.uniform(0, L - span)
        s1 = rng.uniform(s0 + span, L)
        ss = np.arange(s0, s1, STEP_M)
        if rng.random() < 0.5:
            ss = ss[::-1]
        pts, offset, target, dwell = [], None, None, 0.0
        side = rng.choice([-1, 1])
        for s in ss:
            p, nrm = _frame(route, s)
            walk = _span(c.walkable, p, nrm, CAST_M) or (0.0, 0.0)
            road = _span(road_geom, p, nrm, CAST_M)
            if offset is None:
                offset = rng.uniform(*walk)
            if road is not None and road[1] - road[0] <= PARALLEL_M and road[0] < offset < road[1]:
                offset = road[0] - KERB_M if side < 0 else road[1] + KERB_M
            elif road is not None and road[1] - road[0] <= PARALLEL_M:
                side = -1 if offset < road[0] else 1
            free = _side(walk, road, side)
            if target is None or (abs(offset - target) < 0.5 and dwell <= 0):
                target, dwell = rng.uniform(*free), rng.uniform(30, 90)
            step = np.clip(target - offset, -DRIFT * STEP_M, DRIFT * STEP_M)
            offset = float(np.clip(offset + step, *free))
            dwell -= STEP_M
            pts.append(p + offset * nrm)
        if len(pts) < 2:
            continue
        path = _inside(c.walkable, _chaikin(np.array(pts)))
        path = np.array(LineString(path).simplify(0.3).coords)  # keeps the file small
        trip = _timed("walk", path, rng.uniform(1.1, 1.5), rng.uniform(0, LOOP_S))
        if clock is not None:
            trip = _time_crossings(trip, lane_zone, clock, rng)
        if trip is not None:
            trips.append(trip)
    return trips


def cyclist_trips(c: Corridor, n: int, rng: np.random.Generator) -> list[Trip]:
    """Both ways along the two-way cycle track, each direction on its own (left) half."""
    route = c.cycle_route
    trips = []
    for _ in range(n):
        ss = np.append(np.arange(0, route.length, 5.0), route.length)  # fine enough not to cut corners
        forward = rng.random() < 0.5
        if not forward:
            ss = ss[::-1]
        keep = 0.75 if forward else -0.75  # left of travel (UK), on the route's normal
        offset = keep + rng.uniform(-0.3, 0.3)
        pts = []
        for s in ss:
            p, nrm = _frame(route, s)
            offset = float(np.clip(offset + rng.normal(0, 0.1), keep - 0.45, keep + 0.45))
            pts.append(p + offset * nrm)
        path = np.array(LineString(_inside(c.cycle, np.array(pts))).simplify(0.2).coords)
        trips.append(_timed("bike", path, rng.uniform(4.0, 6.0), rng.uniform(0, LOOP_S)))
    return trips


def bus_trips(c: Corridor, n_per_pulse: int, rng: np.random.Generator) -> list[Trip]:
    """Convoys on the single signalled lane: one direction per green phase."""
    route = c.routes[c.lane_routes[0]]
    ss = np.append(np.arange(0, route.length, 10.0), route.length)
    line = np.array([route.interpolate(s).coords[0] for s in ss])
    starts = [s for s, _, _ in PULSES] + [LOOP_S]
    trips = []
    for k, (green, until, direction) in enumerate(PULSES):
        pts = line if direction > 0 else line[::-1]
        clear_by = starts[k + 1] - 2.0
        gap = (until - green) / max(n_per_pulse, 1)
        for i in range(n_per_pulse):
            t0 = green + i * gap + rng.uniform(0, 0.3 * gap)
            # fast enough to be off the lane before the other way goes green
            speed = max(rng.uniform(5.5, 7.0), route.length / (clear_by - t0))
            trips.append(_timed("bus", pts, speed, t0))
    return trips


def wrap_loop(trips: list[Trip], loop_s: float = LOOP_S) -> list[Trip]:
    """Copies shifted back by whole loops, so trips (and their fading trails) that run
    past the end reappear at t=0. Each copy keeps its original's id."""
    out = []
    for i, t in enumerate(trips):
        out.append(Trip(t.kind, t.path, t.timestamps, i))
        k = 1
        while t.timestamps[-1] - k * loop_s > -TRAIL_S:
            out.append(Trip(t.kind, t.path, [x - k * loop_s for x in t.timestamps], i))
            k += 1
    return out


_KIND = {"walk": "w", "bike": "b", "bus": "u"}


def to_deck_json(trips: list[Trip], crs: str = "EPSG:27700") -> list[dict]:
    """Compact rows for deck.gl: i = trip id, k = kind, p = [[lon, lat]], t = seconds."""
    from pyproj import Transformer

    to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    rows = []
    for t in trips:
        xs, ys = zip(*t.path)
        lon, lat = to_wgs.transform(xs, ys)
        rows.append({
            "i": t.id,
            "k": _KIND[t.kind],
            "p": [[round(a, 6), round(b, 6)] for a, b in zip(lon, lat)],
            "t": [round(float(x), 1) for x in t.timestamps],
        })
    return rows
