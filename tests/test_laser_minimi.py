"""03/11 (secondo giro) — misure minime per il laser in «Prepara per il laser»: foro più piccolo dello spessore,
ponticelli sottili tra fori o col bordo, linguette strette. Avvisi da leggere, non blocchi; niente avvisi falsi sui
pezzi normali (vaschetta, piastra forata, angoli tondi)."""
import build123d as bd
import pytest

from app.service import Service
from cad_engine import laser_minimi


@pytest.fixture
def piastra():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 200, 'profondita': 100, 'spessore': 3, 'raggio': 3, 'k': 0.4})['ok']
    return s


def _laser(s):
    return [a for a in s.prepara_info()['controllo']['avvisi'] if a.startswith('Laser')]


def test_pezzi_normali_nessun_avviso(piastra):
    s = piastra
    assert s.fori_guidati(s.fori_faccia(), {'tipo': 'tondo', 'd': 10, 'disposizione': 'angoli', 'bordo': 20})['ok']
    assert s.angoli_sviluppo(None, 'raggio', 8)['ok']
    assert _laser(s) == []
    v = Service()
    assert v.new_project('lamiera', {'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.4})['ok']
    assert v.piega_bordi('SM1', [{'kind': 'edge', 'ref': f'L{i}'} for i in range(1, 5)], {'length': '30'}, 'chiusi')['ok']
    assert _laser(v) == []


def test_foro_piu_piccolo_dello_spessore(piastra):
    s = piastra
    assert s.fori_guidati(s.fori_faccia(), {'tipo': 'tondo', 'd': '2,5', 'disposizione': 'centro'})['ok']
    av = _laser(s)
    assert len(av) == 1 and 'un foro è più piccolo dello spessore' in av[0] and '2,5' in av[0], av
    info = s.prepara_info()
    assert info['controllo']['ok']                             # non blocca: il DXF si fa lo stesso
    assert next(v for v in info['voci'] if v['id'] == 'laser')['si']


def test_asola_piu_stretta_dello_spessore(piastra):
    s = piastra
    assert s.fori_guidati(s.fori_faccia(), {'tipo': 'asola', 'larg': 20, 'alt': 2, 'disposizione': 'centro'})['ok']
    av = _laser(s)
    assert len(av) == 1 and 'più piccolo dello spessore' in av[0] and '2 mm' in av[0], av


def test_ponticello_tra_fori_e_col_bordo(piastra):
    s = piastra
    # fila di 3 fori Ø10 a passo 11: tra uno e l'altro resta 1 mm (spessore 3)
    assert s.fori_guidati(s.fori_faccia(), {'tipo': 'tondo', 'd': 10, 'disposizione': 'fila', 'n': 3, 'passo': 11,
                                            'verso': 'x', 'lato': 'mezzo'})['ok']
    av = _laser(s)
    assert len(av) == 1 and 'tra 2 coppie di fori' in av[0] and '1 mm' in av[0], av
    s.undo()
    # un foro Ø10 col centro a 6 dal bordo: tra il foro e il bordo 1 mm
    assert s.fori_guidati(s.fori_faccia(), {'tipo': 'tondo', 'd': 10, 'disposizione': 'punti', 'punti': [[100, 6]]})['ok']
    av = _laser(s)
    assert len(av) == 1 and 'tra 1 foro e il bordo' in av[0], av


def test_linguetta_stretta():
    # piastra 100 × 50 con una linguetta larga 1,5 (spessore 3) che sporge di 10 in alto
    pts = [(0, 0), (100, 0), (100, 50), (51.5, 50), (51.5, 60), (50, 60), (50, 50), (0, 50)]
    f = bd.Face(bd.Wire.make_polygon([bd.Vector(x, y, 0) for x, y in pts], close=True))
    av = laser_minimi.controlla(f, 3)
    assert len(av) == 1 and 'una parte che sporge è larga solo 1,5 mm' in av[0], av
    # una fessura stretta (il taglio che entra) non è una linguetta
    pts = [(0, 0), (100, 0), (100, 50), (51.5, 50), (51.5, 40), (50, 40), (50, 50), (0, 50)]
    f = bd.Face(bd.Wire.make_polygon([bd.Vector(x, y, 0) for x, y in pts], close=True))
    assert laser_minimi.controlla(f, 3) == []
