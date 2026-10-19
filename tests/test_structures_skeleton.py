"""Strutture da scheletro disegnato: linee dello sketch → tubolari, ripetizioni a distanza, collegamenti,
eccezioni per singola asta, modelli a misure (scaffale, armadio, cancello)."""
import pytest

from app import sketch_ops as so
from app.service import Service
from cad_engine import templates
from cad_engine.document import Document
from cad_engine.structures import cut_list


def _righe(res):
    return sorted((r['profile'], r['length_mm'], '/'.join(r['cuts']), r['qty']) for r in cut_list(res.structures)['rows'])


def test_spalla_ripetuta_e_collegata():
    """Scaffale disegnato: spalla di fianco 400 × 1800 con 4 ripiani, ripetuta a L = 1000 e collegata.
    Montanti 30×30 sotto e sopra battono contro i traversi (1800 − 2·20 del 40×20 messo in piedi), i traversi
    intermedi battono contro i montanti (400 − 30), quelli in cima e a terra si tagliano a 45°."""
    d = Document('Scaffale', 'S235')
    d.set_parameter('L', 1000)
    sk = d.add_sketch('YZ', 'Spalla')
    so.add_polyline(d, sk.id, ['O', [0, 1800]], False)
    so.add_polyline(d, sk.id, [[400, 0], [400, 1800]], False)
    for h in (0, 600, 1200, 1800):                 # i punti a terra coincidono: lo scheletro li unisce
        so.add_polyline(d, sk.id, [[0, h], [400, h]], False)
    d.add_feature('structure', 'Scaffale', points={}, members=[], skeletons=[{
        'id': 'K1', 'sketch': sk.id, 'profile': '30x30x2', 'group': 'Spalle',
        'copies': [[0, 0, 0], ['L', 0, 0]], 'connect': {'profile': '40x20x2', 'group': 'Traversi'}}])
    res = d.rebuild()
    assert res.ok, [f.message for f in res.errors]
    assert len(res.structures[0].members) == 20 and not res.structures[0].warnings
    assert _righe(res) == [('30×30×2', 370.0, 'dritto/dritto', 4), ('30×30×2', 430.0, '45°/45°', 4),
                           ('30×30×2', 1760.0, 'dritto/dritto', 4),
                           ('40×20×2', 970.0, 'dritto/dritto', 4), ('40×20×2', 1020.0, '45°/45°', 4)]
    d.set_parameter('L', 1200)                     # la distanza è un parametro
    assert ('40×20×2', 1170.0, 'dritto/dritto', 4) in _righe(d.rebuild())


@pytest.mark.parametrize('nome,pezzi', [('scaffale', 20), ('armadio', 16), ('cancello', 15)])
def test_modelli_a_misure(nome, pezzi):
    doc = getattr(templates, nome)()
    res = doc.rebuild()
    assert res.ok, [f.message for f in res.errors]
    assert cut_list(res.structures)['pieces'] == pezzi
    assert not res.structures[0].warnings


def test_cancello_sbarre_e_parametri():
    doc = templates.cancello(L=1500, H=1200, passo=120)
    res = doc.rebuild()
    assert ('20×20×2', 1140.0, 'dritto/dritto', 11) in _righe(res)      # 1200 − 60 del telaio
    doc.set_parameter('H', 1000)
    assert ('20×20×2', 940.0, 'dritto/dritto', 11) in _righe(doc.rebuild())


def test_dallo_sketch_con_eccezioni():
    s = Service()
    assert s.new_project('disegno', {'name': 'Telaio', 'piano': 'XZ'})['ok']
    assert s.sketch_add_rectangle('S1', 'O', [1000, 2000])['ok']
    v = s.sketch_view('S1')['sketch']
    assert v['open'] is False
    sx = next(l['id'] for l in v['lines'] if l.get('label') == 'lato sinistro')
    dx = next(l['id'] for l in v['lines'] if l.get('label') == 'lato destro')
    assert s.sketch_add_polyline('S1', [{'on': sx, 'xy': [0, 1000]}, {'on': dx, 'xy': [1000, 1000]}], False)['ok']
    r = s.create_from_sketch('S1', 'structure', {'profile': '40x40x3', 'group': 'Spalle', 'copies': 2,
                                                 'distance': 600, 'side': 'back', 'connect': True,
                                                 'connect_profile': '40x20x2'})
    assert r['ok'], r.get('message')
    assert r['state']['cutlist']['pieces'] == 16
    asta = s.result.structures[0].members[0].id
    assert s.edit_member(f'ST1/{asta}', {'profile': '50x50x3'})['ok']
    assert s.doc.feature('ST1')['overrides'][asta]['profile'] == '50x50x3'
    assert s.delete_members([f'ST1/{asta}'])['ok']
    assert s.state()['cutlist']['pieces'] == 15
    # cambio lo sketch: le eccezioni restano, la struttura segue
    alto = next(d for d in s.state()['dimensions'] if d['label'] == '2000')
    assert s.set_dimension(alto['sketch'], alto['dim'], 2200)['ok']
    assert s.state()['cutlist']['pieces'] == 15
    assert 2160.0 in {x['length_mm'] for x in s.state()['cutlist']['rows']}


def test_scheletro_aperto_va_bene():
    s = Service()
    s.new_project('disegno', {'piano': 'XY'})
    assert s.sketch_add_polyline('S1', ['O', [1000, 0], [1000, 500]], False)['ok']
    v = s.sketch_view('S1')['sketch']
    assert v['open'] and 'struttura' in v['status']
    r = s.create_from_sketch('S1', 'structure', {'profile': '40x40x3'})
    assert r['ok'] and r['state']['cutlist']['pieces'] == 2


def test_modello_si_modifica_dopo():
    """I dati del modello (anche ripiani e profili) si cambiano dopo: la struttura si rifà, i ritocchi restano."""
    s = Service()
    s.new_project('scaffale', {})
    sel = s.select('struct=ST1')['selection']
    assert [f[0] for f in sel['template']['fields']] == ['L', 'P', 'H', 'ripiani', 'montanti', 'traversi']
    asta = s.result.structures[0].members[0].id
    assert s.edit_member(f'ST1/{asta}', {'profile': '50x50x3'})['ok']
    r = s.structure_template_apply('ST1', {'ripiani': 5, 'H': 2200, 'traversi': '40x30x2'})
    assert r['ok'], r.get('message')
    assert r['state']['cutlist']['pieces'] == 24
    assert s.doc.feature('ST1')['overrides'][asta] == {'profile': '50x50x3'}
    assert next(p for p in r['state']['parameters'] if p['name'] == 'H')['value'] == 2200
    assert s.undo()['ok'] and s.state()['cutlist']['pieces'] == 20
    assert not s.structure_template_apply('ST1', {'montanti': '40x40'})['ok']
