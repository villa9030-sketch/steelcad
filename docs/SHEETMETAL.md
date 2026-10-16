# Lamiera piegata

## Come si costruisce
Uno sketch chiuso (il contorno del piano) → feature **Lamiera** (`sheet`) con lo spessore →
**flange** sui lati dritti del contorno esterno. Le flange stanno dentro la feature (come le aste
dentro una struttura): una sola voce nell'albero, con una riga per flangia.

Dall'interfaccia:
- File → Nuovo → Lamiera;
- clic su un fianco della lamiera → "Flangia su questo lato";
- clic su una flangia → lunghezza, angolo, verso, posizione, fessura d'angolo e fori;
- scheda **Lamiera** in basso: dati di piega, tabella delle pieghe, anteprima dello sviluppo ed export DXF.

## Convenzioni (come un disegno d'officina)
- **Contorno = quota esterna** del pezzo finito (posizione "quota esterna sul contorno", default):
  una U 500×300 con ali da 30 misura fuori tutto 500 × 300 × 30.
  Con "piega dal bordo" il piano resta intero e la flangia si aggiunge fuori.
- **Lunghezza della flangia** = dallo spigolo vivo esterno (intersezione delle facce esterne) alla
  punta. Per 90° è l'altezza esterna dell'ala.
- **Fori sulla flangia**: `u` lungo il lato, dal primo punto della linea dello sketch; `v` dallo
  spigolo vivo esterno verso la punta. Un foro che tocca la zona di piega è rifiutato.
- **Angoli tra due flange**: ogni flangia si ferma dove incontra la linea di fine piano della
  vicina; nello sviluppo resta uno scarico quadrato. La "fessura d'angolo" aggiunge gioco.

## Calcolo della piega
Nessun valore di default: spessore, raggio interno e metodo li dà l'utente (sono dati della
piegatrice). Se manca qualcosa la lamiera non si costruisce e la scheda dice cosa manca.

| Metodo | Da dove viene K |
|---|---|
| K-factor | scritto dall'utente (0–1) |
| DIN 6935 | k = 0,65 + 0,5·log10(r/s) per r/s < 5, altrimenti 1; K = k/2 |
| Deduzione a 90° | dalla tabella della pressa: BA = 2·setback − BD; vale solo per pieghe a 90° |

    BA      = θ · (r + K·t)
    setback = (r + t) · tan(θ/2)
    BD      = 2 · setback − BA
    sviluppo di un'ala = L − BD   (dallo spigolo vivo esterno)

## Lo sviluppo è verificabile
- È calcolato dalle stesse quote del 3D, non "srotolando" il solido. Le strisce delle flange sono
  lunghe BA + tratto dritto e partono dalla linea di fine piano.
- **Verifica incrociata**: con K = 0,5 la fibra neutra è a metà spessore, quindi area dello
  sviluppo × spessore = volume del solido di OpenCascade. I test lo controllano su U, vasca a 4
  flange, flange su/giù, "dal bordo", 45°/135° e fori; coincide a 1e-9.
- `test_parts/sheetmetal_u_2mm/expected.json` ha i conti a mano della U di riferimento.
- **Da fare con un pezzo vero**: piegare la U sulla pressa e misurare lo sviluppo. Poi si scrivono
  in quel file il raggio e il K reali.

## DXF dello sviluppo
- **CUT**: contorno e fori.
- **BEND**: linea tratteggiata al centro della piega, con scritta tipo "FL1 SU 90° R2".
- I controlli (contorni chiusi, doppioni, microsegmenti, unità mm) guardano solo il layer CUT.

## Limiti attuali
- Flange solo sui lati dritti del contorno esterno del piano; niente flange sulle flange.
- Niente risvolti (oltre 170°).
- Lavorazioni dopo la lamiera (estrusioni, fori come feature a parte) non entrano nello sviluppo:
  l'export lo dice. I fori sulla base vanno nello sketch, quelli sulle ali nel pannello della flangia.
- Solid-to-sheet (da un STEP importato) è della Milestone 4.
