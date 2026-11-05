"""Altri modi di fare rettangoli e cerchi (05/11, idee da SolidCraft: sketch.rectangle.center/three_point/rounded,
sketch.circle.three_point/two_tangent/three_tangent). Si scelgono dentro gli strumenti Rettangolo e Cerchio.

Ogni forma nasce con i vincoli che la tengono com'è, così poi le quote funzionano come per il rettangolo e il
cerchio normali:
- rettangolo dal centro: il centro è un punto in mezzo alla diagonale (simmetrico), quote larghezza e altezza;
- rettangolo a 3 punti (storto): lati a squadra, quote dei due lati e angolo del primo dall'orizzontale;
- rettangolo raccordato: quattro raccordi tangenti dello stesso raggio, quote fuori tutto e raggio;
- cerchio per 3 punti: passa per i punti cliccati che c'erano già (restano legati), quota il diametro;
- cerchio tangente a 2 linee (raggio scritto) o a 3 linee: tangenze vere, si muove con le linee.
"""
from __future__ import annotations

import itertools
import math

from cad_engine.errors import SketchError
from cad_engine.sketch.model import ORIGIN

from app import sketch_ops
from app.sketch_edit import _solved_xy

_r = sketch_ops._r


def _xy_di(sk, p):
    """Le coordinate di un punto dato come id, aggancio {'xy': …} o [x, y] (senza creare niente)."""
    if isinstance(p, str):
        e = sk.entities.get(p)
        if not e or e['kind'] != 'point':
            raise SketchError(f'Nello sketch non c’è il punto {p}.')
        return float(e['x']), float(e['y'])
    if isinstance(p, dict):
        return tuple(float(v) for v in p.get('xy', (0, 0)))
    return float(p[0]), float(p[1])


def _costruzione(sk, ids, flag):
    for k in ids:
        sk.entities[k]['construction'] = bool(flag)


# ------------------------------------------------------------------------------- rettangoli
def add_rectangle_center(doc, sid: str, center, corner, construction: bool = False) -> dict:
    """Rettangolo dal centro: clic sul centro (anche il centro di un foro o l'origine) e su un angolo."""
    sk = doc.sketch(sid)
    pc, (cx, cy), nuovo = sketch_ops._point_ref(sk, center)
    bx, by = _xy_di(sk, corner)
    w2, h2 = abs(bx - cx), abs(by - cy)
    if w2 < 1e-6 or h2 < 1e-6:
        raise SketchError('Il rettangolo ha bisogno di larghezza e altezza.')
    r = sk.rectangle(cx - w2, cy - h2, cx + w2, cy + h2)
    _costruzione(sk, r['lines'], construction)
    sk.dimension('length', r['bottom'], value=_r(2 * w2))
    sk.dimension('length', r['left'], value=_r(2 * h2))
    sk.constrain('symmetric', r['corners'][0], r['corners'][2], pc)     # il centro sta in mezzo alla diagonale
    if nuovo:
        sketch_ops._position(sk, pc, (cx, cy))
    return {**r, 'center': pc}


def add_rectangle_3p(doc, sid: str, p1, p2, p3, construction: bool = False) -> dict:
    """Rettangolo a 3 punti (anche storto): i primi due clic sono il primo lato, il terzo dice quanto è largo
    (e da che parte)."""
    sk = doc.sketch(sid)
    xa, xb = _xy_di(sk, p1), _xy_di(sk, p2)
    L = math.dist(xa, xb)
    if L < 1e-6:
        raise SketchError('I due punti del primo lato coincidono.')
    ux, uy = (xb[0] - xa[0]) / L, (xb[1] - xa[1]) / L
    nx, ny = -uy, ux
    x3 = _xy_di(sk, p3)
    w = (x3[0] - xb[0]) * nx + (x3[1] - xb[1]) * ny
    if abs(w) < 1e-6:
        raise SketchError('Il rettangolo ha bisogno di una larghezza: il terzo punto è sul primo lato.')
    pa, xa, nuovo_a = sketch_ops._point_ref(sk, p1)
    pb, xb, _ = sketch_ops._point_ref(sk, p2)
    pc = sk.point(xb[0] + nx * w, xb[1] + ny * w)
    pd = sk.point(xa[0] + nx * w, xa[1] + ny * w)
    giro = [pa, pb, pc, pd]
    lati = []
    for i in range(4):
        lid = sk.line(giro[i], giro[(i + 1) % 4], construction=bool(construction))
        sk.entities[lid]['label'] = f'lato {lid}'
        lati.append(lid)
    for i in range(3):
        sk.constrain('perpendicular', lati[i], lati[i + 1], auto=True)
    sk.dimension('length', lati[0], value=_r(L))
    sk.dimension('length', lati[1], value=_r(abs(w)))
    hv = sketch_ops._snap_hv(xa, xb)
    if hv:
        sk.constrain(hv, lati[0], auto=True)
    else:
        # storto: l'angolo del primo lato dall'orizzontale, con una guida orizzontale corta (come «100<30»)
        q = sk.point(xa[0] + 20, xa[1], construction=True)
        g = sk.line(pa, q, construction=True)
        sk.constrain('horizontal', g)
        sk.dimension('length', g, value=20)
        sk.dimension('angle', g, lati[0], value=_r(math.degrees(math.atan2(uy, ux))))
    if nuovo_a:
        sketch_ops._position(sk, pa, xa)
    return {'lines': lati, 'corners': giro}


def add_rectangle_rounded(doc, sid: str, p0, p1, r, construction: bool = False) -> dict:
    """Rettangolo con gli angoli raccordati: due angoli opposti (del fuori tutto) e il raggio. Quote: larghezza e
    altezza fuori tutto, il raggio (uno: gli altri tre sono uguali), la posizione dall'origine."""
    sk = doc.sketch(sid)
    r = float(r)
    a, b = _xy_di(sk, p0), _xy_di(sk, p1)
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    W, H = x1 - x0, y1 - y0
    if W < 1e-6 or H < 1e-6:
        raise SketchError('Il rettangolo ha bisogno di larghezza e altezza.')
    if r <= 0:
        raise SketchError('Il raggio dei raccordi deve essere maggiore di zero.')
    if 2 * r >= min(W, H) - 1e-6:
        raise SketchError(f'Raggio troppo grande: con {min(W, H):g} mm di lato il raggio sta sotto {min(W, H) / 2:g}.')
    P = sk.point
    b1, b2 = P(x0 + r, y0), P(x1 - r, y0)
    r1, r2 = P(x1, y0 + r), P(x1, y1 - r)
    t1, t2 = P(x1 - r, y1), P(x0 + r, y1)
    l1, l2 = P(x0, y1 - r), P(x0, y0 + r)
    centri = [P(x1 - r, y0 + r), P(x1 - r, y1 - r), P(x0 + r, y1 - r), P(x0 + r, y0 + r)]
    costr = bool(construction)
    sotto, destro = sk.line(b1, b2, construction=costr, label='lato sotto'), sk.line(r1, r2, construction=costr, label='lato destro')
    sopra, sinistro = sk.line(t1, t2, construction=costr, label='lato sopra'), sk.line(l1, l2, construction=costr, label='lato sinistro')
    archi = [sk.arc(centri[0], b2, r1, construction=costr), sk.arc(centri[1], r2, t1, construction=costr),
             sk.arc(centri[2], t2, l1, construction=costr), sk.arc(centri[3], l2, b1, construction=costr)]
    for lid, t in ((sotto, 'horizontal'), (destro, 'vertical'), (sopra, 'horizontal'), (sinistro, 'vertical')):
        sk.constrain(t, lid, auto=True)
    vicini = [(sotto, destro), (destro, sopra), (sopra, sinistro), (sinistro, sotto)]
    for arco, (la, lb) in zip(archi, vicini):
        sk.constrain('tangent', la, arco, auto=True)
        sk.constrain('tangent', lb, arco, auto=True)
    sk.dimension('radius', archi[3], value=_r(r))
    for arco in archi[:3]:
        sk.constrain('equal', arco, archi[3], auto=True)
    sk.dimension('hdistance', l2, r1, value=_r(W))          # fuori tutto
    sk.dimension('vdistance', b1, t2, value=_r(H))
    sk.dimension('hdistance', ORIGIN, l2, value=_r(x0))
    sk.dimension('vdistance', ORIGIN, b1, value=_r(y0))
    return {'lines': [sotto, destro, sopra, sinistro], 'arcs': archi}


# ------------------------------------------------------------------------------- cerchi
def _per_tre(p1, p2, p3):
    (x1, y1), (x2, y2), (x3, y3) = p1, p2, p3
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    scala = max(math.dist(p1, p2), math.dist(p2, p3), math.dist(p1, p3), 1e-9)
    if abs(d) < 1e-9 * scala * scala:
        raise SketchError('I tre punti sono in fila: per tre punti in fila non passa un cerchio.')
    ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / d
    uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / d
    return (ux, uy), math.hypot(x1 - ux, y1 - uy)


def add_circle_3p(doc, sid: str, p1, p2, p3, construction: bool = False) -> str:
    """Cerchio per 3 punti. I punti cliccati che c'erano già (spigoli, centri, agganci) restano sul cerchio: se si
    spostano, il cerchio li segue. Gli altri servono solo a disegnarlo: il cerchio ha la sua quota e la posizione."""
    sk = doc.sketch(sid)
    pts = [p1, p2, p3]
    xy = [_xy_di(sk, p) for p in pts]
    for i, j in ((0, 1), (1, 2), (0, 2)):
        if math.dist(xy[i], xy[j]) < 1e-6:
            raise SketchError('Due dei tre punti coincidono: servono tre punti diversi.')
    (cx, cy), R = _per_tre(*xy)
    legati = [sketch_ops._point_ref(sk, p)[0] for p in pts if isinstance(p, (str, dict))]
    pc = sk.point(cx, cy)
    cid = sk.circle(pc, R, construction=bool(construction))
    for p in legati:
        sk.constrain('on_line', p, cid)
    if len(legati) < 3:
        sk.dimension('diameter', cid, value=_r(2 * R))
    if len(legati) < 2:
        sketch_ops._position(sk, pc, (cx, cy))
    return cid


def _rette(doc, sk, linee):
    """Ogni linea come retta: (normale, offset) con n·p = d, e i suoi due estremi."""
    pts = _solved_xy(doc, sk)
    out = []
    for lid in linee:
        e = sk.entities.get(lid)
        if not e or e['kind'] != 'line':
            raise SketchError('Per il cerchio tangente clicca delle linee.')
        a, b = pts.get(e['a'], (sk.entities[e['a']]['x'], sk.entities[e['a']]['y'])), \
            pts.get(e['b'], (sk.entities[e['b']]['x'], sk.entities[e['b']]['y']))
        L = math.dist(a, b)
        if L < 1e-9:
            raise SketchError('Una delle linee è lunga zero.')
        n = (-(b[1] - a[1]) / L, (b[0] - a[0]) / L)
        out.append((n, n[0] * a[0] + n[1] * a[1], a, b))
    return out


def _risolvi2(n1, n2, d1, d2):
    det = n1[0] * n2[1] - n1[1] * n2[0]
    if abs(det) < 1e-12:
        return None
    return ((d1 * n2[1] - d2 * n1[1]) / det, (n1[0] * d2 - n2[0] * d1) / det)


def tangent_circle_geometry(doc, sid: str, linee: list, r=None, vicino=None, clic=None) -> tuple:
    """Il cerchio tangente alle linee: ((cx, cy), raggio). Con 2 linee il raggio è scritto e il mouse (vicino) dice
    in quale dei quattro angoli va; con 3 linee il raggio viene da sé e si sceglie, tra i cerchi possibili, quello
    che tocca le linee più vicino ai punti cliccati (clic)."""
    sk = doc.sketch(sid)
    if len(set(linee)) != len(linee):
        raise SketchError('Clicca linee diverse.')
    rette = _rette(doc, sk, linee)
    if len(linee) == 2:
        (n1, d1, a1, _), (n2, d2, a2, _) = rette
        v = vicino or a1
        s1 = 1 if n1[0] * v[0] + n1[1] * v[1] - d1 >= 0 else -1
        s2 = 1 if n2[0] * v[0] + n2[1] * v[1] - d2 >= 0 else -1
        if abs(n1[0] * n2[1] - n1[1] * n2[0]) < 1e-9:
            # parallele: il cerchio sta in mezzo, il diametro è la distanza tra le linee
            dist = abs(n1[0] * a2[0] + n1[1] * a2[1] - d1)
            if dist < 1e-6:
                raise SketchError('Le due linee sono una sopra l’altra: non c’è posto per un cerchio.')
            dm = d1 + (n1[0] * a2[0] + n1[1] * a2[1] - d1) / 2
            t = (v[0] * n1[1] - v[1] * n1[0])                   # dove sta il mouse lungo le linee
            return (n1[0] * dm + n1[1] * t, n1[1] * dm - n1[0] * t), dist / 2
        r = float(r or 0)
        if r <= 0:
            raise SketchError('Scrivi il raggio del cerchio.')
        c = _risolvi2(n1, n2, d1 + s1 * r, d2 + s2 * r)
        return c, r
    if len(linee) != 3:
        raise SketchError('Il cerchio tangente si fa con 2 o 3 linee.')
    candidati = []
    for s in itertools.product((1, -1), repeat=3):
        # n_i·c - s_i·r = d_i: tre equazioni in cx, cy, r
        M = [[n[0], n[1], -si] for (n, _, _, _), si in zip(rette, s)]
        dv = [d for (_, d, _, _) in rette]
        det = (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1]) - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
               + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))
        if abs(det) < 1e-12:
            continue
        sol = []
        for k in range(3):
            Mk = [row[:] for row in M]
            for i in range(3):
                Mk[i][k] = dv[i]
            sol.append((Mk[0][0] * (Mk[1][1] * Mk[2][2] - Mk[1][2] * Mk[2][1]) - Mk[0][1] * (Mk[1][0] * Mk[2][2] - Mk[1][2] * Mk[2][0])
                        + Mk[0][2] * (Mk[1][0] * Mk[2][1] - Mk[1][1] * Mk[2][0])) / det)
        cx, cy, rr = sol
        if rr <= 1e-6:
            continue
        tocchi = [(cx - si * rr * n[0], cy - si * rr * n[1]) for (n, _, _, _), si in zip(rette, s)]
        if clic:
            costo = sum(math.dist(t, q) for t, q in zip(tocchi, clic))
        else:
            costo = math.dist((cx, cy), vicino or (0, 0))
        candidati.append((costo, (cx, cy), rr))
    if not candidati:
        raise SketchError('Nessun cerchio tocca queste tre linee (sono parallele?).')
    _, c, rr = min(candidati, key=lambda x: x[0])
    return c, rr


def add_circle_tangent(doc, sid: str, linee: list, r=None, vicino=None, clic=None, construction: bool = False) -> str:
    """Cerchio tangente a 2 linee (raggio scritto) o a 3 linee: tangenze vere, segue le linee se si spostano."""
    sk = doc.sketch(sid)
    (cx, cy), rr = tangent_circle_geometry(doc, sid, linee, r, vicino, clic)
    pc = sk.point(cx, cy)
    cid = sk.circle(pc, rr, construction=bool(construction))
    for lid in linee:
        sk.constrain('tangent', lid, cid)
    rette = _rette(doc, sk, linee)
    parallele = len(linee) == 2 and abs(rette[0][0][0] * rette[1][0][1] - rette[0][0][1] * rette[1][0][0]) < 1e-9
    if len(linee) == 2 and not parallele:
        sk.dimension('radius', cid, value=_r(rr))
    elif parallele:
        sketch_ops._position(sk, pc, (cx, cy))          # tra due parallele il cerchio scorre: resta dov'è
    return cid


add_rectangle_center = sketch_ops.guarded(add_rectangle_center)
add_rectangle_3p = sketch_ops.guarded(add_rectangle_3p)
add_rectangle_rounded = sketch_ops.guarded(add_rectangle_rounded)
add_circle_3p = sketch_ops.guarded(add_circle_3p)
add_circle_tangent = sketch_ops.guarded(add_circle_tangent)
