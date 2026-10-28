"""Saldature segnate sugli spigoli del pezzo (24/10): si vedono, i metri vanno in distinta, restano se il pezzo cambia."""
import math

from app.service import Service


def _spigolo_dritto(s, lung):
    """Un punto a metà di uno spigolo dritto lungo «lung» (dagli spigoli della scena)."""
    for e in s.scene()['objects'][0]['edges']:
        a, b = e[:3], e[-3:]
        if abs(math.dist(a, b) - lung) < 1e-6 and len(e) == 6:
            return [(a[i] + b[i]) / 2 for i in range(3)]
    raise AssertionError('spigolo non trovato')


def test_saldatura_sullo_spigolo_e_in_distinta():
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 300, 'profondita': 200, 'spessore': 3, 'raggio': 3, 'k': 0.4})
    p = _spigolo_dritto(s, 300)
    r = s.add_saldatura([p], {'tipo': 'angolo', 'a': '4'})
    assert r['ok'], r
    w = s.state()['saldature']
    assert len(w) == 1 and w[0]['tipo'] == 'angolo' and w[0]['a'] == '4' and not w[0]['persa']
    assert abs(w[0]['m'] - 0.3) < 1e-6 and w[0]['linee']
    s.undo()
    assert s.state()['saldature'] == []
    s.redo()
    assert len(s.state()['saldature']) == 1
    assert s.del_saldatura(0)['ok'] and s.state()['saldature'] == []


def test_saldatura_resta_se_il_pezzo_cambia():
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 300, 'profondita': 200, 'spessore': 3, 'raggio': 3, 'k': 0.4})
    assert s.add_saldatura([_spigolo_dritto(s, 300)], {'tipo': 'V', 'a': '3'})['ok']
    nomi = [p['name'] for p in s.state()['parameters']]
    larg = next(n for n in nomi if n.upper() in ('W', 'LARGHEZZA'))
    assert s.set_parameter(larg, 400)['ok']
    w = s.state()['saldature'][0]
    assert not w['persa'] and abs(w['m'] - 0.4) < 1e-6
