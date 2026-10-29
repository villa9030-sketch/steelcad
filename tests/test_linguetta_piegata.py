"""Linguetta tagliata e piegata (29/10): taglio a U, poi la linea di piega tra le punte del taglio. Si piega solo la
linguetta; il resto resta fermo, lo sviluppo resta quello disegnato."""
import build123d as bd
import pytest

from app.service import Service

# la U: gambe larghe 3, la linguetta 80 × 50 appesa alla linea y = 80
U = [[57, 80], [57, 27], [143, 27], [143, 80], [140, 80], [140, 30], [60, 30], [60, 80]]
AREA_U = 200 * 100 - (86 * 53 - 80 * 50)


def _lamiera():
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 1.5, 'raggio': 1.5, 'k': 0.4})
    sid = s.sketch_on_flat('SM1')['sketch']
    assert s.sketch_add_polyline(sid, U, True)['ok']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')
    assert s.result.body.sheet.flat_area == pytest.approx(AREA_U, rel=1e-9)
    return s


def _linea(s, a, b, ang=90, verso='up', flip=False):
    sid = s.sketch_on_flat('SM1')['sketch']
    assert s.sketch_add_polyline(sid, [a, b], False)['ok']
    return s.sheet_fold(sid, ang, verso, flip)


@pytest.mark.parametrize('ang,verso', [(90, 'up'), (45, 'up'), (90, 'down')])
def test_linguetta_dal_taglio_a_u(ang, verso):
    s = _lamiera()
    v0 = bd.Solid(s.result.body.shape).volume
    r = _linea(s, [57, 80], [143, 80], ang, verso)
    assert r['ok'], r.get('message')
    assert not s.state()['errors']
    f = s.doc.features[-1]
    assert f['type'] == 'sheet_tab_fold'
    b = s.result.body
    assert len(bd.Shape.cast(b.shape).solids()) == 1
    assert b.sheet.flat_area == pytest.approx(AREA_U, rel=1e-6)          # lo sviluppo resta quello disegnato
    assert bd.Shape.cast(b.shape).volume == pytest.approx(v0, rel=2e-3)  # la lamiera è la stessa, solo piegata
    bb = bd.Shape.cast(b.shape).bounding_box()
    if verso == 'up':
        assert bb.max.Z > 30
    else:
        assert bb.min.Z < -30
    assert any(str(t).startswith(f['id']) for _a, _b, t in b.sheet.bend_lines)   # la linea di piega nel DXF


def test_dalla_faccia_di_sopra_e_dxf(tmp_path):
    """Come l'ha fatta Stefano: U e linea disegnate sulla faccia di sopra; poi il DXF di sviluppo si esporta."""
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 1.5, 'raggio': 1.5, 'k': 0.4})
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_polyline(sid, U, True)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_polyline(sid, [[57, 80], [143, 80]], False)['ok']
    r = s.sheet_fold(sid, 90, 'up')
    assert r['ok'], r.get('message')
    assert s.doc.features[-1]['type'] == 'sheet_tab_fold' and not s.state()['errors']
    assert s.result.body.sheet.flat_area == pytest.approx(AREA_U, rel=1e-6)
    r = s.export_dxf(str(tmp_path / 'p.dxf'))
    assert r['ok'], r.get('message')


def test_linguetta_che_si_stringe():
    """La punta più stretta della linea (lati inclinati): quello che la piega ha in più si toglie, lo sviluppo resta."""
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 1.5, 'raggio': 1.5, 'k': 0.4})
    sid = s.sketch_on_flat('SM1')['sketch']
    assert s.sketch_add_polyline(sid, [[57, 80], [67, 27], [133, 27], [143, 80], [140, 80], [130, 30], [70, 30], [60, 80]], True)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    area = s.result.body.sheet.flat_area
    r = _linea(s, [57, 80], [143, 80])
    assert r['ok'], r.get('message')
    assert not s.state()['errors']
    assert s.result.body.sheet.flat_area == pytest.approx(area, rel=1e-6)
    assert len(bd.Shape.cast(s.result.body.shape).solids()) == 1
    assert bd.Shape.cast(s.result.body.shape).volume == pytest.approx(area * 1.5, rel=3e-3)    # rifilata anche nel 3D


@pytest.mark.parametrize('verso2', ['down', 'up'])
def test_seconda_piega_sulla_linguetta(verso2):
    """La maniglia (29/10): dopo la prima piega della linguetta una linea a metà linguetta la piega ancora; e una
    terza. Lo sviluppo resta quello disegnato, il pezzo resta uno, la linguetta resta una lavorazione sola."""
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 1.5, 'raggio': 1.5, 'k': 0.4})
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_polyline(sid, U, True)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_polyline(sid, [[57, 80], [143, 80]], False)['ok']
    assert s.sheet_fold(sid, 10, 'down')['ok']
    n = len(s.doc.features)
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_polyline(sid, [[57, 60], [143, 60]], False)['ok']
    r = s.sheet_fold(sid, 30, verso2)
    assert r['ok'], r.get('message')
    assert not s.state()['errors'] and len(s.doc.features) == n
    lp = s.doc.features[-1]
    assert lp['type'] == 'sheet_tab_fold' and len(lp['altre']) == 1
    b = s.result.body
    assert len(bd.Shape.cast(b.shape).solids()) == 1
    assert b.sheet.flat_area == pytest.approx(AREA_U, rel=1e-6)
    assert sum(1 for _a, _b, t in b.sheet.bend_lines if str(t).startswith('LP1')) == 2
    r = _linea(s, [57, 45], [143, 45], 20, 'up')                       # e una terza
    assert r['ok'], r.get('message')
    assert not s.state()['errors'] and len(s.doc.features[-1]['altre']) == 2
    assert s.result.body.sheet.flat_area == pytest.approx(AREA_U, rel=1e-6)
    assert s.undo()['ok']                                               # Annulla: torna la linea, via la terza piega
    lp = next(f for f in s.doc.features if not hasattr(f, 'entities') and f.get('type') == 'sheet_tab_fold')
    assert len(lp['altre']) == 1


def test_prima_a_meta_poi_alla_radice():
    """Come l'ha fatta Stefano (29/10): prima la piega a metà linguetta, poi quella dove finisce il taglio. Quella alla
    radice diventa la prima; SU / GIÙ nel DXF come scelti."""
    s = _lamiera()
    assert _linea(s, [57, 55], [143, 55], 10, 'down')['ok']          # a metà: si piega solo la punta
    r = _linea(s, [57, 80], [143, 80], 30, 'down')                   # alla radice
    assert r['ok'], r.get('message')
    assert not s.state()['errors']
    lp = s.doc.features[-1]
    assert lp['type'] == 'sheet_tab_fold' and lp['a'] == [57, 80] and lp['angle'] == 30
    assert [x['angle'] for x in lp['altre']] == [10]
    b = s.result.body
    assert b.sheet.flat_area == pytest.approx(AREA_U, rel=1e-6)
    assert sorted(t for _a, _b, t in b.sheet.bend_lines if str(t).startswith('LP1')) == ['LP1 GIÙ 30° R1,5', 'LP1.2 GIÙ 10° R1,5']
    assert bd.Shape.cast(b.shape).bounding_box().min.Z < -20


def test_piega_normale_resta_normale():
    """Una linea da bordo a bordo resta la piega di sempre (non una linguetta)."""
    s = _lamiera()
    r = _linea(s, [180, -5], [180, 105])
    assert r['ok'], r.get('message')
    assert s._sheet_def('SM1').get('folds')
    assert s.doc.features[-1]['type'] != 'sheet_tab_fold'


def test_linea_che_non_chiude():
    """Una linea a metà della linguetta, che non tocca il taglio da tutte e due le parti: si dice cosa fare."""
    s = _lamiera()
    r = _linea(s, [70, 60], [100, 60])
    assert not r['ok'] and 'attraversa' in r['message']
