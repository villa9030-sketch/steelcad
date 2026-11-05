"""Linee guida pronte (05/11, idee da SolidCraft: sketch.construction_line.*). Un solo comando «Linea guida», con
dentro i modi di farla:

- orizzontale o verticale per un punto;
- parallela a una linea, alla distanza scritta (la quota resta: cambiandola la guida si sposta);
- perpendicolare a una linea, per un punto;
- a un angolo scritto da una linea, per un punto;
- bisettrice di due linee (in mezzo all'angolo);
- tangente a un cerchio (o a un arco) da un punto;
- tangente comune a due cerchi.

Ogni guida è una linea di costruzione (tratteggiata, non si taglia) con vincoli veri: se si sposta o si gira la
linea (o il cerchio) di partenza, la guida segue. Le lunghezze delle guide sono quote di servizio, non si vedono
(come per le altre linee di costruzione). Gli aiuti che servono ai vincoli (il raggio fino al punto di tangenza, il
piede della parallela) sono anche loro di costruzione.

La parte geometrica (`geometria`) è pura: serve sia a fare la guida sia all'anteprima del comando.
"""
from __future__ import annotations

import math

from cad_engine.errors import SketchError

from app import sketch_ops
from app.sketch_edit import _solved_xy

_r = sketch_ops._r
MODI = ('hv', 'parallela', 'perpendicolare', 'angolo', 'bisettrice', 'tangente', 'tangente2')


# ------------------------------------------------------------------------------- lettura dello sketch
def _linea(doc, sk, lid, pts=None):
    e = sk.entities.get(lid)
    if not e or e['kind'] != 'line':
        raise SketchError('Clicca una linea.')
    pts = pts or _solved_xy(doc, sk)
    a, b = pts[e['a']], pts[e['b']]
    if math.dist(a, b) < 1e-9:
        raise SketchError('Questa linea è lunga zero.')
    return e, a, b


def _tondo(doc, sk, cid):
    """Un cerchio o un arco: (centro id, (cx, cy), raggio)."""
    e = sk.entities.get(cid)
    if not e or e['kind'] not in ('circle', 'arc'):
        raise SketchError('Clicca un cerchio o un arco.')
    from cad_engine.sketch import solve
    try:
        ss = solve(sk, doc.resolved_parameters())
        pts = ss.points
        r = ss.circles[cid][1] if cid in ss.circles else ss.arcs[cid][3]
    except (SketchError, KeyError):
        pts = {k: (v['x'], v['y']) for k, v in sk.entities.items() if v['kind'] == 'point'}
        r = e['r'] if e['kind'] == 'circle' else math.dist(pts[e['center']], pts[e['start']])
    return e['center'], pts[e['center']], float(r)


def _unit(a, b):
    L = math.dist(a, b)
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


def _xy(sk, p, pts):
    if isinstance(p, str):
        if p not in pts:
            raise SketchError('Questo punto non c’è più.')
        return tuple(pts[p])
    if isinstance(p, dict):
        return tuple(float(v) for v in p.get('xy', (0, 0)))
    return float(p[0]), float(p[1])


def _dist_retta(p, a, b):
    u = _unit(a, b)
    return (p[0] - a[0]) * -u[1] + (p[1] - a[1]) * u[0]           # con segno: + a sinistra di a→b


# ------------------------------------------------------------------------------- geometria (anche per l'anteprima)
def tangenti_punto(p, c, r):
    """I due punti dove le tangenti da p toccano il cerchio (c, r)."""
    d = math.dist(p, c)
    if d < r - 1e-9:
        raise SketchError('Il punto è dentro il cerchio: da lì non parte nessuna tangente.')
    if d < r + 1e-9:
        return [tuple(p)]
    base = math.atan2(p[1] - c[1], p[0] - c[0])
    a = math.acos(r / d)
    return [(c[0] + r * math.cos(base + s * a), c[1] + r * math.sin(base + s * a)) for s in (1, -1)]


def tangenti_comuni(c1, r1, c2, r2):
    """Le tangenti comuni a due cerchi: [(t1, t2), …] (fino a 4: le due esterne, poi le due interne)."""
    d = math.dist(c1, c2)
    if d < 1e-9:
        raise SketchError('I due cerchi hanno lo stesso centro: non c’è una tangente comune.')
    ux, uy = (c2[0] - c1[0]) / d, (c2[1] - c1[1]) / d
    out = []
    for s in (1, -1):                       # s = 1 esterne, s = -1 interne (incrociate)
        k = (r1 - s * r2) / d
        if abs(k) > 1 + 1e-12:
            continue
        k = max(-1.0, min(1.0, k))
        h = math.sqrt(max(0.0, 1 - k * k))
        for t in (1, -1):
            nx, ny = ux * k - t * h * uy, uy * k + t * h * ux
            out.append(((c1[0] + r1 * nx, c1[1] + r1 * ny), (c2[0] + s * r2 * nx, c2[1] + s * r2 * ny)))
    if not out:
        raise SketchError('Un cerchio è dentro l’altro: non c’è una tangente comune.')
    return out


def _seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy or 1.0
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def geometria(doc, sid: str, come: str, dati: dict) -> dict:
    """Dove va la guida: {'a': (x, y), 'b': (x, y), …} più quello che serve per farla (verso, lato, scelta)."""
    sk = doc.sketch(sid)
    pts = _solved_xy(doc, sk)
    mouse = dati.get('mouse')
    mouse = (float(mouse[0]), float(mouse[1])) if mouse else None
    if come == 'hv':
        p = _xy(sk, dati['punto'], pts)
        verso = dati.get('verso')
        q = mouse or (p[0] + 50, p[1])
        if verso not in ('h', 'v'):
            verso = 'h' if abs(q[0] - p[0]) >= abs(q[1] - p[1]) else 'v'
        L = float(dati.get('lunghezza') or 0) or max(2 * (abs(q[0] - p[0]) if verso == 'h' else abs(q[1] - p[1])), 20.0)
        u = (1.0, 0.0) if verso == 'h' else (0.0, 1.0)
        return {'a': (p[0] - u[0] * L / 2, p[1] - u[1] * L / 2), 'b': (p[0] + u[0] * L / 2, p[1] + u[1] * L / 2),
                'verso': verso, 'lunghezza': L}
    if come == 'parallela':
        _, a, b = _linea(doc, sk, dati['linea'], pts)
        d = float(dati.get('distanza') or 0)
        if d <= 0:
            raise SketchError('Scrivi a che distanza va la guida.')
        lato = dati.get('lato')
        if lato not in (1, -1):
            lato = 1 if mouse is None or _dist_retta(mouse, a, b) >= 0 else -1
        u = _unit(a, b)
        n = (-u[1] * lato * d, u[0] * lato * d)
        return {'a': (a[0] + n[0], a[1] + n[1]), 'b': (b[0] + n[0], b[1] + n[1]), 'lato': lato, 'distanza': d}
    if come == 'perpendicolare':
        _, a, b = _linea(doc, sk, dati['linea'], pts)
        p = _xy(sk, dati['punto'], pts)
        u = _unit(a, b)
        t = (p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1]
        f = (a[0] + u[0] * t, a[1] + u[1] * t)                        # il piede sulla linea
        if math.dist(p, f) > 1e-6:
            return {'a': f, 'b': (2 * p[0] - f[0], 2 * p[1] - f[1]), 'sulla': False}
        L = float(dati.get('lunghezza') or 0) or max(math.dist(a, b) / 2, 20.0)
        n = (-u[1], u[0])
        if mouse and (mouse[0] - p[0]) * n[0] + (mouse[1] - p[1]) * n[1] < 0:
            n = (-n[0], -n[1])
        return {'a': (p[0] - n[0] * L / 2, p[1] - n[1] * L / 2), 'b': (p[0] + n[0] * L / 2, p[1] + n[1] * L / 2),
                'sulla': True, 'lunghezza': L}
    if come == 'angolo':
        _, a, b = _linea(doc, sk, dati['linea'], pts)
        p = _xy(sk, dati['punto'], pts)
        g = float(dati.get('angolo') or 0)
        if not (0 < g < 180):
            raise SketchError('Scrivi un angolo tra 0 e 180 gradi (0 e 180 sono la parallela).')
        u = _unit(a, b)
        verso = dati.get('verso')
        if verso not in (1, -1):
            verso = 1
            if mouse:
                cand = []
                for s in (1, -1):
                    t = math.radians(s * g)
                    w = (u[0] * math.cos(t) - u[1] * math.sin(t), u[0] * math.sin(t) + u[1] * math.cos(t))
                    m = (mouse[0] - p[0], mouse[1] - p[1])
                    cand.append((abs(m[0] * w[1] - m[1] * w[0]), s))      # la retta più vicina al mouse
                verso = min(cand)[1]
        t = math.radians(verso * g)
        w = (u[0] * math.cos(t) - u[1] * math.sin(t), u[0] * math.sin(t) + u[1] * math.cos(t))
        L = float(dati.get('lunghezza') or 0) or (max(2 * math.dist(p, mouse), 20.0) if mouse else max(math.dist(a, b), 20.0))
        return {'a': (p[0] - w[0] * L / 2, p[1] - w[1] * L / 2), 'b': (p[0] + w[0] * L / 2, p[1] + w[1] * L / 2),
                'verso': verso, 'angolo': g, 'lunghezza': L}
    if come == 'bisettrice':
        l1, l2 = dati['linee']
        if l1 == l2:
            raise SketchError('Clicca due linee diverse.')
        _, a1, b1 = _linea(doc, sk, l1, pts)
        _, a2, b2 = _linea(doc, sk, l2, pts)
        u1, u2 = _unit(a1, b1), _unit(a2, b2)
        det = u1[0] * u2[1] - u1[1] * u2[0]
        if abs(det) < 1e-9:
            raise SketchError('Le due linee sono parallele: la guida in mezzo si fa con «parallela», a metà distanza.')
        t = ((a2[0] - a1[0]) * u2[1] - (a2[1] - a1[1]) * u2[0]) / det
        i = (a1[0] + u1[0] * t, a1[1] + u1[1] * t)
        dirs = []
        for w in ((u1[0] + u2[0], u1[1] + u2[1]), (u1[0] - u2[0], u1[1] - u2[1])):
            n = math.hypot(*w)
            if n > 1e-9:
                dirs.append((w[0] / n, w[1] / n))
        w = dirs[0]
        if mouse and len(dirs) == 2 and math.dist(mouse, i) > 1e-9:
            m = (mouse[0] - i[0], mouse[1] - i[1])
            w = min(dirs, key=lambda d: abs(m[0] * d[1] - m[1] * d[0]))
        L = float(dati.get('lunghezza') or 0) or (max(2 * math.dist(i, mouse), 20.0) if mouse else
                                                  max(math.dist(a1, b1), math.dist(a2, b2), 20.0))
        return {'a': (i[0] - w[0] * L / 2, i[1] - w[1] * L / 2), 'b': (i[0] + w[0] * L / 2, i[1] + w[1] * L / 2),
                'incrocio': i, 'lunghezza': L}
    if come == 'tangente':
        p = _xy(sk, dati['punto'], pts)
        _, c, r = _tondo(doc, sk, dati['cerchio'])
        tocchi = tangenti_punto(p, c, r)
        if len(tocchi) == 1:                                  # il punto è sul cerchio: la tangente lì
            n = _unit(c, p)
            w = (-n[1], n[0])
            L = float(dati.get('lunghezza') or 0) or max(r, 20.0)
            return {'a': (p[0] - w[0] * L / 2, p[1] - w[1] * L / 2), 'b': (p[0] + w[0] * L / 2, p[1] + w[1] * L / 2),
                    'sul_cerchio': True, 'lunghezza': L}
        k = dati.get('scelta')
        if k not in (0, 1):
            k = 0 if mouse is None else min((0, 1), key=lambda j: _seg_dist(mouse, p, tocchi[j]))
        return {'a': p, 'b': tocchi[k], 'scelta': k, 'sul_cerchio': False}
    if come == 'tangente2':
        c1id, c2id = dati['cerchi']
        if c1id == c2id:
            raise SketchError('Clicca due cerchi diversi.')
        _, c1, r1 = _tondo(doc, sk, c1id)
        _, c2, r2 = _tondo(doc, sk, c2id)
        tutte = tangenti_comuni(c1, r1, c2, r2)
        k = dati.get('scelta')
        if not isinstance(k, int) or not (0 <= k < len(tutte)):
            k = 0 if mouse is None else min(range(len(tutte)), key=lambda j: _seg_dist(mouse, *tutte[j]))
        return {'a': tutte[k][0], 'b': tutte[k][1], 'scelta': k, 'tutte': tutte}
    raise SketchError('Modo di linea guida sconosciuto.')


# ------------------------------------------------------------------------------- la guida, coi vincoli
def _guida(sk, a, b, label):
    pa, pb = sk.point(*a), sk.point(*b)
    lid = sk.line(pa, pb, construction=True, label=label)
    return lid, pa, pb


def _punto(sk, p):
    """Il punto da cui passa la guida: quello cliccato (resta legato) o uno nuovo, messo con la sua posizione."""
    pid, xy, nuovo = sketch_ops._point_ref(sk, p)
    if nuovo and not isinstance(p, dict):
        sketch_ops._position(sk, pid, xy)
    return pid


def add_guide(doc, sid: str, come: str, dati: dict) -> str:
    """Fa la linea guida; ritorna il suo id."""
    if come not in MODI:
        raise SketchError('Modo di linea guida sconosciuto.')
    sk = doc.sketch(sid)
    g = geometria(doc, sid, come, dati)
    a, b = g['a'], g['b']
    if math.dist(a, b) < 1e-6:
        raise SketchError('La guida verrebbe lunga zero.')
    C = sk.constrain
    if come == 'hv':
        p = _punto(sk, dati['punto'])
        lid, pa, pb = _guida(sk, a, b, 'guida orizzontale' if g['verso'] == 'h' else 'guida verticale')
        C('symmetric', pa, pb, p, auto=True)
        C('horizontal' if g['verso'] == 'h' else 'vertical', lid, auto=True)
        sk.dimension('length', lid, value=_r(g['lunghezza']))
        return lid
    if come == 'parallela':
        L = dati['linea']
        e = sk.entities[L]
        lid, pa, pb = _guida(sk, a, b, 'guida parallela')
        piede = sk.line(e['a'], pa, construction=True, label='piede della guida')
        C('parallel', lid, L, auto=True)
        C('equal', lid, L, auto=True)
        C('perpendicular', piede, L, auto=True)
        sk.dimension('pldistance', pa, L, value=_r(g['distanza']))     # la quota che si vede e si cambia
        return lid
    if come == 'perpendicolare':
        L = dati['linea']
        p = _punto(sk, dati['punto'])
        lid, pa, pb = _guida(sk, a, b, 'guida perpendicolare')
        C('perpendicular', lid, L, auto=True)
        C('symmetric', pa, pb, p, auto=True)
        if g['sulla']:
            sk.dimension('length', lid, value=_r(g['lunghezza']))
        else:
            C('on_line', pa, L, auto=True)                  # parte dalla linea, passa dal punto
        return lid
    if come == 'angolo':
        L = dati['linea']
        p = _punto(sk, dati['punto'])
        lid, pa, pb = _guida(sk, a, b, f'guida a {g["angolo"]:g}°')
        C('symmetric', pa, pb, p, auto=True)
        sk.dimension('length', lid, value=_r(g['lunghezza']))
        # l'angolo con segno va dalla prima linea alla seconda: il verso sceglie l'ordine, il numero resta positivo
        if g['verso'] == 1:
            sk.dimension('angle', L, lid, value=_r(g['angolo']))
        else:
            sk.dimension('angle', lid, L, value=_r(g['angolo']))
        return lid
    if come == 'bisettrice':
        l1, l2 = dati['linee']
        e1, e2 = sk.entities[l1], sk.entities[l2]
        pts = _solved_xy(doc, sk)
        comune = ({e1['a'], e1['b']} & {e2['a'], e2['b']})
        if comune:
            i = next(iter(comune))
        else:
            i = sk.point(*g['incrocio'], construction=True)
            C('on_line', i, l1, auto=True)
            C('on_line', i, l2, auto=True)
        lid, pa, pb = _guida(sk, a, b, 'bisettrice')
        C('symmetric', pa, pb, i, auto=True)
        sk.dimension('length', lid, value=_r(g['lunghezza']))
        # la bisettrice è l'asse dello specchio che porta la prima linea sulla seconda: la punta della prima,
        # specchiata, sta sulla seconda
        lontano = max((e1['a'], e1['b']), key=lambda q: math.dist(pts[q], g['incrocio']))
        A = pts[lontano]
        w = _unit(a, b)
        t = (A[0] - g['incrocio'][0]) * w[0] + (A[1] - g['incrocio'][1]) * w[1]
        f = (g['incrocio'][0] + w[0] * t, g['incrocio'][1] + w[1] * t)
        specchio = sk.point(2 * f[0] - A[0], 2 * f[1] - A[1], construction=True)
        C('symmetric', lontano, specchio, lid, auto=True)
        C('on_line', specchio, l2, auto=True)
        return lid
    if come == 'tangente':
        cid = dati['cerchio']
        centro = sk.entities[cid]['center']
        p = _punto(sk, dati['punto'])
        if g['sul_cerchio']:
            lid, pa, pb = _guida(sk, a, b, 'guida tangente')
            raggio = sk.line(centro, p, construction=True, label='raggio del punto di tangenza')
            C('symmetric', pa, pb, p, auto=True)
            C('perpendicular', lid, raggio, auto=True)
            sk.dimension('length', lid, value=_r(g['lunghezza']))
            return lid
        t = sk.point(*b)
        lid = sk.line(p, t, construction=True, label='guida tangente')
        raggio = sk.line(centro, t, construction=True, label='raggio del punto di tangenza')
        C('on_line', t, cid, auto=True)
        C('perpendicular', lid, raggio, auto=True)
        return lid
    # tangente comune
    c1id, c2id = dati['cerchi']
    lid, t1, t2 = _guida(sk, a, b, 'tangente comune')
    r1 = sk.line(sk.entities[c1id]['center'], t1, construction=True, label='raggio del punto di tangenza')
    r2 = sk.line(sk.entities[c2id]['center'], t2, construction=True, label='raggio del punto di tangenza')
    C('on_line', t1, c1id, auto=True)
    C('on_line', t2, c2id, auto=True)
    C('perpendicular', lid, r1, auto=True)
    C('perpendicular', lid, r2, auto=True)
    return lid


add_guide = sketch_ops.guarded(add_guide)
