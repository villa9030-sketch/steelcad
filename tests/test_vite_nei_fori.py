"""Vite nei fori allineati (03/11, secondo giro): 2 clic, il foro di un pezzo e quello dell'altro, e la vite giusta
proposta dal diametro del foro (Ø13 → M12) e dallo spessore del pacco (8 + 5 + dado), con il dado sotto; un Annulla."""
import numpy as np
import pytest

from app.service import Service
from cad_engine import assembly as A
from cad_engine.topology.naming import _faces_of


def _piastra(cart, nome, L, P, sp, fori, d):
    s = Service()
    assert s.new_project('zero', {'name': nome})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    assert s.sketch_add_rectangle(sid, [0, 0], [L, P])['ok']
    for x, y in fori:
        assert s.sketch_add_circle(sid, [x, y], d / 2)['ok']
    assert s.create_from_sketch(sid, 'plate', {'thickness': sp})['ok']
    f = cart / f'{nome}.steelcad'
    assert s.save(str(f))['ok']
    return f


@pytest.fixture()
def assieme(tmp_path, monkeypatch):
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    monkeypatch.setenv('HOME', str(tmp_path))
    base = _piastra(tmp_path, 'Base', 300, 200, 8, [(25, 25), (275, 25), (275, 175), (25, 175)], 13)
    piatto = _piastra(tmp_path, 'Piatto', 80, 60, 5, [(20, 30)], 13)
    s = Service()
    assert s.new_assembly('Prova')['ok']
    assert s.asm_insert(str(base))['ok'] and s.asm_insert(str(piatto))['ok']
    return s


def _foro(s, iid, vicino):
    i = s.asm.instance(iid)
    part = s.asm_parts[i['file']]
    cand = []
    for k, f in enumerate(_faces_of(part.shape)):
        inf = A.face_info(part, f)
        if inf['kind'] == 'cilindrica':
            p = np.array(i['R']) @ np.array(inf['p']) + np.array(i['T'])
            cand.append((np.linalg.norm(p[:2] - np.array(vicino)), k))
    return {'inst': iid, 'face': min(cand)[1]}


def test_proposta_dal_diametro_e_dallo_spessore(assieme):
    s = assieme
    # il piatto appoggiato sulla base (faccia su faccia) e foro su foro
    a, b = _foro(s, 'I1', (25, 25)), _foro(s, 'I2', (20 + 350, 30))
    sopra = next(k for k, f in enumerate(_faces_of(s.asm_parts[s.asm.instance('I1')['file']].shape))
                 if A.face_info(s.asm_parts[s.asm.instance('I1')['file']], f)['kind'] == 'piana'
                 and A.face_info(s.asm_parts[s.asm.instance('I1')['file']], f)['n'][2] > 0.99)
    sotto = next(k for k, f in enumerate(_faces_of(s.asm_parts[s.asm.instance('I2')['file']].shape))
                 if A.face_info(s.asm_parts[s.asm.instance('I2')['file']], f)['kind'] == 'piana'
                 and A.face_info(s.asm_parts[s.asm.instance('I2')['file']], f)['n'][2] < -0.99)
    assert s.asm_add_mate('faccia', {'inst': 'I1', 'face': sopra}, {'inst': 'I2', 'face': sotto})['ok']
    assert s.asm_add_mate('asse', a, b)['ok']
    r = s.asm_bullone(a, b, {'verso': [0, 0, 1]}, True)
    assert r['ok'], r.get('message')
    p = r['proposta']
    assert (p['tipo'], p['misura'], p['dado']) == ('vite_te', 'M12', True)
    assert p['pacco'] == 13 and p['L'] == 30                      # 8 + 5 + dado 10,8 + 2 = 25,8 → 30
    assert r['allineati'] and 'M12×30' in p['testo'] and 'dado' in p['testo']


def test_due_clic_e_la_vite_c_e(assieme):
    s = assieme
    a, b = _foro(s, 'I1', (25, 25)), _foro(s, 'I2', (370, 30))
    n0 = len(s.asm.instances)
    # i fori non sono allineati: li allinea, poi vite e dado (il piatto resta dove l'asse lo porta)
    r = s.asm_bullone(a, b, {'verso': [0, 0, 1]})
    assert r['ok'], r.get('message')
    assert len(s.asm.instances) == n0 + 2
    assert 'M12' in r['message'] and 'dado' in r['message']
    assert not s.asm.warnings
    vite, dado = s.asm.instances[-2], s.asm.instances[-1]
    asse = np.array(vite['R'])[:, 1]
    assert abs(asse[2] - 1) < 1e-6                                 # testa in su
    assert abs(vite['T'][0] - 25) < 1e-4 and abs(vite['T'][1] - 25) < 1e-4
    assert abs(dado['T'][0] - 25) < 1e-4 and abs(dado['T'][1] - 25) < 1e-4
    # il piatto è stato portato sopra la base (la vite li stringe): niente pezzi uno dentro l'altro
    pt = A.placed_shape(s.asm_parts[s.asm.instance('I2')['file']], s.asm.instance('I2')['R'], s.asm.instance('I2')['T']).bounding_box()
    assert abs(pt.min.Z - 8) < 1e-4 and abs(vite['T'][2] - 13) < 1e-4
    assert 'M12×30' in r['message'] or 'M12x30' in r['message']
    assert 'Nessuna' in s.asm_interferences()['message']
    # un Annulla toglie tutto (vite, dado, foro su foro)
    s.undo()
    assert len(s.asm.instances) == n0 and not s.asm.mates


def test_vite_e_dado_sul_pacco(assieme):
    s = assieme
    a, b = _foro(s, 'I1', (25, 25)), _foro(s, 'I2', (370, 30))
    I1 = s.asm_parts[s.asm.instance('I1')['file']]
    I2 = s.asm_parts[s.asm.instance('I2')['file']]
    sopra = next(k for k, f in enumerate(_faces_of(I1.shape)) if A.face_info(I1, f)['kind'] == 'piana' and A.face_info(I1, f)['n'][2] > 0.99)
    sotto = next(k for k, f in enumerate(_faces_of(I2.shape)) if A.face_info(I2, f)['kind'] == 'piana' and A.face_info(I2, f)['n'][2] < -0.99)
    assert s.asm_add_mate('faccia', {'inst': 'I1', 'face': sopra}, {'inst': 'I2', 'face': sotto})['ok']
    r = s.asm_bullone(a, b, {'verso': [0, 0, 1]})
    assert r['ok'], r.get('message')
    vite, dado = s.asm.instances[-2], s.asm.instances[-1]
    assert abs(vite['T'][2] - 13) < 1e-4                          # sotto la testa sul piatto (8 + 5)
    bb = A.placed_shape(s.asm_parts[dado['file']], dado['R'], dado['T']).bounding_box()
    assert abs(bb.max.Z - 0) < 1e-4                              # il dado sotto la base
    assert 'Nessuna' in s.asm_interferences()['message']


def test_proposta_prima_di_allineare_conta_i_due_fori(assieme):
    s = assieme
    r = s.asm_bullone(_foro(s, 'I1', (25, 25)), _foro(s, 'I2', (370, 30)), {'verso': [0, 0, 1]}, True)
    assert r['ok'] and r['allineati'] is False
    import json
    json.dumps(r)                                                  # va al browser così com'è
    assert r['proposta']['pacco'] == 13 and r['proposta']['L'] == 30


def test_foro_troppo_piccolo_o_non_foro(assieme):
    s = assieme
    r = s.asm_bullone({'inst': 'I1', 'face': 0}, _foro(s, 'I2', (370, 30)), None, True)
    assert not r['ok']


def test_finestra_viteria_propone_la_misura_del_foro(assieme):
    s = assieme
    r = s.asm_vite_proposta(_foro(s, 'I1', (25, 25)), [0, 0, 1])
    assert r['ok'] and r['proposta']['misura'] == 'M12' and r['proposta']['L'] == 25    # 8 + dado + 2 → 25


def test_clic_vicino_al_foro_vale_come_clic_nel_foro(assieme):
    s = assieme
    sopra = next(k for k, f in enumerate(_faces_of(s.asm_parts[s.asm.instance('I1')['file']].shape))
                 if A.face_info(s.asm_parts[s.asm.instance('I1')['file']], f)['kind'] == 'piana'
                 and A.face_info(s.asm_parts[s.asm.instance('I1')['file']], f)['n'][2] > 0.99)
    # clic sulla faccia di sopra della base a 3 mm dal bordo del foro (25, 25), e nel foro del piatto
    vicino = {'inst': 'I1', 'face': sopra, 'pt': [25 + 6.5 + 3, 25, 8]}
    r = s.asm_bullone(vicino, _foro(s, 'I2', (370, 30)), {'verso': [0, 0, 1]}, True)
    assert r['ok'] and r['proposta']['misura'] == 'M12'
    assert s.asm_add_mate('asse', vicino, _foro(s, 'I2', (370, 30)))['ok']
    assert s.asm.mates[0]['a']['kind'] == 'cilindrica'
    lontano = {'inst': 'I1', 'face': sopra, 'pt': [150, 100, 8]}
    assert not s.asm_bullone(lontano, _foro(s, 'I2', (370, 30)), None, True)['ok']
