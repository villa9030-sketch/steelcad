"""Testi da marcare col laser: lettere a tratto singolo (linee aperte, non contorni), una passata sola.

Il carattere è Relief SingleLine (licenza SIL OFL, viene con build123d): ogni lettera è fatta di tratti aperti
(la «A» sono due tratti, la «O» un giro). Nel file i tratti hanno un «chiudi» finto che qui non si segue.
L'altezza data è quella delle maiuscole e delle cifre.
"""
from __future__ import annotations

import glob
import math
import os
from functools import lru_cache

import build123d as bd

PASSI_CURVA = 6                     # segmenti per ogni pezzo di curva


def _font_path() -> str:
    cand = glob.glob(os.path.join(os.path.dirname(bd.__file__), 'data', 'fonts', 'reliefsingleline', '*.ttf'))
    if not cand:
        raise FileNotFoundError('Manca il carattere per la marcatura (Relief SingleLine).')
    return cand[0]


@lru_cache(maxsize=1)
def _font():
    import logging

    from fontTools.ttLib import TTFont
    logging.getLogger('fontTools').setLevel(logging.ERROR)        # il file ha una tabella dei nomi un po' storta
    f = TTFont(_font_path())
    alto = getattr(f['OS/2'], 'sCapHeight', 0) or 675
    return f, f.getGlyphSet(), f.getBestCmap(), f['hmtx'], float(alto)


@lru_cache(maxsize=512)
def _glifo(ch: str) -> tuple:
    """I tratti di una lettera (unità del carattere) e quanto avanza."""
    from fontTools.pens.basePen import BasePen
    f, gs, cmap, hmtx, _ = _font()
    nome = cmap.get(ord(ch)) or cmap.get(ord('?'))
    if nome is None:
        return (), 500

    class Penna(BasePen):
        def __init__(self, gs):
            super().__init__(gs)
            self.tratti, self.cur = [], None

        def _moveTo(self, p):
            self._chiudi()
            self.cur = [p]

        def _lineTo(self, p):
            self.cur.append(p)

        def _qCurveToOne(self, p1, p2):
            p0 = self.cur[-1]
            for i in range(1, PASSI_CURVA + 1):
                t = i / PASSI_CURVA
                self.cur.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                                 (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]))

        def _curveToOne(self, p1, p2, p3):
            p0 = self.cur[-1]
            for i in range(1, PASSI_CURVA + 1):
                t = i / PASSI_CURVA
                a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
                self.cur.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))

        def _closePath(self):
            self._chiudi()                         # tratto singolo: non si torna al punto di partenza

        def _endPath(self):
            self._chiudi()

        def _chiudi(self):
            if self.cur and len(self.cur) > 1:
                self.tratti.append(tuple(self.cur))
            self.cur = None

    pen = Penna(gs)
    gs[nome].draw(pen)
    pen._chiudi()
    return tuple(pen.tratti), hmtx[nome][0]


def tratti(testo: str, h: float, x: float = 0.0, y: float = 0.0, angolo: float = 0.0) -> list:
    """Le polilinee del testo: alto h (maiuscole), il punto (x, y) in basso a sinistra, ruotato di angolo°.
    Più righe con «\\n» (interlinea 1,6 h)."""
    *_, alto = _font()
    k = h / alto
    ca, sa = math.cos(math.radians(angolo)), math.sin(math.radians(angolo))
    out = []
    for r, riga in enumerate(str(testo).split('\n')):
        avanti = 0.0
        y0 = -r * 1.6 * h
        for ch in riga:
            glifo, larg = _glifo(ch)
            for t in glifo:
                pts = []
                for gx, gy in t:
                    u, v = avanti + gx * k, y0 + gy * k
                    pts.append((x + u * ca - v * sa, y + u * sa + v * ca))
                out.append(pts)
            avanti += larg * k
    return out


def larghezza(testo: str, h: float) -> float:
    *_, alto = _font()
    return max((sum(_glifo(ch)[1] for ch in riga) for riga in str(testo).split('\n')), default=0) * h / alto


# ============================================================================ testi da tagliare (stencil)
# 22/10: lettere a contorno chiuso, tagliate attraverso la lamiera. Caratteri stencil (licenza SIL OFL, nella cartella
# cad_engine/fonts): le isole di O, A, B, R, 0, 8… restano attaccate coi ponticelli, non cadono.
STENCIL = {'saira': ('Saira Stencil One', 'SairaStencilOne-Regular.ttf'),
           'allerta': ('Allerta Stencil', 'AllertaStencil-Regular.ttf')}


@lru_cache(maxsize=4)
def _font_stencil(nome: str):
    import logging

    from fontTools.ttLib import TTFont
    if nome not in STENCIL:
        raise ValueError(f'Carattere «{nome}» sconosciuto.')
    logging.getLogger('fontTools').setLevel(logging.ERROR)
    f = TTFont(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'fonts', STENCIL[nome][1]))
    alto = getattr(f['OS/2'], 'sCapHeight', 0) or 0.7 * f['head'].unitsPerEm
    return f, f.getGlyphSet(), f.getBestCmap(), f['hmtx'], float(alto)


@lru_cache(maxsize=1024)
def _glifo_stencil(nome: str, ch: str) -> tuple:
    """I contorni chiusi di una lettera (unità del carattere) come pezzi del carattere, ('L', p0, p1),
    ('Q', p0, p1, p2) o ('C', p0, p1, p2, p3), e quanto avanza."""
    from fontTools.pens.basePen import BasePen
    f, gs, cmap, hmtx, _ = _font_stencil(nome)
    g = cmap.get(ord(ch)) or cmap.get(ord('?'))
    if g is None:
        return (), 500

    class Penna(BasePen):
        def __init__(self, gs):
            super().__init__(gs)
            self.giri, self.cur, self.p = [], None, None

        def _moveTo(self, p):
            self._chiudi()
            self.cur, self.p = [], p

        def _aggiungi(self, pezzo):
            if math.dist(pezzo[1], pezzo[-1]) > 1e-6 or len(pezzo) > 3:
                self.cur.append(pezzo)
            self.p = pezzo[-1]

        def _lineTo(self, p):
            self._aggiungi(('L', self.p, p))

        def _qCurveToOne(self, p1, p2):
            self._aggiungi(('Q', self.p, p1, p2))

        def _curveToOne(self, p1, p2, p3):
            self._aggiungi(('C', self.p, p1, p2, p3))

        def _closePath(self):
            self._chiudi()

        def _endPath(self):
            self._chiudi()

        def _chiudi(self):
            if self.cur:
                if math.dist(self.cur[0][1], self.cur[-1][-1]) > 1e-6:
                    self.cur.append(('L', self.cur[-1][-1], self.cur[0][1]))
                if len(self.cur) > 1:
                    self.giri.append(tuple(self.cur))
            self.cur = None

    pen = Penna(gs)
    gs[g].draw(pen)
    pen._chiudi()
    return tuple(pen.giri), hmtx[g][0]


# 02/11 («non riesci a raggiare tutto anziché avere migliaia di tratti?»): le curve delle lettere tagliate diventano
# archi veri, non più tanti trattini. Pezzo più leggero (meno facce), taglio più pulito, DXF senza microsegmenti.
TOLL_ARCO = 0.01                    # mm: quanto un arco può scostarsi dalla curva del carattere
CORTO = 0.02                        # mm: un pezzo più corto si unisce al vicino


def _bezier(pezzo):
    """La curva del pezzo come funzione di t (0..1)."""
    k, *p = pezzo
    if k == 'L':
        return lambda t: (p[0][0] + (p[1][0] - p[0][0]) * t, p[0][1] + (p[1][1] - p[0][1]) * t)
    if k == 'Q':
        return lambda t: tuple((1 - t) ** 2 * p[0][i] + 2 * (1 - t) * t * p[1][i] + t * t * p[2][i] for i in (0, 1))
    return lambda t: tuple((1 - t) ** 3 * p[0][i] + 3 * (1 - t) ** 2 * t * p[1][i] + 3 * (1 - t) * t * t * p[2][i]
                           + t ** 3 * p[3][i] for i in (0, 1))


def _centro(a, m, b):
    """Il centro del cerchio per tre punti (None se sono in fila)."""
    d = 2 * (a[0] * (m[1] - b[1]) + m[0] * (b[1] - a[1]) + b[0] * (a[1] - m[1]))
    if abs(d) < 1e-12:
        return None
    a2, m2, b2 = a[0] ** 2 + a[1] ** 2, m[0] ** 2 + m[1] ** 2, b[0] ** 2 + b[1] ** 2
    return ((a2 * (m[1] - b[1]) + m2 * (b[1] - a[1]) + b2 * (a[1] - m[1])) / d,
            (a2 * (b[0] - m[0]) + m2 * (a[0] - b[0]) + b2 * (m[0] - a[0])) / d)


def _dalla_retta(p, a, b):
    lung = math.dist(a, b)
    if lung < 1e-12:
        return math.dist(p, a)
    return abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / lung


def _archi(f, t0, t1, toll, prof=0) -> list:
    """Linee e archi che seguono la curva f tra t0 e t1 entro toll."""
    a, m, b = f(t0), f((t0 + t1) / 2), f(t1)
    prove = [f(t0 + (t1 - t0) * i / 8) for i in (1, 2, 3, 5, 6, 7)] + [m]
    if max(_dalla_retta(p, a, b) for p in prove) <= toll:
        return [('L', a, b)]
    c = _centro(a, m, b)
    if c is not None:
        r = math.dist(c, a)
        if max(abs(math.dist(p, c) - r) for p in prove) <= toll:
            return [('A', a, m, b)]
    if prof > 10:
        return [('L', a, m), ('L', m, b)]
    return _archi(f, t0, (t0 + t1) / 2, toll, prof + 1) + _archi(f, (t0 + t1) / 2, t1, toll, prof + 1)


def _unisci_corti(giro: list) -> list:
    """Toglie i pezzi più corti di CORTO: il pezzo dopo parte dove partiva quello tolto."""
    giro = list(giro)
    i = 0
    while len(giro) > 2 and i < len(giro):
        if math.dist(giro[i][1], giro[i][-1]) >= CORTO:
            i += 1
            continue
        inizio = giro[i][1]
        del giro[i]
        j = i % len(giro)
        k, _, *resto = giro[j]
        if k == 'A' and _dalla_retta(resto[0], inizio, resto[-1]) < TOLL_ARCO:
            giro[j] = ('L', inizio, resto[-1])
        else:
            giro[j] = (k, inizio, *resto)
    return giro


def _punti_arco(a, m, b) -> list:
    """Punti lungo l'arco per a, m, b (a compreso, b escluso): un punto ogni 10°."""
    c = _centro(a, m, b)
    if c is None:
        return [a]
    r = math.dist(c, a)
    ta, tm, tb = (math.atan2(q[1] - c[1], q[0] - c[0]) for q in (a, m, b))
    giro = (tb - ta) % (2 * math.pi)
    verso = 1 if (tm - ta) % (2 * math.pi) < giro else -1
    ampiezza = giro if verso > 0 else 2 * math.pi - giro
    n = max(2, math.ceil(math.degrees(ampiezza) / 10))
    return [(c[0] + r * math.cos(ta + verso * ampiezza * i / n), c[1] + r * math.sin(ta + verso * ampiezza * i / n))
            for i in range(n)]


@lru_cache(maxsize=256)
def contorni_curve(testo: str, h: float, x: float = 0.0, y: float = 0.0, angolo: float = 0.0,
                   font: str = 'saira') -> tuple:
    """I contorni chiusi del testo da tagliare, in linee e archi: ogni contorno è una lista di ('L', a, b) e
    ('A', a, m, b) (m un punto a metà arco), uno di seguito all'altro."""
    *_, alto = _font_stencil(font)
    k = h / alto
    ca, sa = math.cos(math.radians(angolo)), math.sin(math.radians(angolo))
    out = []
    for r, riga in enumerate(str(testo).split('\n')):
        avanti = 0.0
        y0 = -r * 1.6 * h
        sposta = lambda q: (x + (avanti + q[0] * k) * ca - (y0 + q[1] * k) * sa,  # noqa: E731
                            y + (avanti + q[0] * k) * sa + (y0 + q[1] * k) * ca)
        for ch in riga:
            giri, larg = _glifo_stencil(font, ch)
            for gr in giri:
                pezzi = []
                for pz in gr:
                    pp = (pz[0], *[sposta(q) for q in pz[1:]])
                    pezzi += [('L', pp[1], pp[2])] if pz[0] == 'L' else _archi(_bezier(pp), 0.0, 1.0, TOLL_ARCO)
                # i pezzi uno attaccato all'altro esattamente (la curva rifatta può sbagliare di un'inezia)
                pezzi = [(pz[0], pezzi[i - 1][-1] if i else pezzi[-1][-1], *pz[2:]) for i, pz in enumerate(pezzi)]
                pezzi = _unisci_corti(pezzi)
                if len(pezzi) > 1:
                    out.append(tuple(pezzi))
            avanti += larg * k
    return tuple(out)


def contorni(testo: str, h: float, x: float = 0.0, y: float = 0.0, angolo: float = 0.0, font: str = 'saira') -> list:
    """I contorni chiusi del testo da tagliare come punti (senza ripetere il primo), per disegnarli."""
    out = []
    for giro in contorni_curve(testo, h, x, y, angolo, font):
        pts = []
        for pz in giro:
            pts += [pz[1]] if pz[0] == 'L' else _punti_arco(*pz[1:])
        out.append(pts)
    return out


def larghezza_stencil(testo: str, h: float, font: str = 'saira') -> float:
    *_, alto = _font_stencil(font)
    return max((sum(_glifo_stencil(font, ch)[1] for ch in riga) for riga in str(testo).split('\n')), default=0) * h / alto


def origine(e: dict, x: float, y: float) -> tuple:
    """Il punto in basso a sinistra da cui si scrive il testo ``e``. Un testo centrato (30/10, «che fatica centrare
    una scritta in un foro») ha (x, y) al centro: in larghezza e in altezza delle maiuscole, anche girato."""
    if not e.get('centrato'):
        return x, y
    h = float(e['h'])
    # il centro del disegno vero delle lettere (non della larghezza col passo dell'ultima lettera)
    tr = contorni(e['text'], h, 0, 0, 0, e['stencil']) if e.get('stencil') else tratti(e['text'], h, 0, 0, 0)
    xs = [q[0] for t in tr for q in t]
    if not xs:
        return x, y
    n = len(str(e['text']).split(chr(10)))
    u = -(min(xs) + max(xs)) / 2
    v = -(h - (n - 1) * 1.6 * h) / 2                  # in altezza: le maiuscole (le code di g, p… non spostano)
    ca, sa = math.cos(math.radians(e.get('angle', 0))), math.sin(math.radians(e.get('angle', 0)))
    return x + u * ca - v * sa, y + u * sa + v * ca
