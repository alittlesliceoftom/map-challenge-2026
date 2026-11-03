#!/usr/bin/env python3
"""
setup_challenge.py — make this #30DayMapChallenge site yours.

    python3 setup_challenge.py

It asks a few questions (your name, links, colours), then writes:

    site.toml           your name, headline, intro and footer links
    mapkit/palette.py   your six colours (the block between the >>> and <<< lines)
    README.md           its first paragraph, so it says whose site this is

and offers to set up Python and show you a preview. Run it again any time to
change your answers. It never touches days/, where your maps live.

It only uses Python's built-in modules, so it works before anything is installed.
"""

from __future__ import annotations

import colorsys
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import threading
import webbrowser
from pathlib import Path

try:
    import tomllib          # Python 3.11+: reads site.toml exactly
except ImportError:         # older Python: rough_parse() below reads what it needs
    tomllib = None

ROOT = Path(__file__).resolve().parent
PLACEHOLDER_NAME = "Your Name"

PALETTE_BLOCK = re.compile(r"^# >>> .*?^# <<< [^\n]*$", re.S | re.M)
ABOUT_BLOCK = re.compile(r"<!-- about -->.*?<!-- /about -->", re.S)
CREDIT_BLOCK = re.compile(r"^(?:#[^\n]*\n)*\[template\].*\Z", re.S | re.M)

# Ready-made palettes. Each one has been designed so that colourblind viewers
# can still tell all six colours apart.
PRESETS = [
    {
        "title": "Okabe–Ito",
        "about": "the classic colourblind-safe set (Okabe & Ito, 2008)",
        "colours": [("ORANGE", "#e69f00"), ("SKY_BLUE", "#56b4e9"), ("BLUISH_GREEN", "#009e73"),
                    ("YELLOW", "#f0e442"), ("BLUE", "#0072b2"), ("VERMILLION", "#d55e00")],
        "highlight": "YELLOW",
        "alert": "VERMILLION",
        "note": "YELLOW is very light on paper: use it for filled shapes with an INK "
                "outline (points, polygons), not for thin lines or text.",
    },
    {
        "title": "Tol Bright",
        "about": "bright and colourblind-safe (Paul Tol)",
        "colours": [("BLUE", "#4477aa"), ("RED", "#ee6677"), ("GREEN", "#228833"),
                    ("YELLOW", "#ccbb44"), ("CYAN", "#66ccee"), ("PURPLE", "#aa3377")],
        "highlight": "YELLOW",
        "alert": "RED",
        "note": "YELLOW and CYAN are light: give them an INK outline.",
    },
    {
        "title": "Tol Vibrant",
        "about": "punchy and colourblind-safe (Paul Tol)",
        "colours": [("ORANGE", "#ee7733"), ("BLUE", "#0077bb"), ("CYAN", "#33bbee"),
                    ("MAGENTA", "#ee3377"), ("RED", "#cc3311"), ("TEAL", "#009988")],
        "highlight": "CYAN",
        "alert": "RED",
        "note": "CYAN is light: give it an INK outline.",
    },
]

# The template author's own six colours belong to her site. Pick your own!
TAKEN = {"#ff7a1a", "#ffc21a", "#d7263d", "#2bb39a", "#3a7bf2", "#5e3aa8"}

# Footer links to ask about. "{}" is filled in when someone types a username.
LINK_QUESTIONS = [
    ("GitHub", "https://github.com/{}"),
    ("LinkedIn", "https://www.linkedin.com/in/{}"),
    ("Bluesky", "https://bsky.app/profile/{}"),
    ("Mastodon", None),
    ("Instagram", "https://www.instagram.com/{}"),
]


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
def rgb(hex_):
    hex_ = hex_.lstrip("#")
    return tuple(int(hex_[i:i + 2], 16) for i in (0, 2, 4))


def luminance(hex_):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def parse_hexes(text):
    """'#1b9e77, d95f02 …' -> ['#1b9e77', '#d95f02', …] (6-digit codes only)."""
    return ["#" + h.lower() for h in re.findall(r"#?\b([0-9a-fA-F]{6})\b", text)]


def custom_palette(hexes):
    """A palette from six colours someone typed in. Raises ValueError if they won't do."""
    hexes = [h.lower() for h in hexes]
    if len(hexes) != 6:
        raise ValueError(f"I need exactly 6 colours, I found {len(hexes)}.")
    if len(set(hexes)) != 6:
        raise ValueError("Two of those are the same colour. I need 6 different ones.")
    if set(hexes) == TAKEN:
        raise ValueError("Those are the template author's own colours, so they stay on her "
                         "site. Pick your own six (or one of the ready-made sets).")
    names = [f"COLOUR_{i}" for i in range(1, 7)]
    lightest = max(range(6), key=lambda i: luminance(hexes[i]))

    def redness(i):            # 0 = a strong red; used for the "missing" flags
        h, s, _ = colorsys.rgb_to_hsv(*(c / 255 for c in rgb(hexes[i])))
        return min(h, 1 - h) + (1 - s) * 0.5

    alert = min((i for i in range(6) if i != lightest), key=redness)
    return {
        "title": "My own colours",
        "about": "",
        "colours": list(zip(names, hexes)),
        "highlight": names[lightest],
        "alert": names[alert],
        "note": "Check that colourblind viewers can still tell these apart "
                "(search for a 'colour blindness simulator' and try a map in it).",
    }


def colours_block(palette):
    """The Python lines between >>> and <<< in mapkit/palette.py."""
    names = [name for name, _ in palette["colours"]]
    width = max(len(n) for n in names)
    title = palette["title"] + (f", {palette['about']}" if palette.get("about") else "")
    lines = [
        f"# >>> YOUR SIX COLOURS: {title}",
        "# (setup_challenge.py rewrites everything from here down to the <<< line.",
        "#  You can also edit the colours by hand; just keep the >>> and <<< lines.)",
    ]
    if palette.get("note"):
        lines += textwrap.wrap(palette["note"], 76, initial_indent="# ", subsequent_indent="# ")
    lines += [f'{name.ljust(width)} = "{hex_}"' for name, hex_ in palette["colours"]]
    lines += [
        "",
        f"CATEGORICAL = [{', '.join(names)}]",
        f"CATEGORICAL_NAMES = {json.dumps([n.lower().replace('_', '-') for n in names])}",
        "",
        f"HIGHLIGHT = {palette['highlight']}   # behind the headline's 2nd line, under your name",
        f"ALERT = {palette['alert']}   # the \"missing\" flags on day pages",
        "# <<< YOUR SIX COLOURS",
    ]
    return "\n".join(lines)


def write_palette(root, palette):
    path = root / "mapkit" / "palette.py"
    text = path.read_text(encoding="utf-8")
    if not PALETTE_BLOCK.search(text):
        raise SystemExit("mapkit/palette.py has lost its '# >>>' / '# <<<' lines, so I don't "
                         "know where your colours go. Put them back around the colour block.")
    block = colours_block(palette)
    path.write_text(PALETTE_BLOCK.sub(lambda _: block, text, count=1), encoding="utf-8")


def current_colours(root):
    """The six hex codes in palette.py right now (for showing 'keep these')."""
    text = (root / "mapkit" / "palette.py").read_text(encoding="utf-8")
    match = PALETTE_BLOCK.search(text)
    return re.findall(r'=\s*"(#[0-9a-fA-F]{6})"', match.group(0))[:6] if match else []


# Coloured blocks in the terminal, so you can see a palette before choosing it.
USE_COLOUR = sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
TRUE_COLOUR = os.environ.get("COLORTERM", "") in ("truecolor", "24bit")


def swatch(hex_):
    if not USE_COLOUR:
        return hex_ + " "
    r, g, b = rgb(hex_)
    if TRUE_COLOUR:
        return f"\033[48;2;{r};{g};{b}m    \033[0m "
    cube = 16 + 36 * round(r / 255 * 5) + 6 * round(g / 255 * 5) + round(b / 255 * 5)
    return f"\033[48;5;{cube}m    \033[0m "


def swatches(hexes):
    return "".join(swatch(h) for h in hexes)


# ---------------------------------------------------------------------------
# Writing site.toml and README.md
# ---------------------------------------------------------------------------
def toml_string(value):
    return json.dumps(value, ensure_ascii=False)     # JSON strings are valid TOML strings


def setting(key, value, comment=""):
    line = f"{key} = {toml_string(value)}"
    return f"{line.ljust(36)} # {comment}" if comment else line


def site_toml_text(a, credit):
    links = ",\n".join(f"  {{ label = {toml_string(label)}, url = {toml_string(url)} }}"
                       for label, url in a["links"])
    text = f"""# Settings for the website. Edit freely, then run `python build.py`.
# (Written by setup_challenge.py: run it again any time to redo these answers.)

{setting("name", a["name"], "shown top-right on the calendar")}
{setting("made_by_url", a["made_by_url"], "your name links here (calendar + footer)")}
{setting("made_with", a.get("made_with", ""), "optional, after your name in the footer")}
{setting("title_top", a["title_top"], "big headline, line 1")}
{setting("title_bottom", a["title_bottom"], "big headline, line 2 (highlighted)")}
{setting("intro", a["intro"])}

year = {int(a["year"])}
month = 11                           # November

challenge_url = "https://30daymapchallenge.com/"

# The site's own web address, once it has one (e.g. "https://example.com/maps").
# Used so links shared on social media show the map's preview image.
site_url = {toml_string(a["site_url"])}

# Links shown in the footer. Leave the url empty to hide one.
links = [
{links}
]
"""
    if credit:
        text += "\n" + credit.rstrip() + "\n"
    return text


def write_site(root, answers):
    path = root / "site.toml"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    match = CREDIT_BLOCK.search(old)
    path.write_text(site_toml_text(answers, match.group(0) if match else ""), encoding="utf-8")


def write_readme(root, a):
    path = root / "README.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    live = f" Live at <{a['site_url']}>." if a["site_url"] else ""
    about = (
        "<!-- about -->\n"
        f"{a['name']}'s [#30DayMapChallenge](https://30daymapchallenge.com/) {a['year']} portfolio: "
        "a calendar of the 30 daily themes, where each finished day opens to an interactive map, "
        f"why it was made, and where the data comes from. Everything is Python.{live}\n"
        "<!-- /about -->"
    )
    if ABOUT_BLOCK.search(text):
        path.write_text(ABOUT_BLOCK.sub(lambda _: about, text, count=1), encoding="utf-8")


def apply(root, answers):
    """Write everything. `answers` is what main() collects (see the tests for an example)."""
    write_site(root, answers)
    if answers.get("palette"):
        write_palette(root, answers["palette"])
    write_readme(root, answers)


# ---------------------------------------------------------------------------
# Asking questions
# ---------------------------------------------------------------------------
def ask(question, default=""):
    hint = f" [{default}]" if default else ""
    try:
        answer = input(f"{question}{hint}: ").strip()
    except EOFError:
        raise SystemExit("\nStopped. Nothing was saved.")
    return answer or default


def ask_yes(question, default=True):
    while True:
        answer = ask(f"{question} ({'Y/n' if default else 'y/N'})").lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


def clean_url(text):
    """'example.com' -> 'https://example.com'. Empty stays empty."""
    text = text.strip()
    if text and not re.match(r"^[a-z][a-z0-9+.-]*:", text, re.I):
        text = "https://" + text
    return text


def link_url(label, text, pattern):
    """Accepts a full link or just a username, e.g. 'janedoe' for GitHub."""
    text = text.strip()
    if not text or "://" in text:
        return text
    if label == "Mastodon":
        handle = re.match(r"^@?([\w.]+)@([\w.-]+\.\w+)$", text)      # @you@server.social
        if handle:
            return f"https://{handle.group(2)}/@{handle.group(1)}"
    is_username = "/" not in text and (text.startswith("@") or "." not in text or label == "Bluesky")
    if pattern and is_username:
        return pattern.format(text.lstrip("@"))
    return clean_url(text)


TOML_STRING = r'"(?:[^"\\\n]|\\.)*"'


def rough_parse(text):
    """Enough of site.toml for Pythons older than 3.11 (no tomllib): the plain
    "quoted" settings, the year and the links."""
    top = re.split(r"^\[", text, maxsplit=1, flags=re.M)[0]      # stop at [template]

    def unquote(quoted):
        try:
            return json.loads(quoted)
        except ValueError:
            return quoted[1:-1]

    old = {key: unquote(value) for key, value in re.findall(rf"^(\w+)\s*=\s*({TOML_STRING})", top, re.M)}
    year = re.search(r"^year\s*=\s*(\d{4})", top, re.M)
    if year:
        old["year"] = int(year.group(1))
    old["links"] = [{"label": unquote(label), "url": unquote(url)} for label, url in
                    re.findall(rf"label\s*=\s*({TOML_STRING})\s*,\s*url\s*=\s*({TOML_STRING})", top)]
    return old


def previous_answers(root):
    """What site.toml says now, so a second run can offer it as the default."""
    path = root / "site.toml"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    old = None
    if tomllib is not None:
        try:
            old = tomllib.loads(text)
        except ValueError:
            pass
    if old is None:
        old = rough_parse(text)
    return {} if old.get("name") in (None, "", PLACEHOLDER_NAME) else old


def themes_year(root):
    match = re.search(r"#30DayMapChallenge (\d{4})", (root / "themes.toml").read_text(encoding="utf-8"))
    return int(match.group(1)) if match else None


def heading(step, title):
    print(f"\n── {step} · {title} " + "─" * max(0, 60 - len(title)))


def choose_palette(root, rerun):
    print("Your six colours go on the calendar squares, the day pages and your maps")
    print("(from mapkit import palette as P; P.categorical(3) gives you the first 3).\n")
    for i, p in enumerate(PRESETS, start=1):
        print(f"  {i}  {p['title']:<12} {swatches([h for _, h in p['colours']])}  {p['about']}")
    own = len(PRESETS) + 1
    print(f"  {own}  My own: type six colour codes (like #1b9e77)")
    keep = None
    if rerun and current_colours(root):
        keep = own + 1
        print(f"  {keep}  Keep my current ones   {swatches(current_colours(root))}")
    choices = [str(n) for n in range(1, (keep or own) + 1)]
    while True:
        choice = ask("Which one?", str(keep or 1))
        if choice not in choices:
            print(f"  Type a number from 1 to {choices[-1]}.")
            continue
        n = int(choice)
        if n == keep:
            return None
        if n <= len(PRESETS):
            return PRESETS[n - 1]
        while True:
            print("  Pick them in the order you'll use them (the first is your most-used colour).")
            print("  Tip: test them with a colour-blindness simulator before you commit.")
            try:
                palette = custom_palette(parse_hexes(ask("  Six colour codes")))
            except ValueError as err:
                print(f"  {err}")
                continue
            print(f"  {swatches([h for _, h in palette['colours']])}")
            if ask_yes("  Use these?"):
                return palette


def collect_answers(root):
    old = previous_answers(root)
    rerun = bool(old)
    old_links = {link.get("label", ""): link.get("url", "") for link in old.get("links", [])}

    heading("1/6", "You")
    name = ""
    while not name:
        name = ask("Your name (shown on the calendar)", old.get("name", ""))
    website = clean_url(ask("Your website: your name will link here (blank if none)",
                            old.get("made_by_url", "")))

    heading("2/6", "Links in the footer")
    print("A username or a full link. Leave blank to skip.")
    links = []
    if website:
        links.append(("Website", website))
    asked = {"Website"}
    for label, pattern in LINK_QUESTIONS:
        asked.add(label)
        url = link_url(label, ask(f"  {label}", old_links.get(label, "")), pattern)
        if url:
            links.append((label, url))
    for label, url in old_links.items():          # links you added by hand last time
        if label not in asked and url and ask_yes(f"  Keep your {label} link ({url})?"):
            links.append((label, url))
    while True:
        label = ask("  Another link? Its name, e.g. 'Newsletter' (blank to finish)")
        if not label:
            break
        url = clean_url(ask(f"  {label} link"))
        if url:
            links.append((label, url))

    heading("3/6", "Which year")
    while True:
        year = ask("Which November are you mapping?", str(old.get("year", themes_year(root) or 2026)))
        if year.isdigit() and 2019 <= int(year) <= 2100:
            year = int(year)
            break
        print("  Type a year, like 2026.")
    if themes_year(root) and year != themes_year(root):
        print(f"  Note: themes.toml has the {themes_year(root)} themes. Copy the {year} ones "
              "from https://30daymapchallenge.com/ into it.")

    heading("4/6", "Headline")
    title_top = ask("Big headline, line 1", old.get("title_top", "30 Maps"))
    title_bottom = ask("Big headline, line 2 (highlighted)", old.get("title_bottom", "30 Days"))
    intro = ask("One line about it",
                old.get("intro", f"#30DayMapChallenge, November {year}. One map a day, built in Python."))

    heading("5/6", "Where it will live")
    print("The web address your site will have, e.g. https://you.github.io/maps")
    site_url = clean_url(ask("Leave blank if you don't know yet", old.get("site_url", "")))

    heading("6/6", "Colours")
    palette = choose_palette(root, rerun)

    return {
        "name": name, "made_by_url": website, "made_with": old.get("made_with", ""),
        "links": links, "year": year, "title_top": title_top, "title_bottom": title_bottom,
        "intro": intro, "site_url": site_url, "palette": palette,
    }


def summary(a):
    print("\n── Check your answers " + "─" * 46)
    print(f"  Name:      {a['name']}" + (f"  →  {a['made_by_url']}" if a["made_by_url"] else ""))
    for label, url in a["links"]:
        print(f"  {label + ':':<10} {url}")
    print(f"  Headline:  {a['title_top']} / {a['title_bottom']}")
    print(f"  Intro:     {a['intro']}")
    print(f"  Year:      {a['year']}")
    print(f"  Address:   {a['site_url'] or '(not yet)'}")
    if a["palette"]:
        print(f"  Colours:   {a['palette']['title']}  {swatches([h for _, h in a['palette']['colours']])}")
    else:
        print("  Colours:   (keeping your current ones)")


# ---------------------------------------------------------------------------
# Python and the preview
# ---------------------------------------------------------------------------
def find_python():
    """A Python that's 3.11 or newer (the builder needs it)."""
    if sys.version_info >= (3, 11):
        return sys.executable
    for name in ("python3.14", "python3.13", "python3.12", "python3.11"):
        path = shutil.which(name)
        if path:
            return path
    return None


def venv_python(root):
    return root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def setup_python(root):
    python = find_python()
    if not python:
        print("This project needs Python 3.11 or newer and I couldn't find one.\n"
              "Install it from https://www.python.org/downloads/ and run this again.")
        return False
    try:
        if not venv_python(root).exists():
            print("Making .venv (this project's own Python) …")
            subprocess.run([python, "-m", "venv", ".venv"], cwd=root, check=True)
        print("Installing the mapping libraries (a minute or two) …")
        pip = [str(venv_python(root)), "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]
        subprocess.run(pip + ["-r", "requirements.txt"], cwd=root, check=True)
        subprocess.run(pip + ["-e", "."], cwd=root, check=True)
    except (subprocess.CalledProcessError, OSError) as err:
        print(f"Setting up Python didn't work ({err}).\n"
              "You can do it by hand: see 'Getting started' in README.md.")
        return False
    return True


def preview(root):
    url = "http://localhost:8000"
    print(f"\nBuilding your site and opening {url} (press Ctrl+C here to stop) …")
    threading.Timer(2, webbrowser.open, [url]).start()
    try:
        subprocess.run([str(venv_python(root)), "build.py", "--serve"], cwd=root)
    except KeyboardInterrupt:
        pass


def check_root(root):
    missing = [p for p in ("build.py", "site.toml", "themes.toml", "mapkit/palette.py")
               if not (root / p).exists()]
    if missing:
        raise SystemExit(f"Run this from the project folder: I can't find {', '.join(missing)}.")


def main():
    check_root(ROOT)
    print("\n  Make it yours: a #30DayMapChallenge site\n"
          "  Six quick questions. Press Enter to accept a [suggestion].")
    try:
        answers = collect_answers(ROOT)
        summary(answers)
        if not ask_yes("\nSave these?"):
            print("Nothing was saved. Run it again whenever you like.")
            return
    except KeyboardInterrupt:
        print("\nStopped. Nothing was saved.")
        return
    apply(ROOT, answers)
    print("Saved: site.toml, mapkit/palette.py and README.md.")

    try:
        ready = venv_python(ROOT).exists()
        if ask_yes("\nSet up Python for this project now (.venv + mapping libraries)?", not ready):
            ready = setup_python(ROOT)
        if ready and ask_yes("Open a preview of your site?"):
            preview(ROOT)
    except KeyboardInterrupt:
        print()

    print("""
All set. From now on, in this folder:

    source .venv/bin/activate        # every time you open a terminal
    python new_day.py 1              # start day 1
    python build.py --serve          # see your site at http://localhost:8000

README.md walks you through the daily routine and putting the site online.
Happy mapping!""")


if __name__ == "__main__":
    main()
