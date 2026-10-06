# DoughLab 🍕

> ⚠️ **Nome provvisorio**: esiste già altro software con questo nome. Lo cambieremo prima di qualsiasi pubblicazione.

Laboratorio digitale per impasti pizza/pane. Prevede **quando** l'impasto è davvero maturo, non solo che ora segna il piano. Si installa come PWA sull'iPhone.

- **Backend**: FastAPI + SQLAlchemy 2.0 async + SQLite
- **Frontend**: Jinja2 + HTMX + Alpine.js + Chart.js + CSS variables (dark/light auto + toggle)
- **Modelli scientifici**: Newton (termico) + Q10 (fermentazione) + baker's % (ingredienti)
- **Tooling**: `uv` + ruff + mypy + pytest

---

## Indice

1. [Funzionalità](#funzionalità)
2. [Avvio rapido](#avvio-rapido)
3. [Accesso dal cellulare in LAN](#accesso-dal-cellulare-in-lan)
4. [Struttura del progetto](#struttura-del-progetto)
5. [Architettura](#architettura)
6. [I modelli scientifici](#i-modelli-scientifici)
7. [Documentazione del codice](#documentazione-del-codice)
8. [Testing](#testing)
9. [Convenzioni di sviluppo](#convenzioni-di-sviluppo)
10. [Roadmap](#roadmap)

---

## Funzionalità

- **Formula**: numero e peso dei panetti, idratazione, sale e tipo di lievito (fresco, secco attivo, madre) danno le grammature. Olio, zucchero e prefermento stanno nei parametri avanzati.
- **Fasi e temperature**: la sequenza di fasi (TA/TC, contenitore) genera la curva termica e la maturità. La **dose di lievito non si inserisce**: è calcolata dal piano.
- **Ricette base**: 5 preset caricabili con un click, con un orientamento sulla farina.
- **Suggerimenti di cottura**: in sola lettura, per forno domestico o elettrico con cielo e platea indipendenti. Non influenzano la maturazione.
- **Registro prove**: ogni prova salva lo snapshot del piano, l'orario in cui l'impasto era davvero pronto, temperatura, voto, note e i parametri di cottura realmente usati; mostra lo scarto rispetto alla stima.
- **Export `.ics`** per il Calendario, **PWA** installabile e tema chiaro/scuro.

---

## Avvio rapido

```bash
uv sync                 # installa dipendenze (crea .venv)
uv run doughlab         # avvia uvicorn con reload su 0.0.0.0:8000
```

Poi apri <http://localhost:8000>.

Se compare `Address already in use`, c'è già un'istanza in ascolto sulla porta 8000: riusala oppure fermala (`lsof -i :8000`). Il reload osserva solo `src/doughlab`, non `tests/`.

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
│   │   ├── ingredients.py         # calcolo baker's percentage
│   │   ├── presets.py             # ricette predefinite
│   │   └── scheduler.py           # orchestra tutto in un PlanResult
│   ├── templates/
│   │   ├── base.html              # layout, CSS con variabili, tema chiaro/scuro
│   │   ├── planner.html           # tab Pianifica + Registro prove (HTMX live, Alpine)
│   │   └── partials/
│   │       ├── plan_result.html   # fragment di /plan: ingredienti, riepilogo, grafico, timeline
│   │       └── bake_history.html  # form del registro prove + cronologia
│   └── static/
│       ├── manifest.webmanifest   # PWA
│       ├── sw.js                  # service worker (shell cache)
│       └── icons/                 # icone PWA
└── tests/
    ├── test_thermal.py            # proprietà di Newton
    ├── test_fermentation.py       # proprietà di Q10 e taratura della dose
    ├── test_ingredients.py        # baker's percentage e prefermento
    ├── test_scheduler.py          # end-to-end del piano
    └── test_main.py               # form, template, registro prove, .ics
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
│ db.py       │  (registro prove; ricette: futuro)
│ SQLAlchemy  │
│  async      │
└─────────────┘
```

Flusso di una richiesta `POST /plan`:

1. **main.py** riceve il form e lo normalizza: numeri non finiti o fuori intervallo tornano al default o ai limiti degli input HTML, al massimo 30 fasi.
2. Costruisce un `PlanInput` con lievito a 0 e chiama `scheduler.build_plan(...)` solo per ottenere la curva termica.
3. **scheduler.py** converte le fasi in `ThermalSegment` e chiama `thermal.simulate(...)` → `ThermalCurve`.
4. `fermentation.suggest_yeast_pct(...)` calcola la dose che porta la maturità al 100% a fine piano, contando solo le fasi fermentanti (`fermentation_activity_mask`).
5. Con quella dose `build_plan` produce il `PlanResult` definitivo: `fermentation.simulate(...)` → `FermentationResult` (lavoro cumulato W(t) e maturità %) e, per ogni fase, l'intervallo `maturity_start_pct` → `maturity_end_pct`.
6. `ingredients.compute(...)` ricava le grammature con lo stesso lievito suggerito.
7. Rende `partials/plan_result.html` (ingredienti, riepilogo, grafico, timeline) e aggiorna con `hx-swap-oob` il pannello del registro prove con lo snapshot del piano.

Il frontend invia la richiesta via **HTMX** `hx-post` quando modifichi un campo (`input` dopo 450 ms, `change` dopo 200 ms), quindi la UI è "live". Il cambio del profilo forno non ricalcola: aggiorna solo i suggerimenti di cottura.

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
| Fresco | 3.0 | 25 °C | 0.56 | tarato sui calcolatori di riferimento |
| Secco attivo | 3.0 | 25 °C | 1.34 | 2.4× il fresco a parità di grammi (1 g secco ≈ 2.4 g fresco) |
| Madre | 2.2 | 26 °C | 0.45 | non tarato: nessun riferimento; più tollerante al freddo |

Fresco e secco attivo sono tarati con un fit su 9 dosi pubblicate da PizzApp, Dough School e when.pizza (room temperature da 2 a 12 h, 16 e 28 °C, programmi con frigo): errore logaritmico medio 0.13 contro 0.68 con i parametri precedenti. Un caso di verifica: 9 h a 22 °C danno 0.115% di secco attivo (PizzApp 0.119%, Dough School 0.096%).

Ancore usate nel fit (dose di riferimento in lievito istantaneo, IDY; il fresco vale 3 × IDY, il secco attivo 1.25 × IDY):

| Scenario | IDY di riferimento | Fonte |
|---|---|---|
| 22 °C, 2 h | 0.45% | when.pizza |
| 22 °C, 8 h | 0.10% | when.pizza |
| 22 °C, 9 h | 0.095% (0.119% di secco attivo ÷ 1.25) | PizzApp |
| 22 °C, 12 h | 0.07% | when.pizza |
| 16 °C, 8 h | 0.20% | when.pizza |
| 28 °C, 8 h | 0.05% | when.pizza |
| 2 h a 22 °C + 22 h in frigo (4 °C) | 0.15% | Dough School |
| 2 h a 22 °C + 46 h in frigo | 0.08% | Dough School |
| 2 h a 22 °C + 70 h in frigo | 0.05% | Dough School |

Non usati nel fit e controllati dopo: frigo puro 24-72 h (when.pizza) e le dosi a temperatura ambiente di PizzaPlan.

Dalla velocità al **lavoro cumulato** (= maturità):

$$W(t) = \int_0^t k(T(\tau)) \cdot 100 \cdot p_{\text{lievito}} \, d\tau$$

`p_lievito` è la frazione usata nei calcoli (`0.0015` = 0.15%); il fattore 100 la converte in punti percentuali. L'integrale è calcolato con trapezi (O(n)). Quando $W(t) \ge W_{\text{target}}$ l'impasto raggiunge il target.

**Lievito consigliato** (`suggest_yeast_pct`): calcola il lavoro di riferimento con una dose dell'1% e scala linearmente per trovare la dose che raggiunge il target. Il calcolo è automatico: la stessa dose viene usata per la maturità e per i grammi mostrati. Il target predefinito (`DEFAULT_TARGET_WORK = 1`) è un riferimento iniziale, non una previsione scientificamente validata: temperatura reale dell'impasto, forza del lievito e farina richiedono calibrazione con prove.

### Limiti onesti del modello

- Ignora calore generato dalla fermentazione (trascurabile < 2 kg)
- Ignora evaporazione (assume impasto coperto)
- `T_ambiente` costante nel segmento (frigo in realtà oscilla)
- il target di maturità è un riferimento sperimentale, non una misura universale; il dosaggio consigliato va confrontato con risultati reali prima di affidarcisi
- i riferimenti usati per la taratura non coincidono tra loro (tabelle generiche da 0.05% a 0.5% per lo stesso scenario): il fit privilegia i tre calcolatori convergenti. Su frigo puro (24-72 h) il modello suggerisce ancora circa il 25-35% in più di when.pizza; le ricette con puntata a temperatura ambiente prima del frigo sono entro ±22%
- non distingue secco attivo e istantaneo: il tipo "secco" è calibrato sull'attivo (istantaneo ≈ 0.8× l'attivo)
- con un prefermento la dose di lievito è calcolata sulla farina totale e conta come presente dall'inizio: è un'approssimazione, perché di solito il lievito sta tutto nel prefermento
- orari in ora locale senza fuso: un piano che attraversa il cambio ora legale (ultima domenica di ottobre/marzo) può risultare sfasato di un'ora
- i valori del form sono limitati lato server agli stessi intervalli degli input HTML (fasi ≤ 30, durata ≤ 720 h, ecc.); valori non numerici tornano al default

---

## Documentazione del codice

### [config.py](src/doughlab/config.py)

Carica configurazione da variabili d'ambiente e `.env` tramite `pydantic-settings`. Prefisso env `DOUGHLAB_`.

| Setting | Default | Note |
|---|---|---|
| `app_name` | `"DoughLab"` | mostrato nei template |
| `debug` | `True` | flag generico (non ancora usato) |
| `db_url` | `sqlite+aiosqlite:///data/doughlab.db` | async |
| `default_ambient_c` | `22.0` | previsto come fallback del form (non ancora usato) |
| `default_fridge_c` | `4.0` | previsto come fallback del form (non ancora usato) |

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
- **`Bake`**: una prova reale, usata dal registro prove (`POST /bakes`). Ha `notes` e `rating` 1-5; `log` è una lista JSON con una voce `plan` (snapshot del piano, inclusi i suggerimenti di cottura) e una voce `observation` (orario di maturità reale, T° impasto, parametri di cottura effettivi).

> Solo `Bake` è esposto, tramite il registro prove. `Recipe` e `RecipeVersion` esistono ma non sono ancora usati: arriveranno con la persistenza ricette (fase 2).

### [services/thermal.py](src/doughlab/services/thermal.py)

| Simbolo | Tipo | Scopo |
|---|---|---|
| `Container` | `StrEnum` | profili di contenitore (vedi tabella sopra) |
| `Environment` | `StrEnum` | profili di ambiente |
| `CONTAINER_LABELS`, `ENVIRONMENT_LABELS` | `dict[Enum, str]` | etichette italiane per la UI |
| `TAU_TABLE` | `dict[(Container, Environment), float]` | τ (ore) per ogni combinazione |
| `tau_for(container, env)` | funzione | lookup di τ in `TAU_TABLE` |
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
| `simulate(curve, kind, yeast_pct, target_work, active_mask=None)` | funzione | integra W(t), interpola `ready_at_h` quando W=target; `active_mask` esclude gli intervalli non fermentanti |
| `suggest_yeast_pct(curve, kind, target_work, active_mask=None)` | funzione | % di lievito che fa W_final = target |

### [services/ingredients.py](src/doughlab/services/ingredients.py)

Calcolo grammature con il sistema **baker's percentage**: tutto è relativo al 100% di farina.

| Simbolo | Tipo | Scopo |
|---|---|---|
| `RecipeStyle` | `StrEnum` | 7 stili (napoletana, teglia, pala, pinsa, romana, pane, panettone) |
| `STYLE_LABELS` | `dict[RecipeStyle, str]` | etichette italiane |
| `RecipeIngredients` | `dataclass` | input: `panetto_g`, `n_panetti`, %idratazione, %sale, %lievito, %olio, %zucchero, %prefermento, %idratazione prefermento |
| `IngredientWeights` | `dataclass` | output: grammi di farina/acqua/sale/lievito/olio/zucchero + ripartizione tra prefermento e impasto finale |
| `compute(ri)` | funzione | risolve `farina * (1 + idratazione + sale + ...) = peso_totale` e distribuisce; l'acqua del prefermento non supera quella totale |

La logica: dato peso_panetto×n_panetti = peso_totale, si imposta `denominatore = 1 + sum(percentuali)` e si ricava `farina = peso_totale / denominatore`. Da lì tutte le grammature sono `farina × percentuale`.

### [services/presets.py](src/doughlab/services/presets.py)

Ricette predefinite caricabili con un click dalla UI (`/?preset=<key>`).

| Simbolo | Tipo | Scopo |
|---|---|---|
| `BakingAdvice` | `dataclass` | profilo casa + setpoint indipendenti cielo/platea (`split_plate_c`, `split_ceiling_c`), durata e hint |
| `Preset` | `dataclass` | `(key, label, style, description, flour_hint, baking, ingredients, yeast_kind, target_work, phases)` |
| `PRESETS` | `list[Preset]` | lista di preset (5 al momento) |
| `PRESETS_BY_KEY` | `dict[str, Preset]` | lookup O(1) |

Preset inclusi (ogni base comprende anche un orientamento sulla farina; percentuali proteiche indicative, da valutare insieme a W e alle indicazioni del molino):
- `napoletana` — 8h a 22°C diretto
- `napoletana_frigo` — 24h con maturazione in frigo
- `teglia` — teglia romana 24h+ con olio
- `pinsa` — pinsa 48h ad alta idratazione
- `pane_biga` — pane con biga al 30%

I suggerimenti per napoletana e teglia sono orientativi e non modificabili nel pianificatore; nel registro delle prove si annotano i parametri effettivamente usati. Gli intervalli riportati seguono la [guida Macte sulle temperature](https://macteovens.com/blogs/ricette-consigli/temperatura-forno-pizza-quanti-gradi-per-ogni-tipo-da-napoletana-a-teglia). Il profilo a resistenze separate mostra setpoint distinti per cielo e platea fino a 510 °C; verifica sempre i limiti del tuo forno. Per pinsa e pane, senza un riferimento univoco, i setpoint restano da calibrare.

### [services/scheduler.py](src/doughlab/services/scheduler.py)

Il "direttore d'orchestra". Converte una lista di fasi in un `PlanResult` completo.

| Simbolo | Tipo | Scopo |
|---|---|---|
| `PhaseKind` | `StrEnum` | 10 fasi (preferment, autolyse, mix, bulk, maturation, temper, shape, proof, open, bake) |
| `PHASE_LABELS` | `dict[PhaseKind, str]` | etichette italiane |
| `FERMENTING_PHASES` | `set[PhaseKind]` | fasi la cui durata contribuisce all'attività del lievito; esclude autolisi e cottura |
| `fermentation_activity_mask(thermal, phases)` | funzione | maschera booleana per intervallo di tempo: `True` dove la fase è fermentante |
| `PlanPhase` | `dataclass` | input: `(kind, label, hours, ambient_c, container, environment)` |
| `PlanInput` | `dataclass` | wrapper: `(start_at, initial_dough_c, phases, yeast_kind, yeast_pct, target_work)` |
| `PhaseResult` | `dataclass` | output per fase: `(phase, start_at, end_at, maturity_start_pct, maturity_end_pct)` |
| `PlanResult` | `dataclass` | output totale: `(phases, thermal, fermentation, total_hours, ready_at, end_at)` |
| `build_plan(inp)` | funzione | orchestrazione: fasi → curva termica → fermentazione → risultato |

### [main.py](src/doughlab/main.py)

L'app FastAPI. Route attuali:

| Metodo | Path | Scopo |
|---|---|---|
| `GET` | `/` | pagina `planner.html` con tab Piano/Registro, primo preset e storico recente |
| `GET` | `/?preset=<key>&yeast=<kind>&oven=<profile>` | carica preset mantenendo lievito e profilo forno |
| `POST` | `/plan` | ritorna il **fragment HTML** `plan_result.html` (HTMX swap) |
| `POST` | `/bakes` | salva nel database una prova reale e restituisce lo scarto dalla maturità prevista |
| `POST` | `/plan.ics` | ritorna il piano come file `.ics` da aprire in Calendario (orari in ora locale del server) |
| `GET` | `/static/*` | asset statici (PWA, icone, SW) |

Helper interni:
- `_common_ctx()` → dropdown e metadati sempre serviti al template
- `_number(data, key, default, low, high)` → numero finito dentro i limiti, altrimenti il default (nessun `inf`/`NaN` arriva ai servizi)
- `_parse_phase_form(data)` → legge campi index-based `phase_kind_0`, `phase_hours_0`, ... (max 30 fasi, durata ≤ 720 h)
- `_parse_ingredients(data)` → estrae grammature e percentuali dal form, con gli stessi limiti degli input HTML
- `_baking_advice(preset, oven_profile)` → suggerimento di cottura per il profilo `home` o `split`
- `_default_recipe_ctx()` / `_preset_ctx(key)` → struttura dati per il template
- `_compute_plan_and_ingredients(data)` → pacchetto unificato per `/plan` e `/plan.ics`; lo snapshot contiene i suggerimenti di entrambi i profili forno (`baking_options`)
- `_make_bake_record(data)` / `_bake_history_item(record)` / `_recent_bakes()` → salvataggio e lettura del registro prove

### [templates/](src/doughlab/templates/)

- **`base.html`**: layout minimale con variabili CSS semantiche (`--bg`, `--surface`, `--ac`…), dark mode automatica (preferenza di sistema) + toggle manuale persistente in `localStorage`. Alpine.js + HTMX + Chart.js caricati da CDN. Niente Node, niente build step. Il testo secondario (`--mut`) rispetta il contrasto AA in entrambi i temi.
- **`planner.html`**: una tab bar nella stessa pagina separa **Pianifica** da **Registro prove**. La scheda Piano contiene input base, ricetta, fasi e suggerimenti di cottura in sola lettura, selezionabili per forno domestico o elettrico con cielo e platea. I parametri reali si annotano nel Registro e non influenzano la maturazione.
- **`partials/plan_result.html`**: HTMX aggiorna ingredienti e riepilogo in `#result`, grafico e timeline in `#detailsResult`, e lo snapshot nel tab nascosto `#bakeHistory` con `hx-swap-oob`. Il tab Registro può quindi essere aperto senza ricalcolare o perdere il piano. Il grafico ha altezza responsive fissa (`.chart-wrap`), nasconde i titoli degli assi sotto i 560 px, legge i colori dalle variabili CSS e si ridisegna al cambio tema; l'asse X è il tempo trascorso in ore.
- **`partials/bake_history.html`**: form del registro prove (orario reale di maturità, T° impasto, voto, note, parametri di cottura usati) e cronologia con lo scarto dalla stima. Il tipo di forno segue la scelta del planner e i valori consigliati compaiono come placeholder; le prove sono salvate in `Bake.log`.

Nota UX: nel form le percentuali sono inserite in formato umano (`62`, `2.8`) e convertite server-side in frazioni per i calcoli. I decimali si possono digitare liberamente. Il lievito non è un input: la percentuale suggerita dall'app determina anche i grammi mostrati. Giorni e mesi nel risultato sono localizzati in italiano.

### [static/](src/doughlab/static/)

- **`manifest.webmanifest`**: nome, colori, icone 192/512 → "installabile" come PWA.
- **`sw.js`**: service worker minimale, cache-first per asset statici, network-first per il resto. Salva l'ultima pagina vista, ma Alpine.js, HTMX e Chart.js arrivano da CDN e non sono nella cache: **offline la pagina si apre ma non è interattiva** finché non verranno serviti da `static/`.
- **`icons/*.png`**: placeholder generati con Python puro (zlib). Da sostituire con grafica vera.

---

## Testing

53 test (al 2026-10-06). Lanciali con `uv run pytest`.

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
| `test_room_temperature_dose_matches_independent_calculators` | 9 h a 22 °C: secco attivo tra 0.09% e 0.13% (PizzApp 0.119%, Dough School 0.096%) e fresco = 2.4 × secco |
| `test_fermentation_monotone` | W(t) sempre crescente |
| `test_suggested_pct_hits_target` | con la % suggerita, maturità finale ≈ 100% |

### [tests/test_scheduler.py](tests/test_scheduler.py)

| Test | Proprietà verificata |
|---|---|
| `test_total_hours_sum` | somma ore = `end_at - start_at` |
| `test_end_and_phase_consistency` | ultima `PhaseResult.end_at` == `end_at` globale |
| `test_maturity_increases_in_fermenting_phases` | nell'appretto la maturità cresce |

### [tests/test_ingredients.py](tests/test_ingredients.py)

| Test | Proprietà verificata |
|---|---|
| `test_total_mass_matches_panetti` | somma grammature == `panetto_g × n_panetti` |
| `test_hydration_ratio` | `acqua / farina == idratazione%` |
| `test_salt_ratio` | `sale / farina == sale%` |
| `test_preferment_split` | prefermento + rinfresco == totale |
| `test_oil_included_in_total` | l'olio entra nel bilancio massico |
| `test_preferment_water_never_exceeds_total_water` | il prefermento non porta l'acqua dell'impasto finale sotto zero |

### [tests/test_main.py](tests/test_main.py)

| Test | Proprietà verificata |
|---|---|
| `test_suggested_yeast_is_used_for_plan_and_weights` | dose suggerita usata nel piano e nei grammi |
| `test_hydration_change_recalculates_all_ingredient_weights` | variazione idratazione aggiorna pesi ingredienti a peso totale costante |
| `test_planner_shows_primary_inputs_and_hides_manual_yeast_dose` | UI mostra i quattro input base e non chiede la dose di lievito |
| `test_selected_yeast_type_survives_recipe_change` | la selezione del lievito viene mantenuta cambiando preset |
| `test_oven_profile_survives_recipe_change` | la scelta del profilo forno si conserva cambiando preset |
| `test_legacy_nettuno_oven_profile_maps_to_split_heaters` | i vecchi URL Nettuno vengono convertiti nel profilo generico |
| `test_schedule_duration_changes_yeast_suggestion_not_formula_percentages` | il piano cambia il lievito stimato ma non idratazione e sale impostati |
| `test_phase_cards_explain_temperature_and_preset_effects` | UI spiega preset, fasi, TA/TC e ordine degli input |
| `test_non_fermenting_phase_duration_does_not_change_yeast_suggestion` | autolisi e cottura non contribuiscono alla stima del lievito |
| `test_summary_combines_ready_and_end_when_they_match` | evita date duplicate se maturità e fine piano coincidono |
| `test_summary_separates_ready_from_later_bake_phase` | distingue la maturità dalla fine del piano se segue la cottura |
| `test_chart_x_axis_uses_elapsed_hours_not_sample_indexes` | asse X in ore reali, non in indici dei campioni |
| `test_chart_has_fixed_responsive_height_and_follows_theme` | il grafico ha altezza responsive fissa e si ridisegna al cambio tema |
| `test_bake_observation_saves_snapshot_and_prediction_delta` | conserva lo snapshot e calcola lo scarto temporale |
| `test_bake_route_persists_observation_in_sqlite` | `/bakes` conserva snapshot e risultato nel DB |
| `test_cooking_advice_is_not_overridden_by_planner_form` | il planner mantiene i suggerimenti del preset |
| `test_split_oven_profile_keeps_preset_platea_and_ceiling_advice` | i suggerimenti cielo/platea restano quelli del preset |
| `test_teglia_preset_shows_split_oven_cielo_and_platea_advice` | il preset teglia mostra setpoint separati e hint di cottura |
| `test_hostile_form_values_never_hang_or_produce_non_finite_plans` | inf/NaN, ore enormi o negative, date ed enum non validi non bloccano né producono piani non finiti |
| `test_phase_count_is_capped` | il server accetta al massimo 30 fasi |
| `test_ics_export_uses_local_time_not_utc` | l'export `.ics` non sposta gli orari di fuso |
| `test_bake_form_never_embeds_snapshot_text_in_javascript` | uno snapshot ostile o non-oggetto non genera JS iniettato né errori 500 |

---

## Convenzioni di sviluppo

- **Formattazione**: `ruff` fa sia linting che format (`line-length=100`, target `py312`).
- **Type checking**: `mypy` in modalità `strict`.
- **Import style**: ordinati da ruff (regola `I`); si importa SEMPRE con nomi relativi dentro `doughlab/`.
- **Dataclass vs Pydantic**: Pydantic solo ai confini (settings, schema API). Dentro i servizi, `dataclass` semplici per minimo overhead.
- **Numpy ovunque**: le curve termiche/fermentazione viaggiano come `np.ndarray`. Nel template, `.tolist()` per Chart.js.
- **Nessun bundler**: HTMX, Alpine.js e Chart.js da CDN, CSS scritto a mano con variabili. Niente Node, niente webpack, niente step di build.
- **Niente lazy-load SQLAlchemy in async**: `expire_on_commit=False`.
- **Documentazione**: questo README va tenuto aggiornato ad ogni cambio di API o aggiunta di modulo. Niente file `.md` paralleli per feature singole.

---

## Roadmap

### ✅ MVP (fatto)
- Modello termico Newton con profili contenitore/ambiente
- Modello fermentazione Q10 (fresco/secco attivo/LM), tarato sulle dosi di calcolatori di riferimento
- Calcolatore grammature baker's percentage (con prefermento)
- 5 preset ricette (napoletana / napoletana frigo / teglia / pinsa / pane biga)
- Pianificatore HTMX con grafico Chart.js
- Suggerimenti di cottura per forno domestico o elettrico cielo/platea
- Registro prove: esito reale, voto, note e parametri di cottura, con scarto dalla stima
- Export `.ics` per Calendario iOS
- PWA installabile
- UI con palette rivista + dark mode (auto + toggle), verificata da 320 px a desktop
- Input del form validati lato server
- 53 test unitari verdi

### 🔜 Fase 2 — Il tool completo per il pizzaiolo
- Persistenza ricette con versioning (ORM già pronto)
- UI load/save/elenco ricette (unificare con preset bar)
- **Live Bake mode**: timer mobile per fase corrente + checkpoint
- Diario infornate: upload foto e storico per ricetta (il registro prove base è già disponibile)
- Librerie JS in `static/` per far funzionare davvero l'app offline

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
