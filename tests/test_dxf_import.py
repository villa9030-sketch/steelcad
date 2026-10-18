"""Import di sviluppi da DXF: contorni, fori, scassi sugli angoli, linee di piega → flange, sviluppo uguale al disegno."""
import math

import build123d as bd
import ezdxf
import pytest

from cad_engine.importers import dxf_import as I

T, R, K = 1.5, 1.5, 0.4


def _scrivi(tmp_path, nome, fn, unita=4):
    d = ezdxf.new()
    d.header['$INSUNITS'] = unita
    for ly in ('TAGLIO', 'PIEGA', 'TESTO'):
        d.layers.add(ly)
    fn(d.modelspace())
    p = tmp_path / nome
    d.saveas(p)
    return p


def _profilo_c(msp):
    """C 600 × 170 sviluppato: righe di piega a 15, 55, 115, 155; tre fori Ø8 sull'anima."""
    msp.add_lwpolyline([(0, 0), (600, 0), (600, 170), (0, 170)], close=True, dxfattribs={'layer': 'TAGLIO'})
    for x in (50, 300, 550):
        msp.add_circle((x, 85), 4, dxfattribs={'layer': 'TAGLIO'})
    for y in (15, 55, 115, 155):
        msp.add_line((0, y), (600, y), dxfattribs={'layer': 'PIEGA'})
    msp.add_line((300, 70), (300, 100), dxfattribs={'layer': 'PIEGA'})          # asse di un foro: non è una piega
    msp.add_text('S235 sp 1,5', dxfattribs={'layer': 'TESTO'})


def _vaschetta(msp):
    """Pannello 440 × 290 con quattro scassi 20 × 20 disegnati come quadrati sugli angoli, pieghe a 20 dal bordo."""
    msp.add_lwpolyline([(0, 0), (440, 0), (440, 290), (0, 290)], close=True, dxfattribs={'layer': 'TAGLIO'})
    for x, y in ((0, 0), (420, 0), (0, 270), (420, 270)):
        msp.add_lwpolyline([(x, y), (x + 20, y), (x + 20, y + 20), (x, y + 20)], close=True, dxfattribs={'layer': 'TAGLIO'})
    for a, b in (((20, 20), (20, 270)), ((420, 20), (420, 270)), ((20, 20), (420, 20)), ((20, 270), (420, 270))):
        msp.add_line(a, b, dxfattribs={'layer': 'PIEGA'})


def test_lettura_contorni_e_indizi(tmp_path):
    an = I.leggi(_scrivi(tmp_path, 'c.dxf', _profilo_c))
    g = an.giri[an.scelto]
    assert abs(g.area - 600 * 170) < 1
    assert len(I.tagli(an, an.scelto)) == 3
    assert len(an.pieghe) == 5 and len(I.pieghe_utili(an, an.scelto)) == 4      # l'asse del foro resta fuori
    assert an.spessore == 1.5 and an.materiale == 'S235'


def test_unita_dichiarate_male(tmp_path):
    """$INSUNITS = metri ma disegnato in mm: il pezzo non deve venire mille volte più grande."""
    an = I.leggi(_scrivi(tmp_path, 'm.dxf', _profilo_c, unita=6))
    assert abs(an.giri[an.scelto].area - 600 * 170) < 1


def test_profilo_c_sviluppo_uguale_al_disegno(tmp_path):
    an = I.leggi(_scrivi(tmp_path, 'c.dxf', _profilo_c))
    doc, rep = I.costruisci(an, an.scelto, T, R, K)
    assert rep['flange'] == 4 and not rep['avvisi']
    res = doc.rebuild()
    assert res.ok
    data = res.body.sheet
    piatto = 600 * 170 - 3 * math.pi * 16
    assert abs(data.flat_area - piatto) < 0.5
    assert abs(rep['area_dxf'] - piatto) < 0.5
    # flange sulla punta: la seconda e la quarta hanno una madre
    fl = doc.features[1]['flanges']
    assert sum(1 for f in fl if f.get('parent')) == 2
    s = bd.Shape.cast(res.body.shape)
    assert len(s.solids()) == 1
    # l'anima è larga quanto la distanza tra le linee di piega più (ossb − BA/2) per parte
    from cad_engine.sheetmetal import bend_values
    b = bend_values(90, R, T, 'k', K)
    d = b.ossb - b.ba / 2
    h, w, lung = sorted(s.bounding_box().size)
    assert abs(lung - 600) < 1e-3 and abs(w - (60 + 2 * d)) < 1e-3 and abs(h - (40 + 2 * d)) < 1e-3


def test_scassi_sugli_angoli(tmp_path):
    an = I.leggi(_scrivi(tmp_path, 'v.dxf', _vaschetta))
    assert len(I.tagli(an, an.scelto)) == 4
    assert len(I.pieghe_utili(an, an.scelto)) == 4
    doc, rep = I.costruisci(an, an.scelto, T, R, K, angolo=90, verso='up')
    assert rep['flange'] == 4
    assert abs(rep['area_dxf'] - (440 * 290 - 4 * 400)) < 0.5
    # agli angoli SteelCAD lascia lo scarico: manca al più qualche decina di mm² per angolo
    assert rep['area_dxf'] - rep['area_pezzo'] < 4 * 100


def test_direzione_per_piega(tmp_path):
    an = I.leggi(_scrivi(tmp_path, 'c.dxf', _profilo_c))
    pieghe = [{'angle': 90, 'direction': 'down'}, {}, {}, {}]
    doc, _ = I.costruisci(an, an.scelto, T, R, K, pieghe=pieghe)
    assert doc.rebuild().ok


def test_dati_mancanti(tmp_path):
    an = I.leggi(_scrivi(tmp_path, 'c.dxf', _profilo_c))
    with pytest.raises(I.ImportError_, match='spessore'):
        I.costruisci(an, an.scelto, None, R, K)
    with pytest.raises(I.ImportError_, match='raggio'):
        I.costruisci(an, an.scelto, T, None, K)


def test_servizio_import(tmp_path):
    from app.service import Service
    p = _scrivi(tmp_path, 'c.dxf', _profilo_c)
    svc = Service()
    r = svc.import_dxf(str(p))
    assert r['ok'] and r['giro']['pieghe'] and '<svg' in r['svg']
    x = svc.import_dxf_create(r['scelto'], {'thickness': '1,5', 'radius': '1,5', 'k': '0,4', 'material': 'S235'})
    assert x['ok'], x.get('message')
    assert 'Importato: 4 flange' in x['message']
    assert x['state']['tree']
    x = svc.import_dxf_create(r['scelto'], {'thickness': '1,5', 'radius': '', 'k': '0,4'})
    assert not x['ok'] and 'raggio' in x['message']
