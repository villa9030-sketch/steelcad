"""Disegno libero degli sketch dall'interfaccia: linee, rettangoli, cerchi, cancellazione.

Ogni forma disegnata arriva già con vincoli e quote, così il pezzo resta modificabile:
- i tratti quasi orizzontali/verticali diventano orizzontali/verticali;
- ogni tratto ha la sua lunghezza (in un contorno chiuso si salta l'ultimo orizzontale e
  l'ultimo verticale: sono già determinati dagli altri, quotarli sarebbe una quota doppia);
- il primo punto, se non è un punto che c'era già, prende la posizione dall'origine
  (distanza orizzontale e verticale);
- i cerchi hanno il diametro e la posizione del centro.
"""
from __future__ import annotations

import math

from cad_engine.errors import SketchError, SteelCADError
from cad_engine.sketch import solve
from cad_engine.sketch.model import ORIGIN
from cad_engine.sketch.profile import PLANES

HV_TOL = math.radians(3)      # entro 3° un tratto diventa orizzontale o verticale


def view(doc, sid: str, body=None) -> dict:
    """Lo sketch risolto, anche se il contorno è ancora aperto (mentre si disegna)."""
    sk = doc.sketch(sid)
    if isinstance(sk.plane, str):
        pl = PLANES[sk.plane]
    else:
        if body is None:
            raise SteelCADError('La faccia di questo sketch non c’è più nel pezzo.', code='piano')
        pl = doc._plane(sk, body)
    try:
        ss = solve(sk, doc.resolved_parameters())
        pts, stato = ss.points, ss.status.message
    except SteelCADError as ex:
        pts = {k: (e['x'], e['y']) for k, e in sk.entities.items() if e['kind'] == 'point'}
        stato = ex.message
    fr = next((f for f in (doc.last.features if doc.last else []) if f.id == sid), None)
    if fr is not None and not fr.ok:
        stato = fr.message
    g = lambda p: [(q := pl.from_local_coords(p)).X, q.Y, q.Z]  # noqa: E731
    out = {'id': sid, 'name': sk.name, 'plane': sk.plane, 'status': stato, 'ok': bool(fr and fr.ok),
           'origin': g((0, 0)), 'x_dir': [pl.x_dir.X, pl.x_dir.Y, pl.x_dir.Z], 'y_dir': [pl.y_dir.X, pl.y_dir.Y, pl.y_dir.Z],
           'z_dir': [pl.z_dir.X, pl.z_dir.Y, pl.z_dir.Z],
           'points': [{'id': k, 'xy': list(v), 'xyz': g(v)} for k, v in pts.items()
                      if not sk.entities.get(k, {}).get('construction')],
           'lines': [], 'circles': [],
           'used_by': [f['id'] for f in doc.features if not hasattr(f, 'entities') and f.get('sketch') == sid],
           'on_face': sk.plane.get('face') if isinstance(sk.plane, dict) else None}
    if out['on_face']:
        try:
            f0 = doc.feature(out['on_face'].split('/')[0])
            out['on_sheet'] = not hasattr(f0, 'entities') and f0.get('type') == 'sheet'
        except SteelCADError:
            out['on_sheet'] = False
    for k, e in sk.entities.items():
        if e['kind'] == 'line' and not e.get('construction'):
            out['lines'].append({'id': k, 'a': e['a'], 'b': e['b'], 'label': sk.describe(k),
                                 'pa': g(pts[e['a']]), 'pb': g(pts[e['b']])})
        elif e['kind'] == 'circle' and not e.get('construction'):
            c = pts[e['center']]
            r = e['r']
            try:
                r = ss.circles[k][1]
            except Exception:  # noqa: BLE001
                pass
            out['circles'].append({'id': k, 'center': g(c), 'r': r, 'label': sk.describe(k)})
    return out


def _snap_hv(a, b):
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    for k in range(-4, 5):
        if abs(ang - k * math.pi / 2) < HV_TOL:
            return 'horizontal' if k % 2 == 0 else 'vertical'
    return None


def _position(sk, pid, xy):
    """Il primo punto di una forma prende la posizione dall'origine (se non è l'origine)."""
    if pid == ORIGIN:
        return
    sk.dimension('hdistance', ORIGIN, pid, value=_r(xy[0]))
    sk.dimension('vdistance', ORIGIN, pid, value=_r(xy[1]))


def _r(v: float):
    v = round(float(v), 2)
    return int(v) if v.is_integer() else v


def _point_ref(sk, p):
    """p è un id di punto esistente oppure [x, y]: ritorna (id, xy, nuovo?)."""
    if isinstance(p, str):
        if sk.kind(p) != 'point':
            raise SketchError(f'{p} non è un punto.')
        e = sk.entities[p]
        return p, (e['x'], e['y']), False
    x, y = float(p[0]), float(p[1])
    return sk.point(x, y), (x, y), True


def add_polyline(doc, sid: str, pts: list, closed: bool) -> list[str]:
    sk = doc.sketch(sid)
    if len(pts) < 2:
        raise SketchError('Servono almeno due punti.')
    refs = [_point_ref(sk, p) for p in pts]
    for i in range(len(refs) - 1):
        if math.dist(refs[i][1], refs[i + 1][1]) < 1e-6:
            raise SketchError('Due punti consecutivi coincidono: un tratto lungo zero non si può fare.')
    ids = [r[0] for r in refs]
    xy = [r[1] for r in refs]
    if closed:
        if len(ids) < 3:
            raise SketchError('Per chiudere un contorno servono almeno tre punti.')
        ids.append(ids[0])
        xy.append(xy[0])
    linee = [sk.line(ids[i], ids[i + 1]) for i in range(len(ids) - 1)]
    for lid in linee:
        sk.entities[lid]['label'] = f'lato {lid}'     # "il fianco sul lato L3", non "linea L3"
    tipi = [_snap_hv(xy[i], xy[i + 1]) for i in range(len(linee))]
    for lid, t in zip(linee, tipi):
        if t:
            sk.constrain(t, lid, auto=True)
    salta = set()
    if closed:
        for t in ('horizontal', 'vertical'):
            ultimi = [i for i, x in enumerate(tipi) if x == t]
            if ultimi:
                salta.add(ultimi[-1])
        if tipi[-1] is None:
            salta.add(len(linee) - 1)
    for i, lid in enumerate(linee):
        if i not in salta:
            sk.dimension('length', lid, value=_r(math.dist(xy[i], xy[i + 1])))
    if refs[0][2]:
        _position(sk, ids[0], xy[0])
    return linee


def add_rectangle(doc, sid: str, p0, p1) -> dict:
    sk = doc.sketch(sid)
    a = (float(p0[0]), float(p0[1])) if not isinstance(p0, str) else (sk.entities[p0]['x'], sk.entities[p0]['y'])
    b = (float(p1[0]), float(p1[1]))
    if abs(b[0] - a[0]) < 1e-6 or abs(b[1] - a[1]) < 1e-6:
        raise SketchError('Il rettangolo ha bisogno di larghezza e altezza.')
    r = sk.rectangle(a[0], a[1], b[0], b[1])
    sk.dimension('length', r['bottom'], value=_r(abs(b[0] - a[0])))
    sk.dimension('length', r['left'], value=_r(abs(b[1] - a[1])))
    if isinstance(p0, str):
        # agganciato a un punto che c'era (anche l'origine): l'angolo più vicino coincide con quello
        e = sk.entities[p0]
        dove = min(r['corners'], key=lambda k: math.dist((sk.entities[k]['x'], sk.entities[k]['y']), (e['x'], e['y'])))
        sk.constrain('coincident', dove, p0)
    else:
        _position(sk, r['corners'][0], (min(a[0], b[0]), min(a[1], b[1])))
    return r


def add_circle(doc, sid: str, center, r: float) -> str:
    sk = doc.sketch(sid)
    r = float(r)
    if r <= 0:
        raise SketchError('Il cerchio ha bisogno di un raggio.')
    pid, xy, nuovo = _point_ref(sk, center)
    cid = sk.circle(pid, r)
    sk.dimension('diameter', cid, value=_r(2 * r))
    if nuovo:
        _position(sk, pid, xy)
    return cid


def delete(doc, sid: str, eids: list[str]) -> None:
    """Toglie linee/cerchi, i vincoli che li usano e i punti rimasti soli (mai l'origine)."""
    sk = doc.sketch(sid)
    via = set(eids)
    for e in eids:
        if e not in sk.entities or e == ORIGIN:
            raise SketchError(f'Nello sketch non c’è {e}.')
    for k in list(sk.entities):
        if k in via:
            del sk.entities[k]
    while True:
        usati = {ORIGIN}
        for e in sk.entities.values():
            for key in ('a', 'b', 'center', 'start', 'end'):
                if key in e:
                    usati.add(e[key])
        soli = [k for k, e in sk.entities.items() if e['kind'] == 'point' and k not in usati]
        via |= set(soli)
        for k in soli:
            del sk.entities[k]
        for cid, c in list(sk.constraints.items()):
            if any(r in via or r not in sk.entities for r in c['refs']):
                del sk.constraints[cid]
        if not soli:
            break


def _prune(doc, sid: str, before: set) -> list[str]:
    """Toglie le quote/vincoli appena aggiunti che il risolutore trova doppi o in conflitto."""
    sk = doc.sketch(sid)
    tolti = []
    for _ in range(12):
        try:
            st = solve(sk, doc.resolved_parameters()).status
        except SteelCADError:
            break
        nuovi = [c for c in list(st.redundant) + list(st.conflicting) if c not in before and c in sk.constraints]
        if not nuovi:
            break
        c = max(nuovi, key=lambda k: int(''.join(ch for ch in k if ch.isdigit()) or 0))
        del sk.constraints[c]
        tolti.append(c)
    return tolti


def guarded(fn):
    def run(doc, sid, *a, **kw):
        before = set(doc.sketch(sid).constraints)
        out = fn(doc, sid, *a, **kw)
        _prune(doc, sid, before)
        return out
    return run


add_polyline = guarded(add_polyline)
add_rectangle = guarded(add_rectangle)
add_circle = guarded(add_circle)
