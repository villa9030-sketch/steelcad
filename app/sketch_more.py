"""Altri strumenti di disegno: arco per tre punti, poligono regolare, raccordo e smusso di uno spigolo.

Ogni forma nasce con i vincoli che la tengono com'è (raggio, lati uguali, tangenze), così resta
modificabile con le quote come il resto del disegno.
"""
from __future__ import annotations

import math

from cad_engine.errors import SketchError
from cad_engine.sketch.model import ORIGIN

from app import sketch_ops
from app.sketch_edit import _sync
from app.sketch_trim import _cleanup


def _r(v):
    return sketch_ops._r(v)


# ------------------------------------------------------------------------------- arco per tre punti
def add_arc3(doc, sid: str, p1, p2, p3, construction: bool = False) -> str:
    """Arco dal primo punto al terzo passando per il secondo. Quota: il raggio."""
    sk = doc.sketch(sid)
    a, xa, nuovo_a = sketch_ops._point_ref(sk, p1)
    b, xb, _ = sketch_ops._point_ref(sk, p3)
    xm = (float(p2[0]), float(p2[1])) if not isinstance(p2, (str, dict)) else sketch_ops._point_ref(sk, p2)[1]
    (x1, y1), (x2, y2), (x3, y3) = xa, xm, xb
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        raise SketchError('I tre punti sono in fila: per un arco servono tre punti non allineati.')
    ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / d
    uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    c = sk.point(ux, uy)
    # gli archi vanno in senso antiorario: se i tre punti girano in senso orario si parte dal terzo
    antiorario = (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1) > 0
    arco = sk.arc(c, a, b, construction=construction) if antiorario else sk.arc(c, b, a, construction=construction)
    sk.dimension('radius', arco, value=_r(r))
    if nuovo_a:
        sketch_ops._position(sk, a, xa)
    return arco


# ------------------------------------------------------------------------------- poligono
def add_polygon(doc, sid: str, center, vertex, n: int, construction: bool = False) -> dict:
    """Poligono regolare inscritto in un cerchio di costruzione: centro, un vertice, numero di lati.
    Vincoli: vertici sul cerchio, lati uguali; quote: diametro del cerchio e posizione del centro."""
    sk = doc.sketch(sid)
    n = int(n)
    if not 3 <= n <= 64:
        raise SketchError('Il poligono va da 3 a 64 lati.')
    c, xc, nuovo = sketch_ops._point_ref(sk, center)
    vx, vy = (float(vertex[0]), float(vertex[1])) if not isinstance(vertex, (str, dict)) else sketch_ops._point_ref(sk, vertex)[1]
    r = math.hypot(vx - xc[0], vy - xc[1])
    if r < 1e-6:
        raise SketchError('Il vertice coincide con il centro: il poligono non ha grandezza.')
    a0 = math.atan2(vy - xc[1], vx - xc[0])
    guida = sk.circle(c, r, construction=True)
    sk.dimension('diameter', guida, value=_r(2 * r))
    pts = [sk.point(xc[0] + r * math.cos(a0 + 2 * math.pi * i / n), xc[1] + r * math.sin(a0 + 2 * math.pi * i / n)) for i in range(n)]
    linee = []
    for i in range(n):
        lid = sk.line(pts[i], pts[(i + 1) % n], construction=construction)
        sk.entities[lid]['label'] = f'lato {lid}'
        linee.append(lid)
    for p in pts:
        sk.constrain('on_line', p, guida)
    for lid in linee[1:]:
        sk.constrain('equal', linee[0], lid)
    hv = sketch_ops._snap_hv((sk.entities[pts[0]]['x'], sk.entities[pts[0]]['y']), (sk.entities[pts[1]]['x'], sk.entities[pts[1]]['y']))
    if hv:
        sk.constrain(hv, linee[0])               # il primo lato orizzontale/verticale: non gira più
    if nuovo:
        sketch_ops._position(sk, c, xc)
    return {'lines': linee, 'guide': guida}


# ------------------------------------------------------------------------------- raccordo e smusso
def _corner(sk, pid):
    """Le due linee che si incontrano nel punto pid: (linea1, altro estremo1, linea2, altro estremo2)."""
    if pid not in sk.entities or sk.entities[pid]['kind'] != 'point':
        raise SketchError('Clicca uno spigolo: il punto dove si incontrano due linee.')
    linee = [k for k, e in sk.entities.items() if e['kind'] == 'line' and pid in (e['a'], e['b'])
             and not e.get('ref')]
    altro = [k for k, e in sk.entities.items() if e['kind'] in ('arc', 'circle')
             and pid in (e.get('start'), e.get('end'), e.get('center'))]
    if len(linee) != 2 or altro:
        raise SketchError('In questo punto non si incontrano esattamente due linee: lì non c’è uno spigolo da raccordare.')
    l1, l2 = linee
    o1 = sk.entities[l1]['b'] if sk.entities[l1]['a'] == pid else sk.entities[l1]['a']
    o2 = sk.entities[l2]['b'] if sk.entities[l2]['a'] == pid else sk.entities[l2]['a']
    return l1, o1, l2, o2


def _setback(sk, pid, l1, o1, l2, o2, dist_fn):
    P = (sk.entities[pid]['x'], sk.entities[pid]['y'])
    A = (sk.entities[o1]['x'], sk.entities[o1]['y'])
    B = (sk.entities[o2]['x'], sk.entities[o2]['y'])
    L1, L2 = math.dist(P, A), math.dist(P, B)
    u1 = ((A[0] - P[0]) / L1, (A[1] - P[1]) / L1)
    u2 = ((B[0] - P[0]) / L2, (B[1] - P[1]) / L2)
    th = math.acos(max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1])))
    if th < 1e-6 or th > math.pi - 1e-6:
        raise SketchError('Le due linee sono in fila: non c’è uno spigolo.')
    d = dist_fn(th)
    if d >= min(L1, L2) - 1e-6:
        raise SketchError(f'Troppo grande per questo spigolo: le linee sono lunghe {L1:.1f} e {L2:.1f} mm.')
    return P, u1, u2, th, d


def _stacca(sk, pid, l1, l2, t1, t2):
    """Le due linee non arrivano più nello spigolo ma ai punti t1, t2; le loro lunghezze non valgono più."""
    for lid, t in ((l1, t1), (l2, t2)):
        e = sk.entities[lid]
        e['a' if e['a'] == pid else 'b'] = t
    via = [k for k, c in sk.constraints.items() if c['type'] == 'length' and c['refs'][0] in (l1, l2)]
    _cleanup(sk, via)


def fillet(doc, sid: str, pid: str, r) -> str:
    """Raccordo di raggio r nello spigolo pid: un arco tangente alle due linee, che si accorciano."""
    sk = doc.sketch(sid)
    _sync(doc, sk)
    r = float(r)
    if r <= 0:
        raise SketchError('Il raggio del raccordo deve essere maggiore di zero.')
    l1, o1, l2, o2 = _corner(sk, pid)
    P, u1, u2, th, d = _setback(sk, pid, l1, o1, l2, o2, lambda th: r / math.tan(th / 2))
    t1 = sk.point(P[0] + u1[0] * d, P[1] + u1[1] * d)
    t2 = sk.point(P[0] + u2[0] * d, P[1] + u2[1] * d)
    bx, by = u1[0] + u2[0], u1[1] + u2[1]
    bl = math.hypot(bx, by)
    h = r / math.sin(th / 2)
    c = sk.point(P[0] + bx / bl * h, P[1] + by / bl * h)
    p1, p2, pc = ((sk.entities[k]['x'], sk.entities[k]['y']) for k in (t1, t2, c))
    antiorario = (p1[0] - pc[0]) * (p2[1] - pc[1]) - (p1[1] - pc[1]) * (p2[0] - pc[0]) > 0
    costr = bool(sk.entities[l1].get('construction'))
    arco = sk.arc(c, t1, t2, construction=costr) if antiorario else sk.arc(c, t2, t1, construction=costr)
    _stacca(sk, pid, l1, l2, t1, t2)
    sk.constrain('tangent', l1, arco)
    sk.constrain('tangent', l2, arco)
    sk.dimension('radius', arco, value=_r(r))
    return arco


def chamfer(doc, sid: str, pid: str, dist) -> str:
    """Smusso uguale sui due lati dello spigolo pid: una linea dritta, le due linee si accorciano di dist."""
    sk = doc.sketch(sid)
    _sync(doc, sk)
    dist = float(dist)
    if dist <= 0:
        raise SketchError('La misura dello smusso deve essere maggiore di zero.')
    l1, o1, l2, o2 = _corner(sk, pid)
    P, u1, u2, th, d = _setback(sk, pid, l1, o1, l2, o2, lambda th: dist)
    t1 = sk.point(P[0] + u1[0] * d, P[1] + u1[1] * d)
    t2 = sk.point(P[0] + u2[0] * d, P[1] + u2[1] * d)
    costr = bool(sk.entities[l1].get('construction'))
    nuova = sk.line(t1, t2, construction=costr)
    sk.entities[nuova]['label'] = f'lato {nuova}'
    _stacca(sk, pid, l1, l2, t1, t2)
    sk.dimension('length', nuova, value=_r(math.dist((sk.entities[t1]['x'], sk.entities[t1]['y']),
                                                     (sk.entities[t2]['x'], sk.entities[t2]['y']))))
    return nuova


def _join(sk, l1, l2, c1, c2) -> str:
    """Come AutoCAD con due linee: se hanno già un estremo in comune è quello lo spigolo; se no si
    allungano/accorciano fino a dove si incontrano (resta la parte dove hai cliccato) e si uniscono lì."""
    for l in (l1, l2):
        if sk.entities.get(l, {}).get('kind') != 'line':
            raise SketchError('Clicca due linee.')
    if l1 == l2:
        raise SketchError('Clicca due linee diverse.')
    e1, e2 = sk.entities[l1], sk.entities[l2]
    comune = {e1['a'], e1['b']} & {e2['a'], e2['b']}
    if comune:
        return comune.pop()
    xy = lambda p: (sk.entities[p]['x'], sk.entities[p]['y'])  # noqa: E731
    a1, b1, a2, b2 = xy(e1['a']), xy(e1['b']), xy(e2['a']), xy(e2['b'])
    d1 = (b1[0] - a1[0], b1[1] - a1[1])
    d2 = (b2[0] - a2[0], b2[1] - a2[1])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-12:
        raise SketchError('Le due linee sono parallele: non si incontrano.')
    t = ((a2[0] - a1[0]) * d2[1] - (a2[1] - a1[1]) * d2[0]) / den
    X = (a1[0] + d1[0] * t, a1[1] + d1[1] * t)
    angolo = None
    via = []
    for lid, e, a, d, c in ((l1, e1, a1, d1, c1), (l2, e2, a2, d2, c2)):
        L2 = d[0] * d[0] + d[1] * d[1]
        tc = ((float(c[0]) - a[0]) * d[0] + (float(c[1]) - a[1]) * d[1]) / L2
        tx = ((X[0] - a[0]) * d[0] + (X[1] - a[1]) * d[1]) / L2
        chiave = 'b' if tx >= tc else 'a'            # resta la parte dove hai cliccato, l'altro estremo va in X
        vecchio = e[chiave]
        if angolo is None:
            altri = [k for k, x in sk.entities.items() if k != lid and vecchio in (x.get('a'), x.get('b'), x.get('center'), x.get('start'), x.get('end'))]
            if vecchio == ORIGIN or altri:
                angolo = sk.point(*X)
            else:
                angolo = vecchio
                sk.entities[vecchio]['x'], sk.entities[vecchio]['y'] = X
                via += [k for k, cc in sk.constraints.items() if vecchio in cc['refs'] and cc['type'] in ('hdistance', 'vdistance', 'distance', 'fix', 'coincident')]
        e[chiave] = angolo
        via += [k for k, cc in sk.constraints.items() if cc['type'] == 'length' and cc['refs'] == [lid]]
    _cleanup(sk, via)
    return angolo


def fillet_lines(doc, sid: str, l1: str, l2: str, c1, c2, r) -> str | None:
    """Raccordo cliccando le due linee (come AutoCAD). Raggio 0: le unisce in uno spigolo vivo."""
    sk = doc.sketch(sid)
    _sync(doc, sk)
    pid = _join(sk, l1, l2, c1, c2)
    if float(r) == 0:
        return None
    return _fillet_raw(doc, sid, pid, r)


def chamfer_lines(doc, sid: str, l1: str, l2: str, c1, c2, d) -> str | None:
    sk = doc.sketch(sid)
    _sync(doc, sk)
    pid = _join(sk, l1, l2, c1, c2)
    if float(d) == 0:
        return None
    return _chamfer_raw(doc, sid, pid, d)


_fillet_raw, _chamfer_raw = fillet, chamfer
add_arc3 = sketch_ops.guarded(add_arc3)
add_polygon = sketch_ops.guarded(add_polygon)
fillet = sketch_ops.guarded(fillet)
chamfer = sketch_ops.guarded(chamfer)
fillet_lines = sketch_ops.guarded(fillet_lines)
chamfer_lines = sketch_ops.guarded(chamfer_lines)


# ------------------------------------------------------------------------- spigoli del pezzo (linee arancio)
def is_part_corner(sk, pid) -> bool:
    """pid è uno spigolo del pezzo: un punto dei bordi (arancio) dove arrivano due bordi dritti e nient'altro."""
    e = sk.entities.get(pid)
    if not e or e['kind'] != 'point' or not e.get('ref'):
        return False
    linee = [k for k, x in sk.entities.items() if x['kind'] == 'line' and pid in (x['a'], x['b'])]
    archi = [k for k, x in sk.entities.items() if x['kind'] in ('arc', 'circle') and pid in (x.get('start'), x.get('end'), x.get('center'))]
    if len(linee) != 2 or not all(sk.entities[k].get('ref') for k in linee) or archi:
        return False
    xy = lambda p: (sk.entities[p]['x'], sk.entities[p]['y'])  # noqa: E731
    P = xy(pid)
    (ax, ay), (bx, by) = (xy(sk.entities[k]['b'] if sk.entities[k]['a'] == pid else sk.entities[k]['a']) for k in linee)
    u, w = (ax - P[0], ay - P[1]), (bx - P[0], by - P[1])
    sen = abs(u[0] * w[1] - u[1] * w[0]) / ((math.hypot(*u) * math.hypot(*w)) or 1)
    return sen > 1e-6                               # due bordi in fila non fanno uno spigolo


def ref_corner_of_lines(sk, l1, l2):
    """Con il raccordo "clic sulle due linee": se sono bordi del pezzo, lo spigolo dove si incontrano."""
    e1, e2 = sk.entities.get(l1, {}), sk.entities.get(l2, {})
    if not (e1.get('ref') or e2.get('ref')):
        return None
    comune = {e1.get('a'), e1.get('b')} & {e2.get('a'), e2.get('b')} if e1.get('ref') and e2.get('ref') else set()
    if len(comune) != 1:
        raise SketchError('Le linee arancio sono i bordi del pezzo: per raccordare il pezzo clicca lo spigolo dove '
                          'si incontrano due bordi (o i due bordi vicini).')
    return comune.pop()


def _dentro(sk, q) -> bool:
    """q sta dentro la faccia? Si conta quante volte una semiretta da q attraversa i bordi arancio."""
    xy = lambda p: (sk.entities[p]['x'], sk.entities[p]['y'])  # noqa: E731
    segs = []
    for e in sk.entities.values():
        if not e.get('ref'):
            continue
        if e['kind'] == 'line':
            segs.append((xy(e['a']), xy(e['b'])))
        elif e['kind'] == 'arc':
            c, a, b = xy(e['center']), xy(e['start']), xy(e['end'])
            r = math.dist(c, a)
            a0, a1 = math.atan2(a[1] - c[1], a[0] - c[0]), math.atan2(b[1] - c[1], b[0] - c[0])
            while a1 <= a0:
                a1 += 2 * math.pi
            pts = [(c[0] + r * math.cos(a0 + (a1 - a0) * i / 16), c[1] + r * math.sin(a0 + (a1 - a0) * i / 16)) for i in range(17)]
            segs += list(zip(pts, pts[1:]))
    dentro = False
    for (x1, y1), (x2, y2) in segs:
        if (y1 > q[1]) != (y2 > q[1]):
            x = x1 + (q[1] - y1) * (x2 - x1) / (y2 - y1)
            if x > q[0]:
                dentro = not dentro
    return dentro


def part_corner(doc, sid: str, pid: str, size, tool: str) -> dict:
    """Raccordo (o smusso) di uno spigolo del pezzo mentre si disegna sulla sua faccia. I bordi arancio non
    sono linee dello sketch: lo spigolo si arrotonda togliendo la punta (spigolo vivo verso fuori) o
    aggiungendo materiale (spigolo verso dentro, es. dove una linguetta incontra la parete). Diventa un
    taglio/linguetta subito dopo lo sketch, con un suo sketchino; i bordi arancio prendono la forma nuova."""
    sk = doc.sketch(sid)
    size = float(size)
    if size <= 0:
        raise SketchError('La misura deve essere maggiore di zero.')
    if not is_part_corner(sk, pid):
        raise SketchError('Qui non c’è uno spigolo del pezzo da raccordare.')
    l1, l2 = [k for k, x in sk.entities.items() if x['kind'] == 'line' and pid in (x['a'], x['b'])]
    o1 = sk.entities[l1]['b'] if sk.entities[l1]['a'] == pid else sk.entities[l1]['a']
    o2 = sk.entities[l2]['b'] if sk.entities[l2]['a'] == pid else sk.entities[l2]['a']
    fn = (lambda th: size / math.tan(th / 2)) if tool == 'fillet' else (lambda th: size)
    P, u1, u2, th, d = _setback(sk, pid, l1, o1, l2, o2, fn)
    T1 = (P[0] + u1[0] * d, P[1] + u1[1] * d)
    T2 = (P[0] + u2[0] * d, P[1] + u2[1] * d)
    bx, by = u1[0] + u2[0], u1[1] + u2[1]
    bl = math.hypot(bx, by)
    C = None
    if tool == 'fillet':
        h = size / math.sin(th / 2)
        C = (P[0] + bx / bl * h, P[1] + by / bl * h)
        M = (P[0] + bx / bl * (h - size) / 2, P[1] + by / bl * (h - size) / 2)
    else:
        M = ((P[0] + T1[0] + T2[0]) / 3, (P[1] + T1[1] + T2[1]) / 3)
    aggiungi = not _dentro(sk, M)
    # lo sketchino con la punta da togliere/aggiungere: spigolo, due tratti sui bordi, arco (o smusso)
    piccolo = doc.add_sketch(dict(sk.plane), f'Sketch: {"raccordo" if tool == "fillet" else "smusso"} spigolo')
    fix = lambda q: (piccolo.constrain('fix', pp := piccolo.point(*q)), pp)[1]  # noqa: E731
    pP, p1, p2 = fix(P), fix(T1), fix(T2)
    piccolo.line(p1, pP)
    piccolo.line(pP, p2)
    if C is not None:
        pc = piccolo.point(*C)
        antiorario = (T1[0] - C[0]) * (T2[1] - C[1]) - (T1[1] - C[1]) * (T2[0] - C[0]) > 0
        arco = piccolo.arc(pc, p1, p2) if antiorario else piccolo.arc(pc, p2, p1)
        piccolo.dimension('radius', arco, value=_r(size))
    else:
        piccolo.line(p2, p1)
    nome = f'{"Raccordo" if tool == "fillet" else "Smusso"} spigolo {"R" if tool == "fillet" else ""}{_r(size)}'
    su_lamiera = isinstance(sk.plane, dict) and any(
        not isinstance(f, type(sk)) and f.get('type') == 'sheet'
        and f['id'] == (sk.plane.get('flat') or (sk.plane.get('face') or '').split('/')[0]) for f in doc.features)
    if aggiungi:
        if not su_lamiera or sk.plane.get('flat'):
            raise SketchError('Questo spigolo va verso dentro: per arrotondarlo bisogna aggiungere materiale, e si '
                              'può fare solo sulle facce di una lamiera.')
        fid = doc.add_feature('sheet_cut', nome, sketch=piccolo.id, mode='add')
    elif su_lamiera:
        fid = doc.add_feature('sheet_cut', nome, sketch=piccolo.id)
    else:
        fid = doc.add_feature('extrude', nome, sketch=piccolo.id, operation='cut', through_all=True, reverse=True)
    # in ordine: subito dopo lo sketch su cui si sta disegnando (vede la stessa faccia, stesse coordinate)
    nuovi = doc.features[-2:]
    del doc.features[-2:]
    i = doc.features.index(sk) + 1
    doc.features[i:i] = nuovi
    # i bordi arancio dello sketch aperto seguono la forma nuova
    ref = lambda q: (sk.constrain('fix', pp := sk.point(*q, construction=True)), sk.entities[pp].__setitem__('ref', True), pp)[2]  # noqa: E731
    r1, r2 = ref(T1), ref(T2)
    for lid, rr in ((l1, r1), (l2, r2)):
        e = sk.entities[lid]
        e['a' if e['a'] == pid else 'b'] = rr
    if C is not None:
        rc = sk.point(*C, construction=True)
        sk.entities[rc]['ref'] = True
        a = sk.arc(rc, r1, r2, construction=True) if antiorario else sk.arc(rc, r2, r1, construction=True)
        sk.dimension('radius', a, value=_r(size))
    else:
        a = sk.line(r1, r2, construction=True, label='bordo del pezzo')
    sk.entities[a]['ref'] = True
    legati = [k for k, c in sk.constraints.items() if pid in c['refs']]
    if all(sk.constraints[k]['type'] == 'fix' for k in legati) and not any(
            pid in (x.get('a'), x.get('b'), x.get('center'), x.get('start'), x.get('end')) for x in sk.entities.values()):
        for k in legati:                              # la punta non c'è più: via anche il suo punto
            del sk.constraints[k]
        del sk.entities[pid]
    return {'feature': fid, 'added': aggiungi}
