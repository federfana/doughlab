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
- **Ricette base**: 5 preset caricabili con un click, con un orientamento sulla farina. Per la teglia c'è un piccolo calcolatore: *lato × lato ÷ 2* = grammi di impasto (30 × 40 cm ≈ 600 g) e un pulsante per usarlo come peso del panetto.
- **Suggerimenti di cottura**: in sola lettura, per forno domestico o elettrico con cielo e platea indipendenti. Non influenzano la maturazione.
- **Diario**: ogni prova ha nome, data, formula, forno, voto a stelle (mezze stelle: tocca la metà sinistra di una stella; ritocca lo stesso valore per toglierlo), note, "da cambiare" e fino a 5 foto. Può nascere da un piano (pulsante *Salva questa prova nel diario*, che precompila ingredienti, fasi e forno) e, con gli orari reali, mostra la partenza e il pronto stimati, quelli reali e lo scarto tra le DURATE (non tra le date: se il piano partiva un altro giorno il confronto resta valido).
- **Ricette salvate**: formula, fasi, lievito e forno si salvano con un nome (*Le mie ricette*); salvare di nuovo con lo stesso nome crea una nuova versione, e ogni versione si può riaprire. Le prove del diario nate da una ricetta salvata restano collegate e si filtrano per ricetta.
- **In corso (Live Bake)**: *Avvia in cucina* segue le fasi in tempo reale con timer, avanzamento manuale, ±15 min, controlli per fase, temperatura misurata, avviso a fine fase e schermo acceso. Lo stato resta nel browser (sopravvive a ricarica e chiusura) e a fine impasto precompila il diario con gli orari reali.
- **Ricerca nel Diario** per nome, tipo, note, forno.
- **Farine**: un archivio con W, P/L, proteine e idratazione consigliata, già carico con le farine di Agricola Piano, Caputo, Casillo, Le Farine Magiche, Vigevano (dati dichiarati dai produttori) e alcune categorie generiche. Nel piano scegli una farina o una miscela (fino a 3): vedi W, P/L e proteine medi, i grammi per farina e l'**idratazione consigliata** (dal produttore, oppure stimata dalla forza W) confrontata con la tua, con un pulsante per adottarla. Ogni farina dice se è indicata per impasti **diretti o indiretti** (come sulle schede di Agricola Piano) e il piano avvisa se una farina "solo diretta" incontra un prefermento, o viceversa. La miscela passa a Diario (farina, W, proteine) e ricette salvate.
- **Backup**: importa ed esporta il Diario in JSON con le foto (formato compatibile con il backup di [Pizza Lab](https://pizzalab.sibellutu.com/)). L'importazione è ripetibile: le voci già presenti non si duplicano e non sovrascrivono modifiche locali più recenti.
- **Export `.ics`** per il Calendario, **PWA** installabile e tema chiaro/scuro. Le librerie JS sono locali (`static/vendor/`): su `localhost` o in HTTPS, dopo la prima visita, l'app si apre e funziona anche offline, tranne le operazioni che passano dal server.

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

> **Contesto sicuro**: service worker (uso offline), Wake Lock (schermo acceso nel tab *In corso*) e notifiche funzionano solo su `localhost` o in HTTPS, non su `http://<IP-del-Mac>:8000`. Dal telefono in LAN il timer del Live Bake funziona, ma lo schermo può spegnersi e non ci sono notifiche: vibrazione e avvisi a schermo restano.

> **Sicurezza**: l'app non ha autenticazione né protezione CSRF, pensata per una rete domestica fidata. Non esporla su Internet senza metterle davanti un proxy con login e HTTPS.

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
│   ├── models.py                  # ORM: Recipe, RecipeVersion, DiaryEntry, DiaryPhoto
│   ├── web.py                     # template Jinja e contesto comune
│   ├── main.py                    # FastAPI app: pianificatore, /plan, /plan.ics
│   ├── planning.py                # dal form al piano: parsing, preset, calcolo
│   ├── recipes.py                 # router ricette salvate con versioning
│   ├── flours.py                  # router farine, seed, miscela del piano
│   ├── diary.py                   # router del Diario: CRUD, foto, ricerca, import/export
│   ├── services/
│   │   ├── thermal.py             # modello di Newton (τ per profilo)
│   │   ├── fermentation.py        # modello Q10 del lievito
│   │   ├── ingredients.py         # calcolo baker's percentage
│   │   ├── presets.py             # ricette predefinite
│   │   ├── fields.py              # lettura difensiva di numeri, testi, date
│   │   ├── flour_blend.py         # medie pesate della miscela e idratazione consigliata
│   │   ├── flour_seed.py          # farine predefinite con fonte
│   │   ├── images.py              # controllo del tipo di immagine dai primi byte
│   │   ├── backup.py              # parsing/scrittura del backup JSON del Diario
│   │   └── scheduler.py           # orchestra tutto in un PlanResult
│   ├── templates/
│   │   ├── base.html              # layout, CSS con variabili, tema chiaro/scuro
│   │   ├── planner.html           # tab Pianifica + In corso + Diario + Farine (HTMX, Alpine)
│   │   └── partials/
│   │       ├── plan_result.html   # fragment di /plan: ingredienti, riepilogo, grafico, timeline
│   │       ├── recipes_panel.html # Le mie ricette: salvataggio, elenco, versioni
│   │       ├── flours_panel.html  # tab Farine: elenco per produttore, modulo
│   │       ├── flour_optgroups.html # opzioni del selettore farine (anche fuori banda)
│   │       ├── diary_panel.html   # Diario: barra, messaggi, import, elenco
│   │       ├── diary_form.html    # modulo di una prova (con foto)
│   │       └── diary_entry.html   # scheda di una prova
│   └── static/
│       ├── manifest.webmanifest   # PWA
│       ├── sw.js                  # service worker (precache shell + librerie)
│       ├── vendor/                # Alpine, HTMX, Chart.js (versioni fissate)
│       └── icons/                 # icone PWA
└── tests/
    ├── test_thermal.py            # proprietà di Newton
    ├── test_fermentation.py       # proprietà di Q10 e taratura della dose
    ├── test_ingredients.py        # baker's percentage e prefermento
    ├── test_scheduler.py          # end-to-end del piano
    ├── test_backup.py             # parsing/export dei backup, immagini
    ├── test_diary.py              # rotte del Diario su SQLite temporaneo
    ├── test_recipes.py            # ricette salvate, versioni, collegamento al Diario
    ├── test_flours.py             # farine, miscele, idratazione, rotte
    └── test_main.py               # form, template, .ics
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
│ db.py       │  (diario prove; ricette: futuro)
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
7. Rende `partials/plan_result.html` (ingredienti, riepilogo, grafico, timeline) con il pulsante che apre il Diario precompilato (`POST /diario/da-piano`).

Il frontend invia la richiesta via **HTMX** `hx-post` quando modifichi un campo (`input` dopo 450 ms, `change` dopo 200 ms), quindi la UI è "live". Il cambio del profilo forno non ricalcola: aggiorna solo i suggerimenti di cottura.

---

## I modelli scientifici

### 1. Modello termico — Newton

Equazione fondamentale:

$$\frac{dT}{dt} = -\frac{T - T_{\text{amb}}}{\tau}$$

Soluzione esatta su un segmento ad ambient costante:

$$T(t + \Delta t) = T_{\text{amb}} + (T(t) - T_{\text{amb}}) \cdot e^{-\Delta t / \tau}$$

**τ (costante di tempo)** = tempo per percorrere il 63% della strada verso l'ambiente. Dipende da massa, superficie, mezzo. Noi usiamo una tabella `(Container × Environment) → τ` con 16 combinazioni in [services/thermal.py](src/doughlab/services/thermal.py).

I profili del modello, con ciò che offre l'interfaccia (colonna *UI*):

| Container | Significato | UI |
|---|---|---|
| `MASS_BOWL` | massa in ciotola (puntata) | 🥣 Massa in ciotola |
| `BALLS_BOX` | panetti stagliati in cassetta | 📦 Panetti in cassetta |
| `MASS_BOX` | massa in cassetta coperta | ritirato: diventa `MASS_BOWL` |
| `BALLS_SINGLE` | panetto singolo esposto | ritirato: diventa `BALLS_BOX` |

| Environment | Significato | UI |
|---|---|---|
| `AMBIENT` | casa | 🏠 TA · Casa |
| `FRIDGE_HOME` | frigo domestico | ❄️ TC · Frigo |
| `CHAMBER` | cella di lievitazione | 🌡️ TC · Cella |
| `FRIDGE_BOX` | cassetta chiusa in frigo | ritirato: diventa `FRIDGE_HOME` |

I valori ritirati restano nel modello e nella tabella τ (i test li usano), ma il form non li offre più: `parse_container`/`parse_environment` in `services/thermal.py` li convertono nel profilo più simile quando arrivano da un form o da una ricetta salvata. I preset usano solo i valori offerti: passando da `MASS_BOX` a `MASS_BOWL` la dose di lievito suggerita per i preset con maturazione in frigo è salita di circa il 2% (es. teglia 0.190% → 0.195%).

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
- `init_db()`: `create_all()` idempotente più `_add_missing_columns`, chiamato dal `lifespan` di FastAPI. Aggiunge con `ALTER TABLE` le colonne dei modelli che mancano nelle tabelle già esistenti (le righe esistenti restano) e restituisce l'insieme `(tabella, colonna)` aggiunto, che `main.py` usa per riempire i dati nuovi delle farine predefinite. Una colonna `NOT NULL` nuova deve avere un default semplice, altrimenti parte un errore chiaro. Non gestisce rinomine, cancellazioni, cambi di tipo, indici e vincoli: per quelli serve una migrazione vera.

### [models.py](src/doughlab/models.py)

Cinque modelli ORM:

- **`Recipe`**: metadati della ricetta (nome, stile, note).
- **`RecipeVersion`**: ogni modifica è una nuova riga → **ricettario versionato**. Payload JSON contiene fasi/ingredienti/parametri, utile come MVP prima di normalizzare lo schema.
- **`DiaryEntry`**: una prova del diario. Colonne per i campi del backup (nome, data, tipo, forno, farina, idratazione, ore frigo/ambiente, panetti, temperature, voto 0.5-5, ingredienti, procedimento, note, "da cambiare", etichette), più `started_at`/`ready_at` reali, `plan` (snapshot JSON del piano di origine, se c'è) ed `extra` (chiavi di backup sconosciute, restituite nell'export). `external_id` (uuid o id del backup) rende l'importazione ripetibile.
- **`Flour`**: una farina (produttore, nome, tipo, `w`, `pl`, `protein`, `hydration_min/max`, `hydration_note`, `method` (diretto / indiretto / entrambi / vuoto), `method_note`, uso, note, `source_url`, `builtin`). Unica per coppia produttore+nome. Alla prima apertura (tabella vuota) viene caricata da `services/flour_seed.py`; poi le tue modifiche e cancellazioni restano tue, e *Ripristina predefinite* aggiunge solo quelle mancanti.
- **`DiaryPhoto`**: fino a 5 foto per voce (`main`, `extra1`..`extra4`), binario `deferred` (si legge solo quando serve una foto o l'export), con didascalia e inquadratura.

> `Recipe` e `RecipeVersion` esistono ma non sono ancora usati: arriveranno con la persistenza ricette (fase 2). La vecchia tabella `bakes` non viene più usata (era vuota) e non viene eliminata dal database.

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

I suggerimenti per napoletana e teglia sono orientativi e non modificabili nel pianificatore; nel Diario si annotano i parametri effettivamente usati. Gli intervalli riportati seguono la [guida Macte sulle temperature](https://macteovens.com/blogs/ricette-consigli/temperatura-forno-pizza-quanti-gradi-per-ogni-tipo-da-napoletana-a-teglia). Il profilo a resistenze separate mostra setpoint distinti per cielo e platea fino a 510 °C; verifica sempre i limiti del tuo forno. Per pinsa e pane, senza un riferimento univoco, i setpoint restano da calibrare.

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
| `GET` | `/` | pagina `planner.html` con tab Pianifica/In corso/Diario/Farine e primo preset |
| `GET` | `/?preset=<key>&yeast=<kind>&oven=<profile>` | carica preset mantenendo lievito e profilo forno |
| `GET` | `/?recipe=<id>&version=<n>` | carica una ricetta salvata (ultima versione se `version` manca) |
| `POST` | `/plan` | ritorna il **fragment HTML** `plan_result.html` (HTMX swap) |
| `POST` | `/diario/da-piano` | apre il modulo del Diario precompilato con il piano corrente |
| `POST` | `/plan.ics` | ritorna il piano come file `.ics` da aprire in Calendario (orari in ora locale del server) |
| `GET` | `/static/*` | asset statici (PWA, icone, SW) |

`main.py` contiene solo le rotte; i calcoli del form vivono in `planning.py`.

### [planning.py](src/doughlab/planning.py)

- `number(data, key, default, low, high)` → numero finito dentro i limiti, altrimenti il default (nessun `inf`/`NaN` arriva ai servizi)
- `parse_phase_form(data)` → legge campi index-based `phase_kind_0`, `phase_hours_0`, ... (max 30 fasi, durata ≤ 720 h)
- `parse_ingredients(data)` → estrae grammature e percentuali dal form, con gli stessi limiti degli input HTML
- `baking_advice(preset, oven_profile)` → suggerimento di cottura per il profilo `home` o `split`
- `default_recipe_ctx()` / `preset_ctx(key)` → struttura dati per il template
- `compute_plan_and_ingredients(data)` → pacchetto unificato per `/plan`, `/plan.ics` e `/diario/da-piano`; `plan_snapshot` riassume piano, grammature, fasi, cottura e ricetta di origine (`recipe_id`, `recipe_version`)

### [recipes.py](src/doughlab/recipes.py)

Router `/ricette` (risposte HTML di `partials/recipes_panel.html`).

| Metodo | Path | Scopo |
|---|---|---|
| `POST` | `/ricette` | salva la ricetta del form con `save_name` (e `save_message` facoltativo): nome nuovo = v1, nome esistente = nuova versione |
| `POST` | `/ricette/{id}/elimina` | elimina ricetta e versioni (le prove del diario restano) |

`payload_from_form` salva ciò che definisce la ricetta (formula, fasi, lievito, `target_work`, forno, T° iniziale) e non l'orario di partenza. `load_recipe(id, version)` ricostruisce il contesto del pianificatore a partire dal preset di origine; un payload illeggibile viene ignorato. Dopo un salvataggio, il pannello aggiorna i campi nascosti `recipe_id`/`recipe_version` del piano con `hx-swap-oob`.

### [flours.py](src/doughlab/flours.py)

Router `/farine` (risposte HTML di `partials/flours_panel.html`).

| Metodo | Path | Scopo |
|---|---|---|
| `GET` | `/farine?q=<testo>`, `/farine/nuova`, `/farine/{id}/modifica` | elenco raggruppato per produttore con ricerca, modulo vuoto, modulo di modifica |
| `POST` | `/farine`, `/farine/{id}` | crea o modifica (nome obbligatorio; idratazione min e max insieme o nessuna; produttore+nome unici) |
| `POST` | `/farine/{id}/elimina` | elimina (ricette e prove già salvate restano) |
| `POST` | `/farine/ripristina` | aggiunge le farine predefinite mancanti |

`blend_context(data, hydration)` legge `flour_id_N`/`flour_pct_N` dal form del piano (max 3, percentuali normalizzate a 100) e restituisce la miscela; `snapshot_extras` aggiunge allo snapshot `flours`, `flour_label`, `flour_w`, `flour_protein`, che il Diario usa per precompilare farina, W e proteine.

### [services/flour_blend.py](src/doughlab/services/flour_blend.py)

Funzioni pure. W, P/L e proteine della miscela sono **medie pesate** sulle sole farine che hanno il dato (per la W è una stima: non è davvero lineare). L'idratazione consigliata è la media pesata degli intervalli del produttore; se manca, `estimate_hydration(w)` la ricava dalla forza (W 240 → 58-62%, 290 → 63-68%, 340 → 66-72%, oltre 380 → 70-78%, coerente con le schede dei produttori ma pur sempre una regola empirica non tarata). `basis` dice se l'indicazione è del produttore, stimata o mista; `hydration_position` confronta con la tua idratazione (mezzo punto di tolleranza).

Dati predefiniti: dove il produttore scrive "oltre il 65%" o "fino all'80%", gli estremi numerici sono una nostra interpretazione e le sue parole stanno in `hydration_note`; gli intervalli di W stanno in `notes` e `w` è il valore centrale. Le ceneri (il residuo minerale dopo la combustione, indice di quanto la farina è raffinata) non sono gestite.

### [diary.py](src/doughlab/diary.py)

Router `/diario`. Tutte le rotte restituiscono il pannello `partials/diary_panel.html` (HTMX lo sostituisce intero), tranne foto ed export.

| Metodo | Path | Scopo |
|---|---|---|
| `GET` | `/diario?q=<testo>&recipe=<id>`, `/diario/nuova`, `/diario/{id}/modifica` | elenco con ricerca e filtro per ricetta, modulo vuoto, modulo di modifica |
| `POST` | `/diario`, `/diario/{id}` | crea o modifica (multipart: campi + `photo_<slot>`, `label_<slot>`, `remove_<slot>`) |
| `POST` | `/diario/{id}/elimina` | elimina voce e foto |
| `GET` | `/diario/foto/{id}` | serve la foto (`nosniff`, cache privata; l'URL include una versione) |
| `POST` | `/diario/importa` | importa un backup JSON (max 100 MB) e mostra il resoconto |
| `GET` | `/diario/export.json` | scarica il backup completo con le foto |

Sicurezza e robustezza: il tipo dell'immagine è deciso dai primi byte (solo JPEG/PNG/WebP, max 12 MB), i testi hanno lunghezza massima, i numeri vengono validati e limitati (nessun `inf`/`NaN`), tutto passa dall'autoescape di Jinja. Se `ready_at` precede `started_at` il modulo resta aperto con l'errore in evidenza e i valori digitati.

### [services/backup.py](src/doughlab/services/backup.py)

`parse_backup(raw)` legge `{"entries": [...]}` (valori sempre stringa) in `DiaryData`; `build_backup(entries)` fa il percorso inverso. Le foto sono data URL base64 negli slot `photos.main/extra1..4`, con `photoLabels` e `photoSettings`. Le chiavi sconosciute vengono conservate in `extra`; DoughLab aggiunge un blocco `doughlab` (piano e orari reali) che le altre app ignorano. L'importazione abbina le voci per `id`: se la voce esiste viene aggiornata solo quando `updatedAt` del file è più recente.

### [templates/](src/doughlab/templates/)

- **`base.html`**: layout minimale con variabili CSS semantiche (`--bg`, `--surface`, `--ac`…), dark mode automatica (preferenza di sistema) + toggle manuale persistente in `localStorage`. Alpine.js, HTMX e Chart.js sono serviti da `static/vendor/`. Niente Node, niente build step. Il testo secondario (`--mut`) rispetta il contrasto AA in entrambi i temi.
- **`planner.html`**: una tab bar nella stessa pagina separa **Pianifica**, **In corso**, **Diario** e **Farine**. La scheda Piano contiene input base, ricetta, fasi e suggerimenti di cottura in sola lettura, selezionabili per forno domestico o elettrico con cielo e platea. I parametri reali si annotano nel Diario e non influenzano la maturazione. `compressPhotoInput` riduce le foto a 1600 px (JPEG) nel browser prima del caricamento.
  **Live Bake** (tab *In corso*, tutto lato client in `plannerUI`): *Avvia in cucina* legge il piano da `#liveData` e salva lo stato in `localStorage['dl-live']` (orari reali di inizio fase, minuti aggiunti/tolti, controlli spuntati, T° misurata). La fase corrente è l'ultima con un orario reale; il timer conta alla scadenza prevista e, se superata, va in negativo. Alla scadenza scattano vibrazione e notifica (solo se la pagina è aperta), e la Wake Lock API tiene acceso lo schermo. Il "pronto" reale è l'inizio della prima fase di cottura (o la fine dell'ultima fase). *Salva nel diario* chiama `/diario/da-piano` con l'orario di partenza reale, quindi compila `started_at`, `ready_at` e `dough_temp`.
- **`partials/plan_result.html`**: HTMX aggiorna ingredienti e riepilogo in `#result`, grafico e timeline in `#detailsResult`, e offre il pulsante per salvare la prova nel Diario. Il grafico ha altezza responsive fissa (`.chart-wrap`), nasconde i titoli degli assi sotto i 560 px, legge i colori dalle variabili CSS e si ridisegna al cambio tema; l'asse X è il tempo trascorso in ore.
- **`partials/flours_panel.html`**: elenco per produttore (con scheda del produttore, in nuova scheda), ricerca, modulo; vive nel tab *Farine*, fuori da `#planForm`. Ogni risposta include fuori banda (`hx-swap-oob`) `#flourOptionsSource`, la copia delle opzioni: un listener `htmx:oobAfterSwap` in `planner.html` rigenera i selettori del piano tenendo la scelta se la farina esiste ancora. Nel pianificatore, la sezione *Farina* ha tre righe farina+percentuale e il blocco *Farina* del risultato mostra miscela, statistiche e idratazione consigliata (pulsante `useHydration`).
- **`partials/recipes_panel.html`**: salvataggio con nome, elenco ricette con versioni, prove collegate; sta fuori da `#planForm` per non innescare ricalcoli.
- **`partials/diary_panel.html`, `diary_form.html`, `diary_entry.html`**: barra (nuova prova, esporta), importazione, modulo a sezioni (prova, impasto, cottura, note, foto) ed elenco di schede con miniatura, voto a stelle (`starRating()` in `planner.html`, valore nel campo nascosto `rating`; sulla scheda `.stars-static` riempito via `--fill`), dati chiave e confronto stima/reale.

Nota UX: nel form le percentuali sono inserite in formato umano (`62`, `2.8`) e convertite server-side in frazioni per i calcoli. I decimali si possono digitare liberamente: i campi numerici usano `step="any"` perché un valore non multiplo dello step rende il form non valido e HTMX non ricalcola. Le frecce di idratazione, sale, prefermento e peso panetto (±5 g) sono pulsanti custom (`adjustPercent`). La durata di ogni fase si digita in **ore e minuti** (due campi; il campo nascosto `phase_hours_N` porta al server ore decimali, quindi l'API non cambia) e ovunque viene mostrata come `1 h 30 min`, `45 min` o `1 min 15 s` con i filtri Jinja `hours` e `minutes` (`format_hours`/`format_minutes` in `services/fields.py`): niente più `0.5 h` o `1.25 min`. Il lievito non è un input: la percentuale suggerita dall'app determina anche i grammi mostrati. Giorni e mesi nel risultato sono localizzati in italiano.

### [static/](src/doughlab/static/)

- **`manifest.webmanifest`**: nome, colori, icone 192/512 → "installabile" come PWA.
- **`sw.js`**: service worker minimale, cache-first solo per `/static/*` (le richieste dinamiche di HTMX, foto ed export non passano mai dalla cache, altrimenti diario e ricette risulterebbero vecchi), network-first per le pagine HTML. Precarica pagina iniziale, manifest e le tre librerie di `static/vendor/` (versioni fissate nel nome del file; cambiando versione si aggiorna anche `CACHE` in `sw.js`) e salva l'ultima pagina vista. Offline l'app si apre ed è interattiva; calcolo del piano, diario e ricette richiedono comunque il server.
- **`icons/*.png`**: placeholder generati con Python puro (zlib). Da sostituire con grafica vera.

---

## Testing

124 test (al 2026-10-06). Lanciali con `uv run pytest`.

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
| `test_default_plan_starts_now_not_tomorrow` | l'inizio predefinito del piano è adesso, non il giorno dopo |
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
| `test_cooking_advice_is_not_overridden_by_planner_form` | il planner mantiene i suggerimenti del preset |
| `test_split_oven_profile_keeps_preset_platea_and_ceiling_advice` | i suggerimenti cielo/platea restano quelli del preset |
| `test_teglia_preset_shows_split_oven_cielo_and_platea_advice` | il preset teglia mostra setpoint separati e hint di cottura |
| `test_hostile_form_values_never_hang_or_produce_non_finite_plans` | inf/NaN, ore enormi o negative, date ed enum non validi non bloccano né producono piani non finiti |
| `test_phase_count_is_capped` | il server accetta al massimo 30 fasi |
| `test_ics_export_uses_local_time_not_utc` | l'export `.ics` non sposta gli orari di fuso |
| `test_durations_are_shown_in_hours_and_minutes_never_decimals` | `format_minutes`/`format_hours` danno `30 s`, `1 min 15 s`, `1 h 30 min`... |
| `test_phase_duration_is_typed_as_hours_and_minutes_but_posted_as_decimal_hours` | i campi ore/minuti convivono con il campo nascosto in ore decimali |
| `test_form_offers_only_casa_frigo_cella_and_ciotola_cassetta_with_icons` | il form offre solo Casa/Frigo/Cella e Ciotola/Cassetta, con icone |
| `test_presets_only_use_offered_containers_and_environments` | i preset non usano valori ritirati |
| `test_teglia_preset_suggests_tray_formula_and_other_presets_do_not` | il calcolatore della teglia compare solo per la teglia |
| `test_stesura_phases_use_the_dough_ball_profile_not_the_bowl` | la Stesura di teglia e pinsa usa il profilo dei panetti in cassetta (superficie alta, risposta rapida) |
| `test_retired_container_and_environment_values_map_to_the_closest_offered_one` | `mass_box`/`fridge_box` da un form diventano `mass_bowl`/`fridge_home` |
| `test_planner_numeric_inputs_accept_any_value_so_the_form_stays_valid` | nessun campo numerico del pianificatore ha uno `step` vincolante (un valore "non valido" per il browser blocca il ricalcolo HTMX) |
| `test_panetto_weight_is_not_rounded_to_multiples_of_ten` | 265 g si calcola come 265 g |

### [tests/test_backup.py](tests/test_backup.py)

| Test | Proprietà verificata |
|---|---|
| `test_strings_become_numbers_and_text` | le stringhe del backup diventano numeri, date, testi e foto |
| `test_hostile_or_empty_values_are_neutralised` | NaN, infiniti, date e foto non valide non rompono l'importazione |
| `test_invalid_photos_produce_warnings` | le foto illeggibili vengono segnalate |
| `test_non_backup_files_are_rejected` | file che non sono backup danno un errore chiaro |
| `test_round_trip_keeps_everything` | export + reimport non perdono campi, chiavi sconosciute, foto |
| `test_entries_without_id_get_unique_ids` | le voci senza id ne ricevono uno univoco |
| `test_rating_is_rounded_to_half_points` | il voto è a mezzi punti, 0 significa nessun voto |
| `test_image_type_is_decided_by_content_not_by_declared_type` | SVG/HTML travestiti da JPEG vengono rifiutati |

### [tests/test_diary.py](tests/test_diary.py)

| Test | Proprietà verificata |
|---|---|
| `test_entry_with_photo_is_saved_and_photo_is_served` | salvataggio con foto, escape dell'HTML, header della foto |
| `test_ready_before_start_shows_visible_error_and_keeps_values` | l'errore sugli orari è in evidenza e il modulo conserva i valori |
| `test_only_start_without_ready_time_is_accepted` | un piano futuro senza orario reale si salva |
| `test_non_image_upload_is_rejected` | un file non immagine non viene salvato |
| `test_update_replaces_and_removes_photos_then_delete` | modifica, sostituzione/rimozione foto, eliminazione a cascata |
| `test_import_is_idempotent_and_never_overwrites_newer_local_edits` | reimportare non duplica né sovrascrive modifiche locali più recenti |
| `test_export_then_import_into_empty_diary_is_lossless` | export e reimport in un diario vuoto non perdono nulla |
| `test_import_rejects_non_backup_files` | file non validi o assenti danno un messaggio |
| `test_plan_prefills_new_diary_entry` | il piano precompila la voce e viene conservato |
| `test_diary_shows_prediction_error_for_linked_plan` | confronto stima/reale nella scheda |
| `test_comparison_uses_durations_so_a_wrong_plan_date_does_not_skew_it` | con partenza del piano nota lo scarto è tra durata stimata e reale, non tra date; la scheda mostra entrambi gli intervalli |
| `test_form_shows_the_planned_start_of_a_linked_plan` | il modulo mostra la partenza prevista del piano collegato |
| `test_rating_is_a_star_widget_and_entries_show_stars_not_numbers` | il modulo usa il widget a stelle, le schede mostrano stelle riempite in proporzione (solo se c'è un voto) e la modifica riapre il valore |
| `test_hostile_rating_value_cannot_reach_javascript` | un voto malevolo non finisce mai nel JavaScript del modulo |
| `test_out_of_range_ids_are_rejected_not_crashing` | id enormi danno 422, non 500 (overflow SQLite) |
| `test_service_worker_never_caches_dynamic_responses` | il service worker mette in cache solo `/static/*` e pagine HTML |

### [tests/test_db.py](tests/test_db.py)

| Test | Proprietà verificata |
|---|---|
| `test_missing_columns_are_added_with_defaults_and_old_rows_survive` | le colonne nuove vengono aggiunte con default e le righe esistenti restano |
| `test_nothing_to_add_returns_empty_set` | senza differenze non cambia nulla |
| `test_new_not_null_column_without_a_simple_default_is_refused` | una colonna `NOT NULL` senza default semplice viene rifiutata con un errore chiaro |

### [tests/test_flours.py](tests/test_flours.py)

| Test | Proprietà verificata |
|---|---|
| `test_blend_uses_weighted_averages_and_normalises_percentages` | W e proteine sono medie pesate; percentuali che non fanno 100 vengono normalizzate |
| `test_missing_values_are_averaged_only_over_the_flours_that_have_them` | un dato mancante non abbassa la media |
| `test_hydration_advice_prefers_producer_data_and_falls_back_to_w` | produttore, stima dalla W o mista; nessun dato = nessun consiglio |
| `test_estimated_hydration_grows_with_flour_strength` | più W, più idratazione stimata |
| `test_hydration_position_has_half_point_tolerance` | sotto / dentro / sopra l'intervallo |
| `test_rows_ignore_invalid_duplicate_and_excess_entries` | righe non valide, doppie o enormi ignorate |
| `test_builtin_data_is_consistent_and_covers_the_requested_producers` | dati predefiniti coerenti, con fonte, per i produttori richiesti |
| `test_seed_runs_once_and_restore_adds_only_missing_ones` | il seed parte a tabella vuota; *Ripristina* aggiunge solo le mancanti |
| `test_flour_crud_validation_and_search` | creazione, modifica, eliminazione, validazioni, duplicati, ricerca, escape |
| `test_plan_shows_blend_stats_and_hydration_advice` | il piano mostra miscela, W e consiglio sull'idratazione |
| `test_blend_prefills_diary_and_is_saved_with_the_recipe` | la miscela precompila il Diario e si riapre con la ricetta |
| `test_planner_lists_flours_in_a_selector_and_has_the_manager` | selettore per produttore e tab Farine con il pannello |
| `test_flour_changes_refresh_the_planner_options_out_of_band` | ogni modifica rimanda le opzioni del selettore del piano |
| `test_method_warnings_only_for_exclusive_declarations` | avvisi solo per "solo diretto" con prefermento o "solo indiretto" senza |
| `test_agricola_piano_flours_all_declare_direct_or_indirect_use` | tutte le farine Agricola Piano hanno l'impasto dichiarato |
| `test_flour_form_saves_method_and_ignores_unknown_values` | il modulo salva l'impasto e ignora valori sconosciuti |
| `test_plan_warns_when_exclusive_direct_flour_meets_a_preferment` | il piano avvisa quando una farina solo diretta incontra un prefermento |
| `test_backfill_fills_builtin_methods_without_overwriting_user_data` | il riempimento dopo la migrazione non tocca i dati dell'utente |

### [tests/test_recipes.py](tests/test_recipes.py)

| Test | Proprietà verificata |
|---|---|
| `test_saving_same_name_creates_new_version_and_old_one_can_be_opened` | stesso nome = nuova versione; `?recipe=` apre l'ultima, `&version=` una precedente |
| `test_save_requires_name_and_ignores_missing_recipe` | nome vuoto rifiutato; id inesistenti o non numerici non rompono la pagina |
| `test_recipe_name_is_escaped_and_delete_removes_versions` | nomi ostili escapati; l'eliminazione rimuove anche le versioni |
| `test_diary_entry_keeps_recipe_link_and_can_be_filtered` | collegamento ricetta-prova, filtro per ricetta e ricerca testuale |
| `test_plan_snapshot_carries_recipe_link` | lo snapshot del piano porta `recipe_id`/`recipe_version` |
| `test_saved_recipe_with_retired_container_opens_with_the_closest_offered_one` | una ricetta salvata con valori ritirati si riapre con quelli più simili |

---

## Convenzioni di sviluppo

- **Formattazione**: `ruff` fa sia linting che format (`line-length=100`, target `py312`).
- **Type checking**: `mypy` in modalità `strict`.
- **Import style**: ordinati da ruff (regola `I`); si importa SEMPRE con nomi relativi dentro `doughlab/`.
- **Dataclass vs Pydantic**: Pydantic solo ai confini (settings, schema API). Dentro i servizi, `dataclass` semplici per minimo overhead.
- **Numpy ovunque**: le curve termiche/fermentazione viaggiano come `np.ndarray`. Nel template, `.tolist()` per Chart.js.
- **Nessun bundler**: HTMX, Alpine.js e Chart.js copiati in `static/vendor/`, CSS scritto a mano con variabili. Niente Node, niente webpack, niente step di build.
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
- Diario prove con foto, voto, note, orari reali e scarto dalla stima
- Importazione/esportazione del backup del Diario (foto incluse, compatibile con Pizza Lab)
- Export `.ics` per Calendario iOS
- PWA installabile
- UI con palette rivista + dark mode (auto + toggle), verificata da 320 px a desktop
- Input del form validati lato server
- 124 test unitari verdi

### ✅ Fase 2 (fatta)
- Ricette salvate con versioning, riapribili e collegate alle prove del Diario
- Live Bake: timer per fase, controlli, orari reali che precompilano il diario
- Ricerca nel Diario e filtro per ricetta
- Database farine con miscele e idratazione consigliata
- Librerie JS in `static/vendor/`: offline su `localhost`/HTTPS (su HTTP in LAN il browser non attiva il service worker)

### 🔜 Prossimi passi
- Confrontare le prove di una ricetta (scarto medio stima/reale) e usarlo per tarare `target_work`
- Migrazioni vere (rinomine, cambi di tipo, vincoli): oggi si aggiungono solo colonne nuove
- Notifiche di fine fase anche a pagina chiusa (richiede Web Push/server)

### 🔮 Fase 3 — Analisi
- Analisi alveolatura via OpenCV (contorni bolle, uniformità, densità)
- Suggerimenti correlati ai log passati

### 🧪 Fase 4 — Avanzata
- Fork/diff visuale delle ricette (git-like)
- Starter / LM tracker (rinfreschi, raddoppio)
- Calibrazione automatica τ e Q10 sui log reali con `scipy.optimize`
- Integrazione termometro BLE
- (Opzionale) ESP32 + termocoppia per logging forno
