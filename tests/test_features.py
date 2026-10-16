"""Tasca, aggiunta, foro, raccordo, smusso, sketch su faccia; nomi topologici stabili."""
import math

import pytest

from cad_engine.analysis import properties
from cad_engine.features.base import volume

from conftest import FORO, plate


def vol(doc):
    res = doc.rebuild()
    assert res.ok, [f.message for f in res.errors]
    return volume(res.body.shape)


def test_tasca_passante_e_cieca():
    doc, *_ = plate()
    sk = doc.add_sketch('XY', 'Tasca')
    sk.polyline([(20, 20), (60, 20), (60, 60), (20, 60)], closed=True)
    e2 = doc.add_feature('extrude', 'Tasca', sketch=sk.id, through_all=True, operation='cut', symmetric=True)
    assert vol(doc) == pytest.approx(300 * 200 * 5 - FORO * 5 - 40 * 40 * 5, rel=1e-9)
    doc.edit_feature(e2, through_all=False, symmetric=False, distance=2)
    assert vol(doc) == pytest.approx(300 * 200 * 5 - FORO * 5 - 40 * 40 * 2, rel=1e-9)


def test_tasca_che_non_tocca_il_pezzo():
    doc, *_ = plate()
    sk = doc.add_sketch('XY')
    sk.polyline([(500, 20), (560, 20), (560, 60), (500, 60)], closed=True)
    doc.add_feature('extrude', 'Lontana', sketch=sk.id, distance=5, operation='cut')
    res = doc.rebuild()
    assert not res.ok
    assert 'non tocca il pezzo' in res.errors[0].message


def test_aggiungi_e_parte_staccata():
    doc, *_ = plate()
    sk = doc.add_sketch('XY')
    sk.polyline([(0, 0), (50, 0), (50, 50), (0, 50)], closed=True)
    e2 = doc.add_feature('extrude', 'Rialzo', sketch=sk.id, distance=15, operation='add')
    assert vol(doc) == pytest.approx(300 * 200 * 5 - FORO * 5 + 50 * 50 * 10, rel=1e-9)
    sk.move_point('P1', 400, 0)
    for p, (x, y) in zip(('P2', 'P3', 'P4'), ((450, 0), (450, 50), (400, 50))):
        sk.move_point(p, x, y)
    res = doc.rebuild()
    assert not res.ok and 'staccato' in res.errors[0].message


def test_foro_passante_su_faccia_e_foro_cieco():
    doc, *_ = plate()
    sk = doc.add_sketch({'face': 'E1/fine'}, 'Fori')
    p1 = sk.point(30, 30)
    p2 = sk.point(270, 30)
    h1 = doc.add_feature('hole', 'Fori di fissaggio', sketch=sk.id, points=[p1, p2], diameter=9, through=True)
    assert vol(doc) == pytest.approx(300 * 200 * 5 - FORO * 5 - 2 * math.pi * 4.5 ** 2 * 5, rel=1e-9)
    doc.edit_feature(h1, through=False, depth=3)
    assert vol(doc) == pytest.approx(300 * 200 * 5 - FORO * 5 - 2 * math.pi * 4.5 ** 2 * 3, rel=1e-9)
    names = doc.last.body.names
    assert names.get(f'{h1}/foro/{p1}') and names.get(f'{h1}/fondo/{p2}')


def test_foro_fuori_dal_pezzo():
    doc, *_ = plate()
    sk = doc.add_sketch({'face': 'E1/fine'})
    p = sk.point(600, 30)
    doc.add_feature('hole', sketch=sk.id, points=[p], diameter=9)
    res = doc.rebuild()
    assert not res.ok and 'non tocca il pezzo' in res.errors[0].message


def test_raccordo_resta_sullo_stesso_spigolo_dopo_le_modifiche():
    doc, sk, r, c, ids, e1 = plate()
    spigolo = {'faces': sorted([f'{e1}/lato/{r["bottom"]}', f'{e1}/lato/{r["right"]}'])}
    doc.add_feature('fillet', 'Angolo', edges=[spigolo], radius=10)
    perso = 100 - math.pi * 25          # (1 - pi/4) * R^2
    assert vol(doc) == pytest.approx(300 * 200 * 5 - FORO * 5 - perso * 5, rel=1e-9)
    # cambio di misura: il raccordo è ancora sullo spigolo in basso a destra
    doc.set_parameter('larghezza', 450)
    v = vol(doc)
    assert v == pytest.approx(450 * 200 * 5 - FORO * 5 - perso * 5, rel=1e-9)
    bb = properties(doc.last.body.shape, 'S235')['bbox_mm']
    assert bb['size'] == pytest.approx([450, 200, 5], abs=1e-6)
    # un foro in più non sposta il raccordo
    s2 = doc.add_sketch({'face': f'{e1}/fine'})
    p = s2.point(40, 150)
    doc.add_feature('hole', sketch=s2.id, points=[p], diameter=10)
    assert vol(doc) == pytest.approx(v - math.pi * 25 * 5, rel=1e-9)
    raccordi = doc.last.body.names['F1/raccordo/1']
    from cad_engine.analysis.measure import properties as pr
    centro = pr(raccordi[0], 'S235')['bbox_mm']
    assert centro['max'][0] == pytest.approx(450, abs=1e-6) and centro['min'][1] == pytest.approx(0, abs=1e-6)


def test_raccordo_troppo_grande():
    doc, sk, r, c, ids, e1 = plate()
    doc.add_feature('fillet', edges=[{'faces': sorted([f'{e1}/lato/{r["bottom"]}', f'{e1}/lato/{r["right"]}'])}],
                    radius=300)
    res = doc.rebuild()
    assert not res.ok
    m = res.errors[0].message
    assert m.startswith('Il raccordo R300 non si può fare') and '200 mm' in m


def test_smusso_sugli_spigoli_sopra():
    doc, sk, r, c, ids, e1 = plate()
    lati = [r['bottom'], r['right'], r['top'], r['left']]
    doc.add_feature('chamfer', 'Bisello', edges=[{'faces': sorted([f'{e1}/fine', f'{e1}/lato/{l}'])} for l in lati],
                    distance=1)
    perimetro = 2 * (300 + 200)
    atteso = 300 * 200 * 5 - FORO * 5 - perimetro * 0.5
    # agli angoli gli smussi si incontrano: correzione dei 4 spigoli d'angolo (piramidi)
    assert vol(doc) == pytest.approx(atteso + 4 * (1 / 3), rel=1e-6)


def test_riferimento_perso_detto_chiaramente():
    doc, sk, r, c, ids, e1 = plate()
    doc.add_feature('fillet', edges=[{'faces': [f'{e1}/lato/L9', f'{e1}/fine']}], radius=2)
    res = doc.rebuild()
    assert not res.ok
    assert 'non esiste più' in res.errors[0].message


def test_feature_dopo_un_errore_non_costruita():
    doc, *_ = plate()
    doc.add_feature('fillet', edges=[{'faces': ['E1/lato/L9', 'E1/fine']}], radius=2)
    doc.add_feature('chamfer', edges=[{'faces': ['E1/lato/L1', 'E1/fine']}], distance=1)
    res = doc.rebuild()
    assert res.features[-1].message.startswith('Non costruita: prima va sistemato l\'errore in F1')


def test_peso_per_materiale():
    for mat, dens in (('S235', 7.85), ('AISI304', 7.90), ('AL6082', 2.70)):
        doc, *_ = plate(material=mat)
        p = properties(doc.rebuild().body.shape, mat)
        assert p['mass_kg'] == pytest.approx((300 * 200 * 5 - FORO * 5) / 1e6 * dens, rel=1e-12)
