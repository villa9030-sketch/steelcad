"""Le impronte degli altri pezzi dell'assieme su una faccia (30/10, ARCH1019: due C con le linguette in basso che
entrano nella piastra, «vedo in trasparenza le C ma non ho gli snap per fare gli scassi»).

- ``penetrazioni``: dove un altro pezzo entra nel corpo (la sezione a metà della parte che entra): la sagoma
  dello scasso.
- ``appoggi``: dove un altro pezzo appoggia sulla faccia (la sua sezione appena fuori dalla faccia).
- ``anelli``: una sagoma come contorno nel piano dello sketch (punti, o un cerchio), allargata del gioco.
Tutto nelle coordinate del pezzo; ``altro`` è già messo nel posto giusto rispetto al pezzo.
"""
from __future__ import annotations

import math

import build123d as bd

GRANDE = 1e5
TOCCA = 0.05          # mm: un pezzo a meno di così dalla faccia ci appoggia


def _lastra(plane: bd.Plane, quota: float) -> bd.Face:
    p = bd.Plane(origin=plane.origin + plane.z_dir * quota, x_dir=plane.x_dir, z_dir=plane.z_dir)
    return bd.Face.make_rect(GRANDE, GRANDE, p)


def _sezione(shape, faccia) -> list:
    try:
        x = bd.Shape.cast(shape.wrapped if hasattr(shape, 'wrapped') else shape) & faccia
    except Exception:  # noqa: BLE001 - una sezione che non riesce: niente impronta
        return []
    return [f for f in (x.faces() if x is not None else []) if f.area > 1e-6]


def _vicini(a, b, gioco: float = 1.0) -> bool:
    A, B = a.bounding_box(), b.bounding_box()
    return all(tuple(A.min)[i] <= tuple(B.max)[i] + gioco and tuple(B.min)[i] <= tuple(A.max)[i] + gioco
               for i in range(3))


def penetrazioni(corpo, altro, plane: bd.Plane) -> list:
    """Le sagome (facce 3D sul piano a metà della parte che entra) dove ``altro`` entra in ``corpo``."""
    corpo, altro = bd.Shape.cast(_w(corpo)), bd.Shape.cast(_w(altro))
    if not _vicini(corpo, altro):
        return []
    try:
        inter = corpo & altro
    except Exception:  # noqa: BLE001
        return []
    if inter is None:                             # vicini ma senza niente in comune
        return []
    out = []
    for so in inter.solids():
        if so.volume < 1e-3:
            continue
        q = [(bd.Vector(v) - plane.origin).dot(plane.z_dir) for v in so.vertices()]
        out += _sezione(so, _lastra(plane, (min(q) + max(q)) / 2))
    return out


def appoggi(altro, plane: bd.Plane, faccia: bd.Face | None = None) -> list:
    """Le sagome di ``altro`` appena fuori dalla faccia (dove ci appoggia)."""
    altro = bd.Shape.cast(_w(altro))
    if faccia is not None and not _vicini(faccia, altro):
        return []
    return _sezione(altro, _lastra(plane, TOCCA))


def anelli(faccia: bd.Face, plane: bd.Plane, gioco: float = 0.0) -> list:
    """Il contorno esterno della sagoma nel piano dello sketch: ('cerchio', (x, y), r) o ('poli', [(x, y), …])."""
    f = faccia
    if gioco > 0:
        try:
            f = bd.offset(faccia, gioco, kind=bd.Kind.INTERSECTION).faces()[0]
        except Exception:  # noqa: BLE001 - l'allargamento non riesce: la sagoma giusta
            f = faccia
    w = f.outer_wire()
    ed = w.order_edges()
    loc = lambda v: (lambda q: (q.X, q.Y))(plane.to_local_coords(bd.Vector(v)))  # noqa: E731
    if len(ed) == 1 and ed[0].geom_type == bd.GeomType.CIRCLE:
        return [('cerchio', loc(ed[0].arc_center), ed[0].radius)]
    pts = []
    for e in ed:
        if e.geom_type == bd.GeomType.LINE:
            pts.append(loc(e.start_point()))
        else:                                       # archi e curve: a tratti di circa 1 mm (almeno 8)
            n = max(8, int(math.ceil(e.length)))
            pts += [loc(e.position_at(k / n)) for k in range(n)]
    return [('poli', pts)]


def _w(s):
    return s.wrapped if hasattr(s, 'wrapped') else s
