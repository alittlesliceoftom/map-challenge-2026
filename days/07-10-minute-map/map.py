"""
Day 7 · 10 minute map
The prompt: You have no more than 10 minutes to complete this map.

What I'm mapping: Kenya by county, bivariate: households with electricity vs adults using
mobile money (or with a bank account), DHS 2022, with the high-voltage grid on top.

Run it from the project folder:
    python days/07-10-minute-map/map.py
It saves map.html next to this file. Then see it on the site with:
    python build.py --serve
"""

import json
from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd

from mapkit import palette as P
from branca.element import MacroElement
from jinja2 import Template

from mapkit.folium_style import add_basemap, add_credit, add_title, style_map

HERE = Path(__file__).parent
DATA = HERE / "data"

# DHS county labels that are spelled differently in geoBoundaries
RENAME = {"Tharaka-Nithi": "Tharaka", "Trans-Nzoia": "Trans Nzoia", "Elgeyo Marakwet": "Elgeyo-Marakwet"}


def dhs(indicator: str) -> pd.Series:
    """One DHS indicator by county (rows labelled '..County'; the rest are former provinces,
    except Nairobi, which is both and appears once without the dots)."""
    rows = json.loads((DATA / f"dhs_{indicator}.json").read_text())["Data"]
    s = {r["CharacteristicLabel"].lstrip("."): r["Value"] for r in rows
         if r["CharacteristicLabel"].startswith("..") or r["CharacteristicLabel"] == "Nairobi"}
    return pd.Series(s).rename(index=RENAME)


# ── Data ──────────────────────────────────────────────────────────────────
df = pd.DataFrame({
    "electricity": dhs("HC_ELEC_H_ELC"),
    # women and men 15-49 are asked separately; simple average of the two
    "mobile_money": (dhs("CO_MOBB_W_MBF") + dhs("CO_MOBB_M_MBF")) / 2,
    "bank": (dhs("CO_MOBB_W_BNK") + dhs("CO_MOBB_M_BNK")) / 2,
    # people whose main lighting is a solar lantern / solar home system (e.g. M-KOPA)
    "solar": dhs("HC_LTFL_P_SOL"),
}).round(1)

# Bivariate classes: each variable split into county thirds (0 = low, 2 = high)
for col in df:
    df[f"{col}_k"] = pd.qcut(df[col], 3, labels=False)

counties = gpd.read_file(DATA / "counties.geojson").merge(df, left_on="shapeName", right_index=True, how="left")
assert counties["electricity"].notna().all(), "county name mismatch"
print(df[["electricity", "mobile_money", "bank", "solar"]].describe().round(1))

grid = gpd.read_file(DATA / "tx" / "Kenya Electricity Transmission Network.shp")
grid = grid[grid.STATUS == "Existing"]

# 3x3 bivariate palette (Stevens pink-blue). BIV[y][x]: x = electricity, y = money
BIV = [
    ["#d6d2cc", "#ace4e4", "#5ac8c8"],
    ["#dfb0d6", "#a5add3", "#5698b9"],
    ["#be64ac", "#8c62aa", "#3b4994"],
]


def cuts(col: str) -> str:
    q = df[col].quantile([1 / 3, 2 / 3]).round().astype(int).tolist()
    return f"&lt;{q[0]}% · {q[0]}–{q[1]}% · &gt;{q[1]}%"


def band(col: str, k: int) -> str:
    """The actual range of county values in third k of a column, e.g. '36–54%'."""
    v = df.loc[df[f"{col}_k"] == k, col]
    return f"{v.min():.0f}–{v.max():.0f}%"


NAMES = {"electricity": "Electricity", "mobile_money": "Mobile money", "bank": "Bank account", "solar": "Solar lighting"}

# Each bivariate layer: (x column, y column, layer name). Pink = high y, low x.
PAIRS = [
    ("electricity", "mobile_money", "Electricity × mobile money"),
    ("electricity", "bank", "Electricity × bank account"),
    ("bank", "mobile_money", "Bank account × mobile money"),
    ("solar", "mobile_money", "Solar lighting × mobile money"),
]


def cell_tip(xc: str, yc: str, x: int, y: int) -> str:
    """Hover text for one legend cell: the ranges it stands for and how many counties."""
    n = ((df[f"{xc}_k"] == x) & (df[f"{yc}_k"] == y)).sum()
    return f"{NAMES[xc]} {band(xc, x)}\n{NAMES[yc]} {band(yc, y)}\n{n} counties"


# ── Map ───────────────────────────────────────────────────────────────────
m = folium.Map(location=[0.3, 37.9], zoom_start=6, tiles=None)
add_basemap(m, "light-nolabels")
style_map(m)

TIP = folium.GeoJsonTooltip
fields = ["shapeName", "electricity", "solar", "mobile_money", "bank"]
aliases = ["County", "Households with electricity (%)", "People lit mainly by solar (%)", "Adults using mobile money (%)", "Adults with a bank account (%)"]

groups = []
for i, (xc, yc, label) in enumerate(PAIRS):
    fg = folium.FeatureGroup(name=label, show=i == 0)
    groups.append(fg)
    folium.GeoJson(
        counties[fields + [f"{xc}_k", f"{yc}_k", "geometry"]],
        style_function=lambda f, xc=xc, yc=yc: {
            "fillColor": BIV[f["properties"][f"{yc}_k"]][f["properties"][f"{xc}_k"]],
            "fillOpacity": 0.9, "color": P.INK, "weight": 0.5,
        },
        highlight_function=lambda f: {"weight": 2.5, "color": P.INK},
        tooltip=TIP(fields=fields, aliases=aliases, localize=True),
    ).add_to(fg)
    fg.add_to(m)

lines = folium.FeatureGroup(name="High-voltage grid (33–220 kV)", show=True)
folium.GeoJson(
    grid[["VOLTAGE_KV", "FROM_NM", "TO_NM", "geometry"]],
    style_function=lambda f: {"color": P.ORANGE, "weight": 3 if f["properties"]["VOLTAGE_KV"] >= 132 else 1.5},
    tooltip=TIP(fields=["VOLTAGE_KV", "FROM_NM", "TO_NM"], aliases=["kV", "From", "To"]),
).add_to(lines)
lines.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

add_title(m, "Phones got there first",
          "Kenya by county, 2022. Almost every county uses mobile money; far fewer homes have electricity. "
          "Pink = money without power, blue = both.")

# One bivariate legend per layer (x left→right, y bottom→top); only the active one shows
legends = ""
for i, (xc, yc, _) in enumerate(PAIRS):
    cells = "".join(
        f'<span style="background:{BIV[y][x]};cursor:help" title="{cell_tip(xc, yc, x, y)}"></span>'
        for y in (2, 1, 0) for x in (0, 1, 2)
    )
    legends += f"""
<div class="mk-box mk-legend biv-legend" id="biv-legend-{i}" style="width:230px;{'' if i == 0 else 'display:none'}">
  <b>How to read it (county thirds)</b>
  <div style="display:flex;gap:8px;align-items:center;margin-top:6px">
    <div style="writing-mode:vertical-rl;transform:rotate(180deg);font-size:11px">{NAMES[yc]} ↑</div>
    <div class="biv-grid">{cells}</div>
  </div>
  <div style="font-size:11px;margin-left:22px">{NAMES[xc]} →</div>
  <div style="font-size:10.5px;line-height:1.4;margin-top:6px;color:{P.MUTED}">
    {NAMES[xc]}: {cuts(xc)}<br>
    {NAMES[yc]}: {cuts(yc)}<br>
    <span style="color:{P.ORANGE}">━</span> grid line (33–220 kV)
  </div>
</div>"""
legends += """
<style>
  .biv-grid { display:grid; grid-template-columns:repeat(3,26px); grid-template-rows:repeat(3,26px); gap:2px; }
  .biv-grid span { display:block; }
</style>"""
m.get_root().html.add_child(folium.Element(legends))

# Only one bivariate layer at a time: turning one on turns the others off and swaps the legend
names = [g.get_name() for g in groups]
switch = f"""
{{% macro script(this, kwargs) %}}
(function() {{
  var map = {m.get_name()};
  var layers = [{", ".join(names)}];
  map.on("overlayadd", function(e) {{
    var i = layers.indexOf(e.layer);
    if (i < 0) return;
    // defer: the layer control is still looping over its checkboxes
    setTimeout(function() {{ layers.forEach(function(l, j) {{ if (j !== i && map.hasLayer(l)) map.removeLayer(l); }}); }}, 0);
    document.querySelectorAll(".biv-legend").forEach(function(el, j) {{ el.style.display = j === i ? "" : "none"; }});
  }});
}})();
{{% endmacro %}}
"""
macro = MacroElement()
macro._template = Template(switch)
m.add_child(macro)

add_credit(m, 'Data: <a href="https://dhsprogram.com/">Kenya DHS 2022</a> (KNBS, ICF), '
              '<a href="https://www.geoboundaries.org/">geoBoundaries</a>, '
              '<a href="https://datacatalog.worldbank.org/search/dataset/0040440">World Bank / KETRACO</a>')

m.save(HERE / "map.html")
print("Saved", HERE / "map.html")
