import json
import re

import folium

from mapkit.folium_style import OSM_DATA_CREDIT, add_basemap, add_credit


def test_data_credit_is_added_to_the_map_corner_after_the_map_exists():
    m = folium.Map(location=[51.5, -0.1], zoom_start=12, tiles=None)
    add_basemap(m, "light")
    add_credit(m, OSM_DATA_CREDIT)
    html = m.get_root().render()

    call = f"{m.get_name()}.attributionControl.addAttribution("
    assert call in html
    created = re.search(rf"var {m.get_name()} = L\.map\(", html)
    assert created and created.start() < html.index(call)

    # The credit text arrives as a safe JS string that decodes back to the exact HTML.
    arg = html[html.index(call) + len(call):].split(");", 1)[0]
    assert json.loads(arg) == OSM_DATA_CREDIT
    assert "openstreetmap.org/copyright" in OSM_DATA_CREDIT
