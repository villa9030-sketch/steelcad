"""03/11, «e le viste?»: nell'editor delle tavole la scala delle viste di un foglio (tutte insieme, il cartiglio la
scrive, le quote restano giuste) e la grandezza dell'isometrica in %: ritocchi['scala'] e ritocchi['iso']."""
import pytest

from cad_engine.tavole_ritocchi import oggetti

from test_uscite_officina import _telaio


def _fogli(s, r=None):
    s.doc.meta['tavole'] = {'foglio1': r} if r else {}
    s._tavole_base = None
    return s._fogli({**s.drawing_fields()['fields'], 'formato': 'A3'})


def _bb(f, id_):
    return next(o['bbox'] for o in oggetti(f) if o['id'] == id_)


def _scritta_scala(f):
    testi = [tx for (l, p, tx, h, al), t in zip(f.testi, f.testi.tag) if t == 'cartiglio']
    return [t for t in testi if t.startswith('1:')]


@pytest.fixture(scope='module')
def telaio():
    return _telaio()


def test_scala_delle_viste_scelta_a_mano(telaio):
    f0 = _fogli(telaio)[0]
    assert _scritta_scala(f0) == ['1:15']
    f = _fogli(telaio, {'scala': '1:20'})[0]
    assert _scritta_scala(f) == ['1:20']
    for v in ('vista:fronte', 'vista:alto', 'vista:sinistra'):     # tutte le viste più piccole, insieme
        assert f.elementi[v]['T'][0] == pytest.approx(f0.elementi[v]['T'][0] * 15 / 20)
    # le quote dicono sempre le misure vere
    valori = sorted(round(e['valore'], 1) for e in f.elementi.values() if e.get('kind') == 'quota' and e.get('padre') == 'vista:fronte')
    assert 807 in valori and 795 in valori


def test_isometrica_piu_grande(telaio):
    f0 = _fogli(telaio)[0]
    f = _fogli(telaio, {'iso': 1.3})[0]
    a, b = _bb(f0, 'vista:iso'), _bb(f, 'vista:iso')
    assert (b[2] - b[0]) == pytest.approx(1.3 * (a[2] - a[0]), rel=0.05)
    assert _scritta_scala(f) == ['1:15']                           # le viste non cambiano
    assert _bb(f, 'vista:fronte') == pytest.approx(_bb(f0, 'vista:fronte'))
    _fogli(telaio)
