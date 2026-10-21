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
