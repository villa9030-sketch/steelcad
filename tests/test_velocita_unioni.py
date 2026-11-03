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
    res = doc.rebuild()
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
