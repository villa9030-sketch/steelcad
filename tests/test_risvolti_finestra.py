"""04/11, pannello parete: «perché da questi tagli non posso fare le pieghe?». I lati dritti di una finestra tagliata
nella lamiera non si accendevano (si cercavano i bordi solo sul contorno esterno della faccia). Ora si piegano, e
quando i risvolti si incrociano negli angoli dello sviluppo la piega si accorcia da sola di quanto serve."""
from app.service import Service


def _pannello_con_finestra():
    s = Service()
    assert s.new_project('lamiera', {'name': 'Pannello', 'larghezza': 600, 'profondita': 400, 'spessore': 2,
                                     'raggio': 1, 'k': 0.4})['ok']
    sk = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_rectangle(sk, [100, 80], [500, 320])['ok']
    assert s.create_from_sketch(sk, 'cut', {})['ok']
    return s


def test_i_lati_della_finestra_si_accendono():
    s = _pannello_con_finestra()
    liberi = sorted(round(e['length']) for e in s.scene()['bend_edges'] if e['kind'] == 'libero')
    assert liberi == [240, 240, 400, 400], liberi


def test_quattro_risvolti_nella_finestra():
    s = _pannello_con_finestra()
    a0 = s.result.body.sheet.flat.area
    for lato in (240, 400, 240, 400):
        # i lati rimasti della finestra (gli scarichi delle pieghe già fatte li accorciano di qualche millimetro)
        e = max((x for x in s.scene()['bend_edges'] if x['kind'] == 'libero' and x['face'] == 'SM1/sopra'
                 and abs(x['length'] - lato) < 25), key=lambda x: x['length'])
        r = s.add_edge_flange(e['face'], e['ea'], e['eb'], {'length': '20', 'angle': '90', 'direction': 'down'})
        assert r['ok'], r.get('message')
    d = s.result.body.sheet
    assert not [f.message for f in s.result.features if not f.ok]
    assert len(d.extra_bends) == 4
    # ogni angolo: un risvolto intero e uno accorciato, niente sovrapposizioni nello sviluppo
    assert sum(b['width'] for b in d.extra_bends) < 2 * (240 + 400) - 3 * 19
    assert d.flat.area > a0 + 0.9 * 2 * (240 + 400) * 19
    # tutti e quattro dalla stessa parte (04/11: il quarto veniva al contrario, il baricentro era sceso sotto la lamiera)
    assert len({b['direction'] for b in d.extra_bends}) == 1


def test_bordi_esterni_come_prima():
    """Sul pezzo senza finestra nessun bordo libero nuovo (i bordi del contorno restano quelli di sempre)."""
    s = Service()
    assert s.new_project('lamiera', {'name': 'Piatto', 'larghezza': 300, 'profondita': 200, 'spessore': 2,
                                     'raggio': 1, 'k': 0.4})['ok']
    assert not [e for e in s.scene()['bend_edges'] if e['kind'] == 'libero']
