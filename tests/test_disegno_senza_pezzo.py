"""05/11 (Stefano: «ho schiacciato Esc 2 volte»): un disegno che non è ancora un pezzo, fuori dallo sketch, si vede
con le sue linee (prima restavano a video solo le quote, sospese nel vuoto). Quando il pezzo c'è, non si mostra più."""
from app.service import Service


def _disegno():
    s = Service()
    assert s.new_project('zero', {'name': 'Pezzo'})['ok']
    assert s.sketch_add_polyline('S1', [[0, 0], [200, 0], [200, 40], [40, 40], [40, 200], [0, 200]], True)['ok']
    assert s.sketch_add_circle('S1', [120, 120], 12.5)['ok']
    return s


def test_il_disegno_senza_pezzo_si_vede():
    s = _disegno()
    d = s.scene()['disegni']
    assert len(d) == 1 and d[0]['sketch'] == 'S1'
    assert len(d[0]['linee']) == 7                         # 6 lati e il cerchio
    xs = [p[0] for l in d[0]['linee'] for p in l]
    assert min(xs) == 0 and max(xs) == 200


def test_col_pezzo_fatto_non_si_mostra_piu():
    s = _disegno()
    assert s.create_from_sketch('S1', 'plate', {'thickness': 5})['ok']
    assert s.scene()['disegni'] == []
