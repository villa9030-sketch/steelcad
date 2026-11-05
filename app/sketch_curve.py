"""Ellissi e curve libere nello sketch (05/11, idea da SolidCraft): disegnarle, vederle, trascinarne i punti.

- Ellisse: clic sul centro, clic sulla fine di un asse, poi quanto è larga dall'altra parte. Arriva con le quote dei
  due assi (tutto l'asse, da parte a parte, come si misura in officina) e la posizione del centro; se è dritta resta
  dritta (orizzontale o verticale), se no ha la sua inclinazione. L'arco di ellisse ha in più partenza e arrivo.
- Curva libera: passa per i punti cliccati; aperta o chiusa (si torna sul primo punto). I punti sono punti normali:
  ci si aggancia, si quotano, si trascinano (la curva li segue).
"""
from __future__ import annotations

import math

from cad_engine.errors import SketchError
from cad_engine.sketch import solve
from cad_engine.sketch import curve as cv
from cad_engine.sketch.model import ORIGIN, punti_entita

from . import sketch_ops
from .sketch_ops import HV_TOL, _point_ref, _position, _r


def vista(sk, pts: dict, g) -> list:
    """Le ellissi e le curve libere per l'interfaccia: la curva in punti (2D e 3D) e i punti da trascinare."""
    out = []
    for k, e in sk.entities.items():
        if e['kind'] not in ('ellipse', 'spline'):
            continue
        try:
            if e['kind'] == 'ellipse':
                c, m, n = pts[e['center']], pts[e['major']], pts[e['minor']]
                s, f = (pts[e['start']], pts[e['end']]) if 'start' in e else (None, None)
                xy = cv.ellisse_campioni(c, m, n, s, f)
                a, b, ang = cv.ellisse_assi(c, m, n)
                extra = {'center_id': e['center'], 'major': e['major'], 'minor': e['minor'], 'start': e.get('start'),
                         'end': e.get('end'), 'xc': list(c), 'a': a, 'b': b, 'ang': ang, 'closed': 'start' not in e}
            else:
                xy = cv.spline_campioni([pts[p] for p in e['points']], bool(e.get('closed')))
                extra = {'points_ids': list(e['points']), 'closed': bool(e.get('closed')),
                         'start': e['points'][0], 'end': e['points'][-1]}
        except (KeyError, ZeroDivisionError):
            continue
        out.append({'id': k, 'kind': e['kind'], 'label': sk.describe(k), 'pts': [list(q) for q in xy],
                    'p3': [g(q) for q in xy], 'handles': [p for p in punti_entita(e) if p != ORIGIN],
                    'construction': bool(e.get('construction')), 'ref': bool(e.get('ref')),
                    'xray': bool(e.get('xray')), **extra})
    return out


def add_ellipse(doc, sid: str, center, major, b, start=None, end=None, construction: bool = False) -> str:
    """Ellisse dal centro (punto, aggancio o [x, y]), dalla fine di un asse ([x, y]) e da metà dell'altro asse.
    Con start e end: l'arco di ellisse (antiorario), che può partire e arrivare su punti che ci sono già."""
    sk = doc.sketch(sid)
    b = float(b)
    pc, cxy, nuovo = _point_ref(sk, center)
    mx, my = float(major[0]), float(major[1])
    a = math.hypot(mx - cxy[0], my - cxy[1])
    if a < 1e-6 or b < 1e-6:
        raise SketchError('L’ellisse ha bisogno di due assi più lunghi di zero.')
    arco = {}
    if start is not None or end is not None:
        if start is None or end is None:
            raise SketchError('Per un arco di ellisse servono la partenza e l’arrivo.')
        arco = {'start': _estremo(sk, start), 'end': _estremo(sk, end)}
    eid = sk.ellipse(pc, (mx, my), b, construction=bool(construction), **arco)
    e = sk.entities[eid]
    c_, m_, n_ = ((sk.entities[e[k]]['x'], sk.entities[e[k]]['y']) for k in ('center', 'major', 'minor'))
    a, bb, ang = cv.ellisse_assi(c_, m_, n_)
    # le quote una alla volta, dalla più utile: un arco attaccato a punti che ci sono già ha spesso l'asse grande
    # deciso da loro; quella quota allora non si mette (prima il «togli le doppie» toglieva anche l'asse piccolo)
    par = doc.resolved_parameters()

    def guai():
        try:
            st = solve(sk, par).status
            return len(st.redundant) + len(st.conflicting) + (st.state == 'non risolto')
        except SketchError:
            return 10 ** 6

    def prova(fa):
        prima, quanti = set(sk.constraints), guai()
        fa()
        if guai() > quanti:                      # la quota nuova fa doppio o litiga: non si mette
            for k in set(sk.constraints) - prima:
                del sk.constraints[k]
    # dritta resta dritta; se no la sua inclinazione (dall'orizzontale)
    for k in range(-2, 3):
        if abs(ang - k * math.pi / 2) < HV_TOL:
            prova(lambda k=k: sk.constrain('horizontal' if k % 2 == 0 else 'vertical', e['center'], e['major'], auto=True))
            break
    else:
        prova(lambda: sk.dimension('tilt', eid, value=_r(round(math.degrees(ang), 4))))
    prova(lambda: sk.dimension('minor_axis', eid, value=_r(2 * bb)))
    prova(lambda: sk.dimension('major_axis', eid, value=_r(2 * a)))
    if nuovo:
        _position(sk, pc, cxy)
    return eid


def _estremo(sk, p):
    """La partenza o l'arrivo di un arco di ellisse: un punto che c'è già (id o aggancio) o [x, y]."""
    if isinstance(p, (list, tuple)):
        return (float(p[0]), float(p[1]))           # lo porta sull'ellisse il modello
    pid, _xy, _nuovo = _point_ref(sk, p)
    return pid


def add_spline(doc, sid: str, pts: list, closed: bool = False, construction: bool = False) -> str:
    """Curva libera per i punti (ognuno un punto che c'è già, un aggancio o [x, y]), aperta o chiusa."""
    sk = doc.sketch(sid)
    if not isinstance(pts, (list, tuple)) or len(pts) < 2:
        raise SketchError('Per una curva libera servono almeno due punti.')
    ids = [_point_ref(sk, p)[0] for p in pts]
    if closed and len(ids) > 2 and ids[0] == ids[-1]:
        ids = ids[:-1]
    return sk.spline(ids, closed=bool(closed), construction=bool(construction))


add_ellipse = sketch_ops.guarded(add_ellipse)
add_spline = sketch_ops.guarded(add_spline)


def move_point(doc, sid: str, pid: str, xy) -> None:
    """Trascinare un punto di una curva libera o di un'ellisse. Il centro dell'ellisse la sposta tutta; la fine di un
    asse cambia quell'asse (e l'inclinazione): le quote dell'ellisse seguono. Un punto legato da altre quote o
    vincoli non si stacca: lo dice."""
    from .sketch_edit import _sync, move
    sk = doc.sketch(sid)
    if pid == ORIGIN or pid not in sk.entities or sk.entities[pid]['kind'] != 'point':
        raise SketchError('Si trascinano i punti delle curve libere e delle ellissi.')
    if sk.entities[pid].get('ref'):
        raise SketchError('I bordi arancio sono il pezzo vero: non si spostano.')
    _sync(doc, sk)
    x, y = float(xy[0]), float(xy[1])
    p0 = sk.entities[pid]
    dx, dy = x - p0['x'], y - p0['y']
    ellissi = [(k, e) for k, e in sk.entities.items() if e['kind'] == 'ellipse' and pid in punti_entita(e)]
    for k, e in ellissi:
        if pid == e['center']:
            move(doc, sid, [k], dx, dy)              # tutta l'ellisse, con le quote di posizione
            return
    for k, e in ellissi:
        if pid in (e['major'], e['minor']):
            c = sk.entities[e['center']]
            pm = sk.entities[e['major']]
            dritta = any(q['type'] in ('horizontal', 'vertical') and set(q['refs']) == {e['center'], e['major']}
                         for q in sk.constraints.values())
            if pid == e['major'] and dritta:          # dritta resta dritta: cambia solo la lunghezza
                ang0 = math.atan2(pm['y'] - c['y'], pm['x'] - c['x'])
                t = (x - c['x']) * math.cos(ang0) + (y - c['y']) * math.sin(ang0)
                x, y = c['x'] + t * math.cos(ang0), c['y'] + t * math.sin(ang0)
            nuovo = math.hypot(x - c['x'], y - c['y'])
            if nuovo < 1e-6:
                raise SketchError('L’asse dell’ellisse non può essere lungo zero.')
            pn = sk.entities[e['minor']]
            if pid == e['major']:
                b = math.hypot(pn['x'] - c['x'], pn['y'] - c['y'])
                if nuovo <= b * (1 + 1e-6):
                    raise SketchError('L’asse grande deve restare più lungo dell’asse piccolo.')
                ang = math.atan2(y - c['y'], x - c['x'])
                pm['x'], pm['y'] = x, y
                pn['x'], pn['y'] = c['x'] - b * math.sin(ang), c['y'] + b * math.cos(ang)
            else:
                a = math.hypot(pm['x'] - c['x'], pm['y'] - c['y'])
                if nuovo >= a * (1 - 1e-6):
                    raise SketchError('L’asse piccolo deve restare più corto dell’asse grande.')
                ang = math.atan2(pm['y'] - c['y'], pm['x'] - c['x'])
                pn['x'], pn['y'] = c['x'] - nuovo * math.sin(ang), c['y'] + nuovo * math.cos(ang)
            # le quote dell'ellisse prendono le misure nuove (se sono numeri)
            for q in sk.constraints.values():
                if q['refs'] != [k] or not isinstance(q.get('value'), (int, float)):
                    continue
                if q['type'] == 'major_axis' and pid == e['major']:
                    q['value'] = _r(2 * nuovo)
                elif q['type'] == 'minor_axis' and pid == e['minor']:
                    q['value'] = _r(2 * nuovo)
                elif q['type'] == 'tilt' and pid == e['major']:
                    q['value'] = _r(round(math.degrees(math.atan2(y - c['y'], x - c['x'])), 4))
            return
    move(doc, sid, [pid], dx, dy)
