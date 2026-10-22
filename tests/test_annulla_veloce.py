"""Annulla e Rifai ritrovano le versioni già fatte invece di ricostruire tutto (22/10)."""
from app.service import Service


def test_annulla_e_rifai_dalla_cache():
    s = Service()
    assert s.new_project('lamiera', {'name': 'L', 'larghezza': 200, 'profondita': 100, 'spessore': 2,
                                     'raggio': 1, 'k': 0.4})['ok']
    assert s.add_flange('SM1', 'L2', {'length': '40'})['ok']
    sk = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_circle(sk, [50, 50], 5)['ok']
    assert s.create_from_sketch(sk, 'cut', {})['ok']
    prima = s.result.body
    m1 = s.scene()['objects'][0]
    assert s.edit_flange('SM1', 'FL1', {'length': '55'})['ok']
    assert s.result.rebuilt > 0
    assert s.undo()['ok']
    assert s.result.rebuilt == 0 and s.result.body is prima       # niente rifatto: è il pezzo di prima
    assert s.scene()['objects'][0]['positions'] == m1['positions']
    assert s.redo()['ok'] and s.result.rebuilt == 0
    assert abs(s.result.body.sheet.flanges[0].length - 55) < 1e-6
