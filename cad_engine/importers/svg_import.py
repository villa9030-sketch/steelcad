"""Import di un disegno SVG (un logo, una sagoma) dentro uno sketch (05/11, idea da SolidCraft sketch.insert_svg).

Come l'import del DXF: si legge il file, si mostra, e si mette nel disegno dove e quanto grande dici tu (la
larghezza in mm, l'altezza segue). Le curve dell'SVG (Bézier, archi d'ellisse) diventano archi di cerchio e
linee, entro un errore piccolo (TOL mm sulla misura finale): il laser taglia archi veri, non mille trattini.
I testi dell'SVG non si leggono (vanno trasformati in tracciati nel programma di grafica): si dice quanti sono.
La lettura usa svgelements (già nel programma con build123d): niente servizi esterni.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import SteelCADError

TOL = 0.02          # mm: quanto una linea o un arco può scostarsi dalla curva dell'SVG
PX_MM = 25.4 / 96   # l'SVG misura in px a 96 dpi (svgelements riporta tutto lì, con le sue trasformazioni)


@dataclass
class DisegnoSvg:
    file: str
    sottotracciati: list = field(default_factory=list)   # liste di segmenti svgelements (coordinate in px, y in giù)
    cerchi: list = field(default_factory=list)            # (cx, cy, r) in px
    testi: int = 0
    bbox: tuple = (0.0, 0.0, 0.0, 0.0)                    # xmin, ymin, xmax, ymax in px

    @property
    def larghezza_mm(self) -> float:
        return (self.bbox[2] - self.bbox[0]) * PX_MM

    @property
    def altezza_mm(self) -> float:
        return (self.bbox[3] - self.bbox[1]) * PX_MM


def leggi(path) -> DisegnoSvg:
    import svgelements as S
    p = Path(path)
    if not p.is_file():
        raise SteelCADError(f'Il file {p.name} non c’è.', code='import')
    try:
        doc = S.SVG.parse(str(p))
    except Exception as ex:  # noqa: BLE001 - un SVG rovinato: lo si dice in parole semplici
        raise SteelCADError(f'Il file {p.name} non si legge come disegno SVG ({type(ex).__name__}).', code='import') from None
    out = DisegnoSvg(str(p))
    xs, ys = [], []
    for e in doc.elements():
        if isinstance(e, S.Text):
            out.testi += 1
            continue
        if not isinstance(e, S.Shape):
            continue
        try:
            if e.values.get('visibility') == 'hidden' or e.values.get('display') == 'none':
                continue
        except AttributeError:
            pass
        if isinstance(e, (S.Circle, S.Ellipse)):
            rx, ry = e.implicit_rx, e.implicit_ry
            if rx and ry and abs(rx - ry) <= 1e-6 * max(rx, ry) and _senza_storture(e):
                c = e.implicit_center
                out.cerchi.append((c.x, c.y, rx))
                xs += [c.x - rx, c.x + rx]
                ys += [c.y - rx, c.y + rx]
                continue
        corrente = []
        for seg in S.Path(e).segments():
            if isinstance(seg, S.Move):
                if corrente:
                    out.sottotracciati.append(corrente)
                corrente = []
                continue
            if seg.start is None or seg.end is None:
                continue
            if isinstance(seg, S.Close) and math.dist(seg.start, seg.end) < 1e-9:
                continue
            corrente.append(seg)
            for t in (0, 0.25, 0.5, 0.75, 1):
                q = seg.point(t)
                xs.append(q.x)
                ys.append(q.y)
        if corrente:
            out.sottotracciati.append(corrente)
    if not xs:
        cosa = (f' (ci sono {out.testi} testi: nel programma di grafica trasformali in tracciati, «converti in curve»)'
                if out.testi else '')
        raise SteelCADError(f'Nel file {p.name} non ci sono linee da importare{cosa}.', code='import')
    out.bbox = (min(xs), min(ys), max(xs), max(ys))
    if out.bbox[2] - out.bbox[0] <= 0 and out.bbox[3] - out.bbox[1] <= 0:
        raise SteelCADError(f'Il disegno di {p.name} non ha misura.', code='import')
    return out


def _senza_storture(e) -> bool:
    """Il cerchio resta un cerchio (niente scala diversa in x e y, niente inclinazione)."""
    try:
        m = e.transform
        return abs(m.a * m.b + m.c * m.d) < 1e-9 and abs(math.hypot(m.a, m.b) - math.hypot(m.c, m.d)) < 1e-9
    except AttributeError:
        return True


def _cerchio_per_3(a, m, b):
    ax, ay = a
    bx, by = m
    cx, cy = b
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return (ux, uy), math.dist((ux, uy), a)


def _dist_retta(q, a, b):
    L = math.dist(a, b)
    if L < 1e-12:
        return math.dist(q, a)
    return abs((b[0] - a[0]) * (a[1] - q[1]) - (a[0] - q[0]) * (b[1] - a[1])) / L


def _spezza(P, t0, t1, tol, prof=0) -> list:
    """Una curva (P: t → (x, y)) fra t0 e t1 come linee ('L', a, b) e archi ('A', a, m, b)."""
    a, b = P(t0), P(t1)
    tm = (t0 + t1) / 2
    m = P(tm)
    q1, q3 = P(t0 + (t1 - t0) / 4), P(t0 + 3 * (t1 - t0) / 4)
    if max(_dist_retta(q, a, b) for q in (m, q1, q3)) <= tol and math.dist(a, b) > 0:
        return [('L', a, b)]
    if prof < 12:
        c = _cerchio_per_3(a, m, b)
        if c is not None and math.dist(a, b) > 1e-9:
            (cx, cy), r = c
            # q1 e q3 sul cerchio e dalla parte giusta (lo stesso lato della corda di m)
            lato = lambda q: (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])  # noqa: E731
            if all(abs(math.dist(q, (cx, cy)) - r) <= tol and lato(q) * lato(m) > 0 for q in (q1, q3)):
                return [('A', a, m, b)]
        return _spezza(P, t0, tm, tol, prof + 1) + _spezza(P, tm, t1, tol, prof + 1)
    return [('L', a, m), ('L', m, b)]


def geometria(dis: DisegnoSvg, larghezza: float, x0: float = 0.0, y0: float = 0.0) -> dict:
    """Il disegno nelle coordinate dello sketch: largo `larghezza` mm, l'angolo in basso a sinistra in (x0, y0).
    {'giri': [[('L', a, b) | ('A', a, m, b), ...]], 'cerchi': [((cx, cy), r)], 'scala': mm per px, 'w', 'h'}"""
    import svgelements as S
    if not larghezza or larghezza <= 0:
        raise SteelCADError('La larghezza deve essere maggiore di zero.', code='dato')
    xmin, ymin, xmax, ymax = dis.bbox
    w_px, h_px = xmax - xmin, ymax - ymin
    k = larghezza / (w_px if w_px > 0 else h_px)
    tol_px = TOL / k

    def a_sketch(q):
        return (x0 + (q[0] - xmin) * k, y0 + (ymax - q[1]) * k)      # l'SVG ha la y in giù

    giri = []
    for sotto in dis.sottotracciati:
        giro = []
        for seg in sotto:
            if isinstance(seg, (S.Line, S.Close)):
                if math.dist(seg.start, seg.end) * k > 1e-6:
                    giro.append(('L', a_sketch(seg.start), a_sketch(seg.end)))
                continue
            P = lambda t, s=seg: (lambda q: (q.x, q.y))(s.point(t))  # noqa: E731
            for pz in _spezza(P, 0.0, 1.0, tol_px):
                giro.append((pz[0], *(a_sketch(q) for q in pz[1:])))
        if giro:
            giri.append(giro)
    cerchi = [(a_sketch((cx, cy)), r * k) for cx, cy, r in dis.cerchi]
    return {'giri': giri, 'cerchi': cerchi, 'scala': k, 'w': w_px * k, 'h': h_px * k}


def polilinee(geo: dict) -> list:
    """Per l'anteprima: ogni pezzo come una spezzata (gli archi in 16 tratti)."""
    out = []
    for giro in geo['giri']:
        linea = []
        for pz in giro:
            if pz[0] == 'L':
                tratto = [pz[1], pz[2]]
            else:
                a, m, b = pz[1:]
                c = _cerchio_per_3(a, m, b)
                if c is None:
                    tratto = [a, b]
                else:
                    (cx, cy), r = c
                    t0, tm_, t1 = (math.atan2(q[1] - cy, q[0] - cx) for q in (a, m, b))
                    giro_ = lambda u: (u - t0) % (2 * math.pi)  # noqa: E731
                    sweep = giro_(t1) if giro_(tm_) < giro_(t1) else giro_(t1) - 2 * math.pi
                    tratto = [(cx + r * math.cos(t0 + sweep * i / 16), cy + r * math.sin(t0 + sweep * i / 16))
                              for i in range(17)]
            if linea and math.dist(linea[-1], tratto[0]) < 1e-9:
                linea += [list(q) for q in tratto[1:]]
            else:
                if linea:
                    out.append(linea)
                linea = [list(q) for q in tratto]
        if linea:
            out.append(linea)
    for (cx, cy), r in geo['cerchi']:
        out.append([[cx + r * math.cos(2 * math.pi * i / 48), cy + r * math.sin(2 * math.pi * i / 48)] for i in range(49)])
    return out


def nello_sketch(sk, geo: dict) -> dict:
    """Mette la geometria nello sketch: punti bloccati dove sono, anche i centri degli archi (il disegno resta
    com'è e risulta tutto definito; si sblocca con «Sistema il disegno»), archi veri, cerchi col loro diametro.
    Rende quanti pezzi."""
    punti: dict = {}

    def pt(q):
        key = (round(q[0], 5), round(q[1], 5))
        if key not in punti:
            pid = sk.point(q[0], q[1])
            sk.constrain('fix', pid)
            punti[key] = pid
        return punti[key]

    n = {'linee': 0, 'archi': 0, 'cerchi': 0}
    for giro in geo['giri']:
        for pz in giro:
            if pz[0] == 'L':
                a, b = pt(pz[1]), pt(pz[2])
                if a != b:
                    sk.line(a, b)
                    n['linee'] += 1
                continue
            a, m, b = pz[1:]
            c = _cerchio_per_3(a, m, b)
            pa, pb = pt(a), pt(b)
            if c is None or pa == pb:
                if pa != pb:
                    sk.line(pa, pb)
                    n['linee'] += 1
                continue
            (cx, cy), _r = c
            antiorario = (a[0] - cx) * (m[1] - cy) - (a[1] - cy) * (m[0] - cx) > 0
            cp = sk.point(cx, cy, construction=True)   # i centri delle curve non si vedono (lontani, sparsi)
            sk.constrain('fix', cp)                 # anche il centro: il disegno arriva «tutto definito»
            sk.arc(cp, pa, pb) if antiorario else sk.arc(cp, pb, pa)
            n['archi'] += 1
    for (cx, cy), r in geo['cerchi']:
        cp = sk.point(cx, cy)
        sk.constrain('fix', cp)
        cid = sk.circle(cp, r)
        sk.dimension('diameter', cid, value=round(2 * r, 6))
        n['cerchi'] += 1
    return n
