# How the OpenStreetMap data was fetched

`geometry.py` uses osmnx 2.x (`features_from_bbox` and `graph_from_bbox`) over a bounding box
padded about 80 m around the route anchors in `ROUTES`:

- Streets: every feature with a `highway` tag (`tags={"highway": True}`), with `tunnel` features
  dropped. Cached to `data/streets.gpkg`.
- Buildings: every feature with a `building` tag. Cached to `data/buildings.gpkg`.
- Street network for routing: `graph_from_bbox(..., network_type="all")`, projected to EPSG:27700
  and made undirected. Cached to `data/graph.graphml`.

Delete the files in `data/` to fetch fresh data. Downloaded 8 Nov 2026.
