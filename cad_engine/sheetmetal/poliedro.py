"""Lamiera da facce piane: una forma qualsiasi fatta di facce piane (cassone + tramoggia, scarichi decentrati, bordi
piegati, angoli smussati…) diventa uno o più pezzi di lamiera piegata.

- La forma si descrive **per sezioni**: poligoni orizzontali (rettangoli, anche smussati, anche spostati) a varie
  quote; tra due sezioni di fila ci sono le facce (trapezi). Una sezione alla stessa quota della precedente ma più
  larga è un bordo piegato in fuori (bordo superiore, flangia dello scarico).
- Le misure sono quelle della superficie di riferimento: esterna (pezzo finito), interna o in asse lamiera.
- Ogni spigolo tra due facce è una **piega** o una **saldatura**. La proposta automatica mette più pieghe possibile
  con due vincoli: ogni pezzo sta nel foglio (es. 1500 × 3000) e nello sviluppo non si sovrappone a sé stesso.
  Gli spigoli tra facce complanari (gli angoli dei bordi) sono tagli, non pieghe.
- Sviluppo di ogni pezzo: le facce si ribaltano lungo le pieghe (albero a partire dalla faccia più grande) con la
  correzione di piega vera (BA − 2·setback, con il setback dal lato giusto della superficie di riferimento);
  sulle saldature la faccia che arriva contro l'altra si accorcia dello spessore (giunto di testa).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..errors import FeatureError
from .shapes import Facce, _contorno, _cross, _dot, _in_piano, _norm, _normale, _sub, _unit

COMPLANARI = 0.5          # gradi: sotto, due facce sono nello stesso piano (giunto di taglio, non piega)


# ============================================================================ forma per sezioni
@dataclass
class Sezione:
    larghezza: float           # lungo X
    profondita: float          # lungo Y
    z: float
    ex: float = 0.0            # spostamento del centro
    ey: float = 0.0
    smusso: float = 0.0        # smusso degli angoli (0 = rettangolo)
    nome: str = ''

    def punti(self):
        a, b, c = self.larghezza / 2, self.profondita / 2, self.smusso
        cx, cy, z = self.ex, self.ey, self.z
        if c <= 0:          # davanti a destra, dietro a destra, dietro a sinistra, davanti a sinistra (antiorario)
            return [(cx + a, cy - b, z), (cx + a, cy + b, z), (cx - a, cy + b, z), (cx - a, cy - b, z)]
        return [(cx + a - c, cy - b, z), (cx + a, cy - b + c, z), (cx + a, cy + b - c, z), (cx + a - c, cy + b, z),
                (cx - a + c, cy + b, z), (cx - a, cy + b - c, z), (cx - a, cy - b + c, z), (cx - a + c, cy - b, z)]


LATI4 = ['destra', 'dietro', 'sinistra', 'davanti']
LATI8 = ['davanti-destra', 'destra', 'dietro-destra', 'dietro', 'dietro-sinistra', 'sinistra', 'davanti-sinistra', 'davanti']


@dataclass
class Guscio:
    punti: list
    facce: list                       # [[i, j, k, l]] normale verso fuori
    nomi: list                        # nome di ogni faccia
    spigoli: dict = field(default_factory=dict)   # chiave -> {'facce': (f, g), 'v': (a, b), 'nome', 'lung', 'angolo'}


def guscio_da_sezioni(sezioni: list[Sezione], fasce: list[str] | None = None, aperte: set | None = None) -> Guscio:
    """Le facce tra una sezione e la successiva. fasce: il nome di ogni fascia (tra la sezione i e la i+1).
    aperte: le fasce (indici) con gli angoli aperti: ogni faccia è un rettangolo che finisce dritto sul suo lato
    (lo scasso d'angolo dei bordi piegati), invece dei trapezi che si incontrano a 45°."""
    if len(sezioni) < 2:
        raise FeatureError('Servono almeno due sezioni.')
    n = len(sezioni[0].punti())
    if any(len(s.punti()) != n for s in sezioni):
        raise FeatureError('Le sezioni devono avere lo stesso numero di lati (tutte smussate o tutte no).')
    for s in sezioni:
        if s.larghezza <= 0 or s.profondita <= 0:
            raise FeatureError('Ogni sezione ha larghezza e profondità maggiori di zero.')
        if s.smusso * 2 >= min(s.larghezza, s.profondita):
            raise FeatureError('Lo smusso degli angoli è più grande della sezione.')
    lati = LATI4 if n == 4 else LATI8
    P, F, nomi = [], [], []
    for s in sezioni:
        P += s.punti()
    for b in range(len(sezioni) - 1):
        for j in range(n):
            a0, a1 = b * n + j, b * n + (j + 1) % n
            b0, b1 = (b + 1) * n + j, (b + 1) * n + (j + 1) % n
            F.append([a0, a1, b1, b0])
            nomi.append(f'{(fasce or [])[b] if fasce and b < len(fasce) else "fascia " + str(b + 1)} {lati[j]}')
    nfasce = len(sezioni) - 1
    for b in sorted(aperte or ()):
        # il lato che resta è quello in comune con la fascia vicina: per la prima fascia (la flangia dello scarico,
        # attaccata da sopra) è quello della sezione dopo; per le altre (il bordo in alto) quello della sezione prima
        dal_basso = not (b == 0 and nfasce > 1)
        tenuta, altra = (sezioni[b], sezioni[b + 1]) if dal_basso else (sezioni[b + 1], sezioni[b])
        # bordo verso dentro (la sezione del bordo più stretta di quella da cui parte, 22/10): le facce dritte si
        # accavallerebbero negli angoli; finiscono dritte prima dell'angolo e lì resta lo scasso quadrato
        dentro = altra.larghezza * altra.profondita < tenuta.larghezza * tenuta.profondita
        for j in range(n):
            f = F[b * n + j]
            if not dal_basso:
                f = [f[3], f[2], f[1], f[0]]                  # stessa faccia, girata: il lato da tenere viene prima
            a0, a1, b1, b0 = (P[i] for i in f)
            u = _unit(_sub(a1, a0))
            nrm = _normale(P, f)
            w = _unit(_cross(nrm, u))
            prof = _dot(_sub(b0, a0), w)
            if prof < 0:
                w, prof = (-w[0], -w[1], -w[2]), -prof
            if not dentro:
                n0 = tuple(a0[q] + w[q] * prof for q in range(3))
                n1 = tuple(a1[q] + w[q] * prof for q in range(3))
                P += [n0, n1]
                nuova = [f[0], f[1], len(P) - 1, len(P) - 2]
                F[b * n + j] = nuova if dal_basso else nuova[::-1]
                continue
            lato = _norm(_sub(a1, a0))
            if lato <= 2 * prof + 1e-6:
                raise FeatureError(f'Il bordo verso dentro con gli angoli dritti ({prof:.0f} mm) è più largo di metà '
                                   f'lato ({lato:.0f} mm): fallo più corto o con gli angoli a 45°.')
            s0 = tuple(a0[q] + u[q] * prof for q in range(3))
            s1 = tuple(a1[q] - u[q] * prof for q in range(3))
            o0 = tuple(s0[q] + w[q] * prof for q in range(3))
            o1 = tuple(s1[q] + w[q] * prof for q in range(3))
            P += [s0, s1, o0, o1]
            i0, i1 = len(P) - 4, len(P) - 3
            nuova = [i0, i1, len(P) - 1, len(P) - 2]
            F[b * n + j] = nuova if dal_basso else nuova[::-1]
            # la faccia accanto (la parete) ha lo spigolo a0→a1 percorso al contrario: ci entrano i due punti nuovi
            for k, g in enumerate(F):
                if k == b * n + j:
                    continue
                for m in range(len(g)):
                    if g[m] == f[1] and g[(m + 1) % len(g)] == f[0]:
                        F[k] = g[:m + 1] + [i1, i0] + g[m + 1:]
                        break
    G = Guscio(P, F, nomi)
    _orienta(G, sezioni)
    _trova_spigoli(G, n, fasce)
    return G


def _orienta(G: Guscio, sezioni):
    """Normali verso fuori: la prima faccia non orizzontale guarda lontano dall'asse."""
    for k, f in enumerate(G.facce):
        nrm = _normale(G.punti, f)
        if abs(nrm[2]) > 0.99:
            continue
        c = [sum(G.punti[i][q] for i in f) / len(f) for q in range(3)]
        s = sezioni[0]
        if (c[0] - s.ex) * nrm[0] + (c[1] - s.ey) * nrm[1] < 0:
            G.facce = [list(reversed(x)) for x in G.facce]
        return


def _trova_spigoli(G: Guscio, n, fasce):
    """Le chiavi degli spigoli sono per nome (lato:cassone:0, giro:tramoggia:2): restano le stesse se si aggiunge o
    toglie una fascia (la flangia dello scarico), così le scelte piega/saldatura dell'utente non si spostano."""
    nome_f = lambda b: (fasce[b] if fasce and b < len(fasce) else f'fascia{b + 1}').replace(' ', '_')  # noqa: E731
    usi = {}
    for k, f in enumerate(G.facce):
        for a, b in zip(f, f[1:] + f[:1]):
            usi.setdefault(frozenset((a, b)), []).append(k)
    for key, fs in usi.items():
        if len(fs) != 2:
            continue
        a, b = sorted(key)
        f, g = fs
        bf, bg = f // n, g // n
        if bf == bg:                         # stesso giro di facce: spigolo d'angolo
            nome = f'spigolo {G.nomi[f].split(" ", 1)[0] if " " in G.nomi[f] else ""} {G.nomi[f].rsplit(" ", 1)[-1]}/{G.nomi[g].rsplit(" ", 1)[-1]}'
            chiave = f'lato:{nome_f(bf)}:{min(f % n, g % n) if abs(f % n - g % n) == 1 else max(f % n, g % n)}'
        else:                                # tra due fasce: cambio di pendenza (o bordo)
            nome = f'{G.nomi[min(f, g)]} → {G.nomi[max(f, g)].rsplit(" ", 1)[0]}'
            chiave = f'giro:{nome_f(max(bf, bg))}:{f % n}'
        n1, n2 = _normale(G.punti, G.facce[f]), _normale(G.punti, G.facce[g])
        ang = math.degrees(math.acos(max(-1.0, min(1.0, _dot(n1, n2)))))
        G.spigoli[chiave] = {'facce': (f, g), 'v': (a, b), 'nome': nome.strip(),
                             'lung': _norm(_sub(G.punti[a], G.punti[b])), 'angolo': ang}


# ============================================================================ sviluppo di un pezzo
@dataclass
class Tecnologia:
    t: float
    r: float | None
    k: float | None
    rif: str = 'esterno'               # 'esterno' | 'interno' | 'asse'

    def correzione(self, angolo, verso_fuori: bool) -> float:
        """Quanto cambia lo sviluppo per una piega di `angolo` gradi rispetto agli spigoli vivi della superficie di
        riferimento. verso_fuori: la faccia nuova va dal lato della normale (la superficie di riferimento è dentro
        la piega)."""
        if self.r is None or self.k is None or angolo < 1e-6:
            return 0.0
        th = math.radians(angolo)
        ba = th * (self.r + self.k * self.t)
        if self.rif == 'asse':
            c = self.t / 2
        elif self.rif == 'esterno':
            c = 0.0 if verso_fuori else self.t
        else:
            c = self.t if verso_fuori else 0.0
        return ba - 2 * (self.r + c) * math.tan(th / 2)


@dataclass
class Pezzo:
    facce: list                         # indici delle facce del guscio
    poligoni: dict                      # faccia -> [(x, y)] nello sviluppo
    pieghe: list                        # [{'spigolo', 'a', 'b', 'angolo', 'verso', 'lung', 'corr'}]
    saldature: list                     # chiavi degli spigoli saldati sul bordo di questo pezzo
    nome: str = ''

    def punti(self):
        return [q for poly in self.poligoni.values() for q in poly]


def _verso(G, f, g, a, b):
    """True se la faccia g sta dal lato della normale di f (piega "verso fuori")."""
    nf = _normale(G.punti, G.facce[f])
    cg = [sum(G.punti[i][q] for i in G.facce[g]) / len(G.facce[g]) for q in range(3)]
    return _dot(_sub(cg, G.punti[a]), nf) > 0


def sviluppa_pezzo(G: Guscio, facce: list, pieghe: set, tec: Tecnologia) -> Pezzo:
    """Le facce del pezzo ribaltate sul piano lungo le pieghe (in albero: un giro chiuso di pieghe non si sviluppa)."""
    facce = list(facce)
    radice = max(facce, key=lambda f: _area3(G, f))
    poligoni, posto = {}, {}
    loc = _in_piano(G.punti, G.facce[radice])
    poligoni[radice] = loc
    posto[radice] = {v: q for v, q in zip(G.facce[radice], loc)}
    coda = [radice]
    usate = []
    pezzo_pieghe = []
    while coda:
        f = coda.pop(0)
        for key in sorted(pieghe):
            s = G.spigoli[key]
            if f not in s['facce']:
                continue
            g = s['facce'][1] if s['facce'][0] == f else s['facce'][0]
            if g not in facce or g in poligoni:
                if g in poligoni and key not in usate and key not in [p['spigolo'] for p in pezzo_pieghe]:
                    raise FeatureError('Le pieghe chiudono un giro: almeno uno di quegli spigoli va saldato '
                                       f'({s["nome"]}).')
                continue
            a, b = s['v']
            lg = _in_piano(G.punti, G.facce[g])
            pg = {v: q for v, q in zip(G.facce[g], lg)}
            A2, B2 = posto[f][a], posto[f][b]
            a2, b2 = pg[a], pg[b]
            ang = math.atan2(B2[1] - A2[1], B2[0] - A2[0]) - math.atan2(b2[1] - a2[1], b2[0] - a2[0])
            c, sn = math.cos(ang), math.sin(ang)
            R = lambda q, a2=a2, A2=A2, c=c, sn=sn: (A2[0] + c * (q[0] - a2[0]) - sn * (q[1] - a2[1]),  # noqa: E731
                                                       A2[1] + sn * (q[0] - a2[0]) + c * (q[1] - a2[1]))
            ex_, ey_ = B2[0] - A2[0], B2[1] - A2[1]
            ln = math.hypot(ex_, ey_)
            px, py = -ey_ / ln, ex_ / ln
            cgx = sum(R(q)[0] for q in lg) / len(lg) - A2[0]
            cgy = sum(R(q)[1] for q in lg) / len(lg) - A2[1]
            if cgx * px + cgy * py < 0:
                px, py = -px, -py
            fuori = _verso(G, f, g, a, b)
            d = tec.correzione(s['angolo'], fuori)
            T = lambda q, R=R, d=d, px=px, py=py: (R(q)[0] + d * px, R(q)[1] + d * py)  # noqa: E731
            poligoni[g] = [T(q) for q in lg]
            posto[g] = {v: T(q) for v, q in zip(G.facce[g], lg)}
            pezzo_pieghe.append({'spigolo': key, 'a': (A2[0] + d / 2 * px, A2[1] + d / 2 * py),
                                 'b': (B2[0] + d / 2 * px, B2[1] + d / 2 * py), 'angolo': s['angolo'],
                                 'verso': 'su' if fuori else 'giù', 'lung': ln, 'corr': d,
                                 'striscia': (A2, B2, (A2[0] + d * px, A2[1] + d * py), (B2[0] + d * px, B2[1] + d * py))})
            usate.append(key)
            coda.append(g)
    if set(poligoni) != set(facce):
        raise FeatureError('Il pezzo non è unito da pieghe.')
    p = Pezzo(facce, poligoni, pezzo_pieghe, [])
    p.vertici = {f: dict(posto[f]) for f in facce}       # i vertici prima dei rifili (per le linee di saldatura)
    _accorcia_saldature(G, p, pieghe, tec)
    _scarichi(G, p, pieghe)
    return p


def _area3(G, f):
    pts = [G.punti[i] for i in G.facce[f]]
    s = (0.0, 0.0, 0.0)
    for i in range(1, len(pts) - 1):
        c = _cross(_sub(pts[i], pts[0]), _sub(pts[i + 1], pts[0]))
        s = (s[0] + c[0], s[1] + c[1], s[2] + c[2])
    return _norm(s) / 2


def _accorcia_saldature(G, p: Pezzo, pieghe: set, tec: Tecnologia):
    """Sulle saldature una delle due facce (quella con l'indice più alto) arriva contro l'altra e si rifila:
    - se le due facce sono nello stesso pezzo, lungo il bordo dell'altra così com'è nello sviluppo: la deduzione delle
      pieghe vicine le avvicina e lì si sovrapporrebbero (il materiale che in 3D colliderebbe sulla saldatura);
    - in più, sugli spigoli sporgenti con le misure esterne, dello spessore: t / sen(angolo) (t a 90°), il giunto di
      testa contro la faccia interna dell'altra.
    Il rifilo è un taglio con un semipiano: va bene anche se la faccia ha più saldature."""
    for key, s in G.spigoli.items():
        if key in pieghe:
            continue
        f, g = s['facce']
        if f not in p.facce and g not in p.facce:
            continue
        p.saldature.append(key)
        if s['angolo'] < COMPLANARI:
            continue
        corta, altra = max(f, g), min(f, g)
        if corta not in p.facce:
            continue
        a, b = s['v']
        stessa = altra in p.facce
        if stessa:
            # il bordo dell'altra serve solo se nello sviluppo le due facce si toccano lì (stesso spigolo, avvicinato
            # dalle pieghe). La giunzione che chiude un anello (falda davanti saldata alla sinistra, con le altre falde
            # in mezzo) ha i due lati lontani: il semipiano dell'altra tagliava via metà faccia (28/10)
            Ac, Bc = p.vertici[corta][a], p.vertici[corta][b]
            Aa, Ba = p.vertici[altra][a], p.vertici[altra][b]
            if math.dist(Ac, Aa) + math.dist(Bc, Ba) > 10 * tec.t + 20:
                continue                                    # come prima, quando il semipiano non la toccava
        A, B = (p.vertici[altra][a], p.vertici[altra][b]) if stessa else (p.vertici[corta][a], p.vertici[corta][b])
        ex_, ey_ = B[0] - A[0], B[1] - A[1]
        ln = math.hypot(ex_, ey_)
        nx, ny = -ey_ / ln, ex_ / ln
        cv = p.vertici[corta]
        cx = sum(q[0] for q in cv.values()) / len(cv) - A[0]
        cy = sum(q[1] for q in cv.values()) / len(cv) - A[1]
        if cx * nx + cy * ny < 0:
            nx, ny = -nx, -ny
        sporge = tec.rif == 'esterno' and not _verso(G, altra, corta, a, b)
        dd = tec.t / max(math.sin(math.radians(s['angolo'])), 0.3) if sporge else 0.0
        poly = p.poligoni[corta]
        tenuto = _taglia_semipiano(poly, A, (nx, ny), dd)
        if len(tenuto) >= 3:
            p.poligoni[corta] = tenuto


SCARICO_MAX = 0.03        # una sovrapposizione fino al 3% della faccia più piccola si toglie con lo scarico d'angolo


def _scarichi(G, p: Pezzo, pieghe: set):
    """Scarichi d'angolo: due facce del pezzo non unite dalla stessa piega che nello sviluppo si accavallano per
    poco (vicino a dove si incontrano più pieghe: la deduzione di piega le avvicina) — la seconda si rifila lungo il
    bordo dell'altra che toglie meno materiale. Se si accavallano di più, il pezzo non si fa così (lo dice
    sovrapposizione())."""
    vicine = {frozenset(G.spigoli[k]['facce']) for k in pieghe}
    fs = sorted(p.poligoni)
    for i in range(len(fs)):
        for j in range(i + 1, len(fs)):
            X, Y = fs[i], fs[j]
            if frozenset((X, Y)) in vicine:
                continue
            px, py = p.poligoni[X], p.poligoni[Y]
            inter = _clip(py, px)
            if len(inter) < 3:
                continue
            area = _area2(inter)
            if area < 1e-6 or area > SCARICO_MAX * min(_area2(px), _area2(py)):
                continue
            # il lato di X che, preso come confine, lascia a Y più materiale senza più toccare X
            migliore = None
            cx = sum(q[0] for q in px) / len(px)
            cy = sum(q[1] for q in px) / len(px)
            for k in range(len(px)):
                A, B = px[k - 1], px[k]
                ln = math.hypot(B[0] - A[0], B[1] - A[1])
                if ln < 1e-9:
                    continue
                n = (-(B[1] - A[1]) / ln, (B[0] - A[0]) / ln)
                if (cx - A[0]) * n[0] + (cy - A[1]) * n[1] > 0:     # n verso fuori da X
                    n = (-n[0], -n[1])
                resto = _taglia_semipiano(py, A, n, 0.0)
                if len(resto) < 3:
                    continue
                sov = _clip(resto, px)
                if len(sov) >= 3 and _area2(sov) > 1e-3:
                    continue
                if migliore is None or _area2(resto) > migliore[0]:
                    migliore = (_area2(resto), resto)
            if migliore is not None:
                p.poligoni[Y] = migliore[1]


def _taglia_semipiano(poly, A, n, d):
    """La parte del poligono con (q − A)·n ≥ d."""
    dist = lambda q: (q[0] - A[0]) * n[0] + (q[1] - A[1]) * n[1] - d  # noqa: E731
    out = []
    for i in range(len(poly)):
        p, q = poly[i - 1], poly[i]
        dp, dq = dist(p), dist(q)
        if dq >= -1e-9:
            if dp < -1e-9:
                t = dp / (dp - dq)
                out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
            out.append(q)
        elif dp >= -1e-9:
            t = dp / (dp - dq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


# ============================================================================ controlli
def _area2(poly):
    return abs(sum(poly[i][0] * poly[i - 1][1] - poly[i - 1][0] * poly[i][1] for i in range(len(poly)))) / 2


def _clip(subj, clip):
    """Intersezione di due poligoni convessi (Sutherland–Hodgman)."""
    def dentro(p, a, b, s):
        return s * ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) >= -1e-9

    def incrocio(p, q, a, b):
        x1, y1, x2, y2 = p[0], p[1], q[0], q[1]
        x3, y3, x4, y4 = a[0], a[1], b[0], b[1]
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) < 1e-12:
            return q
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    s = 1 if sum(clip[i][0] * clip[i - 1][1] - clip[i - 1][0] * clip[i][1] for i in range(len(clip))) < 0 else -1
    out = list(subj)
    for i in range(len(clip)):
        a, b = clip[i - 1], clip[i]
        inp, out = out, []
        if not inp:
            break
        for j in range(len(inp)):
            p, q = inp[j - 1], inp[j]
            if dentro(q, a, b, s):
                if not dentro(p, a, b, s):
                    out.append(incrocio(p, q, a, b))
                out.append(q)
            elif dentro(p, a, b, s):
                out.append(incrocio(p, q, a, b))
    return out


def sovrapposizione(p: Pezzo, G: Guscio, pieghe: set) -> float:
    """Area in cui due facce del pezzo non vicine si coprono nello sviluppo (> 0: il pezzo non si taglia così)."""
    vicine = set()
    for key in pieghe:
        f, g = G.spigoli[key]['facce']
        vicine.add(frozenset((f, g)))
    tot = 0.0
    fs = list(p.poligoni)
    for i in range(len(fs)):
        for j in range(i + 1, len(fs)):
            if frozenset((fs[i], fs[j])) in vicine:
                continue
            x = _clip(p.poligoni[fs[i]], p.poligoni[fs[j]])
            if len(x) >= 3:
                tot += _area2(x)
    return tot


def ingombro_minimo(punti) -> tuple[float, float, float]:
    """Il rettangolo più piccolo che contiene i punti (pinze rotanti sul guscio convesso): (lato corto, lungo, angolo)."""
    pts = sorted(set((round(x, 6), round(y, 6)) for x, y in punti))
    if len(pts) < 3:
        return (0.0, 0.0, 0.0)

    def giro(lst):
        h = []
        for q in lst:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (q[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(q)
        return h
    hull = giro(pts)[:-1] + giro(pts[::-1])[:-1]
    best = None
    for i in range(len(hull)):
        a, b = hull[i - 1], hull[i]
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        c, s = math.cos(-ang), math.sin(-ang)
        xs = [q[0] * c - q[1] * s for q in hull]
        ys = [q[0] * s + q[1] * c for q in hull]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if best is None or w * h < best[0] * best[1]:
            best = (w, h, ang)
    w, h, ang = best
    return (min(w, h), max(w, h), math.degrees(ang))


def sta_nel_foglio(p: Pezzo, foglio) -> bool:
    corto, lungo, _ = ingombro_minimo(p.punti())
    return corto <= min(foglio) + 1e-6 and lungo <= max(foglio) + 1e-6


# ============================================================================ proposta automatica
def proponi(G: Guscio, tec: Tecnologia, foglio=(1500, 3000), forzati: dict | None = None) -> set:
    """Le pieghe: più possibile finché ogni pezzo sta nel foglio e non si sovrappone a sé stesso. Si provano più
    ordini (spigoli più lunghi prima; prima i giri orizzontali; prima gli spigoli d'angolo) e vince quello con meno
    metri di saldatura, a parità con meno pezzi. forzati: {spigolo: 'piega' | 'saldatura'} scelti dall'utente."""
    ordini = [lambda k: -G.spigoli[k]['lung'],
              lambda k: (0 if k.startswith('giro') else 1, -G.spigoli[k]['lung']),
              lambda k: (0 if k.startswith('lato') else 1, -G.spigoli[k]['lung'])]
    migliore = None
    for chiave in ordini:
        pieghe = _proponi(G, tec, foglio, forzati, chiave)
        sald = metri_saldatura(G, pieghe)[0]
        npezzi = len(G.facce) - len(pieghe)
        if migliore is None or (round(sald, 3), npezzi) < migliore[0]:
            migliore = ((round(sald, 3), npezzi), pieghe)
    return migliore[1]


def _proponi(G, tec, foglio, forzati, chiave) -> set:
    forzati = forzati or {}
    padre = list(range(len(G.facce)))

    def radice(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x
    pieghe = set()
    candidati = [k for k, s in G.spigoli.items() if s['angolo'] >= COMPLANARI and forzati.get(k) != 'saldatura']
    obbligate = [k for k in candidati if forzati.get(k) == 'piega']
    libere = sorted((k for k in candidati if k not in obbligate), key=chiave)
    for k in obbligate + libere:
        f, g = G.spigoli[k]['facce']
        rf, rg = radice(f), radice(g)
        if rf == rg:
            continue                                       # chiuderebbe un giro di pieghe
        prova = pieghe | {k}
        facce = [x for x in range(len(G.facce)) if radice(x) in (rf, rg)]
        try:
            p = sviluppa_pezzo(G, facce, prova, tec)
        except FeatureError:
            continue
        if k not in obbligate and (not sta_nel_foglio(p, foglio) or sovrapposizione(p, G, prova) > 1.0):
            continue
        pieghe = prova
        padre[rf] = rg
    return pieghe


def pezzi(G: Guscio, pieghe: set, tec: Tecnologia) -> list[Pezzo]:
    """I pezzi: gruppi di facce unite da pieghe, sviluppati. Nomi A, B, C… dal più grande."""
    padre = list(range(len(G.facce)))

    def radice(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x
    for k in pieghe:
        f, g = G.spigoli[k]['facce']
        padre[radice(f)] = radice(g)
    gruppi = {}
    for f in range(len(G.facce)):
        gruppi.setdefault(radice(f), []).append(f)
    out = [sviluppa_pezzo(G, fs, {k for k in pieghe if all(x in fs for x in G.spigoli[k]['facce'])}, tec)
           for fs in gruppi.values()]
    out.sort(key=lambda p: -sum(_area2(q) for q in p.poligoni.values()))
    for i, p in enumerate(out):
        p.nome = chr(ord('A') + i)
    return out


def metri_saldatura(G: Guscio, pieghe: set) -> tuple[float, float]:
    """(saldature tra facce inclinate, giunti degli angoli dei bordi complanari), in metri."""
    sald = sum(s['lung'] for k, s in G.spigoli.items() if k not in pieghe and s['angolo'] >= COMPLANARI)
    giunti = sum(s['lung'] for k, s in G.spigoli.items() if k not in pieghe and s['angolo'] < COMPLANARI)
    return sald / 1000, giunti / 1000


def come_facce(G: Guscio) -> Facce:
    return Facce(G.punti, G.facce)


# ============================================================================ dentro SteelCAD (feature sheet_shape)
DIVISIONI = {'auto': 'automatica (meno saldature)', 'verticali': 'pieghe sugli spigoli verticali (cassone a fascia)',
             'tramoggia': 'pieghe sugli spigoli della tramoggia', 'lati': 'un pezzo per lato'}


def _forzati_divisione(G: Guscio, divisione: str) -> dict:
    """La strategia di divisione come scelte forzate: quali spigoli d'angolo restano saldati."""
    salda = {'verticali': ('tramoggia',), 'tramoggia': ('cassone',), 'lati': ('tramoggia', 'cassone')}.get(divisione, ())
    lati = [k for k in G.spigoli if k.startswith('lato:')]
    n = 1 + max((int(k.split(':')[2]) for k in lati), default=0)
    # angoli smussati (8 facce per giro, le smussature in posizione pari): ogni smussatura resta piegata sul lato dopo e
    # si salda solo al lato prima. Saldando tutto, le smussature diventavano pezzi a sé, strisce di 2 mm (23/10)
    return {k: 'saldatura' for k in lati if k.split(':')[1] in salda and (n != 8 or int(k.split(':')[2]) % 2 == 1)}


def _superficie_media(G: Guscio, t: float, rif: str) -> Facce:
    """La superficie in asse lamiera (per il solido): i vertici spostati di t/2 dalle facce attorno, verso il materiale."""
    import numpy as np
    if rif == 'asse':
        return Facce(G.punti, G.facce)
    segno = -1.0 if rif == 'esterno' else 1.0
    P = np.array(G.punti, dtype=float)
    vicine = [[] for _ in G.punti]
    for f in G.facce:
        n = np.array(_normale(G.punti, f))
        for i in f:
            vicine[i].append(n)
    nuovi = P.copy()
    for i, ns in enumerate(vicine):
        if not ns:
            continue
        N = np.unique(np.round(np.array(ns), 9), axis=0)
        off = np.linalg.lstsq(N, np.ones(len(N)), rcond=None)[0] * (t / 2)
        if np.linalg.norm(off) > 3 * t:                    # facce quasi parallele: la media basta
            m = N.sum(axis=0)
            off = m / np.linalg.norm(m) * (t / 2)
        nuovi[i] = P[i] + segno * off
    return Facce([tuple(map(float, q)) for q in nuovi], G.facce)


def _piani_medi(G: Guscio, t: float, rif: str) -> list:
    """Per ogni faccia il suo piano in asse lamiera esatto: (normale, n·x)."""
    sposta = {'esterno': -t / 2, 'interno': t / 2, 'asse': 0.0}.get(rif, -t / 2)
    out = []
    for f in G.facce:
        n = _normale(G.punti, f)
        q = G.punti[f[0]]
        out.append((tuple(n), sum(n[k] * q[k] for k in range(3)) + sposta))
    return out


def _solido_a_facce(S: Facce, t: float):
    """Il solido faccia per faccia: ogni faccia (in asse lamiera) ispessita di t, poi tutte fuse. Più lento della
    cucitura delle pelli, ma regge i vertici dove si incontrano tante facce (angoli aperti, smussi, flange)."""
    import build123d as bd

    from .shapes import _faccia_piana
    prismi, perse = [], 0
    for f in S.facce:
        n = _normale(S.punti, f)
        pts = [tuple(S.punti[i][q] - n[q] * t / 2 for q in range(3)) for i in f]
        # spostati a metà spessore i vertici di una faccia possono non stare più su un piano (scarico spostato: le
        # falde davanti e dietro): si riportano sul piano medio della faccia. Prima la faccia falliva e si perdeva
        # in silenzio: nel 3D mancavano due lati, lo sviluppo li aveva (20/10)
        c = [sum(q[k] for q in pts) / len(pts) for k in range(3)]
        pts = [tuple(q[k] - sum((q[j] - c[j]) * n[j] for j in range(3)) * n[k] for k in range(3)) for q in pts]
        try:
            prismi.append(bd.extrude(bd.Face(_faccia_piana(pts)), amount=t, dir=n))
        except Exception:  # noqa: BLE001
            perse += 1
    if not prismi:
        raise FeatureError('Non riesco a fare il solido della forma.')
    if perse:
        raise FeatureError(f'Il 3D della forma resta senza {perse} {"faccia" if perse == 1 else "facce"}: non le so '
                           'costruire (lo sviluppo c’è). Cambia di poco le misure o scrivimi il caso.')
    tutto = prismi[0].fuse(*prismi[1:]) if len(prismi) > 1 else prismi[0]
    return tutto.clean() if hasattr(tutto, 'clean') else tutto


def costruisci(fdef: dict, valuta, t: float, r, k, fid: str):
    """Dalla definizione (sezioni, fasce, scelte) al solido, allo sviluppo dei pezzi e alla tabella pieghe."""
    import build123d as bd

    from ..units import fmt_mm
    from .shapes import _faccia_piana, _pulisci_contorno, _solido
    sez = []
    for i, d in enumerate(fdef.get('sezioni') or []):
        q = lambda key, cosa, dflt=0: valuta(d.get(key, dflt), f'{cosa} della sezione {i + 1}')  # noqa: E731
        sez.append(Sezione(q('w', 'la larghezza'), q('d', 'la profondità'), q('z', 'la quota'), q('ex', 'lo spostamento X'),
                           q('ey', 'lo spostamento Y'), q('smusso', 'lo smusso'), d.get('nome', '')))
    fasce = list(fdef.get('fasce') or [])
    aperte = {i for i, nome in enumerate(fasce) if nome in (fdef.get('aperte') or [])}
    try:
        G = guscio_da_sezioni(sez, fasce, aperte)
    except FeatureError as ex:
        ex.feature = fid
        raise
    foglio = tuple(valuta(x, 'il foglio') for x in (fdef.get('foglio') or [1500, 3000]))
    if min(foglio) <= 0:
        raise FeatureError('Il formato del foglio va scritto con due misure maggiori di zero.', feature=fid)
    tec = Tecnologia(t, r, k, fdef.get('ref', 'esterno'))
    divisione = fdef.get('divisione', 'auto')
    if divisione not in DIVISIONI:
        raise FeatureError(f'Divisione "{divisione}" sconosciuta.', feature=fid)
    scelte = dict(fdef.get('spigoli') or {})
    forzati = {**_forzati_divisione(G, divisione), **{kk: vv for kk, vv in scelte.items() if kk in G.spigoli}}
    pieghe = proponi(G, tec, foglio, forzati)
    try:
        ps = pezzi(G, pieghe, tec)
    except FeatureError as ex:
        ex.feature = fid
        raise
    avvisi = []
    if r is None or k is None:
        avvisi.append('Raggio e K non impostati: lo sviluppo è senza correzione di piega.')
    # lo sviluppo: ogni pezzo con il lato lungo in orizzontale, in fila con 100 mm tra uno e l'altro
    facce_flat, linee, righe, info_pezzi = [], [], [], []
    x = 0.0
    corr_tot = 0.0
    mappe = []
    schegge, strette = [], []                    # pezzi e facce troppo stretti (smussi piccoli, 28/10)
    for p in ps:
        corto, lungo, ang = ingombro_minimo(p.punti())
        c, s = math.cos(math.radians(-ang)), math.sin(math.radians(-ang))

        def rot1(q, c=c, s=s):
            return (q[0] * c - q[1] * s, q[0] * s + q[1] * c)
        rot = rot1
        pts = [rot(q) for q in p.punti()]
        if max(q[1] for q in pts) - min(q[1] for q in pts) > max(q[0] for q in pts) - min(q[0] for q in pts) + 1e-6:
            def rot(q, rot1=rot1):
                w = rot1(q)
                return (-w[1], w[0])
            pts = [rot(q) for q in p.punti()]
        mx, my = min(q[0] for q in pts), min(q[1] for q in pts)

        def sp(q, rot=rot, mx=mx, my=my, x=x):
            w = rot(q)
            return (w[0] - mx + x, w[1] - my)
        def faccia(pts):
            # tutte con lo stesso verso (antiorario): facce con versi opposti non si fondono
            if sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1] for i in range(len(pts))) > 0:
                pts = pts[::-1]
            return bd.Face(_faccia_piana(pts))
        pezzi_f = [faccia([sp(q) for q in poly]) for poly in p.poligoni.values() if len(poly) >= 3]
        for q in p.pieghe:
            if q['corr'] > 1e-9:
                A2, B2, A3, B3 = q['striscia']
                pezzi_f.append(faccia([sp(A2), sp(B2), sp(B3), sp(A3)]))
        unione = pezzi_f[0].fuse(*pezzi_f[1:]).clean() if len(pezzi_f) > 1 else pezzi_f[0]
        parti = unione.faces() if not isinstance(unione, bd.Face) else [unione]
        if len(parti) > 1:
            avvisi.append(f'Il pezzo {p.nome} nello sviluppo è venuto staccato in {len(parti)} parti: controlla le pieghe.')
        facce_flat += [_pulisci_contorno(f) for f in parti]
        for f in p.facce:                    # tre vertici di ogni faccia: sul pezzo e nello sviluppo (per disegnarci)
            vs = G.facce[f][:3]
            mappe.append({'faccia': f, 'nome': G.nomi[f], 'pts3': [G.punti[v] for v in vs],
                          'pts2': [sp(p.vertici[f][v]) for v in vs], 'normale': _normale(G.punti, G.facce[f]),
                          'poly3': [G.punti[v] for v in G.facce[f]]})
        for i, q in enumerate(p.pieghe, 1):
            a, b = sp(q['a']), sp(q['b'])
            nome = f'{p.nome}{i}'
            linee.append((a, b, f'{nome} {fmt_mm(round(q["angolo"], 1))}° {q["verso"]}'))
            corr = q['corr'] if r is not None and k is not None else None
            corr_tot += corr or 0.0
            righe.append({'n': nome, 'label': nome, 'angle': q['angolo'], 'length': q['lung'], 'correction': corr,
                          'verso': q['verso'], 'pezzo': p.nome})
        sov = sovrapposizione(p, G, {qq['spigolo'] for qq in p.pieghe})
        nel = corto <= min(foglio) + 1e-6 and lungo <= max(foglio) + 1e-6
        if not nel:
            avvisi.append(f'Il pezzo {p.nome} ({fmt_mm(round(corto))} × {fmt_mm(round(lungo))}) non sta nel foglio '
                          f'{fmt_mm(min(foglio))} × {fmt_mm(max(foglio))}: salda uno spigolo in più.')
        if sov > 1.0:
            avvisi.append(f'Nello sviluppo del pezzo {p.nome} delle facce si sovrappongono ({fmt_mm(round(sov))} mm²): '
                          'scegli un’altra saldatura.')
        # 28/10: le schegge (smussi piccoli): un pezzo largo pochi mm non si taglia bene, una faccia stretta tra due
        # pieghe non si piega (la cava della matrice è 8 volte lo spessore: servono almeno 4 spessori per lato)
        minimo = 4 * t
        if corto < minimo:
            schegge.append((p.nome, corto))
        else:
            piegate: dict = {}
            for qq in p.pieghe:
                for ff in G.spigoli[qq['spigolo']]['facce']:
                    piegate[ff] = piegate.get(ff, 0) + 1
            for ff, n in piegate.items():
                if n >= 2 and ff in p.poligoni and len(p.poligoni[ff]) >= 3:
                    largo = ingombro_minimo(p.poligoni[ff])[0]
                    if largo < minimo:
                        strette.append((G.nomi[ff], largo))
        info_pezzi.append({'nome': p.nome, 'facce': [G.nomi[f] for f in p.facce], 'pieghe': len(p.pieghe),
                           'ingombro': [round(corto, 1), round(lungo, 1)], 'nel_foglio': nel})
        x += max(q[0] for q in pts) - mx + 100
    if schegge or strette:
        cosa = []
        if strette:
            cosa.append(f'{len(strette)} {"faccia larga" if len(strette) == 1 else "facce larghe"} '
                        f'{fmt_mm(round(min(x for _, x in strette), 1))} mm tra due pieghe (non si piegano: ne servono almeno '
                        f'{fmt_mm(round(4 * t))})')
        if schegge:
            cosa.append(f'{len(schegge)} {"pezzo" if len(schegge) == 1 else "pezzi"} a scheggia, larghi '
                        f'{fmt_mm(round(min(x for _, x in schegge), 1))} mm ({", ".join(n for n, _ in schegge)})')
        avvisi.append('Smusso troppo piccolo: ' + ' e '.join(cosa) + '. Toglilo (0 = angolo vivo) o fallo di almeno '
                      f'{fmt_mm(math.ceil(4 * t / math.sqrt(2)))} mm.')
    flat = facce_flat[0] if len(facce_flat) == 1 else bd.Compound(children=facce_flat)
    sald, giunti = metri_saldatura(G, pieghe)
    spigoli = [{'key': kk, 'nome': s_['nome'], 'lung': round(s_['lung'], 1), 'angolo': round(s_['angolo'], 2),
                'scelta': 'piega' if kk in pieghe else ('taglio' if s_['angolo'] < COMPLANARI else 'saldatura'),
                'scelto_da': 'te' if kk in scelte else ('divisione' if kk in forzati else 'proposta')}
               for kk, s_ in sorted(G.spigoli.items(), key=lambda it: it[0])]
    media = _superficie_media(G, t, tec.rif)
    area = sum(_area3(G, f) for f in range(len(G.facce)))
    try:
        solido = _solido(media, t, _piani_medi(G, t, tec.rif))
        buono = solido.is_valid and abs(abs(solido.volume) - area * t) < 0.08 * area * t
    except Exception:  # noqa: BLE001
        buono = False
    if not buono:
        solido = _solido_a_facce(media, t)
    info = {'pieghe': len(righe), 'angolo_max': max((x_['angle'] for x_ in righe), default=0.0),
            'correzione_totale': corr_tot, 'avvisi': avvisi, 'pezzi': info_pezzi, 'saldature_m': round(sald, 3),
            'giunti_m': round(giunti, 3), 'spigoli': spigoli, 'divisione': divisione, 'foglio': list(foglio),
            'mappe': mappe, 'rif': tec.rif}
    return solido, flat, linee, righe, info, fdef.get('name') or 'Forma da sezioni'


__all__ = ['Sezione', 'Guscio', 'guscio_da_sezioni', 'Tecnologia', 'Pezzo', 'sviluppa_pezzo', 'proponi', 'pezzi',
           'sovrapposizione', 'ingombro_minimo', 'sta_nel_foglio', 'metri_saldatura', 'come_facce', '_contorno']
