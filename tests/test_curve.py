"""05/11 (idee da SolidCraft): ellissi e curve libere nello sketch, in tutta la catena: disegno, risolutore, pezzo 3D,
sviluppo, DXF per il laser (in archi tangenti, come li vuole Lantek), DXF letto, file salvati."""
import math
import os
import tempfile

import ezdxf
import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402
from app import sketch_curve, sketch_edit, sketch_ops  # noqa: E402
from cad_engine.errors import SketchError  # noqa: E402
from cad_engine.importers import dxf_import  # noqa: E402
from cad_engine.sketch import curve as cv  # noqa: E402
from cad_engine.sketch import solve  # noqa: E402
from cad_engine.sketch.model import Sketch  # noqa: E402
from cad_engine.sketch.solver import misura  # noqa: E402


def _volume(s):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(s.result.body.shape, g)
    return g.Mass()


def _distanza_dai_pezzi(pezzi, q):
    """Quanto il punto q sta lontano dalla catena di linee e archi (per tre punti)."""
    best = math.inf
    for p in pezzi:
        if p[0] == 'L':
            (ax, ay), (bx, by) = p[1], p[2]
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / (dx * dx + dy * dy)))
            best = min(best, math.hypot(ax + t * dx - q[0], ay + t * dy - q[1]))
            continue
        c = cv.centro3(p[1], p[2], p[3])
        r = math.dist(c, p[1])
        t0, tm, t1 = (math.atan2(x[1] - c[1], x[0] - c[0]) for x in (p[1], p[2], p[3]))
        sw = (t1 - t0) % (2 * math.pi)
        if not (tm - t0) % (2 * math.pi) < sw:
            t0, sw = t1, 2 * math.pi - sw
        a = math.atan2(q[1] - c[1], q[0] - c[0])
        if (a - t0) % (2 * math.pi) <= sw:
            best = min(best, abs(math.dist(q, c) - r))
        else:
            best = min(best, math.dist(q, p[1]), math.dist(q, p[3]))
    return best


# ------------------------------------------------------------------------------------------------ i conti
def test_curva_libera_passa_per_i_punti_ed_e_liscia():
    pts = [(0, 0), (50, 40), (120, -10), (200, 60), (260, 0)]
    bz = cv.spline_bezier(pts)
    assert [b[0] for b in bz] + [bz[-1][3]] == pts
    for b1, b2 in zip(bz, bz[1:]):           # tangente continua: le maniglie di qua e di là in fila col punto
        d1 = cv.bezier_derivata(b1, 1.0)
        d2 = cv.bezier_derivata(b2, 0.0)
        assert abs(d1[0] * d2[1] - d1[1] * d2[0]) < 1e-6 * math.hypot(*d1) * math.hypot(*d2)
    chiusa = cv.spline_bezier(pts[:4], True)
    assert len(chiusa) == 4 and chiusa[-1][3] == pts[0]


@pytest.mark.parametrize('toll', [0.01, 0.05])
def test_ellisse_e_curva_in_archi_tangenti_entro_la_tolleranza(toll):
    c, a, b, ang = (10, 5), 200, 60, 0.3
    m = cv.ellisse_punto(c, a, b, ang, 0)
    n = cv.ellisse_punto(c, a, b, ang, math.pi / 2)
    pezzi = cv.ellisse_in_archi(c, m, n, toll=toll)
    assert all(p[0] == 'A' for p in pezzi)
    for i in range(2000):
        assert _distanza_dai_pezzi(pezzi, cv.ellisse_punto(c, a, b, ang, 2 * math.pi * i / 2000)) <= toll
    for p, q in zip(pezzi, pezzi[1:] + pezzi[:1]):      # catena chiusa senza fessure
        assert math.dist(p[-1], q[1]) < 1e-9
    pts = [(0, 0), (50, 40), (120, -10), (200, 60)]
    bz = cv.spline_bezier(pts, True)
    pz = cv.spline_in_archi(pts, True, toll)
    for b_ in bz:
        for i in range(200):
            assert _distanza_dai_pezzi(pz, cv.bezier_punto(b_, i / 200)) <= toll


# ------------------------------------------------------------------------------------------------ risolutore
def test_ellisse_quotata_con_i_due_assi_e_l_inclinazione():
    sk = Sketch('S1')
    el = sk.ellipse((0, 0), (100, 0), 40)
    e = sk.entities[el]
    sk.constrain('coincident', e['center'], 'O')
    for t, v in (('major_axis', 300), ('minor_axis', 120), ('tilt', 30)):
        sk.dimension(t, el, value=v)
    ss = solve(sk)
    assert ss.status.state == 'completo'
    a, b, ang = cv.ellisse_assi(*(ss.points[e[k]] for k in ('center', 'major', 'minor')))
    assert (round(a, 6), round(b, 6), round(math.degrees(ang), 6)) == (150, 60, 30)
    assert [round(misura(ss, c), 6) for c in sk.constraints.values() if c['type'] in ('major_axis', 'minor_axis', 'tilt')] == [300, 120, 30]


def test_il_piu_lungo_diventa_l_asse_grande():
    sk = Sketch('S1')
    el = sk.ellipse((0, 0), (0, 50), 120)               # cliccato prima l'asse corto, in verticale
    e = sk.entities[el]
    a, b, ang = cv.ellisse_assi(*((sk.entities[e[k]]['x'], sk.entities[e[k]]['y']) for k in ('center', 'major', 'minor')))
    assert (round(a, 9), round(b, 9)) == (120, 50)
    with pytest.raises(SketchError, match='cerchio'):
        sk.ellipse((0, 0), (50, 0), 50)


def test_punti_della_curva_libera_sono_punti_normali():
    """Coincidente e quote sui punti di passaggio: la curva li segue."""
    sk = Sketch('S1')
    sp = sk.spline([(0, 0), (50, 40), (100, 0), (150, 30)])
    p = sk.entities[sp]['points']
    sk.constrain('coincident', p[0], 'O')
    sk.dimension('hdistance', p[0], p[-1], value=200)
    sk.dimension('vdistance', p[0], p[1], value=60)
    ss = solve(sk)
    assert ss.points[p[-1]][0] == pytest.approx(200) and ss.points[p[1]][1] == pytest.approx(60)
    assert ss.splines == {sp: (p, False)}


def test_punto_sull_ellisse_e_linea_tangente():
    sk = Sketch('S1')
    el = sk.ellipse((0, 0), (100, 0), 50)
    e = sk.entities[el]
    for k in ('center',):
        sk.constrain('fix', e[k])
    sk.dimension('major_axis', el, value=200)
    sk.dimension('minor_axis', el, value=100)
    sk.constrain('horizontal', e['center'], e['major'])
    q = sk.point(80, 40)
    sk.constrain('on_line', q, el)
    a_, b_ = sk.point(-150, 80), sk.point(150, 70)
    ln = sk.line(a_, b_)
    sk.constrain('horizontal', ln)
    sk.constrain('tangent', ln, el)
    ss = solve(sk)
    x, y = ss.points[q]
    assert (x / 100) ** 2 + (y / 50) ** 2 == pytest.approx(1, abs=1e-7)
    assert ss.points[a_][1] == pytest.approx(50, abs=1e-6)          # la linea orizzontale tocca l'ellisse in cima


# ------------------------------------------------------------------------------------------------ catena intera
def _sopraluce():
    """Mezza ellisse 800 × 600 sopra tre lati di un rettangolo, dentro una goccia (curva libera chiusa) e un'ellisse."""
    s = Service()
    assert s.new_project('zero', {})['ok']
    assert s.sketch_add_polyline('S1', [[-400, 0], [-400, -300], [400, -300], [400, 0]], False)['ok']
    sk = s.doc.sketch('S1')
    angolo = lambda x: next(k for k, e in sk.entities.items() if e['kind'] == 'point' and k != 'O'  # noqa: E731
                            and abs(e['x'] - x) < 1e-6 and abs(e['y']) < 1e-6)
    r = s.sketch_add_ellipse('S1', 'O', [400, 0], 300, angolo(400), angolo(-400))
    assert r['ok'], r
    assert s.sketch_add_spline('S1', [[-250, -60], [-180, -140], [-250, -240], [-320, -140]], True)['ok']
    assert s.sketch_add_ellipse('S1', [200, -150], [300, -150], 50)['ok']
    return s


def test_sopraluce_piastra_dxf_solo_archi_e_linee(tmp_path):
    s = _sopraluce()
    v = s.sketch_view('S1')['sketch']
    assert v['profiles'] == 1 and not v['sciolte']
    assert sorted((c['kind'], c['closed']) for c in v['curves']) == [('ellipse', False), ('ellipse', True), ('spline', True)]
    assert s.create_from_sketch('S1', 'plate', {'thickness': 5})['ok']
    q = cv.spline_campioni([[-250, -60], [-180, -140], [-250, -240], [-320, -140]], True, 400)
    goccia = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(q, q[1:] + q[:1]))) / 2
    assert _volume(s) == pytest.approx(5 * (800 * 300 + math.pi * 400 * 300 / 2 - goccia - math.pi * 100 * 50), rel=1e-5)
    r = s.export_dxf(str(tmp_path / 'p.dxf'))
    assert r['ok'], r
    doc = ezdxf.readfile(tmp_path / 'p.dxf')
    tipi = {e.dxftype() for e in doc.modelspace()}
    assert tipi <= {'LINE', 'ARC'}, tipi                # niente spline né polilinee: Lantek vuole linee e archi
    rep = __import__('cad_engine.exporters.dxf', fromlist=['check']).check(tmp_path / 'p.dxf')
    assert rep['ok'] and rep['contours'] == 3
    assert rep['size_mm'][0] == pytest.approx(800, abs=0.01) and rep['size_mm'][1] == pytest.approx(600, abs=0.01)
    # il DXF del disegno (Salva in DXF) le ha uguali
    r = s.sketch_export_dxf('S1', str(tmp_path / 's.dxf'))
    assert r['ok'] and 'archi tangenti' in r['message']
    assert {e.dxftype() for e in ezdxf.readfile(tmp_path / 's.dxf').modelspace()} <= {'LINE', 'ARC'}


def test_lamiera_con_ellisse_sviluppo_e_dxf(tmp_path):
    s = Service()
    assert s.new_project('zero', {})['ok']
    assert s.sketch_add_ellipse('S1', 'O', [250, 0], 100)['ok']
    assert s.sketch_add_spline('S1', [[-80, 0], [0, 50], [80, 0], [0, -40]], True)['ok']
    assert s.create_from_sketch('S1', 'sheet', {'thickness': 2})['ok']
    r = s.export_dxf(str(tmp_path / 'l.dxf'))
    assert r['ok'] and '500 × 200' in r['message'], r


def test_file_salvato_si_riapre_uguale(tmp_path):
    s = _sopraluce()
    assert s.create_from_sketch('S1', 'plate', {'thickness': 5})['ok']
    p = tmp_path / 'c.steelcad'
    assert s.save(str(p))['ok']
    s2 = Service()
    assert s2.open(str(p))['ok']
    assert _volume(s2) == pytest.approx(_volume(s), rel=1e-9)


def test_trascina_punto_curva_e_assi_dell_ellisse():
    s = _sopraluce()
    sk = s.doc.sketch('S1')
    sp = next(k for k, e in sk.entities.items() if e['kind'] == 'spline')
    pid = sk.entities[sp]['points'][1]
    assert s.sketch_move_point('S1', pid, [-150, -150])['ok']
    assert solve(s.doc.sketch('S1')).points[pid] == pytest.approx((-150, -150))
    el = next(k for k, e in s.doc.sketch('S1').entities.items() if e['kind'] == 'ellipse' and 'start' not in e)
    e = s.doc.sketch('S1').entities[el]
    assert s.sketch_move_point('S1', e['minor'], [200, -110])['ok']                  # più alta: asse piccolo 80
    assert [c['value'] for c in s.doc.sketch('S1').constraints.values() if c['type'] == 'minor_axis' and c['refs'] == [el]] == [80]
    assert s.sketch_move_point('S1', e['center'], [150, -150])['ok']                 # il centro la sposta tutta
    ss = solve(s.doc.sketch('S1'))
    assert ss.points[e['center']] == pytest.approx((150, -150)) and ss.points[e['major']] == pytest.approx((250, -150))
    r = s.sketch_move_point('S1', e['minor'], [150, 0])
    assert not r['ok'] and 'asse piccolo' in r['message']


def test_elimina_un_punto_della_curva_libera():
    d = Service()
    assert d.new_project('zero', {})['ok']
    r = d.sketch_add_spline('S1', [[0, 0], [50, 40], [100, 0], [150, 30]], False)
    sk = d.doc.sketch('S1')
    p = sk.entities[r['id']]['points']
    sketch_ops.delete(d.doc, 'S1', [p[1]])
    assert sk.entities[r['id']]['points'] == [p[0], p[2], p[3]]
    sketch_ops.delete(d.doc, 'S1', [p[2], p[3]])
    assert r['id'] not in sk.entities                    # con un punto solo non è più una curva


def test_copia_specchio_e_serie_di_curve():
    d = Service()
    assert d.new_project('zero', {})['ok']
    el = d.sketch_add_ellipse('S1', [100, 0], [160, 0], 20, [160, 0], [40, 0])['id']
    sp = d.sketch_add_spline('S1', [[100, 40], [130, 70], [160, 40]], False)['id']
    sketch_edit.copy(d.doc, 'S1', [el, sp], 0, 200)
    sk = d.doc.sketch('S1')
    assert sum(1 for e in sk.entities.values() if e['kind'] == 'ellipse') == 2
    asse = sk.line('O', sk.point(0, 100), construction=True)
    sketch_edit.mirror(d.doc, 'S1', [el, sp], asse)
    ss = solve(sk, d.doc.resolved_parameters())
    spec = [k for k, e in sk.entities.items() if e['kind'] == 'ellipse'][-1]
    c = ss.points[sk.entities[spec]['center']]
    assert c == pytest.approx((-100, 0), abs=1e-6)
    s_, e_ = (ss.points[sk.entities[spec][k]] for k in ('start', 'end'))
    assert s_ == pytest.approx((-40, 0), abs=1e-6) and e_ == pytest.approx((-160, 0), abs=1e-6)   # il verso si gira
    sketch_edit.pattern_circular(d.doc, 'S1', [sp], 'O', 4)
    assert sum(1 for e in sk.entities.values() if e['kind'] == 'spline') == 3 + 3
    assert solve(sk, d.doc.resolved_parameters()).status.ok_for_features


def test_profilo_piegato_non_prende_le_curve():
    s = Service()
    assert s.new_project('zero', {})['ok']
    assert s.sketch_add_spline('S1', [[0, 0], [50, 40], [100, 0]], False)['ok']
    r = s.create_from_sketch('S1', 'profilo', {'lunghezza': 300, 'spessore': 2})
    assert not r['ok'] and 'curve libere' in r['message']


# ------------------------------------------------------------------------------------------------ DXF letto
def test_dxf_con_ellissi_e_spline_letto_in_archi(tmp_path):
    p = tmp_path / 'c.dxf'
    d = ezdxf.new('R2010')
    d.header['$INSUNITS'] = 4
    m = d.modelspace()
    m.add_ellipse((0, 0), major_axis=(300, 0), ratio=0.5)
    m.add_ellipse((0, 0), major_axis=(0, 100), ratio=0.4)          # foro ellittico in piedi
    d.saveas(p)
    an = dxf_import.leggi(p)
    assert [round(g.area) for g in an.giri] == [round(math.pi * 300 * 150), round(math.pi * 100 * 40)]
    assert all(t.tipo == 'arc' for g in an.giri for t, _ in g.tratti)   # archi veri, non centinaia di segmentini
    fuori, pezzo = dxf_import.faccia_dxf(an, an.scelto)
    assert pezzo.area == pytest.approx(math.pi * (300 * 150 - 100 * 40), rel=1e-5)


def test_arco_attaccato_agli_spigoli_tiene_l_asse_piccolo():
    """La mezza ellisse sopra la base: l'asse grande lo decidono gli spigoli, l'asse piccolo resta quotato."""
    s = _sopraluce()
    sk = s.doc.sketch('S1')
    el = next(k for k, e in sk.entities.items() if e['kind'] == 'ellipse' and 'start' in e)
    tipi = sorted(c['type'] for c in sk.constraints.values() if c['refs'] == [el])
    assert tipi == ['minor_axis']
    assert solve(sk).status.state in ('completo', 'parziale') and not solve(sk).status.redundant


def test_mezza_ellisse_cambia_l_altezza_con_la_quota():
    s = _sopraluce()
    sk = s.doc.sketch('S1')
    el = next(k for k, e in sk.entities.items() if e['kind'] == 'ellipse' and 'start' in e)
    did = next(k for k, c in sk.constraints.items() if c['refs'] == [el] and c['type'] == 'minor_axis')
    assert s.set_dimension('S1', did, '400')['ok']                     # l'arco sale 200 invece di 300
    ss = solve(s.doc.sketch('S1'))
    e = s.doc.sketch('S1').entities[el]
    assert ss.status.state in ('completo', 'parziale') and not ss.status.redundant
    assert math.dist(ss.points[e['center']], ss.points[e['minor']]) == pytest.approx(200)
    assert ss.points[e['start']] == pytest.approx((400, 0)) and ss.points[e['end']] == pytest.approx((-400, 0))
    v = s.sketch_view('S1')['sketch']
    assert v['profiles'] == 1


# ------------------------------------------------------------------------------------------------ accorcia
def test_accorcia_ellisse_e_linea_fanno_un_contorno():
    """Un'ellisse tagliata da una linea orizzontale: si accorcia la linea fuori e la parte di sotto dell'ellisse,
    resta un contorno chiuso (arco di ellisse + linea) che diventa piastra."""
    from app import sketch_trim
    s = Service()
    assert s.new_project('zero', {})['ok']
    assert s.sketch_add_ellipse('S1', 'O', [300, 0], 150)['ok']
    assert s.sketch_add_polyline('S1', [[-400, -50], [400, -50]], False)['ok']
    sk = s.doc.sketch('S1')
    el = next(k for k, e in sk.entities.items() if e['kind'] == 'ellipse')
    ln = next(k for k, e in sk.entities.items() if e['kind'] == 'line')
    prev = sketch_trim.trim_preview(s.doc, 'S1', el, [0, -150])
    assert not prev['all'] and min(q[1] for q in prev['remove']) == pytest.approx(-150, abs=0.1)
    for click in ([-380, -50], [380, -50]):            # i pezzi di linea fuori dall'ellisse
        assert s.sketch_trim('S1', ln, click)['ok']
    assert s.sketch_trim('S1', el, [0, -150])['ok']    # la pancia sotto
    sk = s.doc.sketch('S1')
    e = sk.entities[el]
    assert 'start' in e and 'end' in e
    ss = solve(sk)
    x0 = 300 * math.sqrt(1 - (50 / 150) ** 2)
    assert sorted([ss.points[e['start']][0], ss.points[e['end']][0]]) == pytest.approx([-x0, x0], abs=1e-6)
    v = s.sketch_view('S1')['sketch']
    assert v['profiles'] == 1 and not v['sciolte']
    assert s.create_from_sketch('S1', 'plate', {'thickness': 3})['ok']


def test_curva_libera_non_si_accorcia():
    s = Service()
    assert s.new_project('zero', {})['ok']
    r = s.sketch_add_spline('S1', [[0, 0], [50, 40], [100, 0]], False)
    r = s.sketch_trim('S1', r['id'], [50, 40])
    assert not r['ok'] and 'non si accorcia' in r['message']


def test_foro_ellittico_e_asola_libera_sulla_lamiera_piegata(tmp_path):
    """Sulla faccia di una lamiera con le flange: un foro a ellisse e una sagoma a curva libera; lo sviluppo e il DXF
    per il laser li hanno in archi."""
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 400, 'profondita': 250, 'spessore': 2, 'raggio': 2, 'k': 0.4})['ok']
    assert s.add_flange('SM1', 'L2', {'length': '40'})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_ellipse(sid, [120, 120], [180, 120], 30)['ok']
    assert s.sketch_add_spline(sid, [[250, 80], [300, 120], [280, 180], [230, 150]], True)['ok']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r
    r = s.export_dxf(str(tmp_path / 'f.dxf'))
    assert r['ok'] and '3 contorni' in r['message'], r
    tipi = {e.dxftype() for e in ezdxf.readfile(tmp_path / 'f.dxf').modelspace() if e.dxf.layer == 'CUT'}
    assert tipi <= {'LINE', 'ARC', 'CIRCLE'}


def test_tavola_del_sopraluce(tmp_path):
    s = _sopraluce()
    assert s.create_from_sketch('S1', 'plate', {'thickness': 5})['ok']
    campi = {**s.drawing_fields()['fields'], 'azienda': 'Prova', 'numero': 'C-1'}
    p = s.drawing_preview(campi)
    assert p['ok'] and p['sheets']
    assert s.export_drawings(str(tmp_path / 't.pdf'), campi)['ok']
    assert s.export_drawings(str(tmp_path / 't.dxf'), campi)['ok']


def test_inclinazione_scritta_prende_il_posto_di_dritta():
    s = Service()
    assert s.new_project('zero', {})['ok']
    el = s.sketch_add_ellipse('S1', [0, 0], [100, 0], 50)['id']
    r = s.sketch_dimension('S1', 'tilt', [el])
    assert r['ok'] and not r.get('guidata')
    sk = s.doc.sketch('S1')
    assert not any(c['type'] == 'horizontal' for c in sk.constraints.values())
    assert not any(c.get('driven') for c in sk.constraints.values())
    did = next(k for k, c in sk.constraints.items() if c['type'] == 'tilt')
    assert s.set_dimension('S1', did, '30')['ok']
    ss = solve(s.doc.sketch('S1'))
    e = sk.entities[el]
    c, m = ss.points[e['center']], ss.points[e['major']]
    assert math.degrees(math.atan2(m[1] - c[1], m[0] - c[0])) == pytest.approx(30)
    assert ss.status.state == 'completo'


def test_offset_di_una_curva_lo_dice():
    s = Service()
    assert s.new_project('zero', {})['ok']
    sp = s.sketch_add_spline('S1', [[0, 0], [50, 40], [100, 0]], False)['id']
    r = s.sketch_offset_preview('S1', [sp], 10, 'right')
    assert not r['ok'] and 'curve libere' in r['message']


def test_curva_libera_aperta_chiude_il_contorno_con_le_linee():
    """Una sagoma da cancello: base dritta e sopra una curva libera da un angolo all'altro."""
    s = Service()
    assert s.new_project('zero', {})['ok']
    assert s.sketch_add_polyline('S1', [[0, 100], [0, 0], [500, 0], [500, 100]], False)['ok']
    sk = s.doc.sketch('S1')
    a = next(k for k, e in sk.entities.items() if e['kind'] == 'point' and (e['x'], e['y']) == (0, 100))
    b = next(k for k, e in sk.entities.items() if e['kind'] == 'point' and (e['x'], e['y']) == (500, 100))
    assert s.sketch_add_spline('S1', [b, [380, 180], [250, 140], [120, 200], a], False)['ok']
    v = s.sketch_view('S1')['sketch']
    assert v['profiles'] == 1 and not v['sciolte']
    assert s.create_from_sketch('S1', 'sheet', {'thickness': 3})['ok']
