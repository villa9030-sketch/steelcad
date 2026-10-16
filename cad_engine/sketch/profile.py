"""Dallo sketch risolto alle facce: contorni chiusi, fori e isole.

Ogni bordo creato ricorda da quale entità dello sketch nasce: serve ai nomi
topologici (la faccia laterale nata dalla linea L2 si chiama "E1/lato/L2").
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import build123d as bd

from ..errors import SketchError
from ..units import TOL, fmt_mm
from .solver import SolvedSketch

PLANES = {'XY': bd.Plane.XY, 'XZ': bd.Plane.XZ, 'YZ': bd.Plane.YZ}


@dataclass
class SourceEdge:
    entity: str
    edge: bd.Edge
    kind: str            # line | arc | circle
    key: tuple           # firma geometrica per ritrovare il bordo dopo la costruzione della faccia


@dataclass
class Profile:
    plane: bd.Plane
    faces: list          # bd.Face
    sources: list        # SourceEdge

    def entity_of(self, edge: bd.Edge) -> str | None:
        """Quale entità dello sketch ha generato questo bordo (confronto geometrico)."""
        k = _key(edge)
        for s in self.sources:
            if _same_key(s.key, k):
                return s.entity
        return None


def _key(edge: bd.Edge) -> tuple:
    gt = edge.geom_type
    if gt == bd.GeomType.CIRCLE:
        c = edge.arc_center
        closed = edge.is_closed
        mid = None if closed else edge.position_at(0.5)
        return ('circle', (c.X, c.Y, c.Z), edge.radius, None if mid is None else (mid.X, mid.Y, mid.Z))
    m = edge.position_at(0.5)
    return (str(gt), (m.X, m.Y, m.Z), edge.length, None)


def _same_key(a: tuple, b: tuple, tol: float = 1e-5) -> bool:
    if a[0] != b[0]:
        return False
    if math.dist(a[1], b[1]) > tol or abs(a[2] - b[2]) > tol:
        return False
    if (a[3] is None) != (b[3] is None):
        return False
    return a[3] is None or math.dist(a[3], b[3]) <= tol


def build(ss: SolvedSketch, plane: bd.Plane) -> Profile:
    sk = ss.sketch
    g = lambda pid: plane.from_local_coords(ss.points[pid])  # noqa: E731

    sources: list[SourceEdge] = []
    circles: list[tuple[str, bd.Edge]] = []
    open_edges = []          # (entity, edge, a(x,y), b(x,y))
    for eid, (a, b) in ss.lines.items():
        if sk.entities[eid].get('construction'):
            continue
        e = bd.Edge.make_line(g(a), g(b))
        open_edges.append((eid, e, ss.points[a], ss.points[b]))
    for eid, (c, a, b, r) in ss.arcs.items():
        if sk.entities[eid].get('construction'):
            continue
        cx, cy = ss.points[c]
        t0 = math.atan2(ss.points[a][1] - cy, ss.points[a][0] - cx)
        t1 = math.atan2(ss.points[b][1] - cy, ss.points[b][0] - cx)
        while t1 <= t0:
            t1 += 2 * math.pi
        tm = (t0 + t1) / 2
        mid = plane.from_local_coords((cx + r * math.cos(tm), cy + r * math.sin(tm)))
        e = bd.Edge.make_three_point_arc(g(a), mid, g(b))
        open_edges.append((eid, e, ss.points[a], ss.points[b]))
    for eid, (c, r) in ss.circles.items():
        if sk.entities[eid].get('construction'):
            continue
        pl = bd.Plane(origin=g(c), x_dir=plane.x_dir, z_dir=plane.z_dir)
        circles.append((eid, bd.Edge.make_circle(r, pl)))
    for eid, e, *_ in open_edges:
        sources.append(SourceEdge(eid, e, sk.entities[eid]['kind'], _key(e)))
    for eid, e in circles:
        sources.append(SourceEdge(eid, e, 'circle', _key(e)))

    loops = [bd.Wire([e]) for _, e in circles] + _loops(sk, open_edges)
    # uno sketch di soli punti (posizioni di fori) è valido: non ha facce
    return Profile(plane, _faces(loops, plane) if loops else [], sources)


def _loops(sk, open_edges) -> list:
    """Collega linee e archi in contorni chiusi (estremità confrontate in coordinate dello sketch)."""
    nodes: list[tuple[float, float]] = []

    def node(p):
        for i, q in enumerate(nodes):
            if math.dist(p, q) < 1e-6 * max(1.0, abs(p[0]), abs(p[1])):
                return i
        nodes.append(p)
        return len(nodes) - 1

    adj: dict[int, list[int]] = {}
    ends = []
    for i, (_, _, a, b) in enumerate(open_edges):
        na, nb = node(a), node(b)
        ends.append((na, nb))
        adj.setdefault(na, []).append(i)
        adj.setdefault(nb, []).append(i)
    for n, lst in adj.items():
        x, y = nodes[n]
        if len(lst) == 1:
            raise SketchError(f'Il profilo non è chiuso: c\'è un\'estremità libera in ({fmt_mm(x)}; {fmt_mm(y)}).',
                              code='profilo_aperto')
        if len(lst) > 2:
            raise SketchError(f'In ({fmt_mm(x)}; {fmt_mm(y)}) si incontrano {len(lst)} linee: il contorno è ambiguo. '
                              'Separa i contorni o usa linee di costruzione.', code='profilo_ambiguo')
    used = [False] * len(open_edges)
    loops = []
    for start in range(len(open_edges)):
        if used[start]:
            continue
        chain = [start]
        used[start] = True
        cur_node = ends[start][1]
        first_node = ends[start][0]
        while cur_node != first_node:
            nxt = next(i for i in adj[cur_node] if not used[i])
            used[nxt] = True
            chain.append(nxt)
            a, b = ends[nxt]
            cur_node = b if a == cur_node else a
        loops.append(bd.Wire([open_edges[i][1] for i in chain]))
    return loops


def _faces(loops: list, plane: bd.Plane) -> list:
    """Annidamento pari/dispari: livello 0 contorno, 1 foro, 2 isola dentro il foro…"""
    info = []
    for w in loops:
        f = bd.Face(w)
        if f.area < TOL:
            raise SketchError('Un contorno dello sketch ha area zero.', code='profilo_degenere')
        info.append((w, f))
    depth = []
    parent = []
    for i, (w, f) in enumerate(info):
        p = w.edges()[0].position_at(0.5)
        contenitori = [j for j, (w2, f2) in enumerate(info) if j != i and f2.area > f.area and _inside(f2, p)]
        depth.append(len(contenitori))
        parent.append(min(contenitori, key=lambda j: info[j][1].area) if contenitori else None)
    faces = []
    for i, (w, f) in enumerate(info):
        if depth[i] % 2:
            continue
        holes = [info[j][0] for j in range(len(info)) if parent[j] == i and depth[j] == depth[i] + 1]
        face = bd.Face(w, holes) if holes else f
        if face.normal_at().dot(plane.z_dir) < 0:
            face = -face
        faces.append(face)
    for i in range(len(info)):
        for j in range(i + 1, len(info)):
            if depth[i] == depth[j] and _overlap(info[i][1], info[j][1]):
                raise SketchError('Due contorni dello sketch si sovrappongono: il profilo non è chiaro.',
                                  code='profilo_sovrapposto')
    return faces


def _inside(face: bd.Face, p: bd.Vector) -> bool:
    return face.is_inside(p)


def _overlap(f1: bd.Face, f2: bd.Face) -> bool:
    try:
        inter = f1.intersect(f2)
    except Exception:  # noqa: BLE001 - se il kernel non sa dirlo, non blocchiamo
        return False
    if inter is None:
        return False
    area = sum(getattr(x, 'area', 0.0) for x in (inter if isinstance(inter, list) else [inter]))
    return area > TOL
