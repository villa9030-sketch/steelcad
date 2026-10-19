"""Comandi di disegno: costruzione, agganci legati, offset, specchia, copia, sposta, serie, quote a mano."""
import pytest

from app import sketch_edit as se
from app import sketch_ops as so
from cad_engine.document import Document
from cad_engine.errors import SketchError
from cad_engine.sketch import solve


def _rett():
    d = Document('x')
    d.add_sketch('XY', 'S')
    so.add_rectangle(d, 'S1', 'O', [200, 100])
    return d, d.sketch('S1')


def _st(d):
    ss = solve(d.sketch('S1'), d.resolved_parameters())
    return ss.status, ss


def _xs(ss, sk):
    return sorted({round(v[0], 6) for v in ss.points.values()})


def _cx(ss, sk):
    return sorted(round(ss.points[sk.entities[c]['center']][0], 6) for c in ss.circles)


def test_offset_legato_al_parametro_e_all_originale():
    d, sk = _rett()
    lati = [k for k, e in sk.entities.items() if e['kind'] == 'line']
    se.offset(d, 'S1', lati, 10, 'out')
    st, ss = _st(d)
    assert st.state == 'completo' and d.parameters == {'off1': 10}
    assert [x for x in _xs(ss, sk) if x in (-10, 0, 200, 210)] == [-10, 0, 200, 210]
    d.set_parameter('off1', 15)
    assert {-15, 215} <= set(_xs(_st(d)[1], sk))
    dl = next(k for k, c in sk.constraints.items() if c['type'] == 'length' and c['value'] == 200)
    sk.set_value(dl, 300)
    xs = set(_xs(_st(d)[1], sk))
    assert {-15, 315} <= xs and 285 not in xs                       # non si è rovesciato
    with pytest.raises(SketchError, match='troppo grande'):
        d2, sk2 = _rett()
        se.offset(d2, 'S1', [k for k, e in sk2.entities.items() if e['kind'] == 'line'], 60, 'in')


def test_offset_cerchio():
    d, sk = _rett()
    c = so.add_circle(d, 'S1', [30, 30], 5)
    se.offset(d, 'S1', [c], 3, 'out')
    st, ss = _st(d)
    assert st.state == 'completo' and sorted(round(v[1], 6) for v in ss.circles.values()) == [5, 8]


def test_specchio_legato():
    d, sk = _rett()
    c = so.add_circle(d, 'S1', [30, 30], 5)
    asse = so.add_polyline(d, 'S1', [[100, 0], [100, 100]], False, construction=True)[0]
    se.mirror(d, 'S1', [c], asse)
    st, ss = _st(d)
    assert st.state == 'completo' and _cx(ss, sk) == [30, 170]
    dx = next(k for k, cc in sk.constraints.items() if cc['type'] == 'hdistance' and cc['value'] == 30)
    sk.set_value(dx, 20)
    assert _cx(_st(d)[1], sk) == [20, 180]


def test_serie_col_passo_parametro():
    d, sk = _rett()
    c = so.add_circle(d, 'S1', [30, 30], 5)
    se.pattern(d, 'S1', [c], 4, 40, 2, 40)
    st, ss = _st(d)
    assert st.state == 'completo' and len(ss.circles) == 8
    d.set_parameter('px1', 45)
    assert sorted(set(_cx(_st(d)[1], sk))) == [30, 75, 120, 165]


def test_copia_e_sposta():
    d, sk = _rett()
    c = so.add_circle(d, 'S1', [30, 30], 5)
    se.copy(d, 'S1', [c], 50, 20)
    assert _st(d)[0].state == 'completo'
    se.move(d, 'S1', [c], 10, 0)
    st, ss = _st(d)
    assert st.state == 'completo' and _cx(ss, sk) == [40, 80]        # si sposta solo la selezione


def test_agganci_legati_alle_guide():
    d, sk = _rett()
    g1 = so.add_polyline(d, 'S1', [[60, -20], [60, 120]], False, construction=True)[0]
    g2 = so.add_polyline(d, 'S1', [[-20, 40], [220, 40]], False, construction=True)[0]
    c = so.add_circle(d, 'S1', {'cross': [g1, g2], 'xy': [60, 40]}, 4)
    st, ss = _st(d)
    assert st.state == 'completo' and ss.points[sk.entities[c]['center']] == pytest.approx((60, 40))
    dim = next(k for k, cc in sk.constraints.items() if cc['type'] == 'hdistance' and cc['refs'][1] == sk.entities[g1]['a'])
    sk.set_value(dim, 80)
    assert _st(d)[1].points[sk.entities[c]['center']] == pytest.approx((80, 40))
    lato = next(k for k, e in sk.entities.items() if e.get('label') == 'lato sopra')
    c2 = so.add_circle(d, 'S1', {'mid': lato}, 3)
    st, ss = _st(d)
    assert st.state == 'completo' and ss.points[sk.entities[c2]['center']] == pytest.approx((100, 100))
    # le guide non diventano contorno: il pezzo si estrude con 4 lati e 2 fori... (uno sta sul bordo: lo togliamo)
    so.delete(d, 'S1', [c2])
    d.add_feature('extrude', 'P', sketch='S1', distance=5)
    r = d.rebuild()
    assert r.ok and len(r.body.faces()) == 7                       # 6 della piastra + il foro


def test_quote_a_mano_e_doppie():
    d, sk = _rett()
    c = so.add_circle(d, 'S1', [30, 30], 5)
    cen = sk.entities[c]['center']
    # la posizione c'è già (messa disegnando): si riprende quella, non si rifiuta e non se ne fa un'altra
    n = len(sk.constraints)
    gia = se.add_dimension(d, 'S1', 'hdistance', ['O', cen])
    assert sk.constraints[gia]['type'] == 'hdistance' and len(sk.constraints) == n
    lato = next(k for k, e in sk.entities.items() if e.get('label') == 'lato sinistro')
    p = so.add_circle(d, 'S1', [150, 70], 4)
    pc = sk.entities[p]['center']
    # tolgo la posizione automatica e la rimetto come distanza dal lato
    for k, cc in list(sk.constraints.items()):
        if cc['type'] == 'hdistance' and cc['refs'][1] == pc:
            del sk.constraints[k]
    did = se.add_dimension(d, 'S1', 'pldistance', [pc, lato])
    assert sk.constraints[did]['value'] == 150 and _st(d)[0].state == 'completo'


def test_costruzione_si_attiva_e_disattiva():
    d, sk = _rett()
    lati = [k for k, e in sk.entities.items() if e['kind'] == 'line']
    se.set_construction(d, 'S1', lati[:1], True)
    assert sk.entities[lati[0]]['construction']
    d.add_feature('extrude', 'P', sketch='S1', distance=5)
    assert not d.rebuild().ok                                        # un lato è guida: il contorno è aperto
    se.set_construction(d, 'S1', lati[:1], False)
    assert d.rebuild().ok


def test_serie_dei_bordi_di_una_finestra_tagliata_si_taglia():
    """Il caso di Stefano (19/10): finestre già tagliate, poi uno sketch sulla faccia; si selezionano i bordi
    arancio di una finestra e si fa la serie. Le copie erano bordi arancio anche loro (fissi, solo guida): lo
    sketch risultava vuoto e "Taglia attraverso" spento. Ora le copie sono disegno vero e si tagliano."""
    from app.service import Service
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 400, 'profondita': 400, 'spessore': 2, 'raggio': 1, 'k': 0.21})['ok']
    faccia = s.fori_faccia()
    assert s.fori_guidati(faccia, {'tipo': 'finestra', 'lungh': 30, 'larg': 12, 'x': 100, 'y': 60})['ok']
    sid = s.sketch_on_face(faccia)['sketch']
    sk = s.doc.sketch(sid)
    # i 4 bordi arancio della finestra: le linee di riferimento dentro il rettangolo 85..115 × 54..66
    def dentro(e):
        a, b = sk.entities[e['a']], sk.entities[e['b']]
        return all(84 < p['x'] < 116 and 53 < p['y'] < 67 for p in (a, b))
    bordi = [k for k, e in sk.entities.items() if e['kind'] == 'line' and e.get('ref') and dentro(e)]
    assert len(bordi) == 4
    r = s.sketch_pattern(sid, bordi, 3, 50, 2, 80)
    assert r['ok'], r.get('message')
    v = s.sketch_view(sid)['sketch']
    assert v['drawn'] == 20                              # 5 finestre nuove × 4 lati, disegno vero
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')
    assert len(s.result.body.sheet.flat.inner_wires()) == 6
