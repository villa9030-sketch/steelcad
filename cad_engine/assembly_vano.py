"""«Metti nel vano» (04/11, Stefano: «accoppiare quel pannello dentro il telaio è difficile, deve essere facile»).

Clic sul pannello, poi sul telaio: Radius trova da solo i vani del telaio (i buchi chiusi da tutte le parti, guardando
il telaio dritto davanti), sceglie quello dove il pannello ci sta, lo mette in piedi, lo gira nel verso in cui entra
e lo centra con lo stesso gioco tutto intorno; in profondità a filo davanti, in mezzo o a filo dietro. Qui solo i
conti: dove va il pannello e con quali facce fare gli accoppiamenti veri (in mezzo sui due lati del vano, distanza
o in mezzo in profondità), così se il telaio cambia il pannello resta centrato col risolutore di sempre.

Come trova i vani: il telaio visto lungo il suo spessore (la direzione più corta) diventa una mappa a quadretti
(pieno dove c'è materiale a qualunque profondità); i vuoti chiusi che non toccano il fuori sono i vani. Poi le misure
vere col «metro»: raggi dal centro del vano verso i quattro lati, a più profondità e su più righe (vince il più
corto: un fazzoletto in un angolo o un profilo più grosso dietro stringono il vano davvero).
"""
from __future__ import annotations

import math

import numpy as np

from . import assembly as A
from .assembly_appoggia import DENTRO, _pezzo, entra, nome_lato

PIATTO = 0.5                 # il telaio è «piatto» se lo spessore è meno di metà del lato più corto
AREA_MIN = 50.0 * 50.0       # mm²: sotto questo è un foro, non un vano
_CACHE: dict = {}


class VanoError(A.AssemblyError):
    pass


# ------------------------------------------------------------------ il telaio: assi, triangoli, vani
def _triangoli(part):
    m = A.part_mesh(part)
    P = np.array(m['positions'], dtype=float).reshape(-1, 3)
    idx = np.array(m['indices'], dtype=int).reshape(-1, 3)
    faccia = np.full(len(idx), -1, dtype=int)
    for f in m['faces']:
        faccia[f['start'] // 3:(f['start'] + f['count']) // 3] = f['index']
    return P, idx, faccia


def _assi(P, R):
    """Gli assi del pezzo (nelle sue coordinate): n lungo lo spessore, u e v sul piano; u quello più orizzontale nel
    mondo (sinistra/destra prima di sopra/sotto, come Appoggia), u e v verso il positivo del mondo."""
    est = P.max(axis=0) - P.min(axis=0)
    k = int(np.argmin(est))
    altri = [i for i in range(3) if i != k]
    if est[k] > PIATTO * min(est[i] for i in altri):
        raise VanoError('Il pezzo fermo non è un telaio piatto (un’anta, una cornice, una parete): «Metti nel vano» '
                        'cerca i buchi guardandolo dritto. Per gli altri casi usa «Appoggia».')
    e = np.eye(3)
    u, v = e[altri[0]], e[altri[1]]
    U, V = R @ u, R @ v
    if abs(U[0]) < abs(V[0]) or (abs(abs(U[0]) - abs(V[0])) < 1e-6 and abs(U[1]) < abs(V[1])):
        u, v, U, V = v, u, V, U
    if U[np.argmax(np.abs(U))] < 0:
        u = -u
    if V[np.argmax(np.abs(V))] < 0:
        v = -v
    return u, v, np.cross(u, v)


def _mappa(Q2, tri, passo, o, forma):
    """Pieno (True) dove un triangolo, visto dritto, copre il centro del quadretto."""
    M = np.zeros(forma, dtype=bool)
    for a, b, c in tri:
        A2, B2, C2 = Q2[a], Q2[b], Q2[c]
        d1, d2 = B2 - A2, C2 - A2
        det = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(det) < 1e-9:                   # un fianco visto di taglio: lo coprono le facce davanti e dietro
            continue
        lo = np.minimum(np.minimum(A2, B2), C2)
        hi = np.maximum(np.maximum(A2, B2), C2)
        i0, j0 = np.maximum(np.floor((lo - o) / passo - 0.5).astype(int), 0)
        i1, j1 = np.minimum(np.ceil((hi - o) / passo - 0.5).astype(int), np.array(forma) - 1)
        if i1 < i0 or j1 < j0:
            continue
        gi, gj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing='ij')
        px = o[0] + (gi + 0.5) * passo - A2[0]
        py = o[1] + (gj + 0.5) * passo - A2[1]
        s = (px * d2[1] - py * d2[0]) / det
        t = (d1[0] * py - d1[1] * px) / det
        dentro = (s >= -1e-6) & (t >= -1e-6) & (s + t <= 1 + 1e-6)
        M[gi[dentro], gj[dentro]] = True
    return M


def _raggio(T0, E1, E2, o, d):
    """Il primo triangolo che il raggio da o lungo d tocca: (distanza, indice) o (None, None)."""
    h = np.cross(d, E2)
    a = np.einsum('ij,ij->i', E1, h)
    ok = np.abs(a) > 1e-12
    f = np.zeros_like(a)
    f[ok] = 1.0 / a[ok]
    s = o - T0
    uu = f * np.einsum('ij,ij->i', s, h)
    q = np.cross(s, E1)
    vv = f * (q @ d)
    t = f * np.einsum('ij,ij->i', E2, q)
    buoni = ok & (uu >= -1e-9) & (vv >= -1e-9) & (uu + vv <= 1 + 1e-9) & (t > 1e-6)
    if not buoni.any():
        return None, None
    i = int(np.argmin(np.where(buoni, t, np.inf)))
    return float(t[i]), i


class _Telaio:
    def __init__(self, part, R):
        self.part = part
        P, idx, faccia = _triangoli(part)
        self.P, self.idx, self.faccia = P, idx, faccia
        self.u, self.v, self.n = _assi(P, np.asarray(R, dtype=float))
        self.T0 = P[idx[:, 0]]
        self.E1 = P[idx[:, 1]] - self.T0
        self.E2 = P[idx[:, 2]] - self.T0
        qn = P @ self.n
        self.lo_n, self.hi_n = float(qn.min()), float(qn.max())
        self.vani = self._trova()

    def _raggi(self, c, du, dv, z, righe):
        """Dal punto c (u, v) alla profondità z i raggi lungo ±du, su più righe spostate lungo dv: le due distanze
        più corte (inf se da quella parte il raggio esce: un lato senza parete) e le facce toccate sulla riga 0."""
        meno, piu, fm, fp = math.inf, math.inf, None, None
        for r in righe:
            o = self.u * c[0] + self.v * c[1] + dv * r + self.n * z
            for verso in (-1, 1):
                t, k = _raggio(self.T0, self.E1, self.E2, o, du * verso)
                if t is None:
                    continue
                if verso < 0:
                    meno = min(meno, t)
                    if r == 0:
                        fm = int(self.faccia[k])
                else:
                    piu = min(piu, t)
                    if r == 0:
                        fp = int(self.faccia[k])
        return meno, piu, fm, fp

    def _livelli(self):
        """Le profondità (lungo n) dove il telaio cambia sezione: le facce piane a squadra con lo spessore, più le due
        facce esterne. Tra due livelli la sezione è la stessa (uno «strato»)."""
        pz = _pezzo(self.part)
        liv = {round(self.lo_n, 3), round(self.hi_n, 3)}
        for k, i in pz.piane():
            if abs(float(np.dot(i['n'], self.n))) > 0.9999:
                pts = pz.per_faccia.get(k)
                if pts is not None and len(pts):
                    liv.add(round(float((pts @ self.n).mean()), 3))
        liv = sorted(liv)
        return [(a, b) for a, b in zip(liv, liv[1:]) if b - a > 0.05]

    def _trova(self):
        from scipy import ndimage
        Q2 = np.stack([self.P @ self.u, self.P @ self.v], axis=1)
        lo, hi = Q2.min(axis=0), Q2.max(axis=0)
        passo = max(1.0, float((hi - lo).max()) / 500)
        o = lo - 2 * passo
        forma = tuple(int(x) for x in np.ceil((hi - lo) / passo + 4))
        pieno = ndimage.binary_dilation(_mappa(Q2, self.idx, passo, o, forma))   # niente fessure tra un tubo e l'altro
        lab, quanti = ndimage.label(~pieno)
        fuori = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
        vani = []
        strati = self._livelli()
        for k in range(1, quanti + 1):
            if k in fuori:
                continue
            zona = lab == k
            if zona.sum() * passo * passo < AREA_MIN:
                continue
            dist = ndimage.distance_transform_edt(zona)
            i, j = np.unravel_index(int(np.argmax(dist)), dist.shape)
            c = np.array([o[0] + (i + 0.5) * passo, o[1] + (j + 0.5) * passo])
            # prima alla buona dal centro (il più stretto tra gli strati), poi strato per strato su tre righe
            mu = [self._raggi(c, self.u, self.v, (a + b) / 2, [0.0]) for a, b in strati]
            mv = [self._raggi(c, self.v, self.u, (a + b) / 2, [0.0]) for a, b in strati]
            lim = [min(x[0] for x in mu), min(x[1] for x in mu), min(x[0] for x in mv), min(x[1] for x in mv)]
            if not all(math.isfinite(x) for x in lim):
                continue
            c = c + np.array([(lim[1] - lim[0]) / 2, (lim[3] - lim[2]) / 2])
            W, H = lim[0] + lim[1], lim[2] + lim[3]
            vn = {'strati': []}
            for a, b in strati:
                z = (a + b) / 2
                ru = self._raggi(c, self.u, self.v, z, [0.0, -0.35 * H, 0.35 * H])
                rv = self._raggi(c, self.v, self.u, z, [0.0, -0.35 * W, 0.35 * W])
                vn['strati'].append({'z0': a, 'z1': b, 'lo_u': float(c[0] - ru[0]), 'hi_u': float(c[0] + ru[1]),
                                     'lo_v': float(c[1] - rv[0]), 'hi_v': float(c[1] + rv[1]),
                                     'facce': {'-u': self._lato(ru[2], self.u), '+u': self._lato(ru[3], -self.u),
                                               '-v': self._lato(rv[2], self.v), '+v': self._lato(rv[3], -self.v)}})
            # il vano che passa da parte a parte: il più stretto di tutti gli strati, con le facce di quello
            for chi, lato, sc in (('lo_u', '-u', max), ('hi_u', '+u', min), ('lo_v', '-v', max), ('hi_v', '+v', min)):
                s = sc(vn['strati'], key=lambda x: x[chi])
                vn[chi] = s[chi]
                vn.setdefault('facce', {})[lato] = s['facce'][lato]
            vani.append(vn)
        for vn in vani:
            vn['fronte'], vn['retro'] = self._fronte(vn)
        return vani

    def faccia_a(self, livello, verso, rett):
        """La faccia piana del telaio al livello (lungo n) che guarda verso (±n) e tocca il rettangolo (u, v): la
        battuta su cui posa il pannello in una scanalatura."""
        pz = _pezzo(self.part)
        lo_u, hi_u, lo_v, hi_v = rett
        meglio = None
        for k, i in pz.piane():
            if float(np.dot(i['n'], self.n)) * verso < 0.9999:
                continue
            pts = pz.per_faccia.get(k)
            if pts is None or not len(pts) or abs(float((pts @ self.n).mean()) - livello) > 0.02:
                continue
            qu, qv = pts @ self.u, pts @ self.v
            dentro = (min(qu.max(), hi_u) - max(qu.min(), lo_u)) > 0 and (min(qv.max(), hi_v) - max(qv.min(), lo_v)) > 0
            if dentro and (meglio is None or len(pts) > meglio[0]):
                meglio = (len(pts), k)
        return meglio[1] if meglio else None

    def _lato(self, k, verso):
        """La faccia toccata, se è piana e guarda dentro il vano (per «in mezzo»); se no None."""
        if k is None or k < 0:
            return None
        i = _pezzo(self.part).info(k)
        if i['kind'] != 'piana' or float(np.dot(i['n'], verso)) < 0.9999:
            return None
        return k

    def _fronte(self, vn):
        """Le facce davanti (+n) e dietro (-n) dei pezzi che bordano il vano: (k, livello) per ciascuna."""
        pz = _pezzo(self.part)
        largo = 10.0
        out = []
        for verso in (1, -1):
            migliore = None
            for k, i in pz.piane():
                if float(np.dot(i['n'], self.n)) * verso < 0.9999:
                    continue
                pts = pz.per_faccia.get(k)
                if pts is None or not len(pts):
                    continue
                qu, qv = pts @ self.u, pts @ self.v
                if (qu.max() < vn['lo_u'] - largo or qu.min() > vn['hi_u'] + largo
                        or qv.max() < vn['lo_v'] - largo or qv.min() > vn['hi_v'] + largo):
                    continue
                liv = float((pts @ self.n).mean())
                if migliore is None or liv * verso > migliore[1] * verso + 1e-6:
                    migliore = (k, liv)
            if migliore is None:
                migliore = (None, self.hi_n if verso > 0 else self.lo_n)
            out.append(migliore)
        return out


def telaio(part, R) -> _Telaio:
    """I vani di un telaio (nelle sue coordinate): si cercano una volta per pezzo."""
    R = np.asarray(R, dtype=float)
    c = _CACHE.get(id(part))
    if c is not None and c.part is part:
        u, v, n = _assi(c.P, R)
        if np.allclose(u, c.u) and np.allclose(v, c.v):
            return c
    if len(_CACHE) > 32:
        _CACHE.clear()
    c = _CACHE[id(part)] = _Telaio(part, R)
    return c


# ------------------------------------------------------------------ il pannello: come entra
def _area(pz, k) -> float:
    import build123d as bd
    try:
        return float(bd.Face(pz.facce[k]).area)
    except Exception:  # noqa: BLE001
        return 0.0


def _fondo(pz, e):
    """Da che parte (lungo e, l'asse dello spessore del pannello) c'è il fondo pieno: +1 o -1. Il lato con più
    superficie piana sull'estremo (il fondo di una vaschetta, non le punte delle pieghe)."""
    lo, hi = pz.estremi(e)
    tot = {1: 0.0, -1: 0.0}
    for k, i in pz.piane():
        d = float(np.dot(i['n'], e))
        if abs(d) < 0.9999:
            continue
        pts = pz.per_faccia.get(k)
        if pts is None or not len(pts):
            continue
        liv = float((pts @ e).mean())
        if d > 0 and abs(liv - hi) < 0.05:
            tot[1] += _area(pz, k)
        elif d < 0 and abs(liv - lo) < 0.05:
            tot[-1] += _area(pz, k)
    return 1 if tot[1] >= tot[-1] else -1


def _rotazioni(pz, tl: _Telaio, f_loc, capovolgi):
    """Le quattro rotazioni (pannello → telaio, nelle coordinate del telaio) col fondo verso il davanti (o dietro
    se capovolto), un quarto di giro alla volta attorno allo spessore."""
    est = pz.punti.max(axis=0) - pz.punti.min(axis=0)
    t = int(np.argmin(est))
    a1, a2 = [i for i in range(3) if i != t]
    e = np.eye(3)
    fondo = _fondo(pz, e[t])
    dove = f_loc * (-1 if capovolgi else 1)
    out = []
    for w in (tl.u, tl.v, -tl.u, -tl.v):
        M = np.zeros((3, 3))
        M[:, t] = dove * fondo
        M[:, a1] = w
        M[:, a2] = np.cross(dove * fondo, w)
        if np.linalg.det(M) < 0:
            M[:, a2] = -M[:, a2]
        out.append(M)
    return out


def _davanti(tl: _Telaio, Ra):
    """Il verso del davanti del telaio (nelle sue coordinate): verso chi guarda (davanti), se no sopra, se no destra."""
    N = Ra @ tl.n
    punti = float(np.dot(N, [0, -1, 0])) * 4 + float(np.dot(N, [0, 0, 1])) * 2 + float(np.dot(N, [1, 0, 0]))
    return tl.n if punti >= 0 else -tl.n


def _ingombro(pz, M, tl):
    Q = pz.punti @ M.T
    qu, qv = Q @ tl.u, Q @ tl.v
    return Q, float(qu.max() - qu.min()), float(qv.max() - qv.min())


def _passa(w, h, r) -> bool:
    return w <= r['hi_u'] - r['lo_u'] + 1e-6 and h <= r['hi_v'] - r['lo_v'] + 1e-6


def _sedi(pz, M, tl, vn):
    """Le scanalature dove il pannello entra (05/11, il ferma plexi): strati di fila più larghi del vano che passa,
    dove il pannello ci sta di lato, alti almeno quanto il suo spessore. Ognuna: (z0, z1, gli strati)."""
    Q, w, h = _ingombro(pz, M, tl)
    sp = float((Q @ tl.n).max() - (Q @ tl.n).min())
    out, fila = [], []
    for s in vn['strati'] + [None]:
        if s is not None and _passa(w, h, s):
            fila.append(s)
            continue
        if fila and fila[-1]['z1'] - fila[0]['z0'] >= sp - 1e-6 and len(fila) < len(vn['strati']):
            out.append((fila[0]['z0'], fila[-1]['z1'], fila))
        fila = []
    return out


def _ci_sta(pz, M, tl, vn):
    _, w, h = _ingombro(pz, M, tl)
    return _passa(w, h, vn) or bool(_sedi(pz, M, tl, vn))


def _nome_vani(tl: _Telaio, Ra, vani):
    """Il nome di ogni vano per i pulsanti: dove sta nel telaio (sotto, sopra, a sinistra…)."""
    c0 = (tl.P.min(axis=0) + tl.P.max(axis=0)) / 2
    nomi = []
    for vn in vani:
        c = tl.u * (vn['lo_u'] + vn['hi_u']) / 2 + tl.v * (vn['lo_v'] + vn['hi_v']) / 2
        d = Ra @ (c - (tl.u * float(c0 @ tl.u) + tl.v * float(c0 @ tl.v)))
        nomi.append('al centro' if np.linalg.norm(d) < 20 else nome_lato(d))
    for k, x in enumerate(nomi):
        if nomi.count(x) > 1:
            nomi[k] = f'{x} {nomi[:k + 1].count(x)}'
    return nomi


def _misure(pz, M, tl, vn):
    """Le misure da far vedere: quelle del vano che passa, o della scanalatura dove il pannello entra."""
    _, w, h = _ingombro(pz, M, tl)
    if _passa(w, h, vn):
        return vn['hi_u'] - vn['lo_u'], vn['hi_v'] - vn['lo_v']
    for _, _, fila in _sedi(pz, M, tl, vn):
        r = _rett(fila)
        return r['hi_u'] - r['lo_u'], r['hi_v'] - r['lo_v']
    return vn['hi_u'] - vn['lo_u'], vn['hi_v'] - vn['lo_v']


def _rett(fila) -> dict:
    """Il rettangolo libero comune a più strati, con le facce dello strato più stretto per ogni lato."""
    r = {'facce': {}}
    for chi, lato, sc in (('lo_u', '-u', max), ('hi_u', '+u', min), ('lo_v', '-v', max), ('hi_v', '+v', min)):
        s = sc(fila, key=lambda x: x[chi])
        r[chi] = s[chi]
        r['facce'][lato] = s['facce'][lato] if math.isfinite(s[chi]) else None
    return r


def _sposta_lato(lo, hi, qmin, qmax, gioco, centro):
    """Di quanto spostare il pannello lungo una direzione: centrato tra due pareti; con una parete sola, a quella
    con lo stesso gioco degli altri lati (Stefano, 05/11: «b»); senza pareti, sul centro del vano."""
    if math.isfinite(lo) and math.isfinite(hi):
        return (lo + hi) / 2 - (qmin + qmax) / 2
    if math.isfinite(lo):
        return lo + gioco - qmin
    if math.isfinite(hi):
        return hi - gioco - qmax
    return centro - (qmin + qmax) / 2


def metti(part_a, Ra, Ta, part_b, Rb, opz: dict | None = None, punto=None) -> dict:
    """Dove va il pannello (part_b) nel vano del telaio (part_a, messo in Ra, Ta).

    opz: vano (indice; None = quello dove ci sta, il più vicino al clic), gira (quarti di giro), capovolgi, prof
    ('davanti' | 'mezzo' | 'dietro', se passa da parte a parte), sede (quale scanalatura, se non passa). Ritorna R,
    T, i vani (con misure, nome, se ci sta), quello scelto, i giochi ai quattro lati e gli accoppiamenti da fare
    ('vincoli': ('centra', fa, fa2, fb, fb2) o ('distanza', lato, fa, fb), con gli indici delle facce)."""
    opz = dict(opz or {})
    Ra, Ta, Rb = (np.asarray(x, dtype=float) for x in (Ra, Ta, Rb))
    tl = telaio(part_a, Ra)
    if not tl.vani:
        raise VanoError('In questo pezzo non trovo un vano chiuso da tutte le parti (un buco in mezzo ai tubi): '
                        'clicca il telaio con il vano dove va il pannello.')
    pz = _pezzo(part_b)
    f_loc = _davanti(tl, Ra)
    capo = bool(opz.get('capovolgi'))
    rot = _rotazioni(pz, tl, f_loc, capo)
    nomi = _nome_vani(tl, Ra, tl.vani)
    info_vani = []
    for k, vn in enumerate(tl.vani):
        entra_ = [M for M in rot if _ci_sta(pz, M, tl, vn)]
        W, H = _misure(pz, entra_[0] if entra_ else rot[0], tl, vn)
        info_vani.append({'i': k, 'nome': nomi[k], 'W': W, 'H': H, 'ci_sta': bool(entra_)})
    scelto = opz.get('vano')
    if scelto is None or not 0 <= int(scelto) < len(tl.vani):
        buoni = [x for x in info_vani if x['ci_sta']]
        if not buoni:
            _, w, h = _ingombro(pz, rot[0], tl)
            a, b = sorted((w, h))
            meglio = min(info_vani, key=lambda x: max(a - min(x['W'], x['H']), 0) + max(b - max(x['W'], x['H']), 0))
            W, H = meglio['W'], meglio['H']
            manca = []
            if a > min(W, H) + 1e-6:
                manca.append(f'{_mm(a - min(W, H))} mm sul lato corto')
            if b > max(W, H) + 1e-6:
                manca.append(f'{_mm(b - max(W, H))} mm sul lato lungo')
            raise VanoError(f'Il pannello è {_mm(a)} × {_mm(b)}, il vano più grande che trovo {_mm(min(W, H))} × '
                            f'{_mm(max(W, H))}: non ci sta, mancano {" e ".join(manca) or "pochi decimi"}.')
        if punto is not None and len(buoni) > 1:
            q = Ra.T @ (np.asarray(punto, dtype=float) - Ta)
            pu, pv = float(q @ tl.u), float(q @ tl.v)

            def lontano(x):
                vn = tl.vani[x['i']]
                du = max(vn['lo_u'] - pu, 0, pu - vn['hi_u'])
                dv = max(vn['lo_v'] - pv, 0, pv - vn['hi_v'])
                return (math.hypot(du, dv), x['W'] * x['H'])
            scelto = min(buoni, key=lontano)['i']
        else:
            scelto = min(buoni, key=lambda x: x['W'] * x['H'])['i']
    scelto = int(scelto)
    vn = tl.vani[scelto]
    entrano = [k for k, M in enumerate(rot) if _ci_sta(pz, M, tl, vn)]
    if not entrano:
        _, w, h = _ingombro(pz, rot[0], tl)
        a, b = sorted((w, h))
        W, H = info_vani[scelto]['W'], info_vani[scelto]['H']
        raise VanoError(f'Nel vano {nomi[scelto]} ({_mm(W)} × {_mm(H)}) il pannello ({_mm(a)} × {_mm(b)}) non ci sta: '
                        'scegli l’altro vano.')
    # il verso di partenza: quello che entra girando di meno il pannello da com'è adesso
    Rloc_b = Ra.T @ Rb
    primo = max(range(len(entrano)), key=lambda j: float(np.trace(rot[entrano[j]].T @ Rloc_b)))
    M = rot[entrano[(primo + int(opz.get('gira') or 0)) % len(entrano)]]
    Q, w, h = _ingombro(pz, M, tl)
    qu, qv, qf, qn = Q @ tl.u, Q @ tl.v, Q @ f_loc, Q @ tl.n
    du, dv, df, dn = M.T @ tl.u, M.T @ tl.v, M.T @ f_loc, M.T @ tl.n
    U, V, F, N = Ra @ tl.u, Ra @ tl.v, Ra @ f_loc, Ra @ tl.n
    lati = {'u': (nome_lato(-U), nome_lato(U)), 'v': (nome_lato(-V), nome_lato(V)), 'f': (nome_lato(F), nome_lato(-F))}
    mob = {'u': (pz.faccia_estrema(du, -1), pz.faccia_estrema(du, +1)),
           'v': (pz.faccia_estrema(dv, -1), pz.faccia_estrema(dv, +1))}
    vincoli = []
    sedi = [] if _passa(w, h, vn) else _sedi(pz, M, tl, vn)
    sede = None
    if not sedi:                                       # passa da parte a parte: a filo davanti / in mezzo / dietro
        r = vn
        (kf, liv_f), (kr, liv_r) = vn['fronte'], vn['retro']
        davanti = liv_f if np.dot(f_loc, tl.n) > 0 else -liv_r          # i livelli lungo f_loc
        dietro = liv_r if np.dot(f_loc, tl.n) > 0 else -liv_f
        fronte_k, retro_k = (kf, kr) if np.dot(f_loc, tl.n) > 0 else (kr, kf)
        pf, pr = pz.faccia_estrema(df, +1), pz.faccia_estrema(df, -1)
        prof = opz.get('prof') or 'davanti'
        if prof == 'dietro':
            sf = dietro - float(qf.min())
            if None not in (retro_k, pr):
                vincoli.append(('distanza', lati['f'][1], retro_k, pr))
        elif prof == 'mezzo':
            sf = (davanti + dietro) / 2 - (float(qf.max()) + float(qf.min())) / 2
            if None not in (fronte_k, retro_k, pf, pr):
                vincoli.append(('centra', fronte_k, retro_k, pf, pr))
        else:
            prof = 'davanti'
            sf = davanti - float(qf.max())
            if None not in (fronte_k, pf):
                vincoli.append(('distanza', lati['f'][0], fronte_k, pf))
        t_n = f_loc * sf
        livello_rett = davanti
    else:                                              # nella scanalatura: posato sulla battuta, o in mezzo
        prof = 'sede'
        k_sede = int(opz.get('sede') or 0) % len(sedi)
        z0, z1, fila = sedi[k_sede]
        r = _rett(fila)
        su_ = float(np.dot(N, [0, 0, 1]))
        lo_p, hi_p = float(qn.min()), float(qn.max())
        bn_lo, bn_hi = pz.faccia_estrema(dn, -1), pz.faccia_estrema(dn, +1)
        if su_ > 0.5 or su_ < -0.5:                     # in piano: posa sulla battuta di sotto (il peso)
            giu = 1 if su_ > 0.5 else -1
            sn = (z0 - lo_p) if giu > 0 else (z1 - hi_p)
        else:
            giu = 0
            sn = (z0 + z1) / 2 - (lo_p + hi_p) / 2
        t_n = tl.n * sn
        livello_rett = (z0 + z1) / 2 * float(np.dot(tl.n, f_loc))
        sede = {'alta': z1 - z0, 'giu': giu, 'z': (z0, z1), 'quante': len(sedi), 'i': k_sede}
    W, H = r['hi_u'] - r['lo_u'], r['hi_v'] - r['lo_v']
    gu = (W - w) / 2 if math.isfinite(W) else None
    gv = (H - h) / 2 if math.isfinite(H) else None
    c_u = (vn['lo_u'] + vn['hi_u']) / 2
    c_v = (vn['lo_v'] + vn['hi_v']) / 2
    su = _sposta_lato(r['lo_u'], r['hi_u'], float(qu.min()), float(qu.max()), gv if gv is not None else 0.0, c_u)
    sv = _sposta_lato(r['lo_v'], r['hi_v'], float(qv.min()), float(qv.max()), gu if gu is not None else 0.0, c_v)
    t_loc = tl.u * su + tl.v * sv + t_n
    R = Ra @ M
    T = Ra @ t_loc + Ta
    # gli accoppiamenti di lato: in mezzo tra due pareti, o la distanza da quella che c'è
    for k, (lo, hi), (b0, b1), s in (('u', ('-u', '+u'), mob['u'], su), ('v', ('-v', '+v'), mob['v'], sv)):
        a0, a1 = r['facce'][lo], r['facce'][hi]
        if None not in (a0, a1, b0, b1):
            vincoli.append(('centra', a0, a1, b0, b1))
        elif a0 is not None and b0 is not None:
            vincoli.append(('distanza', lati[k][0], a0, b0))
        elif a1 is not None and b1 is not None:
            vincoli.append(('distanza', lati[k][1], a1, b1))
    if sede is not None:
        a_lo, a_hi = sede['z']
        ingombro = (r['lo_u'] if math.isfinite(r['lo_u']) else float(qu.min()) + su,
                    r['hi_u'] if math.isfinite(r['hi_u']) else float(qu.max()) + su,
                    r['lo_v'] if math.isfinite(r['lo_v']) else float(qv.min()) + sv,
                    r['hi_v'] if math.isfinite(r['hi_v']) else float(qv.max()) + sv)
        f_lo, f_hi = tl.faccia_a(a_lo, +1, ingombro), tl.faccia_a(a_hi, -1, ingombro)
        if sede['giu'] > 0 and None not in (f_lo, bn_lo):           # posato sulla battuta di sotto
            vincoli.append(('distanza', nome_lato(-N), f_lo, bn_lo))
        elif sede['giu'] < 0 and None not in (f_hi, bn_hi):
            vincoli.append(('distanza', nome_lato(N), f_hi, bn_hi))
        elif None not in (f_lo, f_hi, bn_lo, bn_hi):
            vincoli.append(('centra', f_lo, f_hi, bn_lo, bn_hi))

    def gioco(lo, hi, qmin, qmax, s):
        return (float(qmin + s - lo) if math.isfinite(lo) else None, float(hi - (qmax + s)) if math.isfinite(hi) else None)
    giochi = {'u': gioco(r['lo_u'], r['hi_u'], float(qu.min()), float(qu.max()), su),
              'v': gioco(r['lo_v'], r['hi_v'], float(qv.min()), float(qv.max()), sv)}

    # il rettangolo del vano (o della scanalatura) per farlo vedere in azzurro, nel mondo
    def chiudi(lo, hi, qmin, qmax, s):
        return (lo if math.isfinite(lo) else qmin + s, hi if math.isfinite(hi) else qmax + s)

    def rettangolo(rr, liv):
        a0, a1 = chiudi(rr['lo_u'], rr['hi_u'], float(qu.min()), float(qu.max()), su)
        b0, b1 = chiudi(rr['lo_v'], rr['hi_v'], float(qv.min()), float(qv.max()), sv)
        return [(Ra @ (tl.u * a + tl.v * b + f_loc * liv) + Ta).tolist() for a, b in ((a0, b0), (a1, b0), (a1, b1), (a0, b1))]
    rett = rettangolo(r, livello_rett)
    for x in info_vani:
        x['rett'] = rett if x['i'] == scelto else rettangolo(tl.vani[x['i']], vn['fronte'][1] * float(np.dot(tl.n, f_loc)))
    tiene = len(vincoli) >= 3                         # tenuto di lato in tutte e due le direzioni e in profondità
    return {'R': R, 'T': T, 'vani': info_vani, 'vano': scelto, 'rett': rett, 'prof': prof, 'sede': sede,
            'lati': lati, 'giochi': giochi, 'pannello': (w, h), 'versi': len(entrano), 'vincoli': vincoli,
            'tiene': tiene}


def metti_senza_entrare(part_a, Ra, Ta, part_b, Rb, opz=None, punto=None) -> dict:
    """Come metti(), più quanto il pannello entra nel telaio: 'dentro' (mm³) e, in una scanalatura, 'tocca' (mm):
    di quanto lo spigolo entra nei raggi delle pieghe (il pezzo in comune più sottile, misurato di traverso)."""
    from .assembly_appoggia import _comune, _posato
    r = metti(part_a, Ra, Ta, part_b, Rb, opz, punto)
    c = _comune(_posato(part_a, Ra, Ta), _posato(part_b, r['R'], r['T']))
    try:
        r['dentro'] = float(c.volume) if c is not None else 0.0
    except Exception:  # noqa: BLE001
        r['dentro'] = 0.0
    r['tocca'] = 0.0
    if r['dentro'] > DENTRO and c is not None:
        try:
            r['tocca'] = max(min(s.bounding_box().size.X, s.bounding_box().size.Y, s.bounding_box().size.Z)
                             for s in c.solids())
        except Exception:  # noqa: BLE001
            r['tocca'] = 0.0
    return r


def _mm(x) -> str:
    v = round(float(x), 1)
    return (str(int(v)) if abs(v - round(v)) < 1e-9 else str(v)).replace('.', ',')


__all__ = ['metti', 'metti_senza_entrare', 'telaio', 'VanoError', 'DENTRO']
