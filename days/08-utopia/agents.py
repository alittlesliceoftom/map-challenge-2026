"""Synthetic trips for walkers, cyclists and buses (all in metres, seconds).

These are illustrative, not counts: enough people to feel like a busy, pleasant
Saturday on a car-free Waterloo Bridge and Strand.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

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


def _aim(walk, lane, rng) -> float:
    """A spot somewhere across the full width, but not in the bus/bike lane."""
    for _ in range(8):
        x = rng.uniform(*walk)
        if lane is None or not (lane[0] - 0.5 < x < lane[1] + 0.5):
            return x
    return x


def walker_trips(c: Corridor, n: int, rng: np.random.Generator) -> list[Trip]:
    names = list(c.routes)
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
        for s in ss:
            p, nrm = _frame(route, s)
            walk = _span(c.walkable, p, nrm, CAST_M) or (0.0, 0.0)
            lane = _span(c.lane, p, nrm, CAST_M)
            if offset is None:
                offset = _aim(walk, lane, rng)
            if target is None or (abs(offset - target) < 0.5 and dwell <= 0):
                target, dwell = _aim(walk, lane, rng), rng.uniform(30, 90)
            in_lane = lane is not None and lane[0] - 0.5 < offset < lane[1] + 0.5
            drift = DRIFT * STEP_M * (2.5 if in_lane else 1.0)  # cross the lane briskly
            step = np.clip(target - offset, -drift, drift)
            offset = float(np.clip(offset + step, *walk))
            dwell -= STEP_M
            pts.append(p + offset * nrm)
        if len(pts) < 2:
            continue
        path = _inside(c.walkable, _chaikin(np.array(pts)))
        path = np.array(LineString(path).simplify(0.3).coords)  # keeps the file small
        trips.append(_timed("walk", path, rng.uniform(1.1, 1.5), rng.uniform(0, LOOP_S)))
    return trips


def cyclist_trips(c: Corridor, n: int, rng: np.random.Generator) -> list[Trip]:
    trips = []
    for _ in range(n):
        route = _pick_route(c, c.lane_routes, rng)
        ss = np.arange(0, route.length, 15.0)
        if rng.random() < 0.5:
            ss = ss[::-1]
        offset = rng.uniform(-1.5, 1.5)
        pts = []
        for s in ss:
            p, nrm = _frame(route, s)
            offset = float(np.clip(offset + rng.normal(0, 0.3), -1.5, 1.5))
            pts.append(p + offset * nrm)
        path = _inside(c.lane, np.array(pts))
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
