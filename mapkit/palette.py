"""
palette.py — every colour used by the website AND by your maps.

Change a colour here and it changes everywhere on the next build.

    from mapkit import palette as P

    P.categorical(3)        # the first 3 "which one" colours, in order
    P.CATEGORICAL           # all 6 (their names: P.CATEGORICAL_NAMES)
    P.ramp("sunrise", 5)    # "how much" colours: light -> dark, 5 steps
    P.diverging(7)          # "above / below": blue <- middle -> red
    P.cmap("lagoon")        # the same ramp as a matplotlib colormap
    P.PAPER, P.INK          # page background and outline colour
    P.TUBE_LINES["Victoria"]  # official London Underground line colours

Rules of thumb:

* Use categorical colours IN ORDER. Ask for as many as you need; don't skip
  around.
* Give filled shapes a thin INK outline — it's part of the look and it keeps
  the palest colours visible.
* More than 6 categories? Group the small ones into "Other" instead of
  inventing a 7th colour.
* Notes on your six colours (which ones are pale, etc.) sit right next to
  them, in the block between the >>> and <<< lines below.
"""

# ---------------------------------------------------------------------------
# Base colours: page, outlines, basemap
# ---------------------------------------------------------------------------
PAPER = "#f1ece2"   # page background (newsprint)
INK = "#171412"     # text, outlines, grid lines
CREAM = "#f6f1e7"   # light text on dark colours
MUTED = "#5a5248"   # secondary text
DOTS = "#cbc2b3"    # the dotted pattern on empty calendar days
LAND = "#f8f4ec"    # land on your own basemaps
WATER = "#d3e0e0"   # water on your own basemaps
MIDDLE = "#e9e3d6"  # the neutral middle of the diverging ramp

# ---------------------------------------------------------------------------
# Categorical: "which one" (types, groups, names). Fixed order.
# ---------------------------------------------------------------------------
# >>> YOUR SIX COLOURS: Okabe–Ito, the classic colourblind-safe set (Okabe & Ito, 2008)
# (setup_challenge.py rewrites everything from here down to the <<< line.
#  You can also edit the colours by hand; just keep the >>> and <<< lines.)
# YELLOW is very light on paper: use it for filled shapes with an INK
# outline (points, polygons), not for thin lines or text.
ORANGE       = "#e69f00"
SKY_BLUE     = "#56b4e9"
BLUISH_GREEN = "#009e73"
YELLOW       = "#f0e442"
BLUE         = "#0072b2"
VERMILLION   = "#d55e00"

CATEGORICAL = [ORANGE, SKY_BLUE, BLUISH_GREEN, YELLOW, BLUE, VERMILLION]
CATEGORICAL_NAMES = ["orange", "sky-blue", "bluish-green", "yellow", "blue", "vermillion"]

HIGHLIGHT = YELLOW   # behind the headline's 2nd line, under your name
ALERT = VERMILLION   # the "missing" flags on day pages
# <<< YOUR SIX COLOURS

# ---------------------------------------------------------------------------
# Sequential: "how much". Each ramp goes light -> dark (7 steps).
# They shift hue as they darken (like a sunset) so they stay bright,
# but lightness always goes down steadily, so "darker" always means "more".
# ---------------------------------------------------------------------------
RAMPS = {
    # heat, density, intensity — the go-to
    "sunrise":   ["#fff3b8", "#ffc940", "#ff921a", "#f05e2f", "#d5263e", "#a02046", "#6e1747"],
    # one colour family, for amounts
    "tangerine": ["#ffe7c7", "#ffc27e", "#ff9743", "#f46c17", "#db4a0f", "#b53912", "#8f2a12"],
    # nature, vegetation, parks, rural
    "meadow":    ["#f8f5b8", "#c0df69", "#7ac75c", "#22a88a", "#15847f", "#13616f", "#163f5a"],
    # water, depth, rain, cold
    "lagoon":    ["#e6f2ff", "#a9d0ff", "#71acfa", "#4785ed", "#3b5ad4", "#3934a5", "#2b1f63"],
    # people, nightlife, taste
    "berry":     ["#ffe0d8", "#ffac9c", "#f8756f", "#de3f54", "#b02051", "#741a5a", "#3f1446"],
}

# Diverging: "above / below a middle value". Blue side, neutral middle, red side.
DIVERGING = ["#2f45b8", "#5a94ef", "#c4dcfb", MIDDLE, "#ffc59a", "#f36a3f", "#b81d3a"]

# ---------------------------------------------------------------------------
# Real-world colours: London Underground lines (TfL's own colours).
# The one exception to "max 6 categories": people already know these colours,
# so the map reads better with them than with our palette.
# Keys are spelled exactly like the OpenStreetMap `line` tag, so
# P.TUBE_LINES[row["line"]] works. Shared tunnels have several names in one
# tag ("Circle;District") — split on ";" first.
# Watch out: Circle (yellow) is pale on light basemaps, and Northern is
# almost the same colour as INK.
# ---------------------------------------------------------------------------
TUBE_LINES = {
    "Bakerloo": "#B05F0F",
    "Central": "#E02525",
    "Circle": "#FECE08",
    "District": "#04783F",
    "Hammersmith & City": "#EE9BAC",
    "Jubilee": "#7B848B",
    "Metropolitan": "#861A54",
    "Northern": "#231F20",
    "Piccadilly": "#1B3F94",
    "Victoria": "#0C9FDC",
    "Waterloo & City": "#6DC7B0",
}


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------
def categorical(n):
    """The first n "which one" colours, in the fixed order."""
    if not 1 <= n <= len(CATEGORICAL):
        raise ValueError(
            f"categorical() gives 1 to {len(CATEGORICAL)} colours, you asked for {n}. "
            "With more categories, group the small ones into 'Other'."
        )
    return CATEGORICAL[:n]


def ramp(name, n=7):
    """n colours from a "how much" ramp, light -> dark."""
    if name not in RAMPS:
        raise ValueError(f"Unknown ramp {name!r}. Choose from: {', '.join(RAMPS)}")
    return _sample(RAMPS[name], n)


def diverging(n=7):
    """n colours from the diverging ramp. Use an odd n to get a neutral middle."""
    return _sample(DIVERGING, n)


def cmap(name, n=None):
    """A ramp as a matplotlib colormap (for geopandas .plot(cmap=...)).

    name: a ramp name ("sunrise", "lagoon", ...) or "diverging".
    n:    if given, a stepped colormap with n classes instead of a smooth one.
    """
    from matplotlib.colors import LinearSegmentedColormap, ListedColormap

    stops = DIVERGING if name == "diverging" else RAMPS[name]
    if n:
        return ListedColormap(_sample(stops, n), name=f"{name}_{n}")
    return LinearSegmentedColormap.from_list(name, stops)


def text_on(background):
    """INK or CREAM — whichever text colour reads better on this background."""
    contrast_with_ink = (_luminance(background) + 0.05) / (_luminance(INK) + 0.05)
    return INK if contrast_with_ink >= 5.5 else CREAM


def day_colour(day):
    """The highlight colour for a challenge day on the calendar (cycles the 6)."""
    return CATEGORICAL[(day - 1) % len(CATEGORICAL)]


def css_variables():
    """All colours as CSS custom properties, for the website's stylesheet."""
    lines = [
        f"  --paper: {PAPER};", f"  --ink: {INK};", f"  --cream: {CREAM};",
        f"  --muted: {MUTED};", f"  --dots: {DOTS};", f"  --land: {LAND};",
        f"  --water: {WATER};", f"  --middle: {MIDDLE};",
        f"  --highlight: {HIGHLIGHT};", f"  --on-highlight: {text_on(HIGHLIGHT)};",
        f"  --alert: {ALERT};", f"  --on-alert: {text_on(ALERT)};",
    ]
    for name, hex_ in zip(CATEGORICAL_NAMES, CATEGORICAL):
        lines.append(f"  --{name}: {hex_};")
    for name, stops in RAMPS.items():
        for i, hex_ in enumerate(stops, start=1):
            lines.append(f"  --{name}-{i}: {hex_};")
    return ":root {\n" + "\n".join(lines) + "\n}\n"


# ---------------------------------------------------------------------------
# Helpers (you don't need to read these)
# ---------------------------------------------------------------------------
def _hex_to_rgb(hex_):
    hex_ = hex_.lstrip("#")
    return tuple(int(hex_[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#" + "".join(f"{round(v):02x}" for v in rgb)


def _sample(stops, n):
    """Pick n evenly spaced colours along a list of colour stops."""
    if n == len(stops):
        return list(stops)
    if n == 1:
        return [stops[len(stops) // 2]]
    out = []
    for i in range(n):
        pos = i * (len(stops) - 1) / (n - 1)
        lo = int(pos)
        hi = min(lo + 1, len(stops) - 1)
        t = pos - lo
        a, b = _hex_to_rgb(stops[lo]), _hex_to_rgb(stops[hi])
        out.append(_rgb_to_hex([a[k] + (b[k] - a[k]) * t for k in range(3)]))
    return out


def _luminance(hex_):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in _hex_to_rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
