"""03/11, tavole dei telai in tubo: le catene di quote sommano esattamente il fuori tutto (tubi e luci, prima mancava lo
spessore dei tubi: 343,5 + 373,5 ≠ 807), la scala nel cartiglio è una scala normale da officina (1:15, non
«1:14,14 (A2 1:10)»), il cartiglio dice «DISEGNO DI ASSIEME» e nel cancello le quote in basso non si sovrappongono."""
import pytest

from app.service import Service
from cad_engine import drawings as D

from test_uscite_officina import _telaio


@pytest.fixture(scope='module')
def telaio():
    return _telaio()


@pytest.fixture(scope='module')
def cancello():
    s = Service()
    assert s.new_project('cancello', {'name': 'Cancello', 'L': 1500, 'H': 1200, 'telaio': '60x40x3', 'sbarre': '20x20x2',
                                      'passo': 120})['ok']
    return s


def _fogli(s, formato='A3'):
    s._tavole_base = None
    return s._fogli({**s.drawing_fields()['fields'], 'formato': formato})


def _quote(f, gruppo):
    """Le quote di un gruppo: (orizzontale?, valore)."""
    return [(abs(e['a'][1] - e['b'][1]) < 1e-6, e['valore']) for e in f.elementi.values()
            if e.get('kind') == 'quota' and str(e.get('padre') or '') == gruppo]


def _somma_scritta(quote, orizz):
    return round(sum(float(D.fmt(v).replace(',', '.')) for o, v in quote if o == orizz), 2)


def test_catene_dei_tubi_sommano_il_fuori_tutto(telaio):
    vista = _fogli(telaio)[0]
    attese = {'fronte': (807, 795), 'sinistra': (725, 795), 'alto': (807, 725)}
    for v, (larg, alt) in attese.items():
        catena = _quote(vista, f'vista:{v}/luci')
        tutto = [x for o, x in _quote(vista, f'vista:{v}')]
        assert larg in [round(x, 2) for x in tutto] and alt in [round(x, 2) for x in tutto], (v, tutto)
        if any(o for o, _ in catena):
            assert _somma_scritta(catena, True) == larg, (v, catena)
        if any(not o for o, _ in catena):
            assert _somma_scritta(catena, False) == alt, (v, catena)
    # i tubi ci sono nella catena (30), e le luci di prima anche
    davanti = [round(x, 2) for _, x in _quote(vista, 'vista:fronte/luci')]
    assert davanti.count(30) >= 3 and 343.5 in davanti and 373.5 in davanti


def test_catena_del_cancello_somma(cancello):
    vista = _fogli(cancello)[0]
    q = _quote(vista, 'vista:fronte')
    assert 1500 in [round(x, 2) for o, x in q if o]
    # sbarre a passo costante: bordo → prima, n × passo, ultima → bordo
    passo = [x for o, x in q if o and round(x, 2) != 1500]
    assert round(sum(passo), 2) == 1500, passo


def test_scala_normale_nel_cartiglio(telaio):
    for formato in ('A3', 'A4', 'A2'):
        f = _fogli(telaio, formato)[0]
        sc = f.testi[f.i_scala][2]
        assert '(' not in sc and 'A2' not in sc, sc
        assert any(abs(D._scala_da_testo(sc) - n) < 1e-9 for n in D.SCALE_NORMALI), sc
        assert abs(f.scala - D._scala_da_testo(sc)) < 1e-6          # la scala scritta è quella vera del foglio


def test_struttura_disegno_di_assieme(telaio):
    vista, taglio = _fogli(telaio)
    t = [x[2] for x in vista.testi]
    assert 'DISEGNO DI ASSIEME' in t and 'DISEGNO DI PARTICOLARE' not in t
    assert 'DISTINTA DI TAGLIO' in [x[2] for x in taglio.testi]


def _scatola(testo):
    l, (x, y), t, h, al = testo
    w = len(t) * h * 0.55
    if al == 'cv':
        return (x - h / 2, y - w / 2, x + h / 2, y + w / 2)
    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def _toccano(a, b, m=0.0):
    return a[0] < b[2] - m and b[0] < a[2] - m and a[1] < b[3] - m and b[1] < a[3] - m


@pytest.mark.parametrize('chi', ['telaio', 'cancello'])
def test_numeri_delle_quote_non_si_sovrappongono(chi, request):
    """I numeri delle quote delle viste non si toccano tra loro né con le frecce (il «174» del cancello sulle frecce,
    i «30» dei tubi sopra le luci)."""
    f = _fogli(request.getfixturevalue(chi))[0]
    testi = [(t, g) for t, g in zip(f.testi, f.testi.tag) if t[0] == 'quote' and str(g).startswith('vista:')]
    scatole = [_scatola(t) for t, _ in testi]
    for i in range(len(scatole)):
        for j in range(i + 1, len(scatole)):
            assert not _toccano(scatole[i], scatole[j]), (testi[i][0][2], testi[j][0][2])
    frecce = [p for (l, p), g in zip(f.pieni, f.pieni.tag) if l == 'quote' and str(g).startswith('vista:')]
    for (t, g), sc in zip(testi, scatole):
        for pts in frecce:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            assert not _toccano(sc, (min(xs), min(ys), max(xs), max(ys)), 0.05), (t[2], g)
