"""Gli errori con la soluzione dentro (28/10): il messaggio propone il valore giusto, e rifacendo la stessa chiamata con
quel valore funziona."""
import build123d as bd
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder

from app.service import Service
from cad_engine.topology.naming import _faces_of


def test_flangia_troppo_corta():
    s = Service()
    assert s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 3, 'raggio': 3, 'k': 0.4})['ok']
    campi = {'length': '2', 'angle': '90', 'direction': 'up', 'position': 'inside'}
    r = s.add_flange('SM1', 'L1', campi)
    assert not r['ok'] and r.get('soluzioni'), r
    sol = r['soluzioni'][0]
    assert 'length' in sol['cambia']
    r2 = s.add_flange('SM1', 'L1', {**campi, **sol['cambia']})
    assert r2['ok'], r2.get('message')


def test_svasatura_troppo_profonda(tmp_path):
    p = bd.Box(200, 100, 3, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
    p -= bd.Cylinder(4.5, 3, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(bd.Location((50, 50, 0)))
    f = tmp_path / 'p.step'
    bd.export_step(p, str(f))
    s = Service()
    assert s.import_step(str(f))['ok']
    k = next(i for i, x in enumerate(_faces_of(s.result.body.shape)) if BRepAdaptor_Surface(x).GetType() == GeomAbs_Cylinder)
    fo = s.select('body', k)['selection']['foro']
    spec = {'tipo': 'svasato', 'D': '20', 'angolo': '90'}
    r = s.hole_adopt(fo['faccia'], [fo['centri'][fo['cerchio']]], fo['d'], spec)
    assert not r['ok'] and r.get('soluzioni'), r
    assert '[foro' in r['message']           # il diametro per la soluzione (l'interfaccia non lo mostra)
    sol = r['soluzioni'][0]
    assert float(sol['cambia']['D']) <= 9 + 2 * 3 + 1e-9   # a 90°: Ø foro + 2 × spessore
    r2 = s.hole_adopt(fo['faccia'], [fo['centri'][fo['cerchio']]], fo['d'], {**spec, **sol['cambia']})
    assert r2['ok'], r2.get('message')
