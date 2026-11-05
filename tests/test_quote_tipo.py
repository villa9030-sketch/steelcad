"""Quote che cambiano tipo con un clic (05/11, idee da SolidCraft): raggio ↔ diametro, lo sviluppo dell'arco (la
lunghezza lungo l'arco, per calandrare), quota normale ↔ di riferimento. Il disegno non si muove cambiando tipo."""
import math

import pytest

from app.service import Service
from cad_engine.sketch import solve


def _nuovo():
    s = Service()
    assert s.new_project('zero', {'name': 'Q'})['ok']
    return s, 'S1'


def _raccordato(s, sid, r=5):
    assert s.sketch_add_rectangle_rounded(sid, [0, 0], [100, 60], r)['ok']
    sk = s.doc.sketch(sid)
    rq = next(k for k, c in sk.constraints.items() if c['type'] == 'radius')
    return sk, rq


def _quote(s, sid):
    return {d['dim']: d for d in s.state()['dimensions'] if d['sketch'] == sid} if 'dimensions' in s.state() else \
        {d['dim']: d for d in s._dimensions(sid)}


def _ss(s, sid):
    return solve(s.doc.sketch(sid), s.doc.resolved_parameters())


def test_raggio_diventa_diametro_e_torna_senza_muovere_niente():
    s, sid = _nuovo()
    sk, rq = _raccordato(s, sid, 5)
    prima = dict(_ss(s, sid).points)
    r = s.sketch_dimension_kind(sid, rq, 'diameter')
    assert r['ok'], r
    assert sk.constraints[rq]['type'] == 'diameter' and sk.constraints[rq]['value'] == 10
    assert all(math.dist(prima[k], v) < 1e-6 for k, v in _ss(s, sid).points.items() if k in prima)
    d = _quote(s, sid)[rq]
    assert d['label'] == 'Ø10'
    assert s.set_dimension(sid, rq, '30')['ok']                       # il diametro 30: raggio 15
    arco = sk.constraints[rq]['refs'][0]
    assert _ss(s, sid).arcs[arco][3] == pytest.approx(15)
    assert s.sketch_dimension_kind(sid, rq, 'radius')['ok']
    assert sk.constraints[rq]['type'] == 'radius' and sk.constraints[rq]['value'] == 15
    assert _quote(s, sid)[rq]['label'] == 'R15'


def test_diametro_del_foro_diventa_raggio():
    s, sid = _nuovo()
    assert s.sketch_add_circle(sid, [0, 0], 10)['ok']
    sk = s.doc.sketch(sid)
    dq = next(k for k, c in sk.constraints.items() if c['type'] == 'diameter')
    assert s.sketch_dimension_kind(sid, dq, 'radius')['ok']
    assert sk.constraints[dq]['value'] == 10 and _quote(s, sid)[dq]['label'] == 'R10'
    # un cerchio intero non ha lo sviluppo (è la circonferenza): lo si dice
    r = s.sketch_dimension_kind(sid, dq, 'arclength')
    assert not r['ok'] and 'arco' in r['message']


def test_quota_scritta_con_un_nome_resta_col_nome():
    s, sid = _nuovo()
    assert s.sketch_add_circle(sid, [0, 0], 10)['ok']
    sk = s.doc.sketch(sid)
    dq = next(k for k, c in sk.constraints.items() if c['type'] == 'diameter')
    assert s.set_parameter('D', 20)['ok'] if 'D' in s.doc.parameters else s.doc.parameters.setdefault('D', 20)
    assert s.set_dimension(sid, dq, 'D')['ok']
    assert s.sketch_dimension_kind(sid, dq, 'radius')['ok']
    assert sk.constraints[dq]['value'] == 'D/2'
    assert _ss(s, sid).circles[sk.constraints[dq]['refs'][0]][1] == pytest.approx(10)


def test_sviluppo_dell_arco_comanda_il_raccordo():
    s, sid = _nuovo()
    sk, rq = _raccordato(s, sid, 10)
    arco = sk.constraints[rq]['refs'][0]
    r = s.sketch_dimension_kind(sid, rq, 'arclength')
    assert r['ok'], r
    c = sk.constraints[rq]
    assert c['type'] == 'arclength' and not c.get('driven')
    assert c['value'] == pytest.approx(math.pi * 10 / 2, abs=1e-5)           # un quarto di giro
    d = _quote(s, sid)[rq]
    assert d['label'].startswith('⌒15,7')
    # lo sviluppo 31,4 (un quarto di giro): il raggio diventa 20
    assert s.set_dimension(sid, rq, str(round(math.pi * 10, 6)))['ok']
    ss = _ss(s, sid)
    assert ss.status.state != 'non risolto'
    assert ss.arcs[arco][3] == pytest.approx(20, abs=1e-4)
    # e torna raggio
    assert s.sketch_dimension_kind(sid, rq, 'radius')['ok']
    assert sk.constraints[rq]['value'] == pytest.approx(20, abs=1e-4)


def test_sviluppo_di_un_arco_libero_con_la_quota():
    """Con lo strumento Quota: clic sull'arco = raggio; lo sviluppo si mette anche direttamente."""
    s, sid = _nuovo()
    assert s.sketch_add_arc3(sid, [100, 0], [100 * math.cos(math.pi / 4), 100 * math.sin(math.pi / 4)], [0, 100])['ok']
    sk = s.doc.sketch(sid)
    arco = next(k for k, e in sk.entities.items() if e['kind'] == 'arc')
    rq = next(k for k, c in sk.constraints.items() if c['type'] == 'radius')
    assert s.sketch_delete_dimension(sid, rq)['ok']
    r = s.sketch_dimension(sid, 'arclength', [arco])
    assert r['ok'], r
    c = sk.constraints[r['dim']]
    assert c['value'] == pytest.approx(math.pi * 50, abs=1e-4)


def test_quota_di_riferimento_e_ritorno():
    s, sid = _nuovo()
    assert s.sketch_add_rectangle(sid, [0, 0], [100, 50])['ok']
    sk = s.doc.sketch(sid)
    larg = next(k for k, c in sk.constraints.items() if c['type'] == 'length' and c['value'] == 100)
    r = s.sketch_dimension_reference(sid, larg, True)
    assert r['ok'], r
    assert sk.constraints[larg]['driven']
    assert _quote(s, sid)[larg]['label'] == '(100)'
    assert not s.set_dimension(sid, larg, '120')['ok']             # di riferimento: non comanda
    r = s.sketch_dimension_reference(sid, larg, False)
    assert r['ok'], r
    assert not sk.constraints[larg].get('driven')
    assert s.set_dimension(sid, larg, '120')['ok']
    pts = _ss(s, sid).points
    assert max(p[0] for p in pts.values()) == pytest.approx(120)


def test_quota_di_riferimento_che_non_puo_comandare_resta_tale():
    s, sid = _nuovo()
    assert s.sketch_add_rectangle(sid, [0, 0], [100, 50])['ok']
    sk = s.doc.sketch(sid)
    sotto = next(k for k, e in sk.entities.items() if e.get('label') == 'lato sotto')
    sopra = next(k for k, e in sk.entities.items() if e.get('label') == 'lato sopra')
    # la larghezza del lato sopra la decide già il lato sotto (rettangolo): una sua quota sta tra parentesi
    did = sk.dimension('length', sopra, value=100)
    assert s.sketch_dimension_reference(sid, did, True)['ok']
    r = s.sketch_dimension_reference(sid, did, False)
    assert not r['ok'] and 'riferimento' in r['message']
    assert sk.constraints[did]['driven']                              # resta com'era
    assert sotto


def test_le_quote_vecchie_restano_uguali():
    """Un pezzo salvato prima: le sue quote non cambiano tipo da sole."""
    s, sid = _nuovo()
    sk, rq = _raccordato(s, sid, 5)
    tipi = {k: c['type'] for k, c in sk.constraints.items()}
    s.state()
    assert {k: c['type'] for k, c in sk.constraints.items()} == tipi
