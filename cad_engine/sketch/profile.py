"""Dallo sketch risolto alle facce: contorni chiusi, fori e isole.

Ogni bordo creato ricorda da quale entità dello sketch nasce: serve ai nomi
topologici (la faccia laterale nata dalla linea L2 si chiama "E1/lato/L2").
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

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
    aperto: str = ''     # linee aperte tollerate (persiane, scheletri, disegno in corso): il perché
    sciolte: list = field(default_factory=list)   # linee/archi che non chiudono nessun contorno: non contano

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


# 24/10: i lati e le facce già costruiti si ricordano (stesse coordinate, stesso piano): a ogni modifica di uno sketch
# da 300 fori si ricostruiva tutto, ora solo quello che è cambiato
_LATI: dict = {}
_FACCE: dict = {}


def _ricorda(memo: dict, chiave, fa):
    v = memo.get(chiave)
    if v is None:
        if len(memo) > 60000:
            memo.clear()
            _FACCE.clear()
        v = memo[chiave] = fa()
    return v


def _faccia_ricordata(w) -> bd.Face:
    """La faccia di un contorno fatto degli stessi lati (gli stessi lati del kernel, ricordati sopra) è la stessa."""
    lati = [e.wrapped for e in w.edges()]
    chiave = tuple(sorted(hash(x) for x in lati))
    v = _FACCE.get(chiave)
    if v is not None and len(v[0]) == len(lati) and all(any(a.IsSame(b) for b in v[0]) for a in lati):
        return v[1]
    f = bd.Face(w)
    if len(_FACCE) > 60000:
        _FACCE.clear()
    _FACCE[chiave] = (lati, f)
    return f


def build(ss: SolvedSketch, plane: bd.Plane) -> Profile:
    sk = ss.sketch
    o_, x_, z_ = plane.origin, plane.x_dir, plane.z_dir
    chiave_piano = tuple(round(c, 12) for v in (o_, x_, z_) for c in (v.X, v.Y, v.Z))
    g = lambda pid: plane.from_local_coords(ss.points[pid])  # noqa: E731

    sources: list[SourceEdge] = []
    circles: list[tuple[str, bd.Edge]] = []
    open_edges = []          # (entity, edge, a(x,y), b(x,y))
    for eid, (a, b) in ss.lines.items():
        if sk.entities[eid].get('construction'):
            continue
        if math.dist(ss.points[a], ss.points[b]) < 1e-6:
            continue                 # un tratto lungo zero tra due punti sovrapposti: nel contorno non conta
        e = _ricorda(_LATI, (chiave_piano, 'L', ss.points[a], ss.points[b]), lambda: bd.Edge.make_line(g(a), g(b)))
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
        e = _ricorda(_LATI, (chiave_piano, 'A', ss.points[a], ss.points[b], ss.points[c], r), lambda: bd.Edge.make_three_point_arc(
            g(a), plane.from_local_coords((cx + r * math.cos(tm), cy + r * math.sin(tm))), g(b)))
        open_edges.append((eid, e, ss.points[a], ss.points[b]))
    for eid, (c, r) in ss.circles.items():
        if sk.entities[eid].get('construction'):
            continue
        circles.append((eid, _ricorda(_LATI, (chiave_piano, 'C', ss.points[c], r), lambda: bd.Edge.make_circle(
            r, bd.Plane(origin=g(c), x_dir=plane.x_dir, z_dir=plane.z_dir)))))
    for eid, e, *_ in open_edges:
        sources.append(SourceEdge(eid, e, sk.entities[eid]['kind'], _key(e)))
    for eid, e in circles:
        sources.append(SourceEdge(eid, e, 'circle', _key(e)))

    chiusi, sciolte = _loops(sk, open_edges)
    loops = [bd.Wire([e]) for _, e in circles] + chiusi
    # i testi da tagliare: ogni contorno di lettera è un contorno chiuso (22/10)
    for e in sk.entities.values():
        if e['kind'] != 'text' or not e.get('stencil') or e['center'] not in ss.points:
            continue
        from . import testo as testo_mod
        x, y = ss.points[e['center']]
        for giro in testo_mod.contorni(e['text'], e['h'], x, y, e.get('angle', 0), e['stencil']):
            if len(giro) >= 3 and abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(giro, giro[1:] + giro[:1]))) > 1e-4:
                loops.append(bd.Wire.make_polygon([plane.from_local_coords(q) for q in giro], close=True))
    if sciolte and not loops:
        # niente di chiuso: è davvero un contorno aperto (o lo scheletro di una struttura)
        x, y = sciolte[0][1]
        raise SketchError(f'Il profilo non è chiuso: c\'è un\'estremità libera in ({fmt_mm(x)}; {fmt_mm(y)}).',
                          code='profilo_aperto')
    # uno sketch di soli punti (posizioni di fori) è valido: non ha facce
    return Profile(plane, _faces(loops, plane) if loops else [], sources, sciolte=[e for e, _ in sciolte])


def _loops(sk, open_edges) -> tuple[list, list]:
    """Collega linee e archi in contorni chiusi (estremità confrontate in coordinate dello sketch).
    Le linee che non chiudono niente (una linea dimenticata, un pezzo che sporge da un contorno) si tolgono
    e si rendono a parte: (contorni, [(entità, estremità libera), ...]). Prima bloccavano tutto il taglio."""
    nodes: list[tuple[float, float]] = []
    # griglia per trovare i punti vicini senza confrontarli tutti (serie grandi: migliaia di estremità); la
    # cella è grande almeno quanto la tolleranza più larga, si guarda la cella e le otto attorno
    cella = 1e-6 * max([1.0] + [abs(c) for *_, a, b in open_edges for c in (*a, *b)])
    griglia: dict = {}

    def node(p):
        cx, cy = math.floor(p[0] / cella), math.floor(p[1] / cella)
        vicini = [i for dx in (-1, 0, 1) for dy in (-1, 0, 1) for i in griglia.get((cx + dx, cy + dy), ())]
        for i in sorted(vicini):
            if math.dist(p, nodes[i]) < 1e-6 * max(1.0, abs(p[0]), abs(p[1])):
                return i
        nodes.append(p)
        griglia.setdefault((cx, cy), []).append(len(nodes) - 1)
        return len(nodes) - 1

    adj: dict[int, list[int]] = {}
    ends = []
    tolto = [False] * len(open_edges)
    doppie = set()
    nodo3 = {}                                   # il punto vero di ogni nodo: il primo che ci arriva
    for i, (eid, e, a, b) in enumerate(open_edges):
        na, nb = node(a), node(b)
        ends.append((na, nb))
        nodo3.setdefault(na, e.start_point())
        nodo3.setdefault(nb, e.end_point())
        # la stessa linea disegnata due volte (21/10: il bordo chiuso a mano e poi di nuovo) conta una: se no in
        # quei punti «si incontrano 3 linee»
        chiave = frozenset((na, nb))
        if na == nb or (sk.entities.get(eid, {}).get('kind') == 'line' and chiave in doppie):
            tolto[i] = True
            continue
        if sk.entities.get(eid, {}).get('kind') == 'line':
            doppie.add(chiave)
        adj.setdefault(na, []).append(i)
        adj.setdefault(nb, []).append(i)
    # si tolgono le estremità libere una dopo l'altra: resta solo quello che fa parte di un giro chiuso
    sciolte = []
    coda = [n for n, lst in adj.items() if len(lst) == 1]
    while coda:
        n = coda.pop()
        vive = [i for i in adj[n] if not tolto[i]]
        if len(vive) != 1:
            continue
        i = vive[0]
        tolto[i] = True
        sciolte.append((open_edges[i][0], nodes[n]))
        a, b = ends[i]
        altro = b if a == n else a
        if sum(1 for j in adj[altro] if not tolto[j]) == 1:
            coda.append(altro)
    for n in adj:
        adj[n] = [i for i in adj[n] if not tolto[i]]
    for n, lst in adj.items():
        x, y = nodes[n]
        if len(lst) > 2:
            raise SketchError(f'In ({fmt_mm(x)}; {fmt_mm(y)}) si incontrano {len(lst)} linee: il contorno è ambiguo. '
                              'Separa i contorni o usa linee di costruzione.', code='profilo_ambiguo')
    used = list(tolto)
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
        loops.append(bd.Wire([_ai_nodi(open_edges[i], ends[i], nodo3, sk) for i in chain]))
    return loops, sciolte


def _ai_nodi(oe, ends, nodo3, sk):
    """Il tratto con gli estremi esattamente nei nodi: due punti agganciati in modi diversi (uno sulla guida, uno
    dalla quota) possono stare a qualche decimillesimo; uniti nel nodo, ma il filo va chiuso davvero."""
    eid, e, *_ = oe
    A, B = nodo3[ends[0]], nodo3[ends[1]]
    if sk.entities.get(eid, {}).get('kind') != 'line' or ((e.start_point() - A).length < 1e-9
                                                           and (e.end_point() - B).length < 1e-9):
        return e
    return bd.Edge.make_line(A, B)


def _faces(loops: list, plane: bd.Plane) -> list:
    """Annidamento pari/dispari: livello 0 contorno, 1 foro, 2 isola dentro il foro…"""
    info = []
    for w in loops:
        try:
            f = _faccia_ricordata(w)
        except ValueError:
            raise SketchError('Un contorno dello sketch non si chiude esattamente (due estremità vicine ma non '
                              'unite): unisci i punti con «coincidente».', code='profilo_aperto') from None
        if f.area < TOL:
            raise SketchError('Un contorno dello sketch ha area zero.', code='profilo_degenere')
        info.append((w, f))
    # aree e ingombri calcolati una volta: con una serie di 75 asole i confronti a coppie erano migliaia, ognuno
    # con l'area rifatta e un'intersezione vera anche tra contorni lontanissimi
    aree = [f.area for _, f in info]
    box = [f.bounding_box() for _, f in info]

    def dentro_box(b, q):
        return b.min.X - TOL <= q.X <= b.max.X + TOL and b.min.Y - TOL <= q.Y <= b.max.Y + TOL             and b.min.Z - TOL <= q.Z <= b.max.Z + TOL

    def toccano(a, b):
        return not (a.max.X < b.min.X - TOL or b.max.X < a.min.X - TOL or a.max.Y < b.min.Y - TOL
                    or b.max.Y < a.min.Y - TOL or a.max.Z < b.min.Z - TOL or b.max.Z < a.min.Z - TOL)

    depth = []
    parent = []
    xs = [(b.min.X, b.max.X) for b in box]
    for i, (w, f) in enumerate(info):
        p = w.edges()[0].position_at(0.5)
        px = p.X
        contenitori = [j for j in range(len(info)) if j != i and xs[j][0] - TOL <= px <= xs[j][1] + TOL
                       and aree[j] > aree[i] and dentro_box(box[j], p) and _inside(info[j][1], p)]
        depth.append(len(contenitori))
        parent.append(min(contenitori, key=lambda j: aree[j]) if contenitori else None)
    faces = []
    for i, (w, f) in enumerate(info):
        if depth[i] % 2:
            continue
        holes = [info[j][0] for j in range(len(info)) if parent[j] == i and depth[j] == depth[i] + 1]
        try:
            face = bd.Face(w, holes) if holes else f
            if holes and abs(face.area - (f.area - sum(info[j][1].area for j in range(len(info))
                                                         if parent[j] == i and depth[j] == depth[i] + 1))) > TOL:
                raise ValueError
        except Exception:  # noqa: BLE001 - un contorno interno che esce da quello esterno
            raise SketchError('Due contorni dello sketch si sovrappongono (uno esce dall’altro): il profilo non è '
                              'chiaro. Uniscili in un solo contorno o separali.', code='profilo_sovrapposto') from None
        if face.normal_at().dot(plane.z_dir) < 0:
            face = -face
        faces.append(face)
    # le coppie che si toccano: in ordine di X, si guarda solo chi comincia prima che l'altro finisca (24/10: 300
    # fori facevano 45.000 confronti a coppie a ogni modifica)
    ordine = sorted(range(len(info)), key=lambda k: (box[k].min.X, k))
    for n, i in enumerate(ordine):
        for j in ordine[n + 1:]:
            if box[j].min.X > box[i].max.X + TOL:
                break
            a_, b_ = min(i, j), max(i, j)
            if depth[a_] == depth[b_] and toccano(box[a_], box[b_]) and _overlap(info[a_][1], info[b_][1]):
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
