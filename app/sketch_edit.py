"""Comandi di modifica dello sketch: costruzione, offset, specchia, copia, sposta, serie, quota.

Tutto resta legato, non sono copie morte:
- offset: ogni tratto nuovo è parallelo al suo e a distanza fissa, dentro un parametro (off1, …):
  cambi il parametro e l'offset si sposta; cambi l'originale e l'offset lo segue;
- specchia: ogni punto nuovo è simmetrico al suo rispetto alla linea scelta;
- copia e serie: le copie hanno le stesse quote dell'originale e stanno a un passo fisso dal suo
  primo punto; nella serie il passo è un parametro (px1, py1);
- quota: misure aggiunte a mano; se sono doppie o in conflitto vengono rifiutate col motivo.
"""
from __future__ import annotations

import math

from cad_engine.errors import SketchError, SteelCADError
from cad_engine.sketch import solve
from cad_engine.sketch.model import DIMENSIONS, ORIGIN

from .sketch_ops import _r, guarded


# --------------------------------------------------------------------------- aiuti
def _xy(sk, pid):
    e = sk.entities[pid]
    return (e['x'], e['y'])


def _solved_xy(doc, sk):
    try:
        return solve(sk, doc.resolved_parameters()).points
    except SteelCADError:
        return {k: (e['x'], e['y']) for k, e in sk.entities.items() if e['kind'] == 'point'}


def _sync(doc, sk):
    """Porta le coordinate salvate a quelle risolte: i calcoli partono dalla forma vera."""
    for k, (x, y) in _solved_xy(doc, sk).items():
        if k in sk.entities and k != ORIGIN:
            sk.entities[k]['x'], sk.entities[k]['y'] = float(x), float(y)


def _points_of(sk, eids) -> list[str]:
    out = []
    for e in eids:
        ent = sk.entities[e]
        for key in ('a', 'b', 'center', 'start', 'end'):
            if key in ent and ent[key] not in out:
                out.append(ent[key])
        if ent['kind'] == 'point' and e not in out:
            out.append(e)
    return out


def _check(sk, eids):
    if not eids:
        raise SketchError('Seleziona prima qualcosa (clic su linee o cerchi, Maiusc per aggiungerne).')
    for e in eids:
        if e not in sk.entities:
            raise SketchError(f'Nello sketch non c’è {e}.')


def _new_param(doc, base: str, value) -> str:
    i = 1
    while f'{base}{i}' in doc.parameters:
        i += 1
    doc.set_parameter(f'{base}{i}', value)
    return f'{base}{i}'


# --------------------------------------------------------------------------- costruzione
def set_construction(doc, sid, eids, flag: bool):
    sk = doc.sketch(sid)
    _check(sk, eids)
    eids = [e for e in eids if not sk.entities[e].get('ref')]
    for e in eids:
        if sk.entities[e]['kind'] in ('line', 'circle', 'arc'):
            sk.entities[e]['construction'] = bool(flag)


# --------------------------------------------------------------------------- offset
def _chain(sk, lines):
    """Ordina linee collegate in una catena. Ritorna (punti in ordine, linee in ordine, chiusa)."""
    resto = list(lines)
    if len(resto) == 1:
        e = sk.entities[resto[0]]
        return [e['a'], e['b']], resto, False
    gradi = {}
    for l in resto:
        e = sk.entities[l]
        for p in (e['a'], e['b']):
            gradi[p] = gradi.get(p, 0) + 1
    if any(g > 2 for g in gradi.values()):
        raise SketchError('Le linee scelte si diramano: per l’offset servono linee in fila (un contorno).')
    estremi = [p for p, g in gradi.items() if g == 1]
    chiusa = not estremi
    if len(estremi) not in (0, 2):
        raise SketchError('Le linee scelte non sono collegate in fila.')
    start = estremi[0] if estremi else sk.entities[resto[0]]['a']
    pts, ordine, cur = [start], [], start
    while resto:
        nxt = next((l for l in resto if cur in (sk.entities[l]['a'], sk.entities[l]['b'])), None)
        if nxt is None:
            raise SketchError('Le linee scelte non sono collegate in fila.')
        e = sk.entities[nxt]
        cur = e['b'] if e['a'] == cur else e['a']
        resto.remove(nxt)
        ordine.append(nxt)
        pts.append(cur)
    if chiusa:
        pts = pts[:-1]
    return pts, ordine, chiusa


def _offset_geometry(sk, lines, dist, side):
    pts, ordine, chiusa = _chain(sk, lines)
    xy = [_xy(sk, p) for p in pts]
    n = len(ordine)
    if chiusa:
        area = sum(xy[i][0] * xy[(i + 1) % n][1] - xy[(i + 1) % n][0] * xy[i][1] for i in range(n)) / 2
        segno = 1 if area > 0 else -1          # antiorario: la normale a destra guarda fuori
        verso = segno if side == 'out' else -segno
    else:
        verso = 1 if side == 'right' else -1
    righe = []
    for i in range(n):
        a, b = xy[i], xy[(i + 1) % len(xy)] if chiusa else xy[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        nx, ny = dy / L * verso, -dx / L * verso      # normale (a destra se verso = 1)
        righe.append(((a[0] + nx * dist, a[1] + ny * dist), (b[0] + nx * dist, b[1] + ny * dist), (dx / L, dy / L)))

    def incrocio(r1, r2):
        (p, _, d1), (q, _, d2) = r1, r2
        cr = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(cr) < 1e-12:
            return r1[1]
        t = ((q[0] - p[0]) * d2[1] - (q[1] - p[1]) * d2[0]) / cr
        return (p[0] + d1[0] * t, p[1] + d1[1] * t)

    nuovi = []
    if chiusa:
        for i in range(n):
            nuovi.append(incrocio(righe[i - 1], righe[i]))
    else:
        nuovi.append(righe[0][0])
        for i in range(1, n):
            nuovi.append(incrocio(righe[i - 1], righe[i]))
        nuovi.append(righe[-1][1])
    # un offset verso dentro troppo grande ribalta i tratti
    m = len(nuovi)
    for i in range(n):
        a, b = nuovi[i], nuovi[(i + 1) % m]
        s0, s1 = xy[i], xy[(i + 1) % len(xy)]
        if (b[0] - a[0]) * (s1[0] - s0[0]) + (b[1] - a[1]) * (s1[1] - s0[1]) <= 1e-9:
            raise SketchError(f'Offset di {dist:g} troppo grande verso dentro: il contorno si rovescia.')
    return pts, ordine, chiusa, nuovi


def offset_preview(doc, sid, eids, dist, side) -> dict:
    sk = doc.sketch(sid)
    _check(sk, eids)
    _sync(doc, sk)
    dist = float(dist)
    linee = [e for e in eids if sk.entities[e]['kind'] == 'line']
    cerchi = [e for e in eids if sk.entities[e]['kind'] == 'circle']
    out = {'lines': [], 'circles': [], 'closed': None}
    if linee:
        _, _, chiusa, nuovi = _offset_geometry(sk, linee, dist, side)
        out['closed'] = chiusa
        k = len(nuovi)
        segs = range(k) if chiusa else range(k - 1)
        out['lines'] = [[list(nuovi[i]), list(nuovi[(i + 1) % k])] for i in segs]
    for c in cerchi:
        e = sk.entities[c]
        r = e['r'] + (dist if side in ('out', 'right') else -dist)
        if r <= 0:
            raise SketchError('Offset troppo grande verso dentro: il cerchio sparirebbe.')
        out['circles'].append([list(_xy(sk, e['center'])), r])
    return out


def offset_side(doc, sid, eids, dist, point) -> dict:
    """Come in AutoCAD: il lato dell'offset è quello dove sta il mouse. Si prova da tutte e due le parti e
    vince quella con l'anteprima più vicina al punto. Ritorna {'side', 'preview'}."""
    sk = doc.sketch(sid)
    _check(sk, eids)
    linee = [e for e in eids if sk.entities[e]['kind'] == 'line']
    chiusa = _chain(sk, linee)[2] if linee else True
    px, py = float(point[0]), float(point[1])

    def dist_seg(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = dx * dx + dy * dy or 1
        t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L))
        return math.hypot(px - a[0] - t * dx, py - a[1] - t * dy)

    migliore = None
    for side in (('out', 'in') if chiusa else ('right', 'left')):
        try:
            pv = offset_preview(doc, sid, eids, dist, side)
        except SketchError:
            continue                        # verso dentro troppo grande: resta solo l'altra parte
        d = min([dist_seg(a, b) for a, b in pv['lines']] +
                [abs(math.hypot(px - c[0], py - c[1]) - r) for c, r in pv['circles']] or [math.inf])
        if migliore is None or d < migliore[0]:
            migliore = (d, side, pv)
    if migliore is None:
        raise SketchError(f'Offset di {float(dist):g} troppo grande da tutte e due le parti.')
    return {'side': migliore[1], 'preview': migliore[2]}


def offset(doc, sid, eids, dist, side):
    sk = doc.sketch(sid)
    _check(sk, eids)
    _sync(doc, sk)
    d = float(dist)
    if d <= 0:
        raise SketchError('La distanza dell’offset deve essere maggiore di zero.')
    par = _new_param(doc, 'off', _r(d))
    linee = [e for e in eids if sk.entities[e]['kind'] == 'line']
    cerchi = [e for e in eids if sk.entities[e]['kind'] == 'circle']
    nuove = []
    if linee:
        pts, ordine, chiusa, nuovi = _offset_geometry(sk, linee, d, side)
        ids = [sk.point(x, y) for x, y in nuovi]
        k = len(ids)
        segs = range(k) if chiusa else range(k - 1)
        for i in segs:
            l = sk.line(ids[i], ids[(i + 1) % k])
            sk.entities[l]['label'] = f'lato {l}'
            src = ordine[i]
            sk.constrain('parallel', l, src)
            # il lato dell'offset: una guida corta dal primo punto del tratto originale, a 90° (con il
            # segno: sempre dalla stessa parte) e lunga "off"; il lato nuovo passa per la sua punta.
            # Con il segno dell'angolo l'offset non si può rovesciare, anche se l'originale cambia molto.
            e = sk.entities[src]
            a0, b0 = _xy(sk, e['a']), _xy(sk, e['b'])
            ux, uy = b0[0] - a0[0], b0[1] - a0[1]
            L = math.hypot(ux, uy)
            nx, ny = (nuovi[i][0] - a0[0], nuovi[i][1] - a0[1])
            lato = 1 if ux * ny - uy * nx > 0 else -1       # + = a sinistra del tratto originale
            # la normale vera dal punto a0 (non il vertice, che negli spigoli sta in diagonale)
            pnx, pny = -uy / L * lato, ux / L * lato
            q = sk.point(a0[0] + pnx * d, a0[1] + pny * d)
            g = sk.line(e['a'], q, construction=True)
            sk.dimension('angle', src, g, value=90 * lato)
            sk.dimension('length', g, value=par)
            sk.constrain('on_line', q, l)
            nuove.append(l)
        if not chiusa:
            # le estremità: una linea di costruzione perpendicolare dall'estremo dell'originale
            for p_src, p_new, src in ((pts[0], ids[0], ordine[0]), (pts[-1], ids[-1], ordine[-1])):
                c = sk.line(p_src, p_new, construction=True)
                sk.constrain('perpendicular', c, src)
            # l'ultimo tratto non ha la distanza sul suo punto b: basta il parallelo + i punti condivisi
    for c in cerchi:
        e = sk.entities[c]
        r = e['r'] + (d if side in ('out', 'right') else -d)
        if r <= 0:
            raise SketchError('Offset troppo grande verso dentro: il cerchio sparirebbe.')
        n = sk.circle(e['center'], r, construction=bool(e.get('construction')))
        _circle_offset(sk, c, n, par, r > e['r'])
        nuove.append(n)
    return nuove


def _circle_offset(sk, src, new, par, fuori: bool):
    """Cerchio concentrico: centro in comune, diametro = diametro dell'originale ± 2·offset."""
    d_src = next((c for c in sk.constraints.values() if c['type'] in ('diameter', 'radius') and c['refs'] == [src]), None)
    if d_src is not None and d_src['type'] == 'diameter':
        base = d_src['value']
        expr = f'({base}) {"+" if fuori else "-"} 2*{par}'
    else:
        base = sk.entities[src]['r'] * 2
        expr = f'{_r(base)} {"+" if fuori else "-"} 2*{par}'
    sk.dimension('diameter', new, value=expr)


# --------------------------------------------------------------------------- specchia
def mirror(doc, sid, eids, axis):
    """Specchia la selezione (una copia, l'originale resta) su un asse: una linea dello sketch, oppure due punti
    [p1, p2] (id, [x, y] o agganci come {'mid': linea}): allora l'asse diventa una linea di costruzione."""
    from .sketch_ops import _point_ref
    sk = doc.sketch(sid)
    _check(sk, eids)
    if isinstance(axis, (list, tuple)):
        if len(axis) != 2:
            raise SketchError('L’asse dello specchio sono due punti.')
        ids = []
        for p in axis:
            if isinstance(p, str):
                if p not in sk.entities or sk.entities[p]['kind'] != 'point':
                    raise SketchError(f'Nello sketch non c’è il punto {p}.')
                ids.append(p)
                continue
            pid, _pos, nuovo = _point_ref(sk, p)
            if nuovo and not isinstance(p, dict):
                sk.constrain('fix', pid)                 # un punto qualsiasi dell'asse: resta dov'è
            ids.append(pid)
        (x1, y1), (x2, y2) = _xy(sk, ids[0]), _xy(sk, ids[1])
        if math.hypot(x2 - x1, y2 - y1) < 1e-6:
            raise SketchError('I due punti dell’asse coincidono: clicca due punti diversi.')
        axis = sk.line(ids[0], ids[1], construction=True, label='asse dello specchio')
    if axis not in sk.entities or sk.entities[axis]['kind'] != 'line':
        raise SketchError('Per specchiare scegli una linea come asse (va bene anche di costruzione).')
    eids = [e for e in eids if e != axis]
    if not eids:
        raise SketchError('Seleziona cosa specchiare, poi la linea che fa da asse.')
    _sync(doc, sk)
    ax = sk.entities[axis]
    (x1, y1), (x2, y2) = _xy(sk, ax['a']), _xy(sk, ax['b'])
    ux, uy = x2 - x1, y2 - y1
    L = math.hypot(ux, uy)
    ux, uy = ux / L, uy / L

    def rifletti(p):
        dx, dy = p[0] - x1, p[1] - y1
        t = dx * ux + dy * uy
        fx, fy = x1 + ux * t, y1 + uy * t
        return (2 * fx - p[0], 2 * fy - p[1]), math.hypot(p[0] - fx, p[1] - fy)

    mappa = {}
    for p in _points_of(sk, eids):
        if p in (ax['a'], ax['b']):
            mappa[p] = p
            continue
        q, dist = rifletti(_xy(sk, p))
        if dist < 1e-6:
            mappa[p] = p                    # sta sull'asse: resta lui
            continue
        mappa[p] = sk.point(*q)
        sk.constrain('symmetric', p, mappa[p], axis)
    nuove = []
    for e in eids:
        ent = sk.entities[e]
        if ent['kind'] == 'line':
            if mappa[ent['a']] == ent['a'] and mappa[ent['b']] == ent['b']:
                continue                    # la linea sta sull'asse
            guida = bool(ent.get('construction')) and not ent.get('ref') and not ent.get('xray')   # il bordo specchiato è disegno
            l = sk.line(mappa[ent['a']], mappa[ent['b']], construction=guida)
            sk.entities[l]['label'] = f'lato {l}'
            nuove.append(l)
        elif ent['kind'] == 'circle':
            c = sk.circle(mappa[ent['center']], ent['r'], construction=bool(ent.get('construction')) and not ent.get('ref') and not ent.get('xray'))
            sk.constrain('equal', c, e)
            nuove.append(c)
        elif ent['kind'] == 'arc':
            # nello specchio il verso si gira: l'inizio dell'arco nuovo è lo specchio della fine
            a = sk.arc(mappa[ent['center']], mappa[ent['end']], mappa[ent['start']],
                       construction=bool(ent.get('construction')) and not ent.get('ref') and not ent.get('xray'))
            nuove.append(a)
    return nuove


# --------------------------------------------------------------------------- copia, serie, sposta
def _duplicate(sk, eids, dx, dy):
    """Copia geometria e vincoli interni; ritorna (mappa punti, entità nuove)."""
    pts = _points_of(sk, eids)
    mappa = {}
    for p in pts:
        if p == ORIGIN:
            raise SketchError('Non si copia l’origine: seleziona linee o cerchi che non ci passano.')
        x, y = _xy(sk, p)
        mappa[p] = sk.point(x + dx, y + dy)
    nuove = {}
    for e in eids:
        ent = dict(sk.entities[e])
        if ent.get('ref') or ent.get('xray'):
            # la copia di un bordo del pezzo (arancio) è disegno vero, da tagliare: non un altro bordo fisso, né una
            # guida. Copiare le finestre già tagliate per farne altre uguali è il caso tipico
            for k in ('ref', 'xray', 'construction', 'piega'):
                ent.pop(k, None)
            if str(ent.get('label', '')).startswith('bordo'):
                ent.pop('label')
        for key in ('a', 'b', 'center', 'start', 'end'):
            if key in ent:
                ent[key] = mappa[ent[key]]
        k = {'line': 'L', 'circle': 'C', 'arc': 'A'}.get(ent['kind'], 'P')
        nid = sk._new_id(k, sk.entities)
        if ent['kind'] == 'line' and ent.get('label', '').startswith('lato '):
            ent['label'] = f'lato {nid}'
        sk.entities[nid] = ent
        nuove[e] = nid
    tutti = set(eids) | set(pts)
    trad = {**mappa, **nuove}
    for cid, c in list(sk.constraints.items()):
        if c['type'] == 'fix':
            continue                        # "fisso" vale per i bordi del pezzo: le copie si muovono con la loro quota
        if c['refs'] and all(r in tutti for r in c['refs']):
            nc = {**c, 'refs': [trad[r] for r in c['refs']]}
            kid = sk._new_id('D' if c['type'] in DIMENSIONS else 'K', sk.constraints)
            sk.constraints[kid] = nc
    return pts, mappa, list(nuove.values())


def copy(doc, sid, eids, dx, dy):
    """Una copia spostata di (dx, dy), con le stesse quote dell'originale."""
    sk = doc.sketch(sid)
    _check(sk, eids)
    _sync(doc, sk)
    pts, mappa, nuove = _duplicate(sk, eids, float(dx), float(dy))
    a = pts[0]
    sk.dimension('hdistance', a, mappa[a], value=_r(dx))
    sk.dimension('vdistance', a, mappa[a], value=_r(dy))
    return nuove


def pattern(doc, sid, eids, cols, px, rows=1, py=0):
    """Serie a griglia: cols colonne a passo px (lungo X), rows righe a passo py (lungo Y), originale
    compreso. I passi diventano parametri: si cambiano dopo e tutte le copie seguono."""
    sk = doc.sketch(sid)
    _check(sk, eids)
    _sync(doc, sk)
    cols, rows = int(cols), int(rows)
    if cols < 1 or rows < 1 or cols * rows < 2:
        raise SketchError('Per una serie servono almeno 2 elementi (colonne × righe).')
    if cols > 1 and abs(float(px)) < 1e-9 or rows > 1 and abs(float(py)) < 1e-9:
        raise SketchError('Il passo della serie non può essere zero.')
    npx = _new_param(doc, 'px', _r(px)) if cols > 1 else None
    npy = _new_param(doc, 'py', _r(py)) if rows > 1 else None
    nuove = []
    for j in range(rows):
        for i in range(cols):
            if i == 0 and j == 0:
                continue
            pts, mappa, ent = _duplicate(sk, eids, float(px) * i, float(py) * j)
            a = pts[0]
            sk.dimension('hdistance', a, mappa[a], value=f'{i}*{npx}' if i else 0)
            sk.dimension('vdistance', a, mappa[a], value=f'{j}*{npy}' if j else 0)
            nuove += ent
    return nuove


def _passo_angolo(n: int, totale: float) -> float:
    """L'angolo tra una copia e la successiva: sul giro intero sono equidistanti (360/n), su un arco la prima e
    l'ultima stanno agli estremi (totale/(n-1))."""
    giro = abs(abs(totale) - 360) < 1e-9
    return totale / n if giro else totale / (n - 1)


def _angoli_serie(n: int, totale: float) -> list[float]:
    passo = _passo_angolo(n, totale)
    return [passo * k for k in range(1, n)]


def _ruota(c, gradi):
    a = math.radians(gradi)
    ca, sa = math.cos(a), math.sin(a)
    return lambda p: (c[0] + (p[0] - c[0]) * ca - (p[1] - c[1]) * sa, c[1] + (p[0] - c[0]) * sa + (p[1] - c[1]) * ca)


def pattern_circular(doc, sid, eids, center, n, total=360):
    """Serie attorno a un centro (05/11, idea da SolidCraft): n elementi in tutto, originale compreso, su un angolo
    totale (360 = giro intero, equidistanti; meno di 360 = la prima e l'ultima agli estremi). Esempio: 8 fori su
    una flangia tonda.

    Come lo specchio, le copie non sono morte: ogni punto della copia è il punto dell'originale girato attorno al
    centro (vincolo «girato attorno al centro»), i cerchi hanno lo stesso diametro dell'originale. L'angolo tra una
    copia e l'altra diventa un parametro (ang1): lo cambi dopo e le copie girano. Il centro è un punto cliccato (il
    centro di un cerchio, un punto del disegno), un aggancio, oppure le coordinate [x, y]."""
    from .sketch_ops import _point_ref, _position
    sk = doc.sketch(sid)
    _check(sk, eids)
    n, total = int(n), float(total)
    if n < 2:
        raise SketchError('Per una serie servono almeno 2 elementi (originale compreso).')
    if n > 400:
        raise SketchError('Al massimo 400 elementi in una serie.')
    if abs(total) < 1e-9 or abs(total) > 360 + 1e-9:
        raise SketchError('L’angolo della serie va da 1 a 360 gradi (360 = giro intero).')
    if any(sk.entities[e].get('kind') == 'point' for e in eids):
        eids = [e for e in eids if sk.entities[e]['kind'] != 'point']
        _check(sk, eids)
    _sync(doc, sk)
    pid, cxy, nuovo = _point_ref(sk, center)
    if nuovo and not isinstance(center, dict):
        _position(sk, pid, cxy)              # un centro scritto con le coordinate: quotato dall'origine
    cxy = _xy(sk, pid)
    punti = _points_of(sk, eids)
    if ORIGIN in punti and pid != ORIGIN:
        raise SketchError('Non si gira l’origine: seleziona linee o cerchi che non ci passano.')
    if all(math.dist(_xy(sk, p), cxy) < 1e-6 for p in punti):
        raise SketchError('Quello scelto sta tutto sul centro: girandolo resta lì. Scegli un altro centro.')
    # il parametro è l'angolo tra una copia e l'altra (come il passo della serie a griglia): cambiato dopo, le copie
    # girano tutte insieme e restano equidistanti
    par = _new_param(doc, 'ang', _r(_passo_angolo(n, total)))
    nuove = []
    for k, g in enumerate(_angoli_serie(n, total), start=1):
        rot = _ruota(cxy, g)
        expr = f'{k}*{par}'
        mappa = {}
        for p in punti:
            if p == pid or math.dist(_xy(sk, p), cxy) < 1e-6:
                mappa[p] = p                 # sta sul centro: resta lui
                continue
            mappa[p] = sk.point(*rot(_xy(sk, p)))
            vid = sk.constrain('rotated', p, mappa[p], pid)
            sk.constraints[vid]['value'] = expr
        for e in eids:
            ent = sk.entities[e]
            guida = bool(ent.get('construction')) and not ent.get('ref') and not ent.get('xray')
            if ent['kind'] == 'line':
                l = sk.line(mappa[ent['a']], mappa[ent['b']], construction=guida)
                sk.entities[l]['label'] = f'lato {l}'
                nuove.append(l)
            elif ent['kind'] == 'circle':
                c = sk.circle(mappa[ent['center']], ent['r'], construction=guida)
                sk.constrain('equal', c, e)
                if ent.get('hole'):
                    sk.entities[c]['hole'] = dict(ent['hole'])
                nuove.append(c)
            elif ent['kind'] == 'arc':
                nuove.append(sk.arc(mappa[ent['center']], mappa[ent['start']], mappa[ent['end']], construction=guida))
            elif ent['kind'] == 'text':
                t = sk.text(mappa[ent['center']], ent['text'], ent['h'], (ent.get('angle') or 0) + g, ent.get('stencil'))
                if ent.get('centrato'):
                    sk.entities[t]['centrato'] = True
                nuove.append(t)
    return nuove


def move(doc, sid, eids, dx, dy):
    """Sposta: si spostano i punti e si aggiornano le quote di posizione che li legano al resto."""
    sk = doc.sketch(sid)
    _check(sk, eids)
    if any(sk.entities[e].get('ref') for e in eids):
        raise SketchError('I bordi arancio sono il pezzo vero: non si cancellano né si modificano (servono per agganciarsi e per chiudere i contorni).')
    _sync(doc, sk)
    pts = set(_points_of(sk, eids))
    if ORIGIN in pts:
        raise SketchError('L’origine non si sposta: togli dalla selezione ciò che ci passa.')
    for p in pts:
        sk.entities[p]['x'] += dx
        sk.entities[p]['y'] += dy
    bloccati = []
    for cid, c in sk.constraints.items():
        refs = c['refs']
        dentro = [r in pts or r in eids for r in refs]
        if all(dentro) or not any(dentro):
            continue
        if c['type'] in ('hdistance', 'vdistance') and len(refs) == 2 and isinstance(c['value'], (int, float)):
            d = dx if c['type'] == 'hdistance' else dy
            c['value'] = _r(c['value'] + (d if refs[1] in pts else -d))
        elif c['type'] in ('horizontal', 'vertical', 'parallel', 'perpendicular', 'equal'):
            continue
        else:
            bloccati.append(sk.describe_constraint(cid))
    if bloccati:
        raise SketchError('Non si può spostare liberamente: ' + bloccati[0] + ' lo lega al resto del disegno. '
                          'Cambia quella quota, oppure togli il vincolo.')


# --------------------------------------------------------------------------- quote a mano
def add_dimension(doc, sid, kind, refs, value=None, info=None):
    """Quota a mano, come in ogni CAD: se c'è già la stessa quota si rende quella (la si cambia); se la misura è
    già decisa da un'altra quota (di solito una messa da sola mentre si disegnava), quella si toglie e comanda la
    nuova. info riceve 'esistente' o 'tolta' (la descrizione della quota sostituita)."""
    info = {} if info is None else info
    sk = doc.sketch(sid)
    if kind not in DIMENSIONS:
        raise SketchError(f'Quota "{kind}" sconosciuta.')
    for r in refs:
        if r not in sk.entities:
            raise SketchError(f'Nello sketch non c’è {r}.')
    # che cosa vuole ogni quota: tipo di elemento per ogni riferimento
    vuole = {'length': ('line',), 'diameter': ('circle',), 'radius': ('arc',), 'distance': ('point', 'point'),
             'hdistance': ('point', 'point'), 'vdistance': ('point', 'point'), 'pldistance': ('point', 'line')}.get(kind)
    nomi = {'line': 'una linea', 'circle': 'un cerchio', 'arc': 'un arco', 'point': 'un punto'}
    if vuole is not None:
        tipi = [sk.entities[r]['kind'] for r in refs]
        if len(refs) != len(vuole) or any(t != v and not (v == 'circle' and t == 'arc') for t, v in zip(tipi, vuole)):
            raise SketchError('Per questa quota scegli ' + ' e '.join(nomi[v] for v in vuole) + '.')
    simmetrica = kind in ('distance', 'length', 'diameter', 'radius')
    for cid, c in sk.constraints.items():
        if c['type'] == kind and (list(c['refs']) == list(refs) or (simmetrica and sorted(c['refs']) == sorted(refs))
                                  or (kind in ('hdistance', 'vdistance') and sorted(c['refs']) == sorted(refs))):
            info['esistente'] = True
            return cid
    pts = _solved_xy(doc, sk)
    if value is None:
        if kind == 'length':
            e = sk.entities[refs[0]]
            value = math.dist(pts[e['a']], pts[e['b']])
        elif kind == 'diameter':
            value = 2 * solve(sk, doc.resolved_parameters()).circles[refs[0]][1]
        elif kind == 'radius':
            ss = solve(sk, doc.resolved_parameters())
            value = ss.arcs[refs[0]][3] if refs[0] in ss.arcs else ss.circles[refs[0]][1]
        elif kind == 'distance':
            value = math.dist(pts[refs[0]], pts[refs[1]])
        elif kind == 'hdistance':
            value = pts[refs[1]][0] - pts[refs[0]][0]
        elif kind == 'vdistance':
            value = pts[refs[1]][1] - pts[refs[0]][1]
        elif kind == 'pldistance':
            e = sk.entities[refs[1]]
            (ax, ay), (bx, by), (px, py) = pts[e['a']], pts[e['b']], pts[refs[0]]
            value = abs((bx - ax) * (ay - py) - (ax - px) * (by - ay)) / math.hypot(bx - ax, by - ay)
        else:
            raise SketchError('Per questa quota serve il valore.')
    if kind in ('hdistance', 'vdistance') and value < 0:
        refs = [refs[1], refs[0]]
        value = -value
    if kind in ('distance', 'length', 'diameter', 'pldistance') and value <= 1e-9:
        raise SketchError('La misura è zero: i due elementi coincidono.')
    did = sk.dimension(kind, *refs, value=_r(value))
    par = doc.resolved_parameters()
    st = solve(sk, par).status
    if did not in st.redundant and did not in st.conflicting:
        return did
    # già decisa: si cerca la quota che la decide (prima quelle sugli stessi elementi, poi le più recenti) e la si
    # toglie, se senza di lei il disegno resta deciso come prima e la nuova non è più doppia
    miei = set(refs) | set(_points_of(sk, [r for r in refs if r != ORIGIN])) - {ORIGIN}
    prima = (len(st.redundant), len(st.conflicting))

    def tocca(c):
        suoi = set(c['refs']) | set(_points_of(sk, [r for r in c['refs'] if r in sk.entities and r != ORIGIN]))
        return len((suoi - {ORIGIN}) & miei)
    candidati = [cid for cid, c in sk.constraints.items() if cid != did and c['type'] in DIMENSIONS
                 and isinstance(c.get('value'), (int, float)) and not c.get('driven')]
    candidati.sort(key=lambda cid: (-tocca(sk.constraints[cid]), -int(''.join(ch for ch in cid if ch.isdigit()) or 0)))
    for cid in candidati:
        vecchio = sk.constraints.pop(cid)
        st2 = solve(sk, par).status
        if did not in st2.redundant and did not in st2.conflicting and                 (len(st2.redundant), len(st2.conflicting)) <= (max(0, prima[0] - 1), prima[1]):
            info['tolta'] = _descr(sk, cid, vecchio)
            return did
        sk.constraints[cid] = vecchio
    # nessuna quota da togliere: la decide il pezzo (i bordi arancio) o i vincoli. Come in ogni CAD la quota si
    # mette lo stesso, di riferimento: mostra la misura tra parentesi, non comanda
    sk.constraints[did]['driven'] = True
    info['guidata'] = True
    return did


QUASI = 0.01          # mm (o gradi): sotto questo scarto due quote che decidono la stessa misura non litigano


def quasi_uguali_di_riferimento(doc, sk) -> list[str]:
    """Due quote che decidono la stessa misura con valori diversi di un niente (arrotondamenti: 1119,267919 contro
    1119,268251) mettono lo sketch in conflitto e lo bloccano (21/10, il cassone). La più recente delle quote in
    conflitto diventa di riferimento, se così il conflitto sparisce e la misura vera è a meno di QUASI dalla sua.
    Ritorna le descrizioni delle quote cambiate."""
    from cad_engine.sketch.solver import misura
    par = doc.resolved_parameters()
    st = solve(sk, par).status
    fatte = []
    for _ in range(8):
        if not st.conflicting:
            break
        cand = [c for c in st.conflicting if c in sk.constraints and sk.constraints[c]['type'] in DIMENSIONS
                and isinstance(sk.constraints[c].get('value'), (int, float)) and not sk.constraints[c].get('driven')]
        cand.sort(key=lambda cid: -int(''.join(ch for ch in cid if ch.isdigit()) or 0))
        trovata = False
        for cid in cand:
            c = sk.constraints[cid]
            c['driven'] = True
            ss = solve(sk, par)
            if len(ss.status.conflicting) < len(st.conflicting) and ss.status.state != 'non risolto':
                try:
                    scarto = abs(abs(misura(ss, c)) - abs(c['value']))
                except (KeyError, ZeroDivisionError, TypeError):
                    scarto = math.inf
                if scarto <= QUASI:
                    fatte.append(sk.describe_constraint(cid))
                    st, trovata = ss.status, True
                    break
            del c['driven']
        if not trovata:
            break
    return fatte


LUNGHEZZE = ('length', 'distance', 'hdistance', 'vdistance')


def primo_punto(sk, did):
    """Il punto da cui parte una quota di lunghezza: dei suoi due punti (le punte della linea, o i due punti
    quotati) quello disegnato prima. Nel rettangolo è l'angolo da cui l'hai tirato: cambiando la larghezza o
    l'altezza resta fermo quello (il lato sinistro va dall'angolo in alto a quello in basso, ma cresce in su).
    None per le altre quote."""
    c = sk.constraints.get(did)
    if not c or c['type'] not in LUNGHEZZE:
        return None
    if c['type'] == 'length':
        e = sk.entities.get(c['refs'][0], {})
        due = [e.get('a'), e.get('b')]
    else:
        due = list(c['refs'][:2])
    if not all(sk.entities.get(p, {}).get('kind') == 'point' for p in due):
        return None
    ordine = {k: i for i, k in enumerate(sk.entities)}       # l'ordine in cui sono stati disegnati
    return min(due, key=lambda p: ordine[p])


def tieni_il_primo_punto(sk, did, prima, params) -> bool:
    """05/11 (idea da SolidCraft): cambiando una lunghezza o una distanza resta fermo il primo punto e si muove
    l'altro: il lato di un rettangolo cresce dal suo primo angolo. Il risolutore, da solo, fa la mossa più piccola
    e divide il cambiamento tra le due punte (40 → 60: 11 mm a sinistra e 9 a destra).

    Da chiamare dopo aver messo il valore nuovo in `sk` (`prima` = lo sketch risolto com'era a video). Se il primo
    punto si sposterebbe, si risolve tenendolo dov'era e le coordinate salvate diventano quelle trovate: la
    ricostruzione parte già dalla forma giusta e non ha più niente da muovere. Se tenerlo fermo non si può (una
    simmetria, un punto già deciso a metà dalle altre quote) o qualche linea si girerebbe, non cambia niente: si
    risolve come sempre. Vale solo quando si cambia una quota: i pezzi salvati si riaprono uguali."""
    import copy as _cp
    from cad_engine.sketch.solver import FULLY, UNDER
    pid = primo_punto(sk, did)
    if pid is None or pid == ORIGIN or prima is None or pid not in prima.points or sk.constraints[did].get('driven'):
        return False
    try:
        normale = solve(sk, params)
    except SteelCADError:
        normale = None
    if normale is not None and normale.status.state in (FULLY, UNDER) and \
            math.dist(normale.points.get(pid, (math.inf, 0)), prima.points[pid]) < 1e-7:
        return False                        # resta già fermo da solo (il caso di quasi tutti i disegni quotati)
    prova = _cp.deepcopy(sk)
    for k, e in prova.entities.items():     # si parte da quello che si vede
        if e['kind'] == 'point' and k in prima.points and k != ORIGIN:
            e['x'], e['y'] = (float(t) for t in prima.points[k])
        elif e['kind'] == 'circle' and k in prima.circles:
            e['r'] = float(prima.circles[k][1])
    prova.constraints['_fermo'] = {'type': 'fix', 'refs': [pid]}
    try:
        ss = solve(prova, params)
    except SteelCADError:
        return False
    if ss.status.state not in (FULLY, UNDER):
        return False
    for lid, (a, b) in prima.lines.items():  # nessuna linea si gira al contrario
        if lid not in ss.lines or a not in ss.points or b not in ss.points:
            continue
        u = (prima.points[b][0] - prima.points[a][0], prima.points[b][1] - prima.points[a][1])
        w = (ss.points[b][0] - ss.points[a][0], ss.points[b][1] - ss.points[a][1])
        if math.hypot(*u) > 1e-6 and math.hypot(*w) > 1e-6 and u[0] * w[0] + u[1] * w[1] < 0:
            return False
    for k, e in sk.entities.items():
        if e['kind'] == 'point' and k in ss.points and k != ORIGIN:
            e['x'], e['y'] = float(ss.points[k][0]), float(ss.points[k][1])
        elif e['kind'] == 'circle' and k in ss.circles:
            e['r'] = float(ss.circles[k][1])
    return True


def _descr(sk, cid, c):
    sk.constraints[cid] = c
    try:
        return sk.describe_constraint(cid)
    finally:
        del sk.constraints[cid]


# le forme nuove passano dal controllo delle quote doppie, come quelle disegnate
offset = guarded(offset)
mirror = guarded(mirror)
copy = guarded(copy)
pattern = guarded(pattern)
pattern_circular = guarded(pattern_circular)
