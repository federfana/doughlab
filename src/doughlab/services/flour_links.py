"""Controllo dei link alle schede dei produttori: `uv run python -m doughlab.services.flour_links`.

Serve a scoprire in tempo quando un prodotto viene tolto dal sito o la pagina cambia indirizzo. Non parte da solo
(l'app resta usabile offline): lancialo ogni tanto e aggiorna `seed_data/flour_seeds.json`.
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .flour_seed import FLOUR_SEEDS

USER_AGENT = "Mozilla/5.0 (compatible; DoughLab link check)"
TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class LinkResult:
    brand: str
    name: str
    url: str
    status: int | None  # None = nessuna risposta
    error: str = ""
    final_url: str = ""

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300

    @property
    def moved(self) -> bool:
        if not self.ok or not self.final_url:
            return False
        # Conta solo un altro sito o un'altra pagina: i parametri riordinati (es. PrestaShop) no.
        before, after = urlsplit(self.url), urlsplit(self.final_url)
        return (before.netloc, before.path.rstrip("/")) != (after.netloc, after.path.rstrip("/"))


def check_url(url: str, timeout: float = TIMEOUT_SECONDS) -> tuple[int | None, str, str]:
    """(stato HTTP, errore, indirizzo finale dopo i reindirizzamenti)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - solo https dai dati
            return response.status, "", response.geturl()
    except urllib.error.HTTPError as error:
        return error.code, str(error.reason), url
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return None, str(getattr(error, "reason", error)), url


def check_links(seeds: Iterable[dict[str, Any]] = FLOUR_SEEDS, workers: int = 8) -> list[LinkResult]:
    items = [s for s in seeds if str(s.get("source_url", "")).startswith("https://")]

    def run(seed: dict[str, Any]) -> LinkResult:
        status, error, final = check_url(seed["source_url"])
        return LinkResult(seed["brand"], seed["name"], seed["source_url"], status, error, final)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run, items))


def main() -> int:
    results = check_links()
    broken = [r for r in results if not r.ok]
    moved = [r for r in results if r.moved]
    for r in broken:
        print(f"NON RAGGIUNGIBILE  {r.brand} · {r.name}: {r.status or '-'} {r.error}\n    {r.url}")
    for r in moved:
        print(f"SPOSTATA           {r.brand} · {r.name}\n    {r.url}\n -> {r.final_url}")
    print(f"{len(results)} link controllati: {len(results) - len(broken)} raggiungibili, "
          f"{len(broken)} non raggiungibili, {len(moved)} spostati.")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
