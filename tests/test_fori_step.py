"""I fori di un pezzo da STEP si svasano e si filettano (28/10): prima il clic sul foro non dava niente, perché non
c'era un cerchio disegnato dietro."""
import build123d as bd
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder

from app.service import Service
from cad_engine.topology.naming import _faces_of


def _piastra_step(tmp_path):
    p = bd.Box(200, 100, 3, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
    for x in (20, 100, 180):
        p -= bd.Cylinder(4.5, 3, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(bd.Location((x, 50, 0)))
    f = tmp_path / 'piastra.step'
    bd.export_step(p, str(f))
    return f


def _primo_foro(s):
    return next(k for k, f in enumerate(_faces_of(s.result.body.shape)) if BRepAdaptor_Surface(f).GetType() == GeomAbs_Cylinder)


def _coni(s):
    return sum(1 for f in _faces_of(s.result.body.shape) if BRepAdaptor_Surface(f).GetType() == GeomAbs_Cone)


def test_svasa_i_fori_dello_step(tmp_path):
    s = Service()
    assert s.import_step(str(_piastra_step(tmp_path)))['ok']
    fo = s.select('body', _primo_foro(s))['selection']['foro']
    assert fo['importato'] and abs(fo['d'] - 9) < 1e-6 and len(fo['uguali']) == 3
    r = s.hole_adopt(fo['faccia'], [fo['centri'][k] for k in fo['uguali']], fo['d'], {'tipo': 'svasato', 'D': '14', 'angolo': '90'})
    assert r['ok'], r.get('message')
    assert _coni(s) == 3
    # ora è un foro di Radius come gli altri: si riconosce dal suo cerchio, col tipo
    fo2 = s.select('body', _primo_foro(s))['selection']['foro']
    assert not fo2.get('importato') and fo2['hole']['tipo'] == 'svasato' and len(fo2['uguali']) == 3


def test_svasatura_impossibile_lascia_il_pezzo_com_era(tmp_path):
    s = Service()
    assert s.import_step(str(_piastra_step(tmp_path)))['ok']
    prima = len(s.doc.features)
    fo = s.select('body', _primo_foro(s))['selection']['foro']
    r = s.hole_adopt(fo['faccia'], [fo['centri'][fo['cerchio']]], fo['d'], {'tipo': 'svasato', 'D': '20', 'angolo': '90'})
    assert not r['ok'] and 'spessore' in r['message']
    assert len(s.doc.features) == prima and _coni(s) == 0


def test_solo_un_foro(tmp_path):
    s = Service()
    assert s.import_step(str(_piastra_step(tmp_path)))['ok']
    fo = s.select('body', _primo_foro(s))['selection']['foro']
    assert s.hole_adopt(fo['faccia'], [fo['centri'][fo['cerchio']]], fo['d'], {'tipo': 'filettato', 'M': 'M12'})['ok']
    assert _coni(s) == 0


def test_il_foro_dello_step_puo_solo_allargarsi(tmp_path):
    """29/10: M10 su un foro Ø9 vuole un preforo Ø8,5: il materiale non torna, quindi si rifiuta col perché; la scheda
    propone solo i filetti che ci stanno."""
    s = Service()
    assert s.import_step(str(_piastra_step(tmp_path)))['ok']
    fo = s.select('body', _primo_foro(s))['selection']['foro']
    assert fo['min_d'] == 9 and fo['filetti_ok'][0] == 'M12'
    prima = len(s.doc.features)
    r = s.hole_adopt(fo['faccia'], [fo['centri'][fo['cerchio']]], fo['d'], {'tipo': 'filettato', 'M': 'M10'})
    assert not r['ok'] and 'solo diventare più grande' in r['message'] and len(s.doc.features) == prima
    assert s.hole_adopt(fo['faccia'], [fo['centri'][k] for k in fo['uguali']], fo['d'], None)['ok']
    fo2 = s.select('body', _primo_foro(s))['selection']['foro']
    assert fo2['min_d'] == 9 and not fo2.get('importato')
    r = s.sketch_hole_diameter(fo2['sketch'], [fo2['cerchio']], '8')
    assert not r['ok'] and 'STEP' in r['message']
    assert s.sketch_hole_diameter(fo2['sketch'], [fo2['cerchio']], '11')['ok']


def test_faccia_del_foro_dal_centro(tmp_path):
    """Dopo una modifica il foro si ritrova dal suo centro (i nomi delle pareti dei fori non bastano)."""
    s = Service()
    assert s.import_step(str(_piastra_step(tmp_path)))['ok']
    fo = s.select('body', _primo_foro(s))['selection']['foro']
    c = fo['centri'][fo['cerchio']]
    assert s.hole_adopt(fo['faccia'], [fo['centri'][k] for k in fo['uguali']], fo['d'], {'tipo': 'filettato', 'M': 'M12'})['ok']
    r = s.faccia_del_foro(c)
    assert r['ok']
    fo2 = s.select('body', r['face'])['selection']['foro']
    assert fo2['hole']['tipo'] == 'filettato' and abs(fo2['d'] - 10.2) < 1e-6
    assert abs(fo2['centri'][fo2['cerchio']][0] - c[0]) < 1e-3
