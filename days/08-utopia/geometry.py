"""Corridor geometry: where people can walk, the single bus lane and the cycle track beside it.

Everything is in metres (British National Grid) so distances and widths are easy.
Routes are shortest paths through the OSM street network between hand-placed
anchors, so they always follow real streets.
"""

from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

CRS = "EPSG:27700"
DATA = Path(__file__).parent / "data"

# Anchors as (lon, lat). A route is the street path through its anchors in order.
ROUTES: dict[str, list[tuple[float, float]]] = {
    # Waterloo station forecourt -> bridge -> Lancaster Place -> Wellington St -> piazza
    "bridge_spine": [(-0.11255, 51.50395), (-0.11900, 51.51110),
                     (-0.12050, 51.51230), (-0.12198, 51.51180)],
    # Strand west from the Lancaster Place junction, up Southampton St into the piazza
    "strand_west": [(-0.11900, 51.51110), (-0.12180, 51.51070), (-0.12198, 51.51180)],
    # Strand east to St Mary le Strand / Aldwych (car-free since 2022)
    "strand_east": [(-0.11900, 51.51110), (-0.11660, 51.51245), (-0.11480, 51.51300)],
    # The one signalled bus lane (cycle track alongside): bridge, Lancaster Place, Aldwych
    "bus_lane": [(-0.11414, 51.50556), (-0.11620, 51.50790), (-0.11780, 51.51320)],
}
LANE_ROUTES: list[str] = ["bus_lane"]
WALK_ROUTES: list[str] = ["bridge_spine", "strand_west", "strand_east"]

HALF_WIDTH = {"primary": 10.0, "secondary": 10.0, "tertiary": 6.0, "residential": 6.0,
              "unclassified": 6.0, "pedestrian": 4.0, "living_street": 4.0}
DEFAULT_HALF_WIDTH = 3.0  # footways, cycleways, paths, service
ROAD = {"primary", "secondary", "tertiary"}  # the bus lane follows the old carriageway
MAJOR = {"primary", "secondary", "pedestrian", "living_street", "tertiary"}


@dataclass
class Corridor:
    walkable: BaseGeometry
    lane: BaseGeometry
    routes: dict[str, LineString]
    lane_routes: list[str] = field(default_factory=lambda: list(LANE_ROUTES))
    bridge: LineString | None = None  # the lane's centreline across Waterloo Bridge itself
    cycle: BaseGeometry | None = None  # two-way cycle track beside the bus lane
    cycle_route: LineString | None = None  # its centreline


def build_walkable(streets: gpd.GeoDataFrame, buildings: gpd.GeoDataFrame) -> BaseGeometry:
    """Buffer every street by a half-width from its highway tag, minus buildings.

    Elevated streets (OSM layer >= 1, e.g. Waterloo Bridge over the BFI) are added
    back after the buildings are removed, since they pass over them.
    """
    layers = streets["layer"] if "layer" in streets.columns else [None] * len(streets)
    ground, elevated = [], []
    for hw, layer, geom in zip(streets["highway"], layers, streets.geometry):
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            shape = geom  # pedestrian areas, e.g. the piazza
        else:
            shape = geom.buffer(HALF_WIDTH.get(hw, DEFAULT_HALF_WIDTH), cap_style="round")
        try:
            is_up = layer is not None and float(layer) >= 1
        except (TypeError, ValueError):
            is_up = False
        (elevated if is_up else ground).append(shape)
    walkable = unary_union(ground)
    if len(buildings):
        walkable = walkable.difference(unary_union(list(buildings.geometry)))
    return unary_union([walkable, *elevated])


def place_planters(route: LineString, walkable: BaseGeometry, offset: float = 7.5,
                   spacing: float = 24.0, size: tuple[float, float] = (6.0, 2.4)) -> list:
    """Rectangular planters either side of a route, `offset` metres out, every
    `spacing` metres, kept only where they sit fully on the walkable deck."""
    import numpy as np
    from shapely import affinity
    from shapely.geometry import box as _box

    out = []
    for s in np.arange(spacing / 2, route.length - spacing / 2 + 1e-6, spacing):
        p = np.array(route.interpolate(s).coords[0])
        a = np.array(route.interpolate(max(s - 2, 0)).coords[0])
        b = np.array(route.interpolate(min(s + 2, route.length)).coords[0])
        t = (b - a) / np.linalg.norm(b - a)
        n = np.array([-t[1], t[0]])
        ang = float(np.degrees(np.arctan2(t[1], t[0])))
        for side in (-1, 1):
            cx, cy = p + side * offset * n
            rect = affinity.rotate(_box(cx - size[0] / 2, cy - size[1] / 2, cx + size[0] / 2, cy + size[1] / 2),
                                   ang, origin=(cx, cy))
            if walkable.contains(rect.buffer(0.3)):
                out.append(rect)
    return out


def build_lane(routes: dict[str, LineString], lane_routes: list[str], half_width: float = 2.0) -> BaseGeometry:
    return unary_union([routes[n].buffer(half_width, cap_style="flat") for n in lane_routes])


def build_cycle(route: LineString, offset: float = 4.25, half_width: float = 1.5) -> tuple[LineString, BaseGeometry]:
    """A two-way cycle track left of the bus lane (lane half-width 2 m, then a 0.75 m kerb)."""
    centre = route.offset_curve(offset)
    if centre.geom_type != "LineString":  # tight bends can split the offset; keep the main run
        centre = max(centre.geoms, key=lambda g: g.length)
    centre = drop_loops(centre)
    return centre, centre.buffer(half_width, cap_style="flat")


def _bbox() -> tuple[float, float, float, float]:
    lons = [p[0] for pts in ROUTES.values() for p in pts]
    lats = [p[1] for pts in ROUTES.values() for p in pts]
    pad = 0.0012  # ~80 m
    return (min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad)


def _fetch(tags: dict, path: Path) -> gpd.GeoDataFrame:
    if path.exists():
        return gpd.read_file(path)
    gdf = ox.features_from_bbox(_bbox(), tags=tags).reset_index()
    keep = [c for c in ("highway", "name", "tunnel", "area", "building", "layer") if c in gdf.columns]
    gdf = gdf[keep + ["geometry"]]
    path.parent.mkdir(exist_ok=True)
    gdf.to_file(path)
    return gdf


def drop_loops(line: LineString, near: float = 15.0, step: float = 5.0) -> LineString:
    """Cut out-and-back spurs: where the path returns within `near` metres of an earlier
    point after a much longer detour, jump straight there."""
    import numpy as np
    pts = np.array([line.interpolate(s).coords[0] for s in np.arange(0, line.length, step)]
                   + [line.coords[-1]])
    keep, i = [0], 0
    while i < len(pts) - 1:
        d = np.hypot(*(pts[i + 1:] - pts[i]).T)
        arc = step * np.arange(1, len(pts) - i)
        loops = np.where((d < near) & (arc > 3 * d + 30))[0]
        i = i + 1 + (loops[-1] if len(loops) else 0)
        keep.append(i)
    if len(keep) == len(pts):
        return line
    return LineString(pts[keep]).simplify(0.5)


def _route_line(graph, anchors: list[tuple[float, float]]) -> LineString:
    """Street path through the anchors, preferring main streets, in CRS metres."""
    nodes = [ox.distance.nearest_nodes(graph, x, y) for x, y in anchors]
    coords: list[tuple[float, float]] = []
    for a, b in zip(nodes, nodes[1:]):
        path = nx.shortest_path(graph, a, b, weight="cost")
        for u, v in zip(path, path[1:]):
            data = min(graph.get_edge_data(u, v).values(), key=lambda d: d["cost"])
            seg = data.get("geometry") or LineString([(graph.nodes[u]["x"], graph.nodes[u]["y"]),
                                                      (graph.nodes[v]["x"], graph.nodes[v]["y"])])
            pts = list(seg.coords)
            if Point(pts[0]).distance(Point(graph.nodes[u]["x"], graph.nodes[u]["y"])) > 1:
                pts.reverse()
            coords.extend(pts if not coords else pts[1:])
    return LineString(coords)


def _graph():
    path = DATA / "graph.graphml"
    if path.exists():
        g = ox.load_graphml(path)
    else:
        g = ox.graph_from_bbox(_bbox(), network_type="all", simplify=True, retain_all=True)
        g = ox.project_graph(g, to_crs=CRS)
        ox.save_graphml(g, path)
    g = ox.convert.to_undirected(g)  # walkers and the signalled lane ignore one-way rules
    for _, _, d in g.edges(data=True):
        hw = d.get("highway")
        hw = hw[0] if isinstance(hw, list) else hw
        d["cost"] = float(d["length"]) * (1.0 if hw in MAJOR else 2.5)
        d["road"] = hw in ROAD and d.get("tunnel") in (None, "no")  # not the Strand underpass
    return g


def load_corridor() -> Corridor:
    streets = _fetch({"highway": True}, DATA / "streets.gpkg").to_crs(CRS)
    if "tunnel" in streets.columns:
        streets = streets[streets["tunnel"].isna() | (streets["tunnel"] == "no")]
    buildings = _fetch({"building": True}, DATA / "buildings.gpkg").to_crs(CRS)
    buildings = buildings[buildings.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    graph = _graph()
    roads = graph.edge_subgraph([(u, v, k) for u, v, k, d in graph.edges(keys=True, data=True) if d["road"]])
    routes = {}
    for name, anchors in ROUTES.items():
        pts = gpd.GeoSeries([Point(p) for p in anchors], crs="EPSG:4326").to_crs(CRS)
        g = roads if name in LANE_ROUTES else graph
        routes[name] = drop_loops(_route_line(g, [(p.x, p.y) for p in pts]))
    walkable = build_walkable(streets, buildings)
    deck = streets[(streets.get("name") == "Waterloo Bridge") & streets["highway"].isin(["primary"])]
    on_deck = routes[LANE_ROUTES[0]].intersection(unary_union(list(deck.geometry)).buffer(15))
    pieces = [g for g in getattr(on_deck, "geoms", [on_deck]) if g.geom_type == "LineString"]
    bridge = max(pieces, key=lambda g: g.length) if pieces else None
    cycle_route, cycle = build_cycle(routes[LANE_ROUTES[0]])
    return Corridor(walkable=walkable, lane=build_lane(routes, LANE_ROUTES), routes=routes, bridge=bridge,
                    cycle=cycle.difference(build_lane(routes, LANE_ROUTES)), cycle_route=cycle_route)
