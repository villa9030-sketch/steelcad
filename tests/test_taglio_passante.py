"""Togli materiale «attraverso tutto il pezzo» (18/11, carrello di Stefano: i fori Ø9 sulla piega davanti devono passare
anche la piega dietro). Il contorno va dritto, perpendicolare alla faccia: ogni parete piana parallela che incontra
(la piega di fronte, un ritorno, la base) si taglia, anche nello sviluppo. In una piega curva o di traverso no."""
import math
from pathlib import Path

from app.service import Service
from cad_engine.features.base import volume


def _vaschetta():
    """Come il ripiano del carrello: 800×600 sp3, pieghe da 50 su tutti i lati, ritorni da 20."""
    s = Service()
    assert s.new_project('lamiera', {'name': 'Ripiano', 'larghezza': 800, 'profondita': 600, 'spessore': 3,
                                     'raggio': 1, 'k': 0.21})['ok']
    fl = {}
    for lato in ('L1', 'L2', 'L3', 'L4'):
        r = s.add_flange('SM1', lato, {'length': 50})
        assert r['ok'], r.get('message')
    sm = s.doc.feature('SM1')
    for f in [x for x in sm['flanges'] if x.get('edge')]:
        fl[f['edge']] = f['id']
        r = s.add_flange('SM1', None, {'length': 20}, parent=f['id'])
        assert r['ok'], r.get('message')
    return s, fl


def _fori(s, faccia, punti):
    sk = s.sketch_on_face(faccia)['sketch']
    for p in punti:
        assert s.sketch_add_circle(sk, p, 4.5)['ok']
    return sk


def test_fori_sulla_piega_davanti_passano_la_piega_dietro():
    s, fl = _vaschetta()
    sk = _fori(s, f'SM1/{fl["L1"]}/esterno', [(20, 25), (780, 25)])
    p = s.taglio_pareti_passanti(sk)
    assert p['ok'] and p['pareti'] == ['Piega dietro 50 su'], p
    v0 = volume(s.result.body.shape)
    r = s.create_from_sketch(sk, 'cut', {'passante': 1})
    assert r['ok'], r.get('message')
    d = s.result.body.sheet
    assert len(d.flat.inner_wires()) == 4                                # 2 davanti + 2 dietro, nel DXF
    assert abs(v0 - volume(s.result.body.shape) - 4 * math.pi * 4.5 ** 2 * 3) < 0.5
    assert 'Taglio passante' in str(s.state()['tree'])


def test_solo_questa_parete_resta_come_prima():
    s, fl = _vaschetta()
    sk = _fori(s, f'SM1/{fl["L1"]}/esterno', [(20, 25), (780, 25)])
    assert s.create_from_sketch(sk, 'cut', {})['ok']
    assert len(s.result.body.sheet.flat.inner_wires()) == 2


def test_dalla_base_anche_il_ritorno_sopra():
    s, _fl = _vaschetta()
    sk = _fori(s, 'SM1/sopra', [(300, 300)])
    assert s.taglio_pareti_passanti(sk)['pareti'] == []                   # in mezzo: niente sopra, nessuna domanda
    sk2 = _fori(s, 'SM1/sopra', [(300, 590 - 4.5 - 3)])                   # sotto il ritorno dietro (580…596)
    p = s.taglio_pareti_passanti(sk2)
    assert len(p['pareti']) == 1 and 'Piega su piega' in p['pareti'][0], p


def test_nelle_pieghe_si_toglie_tutta_la_piega():
    """18/11: come al laser, la piega toccata si toglie per tutta la larghezza; i ritorni presi di taglio restano
    (e la domanda lo dice: il laser non toglie mezzo spessore)."""
    s, fl = _vaschetta()
    sk = _fori(s, f'SM1/{fl["L1"]}/esterno', [(400, 40)])                 # arriva nelle pieghe parete-ritorno
    p = s.taglio_pareti_passanti(sk)
    assert p['pareti'] == ['Piega dietro 50 su'] and p['pieghe'] == 2 and p['resta'] == 1.5, p
    r = s.create_from_sketch(sk, 'cut', {'passante': 1})
    assert r['ok'], r.get('message')


def test_angolo_del_carrello_il_tubo_passa(tmp_path):
    """Il ripiano di Stefano: finestra 41×41 nell'angolo, sulla base. Passante: via base, raggi e ritorni; un tubo
    40×40 nell'angolo (dentro le pareti, da 3 a 43) non tocca più niente. Solo la base: il ritorno resta."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt
    dati = Path(__file__).parent / 'data' / 'carrello' / 'ripiano_angolo.steelcad'
    esiti = {}
    for passante in (0, 1):
        copia = tmp_path / f'ripiano{passante}.steelcad'
        copia.write_bytes(dati.read_bytes())
        s = Service()
        assert s.open(str(copia))['ok']
        p = s.taglio_pareti_passanti('S4')
        assert len(p['pareti']) == 2 and p['pieghe'] == 4 and p['resta'] == 0.25, p
        r = s.create_from_sketch('S4', 'cut', {'passante': 1} if passante else {})
        assert r['ok'], r.get('message')
        tubo = BRepPrimAPI_MakeBox(gp_Pnt(3, 3, -10), 40, 40, 70).Shape()
        esiti[passante] = volume(BRepAlgoAPI_Common(s.result.body.shape, tubo).Shape())
        assert len(s.result.body.sheet.flat.outer_wire().edges()) > 4
    assert esiti[1] < 1e-3 and esiti[0] > 1000, esiti
