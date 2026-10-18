"""Triangoli e linee per il viewer. Solo per vedere: la geometria vera resta BREP.

Ogni oggetto ha posizioni, indici, e le "fasce" di triangoli che appartengono
a ogni faccia (con il nome stabile, se c'è): così il clic su un triangolo dice
quale faccia hai preso.
"""
from __future__ import annotations

import build123d as bd
from OCP.BRep import BRep_Tool
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopAbs import TopAbs_REVERSED
from OCP.TopLoc import TopLoc_Location

from .topology.naming import _edges_of, _faces_of


def tessellate(shape, names: dict | None = None, *, linear: float = 0.15, angular: float = 0.25) -> dict:
    BRepMesh_IncrementalMesh(shape, linear, False, angular, True)
    pos: list[float] = []
    idx: list[int] = []
    faces = []
    nome_di = {}
    for nome, fs in (names or {}).items():
        for f in fs:
            nome_di.setdefault(f, nome)
    for k, f in enumerate(_faces_of(shape)):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is None:
            continue
        trsf = loc.Transformation()
        base = len(pos) // 3
        for i in range(1, tri.NbNodes() + 1):
            p = tri.Node(i).Transformed(trsf)
            pos.extend((p.X(), p.Y(), p.Z()))
        rev = f.Orientation() == TopAbs_REVERSED
        start = len(idx)
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            if rev:
                b, c = c, b
            idx.extend((base + a - 1, base + b - 1, base + c - 1))
        nome = next((n for g, n in nome_di.items() if g.IsSame(f)), None)
        faces.append({'name': nome, 'index': k, 'start': start, 'count': len(idx) - start})
    edges = []
    for e in _edges_of(shape):
        if BRep_Tool.Degenerated_s(e):
            continue                        # lo spigolo "a punto" del polo di una sfera: niente da disegnare
        be = bd.Edge(e)
        if be.length < 1e-9:
            continue
        n = 2 if be.geom_type == bd.GeomType.LINE else max(8, min(64, int(be.length / 2)))
        try:
            pts = be.positions([i / (n - 1) for i in range(n)])
        except Exception:  # noqa: BLE001 - uno spigolo strano non deve fermare la vista
            continue
        edges.append([round(c, 4) for p in pts for c in (p.X, p.Y, p.Z)])
    return {'positions': [round(v, 4) for v in pos], 'indices': idx, 'faces': faces, 'edges': edges}
