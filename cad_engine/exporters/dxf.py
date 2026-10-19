"""DXF di produzione per pezzi piani (piastre, staffe piane): contorno esterno + fori.

Prima di scrivere si controlla che il pezzo sia davvero piano (un prisma: tutte
le facce o parallele alla faccia grande o perpendicolari). Dopo aver scritto il
file lo si rilegge e si controlla: contorni chiusi, niente doppioni, niente
sovrapposizioni, niente microsegmenti, unità in mm. Un DXF che non passa i
controlli non viene lasciato su disco.

Layer: CUT (taglio), BEND (pieghe), MARK (marcatura), ENGRAVE (incisione).
Per i pezzi piani si usa solo CUT; lo sviluppo della lamiera mette le pieghe su BEND
(linea tratteggiata + scritta "FL1 SU 90° R2"). I controlli sui contorni guardano solo il taglio.
"""
from __future__ import annotations

import math
from pathlib import Path

import build123d as bd
import ezdxf
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane

from ..errors import ExportError
from ..topology.naming import _faces_of
from ..units import MICRO_SEGMENT, fmt_mm

LAYERS = {'CUT': 7, 'BEND': 2, 'MARK': 3, 'ENGRAVE': 4}
TOL = 1e-4   # mm, per confrontare estremità nel file


def flat_reference(shape):
    """La faccia grande del pezzo piano, il suo piano e lo spessore; errore se il pezzo non è piano."""
    facce = [bd.Face(f) for f in _faces_of(shape)]
    piane = [f for f in facce if BRepAdaptor_Surface(f.wrapped).GetType() == GeomAbs_Plane]
    if not piane:
        raise ExportError('Il pezzo non ha facce piane: il DXF si fa solo per pezzi piani.')
    ref = max(piane, key=lambda f: f.area)
    n = ref.normal_at()
    opposte = []
    for f in facce:
        if f is ref:
            continue
        tipo = BRepAdaptor_Surface(f.wrapped).GetType()
        if tipo == GeomAbs_Plane:
            d = abs(f.normal_at().dot(n))
            if d > 1 - 1e-6:
                opposte.append(f)
                continue
            if d < 1e-6:
                continue
        elif tipo == GeomAbs_Cylinder:
            ax = BRepAdaptor_Surface(f.wrapped).Cylinder().Axis().Direction()
            if abs(abs(bd.Vector(ax.X(), ax.Y(), ax.Z()).dot(n)) - 1) < 1e-6:
                continue
        raise ExportError('Il pezzo non è una lamiera piana: ha facce inclinate, raccordi sugli spigoli di sopra '
                          'o pieghe. Per i pezzi piegati serve lo sviluppo (Milestone 3).')
    spessori = {round(abs((f.center() - ref.center()).dot(n)), 6) for f in opposte}
    if len(spessori) != 1:
        raise ExportError('Il pezzo ha più spessori (gradini o tasche non passanti): il DXF di taglio sarebbe '
                          'ambiguo.')
    origin = n * n.dot(ref.center())
    x = bd.Vector(1, 0, 0)
    if abs(n.dot(x)) > 0.99:
        x = bd.Vector(0, 1, 0)
    x = (x - n * n.dot(x)).normalized()
    return ref, bd.Plane(origin=origin, x_dir=x, z_dir=n), spessori.pop()


def export_flat(shape, path, *, name: str = '') -> dict:
    ref, plane, spessore = flat_reference(shape)
    doc = _new_doc()
    msp = doc.modelspace()
    avvisi = _write_face(msp, ref, plane)
    return _finish(doc, path, avvisi, spessore)


def _new_doc():
    doc = ezdxf.new('R2010', setup=True)
    doc.header['$INSUNITS'] = 4        # millimetri
    doc.header['$MEASUREMENT'] = 1     # metrico
    for nome, col in LAYERS.items():
        if nome not in doc.layers:
            doc.layers.add(nome, color=col)
    return doc


def _finish(doc, path, avvisi, spessore, extra=None) -> dict:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    doc.saveas(tmp)
    report = check(tmp)
    report['thickness_mm'] = spessore
    report['warnings'] = avvisi + report['warnings']
    report.update(extra or {})
    if report['problems']:
        tmp.unlink(missing_ok=True)
        raise ExportError('Il DXF non è pronto per il taglio: ' + '; '.join(report['problems']) + '.')
    tmp.replace(path)
    report['path'] = str(path)
    return report


def export_flat_pattern(sheet, path) -> dict:
    """Lo sviluppo di una lamiera piegata: contorno e fori su CUT, linee di piega su BEND con la scritta."""
    if sheet.flat is None:
        raise ExportError('La lamiera non ha uno sviluppo.')
    doc = _new_doc()
    msp = doc.modelspace()
    avvisi = _write_face(msp, sheet.flat, sheet.plane)
    h = max(2.5, min(8.0, sheet.thickness * 2))
    for a, b, testo in sheet.bend_lines:
        msp.add_line(a, b, dxfattribs={'layer': 'BEND', 'linetype': 'DASHED'})
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        if ang > 90 or ang <= -90:
            ang -= 180
        msp.add_text(testo, height=h, rotation=ang, dxfattribs={'layer': 'BEND'}).set_placement(
            (m[0], m[1] + h * 0.4), align=ezdxf.enums.TextEntityAlignment.BOTTOM_CENTER)
    return _finish(doc, path, avvisi, sheet.thickness, {'bend_lines': len(sheet.bend_lines)})


def _write_face(msp, ref, plane) -> list:
    loc = lambda v: plane.to_local_coords(v)  # noqa: E731
    avvisi = []
    for e in ref.edges():
        gt = e.geom_type
        if gt == bd.GeomType.LINE:
            a, b = loc(e.start_point()), loc(e.end_point())
            msp.add_line((a.X, a.Y), (b.X, b.Y), dxfattribs={'layer': 'CUT'})
        elif gt == bd.GeomType.CIRCLE:
            c = loc(e.arc_center)
            r = e.radius
            if e.is_closed:
                msp.add_circle((c.X, c.Y), r, dxfattribs={'layer': 'CUT'})
            else:
                a, b, m = loc(e.start_point()), loc(e.end_point()), loc(e.position_at(0.5))
                t0 = math.degrees(math.atan2(a.Y - c.Y, a.X - c.X))
                t1 = math.degrees(math.atan2(b.Y - c.Y, b.X - c.X))
                tm = math.degrees(math.atan2(m.Y - c.Y, m.X - c.X))
                if not _ccw_contains(t0, t1, tm):
                    t0, t1 = t1, t0
                msp.add_arc((c.X, c.Y), r, t0 % 360, t1 % 360, dxfattribs={'layer': 'CUT'})
        else:
            pts = [loc(p) for p in e.positions([i / 64 for i in range(65)])]
            msp.add_lwpolyline([(p.X, p.Y) for p in pts], dxfattribs={'layer': 'CUT'})
            avvisi.append(f'Una curva ({gt.name.lower()}) è stata approssimata con 64 segmenti.')
    return avvisi


def _ccw_contains(t0: float, t1: float, tm: float) -> bool:
    span = (t1 - t0) % 360
    return (tm - t0) % 360 < span


def check(path) -> dict:
    """Controlli di produzione su un DXF già scritto (si può usare anche su DXF di altri)."""
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    problemi, avvisi = [], []
    if doc.header.get('$INSUNITS', 0) != 4:
        problemi.append('le unità del file non sono millimetri')
    segmenti = []       # (tipo, dati, estremo a, estremo b)
    cerchi = []
    pieghe = 0
    for ent in msp:
        t = ent.dxftype()
        if ent.dxf.layer in ('BEND', 'MARK', 'ENGRAVE'):
            pieghe += ent.dxf.layer == 'BEND' and t == 'LINE'
            continue
        if t == 'LINE':
            a, b = (ent.dxf.start.x, ent.dxf.start.y), (ent.dxf.end.x, ent.dxf.end.y)
            lung = math.dist(a, b)
            segmenti.append(('LINE', (a, b), a, b, lung))
        elif t == 'ARC':
            c, r = (ent.dxf.center.x, ent.dxf.center.y), ent.dxf.radius
            t0, t1 = math.radians(ent.dxf.start_angle), math.radians(ent.dxf.end_angle)
            a = (c[0] + r * math.cos(t0), c[1] + r * math.sin(t0))
            b = (c[0] + r * math.cos(t1), c[1] + r * math.sin(t1))
            lung = r * (((ent.dxf.end_angle - ent.dxf.start_angle) % 360) * math.pi / 180)
            segmenti.append(('ARC', (c, r, ent.dxf.start_angle % 360, ent.dxf.end_angle % 360), a, b, lung))
        elif t == 'CIRCLE':
            cerchi.append(((ent.dxf.center.x, ent.dxf.center.y), ent.dxf.radius))
        elif t == 'LWPOLYLINE':
            pts = [(p[0], p[1]) for p in ent.get_points('xy')]
            for i in range(len(pts) - 1):
                segmenti.append(('LINE', (pts[i], pts[i + 1]), pts[i], pts[i + 1], math.dist(pts[i], pts[i + 1])))
            if ent.closed and len(pts) > 1:
                segmenti.append(('LINE', (pts[-1], pts[0]), pts[-1], pts[0], math.dist(pts[-1], pts[0])))
        elif t == 'SPLINE':
            avvisi.append('il file contiene spline: non tutti i CAM le leggono bene')
        else:
            avvisi.append(f'entità {t} ignorata dai controlli')

    micro = [s for s in segmenti if s[4] < MICRO_SEGMENT]
    if micro:
        problemi.append(f'{len(micro)} microsegmenti più corti di {fmt_mm(MICRO_SEGMENT)} mm')
    # doppioni e sovrapposizioni
    doppi = 0
    for i in range(len(segmenti)):
        for j in range(i + 1, len(segmenti)):
            if _same(segmenti[i], segmenti[j]):
                doppi += 1
            elif segmenti[i][0] == segmenti[j][0] == 'LINE' and _overlap_lines(segmenti[i][1], segmenti[j][1]):
                doppi += 1
    for i in range(len(cerchi)):
        for j in range(i + 1, len(cerchi)):
            if math.dist(cerchi[i][0], cerchi[j][0]) < TOL and abs(cerchi[i][1] - cerchi[j][1]) < TOL:
                doppi += 1
    if doppi:
        problemi.append(f'{doppi} entità doppie o sovrapposte')
    # contorni chiusi: ogni estremità deve toccarne esattamente un'altra
    nodi: list[tuple[float, float]] = []
    gradi: list[int] = []

    def nodo(p):
        for k, q in enumerate(nodi):
            if math.dist(p, q) < TOL:
                gradi[k] += 1
                return
        nodi.append(p)
        gradi.append(1)

    for s in segmenti:
        nodo(s[2])
        nodo(s[3])
    aperti = [nodi[k] for k, g in enumerate(gradi) if g != 2]
    if aperti:
        x, y = aperti[0]
        problemi.append(f'contorno non chiuso ({len(aperti)} estremità libere, la prima in '
                        f'{fmt_mm(x)}; {fmt_mm(y)})')
    contorni = _count_loops(segmenti, nodi) + len(cerchi)
    xs = [p[0] for s in segmenti for p in (s[2], s[3])] + [c[0][0] + d * c[1] for c in cerchi for d in (-1, 1)]
    ys = [p[1] for s in segmenti for p in (s[2], s[3])] + [c[0][1] + d * c[1] for c in cerchi for d in (-1, 1)]
    for sgm in segmenti:                     # gli archi possono sporgere oltre i loro estremi: anche i quadranti
        if sgm[0] == 'ARC':
            (cx, cy), r, a0, a1 = sgm[1]
            for q in (0, 90, 180, 270):
                if (q - a0) % 360 <= (a1 - a0) % 360:
                    xs.append(cx + r * math.cos(math.radians(q)))
                    ys.append(cy + r * math.sin(math.radians(q)))
    size = [max(xs) - min(xs), max(ys) - min(ys)] if xs else [0, 0]
    return {'ok': not problemi, 'problems': problemi, 'warnings': avvisi, 'contours': contorni,
            'entities': len(segmenti) + len(cerchi), 'circles': len(cerchi), 'size_mm': size,
            'circle_diameters': sorted(round(2 * c[1], 6) for c in cerchi), 'bend_lines_found': pieghe}


def _same(s1, s2) -> bool:
    if s1[0] != s2[0]:
        return False
    if s1[0] == 'LINE':
        (a1, b1), (a2, b2) = s1[1], s2[1]
        return ((math.dist(a1, a2) < TOL and math.dist(b1, b2) < TOL) or
                (math.dist(a1, b2) < TOL and math.dist(b1, a2) < TOL))
    (c1, r1, s_1, e1), (c2, r2, s_2, e2) = s1[1], s2[1]
    return math.dist(c1, c2) < TOL and abs(r1 - r2) < TOL and abs(s_1 - s_2) < 1e-6 and abs(e1 - e2) < 1e-6


def _overlap_lines(l1, l2) -> bool:
    (a, b), (c, d) = l1, l2
    ux, uy = b[0] - a[0], b[1] - a[1]
    lu = math.hypot(ux, uy)
    if lu < TOL:
        return False
    ux, uy = ux / lu, uy / lu
    for p in (c, d):
        if abs((p[0] - a[0]) * uy - (p[1] - a[1]) * ux) > TOL:
            return False
    t = sorted(((p[0] - a[0]) * ux + (p[1] - a[1]) * uy) for p in (c, d))
    return min(lu, t[1]) - max(0.0, t[0]) > TOL


def _count_loops(segmenti, nodi) -> int:
    def idx(p):
        return next(k for k, q in enumerate(nodi) if math.dist(p, q) < TOL)
    parent = list(range(len(nodi)))

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k
    for s in segmenti:
        a, b = find(idx(s[2])), find(idx(s[3]))
        parent[a] = b
    return len({find(k) for k in range(len(nodi))})
