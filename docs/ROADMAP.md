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

Viewer, selezione col mouse, quote sul modello e palette comandi: fatti nella
M2. Revolve, serie, specchio, sweep: dopo.

## Milestone 2 — Strutture
Scheletro 2D/3D → profilo 40×40×3 → tubolari reali → gambe → giunti (trim,
extend, 45°, testa) → modifica dimensioni → BOM → cut list → STEP. Catalogo
profili modificabile (quadro, rettangolare, tondo, piatto, angolare, U, C,
HEA, HEB, IPE). Prima UI: viewer Three.js, selezione, pannello proprietà,
quote modificabili sul modello. Scelta finale del guscio desktop.

**Fatta (16/10).** Motore: telaio 2000×1000×900 in 40×40×3 → 2×2040 e 2×1040
a 45°/45°, 4 gambe 880 dritte, 31,98 kg; cambiando L/P/H le lunghezze si
aggiornano (rigenerate solo le aste toccate). BOM, albero, cut list, STEP con
un solido per asta, avvisi di interferenza.

Prima interfaccia (guscio: **pywebview + WebView2**, perché Node e Rust non ci
sono; three.js in locale, funziona senza internet):
- viewer 3D: ruota/sposta/zoom, viste Iso/Sopra/Fronte/Destra/Adatta, hover
  azzurro, selezione ambra (asta intera o faccia della piastra), Esc deseleziona;
- albero del progetto (gruppi e misure) e parametri modificabili, anche con
  espressioni; nuovo parametro con "nome = valore";
- quote sul modello: clic sul numero, scrivi, Invio. Se la quota è legata a un
  parametro cambia il parametro;
- pannello proprietà secondo ciò che selezioni: per un'asta profilo (anche per
  tutto il gruppo), rotazione 90°, inversione, linea d'asse; per la piastra
  peso, ingombro, faccia, export;
- in basso Distinta | Cut list (con totali per profilo) | Info (tempi, avvisi,
  errori);
- annulla/ripeti con il nome dell'operazione, salva/apri con recupero del
  salvataggio automatico (ogni minuto), conferma alla chiusura;
- export STEP e DXF di taglio dalla finestra di Windows;
- palette Ctrl+K: comandi e "L = 2200" per cambiare un parametro al volo;
- modelli rapidi Telaio/tavolo e Piastra, fatti con le stesse feature.

Prove: `pytest` (67 test, compreso lo strato applicativo) e
`tools/prova_ui.py` (browser invisibile: 17 controlli dal clic alla quota
all'export, nessun errore in console).

Scheletro dall'interfaccia (16/10, seconda parte):
- i nodi si vedono sul modello come pallini; cliccandone uno si apre il pannello del nodo;
- "Nuova asta da qui": lunghezza (anche un parametro), profilo, gruppo e direzione X±/Y±/Z±.
  Il nodo nuovo resta legato a quello di partenza (`{"from": "A", "offset": [...]}`): se sposti
  il primo, gli altri lo seguono. Dopo l'asta si continua dal nodo nuovo, come una polilinea;
- "Collega a un altro nodo": clic sul nodo d'arrivo;
- giunto per nodo: automatico (si vede cosa ha scelto), 45°, a battuta (con chi passa),
  dritto, ad angolo;
- posizione del nodo modificabile; Canc elimina le aste selezionate e i nodi rimasti soli;
- progetto "Struttura libera": si parte da un nodo nell'origine;
- regola generale: una modifica che rompe una parte che prima funzionava viene annullata e il
  motivo si spiega ("Non applicato: l'asta M1 ha lunghezza zero…").

Prove: 70 test; `tools/prova_ui.py` con 22 controlli, compreso un cancello costruito da zero
coi clic.

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
