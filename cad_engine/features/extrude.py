"""Estrusione dei profili di uno sketch: nuovo solido, aggiungi materiale, togli (tasca).

Definizione:
    {"id": "E1", "type": "extrude", "sketch": "S1", "distance": 5,
     "operation": "new" | "add" | "cut", "reverse": false, "symmetric": false,
     "through_all": false}

Nomi delle facce create: "E1/lato/<entità sketch>", "E1/inizio", "E1/fine".
"""
from __future__ import annotations

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.gp import gp_Trsf, gp_Vec
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.TopoDS import TopoDS

from ..errors import FeatureError
from ..topology import NamedShape
from ..topology.naming import _edges_of
from ..units import cap, fmt_mm
from .base import Context, check_solid, label, n_solids, volume
from .measure_util import diagonal


def build(fdef: dict, ctx: Context) -> NamedShape:
    fid = fdef['id']
    ss, prof = ctx.sketch(fdef)
    op = fdef.get('operation', 'new')
    if op not in ('new', 'add', 'cut'):
        raise FeatureError(f'Operazione "{op}" sconosciuta: usa nuovo solido, aggiungi o togli.', feature=fid)
    if op == 'new' and ctx.body is not None:
        raise FeatureError('Questa parte ha già un solido: scegli "Aggiungi" per unire o "Togli" per una tasca.',
                           feature=fid)
    if op in ('add', 'cut') and ctx.body is None:
        raise FeatureError(f'{cap(label(fdef))} deve togliere o aggiungere materiale, ma il pezzo non '
                           'esiste ancora: la prima estrusione crea il solido.', feature=fid)

    if not prof.faces:
        raise FeatureError(f'Lo sketch "{ss.sketch.label()}" non ha contorni chiusi da estrudere: disegna un '
                           'contorno chiuso (rettangolo, cerchio, polilinea chiusa).', feature=fid,
                           code='nessun_profilo')
    if fdef.get('through_all'):
        if op != 'cut':
            raise FeatureError('"Passante" vale solo per le tasche.', feature=fid)
        dist = diagonal(ctx.body.shape) * 2 + 10
    else:
        dist = ctx.value(fdef, 'distance', "la distanza")
        if abs(dist) < 1e-9:
            raise FeatureError(f'La distanza di {label(fdef)} deve essere diversa da zero.', feature=fid)
    if fdef.get('reverse'):
        dist = -dist
    n = prof.plane.z_dir
    v = gp_Vec(n.X * dist, n.Y * dist, n.Z * dist)
    shift = None
    if fdef.get('symmetric'):
        shift = gp_Vec(-v.X() / 2, -v.Y() / 2, -v.Z() / 2)

    tool = None
    for face in prof.faces:
        src_face = face.wrapped
        entity_for = {}
        base_edges = _edges_of(src_face)
        for e in base_edges:
            ent = prof.entity_of(_bd_edge(e))
            entity_for[id(e)] = ent
        if shift is not None:
            tr = gp_Trsf()
            tr.SetTranslation(shift)
            moved = TopoDS.Face(BRepBuilderAPI_Transform(src_face, tr, True).Shape())
            pairs = list(zip(_edges_of(src_face), _edges_of(moved)))
            src_face = moved
        else:
            pairs = [(e, e) for e in base_edges]
        mk = BRepPrimAPI_MakePrism(src_face, v, False, True)
        mk.Build()
        if not mk.IsDone():
            raise FeatureError(f'{cap(label(fdef))}: il profilo non si può estrudere.', feature=fid)
        names: dict[str, list] = {}
        for k, (orig, e) in enumerate(pairs):
            ent = entity_for.get(id(orig)) or f'?{k + 1}'
            gen = [TopoDS.Face(x) for x in mk.Generated(e)]
            names.setdefault(f'{fid}/lato/{ent}', []).extend(gen)
        names.setdefault(f'{fid}/inizio', []).append(TopoDS.Face(mk.FirstShape()))
        names.setdefault(f'{fid}/fine', []).append(TopoDS.Face(mk.LastShape()))
        solid = mk.Shape()
        if volume(solid) < 0:          # estrusione contro la normale: il solido va girato
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
    if op == 'add':
        mk = BRepAlgoAPI_Fuse(ctx.body.shape, tool.shape)
    else:
        mk = BRepAlgoAPI_Cut(ctx.body.shape, tool.shape)
    mk.Build()
    if not mk.IsDone():
        raise FeatureError(f'{cap(label(fdef))}: il kernel non riesce a combinare la forma con il pezzo.',
                           feature=fid)
    res = ctx.body.after(mk, mk.Shape(), tool)
    check_solid(res.shape, fdef)
    v0, v1 = volume(ctx.body.shape), volume(res.shape)
    if op == 'cut' and v0 - v1 < 1e-6:
        raise FeatureError(f'{cap(label(fdef))} non tocca il pezzo: controlla dove sta lo sketch e da che '
                           'parte va la tasca (prova "inverti").', feature=fid)
    if op == 'add' and n_solids(res.shape) > 1:
        raise FeatureError(f'{cap(label(fdef))} non tocca il pezzo: il materiale aggiunto resterebbe '
                           'staccato.', feature=fid)
    if op == 'cut' and n_solids(res.shape) > 1:
        raise FeatureError(f'{cap(label(fdef))} divide il pezzo in {n_solids(res.shape)} parti '
                           f'staccate (volume tolto {fmt_mm(v0 - v1)} mm³). Una parte deve restare un solo pezzo.',
                           feature=fid)
    return res


def _bd_edge(e):
    import build123d as bd
    return bd.Edge(e)
