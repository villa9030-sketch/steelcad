"""Pezzo nuovo disegnato nell'assieme (21/10): una lamiera che collega due piastre, disegnata sul loro piano con i
bordi di tutte e due in arancio, montata da sola al suo posto tornando all'assieme."""
import numpy as np

from app.service import Service
from cad_engine import assembly as A


def _due_piastre(tmp_path):
    s = Service()
    for nome in ('Piastra A', 'Piastra B'):
        assert s.new_project('piastra', {'name': nome, 'larghezza': 200, 'altezza': 100, 'spessore': 10, 'foro': 20})['ok']
        assert s.save(str(tmp_path / f'{nome}.steelcad'))['ok']
    assert s.new_assembly('Collegamento')['ok']
    assert s.asm_insert(str(tmp_path / 'Piastra A.steelcad'))['ok']
    assert s.asm_insert(str(tmp_path / 'Piastra B.steelcad'))['ok']     # messa 50 mm a destra della prima
    assert s.save(str(tmp_path / 'collegamento.steelcad-asm'))['ok']
    return s


def _faccia_sopra(s, iid):
    i = s.asm.instance(iid)
    R, T = np.array(i['R']), np.array(i['T'])
    o = next(o for o in s.scene()['objects'] if o['id'] == iid)
    migliore = None
    for f in o['faces']:
        inf = s._asm_face(iid, f['index'])
        if inf['kind'] == 'piana':
            n, q = R @ np.array(inf['n']), R @ np.array(inf['p']) + T
            if n[2] > 0.99 and (migliore is None or q[2] > migliore[0]):
                migliore = (q[2], f['index'])
    return migliore[1]


def test_lamiera_che_collega_due_piastre(tmp_path):
    s = _due_piastre(tmp_path)
    a, b = (i['id'] for i in s.asm.instances)
    bb_a = A.placed_shape(s.asm_parts[s.asm.instance(a)['file']], s.asm.instance(a)['R'], s.asm.instance(a)['T']).bounding_box()
    bb_b = A.placed_shape(s.asm_parts[s.asm.instance(b)['file']], s.asm.instance(b)['R'], s.asm.instance(b)['T']).bounding_box()
    r = s.asm_new_part(a, _faccia_sopra(s, a), 'Lamiera di collegamento')
    assert r['ok'], r.get('message')
    sid = r['sketch']
    # nello sketch ci sono i bordi di tutte e due le piastre (anche il foro): ci si aggancia
    v = s.sketch_view(sid)['sketch']
    xs = [p['xy'][0] for p in v['points'] if p['id'] != 'O']
    assert max(xs) - min(xs) > (bb_b.max.X - bb_a.min.X) - 1
    assert sum(1 for c in v['circles'] if c.get('ref')) == 2
    # gli altri pezzi si vedono attorno (contesto), nelle coordinate del pezzo nuovo
    assert sum(1 for o in s.scene()['objects'] if o['kind'] == 'context') == 2
    # rettangolo da metà della prima a metà della seconda piastra, poi lamiera da 3
    x0, x1 = min(xs) + 100, max(xs) - 100
    ys = [p['xy'][1] for p in v['points'] if p['id'] != 'O']
    assert s.sketch_add_rectangle(sid, [x0, min(ys) + 20], [x1, max(ys) - 20])['ok']
    assert s.create_from_sketch(sid, 'sheet', {'thickness': 3})['ok']
    r = s.asm_back()
    assert r['ok'] and 'montato' in r['message'], r.get('message')
    nuova = s.asm.instances[-1]
    bb = A.placed_shape(s.asm_parts[nuova['file']], nuova['R'], nuova['T']).bounding_box()
    # appoggiata sopra le due piastre (sopra la faccia di sopra), a cavallo della fessura
    assert abs(bb.min.Z - bb_a.max.Z) < 1e-3 and abs(bb.size.Z - 3) < 1e-3
    assert bb.min.X < bb_a.max.X and bb.max.X > bb_b.min.X
    assert not s.asm_interferences().get('interferences')


def test_pezzo_lasciato_vuoto_non_entra(tmp_path):
    s = _due_piastre(tmp_path)
    a = s.asm.instances[0]['id']
    assert s.asm_new_part(a, _faccia_sopra(s, a), 'Vuoto')['ok']
    r = s.asm_back()
    assert r['ok'] and 'vuoto' in r['message'] and len(s.asm.instances) == 2
