"""Gioco tra due pezzi (05/11, idea da SolidCraft inspect.clearance): clic su una faccia di un pezzo e su quella di
fronte dell'altro → quanto spazio c'è tra le due facce e tra i due pezzi interi; se si toccano o uno entra
nell'altro lo dice (con il pezzo in comune, lo stesso conto delle interferenze).
Il ferma plexi e il plexiglass 913 × 913 (tests/data/vano): nella scanalatura 0,5 mm per lato."""
import shutil
from pathlib import Path

import pytest

from app.service import Service
from cad_engine import assembly as A

DATI = Path(__file__).parent / 'data' / 'vano'


@pytest.fixture()
def ferma(tmp_path):
    for f in ('ferma_plexi', 'plexi'):
        shutil.copy(DATI / f'{f}.steelcad', tmp_path / f'{f}.steelcad')
    s = Service()
    assert s.new_assembly_con_pezzi('Ferma', [{'path': str(tmp_path / 'ferma_plexi.steelcad')},
                                              {'path': str(tmp_path / 'plexi.steelcad')}])['ok']
    return s


def _faccia(s, iid, x, nx):
    """L'indice della faccia piana dell'istanza al suo posto, a quella x e con la normale verso nx (±1)."""
    import build123d as bd
    from cad_engine.topology.naming import _faces_of
    i = s.asm.instance(iid)
    sp = A.placed_shape(s.asm_parts[i['file']], i['R'], i['T'])
    for k, f in enumerate(_faces_of(sp.wrapped)):
        bf = bd.Face(f)
        if bf.geom_type != bd.GeomType.PLANE:
            continue
        c = bf.center()
        if abs(c.X - x) < 1e-6 and abs(bf.normal_at(c).X - nx) < 1e-6:
            return k
    raise AssertionError(f'nessuna faccia a x={x}')


def _nel_vano(s):
    o = {x['id']: x for x in s.scene()['objects']}
    r = s.asm_vano({'inst': 'I2', 'face': o['I2']['faces'][0]['index']}, {'inst': 'I1', 'face': o['I1']['faces'][0]['index']})
    assert r['ok'], r.get('message')


def test_lontani_la_distanza_piu_corta(ferma):
    s = ferma
    r = s.asm_gioco({'inst': 'I1'}, {'inst': 'I2'})
    assert r['ok'], r.get('message')
    pz = r['gioco']['pezzi']
    assert pz['stato'] == 'gioco' and pz['mm'] == pytest.approx(50)
    assert sum((a - b) ** 2 for a, b in zip(pz['p'], pz['q'])) ** 0.5 == pytest.approx(50)
    assert '50 mm' in r['message'] and 'facce' not in r['gioco']


def test_plexiglass_nella_scanalatura_mezzo_millimetro_per_lato(ferma):
    s = ferma
    _nel_vano(s)
    destra = s.asm_gioco({'inst': 'I2', 'face': _faccia(s, 'I2', 915.5, 1), 'pt': [915.5, 400, 10]},
                         {'inst': 'I1', 'face': _faccia(s, 'I1', 916, -1)})
    assert destra['ok'], destra.get('message')
    fc = destra['gioco']['facce']
    assert fc['mm'] == pytest.approx(0.5)
    assert fc['p'] == pytest.approx([915.5, 400, 10]) and fc['q'] == pytest.approx([916, 400, 10])   # dove si è cliccato
    sinistra = s.asm_gioco({'inst': 'I2', 'face': _faccia(s, 'I2', 2.5, -1)}, {'inst': 'I1', 'face': _faccia(s, 'I1', 2, 1)})
    assert sinistra['gioco']['facce']['mm'] == pytest.approx(0.5)
    assert destra['message'].startswith('Tra le due facce: 0,5 mm.')


def test_tra_i_pezzi_interi_dice_che_entrano_come_le_interferenze(ferma):
    s = ferma
    _nel_vano(s)
    # il plexiglass sta sulla battuta e lo spigolo entra di 0,13 nei raggi delle pieghe: lo dicono anche le interferenze
    interf = s.asm_interferences()['interferences']
    r = s.asm_gioco({'inst': 'I1'}, {'inst': 'I2'})
    pz = r['gioco']['pezzi']
    assert pz['stato'] == 'dentro' and pz['mm'] == 0
    assert len(interf) == 1 and pz['volume'] == pytest.approx(interf[0]['volume'])
    assert pz['mesh']['positions'] and len(pz['centro']) == 3
    assert 'entrano uno nell’altro' in r['message']


def test_si_toccano(ferma):
    s = ferma
    i = s.asm.instance('I2')
    i['T'] = [i['T'][0] - 50, i['T'][1], i['T'][2]]          # il plexiglass 50 più in qua: accostato, a contatto
    r = s.asm_gioco({'inst': 'I1'}, {'inst': 'I2'})
    assert r['gioco']['pezzi']['stato'] == 'tocca'
    assert 'si toccano' in r['message']


def test_stesso_pezzo_o_fuori_assieme(ferma):
    s = ferma
    r = s.asm_gioco({'inst': 'I1'}, {'inst': 'I1'})
    assert not r['ok'] and 'due pezzi diversi' in r['message']
    assert not Service().asm_gioco({'inst': 'I1'}, {'inst': 'I2'})['ok']
