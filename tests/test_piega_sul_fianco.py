"""Piega sul fianco di una parete (cassetta in un pezzo da rivettare, Stefano 21/10): 90° verso l'interno, fuori
dall'angolo del contorno di spessore + gioco; la parete del lato vicino, piegata dopo, sale e resta dentro."""
import os
import tempfile

import build123d as bd
import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


def test_cassetta_con_pieghe_sui_fianchi():
    s = Service()
    assert s.new_project('lamiera', {'name': 'C', 'larghezza': 300, 'profondita': 190, 'spessore': 2, 'raggio': 1, 'k': 0.4})['ok']
    for e in ('L2', 'L4'):
        assert s.add_flange('SM1', e, {'length': '200'})['ok']
    a0 = s.result.body.sheet.flat_area
    for fl in ('FL1', 'FL2'):
        for end in ('u0', 'u1'):
            r = s.set_ear('SM1', fl, end, True, {'length': '20'})
            assert r['ok'], r.get('message')
    sh = bd.Shape.cast(s.result.body.shape)
    assert len(sh.solids()) == 1
    bb = sh.bounding_box()
    assert bb.min.Y == pytest.approx(-2.2, abs=1e-6) and bb.max.Y == pytest.approx(192.2, abs=1e-6)   # gioco 0,2 + sp
    assert s.result.body.sheet.flat_area > a0
    for e in ('L1', 'L3'):                         # le pareti davanti e dietro salgono dentro
        r = s.add_flange('SM1', e, {'length': '200'})
        assert r['ok'], r.get('message')
    assert len(bd.Shape.cast(s.result.body.shape).solids()) == 1
    assert s.set_ear('SM1', 'FL1', 'u0', False)['ok']
    assert len([e for e in s._sheet_def('SM1')['flanges'][0].get('ears', [])]) == 1


def test_piega_sul_fianco_piu_corta_e_alzata():
    s = Service()
    s.new_project('lamiera', {'name': 'C', 'larghezza': 300, 'profondita': 190, 'spessore': 2, 'raggio': 1, 'k': 0.4})
    s.add_flange('SM1', 'L2', {'length': '200'})
    a0 = s.result.body.sheet.flat_area
    assert s.set_ear('SM1', 'FL1', 'u1', True, {'length': '20', 'height': '100', 'from': '50'})['ok']
    assert s.result.body.sheet.flat_area > a0
    assert not s.set_ear('SM1', 'FL1', 'u1', True, {'length': '20', 'height': '190', 'from': '50'})['ok']   # esce dalla parete


def test_ogni_parete_ha_i_suoi_due_bordi():
    """Clic sul bordo: ogni parete ha i suoi due bordi laterali, ognuno per conto suo; fatta la piega, quel bordo sparisce."""
    s = Service()
    s.new_project('lamiera', {'name': 'C', 'larghezza': 300, 'profondita': 190, 'spessore': 2, 'raggio': 1, 'k': 0.4})
    s.add_flange('SM1', 'L2', {'length': '200'})
    s.add_flange('SM1', 'L4', {'length': '200'})
    lati = [e for e in s.scene()['bend_edges'] if e['kind'] == 'side']
    assert sorted(e['ref'] for e in lati) == ['FL1/u0', 'FL1/u1', 'FL2/u0', 'FL2/u1']
    r = s.set_ear('SM1', 'FL1', 'u0', True, {'length': '20', 'angle': '90', 'direction': 'up'})
    assert r['ok'] and r['select'] == 'flange=SM1/FL1/u0'
    assert 'FL1/u0' not in [e['ref'] for e in s.scene()['bend_edges'] if e['kind'] == 'side']
    sel = s.select('flange=SM1/FL1/u0')['selection']
    assert sel['kind'] == 'sidebend' and sel['def']['direction'] == 'up'
    # sulla faccia della piega si disegna e si fora: il foro va anche nello sviluppo
    sid = s.sketch_on_face('SM1/FL1/u0/esterno')['sketch']
    assert s.sketch_add_circle(sid, [10, 100], 2.5)['ok']
    a0 = s.result.body.sheet.flat_area
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    assert a0 - s.result.body.sheet.flat_area == pytest.approx(3.14159265 * 2.5 ** 2, abs=1e-3)
    assert s.set_ear('SM1', 'FL2', 'u1', True, {'length': '30', 'angle': '45', 'direction': 'down'})['ok']


def test_svasatura_sulla_piega_sul_bordo():
    """Un foro svasato sulla faccia di una piega sul bordo: il cono c'è nel 3D, lo sviluppo resta quello del foro."""
    s = Service()
    s.new_project('lamiera', {'name': 'C', 'larghezza': 300, 'profondita': 280, 'spessore': 2, 'raggio': 1, 'k': 0.21})
    s.add_flange('SM1', 'L2', {'length': '50'})
    assert s.set_ear('SM1', 'FL1', 'u0', True, {'length': '20'})['ok']
    sid = s.sketch_on_face('SM1/FL1/u0/esterno')['sketch']
    assert s.sketch_add_circle(sid, [8, 25], 2.5)['ok']
    cid = next(k for k, e in s.doc.sketch(sid).entities.items() if e['kind'] == 'circle' and not e.get('ref'))
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    a0 = s.result.body.sheet.flat_area
    r = s.sketch_hole_type(sid, [cid], {'tipo': 'svasato', 'D': '8', 'angolo': '90'})
    assert r['ok'], r.get('message')
    assert any(f.geom_type == bd.GeomType.CONE for f in bd.Shape.cast(s.result.body.shape).faces())
    assert s.result.body.sheet.flat_area == pytest.approx(a0, abs=1e-6)


def test_svasatura_sui_fori_del_primo_sketch():
    """Fori disegnati nel contorno della lamiera: si cliccano sul pezzo (pannello del foro) e si svasano (21/10)."""
    s = Service()
    s.new_project('lamiera', {'name': 'L', 'larghezza': 120, 'profondita': 80, 'spessore': 2})
    sid = s._sheet_def('SM1')['sketch']
    s.sketch_add_circle(sid, [40, 40], 3.2)
    s.sketch_add_circle(sid, [80, 40], 3.2)
    s.add_flange('SM1', 'L1', {'length': '30'})
    f = next(f for f in s.scene()['objects'][0]['faces'] if (f['name'] or '').startswith('SM1/foro/'))
    fo = s.select('body', f['index'], f['name'])['selection']['foro']
    assert fo['d'] == pytest.approx(6.4) and len(fo['uguali']) == 2
    a0 = s.result.body.sheet.flat_area
    assert s.sketch_hole_type(sid, fo['uguali'], {'tipo': 'svasato', 'D': '9', 'angolo': '90'})['ok']
    assert len([x for x in bd.Shape.cast(s.result.body.shape).faces() if x.geom_type == bd.GeomType.CONE]) == 2
    assert s.result.body.sheet.flat_area == pytest.approx(a0, abs=1e-6)
