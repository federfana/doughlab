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


def test_planner_warns_and_retries_when_the_plan_cannot_be_computed(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        page = (await client.get("/")).text

        assert 'id="planStale"' in page and "Riprovo da solo" in page
        assert "htmx:sendError" in page and "htmx:afterOnLoad" in page and "requestPath === '/plan'" in page

    run_with_db(tmp_path, monkeypatch, check)


def test_every_stepper_has_its_arrows_outside_the_field_and_salt_defaults_to_2_5(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        page = (await client.get("/")).text
        steppers = re.findall(r'<span class="number-stepper">\s*(<input[^>]*>)\s*<span class="number-stepper-controls">', page)

        names = {m.group(1) for tag in steppers if (m := re.search(r'name="(\w+)"', tag))}
        assert {"n_panetti", "panetto_g", "hydration_pct", "salt_pct", "oil_pct", "sugar_pct",
                "preferment_pct", "preferment_hydration_pct", "preferment_yeast_pct"} <= names
        assert page.count('class="number-stepper-controls"') == len(steppers)  # frecce sempre fuori dal campo
        assert re.search(r'name="salt_pct" value="2\.5"', page)
        assert "adjustPercent(this, 0.5)" in page and "adjustPercent(this, -0.5)" in page
        assert re.search(r'name="n_panetti"[^>]*step="any"', page)

    run_with_db(tmp_path, monkeypatch, check)


def test_stepper_script_is_loaded_and_knows_the_step_of_every_named_number_field(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        page = (await client.get("/")).text
        script = await client.get("/static/steppers.js")

        assert re.search(r'<script src="/static/steppers\.js\?v=\d+"></script>', page)
        assert script.status_code == 200 and "htmx:load" in script.text and "MutationObserver" in script.text

    run_with_db(tmp_path, monkeypatch, check)

    js = (STATIC / "steppers.js").read_text()
    known = set(re.findall(r"\b(\w+): [\d.]+[,}]?", js.split("BY_NAME = {")[1].split("};")[0]))
    prefixes = ("flour_pct_", "phase_ambient_")  # nomi con indice: li riconosce stepFor
    server_side = {"n_panetti", "panetto_g", "hydration_pct", "salt_pct", "oil_pct", "sugar_pct"}
    for path in (STATIC.parent / "templates").rglob("*.html"):
        for tag in re.findall(r'<input type="number"[^>]*>', path.read_text()):
            found = re.search(r'name="(\w+?)(?:_?\{\{[^}]*\}\}|_IDX)?"', tag)
            if found is None:
                continue  # senza nome: lo riconosce l'etichetta o la classe (durate, lati della teglia)
            name = found.group(1)
            assert name in known | server_side or any(name.startswith(p.rstrip("_")) for p in prefixes), (
                f"{path.name}: il campo numerico «{name}» non ha un passo in steppers.js"
            )
