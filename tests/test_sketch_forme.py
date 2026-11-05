"""Serie attorno a un centro e i nuovi modi di fare rettangoli e cerchi (05/11, idee da SolidCraft)."""
import math

import pytest

from app import sketch_edit as se
from app import sketch_forme as sf
from app import sketch_ops as so
from cad_engine.document import Document
from cad_engine.errors import SketchError
from cad_engine.sketch import solve


def _doc():
    d = Document('x')
    d.add_sketch('XY', 'S')
    return d, d.sketch('S1')


def _ss(d):
    return solve(d.sketch('S1'), d.resolved_parameters())


def _angoli(ss, sk, cerchi):
    out = []
    for c in cerchi:
        x, y = ss.points[sk.entities[c]['center']]
        out.append(round(math.degrees(math.atan2(y, x)) % 360, 6))
    return sorted(out)


# ---------------------------------------------------------------------------------------------- serie attorno
def test_serie_attorno_flangia_8_fori():
    d, sk = _doc()
    flangia = so.add_circle(d, 'S1', [0, 0], 100)
    foro = so.add_circle(d, 'S1', [80, 0], 5)
    nuove = se.pattern_circular(d, 'S1', [foro], sk.entities[flangia]['center'], 8, 360)
    assert len(nuove) == 7
    ss = _ss(d)
    assert ss.status.state == 'completo' and not ss.status.redundant
    fori = [foro] + nuove
    assert _angoli(ss, sk, fori) == [0, 45, 90, 135, 180, 225, 270, 315]
    assert all(ss.circles[c][1] == pytest.approx(5) for c in fori)
    assert d.parameters == {'ang1': 45}                    # l'angolo tra le copie: si cambia dopo
    d.set_parameter('ang1', 30)
    assert _angoli(_ss(d), sk, fori) == [0, 30, 60, 90, 120, 150, 180, 210]
    # il foro originale cambia diametro e si sposta: le copie seguono
    dia = next(k for k, c in sk.constraints.items() if c['type'] == 'diameter' and c['refs'] == [foro])
    sk.set_value(dia, 14)
    dx = next(k for k, c in sk.constraints.items() if c['type'] == 'hdistance' and c['value'] == 80)
    sk.set_value(dx, 70)
    ss = _ss(d)
    assert ss.status.state == 'completo'
    assert all(ss.circles[c][1] == pytest.approx(7) for c in fori)
    assert all(math.hypot(*ss.points[sk.entities[c]['center']]) == pytest.approx(70) for c in fori)


def test_serie_attorno_su_un_arco_e_centro_scritto():
    d, sk = _doc()
    r = so.add_rectangle(d, 'S1', [60, -10], [90, 10])
    nuove = se.pattern_circular(d, 'S1', r['lines'], [0, 0], 3, 90)      # 0°, 45°, 90°: agli estremi
    ss = _ss(d)
    assert ss.status.state == 'completo' and not ss.status.redundant and len(nuove) == 8
    assert d.parameters == {'ang1': 45}
    pts = {(round(x, 3), round(y, 3)) for x, y in ss.points.values()}
    assert {(-10, 60), (10, 90)} <= pts                     # la copia a 90°
    # l'originale si allunga: le copie girate anche
    dl = next(k for k, c in sk.constraints.items() if c['type'] == 'length' and c['value'] == 30)
    sk.set_value(dl, 40)
    pts = {(round(x, 3), round(y, 3)) for x, y in _ss(d).points.values()}
    assert {(-10, 60), (10, 100)} <= pts


def test_serie_attorno_errori():
    d, sk = _doc()
    c = so.add_circle(d, 'S1', [0, 0], 5)
    with pytest.raises(SketchError, match='sul centro'):
        se.pattern_circular(d, 'S1', [c], 'O', 6, 360)
    c2 = so.add_circle(d, 'S1', [50, 0], 5)
    with pytest.raises(SketchError, match='almeno 2'):
        se.pattern_circular(d, 'S1', [c2], 'O', 1, 360)
    with pytest.raises(SketchError, match='360'):
        se.pattern_circular(d, 'S1', [c2], 'O', 4, 400)


def test_serie_attorno_dal_servizio_e_annulla():
    from app.service import Service
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 300, 'spessore': 2, 'raggio': 1, 'k': 0.33})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_circle(sid, [150, 150], 100)['ok']
    assert s.sketch_add_circle(sid, [230, 150], 6)['ok']
    sk = s.doc.sketch(sid)
    fl = next(k for k, e in sk.entities.items() if e['kind'] == 'circle' and not e.get('ref') and e['r'] == 100)
    assert s.sketch_construction(sid, [fl], True)['ok']          # la circonferenza dei fori: una guida
    foro = next(k for k, e in sk.entities.items() if e['kind'] == 'circle' and not e.get('ref') and e['r'] == 6)
    r = s.sketch_pattern_circular(sid, [foro], sk.entities[fl]['center'], 6, 360)
    assert r['ok'], r.get('message')
    v = s.sketch_view(sid)['sketch']
    assert len([c for c in v['circles'] if not c.get('ref')]) == 7
    par = {p['name']: p for p in s.state()['parameters']}
    assert par['ang1']['value'] == 60 and par['ang1']['label'] == 'Angolo tra le copie (°)'
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')
    assert len(s.result.body.sheet.flat.inner_wires()) == 6


# ---------------------------------------------------------------------------------------------- rettangoli
def test_rettangolo_dal_centro():
    d, sk = _doc()
    r = sf.add_rectangle_center(d, 'S1', [50, 30], [80, 50])
    ss = _ss(d)
    assert ss.status.state == 'completo' and not ss.status.redundant
    xs = sorted({round(ss.points[p][0], 6) for p in r['corners']})
    ys = sorted({round(ss.points[p][1], 6) for p in r['corners']})
    assert xs == [20, 80] and ys == [10, 50]
    # cambiata la larghezza resta centrato
    dl = next(k for k, c in sk.constraints.items() if c['type'] == 'length' and c['value'] == 60)
    sk.set_value(dl, 100)
    ss = _ss(d)
    assert sorted({round(ss.points[p][0], 6) for p in r['corners']}) == [0, 100]


def test_rettangolo_dal_centro_sull_origine():
    d, sk = _doc()
    sf.add_rectangle_center(d, 'S1', 'O', [40, 25])
    ss = _ss(d)
    assert ss.status.state == 'completo' and not ss.status.redundant
    assert {(round(x, 6), round(y, 6)) for x, y in ss.points.values()} >= {(-40, -25), (40, 25)}


def test_rettangolo_a_tre_punti_storto():
    d, sk = _doc()
    a = math.radians(30)
    p2 = [10 + 100 * math.cos(a), 10 + 100 * math.sin(a)]
    p3 = [p2[0] - 40 * math.sin(a), p2[1] + 40 * math.cos(a)]
    r = sf.add_rectangle_3p(d, 'S1', [10, 10], p2, p3)
    ss = _ss(d)
    assert ss.status.state == 'completo' and not ss.status.redundant
    lati = [math.dist(*(ss.points[p] for p in ss.lines[l])) for l in r['lines']]
    assert lati == pytest.approx([100, 40, 100, 40])
    ang = next(k for k, c in sk.constraints.items() if c['type'] == 'angle')
    assert sk.constraints[ang]['value'] == pytest.approx(30)
    sk.set_value(ang, 45)                                   # lo giri con la quota dell'angolo
    ss = _ss(d)
    a0, b0 = (ss.points[p] for p in ss.lines[r['lines'][0]])
    assert math.degrees(math.atan2(b0[1] - a0[1], b0[0] - a0[0])) == pytest.approx(45)


def test_rettangolo_a_tre_punti_dritto():
    d, sk = _doc()
    sf.add_rectangle_3p(d, 'S1', [0, 0], [100, 0], [50, -30])     # larghezza verso il basso
    ss = _ss(d)
    assert ss.status.state == 'completo' and not ss.status.redundant
    assert not any(c['type'] == 'angle' for c in sk.constraints.values())
    assert min(y for _, y in ss.points.values()) == pytest.approx(-30)


def test_rettangolo_raccordato():
    d, sk = _doc()
    r = sf.add_rectangle_rounded(d, 'S1', [0, 0], [200, 100], 10)
    ss = _ss(d)
    assert ss.status.state == 'completo' and not ss.status.redundant
    assert all(ss.arcs[a][3] == pytest.approx(10) for a in r['arcs'])
    # quote fuori tutto: cambi larghezza e raggio
    W = next(k for k, c in sk.constraints.items() if c['type'] == 'hdistance' and c['value'] == 200)
    R = next(k for k, c in sk.constraints.items() if c['type'] == 'radius')
    sk.set_value(W, 250)
    sk.set_value(R, 20)
    ss = _ss(d)
    assert ss.status.state == 'completo'
    xs = [x for x, _ in ss.points.values()]
    assert min(xs) == pytest.approx(0) and max(xs) == pytest.approx(250)
    assert all(ss.arcs[a][3] == pytest.approx(20) for a in r['arcs'])
    with pytest.raises(SketchError, match='troppo grande'):
        sf.add_rectangle_rounded(d, 'S1', [0, 0], [50, 30], 15)


def test_rettangolo_raccordato_diventa_piastra():
    from app.service import Service
    s = Service()
    assert s.new_project('zero', {'name': 'Piastra'})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    assert s.sketch_add_rectangle_rounded(sid, [0, 0], [120, 80], 12)['ok']
    r = s.create_from_sketch(sid, 'plate', {'thickness': 5})
    assert r['ok'], r.get('message')
    v = s.sketch_view(sid)['sketch']
    assert len(v['arcs']) == 4 and len(v['lines']) == 4


# ---------------------------------------------------------------------------------------------- cerchi
def test_cerchio_per_tre_punti_liberi():
    d, sk = _doc()
    c = sf.add_circle_3p(d, 'S1', [10, 0], [0, 10], [-10, 0])
    ss = _ss(d)
    assert ss.status.state == 'completo' and not ss.status.redundant
    assert ss.circles[c][1] == pytest.approx(10) and ss.points[ss.circles[c][0]] == pytest.approx((0, 0))


def test_cerchio_per_tre_spigoli_resta_legato():
    d, sk = _doc()
    r = so.add_rectangle(d, 'S1', 'O', [80, 60])
    a, b, cc = r['corners'][:3]
    c = sf.add_circle_3p(d, 'S1', a, b, cc)
    ss = _ss(d)
    assert ss.status.state == 'completo' and not ss.status.redundant
    assert ss.circles[c][1] == pytest.approx(50)
    dl = next(k for k, x in sk.constraints.items() if x['type'] == 'length' and x['value'] == 80)
    sk.set_value(dl, 120)                                   # il rettangolo si allarga: il cerchio lo segue
    ss = _ss(d)
    assert ss.circles[c][1] == pytest.approx(math.hypot(120, 60) / 2)
    with pytest.raises(SketchError, match='in fila'):
        sf.add_circle_3p(d, 'S1', [0, 100], [10, 100], [20, 100])


def test_cerchio_tangente_a_due_linee():
    d, sk = _doc()
    r = so.add_rectangle(d, 'S1', 'O', [100, 60])
    c = sf.add_circle_tangent(d, 'S1', [r['bottom'], r['left']], 10, vicino=[30, 30])
    ss = _ss(d)
    assert ss.status.state == 'completo' and not ss.status.redundant
    assert ss.points[ss.circles[c][0]] == pytest.approx((10, 10)) and ss.circles[c][1] == pytest.approx(10)
    # dall'altra parte del mouse: fuori dal rettangolo
    c2 = sf.add_circle_tangent(d, 'S1', [r['bottom'], r['left']], 5, vicino=[-30, -30])
    assert _ss(d).points[_ss(d).circles[c2][0]] == pytest.approx((-5, -5))
    # il raggio è una quota: la cambi e resta tangente
    R = next(k for k, x in sk.constraints.items() if x['type'] == 'radius' and x['refs'] == [c])
    sk.set_value(R, 20)
    assert _ss(d).points[_ss(d).circles[c][0]] == pytest.approx((20, 20))


def test_cerchio_tangente_a_tre_linee():
    d, sk = _doc()
    r = so.add_rectangle(d, 'S1', 'O', [100, 60])
    # i clic sui lati sotto, sinistro e sopra: il cerchio grande che li tocca tutti e tre, a sinistra
    c = sf.add_circle_tangent(d, 'S1', [r['bottom'], r['left'], r['top']], clic=[[20, 0], [0, 30], [20, 60]])
    ss = _ss(d)
    assert ss.status.state == 'completo' and not ss.status.redundant
    assert ss.circles[c][1] == pytest.approx(30) and ss.points[ss.circles[c][0]] == pytest.approx((30, 30))
    H = next(k for k, x in sk.constraints.items() if x['type'] == 'length' and x['value'] == 60)
    sk.set_value(H, 80)                                     # il rettangolo cresce: il cerchio lo segue
    ss = _ss(d)
    assert ss.circles[c][1] == pytest.approx(40)


def test_cerchio_tangente_triangolo():
    d, sk = _doc()
    linee = so.add_polyline(d, 'S1', [[0, 0], [60, 0], [0, 80]], True)
    c = sf.add_circle_tangent(d, 'S1', linee, clic=[[20, 0], [30, 40], [0, 30]])
    ss = _ss(d)
    assert not ss.status.redundant and not ss.status.conflicting
    assert ss.circles[c][1] == pytest.approx(20)                 # inscritto nel 60-80-100: r = (60+80-100)/2
    assert ss.points[ss.circles[c][0]] == pytest.approx((20, 20))
