"""Scala e Spezza nello sketch, e le linee dello sketch da salvare in DXF (05/11, idee da SolidCraft).

- Scala: la selezione si ingrandisce o si rimpicciolisce da un punto (il punto resta fermo). Il fattore si scrive
  (2 = il doppio, 0,5 = la metà) oppure viene da due misure («questa linea adesso è 250, deve essere 1000»).
  Le quote dentro la selezione si moltiplicano; quelle che la legano al resto si rifanno con la misura nuova.
  Se qualcosa non lo permette (una quota scritta con una misura del progetto, un punto fisso, un vincolo verso
  il resto del disegno) niente cambia e si dice cosa.
- Spezza: una linea, un arco o un cerchio diventano due pezzi nel punto cliccato; non si cancella niente
  (Accorcia invece toglie un pezzo). I due pezzi di una linea restano in fila; la lunghezza che c'era resta
  come distanza tra le due estremità di prima.
- DXF: le linee, gli archi e i cerchi disegnati (non le guide, non i bordi del pezzo), i testi da marcare.
"""
from __future__ import annotations

import math

from cad_engine.errors import SketchError
from cad_engine.sketch import solve
from cad_engine.sketch.model import DIMENSIONS, ORIGIN, punti_entita

from . import sketch_ops
from .sketch_edit import _check, _points_of, _sync
from .sketch_ops import _r

TOLL = 1e-3          # mm: dopo la Scala ogni punto deve stare dove deve, entro questo


# --------------------------------------------------------------------------- scala
def fattore(f=None, da=None, a=None) -> float:
    """Il fattore della Scala: scritto, oppure da una misura a un'altra (a / da)."""
    if da not in (None, '') or a not in (None, ''):
        try:
            da, a = float(da), float(a)
        except (TypeError, ValueError):
            raise SketchError('Scrivi le due misure con i numeri: quanto è adesso e quanto deve essere.') from None
        if da <= 0 or a <= 0:
            raise SketchError('Le due misure devono essere maggiori di zero.')
        f = a / da
    try:
        f = float(f)
    except (TypeError, ValueError):
        raise SketchError('Scrivi il fattore con un numero: 2 = il doppio, 0,5 = la metà.') from None
    if not math.isfinite(f) or f <= 0:
        raise SketchError('Il fattore deve essere maggiore di zero (2 = il doppio, 0,5 = la metà).')
    if abs(f - 1) < 1e-12:
        raise SketchError('Con il fattore 1 non cambia niente.')
    return f


def _misura(sk, c):
    """La misura di una quota sul disegno com'è salvato adesso (coordinate dei punti, raggi dei cerchi)."""
    t, refs = c['type'], c['refs']
    P = lambda k: (sk.entities[k]['x'], sk.entities[k]['y'])  # noqa: E731
    if t == 'length':
        e = sk.entities[refs[0]]
        return math.dist(P(e['a']), P(e['b']))
    if t in ('diameter', 'radius'):
        e = sk.entities[refs[0]]
        r = e['r'] if e['kind'] == 'circle' else math.dist(P(e['center']), P(e['start']))
        return 2 * r if t == 'diameter' else r
    if t == 'distance':
        return math.dist(P(refs[0]), P(refs[1]))
    if t == 'hdistance':
        return P(refs[1])[0] - P(refs[0])[0]
    if t == 'vdistance':
        return P(refs[1])[1] - P(refs[0])[1]
    if t == 'pldistance':
        e = sk.entities[refs[1]]
        (ax, ay), (bx, by), (px, py) = P(e['a']), P(e['b']), P(refs[0])
        return abs((bx - ax) * (ay - py) - (ax - px) * (by - ay)) / math.hypot(bx - ax, by - ay)
    if t in ('major_axis', 'minor_axis'):
        e = sk.entities[refs[0]]
        return 2 * math.dist(P(e['center']), P(e['major' if t == 'major_axis' else 'minor']))
    raise KeyError(t)


def _scala_su(doc, sk, eids, base, f):
    """Applica la Scala ai dati dello sketch (si usa anche su una copia, per la prova). Errore se non si può."""
    _check(sk, eids)
    if any(sk.entities[e].get('ref') or sk.entities[e].get('xray') for e in eids):
        raise SketchError('I bordi arancio sono il pezzo vero: non si scalano. Togli dalla selezione i bordi del pezzo.')
    _sync(doc, sk)
    try:
        gia = set(solve(sk, doc.resolved_parameters()).status.conflicting)
    except SketchError:
        gia = set()
    bx, by = float(base[0]), float(base[1])
    pts = set(_points_of(sk, eids))
    if ORIGIN in pts and math.hypot(bx, by) > 1e-9:
        raise SketchError('L’origine non si sposta: scala partendo dall’origine (clic sull’origine come punto fermo), '
                          'oppure togli dalla selezione quello che ci passa.')
    prima = {k: (e['x'], e['y']) for k, e in sk.entities.items() if e['kind'] == 'point'}
    for p in pts:
        e = sk.entities[p]
        e['x'], e['y'] = bx + f * (e['x'] - bx), by + f * (e['y'] - by)
    # le entità che stanno tutte dentro (anche una linea non scelta ma con tutte e due le estremità scelte, o un cerchio
    # col centro scelto): si scalano intere, raggio e altezza del testo compresi
    dentro = set(pts) | {k for k, e in sk.entities.items() if e['kind'] != 'point' and
                         all(p in pts for p in punti_entita(e))}
    for k in dentro:
        e = sk.entities[k]
        if e['kind'] == 'circle':
            e['r'] = e['r'] * f
        elif e['kind'] == 'text':
            e['h'] = e['h'] * f
    mosso = {p for p in pts if math.dist(prima[p], (sk.entities[p]['x'], sk.entities[p]['y'])) > 1e-9}
    def stato(r):
        """'in': si scala tutto; 'mezzo': un'entità con solo qualche punto scalato (si stira); 'fuori'."""
        if r in pts and r not in mosso:
            return 'fermo'            # il punto da cui si scala: va bene con tutti
        if r in dentro:
            return 'in'
        e = sk.entities.get(r, {})
        return 'mezzo' if any(p in mosso for p in punti_entita(e)) else 'fuori'

    legami = []                       # vincoli tra la selezione e il resto: se il disegno non torna, colpa loro
    for cid, c in sk.constraints.items():
        refs = c['refs']
        st = [stato(r) for r in refs]
        if not any(s in ('in', 'mezzo') for s in st):
            continue
        tutta = all(s in ('in', 'fermo') for s in st)
        if c['type'] == 'fix':
            if refs[0] in mosso:
                raise SketchError(f'Non si può scalare: {sk.describe_constraint(cid)} tiene fermo un punto della selezione. '
                                  'Scala partendo da quel punto, oppure toglilo dalla selezione.')
            continue
        if c['type'] not in DIMENSIONS:
            if not tutta:
                legami.append(cid)
            continue
        if c['type'] in ('angle', 'tilt') or c.get('driven'):
            if not tutta and c['type'] in ('angle', 'tilt'):
                legami.append(cid)
            continue
        v = c['value']
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            c['value'] = _r(v * f) if tutta else _r(_misura(sk, c))
        elif tutta:
            c['value'] = f'({v})*{_r(f)}'
        else:
            raise SketchError(f'Non si può scalare: {sk.describe_constraint(cid)} è scritta con «{v}» e lega la '
                              'selezione al resto del disegno. Scrivi un numero in quella quota, oppure scegli anche '
                              'quello a cui è legata.')
    # il disegno risolto deve stare dove l'abbiamo messo: se un vincolo verso il resto lo tira via, non si fa
    voluto = {k: (e['x'], e['y']) for k, e in sk.entities.items() if e['kind'] == 'point'}
    ss = solve(sk, doc.resolved_parameters())
    lontano = [k for k, xy in ss.points.items() if k in voluto and math.dist(xy, voluto[k]) > TOLL]
    nuovi = [c for c in ss.status.conflicting if c not in gia]
    if nuovi or lontano:
        colpa = next((c for c in legami if c in nuovi), None) or (legami[0] if legami else None)
        if colpa is None and nuovi:
            colpa = nuovi[0]
        perche = f' ({sk.describe_constraint(colpa)})' if colpa in sk.constraints else ''
        raise SketchError(f'Non si può scalare da qui: la selezione è attaccata al resto del disegno{perche}. Scala '
                          'partendo dal punto dove è attaccata, scegli anche quello a cui è attaccata, oppure togli il '
                          'vincolo.')


def _su_copia(doc, sid, eids, base, f):
    from cad_engine.sketch.model import Sketch
    copia = Sketch.from_dict(doc.sketch(sid).to_dict())
    _scala_su(doc, copia, list(eids), base, float(f))
    return copia


def scale_check(doc, sid, eids, base, f) -> dict:
    """Prova la Scala su una copia dello sketch (niente cambia): il fattore, o l'errore."""
    _su_copia(doc, sid, eids, base, f)
    return {'factor': float(f)}


def scale(doc, sid, eids, base, f):
    """Tutto o niente: si fa su una copia e, se va, la copia diventa il disegno."""
    copia = _su_copia(doc, sid, eids, base, f)
    sk = doc.sketch(sid)
    sk.entities.clear()
    sk.entities.update(copia.entities)
    sk.constraints.clear()
    sk.constraints.update(copia.constraints)


# --------------------------------------------------------------------------- spezza
def _xy(sk, k):
    return sk.entities[k]['x'], sk.entities[k]['y']


def _break_plan(doc, sk, eid, click):
    if eid not in sk.entities or sk.entities[eid]['kind'] not in ('line', 'circle', 'arc'):
        raise SketchError('Clicca una linea, un arco o un cerchio da spezzare.')
    e = sk.entities[eid]
    if e.get('ref') or e.get('xray'):
        raise SketchError('I bordi arancio sono il pezzo vero: non si spezzano.')
    _sync(doc, sk)
    cx, cy = float(click[0]), float(click[1])
    if e['kind'] == 'line':
        a, b = _xy(sk, e['a']), _xy(sk, e['b'])
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L < 1e-9:
            raise SketchError('La linea è lunga zero: non c’è niente da spezzare.')
        t = ((cx - a[0]) * dx + (cy - a[1]) * dy) / (L * L)
        d1 = t * L
        if d1 < 0.01 or L - d1 < 0.01:
            raise SketchError('Clicca più lontano dalle estremità: lì la linea finisce già.')
        p = (a[0] + dx * t, a[1] + dy * t)
        return {'kind': 'line', 'at': p, 'pieces': [[list(a), list(p)], [list(p), list(b)]], 'lengths': [d1, L - d1]}
    c = _xy(sk, e['center'])
    if e['kind'] == 'circle':
        r = e['r']
        try:
            r = solve(sk, doc.resolved_parameters()).circles[eid][1]
        except Exception:  # noqa: BLE001
            pass
        t = math.atan2(cy - c[1], cx - c[0])
        p = (c[0] + r * math.cos(t), c[1] + r * math.sin(t))
        q = (c[0] - r * math.cos(t), c[1] - r * math.sin(t))
        mezzo = math.pi * r
        return {'kind': 'circle', 'at': p, 'other': q, 'r': r, 't': t,
                'pieces': [_arco(c, r, t, t + math.pi), _arco(c, r, t + math.pi, t + 2 * math.pi)],
                'lengths': [mezzo, mezzo]}
    s, f_ = _xy(sk, e['start']), _xy(sk, e['end'])
    r = math.dist(c, s)
    t0 = math.atan2(s[1] - c[1], s[0] - c[0])
    t1 = math.atan2(f_[1] - c[1], f_[0] - c[0])
    while t1 <= t0:
        t1 += 2 * math.pi
    t = math.atan2(cy - c[1], cx - c[0])
    while t < t0:
        t += 2 * math.pi
    if t > t1:                                  # clic fuori dall'arco: niente da spezzare lì
        raise SketchError('Clicca sull’arco, dove vuoi spezzarlo.')
    if r * (t - t0) < 0.01 or r * (t1 - t) < 0.01:
        raise SketchError('Clicca più lontano dalle estremità: lì l’arco finisce già.')
    p = (c[0] + r * math.cos(t), c[1] + r * math.sin(t))
    return {'kind': 'arc', 'at': p, 'pieces': [_arco(c, r, t0, t), _arco(c, r, t, t1)],
            'lengths': [r * (t - t0), r * (t1 - t)]}


def _arco(c, r, a0, a1, n=48):
    return [[c[0] + r * math.cos(a0 + (a1 - a0) * i / n), c[1] + r * math.sin(a0 + (a1 - a0) * i / n)] for i in range(n + 1)]


def break_preview(doc, sid, eid, click) -> dict:
    piano = _break_plan(doc, doc.sketch(sid), eid, click)
    return {'at': list(piano['at']), 'pieces': piano['pieces'], 'lengths': piano['lengths'], 'kind': piano['kind']}


def spezza(doc, sid, eid, click) -> list:
    """Spezza in due nel punto cliccato. Ritorna i due pezzi."""
    sk = doc.sketch(sid)
    piano = _break_plan(doc, sk, eid, click)
    e = sk.entities[eid]
    costr = bool(e.get('construction'))
    if e['kind'] == 'line':
        uguali = [k for k, c in sk.constraints.items() if c['type'] == 'equal' and eid in c['refs']]
        if uguali:
            raise SketchError(f'Non si spezza: {sk.describe_constraint(uguali[0])} vuole la linea intera. '
                              'Togli prima quel vincolo.')
        a, vecchio_b = e['a'], e['b']
        p = sk.point(*piano['at'])
        e['b'] = p
        l2 = sk.line(p, vecchio_b, construction=costr)
        if e.get('label'):
            sk.entities[l2]['label'] = f'lato {l2}'
        for k in ('piega',):
            if k in e:
                sk.entities[l2][k] = e[k]
        sk.constrain('parallel', l2, eid)             # i due pezzi restano in fila (hanno il punto in comune)
        for cid, c in list(sk.constraints.items()):
            if c['type'] == 'length' and c['refs'] == [eid]:
                # la misura di prima resta: è la distanza tra le due estremità di prima
                c['type'], c['refs'] = 'distance', [a, vecchio_b]
            elif c['type'] == 'tangent' and eid in c['refs']:
                altro = sk.entities.get(next(r for r in c['refs'] if r != eid), {})
                if vecchio_b in (altro.get('start'), altro.get('end')):
                    c['refs'] = [l2 if r == eid else r for r in c['refs']]
        sk.dimension('length', eid, value=_r(piano['lengths'][0]))
        return [eid, l2]
    if e['kind'] == 'arc':
        p = sk.point(*piano['at'])
        vecchia_fine = e['end']
        e['end'] = p
        a2 = sk.arc(e['center'], p, vecchia_fine, construction=costr)
        for c in sk.constraints.values():
            if c['type'] == 'tangent' and eid in c['refs']:
                altro = sk.entities.get(next(r for r in c['refs'] if r != eid), {})
                if vecchia_fine in (altro.get('a'), altro.get('b'), altro.get('start'), altro.get('end')):
                    c['refs'] = [a2 if r == eid else r for r in c['refs']]
        return [eid, a2]
    # cerchio: due mezzi archi, il primo parte dal punto cliccato
    if e.get('hole'):
        raise SketchError('Questo cerchio è un foro con il suo tipo (filettato, svasato…): non si spezza.')
    tang = [k for k, c in sk.constraints.items() if c['type'] == 'tangent' and eid in c['refs']]
    if tang:
        raise SketchError(f'Non si spezza: {sk.describe_constraint(tang[0])} vuole il cerchio intero. Togli prima quel vincolo.')
    p = sk.point(*piano['at'])
    q = sk.point(*piano['other'])
    a1 = sk.arc(e['center'], p, q, construction=costr)
    a2 = sk.arc(e['center'], q, p, construction=costr)
    for c in sk.constraints.values():
        if eid in c['refs']:
            if c['type'] == 'diameter':
                v = c['value']
                c['type'] = 'radius'
                c['value'] = _r(v / 2) if isinstance(v, (int, float)) else f'({v})/2'
            c['refs'] = [a1 if r == eid else r for r in c['refs']]
    del sk.entities[eid]
    return [a1, a2]


spezza = sketch_ops.guarded(spezza)


# --------------------------------------------------------------------------- DXF
def geometria_dxf(doc, sid) -> dict:
    """Quello che va nel DXF, nelle coordinate dello sketch (mm): linee, archi, cerchi da tagliare; testi da marcare
    (tratti) e testi stencil (contorni da tagliare). Fuori: guide (linee di costruzione), bordi del pezzo, viste
    attraverso."""
    from cad_engine.sketch import testo as testo_mod
    sk = doc.sketch(sid)
    ss = solve(sk, doc.resolved_parameters())
    P = ss.points
    out = {'lines': [], 'arcs': [], 'circles': [], 'marks': [], 'cut_texts': [], 'curves': [], 'skipped': 0}
    from cad_engine.sketch import curve as cv
    for k, e in sk.entities.items():
        kind = e['kind']
        if kind not in ('line', 'circle', 'arc', 'text', 'ellipse', 'spline'):
            continue
        if kind in ('ellipse', 'spline') and not (e.get('ref') or e.get('xray') or e.get('construction')):
            # 05/11: ellissi e curve libere come archi tangenti (il laser vuole linee e archi)
            if kind == 'ellipse':
                s_, f_ = (P[e['start']], P[e['end']]) if 'start' in e else (None, None)
                out['curves'].append(cv.ellisse_in_archi(P[e['center']], P[e['major']], P[e['minor']], s_, f_))
            else:
                out['curves'].append(cv.spline_in_archi([P[p] for p in e['points']], bool(e.get('closed'))))
            continue
        if e.get('ref') or e.get('xray') or e.get('construction'):
            out['skipped'] += 1
            continue
        if kind == 'line':
            a, b = P[e['a']], P[e['b']]
            if math.dist(a, b) > 1e-9:
                out['lines'].append((tuple(a), tuple(b)))
        elif kind == 'circle':
            r = ss.circles[k][1] if k in ss.circles else e['r']
            out['circles'].append((tuple(P[e['center']]), float(r)))
        elif kind == 'arc':
            c, s, f = P[e['center']], P[e['start']], P[e['end']]
            r = math.dist(c, s)
            t0 = math.degrees(math.atan2(s[1] - c[1], s[0] - c[0]))
            t1 = math.degrees(math.atan2(f[1] - c[1], f[0] - c[0]))
            out['arcs'].append((tuple(c), r, t0 % 360, t1 % 360))
        else:
            x, y = testo_mod.origine(e, *P[e['center']])
            if e.get('stencil'):
                out['cut_texts'] += list(testo_mod.contorni_curve(e['text'], float(e['h']), x, y,
                                                                  float(e.get('angle', 0)), e['stencil']))
            else:
                out['marks'] += testo_mod.tratti(e['text'], e['h'], x, y, e.get('angle', 0))
    return out
