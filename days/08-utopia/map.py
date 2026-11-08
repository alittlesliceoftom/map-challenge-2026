"""
Day 8 · Utopia
The prompt: A map of something which could be.

What I'm mapping: (write one sentence here once you've decided)

Run it from the project folder:
    python days/08-utopia/map.py
It saves map.html next to this file. Then see it on the site with:
    python build.py --serve
"""

from pathlib import Path

import folium

from mapkit import palette as P
from mapkit.folium_style import add_basemap, style_map

HERE = Path(__file__).parent      # this day's folder
DATA = HERE / "data"              # put the data files you download in here


# ── STEP 1 · An empty map ─────────────────────────────────────────────────
# This step already works: run the file, then open map.html in your browser.
# TODO: move the map to your place. `location` is [latitude, longitude]
#       (in Google Maps, right-click a spot to copy its numbers).
#       `zoom_start`: 2 = the world, 6 = a country, 12 = a city, 16 = a street.
m = folium.Map(location=[20, 0], zoom_start=2, tiles=None)
add_basemap(m, "light")           # background map: also "light-nolabels", "dark", "osm", "mapbox"
style_map(m)                      # the site's font + ink-outlined buttons


# ── STEP 2 · Load your data ───────────────────────────────────────────────
# TODO: download your dataset into the data/ folder, then read it in.
#   A table with latitude/longitude columns (CSV):  pandas  → pd.read_csv(...)
#   Shapes (GeoJSON, shapefile, GeoPackage):        geopandas → gpd.read_file(...)
# Then LOOK at it before you map anything:
#   how many rows? which columns? what do the first few rows look like?


# ── STEP 3 · Put the data on the map ──────────────────────────────────────
# TODO: draw your data. Useful folium pieces:
#   one point:    folium.CircleMarker(location=[lat, lon], radius=...)
#   one line:     folium.PolyLine(locations=[[lat, lon], [lat, lon], ...])
#   shapes:       folium.GeoJson(your_geodataframe)
# Anything you create needs .add_to(m) to appear on the map.
# Points? Loop over your rows and add one marker per row.


# ── STEP 4 · Colour it with the palette ───────────────────────────────────
# TODO: pick colours from mapkit.palette (print(P.CATEGORICAL) to see them):
#   "which one" (types/groups):  P.categorical(n)  — use them in order
#   "how much" (amounts):        P.ramp("sunrise", n)
# Give filled shapes a thin outline: color=P.INK, weight=1
# (and fill_color=..., fill_opacity=... for the inside).


# ── STEP 5 · Make it talk: tooltips and popups ────────────────────────────
# TODO: a tooltip shows on hover, a popup on click.
#   folium.CircleMarker(..., tooltip="text", popup="text")
# Show the one or two facts that make someone go "oh!" — not every column.


# ── STEP 6 · A title and a legend ─────────────────────────────────────────
# TODO: from mapkit.folium_style import add_title, add_legend
#   add_title(m, "Title", "one-line subtitle")
#   add_legend(m, "What the colours mean", {"label": colour, ...})


# ── Save ──────────────────────────────────────────────────────────────────
m.save(HERE / "map.html")
print("Saved", HERE / "map.html")
