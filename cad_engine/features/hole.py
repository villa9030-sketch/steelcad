"""Fori nei punti di uno sketch (punti o centri di cerchio).

Definizione:
    {"id": "H1", "type": "hole", "sketch": "S2", "points": ["P5", "C1"],
     "diameter": 12, "through": true}            # passante
    {"...": "...", "through": false, "depth": 10, "reverse": false}   # cieco

Il foro va dentro il pezzo, cioè in verso opposto alla normale dello sketch
(per uno sketch su una faccia, la normale esce dal pezzo); "reverse" lo gira.
Il fondo del foro cieco è piatto (la punta a 118° arriverà con i fori filettati).
Nomi: "H1/foro/<punto>", "H1/fondo/<punto>".
"""
from __future__ import annotations

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

from ..errors import FeatureError
from ..topology import NamedShape
from ..topology.naming import _faces_of
from ..units import cap, fmt_mm
from .base import Context, check_solid, label, n_solids, volume
from .measure_util import diagonal


def build(fdef: dict, ctx: Context) -> NamedShape:
    fid = fdef['id']
    if ctx.body is None:
        raise FeatureError('Un foro ha bisogno di un pezzo da forare: prima crea il solido.', feature=fid)
    ss, prof = ctx.sketch(fdef)
    d = ctx.value(fdef, 'diameter', 'il diametro')
    if d <= 0:
        raise FeatureError(f'Il diametro di {label(fdef)} deve essere maggiore di zero.', feature=fid)
    punti = fdef.get('points') or []
    if not punti:
        raise FeatureError(f'{cap(label(fdef))}: scegli almeno un punto dello sketch.', feature=fid)
    n = prof.plane.z_dir * (1 if fdef.get('reverse') else -1)
    through = fdef.get('through', True)
    if through:
        lungo = diagonal(ctx.body.shape) * 2 + 10
    else:
        lungo = ctx.value(fdef, 'depth', 'la profondità')
        if lungo <= 0:
            raise FeatureError(f'La profondità di {label(fdef)} deve essere maggiore di zero.', feature=fid)

    tool = None
    for p in punti:
        e = ss.sketch.entities.get(p)
        if e is None:
            raise FeatureError(f'{cap(label(fdef))}: il punto {p} non esiste più nello sketch.', feature=fid)
        pid = e['center'] if e['kind'] in ('circle', 'arc') else p
        if ss.sketch.entities[pid]['kind'] != 'point':
            raise FeatureError(f'{cap(label(fdef))}: {p} non è un punto né un cerchio.', feature=fid)
        c = prof.plane.from_local_coords(ss.points[pid])
        base = c - n * lungo if through else c
        h = 2 * lungo if through else lungo
        cyl = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(base.X, base.Y, base.Z), gp_Dir(n.X, n.Y, n.Z)), d / 2, h).Shape()
        names = {}
        for f in _faces_of(cyl):
            if BRepAdaptor_Surface(f).GetType() == GeomAbs_Cylinder:
                names.setdefault(f'{fid}/foro/{p}', []).append(f)
            else:
                centro = _plane_point(f)
                lontano = (centro - (base + n * h)).length < (centro - base).length
                if not through and lontano:
                    names.setdefault(f'{fid}/fondo/{p}', []).append(f)
        part = NamedShape(cyl, names)
        if tool is None:
            tool = part
        else:
            fu = BRepAlgoAPI_Fuse(tool.shape, part.shape)
            fu.Build()
            tool = tool.after(fu, fu.Shape(), part)

    mk = BRepAlgoAPI_Cut(ctx.body.shape, tool.shape)
    mk.Build()
    if not mk.IsDone():
        raise FeatureError(f'{cap(label(fdef))}: il kernel non riesce a forare il pezzo.', feature=fid)
    res = ctx.body.after(mk, mk.Shape(), tool)
    check_solid(res.shape, fdef)
    mancanti = [p for p in punti if not res.names.get(f'{fid}/foro/{p}')]
    if mancanti:
        raise FeatureError(f'{cap(label(fdef))}: il foro Ø{fmt_mm(d)} nel punto {", ".join(mancanti)} non '
                           'tocca il pezzo. Controlla la posizione o il verso (prova "inverti").', feature=fid)
    if n_solids(res.shape) > 1:
        raise FeatureError(f'{cap(label(fdef))} divide il pezzo in più parti: il diametro è troppo grande '
                           'per quella posizione.', feature=fid)
    if volume(ctx.body.shape) - volume(res.shape) < 1e-6:
        raise FeatureError(f'{cap(label(fdef))} non toglie materiale.', feature=fid)
    return res


def _plane_point(face):
    import build123d as bd
    return bd.Face(face).center()
