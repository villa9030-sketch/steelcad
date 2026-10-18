"""Tavole: il disegno del pezzo, dello sviluppo e dell'assieme, impaginato su un foglio con cartiglio.

Un foglio è una lista di primitive in mm sul foglio (linee, polilinee, cerchi, testi, su layer). Da lì escono il DXF
(ezdxf), il PDF (scritto qui, senza librerie in più) e l'SVG per l'anteprima.

Viste in proiezione europea (ISO, primo diedro): vista di fronte, sotto la vista dall'alto, a destra la vista da
sinistra; in alto a destra un'isometrica. Le linee nascoste sono tratteggiate. Quote: gli ingombri su ogni vista e i
fori (raggruppati per diametro, con filettature, svasature e inserti presi dagli sketch).
"""
from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field

FORMATI = {'A4': (297.0, 210.0), 'A3': (420.0, 297.0), 'A2': (594.0, 420.0)}
SCALE = [10, 5, 2, 1, 1 / 2, 1 / 2.5, 1 / 5, 1 / 10, 1 / 20, 1 / 50]
LAYER = {'contorno': (7, 0.5), 'nascoste': (8, 0.25), 'tangenti': (8, 0.18), 'piega': (1, 0.25), 'quote': (5, 0.18),
         'testo': (7, 0.25), 'cornice': (7, 0.5), 'cartiglio': (7, 0.25), 'tabella': (7, 0.25)}


@dataclass
class Foglio:
    formato: str = 'A3'
    titolo: str = ''
    linee: list = field(default_factory=list)       # (layer, [(x, y), ...]) polilinee aperte
    cerchi: list = field(default_factory=list)      # (layer, (x, y), r)
    testi: list = field(default_factory=list)       # (layer, (x, y), testo, altezza, allineamento 'l'|'c'|'r')
    pieni: list = field(default_factory=list)       # (layer, [(x, y), ...]) triangoli pieni (frecce)

    @property
    def size(self):
        return FORMATI[self.formato]

    def line(self, layer, *pts):
        self.linee.append((layer, [tuple(map(float, p)) for p in pts]))

    def text(self, layer, p, t, h=3.5, al='l'):
        self.testi.append((layer, (float(p[0]), float(p[1])), str(t), float(h), al))


def fmt(v: float) -> str:
    v = round(v, 2)
    s = f'{v:.2f}'.rstrip('0').rstrip('.')
    return s.replace('.', ',')


def scala_testo(s: float) -> str:
    if s >= 1:
        return f'{fmt(s)}:1'
    return f'1:{fmt(1 / s)}'


# ------------------------------------------------------------------------------------------ proiezioni
VISTE = {'fronte': ((0, -1, 0), (0, 0, 1)), 'alto': ((0, 0, 1), (0, 1, 0)), 'sinistra': ((-1, 0, 0), (0, 0, 1)),
         'iso': ((1, -1, 1), (0, 0, 1))}


def proietta(shape, vista: str) -> dict:
    """Spigoli visti, tangenti e nascosti della vista, come polilinee 2D (mm del pezzo), più i cerchi visti."""
    import build123d as bd
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer

    d, up = VISTE[vista]
    algo = HLRBRep_Algo()
    algo.Add(shape)
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*d))
    ax.SetYDirection(gp_Dir(*up) if vista != 'iso' else _up_iso(d))
    algo.Projector(HLRAlgo_Projector(ax))
    algo.Update()
    algo.Hide()
    h = HLRBRep_HLRToShape(algo)

    def spigoli(comp):
        out = []
        if comp.IsNull():
            return out
        ex = TopExp_Explorer(comp, TopAbs_EDGE)
        while ex.More():
            out.append(bd.Edge(ex.Current()))
            ex.Next()
        return out

    def poly(e):
        if e.geom_type == bd.GeomType.LINE:
            a, b = e.start_point(), e.end_point()
            return [(a.X, a.Y), (b.X, b.Y)]
        n = max(8, min(96, int(e.length / 1.5)))
        return [(p.X, p.Y) for p in e.positions([i / n for i in range(n + 1)])]

    res = {'visti': [], 'tangenti': [], 'nascosti': [], 'cerchi': []}
    for comp in (h.VCompound(), h.OutLineVCompound()):
        for e in spigoli(comp):
            if e.length < 1e-6:
                continue
            res['visti'].append(poly(e))
            if e.geom_type == bd.GeomType.CIRCLE and abs(e.length - 2 * math.pi * e.radius) < 1e-6:
                c = e.arc_center
                res['cerchi'].append(((c.X, c.Y), e.radius))
    for e in spigoli(h.Rg1LineVCompound()):
        if e.length > 1e-6:
            res['tangenti'].append(poly(e))
    for comp in (h.HCompound(), h.OutLineHCompound()):
        for e in spigoli(comp):
            if e.length > 1e-6:
                res['nascosti'].append(poly(e))
    pts = [p for k in ('visti', 'tangenti') for pl in res[k] for p in pl]
    if pts:
        res['bbox'] = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
    else:
        res['bbox'] = (0, 0, 1, 1)
    return res


def _up_iso(d):
    from OCP.gp import gp_Dir
    import numpy as np
    d = np.array(d, dtype=float) / np.linalg.norm(d)
    z = np.array([0, 0, 1.0])
    up = z - d * np.dot(z, d)
    up /= np.linalg.norm(up)
    return gp_Dir(*up)


# ------------------------------------------------------------------------------------------ foglio base
def _cornice(f: Foglio, campi: dict):
    W, H = f.size
    f.line('cornice', (20, 10), (W - 10, 10), (W - 10, H - 10), (20, H - 10), (20, 10))
    # cartiglio in basso a destra: 180 × 50
    x0, y0, x1, y1 = W - 190, 10, W - 10, 60
    L = 'cartiglio'
    f.line(L, (x0, y0), (x0, y1), (x1, y1))
    righe = [y0 + 10, y0 + 20, y0 + 30, y0 + 40]
    for y in righe:
        f.line(L, (x0, y), (x1, y))
    for x in (x0 + 60, x0 + 120):
        f.line(L, (x, y0), (x, y0 + 30))
    celle = [
        (x0, y0 + 40, 180, 'Azienda', campi.get('azienda', '')),
        (x0, y0 + 30, 180, 'Titolo', campi.get('titolo', '')),
        (x0, y0 + 20, 60, 'N. disegno', campi.get('numero', '')),
        (x0 + 60, y0 + 20, 60, 'Materiale', campi.get('materiale', '')),
        (x0 + 120, y0 + 20, 60, 'Spessore / massa', campi.get('spessore_massa', '')),
        (x0, y0 + 10, 60, 'Disegnatore', campi.get('disegnatore', '')),
        (x0 + 60, y0 + 10, 60, 'Data', campi.get('data', '')),
        (x0 + 120, y0 + 10, 60, 'Scala', campi.get('scala', '')),
        (x0, y0, 60, 'Revisione', campi.get('revisione', '')),
        (x0 + 60, y0, 60, 'Foglio', campi.get('foglio', '')),
        (x0 + 120, y0, 60, 'Proiezione', 'europea (ISO E)'),
    ]
    for x, y, w, et, val in celle:
        f.text(L, (x + 1.5, y + 7.2), et, 1.8)
        f.text('testo', (x + 1.5, y + 2), _taglia(val, w, 3.2 if w > 100 else 2.8), 3.2 if w > 100 else 2.8)
    if campi.get('note'):
        f.text('testo', (22, 13), 'Note: ' + campi['note'], 2.5)
    return (20 + 5, 10 + 5, W - 10 - 5, H - 10 - 5), (x0, y0, x1, y1)


def _taglia(t: str, w: float, h: float) -> str:
    n = max(4, int((w - 3) / (h * 0.55)))
    return t if len(t) <= n else t[:n - 1] + '…'


def _freccia(f: Foglio, p, verso, layer='quote', L=2.5):
    vx, vy = verso
    n = math.hypot(vx, vy) or 1
    vx, vy = vx / n, vy / n
    px, py = -vy, vx
    a = (p[0] - vx * L + px * L * 0.3, p[1] - vy * L + py * L * 0.3)
    b = (p[0] - vx * L - px * L * 0.3, p[1] - vy * L - py * L * 0.3)
    f.pieni.append((layer, [p, a, b]))


def quota(f: Foglio, a, b, distanza: float, valore: float, h=2.8, prefisso=''):
    """Quota lineare tra a e b (foglio), spostata di "distanza" a sinistra di a→b; scrive il valore vero."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    A = (ax + nx * distanza, ay + ny * distanza)
    B = (bx + nx * distanza, by + ny * distanza)
    s = 1.5 if distanza > 0 else -1.5
    f.line('quote', (ax + nx * s * 0.6, ay + ny * s * 0.6), (A[0] + nx * s, A[1] + ny * s))
    f.line('quote', (bx + nx * s * 0.6, by + ny * s * 0.6), (B[0] + nx * s, B[1] + ny * s))
    f.line('quote', A, B)
    _freccia(f, A, (-ux, -uy))
    _freccia(f, B, (ux, uy))
    m = ((A[0] + B[0]) / 2 + nx * 1.2 * (1 if distanza > 0 else -2.2), (A[1] + B[1]) / 2 + ny * 1.2 * (1 if distanza > 0 else -2.2))
    f.text('quote', m, prefisso + fmt(valore), h, 'c' if abs(uy) < 0.5 else 'c')
    if abs(uy) > 0.5:                                      # quota verticale: testo ruotato nei formati che lo sanno fare
        f.testi[-1] = ('quote', m, prefisso + fmt(valore), h, 'cv')


def _metti_vista(f: Foglio, v: dict, s: float, ox: float, oy: float, quote_su=True, valori=None):
    """Disegna la vista con scala s, con l'angolo in basso a sinistra del suo ingombro in (ox, oy)."""
    x0, y0, x1, y1 = v['bbox']
    T = lambda p: (ox + (p[0] - x0) * s, oy + (p[1] - y0) * s)  # noqa: E731
    for k, layer in (('visti', 'contorno'), ('tangenti', 'tangenti'), ('nascosti', 'nascoste')):
        for pl in v[k]:
            f.line(layer, *[T(p) for p in pl])
    w, h = (x1 - x0) * s, (y1 - y0) * s
    if quote_su:
        vw, vh = valori if valori else (x1 - x0, y1 - y0)
        quota(f, (ox, oy), (ox + w, oy), -7, vw)                 # larghezza sotto
        quota(f, (ox, oy), (ox, oy + h), 7, vh)                  # altezza a sinistra
    return T, w, h


def _fori(f: Foglio, v: dict, T, s, etichette: dict, gia: set):
    """Note dei fori: un richiamo per diametro (n× Ø...), con filettature/svasature/inserti dagli sketch."""
    gruppi: dict = {}
    for c, r in v['cerchi']:
        k = round(2 * r, 3)
        gruppi.setdefault(k, []).append(c)
    for k, cs in sorted(gruppi.items()):
        if k < 0.5:
            continue
        uniq = []
        for c in cs:
            if not any(math.dist(c, u) < 1e-3 for u in uniq):
                uniq.append(c)
        base = etichette.get(k, f'Ø{fmt(k)}')
        if base in gia:
            continue                                   # stesso foro già richiamato (es. svasatura: cerchio grande e piccolo)
        gia.add(base)
        c = max(uniq, key=lambda q: (q[1], q[0]))
        p = T(c)
        r = k / 2 * s
        testo = base
        testo = (f'{len(uniq)}× ' if len(uniq) > 1 else '') + testo
        q = (p[0] + r * 0.7, p[1] + r * 0.7)
        e = (q[0] + 8, q[1] + 8)
        f.line('quote', q, e, (e[0] + 2 + len(testo) * 1.6, e[1]))
        _freccia(f, q, (q[0] - e[0], q[1] - e[1]))
        f.text('quote', (e[0] + 1, e[1] + 0.8), testo, 2.6)


def etichette_fori(doc) -> dict:
    """Diametro → testo per i fori speciali disegnati negli sketch del pezzo."""
    out = {}
    try:
        from cad_engine.sketch import Sketch
    except ImportError:
        return out
    for f in doc.features:
        if not isinstance(f, Sketch):
            continue
        for e in f.entities.values():
            h = e.get('hole') if e.get('kind') == 'circle' else None
            if not h:
                continue
            d = round(2 * float(e['r']), 3)
            if h.get('tipo') == 'filettato':
                out[d] = f'{h["M"]} (preforo Ø{fmt(d)})'
            elif h.get('tipo') == 'svasato':
                out[d] = f'Ø{fmt(d)} svasato Ø{fmt(float(h["D"]))}×{fmt(float(h.get("angolo", 90)))}°'
                out[round(float(h['D']), 3)] = out[d]           # dalla parte svasata si vede il cerchio grande
            elif h.get('tipo') == 'inserto':
                out[d] = f'Ø{fmt(d)} per inserto {h["codice"]}'
    return out


def _scegli_scala(dims: list, area_w: float, area_h: float) -> float:
    """dims: (larghezza totale, altezza totale) in mm del pezzo, già con le viste affiancate."""
    for s in SCALE:
        if dims[0] * s <= area_w and dims[1] * s <= area_h:
            return s
    return SCALE[-1]


# ------------------------------------------------------------------------------------------ le tavole
def tavola_pezzo(shape, campi: dict, etichette: dict | None = None, formato: str = 'A3') -> Foglio:
    """Fronte, alto, sinistra (europea) + isometrica, con ingombri e note dei fori."""
    f = Foglio(formato, campi.get('titolo', ''))
    area, cart = _cornice(f, campi)
    v = {k: proietta(shape, k) for k in ('fronte', 'alto', 'sinistra', 'iso')}
    wF, hF = v['fronte']['bbox'][2] - v['fronte']['bbox'][0], v['fronte']['bbox'][3] - v['fronte']['bbox'][1]
    wL = v['sinistra']['bbox'][2] - v['sinistra']['bbox'][0]
    hT = v['alto']['bbox'][3] - v['alto']['bbox'][1]
    g = 30                                                # spazio per le quote tra le viste
    aw, ah = (area[2] - area[0]) - 3 * g - 40, (area[3] - area[1]) - 3 * g
    s = _scegli_scala((wF + wL, hF + hT), aw, ah)
    campi = {**campi, 'scala': scala_testo(s)}
    f.testi = []
    f.linee, f.cerchi, f.pieni = [], [], []
    area, cart = _cornice(f, campi)
    ox = area[0] + g
    oyT = area[1] + g + 5
    oyF = oyT + hT * s + g
    TF, _, _ = _metti_vista(f, v['fronte'], s, ox, oyF)
    TT, _, _ = _metti_vista(f, v['alto'], s, ox, oyT)
    TL, _, _ = _metti_vista(f, v['sinistra'], s, ox + wF * s + g, oyF)
    for nome, (x, y) in (('VISTA DI FRONTE', (ox, oyF + hF * s + 4)), ('VISTA DALL’ALTO', (ox, oyT + hT * s + 4)),
                         ('VISTA DA SINISTRA', (ox + wF * s + g, oyF + v['sinistra']['bbox'][3] * 0 + (v['sinistra']['bbox'][3] - v['sinistra']['bbox'][1]) * s + 4))):
        f.text('testo', (x, y), nome, 2.5)
    gia: set = set()
    et = etichette or {}
    _fori(f, v['alto'], TT, s, et, gia)
    _fori(f, v['fronte'], TF, s, et, gia)
    _fori(f, v['sinistra'], TL, s, et, gia)
    # isometrica nello spazio libero più grande: a destra delle viste o sopra le viste (scala sua)
    vi = v['iso']
    wi, hi = vi['bbox'][2] - vi['bbox'][0], vi['bbox'][3] - vi['bbox'][1]
    hL = v['sinistra']['bbox'][3] - v['sinistra']['bbox'][1]
    cima = oyF + max(hF, hL) * s + 12
    candidati = [(ox + (wF + wL) * s + 2 * g, cart[3] + 10, area[2], area[3]),       # a destra
                 (area[0], cima, area[2], area[3])]                                   # sopra
    def scala_in(r):
        return min((r[2] - r[0] - 10) / max(wi, 1e-6), (r[3] - r[1] - 15) / max(hi, 1e-6))
    xi0, yi0, xi1, yi1 = max(candidati, key=scala_in)
    si = scala_in((xi0, yi0, xi1, yi1))
    if si > 0:
        _metti_vista(f, {**vi, 'nascosti': []}, si, xi0 + (xi1 - xi0 - wi * si) / 2, yi0 + (yi1 - yi0 - 12 - hi * si) / 2,
                     quote_su=False)
    f.text('testo', (xi0, yi1 - 3), 'ISOMETRICA (fuori scala)', 2.5)
    return f


def tavola_sviluppo(data, campi: dict, piegature: list, formato: str = 'A3') -> Foglio:
    """Lo sviluppo quotato, con le linee di piega e la tabella pieghe."""
    f = Foglio(formato, campi.get('titolo', ''))
    poly = []
    for pl in data.outline():
        pts = [(pl[i], pl[i + 1]) for i in range(0, len(pl) - 1, 2)]
        if pts and pts[0] != pts[-1]:
            pts.append(pts[0])
        poly.append(pts)
    xs = [p[0] for pl in poly for p in pl]
    ys = [p[1] for pl in poly for p in pl]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    W, H = FORMATI[formato]
    righe_tab = len(piegature)
    aw = (W - 40) * 0.62
    ah = H - 40 - 20
    s = _scegli_scala((x1 - x0, y1 - y0), aw - 40, ah - 30)
    campi = {**campi, 'scala': scala_testo(s)}
    area, cart = _cornice(f, campi)
    ox, oy = area[0] + 25, cart[1] + 30
    T = lambda p: (ox + (p[0] - x0) * s, oy + (p[1] - y0) * s)  # noqa: E731
    for pl in poly:
        f.line('contorno', *[T(p) for p in pl])
    for a, b, testo in data.bend_lines:
        A, B = T(a), T(b)
        f.line('piega', A, B)
        m = ((A[0] + B[0]) / 2, (A[1] + B[1]) / 2)
        f.text('piega', (m[0] + 1, m[1] + 1), testo, 2.2)
    quota(f, T((x0, y0)), T((x1, y0)), -8, x1 - x0)
    quota(f, T((x0, y0)), T((x0, y1)), 8, y1 - y0)
    f.text('testo', (ox, oy + (y1 - y0) * s + 6), 'SVILUPPO visto dal lato dello sketch · linee di piega in rosso: flangia, verso, angolo, raggio', 2.5)
    # tabella pieghe a destra, sopra il cartiglio
    tx, ty = cart[0], cart[3] + 10 + 7 * (righe_tab + 1)
    col = [0, 14, 34, 64, 84, 104, 124, 144, 180]
    intest = ['P', 'Flangia', 'Lungh. est.', 'Angolo', 'Verso', 'R int.', 'K', 'Largh.']
    _tabella(f, tx, ty, col, [intest] + piegature, 'TABELLA PIEGHE')
    return f


def _tabella(f: Foglio, x, ytop, col, righe, titolo=None):
    h = 7
    if titolo:
        f.text('testo', (x, ytop + 2), titolo, 2.8)
    for i, r in enumerate(righe):
        y = ytop - i * h
        f.line('tabella', (x, y), (x + col[-1], y))
        for j, val in enumerate(r):
            f.text('tabella' if i else 'testo', (x + col[j] + 1.2, y - 5), _taglia(str(val), col[j + 1] - col[j], 2.4), 2.4)
    yb = ytop - len(righe) * h
    f.line('tabella', (x, yb), (x + col[-1], yb))
    for c in col:
        f.line('tabella', (x + c, ytop), (x + c, yb))


def tavola_assieme(forme: list, campi: dict, distinta: list, formato: str = 'A3') -> Foglio:
    """L'assieme: fronte e alto, isometrica grande con i palloncini, e la distinta sopra il cartiglio.
    forme: [(numero di posizione, forma messa al suo posto)]."""
    import build123d as bd
    f = Foglio(formato, campi.get('titolo', ''))
    tutto = bd.Compound(children=[s for _, s in forme]).wrapped
    vF, vT, vI = proietta(tutto, 'fronte'), proietta(tutto, 'alto'), proietta(tutto, 'iso')
    wF, hF = vF['bbox'][2] - vF['bbox'][0], vF['bbox'][3] - vF['bbox'][1]
    hT = vT['bbox'][3] - vT['bbox'][1]
    W, H = FORMATI[formato]
    g = 28
    s = _scegli_scala((wF, hF + hT), (W - 40) * 0.42 - g, H - 40 - 2 * g)
    campi = {**campi, 'scala': scala_testo(s)}
    area, cart = _cornice(f, campi)
    ox, oyT = area[0] + g, area[1] + g
    oyF = oyT + hT * s + g
    _metti_vista(f, {**vF, 'nascosti': []}, s, ox, oyF)
    _metti_vista(f, {**vT, 'nascosti': []}, s, ox, oyT)
    f.text('testo', (ox, oyF + hF * s + 4), 'VISTA DI FRONTE', 2.5)
    f.text('testo', (ox, oyT + hT * s + 4), 'VISTA DALL’ALTO', 2.5)
    # isometrica con palloncini
    xi0, yi0 = area[0] + (area[2] - area[0]) * 0.45, cart[3] + 12 + 7 * (len(distinta) + 1) + 6
    xi1, yi1 = area[2], area[3]
    wi, hi = vI['bbox'][2] - vI['bbox'][0], vI['bbox'][3] - vI['bbox'][1]
    si = min((xi1 - xi0 - 20) / max(wi, 1e-6), (yi1 - yi0 - 20) / max(hi, 1e-6))
    oxi, oyi = xi0 + (xi1 - xi0 - wi * si) / 2, yi0 + (yi1 - yi0 - hi * si) / 2
    TI, _, _ = _metti_vista(f, {**vI, 'nascosti': []}, si, oxi, oyi, quote_su=False)
    import numpy as np
    d = np.array(VISTE['iso'][0], dtype=float)
    d /= np.linalg.norm(d)
    upd = _up_iso(VISTE['iso'][0])
    up = np.array([upd.X(), upd.Y(), upd.Z()])
    xd = np.cross(up, d)
    fatti = set()
    palloncini = []
    cx_iso = oxi + wi * si / 2
    for num, sh in forme:
        if num in fatti:
            continue
        fatti.add(num)
        c = sh.center()
        p3 = np.array([c.X, c.Y, c.Z])
        p = TI((float(np.dot(p3, xd)), float(np.dot(p3, up))))
        verso = 1 if p[0] >= cx_iso else -1
        q = (p[0] + verso * 18, p[1] + 14)
        while any(math.dist(q, b) < 10 for b in palloncini):      # non sopra un altro palloncino
            q = (q[0] + verso * 4, q[1] + 9)
        palloncini.append(q)
        f.line('quote', p, q)
        f.cerchi.append(('quote', q, 4.0))
        f.text('quote', (q[0], q[1] - 1.2), str(num), 3.2, 'c')
        f.cerchi.append(('quote', p, 0.6))
    f.text('testo', (xi0, yi1 - 3), 'ISOMETRICA (fuori scala)', 2.5)
    col = [0, 12, 76, 90, 116, 140, 180]
    intest = ['Pos.', 'Descrizione', 'Q.tà', 'Materiale', 'Spessore', 'Peso kg']
    _tabella(f, cart[0], cart[3] + 10 + 7 * (len(distinta) + 1), col, [intest] + distinta, 'DISTINTA')
    return f


# ------------------------------------------------------------------------------------------ uscite
def to_dxf(fogli: list, path):
    """Un DXF per foglio (più fogli: uno di fianco all'altro nello stesso file, distanziati)."""
    import ezdxf
    doc = ezdxf.new('R2010', setup=True)
    doc.units = ezdxf.units.MM
    for nome, (col, lw) in LAYER.items():
        if nome not in doc.layers:
            doc.layers.add(nome, color=col, lineweight=int(lw * 100))
    doc.layers.get('nascoste').dxf.linetype = 'DASHED'
    doc.layers.get('piega').dxf.linetype = 'DASHDOT'
    msp = doc.modelspace()
    dx = 0.0
    for f in fogli:
        o = lambda p: (p[0] + dx, p[1])  # noqa: E731
        for layer, pts in f.linee:
            if len(pts) == 2:
                msp.add_line(o(pts[0]), o(pts[1]), dxfattribs={'layer': layer})
            else:
                msp.add_lwpolyline([o(p) for p in pts], dxfattribs={'layer': layer})
        for layer, c, r in f.cerchi:
            msp.add_circle(o(c), r, dxfattribs={'layer': layer})
        for layer, pts in f.pieni:
            msp.add_solid([o(p) for p in pts], dxfattribs={'layer': layer})
        for layer, p, t, h, al in f.testi:
            from ezdxf.enums import TextEntityAlignment
            e = msp.add_text(t, height=h, dxfattribs={'layer': layer, 'rotation': 90 if al == 'cv' else 0, 'style': 'OpenSans'})
            a = {'l': TextEntityAlignment.BOTTOM_LEFT, 'c': TextEntityAlignment.BOTTOM_CENTER,
                 'r': TextEntityAlignment.BOTTOM_RIGHT, 'cv': TextEntityAlignment.BOTTOM_CENTER}[al]
            e.set_placement(o(p), align=a)
        dx += f.size[0] + 50
    doc.saveas(str(path))


def _pdf_testo(t: str) -> str:
    b = t.encode('cp1252', errors='replace')
    out = []
    for ch in b:
        c = chr(ch)
        if c in '()\\':
            out.append('\\' + c)
        elif 32 <= ch < 127:
            out.append(c)
        else:
            out.append(f'\\{ch:03o}')
    return ''.join(out)


def to_pdf(fogli: list, path):
    """PDF vettoriale, una pagina per foglio (Helvetica, linee con spessori e tratteggi dei layer)."""
    k = 72 / 25.4
    oggetti = []

    def obj(s):
        oggetti.append(s)
        return len(oggetti)

    font = obj('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>')
    pagine = []
    kids_pos = None
    for f in fogli:
        W, H = f.size
        c = ['1 J 1 j']
        attuale = None
        for layer, pts in f.linee:
            if layer != attuale:
                col, lw = LAYER.get(layer, (7, 0.25))
                tr = '[3 1.5] 0 d' if layer == 'nascoste' else '[6 1.5 1 1.5] 0 d' if layer == 'piega' else '[] 0 d'
                rgb = '0.75 0.1 0.1 RG' if layer == 'piega' else '0.15 0.3 0.6 RG' if layer == 'quote' else '0 0 0 RG'
                c.append(f'{lw * k:.3f} w {tr} {rgb}')
                attuale = layer
            c.append(' '.join(f'{p[0] * k:.2f} {p[1] * k:.2f} {"m" if i == 0 else "l"}' for i, p in enumerate(pts)) + ' S')
        c.append('[] 0 d')
        for layer, (cx, cy), r in f.cerchi:
            col, lw = LAYER.get(layer, (7, 0.25))
            m = 0.5523 * r
            P = lambda x, y: f'{(cx + x) * k:.2f} {(cy + y) * k:.2f}'  # noqa: E731
            c.append(f'{lw * k:.3f} w 0.15 0.3 0.6 RG {P(r, 0)} m {P(r, m)} {P(m, r)} {P(0, r)} c {P(-m, r)} {P(-r, m)} {P(-r, 0)} c '
                     f'{P(-r, -m)} {P(-m, -r)} {P(0, -r)} c {P(m, -r)} {P(r, -m)} {P(r, 0)} c S')
        for layer, pts in f.pieni:
            c.append('0.15 0.3 0.6 rg ' + ' '.join(f'{p[0] * k:.2f} {p[1] * k:.2f} {"m" if i == 0 else "l"}' for i, p in enumerate(pts)) + ' f')
        for layer, (x, y), t, h, al in f.testi:
            rgb = '0.15 0.3 0.6 rg' if layer == 'quote' else '0.75 0.1 0.1 rg' if layer == 'piega' else '0 0 0 rg'
            lw_t = len(t) * h * 0.5
            if al == 'cv':
                c.append(f'BT {rgb} /F1 {h * k:.2f} Tf 0 1 -1 0 {x * k:.2f} {(y - lw_t / 2) * k:.2f} Tm ({_pdf_testo(t)}) Tj ET')
                continue
            dx = {'l': 0, 'c': -lw_t / 2, 'r': -lw_t}[al]
            c.append(f'BT {rgb} /F1 {h * k:.2f} Tf {(x + dx) * k:.2f} {y * k:.2f} Td ({_pdf_testo(t)}) Tj ET')
        stream = '\n'.join(c).encode('latin-1')
        cont = obj(f'<< /Length {len(stream)} >>\nstream\n'.encode('latin-1') + stream + b'\nendstream')
        pagine.append((cont, W * k, H * k))
    kids_pos = len(oggetti) + 1 + len(pagine)
    ids = []
    for cont, w, h in pagine:
        ids.append(obj(f'<< /Type /Page /Parent {kids_pos} 0 R /MediaBox [0 0 {w:.2f} {h:.2f}] /Contents {cont} 0 R '
                       f'/Resources << /Font << /F1 {font} 0 R >> >> >>'))
    pages = obj(f'<< /Type /Pages /Kids [{" ".join(f"{i} 0 R" for i in ids)}] /Count {len(ids)} >>')
    assert pages == kids_pos
    cat = obj(f'<< /Type /Catalog /Pages {pages} 0 R >>')
    out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offs = []
    for i, o in enumerate(oggetti, 1):
        offs.append(len(out))
        body = o if isinstance(o, bytes) else o.encode('latin-1')
        out += f'{i} 0 obj\n'.encode() + body + b'\nendobj\n'
    xref = len(out)
    out += f'xref\n0 {len(oggetti) + 1}\n0000000000 65535 f \n'.encode()
    for o in offs:
        out += f'{o:010d} 00000 n \n'.encode()
    out += f'trailer\n<< /Size {len(oggetti) + 1} /Root {cat} 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    with open(path, 'wb') as fh:
        fh.write(bytes(out))


def to_svg(f: Foglio) -> str:
    W, H = f.size
    Y = lambda y: H - y  # noqa: E731
    stile = {'contorno': 'stroke="#111" stroke-width="0.45"', 'nascoste': 'stroke="#666" stroke-width="0.22" stroke-dasharray="2.5 1.2"',
             'tangenti': 'stroke="#777" stroke-width="0.16"', 'piega': 'stroke="#C0392B" stroke-width="0.25" stroke-dasharray="5 1.2 1 1.2"',
             'quote': 'stroke="#2B5BA0" stroke-width="0.16"', 'cornice': 'stroke="#111" stroke-width="0.5"',
             'cartiglio': 'stroke="#111" stroke-width="0.25"', 'tabella': 'stroke="#111" stroke-width="0.2"', 'testo': 'stroke="#111"'}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}mm" height="{H}mm">',
           f'<rect width="{W}" height="{H}" fill="#fff"/>', '<g fill="none" stroke-linecap="round" stroke-linejoin="round">']
    for layer, pts in f.linee:
        out.append(f'<polyline {stile.get(layer, stile["contorno"])} points="{" ".join(f"{p[0]:.2f},{Y(p[1]):.2f}" for p in pts)}"/>')
    for layer, (x, y), r in f.cerchi:
        out.append(f'<circle {stile["quote"]} cx="{x:.2f}" cy="{Y(y):.2f}" r="{r:.2f}"/>')
    out.append('</g>')
    for layer, pts in f.pieni:
        out.append(f'<polygon fill="#2B5BA0" points="{" ".join(f"{p[0]:.2f},{Y(p[1]):.2f}" for p in pts)}"/>')
    import html
    for layer, (x, y), t, h, al in f.testi:
        col = '#2B5BA0' if layer == 'quote' else '#C0392B' if layer == 'piega' else '#111'
        anchor = {'l': 'start', 'c': 'middle', 'r': 'end', 'cv': 'middle'}[al]
        rot = f' transform="rotate(-90 {x:.2f} {Y(y):.2f})"' if al == 'cv' else ''
        out.append(f'<text x="{x:.2f}" y="{Y(y):.2f}" font-family="Helvetica,Arial,sans-serif" font-size="{h:.2f}" '
                   f'fill="{col}" text-anchor="{anchor}"{rot}>{html.escape(t)}</text>')
    out.append('</svg>')
    return '\n'.join(out)


def oggi() -> str:
    return datetime.date.today().strftime('%d/%m/%Y')
