"""
build.py — turns the days/ folders into the website in site/.

    python build.py             build the site into site/
    python build.py --serve     build, then show it at http://localhost:8000
    python build.py --thumbs    also make calendar previews of interactive maps
                                (takes a screenshot with Google Chrome)

How a day gets onto the site
----------------------------
Each day lives in a folder like days/01-points/ containing:

    map.py        your code. Running it saves the map next to it:
                  map.html (interactive) or map.png / map.jpg (static, or a photo)
    notes.md      your reasoning. The first line "# ..." is the map's title.
    sources.toml  where the data comes from (one [[source]] block per dataset)
    thumb.png     optional: the preview image for the calendar square

A day appears as finished on the calendar as soon as its map file exists.
"""

from __future__ import annotations

import argparse
import ast
import calendar
import datetime as dt
import functools
import http.server
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

from mapkit import palette as P

ROOT = Path(__file__).resolve().parent
DAYS_DIR = ROOT / "days"
SITE_DIR = ROOT / "site"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"

# The map file a day can have, in order of preference.
MAP_FILES = ["map.html", "map.png", "map.jpg", "map.jpeg", "map.webp"]

# Every data source needs all of these. Missing ones are flagged on the page.
SOURCE_FIELDS = {
    "name": "Name",
    "url": "Link",
    "from": "From",
    "what": "What",
    "time": "Time",
    "resolution": "Resolution",
    "licence": "Licence",
}

# Anything that looks like an access token (e.g. a Mapbox "pk.…" token).
# The day page shows your code, so these get blanked out before publishing.
SECRET_PATTERN = re.compile(r"\b(?:pk|sk|tk)\.[A-Za-z0-9_\-.]{20,}")

# Nicer names for libraries in the "How it was made" section.
TOOL_NAMES = {"osmnx": "OSMnx", "plotly": "Plotly", "pydeck": "pydeck", "sklearn": "scikit-learn"}


# ---------------------------------------------------------------------------
# One challenge day
# ---------------------------------------------------------------------------
@dataclass
class Day:
    number: int
    theme: str
    prompt: str
    date: dt.date
    folder: Path | None = None
    map_file: Path | None = None
    title: str = ""
    notes_html: str = ""
    sources: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    code: str = ""
    thumb: str = ""                       # preview image file name, if any
    warnings: list = field(default_factory=list)

    @property
    def done(self):
        return self.map_file is not None

    @property
    def slug(self):
        return f"{self.number:02d}"

    @property
    def is_image(self):
        return self.done and self.map_file.suffix != ".html"

    @property
    def colour(self):
        return P.day_colour(self.number)

    @property
    def text_colour(self):
        return P.text_on(self.colour)

    @property
    def date_label(self):
        return f"{self.date:%A} {self.date.day} {self.date:%B %Y}"


# ---------------------------------------------------------------------------
# Reading the days/ folders
# ---------------------------------------------------------------------------
def load_toml(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def find_day_folders(days_dir):
    """{1: Path('days/01-points'), ...} for every folder named like '01-something'."""
    folders = {}
    if days_dir.exists():
        for path in sorted(days_dir.iterdir()):
            match = re.match(r"^(\d{1,2})-", path.name)
            if path.is_dir() and match:
                folders[int(match.group(1))] = path
    return folders


def read_notes(folder):
    """Returns (title, html). The first '# heading' line is the title."""
    notes = folder / "notes.md"
    if not notes.exists():
        return "", ""
    lines = notes.read_text(encoding="utf-8").strip().splitlines()
    title = ""
    if lines and lines[0].startswith("# "):
        title = lines.pop(0)[2:].strip()
    body = "\n".join(lines).strip()
    html = markdown.markdown(body, extensions=["extra", "sane_lists"]) if body else ""
    return title, html


def read_sources(folder, warnings):
    """Reads sources.toml and marks which fields are missing in each source."""
    path = folder / "sources.toml"
    if not path.exists():
        warnings.append("no sources.toml")
        return []
    try:
        data = load_toml(path)
    except tomllib.TOMLDecodeError as err:
        warnings.append(f"sources.toml has a typo: {err}")
        return []
    sources = []
    for i, raw in enumerate(data.get("source", []), start=1):
        source = {key: str(raw.get(key, "")).strip() for key in SOURCE_FIELDS}
        source["missing"] = [key for key in SOURCE_FIELDS if not source[key]]
        for key in source["missing"]:
            warnings.append(f"source {i} ({source['name'] or 'unnamed'}): '{key}' is empty")
        sources.append(source)
    if not sources:
        warnings.append("sources.toml lists no [[source]] yet")
    return sources


def find_tools(code):
    """Which libraries does map.py import? (skips Python's built-in modules and mapkit)"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ["Python"]
    tools = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if top in sys.stdlib_module_names or top == "mapkit":
                continue
            label = TOOL_NAMES.get(top, top)
            if label not in tools:
                tools.append(label)
    return ["Python"] + tools


def load_days(days_dir, settings):
    """All 30 days: the theme for each, plus your map, notes and sources if they exist."""
    themes = load_toml(ROOT / "themes.toml")["day"]
    folders = find_day_folders(days_dir)
    days = []
    for t in themes:
        day = Day(
            number=t["day"],
            theme=t["theme"],
            prompt=t.get("prompt", ""),
            date=dt.date(settings["year"], settings["month"], t["day"]),
        )
        folder = folders.get(day.number)
        if folder:
            day.folder = folder
            day.map_file = next((folder / f for f in MAP_FILES if (folder / f).exists()), None)
            day.title, day.notes_html = read_notes(folder)
            day.sources = read_sources(folder, day.warnings)
            code_file = folder / "map.py"
            if code_file.exists():
                code = code_file.read_text(encoding="utf-8")
                if SECRET_PATTERN.search(code):
                    day.warnings.append("map.py contains what looks like a token — hidden on the page. "
                                        "Use os.environ['MAPBOX_TOKEN'] instead.")
                    code = SECRET_PATTERN.sub("[TOKEN REMOVED]", code)
                day.code = code
                day.tools = find_tools(code)
            if day.done and not day.title:
                day.warnings.append("notes.md has no '# Title' line")
        days.append(day)
    return days


# ---------------------------------------------------------------------------
# Calendar previews (optional)
# ---------------------------------------------------------------------------
def find_chrome():
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chrome"),
    ]
    return next((c for c in candidates if c and Path(c).exists()), None)


def make_thumbnail(map_html, png):
    """Screenshot an interactive map into a PNG for the calendar square."""
    chrome = find_chrome()
    if not chrome:
        print("  (no Google Chrome found — skipping previews)")
        return False
    subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--window-size=560,504", "--virtual-time-budget=8000",
         f"--screenshot={png}", map_html.resolve().as_uri()],
        capture_output=True, timeout=90,
    )
    return png.exists()


# ---------------------------------------------------------------------------
# Writing the website
# ---------------------------------------------------------------------------
def build(out_dir=SITE_DIR, days_dir=DAYS_DIR, make_thumbs=False, settings=None):
    if settings is None:
        settings = load_toml(ROOT / "site.toml")
    days = load_days(days_dir, settings)
    done = [d for d in days if d.done]

    # Start from an empty site/ folder.
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "assets").mkdir(parents=True)
    shutil.copytree(STATIC_DIR, out_dir / "assets", dirs_exist_ok=True)
    (out_dir / "assets" / "palette.css").write_text(P.css_variables(), encoding="utf-8")

    # Copy each finished day's map (and preview) into site/days/NN/.
    for day in done:
        target = out_dir / "days" / day.slug
        target.mkdir(parents=True)
        shutil.copy2(day.map_file, target / day.map_file.name)
        thumb = day.folder / "thumb.png"
        # With --thumbs, (re)make the preview whenever the map is newer than it.
        outdated = not thumb.exists() or thumb.stat().st_mtime < day.map_file.stat().st_mtime
        if make_thumbs and not day.is_image and outdated:
            print(f"  making preview for day {day.slug}…")
            make_thumbnail(day.map_file, thumb)
        if thumb.exists():
            shutil.copy2(thumb, target / "thumb.png")
            day.thumb = "thumb.png"
        elif day.is_image:
            day.thumb = day.map_file.name

    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape(["html"]))
    common = {"s": settings, "categorical": P.CATEGORICAL, "fields": SOURCE_FIELDS}

    # The calendar page. Weeks start on Sunday; 0 means "not in this month".
    weeks = calendar.Calendar(firstweekday=6).monthdayscalendar(settings["year"], settings["month"])
    by_number = {d.number: d for d in days}
    grid = [[by_number.get(n) for n in week] for week in weeks]
    (out_dir / "index.html").write_text(
        env.get_template("index.html").render(
            **common, root="", weeks=grid, done_count=len(done),
            weekdays=["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        ),
        encoding="utf-8",
    )

    # One page per finished day, with links to the previous / next finished day.
    for i, day in enumerate(done):
        prev_day = done[i - 1] if i > 0 else None
        next_day = done[i + 1] if i + 1 < len(done) else None
        (out_dir / "days" / day.slug / "index.html").write_text(
            env.get_template("day.html").render(**common, root="../../", day=day,
                                                prev=prev_day, next=next_day),
            encoding="utf-8",
        )

    return days


def report(days, out_dir):
    """Print what was built, plus anything still missing on finished days."""
    done = [d for d in days if d.done]
    where = out_dir.relative_to(ROOT) if out_dir.is_relative_to(ROOT) else out_dir
    print(f"Built {len(done)} of 30 days → {where}/index.html")
    for day in days:
        if day.folder and not day.done:
            print(f"  … day {day.slug}: in progress (run its map.py to make the map)")
        elif day.done:
            for warning in day.warnings:
                print(f"  ⚠ day {day.slug}: {warning}")


def serve(out_dir, port=8000):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out_dir))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"Serving at http://localhost:{port}  (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the 30-day map challenge website.")
    parser.add_argument("--serve", action="store_true", help="serve the site at http://localhost:8000")
    parser.add_argument("--thumbs", action="store_true", help="screenshot interactive maps for the calendar")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    built = build(make_thumbs=args.thumbs)
    report(built, SITE_DIR)
    if args.serve:
        serve(SITE_DIR, args.port)
