"""Farine predefinite: dati dichiarati dai produttori sulle loro pagine ufficiali.

I dati stanno in `seed_data/flour_seeds.json` (si modificano senza toccare il codice). Dove la scheda dà un
intervallo, `w` e `pl` sono il valore centrale e l'intervallo sta in `notes`. Dove il produttore scrive
"oltre X%" o "fino a X%", `hydration_min/max` sono la nostra interpretazione e le parole originali stanno
in `hydration_note`. I valori variano da partita a partita: fa fede l'etichetta del sacco.

Struttura del file:
- `version`: versione dell'archivio; va alzata ogni volta che si aggiungono, ritirano o completano farine.
- `flours`: le farine, in ordine. `since` (opzionale) è la versione in cui la farina è comparsa: serve a
  non rimettere a chi l'ha eliminata una farina che già c'era. `verified` è la data (AAAA-MM-GG o AAAA-MM)
  in cui i dati sono stati confrontati con la scheda del produttore.
- `revised` e `was` (opzionali, insieme): la farina è stata corretta nella versione `revised` e `was` riporta
  i valori precedenti dei campi cambiati. Gli archivi esistenti ricevono i valori nuovi solo se quei campi
  sono ancora quelli di `was` (cioè non li hai modificati tu).
- `removed`: farine ritirate (non più in vendita o non più valide), tolte dagli archivi esistenti.
- `corrections`: farine della prima versione con un altro nome, corrette solo se non modificate.
- `draft_note`: nota che marca i dati provvisori della prima versione.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parent.parent / "seed_data" / "flour_seeds.json"
_FLOUR_KEYS = {
    "brand", "name", "kind", "w", "pl", "protein", "hydration_min", "hydration_max", "hydration_note",
    "method", "method_note", "use", "notes", "source_url", "since", "verified", "revised", "was",
}


def _pair(value: Any) -> tuple[str, str]:
    brand, name = value
    return str(brand), str(name)


def load_seeds(path: Path = DATA_FILE) -> dict[str, Any]:
    """Legge e controlla il file dei dati; un errore dice quale farina non va."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    flours: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(raw["flours"]):
        label = f"farina n. {index + 1} ({item.get('brand', '?')} {item.get('name', '?')})"
        if not item.get("name"):
            raise ValueError(f"{path.name}: {label} senza nome")
        if unknown := set(item) - _FLOUR_KEYS:
            raise ValueError(f"{path.name}: {label} ha campi sconosciuti: {sorted(unknown)}")
        if ("revised" in item) != ("was" in item):
            raise ValueError(f"{path.name}: {label}: `revised` e `was` vanno insieme")
        if unknown := set(item.get("was", {})) - _FLOUR_KEYS:
            raise ValueError(f"{path.name}: {label}: `was` ha campi sconosciuti: {sorted(unknown)}")
        key = (item.get("brand", ""), item["name"])
        if key in seen:
            raise ValueError(f"{path.name}: {label} è duplicata")
        seen.add(key)
        flours.append(item)
    return {
        "version": int(raw["version"]),
        "draft_note": str(raw["draft_note"]),
        "removed": tuple(_pair(x) for x in raw.get("removed", [])),
        "corrections": {_pair(c["from"]): _pair(c["to"]) for c in raw.get("corrections", [])},
        "flours": flours,
    }


_DATA = load_seeds()

SEED_VERSION: int = _DATA["version"]
DRAFT_NOTE: str = _DATA["draft_note"]
SEED_REMOVED: tuple[tuple[str, str], ...] = _DATA["removed"]
# Nome come era nella prima versione (dati ripresi da un'app di terzi) -> nome corretto.
# La sincronizzazione le corregge solo se non le hai modificate.
SEED_CORRECTIONS: dict[tuple[str, str], tuple[str, str]] = _DATA["corrections"]
# Versione in cui sono comparse le farine aggiunte dopo la prima (le altre non compaiono: valgono 1).
SEED_SINCE: dict[tuple[str, str], int] = {
    (f["brand"], f["name"]): int(f["since"]) for f in _DATA["flours"] if int(f.get("since", 1)) > 1
}
# (produttore, nome) -> (versione della correzione, valori precedenti dei campi cambiati).
SEED_REVISIONS: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {
    (f["brand"], f["name"]): (int(f["revised"]), dict(f["was"])) for f in _DATA["flours"] if "revised" in f
}
# Campi che finiscono nel database (`since`, `revised` e `was` servono solo qui sopra); impasto e nota sempre presenti.
FLOUR_SEEDS: tuple[dict[str, Any], ...] = tuple(
    {
        **{k: v for k, v in f.items() if k not in {"since", "revised", "was"}},
        "method": f.get("method", ""),
        "method_note": f.get("method_note", ""),
    }
    for f in _DATA["flours"]
)
