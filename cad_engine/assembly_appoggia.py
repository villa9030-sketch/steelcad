"""«Appoggia» (03/11, Stefano: appoggiare e centrare in un comando solo).

Clic su una faccia del pezzo da muovere, poi su quella del pezzo fermo: il pezzo si appoggia SENZA capovolgersi né
entrare nell'altro e parte al centro della faccia. Qui solo i conti: dove va il pezzo e con quali facce fare gli
accoppiamenti veri (faccia su faccia per l'appoggio, in mezzo o distanza per la posizione sulla faccia), così se un
pezzo cambia l'assieme lo rimette a posto da solo col risolutore di sempre.

La regola contro il capovolgimento: se la faccia cliccata del pezzo da muovere guarda dalla stessa parte di quella
del pezzo fermo (si clicca quella che si vede, sopra), il pezzo NON si gira: appoggia con la sua faccia più in fondo
dalla parte opposta (la faccia sotto). Se invece la faccia cliccata guarda già verso l'altro pezzo (si è girata la
vista e cliccata quella sotto), appoggia quella. In ogni caso la faccia d'appoggio è quella più esterna del pezzo da
quella parte: il pezzo resta fuori dall'altro.
"""
from __future__ import annotations

import math

import numpy as np

from . import assembly as A

TOL = 0.02                           # mm: una faccia «sta sull'estremo» del pezzo
PARALLELA = 0.9999

# i nomi dei lati come li dice l'officina, per la direzione del mondo verso cui stanno
_LATI = (((-1, 0, 0), 'sinistra'), ((1, 0, 0), 'destra'), ((0, -1, 0), 'davanti'), ((0, 1, 0), 'dietro'),
         ((0, 0, -1), 'sotto'), ((0, 0, 1), 'sopra'))


def nome_lato(v) -> str:
    v = np.asarray(v, dtype=float)
    return max(_LATI, key=lambda x: float(np.dot(v, x[0])))[1]


class _Pezzo:
    """Le facce di un pezzo con i punti della maglia (per gli estremi), nelle coordinate del pezzo."""

    def __init__(self, part):
        from .topology.naming import _faces_of
        self.part = part
        self.facce = list(_faces_of(part.shape))
        m = A.part_mesh(part)
        P = np.array(m['positions'], dtype=float).reshape(-1, 3)
        idx = np.array(m['indices'], dtype=int)
        self.punti = P
        self.per_faccia = {}
        for f in m['faces']:
            sel = idx[f['start']:f['start'] + f['count']]
            self.per_faccia[f['index']] = P[np.unique(sel)] if len(sel) else np.zeros((0, 3))
        self._info = {}

    def info(self, k):
        if k not in self._info:
            self._info[k] = A.face_info(self.part, self.facce[k])
        return self._info[k]

    def piane(self):
        for k in range(len(self.facce)):
            i = self.info(k)
            if i['kind'] == 'piana':
                yield k, i

    def vicine(self, k) -> list:
        """Le facce che toccano la faccia k lungo un suo spigolo."""
        from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as MappaListe
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        from OCP.TopExp import TopExp, TopExp_Explorer
        if getattr(self, '_anc', None) is None:
            self._anc = MappaListe()
            TopExp.MapShapesAndAncestors_s(self.part.shape, TopAbs_EDGE, TopAbs_FACE, self._anc)
        out = set()
        ex = TopExp_Explorer(self.facce[k], TopAbs_EDGE)
        while ex.More():
            i = self._anc.FindIndex(ex.Current())
            if i:
                for g in self._anc.FindFromIndex(i):
                    for j, f in enumerate(self.facce):
                        if j != k and f.IsSame(g):
                            out.add(j)
            ex.Next()
        return sorted(out)

    def estremi(self, d, punti=None):
        q = (self.punti if punti is None else punti) @ d
        return float(q.min()), float(q.max())

    def faccia_estrema(self, d, verso, vicino=None):
        """La faccia piana più esterna del pezzo lungo d: verso=-1 quella in fondo (normale -d), +1 in cima (normale
        +d). Se ce n'è più d'una a quel livello, quella più vicina al punto «vicino»."""
        lo, hi = self.estremi(d)
        livello = lo if verso < 0 else hi
        cand = []
        for k, i in self.piane():
            n = np.array(i['n'])
            if np.dot(n, d) * verso < PARALLELA:
                continue
            pts = self.per_faccia.get(k)
            if pts is None or not len(pts) or abs(float((pts @ d).mean()) - livello) > TOL:
                continue
            c = pts.mean(axis=0)
            cand.append((0 if vicino is None else float(np.linalg.norm(A._perp(c - vicino, d))), -len(pts), k))
        return min(cand)[2] if cand else None


_CACHE: dict = {}


def _pezzo(part) -> _Pezzo:
    """Lo stesso pezzo tra un'anteprima e l'altra (ogni scelta nel pannello rifà i conti): le facce si leggono una volta."""
    c = _CACHE.get(id(part))
    if c is None or c.part is not part:
        if len(_CACHE) > 64:
            _CACHE.clear()
        c = _CACHE[id(part)] = _Pezzo(part)
    return c


def _assi_della_faccia(pa: _Pezzo, ka: int, n_loc):
    """Le due direzioni sulla faccia del pezzo fermo (nelle sue coordinate): dai lati che la bordano, se no dagli
    assi del pezzo."""
    cand = []
    for j in pa.vicine(ka):
        i = pa.info(j)
        if i['kind'] == 'piana' and abs(np.dot(i['n'], n_loc)) < 1e-6:
            cand.append(np.array(i['n'], dtype=float))
    for e in np.eye(3):
        cand.append(e)
    for c in cand:
        u = A._perp(c, n_loc)
        if np.linalg.norm(u) > 0.5:
            u = u / np.linalg.norm(u)
            return u, np.cross(n_loc, u)
    raise A.AssemblyError('Non trovo le direzioni di questa faccia.')


def _bordi(pa: _Pezzo, ka: int, u):
    """I due lati della faccia del pezzo fermo lungo u (le facce piane che la bordano, a squadra): (basso, alto)
    come indici di faccia, o None se da quella parte non c'è una faccia piana."""
    pts = pa.per_faccia[ka]
    lo, hi = pa.estremi(u, pts)
    basso = alto = None
    for j in pa.vicine(ka):
        i = pa.info(j)
        if i['kind'] != 'piana' or abs(abs(float(np.dot(i['n'], u))) - 1) > 1e-4:
            continue
        q = float(np.dot(i['p'], u))
        if abs(q - lo) < TOL:
            basso = j
        elif abs(q - hi) < TOL:
            alto = j
    return lo, hi, basso, alto


def appoggia(part_a, Ra, Ta, ka: int, part_b, Rb, Tb, kb: int, opz: dict | None = None) -> dict:
    """Dove va il pezzo b (R, T) appoggiato sulla faccia ka del pezzo a, e le facce per gli accoppiamenti.

    opz: capovolgi (bool), gira (quanti quarti di giro attorno alla normale), e per le due direzioni della faccia
    'u' e 'v': {'modo': 'centro' | 'basso' | 'alto', 'mm': distanza dal bordo}. Ritorna R, T, la faccia d'appoggio
    (kb2), le direzioni con i nomi dei lati e, per ogni direzione, le facce da accoppiare (o None)."""
    opz = opz or {}
    Ra, Ta, Rb, Tb = (np.array(x, dtype=float) for x in (Ra, Ta, Rb, Tb))
    pa, pb = _pezzo(part_a), _pezzo(part_b)
    fa, fb = pa.info(ka), pb.info(kb)
    if fa['kind'] != 'piana' or fb['kind'] != 'piana':
        raise A.AssemblyError('Appoggia vuole due facce piane: una del pezzo da mettere, una di quello fermo. '
                              'Per un tubo su una faccia usa «Tangente».')
    na_loc = np.array(fa['n'], dtype=float)
    nA = Ra @ na_loc
    pA = Ra @ np.array(fa['p'], dtype=float) + Ta
    nb_loc = np.array(fb['n'], dtype=float)
    # il «su» del pezzo da muovere (nelle sue coordinate): la faccia cliccata se guarda come quella ferma
    su = nb_loc if float(np.dot(Rb @ nb_loc, nA)) > 0.01 else -nb_loc
    if opz.get('capovolgi'):
        su = -su
    centro_b = pb.per_faccia[kb].mean(axis=0) if len(pb.per_faccia.get(kb, [])) else np.array(fb['p'])
    kb2 = pb.faccia_estrema(su, -1, centro_b)
    if kb2 is None:
        raise A.AssemblyError('Da quella parte il pezzo non ha una faccia piana su cui appoggiare: prova «Capovolgi», '
                              'o per un tubo usa «Tangente».')
    # rotazione: il «su» del pezzo va sulla normale della faccia ferma, girando il meno possibile
    R1 = A._rot_min(Rb @ su, nA) @ Rb
    # le direzioni della faccia ferma (nel mondo), in ordine come le pensa l'officina: prima sinistra/destra
    u_loc, v_loc = _assi_della_faccia(pa, ka, na_loc)
    U, V = Ra @ u_loc, Ra @ v_loc
    if abs(U[0]) < abs(V[0]) or (abs(abs(U[0]) - abs(V[0])) < 1e-6 and abs(U[1]) < abs(V[1])):
        U, V, u_loc, v_loc = V, U, v_loc, u_loc
    if U[np.argmax(np.abs(U))] < 0:
        U, u_loc = -U, -u_loc
    if V[np.argmax(np.abs(V))] < 0:
        V, v_loc = -V, -v_loc
    # il giro attorno alla normale: a squadra con i lati della faccia ferma (il quarto di giro più vicino), più quelli
    # chiesti con «Gira di 90°»
    dirs_b = []
    for k, i in pb.piane():
        w = np.array(i['n'], dtype=float)
        if abs(np.dot(w, su)) < 1e-6:
            dirs_b.append(w)
    if not dirs_b:
        dirs_b = [A._perp(e, su) for e in np.eye(3) if np.linalg.norm(A._perp(e, su)) > 0.5]
    w0 = R1 @ dirs_b[0]
    w0 = w0 / np.linalg.norm(w0)
    ang = math.atan2(float(np.dot(np.cross(w0, U), nA)), float(np.dot(w0, U)))
    ang = ang - round(ang / (math.pi / 2)) * (math.pi / 2) + (math.pi / 2) * int(opz.get('gira') or 0)   # il resto: a squadra girando poco
    R = A._rot_axis(nA, ang) @ R1
    # dove sta il pezzo, ruotato, prima di spostarlo: estremi lungo U, V e la faccia d'appoggio lungo nA
    Pb = pb.punti @ R.T
    pc = R @ np.array(pb.info(kb2)['p'], dtype=float)
    T = np.zeros(3) + nA * float(np.dot(nA, pA) - np.dot(nA, pc))
    dirs = {}
    for chiave, Dw, Dloc in (('u', U, u_loc), ('v', V, v_loc)):
        lo_a, hi_a, basso, alto = _bordi(pa, ka, Dloc)
        lo_a += float(np.dot(Dw, Ta))
        hi_a += float(np.dot(Dw, Ta))
        q = Pb @ Dw
        lo_b, hi_b = float(q.min()), float(q.max())
        scelta = (opz.get(chiave) or {})
        modo = scelta.get('modo') or 'centro'
        try:
            mm = float(str(scelta.get('mm') if scelta.get('mm') not in (None, '') else 0).replace(',', '.'))
        except ValueError:
            raise A.AssemblyError('Scrivi la distanza dal bordo in mm (un numero).') from None
        if modo == 'basso':
            sp = lo_a + mm - lo_b
        elif modo == 'alto':
            sp = hi_a - mm - hi_b
        else:
            modo = 'centro'
            sp = (lo_a + hi_a) / 2 - (lo_b + hi_b) / 2
        T = T + Dw * sp
        # le facce del pezzo che si muove agli estremi lungo questa direzione (nelle sue coordinate)
        d_loc = R.T @ Dw
        fb_basso = pb.faccia_estrema(d_loc, -1)
        fb_alto = pb.faccia_estrema(d_loc, +1)
        dirs[chiave] = {'modo': modo, 'mm': mm, 'dir': Dw.tolist(), 'basso': nome_lato(-Dw), 'alto': nome_lato(Dw),
                        'lungo_a': hi_a - lo_a, 'lungo_b': hi_b - lo_b,
                        'fermo': (basso, alto), 'mobile': (fb_basso, fb_alto),
                        # distanze dai due bordi, a pezzo messo (per il pannello)
                        'da_basso': lo_b + sp - lo_a, 'da_alto': hi_a - (hi_b + sp)}
    return {'R': R, 'T': T, 'kb2': kb2, 'su': su.tolist(), 'dirs': dirs}
