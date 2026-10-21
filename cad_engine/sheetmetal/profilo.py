"""Profilo estruso in lamiera (21/10, Stefano: «disegnare il profilo, estruderlo e farlo diventare una lamiera
fatta in bumping»).

Il profilo è una catena aperta di linee e archi disegnata in uno sketch. Ogni spigolo è una piega; ogni arco
diventa N colpi (bumping): il poligono tangente all'arco, con N pieghe da angolo/N. La linea disegnata è una
faccia della lamiera (di solito quella interna: lo spessore va dalla parte convessa), lo spessore dall'altra.
Il pezzo è la sezione estrusa della lunghezza data; lo sviluppo si calcola con raggio e K della piegatrice:
tratti dritti tra le pieghe (meno gli arretramenti) più gli archi della fibra neutra.
"""
from __future__ import annotations

import math

import build123d as bd

from ..errors import FeatureError
from ..units import fmt_mm

TOL = 1e-3


def catena(ss, fid) -> list:
    """Le linee e gli archi (non di costruzione) dello sketch in fila, dal capo libero: [('L', p0, p1) |
    ('A', centro, raggio, angolo iniziale, ampiezza con segno, p0, p1)]."""
    sk = ss.sketch
    pezzi = []
    for eid, (a, b) in ss.lines.items():
        if sk.entities[eid].get('construction'):
            continue
        pezzi.append({'k': 'L', 'p': [ss.points[a], ss.points[b]]})
    for eid, (c, a, b, r) in ss.arcs.items():
        if sk.entities[eid].get('construction'):
            continue
        cx, cy = ss.points[c]
        pa, pb = ss.points[a], ss.points[b]
        a0 = math.atan2(pa[1] - cy, pa[0] - cx)
        a1 = math.atan2(pb[1] - cy, pb[0] - cx)
        while a1 <= a0:
            a1 += 2 * math.pi
        pezzi.append({'k': 'A', 'p': [pa, pb], 'c': (cx, cy), 'r': r, 'a0': a0, 'sweep': a1 - a0})
    if not pezzi:
        raise FeatureError('Disegna il profilo con linee e archi (le linee di costruzione non contano).', feature=fid)
    if any(e['kind'] == 'circle' and not e.get('construction') for e in sk.entities.values()):
        raise FeatureError('Nel profilo non ci vanno cerchi interi: usa archi.', feature=fid)
    uguale = lambda p, q: math.dist(p, q) < TOL  # noqa: E731
    capi = []
    for e in pezzi:
        for q in e['p']:
            n = sum(1 for f in pezzi for w in f['p'] if uguale(q, w))
            if n == 1:
                capi.append(q)
            elif n > 2:
                raise FeatureError('Il profilo si dirama: deve essere una sola fila di linee e archi.', feature=fid)
    if not capi:
        raise FeatureError('Il profilo è chiuso: per una lamiera piegata lascialo aperto (un capo e una coda).',
                           feature=fid)
    if len(capi) != 2:
        raise FeatureError('Il profilo è spezzato in più pezzi: collega le linee una all’altra.', feature=fid)
    fila, cur, usati = [], min(capi), set()
    while len(usati) < len(pezzi):
        k = next((i for i, e in enumerate(pezzi) if i not in usati and any(uguale(cur, w) for w in e['p'])), None)
        if k is None:
            raise FeatureError('Il profilo è spezzato: collega le linee una all’altra.', feature=fid)
        usati.add(k)
        e = pezzi[k]
        avanti = uguale(cur, e['p'][0])
        p0, p1 = (e['p'][0], e['p'][1]) if avanti else (e['p'][1], e['p'][0])
        if e['k'] == 'L':
            fila.append(('L', p0, p1))
        else:
            s0, sw = (e['a0'], e['sweep']) if avanti else (e['a0'] + e['sweep'], -e['sweep'])
            fila.append(('A', e['c'], e['r'], s0, sw, p0, p1))
        cur = p1
    return fila


def spigoli(fila, colpi, passo, fid) -> tuple[list, list]:
    """La linea disegnata come poligono di spigoli vivi: gli archi diventano N colpi (poligono tangente).
    Ritorna (punti, colpi per arco)."""
    pts = [fila[0][1]]
    n_archi = []
    for s in fila:
        if s[0] == 'L':
            pts.append(s[2])
            continue
        _, c, r, s0, sw, _p0, p1 = s
        lung = abs(sw) * r
        n = int(colpi) if colpi else max(2, math.ceil(lung / (passo or 20.0)))
        if n < 1 or n > 400:
            raise FeatureError('I colpi per arco vanno da 1 a 400.', feature=fid)
        beta = sw / n
        if abs(beta) > math.radians(90) + 1e-9:
            raise FeatureError(f'Con {n} colpi ogni piega sarebbe di {fmt_mm(round(math.degrees(abs(beta)), 1))}°: '
                               'servono più colpi.', feature=fid)
        rv = r / math.cos(beta / 2)
        for k in range(1, n + 1):
            th = s0 + (k - 0.5) * beta
            pts.append((c[0] + rv * math.cos(th), c[1] + rv * math.sin(th)))
        pts.append(p1)
        n_archi.append(n)
    # via punti doppi e allineati (un arco tangente alla linea: il primo tratto del poligono continua la linea)
    pulito = [pts[0]]
    for q in pts[1:]:
        if math.dist(q, pulito[-1]) > TOL:
            pulito.append(q)
    i = 1
    while i < len(pulito) - 1:
        a, b, c = pulito[i - 1], pulito[i], pulito[i + 1]
        u = (b[0] - a[0], b[1] - a[1])
        v = (c[0] - b[0], c[1] - b[1])
        if abs(u[0] * v[1] - u[1] * v[0]) < 1e-9 * math.hypot(*u) * math.hypot(*v) and u[0] * v[0] + u[1] * v[1] > 0:
            del pulito[i]
        else:
            i += 1
    if len(pulito) < 2:
        raise FeatureError('Il profilo è troppo corto.', feature=fid)
    return pulito, n_archi


def _giri(pts):
    """Angolo di piega con segno a ogni spigolo interno (+ a sinistra)."""
    out = []
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        u = math.atan2(b[1] - a[1], b[0] - a[0])
        v = math.atan2(c[1] - b[1], c[0] - b[0])
        d = (v - u + math.pi) % (2 * math.pi) - math.pi
        out.append(d)
    return out


def _sposta(pts, t, lato):
    """La polilinea spostata di t dal lato del materiale (lato = +1 sinistra, -1 destra), spigoli a spigolo vivo."""
    righe = []
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        nx, ny = -dy / L * lato, dx / L * lato
        righe.append(((a[0] + nx * t, a[1] + ny * t), (b[0] + nx * t, b[1] + ny * t)))
    out = [righe[0][0]]
    for (p, q), (r, s) in zip(righe, righe[1:]):
        d1, d2 = (q[0] - p[0], q[1] - p[1]), (s[0] - r[0], s[1] - r[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-12:
            out.append(q)
            continue
        tt = ((r[0] - p[0]) * d2[1] - (r[1] - p[1]) * d2[0]) / den
        out.append((p[0] + d1[0] * tt, p[1] + d1[1] * tt))
    out.append(righe[-1][1])
    return out


def costruisci(ss, plane, L, t, r_piega, k_piega, colpi, passo, gira, fid):
    """Solido, sviluppo (rettangolo con le linee dei colpi), righe della tabella e info."""
    fila = catena(ss, fid)
    pts, n_archi = spigoli(fila, colpi, passo, fid)
    giri = _giri(pts)
    totale = sum(giri)
    lato = -1 if totale >= 0 else 1                  # lo spessore dalla parte convessa: la linea è la faccia interna
    if gira:
        lato = -lato
    altro = _sposta(pts, t, lato)
    sezione = [plane.from_local_coords(q) for q in pts + list(reversed(altro))]
    try:
        faccia = bd.Face(bd.Wire.make_polygon(sezione, close=True))
        solido = bd.extrude(faccia, amount=L, dir=plane.z_dir)
    except Exception as ex:  # noqa: BLE001
        raise FeatureError(f'La sezione del profilo non si chiude ({ex}): pieghe troppo strette per lo spessore?',
                           feature=fid) from None
    if solido.volume < 0:
        solido = bd.extrude(faccia, amount=-L, dir=plane.z_dir)
    # sviluppo: tratti dritti (dalla linea disegnata, meno gli arretramenti) + archi della fibra neutra
    con_dati = r_piega is not None and k_piega is not None
    rp = r_piega if r_piega is not None else 0.0
    kk = k_piega if k_piega is not None else 0.5
    lati = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    arretra, archi, righe = [], [], []
    for j, phi in enumerate(giri):
        dentro = (phi > 0 and lato < 0) or (phi < 0 and lato > 0)      # la linea disegnata sta dentro la piega
        tg = math.tan(abs(phi) / 2)
        arretra.append(rp * tg if dentro else (rp + t) * tg)
        archi.append(abs(phi) * (rp + kk * t))
    dritti = []
    for i, ell in enumerate(lati):
        d = ell - (arretra[i - 1] if i > 0 else 0) - (arretra[i] if i < len(arretra) else 0)
        if d < -1e-6:
            raise FeatureError(f'Tra la piega {i} e la {i + 1} il tratto dritto non basta per il raggio di piega: '
                               'meno colpi o raggio più piccolo.', feature=fid)
        dritti.append(max(0.0, d))
    lungo = sum(dritti) + sum(archi)
    flat = bd.Face(bd.Wire.make_polygon([(0, 0, 0), (lungo, 0, 0), (lungo, L, 0), (0, L, 0)], close=True))
    linee, x = [], 0.0
    for j, phi in enumerate(giri):
        x += dritti[j]
        centro = x + archi[j] / 2
        x += archi[j]
        ang = math.degrees(abs(phi))
        bd_ = 2 * (rp + t) * math.tan(abs(phi) / 2) - archi[j]         # detrazione sugli spigoli esterni
        righe.append({'n': j + 1, 'angle': ang, 'length': L, 'correction': bd_ if con_dati else None,
                      'position': centro, 'direction': 'up' if phi > 0 else 'down'})
        linee.append(((centro, 0.0), (centro, L), f'P{j + 1} {fmt_mm(round(ang, 1))}° a {fmt_mm(round(centro, 1))}'))
    info = {'pieghe': len(giri), 'colpi': n_archi, 'sviluppo': lungo, 'lunghezza': L,
            'angolo_max': max((x['angle'] for x in righe), default=0.0),
            'correzione_totale': sum(x['correction'] or 0 for x in righe), 'avvisi': []}
    if not con_dati:
        info['avvisi'].append('Raggio e K non impostati: sviluppo calcolato a spigolo vivo con K 0,5.')
    return solido, flat, linee, righe, info
