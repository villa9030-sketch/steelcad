"""La distinta della tavola d'assieme si ritocca a mano (28/10): celle, righe tolte, righe in più."""
import build123d as bd

from cad_engine import drawings as D
from cad_engine.tavole_ritocchi import oggetti, ritocca

RIGHE = [['1', 'Fondo', '1', 'S235', '2 mm', '33,33'], ['2', 'Rinforzo', '4', 'S235', '10 mm', '2,31'],
         ['3', 'Vite ISO 10642 M8x20', '8', '—', '', '0,09']]


def _tavola(formato='A3'):
    forme = [(1, bd.Box(200, 100, 2)), (2, bd.Box(20, 20, 10).moved(bd.Location((0, 0, 6))))]
    f = D.tavola_assieme(forme, {'titolo': 'Prova'}, [list(r) for r in RIGHE], 'A2')
    return D.in_formato(f, formato)


def _testi(f):
    return [t for (l, p, t, h, al), tag in zip(f.testi, f.testi.tag) if tag == 'distinta']


def test_la_distinta_si_clicca():
    o = next(x for x in oggetti(_tavola()) if x['id'] == 'distinta')
    assert o['kind'] == 'distinta' and o['righe'] == RIGHE and o['intest'][1] == 'Descrizione'


def test_celle_righe_tolte_e_in_piu():
    f = D.copia_foglio(_tavola())
    prima = [ (round(p[0], 2), round(p[1], 2)) for (l, p, t, h, al), tag in zip(f.testi, f.testi.tag) if tag == 'distinta' and t == 'DISTINTA'][0]
    ritocca(f, {'distinta': {'celle': {'0:1': 'Fondo zincato', '1:2': '6'}, 'via': [2],
                             'nuove': [['3', 'Verniciatura RAL 7035', '1', '', '', '']]}})
    t = _testi(f)
    assert 'Fondo zincato' in t and 'Fondo' not in t
    assert '6' in t and 'Vite ISO 10642 M8x20' not in t
    assert any(x.startswith('Verniciatura') for x in t)
    # stesse righe di prima (una tolta, una in più): il titolo resta dov'era
    dopo = [(round(p[0], 2), round(p[1], 2)) for (l, p, tt, h, al), tag in zip(f.testi, f.testi.tag) if tag == 'distinta' and tt == 'DISTINTA'][0]
    assert dopo == prima


def test_ritocco_uguale_su_ogni_formato():
    for formato in ('A4', 'A3', 'A1'):
        f = D.copia_foglio(_tavola(formato))
        ritocca(f, {'distinta': {'celle': {'0:1': 'Fondo zincato'}}})
        assert 'Fondo zincato' in _testi(f)
