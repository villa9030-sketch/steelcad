"""Triangoli e linee per il viewer. Solo per vedere: la geometria vera resta BREP.

Ogni oggetto ha posizioni, indici, e le "fasce" di triangoli che appartengono
a ogni faccia (con il nome stabile, se c'è): così il clic su un triangolo dice
quale faccia hai preso.
"""
from __future__ import annotations

import build123d as bd
import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopAbs import TopAbs_EDGE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape

from .topology.naming import _edges_of, _faces_of


FORI_TANTI = 40          # da quanti fori in una faccia conviene l'altro algoritmo dei triangoli


def _triangola(shape, linear: float, angular: float) -> None:
    """05/11 (lamiera forata): una faccia piana con centinaia di fori, col triangolatore di sempre, va a minuti (530 fori
    6 secondi, 2000 fori più di un minuto). Con l'algoritmo Delabella la stessa faccia è un secondo. Solo per i pezzi
    con una faccia con tanti fori: gli altri restano triangolati come sempre."""
    from OCP.TopAbs import TopAbs_WIRE
    bucata = False
    for f in _faces_of(shape):
        n, ex = 0, TopExp_Explorer(f, TopAbs_WIRE)
        while ex.More() and n <= FORI_TANTI:
            n += 1
            ex.Next()
        if n > FORI_TANTI:
            bucata = True
            break
    if not bucata:
        BRepMesh_IncrementalMesh(shape, linear, False, angular, True)
        return
    from OCP.IMeshTools import IMeshTools_MeshAlgoType_Delabella, IMeshTools_Parameters
    p = IMeshTools_Parameters()
    # e i fori piccoli a 16 lati (con 0,4 il kernel ne fa 32): sono 2000, a 32 lati erano 400 mila punti da mandare
    # al 3D. I fori grandi li decide comunque la freccia (0,15 mm)
    p.Deflection, p.Angle, p.InParallel = linear, max(angular, 0.8), True
    p.MeshAlgo = IMeshTools_MeshAlgoType_Delabella
    BRepMesh_IncrementalMesh(shape, p)


def tessellate(shape, names: dict | None = None, *, linear: float = 0.15, angular: float = 0.4) -> dict:
    # angolo 0,4 rad (21/10): i fori piccoli a 16 lati invece di 25; quelli grandi li decide la freccia (0,15 mm).
    # Con 400 fori il 3D si preparava in quasi 2 secondi
    _triangola(shape, linear, angular)
    pos: list[float] = []
    idx: list[int] = []
    faces = []
    # le facce con nome in una mappa indicizzata: trovare il nome di una faccia non è più un giro su tutte
    con_nome, nomi = TopTools_IndexedMapOfShape(), []
    for nome, fs in (names or {}).items():
        for f in fs:
            if not con_nome.Contains(f):
                con_nome.Add(f)
                nomi.append(nome)
    edges, visti = [], TopTools_IndexedMapOfShape()
    for k, f in enumerate(_faces_of(shape)):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is None:
            continue
        trsf = loc.Transformation()
        base = len(pos) // 3
        nodo, piazza = tri.Node, pos.extend
        if loc.IsIdentity():                   # di solito: niente trasformazione punto per punto
            for i in range(1, tri.NbNodes() + 1):
                p = nodo(i)
                piazza((p.X(), p.Y(), p.Z()))
        else:
            for i in range(1, tri.NbNodes() + 1):
                p = nodo(i).Transformed(trsf)
                piazza((p.X(), p.Y(), p.Z()))
        rev = f.Orientation() == TopAbs_REVERSED
        start = len(idx)
        triangolo, metti, b0 = tri.Triangle, idx.extend, base - 1
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = triangolo(i).Get()
            metti((b0 + a, b0 + c, b0 + b) if rev else (b0 + a, b0 + b, b0 + c))
        i_nome = con_nome.FindIndex(f)
        nome = nomi[i_nome - 1] if i_nome else None
        faces.append({'name': nome, 'index': k, 'start': start, 'count': len(idx) - start})
        # gli spigoli della faccia: la loro spezzata è già nella triangolazione (ricalcolarli punto per punto
        # sulla curva era metà del tempo della scena)
        ex = TopExp_Explorer(f, TopAbs_EDGE)
        while ex.More():
            e = TopoDS.Edge(ex.Current())
            ex.Next()
            if visti.Contains(e) or BRep_Tool.Degenerated_s(e):
                continue
            poly = BRep_Tool.PolygonOnTriangulation_s(e, tri, loc)
            if poly is None or poly.NbNodes() < 2:
                continue
            visti.Add(e)
            nodi = poly.Nodes()
            if loc.IsIdentity():
                pts = [nodo(nodi.Value(j)) for j in range(nodi.Lower(), nodi.Upper() + 1)]
            else:
                pts = [nodo(nodi.Value(j)).Transformed(trsf) for j in range(nodi.Lower(), nodi.Upper() + 1)]
            edges.append(np.round([c for q in pts for c in (q.X(), q.Y(), q.Z())], 4).tolist())
    for e in _edges_of(shape):                  # gli spigoli rimasti fuori (senza triangolazione): sulla curva
        if visti.Contains(e) or BRep_Tool.Degenerated_s(e):
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
    # arrotondare tutto insieme: un round() per numero erano 250 mila chiamate con 400 fori
    return {'positions': np.round(np.asarray(pos, dtype=float), 4).tolist(), 'indices': idx, 'faces': faces, 'edges': edges}
