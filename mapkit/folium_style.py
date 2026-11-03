"""
folium_style.py — make folium maps match the website.

    import folium
    from mapkit import palette as P
    from mapkit.folium_style import add_basemap, style_map, add_legend, add_title

    m = folium.Map(location=[41.88, -87.63], zoom_start=12, tiles=None)
    add_basemap(m, "light")                        # the background map
    style_map(m)                                   # site font, ink buttons, paper tooltips
    add_title(m, "Where the bakeries are")         # optional title box, top-left
    cafe, bakery = P.categorical(2)
    add_legend(m, "Type of shop", {"Café": cafe, "Bakery": bakery})
    add_credit(m, OSM_DATA_CREDIT)                 # credit YOUR data, bottom-right corner
    m.save("map.html")

These only change how the map LOOKS. Everything about your data — what goes on
the map, colours, tooltips — is still your folium code.
"""

import os
from html import escape

import folium
from branca.element import MacroElement
from jinja2 import Template

from mapkit import palette as P

_FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:'
    'opsz,wght@12..96,400;12..96,600;12..96,800&display=swap" rel="stylesheet">'
)

_CSS = f"""
<style>
  .leaflet-container {{ font-family: "Bricolage Grotesque", system-ui, sans-serif; background: {P.WATER}; }}
  .leaflet-bar {{ border: 1.5px solid {P.INK} !important; border-radius: 0 !important; box-shadow: none !important; }}
  .leaflet-bar a {{ background: {P.PAPER}; color: {P.INK}; border-radius: 0 !important; border-bottom-color: {P.INK} !important; }}
  .leaflet-bar a:hover {{ background: {P.HIGHLIGHT}; }}
  .leaflet-tooltip, .leaflet-popup-content-wrapper {{
    background: {P.PAPER}; color: {P.INK}; border: 1.5px solid {P.INK};
    border-radius: 0; box-shadow: 3px 3px 0 {P.INK}; font-size: 13px;
  }}
  .leaflet-popup-tip {{ background: {P.INK}; }}
  .leaflet-tooltip-top:before {{ border-top-color: {P.INK}; }}
  .leaflet-control-attribution {{ background: rgba(241, 236, 226, .85) !important; color: {P.MUTED}; font-size: 10px; }}
  .mk-box {{
    position: fixed; z-index: 1000; background: {P.PAPER}; color: {P.INK};
    border: 1.5px solid {P.INK}; padding: 10px 12px; font-family: "Bricolage Grotesque", system-ui, sans-serif;
  }}
  .mk-legend {{ right: 12px; bottom: 28px; font-size: 13px; line-height: 1.7; max-width: 260px; }}
  .mk-legend b {{ display: block; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }}
  .mk-legend i {{ display: inline-block; width: 13px; height: 13px; margin-right: 7px; vertical-align: -2px; border: 1.5px solid {P.INK}; }}
  .mk-legend i.circle {{ border-radius: 50%; }}
  .mk-legend i.line {{ height: 4px; width: 22px; border: 0; vertical-align: 3px; }}
  .mk-title {{ left: 56px; top: 12px; max-width: 360px; }}
  .mk-title h1 {{ margin: 0; font-size: 22px; font-weight: 800; letter-spacing: -0.03em; line-height: 1.1; }}
  .mk-title p {{ margin: 4px 0 0; font-size: 13px; color: {P.MUTED}; }}
</style>
"""


# Background maps ("tiles"). A tile URL has {z}/{x}/{y} slots that Leaflet fills in
# as you pan and zoom. If one of these ever stops working, change it here only.
#
# The Esri ones need no account. Their sharp detail stops at zoom 16 (a few streets);
# closer than that the tiles are stretched. For crisp street-level maps use Mapbox.
_ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/{layer}/MapServer/tile/{{z}}/{{y}}/{{x}}"
_ESRI_CREDIT = ("Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors, "
                "and the GIS User Community")
_OSM_CREDIT = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
_MAPBOX_CREDIT = ('&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> ' + _OSM_CREDIT)

BASEMAPS = {
    # name:            (tile URL, labels drawn on top (or None), credit, sharpest zoom)
    "light":          (_ESRI.format(layer="World_Light_Gray_Base"), _ESRI.format(layer="World_Light_Gray_Reference"), _ESRI_CREDIT, 16),
    "light-nolabels": (_ESRI.format(layer="World_Light_Gray_Base"), None, _ESRI_CREDIT, 16),
    "dark":           (_ESRI.format(layer="World_Dark_Gray_Base"), _ESRI.format(layer="World_Dark_Gray_Reference"), _ESRI_CREDIT, 16),
    "osm":            ("https://tile.openstreetmap.org/{z}/{x}/{y}.png", None, _OSM_CREDIT, 19),
}


def add_basemap(m, style="light", mapbox_style="mapbox/light-v11"):
    """Add a background map.

    style: "light" (default), "light-nolabels", "dark", "osm", or "mapbox".

    "mapbox" needs a free Mapbox token in the MAPBOX_TOKEN environment variable
    (never paste it into your code; see README). mapbox_style can be any style
    id, including your own from Mapbox Studio, e.g. "yourname/abc123".
    """
    if style == "mapbox":
        token = os.environ.get("MAPBOX_TOKEN")
        if not token:
            raise RuntimeError("No MAPBOX_TOKEN found. See the README section 'Using Mapbox'.")
        url = f"https://api.mapbox.com/styles/v1/{mapbox_style}/tiles/256/{{z}}/{{x}}/{{y}}@2x?access_token={token}"
        folium.TileLayer(tiles=url, attr=_MAPBOX_CREDIT, name="Mapbox", max_zoom=20).add_to(m)
        return m
    if style not in BASEMAPS:
        raise ValueError(f"Unknown basemap {style!r}. Choose from: {', '.join(BASEMAPS)}, mapbox")
    base, labels, credit, sharpest = BASEMAPS[style]
    folium.TileLayer(tiles=base, attr=credit, name=style, max_native_zoom=sharpest, max_zoom=19).add_to(m)
    if labels:
        folium.TileLayer(tiles=labels, attr=credit, name=f"{style} labels", overlay=True,
                         control=False, max_native_zoom=sharpest, max_zoom=19).add_to(m)
    return m


def style_map(m):
    """Site font, ink-outlined zoom buttons, paper-coloured tooltips and popups."""
    m.get_root().header.add_child(folium.Element(_FONT_LINK + _CSS))
    return m


def add_legend(m, title, items, shape="circle"):
    """A legend box in the bottom-right corner.

    items: {"label": "#hexcolour", ...}   shape: "circle", "square" or "line"
    """
    rows = "".join(
        f'<div><i class="{shape}" style="background:{colour}"></i>{escape(str(label))}</div>'
        for label, colour in items.items()
    )
    html = f'<div class="mk-box mk-legend"><b>{escape(title)}</b>{rows}</div>'
    m.get_root().html.add_child(folium.Element(html))
    return m


OSM_DATA_CREDIT = ('Data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
                   'contributors')


class _Credit(MacroElement):
    _template = Template("""
        {% macro script(this, kwargs) %}
            {{ this._parent.get_name() }}.attributionControl.addAttribution({{ this.html|tojson }});
        {% endmacro %}
    """)

    def __init__(self, html):
        super().__init__()
        self._name = "Credit"
        self.html = html


def add_credit(m, html):
    """Credit your DATA in the map's bottom-right corner, next to the basemap's credit.

    The basemap credits itself, but the data you draw on top needs its own credit
    (most licences ask for it on the map, not just on the day page). html can
    include a link, e.g. OSM_DATA_CREDIT for anything from OpenStreetMap.
    """
    _Credit(html).add_to(m)
    return m


def add_title(m, title, subtitle=""):
    """A title box in the top-left corner (next to the zoom buttons)."""
    sub = f"<p>{escape(subtitle)}</p>" if subtitle else ""
    html = f'<div class="mk-box mk-title"><h1>{escape(title)}</h1>{sub}</div>'
    m.get_root().html.add_child(folium.Element(html))
    return m
