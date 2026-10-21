"""Un taglio su una faccia che arriva proprio al bordo della piega continua attraverso la piega (21/10, il cassone:
scasso sull'orlo, rimaneva la striscia curva tra orlo e flangia che non si poteva tagliare)."""
import math
import os
import tempfile

import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402

T, R, K = 2, 1, 0.21
BA = math.pi / 2 * (R + K * T)


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


def cassone():
    s = Service()
    assert s.new_project('lamiera', {'name': 'C', 'larghezza': 200, 'profondita': 100, 'spessore': T, 'raggio': R, 'k': K})['ok']
    assert s.add_flange('SM1', 'L1', {'length': '30'})['ok']
    r = s.add_flange('SM1', None, {'length': '20'}, 'FL1')
    assert r['ok'], r
    return s


def area(s):
    return s.state()['sheet']['data']['flat_area']


# l'orlo è alto 17 (0…17): sulla faccia esterna la piega sta a y 0, su quella interna a y 17
@pytest.mark.parametrize('faccia,y0,y1,piega', [
    ('SM1/FL2/esterno', 0, 10, True), ('SM1/FL2/esterno', 7, 17, False),
    ('SM1/FL2/interno', 7, 17, True), ('SM1/FL2/interno', 0, 10, False),
])
def test_scasso_su_flangia_e_orlo_porta_via_anche_la_piega_in_mezzo(faccia, y0, y1, piega):
    # prima la flangia tagliata per tutta l'altezza, poi l'orlo dal lato della piega: la striscia curva tra le due
    # resterebbe appesa, si toglie. Dal lato della punta libera si toglie solo quello che è disegnato
    s = cassone()
    sid = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    assert s.sketch_add_rectangle(sid, [85, 0], [115, 24])['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    prima = area(s)
    sid = s.sketch_on_face(faccia)['sketch']
    assert s.sketch_add_rectangle(sid, [85, y0], [115, y1])['ok']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r
    assert s.state()['errors'] == []
    assert prima - area(s) == pytest.approx(30 * (10 + (BA if piega else 0)), abs=0.5)


def test_scasso_sull_orlo_con_la_flangia_intera_lascia_la_piega():
    """Dall'altra parte la flangia c'è: si accorcia l'orlo fino alla piega, la piega resta."""
    s = cassone()
    prima = area(s)
    sid = s.sketch_on_face('SM1/FL2/esterno')['sketch']
    assert s.sketch_add_rectangle(sid, [85, 0], [115, 10])['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    assert prima - area(s) == pytest.approx(30 * 10, abs=0.2)


def test_taglio_lontano_dalla_piega_resta_com_e():
    s = cassone()
    prima = area(s)
    sid = s.sketch_on_face('SM1/FL2/esterno')['sketch']
    v = s.sketch_view(sid)['sketch']
    xs = [p['xy'][0] for p in v['points'] if p['id'] != 'O']
    ys = sorted(p['xy'][1] for p in v['points'] if p['id'] != 'O')
    ym = (ys[0] + ys[-1]) / 2
    assert s.sketch_add_rectangle(sid, [min(xs) + 20, ym - 3], [min(xs) + 50, ym + 3])['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    assert prima - area(s) == pytest.approx(30 * 6, abs=0.2)
