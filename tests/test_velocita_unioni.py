"""03/11, velocità: i solidi di tanti contorni (le lettere di una scritta, una fila di fori) si uniscono in una volta
sola invece che uno alla volta. Il pezzo deve venire identico: stesso volume, stesse facce, stessi nomi."""
import pytest
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from cad_engine.features import base, extrude, hole, revolve
from cad_engine.features.base import volume
from cad_engine.topology.naming import _faces_of

from conftest import plate


def _una_alla_volta(parti):
    """Come si faceva prima del 03/11 (il riferimento)."""
    tool = None
    for part in parti:
        if tool is None:
            tool = part
        else:
            fu = BRepAlgoAPI_Fuse(tool.shape, part.shape)
            fu.Build()
            tool = tool.after(fu, fu.Shape(), part)
    return tool


def _area(f):
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(f, g)
    return g.Mass()


def _firma(doc):
    from cad_engine import document
    document._CACHE_GLOBALE.clear()            # se no il secondo pezzo uguale verrebbe dalla memoria, senza rifarlo
    res = doc.rebuild()
    assert res.cached == 0
    assert res.ok, [f.message for f in res.errors]
    b = res.body
    nomi = sorted((k, len(v), round(sum(_area(f) for f in v), 6)) for k, v in b.names.items())
    return round(volume(b.shape), 6), len(_faces_of(b.shape)), nomi


def _prima_e_dopo(costruisci, monkeypatch):
    dopo = _firma(costruisci())
    for m in (extrude, hole, revolve):
        monkeypatch.setattr(m, 'unisci_parti', _una_alla_volta)
    prima = _firma(costruisci())
    return prima, dopo


def test_scritta_di_tanti_contorni_uguale_a_prima(monkeypatch):
    def costruisci():
        doc, *_ = plate()
        sk = doc.add_sketch({'face': 'E1/fine'}, 'Tante tasche')
        for i in range(12):                        # 12 «lettere» staccate, più una «O» (contorno col buco)
            x = 20 + i * 20
            sk.polyline([(x, 20), (x + 10, 20), (x + 10, 40), (x, 40)], closed=True)
        sk.polyline([(20, 140), (60, 140), (60, 180), (20, 180)], closed=True)
        sk.polyline([(30, 150), (50, 150), (50, 170), (30, 170)], closed=True)
        doc.add_feature('extrude', 'Scritta', sketch=sk.id, distance=2, operation='cut', reverse=True)
        return doc
    prima, dopo = _prima_e_dopo(costruisci, monkeypatch)
    assert dopo == prima
    assert dopo[1] > 60


def test_fila_di_fori_uguale_a_prima(monkeypatch):
    def costruisci():
        doc, *_ = plate()
        sk = doc.add_sketch({'face': 'E1/fine'}, 'Fori')
        punti = [sk.point(20 + 25 * i, 25) for i in range(10)] + [sk.point(20 + 25 * i, 175) for i in range(10)]
        doc.add_feature('hole', 'Fila di fori', sketch=sk.id, points=punti, diameter=9, through=True)
        return doc
    prima, dopo = _prima_e_dopo(costruisci, monkeypatch)
    assert dopo == prima
    assert sum(1 for k, *_ in dopo[2] if '/foro/' in k) == 20


def test_pezzo_nuovo_da_contorni_che_si_toccano(monkeypatch):
    def costruisci():
        from cad_engine.document import Document
        doc = Document('Due rettangoli', 'S235')
        sk = doc.add_sketch('XY')
        sk.polyline([(0, 0), (100, 0), (100, 50), (0, 50)], closed=True)
        sk.polyline([(200, 0), (260, 0), (260, 40), (200, 40)], closed=True)
        doc.add_feature('extrude', 'Base', sketch=sk.id, distance=8, operation='new')
        return doc
    prima, dopo = _prima_e_dopo(costruisci, monkeypatch)
    assert dopo == prima


def test_controllo_del_solido_dice_lo_stesso():
    from OCP.BRepCheck import BRepCheck_Analyzer
    doc, *_ = plate()
    b = doc.rebuild().body
    assert BRepCheck_Analyzer(b.shape, True, True).IsValid() == BRepCheck_Analyzer(b.shape).IsValid() is True
    assert base.unisci_parti([b]) is b


def test_marcatura_dentro_dello_sviluppo_come_prima():
    """Il controllo «il testo sta sulla lamiera» col classificatore preparato una volta: stesse risposte di is_inside,
    anche sui bordi, nei fori e appena fuori."""
    import build123d as bd
    from cad_engine.sheetmetal import _dentro_dello_sviluppo
    lastra = bd.Face(bd.Wire.make_polygon([(0, 0, 0), (100, 0, 0), (100, 60, 0), (0, 60, 0)], close=True))
    foro = bd.Face(bd.Wire.make_circle(10, bd.Plane.XY.moved(bd.Location((50, 30, 0)))))
    flat = lastra - foro
    flat = flat.faces()[0]
    dentro = _dentro_dello_sviluppo(flat)
    punti = [(x, y, z) for x in (-0.1, -0.04, 0, 0.03, 10, 40, 49.99, 50, 60, 60.04, 99.97, 100, 100.06)
             for y in (-0.06, 0, 0.02, 20, 30, 39.97, 40.05, 59.99, 60, 60.2) for z in (0, 0.03, 0.08)]
    attese = [flat.is_inside(bd.Vector(*q), tolerance=0.05) for q in punti]
    assert [dentro(q) for q in punti] == attese
    assert any(attese) and not all(attese)


def test_storia_senza_copie_stesso_testo():
    """La storia salva il progetto come testo a ogni passo: senza le copie il testo è lo stesso, e il progetto non
    cambia a farlo."""
    import json
    from cad_engine.commands import History
    doc, sk, *_ = plate()
    sk2 = doc.add_sketch({'face': 'E1/fine'}, 'Fori')
    sk2.circle((40, 40), 5)
    doc.set_parameter('passo', '20')
    prima = json.dumps(doc.to_dict())
    assert json.dumps(doc.to_dict(copia=False)) == prima
    assert sk.to_dict(copia=False) == sk.to_dict()
    h = History(doc)
    with h.change('quota'):
        doc.set_parameter('larghezza', 320)
    assert h.done[-1].before == prima
    assert json.dumps(doc.to_dict()) == h.done[-1].after
    h.undo()
    assert json.dumps(doc.to_dict()) == prima


def _svasature_una_alla_volta(ns, ss, prof, ritorni, t, fid, fori=None):
    """Le svasature come si facevano prima del 03/11 (un taglio per cono): il riferimento."""
    import math
    import build123d as bd
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    import cad_engine.sheetmetal as SM
    if fori is None:
        fori = [(cerchio, spec, ritorni[i][1]) for i, cerchio, spec in SM._hole_specs(ss, prof)]
    for cerchio, spec, verso in fori:
        if spec.get('tipo') != 'svasato':
            continue
        d, D = 2 * cerchio.radius, float(spec.get('D', 0))
        ang = math.radians(float(spec.get('angolo', 90)))
        if D <= d or (D - d) / 2 / math.tan(ang / 2) > t + 1e-6:
            continue
        h = (D - d) / 2 / math.tan(ang / 2)
        asse = bd.Vector(*verso).normalized()
        c = cerchio.arc_center
        e = 0.05
        cono = bd.Solid.make_cone(D / 2 + e * math.tan(ang / 2), d / 2, h + e, plane=bd.Plane(origin=c - asse * e, z_dir=asse))
        op = BRepAlgoAPI_Cut(ns.shape, cono.wrapped)
        sheet = ns.sheet
        ns = ns.after(op, op.Shape())
        ns.sheet = sheet
        for f in ns.senza_nome():
            ns.names.setdefault(f'{fid}/svasatura', []).append(f)
    return ns


def test_tante_svasature_in_un_taglio_uguale_a_prima(monkeypatch):
    """Le svasature (32 sul porta punte) in un taglio solo: stesso pezzo, stesse facce e stessi nomi."""
    import os
    import tempfile
    os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())
    import cad_engine.sheetmetal as SM
    from app.service import Service
    from cad_engine.document import Document
    s = Service()
    assert s.new_project('lamiera', {'name': 'P', 'larghezza': 300, 'profondita': 120, 'spessore': 4, 'raggio': 1, 'k': 0.4})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    for x in range(30, 290, 30):
        for y in (35, 85):
            assert s.sketch_add_circle(sid, [x, y], 3)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    cerchi = [k for k, e in s.doc.sketch(sid).entities.items() if e['kind'] == 'circle']
    assert s.sketch_hole_type(sid, cerchi, {'tipo': 'svasato', 'D': '12', 'angolo': '90'})['ok']
    assert s.state()['errors'] == []
    dopo = _firma(Document.from_dict(s.doc.to_dict()))
    monkeypatch.setattr(SM, '_countersinks', _svasature_una_alla_volta)
    prima = _firma(Document.from_dict(s.doc.to_dict()))
    assert dopo == prima
    assert sum(n for k, n, _ in dopo[2] if k.endswith('/svasatura')) >= 18


def test_quote_sul_pezzo_ricordate_stessi_numeri():
    """Le posizioni delle quote (da sketch a mondo) ricordate tra una modifica e l'altra: stessi numeri di
    from_local_coords, e cambiando la quota si spostano davvero."""
    import os
    import tempfile
    os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())
    from app import service as SV
    from app.service import Service
    from cad_engine.sketch.profile import PLANES
    s = Service()
    assert s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 3, 'raggio': 1, 'k': 0.4})['ok']
    SV._PUNTI_QUOTE.clear()
    freddo = s._dimensions()
    caldo = s._dimensions()
    assert freddo == caldo and freddo
    pl = PLANES['XY']
    for p in [(0, 0), (12.5, -3.25), (200, 100)]:
        g = pl.from_local_coords(p)
        assert SV._nel_mondo(pl, p) == [g.X, g.Y, g.Z] == SV._nel_mondo(pl, p)
    d = next(x for x in freddo if x['type'] == 'length' and not x.get('driven'))
    assert s.set_dimension(d['sketch'], d['dim'], d['value'] + 50)['ok']
    nuove = {x['dim']: x for x in s._dimensions()}
    assert nuove[d['dim']]['value'] == pytest.approx(d['value'] + 50)
    assert nuove[d['dim']]['a'] != d['a'] or nuove[d['dim']]['b'] != d['b']


def test_filetti_nel_3d_stesse_facce_di_prima():
    """I fori filettati nel 3D: le facce cilindriche si cercano una volta per tutti i fori; stesse facce di prima."""
    import os
    import tempfile
    os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    from app.service import Service
    s = Service()
    assert s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 4, 'raggio': 1, 'k': 0.4})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    for x in (30, 70, 110, 150):
        assert s.sketch_add_circle(sid, [x, 50], 2.5)['ok']
    assert s.sketch_add_circle(sid, [180, 50], 4)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    cerchi = [k for k, e in s.doc.sketch(sid).entities.items() if e['kind'] == 'circle' and abs(e['r'] - 2.5) < 1e-6]
    assert s.sketch_hole_type(sid, cerchi, {'tipo': 'filettato', 'M': 'M6'})['ok']
    fil = s._filettature()
    assert len(fil) == 4

    def come_prima(q, rr):                 # una faccia alla volta, come prima del 03/11
        out = []
        for i, f in enumerate(_faces_of(s.result.body.shape)):
            su = BRepAdaptor_Surface(f)
            if su.GetType() != GeomAbs_Cylinder or abs(su.Cylinder().Radius() - rr) > 1e-3:
                continue
            o, d = su.Cylinder().Axis().Location(), su.Cylinder().Axis().Direction()
            v = (q[0] - o.X(), q[1] - o.Y(), q[2] - o.Z())
            lungo = v[0] * d.X() + v[1] * d.Y() + v[2] * d.Z()
            if max(0.0, v[0] ** 2 + v[1] ** 2 + v[2] ** 2 - lungo ** 2) < 1e-6:
                out.append(i)
        return out
    for t in fil:
        assert t['faces'] and t['faces'] == come_prima(t['c'], t['r0'])
