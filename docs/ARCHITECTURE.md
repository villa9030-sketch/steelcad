# SteelCAD — Architettura

Stato: Milestone 1 (fondamenta). Aggiornato il 16/10/2026.

## 1. Strati

```
UI (web: viewer Three.js + pannelli)          ← Milestone 2
   │  JSON (comandi e risultati), mai oggetti OpenCascade
Application layer  (cad_engine.commands)       comandi, undo/redo, autosave
   │
Parametric model   (cad_engine.document)       parametri, feature, grafo, cache
   │
CAD engine         (cad_engine.sketch, features, topology, exporters, analysis)
   │
build123d 0.13  +  OCP 8.0 (OpenCascade 8.0)   BREP reale
```

Regola: **la UI non importa mai OCP né build123d.** Parla con l'application
layer con dati semplici (dizionari JSON). Il motore funziona e si prova da
solo, senza UI: tutta la Milestone 1 è verificata da test automatici.

## 2. Scelte tecniche (decise)

| Area | Scelta | Perché |
|---|---|---|
| Linguaggio del motore | Python 3.14 | build123d, OCP, planegcs ed ezdxf hanno le ruote binarie pronte per Windows e 3.14; prototipo e test veloci. Il motore si impacchetta poi come processo a parte (PyInstaller). |
| Kernel | OpenCascade 8.0 via OCP 8.0.1 | BREP vero, STEP nativo, booleane con storico (serve per i nomi topologici). |
| Livello comodo sul kernel | build123d 0.13 | API pulita per costruire bordi, facce, esportare STEP. Dove serve lo storico delle operazioni si usa OCP direttamente. |
| Risolutore sketch | planegcs 0.9.6 (il PlaneGCS di FreeCAD) | Stabile, usato in produzione da anni, restituisce gradi di libertà e vincoli in conflitto. Nessun risolutore scritto da zero. |
| DXF | ezdxf 1.4 | Scrittura e rilettura per i controlli. |
| Test | pytest | Ogni gate è un test che si rilancia. |
| Viewer (M2) | Three.js + glTF dalla tassellazione del motore | La mesh è solo per vedere; la geometria vera resta BREP. |
| Guscio desktop (M2) | Tauri se si installa la catena Rust+Node; altrimenti pywebview (usa WebView2 di Windows, già presente, leggerissimo) | Oggi sul PC non ci sono Node né Rust: la decisione finale si prende all'inizio della M2, la UI web è la stessa nei due casi. Electron escluso (pesante). |

Licenze: OpenCascade LGPL 2.1 con eccezione, planegcs LGPL, build123d
Apache 2.0, ezdxf MIT. Compatibili con un prodotto chiuso se le librerie
LGPL restano collegate dinamicamente (come qui: moduli Python separati).

## 3. Struttura delle cartelle

```
steelcad/
  cad_engine/
    errors.py        errori con messaggi chiari in italiano
    units.py         mm, gradi, tolleranze
    materials.py     materiali e densità (con fonte)
    expressions.py   valori di quota: numeri o parametri ("larghezza", "larghezza/2")
    document.py      il modello parametrico: parametri, feature, ricostruzione, cache
    commands.py      comandi, undo/redo
    project_io.py    formato .steelcad, autosave, recupero, copia precedente
    sketch/
      model.py       entità, vincoli, quote (dati puri)
      solver.py      adattatore planegcs + stato dello sketch in parole semplici
      profile.py     dai bordi risolti alle facce (contorno esterno + fori)
    features/
      base.py        interfaccia comune delle feature
      sketch_feature.py
      extrude.py     estrusione: nuovo solido, aggiungi, togli (= tasca)
      hole.py        foro passante o cieco
      dress.py       raccordo e smusso
    topology/
      naming.py      nomi stabili di facce e spigoli (vedi TOPOLOGY_STRATEGY.md)
    exporters/
      step.py
      dxf.py         DXF di produzione con controlli
    analysis/
      measure.py     volume, area, ingombro, peso
  tests/
  test_parts/        pezzi di riferimento con valori attesi
  docs/
```

Le cartelle `profiles/`, `structures/`, `sheetmetal/`, `bom/`, `cutlist/`,
`assemblies/` e `importers/` nascono con le milestone che le usano: niente
moduli vuoti che fingono funzioni.

## 4. Flusso di una modifica

1. La UI manda un comando, per esempio `SetDimension(sketch="S1", dim="D1", value=400)`.
2. `commands.History` salva lo stato prima e dopo (undo/redo).
3. `Document` segna come "sporche" la feature toccata e quelle che dipendono da lei.
4. `Document.rebuild()` ricostruisce solo le feature sporche, in ordine; le altre vengono dalla cache.
5. Il risultato (solido, nomi topologici, misure, messaggi) torna alla UI come dati.

## 5. Grafo delle dipendenze e cache

Ogni feature dichiara da cosa dipende: lo sketch che usa, il solido
precedente, i riferimenti a facce o spigoli, i parametri che legge. Per ogni
feature si calcola un'impronta (hash) della sua definizione più le impronte
di ciò da cui dipende. Se l'impronta non cambia, il risultato si prende dalla
cache. Cambiare un parametro ricostruisce solo le feature che lo usano e
quelle a valle; un pezzo indipendente in un assieme (M2) non si ricostruisce.

## 6. Undo / redo

Ogni modifica passa da un comando. Il comando conserva la definizione del
documento prima e dopo (è JSON piccolo: la geometria non si salva, si
ricostruisce dalla cache). Undo e redo rimettono la definizione e ricostruiscono.
Esiste dal primo giorno, non si aggiunge dopo.

## 7. Errori

Nessun "Operation failed". Ogni errore del motore è un `SteelCADError` con:
messaggio per l'utente in italiano, codice stabile per la UI, dettagli tecnici
separati (per il registro, non per l'utente). Esempio: "Il raccordo R20 non
si può fare: la faccia accanto è larga solo 5 mm."
