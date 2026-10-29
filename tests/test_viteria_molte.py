"""Viteria a quantità (28/10: «non stare lì a farlo una alla volta»): una vite in ogni foro uguale del pezzo,
appoggiata sotto la testa dal lato da cui si guarda; senza foro, N pezzi; un solo Annulla."""
import numpy as np

from app.service import Service
from cad_engine import assembly as A
from cad_engine.topology.naming import _faces_of


def _piastra_4_fori(cart):
    s = Service()
    assert s.new_project('zero', {'name': 'Piastra4'})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    assert s.sketch_add_rectangle(sid, [0, 0], [200, 120])['ok']
    for x, y in ((20, 20), (180, 20), (180, 100), (20, 100)):
        assert s.sketch_add_circle(sid, [x, y], 3.3)['ok']
    r = s.create_from_sketch(sid, 'plate', {'thickness': 6})
    assert r['ok'], r.get('message')
    f = cart / 'Piastra4.steelcad'
    assert s.save(str(f))['ok']
    return f


def _assieme(tmp_path, monkeypatch):
    monkeypatch.setenv('USERPROFILE', str(tmp_path))          # la Libreria delle viti nella cartella della prova
    monkeypatch.setenv('HOME', str(tmp_path))
    s = Service()
    assert s.new_assembly('Prova')['ok']
    assert s.asm_insert(str(_piastra_4_fori(tmp_path)))['ok']
    p = s.asm.instances[0]['id']
    part = s.asm_parts[s.asm.instance(p)['file']]
    foro = next(k for k, f in enumerate(_faces_of(part.shape)) if A.face_info(part, f)['kind'] == 'cilindrica')
    return s, p, foro


def test_in_tutti_i_fori_uguali(tmp_path, monkeypatch):
    s, p, foro = _assieme(tmp_path, monkeypatch)
    assert s.asm_fori_uguali(p, foro)['n'] == 4
    r = s.asm_insert_viteria('vite_tcei', 'M6', 20, {'inst': p, 'face': foro}, {'tutti': True, 'appoggia': True, 'verso': [0, 0, 1]})
    assert r['ok'], r.get('message')
    assert '4 ×' in r['message'] and 'appoggiate' in r['message']
    viti = s.asm.instances[1:]
    assert len(viti) == 4
    centri = set()
    for v in viti:
        T = np.array(v['T'])
        asse = np.array(v['R'])[:, 1]                        # l'asse della vite (Y nel suo pezzo)
        assert abs(abs(asse[2]) - 1) < 1e-6                  # verticale, come i fori
        assert abs(T[2] - 6) < 1e-4                          # il sotto della testa sulla faccia di sopra (z = 6)
        centri.add((round(T[0]), round(T[1])))
    assert centri == {(20, 20), (180, 20), (180, 100), (20, 100)}
    # un solo Annulla le toglie tutte
    assert s.asm_undo[-1][0].startswith('4 ×')
    s.asm_undo_step() if hasattr(s, 'asm_undo_step') else s.undo()
    assert len(s.asm.instances) == 1


def test_dal_lato_che_guardi(tmp_path, monkeypatch):
    s, p, foro = _assieme(tmp_path, monkeypatch)
    r = s.asm_insert_viteria('vite_tcei', 'M6', 20, {'inst': p, 'face': foro}, {'tutti': False, 'appoggia': True, 'verso': [0, 0, -1]})
    assert r['ok'], r.get('message')
    v = s.asm.instances[1]
    assert abs(v['T'][2]) < 1e-4                            # da sotto: la testa sulla faccia di sotto (z = 0)


def test_senza_foro_n_pezzi(tmp_path, monkeypatch):
    s, p, foro = _assieme(tmp_path, monkeypatch)
    r = s.asm_insert_viteria('dado', 'M6', None, None, {'quante': '6'})
    assert r['ok'], r.get('message')
    assert len(s.asm.instances) == 7 and '6 ×' in r['message']


def test_pacco_di_due_piastre(tmp_path, monkeypatch):
    """Il foro della piastra sotto, un'altra piastra appoggiata sopra coi fori allineati: la testa va in cima al pacco."""
    s, p, foro = _assieme(tmp_path, monkeypatch)
    assert s.asm_insert(s.asm.instance(p)['file'])['ok']
    sopra = s.asm.instances[-1]
    sopra['R'] = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    sopra['T'] = [0, 0, 6]
    sopra['fixed'] = True
    s.asm.instance(p)['fixed'] = True
    r = s.asm_insert_viteria('vite_tcei', 'M6', 20, {'inst': p, 'face': foro}, {'tutti': False, 'appoggia': True, 'verso': [0, 0, 1]})
    assert r['ok'], r.get('message')
    assert abs(s.asm.instances[-1]['T'][2] - 12) < 1e-4
