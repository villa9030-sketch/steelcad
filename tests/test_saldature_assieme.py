"""Saldature nell'assieme (28/10: «ovunque schiaccio mi da solo errori»): gli spigoli delle copie, i metri in distinta,
il cordone segue la copia quando si sposta, Annulla e Togli."""
import numpy as np

from app.service import Service


def _piastra(cart, nome):
    s = Service()
    assert s.new_project('piastra', {'name': nome, 'larghezza': 200, 'altezza': 100, 'spessore': 5})['ok']
    f = cart / f'{nome}.steelcad'
    assert s.save(str(f))['ok']
    return f


def _spigolo_lungo(s, iid):
    """Il punto a metà di uno spigolo lungo 200 della copia (coordinate del pezzo)."""
    o = next(o for o in s.scene()['objects'] if o['id'] == iid)
    for e in o['edges']:
        p = np.array(e, dtype=float).reshape(-1, 3)
        if len(p) == 2 and abs(np.linalg.norm(p[1] - p[0]) - 200) < 1e-6:
            return ((p[0] + p[1]) / 2).tolist()
    raise AssertionError('nessuno spigolo da 200')


def test_saldatura_tra_le_copie(tmp_path):
    f = _piastra(tmp_path, 'Piastra')
    s = Service()
    assert s.new_assembly('Prova')['ok']
    assert s.asm_insert(str(f))['ok'] and s.asm_insert(str(f))['ok']
    a, b = [i['id'] for i in s.asm.instances]
    r = s.add_saldatura([{'inst': a, 'p': _spigolo_lungo(s, a)}, {'inst': b, 'p': _spigolo_lungo(s, b)}], {'tipo': 'angolo', 'a': '4'})
    assert r['ok'], r.get('message')
    sw = r['state']['saldature']
    assert len(sw) == 1 and sw[0]['spigoli'] == 2 and abs(sw[0]['m'] - 0.4) < 1e-6 and not sw[0]['persa']
    # la copia b si sposta: il suo tratto la segue
    prima = np.array(sw[0]['linee'][1]).reshape(-1, 3)
    ib = s.asm.instance(b)
    ib['T'] = [ib['T'][0] + 50, ib['T'][1], ib['T'][2]]
    dopo = np.array(s.state()['saldature'][0]['linee'][1]).reshape(-1, 3)
    assert np.allclose(dopo - prima, [50, 0, 0])
    # si salva nell'assieme e si toglie
    assert s.asm.to_dict()['meta']['saldature'][0]['tipo'] == 'angolo'
    assert s.del_saldatura(0)['ok'] and s.state()['saldature'] == []


def test_lontano_dagli_spigoli(tmp_path):
    f = _piastra(tmp_path, 'Piastra')
    s = Service()
    assert s.new_assembly('Prova')['ok'] and s.asm_insert(str(f))['ok']
    a = s.asm.instances[0]['id']
    r = s.add_saldatura([{'inst': a, 'p': [1000, 1000, 1000]}], {'tipo': 'angolo', 'a': '4'})
    assert not r['ok'] and 'spigolo' in r['message']
