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


# 05/11: il ferma plexi (lamiera piegata con la scanalatura alta 16 su tre lati, il quarto lato senza) e il
# plexiglass 913 × 913 sp. 16: non passa nel vano (872), entra nella scanalatura sotto
@pytest.fixture()
def ferma(tmp_path):
    for f in ('ferma_plexi', 'plexi'):
        shutil.copy(DATI / f'{f}.steelcad', tmp_path / f'{f}.steelcad')
    s = Service()
    assert s.new_assembly_con_pezzi('Ferma', [{'path': str(tmp_path / 'ferma_plexi.steelcad')},
                                              {'path': str(tmp_path / 'plexi.steelcad')}])['ok']
    return s, tmp_path


def test_il_plexiglass_entra_nella_scanalatura(ferma):
    s, _ = ferma
    r = s.asm_vano(_clic(s, 'I2'), _clic(s, 'I1'), prova=True)
    assert r['ok'], r.get('message')
    assert r['sede']['alta'] == 16 and r['sede']['giu'] == 1
    assert r['vani'][0]['W'] == 914 and r['vani'][0]['H'] is None          # il lato dietro è aperto
    assert {g['lato']: g['mm'] for g in r['giochi']} == {'sinistra': 0.5, 'destra': 0.5, 'davanti': 0.5, 'dietro': None}
    assert 0.1 < r['tocca'] < 0.2                                           # lo spigolo nei raggi da 1 mm
    r = s.asm_vano(_clic(s, 'I2'), _clic(s, 'I1'))
    assert r['ok'], r.get('message')
    # posato sulla battuta (z 2), 0,5 dalle pareti; dietro lo stesso gioco (Stefano: «b»)
    assert _ingombro(s, 'I2') == [2.5, 2.5, 2, 915.5, 915.5, 18]
    assert sorted((m['type'], m.get('lato')) for m in s.asm.mates) == [('centra', None), ('distanza', 'davanti'),
                                                                        ('distanza', 'sotto')]
    assert 'scanalatura da 16 mm' in r['message'] and '0,13 mm' in r['message']
    assert not s.asm.warnings


def test_la_scanalatura_segue_il_ferma_plexi_se_si_allarga(ferma):
    s, d = ferma
    assert s.asm_vano(_clic(s, 'I2'), _clic(s, 'I1'))['ok']
    assert s.save(str(d / 'ferma.steelcad-asm'))['ok']
    f = d / 'ferma_plexi.steelcad'
    j = json.loads(f.read_text(encoding='utf-8'))
    j['parameters']['W'] += 20                       # il ferma plexi 20 mm più largo
    f.write_text(json.dumps(j), encoding='utf-8')
    s2 = Service()
    assert s2.open(str(d / 'ferma.steelcad-asm'))['ok']
    x0, _, z0, x1, _, z1 = _ingombro(s2, 'I2')
    assert (round(x0, 1), round(x1, 1), z0, z1) == (12.5, 925.5, 2, 18)      # ancora in mezzo, sulla battuta
