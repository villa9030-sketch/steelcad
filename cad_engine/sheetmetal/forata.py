"""Lamiera forata (05/11, idea presa da SolidCraft «sheet.perforate»): un campo di fori su una faccia piana.

Definizione (feature "sheet_perforate"):

    {"id": "LF1", "type": "sheet_perforate", "name": "Lamiera forata",
     "face": "SM1/sopra",            # la faccia piana (base sopra/sotto, flangia esterno/interno, faccia di una forma)
     "sketch": null,                 # oppure uno sketch su quella faccia: i fori solo dentro i suoi contorni chiusi
     "forma": "tondo",               # tondo (d) | asola (lung × larg, "verticale") | quadro (lato)
     "d": 5, "lung": 20, "larg": 5, "lato": 5, "verticale": false,
     "px": 8, "py": 8,               # passo in orizzontale e in verticale (sulla faccia vista di fronte)
     "disposizione": "sfalsata",     # fila | sfalsata (60°: le file a px · √3/2, una sì e una no spostate di mezzo passo)
     "margine": 10}                  # dai bordi e dalle pieghe (sulla zona dello sketch: dal bordo della faccia)

Come la pensa l'officina: la serie si centra nella zona (margini uguali di qua e di là), si fanno solo fori interi:
un foro che toccherebbe un bordo, una piega, un foro che c'è già o il margine non si fa. Il numero dei fori fatti si
legge nell'albero e nel pannello.

Le coordinate sono quelle della faccia vista di fronte (le stesse di uno sketch su quella faccia: x a destra, y in su).
Il taglio è uno solo, con tutti i fori insieme, nel pezzo piegato e nello sviluppo: anche sulle flange, lo sviluppo
ha i fori nel posto giusto (stesse coordinate locali, come per i tagli disegnati sulle facce).
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

import build123d as bd

from ..errors import FeatureError
from ..units import fmt_mm

FORME = ('tondo', 'asola', 'quadro')
DISPOSIZIONI = ('fila', 'sfalsata')
MAX_FORI = 20000             # oltre, il passo è sbagliato (un passo da 1 su un metro quadro): si dice, non si prova
S60 = math.sqrt(3) / 2


@dataclass
class Foro:
    """La forma di un foro intorno al suo centro: il «nocciolo» (un punto, un segmento, un quadrato) e quanto ci si
    allarga intorno (rho). Così la distanza da un bordo si misura sempre allo stesso modo."""
    forma: str
    a: float                 # tondo: diametro; asola: lunghezza fuori tutto; quadro: lato
    b: float = 0.0           # asola: larghezza (diametro delle teste)
    verticale: bool = False

    @property
    def rho(self) -> float:
        return self.a / 2 if self.forma == 'tondo' else self.b / 2 if self.forma == 'asola' else 0.0

    def mezzi(self) -> tuple[float, float]:
        """Mezzo ingombro in x e in y."""
        if self.forma == 'asola':
            return (self.b / 2, self.a / 2) if self.verticale else (self.a / 2, self.b / 2)
        return self.a / 2, self.a / 2

    def nocciolo(self, x: float, y: float) -> list:
        """I tratti del nocciolo intorno a (x, y): [(ax, ay, bx, by)]."""
        if self.forma == 'tondo':
            return [(x, y, x, y)]
        if self.forma == 'asola':
            h = (self.a - self.b) / 2
            return [(x, y - h, x, y + h)] if self.verticale else [(x - h, y, x + h, y)]
        h = self.a / 2
        p = [(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)]
        return [(*p[i], *p[(i + 1) % 4]) for i in range(4)]

    def contorno(self, x: float, y: float, n: int = 20) -> list:
        """Il contorno del foro come polilinea chiusa (per l'anteprima): [(x, y), ...]."""
        if self.forma == 'tondo':
            r = self.a / 2
            return [(x + r * math.cos(2 * math.pi * k / n), y + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        if self.forma == 'quadro':
            h = self.a / 2
            return [(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)]
        r, h = self.b / 2, (self.a - self.b) / 2
        m = max(4, n // 2)
        meta = [(h + r * math.cos(-math.pi / 2 + math.pi * k / m), r * math.sin(-math.pi / 2 + math.pi * k / m)) for k in range(m + 1)]
        giro = meta + [(-u, -v) for u, v in meta]
        return [(x - v, y + u) if self.verticale else (x + u, y + v) for u, v in giro]

    def testo(self) -> str:
        if self.forma == 'tondo':
            return f'Ø{fmt_mm(round(self.a, 2))}'
        if self.forma == 'asola':
            return f'asole {fmt_mm(round(self.a, 2))} × {fmt_mm(round(self.b, 2))}'
        return f'quadri {fmt_mm(round(self.a, 2))}'


# ------------------------------------------------------------------------------------------- conti in piano
def _dist_ps(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll <= 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _si_tagliano(a, b) -> bool:
    ax, ay, bx, by = a
    cx, cy, dx, dy = b

    def lato(px, py, qx, qy, rx, ry):
        return (qx - px) * (ry - py) - (qy - py) * (rx - px)
    d1, d2 = lato(cx, cy, dx, dy, ax, ay), lato(cx, cy, dx, dy, bx, by)
    d3, d4 = lato(ax, ay, bx, by, cx, cy), lato(ax, ay, bx, by, dx, dy)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 != 0 and d2 != 0 and d3 != 0 and d4 != 0


def _dist_ss(a, b) -> float:
    if _si_tagliano(a, b):
        return 0.0
    return min(_dist_ps(a[0], a[1], *b), _dist_ps(a[2], a[3], *b), _dist_ps(b[0], b[1], *a), _dist_ps(b[2], b[3], *a))


class _Bordi:
    """I tratti di bordo (della faccia o della zona disegnata) in una griglia di caselle: ogni foro guarda solo i tratti
    vicini a lui. Per sapere se un punto sta dentro: le intersezioni di una riga orizzontale con i tratti (una volta per
    riga di fori)."""

    def __init__(self, tratti: list, cella: float):
        self.tratti = tratti
        xs = [v for t in tratti for v in (t[0], t[2])] or [0.0]
        ys = [v for t in tratti for v in (t[1], t[3])] or [0.0]
        self.x0, self.y0 = min(xs), min(ys)
        self.c = max(cella, 1e-3)
        self.nx = int((max(xs) - self.x0) / self.c) + 1
        self.ny = int((max(ys) - self.y0) / self.c) + 1
        self.celle: dict = {}
        for k, (ax, ay, bx, by) in enumerate(tratti):
            i0, j0 = self._ij(min(ax, bx), min(ay, by))
            i1, j1 = self._ij(max(ax, bx), max(ay, by))
            for j in range(j0, j1 + 1):
                for i in range(i0, i1 + 1):
                    self.celle.setdefault((i, j), []).append(k)
        self._righe: dict = {}

    def _ij(self, x, y):
        return (min(self.nx - 1, max(0, int((x - self.x0) / self.c))), min(self.ny - 1, max(0, int((y - self.y0) / self.c))))

    def vicini(self, x0, y0, x1, y1) -> set:
        i0, j0 = self._ij(x0, y0)
        i1, j1 = self._ij(x1, y1)
        out = set()
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                out.update(self.celle.get((i, j), ()))
        return out

    def dentro(self, x: float, y: float) -> bool:
        """Pari o dispari: quante volte la riga orizzontale a sinistra del punto passa un bordo."""
        xs = self._righe.get(y)
        if xs is None:
            yy = y + 1.234e-7                   # mai proprio su un vertice
            xs = sorted(ax + (yy - ay) * (bx - ax) / (by - ay) for ax, ay, bx, by in self.tratti
                        if (ay > yy) != (by > yy))
            self._righe[y] = xs
        return bisect.bisect_left(xs, x) % 2 == 1

    def lontano(self, foro: Foro, x, y, gioco: float) -> bool:
        """Il foro in (x, y) sta ad almeno «gioco» da ogni tratto di bordo."""
        mx, my = foro.mezzi()
        g = gioco + 1e-6
        nocc = foro.nocciolo(x, y)
        serve = foro.rho + gioco - 1e-7
        for k in self.vicini(x - mx - g, y - my - g, x + mx + g, y + my + g):
            t = self.tratti[k]
            for n in nocc:
                if _dist_ss(n, t) < serve:
                    return False
            if foro.forma == 'quadro':        # un bordo tutto dentro il quadro (un forellino che c'è già)
                h = foro.a / 2
                if abs(t[0] - x) < h and abs(t[1] - y) < h:
                    return False
        return True


def tratti_della_faccia(facce, piano: bd.Plane, passo: float = 0.5, solo_esterni: bool = False) -> tuple[list, tuple]:
    """I bordi delle facce (esterni e fori) come tratti nel piano: (tratti, scatola x0, y0, x1, y1). Con i punti chiesti
    direttamente al kernel (una faccia con 1000 fori sono 40 mila punti: con gli oggetti di build123d erano 5 secondi)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Line
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS
    tratti = []
    ox, oy, oz = piano.origin.X, piano.origin.Y, piano.origin.Z
    (xx, xy, xz), (yx, yy, yz) = ((piano.x_dir.X, piano.x_dir.Y, piano.x_dir.Z), (piano.y_dir.X, piano.y_dir.Y, piano.y_dir.Z))

    def loc(p):
        dx, dy, dz = p.X() - ox, p.Y() - oy, p.Z() - oz
        return dx * xx + dy * xy + dz * xz, dx * yx + dy * yy + dz * yz
    for f in facce:
        fw = f.wrapped if hasattr(f, 'wrapped') else f
        fili = [BRepTools.OuterWire_s(fw)] if solo_esterni else []
        if not solo_esterni:
            ew = TopExp_Explorer(fw, TopAbs_WIRE)
            while ew.More():
                fili.append(ew.Current())
                ew.Next()
        for w in fili:
            ee = TopExp_Explorer(w, TopAbs_EDGE)
            while ee.More():
                c = BRepAdaptor_Curve(TopoDS.Edge(ee.Current()))
                ee.Next()
                a, b = c.FirstParameter(), c.LastParameter()
                if c.GetType() == GeomAbs_Line:
                    pts = [loc(c.Value(a)), loc(c.Value(b))]
                else:
                    lung = sum(c.Value(a + (b - a) * k / 8).Distance(c.Value(a + (b - a) * (k + 1) / 8)) for k in range(8))
                    n = max(8, min(256, int(math.ceil(lung / passo))))
                    pts = [loc(c.Value(a + (b - a) * k / n)) for k in range(n + 1)]
                for p, q in zip(pts, pts[1:]):
                    if abs(p[0] - q[0]) + abs(p[1] - q[1]) > 1e-9:
                        tratti.append((p[0], p[1], q[0], q[1]))
    if not tratti:
        return [], (0, 0, 0, 0)
    xs = [v for t in tratti for v in (t[0], t[2])]
    ys = [v for t in tratti for v in (t[1], t[3])]
    return tratti, (min(xs), min(ys), max(xs), max(ys))


def _file(lo: float, hi: float, passo: float) -> tuple[int, float]:
    """Quanti centri ci stanno tra lo e hi con quel passo, e dove cade il primo perché la fila stia in mezzo."""
    span = hi - lo
    if span < -1e-9:
        return 0, lo
    n = int(math.floor(span / passo + 1e-9)) + 1
    return n, lo + (span - (n - 1) * passo) / 2


def griglia(scatola: tuple, foro: Foro, px: float, py: float, sfalsata: bool) -> list:
    """I centri della serie centrata nella scatola dei centri possibili (x0, y0, x1, y1): margini uguali di qua e di
    là, come si fa in officina. Sfalsata a 60°: file a py, una sì e una no spostate di mezzo passo, e la serie centrata
    anche contando lo spostamento."""
    x0, y0, x1, y1 = scatola
    ny, ya = _file(y0, y1, py)
    nx, xa = _file(x0, x1, px)
    if nx <= 0 or ny <= 0:
        return []
    if nx * ny > MAX_FORI:
        raise FeatureError(f'Verrebbero più di {MAX_FORI} fori ({nx * ny}): aumenta il passo.')
    pari = [xa + i * px for i in range(nx)]
    dispari = pari
    if sfalsata:
        if (x1 - x0) - (nx - 1) * px >= px / 2 - 1e-9:
            # c'è posto per spostare tutta la fila di mezzo passo: le due file si centrano insieme
            xa = x0 + ((x1 - x0) - ((nx - 1) * px + px / 2)) / 2
            pari = [xa + i * px for i in range(nx)]
            dispari = [x + px / 2 for x in pari]
        else:
            dispari = [x + px / 2 for x in pari[:-1]]
    return [(x, ya + j * py) for j in range(ny) for x in (dispari if j % 2 else pari)]


# ----------------------------------------------------------------------------------- misure della feature
def misure(fdef: dict, ctx) -> tuple:
    """(foro, px, py, sfalsata, margine) dai campi della feature, controllati."""
    fid = fdef['id']
    forma = fdef.get('forma') or 'tondo'
    if forma not in FORME:
        raise FeatureError(f'Forma dei fori «{forma}» sconosciuta (tondo, asola, quadro).', feature=fid)
    if forma == 'tondo':
        foro = Foro('tondo', ctx.value(fdef, 'd', 'il diametro dei fori'))
    elif forma == 'asola':
        foro = Foro('asola', ctx.value(fdef, 'lung', 'la lunghezza delle asole'), ctx.value(fdef, 'larg', 'la larghezza delle asole'),
                    bool(fdef.get('verticale')))
        if foro.b <= 0 or foro.a <= foro.b + 1e-6:
            raise FeatureError('L’asola deve essere più lunga che larga.', feature=fid)
    else:
        foro = Foro('quadro', ctx.value(fdef, 'lato', 'il lato dei quadri'))
    if foro.a <= 0:
        raise FeatureError('La misura dei fori deve essere più di zero.', feature=fid)
    sfalsata = (fdef.get('disposizione') or 'fila') == 'sfalsata'
    px = ctx.value(fdef, 'px', 'il passo')
    if sfalsata:
        py = px * S60
    else:
        py = ctx.value(fdef, 'py', 'il passo in verticale') if fdef.get('py') not in (None, '') else px
    if px <= 0 or py <= 0:
        raise FeatureError('Il passo deve essere più di zero.', feature=fid)
    margine = ctx.value(fdef, 'margine', 'il margine') if fdef.get('margine') not in (None, '') else 0.0
    if margine < 0:
        raise FeatureError('Il margine non può essere negativo.', feature=fid)
    p = ponticello(foro, px, py, sfalsata)
    if p <= 1e-6:
        raise FeatureError(f'Con questo passo i fori si toccano: ci vuole un passo più grande di {fmt_mm(round(_passo_minimo(foro, sfalsata), 2))} mm.',
                           feature=fid)
    return foro, px, py, sfalsata, margine


def ponticello(foro: Foro, px: float, py: float, sfalsata: bool) -> float:
    """La lamiera che resta tra due fori vicini (il ponticello), in mm."""
    vicini = [(px, 0.0), (px / 2, py), (-px / 2, py)] if sfalsata else [(px, 0.0), (0.0, py), (px, py)]
    a = foro.nocciolo(0.0, 0.0)
    out = math.inf
    for dx, dy in vicini:
        b = foro.nocciolo(dx, dy)
        d = min(_dist_ss(p, q) for p in a for q in b)
        if foro.forma == 'quadro':
            h = foro.a / 2
            if abs(dx) < 2 * h and abs(dy) < 2 * h:
                d = 0.0
        out = min(out, d - 2 * foro.rho)
    return out


def _passo_minimo(foro: Foro, sfalsata: bool) -> float:
    mx, my = foro.mezzi()
    return 2 * mx if not sfalsata else max(2 * mx, 2 * my / S60) if foro.forma != 'tondo' else foro.a


# ------------------------------------------------------------------------------------- dove sta la faccia
def piano_faccia(body, face_name: str) -> bd.Plane:
    """Il piano della faccia vista di fronte, come per uno sketch su quella faccia (x a destra, y in su)."""
    from ..sketch.face_plane import plane_of

    class _Sk:                        # plane_of chiede solo il nome per i messaggi
        @staticmethod
        def label():
            return face_name
    return plane_of(body, face_name, _Sk())


def mappa(body, data, face_name: str, fid: str):
    """(src, dst, dentro, g): il piano della faccia sul pezzo e quello nello sviluppo (stesse coordinate locali),
    verso dentro il materiale, la flangia (o None)."""
    from . import _face_planes
    pannelli = getattr(data, 'pannelli', None) or {}
    if face_name in pannelli:
        src, dst, dentro = pannelli[face_name]
        return src, dst, dentro, None
    parti = face_name.split('/')
    if not parti or parti[0] != data.feature:
        raise FeatureError('La lamiera forata va fatta su una faccia piana della lamiera.', feature=fid)
    return _face_planes(parti, data, fid)


def _facce_sul_piano(body, face_name: str, piano: bd.Plane, fid: str) -> list:
    n = piano.z_dir
    out = []
    for f in body.names.get(face_name) or []:
        bf = bd.Face(f)
        if bf.geom_type != bd.GeomType.PLANE:
            continue
        if abs(abs(bf.normal_at().dot(n)) - 1) > 1e-6 or abs((bf.center() - piano.origin).dot(n)) > 1e-4:
            continue
        out.append(bf)
    if not out:
        raise FeatureError('Questa faccia non c’è più o non è piana: scegli di nuovo la faccia.', feature=fid)
    return out


def _facce_di_sotto(body, piano: bd.Plane, t: float, rel: float) -> list:
    """Le facce piane dall'altra parte dello spessore (parallele, a t verso dentro il materiale): il foro deve uscire
    dentro una di loro. Per le forme a facce (tramogge) lo spessore vero è giusto a meno di qualche centesimo. Col
    piano della superficie, senza misurare le facce (dopo una lamiera forata sono migliaia di pareti di fori)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane

    from ..topology.naming import _faces_of
    n = piano.z_dir
    nx, ny, nz = n.X, n.Y, n.Z
    ox, oy, oz = piano.origin.X, piano.origin.Y, piano.origin.Z
    out = []
    for f in _faces_of(body.shape):
        su = BRepAdaptor_Surface(f, False)
        if su.GetType() != GeomAbs_Plane:
            continue
        pl = su.Plane()
        d, q = pl.Axis().Direction(), pl.Location()
        if abs(abs(d.X() * nx + d.Y() * ny + d.Z() * nz) - 1) > 1e-6:
            continue
        if abs((q.X() - ox) * nx + (q.Y() - oy) * ny + (q.Z() - oz) * nz + t) <= max(rel * t, 1e-4):
            out.append(bd.Face(f))
    return out


def zona(body, data, face_name: str, prof, margine: float, foro: Foro, fid: str):
    """I bordi da rispettare e la scatola dove cadono i centri: (bordi faccia, bordi sotto, bordi zona o None, scatola,
    piano, facce sopra, facce sotto)."""
    piano = piano_faccia(body, face_name)
    facce = _facce_sul_piano(body, face_name, piano, fid)
    rel = 0.05 if (getattr(data, 'shape_info', None) or {}).get('kind') == 'sezioni' else 1e-6
    sotto = _facce_di_sotto(body, piano, data.thickness, rel)
    tf, (fx0, fy0, fx1, fy1) = tratti_della_faccia(facce, piano)
    ts, _ = tratti_della_faccia(sotto, piano)
    mx, my = foro.mezzi()
    x0, y0, x1, y1 = fx0 + mx + margine, fy0 + my + margine, fx1 - mx - margine, fy1 - my - margine
    tz = None
    if prof is not None:
        contorni = list(prof.faces)
        if not contorni:
            raise FeatureError('Lo sketch della zona non ha contorni chiusi.', feature=fid)
        n = piano.z_dir
        for c in contorni:
            if abs(abs(c.normal_at().dot(n)) - 1) > 1e-6 or abs((c.center() - piano.origin).dot(n)) > 1e-3:
                raise FeatureError('Il contorno della zona deve essere disegnato sulla stessa faccia dei fori.', feature=fid)
        tz, (cx0, cy0, cx1, cy1) = tratti_della_faccia(contorni, piano)
        x0, y0, x1, y1 = max(x0, cx0 + mx), max(y0, cy0 + my), min(x1, cx1 - mx), min(y1, cy1 - my)
    return tf, ts, tz, (x0, y0, x1, y1), piano, facce, sotto


def centri(body, data, face_name: str, prof, foro: Foro, px, py, sfalsata, margine, fid: str):
    """I centri dei fori interi nella zona, nel piano della faccia vista di fronte: un foro si fa se sta tutto sulla
    faccia (e sulla faccia di sotto), a «margine» dai bordi, dalle pieghe e dai fori che ci sono già, e dentro la zona
    disegnata. Torna (centri, piano, quanti saltati perché non ci stavano interi, facce sopra, facce sotto)."""
    tf, ts, tz, scatola, piano, sopra, sotto = zona(body, data, face_name, prof, margine, foro, fid)
    tutti = griglia(scatola, foro, px, py, sfalsata)
    mx, my = foro.mezzi()
    cella = max(px, py, 2 * mx, 2 * my) + margine
    bf = _Bordi(tf, cella)
    bs = _Bordi(ts, cella) if ts else None
    bz = _Bordi(tz, cella) if tz else None
    buoni, saltati = [], 0
    for x, y in tutti:
        # un punto della griglia fuori dalla faccia (o dalla zona) non è un foro saltato: lì non c'è lamiera da forare
        if not bf.dentro(x, y) or (bs is not None and not bs.dentro(x, y)) or (bz is not None and not bz.dentro(x, y)):
            continue
        if not bf.lontano(foro, x, y, margine) or (bs is not None and not bs.lontano(foro, x, y, margine)) or                 (bz is not None and not bz.lontano(foro, x, y, 0.0)):
            saltati += 1                 # toccherebbe un bordo, una piega, un foro che c'è già o il margine
            continue
        buoni.append((x, y))
    return buoni, piano, saltati, sopra, sotto


# ------------------------------------------------------------------------- i fori fatti senza booleana
# 05/11: un taglio booleano con 1800 cilindri su una lastra sono 13-27 secondi (provato). I fori qui stanno tutti dentro
# una faccia di sopra e una di sotto, lontani dai bordi: le due facce si rifanno con i fori come contorni interni e le
# pareti dei fori si aggiungono al guscio. Pochi decimi di secondo, e il solido si controlla (volume e validità): se
# qualcosa non torna si fa il taglio booleano di sempre.
def _filo(foro: Foro, x: float, y: float, o, ex, ey, n):
    """Il contorno del foro in (x, y) sul piano (o, ex, ey, normale n), come TopoDS_Wire."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeWire
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt

    def P(u, v):
        return gp_Pnt(o[0] + ex[0] * u + ey[0] * v, o[1] + ex[1] * u + ey[1] * v, o[2] + ex[2] * u + ey[2] * v)
    if foro.forma == 'tondo':
        c = gp_Circ(gp_Ax2(P(x, y), gp_Dir(*n), gp_Dir(*ex)), foro.a / 2)
        return BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(c).Edge()).Wire()
    if foro.forma == 'quadro':
        poly = BRepBuilderAPI_MakePolygon()
        for u, v in foro.contorno(x, y):
            poly.Add(P(u, v))
        poly.Close()
        return poly.Wire()
    r, h = foro.b / 2, (foro.a - foro.b) / 2
    Q = (lambda u, v: P(x - v, y + u)) if foro.verticale else (lambda u, v: P(x + u, y + v))
    mk = BRepBuilderAPI_MakeWire()
    mk.Add(BRepBuilderAPI_MakeEdge(Q(-h, -r), Q(h, -r)).Edge())
    mk.Add(BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(Q(h, -r), Q(h + r, 0), Q(h, r)).Value()).Edge())
    mk.Add(BRepBuilderAPI_MakeEdge(Q(h, r), Q(-h, r)).Edge())
    mk.Add(BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(Q(-h, r), Q(-h - r, 0), Q(-h, -r)).Value()).Edge())
    return mk.Wire()


def _giro(wire, n) -> float:
    """Il verso di un contorno attorno alla normale n: > 0 antiorario, < 0 orario (area con segno)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.TopAbs import TopAbs_REVERSED
    pts = []
    ex = BRepTools_WireExplorer(wire)
    while ex.More():
        e = ex.Current()
        c = BRepAdaptor_Curve(e)
        a, b = c.FirstParameter(), c.LastParameter()
        us = [a + (b - a) * k / 16 for k in range(17)]
        if e.Orientation() == TopAbs_REVERSED:
            us.reverse()
        pts += [c.Value(u) for u in us[:-1]]
        ex.Next()
    sx = sy = sz = 0.0
    for i in range(len(pts)):
        p, q = pts[i], pts[(i + 1) % len(pts)]
        sx += p.Y() * q.Z() - p.Z() * q.Y()
        sy += p.Z() * q.X() - p.X() * q.Z()
        sz += p.X() * q.Y() - p.Y() * q.X()
    return sx * n[0] + sy * n[1] + sz * n[2]


def _normale_naturale(face) -> tuple:
    """La normale della superficie della faccia (quella dei suoi contorni, senza il verso della faccia)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    d = BRepAdaptor_Surface(face).Plane().Axis().Direction()
    return d.X(), d.Y(), d.Z()


def _con_fori(face, fili: list):
    """La stessa faccia (stessa superficie, stessi bordi) con in più i fili come fori; fili già nel verso giusto."""
    from OCP.BRep import BRep_Builder
    from OCP.TopAbs import TopAbs_FORWARD, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    avanti = face.Oriented(TopAbs_FORWARD)
    nuova = TopoDS.Face(avanti.EmptyCopied())
    b = BRep_Builder()
    ex = TopExp_Explorer(avanti, TopAbs_WIRE)
    while ex.More():
        b.Add(nuova, ex.Current())
        ex.Next()
    for w in fili:
        b.Add(nuova, w)
    return TopoDS.Face(nuova.Oriented(face.Orientation()))


def _chi_contiene(facce: list, pts: list) -> list:
    """Per ogni punto l'indice della faccia (TopoDS_Face) che lo contiene, o None."""
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN
    if len(facce) == 1:
        return [0] * len(pts)
    out = []
    for p in pts:
        k = None
        for i, f in enumerate(facce):
            if BRepClass_FaceClassifier(f, gp_Pnt(*p), 1e-6).State() == TopAbs_IN:
                k = i
                break
        out.append(k)
    return out


class _Chiave:
    """Facce TopoDS come chiavi (confronto con IsSame): poche, basta una lista."""

    def __init__(self):
        self.voci: list = []

    def __setitem__(self, k, v):
        for i, (x, _) in enumerate(self.voci):
            if x.IsSame(k):
                self.voci[i] = (x, v)
                return
        self.voci.append((k, v))

    def get(self, k, d=None):
        for x, v in self.voci:
            if x.IsSame(k):
                return v
        return d

    def chiavi(self) -> list:
        return [x for x, _ in self.voci]

    def valori(self) -> list:
        return [v for _, v in self.voci]


def _sostituisci(shape, cambi: _Chiave, aggiunte: _Chiave):
    """Il solido con le facce cambiate (cambi: faccia → faccia nuova) e le facce aggiunte nello stesso guscio
    (aggiunte: faccia → [facce]). Le altre facce restano le stesse (stessi nomi)."""
    from OCP.BRep import BRep_Builder
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shell, TopoDS_Solid
    b = BRep_Builder()

    def guscio(sh):
        ex = TopExp_Explorer(sh, TopAbs_FACE)
        facce = []
        while ex.More():
            facce.append(TopoDS.Face(ex.Current()))
            ex.Next()
        if not any(cambi.get(f) is not None for f in facce):
            return sh
        nuovo = TopoDS_Shell()
        b.MakeShell(nuovo)
        for f in facce:
            nuova = cambi.get(f)
            b.Add(nuovo, nuova.Oriented(f.Orientation()) if nuova is not None else f)
            for g in aggiunte.get(f, ()):
                b.Add(nuovo, g)
        nuovo.Closed(True)
        return nuovo

    def solido(so):
        nuovo = TopoDS_Solid()
        b.MakeSolid(nuovo)
        ex = TopExp_Explorer(so, TopAbs_SHELL)
        while ex.More():
            b.Add(nuovo, guscio(ex.Current()))
            ex.Next()
        return nuovo

    if shape.ShapeType() == TopAbs_SOLID:
        return solido(shape)
    if shape.ShapeType() == TopAbs_COMPOUND:
        c = TopoDS_Compound()
        b.MakeCompound(c)
        ex = TopExp_Explorer(shape, TopAbs_SOLID)
        while ex.More():
            b.Add(c, solido(ex.Current()))
            ex.Next()
        return c
    return None


def _area_foro(foro: Foro) -> float:
    if foro.forma == 'tondo':
        return math.pi * foro.a ** 2 / 4
    if foro.forma == 'quadro':
        return foro.a ** 2
    return (foro.a - foro.b) * foro.b + math.pi * foro.b ** 2 / 4


def _fori_diretti(body, data, foro: Foro, pieni: list, piano: bd.Plane, sopra: list, sotto: list, sul_dst: bd.Plane,
                  fid: str):
    """Il pezzo e lo sviluppo con i fori, senza booleana. None se non si riesce (si fa il taglio di sempre)."""
    import copy

    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Vec

    from ..features.base import volume
    if not sotto or not pieni:
        return None
    t = data.thickness
    T = lambda v: (v.X, v.Y, v.Z)  # noqa: E731
    o, ex, ey, n = T(piano.origin), T(piano.x_dir), T(piano.y_dir), T(piano.z_dir)
    giu = gp_Vec(-n[0] * t, -n[1] * t, -n[2] * t)
    f_sopra = [f.wrapped for f in sopra]
    f_sotto = [f.wrapped for f in sotto]
    pts3 = [tuple(o[i] + ex[i] * x + ey[i] * y for i in range(3)) for x, y in pieni]
    i_sopra = _chi_contiene(f_sopra, pts3)
    i_sotto = _chi_contiene(f_sotto, [tuple(p[i] - n[i] * t for i in range(3)) for p in pts3])
    if any(k is None for k in i_sopra + i_sotto):
        return None
    # i versi: un foro è un contorno orario rispetto alla normale della superficie della faccia; le pareti guardano
    # dentro il foro (fuori dal materiale). Si guarda il primo foro, gli altri sono fatti uguali.
    nat_sopra = [_normale_naturale(f) for f in f_sopra]
    nat_sotto = [_normale_naturale(f) for f in f_sotto]
    fili_sopra: dict = {}
    fili_sotto: dict = {}
    pareti: dict = {}
    gira_su = gira_giu = gira_pareti = None
    for (x, y), ks, kg in zip(pieni, i_sopra, i_sotto):
        w = _filo(foro, x, y, o, ex, ey, n)
        if gira_su is None:
            gira_su = _giro(w, nat_sopra[ks]) > 0
        if gira_su:
            w = TopoDS.Wire(w.Reversed())
        pr = BRepPrimAPI_MakePrism(w, giu)
        if not pr.IsDone():
            return None
        w2 = TopoDS.Wire(pr.LastShape())
        if gira_giu is None:
            gira_giu = _giro(w2, nat_sotto[kg]) > 0
        if gira_giu:
            w2 = TopoDS.Wire(w2.Reversed())
        lat = []
        e = TopExp_Explorer(pr.Shape(), TopAbs_FACE)
        while e.More():
            lat.append(TopoDS.Face(e.Current()))
            e.Next()
        if gira_pareti is None:
            f0 = bd.Face(lat[0])
            c = f0.center()
            c0 = bd.Vector(*(o[i] + ex[i] * x + ey[i] * y - n[i] * t / 2 for i in range(3)))
            gira_pareti = f0.normal_at(c).dot(c0 - c) < 0
        if gira_pareti:
            lat = [TopoDS.Face(f.Reversed()) for f in lat]
        fili_sopra.setdefault(ks, []).append(w)
        fili_sotto.setdefault(kg, []).append(w2)
        pareti.setdefault(ks, []).extend(lat)
    cambi, aggiunte = _Chiave(), _Chiave()
    for k, fili in fili_sopra.items():
        cambi[f_sopra[k]] = _con_fori(f_sopra[k], fili)
        aggiunte[f_sopra[k]] = pareti.get(k, [])
    for k, fili in fili_sotto.items():
        cambi[f_sotto[k]] = _con_fori(f_sotto[k], fili)
    nuova = _sostituisci(body.shape, cambi, aggiunte)
    if nuova is None:
        return None
    area = _area_foro(foro) * len(pieni)
    atteso = volume(body.shape) - area * t
    # il controllo: il volume tolto è proprio quello dei fori. Il controllo completo del kernel (BRepCheck) qui non
    # serve e costa 6 secondi con 1700 fori (confronta ogni foro con tutti gli altri): i fori sono lontani tra loro e
    # dai bordi per costruzione (ponticello e margine controllati sopra)
    if abs(volume(nuova) - atteso) > 1e-4 * max(atteso, 1.0):
        return None
    # lo sviluppo: la faccia dove cadono i fori, rifatta con i fori
    flat = data.flat
    fs = flat.faces() if not isinstance(flat, bd.Face) else [flat]
    fw = [f.wrapped for f in fs]
    o2, x2, y2, n2 = T(sul_dst.origin), T(sul_dst.x_dir), T(sul_dst.y_dir), T(sul_dst.z_dir)
    i_flat = _chi_contiene(fw, [tuple(o2[i] + x2[i] * x + y2[i] * y for i in range(3)) for x, y in pieni])
    if any(k is None for k in i_flat):
        return None
    nat = [_normale_naturale(f) for f in fw]
    per_faccia: dict = {}
    gira = None
    for (x, y), k in zip(pieni, i_flat):
        w = _filo(foro, x, y, o2, x2, y2, n2)
        if gira is None:
            gira = _giro(w, nat[k]) > 0
        per_faccia.setdefault(k, []).append(TopoDS.Wire(w.Reversed()) if gira else w)
    nuove = [bd.Face(_con_fori(f, per_faccia[k])) if k in per_faccia else fs[k] for k, f in enumerate(fw)]
    flat_area = sum(f.area for f in nuove)
    if abs((data.flat_area - flat_area) - area) > 1e-4 * max(area, 1.0):
        return None
    # i nomi: le facce di sopra e di sotto sono le stesse con i fori, le pareti dei fori sono nuove
    nomi = {k: [cambi.get(f, f) for f in fs_] for k, fs_ in body.names.items()}
    nomi[f'{fid}/parete'] = [f for v in aggiunte.valori() for f in v]
    nuovo = copy.copy(body)
    nuovo.shape = nuova
    nuovo.names = nomi
    nuovo_flat = nuove[0] if len(nuove) == 1 else bd.Compound(children=nuove)
    return nuovo, nuovo_flat, flat_area


# ------------------------------------------------------------------------------------------- la feature
def _faccia_foro(foro: Foro, x, y, pl: bd.Plane):
    """Il foro come faccia sul piano pl (coordinate locali x, y): per il taglio booleano di riserva."""
    T = lambda v: (v.X, v.Y, v.Z)  # noqa: E731
    return bd.Face(bd.Wire(_filo(foro, x, y, T(pl.origin), T(pl.x_dir), T(pl.y_dir), T(pl.z_dir))))


def piani_sviluppo(body, data, face_name: str, piano: bd.Plane, fid: str) -> tuple:
    """(verso dentro il materiale, il piano della faccia vista di fronte portato nello sviluppo)."""
    src, dst, dentro, _g = mappa(body, data, face_name, fid)
    if abs((piano.origin - src.origin).dot(src.z_dir)) > 1e-3 or abs(abs(piano.z_dir.dot(src.z_dir)) - 1) > 1e-6:
        raise FeatureError('Questa faccia non si porta nello sviluppo: scegli la faccia sopra o sotto, o quella di una '
                           'piega.', feature=fid)
    a0 = src.to_local_coords(piano.origin)
    ax = src.to_local_coords(piano.from_local_coords((1, 0))) - a0
    ay = src.to_local_coords(piano.from_local_coords((0, 1))) - a0
    o2 = dst.from_local_coords((a0.X, a0.Y))
    x2 = dst.from_local_coords((a0.X + ax.X, a0.Y + ax.Y)) - o2
    y2 = dst.from_local_coords((a0.X + ay.X, a0.Y + ay.Y)) - o2
    return dentro, bd.Plane(origin=o2, x_dir=x2, z_dir=x2.cross(y2))


def faccia_e_zona(fdef: dict, ctx, body):
    """(nome della faccia, contorni della zona o None) dai campi della feature."""
    fid = fdef['id']
    face_name = fdef.get('face')
    prof = None
    if fdef.get('sketch'):
        ss, prof = ctx.sketch(fdef)
        pf = ss.sketch.plane
        if not face_name and isinstance(pf, dict):
            face_name = pf.get('face')
    if not face_name or face_name not in body.names:
        raise FeatureError('La faccia della lamiera forata non c’è più: scegli di nuovo la faccia.', feature=fid)
    return face_name, prof


def build(fdef: dict, ctx):
    """I fori tutti insieme, nel pezzo e nello sviluppo."""
    import dataclasses

    from . import _copia_dati, _taglio_semplice, flat_size
    fid = fdef['id']
    body = ctx.body
    data = getattr(body, 'sheet', None) if body is not None else None
    if data is None:
        if ctx.lamiera_persa:
            raise FeatureError(f'Dopo «{ctx.lamiera_persa}» il pezzo non è più una lamiera: sposta la lamiera forata '
                               'prima di lei.', feature=fid)
        raise FeatureError('La lamiera forata si fa su una faccia di una lamiera.', feature=fid)
    foro, px, py, sfalsata, margine = misure(fdef, ctx)
    face_name, prof = faccia_e_zona(fdef, ctx, body)
    pieni, piano, scartati, sopra, sotto = centri(body, data, face_name, prof, foro, px, py, sfalsata, margine, fid)
    if not pieni:
        raise FeatureError('Nella zona non ci sta nessun foro intero: riduci il margine, il passo o i fori.', feature=fid)
    dentro, sul_dst = piani_sviluppo(body, data, face_name, piano, fid)
    fatto = _fori_diretti(body, data, foro, pieni, piano, sopra, sotto, sul_dst, fid)
    if fatto is not None:
        nuovo, nuovo_flat, area = fatto
        sd = dataclasses.replace(data, flat=nuovo_flat, flat_area=area,
                                 flat_size=flat_size(nuovo_flat, data.plane) if isinstance(nuovo_flat, bd.Face) else data.flat_size)
    else:
        lavori = [(_faccia_foro(foro, x, y, piano), dentro, _faccia_foro(foro, x, y, sul_dst)) for x, y in pieni]
        nuovo = _taglio_semplice(fdef, body, data, lavori, data.thickness, fid)
        sd = nuovo.sheet
    info = {'n': len(pieni), 'scartati': scartati, 'foro': foro.testo(), 'faccia': face_name,
            'ponticello': round(ponticello(foro, px, py, sfalsata), 3), 'diretto': fatto is not None}
    nuovo.sheet = _copia_dati(data, dataclasses.replace(sd, forate={**(getattr(data, 'forate', None) or {}), fid: info}))
    return nuovo
