"""Profilo disegnato estruso in lamiera, archi a colpi (21/10, Stefano: «disegnare il profilo, estruderlo e farlo
diventare una lamiera fatta in bumping»). Caso vero: la canala della coclea dentro una tramoggia, disegnata nell'assieme
sul foro della parete ed estrusa fino all'altra parete."""
import math

import build123d as bd
import numpy as np

from app.service import Service
from cad_engine import assembly as A

DATI = {'raggio': 1, 'k': 0.21}


def _u(s, sid, cx=0.0, cy=0.0, r=115, h=150):
    assert s.sketch_add_polyline(sid, [[cx - r, cy + h], [cx - r, cy]], False)['ok']
    assert s.sketch_add_arc3(sid, [cx - r, cy], [cx, cy - r], [cx + r, cy])['ok']
    assert s.sketch_add_polyline(sid, [[cx + r, cy], [cx + r, cy + h]], False)['ok']


def test_u_col_fondo_a_colpi():
    s = Service()
    assert s.new_project('zero', {'name': 'Canala'})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    _u(s, sid)
    r = s.create_from_sketch(sid, 'profilo', {'lunghezza': 1000, 'spessore': 3, 'colpi': 14, **DATI})
    assert r['ok'], r.get('message')
    sh = s.result.body.sheet
    assert len(sh.bend_rows) == 14 and all(abs(x['angle'] - 180 / 14) < 1e-6 for x in sh.bend_rows)
    b = bd.Solid(s.result.body.shape).bounding_box()
    assert abs(b.size.X - 236) < 0.1 and abs(b.size.Z - 1000) < 1e-6         # dentro 230, spessore fuori
    # sviluppo: due sponde + mezzo giro (poligono tangente: poco più del cerchio della fibra neutra)
    ideale = 2 * 150 + math.pi * (115 + 0.21 * 3)
    assert ideale < sh.flat_size[0] < ideale + 3 and abs(sh.flat_size[1] - 1000) < 1e-6
    passi = np.diff([x['position'] for x in sh.bend_rows])
    assert np.allclose(passi, passi[0])                                      # colpi a passo costante


def test_spessore_dall_altra_parte_e_spigoli_vivi():
    s = Service()
    assert s.new_project('zero', {'name': 'Omega'})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    assert s.sketch_add_polyline(sid, [[0, 0], [20, 0], [20, 30], [80, 30], [80, 0], [100, 0]], False)['ok']
    r = s.create_from_sketch(sid, 'profilo', {'lunghezza': 200, 'spessore': 2, 'gira': True, **DATI})
    assert r['ok'], r.get('message')
    assert len(s.result.body.sheet.bend_rows) == 4


def test_canala_coclea_nella_tramoggia(tmp_path):
    s = Service()
    assert s.new_project('piastra', {'name': 'Parete', 'larghezza': 600, 'altezza': 500, 'spessore': 5, 'foro': 230})['ok']
    assert s.save(str(tmp_path / 'Parete.steelcad'))['ok']
    assert s.new_assembly('Tramoggia con coclea')['ok']
    for k in range(2):
        assert s.asm_insert(str(tmp_path / 'Parete.steelcad'))['ok']
        iid = s.asm.instances[-1]['id']
        assert s.asm_rotate(iid, 'x', 90)['ok']
        i = s.asm.instance(iid)
        bb = A.placed_shape(s.asm_parts[i['file']], i['R'], i['T']).bounding_box()
        assert s.asm_move(iid, -bb.min.X, (0 if k == 0 else 1000) - bb.min.Y, -bb.min.Z)['ok']
    assert s.save(str(tmp_path / 'tramoggia.steelcad-asm'))['ok']
    a = s.asm.instances[0]['id']
    # la faccia interna della prima parete (guarda verso la seconda: normale +Y)
    i = s.asm.instance(a)
    R = np.array(i['R'])
    o = next(o for o in s.scene()['objects'] if o['id'] == a)
    faccia = next(f['index'] for f in o['faces'] if s._asm_face(a, f['index'])['kind'] == 'piana'
                  and (R @ np.array(s._asm_face(a, f['index'])['n']))[1] > 0.99)
    r = s.asm_new_part(a, faccia, 'Canala coclea')
    assert r['ok'], r.get('message')
    sid = r['sketch']
    foro = next(c for c in s.sketch_view(sid)['sketch']['circles'] if c.get('ref'))
    cx, cy = foro['xc']
    _u(s, sid, cx, cy, r=115, h=150)
    r = s.create_from_sketch(sid, 'profilo', {'lunghezza': 995, 'spessore': 3, 'colpi': 14, **DATI})
    assert r['ok'], r.get('message')
    r = s.asm_back()
    assert r['ok'], r.get('message')
    can = s.asm.instances[-1]
    bb = A.placed_shape(s.asm_parts[can['file']], can['R'], can['T']).bounding_box()
    assert abs(bb.min.Y - 5) < 0.1 and abs(bb.max.Y - 1000) < 0.1, (bb.min.Y, bb.max.Y)   # da parete a parete
    assert abs((bb.min.X + bb.max.X) / 2 - 300) < 0.1                                   # centrata sul foro
    assert abs(bb.max.Z - (250 + 150)) < 0.1 and 250 - 121 < bb.min.Z < 250 - 117       # sponde in su, fondo sotto
    assert not s.asm_interferences().get('interferences')
    assert s.save(str(tmp_path / 'tramoggia.steelcad-asm'))['ok']
