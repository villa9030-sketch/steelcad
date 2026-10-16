# SteelCAD

CAD parametrico verticale per carpenteria metallica: piastre, telai in
tubolare, lamiera piegata. Pensato per chi conosce l'officina, non il CAD.

**Stato: Milestone 2 completata (strutture in tubolare e prima interfaccia).**
Vedi `docs/ROADMAP.md`.

## Cosa c'è

- Sketch 2D parametrico con vincoli e quote (risolutore PlaneGCS), stato
  spiegato in italiano ("ha ancora 2 gradi di libertà", "questa quota è in
  conflitto con…").
- Feature: estrusione (nuovo / aggiungi / togli = tasca), foro passante o cieco,
  raccordo, smusso; sketch su piani o su facce del pezzo.
- Parametri ed espressioni (`larghezza`, `larghezza/2 - 10`), ricostruzione
  con cache: si rifà solo ciò che è cambiato.
- Nomi stabili di facce e spigoli (un raccordo resta sul suo spigolo anche
  dopo aver cambiato le misure): `docs/TOPOLOGY_STRATEGY.md`.
- Undo/redo, file `.steelcad` con salvataggio sicuro, copia `.bak`,
  autosave e recupero.
- Export STEP (verificato rileggendolo) e DXF di produzione (controlli:
  contorni chiusi, doppioni, sovrapposizioni, microsegmenti, unità).
- Peso dal materiale (S235, inox, alluminio…).
- Strutture in tubolare da uno scheletro: profili a catalogo (quadro,
  rettangolare, tondo, piatto, angolare, U, C, IPE, HEA, HEB), giunti a 45° e
  di testa, cut list con lunghezze e tagli, distinta, avvisi di interferenza.
- Interfaccia desktop: viewer 3D, albero, parametri, quote modificabili sul
  modello, proprietà dell'asta, distinta/cut list, palette Ctrl+K.

## Aprire l'app

Doppio clic su `SteelCAD.bat` (oppure `.venv\Scripts\python app\main.py`).
Parte con un tavolo 2000×1000×900 di esempio; File → Nuovo per telaio o piastra.

## Provare

```
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest            # tutti i test
.venv\Scripts\python tools\milestone1.py  # il flusso del gate, scrive in test_parts\
```

## Esempio

```python
from cad_engine import Document, History
from cad_engine.exporters import step, dxf

doc = Document('Piastra', 'S235')
doc.set_parameter('larghezza', 300)
sk = doc.add_sketch('XY', 'Profilo')
r = sk.rectangle(0, 0, 290, 190)
sk.constrain('coincident', r['corners'][0], 'O')
sk.dimension('length', r['bottom'], value='larghezza')
sk.dimension('length', r['left'], value=200)
foro = sk.circle((150, 100), 14)
sk.dimension('diameter', foro, value=30)
sk.constrain('symmetric', r['corners'][0], r['corners'][2], sk.entities[foro]['center'])
doc.add_feature('extrude', 'Piastra', sketch=sk.id, distance=5)

doc.set_parameter('larghezza', 400)      # si rigenera tutto, il foro resta al centro
res = doc.rebuild()
step.export(res.body.shape, 'piastra.step')
dxf.export_flat(res.body.shape, 'piastra.dxf')
```

## Documenti

`docs/ARCHITECTURE.md`, `docs/UX_PRINCIPLES.md`, `docs/CAD_MODEL.md`,
`docs/TOPOLOGY_STRATEGY.md`, `docs/ROADMAP.md`.
