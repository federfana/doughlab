# DoughLab 🍕

> ⚠️ **Nome provvisorio**: esiste già altro software con questo nome. Lo cambieremo prima di qualsiasi pubblicazione.

Laboratorio digitale per impasti pizza/pane. Prevede **quando** l'impasto è davvero maturo, non solo che ora segna il piano. Si installa come PWA sull'iPhone.

- **Backend**: FastAPI + SQLAlchemy 2.0 async + SQLite
- **Frontend**: Jinja2 + HTMX + Tailwind (CDN) + Chart.js, PWA installabile
- **Modelli scientifici**: Newton (termico) + Q10 (fermentazione)
- **Tooling**: `uv` + ruff + mypy + pytest

---

## Indice

1. [Avvio rapido](#avvio-rapido)
2. [Accesso dal cellulare in LAN](#accesso-dal-cellulare-in-lan)
3. [Struttura del progetto](#struttura-del-progetto)
4. [Architettura](#architettura)
5. [I modelli scientifici](#i-modelli-scientifici)
6. [Documentazione del codice](#documentazione-del-codice)
7. [Testing](#testing)
8. [Convenzioni di sviluppo](#convenzioni-di-sviluppo)
9. [Roadmap](#roadmap)

---

## Avvio rapido

```bash
uv sync                 # installa dipendenze (crea .venv)
uv run doughlab         # avvia uvicorn con reload su 0.0.0.0:8000
```

Poi apri <http://localhost:8000>.

Comandi utili:

```bash
uv run pytest             # test unitari
uv run ruff check .       # linting
uv run ruff check --fix . # autofix sicuri
uv run mypy               # type check
```

## Accesso dal cellulare in LAN

```bash
ipconfig getifaddr en0   # scopri l'IP del Mac sulla Wi-Fi
# es. 192.168.1.126
```

Sull'iPhone, sulla stessa Wi-Fi, apri `http://192.168.1.126:8000`.
Safari → Condividi → **Aggiungi alla schermata Home**: diventa un'icona come un'app.

> **PWA e iOS**: senza HTTPS iOS non registra il service worker e non invia push. Per uso casalingo l'icona-home e l'export `.ics` nel Calendario coprono il 90% dei bisogni. Il resto lo abiliteremo quando aggiungeremo HTTPS.

---

## Struttura del progetto

```
doughlab/
├── pyproject.toml                 # dipendenze + config ruff/pytest/mypy
├── README.md                      # questo file
├── data/                          # DB SQLite (gitignored)
├── src/doughlab/
│   ├── __init__.py                # entry point `doughlab` (uvicorn)
│   ├── config.py                  # Settings (env + .env)
│   ├── db.py                      # engine async + session + init_db()
│   ├── models.py                  # ORM: Recipe, RecipeVersion, Bake
│   ├── main.py                    # FastAPI app + route
│   ├── services/
│   │   ├── thermal.py             # modello di Newton (τ per profilo)
│   │   ├── fermentation.py        # modello Q10 del lievito
│   │   └── scheduler.py           # orchestra tutto in un PlanResult
│   ├── templates/
│   │   ├── base.html              # layout Tailwind + HTMX + Chart.js
│   │   ├── planner.html           # form del pianificatore (HTMX live)
│   │   └── partials/
│   │       └── plan_result.html   # fragment ritornato da /plan
│   └── static/
│       ├── manifest.webmanifest   # PWA
│       ├── sw.js                  # service worker (shell cache)
│       └── icons/                 # icone PWA
└── tests/
    ├── test_thermal.py            # proprietà di Newton
    ├── test_fermentation.py       # proprietà di Q10
    └── test_scheduler.py          # end-to-end del piano
```

---

## Architettura

```
            ┌──────────────────────────────────────────────┐
            │                 Browser / PWA                │
            │  HTMX form live → POST /plan → HTML fragment │
            └───────┬─────────────────────────────┬────────┘
                    │                             │
                    ▼                             ▼
            ┌────────────────┐           ┌──────────────────┐
            │  main.py       │           │  static/sw.js    │
            │  FastAPI route │           │  shell cache     │
            └───────┬────────┘           └──────────────────┘
                    │
       ┌────────────┼────────────────┐
       ▼            ▼                ▼
┌─────────────┐ ┌──────────────┐ ┌──────────────┐
│ scheduler   │ │ thermal      │ │ fermentation │
│  compone    │ │  Newton      │ │  Q10         │
│  PlanResult │◀┤  simulate()  │◀┤  simulate()  │
└─────┬───────┘ └──────────────┘ └──────────────┘
      │
      ▼
┌─────────────┐
│ db.py       │  (futuro: persistenza ricette/bake)
│ SQLAlchemy  │
│  async      │
└─────────────┘
```

Flusso di una richiesta `POST /plan`:

1. **main.py** riceve il form, parsa fasi + lievito + T° iniziale.
2. Costruisce un `PlanInput` e chiama `scheduler.build_plan(...)`.
3. **scheduler.py** converte le fasi in `ThermalSegment` e chiama `thermal.simulate(...)` → `ThermalCurve`.
4. Passa la curva a `fermentation.simulate(...)` → `FermentationResult` (lavoro cumulato W(t) e maturità %).
5. Calcola per ogni fase l'intervallo di maturità (`maturity_start_pct` → `maturity_end_pct`).
6. Rende il template `partials/plan_result.html` con tabella + canvas Chart.js.

Il frontend fa partire la richiesta via **HTMX** `hx-post` ad ogni `change` del form (debounce 300 ms), quindi la UI è "live": muovi un valore e il grafico si ricalcola.

---

## I modelli scientifici

### 1. Modello termico — Newton

Equazione fondamentale:

$$\frac{dT}{dt} = -\frac{T - T_{\text{amb}}}{\tau}$$

Soluzione esatta su un segmento ad ambient costante:

$$T(t + \Delta t) = T_{\text{amb}} + (T(t) - T_{\text{amb}}) \cdot e^{-\Delta t / \tau}$$

**τ (costante di tempo)** = tempo per percorrere il 63% della strada verso l'ambiente. Dipende da massa, superficie, mezzo. Noi usiamo una tabella `(Container × Environment) → τ` con 16 combinazioni in [services/thermal.py](src/doughlab/services/thermal.py).

I profili disponibili:

| Container | Significato |
|---|---|
| `MASS_BOWL` | massa in ciotola/madia (puntata) |
| `MASS_BOX` | massa in cassetta coperta |
| `BALLS_BOX` | panetti stagliati in cassetta |
| `BALLS_SINGLE` | panetto singolo esposto |

| Environment | Significato |
|---|---|
| `AMBIENT` | ambiente di casa |
| `FRIDGE_HOME` | frigo domestico (apre/chiude) |
| `FRIDGE_BOX` | cassetta chiusa in frigo (isolamento) |
| `CHAMBER` | cella di lievitazione |

**Rispetto all'HTML di riferimento** che usa 2 τ fisse (2.8 h frigo, 1.3 h fuori), DoughLab distingue i profili: panetti stagliati rispondono in ~0.9 h a casa, la massa unica in ~1.6 h.

### 2. Modello di fermentazione — Q10

Approssimazione pratica di Arrhenius valida nel range utile (0-40 °C):

$$k(T) = k_{\text{ref}} \cdot Q_{10}^{\,(T - T_{\text{ref}})/10}$$

Interpretazione: **ogni +10 °C la velocità di reazione si moltiplica per Q10**.

Parametri in [services/fermentation.py](src/doughlab/services/fermentation.py):

| Lievito | Q10 | T_ref | k_ref | Note |
|---|---|---|---|---|
| Fresco | 2.7 | 25 °C | 1.0 | riferimento |
| Secco | 2.7 | 25 °C | 3.0 | ~3× il fresco a parità di grammi |
| Madre | 2.2 | 26 °C | 0.45 | più tollerante al freddo (microbiota misto) |

Dalla velocità al **lavoro cumulato** (= maturità):

$$W(t) = \int_0^t k(T(\tau)) \cdot [\text{lievito}\%] \, d\tau$$

Integrato con trapezi (O(n)). Quando $W(t) \ge W_{\text{target}}$ l'impasto è "maturo al 100%".

**Suggerimento del lievito ottimale** (`suggest_yeast_pct`): calcola $W$ assumendo lievito=1%, poi divide il target per il risultato → trova la % che fa atterrare la maturità esattamente al 100%.

### Limiti onesti del modello

- Ignora calore generato dalla fermentazione (trascurabile < 2 kg)
- Ignora evaporazione (assume impasto coperto)
- `T_ambiente` costante nel segmento (frigo in realtà oscilla)
- `target_work = 24` è arbitrario → ha senso solo come confronto *relativo* finché non lo calibri sui tuoi log

---

## Documentazione del codice

### [config.py](src/doughlab/config.py)

Carica configurazione da variabili d'ambiente e `.env` tramite `pydantic-settings`. Prefisso env `DOUGHLAB_`.

| Setting | Default | Note |
|---|---|---|
| `app_name` | `"DoughLab"` | mostrato nei template |
| `debug` | `True` | flag generico |
| `db_url` | `sqlite+aiosqlite:///data/doughlab.db` | async |
| `default_ambient_c` | `22.0` | fallback form |
| `default_fridge_c` | `4.0` | fallback form |

Crea `data/` automaticamente al primo import.

### [db.py](src/doughlab/db.py)

Setup SQLAlchemy 2.0 **async** (richiede l'extra `[asyncio]` per installare `greenlet`).

- `Base`: `DeclarativeBase` da cui ereditano tutti i modelli
- `engine`: `AsyncEngine` basato su `aiosqlite`
- `SessionLocal`: `async_sessionmaker` con `expire_on_commit=False` (consigliato in async per evitare lazy-load sorprese)
- `get_session()`: generatore async usabile come `Depends(get_session)` nei router
- `init_db()`: `create_all()` idempotente, chiamato dal `lifespan` di FastAPI

### [models.py](src/doughlab/models.py)

Tre modelli ORM:

- **`Recipe`**: metadati della ricetta (nome, stile, note).
- **`RecipeVersion`**: ogni modifica è una nuova riga → **ricettario versionato**. Payload JSON contiene fasi/ingredienti/parametri, utile come MVP prima di normalizzare lo schema.
- **`Bake`**: una infornata reale, con `log` JSON di eventi (fase, start, end, T° ambiente, foto, nota) + rating 1-5.

> I modelli esistono ma non sono ancora esposti via API. Lo faremo nella fase 2 (persistenza ricette).

### [services/thermal.py](src/doughlab/services/thermal.py)

| Simbolo | Tipo | Scopo |
|---|---|---|
| `Container` | `StrEnum` | profili di contenitore (vedi tabella sopra) |
| `Environment` | `StrEnum` | profili di ambiente |
| `CONTAINER_LABELS`, `ENVIRONMENT_LABELS` | `dict[Enum, str]` | etichette italiane per la UI |
| `TAU_TABLE` | `dict[(Container, Environment), float]` | τ (ore) per ogni combinazione |
| `tau_for(container, env)` | funzione | lookup di τ con fallback |
| `ThermalSegment` | `dataclass` | `(hours, ambient_c, container, environment, tau_override)` |
| `ThermalCurve` | `dataclass` | `(time_h, temp_c, ambient_c, segment_index)` tutti `np.ndarray` |
| `simulate(segments, initial_c, step_h=0.1)` | funzione | integra Newton segmento per segmento, step temporale configurabile |

**Nota implementativa**: `simulate` usa la soluzione esatta `T_amb + (T - T_amb) e^(-dt/τ)` ad ogni passo, non un metodo di integrazione numerica. Questo è esatto quando `ambient` e `τ` sono costanti nel passo, e cambia valore solo tra segmenti.

### [services/fermentation.py](src/doughlab/services/fermentation.py)

| Simbolo | Tipo | Scopo |
|---|---|---|
| `YeastKind` | `StrEnum` | `FRESH`, `DRY`, `SOURDOUGH` |
| `YeastParams` | `dataclass(frozen=True)` | `(q10, t_ref_c, k_ref, label)` |
| `YEAST_PARAMS` | `dict[YeastKind, YeastParams]` | parametri default (tabella sopra) |
| `rate(temp_c, kind)` | funzione | $k(T)$ pointwise (anche su `np.ndarray`) |
| `FermentationResult` | `dataclass` | `(time_h, rate, cumulative, maturity_pct, ready_at_h, final_pct)` |
| `simulate(curve, kind, yeast_pct, target_work)` | funzione | integra W(t), interpola `ready_at_h` quando W=target |
| `suggest_yeast_pct(curve, kind, target_work)` | funzione | % di lievito che fa W_final = target |

### [services/scheduler.py](src/doughlab/services/scheduler.py)

Il "direttore d'orchestra". Converte una lista di fasi in un `PlanResult` completo.

| Simbolo | Tipo | Scopo |
|---|---|---|
| `PhaseKind` | `StrEnum` | 10 fasi (preferment, autolyse, mix, bulk, maturation, temper, shape, proof, open, bake) |
| `PHASE_LABELS` | `dict[PhaseKind, str]` | etichette italiane |
| `FERMENTING_PHASES` | `set[PhaseKind]` | fasi in cui conta il lievito (usato per UI/validazione futura) |
| `PlanPhase` | `dataclass` | input: `(kind, label, hours, ambient_c, container, environment)` |
| `PlanInput` | `dataclass` | wrapper: `(start_at, initial_dough_c, phases, yeast_kind, yeast_pct, target_work)` |
| `PhaseResult` | `dataclass` | output per fase: `(phase, start_at, end_at, maturity_start_pct, maturity_end_pct)` |
| `PlanResult` | `dataclass` | output totale: `(phases, thermal, fermentation, total_hours, ready_at, end_at)` |
| `build_plan(inp)` | funzione | orchestrazione: fasi → curva termica → fermentazione → risultato |

### [main.py](src/doughlab/main.py)

L'app FastAPI. Route attuali:

| Metodo | Path | Scopo |
|---|---|---|
| `GET` | `/` | pagina `planner.html` con form precompilato |
| `POST` | `/plan` | ritorna il **fragment HTML** `plan_result.html` (HTMX swap) |
| `POST` | `/plan.ics` | ritorna il piano come file `.ics` da aprire in Calendario |
| `GET` | `/static/*` | asset statici (PWA, icone, SW) |

Il parser del form (`_parse_phase_form`) legge campi index-based tipo `phase_kind_0`, `phase_hours_0`, `phase_kind_1`, ... → questo permette aggiunta/rimozione dinamica di righe dal frontend senza payload JSON.

### [templates/](src/doughlab/templates/)

- **`base.html`**: layout minimale, import di Tailwind + HTMX + Chart.js da CDN, registra il service worker. Niente Node, niente build step.
- **`planner.html`**: form del pianificatore. Ogni cambio su un input triggera `hx-post="/plan"` con swap su `#result`. Rendering iniziale invocato con `htmx.trigger('#planForm','submit')` al load.
- **`partials/plan_result.html`**: fragment con tabella fasi + canvas Chart.js. Il grafico ha 3 serie (T° impasto, T° ambiente, maturità %) su due assi y.

### [static/](src/doughlab/static/)

- **`manifest.webmanifest`**: nome, colori, icone 192/512 → "installabile" come PWA.
- **`sw.js`**: service worker minimale, cache-first per asset statici, network-first per il resto. Permette di aprire l'app con l'ultima pagina vista anche offline.
- **`icons/*.png`**: placeholder generati con Python puro (zlib). Da sostituire con grafica vera.

---

## Testing

14 test (al 2026-10-02). Lanciali con `uv run pytest`.

### [tests/test_thermal.py](tests/test_thermal.py)

| Test | Proprietà verificata |
|---|---|
| `test_tau_table_has_all_combos` | tabella τ completa 4×4 |
| `test_equilibrium_reaches_ambient` | dopo tempo lungo, T → T_amb |
| `test_monotone_cooling` | in raffreddamento T è monotòna decrescente |
| `test_monotone_warming` | in riscaldamento T è monotòna crescente |
| `test_balls_warm_faster_than_mass` | panetti stagliati scaldano prima della massa (τ più piccola) |
| `test_time_constant_matches_63pct` | a t=τ, T è a 1-1/e dal gap iniziale |

### [tests/test_fermentation.py](tests/test_fermentation.py)

| Test | Proprietà verificata |
|---|---|
| `test_rate_at_t_ref_equals_k_ref` | $k(T_{\text{ref}}) = k_{\text{ref}}$ |
| `test_q10_doubles_every_10c` | $k(T+10)/k(T) = Q_{10}$ |
| `test_dry_is_stronger_than_fresh` | k_ref secco > fresco |
| `test_fermentation_monotone` | W(t) sempre crescente |
| `test_suggested_pct_hits_target` | con la % suggerita, maturità finale ≈ 100% |

### [tests/test_scheduler.py](tests/test_scheduler.py)

| Test | Proprietà verificata |
|---|---|
| `test_total_hours_sum` | somma ore = `end_at - start_at` |
| `test_end_and_phase_consistency` | ultima `PhaseResult.end_at` == `end_at` globale |
| `test_maturity_increases_in_fermenting_phases` | nell'appretto la maturità cresce |

---

## Convenzioni di sviluppo

- **Formattazione**: `ruff` fa sia linting che format (`line-length=100`, target `py312`).
- **Type checking**: `mypy` in modalità `strict`.
- **Import style**: ordinati da ruff (regola `I`); si importa SEMPRE con nomi relativi dentro `doughlab/`.
- **Dataclass vs Pydantic**: Pydantic solo ai confini (settings, schema API). Dentro i servizi, `dataclass` semplici per minimo overhead.
- **Numpy ovunque**: le curve termiche/fermentazione viaggiano come `np.ndarray`. Nel template, `.tolist()` per Chart.js.
- **Nessun bundler**: HTMX+Tailwind da CDN. Niente Node, niente webpack, niente step di build.
- **Niente lazy-load SQLAlchemy in async**: `expire_on_commit=False`.
- **Documentazione**: questo README va tenuto aggiornato ad ogni cambio di API o aggiunta di modulo. Niente file `.md` paralleli per feature singole.

---

## Roadmap

### ✅ MVP (fatto)
- Modello termico Newton con profili contenitore/ambiente
- Modello fermentazione Q10 (fresco/secco/LM)
- Pianificatore HTMX con grafico Chart.js
- Export `.ics` per Calendario iOS
- PWA installabile
- 14 test unitari verdi
- UI in italiano con etichette leggibili

### 🔜 Fase 2 — Il tool completo per il pizzaiolo
- Calcolatore ingredienti integrato (napoletana, teglia, pinsa, biga, poolish, LM)
- Persistenza ricette con versioning (ORM già pronto)
- UI load/save/elenco ricette
- **Live Bake mode**: timer mobile per fase corrente + checkpoint
- Diario infornate con upload foto e rating

### 🔮 Fase 3 — Analisi
- Analisi alveolatura via OpenCV (contorni bolle, uniformità, densità)
- Database farine (W, P/L) + blend calculator
- Suggerimenti correlati ai log passati

### 🧪 Fase 4 — Avanzata
- Fork/diff visuale delle ricette (git-like)
- Starter / LM tracker (rinfreschi, raddoppio)
- Calibrazione automatica τ e Q10 sui log reali con `scipy.optimize`
- Integrazione termometro BLE
- (Opzionale) ESP32 + termocoppia per logging forno
