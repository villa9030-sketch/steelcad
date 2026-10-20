"""Disegnando su una faccia: le sagome vicine come riferimento e la chiusura lungo il bordo del pezzo.

- ``add_nearby_edges``: i bordi delle facce parallele poco davanti alla faccia (es. la testata di un profilo che
  arriva a 1 mm dalla parete) diventano linee arancio tratteggiate: ci si aggancia per rifilare la parete
  sulla sagoma del profilo.
- ``border_closure``: una spezzata aperta che parte e finisce sul bordo della faccia si chiude lungo il bordo,
  dalla parte che fa il pezzo più piccolo (quello che si vuole togliere).
"""
from __future__ import annotations

import math

import build123d as bd
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane

from cad_engine.errors import SketchError
from cad_engine.topology.naming import _faces_of

TOL = 1e-4


def add_nearby_edges(sk, body, face, plane, fino_a: float) -> int:
    """Proietta sul piano dello sketch i bordi delle facce parallele che stanno davanti alla faccia (dalla
    parte della sua normale) entro ``fino_a`` mm e che le si sovrappongono. Ritorna quante linee ha messo."""
    return project_edges(sk, body, face, plane, fino_a=fino_a)


def project_edges(sk, body, face, plane, fino_a: float | None = None, xray: bool = False, salta: str | None = None,
                  spessore: float = 0.0) -> int:
    """Proietta sul piano dello sketch i bordi (linee, archi, cerchi) delle facce parallele.
    Normale: solo davanti alla faccia, entro ``fino_a``. ``xray`` ("vedi attraverso"): davanti e dietro a qualsiasi
    distanza, segnati ``xray`` per poterli togliere; si salta l'altra faccia della stessa parete (``salta`` = nome
    della parete, entro lo ``spessore``), che ripeterebbe il bordo."""
    n = plane.z_dir
    io = face.wrapped
    bb = face.bounding_box()
    punti: dict = {}

    def pt(v):
        q = plane.to_local_coords(v)
        k = (round(q.X, 4), round(q.Y, 4))
        if k not in punti:
            esistente = next((pid for pid, e in sk.entities.items() if e['kind'] == 'point' and e.get('ref')
                              and abs(e['x'] - k[0]) < TOL and abs(e['y'] - k[1]) < TOL), None)
            if esistente:
                punti[k] = (esistente, False)
            else:
                pid = sk.point(q.X, q.Y, construction=True)
                sk.entities[pid]['ref'] = True
                punti[k] = (pid, True)
        return punti[k][0]

    gia = {frozenset((e['a'], e['b'])) for e in sk.entities.values() if e['kind'] == 'line' and e.get('ref')}
    fatte = 0
    for f in _faces_of(body.shape):
        if f.IsSame(io) or BRepAdaptor_Surface(f).GetType() != GeomAbs_Plane:
            continue
        bf = bd.Face(f)
        if abs(abs(bf.normal_at().dot(n)) - 1) > 1e-6:
            continue
        d = (bf.center() - plane.origin).dot(n)
        if xray:
            if salta and abs(d) <= spessore + TOL and any(x.startswith(salta + '/') for x in body.names_of(f)):
                continue
        else:
            if not (TOL < d <= fino_a + TOL):
                continue
            fb = bf.bounding_box()
            lo, hi, LO, HI = tuple(fb.min), tuple(fb.max), tuple(bb.min), tuple(bb.max)
            if any(lo[i] > HI[i] + fino_a or hi[i] < LO[i] - fino_a for i in range(3)):
                continue
        segna = {'ref': True, 'proj': True, **({'xray': True} if xray else {})}
        for e in bf.edges():
            if e.geom_type == bd.GeomType.LINE:
                a, b = pt(e.start_point()), pt(e.end_point())
                if a == b or frozenset((a, b)) in gia:
                    continue
                lid = sk.line(a, b, construction=True, label='vista attraverso' if xray else 'sagoma vicina')
                sk.entities[lid].update(segna)
                gia.add(frozenset((a, b)))
                fatte += 1
            elif e.geom_type == bd.GeomType.CIRCLE and e.length < 2 * math.pi * e.radius - 1e-6:
                a, b = pt(e.start_point()), pt(e.end_point())
                qc = plane.to_local_coords(e.arc_center)
                qm = plane.to_local_coords(e.position_at(0.5))
                qa = (sk.entities[a]['x'], sk.entities[a]['y'])
                ang = lambda q: math.atan2(q[1] - qc.Y, q[0] - qc.X)  # noqa: E731
                a0, am, a1 = ang(qa), ang((qm.X, qm.Y)), ang((sk.entities[b]['x'], sk.entities[b]['y']))
                giro = lambda x: (x - a0) % (2 * math.pi)  # noqa: E731
                antiorario = giro(am) < giro(a1)
                c = sk.point(qc.X, qc.Y, construction=True)
                sk.entities[c]['ref'] = True
                arco = sk.arc(c, a, b, construction=True) if antiorario else sk.arc(c, b, a, construction=True)
                sk.entities[arco].update(segna)
                sk.dimension('radius', arco, value=round(e.radius, 6))
                fatte += 1
            elif e.geom_type == bd.GeomType.CIRCLE:
                # un foro: cerchio intero, centro fisso e diametro (per riprenderlo dall'altra parte)
                qc = plane.to_local_coords(e.arc_center)
                if any(x['kind'] == 'circle' and x.get('ref') and abs(x['r'] - e.radius) < TOL
                       and abs(sk.entities[x['center']]['x'] - qc.X) < TOL and abs(sk.entities[x['center']]['y'] - qc.Y) < TOL
                       for x in sk.entities.values()):
                    continue
                c = pt(e.arc_center)
                cid = sk.circle(c, e.radius, construction=True)
                sk.entities[cid].update(segna)
                sk.dimension('diameter', cid, value=round(2 * e.radius, 6))
                fatte += 1
    for pid, nuovo in punti.values():
        if nuovo:
            sk.constrain('fix', pid)
            if xray:
                sk.entities[pid]['xray'] = True
    return fatte


def remove_xray(sk) -> None:
    """Toglie la vista attraverso: le sue linee/archi/cerchi; i suoi punti solo se il disegno non ci è attaccato."""
    via = {k for k, e in sk.entities.items() if e.get('xray') and e['kind'] in ('line', 'arc', 'circle')}
    for k in via:
        del sk.entities[k]
    usati = set()
    for e in sk.entities.values():
        usati |= {e.get(x) for x in ('a', 'b', 'center', 'start', 'end')}
    for k, c in sk.constraints.items():
        if c['type'] not in ('fix',):
            usati |= set(c['refs'])
    for k in [k for k, e in sk.entities.items() if e['kind'] == 'point' and e.get('xray') and k not in usati]:
        del sk.entities[k]
    for e in sk.entities.values():
        e.pop('xray', None)                       # i punti a cui è attaccato il disegno restano, come punti fissi
    for k, c in list(sk.constraints.items()):
        if any(r not in sk.entities for r in c['refs']):
            del sk.constraints[k]


def _on_segment(P, A, B) -> float | None:
    """Parametro (0..1) di P sul segmento AB, se ci sta sopra."""
    dx, dy = B[0] - A[0], B[1] - A[1]
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return None
    t = ((P[0] - A[0]) * dx + (P[1] - A[1]) * dy) / L2
    dist = abs(dx * (P[1] - A[1]) - dy * (P[0] - A[0])) / math.sqrt(L2)
    return t if dist < TOL and -1e-6 <= t <= 1 + 1e-6 else None


def _area(pts) -> float:
    return abs(sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1] for i in range(len(pts)))) / 2


class _Vista:
    """Lo sketch con una sola spezzata disegnata (le altre linee non ci sono): per chiuderle una alla volta."""
    def __init__(self, sk, tieni):
        self.entities = {k: e for k, e in sk.entities.items()
                         if not (e['kind'] == 'line' and not e.get('construction')) or k in tieni}


def _gruppi(sk, linee) -> list:
    """Le linee disegnate divise in spezzate collegate (punti in comune)."""
    padre = {l: l for l in linee}

    def radice(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x
    per_punto: dict = {}
    for l in linee:
        e = sk.entities[l]
        for p in (e['a'], e['b']):
            if p in per_punto:
                padre[radice(l)] = radice(per_punto[p])
            else:
                per_punto[p] = l
    out: dict = {}
    for l in linee:
        out.setdefault(radice(l), []).append(l)
    return list(out.values())


def border_closure(sk, points, oltre: float | None = None) -> list | None:
    """Se le linee disegnate sono spezzate aperte con le estremità sul bordo della faccia (linee arancio del
    contorno), i tratti per chiuderle lungo il bordo, ognuna dalla parte del pezzo più piccolo: [(da, a, arco del
    bordo o None)]. None se non c'è niente da chiudere. Più spezzate (19/10: due linee in offset a 190 mm dalle
    due testate per accorciare una flangia) si chiudono una per una; i cerchi disegnati restano fori a parte."""
    linee = [k for k, e in sk.entities.items() if e['kind'] == 'line' and not e.get('construction')]
    if not linee or any(e['kind'] == 'arc' and not e.get('construction') for e in sk.entities.values()):
        return None
    gruppi = _gruppi(sk, linee)
    if len(gruppi) == 1:
        return _una(sk, points, oltre, linee)
    out, errore, chiusi = [], None, any(e['kind'] == 'circle' and not e.get('construction') for e in sk.entities.values())
    for g in gruppi:
        try:
            c = _una(_Vista(sk, set(g)), points, oltre, g)
        except SketchError as ex:                   # una linea sciolta: la lascia perdere il profilo (in rosso)
            errore = errore or ex
            continue
        if c is None:
            chiusi = True                           # un contorno già chiuso (o che si chiude da solo)
        out += c or []
    if not out and errore and not chiusi:
        raise errore
    return out or None


def _una(sk, points, oltre, linee) -> list | None:
    from app.sketch_edit import _chain
    try:
        ordine, _, chiusa = _chain(sk, linee)
    except SketchError:
        return None
    if chiusa:
        return None
    # il contorno della faccia: le linee arancio "bordo del pezzo", in giri chiusi
    bordi = [(e['a'], e['b']) for e in sk.entities.values() if e['kind'] == 'line' and e.get('ref') and not e.get('proj')]
    archi = {frozenset((e['start'], e['end'])): k for k, e in sk.entities.items()
             if e['kind'] == 'arc' and e.get('ref') and not e.get('proj')}
    vicini: dict = {}
    for a, b in bordi + [tuple(x) for x in archi]:
        vicini.setdefault(a, []).append(b)
        vicini.setdefault(b, []).append(a)
    xy = lambda p: points[p]  # noqa: E731
    pa, pb = ordine[0], ordine[-1]

    def segmento(p):
        for a, b in bordi:
            t = _on_segment(xy(p), xy(a), xy(b))
            if t is not None:
                return a, b
        for ab in archi:                                          # sull'estremo di un arco del bordo
            a, b = tuple(ab)
            if math.dist(xy(p), xy(a)) < TOL or math.dist(xy(p), xy(b)) < TOL:
                return a, b
        return None

    sa, sb = segmento(pa), segmento(pb)
    if sa is None or sb is None:
        raise SketchError('La spezzata è aperta: chiudila, oppure falla partire e finire sul bordo della faccia (le linee '
                          'arancio), e la chiudo io lungo il bordo.')
    if any(len(v) != 2 for v in vicini.values()):
        raise SketchError('Il bordo arancio della faccia è interrotto (manca un pezzo): non riesco a chiudere la spezzata '
                          'lungo il bordo. Chiudi tu il contorno, oppure rifai lo sketch sulla faccia.')

    def giro(da, verso, fine):
        """Dal vertice ``verso`` (lasciando ``da``) lungo il contorno, fino a un estremo del segmento ``fine``."""
        out, prima, cur = [], da, verso
        for _ in range(len(vicini) + 1):
            out.append(cur)
            if cur in fine:
                return out
            nxt = [x for x in vicini.get(cur, []) if x != prima]
            if not nxt:
                return None
            prima, cur = cur, nxt[0]
        return None

    # sullo stesso bordo dove comincia una piega: lo scasso è aperto, si chiude oltre il bordo (attraverso la piega
    # e le flange che seguono; quello che esce dal pezzo non conta)
    linea = next((e for e in sk.entities.values() if e['kind'] == 'line' and e.get('ref') and {e['a'], e['b']} == set(sa)), None)
    if oltre and set(sa) == set(sb) and linea is not None and linea.get('piega'):
        A, B = xy(sa[0]), xy(sa[1])
        L = math.dist(A, B)
        nx, ny = -(B[1] - A[1]) / L, (B[0] - A[0]) / L
        cx = sum(xy(p)[0] for p in ordine) / len(ordine) - A[0]
        cy = sum(xy(p)[1] for p in ordine) / len(ordine) - A[1]
        if nx * cx + ny * cy > 0:                                 # la spezzata sta da quella parte: si va dall'altra
            nx, ny = -nx, -ny
        qb = ('nuovo', xy(pb)[0] + nx * oltre, xy(pb)[1] + ny * oltre)
        qa = ('nuovo', xy(pa)[0] + nx * oltre, xy(pa)[1] + ny * oltre)
        return [(pb, qb, None), (qb, qa, None), (qa, pa, None)]
    candidati = []
    if set(sa) == set(sb):
        candidati.append([])                                      # stesso lato: si chiude dritto
        a, b = sa
        # l'altro giro: tutto il resto del contorno
        ta = _on_segment(xy(pa), xy(a), xy(b))
        tb = _on_segment(xy(pb), xy(a), xy(b))
        vicino, lontano = (a, b) if tb < ta else (b, a)        # da pb, il vertice dalla sua parte
        g = giro(lontano, vicino, {lontano})
        if g:
            candidati.append(g)
    else:
        for primo in sb:                                          # da pb verso uno dei due estremi del suo lato
            altro = sb[1] if primo == sb[0] else sb[0]
            g = giro(altro, primo, set(sa))
            if g:
                candidati.append(g)
    if not candidati:
        raise SketchError('Non riesco a chiudere la spezzata lungo il bordo: le estremità stanno su contorni diversi.')
    tratto = [xy(p) for p in ordine]
    migliore = min(candidati, key=lambda g: _area(tratto + [xy(p) for p in g]))
    giro_pt = [pb] + migliore + [pa]
    # i tratti da aggiungere: linee, oppure archi dove il bordo è un arco (stesso centro, stesso verso)
    out = []
    for u, v in zip(giro_pt, giro_pt[1:]):
        if u == v or math.dist(xy(u), xy(v)) < TOL:
            continue
        out.append((u, v, archi.get(frozenset((u, v)))))
    return out
