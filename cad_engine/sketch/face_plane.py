"""Il piano di uno sketch messo su una faccia piana con nome.

Origine: la proiezione dell'origine globale sul piano della faccia; asse X:
l'asse X globale proiettato (o Y, se X è perpendicolare). Così le quote dello
sketch non cambiano quando cambia la forma della faccia.
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
    p = face.center()
    origin = n * n.dot(p)
    x = bd.Vector(1, 0, 0)
    if abs(n.dot(x)) > 0.99:
        x = bd.Vector(0, 1, 0)
    x = (x - n * n.dot(x)).normalized()
    return bd.Plane(origin=origin, x_dir=x, z_dir=n)
