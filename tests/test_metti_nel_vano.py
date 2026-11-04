"""Metti nel vano (04/11, Stefano: «accoppiare il pannello dentro il telaio è difficile, deve essere facile»).
L'anta dell'ufficio (tubi 40×40, traverso a 1100) e la pannellatura 1058 × 918 disegnata sdraiata: un clic sul
pannello, uno sul telaio, e va in piedi nel vano sotto il traverso, girata, centrata con 1 mm per lato, a filo
davanti; gli accoppiamenti veri la tengono centrata se il telaio cambia."""
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from app.service import Service
from cad_engine import assembly as A

DATI = Path(__file__).parent / 'data' / 'vano'


@pytest.fixture()
def assieme(tmp_path):
    for f in ('anta', 'pannello'):
        shutil.copy(DATI / f'{f}.steelcad', tmp_path / f'{f}.steelcad')
    s = Service()
    assert s.new_assembly_con_pezzi('Ufficio', [{'path': str(tmp_path / 'anta.steelcad')},
                                                {'path': str(tmp_path / 'pannello.steelcad')}])['ok']
    return s, tmp_path


def _clic(s, iid):
    o = next(o for o in s.scene()['objects'] if o['id'] == iid)
    return {'inst': iid, 'face': o['faces'][0]['index']}


def _ingombro(s, iid):
    i = s.asm.instance(iid)
    b = A.placed_shape(s.asm_parts[i['file']], i['R'], i['T']).bounding_box()
    return [round(v, 2) for v in (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)]


def test_trova_i_due_vani_e_sceglie_quello_dove_ci_sta(assieme):
    s, _ = assieme
    r = s.asm_vano(_clic(s, 'I2'), _clic(s, 'I1'), prova=True)
    assert r['ok'], r.get('message')
    assert [(v['nome'], v['W'], v['H'], v['ci_sta']) for v in r['vani']] == [
        ('sotto', 920, 1060, True), ('sopra', 920, 920, False)]
    assert r['vano'] == 0
    assert {g['lato']: g['mm'] for g in r['giochi']} == {'sinistra': 1, 'destra': 1, 'sotto': 1, 'sopra': 1}


def test_il_pannello_va_in_piedi_centrato_a_filo_davanti(assieme):
    s, _ = assieme
    r = s.asm_vano(_clic(s, 'I2'), _clic(s, 'I1'))
    assert r['ok'], r.get('message')
    # in piedi nel vano 40..960 × 40..1100, il fondo davanti (y = −20) e le pieghe verso dietro
    assert _ingombro(s, 'I2') == [41, -20, 41, 959, 20, 1099]
    assert sorted(m['type'] for m in s.asm.mates) == ['centra', 'centra', 'distanza']
    assert all(m['da'] == 'vano' for m in s.asm.mates)
    assert not s.asm.warnings
    assert 'Nessuna' in s.asm_interferences()['message']
    assert '1 mm per lato' in r['message'] and 'a filo davanti' in r['message']


def test_capovolto_le_pieghe_vanno_davanti(assieme):
    s, _ = assieme
    s.asm_vano(_clic(s, 'I2'), _clic(s, 'I1'), {'capovolgi': True})
    i = s.asm.instance('I2')
    fondo = np.array(i['R']) @ np.array([0, 0, -1.0])          # il fondo della vaschetta guardava giù (−z)
    assert np.allclose(fondo, [0, 1, 0], atol=1e-9)             # ora guarda dietro
    assert _ingombro(s, 'I2') == [41, -20, 41, 959, 20, 1099]


def test_se_il_telaio_si_allarga_il_pannello_resta_centrato(assieme):
    s, d = assieme
    assert s.asm_vano(_clic(s, 'I2'), _clic(s, 'I1'))['ok']
    assert s.save(str(d / 'ufficio.steelcad-asm'))['ok']
    f = d / 'anta.steelcad'
    j = json.loads(f.read_text(encoding='utf-8'))
    j['features'][0]['constraints']['D1']['value'] = 1100        # l'anta da 1000 a 1100
    f.write_text(json.dumps(j), encoding='utf-8')
    s2 = Service()
    assert s2.open(str(d / 'ufficio.steelcad-asm'))['ok']
    x0, _, z0, x1, _, z1 = _ingombro(s2, 'I2')
    assert (x0, x1) == (91, 1009)                               # vano 40..1060: 51 mm per lato
    assert (z0, z1) == (41, 1099)


def test_se_non_ci_sta_lo_dice_con_le_misure(assieme):
    s, d = assieme
    f = d / 'pannello.steelcad'
    j = json.loads(f.read_text(encoding='utf-8'))
    j['parameters']['W'] = 1080
    f.write_text(json.dumps(j), encoding='utf-8')
    s2 = Service()
    assert s2.new_assembly_con_pezzi('Ufficio', [{'path': str(d / 'anta.steelcad')}, {'path': str(f)}])['ok']
    r = s2.asm_vano(_clic(s2, 'I2'), _clic(s2, 'I1'), prova=True)
    assert not r['ok']
    assert '918 × 1080' in r['message'] and '920 × 1060' in r['message'] and '20 mm' in r['message']
