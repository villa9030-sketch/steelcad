"""Rifà il flusso della Milestone 1 e scrive i file di riferimento in test_parts/.

    .venv\\Scripts\\python tools\\milestone1.py

Sketch XY → rettangolo 300 × 200 → foro Ø30 al centro → estrusione 5 →
larghezza 300 → 400 → STEP + DXF + progetto .steelcad.
"""
import json
import sys
from pathlib import Path

QUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(QUI))

from cad_engine import Document, History, project_io  # noqa: E402
from cad_engine.analysis import properties  # noqa: E402
from cad_engine.exporters import dxf, step  # noqa: E402

OUT = QUI / 'test_parts' / 'plate_300x200_hole30'


def main():
    doc = Document('Piastra 300x200 foro 30', 'S235')
    hist = History(doc)
    with hist.change('Parametro larghezza'):
        doc.set_parameter('larghezza', 300)
    with hist.change('Sketch del profilo'):
        sk = doc.add_sketch('XY', 'Profilo piastra')
        r = sk.rectangle(0, 0, 290, 190)
        sk.constrain('coincident', r['corners'][0], 'O')
        sk.dimension('length', r['bottom'], value='larghezza')
        sk.dimension('length', r['left'], value=200)
        c = sk.circle((150, 100), 14)
        sk.dimension('diameter', c, value=30)
        sk.constrain('symmetric', r['corners'][0], r['corners'][2], sk.entities[c]['center'])
    with hist.change('Estrusione 5 mm'):
        doc.add_feature('extrude', 'Piastra', sketch=sk.id, distance=5, operation='new')

    for larghezza in (300, 400):
        if larghezza != 300:
            with hist.change(f'Larghezza 300 → {larghezza}'):
                doc.set_parameter('larghezza', larghezza)
        res = doc.rebuild()
        if not res.ok:
            raise SystemExit('; '.join(f.message for f in res.errors))
        p = properties(res.body.shape, doc.material)
        print(f'--- larghezza {larghezza}')
        print('  sketch:', res.features[0].message)
        print(f'  volume {p["volume_mm3"]:.4f} mm³, peso {p["mass_kg"]:.4f} kg, ingombro',
              ' x '.join(f'{v:.3f}' for v in p['bbox_mm']['size']))
        print(f'  ricostruite {res.rebuilt}, dalla cache {res.cached}, {res.seconds * 1000:.1f} ms')
        base = OUT / f'piastra_{larghezza}x200'
        st = step.export(res.body.shape, base.with_suffix('.step'), name=f'Piastra {larghezza}x200')
        rep = dxf.export_flat(res.body.shape, base.with_suffix('.dxf'))
        print(f'  STEP: {st["solids"]} solido, volume riletto {st["volume_mm3"]:.4f}')
        print(f'  DXF: {rep["contours"]} contorni, {rep["size_mm"][0]:.3f} x {rep["size_mm"][1]:.3f}, '
              f'fori {rep["circle_diameters"]}, problemi: {rep["problems"] or "nessuno"}')
    project_io.save(doc, OUT / 'piastra.steelcad', backup=False)
    print('undo:', hist.labels()['undo'])
    print('scritto in', OUT)


if __name__ == '__main__':
    main()
