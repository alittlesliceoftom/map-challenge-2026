# 30 Maps, 30 Days

<!-- about -->
asliceoftom's [#30DayMapChallenge](https://30daymapchallenge.com/) 2026 portfolio: a calendar of the 30 daily themes, where each finished day opens to an interactive map, why it was made, and where the data comes from. Everything is Python. Live at <https://asliceoftom.com/projects/map-challenge-2026>.
<!-- /about -->

## Getting started (once)

You need **Python 3.11 or newer** (check with `python3 --version`; get it from
<https://www.python.org/downloads/>) and **git**.

1. At the top of <https://github.com/edichavezz/map-challenge-template>, click
   **Use this template → Create a new repository**. Call it anything, e.g. `map-challenge`.
2. Copy your new repository to your computer and go into it:

   ```bash
   git clone https://github.com/YOUR-USERNAME/map-challenge.git
   cd map-challenge
   ```

3. Make it yours:

   ```bash
   python3 setup_challenge.py
   ```

   It asks for your name, your links (website, GitHub, LinkedIn…), your headline and
   your six colours, then sets up Python and shows you a preview. Run it again any time
   to change your answers.

Setting up Python by hand instead:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Every time you open a terminal

```bash
cd map-challenge                 # wherever you cloned it
source .venv/bin/activate        # uses this project's Python and libraries
```

## The daily routine

```bash
python new_day.py 1              # 1. start day 1: creates days/01-points/
python days/01-points/map.py     # 2. run your map code (repeat as you write it)
python build.py --serve --thumbs # 3. see the whole site at http://localhost:8000
```

In each day's folder:

| File           | What it's for                                                         |
|----------------|-----------------------------------------------------------------------|
| `map.py`       | Your map code, set up as a step-by-step skeleton. Running it saves `map.html`. |
| `notes.md`     | Your reasoning. The first line `# ...` is the map's title.            |
| `sources.toml` | Every dataset: name, link, who publishes it, what it is, time, resolution, licence. |
| `data/`        | Downloaded data files (not uploaded to GitHub: they can be big).      |
| `thumb.png`    | Calendar preview. `--thumbs` (re)makes it with Chrome whenever `map.html` changes. |

A day appears as finished on the calendar as soon as its `map.html` (or `map.png` /
`map.jpg`, for static maps and Day 30's pen-and-paper photo) exists. If a source is
missing a field, the day page shows a "missing" flag until you fill it in.

## Settings

`site.toml` holds your name, headline, intro and footer links. `setup_challenge.py`
writes it, and you can edit it by hand any time. `themes.toml` lists the 30 daily
themes; for a different year, copy that year's themes in from
<https://30daymapchallenge.com/>.

## Colours

Every colour lives in `mapkit/palette.py`. The website and your maps both read
from it, so they always match.

```python
from mapkit import palette as P

P.categorical(3)       # "which one": your first 3 colours, in order
P.CATEGORICAL          # all six
P.ramp("sunrise", 5)   # "how much", light -> dark: sunrise, tangerine, meadow, lagoon, berry
P.diverging(7)         # "above / below": blue <- neutral -> red
P.cmap("lagoon")       # for matplotlib / geopandas .plot(cmap=...)
P.PAPER, P.INK         # background and outline colours
```

Your six colours sit between the `# >>>` and `# <<<` lines in `mapkit/palette.py`,
with notes on which ones are pale. To change them, run `python3 setup_challenge.py`
again or edit them there. `HIGHLIGHT` (behind the headline) and `ALERT` (the "missing"
flags) say which of your six the website uses for those.

## Folium helpers

`mapkit/folium_style.py` makes folium maps look like the site:

```python
from mapkit.folium_style import add_basemap, style_map, add_title, add_legend, add_credit, OSM_DATA_CREDIT

m = folium.Map(location=[41.88, -87.63], zoom_start=12, tiles=None)
add_basemap(m, "light")        # "light", "light-nolabels", "dark", "osm", "mapbox"
style_map(m)                   # site font, ink-outlined buttons, paper tooltips
add_title(m, "Title", "subtitle")
cafe, bakery = P.categorical(2)
add_legend(m, "What the colours mean", {"Café": cafe, "Bakery": bakery})
add_credit(m, OSM_DATA_CREDIT) # credit the data you drew, in the map's corner
```

The basemap credits itself, but your data needs its own credit on the map (the
full-screen link shows the map without the day page). For non-OSM data, pass your own
text, e.g. `add_credit(m, "Trees: City of Chicago")`.

The default basemaps (Esri Light/Dark Gray) need no account. Their detail stops around
zoom 16; zoom in closer than that and the tiles get blurry.

## Using Mapbox (the challenge sponsor)

For crisp street-level basemaps, or your own custom style from Mapbox Studio:

1. Make a free account at mapbox.com and copy your **default public token** (starts with `pk.`).
2. In your Mapbox account, restrict the token to the web address(es) where the site will live.
3. Add it to your shell (once): `echo 'export MAPBOX_TOKEN="pk.…"' >> ~/.zshrc`, then open a new terminal.
4. In `map.py`: `add_basemap(m, "mapbox")` or `add_basemap(m, "mapbox", mapbox_style="you/your-style-id")`.

**Never paste the token into `map.py`.** The day page shows your code. As a safety net,
`build.py` hides anything that looks like a token. A public token does end up inside
`map.html`; that's how Mapbox web maps work, and why step 2 matters.

## Putting it online

**On Vercel (free).** Push your repository to GitHub, then at vercel.com import it as
a new project. `vercel.json` already tells Vercel what to do: install
`requirements-site.txt`, run `build.py`, publish `site/`. Every push redeploys.
Vercel doesn't run your `map.py` files (your data isn't in the repository), so
**commit each day's `map.html` and `thumb.png`**: run `python build.py --thumbs`
locally first.

Then put the address Vercel gives you (or your own) in `site_url` in `site.toml`, so
links shared on social media show each map's preview image.

**Under your own website's address (optional).** If your main site is also on Vercel,
it can show this one at e.g. `your-site.com/maps/`. Add this to the main site's
`vercel.json`, using this project's Vercel address:

```json
{
  "redirects": [
    { "source": "/maps", "destination": "/maps/", "permanent": true }
  ],
  "rewrites": [
    { "source": "/maps/", "destination": "https://YOUR-MAP-PROJECT.vercel.app/" },
    { "source": "/maps/:path*", "destination": "https://YOUR-MAP-PROJECT.vercel.app/:path*" }
  ]
}
```

The redirect adds the trailing `/`. Without it, the site's relative links would point
to the wrong place.

Before publishing, check the basemap's terms of use: the default Esri tiles are fine for
trying things out locally, but Mapbox is the safer choice for a public site.

## Checking the builder

```bash
python -m pytest
```

## Credits

This template was made by [Edita Chavez](https://editachavez.com/) for her own
#30DayMapChallenge ([see hers](https://editachavez.com/projects/map-challenge-2026/)).
Your site's footer says "Template by Edita Chavez"; that comes from the `[template]`
part of `site.toml`. Please keep it, and enjoy the challenge!

**Licence:** MIT (see `LICENSE`). Use it, change it and share it, for anything; just
keep the copyright notice in `LICENSE`. The daily themes and prompts in `themes.toml`
come from <https://30daymapchallenge.com/>.
