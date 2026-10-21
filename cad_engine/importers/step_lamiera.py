"""STEP di una lamiera piegata → sviluppo.

Il pezzo arriva dal cliente come solido. Si riconosce la lamiera e la si spiega:
1. spessore: la distanza tra la faccia piana più grande e quella parallela dietro;
2. un lato della lamiera (lato A): dalla faccia più grande si passa alle pieghe (facce cilindriche tangenti, con
   l'asse lungo lo spigolo) e da queste ai tratti piani dopo; le facce dello spessore e i fori non si attraversano;
3. ogni piega si apre attorno al suo spigolo: il tratto dopo finisce nel piano di quello prima, spostato della
   lunghezza della piega sulla fibra neutra (angolo × (R interno + K × spessore));
4. lo sviluppo è l'unione dei tratti piani portati in piano (con i loro fori) e delle strisce delle pieghe.
Le pieghe una dopo l'altra senza tratto piano in mezzo (bumping fitto) e le forme non a pieghe dritte (coni,
imbutiture) si dicono, non si inventano.
"""
from __future__ import annotations

import math
from collections import deque
from pathlib import Path

import build123d as bd
import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Line, GeomAbs_Plane
from OCP.gp import gp_Trsf

from ..errors import SteelCADError

TOL = 1e-4


class StepError(SteelCADError):
    code = 'step'


def leggi(path) -> bd.Shape:
    try:
        s = bd.import_step(str(path))
    except Exception as ex:  # noqa: BLE001
        raise StepError(f'Lo STEP non si legge: {ex}') from None
    solidi = s.solids() if hasattr(s, 'solids') else []
    if not solidi:
        raise StepError('Nello STEP non c’è un solido.')
    if len(solidi) > 1:
        solidi = sorted(solidi, key=lambda x: -x.volume)
        if solidi[1].volume > 0.02 * solidi[0].volume:
            raise StepError(f'Nello STEP ci sono {len(solidi)} solidi: è un assieme. Per lo sviluppo serve un pezzo solo.')
    return solidi[0]


def _v(p) -> np.ndarray:
    return np.array([p.X, p.Y, p.Z], dtype=float)


def _piano(f: bd.Face):
    c = f.center()
    return _v(c), _v(f.normal_at(c))


def _frame(O, u, w, n) -> np.ndarray:
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = u, w, n, O
    return M


def _trsf(M: np.ndarray) -> bd.Location:
    t = gp_Trsf()
    t.SetValues(*[float(M[i, j]) for i in range(3) for j in range(4)])
    return bd.Location(t)


def _app(M, p) -> np.ndarray:
    return (M @ np.append(p, 1.0))[:3]


def spiega(solido: bd.Shape, k: float = 0.33, raggio_min: float = 0.0) -> dict:
    """Lo sviluppo del solido: {'t', 'flat' (Face nel piano XY), 'pieghe' [...], 'facce' {nome: (Face 3D, M 4x4)},
    'avvisi'}."""
    facce = list(solido.faces())
    tipi = []
    for f in facce:
        ad = BRepAdaptor_Surface(f.wrapped)
        tipi.append(ad.GetType())
    piane = [i for i, t in enumerate(tipi) if t == GeomAbs_Plane]
    if not piane:
        raise StepError('Nel pezzo non ci sono facce piane: non sembra una lamiera.')
    F0 = max(piane, key=lambda i: facce[i].area)
    c0, n0 = _piano(facce[F0])
    # spessore: la faccia piana parallela opposta più vicina dietro la più grande
    t = None
    for i in piane:
        c, n = _piano(facce[i])
        if np.dot(n, n0) < -1 + 1e-6:
            d = float(np.dot(c0 - c, n0))
            if d > TOL and (t is None or d < t):
                t = d
    if t is None or t > 50:
        raise StepError('Non trovo lo spessore (due facce piane parallele una dietro l’altra): non sembra una lamiera.')
    # chi confina con chi (lungo quale spigolo)
    per_spigolo: dict = {}                          # spigolo → facce che lo hanno
    for i, f in enumerate(facce):
        for e in f.edges():
            lst = per_spigolo.setdefault(hash(e), [])
            for x in lst:
                if x[1].wrapped.IsSame(e.wrapped):
                    x[2].append(i)
                    break
            else:
                lst.append((None, e, [i]))
    vicini: dict = {}
    for lst in per_spigolo.values():
        for _n, e, fs in lst:
            for a in fs:
                for b in fs:
                    if a != b:
                        vicini.setdefault(a, []).append((b, e.wrapped))

    def retta(e):
        c = BRepAdaptor_Curve(e)
        if c.GetType() != GeomAbs_Line:
            return None
        p0 = _v(bd.Vector(c.Value(c.FirstParameter())))
        p1 = _v(bd.Vector(c.Value(c.LastParameter())))
        if np.linalg.norm(p1 - p0) < TOL:
            return None
        return p0, p1

    def cilindro(i):
        cy = BRepAdaptor_Surface(facce[i].wrapped).Cylinder()
        ax = cy.Axis()
        return (np.array([ax.Location().X(), ax.Location().Y(), ax.Location().Z()]),
                np.array([ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()]), cy.Radius())

    def tangente(i_piano, i_cil, e):
        """Il piano è tangente alla piega lungo lo spigolo e (spigolo dritto parallelo all'asse, asse a distanza R)."""
        r = retta(e)
        if r is None:
            return False
        o, a, R = cilindro(i_cil)
        u = (r[1] - r[0]) / np.linalg.norm(r[1] - r[0])
        if abs(abs(np.dot(u, a)) - 1) > 1e-6:
            return False
        c, n = _piano(facce[i_piano])
        return abs(abs(np.dot(o - c, n)) - R) < 1e-3

    # visita: tratti piani e pieghe del lato A, ognuno con la sua trasformazione verso il piano
    M0 = np.linalg.inv(_frame(c0, *_assi(facce[F0], n0), n0))
    pos = {F0: M0}
    pieghe, avvisi = [], []
    coda = deque([F0])
    visti_cil = set()
    while coda:
        P = coda.popleft()
        cP, nP = _piano(facce[P])
        for Q, e in vicini.get(P, []):
            if tipi[Q] == GeomAbs_Plane and Q not in pos:
                cQ, nQ = _piano(facce[Q])
                if np.dot(nQ, nP) > 1 - 1e-9 and abs(np.dot(cQ - cP, nP)) < 1e-4:     # la stessa faccia spezzata
                    pos[Q] = pos[P]
                    coda.append(Q)
                continue
            if tipi[Q] != GeomAbs_Cylinder or Q in visti_cil or not tangente(P, Q, e):
                continue
            o, a, R = cilindro(Q)
            # l'altro bordo dritto della piega: il tratto dopo
            figlio = None
            for C, e2 in vicini.get(Q, []):
                if C == P or e2.IsSame(e):
                    continue
                if tipi[C] == GeomAbs_Plane and tangente(C, Q, e2):
                    figlio = (C, e2)
                    break
                if tipi[C] == GeomAbs_Cylinder and retta(e2) is not None:
                    avvisi.append('Due pieghe una dopo l’altra senza tratto piano (bumping fitto): non le spiego, '
                                  'controlla lo sviluppo.')
            if figlio is None:
                continue
            C, e2 = figlio
            visti_cil.add(Q)
            if C in pos:
                continue                                   # già messo da un'altra strada (un giro chiuso)
            cC, nC = _piano(facce[C])
            r1, r2 = retta(e), retta(e2)
            u = (r1[1] - r1[0]) / np.linalg.norm(r1[1] - r1[0])
            O1 = r1[0]
            O2 = r2[0] + u * np.dot(O1 - r2[0], u)
            # verso dal tratto di prima dentro la piega (nel suo piano), e dalla piega dentro il tratto dopo
            cq = _v(facce[Q].center())
            w1 = cq - O1
            w1 = w1 - u * np.dot(w1, u) - nP * np.dot(w1, nP)
            w1 /= np.linalg.norm(w1)
            w2 = cC - O2
            w2 = w2 - u * np.dot(w2, u) - nC * np.dot(w2, nC)
            w2 /= np.linalg.norm(w2)
            phi = math.acos(max(-1.0, min(1.0, float(np.dot(nP, nC)))))
            # il lato A è dentro la piega (concavo) se la sua normale guarda verso l'asse
            pq = _v(facce[Q].center())
            radiale = pq - o - a * np.dot(pq - o, a)
            n_q = _v(facce[Q].normal_at(facce[Q].center()))
            dentro = np.dot(n_q, radiale) < 0
            r_in = R if dentro else R - t
            if r_in < raggio_min - 1e-6:
                r_in = max(r_in, 0.0)
            BA = phi * (r_in + k * t)
            # il tratto dopo: E2 va dove E1 + w1 × BA, nel piano del tratto di prima, con la stessa normale
            dst = _frame(O1 + w1 * BA, u, w1, nP)
            src = _frame(O2, u, w2, nC)
            # attenzione al verso: le due terne devono essere destre allo stesso modo
            if np.linalg.det(src[:3, :3]) * np.linalg.det(dst[:3, :3]) < 0:
                src = _frame(O2, -u, w2, nC)
                dst = _frame(O1 + w1 * BA, -u, w1, nP)
            pos[C] = pos[P] @ dst @ np.linalg.inv(src)
            pieghe.append({'P': P, 'Q': Q, 'C': C, 'e1': r1, 'e2': r2, 'angolo': math.degrees(phi), 'r': r_in,
                           'BA': BA, 'su': bool(dentro), 'MP': pos[P], 'MC': pos[C]})
            coda.append(C)
    # lo sviluppo: tratti piani in piano + strisce delle pieghe
    pezzi = []
    for i, M in pos.items():
        pezzi.append(facce[i].moved(_trsf(M)))
    linee = []
    for b in pieghe:
        a1, b1 = _app(b['MP'], b['e1'][0]), _app(b['MP'], b['e1'][1])
        a2, b2 = _app(b['MC'], b['e2'][0]), _app(b['MC'], b['e2'][1])
        u = b1 - a1
        if np.dot(b2 - a2, u) < 0:
            a2, b2 = b2, a2
        try:
            pezzi.append(bd.Face(bd.Wire.make_polygon([tuple(a1), tuple(b1), tuple(b2), tuple(a2)], close=True)))
        except Exception:  # noqa: BLE001
            pass
        linee.append(((a1 + a2) / 2, (b1 + b2) / 2, b))
    # unione robusta: ogni pezzo diventa una lastrina alta 1 (verso +Z qualunque sia il verso della faccia), si
    # fondono i solidi e si prende la faccia di sotto (a z = 0)
    lastre = [bd.extrude(f, amount=1, dir=(0, 0, 1)) for f in pezzi]
    tutto = lastre[0].fuse(*lastre[1:]).clean() if len(lastre) > 1 else lastre[0]
    fs = [f for f in tutto.faces() if abs(f.center().Z) < 1e-6 and abs(abs(f.normal_at(f.center()).Z) - 1) < 1e-9]
    if len(fs) != 1:
        avvisi.append(f'Lo sviluppo è venuto in {len(fs)} pezzi: qualche parte non è collegata da una piega dritta.')
        fs = sorted(fs, key=lambda f: -f.area)
    # controllo: l'area dello sviluppo è quella della lamiera (volume / spessore), a meno dell'effetto del K
    atteso = solido.volume / t
    scarto = (fs[0].area - atteso) / atteso
    if abs(scarto) > 0.03:
        raise StepError(f'Lo sviluppo non torna con il pezzo (area {fs[0].area / 1e4:.1f} dm² invece di {atteso / 1e4:.1f}, '
                        f'{scarto * 100:+.0f}%): non sembra una lamiera piegata con pieghe dritte (angolare o profilo, '
                        'spigoli vivi, forme speciali). Non lo spiego per non darti uno sviluppo sbagliato.')
    return {'t': t, 'flat': fs[0], 'pieghe': pieghe, 'linee': linee, 'pos': pos, 'facce': facce, 'avvisi': avvisi}


def build(fdef: dict, ctx):
    """La lavorazione «step_lamiera»: il pezzo dallo STEP (salvato dentro il progetto) e il suo sviluppo, come una
    lamiera di SteelCAD (DXF, tabella pieghe, tavole, fori e marcature sui tratti piani)."""
    import base64
    import tempfile
    import zlib

    from ..errors import FeatureError
    from ..sheetmetal import SheetData, flat_size
    from ..topology import NamedShape
    fid = fdef['id']
    if ctx.body is not None:
        raise FeatureError('Il pezzo da STEP va da solo, come prima lavorazione.', feature=fid)
    try:
        dati = zlib.decompress(base64.b64decode(fdef['dati']))
    except Exception:  # noqa: BLE001
        raise FeatureError('I dati dello STEP nel progetto sono rovinati.', feature=fid) from None
    k = ctx.value(fdef, 'k', 'il K-factor') if fdef.get('k') not in (None, '') else 0.33
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'pezzo.step'
        p.write_bytes(dati)
        try:
            solido = leggi(p)
            r = spiega(solido, k=k)
        except StepError as ex:
            raise FeatureError(ex.message, feature=fid) from None
    t = r['t']
    names, pannelli = {}, {}
    for j, (i, M) in enumerate(sorted(r['pos'].items()), 1):
        f = r['facce'][i]
        c, n = _piano(f)
        u, _w = _assi(f, n)
        nome = f'{fid}/tratto{j}'
        names[nome] = [f.wrapped]
        Rm = M[:3, :3]
        src = bd.Plane(origin=tuple(c), x_dir=tuple(u), z_dir=tuple(n))
        dst = bd.Plane(origin=tuple(_app(M, c)), x_dir=tuple(Rm @ u), z_dir=tuple(Rm @ n))
        pannelli[nome] = (src, dst, bd.Vector(*(-n)))
    righe, linee = [], []
    raggi = []
    for j, (a, b, pg) in enumerate(r['linee'], 1):
        verso = 'su' if pg['su'] else 'giù'
        testo = f'P{j} {verso.upper()} {pg["angolo"]:.0f}° R{pg["r"]:g}'.replace('.', ',')
        linee.append(((a[0], a[1]), (b[0], b[1]), testo))
        raggi.append(pg['r'])
        righe.append({'n': j, 'angle': pg['angolo'], 'length': float(np.linalg.norm(b - a)), 'correction': None,
                      'position': None, 'direction': 'up' if pg['su'] else 'down', 'verso': verso})
    flat = r['flat']
    rr = max(set(raggi), key=raggi.count) if raggi else None
    data = SheetData(fid, t, {'thickness': t, 'radius': rr, 'method': 'k', 'k': k, 'bd90': None, 'missing': []}, [],
                     flat, bd.Plane.XY, linee, flat_size(flat, bd.Plane.XY), flat.area, list(r['avvisi']))
    data.bend_rows = righe
    data.shape_info = {'kind': 'step', 'nome': 'Lamiera da STEP', 'pieghe': len(righe), 'avvisi': list(r['avvisi'])}
    data.pannelli = pannelli
    ns = NamedShape(solido.wrapped, names)
    ns.sheet = data
    return ns


def _assi(f: bd.Face, n):
    """Due direzioni nel piano della faccia: lungo il suo spigolo dritto più lungo (lo sviluppo esce dritto)."""
    best = None
    for e in f.edges():
        if e.geom_type == bd.GeomType.LINE and (best is None or e.length > best.length):
            best = e
    if best is not None:
        u = _v(best.position_at(1)) - _v(best.position_at(0))
    else:
        u = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    u = u - n * np.dot(u, n)
    u /= np.linalg.norm(u)
    return u, np.cross(n, u)


def _spessore(f: bd.Face, t) -> bool:
    """Una faccia di bordo (striscia larga quanto lo spessore)."""
    bb = f.bounding_box()
    dims = sorted([bb.size.X, bb.size.Y, bb.size.Z])
    return dims[1] < t * 1.05 + 1e-6 or f.area < 1e-9

