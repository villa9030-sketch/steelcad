"""03/11 — «Arco col raggio»: dopo una linea l'arco parte dalla sua fine, col raggio scritto e quanto gira (90°, mezzo
giro, altro), tangente o a squadra. Niente punti cliccati sulla griglia: il collare 28 + R55 mezzo giro + 28 viene
166 × 58 di fuori tutto (con l'arco a tre punti cliccato veniva 166 × 57 e pieghe storte)."""
import math

import build123d as bd
import pytest

from app import sketch_ops
from app.service import Service
from app.sketch_more import arco_raggio_punti


def _linea(s, sid, a, b):
    assert s.sketch_add_polyline(sid, [a, b], False)['ok']
    sk = s.doc.sketch(sid)
    lid = max((k for k, e in sk.entities.items() if e['kind'] == 'line' and not e.get('ref')), key=lambda k: int(k[1:]))
    return lid, sk.entities[lid]['b']


def _nuovo():
    s = Service()
    assert s.new_project('zero', {'name': 'Collare'})['ok']
    return s, next(f.id for f in s.doc.features if hasattr(f, 'entities'))


def test_collare_con_l_arco_scritto_fuori_tutto_166():
    s, sid = _nuovo()
    lid, fine = _linea(s, sid, [0, 0], [28, 0])
    r = s.sketch_add_arc_raggio(sid, lid, fine, '55', 180, 'squadra', 1)
    assert r['ok'], r.get('message')
    assert s.sketch_add_polyline(sid, [r['end'], [166, 0]], False)['ok']
    v = sketch_ops.view(s.doc, sid, s.result.body)
    (a,) = v['arcs']
    assert a['xc'] == [83, 0] and a['r'] == 55 and abs(a['a1'] - a['a0'] - math.pi) < 1e-12
    assert sorted((l['xa'], l['xb']) for l in v['lines'] if not l['ref']) == [([0, 0], [28, 0]), ([138, 0], [166, 0])]
    r = s.create_from_sketch(sid, 'profilo', {'lunghezza': 30, 'spessore': 3, 'calandra': True, 'gira': True, 'raggio': 1, 'k': 0.4})
    assert r['ok'], r.get('message')
    b = bd.Solid(s.result.body.shape).bounding_box()
    assert abs(b.size.X - 166) < 0.01 and abs(b.size.Y - 58) < 0.01
    righe = s.result.body.sheet.bend_rows
    assert len(righe) == 2 and abs(righe[0]['angle'] - righe[1]['angle']) < 1e-6     # le due pieghe uguali


def test_raggio_che_cambia_dopo_resta_a_squadra():
    """Le quote restano vive: cambiando il raggio a 60 l'arco resta a mezzo giro, col centro sulla linea."""
    s, sid = _nuovo()
    lid, fine = _linea(s, sid, [0, 0], [28, 0])
    assert s.sketch_add_arc_raggio(sid, lid, fine, 55, 180, 'squadra', 1)['ok']
    sk = s.doc.sketch(sid)
    dim = next(k for k, c in sk.constraints.items() if c['type'] == 'radius')
    assert s.set_dimension(sid, dim, '60')['ok']
    (a,) = sketch_ops.view(s.doc, sid, s.result.body)['arcs']
    assert abs(a['r'] - 60) < 1e-6 and abs(a['xc'][1]) < 1e-6 and abs(a['a1'] - a['a0'] - math.pi) < 1e-6


@pytest.mark.parametrize('partenza,lato,giro,centro,fine', [
    ('tangente', 1, 90, (28, 10), (38, 10)),      # continua la linea e gira a sinistra (in su)
    ('tangente', -1, 90, (28, -10), (38, -10)),   # a destra (in giù)
    ('squadra', 1, 180, (38, 0), (48, 0)),        # parte in su a 90°, mezzo giro: torna sulla linea
    ('squadra', -1, 90, (38, 0), (38, -10)),      # parte in giù, un quarto di giro
])
def test_dove_va_l_arco(partenza, lato, giro, centro, fine):
    c, e, _ = arco_raggio_punti((0, 0), (28, 0), 10, giro, partenza, lato)
    assert all(abs(p - q) < 1e-9 for p, q in zip(c + e, centro + fine))


def test_arco_tangente_resta_tangente():
    s, sid = _nuovo()
    lid, fine = _linea(s, sid, [0, 0], [0, 40])
    r = s.sketch_add_arc_raggio(sid, lid, fine, 20, 90, 'tangente', -1)
    assert r['ok'], r.get('message')
    sk = s.doc.sketch(sid)
    assert any(c['type'] == 'tangent' for c in sk.constraints.values())
    (a,) = sketch_ops.view(s.doc, sid, s.result.body)['arcs']
    assert [round(x, 9) for x in a['xc']] == [20, 40] and abs(a['r'] - 20) < 1e-9


def test_arco_senza_linea_o_raggio_sbagliato_lo_dice():
    s, sid = _nuovo()
    lid, fine = _linea(s, sid, [0, 0], [28, 0])
    assert 'raggio' in s.sketch_add_arc_raggio(sid, lid, fine, 0, 180, 'squadra', 1)['message']
    assert 'fine' in s.sketch_add_arc_raggio(sid, lid, 'O', 10, 180, 'squadra', 1)['message']
