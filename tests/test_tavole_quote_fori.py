"""Tavole: catene di quote dei fori nella vista dall'alto e scala scelta a mano (21/10)."""
from app.service import Service
from cad_engine import drawings as D


def _staffa():
    s = Service()
    assert s.new_project('lamiera', {'name': 'Staffa', 'larghezza': 200, 'profondita': 120, 'spessore': 3,
                                     'raggio': 1, 'k': 0.21})['ok']
    sk = s.sketch_on_face('SM1/sopra')['sketch']
    for x, y in ((20, 20), (180, 20), (20, 80), (180, 80), (100, 50)):
        assert s.sketch_add_circle(sk, [x, y], 4.25)['ok']
    assert s.create_from_sketch(sk, 'cut', {})['ok']
    return s


def test_catene_dei_fori_e_scala():
    s = _staffa()
    f = D.tavola_pezzo(s.result.body.shape, {'titolo': 'x', 'scala_fissa': '1:2'}, D.etichette_fori(s.doc))
    testi = [t[2] for t in f.testi]
    assert testi.count('80') >= 2 and testi.count('30') >= 2 and '1:2' in testi     # 20 | 80 | 80, 20 | 30 | 30
    g = D.tavola_pezzo(s.result.body.shape, {'titolo': 'x', 'quote_fori': 'no'}, D.etichette_fori(s.doc))
    assert len(g.linee) < len(f.linee)
    assert D._scala_scelta('1:2,5') == 0.4 and D._scala_scelta('auto') is None
