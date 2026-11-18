"""Il piano di uno sketch messo su una faccia piana con nome.

Assi come li vedi guardando la faccia (la vista dello sketch ha "su" = Z): X verso destra, Y verso
l'alto. Per le facce orizzontali X è l'asse X globale. Origine: l'angolo in basso a sinistra della faccia,
così le quote del disegno partono dallo spigolo del pezzo ("40 dal bordo") e lo seguono se cambia.
"""
from __future__ import annotations

import build123d as bd
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane

from ..errors import SketchError
from ..topology import NamedShape, describe


def plane_of(body: NamedShape, face_name: str, sk) -> bd.Plane:
    facce = body.face(face_name)
    f = facce[0]
    if BRepAdaptor_Surface(f).GetType() != GeomAbs_Plane:
        raise SketchError(f'Lo sketch "{sk.label()}" sta su "{describe(face_name)}", che non è piana.')
    face = bd.Face(f)
    n = face.normal_at()
    su = bd.Vector(0, 0, 1)
    if abs(n.dot(su)) < 0.99:
        x = su.cross(n).normalized()             # faccia in piedi: X a destra guardandola, Y in su
    else:
        x = bd.Vector(1, 0, 0)
        x = (x - n * n.dot(x)).normalized()
    p0 = bd.Plane(origin=face.center(), x_dir=x, z_dir=n)
    loc = [p0.to_local_coords(v) for v in face.vertices()]
    x0, y0 = min(q.X for q in loc), min(q.Y for q in loc)
    parti = face_name.split('/')
    piega = len(parti) == 3 and parti[2] in ('esterno', 'interno')
    if piega and isinstance(getattr(sk, 'plane', None), dict) and sk.plane.get('zero') == 'bordo':
        # 18/11 (carrello): sulla faccia di una piega la X (lungo il lato) parte dal bordo esterno del pezzo, non
        # dall'angolo della faccia: gli angoli sopra/sotto allungano o accorciano la piega di uno spessore e i fori ci
        # andavano dietro. La Y (dalla piega) e le facce della base restano come prima
        bordo = _bordo_lamiera(body, p0, parti[1])
        if bordo is not None:
            x0 = bordo
    angolo = p0.from_local_coords((x0, y0))
    return bd.Plane(origin=angolo, x_dir=x, z_dir=n)


def _bordo_lamiera(body: NamedShape, p0: bd.Plane, fid: str):
    """Dove comincia, lungo la X del piano p0, il lato su cui è fatta la piega fid (per tutta la sua lunghezza, come
    disegnato): non cambia con gli angoli sopra/sotto né coi tagli negli angoli. None se la piega non c'è."""
    data = getattr(body, 'sheet', None)
    g = next((x for x in (getattr(data, 'flanges', None) or []) if x.fid == fid), None)
    if g is None:
        return None
    return min(p0.to_local_coords(p).X for p in (g.origin, g.origin + g.xf * g.length_edge))
