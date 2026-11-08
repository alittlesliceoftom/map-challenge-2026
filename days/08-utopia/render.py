"""Write map.html: the template with trips, tour and extras inlined as JSON."""

import json
from pathlib import Path

TEMPLATE = Path(__file__).parent / "template.html"


def _js(value) -> str:
    return json.dumps(value, separators=(",", ":"))


def render(trips: list[dict], out: Path, tour: list[dict], extras: dict | None = None) -> None:
    html = TEMPLATE.read_text(encoding="utf-8")
    for key, value in (("TRIPS", trips), ("TOUR", tour), ("EXTRAS", extras or {})):
        placeholder = f"/*__{key}__*/null"
        assert placeholder in html, placeholder
        html = html.replace(placeholder, _js(value))
    Path(out).write_text(html, encoding="utf-8")
