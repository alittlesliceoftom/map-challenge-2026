"""
Download each tower's photo so the site is self-contained.

    python days/01-points/fetch_images.py

For every row in towers.csv with an `image_url`, this saves a small JPEG to
images/ and writes its filename into the `image` column. `image_url` can be a web
address OR the path of a photo on your computer (e.g. ~/Downloads/mungos.jpg). To
change a photo, edit `image_url` (and `image_credit`) in towers.csv and run this
again; it re-processes whenever that value changes. map.py then embeds the images in map.html.
"""

import csv
import io
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image

HERE = Path(__file__).parent
CSV = HERE / "towers.csv"
IMAGES = HERE / "images"
WIDTH = 480  # px, plenty for a hover card
UA = "map-challenge-2026 personal project (https://asliceoftom.com)"


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def main():
    rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
    IMAGES.mkdir(exist_ok=True)
    url_log = IMAGES / ".urls.csv"  # remembers which URL each file came from
    seen = dict(csv.reader(open(url_log))) if url_log.exists() else {}
    for r in rows:
        url = r["image_url"].strip()
        if not url:
            r["image"] = ""
            continue
        name = slug(r["name"]) + ".jpg"
        if seen.get(name) == url and (IMAGES / name).exists():
            r["image"] = name
            continue
        if url.startswith("http"):
            data = urlopen(Request(url, headers={"User-Agent": UA}), timeout=30).read()
            time.sleep(2)  # be polite to Wikimedia
        else:
            path = Path(url).expanduser()
            data = (path if path.is_absolute() else HERE / path).read_bytes()  # relative = this folder
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((WIDTH, WIDTH * 2))
        img.save(IMAGES / name, "JPEG", quality=80, optimize=True)
        seen[name] = url
        r["image"] = name
        print("saved", name)
    csv.writer(open(url_log, "w", newline="")).writerows(seen.items())
    w = csv.DictWriter(open(CSV, "w", newline="", encoding="utf-8"), fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)


if __name__ == "__main__":
    main()
