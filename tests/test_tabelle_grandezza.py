"""03/11: «la distinta di taglio non posso ingrandirla o rimpicciolirla, come le viste o l'isometrica». Nell'editor
delle tavole la distinta di taglio dei telai (con i totali per profilo) e la distinta dell'assieme si ingrandiscono e
si spostano: ritocchi['tabelle'][id] = {'k', 'd'}."""
import pytest

from cad_engine import drawings as D
from cad_engine.tavole_ritocchi import oggetti, ritocca

from test_uscite_officina import _telaio


def _bb(f, tag):
    pts = [p for (l, ps), t in zip(f.linee, f.linee.tag) if t == tag for p in ps]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


@pytest.fixture(scope='module')
def foglio_taglio():
    s = _telaio()
    s._tavole_base = None
    fogli = s._fogli({**s.drawing_fields()['fields'], 'formato': 'A3'})
    return next(f for f in fogli if any(o['id'] == 'tabella:taglio' for o in oggetti(f)))


def test_la_distinta_di_taglio_si_seleziona(foglio_taglio):
    o = next(o for o in oggetti(foglio_taglio) if o['id'] == 'tabella:taglio')
    assert o['kind'] == 'tabella' and o['label'] == 'Distinta di taglio'
    testi = [tx for (l, p, tx, h, al), t in zip(foglio_taglio.testi, foglio_taglio.testi.tag) if t == 'tabella:taglio']
    assert 'DISTINTA DI TAGLIO' in testi and any('TOTALI PER PROFILO' in t for t in testi)   # i totali vengono con lei


def test_ingrandita_dall_angolo_in_alto_a_sinistra_e_spostata(foglio_taglio):
    x0, y0, x1, y1 = _bb(foglio_taglio, 'tabella:taglio')
    h0 = max(h for (l, p, tx, h, al), t in zip(foglio_taglio.testi, foglio_taglio.testi.tag) if t == 'tabella:taglio')
    g = D.copia_foglio(foglio_taglio)
    ritocca(g, {'tabelle': {'tabella:taglio': {'k': 1.5}}})
    a0, b0, a1, b1 = _bb(g, 'tabella:taglio')
    assert (a0, b1) == pytest.approx((x0, y1))                    # l'angolo in alto a sinistra resta fermo
    assert a1 - a0 == pytest.approx(1.5 * (x1 - x0))
    assert b1 - b0 == pytest.approx(1.5 * (y1 - y0))
    assert max(h for (l, p, tx, h, al), t in zip(g.testi, g.testi.tag) if t == 'tabella:taglio') == pytest.approx(1.5 * h0)
    g = D.copia_foglio(foglio_taglio)
    ritocca(g, {'tabelle': {'tabella:taglio': {'k': 0.8, 'd': [20, -10]}}})
    a0, b0, a1, b1 = _bb(g, 'tabella:taglio')
    assert (a0, b1) == pytest.approx((x0 + 20, y1 - 10))
    assert a1 - a0 == pytest.approx(0.8 * (x1 - x0))
    assert _bb(g, 'cartiglio') == pytest.approx(_bb(foglio_taglio, 'cartiglio'))   # il resto del foglio non si muove


def test_la_distinta_dell_assieme_cresce_dal_basso_sopra_il_cartiglio():
    from test_distinta_ritocchi import _tavola
    f0 = _tavola()
    x0, y0, x1, y1 = _bb(f0, 'distinta')
    g = D.copia_foglio(f0)
    ritocca(g, {'distinta': {'celle': {'0:1': 'Fondo zincato'}}, 'tabelle': {'distinta': {'k': 1.3}}})
    a0, b0, a1, b1 = _bb(g, 'distinta')
    assert (a0, b0) == pytest.approx((x0, y0))                    # la riga di sotto resta sopra il cartiglio
    assert a1 - a0 == pytest.approx(1.3 * (x1 - x0))
    testi = [tx for (l, p, tx, h, al), t in zip(g.testi, g.testi.tag) if t == 'distinta']
    assert 'Fondo zincato' in testi                               # le celle ritoccate restano, ingrandite
