"""Disegno libero degli sketch dall'interfaccia: linee, rettangoli, cerchi, cancellazione.

Ogni forma disegnata arriva già con vincoli e quote, così il pezzo resta modificabile:
- i tratti quasi orizzontali/verticali diventano orizzontali/verticali;
- ogni tratto ha la sua lunghezza (in un contorno chiuso si salta l'ultimo orizzontale e
  l'ultimo verticale: sono già determinati dagli altri, quotarli sarebbe una quota doppia);
- il primo punto, se non è un punto che c'era già, prende la posizione dall'origine
  (distanza orizzontale e verticale);
- i cerchi hanno il diametro e la posizione del centro.
"""
from __future__ import annotations

import math

import build123d as bd

from cad_engine.errors import SketchError, SteelCADError
from cad_engine.sketch import solve
from cad_engine.sketch.model import ORIGIN
from cad_engine.sketch.profile import PLANES

HV_TOL = math.radians(3)      # entro 3° un tratto diventa orizzontale o verticale


def view(doc, sid: str, body=None) -> dict:
    """Lo sketch risolto, anche se il contorno è ancora aperto (mentre si disegna)."""
    sk = doc.sketch(sid)
    if isinstance(sk.plane, str):
        pl = PLANES[sk.plane]
    else:
        if body is None:
            raise SteelCADError('La faccia di questo sketch non c’è più nel pezzo.', code='piano')
        pl = doc._plane(sk, body)
    try:
        ss = solve(sk, doc.resolved_parameters())
        pts, stato = ss.points, ss.status.message
    except SteelCADError as ex:
        pts = {k: (e['x'], e['y']) for k, e in sk.entities.items() if e['kind'] == 'point'}
        stato = ex.message
    fr = next((f for f in (doc.last.features if doc.last else []) if f.id == sid), None)
    aperto = False
    if fr is not None and (not fr.ok or (fr.message or '').startswith('Il profilo non è chiuso')):
        stato = fr.message
        if stato.startswith('Il profilo non è chiuso'):
            aperto = True               # per uno scheletro di struttura (o una piega su linea) le linee aperte vanno bene
            if isinstance(sk.plane, dict):                       # su una faccia o sullo sviluppo di una lamiera
                stato = ('Linee aperte: vanno bene per la piega su linea, le persiane o la lamiera a contorno. '
                         'Per tagliare o aggiungere materiale il contorno va chiuso.')
            else:
                stato = ('Profilo aperto: «Estrudi in lamiera» lo fa diventare lamiera piegata (gli archi a colpi), '
                         '«Crea struttura» lo fa in tubi. Per una lamiera piana o una piastra il contorno va chiuso.')
    g = lambda p: [(q := pl.from_local_coords(p)).X, q.Y, q.Z]  # noqa: E731
    out = {'id': sid, 'name': sk.name, 'plane': sk.plane, 'status': stato, 'ok': bool(fr and fr.ok), 'open': aperto,
           'origin': g((0, 0)), 'x_dir': [pl.x_dir.X, pl.x_dir.Y, pl.x_dir.Z], 'y_dir': [pl.y_dir.X, pl.y_dir.Y, pl.y_dir.Z],
           'z_dir': [pl.z_dir.X, pl.z_dir.Y, pl.z_dir.Z],
           'points': [{'id': k, 'xy': list(v), 'xyz': g(v)} for k, v in pts.items()
                      if not sk.entities.get(k, {}).get('construction') or sk.entities.get(k, {}).get('ref')],
           'lines': [], 'circles': [], 'arcs': [], 'texts': [],
           'used_by': [f['id'] for f in doc.features if not hasattr(f, 'entities') and f.get('sketch') == sid],
           'on_face': sk.plane.get('face') if isinstance(sk.plane, dict) else None,
           'on_flat': sk.plane.get('flat') if isinstance(sk.plane, dict) else None}
    fatto = (doc._sketch_results or {}).get(sid) if hasattr(doc, '_sketch_results') else None
    out['profiles'] = len(fatto[1].faces) if fatto and fatto[1] is not None else 0
    out['sciolte'] = list(getattr(fatto[1], 'sciolte', []) or []) if fatto and fatto[1] is not None else []
    if out['sciolte'] and out['ok']:
        n = len(out['sciolte'])
        out['status'] = (f'{n} linea sciolta' if n == 1 else f'{n} linee sciolte') + ' (in rosso) non chiude nessun contorno: ' \
            + 'non conta per il taglio. Se non serve, selezionala ed Elimina.'
    out['drawn'] = sum(1 for e in sk.entities.values() if e['kind'] in ('line', 'circle', 'arc', 'text') and not e.get('ref'))
    from cad_engine.sketch import testo as testo_mod
    for k, e in sk.entities.items():
        if e['kind'] != 'text' or e['center'] not in pts:
            continue
        x, y = pts[e['center']]
        if e.get('stencil'):
            tr = [c + c[:1] for c in testo_mod.contorni(e['text'], e['h'], x, y, e.get('angle', 0), e['stencil'])]
            w = testo_mod.larghezza_stencil(e['text'], e['h'], e['stencil'])
        else:
            tr, w = testo_mod.tratti(e['text'], e['h'], x, y, e.get('angle', 0)), testo_mod.larghezza(e['text'], e['h'])
        out['texts'].append({'id': k, 'text': e['text'], 'h': e['h'], 'angle': e.get('angle', 0), 'xy': [x, y],
                             'anchor_id': e['center'], 'strokes': [[g(q) for q in t] for t in tr], 'w': w,
                             'stencil': e.get('stencil')})
    if out['texts'] and isinstance(sk.plane, dict) and not out['profiles'] and not any(t.get('stencil') for t in out['texts']):
        out['status'] = (f'{len(out["texts"])} testo' if len(out['texts']) == 1 else f'{len(out["texts"])} testi') + \
            ': «Marca col laser» li mette sul layer di marcatura del DXF (si vedono anche sul pezzo).'
    if out['on_flat']:
        out['where'] = 'sullo sviluppo della lamiera'
    elif out['on_face']:
        testo = doc.describe_face(out['on_face']).replace('"', '')
        for art, prep in (('la ', 'sulla '), ('il ', 'sul '), ('lo ', 'sullo '), ('l’', 'sull’')):
            if testo.startswith(art):
                testo = prep + testo[len(art):]
                break
        else:
            testo = 'su ' + testo
        out['where'] = testo
    elif (sk.name or '').startswith('Contorno sul piano '):        # pezzo nuovo nato nell'assieme: dice su che faccia
        out['where'] = sk.name[len('Contorno '):]
    else:
        out['where'] = {'XY': 'sul piano XY (dall’alto)', 'XZ': 'sul piano XZ (di fronte)',
                        'YZ': 'sul piano YZ (di lato)'}.get(sk.plane, 'sul piano')
    out['xray'] = any(e.get('xray') and e['kind'] != 'point' for e in sk.entities.values())
    if out['on_flat']:
        out['on_sheet'] = True
    elif out['on_face']:
        try:
            f0 = doc.feature(out['on_face'].split('/')[0])
            out['on_sheet'] = not hasattr(f0, 'entities') and f0.get('type') == 'sheet'
        except SteelCADError:
            out['on_sheet'] = False
    for k, e in sk.entities.items():
        if e['kind'] == 'line':
            out['lines'].append({'id': k, 'a': e['a'], 'b': e['b'], 'label': sk.describe(k),
                                 'construction': bool(e.get('construction')), 'ref': bool(e.get('ref')), 'xray': bool(e.get('xray')), 'piega': e.get('linea_piega'),
                                 'pa': g(pts[e['a']]), 'pb': g(pts[e['b']]),
                                 'xa': list(pts[e['a']]), 'xb': list(pts[e['b']])})
        elif e['kind'] == 'arc':
            c, a, b = pts[e['center']], pts[e['start']], pts[e['end']]
            t0 = math.atan2(a[1] - c[1], a[0] - c[0])
            t1 = math.atan2(b[1] - c[1], b[0] - c[0])
            while t1 <= t0:
                t1 += 2 * math.pi
            out['arcs'].append({'id': k, 'center': g(c), 'xc': list(c), 'r': math.hypot(a[0] - c[0], a[1] - c[1]),
                                'a0': t0, 'a1': t1, 'label': sk.describe(k), 'start': e['start'], 'end': e['end'],
                                'center_id': e['center'],
                                'construction': bool(e.get('construction')), 'ref': bool(e.get('ref')), 'xray': bool(e.get('xray'))})
        elif e['kind'] == 'circle':
            c = pts[e['center']]
            r = e['r']
            try:
                r = ss.circles[k][1]
            except Exception:  # noqa: BLE001
                pass
            out['circles'].append({'id': k, 'center': g(c), 'r': r, 'label': sk.describe(k), 'xc': list(c),
                                   'center_id': e['center'], 'hole': e.get('hole'),
                                   'construction': bool(e.get('construction')), 'ref': bool(e.get('ref')), 'xray': bool(e.get('xray'))})
    return out


def _bend_edges(body_shape, face) -> set:
    """Gli spigoli della faccia che confinano con una faccia cilindrica del pezzo (l'inizio di una piega)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as Mappa
    m = Mappa()
    TopExp.MapShapesAndAncestors_s(body_shape, TopAbs_EDGE, TopAbs_FACE, m)
    out = set()
    for e in face.edges():
        if not m.Contains(e.wrapped):
            continue
        for f in m.FindFromKey(e.wrapped):
            if not f.IsSame(face.wrapped) and BRepAdaptor_Surface(TopoDS.Face(f)).GetType() == GeomAbs_Cylinder:
                out.add(e)
                break
    return out


def add_reference_edges(sk, face, plane, body_shape=None) -> list[str]:
    """I bordi della faccia (o dello sviluppo) su cui si disegna, come linee di costruzione fisse: ci si
    aggancia, ci si quota e ci si fa l'offset ("10 mm dal bordo del pezzo"). Non si tagliano: sono guide."""
    punti: dict = {}
    # i punti arancio che ci sono già (bordi rifatti): si riusano, così il disegno resta attaccato
    for pid, e in sk.entities.items():
        if e['kind'] == 'point' and e.get('ref'):
            punti.setdefault((round(e['x'], 4), round(e['y'], 4)), pid)

    def pt(v):
        q = plane.to_local_coords(v)
        k = (round(q.X, 4), round(q.Y, 4))
        if k not in punti:
            pid = sk.point(q.X, q.Y, construction=True)
            sk.entities[pid]['ref'] = True              # si vede e ci si aggancia, anche se è di costruzione
            sk.constrain('fix', pid)
            punti[k] = pid
        elif not any(c['type'] == 'fix' and c['refs'] == [punti[k]] for c in sk.constraints.values()):
            sk.constrain('fix', punti[k])
        return punti[k]

    pieghe = _bend_edges(body_shape, face) if body_shape is not None else set()
    fatte = []
    for e in face.edges():
        if e.geom_type == bd.GeomType.LINE:
            a, b = pt(e.start_point()), pt(e.end_point())
            if a != b:
                lid = sk.line(a, b, construction=True, label='bordo del pezzo')
                sk.entities[lid]['ref'] = True
                if e in pieghe:
                    sk.entities[lid]['piega'] = True        # qui comincia una piega
                fatte.append(lid)
        elif e.geom_type == bd.GeomType.CIRCLE and abs(e.length - 2 * math.pi * e.radius) < 1e-6:
            c = pt(e.arc_center)
            cid = sk.circle(c, e.radius, construction=True)
            sk.entities[cid]['ref'] = True
            sk.dimension('diameter', cid, value=_r(2 * e.radius))
            fatte.append(cid)
        elif e.geom_type == bd.GeomType.CIRCLE:
            # uno spigolo raccordato: arco con gli estremi fissi; il centro lo trova il raggio (se fosse fisso
            # anche lui, il vincolo sarebbe di troppo)
            a, b = pt(e.start_point()), pt(e.end_point())
            qc, qm = plane.to_local_coords(e.arc_center), plane.to_local_coords(e.position_at(0.5))
            ang = lambda x, y: math.atan2(y - qc.Y, x - qc.X)  # noqa: E731
            a0 = ang(sk.entities[a]['x'], sk.entities[a]['y'])
            giro = lambda t: (t - a0) % (2 * math.pi)  # noqa: E731
            antiorario = giro(ang(qm.X, qm.Y)) < giro(ang(sk.entities[b]['x'], sk.entities[b]['y']))
            c = sk.point(qc.X, qc.Y, construction=True)
            sk.entities[c]['ref'] = True
            arco = sk.arc(c, a, b, construction=True) if antiorario else sk.arc(c, b, a, construction=True)
            sk.entities[arco]['ref'] = True
            sk.dimension('radius', arco, value=_r(e.radius))
            fatte.append(arco)
    return fatte


def add_bend_references(sk, data) -> list[str]:
    """Sullo sviluppo: le linee di piega e i due bordi di ogni striscia di piega come linee arancio fisse (tratteggiate),
    come i bordi del pezzo: ci si aggancia, ci si quota, le linee disegnate si accorciano lì (21/10: per tagliare a
    45° attraverso le pieghe bisogna sapere dove comincia e finisce ognuna). Non tagliano niente: sono guide."""
    punti: dict = {}
    for pid, e in sk.entities.items():
        if e['kind'] == 'point' and e.get('ref'):
            punti.setdefault((round(e['x'], 4), round(e['y'], 4)), pid)

    def pt(x, y):
        k = (round(x, 4), round(y, 4))
        if k not in punti:
            pid = sk.point(x, y, construction=True)
            sk.entities[pid]['ref'] = True
            sk.constrain('fix', pid)
            punti[k] = pid
        return punti[k]

    def tratti(a, b):
        """La linea solo dove c'è lamiera (dopo uno scasso la piega non c'è più): i tratti dentro lo sviluppo."""
        try:
            e = bd.Edge.make_line(data.plane.from_local_coords(tuple(a)), data.plane.from_local_coords(tuple(b)))
            dentro = e.intersect(data.flat)
            pezzi = [x for x in (dentro.edges() if dentro is not None else []) if x.length > 0.05]
        except Exception:  # noqa: BLE001 - se l'intersezione non riesce, la linea intera
            return [(a, b)]
        out = []
        for x in pezzi:
            q0, q1 = data.plane.to_local_coords(x.start_point()), data.plane.to_local_coords(x.end_point())
            out.append(((q0.X, q0.Y), (q1.X, q1.Y)))
        return out

    def linea(a, b, label, tipo):
        ids = []
        for p, q in tratti(a, b):
            if math.hypot(p[0] - q[0], p[1] - q[1]) < 1e-6:
                continue
            lid = sk.line(pt(*p), pt(*q), construction=True, label=label)
            sk.entities[lid]['ref'] = True
            sk.entities[lid]['linea_piega'] = tipo
            ids.append(lid)
        return ids

    fatte = []
    for a, b, testo in data.bend_lines:
        nome = str(testo).split(' ')[0] if testo else ''
        fatte += linea(a, b, f'linea di piega {nome}'.strip(), 'centro')
    for z in data.bend_zones():
        if math.hypot(z[3][0] - z[0][0], z[3][1] - z[0][1]) < 0.05:
            continue                                     # piega senza striscia (BA nullo): basta la linea
        fatte += linea(z[0], z[1], 'inizio della piega', 'bordo')
        fatte += linea(z[3], z[2], 'fine della piega', 'bordo')
    return fatte


def refresh_reference_edges(sk, face, plane, body_shape=None) -> list[str]:
    """Rifà i bordi arancio dalla faccia vera (se ne mancano pezzi): via le linee/archi/cerchi del bordo, i
    punti restano (il disegno ci è attaccato) e si riusano."""
    via = [k for k, e in sk.entities.items() if e['kind'] in ('line', 'arc', 'circle') and e.get('ref') and not e.get('proj')
           and not e.get('linea_piega')]
    for k in via:
        del sk.entities[k]
    for k, c in list(sk.constraints.items()):
        if any(r not in sk.entities for r in c['refs']):
            del sk.constraints[k]
    return add_reference_edges(sk, face, plane, body_shape)


def _snap_hv(a, b):
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    for k in range(-4, 5):
        if abs(ang - k * math.pi / 2) < HV_TOL:
            return 'horizontal' if k % 2 == 0 else 'vertical'
    return None


def _position(sk, pid, xy):
    """Il primo punto di una forma prende la posizione dall'origine (se non è l'origine)."""
    if pid == ORIGIN:
        return
    sk.dimension('hdistance', ORIGIN, pid, value=_r(xy[0]))
    sk.dimension('vdistance', ORIGIN, pid, value=_r(xy[1]))


def _r(v: float):
    # sei decimali: arrotondare al centesimo la quota di una linea inclinata (6,7058 → 6,71) spostava i punti
    # per rispettarla (21/10: una punta Ø11,5 veniva Ø11,51 dopo la rivoluzione)
    v = round(float(v), 6)
    return int(v) if v.is_integer() else v


def _point_ref(sk, p):
    """p è un id di punto esistente, [x, y], oppure un aggancio legato a linee:
    {'mid': linea} metà, {'cross': [l1, l2]} incrocio, {'on': linea, 'xy': [x, y]} sulla linea.
    Ritorna (id, xy, nuovo?). Un punto agganciato resta legato: se sposti la linea, il punto la segue."""
    if isinstance(p, dict):
        x, y = (float(v) for v in p.get('xy', (0, 0)))
        if 'mid' in p:
            e = sk.entities[p['mid']]
            (ax, ay), (bx, by) = (sk.entities[e['a']]['x'], sk.entities[e['a']]['y']), (sk.entities[e['b']]['x'], sk.entities[e['b']]['y'])
            pid = sk.point((ax + bx) / 2, (ay + by) / 2)
            sk.constrain('symmetric', e['a'], e['b'], pid)
        elif 'cross' in p:
            pid = sk.point(x, y)
            for l in p['cross']:
                sk.constrain('on_line', pid, l)
        elif 'on' in p:
            pid = sk.point(x, y)
            sk.constrain('on_line', pid, p['on'])          # su una linea, un cerchio o un arco
        elif 'quad' in p:
            # quadrante di un cerchio/arco (in cima, in fondo, a destra, a sinistra): resta lì anche se il
            # cerchio cambia diametro o si sposta
            e = sk.entities[p['quad']]
            c = sk.entities[e['center']]
            if e['kind'] == 'circle':
                r = e['r']
            else:
                s0 = sk.entities[e['start']]
                r = math.hypot(s0['x'] - c['x'], s0['y'] - c['y'])
            k = int(p.get('k', 0)) % 4
            pid = sk.point(c['x'] + r * math.cos(k * math.pi / 2), c['y'] + r * math.sin(k * math.pi / 2))
            sk.constrain('on_line', pid, p['quad'])
            sk.constrain('horizontal' if k % 2 == 0 else 'vertical', pid, e['center'])
        elif 'tan' in p:
            pid = sk.point(x, y)                # la tangenza la mette add_polyline, sul tratto che arriva qui
        elif 'perp' in p:
            pid = sk.point(x, y)
            sk.constrain('on_line', pid, p['perp'])         # + perpendicolare sul tratto (add_polyline)
        elif 'track' in p:
            # allineato a un altro punto: stessa X (in verticale) e/o stessa Y (in orizzontale)
            pid = sk.point(x, y)
            t = p['track']
            if t.get('x'):
                sk.constrain('vertical', pid, t['x'])
            if t.get('y'):
                sk.constrain('horizontal', pid, t['y'])
        else:
            raise SketchError('Aggancio sconosciuto.')
        e = sk.entities[pid]
        return pid, (e['x'], e['y']), True
    if isinstance(p, str):
        if sk.kind(p) != 'point':
            raise SketchError(f'{p} non è un punto.')
        e = sk.entities[p]
        return p, (e['x'], e['y']), False
    x, y = float(p[0]), float(p[1])
    return sk.point(x, y), (x, y), True


def add_polyline(doc, sid: str, pts: list, closed: bool, construction: bool = False, angles=None) -> list[str]:
    sk = doc.sketch(sid)
    if len(pts) < 2:
        raise SketchError('Servono almeno due punti.')
    refs = [_point_ref(sk, p) for p in pts]
    # due punti diversi già nello stesso posto (risolto: uno agganciato a una guida, uno dalle quote): il tratto
    # sarebbe lungo zero e bloccherebbe lo sketch. Sono già collegati: il tratto non si fa (21/10, il cassone)
    try:
        risolti = solve(sk, doc.resolved_parameters()).points
    except SketchError:
        risolti = {}
    dove = lambda r: risolti.get(r[0], r[1])  # noqa: E731
    tolti = [i for i in range(len(refs) - 1) if refs[i][0] != refs[i + 1][0] and not refs[i][2] and not refs[i + 1][2]
             and math.dist(dove(refs[i]), dove(refs[i + 1])) < 1e-4]
    for i in reversed(tolti):
        del refs[i + 1]
        if angles and i < len(angles):
            angles = list(angles[:i]) + list(angles[i + 1:])
    if len(refs) < 2:
        return []
    for i in range(len(refs) - 1):
        if math.dist(refs[i][1], refs[i + 1][1]) < 1e-6:
            raise SketchError('Due punti consecutivi coincidono: un tratto lungo zero non si può fare.')
    ids = [r[0] for r in refs]
    xy = [r[1] for r in refs]
    if closed:
        if len(ids) < 3:
            raise SketchError('Per chiudere un contorno servono almeno tre punti.')
        ids.append(ids[0])
        xy.append(xy[0])
    linee = [sk.line(ids[i], ids[i + 1]) for i in range(len(ids) - 1)]
    for lid in linee:
        sk.entities[lid]['label'] = f'lato {lid}'     # "il fianco sul lato L3", non "linea L3"
        sk.entities[lid]['construction'] = bool(construction)
    tipi = [_snap_hv(xy[i], xy[i + 1]) for i in range(len(linee))]
    for lid, t in zip(linee, tipi):
        if t:
            sk.constrain(t, lid, auto=True)
    salta = set()
    if closed:
        for t in ('horizontal', 'vertical'):
            ultimi = [i for i, x in enumerate(tipi) if x == t]
            if ultimi:
                salta.add(ultimi[-1])
        if tipi[-1] is None:
            salta.add(len(linee) - 1)
    for i, lid in enumerate(linee):
        if i not in salta:
            sk.dimension('length', lid, value=_r(math.dist(xy[i], xy[i + 1])))
    # angolo scritto ("100<30"): resta quello, misurato dall'asse X con una guida orizzontale corta
    for i, ang in enumerate(angles or []):
        if ang is None or i >= len(linee) or tipi[i]:
            continue
        x0, y0 = xy[i]
        q = sk.point(x0 + 20, y0, construction=True)
        g = sk.line(ids[i], q, construction=True)
        sk.constrain('horizontal', g)
        sk.dimension('length', g, value=20)
        sk.dimension('angle', g, linee[i], value=_r(ang))
    # tangente / perpendicolare: valgono per il tratto che arriva al punto agganciato (o parte, se è il primo)
    for i, p in enumerate(pts):
        if not isinstance(p, dict) or not linee:
            continue
        seg = linee[i - 1] if i > 0 else linee[0]
        if 'tan' in p:
            sk.constrain('tangent', seg, p['tan'])
        if 'perp' in p:
            sk.constrain('perpendicular', seg, p['perp'])
    if refs[0][2]:
        _position(sk, ids[0], xy[0])
    return linee


def add_rectangle(doc, sid: str, p0, p1, construction: bool = False) -> dict:
    sk = doc.sketch(sid)
    if isinstance(p0, dict):
        p0 = _point_ref(sk, p0)[0]
    a = (float(p0[0]), float(p0[1])) if not isinstance(p0, str) else (sk.entities[p0]['x'], sk.entities[p0]['y'])
    b = (float(p1[0]), float(p1[1]))
    if abs(b[0] - a[0]) < 1e-6 or abs(b[1] - a[1]) < 1e-6:
        raise SketchError('Il rettangolo ha bisogno di larghezza e altezza.')
    r = sk.rectangle(a[0], a[1], b[0], b[1])
    for lid in r['lines']:
        sk.entities[lid]['construction'] = bool(construction)
    sk.dimension('length', r['bottom'], value=_r(abs(b[0] - a[0])))
    sk.dimension('length', r['left'], value=_r(abs(b[1] - a[1])))
    if isinstance(p0, str):
        # agganciato a un punto che c'era (anche l'origine): l'angolo più vicino coincide con quello
        e = sk.entities[p0]
        dove = min(r['corners'], key=lambda k: math.dist((sk.entities[k]['x'], sk.entities[k]['y']), (e['x'], e['y'])))
        sk.constrain('coincident', dove, p0)
    else:
        _position(sk, r['corners'][0], (min(a[0], b[0]), min(a[1], b[1])))
    return r


def add_circle(doc, sid: str, center, r: float, construction: bool = False) -> str:
    sk = doc.sketch(sid)
    r = float(r)
    if r <= 0:
        raise SketchError('Il cerchio ha bisogno di un raggio.')
    pid, xy, nuovo = _point_ref(sk, center)
    cid = sk.circle(pid, r, construction=bool(construction))
    sk.dimension('diameter', cid, value=_r(2 * r))
    if nuovo:
        _position(sk, pid, xy)
    return cid


def add_text(doc, sid: str, pos, testo: str, h: float, angolo: float = 0.0, stencil: str | None = None) -> str:
    """Un testo col punto in basso a sinistra in pos: da marcare col laser, o da tagliare (stencil = 'saira'/'allerta')."""
    sk = doc.sketch(sid)
    pid, xy, nuovo = _point_ref(sk, pos)
    tid = sk.text(pid, testo, float(h), float(angolo or 0), stencil or None)
    if nuovo:
        _position(sk, pid, xy)
    return tid


def add_slot(doc, sid: str, c1, c2, r: float, construction: bool = False) -> dict:
    """Asola: due centri e la larghezza (2 × r). Quote: larghezza, interasse, posizione del primo centro."""
    sk = doc.sketch(sid)
    r = float(r)
    if r <= 0:
        raise SketchError('L’asola ha bisogno di una larghezza maggiore di zero.')
    p1, xy1, nuovo1 = _point_ref(sk, c1)
    p2, xy2, _ = _point_ref(sk, c2)
    if math.dist(xy1, xy2) < 1e-6:
        raise SketchError('I due centri dell’asola coincidono: serve un interasse.')
    out = sk.slot(xy1, xy2, r)
    k1, k2 = out['centers']
    for k in (k1, k2):
        sk.entities[k]['construction'] = False      # i centri si vedono: ci si aggancia
    sk.constrain('coincident', k1, p1)
    sk.constrain('coincident', k2, p2)
    for eid in out['arcs'] + out['lines']:
        sk.entities[eid]['construction'] = bool(construction)
    hv = _snap_hv(xy1, xy2)
    if hv:
        sk.constrain(hv, k1, k2)
    sk.dimension('distance', k1, k2, value=_r(math.dist(xy1, xy2)))
    sk.dimension('radius', out['arcs'][0], value=_r(r))
    if nuovo1:
        _position(sk, p1, xy1)
    return out


def delete(doc, sid: str, eids: list[str]) -> None:
    """Toglie linee/cerchi, i vincoli che li usano e i punti rimasti soli (mai l'origine)."""
    sk = doc.sketch(sid)
    for e in eids:
        if e not in sk.entities or e == ORIGIN:
            raise SketchError(f'Nello sketch non c’è {e}.')
    eids = [e for e in eids if not sk.entities[e].get('ref')]     # i bordi del pezzo restano
    if not eids:
        raise SketchError('I bordi arancio sono il pezzo vero: non si cancellano né si modificano (servono per agganciarsi e per chiudere i contorni).')
    via = set(eids)
    for k in list(sk.entities):
        if k in via:
            del sk.entities[k]
    while True:
        usati = {ORIGIN}
        for e in sk.entities.values():
            for key in ('a', 'b', 'center', 'start', 'end'):
                if key in e:
                    usati.add(e[key])
        soli = [k for k, e in sk.entities.items() if e['kind'] == 'point' and k not in usati]
        via |= set(soli)
        for k in soli:
            del sk.entities[k]
        for cid, c in list(sk.constraints.items()):
            if any(r in via or r not in sk.entities for r in c['refs']):
                del sk.constraints[cid]
        if not soli:
            break


def _num(k: str) -> int:
    return int(''.join(ch for ch in k if ch.isdigit()) or 0)


def _prune(doc, sid: str, before: set, era_pulito: bool = True) -> list[str]:
    """Toglie le quote/vincoli appena aggiunti che rendono lo sketch doppio o in conflitto.
    Se il risolutore dà la colpa a una quota vecchia ma prima lo sketch era pulito, la colpa è comunque
    di quelle nuove: si tolgono dalla più recente (le posizioni dall'origine sono le ultime aggiunte)."""
    sk = doc.sketch(sid)
    tolti = []
    for _ in range(16):
        try:
            st = solve(sk, doc.resolved_parameters()).status
        except SteelCADError:
            break
        guai = [c for c in list(st.redundant) + list(st.conflicting) if c in sk.constraints]
        if not guai:
            break
        nuovi = [c for c in guai if c not in before]
        if not nuovi and era_pulito:
            nuovi = [c for c in sk.constraints if c not in before]
        if not nuovi:
            break
        c = max(nuovi, key=_num)
        del sk.constraints[c]
        tolti.append(c)
    return tolti


def guarded(fn):
    def run(doc, sid, *a, **kw):
        sk = doc.sketch(sid)
        before = set(sk.constraints)
        try:
            st = solve(sk, doc.resolved_parameters()).status
            pulito = not st.redundant and not st.conflicting
        except SteelCADError:
            pulito = False
        out = fn(doc, sid, *a, **kw)
        _prune(doc, sid, before, pulito)
        return out
    return run


add_polyline = guarded(add_polyline)
add_rectangle = guarded(add_rectangle)
add_circle = guarded(add_circle)
add_slot = guarded(add_slot)
