"""Forme di lamiera "a geometria": cono / tronco di cono e raccordo quadro (rettangolo) → tondo.

Le misure che si scrivono sono quelle del pezzo FINITO (di solito esterne; si può scegliere interne o in asse).
Lo sviluppo si calcola in asse lamiera (a metà spessore), come si traccia a mano:

- la superficie si divide in facce piane: triangoli che partono dagli angoli della base verso il tondo
  (raccordo), trapezi tra due generatrici (cono a pieghe);
- le facce si "ribaltano" una dopo l'altra sul piano, con le lunghezze vere dei loro lati;
- ogni linea tra due facce è una piega: il suo angolo è l'angolo tra le due facce.

Il numero di pieghe lo decide il raggio: si piega a passo costante sul bordo tondo (più il raggio è piccolo,
più le pieghe sono fitte in gradi); il passo si può anche scrivere a mano. Il cono si può fare calandrato:
allora lo sviluppo è la corona circolare esatta, senza linee di piega.

Nota onesta: lo sviluppo a facce è quello in asse lamiera, senza la correzione di piega (BA − 2·setback) di ogni
singola piega: per le pieghe piccole di questi pezzi è di qualche centesimo per piega. La tabella pieghe la
riporta, così si vede quanto pesa sul totale.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import build123d as bd

from ..errors import FeatureError
from ..expressions import evaluate
from ..topology import NamedShape
from ..units import fmt_mm

RIFERIMENTI = {'esterno': 'misure esterne', 'interno': 'misure interne', 'asse': 'in asse lamiera'}


# ============================================================================ geometria comune
@dataclass
class Facce:
    """Superficie in asse lamiera fatta di facce piane in fila (un anello aperto sulla giunzione)."""
    punti: list                                  # [(x, y, z)]
    facce: list                                  # [[indici]] in ordine lungo l'anello, verso coerente
    pieghe: list = field(default_factory=list)   # [(i_faccia, j_faccia, (a, b))] spigoli in comune = pieghe


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norm(a)
    return (a[0] / n, a[1] / n, a[2] / n)


def _normale(P, f):
    """Normale di una faccia (Newell: va bene anche per i trapezi)."""
    n = [0.0, 0.0, 0.0]
    for i in range(len(f)):
        a, b = P[f[i]], P[f[(i + 1) % len(f)]]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return _unit(tuple(n))


def _in_piano(P, f):
    """Coordinate 2D dei vertici della faccia nel suo piano (senza specchiare)."""
    o = P[f[0]]
    x = _unit(_sub(P[f[1]], o))
    n = _normale(P, f)
    y = _cross(n, x)
    return [(_dot(_sub(P[i], o), x), _dot(_sub(P[i], o), y)) for i in f]


def sviluppa(S: Facce, delta=None) -> tuple[list, list]:
    """Ribalta le facce una dopo l'altra. Ritorna ([poligoni 2D per faccia], [linee di piega 2D con angolo]).
    delta(angolo) = correzione di piega: la faccia nuova si sposta di Δ perpendicolare alla piega (Δ < 0: si
    sovrappone un poco alla precedente, cioè lo sviluppo si accorcia), come succede alla lamiera piegata davvero."""
    piani = []
    pos: dict = {}                               # vertice -> posizione 2D (dell'ultima faccia che l'ha messo)
    linee = []
    for k, f in enumerate(S.facce):
        loc = _in_piano(S.punti, f)
        if k == 0:
            T = lambda q: q  # noqa: E731
        else:
            prec = S.facce[k - 1]
            comuni = [v for v in f if v in prec]
            if len(comuni) < 2:
                raise FeatureError('Facce dello sviluppo non collegate: geometria non valida.')
            # lo spigolo in comune nell'ordine di questa faccia
            ia, ib = f.index(comuni[0]), f.index(comuni[1])
            a2, b2 = loc[ia], loc[ib]
            A2, B2 = pos[comuni[0]], pos[comuni[1]]
            ang = math.atan2(B2[1] - A2[1], B2[0] - A2[0]) - math.atan2(b2[1] - a2[1], b2[0] - a2[0])
            c, s = math.cos(ang), math.sin(ang)

            n1, n2 = _normale(S.punti, prec), _normale(S.punti, f)
            angolo = math.degrees(math.acos(max(-1.0, min(1.0, _dot(n1, n2)))))
            d = delta(angolo) if delta else 0.0

            def R(q, a2=a2, A2=A2, c=c, s=s):
                dx, dy = q[0] - a2[0], q[1] - a2[1]
                return (A2[0] + c * dx - s * dy, A2[1] + s * dx + c * dy)
            # verso dentro la faccia nuova, perpendicolare alla piega
            ex_, ey_ = B2[0] - A2[0], B2[1] - A2[1]
            ln = math.hypot(ex_, ey_)
            px, py = -ey_ / ln, ex_ / ln
            cx = sum(R(q)[0] for q in loc) / len(loc) - A2[0]
            cy = sum(R(q)[1] for q in loc) / len(loc) - A2[1]
            if cx * px + cy * py < 0:
                px, py = -px, -py

            def T(q, R=R, d=d, px=px, py=py):
                x, y = R(q)
                return (x + d * px, y + d * py)
            linee.append(((A2[0] + d / 2 * px, A2[1] + d / 2 * py), (B2[0] + d / 2 * px, B2[1] + d / 2 * py),
                          angolo, (comuni[0], comuni[1]), d, (A2, B2, (A2[0] + d * px, A2[1] + d * py),
                                                          (B2[0] + d * px, B2[1] + d * py))))
        poly = [T(q) for q in loc]
        for v, q in zip(f, poly):
            pos[v] = q
        piani.append(poly)
    return piani, linee


def _contorno(piani: list) -> list:
    """Il bordo esterno dell'unione dei poligoni (spigoli usati una volta sola), come poligono chiuso."""
    chiave = lambda q: (round(q[0], 6), round(q[1], 6))  # noqa: E731
    conta: dict = {}
    for poly in piani:
        for i in range(len(poly)):
            a, b = chiave(poly[i]), chiave(poly[(i + 1) % len(poly)])
            k = frozenset((a, b))
            conta[k] = conta.get(k, 0) + 1
    bordi = [tuple(k) for k, n in conta.items() if n == 1 and len(k) == 2]
    vicini: dict = {}
    for a, b in bordi:
        vicini.setdefault(a, []).append(b)
        vicini.setdefault(b, []).append(a)
    inizio = min(vicini)
    giro, prec, cur = [inizio], None, inizio
    while True:
        nxt = [q for q in vicini[cur] if q != prec]
        if not nxt or nxt[0] == inizio:
            break
        prec, cur = cur, nxt[0]
        giro.append(cur)
        if len(giro) > len(vicini) + 2:
            raise FeatureError('Il contorno dello sviluppo non si chiude.')
    return giro


def _pulisci_contorno(face, tol=0.05):
    """Il contorno dello sviluppo senza i microsegmenti lasciati dalle sovrapposizioni delle correzioni
    (pezzetti di centesimi agli angoli): punti troppo vicini uniti, punti in linea tolti. Così il DXF passa i
    controlli di taglio."""
    pts = [e.start_point() for e in face.outer_wire().order_edges()] if hasattr(face.outer_wire(), 'order_edges')         else [v for v in face.outer_wire().vertices()]
    pts = [(q.X, q.Y) for q in pts]
    out = []
    for q in pts:
        if not out or math.dist(q, out[-1]) > tol:
            out.append(q)
    if len(out) > 2 and math.dist(out[0], out[-1]) <= tol:
        out.pop()
    cambiato = True
    while cambiato and len(out) > 3:
        cambiato = False
        for i in range(len(out)):
            a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
            area = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
            if area < tol * max(math.dist(a, c), 1e-9):      # b sta (quasi) sulla retta a–c
                out.pop(i)
                cambiato = True
                break
    return bd.Face(bd.Wire.make_polygon([(x, y, 0) for x, y in out], close=True))


def _solido(S: Facce, t: float):
    """Il solido costruito direttamente: le facce in asse spostate di ±t/2 (pelle esterna e interna) più le
    fasce sui bordi, cucite in un guscio chiuso. Ispessire faccia per faccia e fondere tutto (build123d) era
    lento (secondi su un raccordo) e lasciava centinaia di facce spezzate."""
    import numpy as np
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    # i punti doppi della giunzione (lo sviluppo apre l'anello lì) nel solido sono uno solo: niente pareti
    # appiccicate sulla giunzione
    unico, idx = {}, []
    for q in S.punti:
        idx.append(unico.setdefault(tuple(round(c, 6) for c in q), len(unico)))
    P = np.array(list(unico), dtype=float)
    S = Facce([], [[idx[i] for i in f] for f in S.facce])
    vicine = [[] for _ in P]                               # normali delle facce attorno a ogni punto
    for f in S.facce:
        a, b, c = (P[i] for i in f[:3])
        n = np.cross(b - a, c - a)
        n /= np.linalg.norm(n)
        for i in f:
            vicine[i].append(n)
    # per ogni punto lo spostamento v che sta a distanza 1 da tutti i piani vicini (minimi quadrati: esatto
    # dove i piani sono 1–3, scarto minimo dove sono di più, per esempio sugli angoli della base del raccordo)
    off = np.zeros_like(P)
    for i, ns in enumerate(vicine):
        if ns:
            N = np.array(ns)
            off[i] = np.linalg.lstsq(N, np.ones(len(ns)), rcond=None)[0] * (t / 2)
    fuori, dentro = P + off, P - off

    def poligoni(pts):
        """Un poligono, o i suoi triangoli se i punti spostati non stanno più in un piano."""
        pts = [tuple(map(float, q)) for q in pts]
        if len(pts) > 3:
            q = np.array(pts)
            n = np.cross(q[1] - q[0], q[2] - q[0])
            n /= np.linalg.norm(n) or 1
            if max(abs(np.dot(x - q[0], n)) for x in q) > 1e-4:
                return [[pts[0], pts[k], pts[k + 1]] for k in range(1, len(pts) - 1)]
        return [pts]

    facce = []
    for f in S.facce:
        facce += poligoni([fuori[i] for i in f])
        facce += poligoni([dentro[i] for i in reversed(f)])
    usi = {}
    for f in S.facce:                                      # i lati usati da una faccia sola sono il bordo
        for a, b in zip(f, f[1:] + f[:1]):
            usi.setdefault(frozenset((a, b)), []).append((a, b))
    for lati in usi.values():
        if len(lati) == 1:
            a, b = lati[0]
            facce += poligoni([fuori[b], fuori[a], dentro[a], dentro[b]])
    cuci = BRepBuilderAPI_Sewing(1e-4)
    for pts in facce:
        cuci.Add(bd.Face(bd.Wire.make_polygon(pts, close=True)).wrapped)
    cuci.Perform()
    ex = TopExp_Explorer(cuci.SewedShape(), TopAbs_SHELL)
    if not ex.More():
        raise FeatureError('Non riesco a fare il solido della forma (guscio non chiuso).')
    ms = BRepBuilderAPI_MakeSolid(TopoDS.Shell(ex.Current()))
    fix = ShapeFix_Solid(ms.Solid())
    fix.Perform()
    return bd.Solid(fix.Solid())


def _passo_auto(r: float) -> float:
    """Passo delle pieghe sul bordo tondo, in base al raggio: fitto sui raggi piccoli, largo sui grandi."""
    return max(8.0, min(40.0, r / 5))


def _correzione(angolo_gradi: float, r: float, k: float, t: float) -> float:
    """Quanto cambia la lunghezza in asse lamiera per una piega vera (raggio r, K) invece dello spigolo vivo."""
    th = math.radians(angolo_gradi)
    return th * (r + k * t) - 2 * (r + t / 2) * math.tan(th / 2)


# ============================================================================ forme
def cono_facce(Dg, Dp, H, t, rif, n):
    """Tronco di cono (Dp = 0: cono a punta) in asse lamiera, con n facce trapezie (n generatrici)."""
    rg, rp = Dg / 2, Dp / 2
    alfa = math.atan2(rg - rp, H)                      # semiapertura
    sp = (t / 2) / math.cos(alfa)                      # spostamento in pianta dell'asse lamiera
    d = {'esterno': -sp, 'interno': sp, 'asse': 0.0}[rif]
    rg, rp = rg + d, (rp + d if Dp > 0 else 0.0)
    if rg <= 0 or rp < 0:
        raise FeatureError('Con questo spessore il cono non ha misure valide.')
    P = []
    for i in range(n + 1):                             # n + 1 generatrici: la prima e l'ultima sono la giunzione
        a = 2 * math.pi * i / n
        P.append((rg * math.cos(a), rg * math.sin(a), 0.0))
        P.append((rp * math.cos(a), rp * math.sin(a), H))
    facce = []
    for i in range(n):
        b0, t0, b1, t1 = 2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 3
        facce.append([b0, b1, t1, t0] if rp > 0 else [b0, b1, t0])
    if rp == 0:                                        # punta: un solo vertice
        apice = len(P)
        P.append((0.0, 0.0, H))
        facce = [[2 * i, 2 * i + 2, apice] for i in range(n)]
    return Facce(P, facce), (rg, rp)


def raccordo_facce(A, B, D, H, t, ex, ey, rif_base, rif_tondo, n):
    """Raccordo rettangolo A × B (a z = 0) → tondo Ø D (a z = H), centro spostato di (ex, ey).
    n divisioni del tondo per ogni quarto. Giunzione a metà del lato davanti (y = −B/2)."""
    da = {'esterno': -t, 'interno': t, 'asse': 0.0}[rif_base]
    dd = {'esterno': -t, 'interno': t, 'asse': 0.0}[rif_tondo]
    a, b, r = (A + da) / 2, (B + da) / 2, (D + dd) / 2
    if a <= 0 or b <= 0 or r <= 0:
        raise FeatureError('Con questo spessore il raccordo non ha misure valide.')
    # angoli della base in giro antiorario partendo dal lato davanti (y = −b): (a,−b), (a,b), (−a,b), (−a,−b)
    angoli = [(a, -b, 0.0), (a, b, 0.0), (-a, b, 0.0), (-a, -b, 0.0)]
    # quarti del tondo: ogni angolo "vede" l'arco tra le direzioni dei due lati vicini
    # (−90° davanti, 0° destra, 90° dietro, 180° sinistra)
    P = [(0.0, -b, 0.0)]                               # 0: metà del lato davanti (giunzione)
    tondo = lambda g: (ex + r * math.cos(g), ey + r * math.sin(g), H)  # noqa: E731
    facce = []
    P.append(tondo(-math.pi / 2))                      # 1: punto del tondo sulla giunzione
    ultimo_t = 1
    prec_angolo = None
    for q in range(4):
        c = len(P)
        P.append(angoli[q])
        g0 = -math.pi / 2 + q * math.pi / 2
        if q == 0:
            facce.append([0, c, ultimo_t])             # mezzo triangolo del lato davanti
        else:
            facce.append([prec_angolo, c, ultimo_t])   # triangolo del lato tra due angoli
        for i in range(1, n + 1):                      # ventaglio dell'angolo
            P.append(tondo(g0 + math.pi / 2 * i / n))
            facce.append([c, len(P) - 1, ultimo_t])
            ultimo_t = len(P) - 1
        prec_angolo = c
    # ultimo mezzo triangolo, chiude sulla giunzione: P0bis (copia della metà davanti) per lo sviluppo aperto
    P.append((0.0, -b, 0.0))
    P.append(tondo(3 * math.pi / 2))
    facce.append([prec_angolo, len(P) - 2, ultimo_t])
    facce.append([len(P) - 2, len(P) - 1, ultimo_t])
    return _ripulisci(Facce(P, facce)), (a, b, r)


def _ripulisci(S: Facce) -> Facce:
    """Toglie facce degeneri (area nulla, per esempio il mezzo triangolo finale)."""
    buone = []
    for f in S.facce:
        if len(set(f)) < 3:
            continue
        pts = [S.punti[i] for i in f]
        ar = _norm(_cross(_sub(pts[1], pts[0]), _sub(pts[2], pts[0])))
        if ar > 1e-9:
            buone.append(f)
    return Facce(S.punti, buone)


# ============================================================================ feature
def build_shape(fdef: dict, ctx) -> NamedShape:
    from . import SheetData
    fid = fdef['id']
    kind = fdef.get('kind')
    v = lambda k, what, d=None: evaluate(fdef[k] if k in fdef else d, ctx.params, what=f'{what} di {fid}')  # noqa: E731
    t = v('thickness', 'lo spessore')
    if not 0 < t <= 20:
        raise FeatureError('Spessore non valido.', feature=fid)
    r_piega = fdef.get('radius')
    k_piega = fdef.get('k')
    passo = fdef.get('pitch')
    passo = v('pitch', 'il passo delle pieghe') if passo not in (None, '') else None
    if kind == 'cone':
        Dg, Dp, H = v('d1', 'il Ø grande'), v('d2', 'il Ø piccolo', 0), v('height', 'l’altezza')
        if Dg <= 0 or Dp < 0 or H <= 0 or Dp >= Dg:
            raise FeatureError('Il cono vuole Ø grande > Ø piccolo ≥ 0 e altezza > 0.', feature=fid)
        rif = fdef.get('ref', 'esterno')
        calandrato = fdef.get('mode') == 'rolled'
        rg = Dg / 2
        p = passo or _passo_auto(rg)
        n = max(12, math.ceil(2 * math.pi * rg / p))
        S, (rgm, rpm) = cono_facce(Dg, Dp, H, t, rif, n)
        S3 = S if Dp > 0 else cono_facce(Dg, 4 * t * Dg / max(H, 1), H, t, rif, n)[0]   # la punta vera non si ispessisce
        if calandrato:
            solido = _cono_liscio(rgm, rpm, H, t)
            flat, linee, righe, info = _sviluppo_cono_liscio(rgm, rpm, H)
        else:
            solido = _solido(S3, t)
            flat, linee, righe, info = _sviluppo_facce(S, r_piega, k_piega, t)
        nome = 'Tronco di cono' if Dp > 0 else 'Cono'
    elif kind == 'transition':
        A, B, D, H = v('a', 'il lato A'), v('b', 'il lato B'), v('d', 'il Ø del tondo'), v('height', 'l’altezza')
        ex, ey = v('ex', 'lo spostamento X', 0), v('ey', 'lo spostamento Y', 0)
        if min(A, B, D, H) <= 0:
            raise FeatureError('Lati, Ø e altezza devono essere maggiori di zero.', feature=fid)
        r = D / 2
        p = passo or _passo_auto(r)
        n = max(3, math.ceil((math.pi * r / 2) / p))
        S, _ = raccordo_facce(A, B, D, H, t, ex, ey, fdef.get('ref_base', 'esterno'), fdef.get('ref_round', 'esterno'), n)
        solido = _solido(S, t)
        flat, linee, righe, info = _sviluppo_facce(S, r_piega, k_piega, t)
        nome = 'Raccordo quadro-tondo'
    else:
        raise FeatureError(f'Forma "{kind}" sconosciuta.', feature=fid)
    shape = solido.solids()[0].wrapped if hasattr(solido, 'solids') and solido.solids() else solido.wrapped
    xs, ys = [q.X for q in flat.vertices()], [q.Y for q in flat.vertices()]
    for e in flat.edges():
        if e.geom_type == bd.GeomType.CIRCLE:
            for q in e.positions([i / 32 for i in range(33)]):
                xs.append(q.X)
                ys.append(q.Y)
    data = SheetData(fid, t, {'thickness': t, 'radius': r_piega, 'method': 'k', 'k': k_piega, 'bd90': None,
                              'missing': []}, [], flat, bd.Plane.XY, linee, (max(xs) - min(xs), max(ys) - min(ys)),
                     flat.area, info['avvisi'])
    data.bend_rows = righe
    data.shape_info = {'kind': kind, 'nome': nome, **info}
    ns = NamedShape(shape, {})
    ns.sheet = data
    return ns


def _sviluppo_facce(S: Facce, r_piega, k_piega, t):
    con_dati = r_piega is not None and k_piega is not None
    delta = (lambda a: _correzione(a, r_piega, k_piega, t)) if con_dati else None
    piani, linee = sviluppa(S, delta)
    if not con_dati:
        giro = _contorno(piani)
        flat = bd.Face(bd.Wire.make_polygon([(q[0], q[1], 0) for q in giro], close=True))
    else:
        # facce spostate della correzione: si uniscono (dove Δ > 0 si aggiunge la striscia della piega)
        pezzi = [bd.Face(bd.Wire.make_polygon([(q[0], q[1], 0) for q in poly], close=True)) for poly in piani]
        for *_, d, (A2, B2, A3, B3) in linee:
            if d > 1e-9:
                pezzi.append(bd.Face(bd.Wire.make_polygon([(*A2, 0), (*B2, 0), (*B3, 0), (*A3, 0)], close=True)))
        flat = pezzi[0].fuse(*pezzi[1:]).clean()
        facce = flat.faces() if not isinstance(flat, bd.Face) else [flat]
        if len(facce) != 1:
            raise FeatureError('Lo sviluppo con la correzione di piega non è venuto un pezzo unico.')
        flat = _pulisci_contorno(facce[0])
    righe, testi, corr_tot = [], [], 0.0
    for i, (A2, B2, ang, _, d, _q) in enumerate(linee, 1):
        lung = math.hypot(B2[0] - A2[0], B2[1] - A2[1])
        corr = d if con_dati else None
        if corr is not None:
            corr_tot += corr
        righe.append({'n': i, 'angle': ang, 'length': lung, 'correction': corr})
        testi.append((A2, B2, f'P{i} {fmt_mm(round(ang, 1))}°'))
    info = {'pieghe': len(linee), 'angolo_max': max((x['angle'] for x in righe), default=0.0),
            'correzione_totale': corr_tot, 'avvisi': []}
    if r_piega is None or k_piega is None:
        info['avvisi'].append('Raggio e K non impostati: la tabella non riporta la correzione di piega.')
    return flat, testi, righe, info


def _cono_liscio(rg, rp, H, t):
    """Cono calandrato: la generatrice in asse lamiera, spostata di ±t/2 sulla normale, fatta girare."""
    g = _unit((rp - rg, 0.0, H))
    nrm = (g[2], 0.0, -g[0])                           # normale verso fuori nel piano XZ
    h = t / 2
    pts = [(rg + nrm[0] * h, 0, nrm[2] * h), (rp + nrm[0] * h, 0, H + nrm[2] * h),
           (rp - nrm[0] * h, 0, H - nrm[2] * h), (rg - nrm[0] * h, 0, -nrm[2] * h)]
    prof = bd.Face(bd.Wire.make_polygon(pts, close=True))
    sol = bd.revolve(prof, bd.Axis.Z, 360)
    # taglio a z = 0 e z = H: le facce di testa orizzontali, come un pezzo vero
    scatola = bd.Box(4 * (rg + t), 4 * (rg + t), H, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return sol & scatola


def _sviluppo_cono_liscio(rg, rp, H):
    """Corona circolare esatta: raggi = distanze dall'apice lungo la generatrice, angolo = 2π·rg / Lg."""
    s = math.hypot(H, rg - rp)
    if abs(rg - rp) < 1e-9:
        raise FeatureError('Ø uguali: è un cilindro, non un cono.')
    Lg = rg * s / (rg - rp)
    Lp = Lg - s
    phi = 2 * math.pi * rg / Lg
    if phi >= 2 * math.pi - 1e-6:
        raise FeatureError('Cono troppo piatto: lo sviluppo supera il giro intero.')
    c = (0.0, 0.0, 0.0)
    a0, a1 = -phi / 2, phi / 2
    P = lambda R, a: (R * math.cos(a), R * math.sin(a), 0.0)  # noqa: E731
    bordo = [bd.Edge.make_three_point_arc(P(Lg, a0), P(Lg, 0.0), P(Lg, a1))]
    if Lp > 1e-9:
        bordo += [bd.Edge.make_line(P(Lg, a1), P(Lp, a1)),
                  bd.Edge.make_three_point_arc(P(Lp, a1), P(Lp, 0.0), P(Lp, a0)),
                  bd.Edge.make_line(P(Lp, a0), P(Lg, a0))]
    else:
        bordo += [bd.Edge.make_line(P(Lg, a1), c), bd.Edge.make_line(c, P(Lg, a0))]
    flat = bd.Face(bd.Wire(bordo))
    info = {'pieghe': 0, 'angolo_max': 0.0, 'correzione_totale': 0.0, 'avvisi': [],
            'raggio_grande': Lg, 'raggio_piccolo': Lp, 'angolo_settore': math.degrees(phi)}
    return flat, [], [], info
