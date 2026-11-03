"""Appoggia, secondo giro (03/11): mai dentro l'altro pezzo (una piastra più grande del fondo di una vaschetta si posa
sui bordi; se girandolo ci sta, lo gira da solo) e al centro che tiene anche sui pannelli piegati (dove la faccia
finisce in una piega e non c'è un lato piano proprio sul bordo)."""
import os
import time

import pytest

from app.service import Service
from cad_engine import assembly as A


def _pezzo(cart, nome, modello=None, **c):
    s = Service()
    assert (s.crea_da_modello(modello, c) if modello else s.new_project('lamiera', c))['ok']
    p = cart / f'{nome}.steelcad'
    assert s.save(str(p))['ok']
    return p


@pytest.fixture()
def pezzi(tmp_path):
    return {'vaschetta': _pezzo(tmp_path, 'Vaschetta', 'scatola', larghezza=200, profondita=150, altezza=50, spessore=2,
                                raggio=2, k=0.33),
            'piastra': _pezzo(tmp_path, 'Piastra', larghezza=300, profondita=200, spessore=8),
            'staffa': _pezzo(tmp_path, 'Staffa', 'staffa', larghezza=100, profondita=80, altezza=80, spessore=3, raggio=3, k=0.33),
            'lunga': _pezzo(tmp_path, 'Lunga', larghezza=180, profondita=100, spessore=5),
            'cart': tmp_path}


def _assieme(*files):
    s = Service()
    assert s.new_assembly_con_pezzi('Prova', [{'path': str(f)} for f in files])['ok']
    return s


def _faccia(s, iid, nome):
    o = next(o for o in s.scene()['objects'] if o['id'] == iid)
    return {'inst': iid, 'face': next(f['index'] for f in o['faces'] if f['name'] == nome)}


def _ingombro(s, iid):
    i = s.asm.instance(iid)
    b = A.placed_shape(s.asm_parts[i['file']], i['R'], i['T']).bounding_box()
    return [round(v, 2) for v in (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)]


def test_piastra_piu_grande_del_fondo_si_posa_sui_bordi(pezzi):
    s = _assieme(pezzi['vaschetta'], pezzi['piastra'])
    fondo = _faccia(s, 'I1', 'SM1/sopra')               # il fondo dentro la vaschetta
    r = s.asm_appoggia(_faccia(s, 'I2', 'SM1/sotto'), fondo, None, True)
    assert r['ok'] and r['dentro'] == 0 and r['alzato'] > 40
    r = s.asm_appoggia(_faccia(s, 'I2', 'SM1/sotto'), fondo)
    assert r['ok'], r.get('message')
    assert _ingombro(s, 'I2') == [-50, -25, 50, 250, 175, 58]       # sopra i bordi (alti 50), al centro
    assert 'Nessuna' in s.asm_interferences()['message']
    assert 'più su' in r['message']


def test_se_girato_ci_sta_lo_gira_da_solo(pezzi):
    s = _assieme(pezzi['vaschetta'], pezzi['lunga'])
    # 180 × 100 nel fondo 192 × 142 ci sta così; girato no: lo metto prima girato di 90°
    assert s.asm_rotate('I2', 'z', 90)['ok']
    a, b = _faccia(s, 'I2', 'SM1/sotto'), _faccia(s, 'I1', 'SM1/sopra')
    r = s.asm_appoggia(a, b, {'gira': 0, 'auto': True}, True)
    assert r['ok'] and r['dentro'] == 0 and r['alzato'] == 0
    # di suo andrebbe a squadra come l'avevo messo: o già ci sta, o l'ha girato da solo e lo dice
    if r['cambio']:
        assert r['scelto']['gira'] in (1, 3) and r['cambio'] == 'Gira di 90°'
    r = s.asm_appoggia(a, b, r['scelto'] or {'gira': 0})
    assert r['ok']
    bb = _ingombro(s, 'I2')
    assert bb[2] == 2 and 'Nessuna' in s.asm_interferences()['message']


def test_scelta_a_mano_che_entra_propone_quella_che_ci_sta(pezzi):
    s = _assieme(pezzi['vaschetta'], pezzi['lunga'])
    a, b = _faccia(s, 'I2', 'SM1/sotto'), _faccia(s, 'I1', 'SM1/sopra')
    giusto = s.asm_appoggia(a, b, None, True)
    assert giusto['alzato'] == 0
    sbagliato = s.asm_appoggia(a, b, {'gira': 1}, True)          # 180 di traverso nei 142: non ci sta
    assert sbagliato['ok'] and sbagliato['alzato'] > 0 and sbagliato['dentro'] == 0
    assert [p['testo'] for p in sbagliato['proposte']][:1] == ['Gira di 90°']


def test_staffa_dentro_la_vaschetta_resta_al_centro_se_la_vaschetta_cambia(pezzi):
    s = _assieme(pezzi['vaschetta'], pezzi['staffa'])
    r = s.asm_appoggia(_faccia(s, 'I2', 'SM1/sopra'), _faccia(s, 'I1', 'SM1/sopra'))
    assert r['ok'], r.get('message')
    assert all(d['tiene'] for d in r['appoggia']['dirs'].values())
    assert 'non c’è un lato piano' not in r['message']
    assert _ingombro(s, 'I2') == [50, 35, 2, 150, 115, 82]
    assert sorted(m['type'] for m in s.asm.mates) == ['centra', 'centra', 'faccia']
    # la vaschetta rifatta più grande: la staffa resta al centro del fondo
    f = pezzi['vaschetta']
    _pezzo(pezzi['cart'], 'Vaschetta', 'scatola', larghezza=260, profondita=180, altezza=50, spessore=2, raggio=2, k=0.33)
    t = time.time() + 5
    os.utime(f, (t, t))
    s._asm_reload()
    assert _ingombro(s, 'I2') == [80, 50, 2, 180, 130, 82]
    assert not s.asm.warnings


def test_fatto_rifiuta_se_entra_ancora(pezzi, monkeypatch):
    from cad_engine import assembly_appoggia as AP
    s = _assieme(pezzi['vaschetta'], pezzi['piastra'])
    monkeypatch.setattr(AP, 'solleva', lambda *a, **k: (a[5], 0.0, 999.0))
    r = s.asm_appoggia(_faccia(s, 'I2', 'SM1/sotto'), _faccia(s, 'I1', 'SM1/sopra'))
    assert not r['ok'] and 'entra' in r['message']


# ------------------------------------------------------------------ Faccia su faccia con le regole di Appoggia
def test_faccia_su_faccia_cliccando_quella_che_si_vede_non_capovolge(pezzi):
    import numpy as np
    s = _assieme(pezzi['piastra'], pezzi['staffa'])
    r = s.asm_add_mate('faccia', _faccia(s, 'I1', 'SM1/sopra'), _faccia(s, 'I2', 'SM1/sopra'), 0, False, None, None, True)
    assert r['ok'], r.get('message')
    assert np.allclose(s.asm.instance('I2')['R'], np.eye(3), atol=1e-9)        # dritta, la parete in su
    bb = _ingombro(s, 'I2')
    assert bb[2] == 8 and bb[5] == 88                                           # appoggiata sopra, non dentro
    assert s.asm.mates[0]['b']['name'] == 'SM1/sotto'


def test_faccia_su_faccia_con_la_punta_dell_ala_resta_come_prima(pezzi):
    s = _assieme(pezzi['piastra'], pezzi['staffa'])
    r = s.asm_add_mate('faccia', _faccia(s, 'I1', 'SM1/sopra'), _faccia(s, 'I2', 'SM1/FL1/punta'), 0, False, None, None, True)
    assert r['ok']
    assert s.asm.mates[0]['b']['name'] == 'SM1/FL1/punta'
    assert 'Nessuna' in s.asm_interferences()['message']


def test_faccia_su_faccia_sotto_contro_sotto_non_entra(pezzi):
    s = _assieme(pezzi['vaschetta'], pezzi['staffa'])
    r = s.asm_add_mate('faccia', _faccia(s, 'I1', 'SM1/sotto'), _faccia(s, 'I2', 'SM1/sotto'), 0, False, None, None, True)
    assert r['ok']
    assert s.asm.mates[0]['b']['name'] == 'SM1/FL1/punta'           # appesa sotto con la punta dell'ala, fuori
    assert _ingombro(s, 'I2')[5] == 0
    assert 'Nessuna' in s.asm_interferences()['message']
