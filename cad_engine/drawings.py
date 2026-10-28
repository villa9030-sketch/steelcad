"""Tavole: il disegno del pezzo, dello sviluppo e dell'assieme, impaginato su un foglio con cartiglio.

Un foglio è una lista di primitive in mm sul foglio (linee, polilinee, cerchi, testi, su layer). Da lì escono il DXF
(ezdxf), il PDF (scritto qui, senza librerie in più) e l'SVG per l'anteprima.

Viste in proiezione europea (ISO, primo diedro): vista di fronte, sotto la vista dall'alto, a destra la vista da
sinistra; in alto a destra un'isometrica. Le linee nascoste sono tratteggiate. Quote: gli ingombri su ogni vista e i
fori (raggruppati per diametro, con filettature, svasature e inserti presi dagli sketch).
"""
from __future__ import annotations

import contextlib
import datetime
import math
from dataclasses import dataclass, field

import build123d as bd

FORMATI = {'A4': (297.0, 210.0), 'A3': (420.0, 297.0), 'A2': (594.0, 420.0)}
SCALE = [10, 5, 2, 1, 1 / 2, 1 / 2.5, 1 / 5, 1 / 10, 1 / 20, 1 / 25, 1 / 50, 1 / 100]
LAYER = {'contorno': (7, 0.5), 'nascoste': (8, 0.25), 'tangenti': (8, 0.18), 'piega': (1, 0.25), 'quote': (5, 0.18),
         'testo': (7, 0.25), 'cornice': (7, 0.5), 'cartiglio': (7, 0.25), 'tabella': (7, 0.25)}


class _Strato(list):
    """Una lista di primitive che ricorda di quale «oggetto» della tavola è ognuna (vista di fronte, una quota, il
    cartiglio…): così i ritocchi a mano (sposta, nascondi, cambia) prendono proprio quelle (23/10)."""
    def __init__(self, foglio, items=(), tag=None):
        super().__init__(items)
        self._f = foglio
        self.tag = list(tag) if tag is not None else [getattr(foglio, 'gruppo', '')] * len(self)

    def append(self, x):
        super().append(x)
        self.tag.append(self._f.gruppo)

    def extend(self, xs):
        xs = list(xs)
        super().extend(xs)
        self.tag.extend([self._f.gruppo] * len(xs))

    def tieni(self, ok):
        """Solo le primitive per cui ok(tag) è vero."""
        coppie = [(x, t) for x, t in zip(self, self.tag) if ok(t)]
        self[:] = [x for x, _ in coppie]
        self.tag = [t for _, t in coppie]


STRATI = ('linee', 'cerchi', 'testi', 'pieni', 'ombre')


@dataclass
class Foglio:
    formato: str = 'A3'
    titolo: str = ''
    linee: list = field(default_factory=list)       # (layer, [(x, y), ...]) polilinee aperte
    cerchi: list = field(default_factory=list)      # (layer, (x, y), r)
    testi: list = field(default_factory=list)       # (layer, (x, y), testo, altezza, allineamento 'l'|'c'|'r')
    pieni: list = field(default_factory=list)       # (layer, [(x, y), ...]) triangoli pieni (frecce)
    ombre: list = field(default_factory=list)       # ((r, g, b), [(x, y), ...]) facce ombreggiate, sotto le linee
    i_scala: int = -1                               # la scritta della scala nel cartiglio (si riscrive scalando)
    gruppo: str = ''                                # l'oggetto che si sta disegnando (vista:fronte, cartiglio…)
    elementi: dict = field(default_factory=dict)    # id → cosa è (quota coi suoi dati, vista con la sua scala…)
    immagini: list = field(default_factory=list)    # (percorso, x, y, w, h): il logo nel cartiglio
    chiave: str = ''                                # quale tavola è (pezzo, sviluppo…): i ritocchi stanno lì
    scala: float = 0.0                              # mm sul foglio per mm veri delle viste (0 = nessuna): per il DXF 1:1
    fattore: float = 1.0                            # quanto è stata rimpicciolita dal foglio dove è impaginata (A2)

    def __setattr__(self, nome, valore):
        if nome in STRATI and not isinstance(valore, _Strato):
            valore = _Strato(self, valore)
        object.__setattr__(self, nome, valore)

    @contextlib.contextmanager
    def oggetto(self, nome: str):
        prima = self.gruppo
        self.gruppo = nome
        try:
            yield
        finally:
            self.gruppo = prima

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
         'destra': ((1, 0, 0), (0, 0, 1)), 'iso': ((1, -1, 1), (0, 0, 1))}


_PROIEZIONI: dict = {}          # (forma, vista) → linee: le linee nascoste sono la parte lenta delle tavole


def proietta(shape, vista: str, veloce: bool = False) -> dict:
    """Spigoli visti, tangenti e nascosti della vista, come polilinee 2D (mm del pezzo), più i cerchi visti.
    La stessa forma (un pezzo non cambiato) non si riproietta: si rende quella già fatta."""
    chiave = (hash(shape), vista, veloce)
    gia = _PROIEZIONI.get(chiave)
    if gia is not None and gia[0].IsEqual(shape):
        return gia[1]
    res = _proietta(shape, vista, veloce)
    if len(_PROIEZIONI) > 200:
        _PROIEZIONI.pop(next(iter(_PROIEZIONI)))
    _PROIEZIONI[chiave] = (shape, res)
    return res


def _proietta(shape, vista: str, veloce: bool = False) -> dict:
    import build123d as bd
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer

    d, up = VISTE[vista]
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*d))
    ax.SetYDirection(gp_Dir(*up) if vista != 'iso' else _up_iso(d))
    if veloce:
        # assiemi (tanti pezzi, viti filettate): linee nascoste sulla maglia triangolata, molto più veloce del
        # calcolo esatto; a scala d'assieme non si vede la differenza
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.HLRBRep import HLRBRep_PolyAlgo, HLRBRep_PolyHLRToShape
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        scatola = Bnd_Box()
        BRepBndLib.Add_s(shape, scatola)
        diag = math.sqrt(scatola.SquareExtent()) if not scatola.IsVoid() else 100.0
        BRepMesh_IncrementalMesh(shape, max(0.02, diag * 4e-4), False, 0.3, True)
        palgo = HLRBRep_PolyAlgo(shape)
        palgo.Projector(HLRAlgo_Projector(ax))
        palgo.Update()
        h = HLRBRep_PolyHLRToShape()
        h.Update(palgo)
    else:
        algo = HLRBRep_Algo()
        algo.Add(shape)
        algo.Projector(HLRAlgo_Projector(ax))
        algo.Update()
        algo.Hide()
        h = HLRBRep_HLRToShape(algo)

    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
    from OCP.TopoDS import TopoDS  # noqa: F811

    def spigoli(comp):
        """Gli spigoli della vista, letti direttamente (senza oggetti build123d: con migliaia di spigolini la
        conversione era metà del tempo delle tavole, 22/10)."""
        out = []
        if comp.IsNull():
            return out
        ex = TopExp_Explorer(comp, TopAbs_EDGE)
        while ex.More():
            out.append(TopoDS.Edge(ex.Current()))
            ex.Next()
        return out

    def poly(e):
        """(polilinea 2D, cerchio intero o None); None se lo spigolo è lungo zero."""
        c = BRepAdaptor_Curve(e)
        u0, u1 = c.FirstParameter(), c.LastParameter()
        if e.Orientation() == TopAbs_REVERSED:
            u0, u1 = u1, u0
        tipo = c.GetType()
        if tipo == GeomAbs_Line:
            a, b = c.Value(u0), c.Value(u1)
            if a.Distance(b) < 1e-6:
                return None, None
            return [(a.X(), a.Y()), (b.X(), b.Y())], None
        a, m, b = c.Value(u0), c.Value((u0 + u1) / 2), c.Value(u1)
        corda = a.Distance(m) + m.Distance(b)
        if corda < 1e-6 and tipo != GeomAbs_Circle:
            return None, None
        cerchio = None
        if tipo == GeomAbs_Circle:
            ci = c.Circle()
            r = ci.Radius()
            lung = abs(u1 - u0) * r
            if lung < 1e-6:
                return None, None
            n = max(8, min(96, int(lung / 1.5)))
            if abs(abs(u1 - u0) - 2 * math.pi) < 1e-6:
                q = ci.Location()
                cerchio = ((q.X(), q.Y()), r)
        else:
            n = max(8, min(96, int(corda / 1.5)))
        return [(q.X(), q.Y()) for q in (c.Value(u0 + (u1 - u0) * k / n) for k in range(n + 1))], cerchio

    res = {'visti': [], 'tangenti': [], 'nascosti': [], 'cerchi': []}
    for comp in (h.VCompound(), h.OutLineVCompound()):
        for e in spigoli(comp):
            pl, cerchio = poly(e)
            if pl is None:
                continue
            res['visti'].append(pl)
            if cerchio:
                res['cerchi'].append(cerchio)
    for e in spigoli(h.Rg1LineVCompound()):
        pl, _ = poly(e)
        if pl is not None:
            res['tangenti'].append(pl)
    for comp in (h.HCompound(), h.OutLineHCompound()):
        for e in spigoli(comp):
            pl, _ = poly(e)
            if pl is not None:
                res['nascosti'].append(pl)
    pts = [p for k in ('visti', 'tangenti') for pl in res[k] for p in pl]
    if pts:
        res['bbox'] = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
    else:
        res['bbox'] = (0, 0, 1, 1)
    return res


def proietta_punto(vista: str, p) -> tuple:
    """Dove cade un punto 3D nella vista (stesse coordinate di proietta)."""
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.HLRAlgo import HLRAlgo_Projector
    d, up = VISTE[vista]
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*d))
    ax.SetYDirection(gp_Dir(*up) if vista != 'iso' else _up_iso(d))
    pr = HLRAlgo_Projector(ax)
    from OCP.gp import gp_Pnt2d
    q = gp_Pnt2d()
    pr.Project(gp_Pnt(*p), q)
    return (q.X(), q.Y())


def piano_catene(file: list, vista: str = 'fronte') -> list:
    """Quali file di aste diventano una catena di quote: [(fila, 0 = orizzontale | 1 = verticale, posizioni, passo)]."""
    out = []
    for fila in file or []:
        assi = fila['assi'] if isinstance(fila, dict) else fila
        pts = [proietta_punto(vista, p) for p in assi]
        for coord in (0, 1):
            lista = sorted(q[coord] for q in pts)
            if len(lista) < 3 or lista[-1] - lista[0] < 1e-6:
                continue
            passi = [b - a for a, b in zip(lista, lista[1:])]
            if min(passi) < 1e-6 or max(passi) - min(passi) > 0.5:
                continue                                   # non a passo costante (o aste una dietro l'altra)
            out.append((fila, coord, lista, sum(passi) / len(passi)))
    return out


def catene_di_passo(f: Foglio, v: dict, s: float, T, file: list, vista: str = 'fronte'):
    """Quote delle file di aste uguali a passo costante (sbarre di un cancello, ripiani di uno scaffale):
    dal bordo alla prima, la campata "n × passo", dall'ultima al bordo. file: [[punti 3D degli assi]]."""
    x0, y0, x1, y1 = v['bbox']
    giu, sx = 0, 0
    for fila, coord, lista, passo in piano_catene(file, vista):
        if True:
            n = len(lista) - 1
            if coord == 0:                                 # in orizzontale: catena sotto la quota d'ingombro
                giu += 1
                y = y0
                d = -7 - 9 * giu
                tappe = [x0] + lista + [x1]
                pezzi = [(tappe[0], tappe[1], None), (lista[0], lista[-1], f'{n} × {fmt(round(passo, 1))} = {fmt(round(passo * n, 1))}'),
                         (lista[-1], tappe[-1], None)]
                for a, b, t in pezzi:
                    if b - a > 1e-6:
                        quota(f, T((a, y)), T((b, y)), d, b - a, testo=t)
                if isinstance(fila, dict):              # la nota per l'officina: quanti, che profilo, passo e luce
                    luce = passo - fila.get('larghezza', 0)
                    A = T((lista[0], y))
                    f.text('testo', (A[0], A[1] + d * 1.0 - 6), f'{fila["nome"]}: {n + 1} × {fila["profilo"]}, passo '
                           f'{fmt(round(passo, 2))}, luce {fmt(round(luce, 2))}', 2.5)
                    giu += 1
            else:                                          # in verticale: a sinistra, fuori dalla quota d'altezza
                sx += 1
                x = x0
                d = 7 + 9 * sx
                tappe = [y0] + lista + [y1]
                pezzi = [(tappe[0], tappe[1], None), (lista[0], lista[-1], f'{n} × {fmt(round(passo, 1))} = {fmt(round(passo * n, 1))}'),
                         (lista[-1], tappe[-1], None)]
                for a, b, t in pezzi:
                    if b - a > 1e-6:
                        quota(f, T((x, a)), T((x, b)), d, b - a, testo=t)


def _up_iso(d):
    from OCP.gp import gp_Dir
    import numpy as np
    d = np.array(d, dtype=float) / np.linalg.norm(d)
    z = np.array([0, 0, 1.0])
    up = z - d * np.dot(z, d)
    up /= np.linalg.norm(up)
    return gp_Dir(*up)


# ------------------------------------------------------------------------------------------ foglio base
# i campi del cartiglio: chiave, etichetta. In ordine: le righe da tre caselle dal basso, poi titolo e azienda
CAMPI_CARTIGLIO = [('revisione', 'Revisione'), ('foglio', 'Foglio'), ('proiezione', 'Proiezione'),
                   ('disegnatore', 'Disegnatore'), ('data', 'Data'), ('scala', 'Scala'),
                   ('numero', 'N. disegno'), ('materiale', 'Materiale'), ('spessore_massa', 'Spessore / massa'),
                   ('cliente', 'Cliente'), ('commessa', 'Commessa'), ('tolleranze', 'Tolleranze generali'),
                   ('finitura', 'Trattamento / finitura')]
NUOVI_CARTIGLIO = ('cliente', 'commessa', 'tolleranze', 'finitura')     # si vedono se scritti (o se li spunti)


def _cornice(f: Foglio, campi: dict):
    with f.oggetto('cartiglio'):
        return _cornice_(f, campi)


def _tipo_documento(campi: dict) -> str:
    t = str(campi.get('titolo') or '').lower()
    for chiave, tipo in (('sviluppo', 'SVILUPPO'), ('esploso', 'ESPLOSO'), ('sezione', 'SEZIONE'),
                         ('distinta di taglio', 'DISTINTA DI TAGLIO')):
        if '— ' + chiave in t:
            return tipo
    return str(campi.get('tipo_doc') or 'DISEGNO DI PARTICOLARE')


def _cornice_(f: Foglio, campi: dict):
    """La cornice e il cartiglio in basso a destra (29/10, come il modello ISO che ha scelto Stefano), 180 mm:
    in alto la tabella delle revisioni (Rev., Data, Descrizione, Da); sotto, a sinistra azienda, titolo, n. disegno e
    revisione, disegnato e approvato, proiezione e «quote in mm»; a destra logo, scala, data, materiale, foglio di,
    tipo di documento. Cliente e commessa (se scritti) sotto il titolo, tolleranze con la nota sulle quote, trattamento
    col materiale."""
    W, H = f.size
    with f.oggetto('cornice'):
        f.line('cornice', (20, 10), (W - 10, 10), (W - 10, H - 10), (20, H - 10), (20, 10))
    L = 'cartiglio'
    f.scala = float(campi.get('_s') or 0)
    x0, x1, y0 = W - 190, W - 10, 10
    xr = x0 + 124.8                                    # la colonna di destra (logo, scala, data…)
    r_ = 7.5                                           # altezza di una riga
    # dal basso: proiezione | tipo · disegnato, approvato | foglio, di · n. disegno, rev. | data, materiale
    # · azienda, titolo | logo, scala · tabella revisioni
    y_pr, y_dis, y_num = y0, y0 + r_, y0 + 2 * r_
    y_az = y_num + 2 * r_
    y_rev = y_az + 3 * r_
    hr = 5.6
    y1 = y_rev + 4 * hr

    def cella(x, y, w, h, etichetta, valore='', hv=2.6, scala=False):
        f.text(L, (x + 1.2, y + h - 2.2), etichetta.upper(), 1.5)
        if valore not in (None, ''):
            if scala:
                f.i_scala = len(f.testi)
            f.text(L, (x + 1.2, y + 1.3), _taglia(str(valore), w, hv), hv)
    # i bordi
    f.line(L, (x0, y0), (x0, y1), (x1, y1))
    for y in (y_dis, y_num, y_az, y_rev):
        f.line(L, (x0, y), (x1, y))
    f.line(L, (xr, y0), (xr, y_rev))
    # tabella revisioni
    col = [x0, x0 + 24.9, x0 + 59.9, x0 + 154.8, x1]
    for k in range(1, 4):
        f.line(L, (x0, y_rev + k * hr), (x1, y_rev + k * hr))
    for x in col[1:-1]:
        f.line(L, (x, y_rev), (x, y1))
    for x, t in zip(col, ('Rev.', 'Data', 'Descrizione', 'Da')):
        f.text(L, (x + 1.2, y1 - hr + 1.8), t.upper(), 1.5)
    revs = [r for r in (campi.get('revisioni') or []) if isinstance(r, dict) and any(str(v).strip() for v in r.values())][-3:]
    for k, r in enumerate(reversed(revs)):             # la più nuova in alto
        y = y1 - (k + 2) * hr
        for (xa, xb), chiave in zip(zip(col, col[1:]), ('rev', 'data', 'descrizione', 'da')):
            f.text(L, (xa + 1.2, y + 1.6), _taglia(str(r.get(chiave, '') or ''), xb - xa, 2.2), 2.2)
    # azienda e titolo | logo e scala
    f.line(L, (x0, y_az + 2 * r_), (xr, y_az + 2 * r_))
    cella(x0, y_az + 2 * r_, xr - x0, r_, 'Azienda', campi.get('azienda', ''))
    f.text(L, (x0 + 1.2, y_az + 2 * r_ - 2.2), 'TITOLO', 1.5)
    f.text(L, (x0 + 1.2, y_az + 5.2), _taglia(str(campi.get('titolo', '')), xr - x0, 4.2), 4.2)
    extra = ' · '.join(f'{et} {campi[k]}' for k, et in (('cliente', 'Cliente'), ('commessa', 'Commessa'))
                       if str(campi.get(k) or '').strip())
    if extra:
        f.text(L, (x0 + 1.2, y_az + 1.3), _taglia(extra, xr - x0, 2.2), 2.2)
    f.line(L, (xr, y_az + r_), (x1, y_az + r_))
    f.text(L, (xr + 1.2, y_az + 3 * r_ - 2.2), 'LOGO', 1.5)
    logo = campi.get('logo')
    if logo:
        f.immagini.append((logo, xr + 4, y_az + r_ + 1.2, x1 - xr - 8, 2 * r_ - 4.6))
    cella(xr, y_az, x1 - xr, r_, 'Scala', campi.get('scala', ''), scala=True)
    # n. disegno e revisione | data e materiale
    xrev = x0 + 94.9
    f.line(L, (xrev, y_num), (xrev, y_az))
    f.text(L, (x0 + 1.2, y_az - 2.2), 'N. DISEGNO', 1.5)
    f.text(L, (x0 + 1.2, y_num + 3.5), _taglia(str(campi.get('numero', '') or ''), xrev - x0, 4.2), 4.2)
    f.text(L, (xrev + 1.2, y_az - 2.2), 'REV.', 1.5)
    f.text(L, (xrev + 1.2, y_num + 3.5), _taglia(str(campi.get('revisione', '') or ''), xr - xrev, 4.2), 4.2)
    f.line(L, (xr, y_num + r_), (x1, y_num + r_))
    cella(xr, y_num + r_, x1 - xr, r_, 'Data', campi.get('data', ''))
    mat = ' · '.join(str(campi[k]) for k in ('materiale', 'spessore_massa', 'finitura') if str(campi.get(k) or '').strip())
    cella(xr, y_num, x1 - xr, r_, 'Materiale', mat, hv=2.2)
    # disegnato, approvato | foglio di
    xapp = x0 + 64.9
    f.line(L, (xapp, y_dis), (xapp, y_num))
    cella(x0, y_dis, xapp - x0, r_, 'Disegnato', campi.get('disegnatore', ''))
    cella(xapp, y_dis, xr - xapp, r_, 'Approvato', campi.get('approvato', ''))
    fg = str(campi.get('foglio') or '').split('/')
    xof = x0 + 154.8
    f.line(L, (xof, y_dis), (xof, y_num))
    cella(xr, y_dis, xof - xr, r_, 'Foglio', fg[0] if fg else '')
    cella(xof, y_dis, x1 - xof, r_, 'Di', fg[1] if len(fg) > 1 else '')
    # proiezione (europea, ISO E: il tronco di cono a sinistra, i cerchi a destra) | tipo di documento
    xpr = x0 + 44.9
    f.line(L, (xpr, y_pr), (xpr, y_dis))
    f.text(L, (x0 + 1.2, y_pr + r_ - 2.2), 'PROIEZIONE', 1.5)
    cy = y_pr + 2.6
    f.line(L, (x0 + 22, cy - 1.2), (x0 + 22, cy + 1.2), (x0 + 28, cy + 2.2), (x0 + 28, cy - 2.2), (x0 + 22, cy - 1.2))
    f.cerchi.append((L, (x0 + 36, cy), 2.2))
    f.cerchi.append((L, (x0 + 36, cy), 1.2))
    nota = 'QUOTE IN mm – NON SCALARE IL DISEGNO'
    if str(campi.get('tolleranze') or '').strip():
        f.text(L, (xpr + 1.2, y_pr + 4.4), _taglia(nota, xr - xpr, 1.8), 1.8)
        f.text(L, (xpr + 1.2, y_pr + 1.3), _taglia('Tolleranze: ' + str(campi['tolleranze']), xr - xpr, 1.8), 1.8)
    else:
        f.text(L, (xpr + 1.2, y_pr + 2.8), _taglia(nota, xr - xpr, 2.0), 2.0)
    cella(xr, y_pr, x1 - xr, r_, 'Tipo documento', _tipo_documento(campi), hv=2.4)
    if campi.get('note'):
        with f.oggetto('note_cartiglio'):
            f.text('testo', (22, 13), _taglia('Note: ' + campi['note'], x0 - 26, 2.5), 2.5)   # non sotto il cartiglio
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


def quota(f: Foglio, a, b, distanza: float, valore: float, h=2.8, prefisso='', testo=None, nome=None):
    """Quota lineare tra a e b (foglio), spostata di "distanza" a sinistra di a→b; scrive il valore vero. Ha un nome
    (quello dato, se no l'oggetto in cui sta + un numero) e si ricorda i suoi dati: la si può ritoccare dopo."""
    if nome is None:
        conta = f.__dict__.setdefault('_nq', {})
        conta[f.gruppo] = conta.get(f.gruppo, 0) + 1
        nome = f'{f.gruppo or "foglio"}/q{conta[f.gruppo]}'
    f.elementi[nome] = {'kind': 'quota', 'a': list(map(float, a)), 'b': list(map(float, b)), 'distanza': float(distanza),
                        'valore': float(valore), 'h': float(h), 'prefisso': prefisso, 'testo': testo, 'padre': f.gruppo}
    with f.oggetto(nome):
        _disegna_quota(f, a, b, distanza, valore, h, prefisso, testo)


def _disegna_quota(f: Foglio, a, b, distanza: float, valore: float, h=2.8, prefisso='', testo=None, freccia=None):
    """Tutto in proporzione al testo (h 2,8 → frecce 2,5): ingrandendo il testo crescono anche frecce e staccate;
    «freccia» = la lunghezza delle frecce, se la vuoi diversa (24/10). Quota corta: frecce fuori che puntano dentro
    e, se il numero non ci sta, il numero di fianco, come in ogni CAD."""
    u = h / 2.8
    Lf = float(freccia) if freccia else 2.5 * u
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    A = (ax + nx * distanza, ay + ny * distanza)
    B = (bx + nx * distanza, by + ny * distanza)
    s = 1.5 * u if distanza > 0 else -1.5 * u
    f.line('quote', (ax + nx * s * 0.6, ay + ny * s * 0.6), (A[0] + nx * s, A[1] + ny * s))
    f.line('quote', (bx + nx * s * 0.6, by + ny * s * 0.6), (B[0] + nx * s, B[1] + ny * s))
    scritta = testo if testo is not None else prefisso + fmt(valore)
    fuori = L < 2 * Lf + u                             # le frecce non ci stanno dentro: fuori, puntate verso dentro
    if fuori:
        e = Lf + 2 * u
        f.line('quote', (A[0] - ux * e, A[1] - uy * e), (B[0] + ux * e, B[1] + uy * e))
        _freccia(f, A, (ux, uy), L=Lf)
        _freccia(f, B, (-ux, -uy), L=Lf)
    else:
        f.line('quote', A, B)
        _freccia(f, A, (-ux, -uy), L=Lf)
        _freccia(f, B, (ux, uy), L=Lf)
    lato = 1.2 * u * (1 if distanza > 0 else -2.2)
    c = 0.0
    w = len(scritta) * h * 0.55
    if L < w + 2 * u:                                  # il numero non ci sta tra le linee: di fianco, dopo B
        c = L / 2 + (Lf + 2 * u if fuori else 0) + u + w / 2
    m = ((A[0] + B[0]) / 2 + ux * c + nx * lato, (A[1] + B[1]) / 2 + uy * c + ny * lato)
    f.text('quote', m, scritta, h, 'c')
    if abs(uy) > 0.5:                                      # quota verticale: testo ruotato nei formati che lo sanno fare
        f.testi[-1] = ('quote', m, scritta, h, 'cv')


_OMBRE: dict = {}


def ombre_iso(shape) -> list:
    """Le facce del pezzo per l'isometrica ombreggiata (23/10, «polish» delle tavole): triangoli visti, dal più
    lontano al più vicino, colorati con la luce dall'alto (acciaio chiaro, come le icone). Coordinate della vista
    'iso' di proietta. Si rendono [((r, g, b), [(x, y)] * 3)]."""
    import numpy as np
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRep import BRep_Tool
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    chiave = hash(shape)
    gia = _OMBRE.get(chiave)
    if gia is not None and gia[0].IsEqual(shape):
        return gia[1]
    d = np.array(VISTE['iso'][0], dtype=float)
    d /= np.linalg.norm(d)
    upd = _up_iso(VISTE['iso'][0])
    up = np.array([upd.X(), upd.Y(), upd.Z()])
    xd = np.cross(up, d)
    luce = d * 0.9 + np.array([0, 0, 1.0]) * 1.1 - xd * 0.45
    luce /= np.linalg.norm(luce)
    scuro, chiaro = np.array([0.50, 0.55, 0.61]), np.array([0.96, 0.97, 0.98])
    scatola = Bnd_Box()
    BRepBndLib.Add_s(shape, scatola)
    diag = math.sqrt(scatola.SquareExtent()) if not scatola.IsVoid() else 100.0
    BRepMesh_IncrementalMesh(shape, max(diag / 600, 0.05), False, 0.35, True)
    tri = []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        fa = TopoDS.Face(ex.Current())
        ex.Next()
        loc = TopLoc_Location()
        t = BRep_Tool.Triangulation_s(fa, loc)
        if t is None:
            continue
        tr = loc.Transformation()
        P = np.array([[q.X(), q.Y(), q.Z()] for q in (t.Node(i).Transformed(tr) for i in range(1, t.NbNodes() + 1))])
        idx = np.array([t.Triangle(i).Get() for i in range(1, t.NbTriangles() + 1)]) - 1
        if fa.Orientation() == TopAbs_REVERSED:
            idx = idx[:, [0, 2, 1]]
        A, B, C = P[idx[:, 0]], P[idx[:, 1]], P[idx[:, 2]]
        n = np.cross(B - A, C - A)
        ln = np.linalg.norm(n, axis=1)
        ok = (ln > 1e-12)
        n[ok] /= ln[ok, None]
        vis = ok & (n @ d > 1e-4)                         # solo quelli girati verso chi guarda
        lum = np.clip(n @ luce, 0, 1) * 0.75 + 0.25
        prof = (A + B + C) @ d / 3
        for i in np.nonzero(vis)[0]:
            col = tuple(float(x) for x in scuro + (chiaro - scuro) * lum[i])
            pts = [(float(q @ xd), float(q @ up)) for q in (A[i], B[i], C[i])]
            tri.append((float(prof[i]), col, pts))
    tri.sort(key=lambda x: x[0])
    res = [(c, p) for _, c, p in tri]
    if len(_OMBRE) > 50:
        _OMBRE.pop(next(iter(_OMBRE)))
    _OMBRE[chiave] = (shape, res)
    return res


def _metti_ombre(f: 'Foglio', ombre: list, T):
    """Le facce ombreggiate nella vista già messa (T: la stessa trasformazione delle sue linee)."""
    f.ombre.extend((c, [T(p) for p in pts]) for c, pts in ombre)


def _metti_vista(f: Foglio, v: dict, s: float, ox: float, oy: float, quote_su=True, valori=None):
    """Disegna la vista con scala s, con l'angolo in basso a sinistra del suo ingombro in (ox, oy)."""
    x0, y0, x1, y1 = v['bbox']
    T = lambda p: (ox + (p[0] - x0) * s, oy + (p[1] - y0) * s)  # noqa: E731
    if f.gruppo.startswith('vista:'):
        f.elementi[f.gruppo] = {'kind': 'vista', 'T': [s, ox - x0 * s, oy - y0 * s], 'label': ETICHETTE_VISTE.get(f.gruppo, f.gruppo)}
    for k, layer in (('visti', 'contorno'), ('tangenti', 'tangenti'), ('nascosti', 'nascoste')):
        for pl in v[k]:
            f.line(layer, *[T(p) for p in pl])
    w, h = (x1 - x0) * s, (y1 - y0) * s
    if quote_su:
        vw, vh = valori if valori else (x1 - x0, y1 - y0)
        quota(f, (ox, oy), (ox + w, oy), -7, vw)                 # larghezza sotto
        quota(f, (ox, oy), (ox, oy + h), 7, vh)                  # altezza a sinistra
    return T, w, h


ETICHETTE_VISTE = {'vista:fronte': 'Vista di fronte', 'vista:alto': 'Vista dall’alto', 'vista:sinistra': 'Vista da sinistra',
                   'vista:destra': 'Vista da destra', 'vista:iso': 'Isometrica', 'vista:esploso': 'Vista esplosa'}

MAX_RICHIAMI = 5          # più tipi di foro di così: lettere sui fori e tabella fori (i richiami si accavallano)


def _gruppi_fori(v: dict, etichette: dict, gia: set) -> list:
    """I fori di una vista per tipo: [(testo, diametro, centri)], senza quelli già visti in un'altra vista."""
    gruppi: dict = {}
    for c, r in v['cerchi']:
        k = round(2 * r, 3)
        gruppi.setdefault(k, []).append(c)
    out = []
    for k, cs in sorted(gruppi.items()):
        if k < 0.5:
            continue
        uniq = []
        for c in cs:
            if not any(math.dist(c, u) < 1e-3 for u in uniq):
                uniq.append(c)
        base = etichette.get(k, f'Ø{fmt(k)}')
        if base in gia:
            continue
        gia.add(base)
        out.append((base, k, uniq))
    return out


def _lettera(i: int) -> str:
    """A … Z, poi AA, AB …"""
    return chr(65 + i) if i < 26 else chr(64 + i // 26) + chr(65 + i % 26)


def _fori_a_lettere(f: Foglio, gruppi: list, s: float, etichette: dict, prima: int) -> list:
    """Una lettera accanto a ogni foro; ritorna le righe della tabella fori [lettera, quanti, testo]."""
    righe = []
    for j, (base, k, uniq, T) in enumerate(gruppi):
        L = _lettera(prima + j)
        r = k / 2 * s
        nom = etichette.get(('nominale', k))
        for u in uniq:
            pu = T(u)
            if nom:
                rn = nom / 2 * s
                f.line('quote', *[(pu[0] + rn * math.cos(math.radians(a)), pu[1] + rn * math.sin(math.radians(a)))
                                  for a in range(100, 371, 10)])
            f.text('quote', (pu[0] + r * 0.75 + 0.4, pu[1] + r * 0.75 + 0.4), L, 2.2)
        righe.append([L, str(len(uniq)), base])
    return righe


def _tabella_fori(f: Foglio, righe: list, x0: float, y0: float, x1: float) -> float:
    """La tabella fori sopra (x0, y0), in una o due colonne entro x1. Ritorna la y della cima."""
    h = 5.0
    larga = 84.0
    due = len(righe) > 14 and (x1 - x0) >= 2 * larga + 4
    meta = (len(righe) + 1) // 2 if due else len(righe)
    pezzi = [righe[:meta], righe[meta:]] if due else [righe]
    alto = (meta + 1) * h
    col = [0, 10, 20, larga]
    for i, pz in enumerate(pezzi):
        if pz:
            _tabella(f, x0 + i * (larga + 4), y0 + alto, col, [['Rif.', 'Q.tà', 'Foro']] + pz,
                     'TABELLA FORI' if i == 0 else None, h)
    return y0 + alto + 6


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
        nom = etichette.get(('nominale', k))
        if nom:                                        # filettato: 3/4 di cerchio sottile al diametro nominale (ISO 6410)
            rn = nom / 2 * s
            for u in uniq:
                pu = T(u)
                f.line('quote', *[(pu[0] + rn * math.cos(math.radians(a)), pu[1] + rn * math.sin(math.radians(a)))
                                  for a in range(100, 371, 10)])
        q = (p[0] + r * 0.7, p[1] + r * 0.7)
        e = (q[0] + 8, q[1] + 8)
        f.line('quote', q, e, (e[0] + 2 + len(testo) * 1.6, e[1]))
        _freccia(f, q, (q[0] - e[0], q[1] - e[1]))
        f.text('quote', (e[0] + 1, e[1] + 0.8), testo, 2.6)


def _centri_fori(v: dict) -> tuple:
    """Le x e le y diverse dei centri dei fori visti in pianta (una volta sola per svasature e cerchi doppi)."""
    xs, ys = [], []
    for c, r in v['cerchi']:
        if 2 * r < 0.5:
            continue
        if not any(abs(c[0] - x) < 0.05 for x in xs):
            xs.append(c[0])
        if not any(abs(c[1] - y) < 0.05 for y in ys):
            ys.append(c[1])
    return sorted(xs), sorted(ys)


def _catene_fori(f: Foglio, v: dict, T, xs, ys):
    """Catene di quote dei fori: sotto la vista (dal bordo sinistro) e a sinistra (dal bordo di sotto)."""
    x0, y0, x1, y1 = v['bbox']
    tappe = [x0] + [x for x in xs if x0 + 1e-6 < x < x1 - 1e-6]
    for a, b in zip(tappe, tappe[1:]):
        quota(f, T((a, y0)), T((b, y0)), -18, b - a)
    tappe = [y0] + [y for y in ys if y0 + 1e-6 < y < y1 - 1e-6]
    for a, b in zip(tappe, tappe[1:]):
        quota(f, T((x0, a)), T((x0, b)), 18, b - a)


def _scala_scelta(v) -> float | None:
    """«1:2», «2:1», «1:1» → il fattore; «auto» o vuoto → None."""
    try:
        a, b = str(v).replace(' ', '').replace(',', '.').split(':')
        return float(a) / float(b)
    except (ValueError, ZeroDivisionError):
        return None


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
                try:
                    out[('nominale', d)] = float(str(h['M']).upper().lstrip('M'))
                except ValueError:
                    pass
            elif h.get('tipo') == 'svasato':
                out[d] = f'Ø{fmt(d)} svasato Ø{fmt(float(h["D"]))}×{fmt(float(h.get("angolo", 90)))}°'
                out[round(float(h['D']), 3)] = out[d]           # dalla parte svasata si vede il cerchio grande
            elif h.get('tipo') == 'inserto':
                out[d] = f'Ø{fmt(d)} per inserto {h["codice"]}'
    return out


# le tavole si impaginano in A2 e si stampano scalate sul foglio scelto: le scale provate sono quelle che sul
# foglio stampato diventano scale normali (1:10 su un A3 è 1:7,07 nell'A2 di lavoro)
FATTORE_USCITA = 1.0


def _scegli_scala(dims: list, area_w: float, area_h: float) -> float:
    """dims: (larghezza totale, altezza totale) in mm del pezzo, già con le viste affiancate."""
    for s0 in SCALE:
        s = s0 / FATTORE_USCITA
        if dims[0] * s <= area_w and dims[1] * s <= area_h:
            return s
    return SCALE[-1] / FATTORE_USCITA


# ------------------------------------------------------------------------------------------ le tavole
def _zone_libere(area, cart, m=8):
    """Le due zone dove si può disegnare senza toccare il cartiglio: sopra di lui (tutta la larghezza) e alla sua
    sinistra (tutta l'altezza). Il cartiglio ha misura fissa: su un A4 occupa più di metà foglio in larghezza."""
    return [(area[0], cart[3] + m, area[2], area[3]), (area[0], area[1], cart[0] - m, area[3])]


def _taglia_cartiglio(r, cart, m=8):
    """Un rettangolo libero, ristretto perché non entri nel cartiglio (si alza sopra o si stringe a sinistra)."""
    x0, y0, x1, y1 = r
    if x1 <= cart[0] - m or y0 >= cart[3] + m:
        return r
    alto = (x0, max(y0, cart[3] + m), x1, y1)
    sinistra = (x0, y0, min(x1, cart[0] - m), y1)
    area = lambda q: max(0, q[2] - q[0]) * max(0, q[3] - q[1])  # noqa: E731
    return max((alto, sinistra), key=area)


def _posto_libero(f: Foglio, pa, pb, verso: int) -> float:
    """La prima distanza (7, 14, 21… mm) dove la linea di quota tra pa e pb non cade su una quota già sul foglio."""
    ux, uy = pb[0] - pa[0], pb[1] - pa[1]
    lu = math.hypot(ux, uy) or 1
    ux, uy = ux / lu, uy / lu
    nx, ny = -uy, ux
    for j in range(1, 12):
        d = verso * 7 * j
        ax, ay = pa[0] + nx * d, pa[1] + ny * d
        libero = True
        for layer, pts in f.linee:
            if layer != 'quote' or len(pts) != 2:
                continue
            (x0, y0), (x1, y1) = pts
            vx, vy = x1 - x0, y1 - y0
            lv = math.hypot(vx, vy)
            if lv < 1e-6 or abs(vx * uy - vy * ux) / lv > 0.05:
                continue                                    # non parallela
            if abs((x0 - ax) * nx + (y0 - ay) * ny) > 3.5:
                continue                                    # parallela ma lontana
            t0, t1 = sorted(((x0 - ax) * ux + (y0 - ay) * uy, (x1 - ax) * ux + (y1 - ay) * uy))
            if t1 > -2 and t0 < lu + 2:                      # si sovrappongono
                libero = False
                break
        if libero:
            return 7 * j
    return 7 * 12


def _quote_a_mano(f: Foglio, quote: list, viste: dict):
    """Le quote messe col tasto Quota sul pezzo (22/10): ognuna nella prima vista (fronte, alto, sinistra) dove il
    tratto si vede in vera lunghezza, staccata dal pezzo verso fuori, oltre le quote automatiche. viste: nome -> (T, centro della vista sul foglio)."""
    for q in quote or []:
        if str(q.get('testo', '')).startswith('Ø'):
            continue                                        # i fori hanno già le loro note
        if q.get('v'):
            _angolo_a_mano(f, q, viste)                     # 28/10: anche gli angoli misurati sul pezzo
            continue
        a, b = q.get('a'), q.get('b')
        if not a or not b:
            continue
        d = [b[i] - a[i] for i in range(3)]
        L = math.sqrt(sum(x * x for x in d))
        if L < 1e-6:
            continue
        for nome in ('fronte', 'alto', 'sinistra', 'destra'):
            if nome not in viste:
                continue
            dirv = VISTE[nome][0]
            nd = math.sqrt(sum(x * x for x in dirv))
            if abs(sum(d[i] * dirv[i] for i in range(3))) / (L * nd) > 1e-4:
                continue                                    # di sbieco in questa vista: non è vera lunghezza
            T, (cx, cy) = viste[nome]
            pa, pb = T(proietta_punto(nome, a)), T(proietta_punto(nome, b))
            # dalla parte opposta al centro della vista, una più in là dell'altra se sono dalla stessa parte
            mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
            ux, uy = pb[0] - pa[0], pb[1] - pa[1]
            lu = math.hypot(ux, uy) or 1
            nx, ny = -uy / lu, ux / lu
            verso = 1 if (mx - cx) * nx + (my - cy) * ny >= 0 else -1
            quota(f, pa, pb, verso * _posto_libero(f, pa, pb, verso), L)
            break


def _angolo_a_mano(f: Foglio, q: dict, viste: dict):
    """Un angolo misurato sul pezzo (tre punti: un lato, il vertice, l'altro lato): nella prima vista dove il suo piano
    è di fronte (si vede in vero), con l'arco e i gradi."""
    a, v, b = q.get('a'), q.get('v'), q.get('b')
    if not (a and v and b):
        return
    u = [a[i] - v[i] for i in range(3)]
    w = [b[i] - v[i] for i in range(3)]
    n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
    ln = math.sqrt(sum(x * x for x in n))
    if ln < 1e-9:
        return
    for nome in ('fronte', 'alto', 'sinistra', 'destra'):
        if nome not in viste:
            continue
        dirv = VISTE[nome][0]
        nd = math.sqrt(sum(x * x for x in dirv))
        if abs(abs(sum(n[i] * dirv[i] for i in range(3))) / (ln * nd) - 1) > 1e-4:
            continue                                        # il piano dell'angolo è di sbieco in questa vista
        T, _ = viste[nome]
        A, V, B = (T(proietta_punto(nome, p)) for p in (a, v, b))
        k = f.fattore
        R = max(8 * k, min(25 * k, 0.6 * min(math.dist(A, V), math.dist(B, V))))
        cos_ = sum(u[i] * w[i] for i in range(3)) / (math.sqrt(sum(x * x for x in u)) * math.sqrt(sum(x * x for x in w)))
        gradi = math.degrees(math.acos(max(-1.0, min(1.0, cos_))))
        disegna_angolo(f, A, V, B, R, fmt(round(gradi, 1)) + '°', k)
        return


def disegna_angolo(f: Foglio, A, V, B, R, testo, k, hq=None, frq=None):
    """La quota d'angolo sul foglio: arco di raggio R attorno al vertice V tra i lati VA e VB, frecce e gradi."""
    hq = hq or 2.8 * k
    frq = frq or 2.5 * hq / 2.8
    a1 = math.atan2(A[1] - V[1], A[0] - V[0])
    a2 = math.atan2(B[1] - V[1], B[0] - V[0])
    da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi        # l'angolo più piccolo, col suo verso
    if abs(da) < 1e-6:
        return
    n = max(8, int(abs(da) / math.radians(5)))
    arco = [(V[0] + R * math.cos(a1 + da * j / n), V[1] + R * math.sin(a1 + da * j / n)) for j in range(n + 1)]
    sg = 1 if da > 0 else -1
    # le linee di richiamo, se l'arco va oltre i lati disegnati
    for ang, P0 in ((a1, A), (a2, B)):
        if math.dist(V, P0) < R:
            f.line('quote', P0, (V[0] + (R + 1.5 * k) * math.cos(ang), V[1] + (R + 1.5 * k) * math.sin(ang)))
    f.line('quote', *arco)
    _freccia(f, arco[0], (math.sin(a1) * sg, -math.cos(a1) * sg), L=frq)      # le punte verso fuori dall'arco
    _freccia(f, arco[-1], (-math.sin(a2) * sg, math.cos(a2) * sg), L=frq)
    am = a1 + da / 2
    f.text('quote', (V[0] + (R + 1.2 * k) * math.cos(am), V[1] + (R + 1.2 * k) * math.sin(am)), testo, hq,
           'l' if math.cos(am) > 0.3 else 'r' if math.cos(am) < -0.3 else 'c')


def _saldature_3d(f: Foglio, saldature: list, viste: dict):
    """Le saldature segnate sul pezzo (28/10): il simbolo ISO 2553 con la freccia sullo spigolo, nella prima vista
    dove lo spigolo non si vede di punta; il gomito verso fuori dalla vista."""
    from .tavole_ritocchi import _saldatura
    k = f.fattore
    hq, frq = 2.8 * k, 2.5 * k
    usati: list = []
    for w in saldature or []:
        m, d = w.get('punto'), w.get('dir')
        if not m:
            continue
        for nome in ('fronte', 'alto', 'sinistra', 'destra'):
            if nome not in viste:
                continue
            dirv = VISTE[nome][0]
            nd = math.sqrt(sum(x * x for x in dirv))
            if d and abs(sum(d[i] * dirv[i] for i in range(3))) / nd > 0.98:
                continue                                    # lo spigolo si vede di punta
            T, (cx, cy) = viste[nome]
            P0 = T(proietta_punto(nome, m))
            sx = 1 if P0[0] >= cx else -1
            sy = 1 if P0[1] >= cy else -1
            dy = sy * 12 * k
            while any(math.dist((P0[0] + sx * 15 * k, P0[1] + dy), u) < 7 * k for u in usati):
                dy += sy * 7 * k                            # più saldature vicine: i gomiti uno sopra l'altro
            K = (P0[0] + sx * 15 * k, P0[1] + dy)
            usati.append(K)
            Fn = (K[0] + sx * 20 * k, K[1])
            _saldatura(f, P0, K, Fn, sx, {'tipo': w.get('tipo', 'angolo'), 'a': w.get('a', '')}, k, hq, frq)
            break


def tavola_pezzo(shape, campi: dict, etichette: dict | None = None, formato: str = 'A3', file_passo=None,
                 quote_mano: list | None = None, saldature: list | None = None) -> Foglio:
    """Fronte, alto, sinistra (europea) + isometrica, con ingombri e note dei fori. Le viste vanno nella zona
    libera più grande (sopra o a sinistra del cartiglio), con il posto per le quote e le catene di passo."""
    f = Foglio(formato, campi.get('titolo', ''))
    area, cart = _cornice(f, campi)
    # 28/10: il fianco si sceglie (da sinistra o da destra) e l'isometrica si può togliere
    fianco = 'destra' if str(campi.get('fianco') or '') == 'destra' else 'sinistra'
    con_iso = str(campi.get('isometrica', 'sì')).lower() not in ('no', 'false', '0')
    v = {k: proietta(shape, k) for k in ('fronte', 'alto', fianco) + (('iso',) if con_iso else ())}
    v['sinistra'] = v[fianco]                    # nel resto della tavola «il fianco»
    wF, hF = v['fronte']['bbox'][2] - v['fronte']['bbox'][0], v['fronte']['bbox'][3] - v['fronte']['bbox'][1]
    wL = v['sinistra']['bbox'][2] - v['sinistra']['bbox'][0]
    hL = v['sinistra']['bbox'][3] - v['sinistra']['bbox'][1]
    hT = v['alto']['bbox'][3] - v['alto']['bbox'][1]
    piano = piano_catene(file_passo) if file_passo else []
    n_or = sum(1 for _, c, _, _ in piano if c == 0)
    n_ve = sum(1 for _, c, _, _ in piano if c == 1)
    gL = 16 + 9 * n_ve                     # a sinistra: quota d'altezza (+ catene verticali)
    gS = 26                                # tra fronte e fianco: la quota d'altezza del fianco
    gF = 22 + 18 * n_or                    # sotto la fronte: quota di larghezza, catene di passo e note, titolo dell'alto
    gT = 14                                # sotto l'alto: la sua quota
    gTop = 10                              # sopra la fronte: il titolo
    # quote dei fori nella vista dall'alto: catene dall'angolo del pezzo (se i fori non sono troppi)
    fx, fy = _centri_fori(v['alto'])
    quote_fori = str(campi.get('quote_fori', 'sì')).lower() not in ('no', 'false', '0') and 0 < max(len(fx), len(fy)) <= 15
    if quote_fori:
        gT += 10
        gL += 10

    def scala_zona(r):
        aw = (r[2] - r[0]) - gL - gS - 6
        ah = (r[3] - r[1]) - gT - gF - gTop
        if aw <= 0 or ah <= 0:
            return 0, 0
        sc = _scegli_scala((wF + wL, max(hF, hL) + hT), aw, ah)
        ok = (wF + wL) * sc <= aw and (max(hF, hL) + hT) * sc <= ah
        return (sc if ok else sc * 0.999), aw * ah
    zona = max(_zone_libere(area, cart), key=lambda r: scala_zona(r))
    s = scala_zona(zona)[0] or SCALE[-1]
    aw_z, ah_z = (zona[2] - zona[0]) - gL - gS - 6, (zona[3] - zona[1]) - gT - gF - gTop
    if (wF + wL) * s > aw_z or (max(hF, hL) + hT) * s > ah_z:     # non entra neanche all'1:100: scala fuori serie
        s = max(1e-3, min(aw_z / max(wF + wL, 1e-6), ah_z / max(max(hF, hL) + hT, 1e-6)))
    fissa = _scala_scelta(campi.get('scala_fissa'))
    if fissa:                                         # scelta a mano (se non entra nel foglio, resta quella)
        s = fissa / FATTORE_USCITA               # la scala vale sul foglio stampato
    campi = {**campi, 'scala': scala_testo(s), '_s': s}
    f.testi = []
    f.linee, f.cerchi, f.pieni = [], [], []
    f.elementi, f.immagini = {}, []
    f.__dict__.pop('_nq', None)
    area, cart = _cornice(f, campi)
    if fianco == 'destra':                       # proiezione europea: la vista da destra sta a sinistra della fronte
        xL = zona[0] + gL
        ox = xL + wL * s + gS
    else:
        ox = zona[0] + gL
        xL = ox + wF * s + gS
    oyT = zona[1] + gT
    oyF = oyT + hT * s + gF
    with f.oggetto('vista:fronte'):
        TF, _, _ = _metti_vista(f, v['fronte'], s, ox, oyF)
        if file_passo:
            catene_di_passo(f, v['fronte'], s, TF, file_passo)
    with f.oggetto('vista:alto'):
        TT, _, _ = _metti_vista(f, v['alto'], s, ox, oyT)
        if quote_fori:
            _catene_fori(f, v['alto'], TT, fx, fy)
    with f.oggetto(f'vista:{fianco}'):
        TL, _, _ = _metti_vista(f, v['sinistra'], s, xL, oyF)
    for vista, nome, (x, y) in (('fronte', 'VISTA DI FRONTE', (ox, oyF + hF * s + 4)), ('alto', 'VISTA DALL’ALTO', (ox, oyT + hT * s + 4)),
                                (fianco, f'VISTA DA {fianco.upper()}', (xL, oyF + hL * s + 4))):
        with f.oggetto(f'vista:{vista}/titolo'):
            f.text('testo', (x, y), nome, 2.5)
    viste_3d = {'fronte': (TF, (ox + wF * s / 2, oyF + hF * s / 2)), 'alto': (TT, (ox + wF * s / 2, oyT + hT * s / 2)),
                fianco: (TL, (xL + wL * s / 2, oyF + hL * s / 2))}
    if quote_mano:
        with f.oggetto('quote3d'):
            _quote_a_mano(f, quote_mano, viste_3d)
    if saldature:
        with f.oggetto('saldature3d'):
            _saldature_3d(f, saldature, viste_3d)
    gia: set = set()
    et = etichette or {}
    # tanti tipi di foro: una lettera su ogni foro e la tabella sopra il cartiglio (se lì non ci sono le viste)
    prova: set = set()
    tutti = [(b, k, u, T) for vista, T in ((v['alto'], TT), (v['fronte'], TF), (v['sinistra'], TL))
             for b, k, u in _gruppi_fori(vista, et, prova)]
    # il posto: sopra il cartiglio, fino sotto le viste (o fino in cima se le viste stanno tutte a sinistra)
    viste_dx = max(xL + wL * s, ox + wF * s)
    sotto_viste = (oyF - 22) if viste_dx > cart[0] - 4 else area[3]
    if oyT - gT < cart[3] + 8 and ox - gL < area[2] and viste_dx > cart[0] - 4:
        sotto_viste = cart[3]                              # le viste scendono fino al cartiglio: niente posto
    n_col = 2 if len(tutti) > 14 and area[2] - cart[0] >= 2 * 84 + 4 else 1
    alto_tab = ((len(tutti) + n_col - 1) // n_col + 1) * 5.0 + 6
    tabella_ok = len(tutti) > MAX_RICHIAMI and cart[3] + 8 + alto_tab <= sotto_viste
    if tabella_ok:
        with f.oggetto('fori'):
            righe = _fori_a_lettere(f, tutti, s, et, 0)
        with f.oggetto('tabella_fori'):
            cima = _tabella_fori(f, righe, cart[0], cart[3] + 8, area[2])
        cart = (cart[0], cart[1], cart[2], cima)         # l'isometrica non ci va sopra
    else:
        for vista, T in (('alto', TT), ('fronte', TF), (fianco, TL)):
            with f.oggetto(f'vista:{vista}/fori'):
                _fori(f, v[vista], T, s, et, gia)
    # isometrica nello spazio libero più grande che resta: a destra delle viste o sopra, mai nel cartiglio
    if not con_iso:
        return f
    vi = v['iso']
    wi, hi = vi['bbox'][2] - vi['bbox'][0], vi['bbox'][3] - vi['bbox'][1]
    destra_viste = viste_dx + 10
    cima = oyF + max(hF, hL) * s + 12
    candidati = [_taglia_cartiglio((destra_viste, area[1], area[2], area[3]), cart),
                 _taglia_cartiglio((area[0], cima, area[2], area[3]), cart)]

    def scala_in(r):
        return min((r[2] - r[0] - 10) / max(wi, 1e-6), (r[3] - r[1] - 15) / max(hi, 1e-6))
    xi0, yi0, xi1, yi1 = max(candidati, key=scala_in)
    si = scala_in((xi0, yi0, xi1, yi1))
    if si > 0 and min(wi, hi) * si > 15:              # un'isometrica minuscola non serve: meglio niente
        with f.oggetto('vista:iso'):
            TI, _, _ = _metti_vista(f, {**vi, 'nascosti': []}, si, xi0 + (xi1 - xi0 - wi * si) / 2, yi0 + (yi1 - yi0 - 12 - hi * si) / 2,
                                    quote_su=False)
            try:
                _metti_ombre(f, ombre_iso(shape), TI)
            except Exception:  # noqa: BLE001 - l'ombra è un abbellimento: senza, la tavola resta giusta
                pass
        with f.oggetto('vista:iso/titolo'):
            f.text('testo', (xi0, yi1 - 3), 'ISOMETRICA (fuori scala)', 2.5)
    return f


def _tratteggio(f: Foglio, giri: list, passo: float):
    """Tratteggio a 45° dentro i giri (sul foglio): righe ogni «passo» mm, tenute dentro col pari/dispari."""
    tutti = [p for g in giri for p in g]
    if not tutti:
        return
    # coordinate ruotate di 45°: u lungo le righe, w attraverso
    rot = lambda p: ((p[0] + p[1]) / math.sqrt(2), (p[1] - p[0]) / math.sqrt(2))  # noqa: E731
    back = lambda u, w: ((u - w) / math.sqrt(2), (u + w) / math.sqrt(2))  # noqa: E731
    R_ = [[rot(p) for p in g] for g in giri]
    ws = [q[1] for g in R_ for q in g]
    w = min(ws) + passo / 2
    while w < max(ws):
        xs = []
        for g in R_:
            for (u1, w1), (u2, w2) in zip(g, g[1:] + g[:1]):
                if (w1 <= w < w2) or (w2 <= w < w1):
                    xs.append(u1 + (w - w1) * (u2 - u1) / (w2 - w1))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            f.line('quote', back(xs[i], w), back(xs[i + 1], w))
        w += passo


def tavola_sezione(shape, campi: dict, asse: str = 'X', formato: str = 'A3') -> Foglio:
    """La sezione A-A: il pezzo tagliato da un piano verticale a metà (asse 'X': piano lungo la larghezza, vista di
    fronte; 'Y': lungo la profondità, vista da sinistra), si guarda la parte dietro il piano, la faccia tagliata
    tratteggiata (22/10)."""
    import build123d as bd
    f = Foglio(formato, campi.get('titolo', ''))
    sh = bd.Shape.cast(shape)
    bb = sh.bounding_box()
    vista = 'fronte' if asse == 'X' else 'sinistra'
    if asse == 'X':                                 # piano y = metà, si tiene la parte con y più grande (dietro)
        y0 = (bb.min.Y + bb.max.Y) / 2
        scatola = bd.Solid.make_box(bb.size.X + 20, bb.max.Y - y0 + 10, bb.size.Z + 20,
                                    bd.Plane(origin=(bb.min.X - 10, y0, bb.min.Z - 10)))
        piano, nome_piano = bd.Plane(origin=(0, y0, 0), z_dir=(0, 1, 0)), f'Y = {fmt(round(y0, 1))}'
    else:                                           # piano x = metà, si tiene la parte con x più grande (vista da sinistra)
        x0 = (bb.min.X + bb.max.X) / 2
        scatola = bd.Solid.make_box(bb.max.X - x0 + 10, bb.size.Y + 20, bb.size.Z + 20,
                                    bd.Plane(origin=(x0, bb.min.Y - 10, bb.min.Z - 10)))
        piano, nome_piano = bd.Plane(origin=(x0, 0, 0), z_dir=(1, 0, 0)), f'X = {fmt(round(x0, 1))}'
    tagliato = sh & scatola
    v = proietta(tagliato.wrapped, vista)
    wv, hv = v['bbox'][2] - v['bbox'][0], v['bbox'][3] - v['bbox'][1]
    campi = dict(campi)
    area, cart = _cornice(f, campi)
    zona = max(_zone_libere(area, cart), key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    aw, ah = zona[2] - zona[0] - 40, zona[3] - zona[1] - 40
    s = _scegli_scala((wv, hv), aw, ah)
    fissa = _scala_scelta(campi.get('scala_fissa'))
    if fissa:
        s = fissa / FATTORE_USCITA
    campi['scala'] = scala_testo(s)
    campi['_s'] = s
    f.testi, f.linee, f.cerchi, f.pieni = [], [], [], []
    area, cart = _cornice(f, campi)
    ox = zona[0] + 20 + (aw - wv * s) / 2
    oy = zona[1] + 20 + (ah - hv * s) / 2
    T, w, h = _metti_vista(f, v, s, ox, oy)
    # le facce tagliate (sul piano): tratteggio
    giri = []
    for fa in tagliato.faces():
        if fa.geom_type != bd.GeomType.PLANE or abs(abs(fa.normal_at().dot(piano.z_dir)) - 1) > 1e-6 \
                or abs((fa.center() - piano.origin).dot(piano.z_dir)) > 1e-4:
            continue
        for wire in [fa.outer_wire()] + list(fa.inner_wires()):
            pts = [q for e in wire.edges() for q in e.positions([i / 12 for i in range(13)])]
            giri.append([T(proietta_punto(vista, (q.X, q.Y, q.Z))) for q in pts])
    _tratteggio(f, giri, 2.0)
    f.text('testo', (ox, oy + h + 6), f'SEZIONE A-A  (piano {nome_piano}, vista {"di fronte" if asse == "X" else "da sinistra"})', 3.0)
    return f


def _sviluppo_forme(data, campi: dict, piegature: list, formato: str = 'A3') -> Foglio:
    """Lo sviluppo quotato, con le linee di piega e la tabella pieghe (sopra il cartiglio, righe più basse se sono
    tante); lo sviluppo nella zona libera più grande, senza toccare tabella e cartiglio."""
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
    area, cart = _cornice(f, {**campi, 'scala': ''})
    # la tabella pieghe: sopra il cartiglio, con l'altezza delle righe che si adatta a quante sono
    righe_tab = len(piegature)
    # coni e raccordi (non dal nome della piega: anche le pieghe su linea si chiamano PL1, PL2…)
    forma = bool(piegature) and bool(getattr(data, 'shape_info', None))
    if forma:                                          # P, angolo, verso (le forme a pezzi piegano su e giù), linea, correzione
        col = [0, 10, 30, 42, 62, 82]
        intest = ['P', 'Angolo', 'Verso', 'Linea', 'Correz.']
        piegature = [[r[0], r[3], r[4] if r[4] != '—' else '', r[2], r[7]] for r in piegature]
    else:
        col = [0, 14, 34, 64, 84, 104, 124, 144, 180]
        intest = ['P', 'Flangia', 'Lungh. est.', 'Angolo', 'Verso', 'R int.', 'K', 'Largh.']
    spazio = (area[3] - 12) - (cart[3] + 10) - 6
    h_riga = 7.0
    n_col = 1
    while righe_tab and h_riga * (-(-righe_tab // n_col) + 1) > spazio:
        if h_riga > 3.6:
            h_riga = max(3.6, spazio / (-(-righe_tab // n_col) + 1))
        elif (n_col + 1) * (col[-1] + 4) <= (area[2] - area[0]) * 0.75:
            n_col += 1
            h_riga = 7.0
        else:
            h_riga = spazio / (-(-righe_tab // n_col) + 1)
            break
    per_col = -(-righe_tab // n_col) if righe_tab else 0
    alto_tab = h_riga * (per_col + 1) + 6 if righe_tab else 0
    larg_tab = n_col * (col[-1] + 4)
    tab_x0 = min(cart[0], area[2] - larg_tab)
    tab_top = cart[3] + 10 + alto_tab
    zone = [(area[0], area[1], min(cart[0], tab_x0) - 10, area[3]), (area[0], tab_top + 8, area[2], area[3])]
    gq = 22                                          # posto per le quote (sotto e a sinistra) e il titolo sopra

    def scala_zona(r):
        aw, ah = (r[2] - r[0]) - gq - 8, (r[3] - r[1]) - gq - 12
        if aw <= 0 or ah <= 0:
            return 0
        sc = _scegli_scala((x1 - x0, y1 - y0), aw, ah)
        return sc if (x1 - x0) * sc <= aw and (y1 - y0) * sc <= ah else sc * 0.999
    zona = max(zone, key=scala_zona)
    s = scala_zona(zona) or SCALE[-1]
    f.testi, f.linee, f.cerchi, f.pieni = [], [], [], []
    campi = {**campi, 'scala': scala_testo(s), '_s': s}
    area, cart = _cornice(f, campi)
    ox, oy = zona[0] + gq, zona[1] + gq
    T = lambda p: (ox + (p[0] - x0) * s, oy + (p[1] - y0) * s)  # noqa: E731
    forma = bool(getattr(data, 'bend_rows', None))
    for pl in poly:
        f.line('contorno', *[T(p) for p in pl])
    punti_et = [(T(a)[0] + (T(b)[0] - T(a)[0]) * 0.86, T(a)[1] + (T(b)[1] - T(a)[1]) * 0.86) for a, b, _ in data.bend_lines]
    fitte = len(punti_et) > 1 and min(math.dist(p, q) for p, q in zip(punti_et, punti_et[1:])) < 3.0
    for i, (a, b, testo) in enumerate(data.bend_lines, 1):
        A, B = T(a), T(b)
        f.line('piega', A, B)
        if forma:                       # coni e raccordi: solo il numero, verso il bordo tondo (le linee lì sono larghe)
            if fitte and not (i == 1 or i % 5 == 0 or i == len(data.bend_lines)):
                continue                # linee troppo vicine a questa scala: un numero ogni 5 (tutti nel DXF)
            q = punti_et[i - 1]
            # le forme divise in pezzi numerano per pezzo (A1, A2… B1): lo stesso nome della tabella
            righe_p = data.bend_rows or []
            nome = str(righe_p[i - 1].get('label') or i) if i - 1 < len(righe_p) else str(i)
            f.text('piega', (q[0] + 0.6, q[1] + 0.6), nome, 1.8)
        else:
            m = ((A[0] + B[0]) / 2, (A[1] + B[1]) / 2)
            f.text('piega', (m[0] + 1, m[1] + 1), testo, 2.2 if len(data.bend_lines) < 20 else 1.6)
    for m in getattr(data, 'marks', None) or []:      # marcature laser: i tratti delle lettere
        pts = [tuple(data.plane.to_local_coords(bd.Vector(*q)))[:2] for q in m['flat']]
        if len(pts) > 1:
            f.line('testo', *[T(q) for q in pts])
    quota(f, T((x0, y0)), T((x1, y0)), -8, x1 - x0)
    quota(f, T((x0, y0)), T((x0, y1)), 8, y1 - y0)
    didascalia = ('SVILUPPO visto dal lato dello sketch · pieghe in rosso, numerate: angoli in tabella' if forma else
                  'SVILUPPO visto dal lato dello sketch · linee di piega in rosso: numero, angolo, verso, raggio')
    larg_zona = zona[2] - ox - 4
    riga, righe_d = '', []
    for parola in didascalia.split(' '):              # a capo dentro la zona del disegno (non sopra la tabella)
        prova = (riga + ' ' + parola).strip()
        if len(prova) * 2.5 * 0.55 > larg_zona and riga:
            righe_d.append(riga)
            riga = parola
        else:
            riga = prova
    righe_d.append(riga)
    for k, testo_d in enumerate(righe_d):
        f.text('testo', (ox, oy + (y1 - y0) * s + 6 + 4 * (len(righe_d) - 1 - k)), testo_d, 2.5)
    if righe_tab:
        for c in range(n_col):
            pezzo = piegature[c * per_col:(c + 1) * per_col]
            if pezzo:
                _tabella(f, tab_x0 + c * (col[-1] + 4), tab_top, col, [intest] + pezzo,
                         'TABELLA PIEGHE' if c == 0 else None, h=h_riga)
    return f


def tavola_taglio(campi: dict, righe: list, totali: list, formato: str = 'A3') -> Foglio:
    """La distinta di taglio di una struttura: profilo, lunghezza, tagli, quantità, gruppo, peso; e i totali per
    profilo (pezzi, metri, kg). È il foglio che va in officina alla troncatrice o al laser tubo."""
    f = Foglio(formato, campi.get('titolo', ''))
    area, cart = _cornice(f, {**campi, 'scala': '—'})
    col = [0, 12, 50, 80, 112, 126, 186, 206, 228]
    intest = ['Pos.', 'Profilo', 'Lunghezza mm', 'Tagli', 'Q.tà', 'Gruppo', 'kg cad.', 'kg tot.']
    ytop = area[3] - 12
    _tabella(f, area[0] + 10, ytop, col, [intest] + righe, 'DISTINTA DI TAGLIO')
    y2 = ytop - 7 * (len(righe) + 1) - 18
    _tabella(f, area[0] + 10, y2, [0, 40, 60, 85, 110], [['Profilo', 'Pezzi', 'Metri', 'kg']] + totali,
             'TOTALI PER PROFILO (barre da comprare)')
    return f


def _tabella(f: Foglio, x, ytop, col, righe, titolo=None, h=7.0):
    if titolo:
        f.text('testo', (x, ytop + 2), titolo, 2.8)
    for i, r in enumerate(righe):
        y = ytop - i * h
        f.line('tabella', (x, y), (x + col[-1], y))
        for j, val in enumerate(r):
            th = min(2.4, h * 0.55)
            f.text('tabella' if i else 'testo', (x + col[j] + 1.2, y - h * 0.72), _taglia(str(val), col[j + 1] - col[j], th), th)
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
    veloce = len(forme) > 4
    vF, vT, vI = proietta(tutto, 'fronte', veloce), proietta(tutto, 'alto', veloce), proietta(tutto, 'iso', veloce)
    wF, hF = vF['bbox'][2] - vF['bbox'][0], vF['bbox'][3] - vF['bbox'][1]
    hT = vT['bbox'][3] - vT['bbox'][1]
    W, H = FORMATI[formato]
    g = 28
    area, cart = _cornice(f, {**campi, 'scala': ''})
    larg_viste = min((W - 40) * 0.5, cart[0] - 10 - area[0])           # a sinistra del cartiglio, sempre
    s = _scegli_scala((wF, hF + hT), larg_viste - g - 6, (area[3] - area[1]) - 2 * g - 10)
    f.testi, f.linee, f.cerchi, f.pieni = [], [], [], []
    campi = {**campi, 'scala': scala_testo(s), '_s': s}
    area, cart = _cornice(f, campi)
    # le due viste in alto a sinistra, una sotto l'altra (in basso resta posto per le note)
    ox = area[0] + g
    oyF = area[3] - 14 - hF * s
    oyT = oyF - g - hT * s
    if oyT < area[1] + g:                              # non ci stanno dall'alto: dal basso come prima
        oyT = area[1] + g
        oyF = oyT + hT * s + g
    with f.oggetto('vista:fronte'):             # 28/10: nomi come nelle tavole dei pezzi: si ritoccano allo stesso modo
        _metti_vista(f, {**vF, 'nascosti': []}, s, ox, oyF)
    with f.oggetto('vista:alto'):
        _metti_vista(f, {**vT, 'nascosti': []}, s, ox, oyT)
    with f.oggetto('vista:fronte/titolo'):
        f.text('testo', (ox, oyF + hF * s + 4), 'VISTA DI FRONTE', 2.5)
    with f.oggetto('vista:alto/titolo'):
        f.text('testo', (ox, oyT + hT * s + 4), 'VISTA DALL’ALTO', 2.5)
    # isometrica con palloncini
    spazio = (area[3] - 40) - (cart[3] + 10)
    h_riga = max(3.4, min(7.0, spazio * 0.5 / max(len(distinta) + 1, 1)))
    xi0 = max(area[0] + (area[2] - area[0]) * 0.45, ox + wF * s + 14)
    yi0 = cart[3] + 12 + h_riga * (len(distinta) + 1) + 6
    xi1, yi1 = area[2], area[3]
    wi, hi = vI['bbox'][2] - vI['bbox'][0], vI['bbox'][3] - vI['bbox'][1]
    si = min((xi1 - xi0 - 20) / max(wi, 1e-6), (yi1 - yi0 - 20) / max(hi, 1e-6))
    oxi, oyi = xi0 + (xi1 - xi0 - wi * si) / 2, yi0 + (yi1 - yi0 - hi * si) / 2
    gruppo_prima = f.gruppo
    f.gruppo = 'vista:iso'                      # l'isometrica con i suoi palloncini: un oggetto solo
    TI, _, _ = _metti_vista(f, {**vI, 'nascosti': []}, si, oxi, oyi, quote_su=False)
    try:
        _metti_ombre(f, ombre_iso(tutto), TI)
    except Exception:  # noqa: BLE001 - l'ombra è un abbellimento
        pass
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
    f.gruppo = 'vista:iso/titolo'
    f.text('testo', (xi0, yi1 - 3), 'ISOMETRICA (fuori scala)', 2.5)
    f.gruppo = gruppo_prima
    col = [0, 12, 76, 90, 116, 140, 180]
    intest = ['Pos.', 'Descrizione', 'Q.tà', 'Materiale', 'Spessore', 'Peso kg']
    with f.oggetto('distinta'):
        _tabella(f, cart[0], cart[3] + 10 + h_riga * (len(distinta) + 1), col, [intest] + distinta, 'DISTINTA', h=h_riga)
    return f


def tavola_esploso(forme: list, campi: dict, distinta: list, montaggio: list, formato: str = 'A3', quanto: float = 0.8,
                   figli: list | None = None) -> Foglio:
    """Vista esplosa per far capire come si monta (22/10): ogni pezzo allontanato dal centro dell'assieme, i
    palloncini con la posizione della distinta, le linee di montaggio tratteggiate (da dove è disegnato a dove va)
    e l'ordine di montaggio scritto. forme: [(posizione, forma al suo posto)]; montaggio: righe di testo."""
    import build123d as bd
    import numpy as np
    f = Foglio(formato, campi.get('titolo', ''))
    centri = [np.array(tuple(sh.center())) for _, sh in forme]
    C = sum(centri) / len(centri)
    tutto_bb = bd.Compound(children=[sh for _, sh in forme]).bounding_box()
    grande = max(tutto_bb.size.X, tutto_bb.size.Y, tutto_bb.size.Z)
    spost, in_fila = [], {}
    figli = figli or [None] * len(forme)
    for (_, sh), c, fg in zip(forme, centri, figli):
        if fg is not None:
            spost.append(None)                       # le viti: dopo, attaccate al loro pezzo
            continue
        dd = (c - C) * quanto
        if np.linalg.norm(dd) < 0.2 * grande:
            dd = None                                 # vicino al centro: dopo, uno alla volta (sotto)
        spost.append(dd)
    # i pezzi vicini al centro (un fondo, un rinforzo dentro la cornice): escono lungo il loro spessore, dalla parte in
    # cui stanno (o sotto), dal più grande; ognuno abbastanza lontano da non finire dietro a un altro nella vista
    # (22/10: il rinforzo sotto il fondo spariva dietro il fondo)
    dv = np.array(VISTE['iso'][0], dtype=float)
    dv /= np.linalg.norm(dv)
    upv = _up_iso(VISTE['iso'][0])
    upv = np.array([upv.X(), upv.Y(), upv.Z()])
    xv = np.cross(upv, dv)

    def impronta(k, d):
        b = forme[k][1].bounding_box()
        pts = [np.array([x, y, z]) + d for x in (b.min.X, b.max.X) for y in (b.min.Y, b.max.Y) for z in (b.min.Z, b.max.Z)]
        u = [float(np.dot(q, xv)) for q in pts]
        v = [float(np.dot(q, upv)) for q in pts]
        return min(u), min(v), max(u), max(v)

    def si_coprono(a, b):
        return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
    def spessore(k):
        b = forme[k][1].bounding_box()
        ax = int(np.argmin([b.size.X, b.size.Y, b.size.Z]))
        return ax

    def area(r):
        return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])

    def comune(a, b):
        return area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))
    for k, d in enumerate(spost):                     # vicini al centro: per cominciare, fuori lungo lo spessore
        if d is None and figli[k] is None:
            ax = spessore(k)
            dd = np.zeros(3)
            dd[ax] = (np.sign((centri[k] - C)[ax]) or -1.0) * grande * 0.55
            spost[k] = dd
    # poi, dal più grande: un pezzo coperto per buona parte da uno già messo (nella vista) esce lungo il suo spessore
    # finché si vede
    ordine = sorted((k for k in range(len(forme)) if figli[k] is None), key=lambda k: -forme[k][1].bounding_box().diagonal)
    messi = []
    for k in ordine:
        dd = np.array(spost[k], dtype=float)
        imp = impronta(k, dd)
        coperto = lambda r: max([comune(r, m) / max(area(r), 1e-9) for _, m in messi] or [0.0])  # noqa: E731
        if coperto(imp) > 0.5:
            ax = spessore(k)
            altro = max(messi, key=lambda m: comune(imp, m[1]))[0]
            verso = np.sign((centri[k] - centri[altro])[ax]) or -1.0
            base = dd.copy()
            for passo in range(1, 40):
                dd = base.copy()
                dd[ax] += verso * grande * 0.12 * passo
                imp = impronta(k, dd)
                if coperto(imp) < 0.1:
                    break
        spost[k] = dd
        messi.append((k, imp))
    # le viti (e i pezzi piccoli infilati in un foro): seguono il pezzo in cui vanno e si sfilano lungo l'asse del
    # foro, dalla parte della testa, appena fuori (22/10: «le viti dovrebbero apparire prima della piastra dove
    # vanno messe, non in cima alla pagina»)
    for _giro in range(len(forme)):
        fatto = True
        for k, fg in enumerate(figli):
            if fg is None or spost[k] is not None:
                continue
            padre, asse, sfila = fg
            if spost[padre] is None:
                fatto = False
                continue
            spost[k] = spost[padre] + np.array(asse, dtype=float) * sfila
        if fatto:
            break
    spost = [d if d is not None else np.zeros(3) for d in spost]
    from OCP.gp import gp_Trsf, gp_Vec
    from OCP.TopLoc import TopLoc_Location

    def sposta(sh, d):
        t = gp_Trsf()
        t.SetTranslation(gp_Vec(*map(float, d)))
        return bd.Shape.cast(sh.wrapped.Moved(TopLoc_Location(t)))
    esplose = [sposta(sh, d) for (_, sh), d in zip(forme, spost)]
    vI = proietta(bd.Compound(children=esplose).wrapped, 'iso', len(forme) > 4)
    area, cart = _cornice(f, {**campi, 'scala': 'fuori scala'})
    h_riga = 5.0 if len(distinta) <= 12 else max(3.4, 60 / (len(distinta) + 1))
    col = [0, 10, 62, 74, 98, 118, 140]
    intest = ['Pos.', 'Descrizione', 'Q.tà', 'Materiale', 'Spessore', 'Peso kg']
    alto_dist = h_riga * (len(distinta) + 1) + 6
    # l'ordine di montaggio a sinistra in basso, la distinta sopra il cartiglio, l'esploso in tutto il resto
    righe_m = montaggio[:18]
    alto_m = 5 + 4.2 * len(righe_m) if righe_m else 0
    yi0 = max(cart[3] + 10 + alto_dist, area[1] + alto_m + 6)
    xi0, xi1, yi1 = area[0] + 6, area[2] - 6, area[3] - 10
    wi, hi = vI['bbox'][2] - vI['bbox'][0], vI['bbox'][3] - vI['bbox'][1]
    si = min((xi1 - xi0 - 40) / max(wi, 1e-6), (yi1 - yi0 - 30) / max(hi, 1e-6))
    oxi, oyi = xi0 + (xi1 - xi0 - wi * si) / 2, yi0 + (yi1 - yi0 - hi * si) / 2
    gruppo_prima = f.gruppo
    f.gruppo = 'vista:esploso'                  # la vista esplosa con linee e palloncini: un oggetto solo
    TI, _, _ = _metti_vista(f, {**vI, 'nascosti': []}, si, oxi, oyi, quote_su=False)
    d = np.array(VISTE['iso'][0], dtype=float)
    d /= np.linalg.norm(d)
    upd = _up_iso(VISTE['iso'][0])
    up = np.array([upd.X(), upd.Y(), upd.Z()])
    xd = np.cross(up, d)
    P2 = lambda p3: TI((float(np.dot(p3, xd)), float(np.dot(p3, up))))  # noqa: E731
    # linee di montaggio: dal centro del pezzo esploso a dove va montato
    for k, ((num, sh), c, dd) in enumerate(zip(forme, centri, spost)):
        attaccato = figli[k] is not None and not figli[k][2]        # va insieme al suo pezzo: la linea è la sua
        if np.linalg.norm(dd) > 1e-6 and not attaccato:
            f.line('nascoste', P2(c + dd), P2(c))
    palloncini, fatti = [], set()
    cx = oxi + wi * si / 2
    for (num, sh), c, dd in zip(forme, centri, spost):
        if num in fatti:
            continue
        fatti.add(num)
        p = P2(c + dd)
        verso = 1 if p[0] >= cx else -1
        q = (p[0] + verso * 16, p[1] + 12)
        while any(math.dist(q, b) < 10 for b in palloncini):
            q = (q[0] + verso * 4, q[1] + 9)
        palloncini.append(q)
        f.line('quote', p, q)
        f.cerchi.append(('quote', q, 4.2))
        f.text('quote', (q[0], q[1] - 1.3), str(num), 3.4, 'c')
        f.cerchi.append(('quote', p, 0.7))
    f.gruppo = 'vista:esploso/titolo'
    f.text('testo', (xi0, yi1 + 3), 'VISTA ESPLOSA (fuori scala) · le linee tratteggiate vanno da ogni pezzo a dove si monta', 2.8)
    f.gruppo = gruppo_prima
    with f.oggetto('distinta'):
        _tabella(f, cart[0], cart[3] + 10 + h_riga * (len(distinta) + 1), col, [intest] + distinta, 'DISTINTA', h=h_riga)
    if righe_m:
        y = area[1] + alto_m
        f.text('testo', (area[0] + 4, y), 'ORDINE DI MONTAGGIO', 2.8)
        for k, r in enumerate(righe_m):
            f.text('testo', (area[0] + 4, y - 5 - 4.2 * k), _taglia(r, cart[0] - area[0] - 12, 2.4), 2.4)
    return f


def _scala_da_testo(t: str):
    """'1:10' → 0.1, '2:1' → 2, '1:2,5' → 0.4; None se non è una scala."""
    try:
        a, b = str(t).replace(',', '.').split(':')
        return float(a) / float(b)
    except (ValueError, ZeroDivisionError):
        return None


def in_formato(f: Foglio, formato: str) -> Foglio:
    """La stessa tavola su un altro foglio della serie A, tale e quale scalata (22/10: «dovrebbero essere sempre
    uguali ma scalate nei vari formati»): tutto si moltiplica per il rapporto tra i fogli, la scala scritta nel
    cartiglio diventa quella vera sul foglio nuovo."""
    if formato == f.formato or formato not in FORMATI:
        return f
    k = FORMATI[formato][0] / FORMATI[f.formato][0]
    S = lambda p: (p[0] * k, p[1] * k)  # noqa: E731
    g = Foglio(formato, f.titolo)
    g.linee = _Strato(g, [(l, [S(p) for p in pts]) for l, pts in f.linee], f.linee.tag)
    g.cerchi = _Strato(g, [(l, S(c), r * k) for l, c, r in f.cerchi], f.cerchi.tag)
    g.pieni = _Strato(g, [(l, [S(p) for p in pts]) for l, pts in f.pieni], f.pieni.tag)
    g.ombre = _Strato(g, [(c, [S(p) for p in pts]) for c, pts in f.ombre], f.ombre.tag)
    g.testi = _Strato(g, [(l, S(p), t, h * k, al) for l, p, t, h, al in f.testi], f.testi.tag)
    g.i_scala = f.i_scala
    g.chiave = f.chiave
    g.scala, g.fattore = f.scala * k, f.fattore * k
    g.immagini = [(p, x * k, y * k, w * k, h * k) for p, x, y, w, h in f.immagini]
    for nome, e in f.elementi.items():
        e = dict(e)
        if e['kind'] == 'quota':
            e.update(a=list(S(e['a'])), b=list(S(e['b'])), distanza=e['distanza'] * k, h=e['h'] * k)
        elif e['kind'] == 'vista':
            e['T'] = [e['T'][0] * k, e['T'][1] * k, e['T'][2] * k]
        g.elementi[nome] = e
    if 0 <= f.i_scala < len(g.testi):
        l, p, t, h, al = g.testi[f.i_scala]
        sc = _scala_da_testo(t)
        if sc:          # la scala vera sul foglio stampato, e quella dell'impaginazione in A2 (come si legge sui disegni)
            g.testi[f.i_scala] = (l, p, f'{scala_testo(sc * k)} ({f.formato} {scala_testo(sc)})', h, al)
    return g


# ------------------------------------------------------------------------------------------ uscite
def to_dxf(fogli: list, path):
    """Le tavole in DXF (24/10: «sempre in scala 1:1»): nel modello ogni foglio è ingrandito della sua scala, così le
    viste sono a misura vera (misurando trovi 420 dove la quota dice 420), con cornice, cartiglio e quote in
    proporzione; più fogli uno di fianco all'altro. Per stampare c'è un layout per foglio, del formato giusto, che
    mostra il modello alla scala della tavola."""
    import ezdxf
    doc = ezdxf.new('R2010', setup=True)
    doc.units = ezdxf.units.MM
    for nome, (col, lw) in LAYER.items():
        if nome not in doc.layers:
            doc.layers.add(nome, color=col, lineweight=int(lw * 100))
    doc.layers.get('nascoste').dxf.linetype = 'DASHED'
    doc.layers.get('piega').dxf.linetype = 'DASHDOT'
    msp = doc.modelspace()
    from ezdxf.enums import TextEntityAlignment
    dx = 0.0
    nomi = set()
    for i, f in enumerate(fogli):
        z = 1 / f.scala if f.scala > 0 else 1.0
        o = lambda p, z=z, dx=dx: (p[0] * z + dx, p[1] * z)  # noqa: E731
        # 28/10: le quote lineari diventano quote vere (DIMENSION), modificabili in AutoCAD; le loro linee e testi
        # disegnati non si scrivono
        quote = {n: e for n, e in f.elementi.items() if e.get('kind') == 'quota' and not e.get('nascosta')}
        for nome, e in quote.items():
            try:
                _quota_dxf(msp, e, o, z)
            except Exception:  # noqa: BLE001 - se ezdxf non la sa fare, resta disegnata a linee
                quote_fatte = None
            else:
                quote_fatte = nome
            if quote_fatte is None:
                quote[nome] = None
        via = {n for n, e in quote.items() if e is not None}
        tieni = lambda tags: [t not in via for t in tags]  # noqa: E731
        for (layer, pts), ok in zip(f.linee, tieni(f.linee.tag)):
            if not ok:
                continue
            if len(pts) == 2:
                msp.add_line(o(pts[0]), o(pts[1]), dxfattribs={'layer': layer})
            else:
                msp.add_lwpolyline([o(p) for p in pts], dxfattribs={'layer': layer})
        for (layer, c, r), ok in zip(f.cerchi, tieni(f.cerchi.tag)):
            if ok:
                msp.add_circle(o(c), r * z, dxfattribs={'layer': layer})
        for (layer, pts), ok in zip(f.pieni, tieni(f.pieni.tag)):
            if ok:
                msp.add_solid([o(p) for p in pts], dxfattribs={'layer': layer})
        for (layer, p, t, h, al), ok in zip(f.testi, tieni(f.testi.tag)):
            if not ok:
                continue
            e = msp.add_text(t, height=h * z, dxfattribs={'layer': layer, 'rotation': 90 if al == 'cv' else 0, 'style': 'OpenSans'})
            a = {'l': TextEntityAlignment.BOTTOM_LEFT, 'c': TextEntityAlignment.BOTTOM_CENTER,
                 'r': TextEntityAlignment.BOTTOM_RIGHT, 'cv': TextEntityAlignment.BOTTOM_CENTER}[al]
            e.set_placement(o(p), align=a)
        W, H = f.size
        nome = ''.join(c for c in f'{i + 1} {f.titolo}' if c not in '<>/\\":;?*|=`,')[:60].strip() or f'Foglio {i + 1}'
        while nome in nomi:
            nome += ' bis'
        nomi.add(nome)
        lay = doc.layouts.new(nome)
        lay.page_setup(size=(W, H), margins=(0, 0, 0, 0), units='mm', scale=1)
        lay.add_viewport(center=(W / 2, H / 2), size=(W, H), view_center_point=(dx + W * z / 2, H * z / 2), view_height=H * z)
        dx += (W + 50) * z
    if 'Layout1' in doc.layouts and len(fogli):
        doc.layouts.delete('Layout1')
    doc.saveas(str(path))


def _quota_dxf(msp, e: dict, o, z: float):
    """Una quota lineare della tavola come DIMENSION allineata nel modello a 1:1: stessi punti, stessa distanza,
    testo e frecce delle stesse misure del foglio; il numero è quello misurato (o il testo scritto a mano)."""
    a, b = o(e['a']), o(e['b'])
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L < 1e-9:
        raise ValueError('quota nulla')
    h = float(e.get('h') or 2.8)
    fr = float(e.get('freccia') or 2.5 * h / 2.8)
    u = h / 2.8
    scritta = e.get('testo') if e.get('testo') not in (None, '') else None
    if scritta is None:
        valore = float(e['valore'])
        # la misura nel modello è quella vera se la vista è in scala; se no (dettaglio ingrandito…) si scrive il numero
        scritta = '<>' if not e.get('prefisso') and abs(L - valore) < 0.005 else (e.get('prefisso') or '') + fmt(valore)
    dim = msp.add_aligned_dim(p1=a, p2=b, distance=float(e['distanza']) * z, text=scritta, dimstyle='EZDXF',
                              override={'dimtxt': h * z, 'dimasz': fr * z, 'dimexe': 1.5 * u * z, 'dimexo': 0.9 * u * z,
                                        'dimgap': 0.8 * u * z, 'dimdec': 2, 'dimdsep': ord(','), 'dimzin': 8, 'dimtad': 1, 'dimlfac': 1,
                                        'dimtih': 0, 'dimtoh': 0, 'dimclrd': 5, 'dimclre': 5, 'dimclrt': 5},
                              dxfattribs={'layer': 'quote'})
    dim.render()


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
    loghi: dict = {}
    for f in fogli:
        W, H = f.size
        c = ['1 J 1 j']
        imm_pag = {}
        for p, x, y, w, h in f.immagini:
            if str(p) not in loghi:
                d = _immagine_pdf(p)
                if d is None:
                    loghi[str(p)] = None
                    continue
                iw, ih, rgb, alfa = d
                sm = ''
                if alfa is not None:
                    m = obj(f'<< /Type /XObject /Subtype /Image /Width {iw} /Height {ih} /ColorSpace /DeviceGray /BitsPerComponent 8 '
                            f'/Filter /FlateDecode /Length {len(alfa)} >>\nstream\n'.encode('latin-1') + alfa + b'\nendstream')
                    sm = f' /SMask {m} 0 R'
                n = obj(f'<< /Type /XObject /Subtype /Image /Width {iw} /Height {ih} /ColorSpace /DeviceRGB /BitsPerComponent 8 '
                        f'/Filter /FlateDecode{sm} /Length {len(rgb)} >>\nstream\n'.encode('latin-1') + rgb + b'\nendstream')
                loghi[str(p)] = (n, iw, ih)
            if loghi[str(p)] is None:
                continue
            n, iw, ih = loghi[str(p)]
            sc = min(w / iw, h / ih)                         # dentro il riquadro, senza deformarlo
            dw, dh = iw * sc, ih * sc
            nome = f'Im{n}'
            imm_pag[nome] = n
            c.append(f'q {dw * k:.2f} 0 0 {dh * k:.2f} {(x + (w - dw) / 2) * k:.2f} {(y + (h - dh) / 2) * k:.2f} cm /{nome} Do Q')
        if f.ombre:
            c.append(f'{0.12 * k:.3f} w')
            for (r, g, b), pts in f.ombre:
                c.append(f'{r:.3f} {g:.3f} {b:.3f} rg {r:.3f} {g:.3f} {b:.3f} RG '
                         + ' '.join(f'{p[0] * k:.2f} {p[1] * k:.2f} {"m" if i == 0 else "l"}' for i, p in enumerate(pts)) + ' h B')
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
        pagine.append((cont, W * k, H * k, imm_pag))
    kids_pos = len(oggetti) + 1 + len(pagine)
    ids = []
    for cont, w, h, imm_pag in pagine:
        xo = (' /XObject << ' + ' '.join(f'/{nm} {n} 0 R' for nm, n in imm_pag.items()) + ' >>') if imm_pag else ''
        ids.append(obj(f'<< /Type /Page /Parent {kids_pos} 0 R /MediaBox [0 0 {w:.2f} {h:.2f}] /Contents {cont} 0 R '
                       f'/Resources << /Font << /F1 {font} 0 R >>{xo} >> >>'))
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


def copia_foglio(f: Foglio) -> Foglio:
    """Una copia da ritoccare (29/10): le primitive sono tuple (non cambiano), si copiano solo le liste e i dati degli
    oggetti. deepcopy di un foglio con 300 fori era lento."""
    g = Foglio(f.formato, f.titolo)
    for nome in STRATI:
        st = getattr(f, nome)
        setattr(g, nome, _Strato(g, list(st), st.tag if isinstance(st, _Strato) else None))
    g.i_scala, g.chiave, g.scala, g.fattore = f.i_scala, f.chiave, f.scala, f.fattore
    g.immagini = list(f.immagini)
    g.elementi = {k: dict(v) for k, v in f.elementi.items()}
    return g


_STILI_SVG = {'contorno': 'stroke:#111;stroke-width:.45', 'nascoste': 'stroke:#666;stroke-width:.22;stroke-dasharray:2.5 1.2',
              'tangenti': 'stroke:#777;stroke-width:.16', 'piega': 'stroke:#C0392B;stroke-width:.25;stroke-dasharray:5 1.2 1 1.2',
              'quote': 'stroke:#2B5BA0;stroke-width:.16', 'cornice': 'stroke:#111;stroke-width:.5',
              'cartiglio': 'stroke:#111;stroke-width:.25', 'tabella': 'stroke:#111;stroke-width:.2', 'testo': 'stroke:#111'}


def to_svg(f: Foglio) -> str:
    """Il foglio in SVG. 29/10: compatto (stili in classi, coordinate a 2 decimali) e raggruppato per oggetto
    (<g data-el="vista:alto">…): con 300 fori l'editor aveva 12.000 elementi da spostare a ogni movimento del mouse."""
    import html
    W, H = f.size
    Y = lambda y: H - y  # noqa: E731
    classe = {k: f'l{i}' for i, k in enumerate(_STILI_SVG)}
    stile = ''.join(f'.{classe[k]}{{{v}}}' for k, v in _STILI_SVG.items())
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}mm" height="{H}mm" '
           'font-family="Helvetica,Arial,sans-serif">',
           f'<style>{stile}.tq{{fill:#2B5BA0}}.tp{{fill:#C0392B}}.tn{{fill:#111}}</style>',
           f'<rect width="{W}" height="{H}" fill="#fff"/>']
    pts_ = lambda pts: ' '.join(f'{p[0]:.2f},{Y(p[1]):.2f}' for p in pts)  # noqa: E731

    def gruppi(strato, scrivi):
        """Le primitive dello strato, quelle dello stesso oggetto di fila in un gruppo solo."""
        tags = strato.tag if isinstance(strato, _Strato) else [''] * len(strato)
        corrente = None
        for x, t in zip(strato, tags):
            if t != corrente:
                if corrente:
                    out.append('</g>')
                if t:
                    out.append(f'<g data-el="{html.escape(t)}">')
                corrente = t
            out.append(scrivi(x))
        if corrente:
            out.append('</g>')

    # l'ombra dell'isometrica: i colori in classi, i triangoli di fila dello stesso colore in un tracciato solo
    # (nell'ordine: quelli dietro prima), coordinate a un decimale
    colori: dict = {}
    tags = f.ombre.tag if isinstance(f.ombre, _Strato) else [''] * len(f.ombre)
    corrente, tratti, col_c = None, [], None

    def chiudi_ombra():
        if tratti:
            out.append(f'<path class="{colori[col_c]}" d="{"".join(tratti)}"/>')
            tratti.clear()
    pezzi_ombra = []
    for ((r, g, b), pts), t in zip(f.ombre, tags):
        col = '#%02X%02X%02X' % (round(r * 255), round(g * 255), round(b * 255))
        colori.setdefault(col, f'o{len(colori)}')
        pezzi_ombra.append((col, pts, t))
    if colori:
        out.append('<style>' + ''.join(f'.{k}{{fill:{c};stroke:{c};stroke-width:.12;stroke-linejoin:round}}' for c, k in colori.items())
                   + '</style>')
    for col, pts, t in pezzi_ombra:
        if t != corrente:
            chiudi_ombra()
            if corrente:
                out.append('</g>')
            if t:
                out.append(f'<g data-el="{html.escape(t)}">')
            corrente = t
        elif col != col_c:
            chiudi_ombra()
        col_c = col
        tratti.append('M' + 'L'.join(f'{p[0]:.1f} {Y(p[1]):.1f}' for p in pts) + 'Z')
    chiudi_ombra()
    if corrente:
        out.append('</g>')
    for p, x, y, w, h in f.immagini:
        dati = _immagine_base64(p)
        if dati:
            out.append(f'<image data-el="cartiglio" x="{x:.2f}" y="{Y(y + h):.2f}" width="{w:.2f}" height="{h:.2f}" '
                       f'preserveAspectRatio="xMidYMid meet" href="{dati}"/>')
    out.append('<g fill="none" stroke-linecap="round" stroke-linejoin="round">')
    # le linee di fila dello stesso oggetto e dello stesso tipo: un tracciato solo (9.000 segmenti → poche decine)
    tags = f.linee.tag if isinstance(f.linee, _Strato) else [''] * len(f.linee)
    corrente, tratti, layer_c = None, [], None

    def chiudi_tracciato():
        if tratti:
            out.append(f'<path class="{classe.get(layer_c, "l0")}" d="{" ".join(tratti)}"/>')
            tratti.clear()
    for (layer, pts), t in zip(f.linee, tags):
        if t != corrente:
            chiudi_tracciato()
            if corrente:
                out.append('</g>')
            if t:
                out.append(f'<g data-el="{html.escape(t)}">')
            corrente = t
        elif layer != layer_c:
            chiudi_tracciato()
        layer_c = layer
        tratti.append('M' + ' '.join(f'{p[0]:.2f} {Y(p[1]):.2f}' for p in pts[:1]) + 'L' + ' '.join(f'{p[0]:.2f} {Y(p[1]):.2f}' for p in pts[1:]))
    chiudi_tracciato()
    if corrente:
        out.append('</g>')
    gruppi(f.cerchi, lambda x: f'<circle class="{classe.get(x[0], classe["quote"])}" cx="{x[1][0]:.2f}" cy="{Y(x[1][1]):.2f}" r="{x[2]:.2f}"/>')
    out.append('</g>')
    gruppi(f.pieni, lambda x: f'<polygon class="tq" points="{pts_(x[1])}"/>')

    def testo(x):
        layer, (tx, ty), t, h, al = x
        col = 'tq' if layer == 'quote' else 'tp' if layer == 'piega' else 'tn'
        anchor = {'l': 'start', 'c': 'middle', 'r': 'end', 'cv': 'middle'}[al]
        rot = f' transform="rotate(-90 {tx:.2f} {Y(ty):.2f})"' if al == 'cv' else ''
        return (f'<text class="{col}" x="{tx:.2f}" y="{Y(ty):.2f}" font-size="{h:.2f}" text-anchor="{anchor}"{rot}>'
                f'{html.escape(t)}</text>')
    gruppi(f.testi, testo)
    out.append('</svg>')
    return '\n'.join(out)


def _immagine_base64(path) -> str | None:
    import base64
    from pathlib import Path
    p = Path(path)
    try:
        tipo = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}[p.suffix.lower()]
        return f'data:{tipo};base64,' + base64.b64encode(p.read_bytes()).decode('ascii')
    except (KeyError, OSError):
        return None


def _immagine_pdf(path):
    """Il logo per il PDF: (larghezza, altezza, dati RGB compressi, maschera alfa compressa o None)."""
    import zlib
    try:
        from PIL import Image
        im = Image.open(path)
        im.load()
    except Exception:  # noqa: BLE001 - un logo che non si legge: la tavola esce lo stesso, senza
        return None
    alfa = None
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA')
        alfa = zlib.compress(im.getchannel('A').tobytes())
    rgb = im.convert('RGB')
    return rgb.width, rgb.height, zlib.compress(rgb.tobytes()), alfa


def oggi() -> str:
    return datetime.date.today().strftime('%d/%m/%Y')


# la tavola dello sviluppo per l'officina sta nel suo modulo (in fondo: usa le funzioni di qui)
from .drawings_sviluppo import tavola_sviluppo  # noqa: E402,F401
