import re

import build

TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def make_day(days, folder, files):
    path = days / folder
    path.mkdir(parents=True)
    for name, content in files.items():
        mode = "wb" if isinstance(content, bytes) else "w"
        with open(path / name, mode) as f:
            f.write(content)


def build_fixture(tmp_path):
    days = tmp_path / "days"
    make_day(days, "01-points", {
        "map.html": "<html>a map</html>",
        "notes.md": "# Where the bakeries are\n\nI wanted to see **why**.",
        "sources.toml": (
            '[[source]]\nname = "Bakeries"\nurl = "https://example.org/bakeries"\n'
            'from = "City open data"\nwhat = "One row per bakery"\ntime = "2026"\n'
            'resolution = ""\nlicence = "CC BY 4.0"\n'
        ),
        "map.py": 'import folium\nimport pandas as pd\nimport os\nfrom mapkit import palette\nTOKEN = "pk.abcdefghijklmnopqrstuvwxyz0123456789"\n',
    })
    make_day(days, "02-lines", {"notes.md": "# Still working on it\n"})   # no map yet
    make_day(days, "03-polygons", {"map.png": TINY_PNG, "notes.md": "# A photo\n"})
    out = tmp_path / "site"
    built = build.build(out_dir=out, days_dir=days)
    return out, built


def test_calendar_has_all_30_days(tmp_path):
    out, _ = build_fixture(tmp_path)
    index = (out / "index.html").read_text()
    assert index.count('class="tile done"') == 2
    assert index.count('class="tile empty"') == 28
    assert "2</strong> of 30 maps" in index


def test_only_finished_days_get_pages(tmp_path):
    out, _ = build_fixture(tmp_path)
    assert (out / "days/01/index.html").exists()
    assert not (out / "days/02").exists()
    assert (out / "days/03/index.html").exists()


def test_day_page_shows_notes_sources_and_missing_fields(tmp_path):
    out, built = build_fixture(tmp_path)
    page = (out / "days/01/index.html").read_text()
    assert "Where the bakeries are" in page
    assert "<strong>why</strong>" in page
    assert 'href="https://example.org/bakeries"' in page
    assert 'missing: add "resolution"' in page
    assert page.count("⚠ missing") == 1
    day1 = built[0]
    assert any("'resolution' is empty" in w for w in day1.warnings)


def test_tools_and_token_hiding(tmp_path):
    out, built = build_fixture(tmp_path)
    page = (out / "days/01/index.html").read_text()
    assert built[0].tools == ["Python", "folium", "pandas"]
    assert "pk.abcdefghijklmnopqrstuvwxyz" not in page
    assert "[TOKEN REMOVED]" in page


def test_image_maps_use_img_and_are_their_own_preview(tmp_path):
    out, _ = build_fixture(tmp_path)
    page = (out / "days/03/index.html").read_text()
    assert '<img src="map.png"' in page
    assert 'src="days/03/map.png"' in (out / "index.html").read_text()


def test_links_are_relative_so_site_works_anywhere(tmp_path):
    out, _ = build_fixture(tmp_path)
    for html in out.rglob("*.html"):
        text = html.read_text()
        assert not re.search(r'(href|src)="/(?!/)', text), html


def test_previews_are_remade_when_the_map_changes(tmp_path, monkeypatch):
    import os
    calls = []

    def fake_thumbnail(map_html, png):
        calls.append(map_html)
        png.write_bytes(TINY_PNG)
        return True

    monkeypatch.setattr(build, "make_thumbnail", fake_thumbnail)
    days = tmp_path / "days"
    make_day(days, "01-points", {"map.html": "<html>v1</html>", "notes.md": "# T\n"})
    out = tmp_path / "site"
    build.build(out_dir=out, days_dir=days, make_thumbs=True)
    build.build(out_dir=out, days_dir=days, make_thumbs=True)
    assert len(calls) == 1                       # unchanged map: preview kept
    map_file = days / "01-points" / "map.html"
    later = (days / "01-points" / "thumb.png").stat().st_mtime + 10
    os.utime(map_file, (later, later))           # the map gets edited
    build.build(out_dir=out, days_dir=days, make_thumbs=True)
    assert len(calls) == 2                       # preview remade


def test_made_by_link_on_every_page(tmp_path):
    out, _ = build_fixture(tmp_path)
    url = build.load_toml(build.ROOT / "site.toml").get("made_by_url")
    if url:
        assert (out / "index.html").read_text().count(f'href="{url}"') >= 2   # byline + footer (+ any footer links)
        assert f'href="{url}"' in (out / "days/01/index.html").read_text()


def footer_site(tmp_path, **changes):
    """Build a one-day site with some site.toml settings changed. Returns (index, day page)."""
    settings = {**build.load_toml(build.ROOT / "site.toml"), **changes}
    for key in [k for k, v in changes.items() if v is None]:
        settings.pop(key)
    days = tmp_path / "days"
    make_day(days, "01-points", {"map.html": "<html>a map</html>", "notes.md": "# T\n"})
    out = tmp_path / "site"
    build.build(out_dir=out, days_dir=days, settings=settings)
    return (out / "index.html").read_text(), (out / "days/01/index.html").read_text()


def test_original_site_invites_visitors_to_use_the_template(tmp_path):
    pages = footer_site(tmp_path, template=None, template_repo="https://github.com/me/tpl")
    for page in pages:
        assert "Use this template for your own" in page
        assert 'href="https://github.com/me/tpl"' in page
        assert "Template by" not in page


def test_copies_credit_the_template_author(tmp_path):
    credit = {"by": "Ada Lovelace", "url": "https://ada.example/", "repo": "https://github.com/ada/tpl"}
    pages = footer_site(tmp_path, template=credit, template_repo=None)
    for page in pages:
        assert "Template by" in page and "Ada Lovelace" in page
        assert 'href="https://ada.example/"' in page
        assert 'href="https://github.com/ada/tpl"' in page
        assert "Use this template for your own" not in page


def test_no_template_line_when_neither_is_set(tmp_path):
    index, _ = footer_site(tmp_path, template=None, template_repo=None)
    assert "template-note" not in index


def test_made_with_follows_the_name(tmp_path):
    index, _ = footer_site(tmp_path, name="Ada", made_by_url="https://ada.example/",
                           made_with="with a little help from Claude")
    assert '>Ada</a> with a little help from Claude' in index


def test_prev_next_skip_unfinished_days(tmp_path):
    out, _ = build_fixture(tmp_path)
    page = (out / "days/01/index.html").read_text()
    assert 'href="../03/index.html"' in page
    assert "../02/" not in page
