"""Grafica: foglio di stile versionato, font locale, barra di navigazione con icone, anello del timer."""
from __future__ import annotations

import re
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from .test_diary import run_with_db

STATIC = Path(__file__).parents[1] / "src/doughlab/static"


def test_page_links_a_versioned_stylesheet_instead_of_inline_css(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        page = (await client.get("/")).text

        assert re.search(r'<link rel="stylesheet" href="/static/app\.css\?v=\d+">', page)
        assert "<style" not in page
        assert 'href="/static/vendor/fonts/fraunces-latin-wght-normal.woff2"' in page

    run_with_db(tmp_path, monkeypatch, check)


def test_stylesheet_and_local_font_are_served(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        css = await client.get("/static/app.css")
        font = await client.get("/static/vendor/fonts/fraunces-latin-wght-normal.woff2")

        assert css.status_code == 200 and "html.dark" in css.text and "--ac:" in css.text
        assert font.status_code == 200 and font.content[:4] == b"wOF2"
        assert "url(\"/static/vendor/fonts/fraunces-latin-wght-normal.woff2\")" in css.text

    run_with_db(tmp_path, monkeypatch, check)
    assert "SIL Open Font License" in (STATIC / "vendor/fonts/Fraunces-OFL.txt").read_text()


def test_the_four_areas_have_an_icon_and_a_label(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        page = (await client.get("/")).text

        for key, label in [("planner", "Pianifica"), ("live", "In corso"), ("diary", "Diario"), ("flours", "Farine")]:
            tab = re.search(rf'<button id="tab-{key}".*?</button>', page, re.S)
            assert tab is not None and "<svg" in tab.group(0) and f"<span>{label}</span>" in tab.group(0)

    run_with_db(tmp_path, monkeypatch, check)


def test_live_timer_is_a_progress_ring_and_the_old_bar_is_gone(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        page = (await client.get("/")).text

        assert 'class="live-ring"' in page and "--p:${Math.min(100, liveProgress() * 100)}" in page
        assert "live-bar" not in page

    run_with_db(tmp_path, monkeypatch, check)


# Classi usate solo da script o test, senza stile proprio.
HOOK_CLASSES = {
    "check", "dur-h", "dur-m", "file-btn-form", "flour-methods", "flour-picker", "home-bake-fields",
    "phase-move", "photo-preview", "split-bake-fields",
}
# Classi aggiunte da Alpine/Jinja a runtime o con stile solo in combinazione (es. `.btn-ghost.active`).
STATE_CLASSES = {"on", "late", "done", "active", "current", "single", "empty", "sotto", "sopra", "cold", "hot",
                 "ok", "warn", "bad", "error", "no-cover"}


def test_stylesheet_covers_every_class_used_by_the_templates() -> None:
    css = (STATIC / "app.css").read_text()
    known = set(re.findall(r"\.([a-zA-Z][\w-]*)", re.sub(r"\{[^}]*\}", "{}", css)))
    for path in (STATIC.parent / "templates").rglob("*.html"):
        for match in re.findall(r'(?<![:\w-])class="([^"{}]+)"', path.read_text()):
            for cls in match.split():
                if cls in HOOK_CLASSES | STATE_CLASSES:
                    continue
                assert cls in known, f"{path.name}: la classe «{cls}» non ha stile in app.css"
