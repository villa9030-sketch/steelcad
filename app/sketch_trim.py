"""Taglia e Allunga, come in AutoCAD (modalità rapida).

- Taglia: clic sul pezzo da togliere di una linea, un cerchio o un arco. Si taglia fino alle intersezioni
  più vicine con tutto il resto del disegno (linee, guide, bordi del pezzo, cerchi, archi), da una parte e
  dall'altra del clic. Senza intersezioni l'oggetto si cancella. Un cerchio tagliato diventa un arco.
- Allunga: clic vicino all'estremità di una linea; quell'estremità arriva alla prima cosa che incontra
  andando dritta.

I punti nuovi restano legati alla linea che li ha tagliati (vincolo "sulla linea"), così se sposti quella
linea il taglio la segue. Le quote che non valgono più (la lunghezza della linea tagliata, la posizione
del punto allungato) si tolgono.
"""
from __future__ import annotations

import math

from cad_engine.errors import SketchError
from cad_engine.sketch import solve
from cad_engine.sketch.model import ORIGIN

from app import sketch_ops
from app.sketch_edit import _sync

EPS = 1e-7
TAU = 2 * math.pi


# ------------------------------------------------------------------------------- geometria
def _geom(doc, sk):
    """Il disegno com'è adesso (risolto): punti, linee, cerchi, archi."""
    _sync(doc, sk)
    try:
        ss = solve(sk, doc.resolved_parameters())
        raggi = {k: r for k, (_, r) in ss.circles.items()}
    except Exception:  # noqa: BLE001
        raggi = {}
    P = {k: (e['x'], e['y']) for k, e in sk.entities.items() if e['kind'] == 'point'}
    G = {}
    for k, e in sk.entities.items():
        if e['kind'] == 'line':
            G[k] = ('line', P[e['a']], P[e['b']])
        elif e['kind'] == 'circle':
            G[k] = ('circle', P[e['center']], raggi.get(k, e['r']))
        elif e['kind'] == 'arc':
            c, a, b = P[e['center']], P[e['start']], P[e['end']]
            t0 = math.atan2(a[1] - c[1], a[0] - c[0])
            t1 = math.atan2(b[1] - c[1], b[0] - c[0])
            while t1 <= t0:
                t1 += TAU
            G[k] = ('arc', c, math.hypot(a[0] - c[0], a[1] - c[1]), t0, t1)
    return P, G


def _ang_in(t, t0, t1):
    while t < t0:
        t += TAU
    while t >= t0 + TAU:
        t -= TAU
    return t <= t1 + EPS


def _line_hits(a, b, other, infinita=False):
    """Intersezioni della linea a→b (parametro t) con un altro oggetto. Con infinita=True la linea a→b si
    considera prolungata (per l'Allunga), l'altro oggetto mai."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    out = []
    if other[0] == 'line':
        c, d = other[1], other[2]
        ex, ey = d[0] - c[0], d[1] - c[1]
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            return out
        t = ((c[0] - a[0]) * ey - (c[1] - a[1]) * ex) / den
        s = ((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) / den
        if -EPS <= s <= 1 + EPS:
            out.append(t)
    else:
        c, r = other[1], other[2]
        fx, fy = a[0] - c[0], a[1] - c[1]
        A = dx * dx + dy * dy
        B = 2 * (fx * dx + fy * dy)
        C = fx * fx + fy * fy - r * r
        disc = B * B - 4 * A * C
        if disc < 0 or A < 1e-18:
            return out
        for sg in (-1, 1):
            t = (-B + sg * math.sqrt(disc)) / (2 * A)
            if other[0] == 'arc':
                p = (a[0] + dx * t, a[1] + dy * t)
                if not _ang_in(math.atan2(p[1] - c[1], p[0] - c[0]), other[3], other[4]):
                    continue
            out.append(t)
    return out if infinita else [t for t in out if -EPS <= t <= 1 + EPS]


def _round_hits(c, r, other):
    """Angoli dove un cerchio (c, r) incontra un altro oggetto."""
    out = []
    if other[0] == 'line':
        a, b = other[1], other[2]
        for t in _line_hits(a, b, ('circle', c, r)):
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            out.append(math.atan2(p[1] - c[1], p[0] - c[0]))
        return out
    c2, r2 = other[1], other[2]
    d = math.hypot(c2[0] - c[0], c2[1] - c[1])
    if d < 1e-12 or d > r + r2 + 1e-9 or d < abs(r - r2) - 1e-9:
        return out
    aa = (r * r - r2 * r2 + d * d) / (2 * d)
    h = math.sqrt(max(0.0, r * r - aa * aa))
    mx, my = c[0] + aa * (c2[0] - c[0]) / d, c[1] + aa * (c2[1] - c[1]) / d
    for sg in ((-1, 1) if h > 1e-12 else (1,)):
        p = (mx + sg * h * (c2[1] - c[1]) / d, my - sg * h * (c2[0] - c[0]) / d)
        if other[0] == 'arc' and not _ang_in(math.atan2(p[1] - c2[1], p[0] - c2[0]), other[3], other[4]):
            continue
        out.append(math.atan2(p[1] - c[1], p[0] - c[0]))
    return out


# ------------------------------------------------------------------------------- taglia
def _trim_plan(doc, sk, eid, click):
    if eid not in sk.entities or sk.entities[eid]['kind'] not in ('line', 'circle', 'arc'):
        raise SketchError('Clicca una linea, un cerchio o un arco da tagliare.')
    if sk.entities[eid].get('ref'):
        raise SketchError('I bordi arancio sono il pezzo vero: non si cancellano né si modificano (servono per agganciarsi e per chiudere i contorni).')
    P, G = _geom(doc, sk)
    me = G[eid]
    altri = [(k, g) for k, g in G.items() if k != eid]
    cx, cy = float(click[0]), float(click[1])
    if me[0] == 'line':
        a, b = me[1], me[2]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy or 1
        tc = ((cx - a[0]) * dx + (cy - a[1]) * dy) / L2
        tagli = sorted({(round(t, 9), k) for k, g in altri for t in _line_hits(a, b, g) if EPS < t < 1 - EPS})
        sx = max((x for x in tagli if x[0] < tc), default=None)
        dx_ = min((x for x in tagli if x[0] > tc), default=None)
        t0 = sx[0] if sx else 0.0
        t1 = dx_[0] if dx_ else 1.0
        at = lambda t: (a[0] + dx * t, a[1] + dy * t)  # noqa: E731
        return {'kind': 'line', 'eid': eid, 'left': sx, 'right': dx_, 'at': at,
                'remove': [list(at(t0)), list(at(t1))], 'all': not tagli}
    c, r = me[1], me[2]
    tc = math.atan2(cy - c[1], cx - c[0])
    angoli = sorted({round(t % TAU, 9): k for k, g in altri for t in _round_hits(c, r, g)}.items())
    if me[0] == 'circle':
        if len(angoli) < 2:
            return {'kind': 'circle', 'eid': eid, 'all': True, 'remove': _arc_pts(c, r, 0, TAU)}
        tcn = tc % TAU
        dopo = next((x for x in angoli if x[0] > tcn), angoli[0])
        prima = next((x for x in reversed(angoli) if x[0] < tcn), angoli[-1])
        tb = dopo[0] if dopo[0] > tcn else dopo[0] + TAU
        ta = prima[0] if prima[0] < tcn else prima[0] - TAU
        return {'kind': 'circle', 'eid': eid, 'all': False, 'c': c, 'r': r, 'keep': (tb, ta + TAU),
                'cut': (dopo[1], prima[1]), 'remove': _arc_pts(c, r, ta, tb)}
    # arco: come una linea, lungo l'angolo
    t0, t1 = me[3], me[4]
    u = lambda t: (t - t0) % TAU  # noqa: E731
    span = t1 - t0
    uc = u(tc)
    if uc > span:                                   # clic fuori dall'arco: vale l'estremo più vicino
        uc = span if uc - span < TAU - uc else 0.0
    tagli = sorted({(round(u(t), 9), k) for t, k in angoli if EPS < u(t) < span - EPS})
    sx = max((x for x in tagli if x[0] < uc), default=None)
    dx_ = min((x for x in tagli if x[0] > uc), default=None)
    ua = sx[0] if sx else 0.0
    ub = dx_[0] if dx_ else span
    return {'kind': 'arc', 'eid': eid, 'all': not tagli, 'c': c, 'r': r, 't0': t0, 'left': sx, 'right': dx_,
            'remove': _arc_pts(c, r, t0 + ua, t0 + ub)}


def _arc_pts(c, r, a0, a1, n=48):
    return [[c[0] + r * math.cos(a0 + (a1 - a0) * i / n), c[1] + r * math.sin(a0 + (a1 - a0) * i / n)] for i in range(n + 1)]


def trim_preview(doc, sid, eid, click) -> dict:
    sk = doc.sketch(sid)
    piano = _trim_plan(doc, sk, eid, click)
    return {'remove': piano['remove'], 'all': piano['all']}


def _lega(sk, pid, cutter):
    """Il punto nuovo resta sulla linea (o sul cerchio, sull'arco) che ha tagliato."""
    if cutter and sk.entities.get(cutter, {}).get('kind') in ('line', 'circle', 'arc'):
        sk.constrain('on_line', pid, cutter)


def _punto(sk, xy, cutter):
    """Il punto del taglio: se lì c'è già un punto di chi taglia (un'estremità), si usa quello; se no uno
    nuovo, legato a chi taglia."""
    e = sk.entities.get(cutter, {})
    for key in ('a', 'b', 'start', 'end'):
        pid = e.get(key)
        if pid and math.dist((sk.entities[pid]['x'], sk.entities[pid]['y']), xy) < 1e-6:
            return pid
    pid = sk.point(*xy)
    _lega(sk, pid, cutter)
    return pid


def _cleanup(sk, via_constraints=()):
    """Toglie i vincoli indicati e poi punti rimasti soli (mai l'origine) e vincoli che li usano."""
    for k in via_constraints:
        sk.constraints.pop(k, None)
    while True:
        usati = {ORIGIN}
        for e in sk.entities.values():
            for key in ('a', 'b', 'center', 'start', 'end'):
                if key in e:
                    usati.add(e[key])
        soli = [k for k, e in sk.entities.items() if e['kind'] == 'point' and k not in usati]
        for k in soli:
            del sk.entities[k]
        rotti = [k for k, c in sk.constraints.items() if any(r not in sk.entities for r in c['refs'])]
        # "sulla linea" di un punto che ora è un'estremità di quella stessa linea/arco: è già lì, è doppio
        for k, c in sk.constraints.items():
            if c['type'] == 'on_line' and k not in rotti and c['refs'][1] in sk.entities:
                e2 = sk.entities[c['refs'][1]]
                if c['refs'][0] in (e2.get('a'), e2.get('b'), e2.get('start'), e2.get('end')):
                    rotti.append(k)
        for k in rotti:
            del sk.constraints[k]
        if not soli and not rotti:
            break


def trim(doc, sid, eid, click):
    sk = doc.sketch(sid)
    piano = _trim_plan(doc, sk, eid, click)
    e = sk.entities[eid]
    if piano['all']:
        sketch_ops.delete(doc, sid, [eid])
        return
    costr = bool(e.get('construction'))
    if piano['kind'] == 'line':
        # la lunghezza della linea non vale più; restano orizzontale/verticale e le quote dei punti rimasti
        quote = [k for k, c in sk.constraints.items() if c['type'] == 'length' and c['refs'] == [eid]]
        quote += [k for k, c in sk.constraints.items() if c['type'] == 'distance' and set(c['refs']) == {e['a'], e['b']}]
        at, sx, dx_ = piano['at'], piano['left'], piano['right']
        if sx and dx_:
            p1 = _punto(sk, at(sx[0]), sx[1])
            p2 = _punto(sk, at(dx_[0]), dx_[1])
            vecchio_b = e['b']
            e['b'] = p1
            l2 = sk.line(p2, vecchio_b, construction=costr)
            if e.get('label'):
                sk.entities[l2]['label'] = f'lato {l2}'
            sk.constrain('on_line', p2, eid)          # i due pezzi restano allineati
            sk.constrain('parallel', l2, eid)
        elif sx:
            e['b'] = _punto(sk, at(sx[0]), sx[1])
        else:
            e['a'] = _punto(sk, at(dx_[0]), dx_[1])
        _cleanup(sk, quote)
        return
    c, r = piano['c'], piano['r']
    if piano['kind'] == 'circle':
        # il cerchio diventa l'arco che resta; il diametro diventa raggio
        ta, tb = piano['keep']
        dia = next((cc for cc in sk.constraints.values() if cc['type'] == 'diameter' and cc['refs'] == [eid]), None)
        # i vincoli "sul cerchio" dei punti agganciati passano all'arco (il cerchio sparisce)
        for cc in sk.constraints.values():
            if cc['type'] == 'on_line' and cc['refs'][1:] == [eid]:
                cc['_arco'] = True
        pa = _punto(sk, (c[0] + r * math.cos(ta), c[1] + r * math.sin(ta)), piano['cut'][0])
        pb = _punto(sk, (c[0] + r * math.cos(tb), c[1] + r * math.sin(tb)), piano['cut'][1])
        arco = sk.arc(e['center'], pa, pb, construction=costr)
        for k, cc in list(sk.constraints.items()):
            if cc.pop('_arco', False):
                if cc['refs'][0] in (pa, pb):
                    del sk.constraints[k]           # le estremità dell'arco ci stanno già sopra
                else:
                    cc['refs'][1] = arco
        del sk.entities[eid]
        if dia is not None:
            v = dia['value']
            sk.dimension('radius', arco, value=v / 2 if isinstance(v, (int, float)) else f'({v})/2')
        _cleanup(sk)
        return
    # arco
    t0, sx, dx_ = piano['t0'], piano['left'], piano['right']
    pt = lambda u: (c[0] + r * math.cos(t0 + u), c[1] + r * math.sin(t0 + u))  # noqa: E731
    if sx and dx_:
        p1, p2 = _punto(sk, pt(sx[0]), sx[1]), _punto(sk, pt(dx_[0]), dx_[1])
        vecchia_fine = e['end']
        e['end'] = p1
        sk.arc(e['center'], p2, vecchia_fine, construction=costr)
    elif sx:
        e['end'] = _punto(sk, pt(sx[0]), sx[1])
    else:
        e['start'] = _punto(sk, pt(dx_[0]), dx_[1])
    _cleanup(sk)


# ------------------------------------------------------------------------------- allunga
def _extend_plan(doc, sk, eid, click):
    if eid not in sk.entities or sk.entities[eid]['kind'] != 'line':
        raise SketchError('Allunga vale per le linee: clicca vicino all’estremità da allungare.')
    if sk.entities[eid].get('ref'):
        raise SketchError('I bordi arancio sono il pezzo vero: non si cancellano né si modificano (servono per agganciarsi e per chiudere i contorni).')
    P, G = _geom(doc, sk)
    e = sk.entities[eid]
    a, b = G[eid][1], G[eid][2]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy or 1
    tc = ((float(click[0]) - a[0]) * dx + (float(click[1]) - a[1]) * dy) / L2
    fine_b = tc >= 0.5                                  # l'estremità più vicina al clic
    altri = [(k, g) for k, g in G.items() if k != eid]
    if fine_b:
        cand = [(t, k) for k, g in altri for t in _line_hits(a, b, g, infinita=True) if t > 1 + 1e-6]
        hit = min(cand, default=None)
    else:
        cand = [(t, k) for k, g in altri for t in _line_hits(a, b, g, infinita=True) if t < -1e-6]
        hit = max(cand, default=None)
    if hit is None:
        raise SketchError('In quella direzione la linea non incontra niente: non c’è dove allungarla.')
    pid = e['b'] if fine_b else e['a']
    dove = (a[0] + dx * hit[0], a[1] + dy * hit[0])
    return {'eid': eid, 'pid': pid, 'to': dove, 'target': hit[1], 'from': list(b if fine_b else a)}


def extend_preview(doc, sid, eid, click) -> dict:
    piano = _extend_plan(doc, doc.sketch(sid), eid, click)
    return {'add': [piano['from'], list(piano['to'])]}


def extend(doc, sid, eid, click):
    sk = doc.sketch(sid)
    piano = _extend_plan(doc, sk, eid, click)
    pid = piano['pid']
    altri = [k for k, x in sk.entities.items() if k != eid and pid in (x.get('a'), x.get('b'), x.get('center'),
                                                                      x.get('start'), x.get('end'))]
    if pid == ORIGIN or altri:
        # l'estremità è attaccata ad altro: la linea se ne stacca con un punto suo
        nuovo = sk.point(*piano['to'])
        e = sk.entities[eid]
        e['b' if e['b'] == pid else 'a'] = nuovo
        pid = nuovo
    else:
        sk.entities[pid]['x'], sk.entities[pid]['y'] = map(float, piano['to'])
    # non valgono più: la lunghezza della linea e la posizione del punto spostato
    via = [k for k, c in sk.constraints.items()
           if (c['type'] == 'length' and c['refs'] == [eid])
           or (c['type'] in ('hdistance', 'vdistance', 'distance', 'fix', 'coincident') and pid in c['refs'])]
    _cleanup(sk, via)
    _lega(sk, pid, piano['target'])


trim = sketch_ops.guarded(trim)
extend = sketch_ops.guarded(extend)
