"""Lamiera piegata: piano di base da uno sketch, flange sui lati, sviluppo esatto.

Definizione (feature "sheet"):

    {"id": "SM1", "type": "sheet", "name": "Staffa", "sketch": "S1",
     "thickness": "sp", "radius": 2, "method": "k", "k": 0.4,          # oppure "din6935", "bd90"
     "flanges": [
        {"id": "FL1", "edge": "L1", "length": 30, "angle": 90, "direction": "up",
         "position": "inside", "gap": 0,
         "holes": [{"u": 50, "v": 20, "d": 8}]}
     ]}

Convenzioni (le stesse di un disegno d'officina, documentate in docs/SHEETMETAL.md):
- il contorno dello sketch è la quota ESTERNA del pezzo finito ("inside": il
  materiale sta dentro il contorno); con "outside" la piega parte dal bordo e la
  flangia si aggiunge fuori;
- la lunghezza della flangia è misurata dallo spigolo vivo esterno (outer virtual
  sharp) fino alla punta: per una piega a 90° è l'altezza esterna;
- i fori sulla flangia: u lungo il lato (dal primo punto della linea dello
  sketch), v dallo spigolo vivo esterno lungo la flangia.

Tecnologia: spessore, raggio interno e metodo di calcolo della piega non hanno
valori di default. Se mancano, la lamiera non si costruisce e il messaggio dice
quale dato manca (non si inventano numeri).

    BA (bend allowance)  = θ · (r + K · t)
    setback esterno       = (r + t) · tan(θ/2)
    BD (bend deduction)   = 2 · setback − BA
    sviluppo di un lato   = L − BD     (dallo spigolo vivo esterno)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import build123d as bd
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane

from ..errors import FeatureError
from ..expressions import evaluate
from ..topology import NamedShape
from ..topology.naming import _faces_of
from ..units import TOL, cap, fmt_mm

METODI = {'k': 'K-factor', 'din6935': 'DIN 6935', 'bd90': 'deduzione di piega a 90°'}
VERSI = {'up': 'su', 'down': 'giù'}
POSIZIONI = {'inside': 'quota esterna sul contorno', 'outside': 'piega dal bordo, flangia fuori'}
TECNO = ('thickness', 'radius', 'method', 'k', 'bd90')


@dataclass
class Bend:
    angle: float          # gradi
    r: float              # raggio interno
    t: float
    k: float              # K-factor usato (anche quando viene da DIN 6935 o dalla deduzione)
    ba: float
    ossb: float           # setback esterno
    bd: float
    method: str

    def as_dict(self) -> dict:
        return {'angle': self.angle, 'r': self.r, 't': self.t, 'k': self.k, 'ba': self.ba,
                'ossb': self.ossb, 'bd': self.bd, 'method': self.method}


def bend_values(angle: float, r: float, t: float, method: str, k: float | None = None,
                bd90: float | None = None, fid: str | None = None) -> Bend:
    """I numeri di una piega. Ogni dato mancante è un errore che dice cosa manca."""
    if not 0 < angle < 180:
        raise FeatureError(f'L’angolo di piega deve stare tra 0° e 180° (escluso): {fmt_mm(angle)}° non va.',
                           feature=fid)
    if angle > 170:
        raise FeatureError('Pieghe oltre 170° (risvolti schiacciati) non sono ancora gestite.', feature=fid)
    th = math.radians(angle)
    ossb = (r + t) * math.tan(th / 2)
    if method == 'k':
        if k is None:
            raise FeatureError(_manca('il K-factor'), feature=fid, code='manca_tecnologia')
        if not 0 <= k <= 1:
            raise FeatureError(f'Il K-factor deve stare tra 0 e 1 (di solito 0,3–0,5): {k} non va.', feature=fid)
        kk = k
    elif method == 'din6935':
        if r <= 0:
            raise FeatureError('La DIN 6935 vale per raggi interni maggiori di zero.', feature=fid)
        kd = 1.0 if r / t >= 5 else 0.65 + 0.5 * math.log10(r / t)
        kk = kd / 2                       # nella norma k è riferito a s/2
    elif method == 'bd90':
        if bd90 is None:
            raise FeatureError(_manca('la deduzione di piega a 90°'), feature=fid, code='manca_tecnologia')
        if abs(angle - 90) > 1e-9:
            raise FeatureError(f'La deduzione a 90° vale solo per pieghe a 90°; questa è a {fmt_mm(angle)}°. '
                               'Per altri angoli scegli K-factor o DIN 6935.', feature=fid)
        ba = 2 * ossb - bd90
        kk = (ba / th - r) / t
        if not 0 <= kk <= 1:
            raise FeatureError(f'Con la deduzione {fmt_mm(bd90)} mm il K-factor verrebbe {kk:.2f}, fuori da 0–1: '
                               'controlla il valore della tabella.', feature=fid)
    elif not method:
        raise FeatureError(_manca('il metodo di calcolo della piega (K-factor, DIN 6935 o deduzione a 90°)'),
                           feature=fid, code='manca_tecnologia')
    else:
        raise FeatureError(f'Metodo di piega "{method}" sconosciuto: usa K-factor, DIN 6935 o deduzione a 90°.',
                           feature=fid)
    ba = th * (r + kk * t)
    return Bend(angle, r, t, kk, ba, ossb, 2 * ossb - ba, method)


def _manca(cosa: str) -> str:
    return (f'Manca {cosa}: è un dato della tua piegatrice (punzone, matrice, materiale) e non lo invento. '
            'Inseriscilo nella scheda Lamiera.')


# =============================================================================== geometria
@dataclass
class FlangeGeo:
    fid: str
    edge: str
    bend: Bend
    length: float
    direction: str
    position: str
    origin: bd.Vector       # inizio del lato nel sistema della flangia (sul piano dello sketch)
    xf: bd.Vector           # lungo il lato
    n: bd.Vector            # verso l'esterno, nel piano
    zf: bd.Vector           # verso cui si piega
    length_edge: float
    reversed: bool
    off: float              # dove finisce il piano di base (coordinata s; 0 = contorno)
    u0: float = 0.0
    u1: float = 0.0
    holes: list = field(default_factory=list)   # (u_f, v, d)

    @property
    def lf(self) -> float:            # tratto dritto
        return self.length - self.bend.ossb

    def p(self, u: float, s: float, z: float = 0.0, lift: float = 0.0) -> bd.Vector:
        return self.origin + self.xf * u + self.n * s + self.zf * z + self.zf * lift


@dataclass
class SheetData:
    feature: str
    thickness: float
    tech: dict
    flanges: list                      # FlangeGeo
    flat: bd.Face | None
    plane: bd.Plane
    bend_lines: list                   # [(a2, b2, testo)]
    flat_size: tuple
    flat_area: float
    warnings: list

    def summary(self) -> dict:
        return {'feature': self.feature, 'thickness': self.thickness, 'tech': self.tech,
                'bends': [{'flange': g.fid, 'edge': g.edge, 'length': g.length, 'direction': g.direction,
                           'position': g.position, 'width': g.u1 - g.u0, **g.bend.as_dict()} for g in self.flanges],
                'flat_size': list(self.flat_size), 'flat_area': self.flat_area, 'warnings': self.warnings,
                'outline': self.outline(), 'bend_lines': [[list(a), list(b), t] for a, b, t in self.bend_lines]}

    def outline(self) -> list:
        """Lo sviluppo come polilinee 2D (per l'anteprima): [[x, y, ...], ...]."""
        if self.flat is None:
            return []
        out = []
        for w in self.flat.wires():
            pts = []
            for e in w.edges():
                n = 2 if e.geom_type == bd.GeomType.LINE else 24
                for p in e.positions([i / (n - 1) for i in range(n)]):
                    q = self.plane.to_local_coords(p)
                    pts += [round(q.X, 3), round(q.Y, 3)]
            out.append(pts)
        return out


def build(fdef: dict, ctx) -> NamedShape:
    fid = fdef['id']
    nome = f'"{fdef["name"]}"' if fdef.get('name') else fid
    ss, prof = ctx.sketch(fdef)
    if len(prof.faces) != 1:
        raise FeatureError(f'Lo sketch della lamiera {nome} deve avere un solo contorno chiuso '
                           f'(ne ha {len(prof.faces)}).', feature=fid)
    face, pl = prof.faces[0], prof.plane
    t = _val(fdef, 'thickness', ctx, 'lo spessore della lamiera', fid)
    if t is None:
        raise FeatureError(_manca('lo spessore'), feature=fid, code='manca_tecnologia')
    if t <= 0:
        raise FeatureError('Lo spessore della lamiera deve essere maggiore di zero.', feature=fid)
    flange_defs = fdef.get('flanges') or []
    tech = {'thickness': t, 'radius': _val(fdef, 'radius', ctx, 'il raggio interno', fid),
            'method': fdef.get('method'), 'k': _val(fdef, 'k', ctx, 'il K-factor', fid),
            'bd90': _val(fdef, 'bd90', ctx, 'la deduzione a 90°', fid)}
    tech['missing'] = _missing(tech)

    N = pl.z_dir
    lati = _outer_lines(face, prof, ss, pl, fid)
    geos = []
    for fl in flange_defs:
        flid = fl.get('id', '?')
        if tech['radius'] is None:
            raise FeatureError(_manca('il raggio interno di piega'), feature=fid, code='manca_tecnologia')
        if tech['radius'] < 0:
            raise FeatureError('Il raggio interno di piega non può essere negativo.', feature=fid)
        lid = fl.get('edge')
        if lid not in lati:
            raise FeatureError(f'La flangia {flid} è sul lato {lid}, che non è un lato dritto del contorno '
                               'esterno della lamiera.', feature=fid)
        if any(g.edge == lid for g in geos):
            raise FeatureError(f'Sul lato {lid} c’è già una flangia.', feature=fid)
        ang = evaluate(fl.get('angle', 90), ctx.params, what=f'l’angolo della flangia {flid}')
        L = evaluate(fl.get('length'), ctx.params, what=f'la lunghezza della flangia {flid}') \
            if fl.get('length') is not None else None
        if L is None:
            raise FeatureError(f'Manca la lunghezza della flangia {flid}.', feature=fid)
        b = bend_values(ang, tech['radius'], t, tech['method'], tech['k'], tech['bd90'], fid)
        if L - b.ossb <= TOL:
            raise FeatureError(f'La flangia {flid} è troppo corta: con raggio {fmt_mm(b.r)} e spessore {fmt_mm(t)} '
                               f'deve essere più lunga di {fmt_mm(round(b.ossb, 2))} mm (la piega da sola).',
                               feature=fid)
        dirz = fl.get('direction', 'up')
        if dirz not in VERSI:
            raise FeatureError(f'Verso della flangia {flid} sconosciuto: su o giù.', feature=fid)
        pos = fl.get('position', 'inside')
        if pos not in POSIZIONI:
            raise FeatureError(f'Posizione della flangia {flid} sconosciuta.', feature=fid)
        A3, B3, n3, a_id, b_id = lati[lid]
        zf = N if dirz == 'up' else -N
        a3 = (B3 - A3).normalized()
        xf = n3.cross(zf)
        rev = xf.dot(a3) < 0
        start = B3 if rev else A3
        origin = start + (N * t if dirz == 'down' else bd.Vector(0, 0, 0))
        sh = 0.0 if pos == 'inside' else b.ossb
        g = FlangeGeo(flid, lid, b, L, dirz, pos, origin, xf, n3, zf, (B3 - A3).length, rev, sh - b.ossb)
        g.ends = (b_id, a_id) if rev else (a_id, b_id)
        g.gap = evaluate(fl.get('gap', 0), ctx.params, what=f'la fessura d’angolo della flangia {flid}')
        g.hole_defs = fl.get('holes') or []
        geos.append(g)

    # dove finiscono le flange agli angoli: se anche il lato vicino ha una flangia, ci si ferma
    # all'incrocio delle due linee di fine piano (così pieghe e flange non si toccano)
    for g in geos:
        g.u0, g.u1 = 0.0, g.length_edge
        g.ext = [0.0, 0.0]
        for i, pid in enumerate(g.ends):
            altra = next((h for h in geos if h is not g and pid in h.ends), None)
            if altra is None:
                continue
            u = _corner_u(g, altra)
            if u is None:
                continue
            if i == 0:
                g.u0 = max(g.u0, u) + g.gap
            else:
                g.u1 = min(g.u1, u) - g.gap
            g.ext[i] = altra.bend.ossb + t + 1
        if g.u1 - g.u0 <= TOL:
            raise FeatureError(f'La flangia {g.fid} non ha più larghezza: le flange vicine se la mangiano tutta.',
                               feature=fid)
        for k, h in enumerate(g.hole_defs):
            u = evaluate(h.get('u'), ctx.params, what=f'la posizione u del foro {k + 1} della flangia {g.fid}')
            v = evaluate(h.get('v'), ctx.params, what=f'la posizione v del foro {k + 1} della flangia {g.fid}')
            d = evaluate(h.get('d'), ctx.params, what=f'il diametro del foro {k + 1} della flangia {g.fid}')
            uf = g.length_edge - u if g.reversed else u
            if d <= 0:
                raise FeatureError(f'Il foro {k + 1} della flangia {g.fid} deve avere diametro maggiore di zero.',
                                   feature=fid)
            if not (g.u0 + d / 2 <= uf + TOL and uf - d / 2 <= g.u1 + TOL):
                raise FeatureError(f'Il foro {k + 1} della flangia {g.fid} esce dalla flangia lungo il lato.',
                                   feature=fid)
            if v - d / 2 < g.bend.ossb - TOL:
                raise FeatureError(f'Il foro {k + 1} della flangia {g.fid} cade nella piega: il bordo del foro deve '
                                   f'stare ad almeno {fmt_mm(round(g.bend.ossb, 2))} mm dallo spigolo esterno '
                                   f'(ora è a {fmt_mm(round(v - d / 2, 2))}).', feature=fid)
            if v + d / 2 > g.length + TOL:
                raise FeatureError(f'Il foro {k + 1} della flangia {g.fid} esce dalla punta della flangia.',
                                   feature=fid)
            g.holes.append((uf, v, d))

    tabs = _closed_corners(fdef, geos, t, ctx, fid)

    # ----------------------------------------------------------------- solido 3D
    base = bd.extrude(face, amount=t, dir=tuple(N))
    for g in geos:
        if g.off < -TOL:
            base = base - _box(g, g.u0 - g.ext[0] if g.ext[0] else g.u0 - 0.0,
                               g.u1 + g.ext[1] if g.ext[1] else g.u1, g.off, g.bend.ossb + t + 1, t)
    _check_base_holes(face, prof, geos, pl, fid)
    parti = [base]
    for g in geos:
        parti.append(_flange_solid(g, t))
    for g, ua, ub in tabs:
        parti.append(_tab_solid(g, ua, ub, t))
    vol_attesa = sum(p.volume for p in parti)
    solido = parti[0]
    for p in parti[1:]:
        solido = solido + p
    solido = solido.clean()
    solidi = solido.solids()
    if len(solidi) != 1:
        raise FeatureError(f'La lamiera {nome} non è venuta un pezzo unico: controlla le flange.', feature=fid)
    if abs(solido.volume - vol_attesa) > 1e-6 * max(vol_attesa, 1) + 1e-3:
        raise FeatureError('Due flange si compenetrano in un angolo: aumenta la fessura d’angolo o accorciale.',
                           feature=fid)
    shape = solidi[0].wrapped

    # ----------------------------------------------------------------- sviluppo
    flat, linee = _flat(face, geos, pl, t, tabs)
    bb = [pl.to_local_coords(v) for v in flat.vertices()] if flat is not None else []
    size = ((max(p.X for p in bb) - min(p.X for p in bb)), (max(p.Y for p in bb) - min(p.Y for p in bb))) \
        if bb else (0.0, 0.0)
    if flat is not None:
        for e in flat.edges():
            if e.geom_type == bd.GeomType.CIRCLE:
                for p in (e.arc_center - e.radius * pl.x_dir, e.arc_center + e.radius * pl.x_dir,
                          e.arc_center - e.radius * pl.y_dir, e.arc_center + e.radius * pl.y_dir):
                    bb.append(pl.to_local_coords(p))
        size = ((max(p.X for p in bb) - min(p.X for p in bb)), (max(p.Y for p in bb) - min(p.Y for p in bb)))
    data = SheetData(fid, t, tech, geos, flat, pl, linee, size, flat.area if flat is not None else 0.0, [])
    ns = NamedShape(shape, _names(shape, fid, geos, lati, prof, pl, t))
    ns.sheet = data
    return ns


def _val(fdef, key, ctx, what, fid):
    v = fdef.get(key)
    if v is None or v == '':
        return None
    return evaluate(v, ctx.params, what=f'{what} della lamiera {fid}')


def _missing(tech) -> list[str]:
    out = []
    if tech['radius'] is None:
        out.append('raggio interno')
    m = tech['method']
    if not m:
        out.append('metodo di calcolo della piega')
    elif m == 'k' and tech['k'] is None:
        out.append('K-factor')
    elif m == 'bd90' and tech['bd90'] is None:
        out.append('deduzione a 90°')
    return out


def _outer_lines(face, prof, ss, pl, fid) -> dict:
    """I lati dritti del contorno esterno: id linea -> (A, B, normale verso fuori, id punto A, id punto B)."""
    out = {}
    for e in face.outer_wire().edges():
        lid = prof.entity_of(e)
        if lid is None or lid not in ss.lines or e.geom_type != bd.GeomType.LINE:
            continue
        a_id, b_id = ss.lines[lid]
        A3 = pl.from_local_coords(ss.points[a_id])
        B3 = pl.from_local_coords(ss.points[b_id])
        a3 = (B3 - A3).normalized()
        n3 = a3.cross(pl.z_dir)
        mid = (A3 + B3) * 0.5
        eps = max(0.01, min(1.0, (B3 - A3).length * 0.01))
        if face.is_inside(mid + n3 * eps):
            n3 = -n3
        out[lid] = (A3, B3, n3, a_id, b_id)
    return out


def _corner_u(g: FlangeGeo, h: FlangeGeo) -> float | None:
    """Dove la linea di fine piano di g incontra quella di h, misurato lungo g (dal suo inizio)."""
    nz = g.zf
    pg = g.origin + g.n * g.off
    ph = h.origin + h.n * h.off
    ph = ph - nz * nz.dot(ph - pg)            # stesso piano (le flange "giù" partono dalla faccia di sopra)
    d1, d2 = g.xf, h.xf
    cr = d1.cross(d2)
    if cr.length < 1e-9:
        return None                           # lati allineati: niente incrocio
    return (ph - pg).cross(d2).dot(cr) / cr.length ** 2


def _box(g: FlangeGeo, u_lo, u_hi, s_lo, s_len, t):
    pts = [g.p(u_lo, s_lo, -1), g.p(u_hi, s_lo, -1), g.p(u_hi, s_lo + s_len, -1), g.p(u_lo, s_lo + s_len, -1)]
    f = bd.Face(bd.Wire.make_polygon(pts, close=True))
    return bd.extrude(f, amount=t + 2, dir=tuple(g.zf))


def _section_points(g: FlangeGeo, t: float):
    b = g.bend
    r, R, th = b.r, b.r + t, math.radians(b.angle)
    cs, cz = g.off, R
    oe = (cs + R * math.sin(th), cz - R * math.cos(th))
    ie = (cs + r * math.sin(th), cz - r * math.cos(th))
    d = (math.cos(th), math.sin(th))
    om = (cs + R * math.sin(th / 2), cz - R * math.cos(th / 2))
    im = (cs + r * math.sin(th / 2), cz - r * math.cos(th / 2))
    lf = g.lf
    return {'os': (cs, 0.0), 'oe': oe, 'om': om, 'ot': (oe[0] + lf * d[0], oe[1] + lf * d[1]),
            'is': (cs, t), 'ie': ie, 'im': im, 'it': (ie[0] + lf * d[0], ie[1] + lf * d[1]), 'c': (cs, cz),
            'd': d, 'nrm': (-math.sin(th), math.cos(th))}


def _flange_solid(g: FlangeGeo, t: float):
    q = _section_points(g, t)
    P = lambda st: g.p(g.u0, st[0], st[1])  # noqa: E731
    edges = [bd.Edge.make_three_point_arc(P(q['os']), P(q['om']), P(q['oe'])),
             bd.Edge.make_line(P(q['oe']), P(q['ot'])),
             bd.Edge.make_line(P(q['ot']), P(q['it'])),
             bd.Edge.make_line(P(q['it']), P(q['ie']))]
    if g.bend.r > TOL:
        edges.append(bd.Edge.make_three_point_arc(P(q['ie']), P(q['im']), P(q['is'])))
    edges.append(bd.Edge.make_line(P(q['is']), P(q['os'])))
    sezione = bd.Face(bd.Wire(edges))
    sol = bd.extrude(sezione, amount=g.u1 - g.u0, dir=tuple(g.xf))
    for uf, v, d in g.holes:
        ds, dz = q['d']
        ns, nz = q['nrm']
        sh = g.off + g.bend.ossb                         # spigolo vivo esterno
        c = g.p(uf, sh + v * ds - ns * 1, v * dz - nz * 1)
        asse = g.n * ns + g.zf * nz
        sol = sol - bd.Solid.make_cylinder(d / 2, t + 2, bd.Plane(origin=c, z_dir=asse))
    return sol


def _check_base_holes(face, prof, geos, pl, fid):
    for w in face.inner_wires():
        for e in w.edges():
            if e.geom_type != bd.GeomType.CIRCLE:
                continue
            c, r = e.arc_center, e.radius
            for g in geos:
                s = (c - g.origin + g.zf * g.zf.dot(g.origin - c)).dot(g.n)
                u = (c - g.origin).dot(g.xf)
                if s + r > g.off - TOL and g.u0 - r < u < g.u1 + r:
                    raise FeatureError(f'Il foro {prof.entity_of(e) or ""} è troppo vicino alla piega della flangia '
                                       f'{g.fid}: il suo bordo deve stare ad almeno {fmt_mm(round(-g.off, 2))} mm dal '
                                       'contorno (dove comincia la piega).', feature=fid)


def _flat(face, geos, pl, t, tabs=()):
    """Lo sviluppo sul piano dello sketch: base accorciata + strisce lunghe BA + tratto dritto."""
    def pf(g, u, s):            # punto sul piano dello sketch (z = 0), anche per le flange "giù"
        p = g.origin + g.xf * u + g.n * s
        return p - pl.z_dir * pl.z_dir.dot(p - pl.origin)

    def poly(pts):              # stessa faccia rivolta come lo sketch, se no l'unione non si fonde
        f = bd.Face(bd.Wire.make_polygon(pts, close=True))
        return f if f.normal_at().dot(pl.z_dir) > 0 else bd.Face(bd.Wire.make_polygon(pts[::-1], close=True))

    flat = face
    for g in geos:
        if g.off < -TOL:
            lo = g.u0 - g.ext[0] if g.ext[0] else g.u0
            hi = g.u1 + g.ext[1] if g.ext[1] else g.u1
            rett = poly([pf(g, lo, g.off), pf(g, hi, g.off), pf(g, hi, g.off + g.bend.ossb + t + 1),
                         pf(g, lo, g.off + g.bend.ossb + t + 1)])
            flat = flat - rett
    linee = []
    for g in geos:
        lung = g.bend.ba + g.lf
        striscia = poly([pf(g, g.u0, g.off), pf(g, g.u1, g.off), pf(g, g.u1, g.off + lung), pf(g, g.u0, g.off + lung)])
        flat = flat + striscia
        for uf, v, d in g.holes:
            c = pf(g, uf, g.off + g.bend.ba + v - g.bend.ossb)
            flat = flat - bd.Face(bd.Wire.make_circle(d / 2, bd.Plane(origin=c, z_dir=pl.z_dir)))
        for h, ua, ub in tabs:
            if h is g:
                lo = g.off + g.bend.ba
                flat = flat + poly([pf(g, ua, lo), pf(g, ub, lo), pf(g, ub, lo + g.lf), pf(g, ua, lo + g.lf)])
        s_mid = g.off + g.bend.ba / 2
        a, b = pl.to_local_coords(pf(g, g.u0, s_mid)), pl.to_local_coords(pf(g, g.u1, s_mid))
        testo = f'{g.fid} {VERSI[g.direction].upper()} {fmt_mm(g.bend.angle)}° R{fmt_mm(g.bend.r)}'
        linee.append(((a.X, a.Y), (b.X, b.Y), testo))
    if isinstance(flat, bd.Face):
        return flat, linee
    flat = flat.clean() if hasattr(flat, 'clean') else flat
    facce = flat.faces()
    if len(facce) != 1:
        raise FeatureError('Lo sviluppo non è venuto un pezzo unico: le flange si sovrappongono nel piano. '
                           'Aumenta la fessura d’angolo.', feature=geos[0].fid if geos else None)
    return facce[0], linee


# =============================================================================== angoli chiusi
def _closed_corners(fdef, geos, t, ctx, fid) -> list:
    """Angoli chiusi tra due flange a 90° nello stesso verso: quella "sopra" si allunga fino a coprire lo
    spessore dell'altra (a filo della sua faccia esterna); quella "sotto" si allunga fino alla faccia
    interna della prima, meno la fessura. Solo nel tratto dritto: in fondo all'angolo resta lo scarico
    della piega. Ritorna [(flangia, u_da, u_a)] cioè le alette da aggiungere."""
    out = []
    per_id = {g.fid: g for g in geos}
    for k, c in enumerate(fdef.get('corners') or []):
        a, b = per_id.get(c.get('over')), per_id.get(c.get('under'))
        if a is None or b is None:
            raise FeatureError(f'L’angolo chiuso {k + 1} usa una flangia che non c’è più.', feature=fid)
        comune = set(a.ends) & set(b.ends)
        if not comune:
            raise FeatureError(f'Le flange {a.fid} e {b.fid} non hanno un angolo in comune.', feature=fid)
        if abs(a.bend.angle - 90) > 1e-9 or abs(b.bend.angle - 90) > 1e-9 or a.direction != b.direction:
            raise FeatureError(f'L’angolo chiuso tra {a.fid} e {b.fid} per ora si fa solo con flange a 90° '
                               'piegate dallo stesso lato.', feature=fid)
        if a.position != 'inside' or b.position != 'inside':
            raise FeatureError('L’angolo chiuso per ora si fa con le flange "quota esterna sul contorno".', feature=fid)
        gap = evaluate(c.get('gap', 0), ctx.params, what=f'la fessura dell’angolo {a.fid}/{b.fid}')
        if gap < 0:
            raise FeatureError('La fessura dell’angolo non può essere negativa.', feature=fid)
        pid = comune.pop()
        sh_a, sh_b = a.off + a.bend.ossb, b.off + b.bend.ossb
        # a fino alla faccia esterna di b; b fino alla faccia interna di a, meno la fessura
        for g, altra, piano in ((a, b, sh_b), (b, a, sh_a - t - gap)):
            den = g.xf.dot(altra.n)
            if abs(den) < 1e-9:
                raise FeatureError(f'Le flange {a.fid} e {b.fid} sono parallele: niente angolo.', feature=fid)
            u = (piano - (g.origin - altra.origin).dot(altra.n)) / den
            if g.ends[0] == pid:
                ua, ub = u, g.u0
            else:
                ua, ub = g.u1, u
            if ub - ua <= TOL:
                continue                     # già lunga abbastanza
            out.append((g, ua, ub))
    return out


def _tab_solid(g: FlangeGeo, ua: float, ub: float, t: float):
    """L'aletta: il tratto dritto della flangia allungato lungo il lato da ua a ub."""
    q = _section_points(g, t)
    pts = [g.p(ua, *q['oe']), g.p(ua, *q['ot']), g.p(ua, *q['it']), g.p(ua, *q['ie'])]
    f = bd.Face(bd.Wire.make_polygon(pts, close=True))
    return bd.extrude(f, amount=ub - ua, dir=tuple(g.xf))


# =============================================================================== nomi
def _names(shape, fid, geos, lati, prof, pl, t) -> dict:
    nomi: dict = {}
    N, O = pl.z_dir, pl.origin
    for f in _faces_of(shape):
        bf = bd.Face(f)
        c = bf.center()
        ad = BRepAdaptor_Surface(f)
        tipo = ad.GetType()
        nome = None
        for g in geos:
            loc = c - g.origin
            u, s, z = loc.dot(g.xf), loc.dot(g.n), loc.dot(g.zf)
            if not (g.u0 - TOL <= u <= g.u1 + TOL and s >= g.off - TOL):
                continue
            if abs(s - g.off) < TOL and -TOL <= z <= t + TOL and tipo == GeomAbs_Plane \
                    and abs(abs(bf.normal_at().dot(g.n)) - 1) < 1e-6:
                continue                                   # la faccia di attacco (sparisce nella fusione)
            if tipo == GeomAbs_Cylinder:
                r = ad.Cylinder().Radius()
                if abs(r - (g.bend.r + t)) < 1e-6 and abs(abs(_axis(ad).dot(g.xf)) - 1) < 1e-6:
                    nome = f'{fid}/{g.fid}/piega_esterna'
                elif abs(r - g.bend.r) < 1e-6 and abs(abs(_axis(ad).dot(g.xf)) - 1) < 1e-6:
                    nome = f'{fid}/{g.fid}/piega_interna'
                else:
                    k = next((i for i, (_, _, d) in enumerate(g.holes) if abs(d / 2 - r) < 1e-6), 0)
                    nome = f'{fid}/{g.fid}/foro{k + 1}'
            elif tipo == GeomAbs_Plane:
                nv = bf.normal_at()
                th = math.radians(g.bend.angle)
                dvec = g.n * math.cos(th) + g.zf * math.sin(th)
                nrm = g.n * -math.sin(th) + g.zf * math.cos(th)
                if abs(abs(nv.dot(g.xf)) - 1) < 1e-6:
                    nome = f'{fid}/{g.fid}/fianco'
                elif abs(abs(nv.dot(dvec)) - 1) < 1e-6:
                    nome = f'{fid}/{g.fid}/punta'
                elif abs(abs(nv.dot(nrm)) - 1) < 1e-6:
                    # esterna: passa per lo spigolo vivo esterno
                    sh = g.off + g.bend.ossb
                    dist = abs((s - sh) * nrm.dot(g.n) + z * nrm.dot(g.zf))
                    nome = f'{fid}/{g.fid}/' + ('esterno' if dist < 1e-6 else 'interno')
            if nome:
                break
        if nome is None:
            h = (c - O).dot(N)
            if tipo == GeomAbs_Plane and abs(abs(bf.normal_at().dot(N)) - 1) < 1e-6:
                nome = f'{fid}/sotto' if abs(h) < 1e-6 else f'{fid}/sopra' if abs(h - t) < 1e-6 else None
            elif tipo == GeomAbs_Plane:
                for lid, (A3, B3, n3, _, _) in lati.items():
                    if abs((c - A3).dot(n3)) < 1e-6:
                        nome = f'{fid}/lato/{lid}'
                        break
            elif tipo == GeomAbs_Cylinder and abs(abs(_axis(ad).dot(N)) - 1) < 1e-6:
                for src in prof.sources:
                    if src.kind == 'circle' and (src.edge.arc_center - (c - N * (c - src.edge.arc_center).dot(N))).length < 1e-6:
                        nome = f'{fid}/foro/{src.entity}'
                        break
        if nome:
            nomi.setdefault(nome, []).append(f)
    return nomi


def _axis(ad) -> bd.Vector:
    d = ad.Cylinder().Axis().Direction()
    return bd.Vector(d.X(), d.Y(), d.Z())


__all__ = ['bend_values', 'build', 'Bend', 'SheetData', 'METODI', 'VERSI', 'POSIZIONI', 'cap']


# =============================================================================== tagli disegnati su una faccia
def build_cut(fdef: dict, ctx) -> NamedShape:
    """Un contorno disegnato su una faccia della lamiera (la base sopra/sotto o una flangia dentro/fuori)
    tagliato attraverso lo spessore. Entra anche nello sviluppo, portato in piano nella posizione giusta."""
    import dataclasses

    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut

    fid = fdef['id']
    body = ctx.body
    data = getattr(body, 'sheet', None) if body is not None else None
    if data is None:
        raise FeatureError('Il taglio di lamiera va disegnato su una faccia di una lamiera (e prima di altre '
                           'lavorazioni non di lamiera).', feature=fid)
    ss, prof = ctx.sketch(fdef)
    if not prof.faces:
        raise FeatureError(f'Lo sketch "{ss.sketch.label()}" non ha contorni chiusi da tagliare.', feature=fid)
    piano = ss.sketch.plane
    nome = piano.get('face', '') if isinstance(piano, dict) else ''
    parti = nome.split('/')
    if not parti or parti[0] != data.feature:
        raise FeatureError('Il taglio di lamiera va disegnato su una faccia della lamiera.', feature=fid)
    t, pl, N = data.thickness, data.plane, data.plane.z_dir

    def proj(p):
        return p - N * N.dot(p - pl.origin)

    if len(parti) == 2 and parti[1] in ('sopra', 'sotto'):
        h = t if parti[1] == 'sopra' else 0.0
        src = bd.Plane(origin=pl.origin + N * h, x_dir=pl.x_dir, z_dir=N)
        dst = pl
        dentro = -N if parti[1] == 'sopra' else N
        g = None
    elif len(parti) == 3 and parti[2] in ('esterno', 'interno'):
        g = next((x for x in data.flanges if x.fid == parti[1]), None)
        if g is None:
            raise FeatureError(f'La flangia {parti[1]} non c’è più.', feature=fid)
        th = math.radians(g.bend.angle)
        dvec = g.n * math.cos(th) + g.zf * math.sin(th)
        nrm = g.n * -math.sin(th) + g.zf * math.cos(th)            # dalla faccia esterna verso l'interna
        sh = g.off + g.bend.ossb
        p0 = g.origin + g.n * sh + (nrm * t if parti[2] == 'interno' else bd.Vector(0, 0, 0))
        src = bd.Plane(origin=p0, x_dir=g.xf, z_dir=g.xf.cross(dvec))
        dst = bd.Plane(origin=proj(g.origin + g.n * (g.off + g.bend.ba - g.bend.ossb)), x_dir=g.xf,
                       z_dir=g.xf.cross(g.n))
        dentro = nrm if parti[2] == 'esterno' else -nrm
    else:
        raise FeatureError('Si può tagliare sulla faccia sopra/sotto della base o sulla faccia esterna/interna '
                           'di una flangia (non sulle pieghe né sui fianchi).', feature=fid)

    # niente tagli nelle pieghe: controllo su punti presi lungo i contorni disegnati
    for f in prof.faces:
        for e in f.edges():
            for p in e.positions([i / 16 for i in range(17)]):
                q = src.to_local_coords(p)
                if g is not None:
                    if q.Y < g.bend.ossb - TOL:
                        raise FeatureError(f'Il taglio cade nella piega della flangia {g.fid}: deve stare ad almeno '
                                           f'{fmt_mm(round(g.bend.ossb, 2))} mm dallo spigolo esterno.', feature=fid)
                else:
                    for h_ in data.flanges:
                        loc = proj(p) - proj(h_.origin)
                        if loc.dot(h_.n) > h_.off + TOL and h_.u0 - TOL <= loc.dot(h_.xf) <= h_.u1 + TOL:
                            raise FeatureError(f'Il taglio cade nella piega della flangia {h_.fid}: sulla base deve '
                                               f'stare ad almeno {fmt_mm(round(-h_.off, 2))} mm dal contorno.',
                                               feature=fid)
    # 3D: attraverso lo spessore
    attrezzo = None
    for f in prof.faces:
        s = bd.extrude(f.moved(bd.Location(-dentro * 0.01)), amount=t + 0.02, dir=tuple(dentro))
        attrezzo = s if attrezzo is None else attrezzo + s
    op = BRepAlgoAPI_Cut(body.shape, attrezzo.wrapped)
    if not op.IsDone():
        raise FeatureError('Il kernel non è riuscito a fare il taglio.', feature=fid)
    nuovo = body.after(op, op.Shape())
    from ..features.base import volume
    if volume(nuovo.shape) > volume(body.shape) - 1e-6:
        raise FeatureError('Il contorno disegnato non tocca la lamiera: non toglie niente.', feature=fid)
    for f in _faces_of(nuovo.shape):
        if not nuovo.names_of(f):
            nuovo.names.setdefault(f'{fid}/parete', []).append(f)
    # sviluppo: lo stesso contorno, portato in piano
    sposta = dst.location * src.location.inverse()
    flat = data.flat
    for f in prof.faces:
        flat = flat.cut(f.moved(sposta))
    flat = flat.clean() if hasattr(flat, 'clean') else flat
    facce = flat.faces() if not isinstance(flat, bd.Face) else [flat]
    if len(facce) != 1:
        raise FeatureError('Il taglio divide lo sviluppo in più pezzi.', feature=fid)
    nuovo.sheet = dataclasses.replace(data, flat=facce[0], flat_area=facce[0].area)
    return nuovo
