"""Accoppiamenti nuovi (21/10, Stefano: «devo avere più opzioni di quelle che ho»): distanza, parallele,
perpendicolari, angolo, tangente, in mezzo, blocca. Pezzi veri nell'assieme, come dal pulsante."""
import math

import numpy as np

from app.service import Service
from cad_engine import assembly as A


def _piastra(cart, nome, larg, alt, sp):
    s = Service()
    assert s.new_project('piastra', {'name': nome, 'larghezza': larg, 'altezza': alt, 'spessore': sp, 'foro': 5})['ok']
    f = cart / f'{nome}.steelcad'
    assert s.save(str(f))['ok']
    return f


def _tondo(cart, d=40, L=200):
    s = Service()
    assert s.new_project('zero', {'name': 'Tondo'})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    assert s.sketch_add_circle(sid, [0, 0], d / 2)['ok']
    r = s.create_from_sketch(sid, 'plate', {'thickness': L})
    assert r['ok'], r.get('message')
    f = cart / 'Tondo.steelcad'
    assert s.save(str(f))['ok']
    return f


def _assieme(cart, *files):
    s = Service()
    assert s.new_assembly('Prova')['ok']
    for f in files:
        assert s.asm_insert(str(f))['ok']
    return s


def _facce(s, iid):
    o = next(o for o in s.scene()['objects'] if o['id'] == iid)
    return [s._asm_face(iid, f['index']) | {'index': f['index']} for f in o['faces']]


def _faccia(s, iid, n=None, kind='piana', piu=True):
    """La faccia di iid con quella normale nel mondo (la più avanti lungo n se piu, la più indietro se no)."""
    i = s.asm.instance(iid)
    R, T = np.array(i['R']), np.array(i['T'])
    cand = []
    for f in _facce(s, iid):
        if f['kind'] != kind:
            continue
        nw, pw = R @ np.array(f['n']), R @ np.array(f['p']) + T
        if n is not None and np.dot(nw, n) < 0.999:
            continue
        cand.append((np.dot(pw, n) if n is not None else 0, f['index']))
    return {'inst': iid, 'face': (max if piu else min)(cand)[1]}


def _mondo(s, ref):
    i = s.asm.instance(ref['inst'])
    f = s._asm_face(ref['inst'], ref['face'])
    R, T = np.array(i['R']), np.array(i['T'])
    return R @ np.array(f['p']) + T, R @ np.array(f['n'])


def _bb(s, iid):
    i = s.asm.instance(iid)
    return A.placed_shape(s.asm_parts[i['file']], i['R'], i['T']).bounding_box()


Z, X, Y = np.array([0, 0, 1.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0])


def test_distanza_parte_da_quella_che_c_e_e_si_cambia(tmp_path):
    a, b = _piastra(tmp_path, 'A', 300, 200, 10), _piastra(tmp_path, 'B', 100, 100, 5)
    s = _assieme(tmp_path, a, b)
    assert s.asm_move('I2', 50, 20, 70)['ok']                    # B sopra A, staccata e spostata
    fa, fb = _faccia(s, 'I1', Z), _faccia(s, 'I2', -Z)
    prima = _bb(s, 'I2').min.Z
    r = s.asm_add_mate('distanza', fa, fb, None)
    assert r['ok'], r.get('message')
    assert abs(_bb(s, 'I2').min.Z - prima) < 1e-6                # misurata: non si muove niente
    m = s.asm.mates[-1]
    assert abs(m['offset'] - (prima - 10)) < 1e-6
    assert s.asm_edit_mate(m['id'], {'offset': '25'})['ok']
    assert abs(_bb(s, 'I2').min.Z - 35) < 1e-6 and not s.asm.warnings


def test_perpendicolari_angolo_e_parallele(tmp_path):
    a, b = _piastra(tmp_path, 'A', 300, 200, 10), _piastra(tmp_path, 'B', 100, 100, 5)
    s = _assieme(tmp_path, a, b)
    assert s.asm_move('I2', 400, 0, 0)['ok']
    fa, fb = _faccia(s, 'I1', Z), _faccia(s, 'I2', Z)
    r = s.asm_add_mate('perpendicolare', fa, fb)
    assert r['ok'], r.get('message')
    pa, na = _mondo(s, fa)
    pb, nb = _mondo(s, fb)
    assert abs(np.dot(na, nb)) < 1e-6 and not s.asm.warnings
    mid = s.asm.mates[-1]['id']
    assert s.asm_delete_mate(mid)['ok']
    r = s.asm_add_mate('angolo', fa, fb, 30)
    assert r['ok'], r.get('message')
    _, nb = _mondo(s, fb)
    assert abs(-np.dot(na, nb) - math.cos(math.radians(30))) < 1e-6 and not s.asm.warnings
    assert s.asm_edit_mate(s.asm.mates[-1]['id'], {'angle': '120'})['ok']
    _, nb = _mondo(s, fb)
    assert abs(math.degrees(math.acos(-np.dot(na, nb))) - 120) < 1e-4 and not s.asm.warnings
    assert s.asm_delete_mate(s.asm.mates[-1]['id'])['ok']
    r = s.asm_add_mate('parallelo', fa, fb)
    assert r['ok'], r.get('message')
    _, nb = _mondo(s, fb)
    assert np.linalg.norm(np.cross(na, nb)) < 1e-6 and not s.asm.warnings


def test_tondo_appoggiato_tangente_alla_piastra(tmp_path):
    a, t = _piastra(tmp_path, 'A', 300, 200, 10), _tondo(tmp_path)
    s = _assieme(tmp_path, a, t)
    assert s.asm_rotate('I2', 'x', 90)['ok']                       # il tondo coricato
    assert s.asm_move('I2', 100, 150, 60)['ok']
    fa = _faccia(s, 'I1', Z)
    ft = _faccia(s, 'I2', kind='cilindrica')
    r = s.asm_add_mate('tangente', fa, ft)
    assert r['ok'], r.get('message')
    bb = _bb(s, 'I2')
    assert abs(bb.min.Z - 10) < 1e-4 and abs(bb.max.Z - 50) < 1e-4 and not s.asm.warnings   # appoggiato sopra
    assert not s.asm_interferences().get('interferences')
    r = s.asm_add_mate('tangente', fa, _faccia(s, 'I2'))
    assert not r['ok'] and 'tubo' in r['message']


def test_in_mezzo_centra_il_piatto(tmp_path):
    a, b = _piastra(tmp_path, 'A', 300, 200, 40), _piastra(tmp_path, 'B', 100, 100, 10)
    s = _assieme(tmp_path, a, b)
    assert s.asm_move('I2', 400, 0, 3)['ok']
    r = s.asm_add_mate('centra', _faccia(s, 'I1', Z), _faccia(s, 'I2', Z), None, False,
                       _faccia(s, 'I1', -Z), _faccia(s, 'I2', -Z))
    assert r['ok'], r.get('message')
    bb = _bb(s, 'I2')
    assert abs((bb.min.Z + bb.max.Z) / 2 - 20) < 1e-6 and not s.asm.warnings
    r = s.asm_add_mate('centra', _faccia(s, 'I1', Z), _faccia(s, 'I2', Z), None, False,
                       _faccia(s, 'I1', X), _faccia(s, 'I2', -Z))
    assert not r['ok'] and 'parallele' in r['message']


def test_blocca_tiene_il_pezzo_dove_sta(tmp_path):
    a, b = _piastra(tmp_path, 'A', 300, 200, 10), _piastra(tmp_path, 'B', 100, 100, 5)
    s = _assieme(tmp_path, a, b)
    assert s.asm_rotate('I2', 'y', 90)['ok'] and s.asm_move('I2', 120, 30, 10)['ok']
    prima = _bb(s, 'I2')
    r = s.asm_add_mate('blocca', {'inst': 'I1', 'face': 0}, {'inst': 'I2', 'face': 0})
    assert r['ok'], r.get('message')
    assert s.asm_move('I2', 500, 0, 0)['ok']                      # lo sposti: torna lì, è bloccato
    dopo = _bb(s, 'I2')
    assert abs(dopo.min.X - prima.min.X) < 1e-6 and abs(dopo.max.Z - prima.max.Z) < 1e-6
