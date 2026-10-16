# SteelCAD — Strategia per i nomi topologici

## Il problema

Dopo una modifica (300 → 400, un foro in più) OpenCascade rinumera facce e
spigoli. Un raccordo salvato come "Edge12" finirebbe su uno spigolo a caso.
SteelCAD **non salva mai indici** di facce o spigoli.

## La soluzione: nomi generati dallo storico + spigoli come incontro di facce

### Facce: nome dato da chi le crea

Ogni feature che crea geometria dà un nome alle facce nuove, usando lo
storico delle operazioni di OpenCascade (`Generated`, `Modified`,
`IsDeleted` di `BRepPrimAPI_MakePrism` e `BRepAlgoAPI_*`):

| Feature | Facce create | Nome |
|---|---|---|
| Estrusione da sketch | faccia laterale nata dalla linea `L2` dello sketch `S1` | `E1/lato/L2` |
| | faccia di partenza / di arrivo | `E1/inizio`, `E1/fine` |
| Foro | parete del foro nel punto `P5` | `H1/foro/P5`, `H1/fondo/P5` |
| Raccordo / smusso | faccia nuova sullo spigolo k | `F1/raccordo/k` |

L'entità dello sketch che genera una faccia si trova confrontando la
geometria (il bordo della faccia piana iniziale contro le linee e i cerchi
risolti), non per ordine: è stabile anche se il risolutore riordina.

Quando un'operazione booleana modifica una faccia (per esempio la faccia
`E1/fine` viene bucata da un foro), la faccia risultante **eredita il nome**
attraverso `Modified`. Se una faccia viene divisa in due, tutte e due le parti
hanno lo stesso nome (un nome può indicare più frammenti). Se viene cancellata,
il nome sparisce.

### Spigoli: l'incontro di due facce con nome

Uno spigolo si identifica con la coppia di facce che separa:
`{E1/fine, E1/lato/L2}` è lo spigolo superiore sul lato L2. Se le stesse due
facce si toccano in più spigoli (raro: una parete tagliata in due), si
distinguono con un ordine geometrico deterministico (posizione del punto
medio lungo l'asse principale) e un indice.

### Cosa succede quando un riferimento si perde

- Nessuna faccia con quel nome → **errore chiaro**, mai una scelta a caso:
  "Il raccordo R5 era sullo spigolo tra la faccia superiore e il lato L2,
  che non esiste più dopo la modifica. Riassegna lo spigolo."
- Più frammenti con lo stesso nome → se l'operazione accetta più elementi
  (raccordo su tutti i tratti) li usa tutti; se ne vuole uno solo, errore che
  chiede di scegliere.

### Perché questa strada

- **Nomi basati sulle feature** (come Onshape e la nuova gestione di FreeCAD
  1.0): stabili alle modifiche di quota, leggibili nei messaggi.
- **Confronto geometrico** solo dove non c'è storico (legame sketch → bordo),
  con tolleranza esplicita.
- **Spigoli come coppie di facce**: sopravvivono a qualunque rinumerazione
  finché le due facce esistono.

### Limiti noti (da affrontare nelle prossime milestone)

- Una modifica che cambia la topologia dello sketch (un lato diviso in due)
  cambia i nomi delle facce laterali nate da quel lato: il riferimento si
  segnala come perso, non si indovina.
- Gli import STEP non hanno storico: le facce importate prendono nomi
  geometrici (tipo, normale, area) e i riferimenti su di esse sono più deboli.

## Implementazione

`cad_engine/topology/naming.py`:

- `NamedShape`: solido + `dict[nome → lista di facce]`;
- `propagate(maker, prima, dopo)`: dopo ogni operazione aggiorna i nomi con
  `Modified` / `Generated` / `IsDeleted`;
- `edge_by_faces(nome_a, nome_b)`: trova gli spigoli comuni;
- `edge_ref(spigolo)`: dal clic sullo spigolo al riferimento stabile da salvare.

Test: `tests/test_topology.py` cambia quote, aggiunge fori e controlla che i
raccordi restino sugli stessi spigoli.
