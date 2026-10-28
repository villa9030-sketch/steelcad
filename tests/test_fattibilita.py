"""Controlli di fattibilità della lamiera (24/10): avvisi in «Info», mai blocchi."""
from app.service import Service


def _lamiera(**kw):
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 120, 'profondita': 60, 'spessore': 2, 'raggio': 2, 'k': 0.4, **kw})
    return s


def _fatt(s):
    return [w for w in s.state()['warnings'] if w.startswith('Fattibilità')]


def test_pezzo_normale_nessun_avviso():
    s = _lamiera()
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    assert _fatt(s) == []


def test_flangia_corta_e_raggio_stretto():
    s = _lamiera()
    assert s.add_flange('SM1', 'L1', {'length': '6'})['ok']                # appoggia 6 mm, ne servono 8
    assert any('corta per la piegatrice' in w for w in _fatt(s))
    s = _lamiera(raggio=0.5)
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    assert any('raggio interno' in w and 'stretto' in w for w in _fatt(s))


def test_foro_vicino_alla_piega():
    s = _lamiera()
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    for p in ([60, 3], [60, 57], [3, 30], [117, 30]):                   # uno solo è vicino alla piega
        assert s.sketch_add_circle(sid, p, 1.5)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    f = _fatt(s)
    assert len(f) == 1 and 'un foro è' in f[0] and 'FL1' in f[0]


def test_u_stretta():
    s = _lamiera(profondita=20)
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    assert s.add_flange('SM1', 'L3', {'length': '40'})['ok']
    assert any('U stretta' in w for w in _fatt(s))
    s = _lamiera(profondita=20)                                           # sui lati corti: lontane, va bene
    assert s.add_flange('SM1', 'L2', {'length': '40'})['ok']
    assert s.add_flange('SM1', 'L4', {'length': '40'})['ok']
    assert not any('U stretta' in w for w in _fatt(s))
