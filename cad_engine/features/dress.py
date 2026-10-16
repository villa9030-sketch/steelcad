"""Raccordo e smusso su spigoli con nome.

Definizione:
    {"id": "F1", "type": "fillet", "edges": [{"faces": ["E1/fine", "E1/lato/L1"]}], "radius": 5}
    {"id": "K1", "type": "chamfer", "edges": [...], "distance": 2}

Gli spigoli si salvano come coppia di facce con nome (vedi TOPOLOGY_STRATEGY.md),
mai come indici. Nomi delle facce nuove: "F1/raccordo/<n>", "K1/smusso/<n>".
"""
from __future__ import annotations

import build123d as bd
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet
from OCP.TopoDS import TopoDS

from ..errors import FeatureError
from ..topology import NamedShape
from ..topology.naming import _contains, _edges_of
from ..units import cap, fmt_mm
from .base import Context, check_solid, label


def build(fdef: dict, ctx: Context) -> NamedShape:
    fid = fdef['id']
    tipo = fdef['type']
    if ctx.body is None:
        raise FeatureError(f'{cap(label(fdef))} ha bisogno di un pezzo.', feature=fid)
    refs = fdef.get('edges') or []
    if not refs:
        raise FeatureError(f'{cap(label(fdef))}: scegli almeno uno spigolo.', feature=fid)
    if tipo == 'fillet':
        val = ctx.value(fdef, 'radius', 'il raggio')
        mk = BRepFilletAPI_MakeFillet(ctx.body.shape)
        parola, sigla = 'raccordo', 'R'
    else:
        val = ctx.value(fdef, 'distance', 'la distanza')
        mk = BRepFilletAPI_MakeChamfer(ctx.body.shape)
        parola, sigla = 'smusso', ''
    if val <= 0:
        raise FeatureError(f'La misura di {label(fdef)} deve essere maggiore di zero.', feature=fid)
    per_ref = []
    for ref in refs:
        edges = ctx.body.edges(ref, feature=fid)
        per_ref.append(edges)
        for e in edges:
            mk.Add(val, e)
    try:
        mk.Build()
        ok = mk.IsDone()
    except Exception:  # noqa: BLE001 - OpenCascade segnala i fallimenti anche con eccezioni
        ok = False
    if not ok:
        stretta = _narrowest(ctx.body, per_ref)
        misura = f'{sigla}{fmt_mm(val)}' if sigla else f'{fmt_mm(val)} mm'
        dove = ' e '.join(ctx.describe(a) for a in refs[0]['faces'])
        raise FeatureError(f'Il {parola} {misura} non si può fare sullo spigolo tra {dove}: è troppo grande per le '
                           f'facce vicine (il lato più corto lì misura {fmt_mm(stretta)} mm). Prova una misura più '
                           'piccola.', feature=fid, code='misura_troppo_grande')
    res = ctx.body.after(mk, mk.Shape())
    for k, edges in enumerate(per_ref, start=1):
        for e in edges:
            for g in mk.Generated(e):
                lst = res.names.setdefault(f'{fid}/{parola}/{k}', [])
                f = TopoDS.Face(g)
                if not _contains(lst, f):
                    lst.append(f)
    check_solid(res.shape, fdef)
    return res


def _narrowest(body: NamedShape, per_ref) -> float:
    """La larghezza più piccola delle facce che toccano gli spigoli scelti, misurata di traverso
    allo spigolo (per spiegare l'errore): i bordi paralleli allo spigolo non contano."""
    corti = []
    facce = body.faces()
    for edges in per_ref:
        for e in edges:
            be = bd.Edge(e)
            dir_e = _direction(be)
            for f in facce:
                bordi = _edges_of(f)
                if not _contains(bordi, e):
                    continue
                for x in bordi:
                    if x.IsSame(e):
                        continue
                    bx = bd.Edge(x)
                    d = _direction(bx)
                    if dir_e is not None and d is not None and abs(dir_e.dot(d)) > 0.999:
                        continue
                    corti.append(bx.length)
    return min(corti) if corti else 0.0


def _direction(edge: bd.Edge):
    if edge.geom_type != bd.GeomType.LINE:
        return None
    return (edge.end_point() - edge.start_point()).normalized()
