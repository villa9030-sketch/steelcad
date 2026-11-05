"""Linee guida pronte (05/11, idee da SolidCraft sketch.construction_line.*): orizzontale/verticale per un punto,
parallela a distanza, perpendicolare, ad angolo, bisettrice, tangente da un punto, tangente comune. Sono linee di
costruzione con vincoli veri: se la linea (o il cerchio) di partenza si sposta, la guida segue."""
import math

import pytest

from app import sketch_guide as sg
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


def _seg(ss, lid):
    a, b = ss.lines[lid]
    return ss.points[a], ss.points[b]


def _dir(p, q):
    L = math.dist(p, q)
    return (q[0] - p[0]) / L, (q[1] - p[1]) / L


def _croce(u, w):
    return u[0] * w[1] - u[1] * w[0]


def _dist_retta(p, a, b):
    u = _dir(a, b)
    return abs((p[0] - a[0]) * -u[1] + (p[1] - a[1]) * u[0])


def _quota(sk, tipo, ref=None):
    return next(k for k, c in sk.constraints.items() if c['type'] == tipo and (ref is None or ref in c['refs']))


def _pulito(ss):
    assert ss.status.state != 'non risolto'
    assert not ss.status.redundant and not ss.status.conflicting


def _storto(d):
    """Una linea storta, quotata: lunghezza 100 a 30° dall'orizzontale, che parte da (10, 20)."""
    lid = so.add_polyline(d, 'S1', [[10, 20], [10 + 100 * math.cos(math.radians(30)), 20 + 50]], False, False, [30])[0]
    return lid


# ---------------------------------------------------------------------------------------------- orizzontale/verticale
def test_guida_orizzontale_per_il_centro_di_un_foro_segue_il_foro():
    d, sk = _doc()
    c = so.add_circle(d, 'S1', [40, 30], 5)
    centro = sk.entities[c]['center']
    g = sg.add_guide(d, 'S1', 'hv', {'punto': centro, 'mouse': [90, 31]})
    assert sk.entities[g]['construction'] and sk.entities[g]['kind'] == 'line'
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    assert a[1] == pytest.approx(30) and b[1] == pytest.approx(30)
    assert (a[0] + b[0]) / 2 == pytest.approx(40)              # il centro è a metà della guida
    sk.set_value(_quota(sk, 'vdistance', centro), 45)            # il foro sale: la guida segue
    a, b = _seg(_ss(d), g)
    assert a[1] == pytest.approx(45) and b[1] == pytest.approx(45)


def test_guida_verticale_dal_mouse_e_punto_libero_con_posizione():
    d, sk = _doc()
    g = sg.add_guide(d, 'S1', 'hv', {'punto': [25, 10], 'mouse': [26, 70]})
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    assert a[0] == pytest.approx(25) and b[0] == pytest.approx(25)
    assert abs(b[1] - a[1]) == pytest.approx(120)                # lunga fino al mouse, da tutte e due le parti
    assert ss.status.state == 'completo'


# ---------------------------------------------------------------------------------------------- parallela
def test_parallela_a_distanza_segue_la_linea_e_la_quota_si_cambia():
    d, sk = _doc()
    L = _storto(d)
    g = sg.add_guide(d, 'S1', 'parallela', {'linea': L, 'distanza': 15, 'mouse': [0, 80]})
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    la, lb = _seg(ss, L)
    assert _croce(_dir(a, b), _dir(la, lb)) == pytest.approx(0, abs=1e-9)
    assert _dist_retta(a, la, lb) == pytest.approx(15) and _dist_retta(b, la, lb) == pytest.approx(15)
    assert math.dist(a, b) == pytest.approx(100)
    # dalla parte del mouse (sopra-sinistra della linea che sale verso destra)
    assert a[1] > la[1]
    # la quota «15» si vede ed è quella della distanza
    q = _quota(sk, 'pldistance')
    assert sk.constraints[q]['value'] == 15
    sk.set_value(q, 40)
    a, b = _seg(_ss(d), g)
    assert _dist_retta(a, la, lb) == pytest.approx(40)
    # la linea di partenza gira (angolo 30 → 45): la guida resta parallela
    ang = _quota(sk, 'angle')
    sk.set_value(ang, 45)
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    la, lb = _seg(ss, L)
    assert _croce(_dir(a, b), _dir(la, lb)) == pytest.approx(0, abs=1e-7)
    assert _dist_retta(a, la, lb) == pytest.approx(40)


def test_parallela_vuole_la_distanza():
    d, sk = _doc()
    L = _storto(d)
    with pytest.raises(SketchError):
        sg.add_guide(d, 'S1', 'parallela', {'linea': L, 'distanza': 0})


# ---------------------------------------------------------------------------------------------- perpendicolare
def test_perpendicolare_da_un_punto_parte_dalla_linea():
    d, sk = _doc()
    L = _storto(d)
    g = sg.add_guide(d, 'S1', 'perpendicolare', {'linea': L, 'punto': [20, 80]})
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    la, lb = _seg(ss, L)
    assert sum(x * y for x, y in zip(_dir(a, b), _dir(la, lb))) == pytest.approx(0, abs=1e-9)
    assert _dist_retta(a, la, lb) == pytest.approx(0, abs=1e-9)          # parte dalla linea
    assert ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) == pytest.approx((20, 80))   # e passa dal punto
    sk.set_value(_quota(sk, 'angle'), 10)                                # la linea gira: la guida resta a squadra
    ss = _ss(d)
    a, b = _seg(ss, g)
    la, lb = _seg(ss, L)
    assert sum(x * y for x, y in zip(_dir(a, b), _dir(la, lb))) == pytest.approx(0, abs=1e-7)


def test_perpendicolare_per_la_punta_della_linea():
    d, sk = _doc()
    L = _storto(d)
    punta = sk.entities[L]['b']
    g = sg.add_guide(d, 'S1', 'perpendicolare', {'linea': L, 'punto': punta, 'mouse': [0, 200]})
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    la, lb = _seg(ss, L)
    assert sum(x * y for x, y in zip(_dir(a, b), _dir(la, lb))) == pytest.approx(0, abs=1e-9)
    assert ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) == pytest.approx(lb)


# ---------------------------------------------------------------------------------------------- angolo
@pytest.mark.parametrize('mouse,verso', [([60, 120], 1), ([60, -60], -1)])
def test_guida_a_un_angolo_dalla_linea(mouse, verso):
    d, sk = _doc()
    L = so.add_polyline(d, 'S1', [[0, 0], [100, 0]], False)[0]
    p = sk.entities[L]['a']
    g = sg.add_guide(d, 'S1', 'angolo', {'linea': L, 'punto': p, 'angolo': 60, 'mouse': mouse})
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    u = _dir(a, b)
    ang = math.degrees(math.atan2(u[1], u[0])) % 180
    assert ang == pytest.approx(60 if verso == 1 else 120)
    q = _quota(sk, 'angle', g)
    assert sk.constraints[q]['value'] == 60
    sk.set_value(q, 30)
    a, b = _seg(_ss(d), g)
    u = _dir(a, b)
    assert math.degrees(math.atan2(u[1], u[0])) % 180 == pytest.approx(30 if verso == 1 else 150)


def test_guida_a_un_angolo_segue_la_linea_storta():
    d, sk = _doc()
    L = _storto(d)
    g = sg.add_guide(d, 'S1', 'angolo', {'linea': L, 'punto': sk.entities[L]['a'], 'angolo': 90, 'mouse': [0, 60]})
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    la, lb = _seg(ss, L)
    assert sum(x * y for x, y in zip(_dir(a, b), _dir(la, lb))) == pytest.approx(0, abs=1e-9)


def test_angolo_zero_non_va():
    d, sk = _doc()
    L = _storto(d)
    with pytest.raises(SketchError):
        sg.add_guide(d, 'S1', 'angolo', {'linea': L, 'punto': [0, 0], 'angolo': 0})


# ---------------------------------------------------------------------------------------------- bisettrice
def test_bisettrice_di_due_linee_con_lo_spigolo_in_comune():
    d, sk = _doc()
    l1, l2 = so.add_polyline(d, 'S1', [[100, 0], [0, 0], [0, 100]], False)
    g = sg.add_guide(d, 'S1', 'bisettrice', {'linee': [l1, l2], 'mouse': [50, 50]})
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    u = _dir(a, b)
    assert abs(u[0]) == pytest.approx(abs(u[1]))                      # a 45°
    assert ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) == pytest.approx((0, 0), abs=1e-9)


def test_bisettrice_di_linee_che_non_si_toccano_segue_le_linee():
    d, sk = _doc()
    l1 = so.add_polyline(d, 'S1', [[10, 0], [100, 0]], False)[0]
    l2 = _storto(d)                                                   # a 30°, da (10, 20)
    g = sg.add_guide(d, 'S1', 'bisettrice', {'linee': [l1, l2], 'mouse': [120, 30]})
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    u = _dir(a, b)
    assert math.degrees(math.atan2(u[1], u[0])) % 180 == pytest.approx(15)
    sk.set_value(_quota(sk, 'angle', l2), 50)                        # l'altra linea si alza: la bisettrice anche
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    u = _dir(a, b)
    assert math.degrees(math.atan2(u[1], u[0])) % 180 == pytest.approx(25)


def test_bisettrice_di_parallele_non_va():
    d, sk = _doc()
    l1 = so.add_polyline(d, 'S1', [[0, 0], [100, 0]], False)[0]
    l2 = so.add_polyline(d, 'S1', [[0, 30], [100, 30]], False)[0]
    with pytest.raises(SketchError, match='parallele'):
        sg.add_guide(d, 'S1', 'bisettrice', {'linee': [l1, l2]})


# ---------------------------------------------------------------------------------------------- tangenti
def test_tangente_da_un_punto_a_un_cerchio_segue_il_cerchio():
    d, sk = _doc()
    c = so.add_circle(d, 'S1', [100, 0], 30)
    g = sg.add_guide(d, 'S1', 'tangente', {'punto': [0, 0], 'cerchio': c, 'mouse': [80, 40]})
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    centro, r = ss.circles[c]
    cc = ss.points[centro]
    assert a == pytest.approx((0, 0), abs=1e-9)
    assert _dist_retta(cc, a, b) == pytest.approx(30)
    assert math.dist(b, cc) == pytest.approx(30)                    # finisce sul punto di tangenza
    assert b[1] > 0                                                 # quella dalla parte del mouse
    sk.set_value(_quota(sk, 'diameter', c), 100)                    # il cerchio si allarga: la guida resta tangente
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    assert _dist_retta(ss.points[centro], a, b) == pytest.approx(50)


def test_tangente_da_un_punto_dentro_il_cerchio_non_va():
    d, sk = _doc()
    c = so.add_circle(d, 'S1', [0, 0], 30)
    with pytest.raises(SketchError, match='dentro'):
        sg.add_guide(d, 'S1', 'tangente', {'punto': [5, 5], 'cerchio': c})


@pytest.mark.parametrize('mouse,incrociata', [([50, 35], False), ([50, -35], False), ([45, 5], True)])
def test_tangente_comune_a_due_cerchi(mouse, incrociata):
    d, sk = _doc()
    c1 = so.add_circle(d, 'S1', [0, 0], 20)
    c2 = so.add_circle(d, 'S1', [100, 0], 10)
    g = sg.add_guide(d, 'S1', 'tangente2', {'cerchi': [c1, c2], 'mouse': mouse})
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    (k1, r1), (k2, r2) = ss.circles[c1], ss.circles[c2]
    assert _dist_retta(ss.points[k1], a, b) == pytest.approx(20)
    assert _dist_retta(ss.points[k2], a, b) == pytest.approx(10)
    # esterna: i due centri dalla stessa parte; incrociata: da parti opposte
    lato = lambda p: (p[0] - a[0]) * (b[1] - a[1]) - (p[1] - a[1]) * (b[0] - a[0])  # noqa: E731
    stessa = lato(ss.points[k1]) * lato(ss.points[k2]) > 0
    assert stessa != incrociata
    # il cerchio piccolo si sposta: la tangente lo segue
    sk.set_value(next(k for k, c in sk.constraints.items() if c['type'] == 'hdistance' and c['value'] == 100), 140)
    ss = _ss(d)
    _pulito(ss)
    a, b = _seg(ss, g)
    assert _dist_retta(ss.points[k2], a, b) == pytest.approx(10)
    assert _dist_retta(ss.points[k1], a, b) == pytest.approx(20)


def test_tangente_comune_cerchio_dentro_l_altro_non_va():
    d, sk = _doc()
    c1 = so.add_circle(d, 'S1', [0, 0], 50)
    c2 = so.add_circle(d, 'S1', [5, 0], 10)
    with pytest.raises(SketchError):
        sg.add_guide(d, 'S1', 'tangente2', {'cerchi': [c1, c2]})


def test_geometria_per_l_anteprima_non_cambia_lo_sketch():
    d, sk = _doc()
    L = _storto(d)
    prima = (dict(sk.entities), dict(sk.constraints))
    g = sg.geometria(d, 'S1', 'parallela', {'linea': L, 'distanza': 10, 'mouse': [0, 100]})
    assert len(g['a']) == 2 and len(g['b']) == 2
    assert (dict(sk.entities), dict(sk.constraints)) == prima


@pytest.mark.parametrize('come', ['hv', 'parallela', 'perpendicolare', 'angolo', 'bisettrice', 'tangente', 'tangente2'])
def test_la_guida_non_lascia_niente_di_libero(come):
    """Una guida fatta su cose già ferme è ferma anche lei: lo sketch completo resta completo."""
    d, sk = _doc()
    l1 = _storto(d)
    l2 = so.add_polyline(d, 'S1', [[0, -40], [120, -40]], False)[0]
    c1 = so.add_circle(d, 'S1', [60, -100], 15)
    c2 = so.add_circle(d, 'S1', [150, -100], 8)
    ss = _ss(d)
    assert ss.status.state == 'completo'
    dati = {'hv': {'punto': sk.entities[l1]['a'], 'mouse': [80, 21]},
            'parallela': {'linea': l1, 'distanza': 12, 'mouse': [0, 90]},
            'perpendicolare': {'linea': l2, 'punto': sk.entities[l1]['b']},
            'angolo': {'linea': l2, 'punto': sk.entities[l2]['a'], 'angolo': 75, 'mouse': [10, 0]},
            'bisettrice': {'linee': [l1, l2], 'mouse': [-100, -40]},
            'tangente': {'punto': sk.entities[l2]['a'], 'cerchio': c1, 'mouse': [40, -80]},
            'tangente2': {'cerchi': [c1, c2], 'mouse': [100, -80]}}[come]
    sg.add_guide(d, 'S1', come, dati)
    ss = _ss(d)
    _pulito(ss)
    assert ss.status.state == 'completo', ss.status.message


def test_dal_servizio_con_anteprima_e_annulla():
    from app.service import Service
    s = Service()
    assert s.new_project('zero', {'name': 'G'})['ok']
    assert s.sketch_add_polyline('S1', [[0, 0], [100, 0]], False)['ok']
    sk = s.doc.sketch('S1')
    L = next(k for k, e in sk.entities.items() if e['kind'] == 'line')
    prima = len(sk.entities)
    pv = s.sketch_guide_preview('S1', 'parallela', {'linea': L, 'distanza': 25, 'mouse': [50, -10]})
    assert pv['ok'] and pv['a'][1] == pytest.approx(-25) and len(sk.entities) == prima    # l'anteprima non cambia niente
    r = s.sketch_add_guide('S1', 'parallela', {'linea': L, 'distanza': '25', 'mouse': [50, -10]})
    assert r['ok'], r
    assert s.doc.sketch('S1').entities[r['guida']]['construction']
    assert any(d['type'] == 'pldistance' and d['label'] == '25' for d in s.state()['dimensions'])
    assert s.undo()['ok']
    assert r['guida'] not in s.doc.sketch('S1').entities
    assert not s.sketch_add_guide('S1', 'boh', {})['ok']
    assert not s.sketch_add_guide('S1', 'parallela', {'linea': L, 'distanza': 'tanto'})['ok']
