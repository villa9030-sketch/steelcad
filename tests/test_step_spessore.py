"""Lo spessore di una lastra piana da STEP si cambia (28/10: «ma non è modificabile»): la faccia di sotto con i fori
resta al suo posto (nell'assieme non si sposta niente), lo spessore cresce verso il materiale."""
import build123d as bd
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder

from app.service import Service
from cad_engine.topology.naming import _faces_of


def _step(tmp_path, forma, nome):
    f = tmp_path / f'{nome}.step'
    bd.export_step(forma, str(f))
    return f


def _piastra(tmp_path):
    p = bd.Box(200, 100, 3, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
    for x in (20, 180):
        p -= bd.Cylinder(4.5, 3, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(bd.Location((x, 50, 0)))
    return _step(tmp_path, p.moved(bd.Location((0, 0, 100))), 'piastra')


def test_lastra_piu_spessa(tmp_path):
    s = Service()
    assert s.import_step(str(_piastra(tmp_path)))['ok']
    sel = s.select('body')['selection']
    assert sel['step'] == {'t': 3.0, 'pieghe': 0}
    bb0 = bd.Shape.cast(s.result.body.shape).bounding_box()
    r = s.step_spessore('5')
    assert r['ok'], r.get('message')
    sh = bd.Shape.cast(s.result.body.shape)
    bb = sh.bounding_box()
    assert abs(bb.size.Z - 5) < 1e-6 and abs(bb.size.X - 200) < 1e-6
    # una delle due facce grandi è rimasta dov'era
    assert abs(bb.min.Z - bb0.min.Z) < 1e-6 or abs(bb.max.Z - bb0.max.Z) < 1e-6
    fori = [f for f in _faces_of(s.result.body.shape) if BRepAdaptor_Surface(f).GetType() == GeomAbs_Cylinder]
    assert len(fori) >= 2
    assert abs(sh.volume - (200 * 100 - 2 * 3.14159265 * 4.5 ** 2) * 5) < 1
    assert s.result.body.sheet.thickness == 5
    assert s.undo()['ok'] and abs(s.result.body.sheet.thickness - 3) < 1e-9


def test_pezzo_piegato_resta_come_il_file(tmp_path):
    a = Service()
    assert a.new_project('lamiera', {'name': 'Angolare', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})['ok']
    assert a.add_flange('SM1', 'L1', {'length': '40', 'angle': '90', 'direction': 'up', 'position': 'inside'})['ok']
    f = tmp_path / 'angolare.step'
    assert a.export_step(str(f))['ok']
    s = Service()
    assert s.import_step(str(f))['ok']
    assert s.select('body')['selection']['step']['pieghe'] == 1
    r = s.step_spessore('4')
    assert not r['ok'] and 'pieghe' in r['message']
    assert abs(s.result.body.sheet.thickness - 2) < 1e-6
