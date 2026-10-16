"""Scrive i pezzi di riferimento delle Milestone 2 e 3 in test_parts/ (quote, volume, peso attesi + file).

    .venv\\Scripts\\python tools\\test_parts.py

- simple_frame_2000x1000: telaio rettangolare in 40×40×3, quattro aste a 45°;
- table_frame: tavolo 2000×1000×900 (telaio sopra + 4 gambe);
- sheetmetal_u_2mm: canalina a U 500×300, sp. 2, flange 30 a 90°, R2, K 0,4, foro Ø20 sulla base
  e Ø8 sulla flangia FL1.
I valori in expected.json sono calcolati a mano con le formule scritte accanto, poi confrontati
con quello che fa il motore: se non coincidono lo script si ferma.
"""
import json
import math
import sys
from pathlib import Path

QUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(QUI))

import build123d as bd  # noqa: E402

from cad_engine import Document, project_io, templates  # noqa: E402
from cad_engine.exporters import dxf, step  # noqa: E402
from cad_engine.structures import cut_list  # noqa: E402

OUT = QUI / 'test_parts'
DENS = 7.85e-6        # kg/mm³, acciaio S235


def _uguale(nome, atteso, ottenuto, tol=1e-6):
    if abs(atteso - ottenuto) > tol * max(1, abs(atteso)):
        raise SystemExit(f'{nome}: atteso {atteso}, ottenuto {ottenuto}')


def _shs_area(b, t):
    """EN 10219: tubo quadro con raggi esterno ro e interno ri = ro − t (ro = 2t per t ≤ 6)."""
    ro = 2 * t
    ri = ro - t
    return (b * b - (4 - math.pi) * ro ** 2) - ((b - 2 * t) ** 2 - (4 - math.pi) * ri ** 2)


def telaio_semplice():
    d = OUT / 'simple_frame_2000x1000'
    d.mkdir(parents=True, exist_ok=True)
    doc = Document('Telaio 2000x1000', 'S235')
    sk = doc.add_sketch('XY', 'Scheletro')
    r = sk.rectangle(0, 0, 1900, 950)
    sk.constrain('coincident', r['corners'][0], 'O')
    sk.dimension('length', r['bottom'], value=2000)
    sk.dimension('length', r['left'], value=1000)
    pts = {f'P{i}': {'sketch': sk.id, 'point': c} for i, c in enumerate(r['corners'])}
    mem = [{'id': f'M{i + 1}', 'group': 'Telaio', 'from': f'P{i}', 'to': f'P{(i + 1) % 4}', 'profile': '40x40x3'}
           for i in range(4)]
    doc.add_feature('structure', 'Telaio', points=pts, members=mem)
    res = doc.rebuild()
    cl = cut_list(res.structures)
    a = _shs_area(40, 3)
    attese = {'2040': 2, '1040': 2}            # misura d'asse + 2 × metà profilo (taglio a 45°)
    for riga in cl['rows']:
        assert riga['cuts'] == ['45°', '45°'], riga
        attese[f'{riga["length_mm"]:g}'] -= riga['qty']
    assert all(v == 0 for v in attese.values()), attese
    vol = sum(m.solid.volume for st in res.structures for m in st.members)
    # a 45° ogni asta è un trapezio: volume = area × (lunghezza esterna − 40)
    _uguale('volume telaio', a * ((2040 - 40) * 2 + (1040 - 40) * 2), vol)
    step.export_project(doc, res, d / 'telaio.step')
    project_io.save(doc, d / 'telaio.steelcad', backup=False)
    exp = {'_nota': 'Asse 2000 × 1000, tubo 40×40×3 EN 10219 (ro = 2t). Volume a mano: area sezione × '
                    '(lunghezza esterna − 40) perché i tagli a 45° tolgono due triangoli.',
           'cut_list': [{'profilo': '40×40×3', 'lunghezza_mm': 2040, 'tagli': '45°/45°', 'pezzi': 2},
                        {'profilo': '40×40×3', 'lunghezza_mm': 1040, 'tagli': '45°/45°', 'pezzi': 2}],
           'area_sezione_mm2': a, 'volume_mm3': vol, 'peso_kg': vol * DENS}
    (d / 'expected.json').write_text(json.dumps(exp, indent=2, ensure_ascii=False), encoding='utf-8')
    print('simple_frame_2000x1000:', cl['pieces'], 'pezzi,', f'{vol * DENS:.3f} kg')


def tavolo():
    d = OUT / 'table_frame'
    d.mkdir(parents=True, exist_ok=True)
    doc = templates.telaio('Tavolo 2000x1000x900')
    res = doc.rebuild()
    cl = cut_list(res.structures)
    righe = sorted((r['length_mm'], '/'.join(r['cuts']), r['qty']) for r in cl['rows'])
    assert righe == [(880.0, 'dritto/dritto', 4), (1040.0, '45°/45°', 2), (2040.0, '45°/45°', 2)], righe
    vol = sum(m.solid.volume for st in res.structures for m in st.members)
    a = _shs_area(40, 3)
    _uguale('volume tavolo', a * ((2040 - 40) * 2 + (1040 - 40) * 2 + 880 * 4), vol)
    step.export_project(doc, res, d / 'tavolo.step')
    project_io.save(doc, d / 'tavolo.steelcad', backup=False)
    exp = {'_nota': 'Tavolo: telaio sopra all’altezza H = 900 (asse), gambe sotto il telaio: 900 − 20 = 880.',
           'cut_list': [{'lunghezza_mm': l, 'tagli': t, 'pezzi': q} for l, t, q in righe],
           'metri_totali': (2040 * 2 + 1040 * 2 + 880 * 4) / 1000, 'volume_mm3': vol, 'peso_kg': vol * DENS}
    (d / 'expected.json').write_text(json.dumps(exp, indent=2, ensure_ascii=False), encoding='utf-8')
    print('table_frame:', cl['pieces'], 'pezzi,', f'{vol * DENS:.3f} kg')


def canalina():
    d = OUT / 'sheetmetal_u_2mm'
    d.mkdir(parents=True, exist_ok=True)
    T, R, K = 2.0, 2.0, 0.4
    doc = Document('Canalina U 500x300 sp2', 'S235')
    sk = doc.add_sketch('XY', 'Base')
    r = sk.rectangle(0, 0, 480, 290)
    sk.constrain('coincident', r['corners'][0], 'O')
    sk.dimension('length', r['bottom'], value=500)
    sk.dimension('length', r['left'], value=300)
    c = sk.circle((250, 150), 10)
    sk.dimension('diameter', c, value=20)
    sk.constrain('symmetric', r['corners'][0], r['corners'][2], sk.entities[c]['center'])
    doc.add_feature('sheet', 'Canalina', sketch=sk.id, thickness=T, radius=R, method='k', k=K, flanges=[
        {'id': 'FL1', 'edge': r['bottom'], 'length': 30, 'angle': 90, 'holes': [{'u': 100, 'v': 18, 'd': 8}]},
        {'id': 'FL2', 'edge': r['top'], 'length': 30, 'angle': 90}])
    res = doc.rebuild()
    if not res.ok:
        raise SystemExit(res.errors[0].message)
    sh = res.body.sheet
    BA = math.pi / 2 * (R + K * T)
    SB = R + T
    BD = 2 * SB - BA
    flat_y = 300 + 2 * (30 - BD)
    vol = 500 * (300 - 2 * SB) * T + 2 * math.pi / 4 * ((R + T) ** 2 - R ** 2) * 500 + 2 * (30 - SB) * T * 500 \
        - math.pi * 100 * T - math.pi * 16 * T
    s = bd.Solid(res.body.shape)
    _uguale('sviluppo X', 500, sh.flat_size[0])
    _uguale('sviluppo Y', flat_y, sh.flat_size[1])
    _uguale('volume', vol, s.volume)
    rep = dxf.export_flat_pattern(sh, d / 'canalina_sviluppo.dxf')
    step.export(res.body.shape, d / 'canalina.step', name='Canalina U')
    project_io.save(doc, d / 'canalina.steelcad', backup=False)
    exp = {
        '_nota': 'U 500 × 300, sp. 2, R interno 2, K 0,4 (dati scelti per il riferimento, non default). '
                 'BA = π/2 · (R + K·T); setback = R + T; BD = 2·setback − BA; sviluppo = 300 + 2·(30 − BD). '
                 'Volume = piano (300 − 2·setback) + 2 quarti di corona (π/4·((R+T)² − R²)) + 2 tratti dritti '
                 '(30 − setback) − fori Ø20 e Ø8, tutto × spessore × 500.',
        'ba_mm': BA, 'bd_mm': BD, 'setback_mm': SB, 'sviluppo_mm': [500, flat_y], 'volume_mm3': vol,
        'peso_kg': vol * DENS, 'ingombro_mm': [500, 300, 30],
        'dxf': {'contorni': rep['contours'], 'fori': rep['circle_diameters'], 'pieghe': rep['bend_lines']},
        'da_confermare': 'Confrontare con un pezzo piegato davvero sulla tua pressa: misura lo sviluppo '
                         'tagliato e l’altezza delle ali, e scrivi qui raggio e K reali.'}
    (d / 'expected.json').write_text(json.dumps(exp, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'sheetmetal_u_2mm: sviluppo 500 × {flat_y:.3f}, {vol * DENS:.3f} kg, DXF {rep["contours"]} contorni')


if __name__ == '__main__':
    telaio_semplice()
    tavolo()
    canalina()
    print('scritto in', OUT)
