# Day 1 · London's octagonal towers

Add a tower with a pull request: append one row to [`towers.csv`](towers.csv).

| Column | Meaning |
|---|---|
| `name`, `address`, `lat`, `lon` | Where it is |
| `type` | `Public building`, `House`, `Church` or `Unknown` |
| `shape` | `octagonal` or `hexagonal` |
| `verified` | `yes` if a source or a photo confirms the shape, otherwise `no` |
| `originally_water_tower` | `yes` / `no` |
| `note` | One line for the popup |
| `link` | A "More" link: an indie architecture blog or Historic England beats Wikipedia |
| `image_url`, `image_credit` | Optional photo you have the right to use (Wikimedia Commons is ideal) and its credit line. Run `python days/01-points/fetch_images.py`: it downloads to `images/` and fills the `image` column |
| `source` | Where you found it |

Then run `python days/01-points/map.py` to check it. Photos show when you hover a marker, and are embedded in `map.html`.
