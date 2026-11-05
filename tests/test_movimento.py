"""Pezzi che si muovono nell'assieme (05/11, idee da SolidCraft joint revolute/slider/cylindrical, joint.find_limits,
motion interference): cerniera, guida, perno; trascinare (muovere a un valore), finecorsa, «Trova da solo», «Controlla
che non sbatta». La posizione di movimento non cambia il file finché non si dice «Tieni questa posizione».

La porta del caso di SolidCraft (motion_sweep_tests.rs): una porta 100 × 4 × 50 incernierata sull'asse Z all'origine e
un blocco 20 × 20 da (60, 30) in mezzo. La faccia della porta a 4 mm dall'asse tocca lo spigolo (80, 30) del blocco
quando r·sin(φ − θ) = 4, cioè a θ = φ − asin(4 / r)."""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from app.assembly_moto_service import valore_scritto
from app.service import Service
from cad_engine import assembly as A
from cad_engine import assembly_moto as M

DATI = Path(__file__).parent / 'data' / 'vano'
GIRO_BLOCCO = math.degrees(math.atan2(30, 80) - math.asin(4 / math.hypot(80, 30)))      # 17,87°


def _blocco(cartella, nome, W, P, sp):
    """Un blocco W × P × sp da (0, 0, 0): la lastra del plexiglass con altre misure, in acciaio."""
    d = json.loads((DATI / 'plexi.steelcad').read_text(encoding='utf-8'))
    d['meta']['name'] = nome
    d['parameters'] = {'W': W, 'P': P, 'sp': sp}
    d['material'] = 'S235'
    f = cartella / f'{nome}.steelcad'
    f.write_text(json.dumps(d), encoding='utf-8')
    return f


def _assieme(tmp_path, *pezzi):
    s = Service()
    r = s.new_assembly_con_pezzi('Prova', [{'path': str(_blocco(tmp_path, *p[:4]))} for p in pezzi])
    assert r['ok'], r.get('message')
    for i, p in zip(s.asm.instances, pezzi):
        i['T'] = list(p[4])
    s._asm_reload()
    return s


def _faccia(s, iid):
    return {'inst': iid, 'face': {x['id']: x for x in s.scene()['objects']}[iid]['faces'][0]['index']}


@pytest.fixture()
def porta(tmp_path):
    """Il blocco fermo (I1) in (60, 30) e la porta (I2) incernierata sul suo spigolo verticale all'origine."""
    s = _assieme(tmp_path, ('Muro', 20, 20, 50, (60, 30, 0)), ('Porta', 100, 4, 50, (0, 0, 0)))
    r = s.asm_add_mate('cerniera', {'inst': 'I2', 'edge_pt': [0, 0, 25]}, _faccia(s, 'I1'))
    assert r['ok'], r.get('message')
    return s, s.asm.mates[-1]['id']


def _punto_porta(s, p=(100, 4, 25)):
    i = s.asm.instance('I2')
    return np.array(i['R']) @ np.array(p, dtype=float) + np.array(i['T'])


def test_valore_scritto_come_lo_scrive_l_officina():
    assert valore_scritto('90°') == 90
    assert valore_scritto('aperta 300') == 300
    assert valore_scritto('-12,5') == -12.5
    assert valore_scritto(45) == 45
    with pytest.raises(A.AssemblyError):
        valore_scritto('aperta')


def test_cerniera_sul_pezzo_fermo_e_gira(porta):
    s, mid = porta
    m = s.asm.mates[-1]
    assert m['type'] == 'cerniera' and m['a']['inst'] == 'I1' and m['b']['inst'] == 'I2'     # gira la porta, non il muro
    assert m['asse_da'] == 'b' and m['angolo'] == 0
    assert np.allclose(s.asm.instance('I2')['T'], [0, 0, 0]) and not s.asm.warnings          # niente si sposta
    r = s.asm_muovi_giunto(mid, {'angolo': '90'}, True)
    assert r['ok'] and r['valori'] == {'angolo': 90}
    # 90° attorno allo spigolo all'origine: la punta della porta (100, 0) va sull'asse Y, il muro resta fermo
    assert np.linalg.norm(_punto_porta(s, (100, 0, 25))[:2]) == pytest.approx(100)
    assert abs(_punto_porta(s, (100, 0, 25))[0]) < 1e-6
    assert np.allclose(s.asm.instance('I1')['T'], [60, 30, 0])
    st = r['state']
    assert [g['id'] for g in st['giunti']] == [mid] and st['giunti'][0]['mosso']
    assert 'in cerniera su' in json.dumps(st['tree'], ensure_ascii=False)


def test_la_posizione_di_movimento_non_cambia_il_file(porta, tmp_path):
    s, mid = porta
    assert s.asm_muovi_giunto(mid, {'angolo': 30}, True)['ok']
    p = tmp_path / 'porta.steelcad-asm'
    assert s._asm_save(str(p))['ok']
    d = json.loads(p.read_text(encoding='utf-8'))
    i2 = next(i for i in d['instances'] if i['id'] == 'I2')
    assert np.allclose(i2['R'], np.eye(3)) and np.allclose(i2['T'], [0, 0, 0])               # disegnata, non aperta
    assert d['mates'][-1]['angolo'] == 0
    assert s.asm_muovi_giunto(mid, {'angolo': 31}, False)['ok']                               # in memoria resta aperta
    assert not np.allclose(s.asm.instance('I2')['R'], np.eye(3))
    # «Torna com'era»
    assert s.asm_giunto_torna(mid)['ok']
    assert np.allclose(s.asm.instance('I2')['R'], np.eye(3))
    # riaperto: chiusa
    s2 = Service()
    assert s2._asm_open(str(p))['ok']
    assert np.allclose(s2.asm.instance('I2')['R'], np.eye(3)) and not s2.asm.warnings


def test_tieni_questa_posizione_si_salva_e_si_annulla(porta):
    s, mid = porta
    s.asm_muovi_giunto(mid, {'angolo': 30}, True)
    r = s.asm_giunto_tieni(mid)
    assert r['ok'] and '30°' in r['message']
    m = next(x for x in s.asm.mates if x['id'] == mid)
    assert m['angolo'] == pytest.approx(30) and not s.asm_moto.get(mid)
    assert s.asm_giunto_torna(mid)['ok']                     # ora «com'era» è 30°
    assert np.linalg.norm(np.array(s.asm.instance('I2')['R']) - np.eye(3)) > 0.1
    s._asm_undo()
    m = next(x for x in s.asm.mates if x['id'] == mid)
    assert m['angolo'] == 0


def test_trova_da_solo_si_ferma_contro_il_blocco(porta):
    """Il caso fatto a mano di SolidCraft: tocca a 17,87°; dall'altra parte fa il giro e lo tocca da dietro."""
    s, mid = porta
    r = s.asm_giunto_limiti(mid)
    assert r['ok'], r.get('message')
    m = next(x for x in s.asm.mates if x['id'] == mid)
    lo, hi = m['lim_angolo']
    giro = min(abs(lo), abs(hi))
    assert giro == pytest.approx(GIRO_BLOCCO, abs=0.15) and giro <= GIRO_BLOCCO     # arrotondato verso dentro
    assert abs(hi - lo) > 300                                                        # dall'altra parte quasi un giro
    assert '«Muro»' in r['message']
    # dentro il finecorsa: fino a lì e non oltre
    lato = 1 if abs(hi) < abs(lo) else -1
    v = s.asm_muovi_giunto(mid, {'angolo': lato * 40}, False)['valori']['angolo']
    assert v == pytest.approx(lato * giro)
    assert A.interferences(s.asm, s.asm_parts) == []


def test_finecorsa_scritto_e_controlla_che_non_sbatta(porta):
    s, mid = porta
    m = next(x for x in s.asm.mates if x['id'] == mid)
    # verso del blocco: il segno dove tocca
    s.asm_giunto_limiti(mid)
    lo, hi = next(x for x in s.asm.mates if x['id'] == mid)['lim_angolo']
    verso = 1 if abs(hi) < abs(lo) else -1
    assert s.asm_edit_mate(mid, {'lim_angolo': ['0', str(verso * 40)]})['ok']
    m = next(x for x in s.asm.mates if x['id'] == mid)
    assert sorted(m['lim_angolo']) == sorted([0, verso * 40])
    r = s.asm_giunto_controlla(mid)
    assert r['ok'] and r['tocca'], r.get('message')
    t = r['tocca']
    assert t['fermo'] == 'Muro' and abs(t['valore']) == pytest.approx(GIRO_BLOCCO, abs=0.15)
    assert np.linalg.norm(np.array(t['punto'][:2]) - [80, 30]) < 1.0            # lo spigolo del blocco
    assert 'Sbatte' in r['message'] and '«Muro»' in r['message']
    assert s.asm_moto[mid]['angolo'] == pytest.approx(t['valore'])               # il pezzo resta dove tocca
    # dall'altra parte non tocca niente
    assert s.asm_edit_mate(mid, {'lim_angolo': ['0', str(-verso * 90)]})['ok']
    r = s.asm_giunto_controlla(mid)
    assert r['ok'] and r['tocca'] is None and 'Non sbatte' in r['message']


def test_controlla_senza_corsa_lo_dice(porta):
    s, mid = porta
    r = s.asm_giunto_controlla(mid)
    assert not r['ok'] and 'finecorsa' in r['message']


def test_si_toccano_gia_ferma_solo_se_entra(tmp_path):
    """La porta appoggiata alla battuta (il blocco subito dietro): aprendo non tocca niente, chiudendo si ferma subito.
    Il finecorsa viene da 0 in su (il verso si gira da solo)."""
    s = _assieme(tmp_path, ('Battuta', 20, 20, 50, (60, 4, 0)), ('Porta', 100, 4, 50, (0, 0, 0)))
    assert s.asm_add_mate('cerniera', {'inst': 'I2', 'edge_pt': [0, 0, 25]}, _faccia(s, 'I1'))['ok']
    mid = s.asm.mates[-1]['id']
    r = s.asm_giunto_limiti(mid)
    assert r['ok'], r.get('message')
    lo, hi = next(x for x in s.asm.mates if x['id'] == mid)['lim_angolo']
    assert lo == pytest.approx(0, abs=0.05) and hi > 100
    assert 'Si toccano già' in r['message']
    v = s.asm_muovi_giunto(mid, {'angolo': -10}, False)['valori']['angolo']
    assert v == pytest.approx(lo)
    assert s.asm_muovi_giunto(mid, {'angolo': 60}, False)['valori']['angolo'] == 60


def test_guida_scorre_fino_al_muro(tmp_path):
    """Un cassetto (la porta sdraiata) su una guida lungo X: scorre fino a toccare il muro 100 mm più in là."""
    s = _assieme(tmp_path, ('Muro', 20, 20, 50, (200, 0, 0)), ('Cassetto', 100, 4, 50, (0, 0, 0)))
    r = s.asm_add_mate('guida', {'inst': 'I2', 'edge_pt': [50, 0, 0]}, _faccia(s, 'I1'))
    assert r['ok'], r.get('message')
    mid = s.asm.mates[-1]['id']
    r = s.asm_giunto_limiti(mid)
    assert r['ok'], r.get('message')
    lo, hi = next(x for x in s.asm.mates if x['id'] == mid)['lim_corsa']
    assert hi == pytest.approx(100, abs=0.15) and hi <= 100
    assert lo is None                                                    # all'indietro non tocca niente
    assert 'scrivilo tu' in r['message']
    v = s.asm_muovi_giunto(mid, {'corsa': 'aperta 300'}, True)['valori']['corsa']
    assert v == pytest.approx(hi)
    assert s.asm.instance('I2')['T'][0] == pytest.approx(hi)


def test_i_pezzi_attaccati_seguono(porta, tmp_path):
    """Una maniglia bloccata sulla porta gira con lei."""
    s, mid = porta
    assert s.asm_insert(str(_blocco(tmp_path, 'Maniglia', 10, 10, 10)))['ok']
    s.asm.instance('I3')['T'] = [80, -10, 20]
    s._asm_reload()
    assert s.asm_add_mate('blocca', {'inst': 'I2'}, {'inst': 'I3'})['ok']
    g = next(g for g in s.state()['giunti'] if g['id'] == mid)
    assert g['mobili'] == ['I2', 'I3'] and not g['bloccato']
    s.asm_muovi_giunto(mid, {'angolo': 90}, True)
    i3 = s.asm.instance('I3')
    q = np.array(i3['R']) @ np.array([0, 0, 0.0]) + np.array(i3['T'])
    assert np.linalg.norm(q[:2]) == pytest.approx(np.hypot(80, 10), abs=1e-6)   # gira attorno all'asse
    assert not np.allclose(q, [80, -10, 20])


def test_perno_mette_i_fori_in_asse(tmp_path):
    """Due piastre con un foro Ø8: il perno porta il foro della seconda sull'asse del primo (gira il meno possibile);
    girando, il foro resta sull'asse."""
    from tests.test_assembly import _faccia as faccia_di, _pezzi
    pp, ps = _pezzi(tmp_path)
    s = Service()
    s.new_assembly('Perno')
    assert s.asm_insert(str(pp))['ok'] and s.asm_insert(str(ps))['ok']
    s.asm.instance('I2')['T'] = [30, 200, 40]
    s._asm_reload()
    fa = faccia_di(s, 'I1', kind='cilindrica', vicino=[60, 50, 1])
    fb = faccia_di(s, 'I2', kind='cilindrica', vicino=[10, 20, 1])
    r = s.asm_add_mate('perno', {'inst': 'I1', 'face': fa}, {'inst': 'I2', 'face': fb})
    assert r['ok'], r.get('message')
    mid = s.asm.mates[-1]['id']

    def foro_b():
        i = s.asm.instance('I2')
        return np.array(i['R']) @ np.array([10, 20, 0.0]) + np.array(i['T'])
    assert np.allclose(foro_b()[:2], [60, 50], atol=1e-6)               # in asse col foro della piastra
    assert foro_b()[2] == pytest.approx(40)                              # all'altezza dove stava
    for vals in ({'angolo': 75}, {'corsa': 12}):
        s.asm_muovi_giunto(mid, vals, True)
        assert np.allclose(foro_b()[:2], [60, 50], atol=1e-6)
    assert foro_b()[2] == pytest.approx(52)


def test_cerniera_vuole_un_asse(tmp_path):
    s = _assieme(tmp_path, ('Muro', 20, 20, 50, (60, 30, 0)), ('Porta', 100, 4, 50, (0, 0, 0)))
    r = s.asm_giunto_asse('cerniera', _faccia(s, 'I2'))
    assert not r['ok'] and 'spigolo' in r['message']
    r = s.asm_add_mate('cerniera', _faccia(s, 'I2'), _faccia(s, 'I1'))
    assert not r['ok'] and 'spigolo' in r['message']
    assert s.asm_giunto_asse('guida', _faccia(s, 'I2'))['ok']                # la guida va bene di fronte a una faccia
    r = s.asm_giunto_asse('cerniera', {'inst': 'I2', 'edge_pt': [0, 0, 25]})
    assert r['ok'] and r['asse']['cosa'] == 'lo spigolo' and abs(abs(r['asse']['d'][2]) - 1) < 1e-9


def test_una_cerniera_sola_e_gli_accoppiamenti_di_prima_sospesi(tmp_path):
    s = _assieme(tmp_path, ('Muro', 20, 20, 50, (60, 30, 0)), ('Porta', 100, 4, 50, (0, 0, 0)))
    assert s.asm_add_mate('blocca', {'inst': 'I1'}, {'inst': 'I2'})['ok']
    r = s.asm_add_mate('cerniera', {'inst': 'I2', 'edge_pt': [0, 0, 25]}, _faccia(s, 'I1'))
    assert r['ok'] and 'sospeso' in r['message']
    assert s.asm.mates[0]['off'] is True
    r = s.asm_add_mate('cerniera', {'inst': 'I2', 'edge_pt': [0, 0, 25]}, _faccia(s, 'I1'))
    assert not r['ok'] and 'ne basta una' in r['message']


def test_verso_contrario_stessa_posizione(porta):
    s, mid = porta
    s.asm_muovi_giunto(mid, {'angolo': 25}, True)
    prima = np.array(s.asm.instance('I2')['R'])
    assert s.asm_edit_mate(mid, {'verso_contrario': True})['ok']
    m = next(x for x in s.asm.mates if x['id'] == mid)
    assert m['verso'] == -1 and s.asm_moto[mid]['angolo'] == -25
    assert np.allclose(s.asm.instance('I2')['R'], prima, atol=1e-9)


def test_assiemi_di_prima_uguali(tmp_path):
    """Senza giunti niente cambia: lo stato non ha giunti e il file salvato non ha campi nuovi."""
    from tests.test_assembly import _faccia as faccia_di, _pezzi
    pp, ps = _pezzi(tmp_path)
    s = Service()
    s.new_assembly('Vecchio')
    s.asm_insert(str(pp))
    s.asm_insert(str(ps))
    s.asm_add_mate('faccia', {'inst': 'I1', 'face': faccia_di(s, 'I1', 'SM1/sopra')}, {'inst': 'I2', 'face': faccia_di(s, 'I2', 'SM1/sotto')})
    assert s.state()['giunti'] == []
    p = tmp_path / 'v.steelcad-asm'
    assert s._asm_save(str(p))['ok']
    testo = p.read_text(encoding='utf-8')
    assert 'moto' not in testo and 'angolo' not in testo and 'lim_' not in testo


def test_giunto_su_pezzo_tenuto_da_altri_lo_dice(porta, tmp_path):
    s, mid = porta
    assert s.asm_insert(str(_blocco(tmp_path, 'Fermo2', 10, 10, 10)))['ok']
    s.asm.instance('I3')['T'] = [300, 300, 0]
    s._asm_reload()
    assert s.asm_add_mate('blocca', {'inst': 'I1'}, {'inst': 'I3'})['ok']          # I3 attaccato al muro
    assert s.asm_add_mate('blocca', {'inst': 'I3'}, {'inst': 'I2'})['ok']          # e la porta attaccata a I3
    g = next(g for g in s.state()['giunti'] if g['id'] == mid)
    assert g['bloccato']
    r = s.asm_giunto_limiti(mid)
    assert not r['ok'] and 'altri accoppiamenti' in r['message']


def test_corsa_rapida(porta):
    """Il conto è rapido: i due lati del finecorsa in pochi secondi."""
    import time
    s, mid = porta
    t0 = time.perf_counter()
    M.trova_limiti(s.asm, s.asm_parts, mid)
    assert time.perf_counter() - t0 < 10


def test_anta_ufficio_sul_pilastro(tmp_path):
    """L'anta dell'ufficio (telaio di tubi 40×40) incernierata sullo spigolo davanti del tubo di sinistra, a 2 mm da un
    pilastro 80 × 80: i tubi non hanno nomi sulle facce (lo spigolo si ritrova da dov'è). Indietro tocca subito il
    pilastro, in avanti si apre oltre 90°: il verso si gira da solo, i gradi in positivo verso dove si apre."""
    import shutil
    shutil.copy(DATI / 'anta.steelcad', tmp_path / 'ANTA.steelcad')
    s = Service()
    assert s.new_assembly_con_pezzi('C', [{'path': str(_blocco(tmp_path, 'PILASTRO', 80, 80, 2200))},
                                          {'path': str(tmp_path / 'ANTA.steelcad')}])['ok']
    s.asm.instance('I1')['T'], s.asm.instance('I2')['T'] = [-82, -40, 0], [0, 0, 0]
    s._asm_reload()
    r = s.asm_add_mate('cerniera', {'inst': 'I2', 'edge_pt': [4, -20, 700]}, _faccia(s, 'I1'))
    assert r['ok'], r.get('message')
    m = s.asm.mates[-1]
    assert m['b']['kind'] == 'spigolo' and m['b']['faces'] is None
    r = s.asm_giunto_limiti(m['id'])
    assert r['ok'], r.get('message')
    lo, hi = next(x for x in s.asm.mates if x['id'] == m['id'])['lim_angolo']
    assert -5 < lo < 0 and hi > 90 and '«PILASTRO»' in r['message']
    assert s.asm_muovi_giunto(m['id'], {'angolo': 90}, False)['valori']['angolo'] == 90
    assert A.interferences(s.asm, s.asm_parts) == []
    # riaperto (il file salvato e riletto): lo spigolo senza nome si ritrova
    p = tmp_path / 'c.steelcad-asm'
    assert s._asm_save(str(p))['ok']
    s2 = Service()
    assert s2._asm_open(str(p))['ok'] and not s2.asm.warnings
    assert s2.asm_muovi_giunto(m['id'], {'angolo': 45}, False)['ok']


def test_trova_parte_dal_disegno_e_rimette_dentro(porta):
    """Trascinata dentro il blocco (senza finecorsa si può): «Trova da solo» cerca dalla posizione disegnata, non da
    lì, e il pezzo torna dentro il finecorsa trovato."""
    s, mid = porta
    s.asm_muovi_giunto(mid, {'angolo': -30}, True)                  # dentro il blocco (da −39,9° a −17,9°)
    assert A.interferences(s.asm, s.asm_parts)
    assert s.asm_giunto_limiti(mid)['ok']
    lo, hi = next(x for x in s.asm.mates if x['id'] == mid)['lim_angolo']
    assert lo == pytest.approx(-GIRO_BLOCCO, abs=0.15) and hi > 300
    assert s.asm_moto[mid]['angolo'] == pytest.approx(lo)
    assert A.interferences(s.asm, s.asm_parts) == []
