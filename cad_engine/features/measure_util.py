"""Misure veloci sul kernel, senza passare da build123d."""
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib


def bbox(shape) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, b, False, False)   # ingombro esatto, senza margine
    a, c = b.CornerMin(), b.CornerMax()
    return (a.X(), a.Y(), a.Z()), (c.X(), c.Y(), c.Z())


def diagonal(shape) -> float:
    (x0, y0, z0), (x1, y1, z1) = bbox(shape)
    return ((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2) ** 0.5
