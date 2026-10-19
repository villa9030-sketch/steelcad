"""Il comando Quota come negli altri CAD (19/10: rispondeva sempre "misura già decisa", perché disegnando le quote
si mettono da sole): sulla stessa misura si riprende la quota che c'è; se un'altra quota la decide, la nuova
prende il suo posto."""
from app.service import Service


def _sketch():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 300, 'spessore': 2})['ok']
    f = next(x for x in s.scene()['objects'][0]['faces'] if x['name'] and x['name'].endswith('sopra'))
    sid = s.sketch_on_face(f['name'])['sketch']
    assert s.sketch_add_rectangle(sid, [50, 50], [150, 100])['ok']
    assert s.sketch_add_circle(sid, [250, 200], 20)['ok']
    return s, sid, s.doc.sketch(sid)


def test_stessa_misura_riprende_la_quota_che_ce():
    s, sid, sk = _sketch()
    c = next(k for k, e in sk.entities.items() if e['kind'] == 'circle')
    n = len(sk.constraints)
    r = s.sketch_dimension(sid, 'diameter', [c])
    assert r['ok'] and r['dim'] in sk.constraints and len(sk.constraints) == n
    assert s.set_dimension(sid, r['dim'], '30')['ok']
    assert abs(sk.constraints[r['dim']]['value'] - 30) < 1e-9


def test_lato_opposto_del_rettangolo_prende_il_posto_della_quota():
    s, sid, sk = _sketch()
    sopra = next(k for k, e in sk.entities.items() if e['kind'] == 'line' and e.get('label') == 'lato sopra')
    r = s.sketch_dimension(sid, 'length', [sopra])
    assert r['ok'] and 'ora comanda la tua' in r['message']
    assert s.set_dimension(sid, r['dim'], '80')['ok']
    v = s.sketch_view(sid)['sketch']
    import math
    lati = sorted(round(math.dist(l['xa'], l['xb']), 6) for l in v['lines'] if not l.get('ref'))
    assert lati == [50, 50, 80, 80]
    assert v['ok']


def test_angolo_scritto_come_formula_non_blocca_lo_schermo():
    """19/10: flangia sulla punta con angolo "180-64": il pezzo era giusto ma lo stato saltava (scritta dell'albero),
    lo schermo restava vecchio e ogni nuovo tentativo diceva "sulla punta c'è già una flangia"."""
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 300, 'spessore': 2})['ok']
    assert s.set_sheet_tech('SM1', {'radius': 1, 'method': 'k', 'k': 0.33})['ok']
    assert s.add_flange('SM1', 'L4', {'length': '100'})['ok']
    r = s.add_flange('SM1', None, {'length': '50', 'angle': '180-64'}, parent='FL1')
    assert r['ok'], r.get('message')
    testi = str(r['state']['tree'])
    assert '116°' in testi
