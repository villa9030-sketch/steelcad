"""Import di uno sviluppo di lamiera da DXF (o DWG): dal disegno piano al pezzo piegato.

1. **Lettura**: linee, archi, cerchi, polilinee (anche con archi), spline ed ellissi (spezzate), anche dentro i
   blocchi; unità del file convertite in mm. Testi, quote, tratteggi e linee nascoste non sono geometria.
2. **Linee di piega**: layer che si chiamano PIEGA/BEND/FOLD…, oppure tipo di linea ad asse/tratto-punto.
3. **Contorni**: i tratti si concatenano in giri chiusi; ogni giro può essere il contorno del pezzo, i giri dentro
   sono i suoi fori. In un disegno con più viste e cartiglio si sceglie quale giro è lo sviluppo.
4. **Pieghe → flange**: lo sviluppo si divide sulle linee di piega; la parte più grande è la base, le altre flange
   (e flange sulla punta, se la linea dopo è parallela). La linea di piega è la **mezzeria** della piega: la
   lunghezza di ogni flangia si calcola perché lo sviluppo di SteelCAD coincida con il disegno.
5. **Fori e sagome**: quello che lo sviluppo di SteelCAD ha in più rispetto al disegno si toglie con un taglio
   sullo sviluppo: il pezzo torna uguale al DXF.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import SteelCADError

TOL = 0.05                     # mm: due estremi più vicini di così sono lo stesso punto
RE_PIEGA_LAYER = re.compile(r'PIEG|BEND|FOLD|CANT|BIEG|PLI', re.I)
RE_PIEGA_LTYPE = re.compile(r'CENTER|DASHDOT|PHANTOM|DIVIDE|ASSE|CENTRE', re.I)
RE_NASCOSTE = re.compile(r'HIDDEN|DASHED|NASCOST|TRATTEGG', re.I)
RE_NON_GEOMETRIA = re.compile(r'DIM|QUOT|TEST|TEXT|FORMAT|CARTIG|TITLE|SQUADR|DEFPOINT|ANNOT|HATCH|TRATT', re.I)
UNITA = {0: 1.0, 1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0}   # $INSUNITS → mm


class ImportError_(SteelCADError):
    code = 'import'


@dataclass
class Tratto:
    tipo: str                      # 'line' | 'arc' | 'circle' | 'poly'
    dati: tuple
    ruolo: str = 'taglio'          # 'taglio' | 'piega'
    layer: str = ''
    gruppo: int | None = None      # i pezzi di una stessa polilinea chiusa: fanno giro tra loro

    def estremi(self):
        if self.tipo == 'line':
            return self.dati[0], self.dati[1]
        if self.tipo == 'arc':
            c, r, a0, a1 = self.dati
            return ((c[0] + r * math.cos(math.radians(a0)), c[1] + r * math.sin(math.radians(a0))),
                    (c[0] + r * math.cos(math.radians(a1)), c[1] + r * math.sin(math.radians(a1))))
        if self.tipo == 'poly':
            return self.dati[0], self.dati[-1]
        return None

    def punti(self, passo: float = 1.0):
        """Il tratto come spezzata (per aree, contenimento, anteprima)."""
        if self.tipo == 'line':
            return list(self.dati)
        if self.tipo == 'poly':
            return list(self.dati)
        if self.tipo == 'arc':
            c, r, a0, a1 = self.dati
            while a1 <= a0:
                a1 += 360
            n = max(4, int(math.radians(a1 - a0) * r / passo))
            return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
                    for i in range(n + 1)]
        c, r = self.dati
        n = max(12, int(2 * math.pi * r / passo))
        return [(c[0] + r * math.cos(2 * math.pi * i / n), c[1] + r * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]


@dataclass
class Giro:
    tratti: list                   # [(Tratto, al_contrario)]
    poligono: list                 # punti (per area e contenimento)
    area: float
    figli: list = field(default_factory=list)
    profondita: int = 0
    padre: int | None = None


@dataclass
class Analisi:
    file: str
    giri: list
    pieghe: list                   # Tratti di piega (solo linee)
    testi: list
    aperti: int                    # tratti di taglio che non chiudono un giro
    scelto: int | None             # il giro proposto come contorno del pezzo
    spessore: float | None = None
    materiale: str | None = None
    unita: str = 'mm'


# ------------------------------------------------------------------------------------------ lettura
def dwg_converter() -> str | None:
    import glob
    custom = os.environ.get('ODA_FC_PATH')
    if custom and os.path.exists(custom):
        return custom
    cand = []
    for base in (r'C:\Program Files\ODA', r'C:\Program Files (x86)\ODA'):
        if os.path.isdir(base):
            cand += glob.glob(os.path.join(base, 'ODAFileConverter*', 'ODAFileConverter.exe'))
    return sorted(cand)[-1] if cand else None


def _dwg_to_dxf(path: Path) -> Path:
    import glob
    import shutil
    import subprocess
    import tempfile
    oda = dwg_converter()
    if not oda:
        raise ImportError_('Per aprire i DWG serve "ODA File Converter" (gratuito, opendesign.com): installalo e riprova. '
                           'Oppure salva il disegno come DXF.')
    tin, tout = tempfile.mkdtemp(prefix='dwg_in_'), tempfile.mkdtemp(prefix='dwg_out_')
    try:
        shutil.copy2(path, Path(tin) / path.name)
        p = subprocess.run([oda, tin, tout, 'ACAD2018', 'DXF', '0', '1'], capture_output=True, timeout=120)
        out = glob.glob(os.path.join(tout, '*.dxf'))
        if p.returncode != 0 or not out:
            raise ImportError_('ODA File Converter non è riuscito a convertire il DWG.')
        dest = Path(tempfile.mkdtemp(prefix='steelcad_dwg_')) / (path.stem + '.dxf')
        shutil.copy2(out[0], dest)
        return dest
    except subprocess.TimeoutExpired:
        raise ImportError_('La conversione del DWG ci mette troppo.') from None
    finally:
        shutil.rmtree(tin, ignore_errors=True)
        shutil.rmtree(tout, ignore_errors=True)


def _tipo_linea(e, doc) -> str:
    lt = e.dxf.get('linetype', 'BYLAYER')
    if lt.upper() in ('BYLAYER', 'BYBLOCK'):
        try:
            lt = doc.layers.get(e.dxf.layer).dxf.linetype
        except Exception:  # noqa: BLE001
            lt = 'CONTINUOUS'
    return lt or 'CONTINUOUS'


def leggi(path) -> Analisi:
    import ezdxf
    from ezdxf import recover
    p = Path(path)
    if not p.exists():
        raise ImportError_(f'Il file {p} non esiste.')
    if p.suffix.lower() == '.dwg':
        p_dxf = _dwg_to_dxf(p)
    else:
        p_dxf = p
    try:
        doc, _ = recover.readfile(str(p_dxf))
    except Exception as ex:  # noqa: BLE001 - file rovinato o non DXF: ezdxf ha molti tipi di errore
        motivo = ''.join(c for c in str(ex)[:120].encode('utf-8', 'replace').decode('utf-8', 'replace') if c.isprintable())
        raise ImportError_(f'Il file {p.name} non si legge come DXF ({motivo}).') from None
    k = UNITA.get(doc.header.get('$INSUNITS', 0), 1.0)
    if k != 1.0:
        # molti DXF dichiarano un'unità sbagliata (metri, pollici) ma sono disegnati in mm: se così il pezzo verrebbe
        # più grande di 20 m, si tengono i mm
        try:
            from ezdxf import bbox as ebbox
            ext = ebbox.extents(doc.modelspace())
            if ext.has_data and max(ext.size.x, ext.size.y) * k > 20000 and max(ext.size.x, ext.size.y) < 20000:
                k = 1.0
        except Exception:  # noqa: BLE001
            pass
    tratti, testi = [], []
    gruppi = [0]

    def aggiungi(e, gruppo=None):
        t = e.dxftype()
        layer = e.dxf.get('layer', '0')
        if t in ('TEXT', 'MTEXT', 'ATTRIB'):
            try:
                testi.append(e.dxf.text if t != 'MTEXT' else e.plain_text())
            except Exception:  # noqa: BLE001
                pass
            return
        if t == 'INSERT':
            try:
                for v in e.virtual_entities():
                    aggiungi(v)
            except Exception:  # noqa: BLE001
                pass
            return
        if t not in ('LINE', 'ARC', 'CIRCLE', 'LWPOLYLINE', 'POLYLINE', 'SPLINE', 'ELLIPSE'):
            return
        lt = _tipo_linea(e, doc)
        if RE_PIEGA_LAYER.search(layer) or RE_PIEGA_LTYPE.search(lt):
            ruolo = 'piega'
        elif RE_NASCOSTE.search(lt) or RE_NON_GEOMETRIA.search(layer):
            return
        else:
            ruolo = 'taglio'
        P = lambda q: (q[0] * k, q[1] * k)  # noqa: E731
        n0 = len(tratti)
        if t == 'LINE':
            tratti.append(Tratto('line', (P(e.dxf.start), P(e.dxf.end)), ruolo, layer))
        elif t == 'ARC':
            c = e.dxf.center
            if e.dxf.get('extrusion', (0, 0, 1))[2] < 0:            # arco visto da sotto: si specchia
                tratti.append(Tratto('arc', ((-c[0] * k, c[1] * k), e.dxf.radius * k, 180 - e.dxf.end_angle, 180 - e.dxf.start_angle), ruolo, layer))
            else:
                tratti.append(Tratto('arc', (P(c), e.dxf.radius * k, e.dxf.start_angle, e.dxf.end_angle), ruolo, layer))
        elif t == 'CIRCLE':
            tratti.append(Tratto('circle', (P(e.dxf.center), e.dxf.radius * k), ruolo, layer))
        else:
            try:
                if t in ('LWPOLYLINE', 'POLYLINE') and e.is_closed and gruppo is None:
                    # una polilinea chiusa è un giro a sé, anche se tocca altri contorni (scassi sugli angoli)
                    gruppi[0] += 1
                    gruppo = gruppi[0]
                for v in e.virtual_entities() if t in ('LWPOLYLINE', 'POLYLINE') else []:
                    aggiungi(v, gruppo)
                if t in ('SPLINE', 'ELLIPSE'):
                    pts = [P(q) for q in e.flattening(0.05)]
                    if len(pts) >= 2:
                        tratti.append(Tratto('poly', tuple(pts), ruolo, layer))
            except Exception:  # noqa: BLE001
                pass
        for x in tratti[n0:]:
            if x.gruppo is None:
                x.gruppo = gruppo

    for e in doc.modelspace():
        aggiungi(e)
    taglio = [t for t in tratti if t.ruolo == 'taglio']
    pieghe = [t for t in tratti if t.ruolo == 'piega' and t.tipo == 'line']
    giri, aperti = _giri(taglio)
    _annida(giri)
    an = Analisi(str(p), giri, pieghe, testi, aperti, _proponi(giri))
    an.spessore, an.materiale = _indizi(testi, p)
    return an


# ------------------------------------------------------------------------------------------ contorni
def _chiave(q):
    return (round(q[0] / TOL), round(q[1] / TOL))


def _giri(tratti) -> tuple:
    """Concatena i tratti in giri chiusi. Ritorna (giri, quanti tratti restano aperti). Le polilinee chiuse fanno
    giro da sole; il resto si concatena per estremi."""
    giri = []
    gruppi: dict = {}
    sciolti = [t for t in tratti if t.gruppo is None]
    for t in tratti:
        if t.gruppo is not None:
            gruppi.setdefault(t.gruppo, []).append(t)
    for lista in gruppi.values():
        g, r = _concatena(lista)
        if r:                                     # polilinea "chiusa" che non chiude: i suoi pezzi vanno col resto
            sciolti += lista
        else:
            giri += g
    g, resto = _concatena(sciolti)
    return giri + g, resto


def _concatena(tratti) -> tuple:
    giri = []
    aperti = [t for t in tratti if t.tipo != 'circle']
    for t in tratti:
        if t.tipo == 'circle':
            pts = t.punti(0.5)
            giri.append(Giro([(t, False)], pts, abs(_area(pts))))
    # indice estremi
    vicini: dict = {}
    for i, t in enumerate(aperti):
        a, b = t.estremi()
        if math.dist(a, b) < TOL and t.tipo == 'poly':           # spline/polilinea già chiusa
            pts = t.punti()
            giri.append(Giro([(t, False)], pts, abs(_area(pts))))
            continue
        for q in (a, b):
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    k = _chiave(q)
                    vicini.setdefault((k[0] + dx, k[1] + dy), set()).add(i)
    usati = set()
    for i0, t0 in enumerate(aperti):
        if i0 in usati or math.dist(*t0.estremi()) < TOL:
            continue
        catena = [(t0, False)]
        usati_c = {i0}
        inizio, cur = t0.estremi()
        chiuso = False
        for _ in range(len(aperti)):
            if math.dist(cur, inizio) < TOL:
                chiuso = True
                break
            cand = [j for j in vicini.get(_chiave(cur), ()) if j not in usati and j not in usati_c]
            nxt = None
            for j in cand:
                a, b = aperti[j].estremi()
                if math.dist(a, cur) < TOL:
                    nxt = (j, False, b)
                    break
                if math.dist(b, cur) < TOL:
                    nxt = (j, True, a)
                    break
            if nxt is None:
                break
            j, rev, cur = nxt
            catena.append((aperti[j], rev))
            usati_c.add(j)
        if chiuso:
            usati |= usati_c
            pts = []
            for t, rev in catena:
                q = t.punti(0.5)
                pts += (q[::-1] if rev else q)[:-1]
            giri.append(Giro(catena, pts, abs(_area(pts))))
    resto = sum(1 for i, t in enumerate(aperti) if i not in usati and math.dist(*t.estremi()) >= TOL)
    giri = [g for g in giri if g.area > 1e-3]
    return giri, resto


def _area(pts) -> float:
    return sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1] for i in range(len(pts))) / 2


def _dentro(q, pts) -> bool:
    x, y = q
    d = False
    for i in range(len(pts)):
        (x1, y1), (x2, y2) = pts[i - 1], pts[i]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            d = not d
    return d


def _annida(giri):
    """Chi sta dentro chi: padre = il giro più piccolo che lo contiene."""
    ordine = sorted(range(len(giri)), key=lambda i: giri[i].area)
    for i in ordine:
        g = giri[i]
        q = g.poligono[0]
        cont = [j for j in ordine if j != i and giri[j].area > g.area and _dentro(q, giri[j].poligono)
                and all(_dentro(p, giri[j].poligono) for p in g.poligono[::max(1, len(g.poligono) // 8)])]
        if cont:
            g.padre = min(cont, key=lambda j: giri[j].area)
    for i, g in enumerate(giri):
        if g.padre is not None:
            giri[g.padre].figli.append(i)
    for i, g in enumerate(giri):
        d, j = 0, g.padre
        while j is not None:
            d += 1
            j = giri[j].padre
        g.profondita = d


def _proponi(giri) -> int | None:
    """Il contorno del pezzo più probabile: un giro di primo livello che non contiene altri contorni con fori
    (in una tavola il primo livello è la cornice)."""
    if not giri:
        return None
    radici = [i for i, g in enumerate(giri) if g.padre is None]
    semplici = [i for i in radici if all(not giri[f].figli for f in giri[i].figli)]
    if len(semplici) == 1:
        return semplici[0]
    # dentro una cornice: i giri di secondo livello che hanno fori ma non nipoti
    cand = [i for i, g in enumerate(giri) if all(not giri[f].figli for f in g.figli) and g.padre is not None]
    if semplici:
        return max(semplici, key=lambda i: giri[i].area)
    return max(cand, key=lambda i: giri[i].area) if cand else max(radici, key=lambda i: giri[i].area)


def _indizi(testi, path: Path):
    """Spessore e materiale scritti nei testi o nel nome del file/cartella (es. "INOX_304_sp3mm")."""
    tutto = ' '.join(testi) + ' ' + str(path)
    sp = None
    m = re.search(r'\bsp(?:essore)?\.?\s*[_:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:mm)?', tutto, re.I)
    if m:
        sp = float(m.group(1).replace(',', '.'))
    mat = None
    for pat, nome in ((r'INOX[\s_-]*316|AISI[\s_-]*316', 'AISI316L'), (r'INOX[\s_-]*304|AISI[\s_-]*304|\bINOX\b', 'AISI304'),
                      (r'ALU\w*[\s_-]*5754|\bAL[\s_-]*5754', 'AL5754'), (r'ALU\w*[\s_-]*6082|\bAL[\s_-]*6082', 'AL6082'), (r'S\s*355', 'S355'), (r'S\s*275', 'S275'),
                      (r'S\s*235|\bFE\s*360', 'S235'), (r'DC\s*01', 'DC01'), (r'ZINC|DX51', 'DX51D')):
        if re.search(pat, tutto, re.I):
            mat = nome
            break
    return sp, mat


def _bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def tagli(an: Analisi, giro: int) -> list:
    """I giri che tolgono materiale al contorno scelto: i fori (dentro) e gli scassi (contorni chiusi che si
    sovrappongono al bordo, come i quadrati sugli angoli). Non le isole dentro un foro."""
    g = an.giri[giro]
    x0, y0, x1, y1 = _bbox(g.poligono)
    cand = []
    for j, h in enumerate(an.giri):
        if j == giro or h.area >= g.area:
            continue
        a0, b0, a1, b1 = _bbox(h.poligono)
        if a1 < x0 - TOL or a0 > x1 + TOL or b1 < y0 - TOL or b0 > y1 + TOL:
            continue
        campione = h.poligono[::max(1, len(h.poligono) // 16)]
        if any(_dentro(q, g.poligono) and _dist_bordo(q, g.poligono) > TOL for q in campione):
            cand.append(j)
    # doppioni (lo stesso foro disegnato due volte) e isole dentro un altro taglio
    out, visti = [], set()
    for j in sorted(cand, key=lambda j: -an.giri[j].area):
        h = an.giri[j]
        chiave = (round(h.area, 1),) + tuple(round(v, 1) for v in _bbox(h.poligono))
        if chiave in visti:
            continue
        if any(_dentro(h.poligono[0], an.giri[k].poligono) for k in out):
            continue
        visti.add(chiave)
        out.append(j)
    return out


def pieghe_utili(an: Analisi, giro: int) -> list:
    """Le linee di piega che attraversano davvero il contorno scelto da bordo a bordo (non gli assi dei fori)."""
    g = an.giri[giro]
    bordi = [g.poligono] + [an.giri[j].poligono for j in tagli(an, giro)]

    def nel_pezzo(q):
        return _dentro(q, g.poligono) and not any(_dentro(q, b) for b in bordi[1:])
    out = []
    for t in an.pieghe:
        a, b = t.dati
        L = math.dist(a, b)
        if L < 1:
            continue
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if not nel_pezzo(m):
            continue
        # gli estremi stanno sul bordo (o fuori): vicino a un contorno di meno di 1 mm o fuori dal pezzo
        if all(not nel_pezzo(q) or min(_dist_bordo(q, x) for x in bordi) <= 1.0 for q in (a, b)):
            out.append(t)
    return out


def _dist_bordo(q, pts) -> float:
    best = float('inf')
    for i in range(len(pts)):
        a, b = pts[i - 1], pts[i]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0 if L2 < 1e-12 else max(0, min(1, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2))
        best = min(best, math.dist(q, (a[0] + dx * t, a[1] + dy * t)))
    return best


# ------------------------------------------------------------------------------------------ anteprima
def anteprima_svg(an: Analisi, larghezza: float = 900) -> dict:
    """SVG dei giri (cliccabili, data-giro) e delle linee di piega, per scegliere il pezzo."""
    pts = [p for g in an.giri for p in g.poligono] + [p for t in an.pieghe for p in t.punti()]
    if not pts:
        return {'svg': '', 'giri': []}
    x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
    x1, y1 = max(p[0] for p in pts), max(p[1] for p in pts)
    w, h = max(x1 - x0, 1), max(y1 - y0, 1)
    m = max(w, h) * 0.03
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0 - m:.2f} {-y1 - m:.2f} {w + 2 * m:.2f} {h + 2 * m:.2f}" '
           f'preserveAspectRatio="xMidYMid meet">']
    sw = max(w, h) / 600
    ordine = sorted(range(len(an.giri)), key=lambda i: -an.giri[i].area)
    for i in ordine:
        g = an.giri[i]
        d = 'M' + ' L'.join(f'{p[0]:.2f},{-p[1]:.2f}' for p in g.poligono) + ' Z'
        out.append(f'<path class="giro{" scelto" if i == an.scelto else ""}" data-giro="{i}" d="{d}" stroke-width="{sw:.3f}"/>')
    for i, t in enumerate(an.pieghe):
        (a, b) = t.dati
        out.append(f'<line class="piega" data-piega="{i}" x1="{a[0]:.2f}" y1="{-a[1]:.2f}" x2="{b[0]:.2f}" y2="{-b[1]:.2f}" stroke-width="{sw:.3f}" '
                   f'stroke-dasharray="{sw * 8:.2f} {sw * 3:.2f}"/>')
    out.append('</svg>')
    info = [{'index': i, 'area': g.area, 'fori': len(g.figli), 'livello': g.profondita,
             'size': [max(p[0] for p in g.poligono) - min(p[0] for p in g.poligono), max(p[1] for p in g.poligono) - min(p[1] for p in g.poligono)]}
            for i, g in enumerate(an.giri)]
    return {'svg': '\n'.join(out), 'giri': info}


# ------------------------------------------------------------------------------------------ costruzione
def _wire(g: Giro):
    """Il giro come Wire di build123d (linee, archi veri, spezzate)."""
    import build123d as bd
    pts = []                                       # punti in sequenza, gli archi col punto di mezzo
    for t, rev in g.tratti:
        if t.tipo == 'circle':
            c, r = t.dati
            return bd.Wire([bd.Edge.make_circle(r, bd.Plane.XY.move(bd.Location((c[0], c[1], 0))))])
        if t.tipo == 'line':
            q = list(t.dati)
        elif t.tipo == 'arc':
            q = t.punti(max(0.2, t.dati[1] / 20))
        else:
            q = list(t.dati)
        if rev:
            q = q[::-1]
        if t.tipo == 'arc':
            pts.append(('arc', q[0], q[len(q) // 2], q[-1]))
        else:
            for a, b in zip(q, q[1:]):
                pts.append(('line', a, b))
    # gli estremi vicini (entro TOL) si fanno coincidere: ognuno parte dove è finito il precedente
    edges, inizio = [], None
    cur = None
    for x in pts:
        a = cur if cur is not None else x[1]
        if inizio is None:
            inizio = a
        fine = x[-1]
        if x is pts[-1]:
            fine = inizio
        if math.dist(a, fine) < 1e-6:
            continue
        if x[0] == 'line':
            edges.append(bd.Edge.make_line((a[0], a[1], 0), (fine[0], fine[1], 0)))
        else:
            m = x[2]
            edges.append(bd.Edge.make_three_point_arc((a[0], a[1], 0), (m[0], m[1], 0), (fine[0], fine[1], 0)))
        cur = fine
    try:
        return bd.Wire(edges)
    except Exception:  # noqa: BLE001
        return bd.Wire.make_polygon([(p[0], p[1], 0) for p in g.poligono], close=True)


def _faccia(g: Giro):
    """La faccia piana di un giro, o None se il giro si incrocia."""
    import build123d as bd
    for fare in (lambda: bd.Face(_wire(g)),
                 lambda: bd.Face(bd.Wire.make_polygon([(p[0], p[1], 0) for p in g.poligono], close=True))):
        try:
            f = fare()
            if f.is_valid and f.area > 1e-6:
                return f
        except Exception:  # noqa: BLE001
            pass
    return None


def faccia_dxf(an: Analisi, giro: int):
    """Lo sviluppo del disegno: (contorno esterno pieno, contorno meno fori), sul piano XY."""
    import build123d as bd
    g = an.giri[giro]
    esterno = _faccia(g)
    if esterno is None:
        raise ImportError_('Il contorno scelto si incrocia da solo: non è lo sviluppo di un pezzo. Scegline un altro.')
    f = esterno
    for h in tagli(an, giro):
        fh = _faccia(an.giri[h])
        if fh is not None:
            f = f - fh
    facce = _facce_2d(f)
    if len(facce) != 1:
        raise ImportError_('Il contorno scelto, tolti i fori, non è un pezzo unico.')
    return esterno, facce[0]


def _dividi(esterno, linee):
    """Divide la faccia sulle linee di piega (allungate un po' oltre il contorno)."""
    import build123d as bd
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
    args, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    args.Append(esterno.wrapped)
    for (a, b) in linee:
        L = math.dist(a, b)
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        tools.Append(bd.Edge.make_line((a[0] - u[0] * 3, a[1] - u[1] * 3, 0), (b[0] + u[0] * 3, b[1] + u[1] * 3, 0)).wrapped)
    sp = BRepAlgoAPI_Splitter()
    sp.SetArguments(args)
    sp.SetTools(tools)
    sp.Build()
    if not sp.IsDone():
        raise ImportError_('Non riesco a dividere lo sviluppo sulle linee di piega.')
    return [f for f in bd.Shape.cast(sp.Shape()).faces() if f.area > 1e-6]


def costruisci(an: Analisi, giro: int, spessore: float, raggio: float, k: float | None, materiale: str = 'S235',
               nome: str = '', angolo: float = 90, verso: str = 'up', pieghe: list | None = None,
               metodo: str = 'k', bd90: float | None = None):
    """Dal giro scelto al Document di SteelCAD: lamiera con base, flange e flange sulla punta, più il taglio sullo
    sviluppo che lo rende uguale al disegno. pieghe: [{'angle','direction'}] per linea (come pieghe_utili)."""
    import build123d as bd

    from ..document import Document
    from ..sheetmetal import bend_values
    if spessore is None or spessore <= 0:
        raise ImportError_('Scrivi lo spessore della lamiera.')
    if raggio is None or raggio < 0:
        raise ImportError_('Serve il raggio interno di piega della tua piegatrice.')
    avvisi = []
    esterno, piatto = faccia_dxf(an, giro)
    linee = [t.dati for t in pieghe_utili(an, giro)]
    facce = _dividi(piatto, linee) if linee else [piatto]

    def faccia_di(q):
        v = bd.Vector(q[0], q[1], 0)
        for i, f in enumerate(facce):
            if f.distance_to(v) < 1e-6:
                return i
        return None
    archi = []                                       # (linea, faccia a sinistra, faccia a destra, normale verso sinistra)
    for i, (a, b) in enumerate(linee):
        L = math.dist(a, b)
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        n = (-u[1], u[0])
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        fa, fb = faccia_di((m[0] + n[0] * 0.3, m[1] + n[1] * 0.3)), faccia_di((m[0] - n[0] * 0.3, m[1] - n[1] * 0.3))
        if fa is None or fb is None or fa == fb:
            avvisi.append(f'La linea di piega {i + 1} non divide il pezzo: ignorata.')
            continue
        archi.append((i, fa, fb, n))
    base = max(range(len(facce)), key=lambda i: facce[i].area)
    figli: dict = {}
    visti, coda = {base}, [base]
    while coda:
        p = coda.pop(0)
        for i, fa, fb, n in archi:
            if p not in (fa, fb):
                continue
            c = fb if p == fa else fa
            if c in visti:
                continue
            nn = n if c == fa else (-n[0], -n[1])              # dalla madre verso la figlia
            figli.setdefault(p, []).append((c, i, nn))
            visti.add(c)
            coda.append(c)
    impost = pieghe or []

    def piega(i):
        d = impost[i] if i < len(impost) and impost[i] else {}
        ang = float(d.get('angle', angolo))
        return ang, d.get('direction', verso), bend_values(ang, raggio, spessore, metodo, k, bd90)

    # la base: le sue linee di piega spostate verso fuori di (ossb − BA/2): lì sta lo spigolo vivo esterno
    base_f = facce[base]
    for c, i, nn in figli.get(base, []):
        a, b = linee[i]
        bv = piega(i)[2]
        dlt = bv.ossb - bv.ba / 2
        sulla = [v for v in base_f.vertices() if abs((v.X - a[0]) * nn[0] + (v.Y - a[1]) * nn[1]) < 1e-4]
        if len(sulla) < 2 or abs(dlt) < 1e-9:
            continue
        L = math.dist(a, b)
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        ts = [(q.X - a[0]) * u[0] + (q.Y - a[1]) * u[1] for q in sulla]
        q0 = (a[0] + u[0] * min(ts), a[1] + u[1] * min(ts))
        q1 = (a[0] + u[0] * max(ts), a[1] + u[1] * max(ts))
        quattro = [(q0[0], q0[1], 0), (q1[0], q1[1], 0), (q1[0] + nn[0] * dlt, q1[1] + nn[1] * dlt, 0),
                   (q0[0] + nn[0] * dlt, q0[1] + nn[1] * dlt, 0)]
        striscia = bd.Face(bd.Wire.make_polygon(quattro, close=True))
        if striscia.normal_at().dot(base_f.normal_at()) < 0:          # orientata come la base, se no non si fondono
            striscia = bd.Face(bd.Wire.make_polygon(quattro[::-1], close=True))
        nuova = base_f.fuse(striscia) if dlt > 0 else base_f.cut(striscia)
        base_f = max(_facce_2d(nuova), key=lambda f: f.area)
    try:
        from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
        uni = ShapeUpgrade_UnifySameDomain(base_f.wrapped, True, True, False)
        uni.Build()
        base_f = max(_facce_2d(bd.Shape.cast(uni.Shape())), key=lambda f: f.area)
    except Exception:  # noqa: BLE001
        pass
    doc = Document(nome or Path(an.file).stem, materiale or 'S235')
    doc.set_parameter('sp', spessore)
    sk = doc.add_sketch('XY', 'Sviluppo importato')
    _sketch_da_faccia(sk, base_f)
    flange, contatore = [], [0]

    def lunghezza(c, i, nn):
        a, _ = linee[i]
        bv = piega(i)[2]
        tip = [x for x in figli.get(c, []) if abs(abs(x[2][0] * nn[0] + x[2][1] * nn[1]) - 1) < 1e-6]
        if tip:
            j = tip[0][1]
            aj, _ = linee[j]
            bj = piega(j)[2]
            d = (aj[0] - a[0]) * nn[0] + (aj[1] - a[1]) * nn[1]
            lf = d - bv.ba / 2 - bj.ba / 2
            return lf + bv.ossb + bj.ossb, tip[0], lf
        far = max((v.X - a[0]) * nn[0] + (v.Y - a[1]) * nn[1] for v in facce[c].vertices())
        lf = far - bv.ba / 2
        return lf + bv.ossb, None, lf

    def aggiungi(c, i, nn, madre=None, lato=None):
        ang, dirz, _ = piega(i)
        L, tip, lf = lunghezza(c, i, nn)
        if lf <= 0:
            raise ImportError_(f'Dopo la linea di piega {i + 1} non c’è abbastanza tratto dritto per raggio '
                               f'{raggio} e spessore {spessore}: controlla i dati della piegatrice.')
        contatore[0] += 1
        fid = f'FL{contatore[0]}'
        fl = {'id': fid, 'angle': ang, 'direction': dirz, 'position': 'inside', 'length': round(L, 3)}
        fl.update({'parent': madre} if madre else {'edge': lato})
        flange.append(fl)
        for x in figli.get(c, []):
            if tip is None or x[1] != tip[1]:
                avvisi.append(f'La linea di piega {x[1] + 1} non è parallela alla sua piega madre: per ora resta piana.')
        if tip:
            aggiungi(tip[0], tip[1], tip[2], madre=fid)

    for c, i, nn in figli.get(base, []):
        a, b = linee[i]
        bv = piega(i)[2]
        dlt = bv.ossb - bv.ba / 2
        lid = _linea_su(sk, (a[0] + nn[0] * dlt, a[1] + nn[1] * dlt), (b[0] - a[0], b[1] - a[1]))
        if lid is None:
            avvisi.append(f'Non trovo il lato della base per la linea di piega {i + 1}: resta piana.')
            continue
        aggiungi(c, i, nn, lato=lid)
    sm = doc.add_feature('sheet', nome or 'Lamiera', sketch=sk.id, thickness='sp', radius=raggio, method=metodo, k=k,
                         bd90=bd90, flanges=flange)
    res = doc.rebuild()
    if res.errors:
        raise ImportError_('Il pezzo non si costruisce: ' + res.errors[0].message)
    # fori e sagome: quello che lo sviluppo ha in più rispetto al disegno
    da_togliere = _unisci_se_toccano(_facce_2d(res.body.sheet.flat.cut(piatto), 0.005))
    if da_togliere:
        skf = doc.add_sketch({'flat': sm}, 'Fori e sagome dal DXF')
        for f in da_togliere:
            _sketch_da_faccia(skf, f, fori=True)
        doc.add_feature('sheet_cut', 'Fori e sagome dal DXF', sketch=skf.id)
        res = doc.rebuild()
        if res.errors:
            raise ImportError_('I fori del disegno non si riportano sul pezzo: ' + res.errors[0].message)
    manca = sum(f.area for f in _facce_2d(piatto.cut(res.body.sheet.flat), 0.005))
    if manca > 1.0:
        avvisi.append(f'{manca:.0f} mm² del disegno non entrano nel pezzo piegato (per esempio agli angoli tra le flange).')
    return doc, {'flange': len(flange), 'pieghe': len(linee), 'avvisi': avvisi,
                 'area_dxf': piatto.area, 'area_pezzo': res.body.sheet.flat_area}


def _unisci_se_toccano(facce: list) -> list:
    """Due zone da tagliare che si toccano in un punto fanno un contorno ambiguo per lo sketch: si uniscono,
    allargate di un centesimo di millimetro."""
    import build123d as bd
    gruppi = []
    for f in facce:
        vicini = [g for g in gruppi if any(f.distance_to(h) < 1e-6 for h in g)]
        nuovo = [f] + [h for g in vicini for h in g]
        gruppi = [g for g in gruppi if g not in vicini] + [nuovo]
    out = []
    for g in gruppi:
        if len(g) == 1:
            out.append(g[0])
            continue
        larghe = [x for f in g for x in _facce_2d(bd.offset(f, amount=0.01, kind=bd.Kind.INTERSECTION))]
        u = larghe[0]
        for x in larghe[1:]:
            u = u.fuse(x)
        u = u.clean() if hasattr(u, 'clean') else u
        out += _facce_2d(u)
    return out


def _facce_2d(x, spessore_min: float = 0.0) -> list:
    """Le facce di un risultato 2D; con spessore_min si scartano le strisce più sottili (rumore numerico)."""
    if x is None:
        return []
    fs = x.faces() if hasattr(x, 'faces') else [x]
    return [f for f in fs if f.area > 0.01 and 2 * f.area / max(f.outer_wire().length, 1e-9) > spessore_min]


def _linea_su(sk, A, d):
    """L'id della linea dello sketch che sta sulla retta per A con direzione d (la più lunga)."""
    L = math.hypot(*d)
    u = (d[0] / L, d[1] / L)
    best = None
    for k, e in sk.entities.items():
        if e['kind'] != 'line':
            continue
        p, q = sk.entities[e['a']], sk.entities[e['b']]
        dist = lambda x: abs((x['x'] - A[0]) * -u[1] + (x['y'] - A[1]) * u[0])  # noqa: E731
        if dist(p) < 1e-3 and dist(q) < 1e-3:
            lung = math.hypot(q['x'] - p['x'], q['y'] - p['y'])
            if best is None or lung > best[0]:
                best = (lung, k)
    return best[1] if best else None


def _sketch_da_faccia(sk, face, fori: bool = False):
    """I contorni di una faccia piana (sul piano XY) come entità dello sketch, con i punti fissi.
    Con fori=True anche i contorni interni (per i tagli)."""
    import build123d as bd
    punti: dict = {}

    def pt(v):
        key = (round(v.X, 5), round(v.Y, 5))
        if key not in punti:
            pid = sk.point(v.X, v.Y)
            sk.constrain('fix', pid)
            punti[key] = pid
        return punti[key]

    fili = [face.outer_wire()] + (list(face.inner_wires()) if fori else [])
    for w in fili:
        for e in w.edges():
            gt = e.geom_type
            if gt == bd.GeomType.LINE:
                a, b = pt(e.start_point()), pt(e.end_point())
                if a != b:
                    sk.line(a, b)
            elif gt == bd.GeomType.CIRCLE and e.is_closed:
                c = e.arc_center
                cp = sk.point(c.X, c.Y)
                sk.constrain('fix', cp)
                cid = sk.circle(cp, e.radius)
                sk.dimension('diameter', cid, value=round(2 * e.radius, 6))
            elif gt == bd.GeomType.CIRCLE:
                a, b, m, c = e.start_point(), e.end_point(), e.position_at(0.5), e.arc_center
                ang = lambda q: math.atan2(q.Y - c.Y, q.X - c.X)  # noqa: E731
                a0 = ang(a)
                giro = lambda x: (x - a0) % (2 * math.pi)  # noqa: E731
                antiorario = giro(ang(m)) < giro(ang(b))
                cp = sk.point(c.X, c.Y)                    # estremi fissi: il raggio è già deciso
                pa, pb = pt(a), pt(b)
                sk.arc(cp, pa, pb) if antiorario else sk.arc(cp, pb, pa)
            else:
                ids = [pt(e.position_at(i / 24)) for i in range(25)]
                for x, y in zip(ids, ids[1:]):
                    if x != y:
                        sk.line(x, y)
