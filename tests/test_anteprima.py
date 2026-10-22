"""Anteprima dei comandi (22/10, «ci deve essere SEMPRE una preview»): il comando provato su una copia; il progetto
vero non cambia (lavorazioni, Annulla, pezzo a video)."""
from app.service import Service


def _stato(s):
    return (len(s.doc.features), len(s.history.done), id(s.result))


def _prova(s, metodo, *args):
    prima = _stato(s)
    r = s.anteprima(metodo, list(args))
    assert _stato(s) == prima, metodo                                   # il progetto vero non si tocca
    return r


def test_lamiera_dal_contorno_piega_e_gradino():
    s = Service()
    assert s.new_project('zero', {'name': 'Staffa'})['ok']
    assert s.sketch_add_rectangle('S1', [0, 0], [300, 200])['ok']
    r = _prova(s, 'create_from_sketch', 'S1', 'sheet', {'thickness': '2', 'radius': '2', 'k': '0,4'})
    assert r['ok'] and r['objects'] and r['objects'][0]['positions']
    assert not _prova(s, 'create_from_sketch', 'S1', 'sheet', {'thickness': '-2'})['ok']        # in rosso, col perché
    assert s.create_from_sketch('S1', 'sheet', {'thickness': '2', 'radius': '2', 'k': '0,4'})['ok']
    fid = s.result.body.sheet.feature
    assert s.add_flange(fid, 'L1', {'length': '40'})['ok']
    flid = s.result.body.sheet.flanges[0].fid
    assert _prova(s, 'gradino', fid, flid, '2', '45', '20', 'dentro')['ok']


def test_struttura_e_serie_e_tubi():
    s = Service()
    assert s.new_project('disegno', {'name': 'Portale', 'piano': 'XZ'})['ok']
    assert s.sketch_add_polyline('S1', [[0, 0], [0, 900], [1500, 900], [1500, 0]], False)['ok']
    r = _prova(s, 'fai_tubi', 'S1', {'profile': '40x40x3', 'ripeti': 1, 'distanza': '600', 'collega': 1, 'collega_profile': '40x40x3'})
    assert r['ok'] and len(r['objects']) == 3 + 3 + 4                                         # sagoma, copia, traversi
    assert not _prova(s, 'fai_tubi', 'S1', {'profile': 'boh'})['ok']


def test_metodo_non_previsto():
    s = Service()
    assert not s.anteprima('save', ['x.steelcad'])['ok']                                        # niente file dalle anteprime
