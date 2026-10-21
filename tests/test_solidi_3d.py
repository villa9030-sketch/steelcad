"""Rivoluzione, raccordi e smussi 3D sugli spigoli (21/10). Anche: i nomi delle facce di una rivoluzione restano
uguali riaprendo il file, e le quote automatiche di una linea inclinata non spostano i punti."""
import math

import build123d as bd

from app.service import Service
from cad_engine import assembly as A


def _punta(s, d=11.5, L=142):
    assert s.new_project('zero', {'name': 'Punta'})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    cono = (d / 2) / math.tan(math.radians(59))
    assert s.sketch_add_polyline(sid, [[0, 0], [d / 2, 0], [d / 2, L - cono], [0, L]], True)['ok']
    assert s.sketch_add_polyline(sid, [[0, -5], [0, L + 5]], False, True)['ok']
    return sid, cono


def test_rivoluzione_punta_e_nomi_stabili(tmp_path):
    s = Service()
    sid, cono = _punta(s)
    r = s.create_from_sketch(sid, 'revolve', {'angle': 360})
    assert r['ok'], r.get('message')
    sol = bd.Solid(s.result.body.shape)
    r_ = 11.5 / 2
    atteso = math.pi * r_ ** 2 * (142 - cono) + math.pi * r_ ** 2 * cono / 3
    assert abs(sol.volume - atteso) < 1e-3 * atteso
    cil = [f for f in sol.faces() if f.geom_type == bd.GeomType.CYLINDER]
    assert cil and abs(cil[0].radius - r_) < 1e-6                      # niente quota arrotondata che sposta i punti
    p = tmp_path / 'punta.steelcad'
    assert s.save(str(p))['ok']
    prima = {n: len(fs) for n, fs in s.result.body.names.items()}
    assert {n: len(fs) for n, fs in A.load_part(p).names.items()} == prima


def test_rivoluzione_vuole_l_asse_e_mezza_sezione():
    s = Service()
    assert s.new_project('zero', {'name': 'X'})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    assert s.sketch_add_rectangle(sid, [-5, 0], [5, 20])['ok']
    r = s.create_from_sketch(sid, 'revolve', {})
    assert not r.get('ok') or s.state()['errors']
    assert s.sketch_add_polyline(sid, [[0, -5], [0, 25]], False, True)['ok']


def test_raccordo_e_smusso_sugli_spigoli():
    s = Service()
    assert s.new_project('piastra', {'name': 'P', 'larghezza': 100, 'altezza': 60, 'spessore': 10, 'foro': 10})['ok']
    v0 = bd.Solid(s.result.body.shape).volume
    r = s.add_edge_dress('fillet', [[100, 60, 5], [0, 60, 5]], 8)
    assert r['ok'] and '2 spigoli' in r['message'], r.get('message')
    v1 = bd.Solid(s.result.body.shape).volume
    assert abs((v0 - v1) - 2 * (64 - math.pi * 16) * 10) < 1e-3              # due angoli R8 tolti sullo spessore
    r = s.add_edge_dress('chamfer', [[50, 0, 10]], 2)
    assert r['ok'], r.get('message')
    assert 'Raccordo R8' in str(s.state()['tree']) and 'Smusso 2 mm' in str(s.state()['tree'])
    s2 = Service()
    assert s2.new_project('lamiera', {'name': 'L', 'larghezza': 100, 'profondita': 50, 'spessore': 2})['ok']
    assert not s2.add_edge_dress('fillet', [[100, 50, 1]], 5)['ok']           # la lamiera si raccorda nel disegno
