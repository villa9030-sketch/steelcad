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

**Fatta (16/10).** Gate `tests/test_milestone3.py`:
- U 500×300, sp. 2, R2, K 0,4 → sviluppo 500 × 352,796, uguale al conto a mano 300 + 2·(30 − BD);
- volume del solido uguale al conto a mano, compresi i fori;
- DXF con 3 contorni, fori Ø8 e Ø20, 2 linee di piega;
- portando W da 500 a 600 tutto si rigenera, e l'annulla funziona.

Verifica incrociata con K 0,5: area dello sviluppo × spessore = volume 3D, a 1e-9.

Metodi di piega: K-factor, DIN 6935, deduzione a 90°, nessun default.

Interfaccia: modello Lamiera, flangia con un clic sul fianco, pannello della flangia (con i fori),
scheda Lamiera (dati di piega, pieghe, anteprima dello sviluppo, export).

Pezzi di riferimento in `test_parts/`: simple_frame_2000x1000, table_frame, sheetmetal_u_2mm
(`tools/test_parts.py`). Dettagli e limiti in `docs/SHEETMETAL.md`.

Manca solo il confronto con un pezzo piegato davvero sulla pressa: vedi `sheetmetal_u_2mm/expected.json`.

**Dopo la prima prova di Stefano (16/10).**
- Corretto: un progetto nuovo creato subito dopo l'avvio lasciava a video il pezzo vecchio. La
  versione della scena ripartiva da 1 e l'interfaccia credeva di averla già.
- Nuovo: disegno libero ("Nuovo → Da zero" oppure clic su uno sketch nell'albero).
  - Vista dall'alto con griglia, strumenti Linea, Rettangolo, Cerchio e Seleziona/Canc.
  - Agganci a punti, origine, orizzontale/verticale e griglia.
  - Lunghezze e diametri si scrivono mentre si disegna; il contorno si chiude cliccando il primo punto.
  - Le quote nascono da sole e quelle doppie si tolgono da sole.
  - Poi "Crea lamiera…" o "Crea piastra…".

**Dopo la seconda prova di Stefano (17/10).**
- Pieghe su pieghe: flange sulla punta di altre flange, anche a catena (omega, scatola bordata, Z).
  Sviluppo esatto, i bordi negli angoli si accorciano da soli. Test in `tests/test_flange_chain.py`.
- "Disegna su questa faccia": la faccia è il piano di lavoro, il resto del pezzo sparisce (tasto G
  per vederlo in trasparenza). Lo sketch lasciato vuoto non resta nell'albero.
- **Spiega** (tasto U): lo sviluppo a video, con le strisce delle pieghe; **Disegna sullo sviluppo**:
  quello che disegni si taglia nello sviluppo e torna nel pezzo piegato sulla faccia giusta.
- Angoli dei bordi della scatola bordata: lo chiede al primo angolo (dritti con i lati lunghi interi,
  dritti con i lati corti interi, tagliati a 45°); si cambia dal pannello di un bordo.
- Sulla faccia (e sullo sviluppo) i bordi del pezzo sono guide fisse: offset dal bordo, agganci, quote.
- Linea con angolo scritto: `100<30` (lunghezza < angolo dall'asse X); l'angolo resta vincolato.
- Corretto: la flangia poteva finire sul lato sbagliato se si cliccava un altro lato mentre la
  precedente si costruiva (la selezione vecchia arrivava dopo e sostituiva il pannello).
- Bordi da piegare scelti col mouse: il bordo si accende passandoci sopra, clic = flangia solo lì
  (prima si prendeva la faccia sottile sbagliata, es. la testata corta invece del bordo lungo).
  Clic su una faccia di flangia: si accende la faccia, non tutta la flangia.
- Offset come AutoCAD: distanza + Invio, clic sull'oggetto, clic dalla parte dove va.
- Disegno 2D rifatto (18/10): comandi nel pannello a destra con stato in parole semplici e passi
  numerati, quote visibili anche sulle facce, assi della faccia come lo schermo e (0;0) nel suo angolo
  in basso a sinistra, bordi del pezzo in arancio, inquadratura sulla faccia intera.
- Offset di una linea sola (quella cliccata) e casella di comando in alto per distanze e misure
  (anche rettangolo `100x50`).
- Taglia e Allunga come AutoCAD, con anteprima (rosso il pezzo che si toglie, tratteggio l'allungamento);
  un cerchio tagliato diventa arco. Archi disegnati e selezionabili nello sketch.
- Agganci su cerchi e archi (quadranti, incroci, sul bordo) legati al cerchio; strumento Asola; il Taglia
  riusa i punti che ci sono già (asola fatta a mano = contorno chiuso).
- Agganci rifatti come AutoCAD: vince il più vicino, simbolo sul punto, incroci cerchio-cerchio, tangente,
  perpendicolare, "sulla linea" anche per le linee normali, puntamento (allineamento a un punto, linea verde),
  F9 per la griglia. Tangente, perpendicolare e puntamento restano vincoli.
- **Interfaccia in stile SolidCraft** (18/10): barra del titolo scura, barra a schede LAMIERA / STRUTTURE /
  PIASTRA con le icone di SolidCraft (MIT/Apache, `app/ui/icons/ATTRIBUTION.md`) e la scheda SKETCH che
  compare mentre disegni; cubo delle viste, barra di navigazione, storia delle operazioni in basso, riga di
  comando; mentre disegni il pannello in basso si chiude.
- Funzioni prese da SolidCraft come idee (codice nostro): raccordo e smusso degli spigoli nello sketch,
  arco per tre punti, poligono regolare, regole di lamiera salvate (materiale, spessore, raggio, K) riusabili
  in ogni progetto, tabella pieghe in CSV.
- Tema scuro (predefinito) e chiaro; raccordo/smusso anche cliccando due linee (come AutoCAD), con R0 per
  unirle; corretto il raccordo sullo spigolo che sta sull'origine.
- Aletta di chiusura della testata dei profili chiusi, piegata da una parete (anche nello sviluppo).
- Lamiera a contorno: la sezione disegnata sulla testata diventa una catena di flange.
- Aggiungi materiale (linguetta): il contorno disegnato su una faccia diventa lamiera nel suo piano.
- Prove: 136 test (`pytest`), `tools/prova_ui.py` (42), `tools/prova_ui_pieghe.py` (55) e
  `tools/prova_ui_comandi.py` (45: ogni pulsante della barra, cubo delle viste, storia, tema, raccordi, chiusura testata).
- In coda (da SolidCraft): orlo, piega lungo una linea, scarichi d'angolo a scelta, altezza/angolo per lato
  in una flangia, foratura a griglia, conversione da solido a lamiera.

## Milestone 4 — Uso in azienda
Configuratori (tavolo, basamento, telaio, cancello, piedistallo, armadio,
carter) sullo stesso motore, ottimizzazione barre da 6 m, componenti
commerciali, PDF, BOM avanzata, import STEP con analisi, da solido a lamiera,
e solo alla fine richieste in linguaggio naturale che producono parametri.

## Fuori dalla strada principale
SLDPRT: solo esperimento separato (openswx); se non si legge, il messaggio
è "Esporta il componente in STEP".
