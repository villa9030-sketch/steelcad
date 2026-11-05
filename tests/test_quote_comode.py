"""Le quote comode (05/11, idee da SolidCraft):
- cambiando una lunghezza resta fermo il primo punto (l'angolo da cui hai tirato il rettangolo) e si muove l'altro,
  invece di dividere il cambiamento tra le due punte;
- l'anteprima mentre scrivi il numero: lo sketch com'è con quel numero, senza cambiare niente (niente annulla);
- i pezzi salvati si riaprono uguali (le coordinate cambiano solo quando cambi una quota)."""
import math

from app.service import Service
from cad_engine.document import Document


def _rettangolo_libero(p0=(10, 10), p1=(50, 30)):
    """Un rettangolo 40 × 20 senza quote di posizione: può scivolare (come uno sketch su una faccia appena
    disegnato, a cui hai tolto le quote dall'origine)."""
    s = Service()
    assert s.new_project('zero', {'name': 'Q'})['ok']
    sid = 'S1'
    assert s.sketch_add_rectangle(sid, list(p0), list(p1))['ok']
    sk = s.doc.sketch(sid)
    for k, c in list(sk.constraints.items()):
        if c['type'] in ('hdistance', 'vdistance'):
            assert s.sketch_delete_dimension(sid, k)['ok']
    larg = next(k for k, c in sk.constraints.items() if c['type'] == 'length' and c['value'] == 40)
    alto = next(k for k, c in sk.constraints.items() if c['type'] == 'length' and c['value'] == 20)
    return s, sid, sk, larg, alto


def _punti(s, sid):
    return {p['id']: tuple(p['xy']) for p in s.sketch_view(sid)['sketch']['points']}


def _vicino(a, b):
    return math.dist(a, b) < 1e-6


def test_la_larghezza_cresce_dal_primo_angolo():
    s, sid, sk, larg, alto = _rettangolo_libero()
    assert s.set_dimension(sid, larg, '60')['ok']
    p = _punti(s, sid)
    assert _vicino(p['P1'], (10, 10)), p          # l'angolo da cui hai tirato resta lì
    assert _vicino(p['P2'], (70, 10)), p          # il lato cresce verso destra
    assert _vicino(p['P4'], (10, 30)), p


def test_l_altezza_cresce_in_su_dal_primo_angolo():
    s, sid, sk, larg, alto = _rettangolo_libero()
    assert s.set_dimension(sid, alto, '25')['ok']
    p = _punti(s, sid)
    assert _vicino(p['P1'], (10, 10)) and _vicino(p['P4'], (10, 35)), p


def test_due_quote_una_dopo_l_altra():
    s, sid, sk, larg, alto = _rettangolo_libero()
    assert s.set_dimension(sid, larg, '60')['ok']
    assert s.set_dimension(sid, alto, '25')['ok']
    p = _punti(s, sid)
    assert _vicino(p['P1'], (10, 10)) and _vicino(p['P3'], (70, 35)), p


def test_annulla_torna_com_era():
    s, sid, sk, larg, alto = _rettangolo_libero()
    prima = _punti(s, sid)
    assert s.set_dimension(sid, larg, '60')['ok']
    assert s.undo()['ok']
    dopo = _punti(s, sid)
    assert all(_vicino(prima[k], dopo[k]) for k in prima)


def test_rettangolo_quotato_dall_origine_come_prima():
    """Il caso di tutti i giorni: il rettangolo ha già le quote dall'origine, il primo angolo era già fermo."""
    s = Service()
    assert s.new_project('zero', {'name': 'Q'})['ok']
    assert s.sketch_add_rectangle('S1', [10, 10], [50, 30])['ok']
    sk = s.doc.sketch('S1')
    coord = {k: (e.get('x'), e.get('y')) for k, e in sk.entities.items()}
    larg = next(k for k, c in sk.constraints.items() if c['type'] == 'length' and c['value'] == 40)
    assert s.set_dimension('S1', larg, '60')['ok']
    p = _punti(s, 'S1')
    assert _vicino(p['P1'], (10, 10)) and _vicino(p['P2'], (70, 10))
    # niente coordinate riscritte: il risolutore lo teneva già fermo da solo
    assert coord == {k: (e.get('x'), e.get('y')) for k, e in sk.entities.items()}


def test_simmetrico_cresce_dalle_due_parti():
    """Un rettangolo centrato (punti simmetrici sull'asse): tenere fermo un angolo non si può, cresce dai due lati."""
    s, sid, sk, larg, alto = _rettangolo_libero((-20, 0), (20, 20))
    sk = s.doc.sketch(sid)
    assert s.sketch_add_polyline(sid, [[0, -30], [0, 40]], False, True)['ok']
    asse = [k for k, e in sk.entities.items() if e['kind'] == 'line'][-1]

    def fn():
        for k in [k for k, c in sk.constraints.items() if c['type'] == 'vertical' and c['refs'] == [asse]]:
            sk.remove(k)                    # verticale lo fa già la simmetria (col lato sotto orizzontale)
        sk.constrain('symmetric', 'P1', 'P2', asse)
    assert s._change('simmetria', fn, keep_broken=True)['ok']
    assert s.sketch_view(sid)['sketch']['ok']
    larg = next(k for k, c in sk.constraints.items() if c['type'] == 'length' and c['refs'] == ['L1'])
    assert s.set_dimension(sid, larg, '60')['ok']
    p = _punti(s, sid)
    assert abs((p['P1'][0] + p['P2'][0]) / 2) < 1e-6, p           # resta centrato sull'asse (x = 0)
    assert abs(abs(p['P2'][0] - p['P1'][0]) - 60) < 1e-6, p


def test_riaperto_resta_uguale():
    """Le coordinate scritte quando cambi la quota fanno parte del file: riaperto, il disegno è lo stesso."""
    s, sid, sk, larg, alto = _rettangolo_libero()
    assert s.set_dimension(sid, larg, '60')['ok']
    prima = _punti(s, sid)
    d = Document.from_dict(s.doc.to_dict())
    from cad_engine.sketch import solve
    ss = solve(d.sketch(sid), d.resolved_parameters())
    assert all(_vicino(ss.points[k], prima[k]) for k in prima)


def test_anteprima_non_cambia_niente():
    s, sid, sk, larg, alto = _rettangolo_libero()
    prima = _punti(s, sid)
    passi = len(s.history.done)
    r = s.sketch_dimension_preview(sid, larg, '70')
    assert r['ok'] and r['sketch']
    p = {q['id']: tuple(q['xy']) for q in r['sketch']['points']}
    assert _vicino(p['P1'], (10, 10)) and _vicino(p['P2'], (80, 10))        # anche l'anteprima tiene il primo angolo
    assert '70' in [d['label'] for d in r['dimensions']]
    assert len(s.history.done) == passi                                      # niente nell'annulla
    dopo = _punti(s, sid)
    assert all(_vicino(prima[k], dopo[k]) for k in prima)
    assert sk.constraints[larg]['value'] == 40


def test_anteprima_numero_a_meta_o_impossibile():
    s, sid, sk, larg, alto = _rettangolo_libero()
    assert s.sketch_dimension_preview(sid, larg, '12,')['ok']               # mentre scrivi: non è un errore
    r = s.sketch_dimension_preview(sid, larg, 'abc')
    assert r.get('sketch') is None
    r = s.sketch_dimension_preview(sid, larg, '0')
    assert r.get('sketch') is None                                          # lato lungo zero: niente anteprima


def test_anteprima_del_diametro_e_del_parametro():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 200, 'profondita': 100, 'spessore': 2})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_circle(sid, [60, 50], 5)['ok']
    d = next(x for x in s.state()['dimensions'] if x['sketch'] == sid and x['type'] == 'diameter')
    r = s.sketch_dimension_preview(sid, d['dim'], '30')
    assert r['ok'] and abs(r['sketch']['circles'][-1]['r'] - 15) < 1e-6
    assert abs(s.doc.sketch(sid).entities[r['sketch']['circles'][-1]['id']]['r'] - 5) < 1e-6
