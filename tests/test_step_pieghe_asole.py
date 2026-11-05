"""STEP di lamiere con asole attraverso le pieghe, angoli chiusi, sponde divise, bordi storti o curvi (05/11, idee
da SolidCraft «sheet.convert»). I pezzi si fanno in Radius (taglio sullo sviluppo, flange, angoli chiusi, piega su
linea), si esportano in STEP e si riaprono: lo sviluppo dallo STEP deve tornare con quello di Radius.
I pezzi importati prima (senza il campo «sviluppo») si riaprono come erano."""
import base64
import zlib

import build123d as bd
import pytest

from app.service import Service
from cad_engine.document import Document
from cad_engine.importers.step_lamiera import leggi, spiega

K = 0.33


def _vasca(chiusi=False, fessura=0):
    s = Service()
    assert s.new_project('lamiera', {'name': 'V', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2,
                                     'k': K})['ok']
    for e in ('L1', 'L2', 'L3', 'L4'):
        assert s.add_flange('SM1', e, {'length': 40})['ok']
    if chiusi:
        fl = [f['id'] for f in s._sheet_def('SM1')['flanges']]
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
            assert s.set_corner('SM1', fl[a], fl[b], 'over', fessura)['ok']
    return s


def _asole(s, rettangoli):
    sid = s.sketch_on_flat('SM1')['sketch']
    for a, b in rettangoli:
        assert s.sketch_add_rectangle(sid, a, b)['ok']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')


def _step(s, tmp_path, nome):
    p = tmp_path / f'{nome}.step'
    assert s.export_step(str(p))['ok']
    return p


def _fori(face):
    return len(face.inner_wires())


def _importa(p, k=K):
    s = Service()
    r = s.import_step(str(p), k)
    assert r['ok'], r.get('message')
    return s, s.result.body.sheet


def test_asole_attraverso_la_piega_una_piega_sola(tmp_path):
    """Due asole attraverso la piega lunga, una attraverso quella corta: la faccia della piega arriva in 3 + 2 pezzi.
    Restano 4 pieghe, le asole tornano fori e lo sviluppo è quello di Radius."""
    v = _vasca()
    _asole(v, [([30, -10], [40, 8]), ([70, -10], [80, 8]), ([292, 55], [310, 65])])
    vero = v.result.body.sheet
    assert _fori(vero.flat) == 3
    s, d = _importa(_step(v, tmp_path, 'asole'))
    assert len(d.bend_rows) == 4 and len(d.bend_lines) == 4
    assert d.flat_area == pytest.approx(vero.flat_area, abs=1.0)
    assert sorted(round(x, 1) for x in d.flat_size) == sorted(round(x, 1) for x in vero.flat_size)
    assert _fori(d.flat) == 3
    # la riga della piega è lunga quanto tutta la piega, non quanto il pezzo tra due asole
    assert sorted(round(r['length'], 3) for r in d.bend_rows) == [192, 192, 292, 292]
    r = s.export_dxf(str(tmp_path / 'asole.dxf'))
    assert r['ok'] and 'Controlli superati' in r['message']


def test_asole_vecchio_import_resta_com_era(tmp_path):
    """Un pezzo importato prima (senza «sviluppo» nel file) si riapre con lo sviluppo di prima, anche se sbagliato;
    il nuovo import ha il campo e si riapre uguale."""
    v = _vasca()
    _asole(v, [([30, -10], [40, 8]), ([70, -10], [80, 8])])
    p = _step(v, tmp_path, 'asole')
    so = leggi(p)
    vecchio, nuovo = spiega(so, k=K), spiega(so, k=K, v2=True)
    assert vecchio['flat'].area < nuovo['flat'].area - 100              # prima mancavano i pezzi di piega
    doc = Document('vecchio', 'S235')
    doc.add_feature('step_lamiera', 'Lamiera da STEP', file=p.name, k=K,
                    dati=base64.b64encode(zlib.compress(p.read_bytes(), 9)).decode('ascii'))
    from cad_engine import project_io
    project_io.save(doc, tmp_path / 'vecchio.steelcad')
    s = Service()
    assert s.open(str(tmp_path / 'vecchio.steelcad'))['ok']
    assert s.result.body.sheet.flat_area == pytest.approx(vecchio['flat'].area, abs=1e-6)
    s2, d = _importa(p)
    assert s2.doc.features[0]['sviluppo'] == 2
    assert s2.save(str(tmp_path / 'nuovo.steelcad'))['ok']
    s3 = Service()
    assert s3.open(str(tmp_path / 'nuovo.steelcad'))['ok']
    assert s3.result.body.sheet.flat_area == pytest.approx(d.flat_area, abs=1e-6)
    assert s3.result.body.sheet.flat_area == pytest.approx(nuovo['flat'].area, abs=1e-6)


def test_asola_che_finisce_dentro_la_piega(tmp_path):
    """Un'asola passante dalla base che si ferma a metà piega: la piega resta una faccia sola con una tacca. Prima la
    striscia era il trapezio tra i due spigoli e la sponda veniva storta; ora la piega si srotola con la tacca."""
    v = _vasca()
    so = bd.Shape.cast(v.result.body.shape)
    so = so.cut(bd.Box(10, 17.5, 20, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN)).moved(bd.Location((115, 2.5, -10))))
    r = spiega(so, k=0.5, v2=True)
    atteso = so.volume / r['t']                                       # K 0,5: lo sviluppo è volume / spessore
    assert r['flat'].area == pytest.approx(atteso, rel=1e-3)
    assert len(r['linee']) == 4 and len(r['flat'].inner_wires()) == 1
    # le misure fuori tutto non cambiano (prima la sponda veniva storta e lo sviluppo più largo)
    intero = spiega(bd.Shape.cast(v.result.body.shape), k=0.5, v2=True)['flat'].bounding_box().size
    bb = r['flat'].bounding_box().size
    assert (bb.X, bb.Y) == (pytest.approx(intero.X, abs=1e-6), pytest.approx(intero.Y, abs=1e-6))


@pytest.mark.parametrize('fessura', [0, 0.5])
def test_vaschetta_ad_angoli_chiusi(tmp_path, fessura):
    """Angoli chiusi: la sponda «sopra» copre la testa dell'altra. Con fessura 0 le due sponde sono unite e la faccia
    di fuori di una continua sulla testa dell'altra: prima la colonnina dell'angolo si contava due volte."""
    v = _vasca(True, fessura)
    vero = v.result.body.sheet
    s, d = _importa(_step(v, tmp_path, f'chiusa{fessura}'))
    assert len(d.bend_rows) == 4
    assert d.flat_area == pytest.approx(vero.flat_area, abs=1.0)
    assert sorted(round(x, 1) for x in d.flat_size) == sorted(round(x, 1) for x in vero.flat_size)


def test_sponda_divisa_da_un_taglio(tmp_path):
    """Un taglio che divide la sponda in due partendo dalla piega: la piega è una, le due metà della sponda vanno
    entrambe nello sviluppo (prima ne mancava una e lo STEP si rifiutava)."""
    v = _vasca()
    so = bd.Shape.cast(v.result.body.shape).cut(
        bd.Box(10, 30, 100, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN)).moved(bd.Location((145, -10, 4))))
    p = tmp_path / 'divisa.step'
    bd.export_step(so, str(p))
    s, d = _importa(p, 0.5)
    assert len(d.bend_rows) == 4
    assert d.flat_area == pytest.approx(so.volume / d.thickness, rel=1e-6)


@pytest.mark.parametrize('taglio', ['storto', 'tondo'])
def test_piega_che_attraversa_un_bordo_storto_o_curvo(tmp_path, taglio):
    """Piega su linea che attraversa un bordo storto o un arco dello sviluppo: la striscia della piega segue il bordo."""
    v = Service()
    v.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 1.5, 'raggio': 1.5, 'k': K})
    sid = v.sketch_on_flat('SM1')['sketch']
    if taglio == 'storto':
        assert v.sketch_add_polyline(sid, [[120, -1], [201, -1], [201, 60]], True)['ok']
        x = 150
    else:
        assert v.sketch_add_circle(sid, [150, 0], 30)['ok']
        x = 160
    assert v.create_from_sketch(sid, 'cut', {})['ok']
    sid = v.sketch_on_flat('SM1')['sketch']
    assert v.sketch_add_polyline(sid, [[x, -5], [x, 105]], False)['ok']
    assert v.sheet_fold(sid, 90, 'up')['ok']
    vero = v.result.body.sheet
    s, d = _importa(_step(v, tmp_path, taglio))
    assert len(d.bend_rows) == 1
    assert d.flat_area == pytest.approx(vero.flat_area, abs=0.05)
    assert sorted(round(x, 1) for x in d.flat_size) == sorted(round(x, 1) for x in vero.flat_size)


def test_elenco_assieme_con_asole(tmp_path):
    """Nell'elenco dei pezzi di uno STEP assieme la vaschetta con le asole conta 4 pieghe."""
    v = _vasca()
    _asole(v, [([30, -10], [40, 8]), ([70, -10], [80, 8])])
    a = bd.Shape.cast(v.result.body.shape)
    p = tmp_path / 'assieme.step'
    bd.export_step(bd.Compound(children=[a, a.moved(bd.Location((0, 400, 0)))]), str(p))
    r = Service().import_step(str(p), K)
    assert r['code'] == 'assieme' and [x['pieghe'] for x in r['pezzi']] == [4, 4]
