"""Lo strato applicativo che usa l'interfaccia: solo dati JSON, errori chiari, undo."""
import json

from app.service import Service
from cad_engine.mesh import tessellate
from cad_engine import templates


def test_stato_e_scena_sono_json():
    s = Service()
    st = s.state()
    json.dumps(st)
    sc = s.scene()
    json.dumps(sc)
    assert len(sc['objects']) == 8
    o = sc['objects'][0]
    assert len(o['positions']) % 3 == 0 and max(o['indices']) < len(o['positions']) // 3
    assert sum(f['count'] for f in o['faces']) == len(o['indices'])


def test_mesh_piastra_con_nomi_di_faccia():
    d = templates.piastra()
    r = d.rebuild()
    m = tessellate(r.body.shape, r.body.names)
    assert len(m['faces']) == 7                     # 2 grandi, 4 fianchi, il foro
    assert all(f['name'] for f in m['faces'])
    assert m['edges']


def test_quote_sul_modello_e_modifica():
    s = Service()
    dims = {d['param']: d for d in s.state()['dimensions']}
    assert set(dims) == {'L', 'P'} and dims['L']['value'] == 2000
    r = s.set_dimension(dims['L']['sketch'], dims['L']['dim'], '2200')
    assert r['ok']
    lung = [x['length_mm'] for x in r['state']['cutlist']['rows']]
    assert 2240 in lung
    assert r['state']['undo'] == ['L = 2200']
    s.undo()
    assert 2040 in [x['length_mm'] for x in s.state()['cutlist']['rows']]


def test_modifica_asta_di_gruppo_e_rotazione():
    s = Service()
    r = s.edit_member('ST1/G1', {'profile': '60x40x3'}, whole_group=True)
    assert r['ok']
    gambe = [x for x in r['state']['cutlist']['rows'] if x['groups'] == ['Gambe']]
    assert gambe[0]['qty'] == 4 and '60' in gambe[0]['profile']
    r = s.edit_member('ST1/G1', {'rotate_by': 90})
    assert r['ok']
    assert s.doc.feature('ST1')['members'][4]['rotate'] == 90


def test_errori_chiari_non_rompono_il_progetto():
    s = Service()
    prima = s.state()['bom_kg']
    r = s.set_parameter('P', 'P*2')
    assert not r['ok'] and 'sé stesso' in r['message']
    r = s.edit_member('ST1/M1', {'profile': '40x40'})
    assert not r['ok'] and r['message']
    assert s.state()['bom_kg'] == prima
    assert s.state()['undo'] == []


def test_dxf_solo_per_piastra(tmp_path):
    s = Service()
    r = s.export_dxf(str(tmp_path / 'x.dxf'))
    assert not r['ok'] and 'cut list' in r['message']
    s.new_project('piastra', {'larghezza': '250'})
    r = s.export_dxf(str(tmp_path / 'p.dxf'))
    assert r['ok'] and '250' in r['message']
    r = s.export_step(str(tmp_path / 'p.step'))
    assert r['ok']


def test_salva_apri(tmp_path):
    s = Service()
    s.set_parameter('H', 800)
    p = tmp_path / 't.steelcad'
    assert s.save(str(p))['ok'] and not s.state()['dirty']
    s2 = Service()
    assert s2.open(str(p))['ok']
    assert next(x for x in s2.state()['parameters'] if x['name'] == 'H')['value'] == 800


def _cancello():
    s = Service()
    s.new_project('vuoto', {'name': 'Cancello'})
    assert s.add_member('ST1', 'A', direction='Z+', length=1000, profile='40x40x3', group='Montanti')['ok']
    assert s.add_member('ST1', 'N1', direction='X+', length='B', group='Traversi')['ok'] is False  # B non esiste
    s.set_parameter('B', 1500)
    assert s.add_member('ST1', 'N1', direction='X+', length='B', group='Traversi')['ok']
    assert s.add_member('ST1', 'N2', direction='Z-', length=1000, group='Montanti')['ok']
    r = s.add_member('ST1', 'N3', to_key='A', group='Traversi')
    assert r['ok'] and r['select'] == 'ST1/M4' and r['node'] == 'ST1:A'
    return s


def test_scheletro_da_zero_e_parametrico():
    s = _cancello()
    righe = sorted((x['length_mm'], tuple(x['cuts']), x['qty']) for x in s.state()['cutlist']['rows'])
    assert righe == [(1040.0, ('45°', '45°'), 2), (1540.0, ('45°', '45°'), 2)]
    s.set_parameter('B', 2000)                       # i nodi seguono il parametro
    assert sorted(x['length_mm'] for x in s.state()['cutlist']['rows']) == [1040.0, 2040.0]
    assert {n['key'] for n in s.scene()['nodes']} == {'A', 'N1', 'N2', 'N3'}


def test_giunti_dal_pannello():
    s = _cancello()
    sel = s.select('ST1:N1')['selection']
    assert set(sel['joint_types']) == {'auto', 'square', 'miter', 'butt', 'angle'}
    assert not s.set_joint('ST1', 'N1', {'type': 'butt'})['ok']             # manca chi passa
    assert not s.set_joint('ST1', 'N1', {'type': 'butt', 'through': ['M1', 'M2']})['ok']
    assert s.set_joint('ST1', 'N1', {'type': 'butt', 'through': ['M2']})['ok']
    tagli = {x['length_mm']: x['cuts'] for x in s.state()['cutlist']['rows']}
    assert 'dritto' in tagli[1000.0]                 # il montante batte sotto il traverso
    assert s.set_joint('ST1', 'N1', {'type': 'auto'})['ok']
    assert 'N1' not in (s.doc.feature('ST1').get('joints') or {})


def test_elimina_e_modifiche_che_rompono():
    s = _cancello()
    assert s.delete_members(['ST1/M2'])['ok']
    assert s.state()['cutlist']['pieces'] == 3
    s.undo()
    r = s.move_node('ST1', 'N1', [0, 0, 0])           # N1 sopra A: asta lunga zero
    assert not r['ok'] and r['message'].startswith('Non applicato')
    assert s.state()['cutlist']['pieces'] == 4 and s.state()['errors'] == []
    assert not s.add_member('ST1', 'A', to_key='N1')['ok']                   # c'è già
