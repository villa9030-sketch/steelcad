"""Bloccati insieme (05/11, idea da SolidCraft joint.rigid_group): due staffe bloccate insieme si spostano, girano,
si appoggiano e si accoppiano come un pezzo solo, senza farne un sottoassieme; la distinta non cambia; il gruppo si
vede nell'albero, si salva, si scioglie. Gli assiemi senza gruppi restano come prima."""
import json

import numpy as np
import pytest

from app.service import Service
from cad_engine import assembly as A


@pytest.fixture()
def assieme(tmp_path):
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 200, 'spessore': 8})['ok']
    assert s.save(str(tmp_path / 'Piastra base.steelcad'))['ok']
    s = Service()
    assert s.crea_da_modello('staffa', {'larghezza': 100, 'profondita': 80, 'altezza': 80, 'spessore': 3,
                                        'raggio': 3, 'k': 0.33})['ok']
    assert s.save(str(tmp_path / 'Staffa a L.steelcad'))['ok']
    s = Service()
    assert s.new_assembly_con_pezzi('Prova', [{'path': str(tmp_path / 'Piastra base.steelcad')},
                                              {'path': str(tmp_path / 'Staffa a L.steelcad'), 'n': 2}])['ok']
    # la seconda staffa girata e spostata rispetto alla prima: come stanno tra loro deve restare uguale
    assert s.asm_rotate('I3', 'z', 90)['ok']
    assert s.asm_move('I3', 40, 150, 30)['ok']
    return s, tmp_path


def _faccia(s, iid, nome):
    o = next(o for o in s.scene()['objects'] if o['id'] == iid)
    return {'inst': iid, 'face': next(f['index'] for f in o['faces'] if f['name'] == nome)}


def _rel(s, a, b):
    ia, ib = s.asm.instance(a), s.asm.instance(b)
    Ra, Ta = np.array(ia['R']), np.array(ia['T'])
    return Ra.T @ np.array(ib['R']), Ra.T @ (np.array(ib['T']) - Ta)


def _uguali(r1, r2):
    return np.allclose(r1[0], r2[0], atol=1e-6) and np.allclose(r1[1], r2[1], atol=1e-4)


def test_bloccati_si_spostano_insieme(assieme):
    s, _ = assieme
    T3 = np.array(s.asm.instance('I3')['T'])
    r = s.asm_blocca_insieme(['I2', 'I3'])
    assert r['ok'], r.get('message')
    assert 'bloccati insieme' in r['message']
    assert np.allclose(s.asm.instance('I3')['T'], T3)          # bloccare non sposta niente
    prima = _rel(s, 'I2', 'I3')
    assert s.asm_move('I2', 10, 20, 30)['ok']
    assert np.allclose(s.asm.instance('I3')['T'], T3 + [10, 20, 30])
    assert _uguali(_rel(s, 'I2', 'I3'), prima)
    # ruotando uno, gira tutto il gruppo attorno al suo centro
    assert s.asm_rotate('I3', 'x', 90)['ok']
    assert _uguali(_rel(s, 'I2', 'I3'), prima)
    assert np.allclose(np.array(s.asm.instance('I2')['R']) @ [0, 0, 1], [0, -1, 0], atol=1e-9)


def test_appoggia_porta_tutto_il_gruppo(assieme):
    s, _ = assieme
    assert s.asm_blocca_insieme(['I2', 'I3'])['ok']
    prima = _rel(s, 'I2', 'I3')
    a, b = _faccia(s, 'I2', 'SM1/sopra'), _faccia(s, 'I1', 'SM1/sopra')
    prova = s.asm_appoggia(a, b, None, True)
    assert prova['ok'] and set(prova['pose']) == {'I2', 'I3'}         # l'anteprima muove tutti e due
    r = s.asm_appoggia(a, b)
    assert r['ok'], r.get('message')
    i = s.asm.instance('I2')
    bb = A.placed_shape(s.asm_parts[i['file']], i['R'], i['T']).bounding_box()
    assert abs(bb.min.Z - 8) < 1e-6                              # la staffa sopra la piastra, come da sola
    assert _uguali(_rel(s, 'I2', 'I3'), prima)
    assert np.allclose(prova['pose']['I3'][3::4][:3], s.asm.instance('I3')['T'], atol=1e-6)
    assert not s.asm.warnings


def test_accoppiamento_sul_secondo_pezzo_porta_il_gruppo(assieme):
    s, _ = assieme
    assert s.asm_blocca_insieme(['I2', 'I3'])['ok']
    prima = _rel(s, 'I2', 'I3')
    r = s.asm_add_mate('faccia', _faccia(s, 'I1', 'SM1/sopra'), _faccia(s, 'I3', 'SM1/sotto'))
    assert r['ok'], r.get('message')
    i = s.asm.instance('I3')
    bb = A.placed_shape(s.asm_parts[i['file']], i['R'], i['T']).bounding_box()
    assert abs(bb.min.Z - 8) < 1e-4
    assert _uguali(_rel(s, 'I2', 'I3'), prima)
    assert not s.asm.warnings
    # tra due pezzi dello stesso gruppo non si accoppia (non si muoverebbe niente)
    r = s.asm_add_mate('faccia', _faccia(s, 'I2', 'SM1/sopra'), _faccia(s, 'I3', 'SM1/sotto'))
    assert not r['ok'] and 'bloccati insieme' in r['message']


def test_blocca_su_un_pezzo_del_gruppo(assieme):
    s, _ = assieme
    assert s.asm_blocca_insieme(['I2', 'I3'])['ok']
    assert s.asm_add_mate('blocca', {'inst': 'I1'}, {'inst': 'I3'})['ok']
    r13, r23 = _rel(s, 'I1', 'I3'), _rel(s, 'I2', 'I3')
    assert s.asm_set('I1', {'fixed': False})['ok'] and s.asm_set('I2', {'fixed': True})['ok']
    assert s.asm_move('I2', 0, 0, 100)['ok']                     # si sposta il gruppo: la piastra lo segue
    assert _uguali(_rel(s, 'I1', 'I3'), r13) and _uguali(_rel(s, 'I2', 'I3'), r23)
    assert not s.asm.warnings


def test_distinta_uguale_e_albero_col_gruppo(assieme):
    s, _ = assieme
    bom = s.state()['bom']
    assert s.asm_blocca_insieme(['I3', 'I2'], 'Staffe')['ok']
    st = s.state()
    assert st['bom'] == bom
    g = next(c for c in st['tree']['children'] if c['kind'] == 'rigido')
    assert g['label'] == 'Staffe' and [c['ref'] for c in g['children']] == ['I2', 'I3']
    assert sum(1 for c in st['tree']['children'] if c['kind'] == 'instance') == 1
    sel = s.select('I3')['selection']
    assert sel['gruppo']['name'] == 'Staffe' and sel['gruppo']['ids'] == ['I2', 'I3']


def test_si_salva_e_si_riapre_uguale(assieme):
    s, tmp = assieme
    assert s.asm_blocca_insieme(['I2', 'I3'])['ok']
    p = tmp / 'gruppo.steelcad-asm'
    assert s.save(str(p))['ok']
    d = json.loads(p.read_text(encoding='utf-8'))
    assert d['gruppi'] == [{'id': 'G1', 'name': 'Gruppo 1', 'pezzi': ['I2', 'I3']}]
    pose = {i['id']: (i['R'], i['T']) for i in s.asm.instances}
    s2 = Service()
    assert s2.open(str(p))['ok']
    for i in s2.asm.instances:
        assert np.allclose(i['R'], pose[i['id']][0]) and np.allclose(i['T'], pose[i['id']][1])
    assert s2.asm_move('I3', 5, 0, 0)['ok']
    assert np.allclose(np.array(s2.asm.instance('I2')['T']), np.array(pose['I2'][1]) + [5, 0, 0])


def test_assieme_senza_gruppi_come_prima(assieme):
    s, _ = assieme
    assert 'gruppi' not in s.asm.to_dict()
    T2 = np.array(s.asm.instance('I2')['T'])
    assert s.asm_move('I3', 5, 0, 0)['ok']
    assert np.allclose(s.asm.instance('I2')['T'], T2)


def test_sciogli_e_annulla(assieme):
    s, _ = assieme
    assert s.asm_blocca_insieme(['I2', 'I3'])['ok']
    r = s.asm_sciogli_gruppo('G1')
    assert r['ok'] and 'sciolto' in r['message']
    T2 = np.array(s.asm.instance('I2')['T'])
    assert s.asm_move('I3', 5, 0, 0)['ok']
    assert np.allclose(s.asm.instance('I2')['T'], T2)
    s.undo()
    s.undo()
    assert s.asm.gruppi and s.asm.gruppi[0]['pezzi'] == ['I2', 'I3']


def test_un_gruppo_si_unisce_e_si_svuota(assieme):
    s, _ = assieme
    assert s.asm_blocca_insieme(['I2', 'I3'])['ok']
    assert not s.asm_blocca_insieme(['I2'])['ok']                 # uno solo: niente
    assert s.asm_blocca_insieme(['I3', 'I1'])['ok']               # I3 è già in un gruppo: si aggiunge la piastra
    assert len(s.asm.gruppi) == 1 and s.asm.gruppi[0]['pezzi'] == ['I1', 'I2', 'I3']
    assert s.asm_remove('I1')['ok'] and s.asm_remove('I2')['ok']
    assert s.asm.gruppi == []                                     # restato con un pezzo solo: il gruppo non c'è più


def test_appoggia_rifa_gli_accoppiamenti_di_tutto_il_gruppo(assieme):
    s, _ = assieme
    assert s.asm_add_mate('faccia', _faccia(s, 'I1', 'SM1/sopra'), _faccia(s, 'I3', 'SM1/sotto'))['ok']
    assert s.asm_blocca_insieme(['I2', 'I3'])['ok']
    assert s.asm_rotate('I2', 'z', 90)['ok']                     # libero di girare sulla piastra: si gira
    r = s.asm_appoggia(_faccia(s, 'I2', 'SM1/sopra'), _faccia(s, 'I1', 'SM1/sopra'))
    assert r['ok'], r.get('message')
    # quello vecchio della seconda staffa è andato: il gruppo ha un posto solo
    assert all('I3' not in (m['a']['inst'], m['b']['inst']) for m in s.asm.mates)
    assert not s.asm.warnings
