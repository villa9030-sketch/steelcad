# SteelCAD — Modello parametrico e formato progetto

## Unità

Lunghezze in **mm**, angoli in **gradi** (anche nel file), pesi in **kg**,
densità in g/cm³. Le conversioni verso il kernel (radianti) avvengono solo
dentro `cad_engine`.

## Documento

Un documento (per ora una parte; dalla M2 anche assiemi e strutture) contiene:

- **parametri** con nome: `{"larghezza": 300, "spessore": 5}`;
- **materiale** della parte;
- **feature** in ordine, ognuna con un id stabile (`S1`, `E1`, …) che non
  cambia mai, anche se la feature viene spostata o rinominata;
- **metadati**: nome, autore, date, versione del formato.

Ogni valore numerico di una feature o di una quota può essere un numero o
un'espressione sui parametri: `300`, `"larghezza"`, `"larghezza/2 - 10"`.
Le espressioni ammettono solo numeri, nomi di parametri e `+ - * / ( )`
(niente codice eseguibile).

## Feature della Milestone 1

| Tipo | Cosa fa | Input |
|---|---|---|
| `sketch` | Sketch 2D vincolato su un piano (XY, XZ, YZ) o su una faccia piana con nome | entità, vincoli, quote |
| `extrude` | Estrude i profili chiusi di uno sketch; `new` nuovo solido, `add` aggiunge, `cut` toglie (tasca) | sketch, distanza, verso |
| `hole` | Fori passanti o ciechi nei punti o centri di cerchio di uno sketch | sketch, punti, diametro, profondità |
| `fillet` / `chamfer` | Raccordo / smusso su spigoli con nome | spigoli, raggio / distanza |

## Sketch

Entità: `point`, `line`, `circle`, `arc`. Composti creati dagli strumenti:
rettangolo, polilinea, asola. Le linee condividono i punti d'angolo, quindi
una polilinea chiusa non ha bisogno di vincoli di coincidenza. Il punto `O`
(origine) esiste sempre ed è fisso.

Vincoli: coincidente, orizzontale, verticale, parallelo, perpendicolare,
tangente, uguale, concentrico, simmetrico, fisso.
Quote: distanza, lunghezza, distanza orizzontale, distanza verticale,
angolo, diametro, raggio.

Le coordinate salvate sono le posizioni "a mano" dell'utente: il risolutore
parte da lì ogni volta e il risultato non si riscrive nella definizione
(niente deriva, undo pulito).

## Formato `.steelcad`

File JSON UTF-8 (dalla M4 un contenitore zip per allegati e anteprime).

```json
{
  "format": "steelcad",
  "version": 1,
  "meta": {"name": "Piastra 300x200", "created": "...", "modified": "..."},
  "units": {"length": "mm", "angle": "deg", "mass": "kg"},
  "parameters": {"larghezza": 300},
  "material": "S235",
  "features": [
    {"id": "S1", "type": "sketch", "name": "Profilo piastra", "plane": "XY",
     "entities": [...], "constraints": [...]},
    {"id": "E1", "type": "extrude", "name": "Piastra", "sketch": "S1",
     "distance": 5, "operation": "new"}
  ]
}
```

Lo STEP non è il progetto: è un'uscita. Il progetto si ricostruisce sempre
dal `.steelcad`.

## Salvataggio sicuro

- scrittura su file temporaneo e poi sostituzione (un file a metà non esiste mai);
- prima di sovrascrivere, la versione precedente diventa `nome.steelcad.bak`;
- autosave in `nome.steelcad.autosave` ogni N secondi di modifiche non salvate;
- all'apertura, se l'autosave è più recente del file, si propone il recupero.
