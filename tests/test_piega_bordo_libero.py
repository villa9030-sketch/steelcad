"""Piega su un bordo libero qualsiasi (21/10): il bordo inclinato del materiale aggiunto su una parete si borda."""
import os
import tempfile

import build123d as bd
import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


def test_bordo_sul_materiale_aggiunto():
    s = Service()
    s.new_project('lamiera', {'name': 'C', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 1, 'k': 0.4})
    assert s.add_flange('SM1', 'L2', {'length': '50'})['ok']
    # la parete diventa inclinata: materiale aggiunto sopra la punta, da 47 a 90 verso il fondo
    sid = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    v = s.sketch_view(sid)['sketch']
    xs = sorted({round(p['xy'][0], 3) for p in v['points'] if p['id'] != 'O'})
    ys = sorted({round(p['xy'][1], 3) for p in v['points'] if p['id'] != 'O'})
    x0, x1, top = xs[0], xs[-1], ys[-1]
    assert s.sketch_add_polyline(sid, [[x0, top], [x1, top + 40], [x1, top]], False)['ok']
    assert s.sheet_tab(sid)['ok']
    a0 = s.result.body.sheet.flat_area
    liberi = [e for e in s.scene()['bend_edges'] if e['kind'] == 'libero']
    e = max(liberi, key=lambda x: x['length'])
    assert e['length'] > 190                              # il lato inclinato
    r = s.add_edge_flange(e['face'], e['ea'], e['eb'], {'length': '20', 'angle': '90', 'direction': 'up'})
    assert r['ok'], r.get('message')
    assert len(bd.Shape.cast(s.result.body.shape).solids()) == 1
    assert s.result.body.sheet.flat_area > a0 + e['length'] * 15
    fid = r['select'][3:]
    assert s.select(r['select'])['selection']['kind'] == 'edgeflange'
    assert s.edit_edge_flange(fid, {'length': '25'})['ok']
    # sulla faccia della piega nuova si disegna, e il suo bordo è di nuovo libero
    assert s.sketch_on_face(f'{fid}/esterno')['ok']
    assert any(x['face'] == f'{fid}/esterno' for x in s.scene()['bend_edges'] if x['kind'] == 'libero')
    assert s.tree_action('sheet_edge_flange', fid, 'elimina')['ok']


def test_tabella_pieghe_con_fianchi_e_bordi_liberi(tmp_path):
    """Le pieghe sul fianco di una parete e sui bordi liberi stanno in tabella con le altre (22/10)."""
    s = Service()
    s.new_project('lamiera', {'name': 'C', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 1, 'k': 0.4})
    s.add_flange('SM1', 'L2', {'length': '50'})
    assert s.set_ear('SM1', 'FL1', 'u0', True, {'length': '20'})['ok']
    e = next(x for x in s.scene()['bend_edges'] if x['kind'] == 'libero')
    assert s.add_edge_flange(e['face'], e['ea'], e['eb'], {'length': '15'})['ok']
    righe = s.result.body.sheet.summary()['bends']
    assert {'FL1', 'FL1/u0'} <= {r['flange'] for r in righe} and any(r['edge'] == 'bordo libero' for r in righe)
    p = tmp_path / 'pieghe.csv'
    r = s.export_bend_table(str(p))
    assert r['ok'] and '3 pieghe' in r['message'] and 'bordo libero' in p.read_text(encoding='utf-8-sig')


def test_gioco_agli_angoli():
    """Gioco scritto a mano: la piega si accorcia ai due capi (22/10)."""
    s = Service()
    s.new_project('lamiera', {'name': 'C', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 1, 'k': 0.4})
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_polyline(sid, [[100, 200], [100, 240], [200, 240], [200, 200]], False)['ok'] and s.sheet_tab(sid)['ok']
    e = max((x for x in s.scene()['bend_edges'] if x['kind'] == 'libero'), key=lambda x: x['length'])
    r = s.add_edge_flange(e['face'], e['ea'], e['eb'], {'length': '20', 'trim0': '5', 'trim1': '7'})
    assert r['ok'], r.get('message')
    assert abs(s.result.body.sheet.extra_bends[-1]['width'] - 88) < 1e-6
    assert s.edit_edge_flange(r['select'][3:], {'trim0': '', 'trim1': ''})['ok']           # di nuovo automatico
    assert abs(s.result.body.sheet.extra_bends[-1]['width'] - 100) < 1e-6
