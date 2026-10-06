"""Farine predefinite: dati dichiarati dai produttori sulle loro pagine ufficiali (ottobre 2026).

Dove la scheda dà un intervallo, `w` e `pl` sono il valore centrale e l'intervallo sta in `notes`.
Dove il produttore scrive "oltre X%" o "fino a X%", `hydration_min/max` sono la nostra
interpretazione e le parole originali stanno in `hydration_note`. I valori variano da partita a
partita: fa fede l'etichetta del sacco.
"""
from __future__ import annotations

from typing import Any

AP = "https://www.agricolapiano.com/it/eviva-la-farina/"
CAPUTO = "https://www.mulinocaputo.it/prodotti/"
CASILLO = "https://shop.molinocasillo.com/it/"
LOCONTE = "https://clienti.loconteshop.com/prodotto/"
VIGEVANO = "https://molinovigevano.com/prodotto/"
GENERIC_NOTE = "Valori orientativi di categoria, non di una marca: usali solo come punto di partenza."

_BASE_SEEDS: tuple[dict[str, Any], ...] = (
    # Agricola Piano
    dict(brand="Agricola Piano", name="Versatile 240", kind="Tipo 0", w=240, pl=0.65, protein=11.5,
         hydration_min=58, hydration_max=60,
         use="Napoletana classica, teglia a media idratazione, pane e focacce.",
         notes="P/L max 0,65; proteine min 11,5% s.s.; W circa 240 (la descrizione cita 200-240).",
         source_url=AP + "115-129-versatile-240-farina-di-grano-tenero-tipo-0-per-pizza-napoletana-grano-italiano-no-pesticidi-no-additivi-con-germe-8056477660614.html"),
    dict(brand="Agricola Piano", name="Mediterranea", kind="Tipo 0", w=280, pl=0.60, protein=13,
         hydration_min=65, hydration_max=70, hydration_note="oltre il 65%",
         use="Pizza contemporanea, teglia, focacce e pane con lievito madre.",
         notes="W 270-290; P/L max 0,60; proteine min 13% s.s.",
         source_url=AP + "119-139-mediterranea-farina-di-grano-tenero-tipo-0-creata-con-malati-di-pizza-farina-per-pizza-100-naturale-con-germe-8056477660904.html"),
    dict(brand="Agricola Piano", name="Forte 320", kind="Tipo 0", w=355, pl=0.60, protein=13,
         hydration_min=65, hydration_max=70, hydration_note="oltre il 65%",
         use="Pizza contemporanea, pala, teglia, focacce e pani a lunga lievitazione.",
         notes="W 350-360 nella scheda, 300-360 nella descrizione; P/L max 0,60; proteine min 13% s.s.",
         source_url=AP + "116-130-forte-320-farina-di-grano-tenero-tipo-0-farina-per-pizza-farina-italiana-no-pesticidi-senza-additivi-con-germe-8056477660416.html"),
    dict(brand="Agricola Piano", name="Profumata 290", kind="Tipo 1", w=280, pl=0.50, protein=13,
         hydration_min=63, hydration_max=66, hydration_note="63-66%, fino al 68%",
         use="Pizza contemporanea, pala, teglia e pane a lunga lievitazione.",
         notes="W 270-290; P/L 0,45-0,55; proteine min 13% s.s.",
         source_url=AP + "127-155-profumata-290-farina-grano-tenero-tipo-1-forte-farina-per-pizza-100-italiana-no-pesticidi-no-additivi-con-germe-8056477661055.html"),
    dict(brand="Agricola Piano", name="Profumata 240", kind="Tipo 1", w=225, pl=0.50, protein=10.5,
         hydration_min=58, hydration_max=62,
         use="Pane casereccio, pizza classica e focacce con metodo diretto.",
         notes="W 210-240; P/L 0,45-0,55; proteine min 10,5% s.s.",
         source_url=AP + "128-157-profumata-240-farina-di-grano-tenero-tipo-1-farina-per-pane-farina-italiana-no-pesticidi-no-additivi-con-germe-8056477661031.html"),
    dict(brand="Agricola Piano", name="Rustica 260", kind="Tipo 2", w=250, pl=0.35, protein=13,
         hydration_min=70, hydration_max=75, hydration_note="oltre il 70%",
         use="Pizza rustica, teglia, focacce e pane a lievitazione naturale.",
         notes="W 240-260; P/L circa 0,35; proteine min 13% s.s.",
         source_url=AP + "131-164-rustica-260-farina-di-grano-tenero-tipo-2-forte-100-italiana-no-pesticidi-no-additivi-con-germe-di-grano-8056477660621.html"),
    dict(brand="Agricola Piano", name="Rustica 210", kind="Tipo 2", w=195, pl=0.355, protein=10.5,
         hydration_min=66, hydration_max=70,
         use="Pane rustico, pizza tonda o teglia con impasto diretto.",
         notes="W 180-210; P/L 0,33-0,38; proteine min 10,5% s.s.",
         source_url=AP + "138-179-rustica-210-farina-di-grano-tenero-tipo-2-farina-per-pane-grano-italiano-no-pesticidi-senza-additivi-con-germe-8056477660591.html"),
    dict(brand="Agricola Piano", name="Suprema 410", kind="Tipo 0", w=395, pl=0.60, protein=13.5,
         hydration_min=70, hydration_max=75, hydration_note="oltre il 70%; 70-75% con biga",
         use="Grandi lievitati, rinfresco del lievito madre, pizza e pane ad alta idratazione.",
         notes="W 380-410; P/L max 0,60; proteine min 13,5% s.s.",
         source_url=AP + "133-169-suprema-410-farina-tipo-0-per-panettone-pandoro-colomba-e-rinfresco-lievito-madre-senza-additivi-con-germe-di-grano-8056477661161.html"),
    # Molino Caputo
    dict(brand="Molino Caputo", name="Pizzeria", kind="Tipo 00", w=270, pl=0.55, protein=12.5,
         use="Pizza napoletana classica.", notes="W 260-280; P/L 0,50-0,60.",
         source_url=CAPUTO + "pizzeria/"),
    dict(brand="Molino Caputo", name="Nuvola", kind="Tipo 0", w=280, pl=0.55, protein=12.5,
         use="Focaccia, pizza in teglia e contemporanea.", notes="W 270-290; P/L 0,50-0,60.",
         source_url=CAPUTO + "nuvola/"),
    dict(brand="Molino Caputo", name="Aria", kind="Tipo 0", w=310, pl=0.55, protein=13,
         use="Pizza in teglia, pala e pinsa ad alta idratazione.", notes="W 300-320; P/L 0,50-0,60.",
         source_url=CAPUTO + "aria/"),
    dict(brand="Molino Caputo", name="Saccorosso", kind="Tipo 00", w=310, pl=0.55, protein=13,
         use="Impasti da pizzeria con riposi lunghi e lievitazione in frigorifero.",
         notes="W 300-320; P/L 0,50-0,60.", source_url=CAPUTO + "saccorosso/"),
    dict(brand="Molino Caputo", name="Manitoba Oro", kind="Tipo 0", w=370, pl=0.50, protein=14,
         use="Prodotti lievitati strutturati e pasticceria.", notes="W 360-380; P/L 0,45-0,55.",
         source_url=CAPUTO + "manitoba-oro/"),
    dict(brand="Molino Caputo", name="Integrale", kind="Integrale", w=180, pl=0.85, protein=13,
         use="", notes="W 170-190; P/L 0,80-0,90.", source_url=CAPUTO + "integrale/"),
    # Molino Casillo
    dict(brand="Molino Casillo", name="La Pizza", kind="Tipo 00", w=260, protein=12,
         use="Pizza fatta in casa, alta e soffice oppure leggera e croccante.",
         notes="Proteine dal valore nutrizionale (g/100 g).",
         source_url=CASILLO + "farine-e-semole/la-pizza/la-pizza"),
    dict(brand="Molino Casillo", name="Zero M", kind="Tipo 0", w=290, protein=12,
         use="Pizze e focacce a lievitazione media.", notes="Proteine dal valore nutrizionale.",
         source_url=CASILLO + "farine-e-semole-per-professionisti/pizzeria/zero-m"),
    dict(brand="Molino Casillo", name="Zero L", kind="Tipo 0", w=340, protein=12.5,
         use="Pizza ad alta idratazione e lievitazione medio-lunga.",
         notes="Proteine dal valore nutrizionale.",
         source_url=CASILLO + "farine-e-semole-per-professionisti/pizzeria/zero-l"),
    dict(brand="Molino Casillo", name="Zero XL", kind="Tipo 0", w=380, protein=13.5,
         use="Pizza a lunga lievitazione e preparazione di bighe.",
         notes="Proteine dal valore nutrizionale.",
         source_url=CASILLO + "farine-e-semole-per-professionisti/pizzeria/zero-xl"),
    dict(brand="Molino Casillo", name="Origine Pizza Ideale", kind="Tipo 0 con germe", w=290,
         protein=12.5, use="Pizze e focacce a lievitazione media.",
         notes="Proteine dal valore nutrizionale.",
         source_url=CASILLO + "farine-e-semole-per-professionisti/origine/pizza-ideale"),
    # Le Farine Magiche (Lo Conte)
    dict(brand="Le Farine Magiche", name="Farina per Pizza", kind="Mix a base 00 con germe fermentato",
         w=260, protein=12.4, use="Pizza tradizionale, pizzette, calzoni e panuozzi.",
         notes="Proteine dal valore nutrizionale.", source_url=LOCONTE + "pizza/"),
    dict(brand="Le Farine Magiche", name="Manitoba per Salati", kind="Mix a base 0 con germe fermentato",
         protein=15, use="Teglia, pala, pinsa, pane e panini.",
         notes="W non indicato nella pagina consultata. Proteine dal valore nutrizionale.",
         source_url=LOCONTE + "farina-manitoba-per-salati/"),
    dict(brand="Le Farine Magiche", name="Pane e Focaccia", kind="Preparato a base tipo 2",
         protein=11.4, use="Pane, focacce, panini rustici e pizza al taglio.",
         notes="W non indicato; contiene lievito. Proteine dal valore nutrizionale.",
         source_url=LOCONTE + "pane-e-focaccia/"),
    # Molino Vigevano
    dict(brand="Molino Vigevano", name="Pizza in Teglia", kind="Tipo 0 con germe", w=350, protein=14.5,
         hydration_min=70, hydration_max=80, hydration_note="fino all'80%",
         use="Pizza e focaccia in teglia; anche prefermenti.", source_url=VIGEVANO + "pizza-in-teglia/"),
    dict(brand="Molino Vigevano", name="Vesuvio", kind="Tipo 0 con germe", w=290, protein=14.5,
         hydration_min=65, hydration_max=70,
         use="Pizza napoletana contemporanea; anche impasti indiretti.",
         source_url=VIGEVANO + "vesuvio/"),
    dict(brand="Molino Vigevano", name="Tramonti", kind="Tipo 0 con germe", w=345, protein=14.5,
         hydration_min=70, hydration_max=80, hydration_note="fino all'80%",
         use="Pizza tonda, teglia, padellino, pane e focaccia.",
         notes="W 330-360. Proteine 14,5% sul sito, 13,1% nel valore nutrizionale dello shop.",
         source_url=VIGEVANO + "tramonti/"),
    dict(brand="Molino Vigevano", name="Oro Fibra Uno", kind="Tipo 1", w=300, protein=13.2,
         use="Pizza tonda, padellino e pane.", notes="W 290-310.",
         source_url=VIGEVANO + "oro-fibra-uno/"),
    dict(brand="Molino Vigevano", name="aRoma", kind="Mix di tipo 0, riso e semola rimacinata", w=345,
         protein=13.5, hydration_min=85, hydration_max=90, hydration_note="oltre l'85%",
         use="Pinsa, pala romana e pizza in teglia.", notes="W 330-360.",
         source_url=VIGEVANO + "aroma/"),
    # Categorie generiche
    dict(brand="Generica", name="00 per pizza", kind="Tipo 00", w=260, pl=0.55, protein=12,
         hydration_min=58, hydration_max=62, use="Pizza tonda a media idratazione.",
         notes=GENERIC_NOTE),
    dict(brand="Generica", name="0 forte", kind="Tipo 0", w=320, pl=0.55, protein=13.5,
         hydration_min=65, hydration_max=70, use="Teglia, pala e lunghe lievitazioni.",
         notes=GENERIC_NOTE),
    dict(brand="Generica", name="Manitoba", kind="Tipo 0", w=380, pl=0.55, protein=14,
         hydration_min=70, hydration_max=75, use="Da miscelare a farine più deboli; grandi lievitati.",
         notes=GENERIC_NOTE),
    dict(brand="Generica", name="Integrale", kind="Integrale", w=180, pl=0.85, protein=13,
         hydration_min=70, hydration_max=75, use="Da miscelare per sapore e fibre.",
         notes=GENERIC_NOTE),
)

# (produttore, nome) -> (impasto, parole del produttore). L'impasto è "diretto" o "indiretto" solo
# se la scheda dice "esclusivamente"; se ammette entrambi è "entrambi"; se cita solo un uso, resta vuoto.
_METHODS: dict[tuple[str, str], tuple[str, str]] = {
    ("Agricola Piano", "Versatile 240"): ("diretto", "Metodo: impasto diretto"),
    ("Agricola Piano", "Mediterranea"): (
        "entrambi", "Permette di lavorare sia con impasti diretti sia indiretti"),
    ("Agricola Piano", "Forte 320"): (
        "entrambi", "Diretto (anche con breve autolisi) o indiretto con biga/poolish"),
    ("Agricola Piano", "Profumata 290"): (
        "entrambi", "Diretto (disciplinare pizza verace napoletana) o indiretto con biga e poolish"),
    ("Agricola Piano", "Profumata 240"): ("diretto", "Metodo: esclusivamente diretto"),
    ("Agricola Piano", "Rustica 260"): (
        "entrambi", "Diretto con autolisi 30-60 minuti; possibile poolish a breve maturazione"),
    ("Agricola Piano", "Rustica 210"): (
        "diretto", "Esclusivamente diretto, con riposo/autolisi iniziale"),
    ("Agricola Piano", "Suprema 410"): (
        "entrambi", "Diretto ad alta idratazione, indiretto con biga o poolish, lievito madre"),
    ("Molino Vigevano", "Vesuvio"): ("entrambi", "Adatta anche a impasti indiretti"),
    ("Molino Vigevano", "Pizza in Teglia"): ("entrambi", "Adatta anche a prefermenti"),
    ("Molino Casillo", "Zero XL"): ("", "Ottima per lunghe lievitazioni e per la preparazione di bighe"),
}

FLOUR_SEEDS: tuple[dict[str, Any], ...] = tuple(
    {
        **seed,
        **dict(zip(("method", "method_note"), _METHODS.get((seed["brand"], seed["name"]), ("", "")), strict=True)),
    }
    for seed in _BASE_SEEDS
)
