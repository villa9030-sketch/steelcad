"""05/11 (idee da SolidCraft): Scala della selezione da un punto, Spezza una linea/arco/cerchio in due, il disegno in DXF."""
import math
import os
import tempfile

import ezdxf
import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app import sketch_ops as so  # noqa: E402
from app import sketch_scala as sc  # noqa: E402
from cad_engine.document import Document  # noqa: E402
from cad_engine.errors import SketchError  # noqa: E402
from cad_engine.sketch import solve  # noqa: E402


def _rett(w=200, h=100):
    d = Document('x')
    d.add_sketch('XY', 'S')
    r = so.add_rectangle(d, 'S1', 'O', [w, h])
    return d, d.sketch('S1'), r


def _linee(sk):
    return [k for k, e in sk.entities.items() if e['kind'] == 'line']


def _ingombro(d, sk):
    ss = solve(sk, d.resolved_parameters())
    xs = [p[0] for p in ss.points.values()]
    ys = [p[1] for p in ss.points.values()]
    return ss, (round(max(xs) - min(xs), 6), round(max(ys) - min(ys), 6))


# ------------------------------------------------------------------------------------------------ scala
def test_fattore_scritto_o_da_due_misure():
    assert sc.fattore(2) == 2
    assert sc.fattore(None, 250, 1000) == 4                 # «questa linea è 250, deve essere 1000»
    for male in (0, -1, 'x'):
        with pytest.raises(SketchError):
            sc.fattore(male)
    with pytest.raises(SketchError, match='non cambia'):
        sc.fattore(1)
    with pytest.raises(SketchError, match='maggiori di zero'):
        sc.fattore(None, 0, 10)


def test_scala_dall_origine_le_quote_seguono():
    d, sk, _ = _rett()
    sc.scale(d, 'S1', _linee(sk), (0, 0), 2)
    ss, box = _ingombro(d, sk)
    assert box == (400, 200) and ss.status.state == 'completo'
    assert sorted(c['value'] for c in sk.constraints.values() if c['type'] == 'length') == [200, 400]


def test_scala_da_misura_a_misura():
    """Il DXF del cliente arrivato in scala sbagliata: la base è 250, deve essere 1000."""
    d, sk, _ = _rett(250, 80)
    sc.scale(d, 'S1', _linee(sk), (0, 0), sc.fattore(None, 250, 1000))
    _, box = _ingombro(d, sk)
    assert box == (1000, 320)


def test_scala_cerchio_dal_centro_e_dall_origine():
    d = Document('x')
    d.add_sketch('XY', 'S')
    c = so.add_circle(d, 'S1', [50, 30], 5)
    sk = d.sketch('S1')
    sc.scale(d, 'S1', [c], (50, 30), 2)                      # dal suo centro: resta lì, diametro doppio
    ss = solve(sk, d.resolved_parameters())
    cen, r = ss.circles[c]
    assert abs(r - 10) < 1e-6 and math.dist(ss.points[cen], (50, 30)) < 1e-6
    sc.scale(d, 'S1', [c], (0, 0), 0.5)                      # dall'origine: il centro si avvicina, le quote di posizione seguono
    ss = solve(sk, d.resolved_parameters())
    cen, r = ss.circles[c]
    assert abs(r - 5) < 1e-6 and math.dist(ss.points[cen], (25, 15)) < 1e-6 and ss.status.state == 'completo'


def test_scala_rifiutata_da_una_quota_con_misura_del_progetto():
    d, sk, r = _rett()
    d.set_parameter('W', 200)
    c = so.add_circle(d, 'S1', [100, 50], 5)
    q = next(k for k, x in sk.constraints.items() if x['type'] == 'hdistance' and sk.entities[c]['center'] in x['refs'])
    sk.constraints[q]['value'] = 'W/2'
    prima = sk.to_dict()
    with pytest.raises(SketchError, match='W/2'):
        sc.scale(d, 'S1', [c], (0, 0), 2)
    # la prova non cambia niente
    with pytest.raises(SketchError, match='W/2'):
        sc.scale_check(d, 'S1', [c], (0, 0), 2)
    assert sk.to_dict()['constraints'] == prima['constraints']
    sc.scale_check(d, 'S1', [c], sk_center(sk, c), 2)          # dal suo centro va bene
    assert sk.to_dict()['constraints'] == prima['constraints']


def sk_center(sk, c):
    p = sk.entities[sk.entities[c]['center']]
    return (p['x'], p['y'])


def test_scala_rifiutata_da_un_vincolo_col_resto():
    """Una linea verticale che arriva su un lato orizzontale: scalare solo lei da un punto che non sta sul lato la
    staccherebbe; il vincolo «sulla linea» lo impedisce e si dice."""
    d, sk, r = _rett()
    linee = so.add_polyline(d, 'S1', [{'on': r['bottom'], 'xy': [100, 0]}, [100, 60]], False)
    with pytest.raises(SketchError, match='Non si può scalare'):
        sc.scale(d, 'S1', linee, (100, 60), 2)
    sc.scale(d, 'S1', linee, (100, 0), 0.5)                  # dal punto sul lato: va
    ss = solve(d.sketch('S1'), d.resolved_parameters())
    l = d.sketch('S1').entities[linee[0]]
    assert abs(math.dist(ss.points[l['a']], ss.points[l['b']]) - 30) < 1e-6


def test_scala_cerchio_sull_angolo_scelto_con_le_linee():
    """Un cerchio col centro su un angolo del rettangolo scelto: si scala con lui (raggio e quota insieme)."""
    d, sk, r = _rett()
    angolo = sk.entities[r['top']]['b']
    c = so.add_circle(d, 'S1', angolo, 5)
    sc.scale(d, 'S1', _linee(sk), (0, 0), 2)
    ss = solve(sk, d.resolved_parameters())
    assert abs(ss.circles[c][1] - 10) < 1e-6 and ss.status.state == 'completo'


def test_scala_bordi_e_origine():
    d, sk, r = _rett()
    with pytest.raises(SketchError, match='origine'):
        sc.scale(d, 'S1', _linee(sk), (10, 10), 2)


# ------------------------------------------------------------------------------------------------ spezza
def test_spezza_linea_in_due_senza_cancellare():
    d, sk, r = _rett()
    n = len(_linee(sk))
    pezzi = sc.spezza(d, 'S1', r['bottom'], (60, 3))
    ss = solve(sk, d.resolved_parameters())
    assert len(_linee(sk)) == n + 1 and ss.status.state == 'completo'
    a, b = (sk.entities[x] for x in pezzi)
    assert math.dist(ss.points[a['a']], ss.points[a['b']]) == pytest.approx(60)
    assert math.dist(ss.points[b['a']], ss.points[b['b']]) == pytest.approx(140)
    # la misura di prima resta (200 tra le due estremità di prima): cambiandola il secondo pezzo segue
    q = next(k for k, c in sk.constraints.items() if c['type'] == 'distance' and c['value'] == 200)
    sk.set_value(q, 300)
    ss = solve(sk, d.resolved_parameters())
    assert math.dist(ss.points[b['a']], ss.points[b['b']]) == pytest.approx(240)
    assert abs(ss.points[b['b']][1]) < 1e-6                 # sempre in fila


def test_spezza_vicino_alla_fine_rifiutato():
    d, sk, r = _rett()
    with pytest.raises(SketchError, match='estremità'):
        sc.spezza(d, 'S1', r['bottom'], (0.001, 0))


def test_spezza_cerchio_in_due_archi():
    d = Document('x')
    d.add_sketch('XY', 'S')
    c = so.add_circle(d, 'S1', [50, 50], 10)
    sk = d.sketch('S1')
    a1, a2 = sc.spezza(d, 'S1', c, (70, 50))
    ss = solve(sk, d.resolved_parameters())
    assert c not in sk.entities and set(ss.arcs) == {a1, a2}
    assert all(abs(ss.arcs[a][3] - 10) < 1e-6 for a in (a1, a2))
    assert any(x['type'] == 'radius' and x['value'] == 10 for x in sk.constraints.values())
    assert math.dist(ss.points[sk.entities[a1]['start']], (60, 50)) < 1e-6


def test_spezza_arco():
    d = Document('x')
    d.add_sketch('XY', 'S')
    sk = d.sketch('S1')
    c = sk.point(0, 0)
    a = sk.arc(c, sk.point(10, 0), sk.point(-10, 0))
    a1, a2 = sc.spezza(d, 'S1', a, (0, 12))
    ss = solve(sk, d.resolved_parameters())
    assert math.dist(ss.points[sk.entities[a1]['end']], (0, 10)) < 1e-6
    assert sk.entities[a2]['start'] == sk.entities[a1]['end']


def test_spezza_rifiuta_bordi():
    d, sk, r = _rett()
    sk.entities[r['bottom']]['ref'] = True
    with pytest.raises(SketchError, match='arancio'):
        sc.spezza(d, 'S1', r['bottom'], (50, 0))


# ------------------------------------------------------------------------------------------------ DXF
def test_dxf_del_disegno(tmp_path):
    from cad_engine.exporters import dxf
    d, sk, r = _rett()
    so.add_circle(d, 'S1', [100, 50], 10)
    so.add_polyline(d, 'S1', [[0, 0], [200, 100]], False, construction=True)    # guida: non va nel DXF
    so.add_text(d, 'S1', [20, 20], 'A1', 8)
    a = sk.arc(sk.point(300, 0), sk.point(310, 0), sk.point(290, 0))            # un arco vero
    geo = sc.geometria_dxf(d, 'S1')
    assert len(geo['lines']) == 4 and len(geo['circles']) == 1 and geo['arcs'] and geo['marks'] and geo['skipped'] == 1
    p = tmp_path / 'disegno.dxf'
    rep = dxf.export_sketch(geo, p)
    doc = ezdxf.readfile(p)
    assert doc.header['$INSUNITS'] == 4
    msp = doc.modelspace()
    tipi = sorted(e.dxftype() for e in msp if e.dxf.layer == 'CUT')
    assert tipi == ['ARC', 'CIRCLE', 'LINE', 'LINE', 'LINE', 'LINE']
    arco = next(e for e in msp if e.dxftype() == 'ARC')
    assert arco.dxf.radius == pytest.approx(10) and arco.dxf.start_angle == pytest.approx(0) and arco.dxf.end_angle == pytest.approx(180)
    assert all(e.dxf.layer == 'MARK' for e in msp if e.dxftype() == 'LWPOLYLINE')
    assert any('contorno non chiuso' in w for w in rep['warnings'])            # l'arco aperto: si dice, non si blocca
    assert a in sk.entities and p.exists() and not (tmp_path / 'disegno.dxf.tmp').exists()


def test_dxf_testo_da_tagliare_chiuso(tmp_path):
    from cad_engine.exporters import dxf
    d = Document('x')
    d.add_sketch('XY', 'S')
    so.add_text(d, 'S1', [0, 0], 'O8', 20, stencil='saira')
    rep = dxf.export_sketch(sc.geometria_dxf(d, 'S1'), tmp_path / 't.dxf')
    assert rep['warnings'] == [] and rep['contours'] >= 2


def test_dxf_vuoto_rifiutato(tmp_path):
    from cad_engine.errors import ExportError
    from cad_engine.exporters import dxf
    d = Document('x')
    d.add_sketch('XY', 'S')
    so.add_polyline(d, 'S1', [[0, 0], [10, 0]], False, construction=True)
    with pytest.raises(ExportError, match='niente da salvare'):
        dxf.export_sketch(sc.geometria_dxf(d, 'S1'), tmp_path / 'x.dxf')


def test_servizio_menu_e_export(tmp_path):
    from app.service import Service
    s = Service()
    s.new_project('lamiera', {'name': 'C', 'larghezza': 200, 'profondita': 150, 'spessore': 2, 'raggio': 1, 'k': 0.21})
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    s.sketch_add_circle(sid, [50, 50], 3)
    assert 'dxf' in s.tree_menu('sketch', sid)['voci']
    assert s.sketch_nome_dxf(sid).endswith('.dxf')
    r = s.sketch_export_dxf(sid, str(tmp_path / 'f.dxf'))
    assert r['ok'], r
    msp = ezdxf.readfile(tmp_path / 'f.dxf').modelspace()
    assert [e.dxftype() for e in msp] == ['CIRCLE']                             # i bordi del pezzo non ci sono
    assert 'Le guide e i bordi del pezzo non ci sono' in r['message']
    assert not s.sketch_export_dxf(sid, str(tmp_path / 'manca' / 'f.dxf'))['ok']
    # Scala e Spezza dal servizio, con l'annulla
    c = next(k for k, e in s.doc.sketch(sid).entities.items() if e['kind'] == 'circle' and not e.get('ref'))
    assert s.sketch_scale_check(sid, [c], [50, 50], '2')['ok']
    assert not s.sketch_scale_check(sid, [c], [50, 50], '1')['ok']
    r = s.sketch_scale(sid, [c], [50, 50], None, '6', '12')
    assert r['ok'] and s.doc.sketch(sid).entities[c]['r'] == pytest.approx(6)
    assert s.sketch_break_preview(sid, c, [60, 50])['ok']
    assert s.sketch_break(sid, c, [60, 50])['ok'] and c not in s.doc.sketch(sid).entities
    assert s.undo()['ok'] and c in s.doc.sketch(sid).entities
