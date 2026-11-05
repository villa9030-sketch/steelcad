"""Pezzi che si muovono nell'assieme (05/11, idee da SolidCraft: joint revolute/slider/cylindrical, joint.limits,
joint.find_limits, motion interference). Ingranaggi, cremagliere, viti, camme e gravità no (Stefano non li vuole).

Tre giunti, accoppiamenti come gli altri (un campo nuovo nel file: gli assiemi di prima si aprono uguali):
- **cerniera**: il pezzo gira attorno a un asse (un foro, un tubo o uno spigolo dritto); valore «angolo» (gradi);
- **guida**: il pezzo scorre lungo una direzione (uno spigolo, un tubo, o di fronte a una faccia); valore «corsa» (mm);
- **perno**: gira e scorre lungo l'asse; valori «angolo» e «corsa».

Il giunto ricorda dove sta il pezzo che si muove (b) rispetto a quello fermo (a) nella posizione disegnata (rel_R,
rel_T: come «blocca») e l'asse nelle coordinate del pezzo fermo. Per il risolutore un giunto è un «blocca» con in più
il movimento: giro attorno all'asse e corsa lungo l'asse. I valori salvati (m['angolo'], m['corsa']) sono la posizione
disegnata; quelli di movimento (asm.moto, solo in memoria) la sostituiscono finché non si dice «Tieni questa posizione».

Finecorsa: m['lim_angolo'], m['lim_corsa'] = [da, a] (None = libero da quella parte). «Trova da solo» e «Controlla che
non sbatta» muovono i pezzi a passi e guardano quando toccano un altro pezzo: passi lunghi quando sono lontani (la
distanza dice di quanto si può girare senza toccare), poi a metà fino a un decimo di millimetro. I pezzi che si toccano
già all'inizio (l'anta appoggiata alla battuta, il perno nel foro) fermano il movimento solo se entrano di più.
"""
from __future__ import annotations

import math
import time

import numpy as np

from .assembly import AssemblyError, _info, _R, _rot_axis, _T, placed_shape

GIUNTI = {'cerniera': ('angolo',), 'guida': ('corsa',), 'perno': ('angolo', 'corsa')}
UNITA = {'angolo': '°', 'corsa': 'mm'}
TOCCA = 0.05                   # mm: sotto questa distanza due pezzi si toccano
FINE = 0.1                     # mm: di quanto si sbaglia al massimo il punto dove toccano
VICINO = 30.0                  # mm: oltre, basta la distanza tra gli ingombri (più veloce)


def e_giunto(m: dict) -> bool:
    return m.get('type') in GIUNTI


def _mate(asm, mid: str) -> dict:
    m = next((x for x in asm.mates if x['id'] == mid), None)
    if m is None or not e_giunto(m):
        raise AssemblyError('Questo accoppiamento non si muove: scegli una cerniera, una guida o un perno.')
    return m


# ------------------------------------------------------------------------------------------- la posa
def asse_locale(m: dict, parts: dict, asm) -> tuple:
    """L'asse del giunto nelle coordinate del pezzo fermo: punto c e versore d (col verso scelto)."""
    k = m.get('asse_da') or 'a'
    inf = _info(m[k], parts, asm)
    c, d = np.array(inf['p'], dtype=float), np.array(inf['n'], dtype=float)
    if k == 'b':                                  # l'asse è sul pezzo che si muove: nella posizione disegnata
        Rr, Tr = np.array(m['rel_R'], dtype=float), np.array(m['rel_T'], dtype=float)
        c, d = Rr @ c + Tr, Rr @ d
    d = d / np.linalg.norm(d) * (-1.0 if m.get('verso', 1) < 0 else 1.0)
    return c, d


def valori(m: dict, moto: dict | None = None) -> dict:
    """I valori del giunto adesso: quelli di movimento se ci sono, se no quelli disegnati."""
    mv = (moto or {}).get(m['id']) or {}
    return {q: float(mv.get(q, m.get(q) or 0.0)) for q in GIUNTI[m['type']]}


def limiti(m: dict, q: str) -> tuple:
    lim = m.get('lim_' + q) or [None, None]
    return (None if lim[0] is None else float(lim[0]), None if lim[1] is None else float(lim[1]))


def dentro_i_limiti(m: dict, q: str, v: float) -> float:
    lo, hi = limiti(m, q)
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v


def posa_relativa(m: dict, parts: dict, asm, vals: dict) -> tuple:
    """Dove sta il pezzo che si muove rispetto a quello fermo, con questi valori: (R, T) come in «blocca»."""
    Rr, Tr = np.array(m['rel_R'], dtype=float), np.array(m['rel_T'], dtype=float)
    c, d = asse_locale(m, parts, asm)
    Q = _rot_axis(d, math.radians(vals.get('angolo', 0.0)))
    return Q @ Rr, Q @ (Tr - c) + c + vals.get('corsa', 0.0) * d


def come_blocca(m: dict, parts: dict, asm, moto: dict | None = None) -> dict:
    """Il giunto per il risolutore: un «blocca» con la posa che danno i valori di adesso."""
    R, T = posa_relativa(m, parts, asm, valori(m, moto))
    return {**m, 'type': 'blocca', 'giunto': m['type'], 'rel_R': R.tolist(), 'rel_T': T.tolist()}


def asse_mondo(m: dict, parts: dict, asm) -> tuple:
    """L'asse nel mondo, col pezzo fermo dove sta adesso."""
    ia = asm.instance(m['a']['inst'])
    c, d = asse_locale(m, parts, asm)
    RA, TA = _R(ia), _T(ia)
    return RA @ c + TA, RA @ d


def mobili(asm, mid: str) -> tuple:
    """I pezzi che il giunto muove: quello attaccato al giunto e quelli accoppiati a lui (la maniglia sull'anta), ma
    non quelli legati anche al pezzo fermo. bloccato: il pezzo che si muove è tenuto anche da altri accoppiamenti a
    pezzi fermi, e il giunto non lo può muovere."""
    m = next(x for x in asm.mates if x['id'] == mid)
    vicini: dict = {}
    for x in asm.mates:
        if x is m or x.get('off'):
            continue
        a, b = x['a']['inst'], x['b']['inst']
        vicini.setdefault(a, set()).add(b)
        vicini.setdefault(b, set()).add(a)
    giro, da_fare = {m['b']['inst']}, [m['b']['inst']]
    while da_fare:
        for v in vicini.get(da_fare.pop(), ()):
            if v not in giro:
                giro.add(v)
                da_fare.append(v)
    terra = {i['id'] for i in asm.instances if i.get('fixed')} or {asm.instances[0]['id']}
    if giro & (terra | {m['a']['inst']}):
        return [m['b']['inst']], True
    ordine = [i['id'] for i in asm.instances]
    return sorted(giro, key=ordine.index), False


# ------------------------------------------------------------------------------------------- la corsa
def _aabb_dist(a, b) -> float:
    gap = np.maximum(0.0, np.maximum(a[0] - b[1], b[0] - a[1]))
    return float(np.linalg.norm(gap))


def _bbox(shape) -> np.ndarray:
    bb = shape.bounding_box()
    return np.array([[bb.min.X, bb.min.Y, bb.min.Z], [bb.max.X, bb.max.Y, bb.max.Z]])


def _angoli(bb) -> np.ndarray:
    return np.array([[x, y, z] for x in bb[:, 0] for y in bb[:, 1] for z in bb[:, 2]])


def _solidi(shape) -> list:
    """I solidi di una forma (i tubi di un telaio uno per uno): ingombri più stretti, conti più piccoli."""
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    out, ex = [], TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out or [shape]


class Corsa:
    """Il giunto mosso a prova, su una copia delle forme: i pezzi che si muovono restano attaccati tra loro (si muovono
    come il pezzo del giunto), gli altri stanno fermi dove sono adesso. Niente cambia nell'assieme.

    Il passo: un punto a distanza r dall'asse, girando di un angolo, si sposta al più di r per l'angolo; e può toccare
    solo punti fermi alla stessa distanza dall'asse. Per ogni coppia di solidi (uno che si muove, uno fermo) r è il più
    piccolo tra i due raggi massimi: l'anta lunga un metro vicino al pilastro va a passi del pilastro, non della punta."""

    def __init__(self, asm, parts: dict, mid: str):
        import build123d as bd
        self.asm, self.parts = asm, parts
        self.m = _mate(asm, mid)
        self.vals0 = valori(self.m, getattr(asm, 'moto', None))
        ia = asm.instance(self.m['a']['inst'])
        self.RA, self.TA = _R(ia), _T(ia)
        self.c, self.d = asse_mondo(self.m, parts, asm)
        ids, self.bloccato = mobili(asm, mid)
        self.nomi = {i['id']: i.get('name') or i['id'] for i in asm.instances}
        self.RB0, self.TB0 = self._posa_b(self.vals0)
        self.mov, self.fer = [], []                  # (id istanza, solido, angoli dell'ingombro | ingombro, raggio)
        for i in asm.instances:
            part = parts.get(i['file'])
            if part is None:
                continue
            s = placed_shape(part, i['R'] if i.get('R') else np.eye(3).tolist(), i.get('T') or [0, 0, 0])
            for so in _solidi(s.wrapped):
                bb = _bbox(bd.Shape.cast(so))
                ang = _angoli(bb)
                if i['id'] in ids:
                    self.mov.append((i['id'], so, ang, self._raggio(ang)))
                else:
                    self.fer.append((i['id'], so, bb, self._raggio(ang)))
        if not self.mov:
            raise AssemblyError('Il pezzo che si muove non si legge.')
        tutti = np.vstack([x[2] for x in self.mov] + [x[2] for x in self.fer])
        self.diag = float(np.linalg.norm(tutti.max(axis=0) - tutti.min(axis=0)))
        self.rmax = max(10.0, max(x[3] for x in self.mov))
        self.base = {}                               # (k mobile, j fermo) → volume in comune all'inizio (si toccano già)
        self._cache = {}

    def _raggio(self, punti) -> float:
        v = punti - self.c
        return max(1.0, float(np.max(np.linalg.norm(v - np.outer(v @ self.d, self.d), axis=1))))

    def _per(self, q, r) -> float:
        """Di quanti mm si sposta al più un punto a raggio r per un grado (per la corsa: 1 mm per mm)."""
        return r * math.pi / 180 if q == 'angolo' else 1.0

    def _posa_b(self, vals):
        R, T = posa_relativa(self.m, self.parts, self.asm, vals)
        return self.RA @ R, self.RA @ T + self.TA

    def _delta(self, vals):
        RB, TB = self._posa_b(vals)
        DR = RB @ self.RB0.T
        return DR, TB - DR @ self.TB0

    def _vals(self, q, v):
        return {**self.vals0, q: v}

    def _mosso(self, s, DR, DT):
        from OCP.gp import gp_Trsf
        from OCP.TopLoc import TopLoc_Location
        tr = gp_Trsf()
        tr.SetValues(DR[0][0], DR[0][1], DR[0][2], DT[0], DR[1][0], DR[1][1], DR[1][2], DT[1],
                     DR[2][0], DR[2][1], DR[2][2], DT[2])
        return s.Moved(TopLoc_Location(tr))

    @staticmethod
    def _dist(x, y):
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        d = BRepExtrema_DistShapeShape(x, y)
        if not d.IsDone() or d.NbSolution() < 1:
            return None, None
        # dove si toccano lungo una linea (l'anta contro il pilastro) le soluzioni sono più d'una: il punto di mezzo
        pts = [d.PointOnShape1(k) for k in range(1, d.NbSolution() + 1)]
        return d.Value(), [sum(q.X() for q in pts) / len(pts), sum(q.Y() for q in pts) / len(pts), sum(q.Z() for q in pts) / len(pts)]

    @staticmethod
    def _comune(x, y):
        import build123d as bd

        from .assembly import _in_comune
        c, v = _in_comune(bd.Shape.cast(x), bd.Shape.cast(y))
        centro = None
        if c is not None and v > 0:
            bb = c.bounding_box()
            centro = [(bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2]
        return v, centro

    def _box(self, ang, DR, DT):
        P = ang @ DR.T + DT
        return np.array([P.min(axis=0), P.max(axis=0)])

    def partenza(self, q, v):
        """I pezzi che si toccano già con il giunto a v: si fermano solo se entrano di più."""
        DR, DT = self._delta(self._vals(q, v))
        self.base = {}
        self._cache.clear()
        for k, (_, sm, ang, _) in enumerate(self.mov):
            box = self._box(ang, DR, DT)
            for j, (_, sf, bb, _) in enumerate(self.fer):
                if _aabb_dist(box, bb) > TOCCA:
                    continue
                smm = self._mosso(sm, DR, DT)
                d, _ = self._dist(smm, sf)
                if d is not None and d <= TOCCA:
                    self.base[(k, j)] = self._comune(smm, sf)[0]

    def stato(self, q, v):
        """(di quanto si può muovere ancora senza toccare niente, almeno; chi tocca: (mobile, fermo, punto) o None)."""
        chiave = (q, round(v, 9))
        if chiave in self._cache:
            return self._cache[chiave]
        DR, DT = self._delta(self._vals(q, v))
        passo, tocca = math.inf, None
        for k, (im, sm, ang, rm) in enumerate(self.mov):
            box = self._box(ang, DR, DT)
            smm = None
            for j, (jf, sf, bb, rf) in enumerate(self.fer):
                per = self._per(q, min(rm, rf))
                ad = _aabb_dist(box, bb)
                gia = (k, j) in self.base
                if ad > (TOCCA if gia else VICINO):
                    passo = min(passo, ad / per)
                    continue
                smm = smm if smm is not None else self._mosso(sm, DR, DT)
                d, p = self._dist(smm, sf)
                if d is None:
                    continue
                if gia:
                    passo = min(passo, (d if d > TOCCA else 5.0) / per)       # si toccano: a passi corti
                    if d > TOCCA:
                        continue
                    vol, centro = self._comune(smm, sf)
                    v0 = self.base[(k, j)]
                    if vol > v0 + max(1.0, 0.02 * v0):
                        tocca = (im, jf, centro or p)
                        break
                    continue
                if d <= TOCCA:
                    tocca = (im, jf, p)
                    break
                passo = min(passo, d / per)
            if tocca:
                break
        self._cache[chiave] = (passo, tocca)
        return passo, tocca

    def cerca(self, q, da, verso, ampiezza, scadenza):
        """Muove il valore q da «da» verso + o − (verso) per al più «ampiezza»: dove tocca. Ritorna
        {'valore': ultimo valore libero, 'tocca': (mobile, fermo, punto) | None, 'libero': bool, 'tempo': bool}."""
        per = self._per(q, self.rmax)                # il punto più lontano: per il passo più piccolo e la precisione
        minimo = 0.5 / per
        massimo = 45.0 if q == 'angolo' else math.inf
        v, (lib, tocca) = da, self.stato(q, da)
        if tocca:
            return {'valore': da, 'tocca': tocca, 'libero': False, 'tempo': False}
        while True:
            fatto = abs(v - da)
            if fatto >= ampiezza - 1e-9:
                return {'valore': v, 'tocca': None, 'libero': True, 'tempo': False}
            if time.perf_counter() > scadenza:
                return {'valore': v, 'tocca': None, 'libero': False, 'tempo': True}
            passo = min(max(0.9 * lib, minimo), massimo, ampiezza - fatto)
            vn = v + verso * passo
            libn, tocca = self.stato(q, vn)
            if tocca:
                lo, hi = v, vn
                while abs(hi - lo) * per > FINE and time.perf_counter() < scadenza + 5:
                    mezzo = (lo + hi) / 2
                    _, t = self.stato(q, mezzo)
                    if t:
                        hi, tocca = mezzo, t
                    else:
                        lo = mezzo
                return {'valore': lo, 'tocca': tocca, 'libero': False, 'tempo': False}
            v, lib = vn, libn

    def ampiezza(self, q) -> float:
        return 360.0 if q == 'angolo' else max(100.0, 2 * self.diag)


def _arrotonda_dentro(v: float, verso: int) -> float:
    """Il finecorsa trovato, arrotondato a un decimo verso dentro (resta libero)."""
    return (math.floor(v * 10 + 1e-6) if verso > 0 else math.ceil(v * 10 - 1e-6)) / 10


def trova_limiti(asm, parts: dict, mid: str, budget: float = 20.0) -> dict:
    """Da dove sta adesso, gira (o scorre) da una parte e dall'altra finché i pezzi che il giunto muove toccano un altro
    pezzo. Per ogni valore: {'da', 'a' (None = non tocca niente), 'da_chi', 'a_chi' (mobile, fermo, punto, valore),
    'tempo'}; 'gia': le coppie che si toccano già."""
    c = Corsa(asm, parts, mid)
    scad = time.perf_counter() + budget
    out = {'bloccato': c.bloccato, 'valori': {}}
    for q in GIUNTI[c.m['type']]:
        v0 = c.vals0[q]
        c._cache.clear()
        c.partenza(q, v0)
        out['gia'] = sorted({(c.nomi[c.mov[a][0]], c.nomi[c.fer[b][0]]) for a, b in c.base})
        ris = {}
        quanti = len(GIUNTI[c.m['type']]) * 2
        for verso, lato in ((-1, 'da'), (1, 'a')):
            resto = max(1.0, (scad - time.perf_counter()) / max(1, quanti))
            quanti -= 1
            r = c.cerca(q, v0, verso, c.ampiezza(q), time.perf_counter() + resto)
            ris[lato] = None if r['tocca'] is None else _arrotonda_dentro(r['valore'], verso)
            if ris[lato] is not None and (ris[lato] - v0) * verso < 0:
                ris[lato] = round(v0, 6)
            ris[lato + '_chi'] = None if r['tocca'] is None else {
                'mobile': c.nomi[r['tocca'][0]], 'fermo': c.nomi[r['tocca'][1]], 'punto': r['tocca'][2], 'valore': r['valore']}
            ris[lato + '_tempo'] = r['tempo']
            ris[lato + '_fino'] = r['valore']
        out['valori'][q] = ris
    return out


def controlla(asm, parts: dict, mid: str, q: str, da: float, a: float, budget: float = 20.0) -> dict:
    """Percorre la corsa da «da» ad «a» a passi: dove tocca per primo (valore, chi, punto) o niente."""
    c = Corsa(asm, parts, mid)
    c.partenza(q, da)
    verso = 1 if a >= da else -1
    r = c.cerca(q, da, verso, abs(a - da), time.perf_counter() + budget)
    out = {'q': q, 'da': da, 'a': a, 'bloccato': c.bloccato, 'tempo': r['tempo'], 'fino': r['valore'],
           'gia': sorted({(c.nomi[c.mov[x][0]], c.nomi[c.fer[y][0]]) for x, y in c.base})}
    if r['tocca'] is not None:
        im, jf, p = r['tocca']
        out['tocca'] = {'valore': r['valore'], 'mobile': c.nomi[im], 'fermo': c.nomi[jf], 'punto': p,
                        'id_mobile': im, 'id_fermo': jf}
    return out
