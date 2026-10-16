"""GATE della Milestone 1.

Sketch XY → rettangolo 300 × 200 → foro Ø30 → estrusione 5 → 300 diventa 400 →
rigenerazione corretta → STEP → DXF. Valori confrontati con test_parts/.
"""
import json
import math
from pathlib import Path

import ezdxf
import pytest

from cad_engine import History
from cad_engine.analysis import properties
from cad_engine.exporters import dxf, step
from cad_engine import project_io

from conftest import FORO, plate

ATTESI = json.loads((Path(__file__).resolve().parents[1] / 'test_parts' / 'plate_300x200_hole30' / 'expected.json')
                    .read_text(encoding='utf-8'))


def _check_plate(body, att):
    p = properties(body.shape, 'S235')
    assert p['volume_mm3'] == pytest.approx(att['volume_mm3'], rel=1e-9)
    assert p['mass_kg'] == pytest.approx(att['mass_kg'], rel=1e-9)
    assert p['bbox_mm']['size'] == pytest.approx(att['bbox_mm'], abs=1e-6)
    return p


def test_gate_milestone_1(tmp):
    doc, sk, r, c, ids, e1 = plate()
    res = doc.rebuild()
    assert res.ok, [f.message for f in res.errors]
    assert res.features[0].sketch_status['state'] == 'completo'
    assert res.features[0].message == 'Lo sketch è completamente vincolato.'
    _check_plate(res.body, ATTESI['300'])

    # il foro è al centro perché è simmetrico rispetto agli angoli
    ss = doc.solved_sketch(sk.id)
    assert ss.points[sk.entities[c]['center']] == pytest.approx((150, 100), abs=1e-7)

    # 300 → 400: si rigenera tutto ciò che dipende dalla larghezza
    hist = History(doc)
    with hist.change('Larghezza 300 → 400'):
        doc.set_parameter('larghezza', 400)
    res = doc.rebuild()
    assert res.ok
    _check_plate(res.body, ATTESI['400'])
    ss = doc.solved_sketch(sk.id)
    assert ss.points[sk.entities[c]['center']] == pytest.approx((200, 100), abs=1e-7)

    # STEP: vera geometria, stesso volume rileggendo
    st = step.export(res.body.shape, tmp / 'piastra.step', name='Piastra 400x200')
    assert st['solids'] == 1
    assert st['volume_mm3'] == pytest.approx(ATTESI['400']['volume_mm3'], rel=1e-9)

    # DXF: contorno chiuso 400 x 200, un foro Ø30, mm, layer CUT
    rep = dxf.export_flat(res.body.shape, tmp / 'piastra.dxf')
    assert rep['ok'] and not rep['problems']
    assert rep['size_mm'] == pytest.approx([400, 200], abs=1e-6)
    assert rep['circle_diameters'] == [30.0]
    assert rep['contours'] == 2
    assert rep['thickness_mm'] == pytest.approx(5)
    d = ezdxf.readfile(tmp / 'piastra.dxf')
    assert d.header['$INSUNITS'] == 4
    assert {e.dxf.layer for e in d.modelspace()} == {'CUT'}
    assert {'CUT', 'BEND', 'MARK', 'ENGRAVE'} <= {l.dxf.name for l in d.layers}

    # undo riporta 300, redo 400
    assert hist.undo() == 'Larghezza 300 → 400'
    _check_plate(doc.rebuild().body, ATTESI['300'])
    hist.redo()
    _check_plate(doc.rebuild().body, ATTESI['400'])

    # il progetto salvato si ricostruisce identico
    path = project_io.save(doc, tmp / 'piastra')
    doc2 = project_io.load(path)
    _check_plate(doc2.rebuild().body, ATTESI['400'])


def test_quota_modificata_direttamente():
    """Clic sulla quota 200, scrivo 250, Invio."""
    doc, sk, r, c, ids, e1 = plate()
    doc.rebuild()
    hist = History(doc)
    with hist.change('Altezza 200 → 250'):
        sk.set_value(ids['h'], 250)
    p = properties(doc.rebuild().body.shape, 'S235')
    assert p['volume_mm3'] == pytest.approx(300 * 250 * 5 - FORO * 5, rel=1e-12)
    assert p['bbox_mm']['size'] == pytest.approx([300, 250, 5], abs=1e-6)


def test_rigenera_solo_quello_che_cambia():
    doc, sk, r, c, ids, e1 = plate()
    res = doc.rebuild()
    assert (res.rebuilt, res.cached) == (2, 0)
    res = doc.rebuild()
    assert (res.rebuilt, res.cached) == (0, 2)
    doc.edit_feature(e1, distance=8)          # cambia solo lo spessore: lo sketch resta in cache
    res = doc.rebuild()
    assert (res.rebuilt, res.cached) == (1, 1)
    doc.set_parameter('nonusato', 7)          # un parametro che nessuno usa non ricostruisce niente
    res = doc.rebuild()
    assert (res.rebuilt, res.cached) == (0, 2)


def test_valori_attesi_coerenti():
    """I valori in test_parts sono calcolati a mano: controlliamo il conto."""
    for w in ('300', '400'):
        v = int(w) * 200 * 5 - FORO * 5
        assert ATTESI[w]['volume_mm3'] == pytest.approx(v, rel=1e-12)
        assert ATTESI[w]['mass_kg'] == pytest.approx(v / 1e6 * 7.85, rel=1e-12)


def test_tempo_di_rigenerazione():
    doc, *_ = plate()
    doc.rebuild()
    doc.set_parameter('larghezza', 410)
    res = doc.rebuild()
    assert res.seconds < 1.0, f'rigenerazione troppo lenta: {res.seconds:.3f} s'
    assert math.isfinite(res.seconds)
