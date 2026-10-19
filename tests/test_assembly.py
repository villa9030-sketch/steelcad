"""Assiemi: pezzi SteelCAD messi insieme con gli accoppiamenti, distinta, interferenze, incastri tra pezzi."""
import os

import numpy as np
import pytest

from app.service import Service
from cad_engine import assembly as A


def _pezzi(cartella):
    """Una piastra 200 × 100 sp. 3 con due fori Ø8 e una staffa a L (base 100 × 40 sp. 2, due fori Ø8, flangia 50)."""
    s = Service()
    s.new_project('lamiera', {'name': 'Piastra', 'larghezza': 200, 'profondita': 100, 'spessore': 3, 'raggio': 2, 'k': 0.4})
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    for x in (60, 140):
        assert s.sketch_add_circle(sid, [x, 50], 4)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    assert s.save(str(cartella / 'piastra.steelcad'))['ok']
    s = Service()
    s.new_project('lamiera', {'name': 'Staffa', 'larghezza': 100, 'profondita': 40, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    for x in (10, 90):
        assert s.sketch_add_circle(sid, [x, 20], 4)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    assert s.add_flange('SM1', 'L3', {'length': '50'})['ok']
    assert s.save(str(cartella / 'staffa.steelcad'))['ok']
    return cartella / 'piastra.steelcad', cartella / 'staffa.steelcad'


def _faccia(s, iid, nome=None, kind='piana', vicino=None):
    best = None
    for o in s.scene()['objects']:
        if o['id'] != iid:
            continue
        for f in o['faces']:
            inf = s._asm_face(iid, f['index'])
            if inf['kind'] != kind or (nome and inf['name'] != nome):
                continue
            d = np.linalg.norm(np.array(inf['p']) - np.array(vicino)) if vicino else 0
            if best is None or d < best[0]:
                best = (d, f['index'])
    return best[1]


def test_risolutore_faccia_e_fori(tmp_path):
    """La staffa parte girata a caso e lontana: faccia su faccia + due fori coassiali la mettono a posto."""
    pp, ps = _pezzi(tmp_path)
    asm = A.Assembly('Prova')
    asm.instances = [{'id': 'I1', 'file': str(pp.resolve()), 'name': 'Piastra'},
                     {'id': 'I2', 'file': str(ps.resolve()), 'name': 'Staffa', 'T': [300, 50, 80],
                      'R': A._rot_axis(np.array([0.3, 1, 0.2]), 1.1).tolist()}]
    parti = {i['file']: A.load_part(i['file']) for i in asm.instances}
    P, St = parti[asm.instances[0]['file']], parti[asm.instances[1]['file']]

    def ref(inst, part, name, kind, near):
        from cad_engine.topology.naming import _faces_of
        cand = [A.face_info(part, f) for f in _faces_of(part.shape)]
        cand = [c for c in cand if c['kind'] == kind and (not name or c['name'] == name)]
        return {'inst': inst, **min(cand, key=lambda c: np.linalg.norm(np.array(c['p']) - near))}
    asm.mates = [
        {'id': 'M1', 'type': 'faccia', 'a': ref('I1', P, 'SM1/sopra', 'piana', [100, 50, 3]), 'b': ref('I2', St, 'SM1/sotto', 'piana', [50, 20, 0])},
        {'id': 'M2', 'type': 'asse', 'a': ref('I1', P, None, 'cilindrica', [60, 50, 1]), 'b': ref('I2', St, None, 'cilindrica', [10, 20, 1])},
        {'id': 'M3', 'type': 'asse', 'a': ref('I1', P, None, 'cilindrica', [140, 50, 1]), 'b': ref('I2', St, None, 'cilindrica', [90, 20, 1])},
    ]
    R, T = A.solve(asm, parti)['I2']
    assert not asm.warnings
    assert np.allclose(R @ np.array([10, 20, 0]) + T, [60, 50, 3], atol=1e-6)        # foro sul foro, appoggiata
    assert np.allclose(R @ np.array([90, 20, 0]) + T, [140, 50, 3], atol=1e-6)
    assert A.interferences(asm, parti) == []


def test_assieme_dal_servizio(tmp_path):
    pp, ps = _pezzi(tmp_path)
    s = Service()
    st = s.new_assembly('Prova')['state']
    assert st['mode'] == 'assembly'
    assert s.asm_insert(str(pp))['ok'] and s.asm_insert(str(ps))['ok']
    r = s.asm_add_mate('faccia', {'inst': 'I1', 'face': _faccia(s, 'I1', 'SM1/sopra')}, {'inst': 'I2', 'face': _faccia(s, 'I2', 'SM1/sotto')})
    assert r['ok'], r.get('message')
    for a, b in (([60, 50, 1], [10, 20, 1]), ([140, 50, 1], [90, 20, 1])):
        r = s.asm_add_mate('asse', {'inst': 'I1', 'face': _faccia(s, 'I1', None, 'cilindrica', a)},
                           {'inst': 'I2', 'face': _faccia(s, 'I2', None, 'cilindrica', b)})
        assert r['ok'], r.get('message')
    i2 = s.asm.instance('I2')
    assert np.allclose(np.array(i2['R']) @ [10, 20, 1] + i2['T'], [60, 50, 4], atol=1e-6)
    st = s.state()
    assert [c['label'] for c in st['tree']['children']] == ['Piastra', 'Staffa', 'Accoppiamenti']
    assert [b['qty'] for b in st['bom']] == [1, 1] and st['bom_kg'] > 0.5
    # una faccia piana non va con "foro su foro"
    r = s.asm_add_mate('asse', {'inst': 'I1', 'face': _faccia(s, 'I1', 'SM1/sopra')}, {'inst': 'I2', 'face': _faccia(s, 'I2', 'SM1/sotto')})
    assert not r['ok'] and 'fori' in r['message']
    # distanza sull'accoppiamento: la staffa si alza di 10
    assert s.asm_edit_mate('M1', {'offset': 10})['ok']
    assert np.allclose(np.array(s.asm.instance('I2')['R']) @ [10, 20, 0] + s.asm.instance('I2')['T'], [60, 50, 13], atol=1e-6)
    # salva, annulla, riapri
    assert s.save(str(tmp_path / 'prova.steelcad-asm'))['ok']
    assert s.undo()['ok'] and s.asm.mates[0].get('offset') == 0
    s2 = Service()
    assert s2.open(str(tmp_path / 'prova.steelcad-asm'))['ok']
    assert len(s2.asm.mates) == 3 and not s2.state()['warnings']
    assert s2.home_info()['recent'][0]['name'] == 'prova'
    # apri un pezzo dall'assieme, modificalo, torna: l'assieme lo rilegge
    r = s2.asm_open_part('I2')
    assert r['ok'] and s2.state()['mode'] == 'part' and s2.state()['can_back']
    assert s2.add_flange('SM1', 'L1', {'length': '30'})['ok']
    assert not s2.asm_back()['ok']                                     # prima va salvato
    assert s2.save()['ok']
    assert s2.asm_back()['ok'] and s2.state()['mode'] == 'assembly'
    sm = next(f for f in s2.asm_parts[s2.asm.instance('I2')['file']].doc.features if isinstance(f, dict) and f.get('type') == 'sheet')
    assert len(sm['flanges']) == 2                                     # la flangia nuova c'è anche nell'assieme
    assert s2.export_step(str(tmp_path / 'assieme.step'))['ok'] and os.path.getsize(tmp_path / 'assieme.step') > 1000


def test_interferenze_e_incastri_tra_pezzi(tmp_path):
    """La staffa appoggiata con la punta della flangia sulla piastra: si compenetrano solo se la si spinge dentro;
    gli incastri mettono le linguette nella staffa e le asole nella piastra (due file salvati, con la copia .bak)."""
    pp, ps = _pezzi(tmp_path)
    s = Service()
    s.new_assembly('Incastri')
    s.asm_insert(str(pp))
    s.asm_insert(str(ps))
    punta = _faccia(s, 'I2', 'SM1/FL1/punta')
    assert s.asm_add_mate('faccia', {'inst': 'I1', 'face': _faccia(s, 'I1', 'SM1/sopra')}, {'inst': 'I2', 'face': punta})['ok']
    assert s.asm_interferences()['interferences'] == []
    assert s.asm_edit_mate('M1', {'offset': -1})['ok']                 # dentro di 1 mm: si compenetrano
    assert len(s.asm_interferences()['interferences']) == 1
    assert s.asm_edit_mate('M1', {'offset': 0})['ok']
    assert s.select('I2', punta)['selection'].get('tabs_with') == 'Piastra'
    assert not s.asm_tabs('I2', punta, 3, 15, 0.2, 0)['ok']              # la punta appoggia solo per 50 mm
    n0 = len(s.asm.mates)
    r = s.asm_tabs('I2', punta, 2, 10, 0.2, 0)
    assert r['ok'], r.get('message')
    assert len(s.asm.mates) == n0 + 2 and not s.state()['warnings']        # le linguette restano nelle asole
    assert (tmp_path / 'piastra.steelcad.bak').exists() and (tmp_path / 'staffa.steelcad.bak').exists()
    assert s.asm_interferences()['interferences'] == []
    vb = s.asm_parts[s.asm.instance('I1')['file']]
    assert any('Asole' in (f.get('name') or '') for f in vb.doc.features if isinstance(f, dict))


def test_struttura_pesa_uguale_nel_pezzo_e_nell_assieme(tmp_path):
    """Le aste si pesano come nella distinta del pezzo (kg/m × taglio): nell'assieme la stessa struttura pesava
    il 2–3% in meno perché si usava il volume del solido."""
    s = Service()
    assert s.new_project('telaio', {'name': 'Banco'})['ok']
    kg = s.state()['bom_kg']
    p = tmp_path / 'banco.steelcad'
    assert s.save(str(p))['ok']
    a = Service()
    a.new_assembly('Prova')
    assert a.asm_insert(str(p))['ok']
    righe = A.bom(a.asm, a.asm_parts)
    assert righe[0]['mass_kg'] == pytest.approx(kg, rel=1e-9)
