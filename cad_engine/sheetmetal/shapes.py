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
    # i vertici nell'ordine del giro (order_edges di build123d ci metteva un terzo di secondo)
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools_WireExplorer
    pts, ex = [], BRepTools_WireExplorer(face.outer_wire().wrapped, face.wrapped)
    while ex.More():
        q = BRep_Tool.Pnt_s(ex.CurrentVertex())
        pts.append((q.X(), q.Y()))
        ex.Next()
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


def _faccia_piana(pts):
    """Una faccia piana dai suoi punti, fatta direttamente con OpenCascade (con build123d era il collo di
    bottiglia: centinaia di facce per ogni forma)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.gp import gp_Pnt
    poli = BRepBuilderAPI_MakePolygon()
    for q in pts:
        poli.Add(gp_Pnt(q[0], q[1], q[2] if len(q) > 2 else 0.0))
    poli.Close()
    return BRepBuilderAPI_MakeFace(poli.Wire(), True).Face()


def _solido(S: Facce, t: float, piani: list | None = None):
    """Il solido costruito direttamente: le facce in asse spostate di ±t/2 (pelle esterna e interna) più le
    fasce sui bordi, cucite in un guscio chiuso. Ispessire faccia per faccia e fondere tutto (build123d) era
    lento (secondi su un raccordo) e lasciava centinaia di facce spezzate.
    piani: per ogni faccia (normale, n·x) del suo piano in asse esatto; dove si incontrano più di tre facce (gli
    angoli del cambio di pendenza di una tramoggia) ogni faccia ha il suo punto d'angolo su quel piano: senza, la
    parete veniva storta e sottile (2,84 su 3) e i fori lì vicino erano rifiutati (28/10)."""
    import numpy as np
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.BRepLib import BRepLib
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
    normali = []
    vicine = [[] for _ in P]                               # normali delle facce attorno a ogni punto
    for k, f in enumerate(S.facce):
        if piani is not None:
            n = np.array(piani[k][0], dtype=float)
            n /= np.linalg.norm(n)
        else:
            a, b, c = (P[i] for i in f[:3])
            n = np.cross(b - a, c - a)
            n /= np.linalg.norm(n)
        normali.append(n)
        for i in f:
            vicine[i].append(n)
    usi = {}                                               # lato -> [(faccia, (a, b))]
    for k, f in enumerate(S.facce):
        for a, b in zip(f, f[1:] + f[:1]):
            usi.setdefault(frozenset((a, b)), []).append((k, (a, b)))
    sul_bordo = {i for lati in usi.values() if len(lati) == 1 for i in lati[0][1]}
    # Ogni punto si sposta di v, a t/2 dai piani delle facce attorno: esatto dove le facce sono 1–3 (lo spigolo di
    # una piega a quartabuono). Sugli angoli della base del raccordo arriva tutto il ventaglio (6–10 facce): lì un
    # punto solo non può stare a t/2 da tutte (o l'angolo sporge, o le facce si assottigliano: −5% di peso). Come
    # nella lamiera vera, ogni faccia ha il suo punto d'angolo a t/2, e tra una faccia e l'altra c'è un raccordo
    # piccolo; il taglio del bordo, lì, è un ventaglio di triangoli attorno al punto in asse.
    ventaglio = {i for i, ns in enumerate(vicine) if len(ns) > 3 and (i in sul_bordo or piani is not None)}
    off = np.zeros_like(P)
    for i, ns in enumerate(vicine):
        if not ns or i in ventaglio:
            continue
        N = np.array(ns)
        if len(ns) <= 3:
            off[i] = np.linalg.lstsq(N, np.ones(len(ns)), rcond=None)[0] * (t / 2)
        else:                                              # (dentro la superficie: non succede nelle forme di oggi)
            m = N.sum(axis=0)
            m /= np.linalg.norm(m)
            off[i] = m * (t / 2) / max(0.5, float(np.mean(N @ m)))

    def base(k, i):                                        # il punto d'angolo della faccia k, sul suo piano in asse
        if piani is None or i not in ventaglio:
            return P[i]
        n = normali[k]
        return P[i] - n * (float(n @ P[i]) - piani[k][1])

    def fuori(k, i):
        return base(k, i) + normali[k] * (t / 2) if i in ventaglio else P[i] + off[i]

    def dentro(k, i):
        return base(k, i) - normali[k] * (t / 2) if i in ventaglio else P[i] - off[i]

    def poligoni(pts):
        """Un poligono, o i suoi triangoli se i punti spostati non stanno più in un piano; niente se è nullo."""
        pts = [tuple(map(float, q)) for q in pts]
        q = np.array(pts)
        if sum(np.linalg.norm(np.cross(q[j] - q[0], q[j + 1] - q[0])) for j in range(1, len(q) - 1)) < 1e-8:
            return []
        if len(pts) > 3:
            n = np.cross(q[1] - q[0], q[2] - q[0])
            n /= np.linalg.norm(n) or 1
            if max(abs(np.dot(x - q[0], n)) for x in q) > 1e-4:
                return [t3 for k in range(1, len(pts) - 1) for t3 in poligoni([pts[0], pts[k], pts[k + 1]])]
        return [pts]

    facce = []
    for k, f in enumerate(S.facce):
        facce += poligoni([fuori(k, i) for i in f])
        facce += poligoni([dentro(k, i) for i in reversed(f)])
    tappo = set()                                          # (faccia, punto) già chiusi sul bordo
    for lati in usi.values():
        if len(lati) == 1:                                 # bordo: la fascia del taglio
            k, (a, b) = lati[0]
            facce += poligoni([fuori(k, b), fuori(k, a), dentro(k, a), dentro(k, b)])
            for c in (a, b):
                if c in ventaglio and (k, c) not in tappo:
                    tappo.add((k, c))
                    facce += poligoni([P[c], dentro(k, c), fuori(k, c)])
            continue
        (k, (a, b)), (g, _) = lati[0], lati[1]
        if a not in ventaglio and b not in ventaglio:
            continue
        # tra due facce del ventaglio: il raccordo sulla pelle esterna e su quella interna
        facce += poligoni([fuori(k, a), fuori(g, a), fuori(g, b), fuori(k, b)])
        facce += poligoni([dentro(k, b), dentro(g, b), dentro(g, a), dentro(k, a)])
        for c in (a, b):                                   # e il ventaglio del taglio attorno al punto in asse
            if c in ventaglio:
                facce += poligoni([P[c], fuori(k, c), fuori(g, c)])
                facce += poligoni([P[c], dentro(g, c), dentro(k, c)])
    # angoli in mezzo alla superficie (più di tre facce, nessun bordo libero): il tappo sulle due pelli, con i punti
    # d'angolo delle facce in giro
    for c in ventaglio - sul_bordo:
        attorno = [k for k, f in enumerate(S.facce) if c in f]
        dopo = {}
        for k in attorno:
            f = S.facce[k]
            j = f.index(c)
            dopo[k] = (f[j - 1], f[(j + 1) % len(f)])          # (prima, dopo) attorno a c nella faccia k
        giro, k = [], attorno[0]
        while k not in giro:
            giro.append(k)
            nxt = dopo[k][1]
            k = next((g for g in attorno if g != k and dopo[g][0] == nxt), None)
            if k is None:
                break
        if len(giro) == len(attorno):
            facce += poligoni([fuori(k, c) for k in giro][::-1])
            facce += poligoni([dentro(k, c) for k in giro])
    cuci = BRepBuilderAPI_Sewing(1e-4)
    for pts in facce:
        cuci.Add(_faccia_piana(pts))
    cuci.Perform()
    ex = TopExp_Explorer(cuci.SewedShape(), TopAbs_SHELL)
    if not ex.More():
        raise FeatureError('Non riesco a fare il solido della forma (guscio non chiuso).')
    solido = BRepBuilderAPI_MakeSolid(TopoDS.Shell(ex.Current())).Solid()
    BRepLib.OrientClosedSolid_s(solido)                    # la pelle con la normale verso fuori
    return bd.Solid(solido)


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
    vuoto = lambda x: x is None or str(x).strip() == ''  # noqa: E731
    r_piega = None if vuoto(fdef.get('radius')) else v('radius', 'il raggio di piega')
    k_piega = None if vuoto(fdef.get('k')) else v('k', 'il K-factor')
    if r_piega is not None and r_piega < 0:
        raise FeatureError(f'Il raggio di piega non può essere negativo: {r_piega} non va.', feature=fid)
    if k_piega is not None and not 0 <= k_piega <= 1:
        raise FeatureError(f'Il K-factor deve stare tra 0 e 1 (di solito 0,3–0,5): {k_piega} non va.', feature=fid)
    for campo in ('ref', 'ref_base', 'ref_round'):
        if fdef.get(campo, 'esterno') not in RIFERIMENTI:
            raise FeatureError(f'Riferimento delle misure "{fdef.get(campo)}" sconosciuto: '
                               + ', '.join(RIFERIMENTI.values()) + '.', feature=fid)
    if fdef.get('mode', 'press') not in ('press', 'rolled'):
        raise FeatureError(f'Modo "{fdef.get("mode")}" sconosciuto: a pieghe o calandrato.', feature=fid)
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
    elif kind == 'profilo':
        # profilo disegnato (linee e archi) estruso in lamiera: gli archi a colpi (bumping)
        from .profilo import costruisci as profilo
        ss, prof = ctx.sketch(fdef)
        L = v('length', 'la lunghezza')
        if not L or L <= 0:
            raise FeatureError('Scrivi di quanto estrudere il profilo (la lunghezza).', feature=fid)
        colpi = fdef.get('hits')
        colpi = v('hits', 'i colpi per arco') if colpi not in (None, '') else None
        solido, flat, linee, righe, info = profilo(ss, prof.plane, L, t, r_piega, k_piega, colpi, passo,
                                                   bool(fdef.get('flip')), fid)
        nome = 'Profilo in lamiera'
        piano_profilo = prof.plane
    elif kind == 'sezioni':
        from .poliedro import costruisci
        valuta = lambda e, what: evaluate(e, ctx.params, what=f'{what} di {fid}')  # noqa: E731
        solido, flat, linee, righe, info, nome = costruisci(fdef, valuta, t, r_piega, k_piega, fid)
    else:
        raise FeatureError(f'Forma "{kind}" sconosciuta.', feature=fid)
    solidi = solido.solids() if hasattr(solido, 'solids') else []
    shape = solidi[0].wrapped if len(solidi) == 1 else solido.wrapped
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
    pannelli = info.pop('pannelli', None)
    verso_L = info.pop('verso_L', 1.0)
    ns = NamedShape(shape, {})
    mappe = info.pop('mappe', None)
    rif = info.pop('rif', 'esterno')
    data.shape_info = {'kind': kind, 'nome': nome, **info}
    if kind == 'profilo' and pannelli:
        ns.names, data.pannelli = _nomi_profilo(fid, shape, piano_profilo, pannelli, verso_L, t)
    if kind == 'sezioni' and mappe:
        ns.names, data.pannelli, data.sagome = _nomi_sezioni(fid, shape, mappe, t, rif)
    ns.sheet = data
    return ns


def _nomi_sezioni(fid, shape, mappe, t, rif):
    """Le facce della forma a sezioni (tramogge, cassoni): «cassone destra fuori/dentro»… Per ognuna i piani sul
    pezzo e nello sviluppo, così si disegna sulla faccia e il contorno va al suo posto nel DXF (22/10). Le facce del
    solido fuse insieme (i bordi complanari) restano senza nome: non si sa in quale pezzo dello sviluppo vanno."""
    from ..topology.naming import _faces_of
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    off_est = {'esterno': 0.0, 'interno': t, 'asse': t / 2}.get(rif, 0.0)
    facce = [bd.Face(f) for f in _faces_of(shape)]
    nomi, mappa, sagome = {}, {}, {}
    for f in facce:
        try:
            c = f.center()
            nf = f.normal_at(c)
        except Exception:  # noqa: BLE001
            continue
        trovate, sul_piano = [], []
        for m in mappe:
            n = bd.Vector(*m['normale'])
            d = nf.dot(n)
            if abs(abs(d) - 1) > 1e-6:
                continue
            lato = 'fuori' if d > 0 else 'dentro'
            off = off_est if lato == 'fuori' else off_est - t
            P0, P1 = bd.Vector(*m['pts3'][0]), bd.Vector(*m['pts3'][1])
            if abs((c - P0).dot(n) - off) > 0.25 * t:          # il solido nasce dalla superficie media: qualche centesimo
                continue
            u = (P1 - P0).normalized()
            v = n.cross(u)
            poly = [((bd.Vector(*q) - P0).dot(u), (bd.Vector(*q) - P0).dot(v)) for q in m['poly3']]
            x, y = (c - P0).dot(u), (c - P0).dot(v)
            voce = (m, lato, n, c, nf * (1 if d > 0 else -1))
            sul_piano.append(voce)
            if _dentro_poligono(x, y, poly):
                trovate.append(voce)
        if len(trovate) != 1:
            # 29/10: più facce sullo stesso piano fuse in una sola dal solido (il bordo in alto con gli angoli a 45°
            # è un anello unico): la faccia prende il nome di ognuno dei lati che stanno su di lei; il lato giusto per
            # ogni foro si sceglie dopo, da dove cade (sagome)
            trovate = []
            for voce in sul_piano:
                m, lato, n = voce[0], voce[1], voce[2]
                off = off_est if lato == 'fuori' else off_est - t
                pts = [bd.Vector(*q) - n * (off_est - off) for q in m['poly3']]
                cm = sum(pts, bd.Vector()) / len(pts)
                dd = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(cm.X, cm.Y, cm.Z)).Vertex(), f.wrapped)
                if dd.IsDone() and dd.Value() < 0.3 * t + 0.05:
                    trovate.append(voce)
            if len(trovate) < 2:
                continue
        for m, lato, n, c, nv in trovate:
            nome = f"{fid}/{m['nome'].replace(' ', '_')}/{lato}"
            nomi.setdefault(nome, []).append(f.wrapped)
            if nome in mappa:
                continue
            off = off_est if lato == 'fuori' else off_est - t
            sagome[nome] = [tuple(bd.Vector(*q) - n * (off_est - off)) for q in m['poly3']]
            _mappa_sezione(mappa, nome, m, lato, n, c, nv)
    return nomi, mappa, sagome


def _mappa_sezione(mappa, nome, m, lato, n, c, nv):
    """Piano sul pezzo e piano nello sviluppo di un lato della forma."""
    # il piano della faccia vera del solido (nasce dalla superficie media: può essere spostata o girata di
    # pochissimo rispetto alla faccia teorica). Se no il contorno arriva nello sviluppo fuori piano e non taglia
    P0, P1, P2 = (bd.Vector(*q) for q in m['pts3'])
    P0, P1, P2 = (q + nv * (c - q).dot(nv) for q in (P0, P1, P2))
    u = (P1 - P0) - nv * (P1 - P0).dot(nv)
    u = u.normalized()
    sorg = bd.Plane(origin=P0, x_dir=u, z_dir=nv)
    q0, q1, q2 = (bd.Vector(q[0], q[1], 0) for q in m['pts2'])
    ux = (q1 - q0).normalized()
    y3 = (P2 - P0).dot(nv.cross(u))
    y2 = ux.cross(q2 - q0).Z
    zf = (0, 0, 1) if (y3 > 0) == (y2 > 0) else (0, 0, -1)
    dest = bd.Plane(origin=q0, x_dir=ux, z_dir=zf)
    mappa[nome] = (sorg, dest, -n if lato == 'fuori' else n)


def _dentro_poligono(x, y, poly) -> bool:
    dentro = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i - 1], poly[i]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            dentro = not dentro
    return dentro


def _nomi_profilo(fid, shape, plane, pannelli, verso_L, t):
    """Le facce del profilo estruso: «tratto N dentro/fuori» (la linea disegnata e l'altra faccia), «testa». Per ogni
    faccia di un tratto la coppia di piani (sul pezzo, nello sviluppo) che porta un contorno disegnato lì nella sua
    posizione sullo sviluppo, e il verso dentro il materiale."""
    from ..topology.naming import _faces_of
    nomi, mappa = {}, {}
    d = plane.z_dir * verso_L
    facce = [bd.Face(f) for f in _faces_of(shape)]
    for i, pn in enumerate(pannelli, 1):
        u3 = (plane.from_local_coords(pn['b']) - plane.from_local_coords(pn['a'])).normalized()
        n3 = (plane.from_local_coords((pn['a'][0] + pn['n'][0], pn['a'][1] + pn['n'][1]))
              - plane.from_local_coords(pn['a'])).normalized()
        for lato, (p, q), dentro in (('dentro', (pn['a'], pn['b']), n3), ('fuori', (pn['a2'], pn['b2']), -n3)):
            P, Q = plane.from_local_coords(p), plane.from_local_coords(q)
            for f in facce:
                c = f.center()
                if abs(f.normal_at(c).dot(dentro)) < 1 - 1e-6 or abs((c - P).dot(dentro)) > 1e-5:
                    continue
                s = (c - P).dot(u3)
                if -1e-6 <= s <= (Q - P).dot(u3) + 1e-6:
                    nome = f'{fid}/tratto{i}/{lato}'
                    nomi.setdefault(nome, []).append(f.wrapped)
                    # sul pezzo: x lungo il tratto, y lungo l'estrusione; nello sviluppo: x lungo lo sviluppo, y uguale
                    x0 = pn['x0'] + (P - plane.from_local_coords(pn['a'])).dot(u3)
                    sorg = bd.Plane(origin=P, x_dir=u3, z_dir=u3.cross(d))
                    dest = bd.Plane(origin=(x0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
                    mappa[nome] = (sorg, dest, dentro)
                    break
    for f in facce:
        if abs(abs(f.normal_at(f.center()).dot(d)) - 1) < 1e-9:
            nomi.setdefault(f'{fid}/testa', []).append(f.wrapped)
    return nomi, mappa


def _sviluppo_facce(S: Facce, r_piega, k_piega, t):
    con_dati = r_piega is not None and k_piega is not None
    delta = (lambda a: _correzione(a, r_piega, k_piega, t)) if con_dati else None
    piani, linee = sviluppa(S, delta)
    if not con_dati:
        giro = _contorno(piani)
        flat = bd.Face(bd.Wire.make_polygon([(q[0], q[1], 0) for q in giro], close=True))
    else:
        # facce spostate della correzione: si uniscono (dove Δ > 0 si aggiunge la striscia della piega)
        pezzi = [bd.Face(_faccia_piana(poly)) for poly in piani]
        for *_, d, (A2, B2, A3, B3) in linee:
            if d > 1e-9:
                pezzi.append(bd.Face(_faccia_piana([A2, B2, B3, A3])))
        # a gruppi di 4 facce vicine, poi i gruppi: sui raccordi (tanti triangoli a ventaglio sugli angoli)
        # un'unione unica di tutto costava due secondi, così un decimo, con lo stesso risultato
        gruppi = [pezzi[i:i + 4] for i in range(0, len(pezzi), 4)]
        gruppi = [g[0].fuse(*g[1:]).clean() if len(g) > 1 else g[0] for g in gruppi]
        flat = gruppi[0].fuse(*gruppi[1:]).clean() if len(gruppi) > 1 else gruppi[0]
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
