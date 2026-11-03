"""
Day 1 · Points
The prompt: A map challenge classic. Map with points.

What I'm mapping: London's octagonal towers and spires, spotted and saved in a Google Maps list.

Run it from the project folder:
    python days/01-points/map.py
It saves map.html next to this file. Then see it on the site with:
    python build.py --serve
"""

import base64
import math
from pathlib import Path

import folium
import pandas as pd

from mapkit import palette as P
from mapkit.folium_style import add_basemap, add_credit, add_legend, add_title, style_map

HERE = Path(__file__).parent      # this day's folder
DATA = HERE / "data"              # put the data files you download in here


# ── STEP 1 · An empty map ─────────────────────────────────────────────────
# This step already works: run the file, then open map.html in your browser.
# TODO: move the map to your place. `location` is [latitude, longitude]
#       (in Google Maps, right-click a spot to copy its numbers).
#       `zoom_start`: 2 = the world, 6 = a country, 12 = a city, 16 = a street.
m = folium.Map(location=[51.537756, -0.17832], zoom_start=12, tiles=None)
add_basemap(m, "light")           # background map: also "light-nolabels", "dark", "osm", "mapbox"
style_map(m)                      # the site's font + ink-outlined buttons


# ── STEP 2 · Load your data ───────────────────────────────────────────────
# towers.csv is the master list: just append a row to add a tower.
#   type:     Public building / House / Church / Unknown
#   verified: yes / no   (no = dashed, pale marker, and the filter's "Unverified" layer)
#   originally_water_tower: yes / no (adds a line to the popup + a filter)
#   shape:    octagonal / hexagonal (hexagons can be hidden with the "Include hexagonal herrings?" box)
#   image_url: photo to show on hover. Change it, then run fetch_images.py
#   (it downloads to images/ and fills the image + keeps the site self-contained)
#   link:     "More" link in the popup     image: image URL shown in the popup (optional)
towers = pd.read_csv(HERE / "towers.csv", keep_default_na=False)
print(len(towers), "towers,", (towers.verified == "no").sum(), "unverified")

# ── STEP 4-5 · Octagon markers: colour = type, dashed outline = unverified ─
TYPES = ["Public building", "House", "Church", "Unknown"]
colours = dict(zip(TYPES, P.categorical(len(TYPES))))

# An octagon as an SVG icon, so it stays the same pixel size at every zoom.
SIZE = 22
OCTAGON = "".join(
    f"{SIZE/2 + (SIZE/2 - 1) * math.cos(math.radians(22.5 + 45 * i)):.1f},"
    f"{SIZE/2 + (SIZE/2 - 1) * math.sin(math.radians(22.5 + 45 * i)):.1f} "
    for i in range(8)
)

def photo(filename):
    """A photo from images/ as an inline data URI, so map.html needs no other files."""
    if not filename:
        return ""
    data = base64.b64encode((HERE / "images" / filename).read_bytes()).decode()
    return f"data:image/jpeg;base64,{data}"


HEXAGON = "".join(
    f"{SIZE/2 + (SIZE/2 - 1) * math.cos(math.radians(60 * i)):.1f},"
    f"{SIZE/2 + (SIZE/2 - 1) * math.sin(math.radians(60 * i)):.1f} "
    for i in range(6)
)

for t in towers.itertuples():
    hexa = t.shape == "hexagonal"
    ok = t.verified == "yes"
    svg = (
        f'<svg width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}">'
        f'<polygon points="{HEXAGON if hexa else OCTAGON}" fill="{colours[t.type]}" fill-opacity="{0.95 if ok else 0.45}" '
        f'stroke="{P.INK}" stroke-width="1.5"{"" if ok else " stroke-dasharray=\"3 2\""}/></svg>'
    )
    src = photo(t.image)
    credit = f'<div style="font-size:10px;opacity:.7">Photo: {t.image_credit}</div>' if t.image_credit else ""
    hover = f"<b>{t.name}</b>" + (
        f'<br><img src="{src}" style="width:220px;margin-top:4px;display:block">{credit}' if src else ""
    )
    more = f'<br><a href="{t.link}" target="_blank" rel="noopener">More &rarr;</a>' if t.link else ""
    tip = (
        f"<b>{t.name}</b><br>{t.type}" + (" · hexagonal!" if hexa else "") + ("" if ok else " (unverified)")
        + ("<br><i>Originally a water tower</i>" if t.originally_water_tower == "yes" else "")
        + (f"<br>{t.note}" if t.note else "") + more
    )
    folium.Marker(
        location=[t.lat, t.lon],
        icon=folium.DivIcon(
            html=svg, icon_size=(SIZE, SIZE), icon_anchor=(SIZE // 2, SIZE // 2),
            class_name=f"tower ver-{t.verified} water-{t.originally_water_tower or 'no'} shape-{'hex' if hexa else 'oct'}",
        ),
        popup=folium.Popup(tip, max_width=260),
        tooltip=folium.Tooltip(hover, sticky=False),
    ).add_to(m)

# Filters: tick boxes (top right) show/hide markers by their CSS classes. A tower
# shows only if BOTH its filter boxes are ticked.
FILTERS = """
<div class="mk-box" style="position:absolute;top:12px;right:12px;z-index:1000;font-size:13px;line-height:1.7">
  <b>Show</b>
  <label style="display:block"><input type="checkbox" data-f="ver-yes" checked> Verified octagonal</label>
  <label style="display:block"><input type="checkbox" data-f="ver-no" checked> Unverified (to check)</label>
  <hr style="margin:4px 0">
  <label style="display:block"><input type="checkbox" data-f="water-yes" checked> Originally a water tower</label>
  <hr style="margin:4px 0">
  <label style="display:block"><input type="checkbox" data-f="shape-hex" checked> Include hexagonal herrings?</label>
</div>
<script>
document.addEventListener("DOMContentLoaded", function () {
  var boxes = document.querySelectorAll("[data-f]");
  function apply() {
    var on = {};
    boxes.forEach(function (b) { on[b.dataset.f] = b.checked; });
    document.querySelectorAll(".tower").forEach(function (el) {
      var show = ["ver-", "water-", "shape-"].every(function (prefix) {
        var c = Array.from(el.classList).find(function (x) { return x.indexOf(prefix) === 0; });
        return on[c] !== false;  // water-no and shape-oct have no box: always shown
      });
      el.style.display = show ? "" : "none";
    });
  }
  boxes.forEach(function (b) { b.addEventListener("change", apply); });
  apply();
});
</script>
"""
m.get_root().html.add_child(folium.Element(FILTERS))

# Fit the view to the towers
m.fit_bounds([[towers.lat.min(), towers.lon.min()], [towers.lat.max(), towers.lon.max()]], padding=(30, 30))

# ── STEP 6 · A title, legend and credit ───────────────────────────────────
add_title(m, "London's octagonal towers", "Spotted around town; the list keeps growing")
add_legend(m, "Building type", colours)
m.get_root().header.add_child(folium.Element(
    "<style>.mk-legend i{border-radius:0!important;clip-path:polygon(30% 0,70% 0,100% 30%,100% 70%,70% 100%,30% 100%,0 70%,0 30%)}</style>"
))
add_credit(m, "Towers: my own Google Maps list plus Historic England, Wikipedia and other sources linked per tower")

# ── Save ──────────────────────────────────────────────────────────────────
m.save(HERE / "map.html")
print("Saved", HERE / "map.html")
