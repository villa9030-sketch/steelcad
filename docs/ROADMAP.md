# SteelCAD — Roadmap

Ogni milestone è un **gate**: non si passa alla successiva finché il suo
flusso non è robusto e coperto da test automatici.

## Milestone 0 — Progetto (fatta)
ARCHITECTURE, UX_PRINCIPLES, CAD_MODEL, TOPOLOGY_STRATEGY, ROADMAP.

## Milestone 1 — Fondamenta del motore (fatta il 16/10/2026)
Sketch XY → rettangolo 300 × 200 → foro Ø30 → estrusione 5 → 300 diventa 400 →
rigenerazione → STEP → DXF. Più: stato dello sketch in parole semplici,
undo/redo, formato `.steelcad`, autosave e recupero, tasca, foro, raccordo,
smusso, nomi topologici stabili, peso.

Verifica: 39 test automatici (`pytest`), gate in `tests/test_milestone1.py`,
file di riferimento in `test_parts/plate_300x200_hole30/`. Rigenerazione della
piastra dopo una modifica: circa 10 ms.

Non ancora fatto (va nella M2 insieme alla prima UI): viewer, selezione col
mouse, quote modificabili sul modello, palette comandi. Revolve, serie,
specchio, sweep: dopo la M2.

## Milestone 2 — Strutture
Scheletro 2D/3D → profilo 40×40×3 → tubolari reali → gambe → giunti (trim,
extend, 45°, testa) → modifica dimensioni → BOM → cut list → STEP. Catalogo
profili modificabile (quadro, rettangolare, tondo, piatto, angolare, U, C,
HEA, HEB, IPE). Prima UI: viewer Three.js, selezione, pannello proprietà,
quote modificabili sul modello. Scelta finale del guscio desktop.

## Milestone 3 — Lamiera
Rettangolo → lamiera sp. 2 → flangia 30 a 90° → seconda flangia → fori →
sviluppo → DXF. K-factor, raggio interno, bend allowance/deduction, scarichi;
parametri tecnologici obbligatori (nessun valore inventato). Confronto con un
pezzo di riferimento con sviluppo noto.

## Milestone 4 — Uso in azienda
Configuratori (tavolo, basamento, telaio, cancello, piedistallo, armadio,
carter) sullo stesso motore, ottimizzazione barre da 6 m, componenti
commerciali, PDF, BOM avanzata, import STEP con analisi, da solido a lamiera,
e solo alla fine richieste in linguaggio naturale che producono parametri.

## Fuori dalla strada principale
SLDPRT: solo esperimento separato (openswx); se non si legge, il messaggio
è "Esporta il componente in STEP".
