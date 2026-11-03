"""
new_day.py — start a new challenge day.

    python new_day.py 2

creates days/02-lines/ with:
    map.py        a step-by-step skeleton for you to fill in
    notes.md      where your reasoning goes
    sources.toml  where your data sources go
    data/         put downloaded data files here
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKELETON = ROOT / "templates" / "day_skeleton"


def slugify(text):
    """'Senses: Sight' -> 'senses-sight'"""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "day"


def main():
    if len(sys.argv) != 2 or not sys.argv[1].isdigit() or not 1 <= int(sys.argv[1]) <= 30:
        sys.exit("Usage: python new_day.py <day number 1–30>")
    number = int(sys.argv[1])

    with open(ROOT / "themes.toml", "rb") as f:
        theme = next(t for t in tomllib.load(f)["day"] if t["day"] == number)

    existing = list((ROOT / "days").glob(f"{number:02d}-*"))
    if existing:
        sys.exit(f"Day {number} already exists: {existing[0].relative_to(ROOT)}")

    folder = ROOT / "days" / f"{number:02d}-{slugify(theme['theme'])}"
    (folder / "data").mkdir(parents=True)
    replacements = {
        "{{DAY}}": str(number),
        "{{THEME}}": theme["theme"],
        "{{PROMPT}}": theme["prompt"] or "(no description for this one)",
        "{{FOLDER}}": folder.name,
    }
    for template in SKELETON.iterdir():
        text = template.read_text(encoding="utf-8")
        for key, value in replacements.items():
            text = text.replace(key, value)
        (folder / template.name).write_text(text, encoding="utf-8")

    rel = folder.relative_to(ROOT)
    print(f"Created {rel}/")
    print(f"  1. Open {rel}/map.py and follow the steps")
    print(f"  2. Run:  python {rel}/map.py")
    print("  3. See it on the site:  python build.py --serve")


if __name__ == "__main__":
    main()
