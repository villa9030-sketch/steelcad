"""Ellissi e curve libere (spline per punti) dello sketch: i conti, senza il kernel.

- **Ellisse**: centro C, fine dell'asse grande M, fine dell'asse piccolo N (sempre a +90° dall'asse grande, come in
  FreeCAD). Punto al parametro u: C + cos(u)·(M−C) + sin(u)·(N−C). L'arco di ellisse va in senso antiorario dal
  punto di partenza a quello di arrivo.
- **Curva libera**: passa per i punti cliccati. Spline cubica C2 con i parametri a lunghezza di corda: aperta con le
  estremità «naturali» (curvatura zero), chiusa periodica. Ogni tratto tra due punti è una cubica di Bézier: la
  stessa curva va nel 3D (B-spline esatta), sullo schermo e nel DXF.
- **Archi tangenti** (biarchi): il laser (Lantek) vuole linee e archi. Ellissi e curve libere si scrivono come archi
  che si toccano tangenti, entro una tolleranza piccola (TOLL_ARCHI). Pezzi come quelli dei testi tagliati:
  ('L', a, b) linea, ('A', a, m, b) arco per tre punti.
"""
from __future__ import annotations

import math

TOLL_ARCHI = 0.01          # mm: quanto gli archi del DXF possono stare lontani dalla curva vera (da decidere con Stefano)


# ================================================================================ ellisse
def ellisse_assi(c, m, n) -> tuple:
    """(a, b, angolo dell'asse grande in radianti) dai tre punti."""
    a = math.hypot(m[0] - c[0], m[1] - c[1])
    b = math.hypot(n[0] - c[0], n[1] - c[1])
    return a, b, math.atan2(m[1] - c[1], m[0] - c[0])


def ellisse_punto(c, a, b, ang, u):
    ca, sa = math.cos(ang), math.sin(ang)
    x, y = a * math.cos(u), b * math.sin(u)
    return (c[0] + x * ca - y * sa, c[1] + x * sa + y * ca)


def ellisse_derivata(c, a, b, ang, u):
    ca, sa = math.cos(ang), math.sin(ang)
    x, y = -a * math.sin(u), b * math.cos(u)
    return (x * ca - y * sa, x * sa + y * ca)


def ellisse_parametro(c, a, b, ang, p) -> float:
    """Il parametro u del punto dell'ellisse più vicino (circa) a p: l'angolo «schiacciato»."""
    ca, sa = math.cos(ang), math.sin(ang)
    dx, dy = p[0] - c[0], p[1] - c[1]
    x, y = dx * ca + dy * sa, -dx * sa + dy * ca
    u = math.atan2(y / max(b, 1e-12), x / max(a, 1e-12))
    for _ in range(6):                      # qualche passo di Newton sulla distanza: il punto davvero più vicino
        px, py = a * math.cos(u), b * math.sin(u)
        tx, ty = -a * math.sin(u), b * math.cos(u)
        f = (px - x) * tx + (py - y) * ty
        df = tx * tx + ty * ty + (px - x) * (-a * math.cos(u)) + (py - y) * (-b * math.sin(u))
        if abs(df) < 1e-12:
            break
        u -= f / df
    return u


def ellisse_intervallo(c, m, n, s=None, e=None) -> tuple:
    """(a, b, angolo, u0, u1): tutta l'ellisse (0, 2π) o l'arco da s a e in senso antiorario."""
    a, b, ang = ellisse_assi(c, m, n)
    if s is None or e is None:
        return a, b, ang, 0.0, 2 * math.pi
    u0 = ellisse_parametro(c, a, b, ang, s)
    u1 = ellisse_parametro(c, a, b, ang, e)
    while u1 <= u0 + 1e-12:
        u1 += 2 * math.pi
    return a, b, ang, u0, u1


def ellisse_campioni(c, m, n, s=None, e=None, quanti: int = 96) -> list:
    a, b, ang, u0, u1 = ellisse_intervallo(c, m, n, s, e)
    k = max(8, int(quanti * (u1 - u0) / (2 * math.pi)))
    return [ellisse_punto(c, a, b, ang, u0 + (u1 - u0) * i / k) for i in range(k + 1)]


# ================================================================================ curva libera
def _risolvi(A, rhs):
    """Sistema lineare piccolo (eliminazione di Gauss con pivot): niente dipendenze."""
    n = len(rhs)
    M = [row[:] + [rhs[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        M[col], M[piv] = M[piv], M[col]
        p = M[col][col]
        if abs(p) < 1e-300:
            continue
        for r in range(n):
            if r != col and M[r][col]:
                f = M[r][col] / p
                for k in range(col, n + 1):
                    M[r][k] -= f * M[col][k]
    return [M[i][n] / M[i][i] if abs(M[i][i]) > 1e-300 else 0.0 for i in range(n)]


def spline_bezier(pts, chiusa: bool = False) -> list:
    """I tratti di Bézier cubici della curva per i punti: [(P0, P1, P2, P3, h)], h = lunghezza della corda (il passo
    del parametro). Punti uguali di fila si saltano."""
    q = []
    for p in pts:
        p = (float(p[0]), float(p[1]))
        if not q or math.dist(p, q[-1]) > 1e-9:
            q.append(p)
    if chiusa and len(q) > 2 and math.dist(q[0], q[-1]) <= 1e-9:
        q.pop()
    if len(q) < 2:
        return []
    if chiusa and len(q) < 3:
        chiusa = False
    if chiusa:
        q = q + [q[0]]
    n = len(q) - 1                                    # tratti
    h = [max(math.dist(q[i], q[i + 1]), 1e-9) for i in range(n)]
    der = []                                          # derivate seconde M_i per x e y
    for k in (0, 1):
        y = [p[k] for p in q]
        if chiusa:
            # periodica: M_0 = M_n; n incognite M_0..M_{n-1}
            A = [[0.0] * n for _ in range(n)]
            r = [0.0] * n
            for i in range(n):
                hp, hn = h[i - 1], h[i]                # h[-1] = l'ultimo tratto (chiude)
                A[i][(i - 1) % n] += hp
                A[i][i] += 2 * (hp + hn)
                A[i][(i + 1) % n] += hn
                yp, yn = y[i - 1] if i else y[n - 1], y[i + 1]
                r[i] = 6 * ((yn - y[i]) / hn - (y[i] - yp) / hp)
            m = _risolvi(A, r)
            der.append(m + [m[0]])
        elif n == 1:
            der.append([0.0, 0.0])
        else:
            # naturale: M_0 = M_n = 0
            A = [[0.0] * (n - 1) for _ in range(n - 1)]
            r = [0.0] * (n - 1)
            for j in range(n - 1):
                i = j + 1
                if j:
                    A[j][j - 1] = h[i - 1]
                A[j][j] = 2 * (h[i - 1] + h[i])
                if j < n - 2:
                    A[j][j + 1] = h[i]
                r[j] = 6 * ((y[i + 1] - y[i]) / h[i] - (y[i] - y[i - 1]) / h[i - 1])
            der.append([0.0] + _risolvi(A, r) + [0.0])
    out = []
    for i in range(n):
        hi = h[i]
        d0, d1 = [], []
        for k in (0, 1):
            y0, y1, m0, m1 = q[i][k], q[i + 1][k], der[k][i], der[k][i + 1]
            s = (y1 - y0) / hi
            d0.append(s - m0 * hi / 3 - m1 * hi / 6)       # derivata all'inizio del tratto
            d1.append(s + m0 * hi / 6 + m1 * hi / 3)       # e alla fine
        P0, P3 = q[i], q[i + 1]
        P1 = (P0[0] + d0[0] * hi / 3, P0[1] + d0[1] * hi / 3)
        P2 = (P3[0] - d1[0] * hi / 3, P3[1] - d1[1] * hi / 3)
        out.append((P0, P1, P2, P3, hi))
    return out


def bezier_punto(b, t):
    P0, P1, P2, P3 = b[:4]
    s = 1 - t
    return (s ** 3 * P0[0] + 3 * s * s * t * P1[0] + 3 * s * t * t * P2[0] + t ** 3 * P3[0],
            s ** 3 * P0[1] + 3 * s * s * t * P1[1] + 3 * s * t * t * P2[1] + t ** 3 * P3[1])


def bezier_derivata(b, t):
    P0, P1, P2, P3 = b[:4]
    s = 1 - t
    return (3 * s * s * (P1[0] - P0[0]) + 6 * s * t * (P2[0] - P1[0]) + 3 * t * t * (P3[0] - P2[0]),
            3 * s * s * (P1[1] - P0[1]) + 6 * s * t * (P2[1] - P1[1]) + 3 * t * t * (P3[1] - P2[1]))


def spline_campioni(pts, chiusa: bool = False, per_tratto: int = 16) -> list:
    out = []
    for i, b in enumerate(spline_bezier(pts, chiusa)):
        for k in range(0 if i == 0 else 1, per_tratto + 1):
            out.append(bezier_punto(b, k / per_tratto))
    return out


# ================================================================================ archi tangenti
def _unit(v):
    L = math.hypot(*v)
    return (v[0] / L, v[1] / L) if L > 1e-15 else None


def _arco_da_tangente(P, T, Q):
    """L'arco che parte da P con tangente T e arriva in Q: ('A', P, mezzo, Q, centro, r, inizio, ampiezza con
    segno) oppure ('L', P, Q) se è dritto."""
    n = (-T[1], T[0])
    v = (Q[0] - P[0], Q[1] - P[1])
    den = 2 * (v[0] * n[0] + v[1] * n[1])
    vv = v[0] ** 2 + v[1] ** 2
    if abs(den) < 1e-12 * max(1.0, math.sqrt(vv)) or vv / abs(den) > 1e7:
        return ('L', P, Q)
    r = vv / den                                       # con segno: >0 il centro sta a sinistra (antiorario)
    c = (P[0] + n[0] * r, P[1] + n[1] * r)
    t0 = math.atan2(P[1] - c[1], P[0] - c[0])
    t1 = math.atan2(Q[1] - c[1], Q[0] - c[0])
    sw = t1 - t0
    if r > 0:
        while sw <= 0:
            sw += 2 * math.pi
    else:
        while sw >= 0:
            sw -= 2 * math.pi
    tm = t0 + sw / 2
    R = abs(r)
    return ('A', P, (c[0] + R * math.cos(tm), c[1] + R * math.sin(tm)), Q, c, R, t0, sw)


def _biarco(P0, T0, P1, T1):
    v = (P1[0] - P0[0], P1[1] - P0[1])
    vv = v[0] ** 2 + v[1] ** 2
    if vv < 1e-18:
        return []
    t = (T0[0] + T1[0], T0[1] + T1[1])
    vt = v[0] * t[0] + v[1] * t[1]
    k = 2 * (1 - (T0[0] * T1[0] + T0[1] * T1[1]))
    if abs(k) < 1e-12:
        if vt <= 1e-12:
            return None
        d = vv / (2 * vt)
    else:
        d = (-vt + math.sqrt(max(vt * vt + k * vv, 0.0))) / k
    if not (d > 0) or not math.isfinite(d):
        return None
    Q0 = (P0[0] + d * T0[0], P0[1] + d * T0[1])
    Q1 = (P1[0] - d * T1[0], P1[1] - d * T1[1])
    J = ((Q0[0] + Q1[0]) / 2, (Q0[1] + Q1[1]) / 2)
    a1 = _arco_da_tangente(P0, T0, J)
    a2 = _arco_da_tangente(P1, (-T1[0], -T1[1]), J)
    a2 = _rovescia(a2)
    return [a1, a2]


def _rovescia(p):
    if p[0] == 'L':
        return ('L', p[2], p[1])
    _, P, m, Q, c, R, t0, sw = p
    return ('A', Q, m, P, c, R, t0 + sw, -sw)


def _distanza(p, q) -> float:
    if p[0] == 'L':
        (ax, ay), (bx, by) = p[1], p[2]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 < 1e-24 else max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / L2))
        return math.hypot(ax + t * dx - q[0], ay + t * dy - q[1])
    _, P, m, Q, c, R, t0, sw = p
    a = math.atan2(q[1] - c[1], q[0] - c[0])
    rel = (a - t0) * (1 if sw > 0 else -1)
    rel %= 2 * math.pi
    if rel <= abs(sw):
        return abs(math.hypot(q[0] - c[0], q[1] - c[1]) - R)
    return min(math.dist(q, P), math.dist(q, Q))


def in_archi(punto, derivata, u0: float, u1: float, toll: float = TOLL_ARCHI, profondita: int = 0) -> list:
    """La curva (punto(u), derivata(u)) tra u0 e u1 in archi tangenti entro toll: [('L', a, b) | ('A', a, m, b)]."""
    P0, P1 = punto(u0), punto(u1)
    T0, T1 = _unit(derivata(u0)), _unit(derivata(u1))
    pezzi = None
    if T0 is not None and T1 is not None:
        pezzi = _biarco(P0, T0, P1, T1)
    if pezzi is not None:
        if not pezzi:
            return []
        err = 0.0
        for i in range(1, 16):                         # 16 punti della curva, con un po' di margine
            q = punto(u0 + (u1 - u0) * i / 16)
            err = max(err, min(_distanza(p, q) for p in pezzi))
            if err > 0.8 * toll:
                break
        # pezzi più corti di 0,05 mm non si dividono più (il laser non li vuole e l'errore lì è già minimo)
        if err <= 0.8 * toll or profondita >= 16 or math.dist(P0, P1) < 0.05:
            return [p[:3] if p[0] == 'L' else p[:4] for p in pezzi]
    elif profondita >= 16:
        return [('L', P0, P1)]
    um = (u0 + u1) / 2
    return (in_archi(punto, derivata, u0, um, toll, profondita + 1)
            + in_archi(punto, derivata, um, u1, toll, profondita + 1))


def ellisse_in_archi(c, m, n, s=None, e=None, toll: float = TOLL_ARCHI) -> list:
    a, b, ang, u0, u1 = ellisse_intervallo(c, m, n, s, e)
    pezzi = []
    k = max(1, math.ceil((u1 - u0) / (math.pi / 2) - 1e-9))     # almeno un pezzo per quarto: i vertici ci cadono
    for i in range(k):
        pezzi += in_archi(lambda u: ellisse_punto(c, a, b, ang, u), lambda u: ellisse_derivata(c, a, b, ang, u),
                          u0 + (u1 - u0) * i / k, u0 + (u1 - u0) * (i + 1) / k, toll)
    return _cuci(pezzi)


def spline_in_archi(pts, chiusa: bool = False, toll: float = TOLL_ARCHI) -> list:
    pezzi = []
    for b in spline_bezier(pts, chiusa):
        pezzi += in_archi(lambda t, b=b: bezier_punto(b, t), lambda t, b=b: bezier_derivata(b, t), 0.0, 1.0, toll)
    return _cuci(pezzi)


def _cuci(pezzi: list) -> list:
    """Ogni pezzo comincia esattamente dove finisce quello prima (niente fessure da arrotondamenti)."""
    out = []
    for p in pezzi:
        if out:
            p = (p[0], out[-1][-1]) + tuple(p[2:])
        if math.dist(p[1], p[-1]) < 1e-9:
            continue
        out.append(p)
    return out


def centro3(a, m, b):
    """Il centro del cerchio per tre punti (None se sono in fila)."""
    (ax, ay), (bx, by), (cx, cy) = a, m, b
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return (ux, uy)


def arco_dxf(a, m, b):
    """Dall'arco per tre punti ai dati di un ARC del DXF: (centro, raggio, gradi inizio, gradi fine) in senso
    antiorario; None se i tre punti sono in fila."""
    c = centro3(a, m, b)
    if c is None:
        return None
    t0 = math.degrees(math.atan2(a[1] - c[1], a[0] - c[0]))
    t1 = math.degrees(math.atan2(b[1] - c[1], b[0] - c[0]))
    tm = math.degrees(math.atan2(m[1] - c[1], m[0] - c[0]))
    if not (tm - t0) % 360 < (t1 - t0) % 360:
        t0, t1 = t1, t0
    return c, math.dist(c, a), t0 % 360, t1 % 360
