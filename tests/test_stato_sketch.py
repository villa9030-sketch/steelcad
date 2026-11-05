"""Stato del disegno (05/11, idee da SolidCraft): quanto manca, linee libere, estremità aperte e «Chiudi»,
«Sistema il disegno» per i disegni importati, import di un SVG nello sketch."""
import math

import ezdxf
import pytest

from app import sketch_ops as so
from app import sketch_stato
from app.service import Service
from cad_engine.document import Document
from cad_engine.importers import svg_import
from cad_engine.sketch import sistema, solve
from cad_engine.sketch import stato as st


def _doc():
    d = Document('x')
    d.add_sketch('XY', 'S')
    return d


def _faccia_sopra():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 300, 'spessore': 2})['ok']
    f = next(x for x in s.scene()['objects'][0]['faces'] if x['name'] and x['name'].endswith('sopra'))
    return s, s.sketch_on_face(f['name'])['sketch']


# ---------------------------------------------------------------- quanto manca
def test_rettangolo_dall_origine_tutto_definito():
    d = _doc()
    so.add_rectangle(d, 'S1', 'O', [200, 100])
    v = so.view(d, 'S1')
    assert v['misure']['frase'] == 'Tutto definito' and v['misure']['dof'] == 0 and v['misure']['liberi'] == []


def test_linee_libere_quelle_senza_misure():
    """Il rettangolo quotato resta deciso; la spezzata girata attorno al suo primo punto si muove ancora."""
    d = _doc()
    so.add_rectangle(d, 'S1', 'O', [200, 100])
    so.add_polyline(d, 'S1', [[300, 0], [400, 10], [420, 80]], False)
    v = so.view(d, 'S1')
    nuove = [l['id'] for l in v['lines'] if l['xa'][0] >= 300 or l['xb'][0] >= 300]
    assert sorted(v['misure']['liberi']) == sorted(nuove)
    assert v['misure']['frase'] == 'Mancano 2 misure'


def test_frase_misure():
    assert st.frase_misure('completo', 0) == 'Tutto definito'
    assert st.frase_misure('parziale', 1) == 'Manca 1 misura'
    assert st.frase_misure('parziale', 3) == 'Mancano 3 misure'
    assert st.frase_misure('sovra-vincolato', -1) == 'Misure di troppo'


def test_cerchio_senza_diametro_e_libero():
    d = _doc()
    sk = d.sketch('S1')
    c = sk.point(50, 50)
    sk.dimension('hdistance', 'O', c, value=50)
    sk.dimension('vdistance', 'O', c, value=50)
    cid = sk.circle(c, 10)
    assert st.elementi_liberi(sk, {}) == [cid]
    sk.dimension('diameter', cid, value=20)
    assert st.elementi_liberi(sk, {}) == []


def test_tanti_pezzi_liberi_svelto():
    """40 quadrilateri liberi: il conto si fa pezzo per pezzo (prima, tutto insieme, 12 secondi)."""
    import time
    d = _doc()
    for i in range(40):
        so.add_polyline(d, 'S1', [[i * 50, 0], [i * 50 + 30, 0], [i * 50 + 30, 20], [i * 50 + 3, 25]], True)
    sk = d.sketch('S1')
    t = time.time()
    liberi = st.elementi_liberi(sk, {})
    assert time.time() - t < 3
    assert len(liberi) == 160


# ---------------------------------------------------------------- estremità aperte, Chiudi
def test_estremita_aperte_e_chiudi():
    """Un contorno disegnato a mano che non torna proprio sul primo punto (0,4 mm): «Chiudi» lo unisce."""
    d = _doc()
    so.add_polyline(d, 'S1', [[0, 0], [100, 0], [100, 60], [0.3, 60.0], [0.0, 0.4]], False)
    sk = d.sketch('S1')
    ap = st.estremita_aperte(sk, solve(sk, {}))
    assert len(ap['aperte']) == 2 and len(ap['coppie']) == 1
    assert 0 < ap['coppie'][0]['dist'] <= st.CHIUDI_TOL
    r = sketch_stato.chiudi(d, 'S1')
    assert r['unite'] == 1 and r['lasciate'] == 0 and len(r['tolte']) <= 2
    sk = d.sketch('S1')
    ss = solve(sk, {})
    assert st.estremita_aperte(sk, ss)['aperte'] == []
    from cad_engine.sketch.profile import PLANES, build
    assert len(build(ss, PLANES['XY']).faces) == 1


def test_estremita_lontane_non_si_uniscono():
    d = _doc()
    so.add_polyline(d, 'S1', [[0, 0], [100, 0], [100, 60], [0, 60], [0, 10]], False)
    sk = d.sketch('S1')
    ap = st.estremita_aperte(sk, solve(sk, {}))
    assert len(ap['aperte']) == 2 and ap['coppie'] == []
    with pytest.raises(Exception):
        sketch_stato.chiudi(d, 'S1')


def test_estremita_sul_bordo_del_pezzo_non_e_aperta():
    """Sulla faccia: una spezzata da bordo a bordo (arancio) tocca il pezzo, non è un'estremità aperta."""
    s, sid = _faccia_sopra()
    assert s.sketch_add_polyline(sid, [[0, 100], [150, 150], [300, 100]], False)['ok']
    v = s.sketch_view(sid)['sketch']
    assert v['aperte'] == []


def test_chiudi_dal_servizio_si_annulla():
    s, sid = _faccia_sopra()
    assert s.sketch_add_polyline(sid, [[50, 50], [150, 50], [150, 120], [50.5, 120], [50, 50.6]], False)['ok']
    v = s.sketch_view(sid)['sketch']
    assert len(v['coppie']) == 1 and v['profiles'] == 0
    r = s.sketch_chiudi(sid)
    assert r['ok'] and 'Unite' in r['message']
    v = s.sketch_view(sid)['sketch']
    assert v['coppie'] == [] and v['aperte'] == [] and v['profiles'] == 1
    assert s.undo()['ok']
    assert len(s.sketch_view(sid)['sketch']['coppie']) == 1


# ---------------------------------------------------------------- Sistema il disegno
def _piastra_dxf(tmp_path):
    d = ezdxf.new()
    d.header['$INSUNITS'] = 4
    b = 0.4142135623730951                     # quarto di cerchio nelle polilinee del DXF
    d.modelspace().add_lwpolyline([(20, 0, 0), (280, 0, b), (300, 20, 0), (300, 180, b), (280, 200, 0),
                                   (20, 200, b), (0, 180, 0), (0, 20, b)], close=True, format='xyb')
    p = tmp_path / 'piastra.dxf'
    d.saveas(p)
    s = Service()
    r = s.import_dxf(str(p))
    assert s.import_dxf_create(r['scelto'], {'thickness': 3, 'radius': 3, 'k': 0.4, 'material': 'S235'})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    return s, sid


def test_sistema_piastra_raccordata_dal_dxf(tmp_path):
    """Piastra 300×200 con 4 raggi R20 dal DXF: punti bloccati. Sistema: orizzontali, verticali, tangenze, raggi
    uguali; resta fermo un punto e mancano proprio larghezza, altezza e raggio. Le tre quote non litigano."""
    s, sid = _piastra_dxf(tmp_path)
    sk = s.doc.sketch(sid)
    prima = {k: (e['x'], e['y']) for k, e in sk.entities.items() if e['kind'] == 'point'}
    a = s.sketch_sistema_anteprima(sid)
    assert a['ok'] and a['conti']['hv'] == 4 and a['conti']['tangenti'] == 8 and a['conti']['uguali'] == 3
    assert a['dopo'] == 'Mancano 3 misure'
    assert len(a['segni']['hv']) == 4 and {x['tipo'] for x in a['segni']['hv']} == {'H', 'V'}
    r = s.sketch_sistema(sid)
    assert r['ok'] and 'tangenze' in r['message']
    sk = s.doc.sketch(sid)
    ss = solve(sk, s.doc.resolved_parameters())
    assert ss.status.state == 'parziale' and ss.status.dof == 3
    assert max(math.dist(ss.points[k], q) for k, q in prima.items() if k in ss.points) < 1e-6   # il disegno non si muove
    lati = [k for k, e in sk.entities.items() if e['kind'] == 'line']
    arco = next(k for k, e in sk.entities.items() if e['kind'] == 'arc')
    orizz = next(k for k in lati if abs(ss.points[sk.entities[k]['a']][1] - ss.points[sk.entities[k]['b']][1]) < 1e-6)
    vert = next(k for k in lati if abs(ss.points[sk.entities[k]['a']][0] - ss.points[sk.entities[k]['b']][0]) < 1e-6)
    sk.dimension('length', orizz, value=300)
    sk.dimension('length', vert, value=150)
    sk.dimension('radius', arco, value=25)
    ss = solve(sk, s.doc.resolved_parameters())
    assert ss.status.state == 'completo', ss.status.message


def test_sistema_trova_punti_quasi_uniti_e_storti_di_niente():
    d = _doc()
    sk = d.sketch('S1')
    pts = [sk.point(*q) for q in ((0, 0), (100, 0.02), (100.004, 50), (0, 50))]
    sk.line(pts[0], pts[1])
    sk.line(pts[1], pts[2])
    p5 = sk.point(100.0, 50.003)                  # due estremità a 3 centesimi: un punto solo
    sk.line(p5, pts[3])
    sk.line(pts[3], pts[0])
    for p in pts + [p5]:
        sk.constrain('fix', p)
    prop = sistema.trova(sk)
    assert len(prop['uniti']) == 1 and len(prop['hv']) == 4 and len(prop['sblocca']) == 5
    nuovo, info = sistema.prova(sk, {})
    assert info['conti']['uniti'] == 1 and info['conti']['hv'] == 4
    ss = solve(nuovo, {})
    assert ss.status.state == 'parziale'
    assert st.estremita_aperte(nuovo, ss)['aperte'] == []


def test_sistema_non_mette_cose_di_troppo():
    """Un rettangolo già fatto a mano: niente da sistemare (orizzontali e verticali ci sono, i lati uguali sarebbero
    di troppo)."""
    d = _doc()
    so.add_rectangle(d, 'S1', 'O', [200, 100])
    nuovo, info = sistema.prova(d.sketch('S1'), {})
    assert info['conti']['hv'] == 0 and info['conti']['uguali'] == 0
    assert solve(nuovo, {}).status.state == 'completo'
    with pytest.raises(Exception):
        sketch_stato.applica(d, 'S1')


def test_sistema_solo_i_tipi_scelti(tmp_path):
    s, sid = _piastra_dxf(tmp_path)
    a = s.sketch_sistema_anteprima(sid, ['hv'])
    assert a['ok'] and a['scelti']['tangenti'] == 0 and a['conti']['tangenti'] == 8
    assert s.sketch_sistema(sid, ['hv'])['ok']
    tipi = [c['type'] for c in s.doc.sketch(sid).constraints.values()]
    assert 'tangent' not in tipi and tipi.count('horizontal') == 2


# ---------------------------------------------------------------- SVG
LOGO = '''<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm" viewBox="0 0 200 100">
<path d="M10 10 L60 10 C 70 10 80 20 80 30 A 20 20 0 0 1 60 50 L10 50 Z"/>
<circle cx="120" cy="50" r="10"/><rect x="140" y="20" width="40" height="40" rx="6"/>
<text x="1" y="1">ciao</text></svg>'''


def test_svg_letto_in_mm(tmp_path):
    p = tmp_path / 'logo.svg'
    p.write_text(LOGO)
    dis = svg_import.leggi(p)
    assert dis.testi == 1 and len(dis.cerchi) == 1
    assert dis.larghezza_mm == pytest.approx(85, abs=1e-3)      # da x=10 a x=180 in unità da 0,5 mm
    assert dis.altezza_mm == pytest.approx(25, abs=1e-3)        # da y=10 a y=60


def test_svg_alla_larghezza_scelta_con_archi_veri(tmp_path):
    p = tmp_path / 'logo.svg'
    p.write_text(LOGO)
    geo = svg_import.geometria(svg_import.leggi(p), 170, 20, 30)
    assert geo['w'] == pytest.approx(170) and geo['h'] == pytest.approx(50, abs=1e-3)
    xs = [q[0] for g in geo['giri'] for pz in g for q in pz[1:]]
    ys = [q[1] for g in geo['giri'] for pz in g for q in pz[1:]]
    assert min(xs) == pytest.approx(20) and min(ys) == pytest.approx(30) and max(ys) == pytest.approx(80)
    archi = [pz for g in geo['giri'] for pz in g if pz[0] == 'A']
    assert 4 <= len(archi) <= 40                             # la Bézier diventa pochi archi, non mille trattini
    (c, r), = geo['cerchi']
    assert r == pytest.approx(10, abs=1e-3) and c[0] == pytest.approx(20 + (120 - 10), abs=1e-3)   # 1 unità = 0,5 mm, x2


def test_svg_curva_entro_la_tolleranza():
    """Una Bézier cubica: ogni punto della curva sta a meno di TOL dagli archi e dalle linee fatti."""
    import svgelements as S
    seg = S.CubicBezier(S.Point(0, 0), S.Point(30, 80), S.Point(90, -40), S.Point(120, 30))
    P = lambda t: (seg.point(t).x, seg.point(t).y)  # noqa: E731
    pezzi = svg_import._spezza(P, 0, 1, 0.02)
    for i in range(201):
        q = P(i / 200)
        dmin = math.inf
        for pz in pezzi:
            if pz[0] == 'L':
                dmin = min(dmin, svg_import._dist_retta(q, pz[1], pz[2]) if True else 0)
            else:
                (cx, cy), r = svg_import._cerchio_per_3(*pz[1:])
                dmin = min(dmin, abs(math.dist(q, (cx, cy)) - r))
        assert dmin <= 0.021


def test_svg_nello_sketch_si_taglia(tmp_path):
    p = tmp_path / 'logo.svg'
    p.write_text(LOGO)
    s, sid = _faccia_sopra()
    from cad_engine.features.base import volume
    v0 = volume(s.result.body.shape)
    r = s.svg_leggi(str(p))
    assert r['ok'] and r['w'] == pytest.approx(85) and r['testi'] == 1
    a = s.sketch_svg_anteprima(sid, {'larghezza': '170', 'x': '150', 'y': '150', 'centro': True})
    assert a['ok'] and a['h'] == pytest.approx(50) and a['polilinee']
    xs = [q[0] for pl in a['polilinee'] for q in pl]
    assert min(xs) == pytest.approx(65) and max(xs) == pytest.approx(235)
    r = s.sketch_svg_inserisci(sid, {'larghezza': '170', 'x': '150', 'y': '150', 'centro': True})
    assert r['ok'] and 'archi' in r['message']
    v = s.sketch_view(sid)['sketch']
    assert v['profiles'] == 3 and v['misure']['frase'] == 'Tutto definito'
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    assert volume(s.result.body.shape) < v0 - 100


def test_svg_senza_linee(tmp_path):
    p = tmp_path / 'vuoto.svg'
    p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm"><text>solo testo</text></svg>')
    r = Service().svg_leggi(str(p))
    assert not r['ok'] and 'tracciati' in r['message']
