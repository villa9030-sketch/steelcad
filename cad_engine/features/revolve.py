"""Rivoluzione: il contorno chiuso dello sketch fatto girare attorno a un asse (una linea di costruzione dello stesso
sketch). Perni, boccole, punte, rondelle, pomelli; con «togli» una gola o un incavo tondo.

Definizione:
    {"id": "RV1", "type": "revolve", "sketch": "S1", "angle": 360, "operation": "new"}

Nomi delle facce: "RV1/giro/<entità dello sketch>" (la superficie fatta dal lato), "RV1/inizio" e "RV1/fine" se
l'angolo è meno di un giro.
"""
from __future__ import annotations

import math

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt
from OCP.TopoDS import TopoDS

from ..errors import FeatureError
from ..topology import NamedShape
from ..topology.naming import _edges_of
from ..units import cap, fmt_mm
from .base import Context, check_solid, label, n_solids, volume
from .extrude import _bd_edge


def _asse(ss, prof, fid):
    """L'asse: la linea di costruzione dello sketch (una sola)."""
    sk = ss.sketch
    linee = [(k, a, b) for k, (a, b) in ss.lines.items()
             if sk.entities[k].get('construction') and not sk.entities[k].get('ref')]
    if not linee:
        raise FeatureError('Per la rivoluzione disegna l’asse: una linea di costruzione (tasto «Costruzione» '
                           'acceso, poi una linea) attorno a cui girare il contorno.', feature=fid, code='asse')
    if len(linee) > 1:
        raise FeatureError('Nello sketch ci sono più linee di costruzione: per la rivoluzione ne serve una sola, '
                           'l’asse. Togli le altre o rendile normali.', feature=fid, code='asse')
    _k, a, b = linee[0]
    pa, pb = ss.points[a], ss.points[b]
    A, B = prof.plane.from_local_coords(pa), prof.plane.from_local_coords(pb)
    d = B - A
    if d.length < 1e-9:
        raise FeatureError('L’asse della rivoluzione è lungo zero.', feature=fid, code='asse')
    return pa, pb, A, d.normalized()


def build(fdef: dict, ctx: Context) -> NamedShape:
    fid = fdef['id']
    ss, prof = ctx.sketch(fdef)
    op = fdef.get('operation', 'new')
    if op not in ('new', 'add', 'cut'):
        raise FeatureError(f'Operazione "{op}" sconosciuta: usa nuovo solido, aggiungi o togli.', feature=fid)
    if op == 'new' and ctx.body is not None:
        raise FeatureError('Questa parte ha già un solido: scegli «Aggiungi» per unire o «Togli» per scavare.',
                           feature=fid)
    if op in ('add', 'cut') and ctx.body is None:
        raise FeatureError(f'{cap(label(fdef))} deve togliere o aggiungere materiale, ma il pezzo non esiste ancora.',
                           feature=fid)
    if not prof.faces:
        raise FeatureError(f'Lo sketch "{ss.sketch.label()}" non ha contorni chiusi da far girare.', feature=fid,
                           code='nessun_profilo')
    ang = ctx.value(fdef, 'angle', 'l’angolo') if fdef.get('angle') not in (None, '') else 360.0
    if not 0 < ang <= 360:
        raise FeatureError(f'L’angolo della rivoluzione va da 0 a 360°: {fmt_mm(ang)} non va.', feature=fid)
    pa, pb, A, d = _asse(ss, prof, fid)
    # il contorno deve stare da una parte sola dell'asse (se lo attraversa il solido si incrocia con se stesso)
    ux, uy = pb[0] - pa[0], pb[1] - pa[1]
    lati = set()
    for f in prof.faces:
        for v in f.vertices():
            q = prof.plane.to_local_coords(v)
            s = ux * (q.Y - pa[1]) - uy * (q.X - pa[0])
            if abs(s) > 1e-6 * math.hypot(ux, uy):
                lati.add(s > 0)
    if len(lati) > 1:
        raise FeatureError('Il contorno sta da tutte e due le parti dell’asse: disegna solo metà sezione, da una '
                           'parte della linea di costruzione.', feature=fid, code='asse')
    ax = gp_Ax1(gp_Pnt(A.X, A.Y, A.Z), gp_Dir(d.X, d.Y, d.Z))
    tool = None
    for face in prof.faces:
        src = face.wrapped
        spigoli = list(_edges_of(src))                 # una volta sola: gli oggetti si abbinano per identità
        mk = BRepPrimAPI_MakeRevol(src, ax, math.radians(ang), True)
        mk.Build()
        if not mk.IsDone():
            raise FeatureError(f'{cap(label(fdef))}: il contorno non si riesce a far girare.', feature=fid)
        names: dict[str, list] = {}
        for k, e in enumerate(spigoli):
            ent = prof.entity_of(_bd_edge(e)) or f'?{k + 1}'
            gen = [TopoDS.Face(x) for x in mk.Generated(e)]
            if gen:
                names.setdefault(f'{fid}/giro/{ent}', []).extend(gen)
        if ang < 360 - 1e-9:
            names.setdefault(f'{fid}/inizio', []).append(TopoDS.Face(mk.FirstShape()))
            names.setdefault(f'{fid}/fine', []).append(TopoDS.Face(mk.LastShape()))
        solid = mk.Shape()
        if volume(solid) < 0:
            solid = solid.Reversed()
        part = NamedShape(solid, names)
        if tool is None:
            tool = part
        else:
            fu = BRepAlgoAPI_Fuse(tool.shape, part.shape)
            fu.Build()
            tool = tool.after(fu, fu.Shape(), part)
    if op == 'new':
        check_solid(tool.shape, fdef)
        return tool
    mk = BRepAlgoAPI_Fuse(ctx.body.shape, tool.shape) if op == 'add' else BRepAlgoAPI_Cut(ctx.body.shape, tool.shape)
    mk.Build()
    if not mk.IsDone():
        raise FeatureError(f'{cap(label(fdef))}: il kernel non riesce a combinare la forma con il pezzo.', feature=fid)
    res = ctx.body.after(mk, mk.Shape(), tool)
    check_solid(res.shape, fdef)
    if op == 'cut' and volume(ctx.body.shape) - volume(res.shape) < 1e-6:
        raise FeatureError(f'{cap(label(fdef))} non tocca il pezzo.', feature=fid)
    if n_solids(res.shape) > 1:
        raise FeatureError(f'{cap(label(fdef))}: il pezzo resterebbe in {n_solids(res.shape)} parti staccate.',
                           feature=fid)
    return res

