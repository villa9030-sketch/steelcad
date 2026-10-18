"""Adattatore verso planegcs (il PlaneGCS di FreeCAD) e stato dello sketch in parole semplici.

Funzione pura: dalla definizione dello sketch e dai parametri del documento
a un `SolvedSketch` (coordinate risolte + stato). La definizione non cambia.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import planegcs as gcs

from ..errors import SketchError
from ..expressions import evaluate
from ..units import cap, TOL, rad
from .model import DIMENSIONS, ORIGIN, Sketch

FULLY, UNDER, OVER, REDUNDANT, FAILED = 'completo', 'parziale', 'sovra-vincolato', 'ridondante', 'non risolto'


@dataclass
class SketchStatus:
    state: str                 # completo | parziale | sovra-vincolato | ridondante | non risolto
    dof: int
    message: str
    conflicting: list = field(default_factory=list)   # id dei vincoli/quote coinvolti
    redundant: list = field(default_factory=list)

    @property
    def ok_for_features(self) -> bool:
        """Si può costruire geometria? Sì se risolto (anche se non del tutto vincolato)."""
        return self.state in (FULLY, UNDER)

    def to_dict(self) -> dict:
        return {'state': self.state, 'dof': self.dof, 'message': self.message,
                'conflicting': self.conflicting, 'redundant': self.redundant}


@dataclass
class SolvedSketch:
    sketch: Sketch
    points: dict          # id -> (x, y)
    circles: dict         # id -> (center_id, r)
    arcs: dict            # id -> (center_id, start_id, end_id, r)
    lines: dict           # id -> (a_id, b_id)
    status: SketchStatus
    values: dict          # id quota -> valore numerico usato

    def xy(self, pid: str) -> tuple[float, float]:
        return self.points[pid]


def _value(sk: Sketch, cid: str, c: dict, params: dict) -> float:
    return evaluate(c['value'], params, what=f'valore della quota {cid}')


_MEMORIA: dict = {}


def solve(sk: Sketch, params: dict | None = None) -> SolvedSketch:
    """Risolve lo sketch. Lo stesso disegno con gli stessi parametri dà la stessa soluzione: la si ricorda
    (una modifica nell'interfaccia risolveva lo stesso sketch 3 volte: prima, dopo, nella ricostruzione)."""
    import dataclasses
    import json
    params = params or {}
    try:
        chiave = json.dumps([sk.plane, sk.entities, sk.constraints, params], sort_keys=True, default=str)
    except (TypeError, ValueError):
        chiave = None
    if chiave is not None and chiave in _MEMORIA:
        return dataclasses.replace(_MEMORIA[chiave], sketch=sk)
    out = _solve(sk, params)
    if chiave is not None:
        if len(_MEMORIA) > 64:
            _MEMORIA.pop(next(iter(_MEMORIA)))
        _MEMORIA[chiave] = out
    return out


def _solve(sk: Sketch, params: dict) -> SolvedSketch:
    # La diagnosi (gradi di libertà, vincoli superflui o in conflitto) si fa su
    # una copia con i punti spostati di pochissimo: se il disegno soddisfa già
    # alla perfezione i vincoli, planegcs vedrebbe superflui vincoli che servono.
    # La soluzione si calcola sempre sul disegno originale.
    dg, _, tag_of_d, values = _build(sk, params, jitter=True)
    diag = dg.diagnose()
    conflict = [tag_of_d[t] for t in diag.conflicting if t in tag_of_d]
    redundant = [tag_of_d[t] for t in diag.redundant if t in tag_of_d]
    status = _status(sk, diag.dof, conflict, redundant, values)
    s, (pid, lid, cid_, aid), _, _ = _build(sk, params, jitter=False)
    if status.state in (OVER, REDUNDANT):
        return _result(sk, s, pid, lid, cid_, aid, status, values, solved=False)
    res = s.solve()
    if res not in (gcs.SolveStatus.Success, gcs.SolveStatus.Converged):
        status = SketchStatus(FAILED, diag.dof,
                              'Con queste quote lo sketch non si può costruire. Controlla che i valori siano '
                              'possibili, per esempio un foro più grande della piastra o un angolo impossibile.')
        return _result(sk, s, pid, lid, cid_, aid, status, values, solved=False)
    return _result(sk, s, pid, lid, cid_, aid, status, values, solved=True)


def _jitter(eid: str, scale: float) -> tuple[float, float]:
    """Spostamento piccolo e deterministico (uguale a ogni esecuzione)."""
    h = sum((i + 1) * ord(ch) for i, ch in enumerate(eid))
    return (math.sin(h) * 1e-3 * scale, math.cos(h * 1.7) * 1e-3 * scale)


def _build(sk: Sketch, params: dict, jitter: bool):
    s = gcs.Sketch()
    pid, lid, cid_, aid = {}, {}, {}, {}
    tag_of = {}          # tag planegcs -> id vincolo nostro
    values = {}

    def add(tag, cid):
        tag_of[int(tag)] = cid

    scale = max([1.0] + [abs(e[k]) for e in sk.entities.values() if e['kind'] == 'point' for k in ('x', 'y')])
    # i punti con un vincolo "fisso" (i bordi arancio del pezzo, a decine) entrano già fissi: niente incognite né
    # equazioni, il risolutore e la diagnosi vanno molto più veloci
    fissi = {c['refs'][0]: kid for kid, c in sk.constraints.items() if c['type'] == 'fix' and len(c['refs']) == 1
             and sk.entities.get(c['refs'][0], {}).get('kind') == 'point'}
    # --- geometria
    for eid, e in sk.entities.items():
        if e['kind'] == 'point':
            if eid == ORIGIN:
                pid[eid] = s.add_fixed_point(0.0, 0.0)
            elif eid in fissi:
                pid[eid] = s.add_fixed_point(e['x'], e['y'])
            else:
                dx, dy = _jitter(eid, scale) if jitter else (0.0, 0.0)
                pid[eid] = s.add_point(e['x'] + dx, e['y'] + dy)
    for eid, e in sk.entities.items():
        k = e['kind']
        if k == 'line':
            lid[eid] = s.add_line(pid[e['a']], pid[e['b']])
        elif k == 'circle':
            cid_[eid] = s.add_circle(pid[e['center']], s.add_param(e['r']))
        elif k == 'arc':
            c, a, b = (s.get_point(pid[e[x]]) for x in ('center', 'start', 'end'))
            r = math.hypot(a[0] - c[0], a[1] - c[1])
            t0 = math.atan2(a[1] - c[1], a[0] - c[0])
            t1 = math.atan2(b[1] - c[1], b[0] - c[0])
            while t1 <= t0:
                t1 += 2 * math.pi
            aid[eid] = s.add_arc_cse(pid[e['center']], pid[e['start']], pid[e['end']], r, t0, t1)

    def curve(ref):
        k = sk.entities[ref]['kind']
        return k, {'line': lid, 'circle': cid_, 'arc': aid}.get(k, {}).get(ref)

    # --- vincoli e quote
    for kid, c in sk.constraints.items():
        t, refs = c['type'], c['refs']
        try:
            if t == 'coincident':
                add(s.coincident(pid[refs[0]], pid[refs[1]]), kid)
            elif t == 'horizontal':
                if len(refs) == 1:
                    add(s.horizontal(lid[refs[0]]), kid)
                else:
                    add(s.horizontal_points(pid[refs[0]], pid[refs[1]]), kid)
            elif t == 'vertical':
                if len(refs) == 1:
                    add(s.vertical(lid[refs[0]]), kid)
                else:
                    add(s.vertical_points(pid[refs[0]], pid[refs[1]]), kid)
            elif t == 'parallel':
                add(s.parallel(lid[refs[0]], lid[refs[1]]), kid)
            elif t == 'perpendicular':
                add(s.perpendicular(lid[refs[0]], lid[refs[1]]), kid)
            elif t == 'tangent':
                (k1, g1), (k2, g2) = curve(refs[0]), curve(refs[1])
                pair = {k1, k2}
                if k1 == 'line' and k2 == 'arc':
                    add(s.tangent_line_arc(g1, g2), kid)
                elif k1 == 'arc' and k2 == 'line':
                    add(s.tangent_line_arc(g2, g1), kid)
                elif k1 == 'line' and k2 == 'circle':
                    add(s.tangent_line_circle(g1, g2), kid)
                elif k1 == 'circle' and k2 == 'line':
                    add(s.tangent_line_circle(g2, g1), kid)
                elif pair == {'circle'}:
                    add(s.tangent_circle_circle(g1, g2), kid)
                elif pair == {'arc'}:
                    add(s.tangent_arc_arc(g1, g2), kid)
                elif pair == {'circle', 'arc'}:
                    c_, a_ = (g1, g2) if k1 == 'circle' else (g2, g1)
                    add(s.tangent_circle_arc(c_, a_), kid)
                else:
                    raise SketchError('La tangenza si mette tra linee, archi e cerchi.')
            elif t == 'equal':
                (k1, g1), (k2, g2) = curve(refs[0]), curve(refs[1])
                if k1 == k2 == 'line':
                    add(s.equal_length(g1, g2), kid)
                elif k1 == k2 == 'circle':
                    add(s.equal_radius_cc(g1, g2), kid)
                elif k1 == k2 == 'arc':
                    add(s.equal_radius_aa(g1, g2), kid)
                elif {k1, k2} == {'circle', 'arc'}:
                    c_, a_ = (g1, g2) if k1 == 'circle' else (g2, g1)
                    add(s.equal_radius_ca(c_, a_), kid)
                else:
                    raise SketchError('"Uguale" vale tra due linee (lunghezza) o tra cerchi e archi (raggio).')
            elif t == 'concentric':
                c1 = sk.entities[refs[0]]['center']
                c2 = sk.entities[refs[1]]['center']
                add(s.coincident(pid[c1], pid[c2]), kid)
            elif t == 'symmetric':
                k3 = sk.entities[refs[2]]['kind']
                if k3 == 'point':
                    add(s.symmetric_point(pid[refs[0]], pid[refs[1]], pid[refs[2]]), kid)
                else:
                    add(s.symmetric_line(pid[refs[0]], pid[refs[1]], lid[refs[2]]), kid)
            elif t == 'on_line':
                # "sulla linea" vale anche per cerchi e archi: il punto resta sul bordo
                k2 = sk.entities[refs[1]]['kind']
                if k2 == 'circle':
                    add(s.point_on_circle(pid[refs[0]], cid_[refs[1]]), kid)
                elif k2 == 'arc':
                    add(s.point_on_arc(pid[refs[0]], aid[refs[1]]), kid)
                else:
                    add(s.point_on_line(pid[refs[0]], lid[refs[1]]), kid)
            elif t == 'fix' and fissi.get(refs[0]) == kid:
                continue                                  # già fisso come punto
            elif t == 'fix':
                e = sk.entities[refs[0]]
                add(s.coordinate_x(pid[refs[0]], s.add_param(e['x'], fixed=True)), kid)
                add(s.coordinate_y(pid[refs[0]], s.add_param(e['y'], fixed=True)), kid)
            elif t in DIMENSIONS:
                v = _value(sk, kid, c, params)
                values[kid] = v
                if t in ('distance', 'length', 'diameter', 'radius', 'pldistance') and v <= 0:
                    raise SketchError(f'{cap(sk.describe_constraint(kid, v))} deve essere maggiore di zero.',
                                      code='quota_non_valida')
                if t == 'distance':
                    add(s.p2p_distance(pid[refs[0]], pid[refs[1]], s.add_param(v, fixed=True)), kid)
                elif t == 'length':
                    e = sk.entities[refs[0]]
                    add(s.p2p_distance(pid[e['a']], pid[e['b']], s.add_param(v, fixed=True)), kid)
                elif t == 'pldistance':
                    add(s.p2l_distance(pid[refs[0]], lid[refs[1]], s.add_param(v, fixed=True)), kid)
                elif t in ('hdistance', 'vdistance'):
                    i = 0 if t == 'hdistance' else 1
                    p1 = s.get_point_param_ids(pid[refs[0]])[i]
                    p2 = s.get_point_param_ids(pid[refs[1]])[i]
                    add(s.difference(p1, p2, s.add_param(v, fixed=True)), kid)
                elif t == 'angle':
                    add(s.l2l_angle(lid[refs[0]], lid[refs[1]], s.add_param(rad(v), fixed=True)), kid)
                elif t in ('diameter', 'radius'):
                    r = v / 2 if t == 'diameter' else v
                    k, g = curve(refs[0])
                    if k == 'circle':
                        add(s.circle_radius(g, s.add_param(r, fixed=True)), kid)
                    elif k == 'arc':
                        add(s.arc_radius(g, s.add_param(r, fixed=True)), kid)
                    else:
                        raise SketchError(f'{cap(DIMENSIONS[t])} si mette su un cerchio o un arco.')
        except KeyError as ex:
            raise SketchError(f'{sk.describe_constraint(kid)} usa un elemento che non va bene ({ex}).',
                              code='vincolo_non_valido') from None

    return s, (pid, lid, cid_, aid), tag_of, values


def _status(sk, dof, conflict, redundant, values) -> SketchStatus:
    def nome(cid):
        return sk.describe_constraint(cid, values.get(cid))

    if conflict:
        # le quote prima dei vincoli; l'ultima aggiunta è di solito quella "nuova"
        dims = sorted((c for c in conflict if c.startswith('D')), key=lambda c: int(c[1:]))
        altri = [c for c in conflict if c not in dims]
        nuova = dims[-1] if dims else altri[0]
        resto = [c for c in dims + altri if c != nuova]
        testo = f'{cap(nome(nuova))} è in conflitto con ' + (', '.join(nome(c) for c in resto) or 'altri vincoli') + \
                '. Togline una oppure cambia il valore.'
        return SketchStatus(OVER, dof, testo, conflicting=conflict, redundant=redundant)
    if redundant:
        if len(redundant) == 1:
            n = nome(redundant[0])
            testo = (f'{n[0].upper()}{n[1:]} non serve: la misura è già decisa dagli altri vincoli. '
                     'Toglila, altrimenti andrà in conflitto quando cambi le quote.')
        else:
            testo = ('Questi vincoli non servono, la geometria è già decisa dagli altri: '
                     + '; '.join(nome(c) for c in redundant) + '. Togline almeno uno.')
        return SketchStatus(REDUNDANT, dof, testo, redundant=redundant)
    if dof == 0:
        return SketchStatus(FULLY, 0, 'Lo sketch è completamente vincolato.')
    gradi = 'grado di libertà' if dof == 1 else 'gradi di libertà'
    return SketchStatus(UNDER, dof, f'Lo sketch ha ancora {dof} {gradi}: mancano quote o vincoli.')


def _result(sk, s, pid, lid, cid_, aid, status, values, solved: bool) -> SolvedSketch:
    pts = {}
    for k, g in pid.items():
        if solved:
            pts[k] = tuple(s.get_point(g))
        else:
            e = sk.entities[k]
            pts[k] = (e['x'], e['y'])
    circles = {}
    for k, g in cid_.items():
        e = sk.entities[k]
        circles[k] = (e['center'], s.get_circle(g).radius if solved else e['r'])
    arcs = {}
    for k, g in aid.items():
        e = sk.entities[k]
        if solved:
            r = s.get_arc(g).radius
        else:
            c, a = sk.entities[e['center']], sk.entities[e['start']]
            r = math.hypot(a['x'] - c['x'], a['y'] - c['y'])
        arcs[k] = (e['center'], e['start'], e['end'], r)
    lines = {k: (sk.entities[k]['a'], sk.entities[k]['b']) for k in lid}
    out = SolvedSketch(sk, pts, circles, arcs, lines, status, values)
    if solved:
        _check_degenerate(out)
    return out


def _check_degenerate(ss: SolvedSketch) -> None:
    for k, (a, b) in ss.lines.items():
        (x1, y1), (x2, y2) = ss.points[a], ss.points[b]
        if math.hypot(x2 - x1, y2 - y1) < TOL:
            raise SketchError(f'Con queste quote {ss.sketch.describe(k)} ha lunghezza zero.', code='sketch_degenere')
    for k, (_, r) in ss.circles.items():
        if r < TOL:
            raise SketchError(f'Con queste quote {ss.sketch.describe(k)} ha raggio zero.', code='sketch_degenere')
