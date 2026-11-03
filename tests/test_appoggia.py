"""Appoggia (03/11, Stefano: appoggiare e centrare in un comando): la staffa a L sopra la piastra, al centro, senza
capovolgerla né farla entrare; su un bordo, a misura dai bordi; accoppiamenti veri che restano se cambia un pezzo."""
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
                                              {'path': str(tmp_path / 'Staffa a L.steelcad')}])['ok']
    return s, tmp_path


def _faccia(s, iid, nome):
    o = next(o for o in s.scene()['objects'] if o['id'] == iid)
    return {'inst': iid, 'face': next(f['index'] for f in o['faces'] if f['name'] == nome)}


def _ingombro(s, iid):
    i = s.asm.instance(iid)
    b = A.placed_shape(s.asm_parts[i['file']], i['R'], i['T']).bounding_box()
    return [round(v, 3) for v in (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)]


def test_staffa_al_centro_cliccando_la_faccia_che_si_vede(assieme):
    s, _ = assieme
    sopra_staffa, sopra_piastra = _faccia(s, 'I2', 'SM1/sopra'), _faccia(s, 'I1', 'SM1/sopra')
    r = s.asm_appoggia(sopra_staffa, sopra_piastra)
    assert r['ok'], r.get('message')
    # dritta (la parete in su), appoggiata sopra (z 8 → 88) e al centro: 100 × 80 su 300 × 200
    assert _ingombro(s, 'I2') == [100, 60, 8, 200, 140, 88]
    assert np.allclose(s.asm.instance('I2')['R'], np.eye(3), atol=1e-9)
    assert 'al centro' in r['message']
    assert sorted(m['type'] for m in s.asm.mates) == ['centra', 'centra', 'faccia']
    assert not s.asm.warnings
    assert 'Nessuna' in s.asm_interferences()['message']


def test_cliccando_la_faccia_sotto_viene_uguale(assieme):
    s, _ = assieme
    r = s.asm_appoggia(_faccia(s, 'I2', 'SM1/sotto'), _faccia(s, 'I1', 'SM1/sopra'))
    assert r['ok']
    assert _ingombro(s, 'I2') == [100, 60, 8, 200, 140, 88]


def test_cliccato_prima_il_pezzo_fermo_si_muove_lo_stesso_l_altro(assieme):
    s, _ = assieme
    r = s.asm_appoggia(_faccia(s, 'I1', 'SM1/sopra'), _faccia(s, 'I2', 'SM1/sopra'))
    assert r['ok']
    assert _ingombro(s, 'I1') == [0, 0, 0, 300, 200, 8]
    assert _ingombro(s, 'I2') == [100, 60, 8, 200, 140, 88]


def test_anteprima_non_cambia_niente_e_dice_le_distanze(assieme):
    s, _ = assieme
    prima = s.asm.to_dict()
    r = s.asm_appoggia(_faccia(s, 'I2', 'SM1/sopra'), _faccia(s, 'I1', 'SM1/sopra'), None, True)
    assert r['ok'] and 'I2' in r['pose']
    assert s.asm.to_dict() == prima
    u, v = r['dirs']['u'], r['dirs']['v']
    assert (u['basso'], u['alto'], u['da_basso'], u['da_alto']) == ('sinistra', 'destra', 100, 100)
    assert (v['basso'], v['alto'], v['da_basso'], v['da_alto']) == ('davanti', 'dietro', 60, 60)


def test_su_un_bordo_e_a_misura(assieme):
    s, _ = assieme
    a, b = _faccia(s, 'I2', 'SM1/sopra'), _faccia(s, 'I1', 'SM1/sopra')
    r = s.asm_appoggia(a, b, {'u': {'modo': 'basso', 'mm': '20'}, 'v': {'modo': 'alto', 'mm': 0}})
    assert r['ok'], r.get('message')
    assert _ingombro(s, 'I2') == [20, 120, 8, 120, 200, 88]
    # rifatto: gli accoppiamenti vecchi tra i due pezzi si tolgono, non si sommano
    r = s.asm_appoggia(a, b, {'u': {'modo': 'alto', 'mm': '15,5'}, 'v': {'modo': 'centro'}})
    assert r['ok']
    assert _ingombro(s, 'I2') == [184.5, 60, 8, 284.5, 140, 88]
    assert len(s.asm.mates) == 3


def test_gira_di_90(assieme):
    s, _ = assieme
    r = s.asm_appoggia(_faccia(s, 'I2', 'SM1/sopra'), _faccia(s, 'I1', 'SM1/sopra'), {'gira': 1})
    assert r['ok']
    assert _ingombro(s, 'I2') == [110, 50, 8, 190, 150, 88]


def test_staffa_storta_si_raddrizza_senza_capovolgersi(assieme):
    s, _ = assieme
    assert s.asm_rotate('I2', 'x', 90)['ok']
    assert s.asm_rotate('I2', 'z', 30)['ok']
    r = s.asm_appoggia(_faccia(s, 'I2', 'SM1/sopra'), _faccia(s, 'I1', 'SM1/sopra'))
    assert r['ok']
    bb = _ingombro(s, 'I2')
    assert bb[2] == 8 and bb[5] == 88                  # sopra la piastra, parete in su
    assert 'Nessuna' in s.asm_interferences()['message']


def test_se_la_piastra_cambia_la_staffa_resta_al_centro(assieme):
    s, cart = assieme
    assert s.asm_appoggia(_faccia(s, 'I2', 'SM1/sopra'), _faccia(s, 'I1', 'SM1/sopra'))['ok']
    import os
    import time
    p = Service()                                       # la piastra rifatta più grande e più spessa, stesso file
    assert p.new_project('lamiera', {'larghezza': 400, 'profondita': 250, 'spessore': 10})['ok']
    f = cart / 'Piastra base.steelcad'
    assert p.save(str(f))['ok']
    t = time.time() + 5
    os.utime(f, (t, t))
    s._asm_reload()
    assert _ingombro(s, 'I1') == [0, 0, 0, 400, 250, 10]
    assert _ingombro(s, 'I2') == [150, 85, 10, 250, 165, 90]
    assert not s.asm.warnings


def test_annulla_torna_a_prima(assieme):
    s, _ = assieme
    prima = _ingombro(s, 'I2')
    assert s.asm_appoggia(_faccia(s, 'I2', 'SM1/sopra'), _faccia(s, 'I1', 'SM1/sopra'))['ok']
    assert s.undo()['ok']
    assert _ingombro(s, 'I2') == prima and not s.asm.mates


def test_facce_non_piane(assieme):
    s, _ = assieme
    o = next(o for o in s.scene()['objects'] if o['id'] == 'I2')
    cil = next(f['index'] for f in o['faces'] if 'piega' in (f['name'] or ''))
    r = s.asm_appoggia({'inst': 'I2', 'face': cil}, _faccia(s, 'I1', 'SM1/sopra'))
    assert not r['ok'] and 'piane' in r['message']


def test_distanza_dal_bordo_si_legge_e_si_scrive_positiva(assieme):
    s, _ = assieme
    assert s.asm_appoggia(_faccia(s, 'I2', 'SM1/sopra'), _faccia(s, 'I1', 'SM1/sopra'),
                          {'u': {'modo': 'basso', 'mm': 20}, 'v': {'modo': 'centro'}})['ok']
    m = next(m for m in s.asm.mates if m['type'] == 'distanza')
    d = s.select('mate=' + m['id'])['selection']['def']
    assert d['offset'] == pytest.approx(20) and d['da'] == 'appoggia'
    assert s.asm_edit_mate(m['id'], {'offset': '35'})['ok']
    assert _ingombro(s, 'I2')[0] == 35
    r = s.asm_trascina_mate(m['id'], 'offset', '50')
    assert r['ok'] and abs(r['pose']['I2'][3] - 50) < 1e-6
    assert s.asm_trascina_mate(m['id'], 'offset', '50', True)['ok']
    assert _ingombro(s, 'I2')[0] == 50


def test_sposta_dice_dove_sta_e_i_bordi_del_pezzo_sotto(assieme):
    s, _ = assieme
    d = s.select('I2')['selection']['dove']
    assert d['min'] == [350, 0, 0] and d['sotto'] is None          # a fianco della piastra: niente sotto
    assert s.asm_appoggia(_faccia(s, 'I2', 'SM1/sopra'), _faccia(s, 'I1', 'SM1/sopra'))['ok']
    d = s.select('I2')['selection']['dove']
    assert d['min'] == [100, 60, 8]
    assert d['sotto']['id'] == 'I1'
    assert (d['sotto']['sinistra'], d['sotto']['destra'], d['sotto']['davanti'], d['sotto']['dietro']) == (100, 100, 60, 60)


def test_nel_pannello_del_pezzo_il_cursore_dice_dal_bordo(assieme):
    s, _ = assieme
    assert s.asm_appoggia(_faccia(s, 'I2', 'SM1/sopra'), _faccia(s, 'I1', 'SM1/sopra'),
                          {'u': {'modo': 'basso', 'mm': 20}, 'v': {'modo': 'alto', 'mm': 30}})['ok']
    mv = s.select('I2')['selection']['movimenti']
    assert sorted((m['nome'], round(m['valore'], 3)) for m in mv) == [('Da dietro (dal bordo)', 30), ('Da sinistra (dal bordo)', 20)]
    assert s.select('I2')['selection']['tenuto'] and not s.select('I1')['selection']['tenuto']
