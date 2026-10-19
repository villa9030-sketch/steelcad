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
# angoli tra i bordi piegati sulle punte che si incontrano (scatola bordata)
MITER_TOL = 0.01      # due bordi "alla stessa altezza" per il taglio a 45° (quote scritte a mano: 34,14 per 34,1421…)
TIP_CORNERS = {'long': 'dritti, lati lunghi interi', 'short': 'dritti, lati corti interi', 'miter': 'tagliati a 45°'}
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
    if not 0 < angle <= 180:
        raise FeatureError(f'L’angolo di piega deve stare tra 0° e 180°: {fmt_mm(angle)}° non va.', feature=fid)
    if 170 < angle < 180:
        raise FeatureError('Tra 170° e 180° lo spigolo vivo esterno va all’infinito e la quota esterna non ha senso: '
                           'per un orlo (risvolto) usa 180°.', feature=fid)
    th = math.radians(angle)
    # orlo (180°): lo spigolo vivo non esiste; si misura dal bordo esterno della piega, a raggio + spessore
    ossb = (r + t) if angle == 180 else (r + t) * math.tan(th / 2)
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
    parent: str | None = None   # flangia sulla cui punta è piegata questa (None: sul contorno della base)
    depth: int = 0
    child: str | None = None    # la flangia piegata sulla punta di questa
    tip_cut: float = 0.0        # di quanto la piega della figlia accorcia il tratto dritto in punta
    tab_ranges: list = field(default_factory=list)   # alette degli angoli chiusi: [(u_da, u_a)]
    miters: list = field(default_factory=list)       # tagli a 45° negli angoli: [(punto, normale verso il bordo, mezza fessura)]
    avviso: str = ''            # perché un angolo scelto a 45° è rimasto dritto
    pext: tuple = (0.0, 0.0)    # flangia sulla punta: di quanto va oltre l'inizio/la fine della madre (su una linguetta)

    @property
    def lf(self) -> float:            # tratto dritto
        return self.length - self.bend.ossb - self.tip_cut

    def frame(self):
        """Direzione lungo la flangia (verso la punta) e normale dalla faccia esterna all'interna."""
        th = math.radians(self.bend.angle)
        return (self.n * math.cos(th) + self.zf * math.sin(th),
                self.n * -math.sin(th) + self.zf * math.cos(th))

    def fp(self, u: float, s: float) -> bd.Vector:
        """Il punto (u, s) della flangia nello sviluppo (s come nel 3D: 0 = contorno, off = fine del piano)."""
        return self.F0 + self.fx * u + self.fn * s

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
    tip_contacts: list = field(default_factory=list)   # bordi sulle punte che si incontrano negli angoli
    tip_mode: str = 'long'
    free_edges: list = field(default_factory=list)     # bordi dove si può ancora piegare: per sceglierli col mouse

    def lato_di(self, g) -> str:
        """Dove sta la piega, in parole: per le pieghe su linea la quota della linea sullo sviluppo (dal bordo da
        cui partono i numeri PL1, PL2...), che è quella che serve alla piegatrice per il registro."""
        x = (getattr(self, 'fold_pos', None) or {}).get(g.fid)
        return g.edge if x is None else f'linea a {fmt_mm(round(x, 2))} mm dal bordo'

    def summary(self) -> dict:
        return {'feature': self.feature, 'thickness': self.thickness, 'tech': self.tech,
                'bends': [{'flange': g.fid, 'edge': self.lato_di(g), 'parent': g.parent, 'length': g.length,
                           'line_at': (getattr(self, 'fold_pos', None) or {}).get(g.fid),
                           'direction': g.direction, 'position': g.position, 'width': g.u1 - g.u0,
                           **g.bend.as_dict()} for g in self.flanges],
                'flat_size': list(self.flat_size), 'flat_area': self.flat_area, 'warnings': self.warnings,
                'outline': self.outline(), 'bend_lines': [[list(a), list(b), t] for a, b, t in self.bend_lines],
                'bend_zones': self.bend_zones(), 'tip_contacts': [list(c) for c in self.tip_contacts],
                'tip_mode': self.tip_mode,
                'bend_rows': getattr(self, 'bend_rows', None), 'shape_info': getattr(self, 'shape_info', None),
                'plane': {k: [getattr(self.plane, a).X, getattr(self.plane, a).Y, getattr(self.plane, a).Z] for k, a in
                          (('origin', 'origin'), ('x', 'x_dir'), ('y', 'y_dir'), ('z', 'z_dir'))}}

    def bend_zones(self) -> list:
        """Le strisce delle pieghe nello sviluppo (lunghe BA): lì non si disegna. [[x, y] × 4] per piega."""
        out = []
        for g in self.flanges:
            if not hasattr(g, 'F0'):
                continue
            s0, s1 = g.off, g.off + g.bend.ba
            pts = [g.fp(g.u0, s0), g.fp(g.u1, s0), g.fp(g.u1, s1), g.fp(g.u0, s1)]
            out.append([[round(q.X, 3), round(q.Y, 3)] for q in (self.plane.to_local_coords(p) for p in pts)])
        return out

    def outline(self) -> list:
        """Lo sviluppo come polilinee 2D (per l'anteprima): [[x, y, ...], ...]. Calcolato una volta per sviluppo."""
        if self.flat is None:
            return []
        memo = self.__dict__.get('_outline')
        if memo is not None and memo[0] is self.flat:
            return memo[1]
        out = self._outline()
        self.__dict__['_outline'] = (self.flat, out)
        return out

    def _outline(self) -> list:
        if self.flat is None:
            return []
        out = []
        for w in self.flat.wires():
            tratti = []
            for e in w.edges():
                n = 2 if e.geom_type == bd.GeomType.LINE else 24
                tratti.append([(q.X, q.Y) for q in (self.plane.to_local_coords(p)
                                                    for p in e.positions([i / (n - 1) for i in range(n)]))])
            # i tratti in fila, testa contro coda (il kernel non promette né l'ordine né il verso)
            fila = tratti.pop(0)
            while tratti:
                coda = fila[-1]
                k, giro = min(((i, r) for i in range(len(tratti)) for r in (False, True)),
                              key=lambda x: math.dist(coda, tratti[x[0]][-1 if x[1] else 0]))
                t = tratti.pop(k)
                fila += (t[::-1] if giro else t)[1:]
            if len(fila) > 1 and math.dist(fila[0], fila[-1]) < 1e-6:
                fila.pop()
            out.append([round(c, 3) for p in fila for c in p])
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
    faccia_disegnata = face
    piegate = []                                   # (piega su linea, la parte che si piega, nello sviluppo)
    if fdef.get('folds'):
        face, lati, extra = _folds(fdef, face, lati, pl, tech, t, ctx, fid)
        usati = {fl.get('edge') for fl in flange_defs if not fl.get('parent')}
        for fo, parte in extra:
            if parte is not None:
                piegate.append((fo, parte))
        flange_defs = list(flange_defs) + [fo for fo, _ in extra]
        tagliati = usati - set(lati)
        if tagliati:
            raise FeatureError(f'Sul lato {", ".join(sorted(tagliati))} c’è una flangia, ma la piega su linea lo taglia o lo '
                               'porta via: togli la flangia o sposta la linea.', feature=fid)
    if flange_defs and tech['radius'] is None:
        raise FeatureError(_manca('il raggio interno di piega'), feature=fid, code='manca_tecnologia')
    if flange_defs and tech['radius'] < 0:
        raise FeatureError('Il raggio interno di piega non può essere negativo.', feature=fid)
    geos = []
    for fl in flange_defs:
        if fl.get('parent'):
            continue                                  # sulla punta di un'altra flangia: dopo
        flid = fl.get('id', '?')
        lid = fl.get('edge')
        if lid not in lati:
            raise FeatureError(f'La flangia {flid} è sul lato {lid}, che non è un lato dritto del contorno '
                               'esterno della lamiera.', feature=fid)
        if any(g.edge == lid for g in geos):
            raise FeatureError(f'Sul lato {lid} c’è già una flangia.', feature=fid)
        A3, B3, n3, a_id, b_id = lati[lid]
        g = _geo(fl, A3, B3, n3, N, tech, t, ctx, fid)
        g.edge = lid
        g.ends = (b_id, a_id) if g.reversed else (a_id, b_id)
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

    contatti = _tip_flanges(fdef, flange_defs, geos, tech, t, ctx, fid)

    for g in geos:
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
            if v + d / 2 > g.length - g.tip_cut + TOL:
                raise FeatureError(f'Il foro {k + 1} della flangia {g.fid} esce dalla punta della flangia'
                                   + (f' o cade nella piega della flangia {g.child}.' if g.child else '.'),
                                   feature=fid)
            g.holes.append((uf, v, d))

    tabs = _closed_corners(fdef, geos, t, ctx, fid)
    for g, ua, ub in tabs:
        g.tab_ranges.append((ua, ub))
    _flat_frames(geos, pl)

    # ----------------------------------------------------------------- solido 3D
    base = bd.extrude(face, amount=t, dir=tuple(N))
    for g in geos:
        if g.parent is None and g.off < -TOL:
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
    # alette che chiudono le testate di un profilo chiuso: servono le facce del pezzo già fatto (il vuoto)
    alette = _end_tab_parts(geos, solido, t, tech, ctx, fid, pl) if any(g.end_tab_defs for g in geos) else []
    if alette:
        parti = [base]
        for g in geos:
            sol = _flange_solid(g, t)
            for a in alette:
                if a['g'] is g:
                    sol = sol - a['cut']
            parti.append(sol)
        for g, ua, ub in tabs:
            parti.append(_tab_solid(g, ua, ub, t))
        for a in alette:
            parti += [a['bend'], a['tab']]
        vol_attesa = sum(p.volume for p in parti)
        solido = parti[0]
        for p in parti[1:]:
            solido = solido + p
        solido = solido.clean()
        solidi = solido.solids()
        if len(solidi) != 1:
            raise FeatureError('Con l’aletta di chiusura il pezzo non è venuto unico.', feature=fid)
        if abs(solido.volume - vol_attesa) > 1e-6 * max(vol_attesa, 1) + 1e-3:
            raise FeatureError('L’aletta di chiusura tocca un’altra parete: aumenta la sua fessura.', feature=fid)
    shape = solidi[0].wrapped

    # ----------------------------------------------------------------- sviluppo
    flat, linee = _flat(face, geos, pl, t, tabs)
    for a in alette:                                    # nello sviluppo: l'aletta oltre la sua piega a 90°
        flat = flat - a['flat_cut']
        flat = flat + a['flat_bend']
        flat = flat + a['flat_tab']
        flat = flat.clean() if hasattr(flat, 'clean') else flat
        facce = flat.faces() if not isinstance(flat, bd.Face) else [flat]
        if len(facce) != 1:
            raise FeatureError('Nello sviluppo l’aletta di chiusura si sovrappone ad altro: aumenta la fessura.', feature=fid)
        flat = facce[0]
        linee.append(a['line'])
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
    # in tabella: prima le flange, poi le pieghe su linea nell'ordine lungo il pezzo (non quello di costruzione,
    # che per le pieghe in serie parte dalla striscia più grande e va a catena da una parte e poi dall'altra)
    ordine = {fo.get('id'): k for k, fo in enumerate(fdef.get('folds') or [])}
    geos = sorted(geos, key=lambda g: (g.fid in ordine, ordine.get(g.fid, 0)))
    fold_pos = {}
    if flat is not None and fdef.get('folds'):
        vs = [pl.to_local_coords(v) for v in flat.vertices()]
        for fo in fdef['folds']:
            (ax, ay), (bx, by) = fo['a'], fo['b']
            L = math.hypot(bx - ax, by - ay) or 1.0
            nx, ny = -(by - ay) / L, (bx - ax) / L
            if (abs(nx) > abs(ny) and nx < 0) or (abs(ny) >= abs(nx) and ny < 0):
                nx, ny = -nx, -ny                   # verso crescente, come la numerazione PL1, PL2...
            fold_pos[fo.get('id')] = (ax + bx) / 2 * nx + (ay + by) / 2 * ny - min(v.X * nx + v.Y * ny for v in vs)
    data = SheetData(fid, t, tech, geos, flat, pl, linee, size, flat.area if flat is not None else 0.0,
                     [g.avviso for g in geos if g.avviso],
                     contatti, fdef.get('tip_corners') or 'long', _free_edges(geos, lati, N, t))
    data.fold_pos = fold_pos
    ns = NamedShape(shape, _names(shape, fid, geos, lati, prof, pl, t))
    ns.sheet = data
    # pieghe su linea con la parte piegata non rettangolare: si toglie dallo sviluppo (e dal pezzo) quello che la
    # striscia della flangia ha in più rispetto al disegno
    for fo, parte in piegate:
        g = next(x for x in geos if x.fid == fo['id'])
        rett = bd.Face(bd.Wire.make_polygon([g.fp(g.u0, g.off), g.fp(g.u1, g.off), g.fp(g.u1, g.off + g.bend.ba + g.lf),
                                             g.fp(g.u0, g.off + g.bend.ba + g.lf)], close=True))
        via = [x for x in _facce(_orienta(rett, pl) - faccia_disegnata) if x.area > 1e-4]
        if via and g.child:
            raise FeatureError(f'La piega su linea {fo["id"]} non è rettangolare (la linea è obliqua o i fianchi inclinati): '
                               f'sulla sua punta non c’è un bordo dritto per piegare {g.child}.', feature=fid)
        if via:
            ns = _cut_from_flat({'id': fid}, ns, ns.sheet, via, t)
    return ns


def _folds(fdef, face, lati, pl, tech, t, ctx, fid):
    """Pieghe lungo una linea disegnata sulla base: la base si divide sulla linea; la parte che si piega diventa una
    flangia sul nuovo lato (la corda), lunga quanto serve perché lo sviluppo resti quello disegnato: lunghezza =
    distanza massima dalla linea + deduzione di piega. La linea è lo spigolo vivo esterno della piega."""
    serie = _folds_paralleli(fdef, face, lati, pl, tech, t, ctx, fid)
    if serie is not None:
        return serie
    extra = []
    for fo in fdef['folds']:
        foid = fo.get('id', '?')
        a2, b2 = fo['a'], fo['b']
        A, B = pl.from_local_coords(tuple(a2)), pl.from_local_coords(tuple(b2))
        if (B - A).length < 1e-6:
            raise FeatureError(f'La piega su linea {foid} ha la linea di lunghezza zero.', feature=fid)
        u = (B - A).normalized()
        n = u.cross(pl.z_dir).normalized()            # a destra della linea
        G = 1e5
        lato_n = bd.Face(bd.Wire.make_polygon([A - u * G, A + u * G, A + u * G + n * G, A - u * G + n * G], close=True))
        lato_n = _orienta(lato_n, pl)
        piega = _facce(face & lato_n)
        resta = _facce(face - lato_n)
        if not piega or not resta:
            raise FeatureError(f'La linea della piega {foid} non attraversa la lamiera: deve tagliarla da parte a parte.',
                               feature=fid)
        if len(piega) != 1 or len(resta) != 1:
            raise FeatureError(f'La linea della piega {foid} divide la lamiera in più di due pezzi: la piega si fa solo '
                               'su una linea che la taglia una volta.', feature=fid)
        # si piega la parte più piccola; con "flip" l'altra
        if (piega[0].area > resta[0].area) != bool(fo.get('flip')):
            n = -n
            piega, resta = resta, piega
        parte, face = piega[0], resta[0]
        # la corda: i vertici del pezzo che resta che stanno sulla linea
        sulla = [bd.Vector(v) for v in face.vertices() if abs((bd.Vector(v) - A).dot(n)) < 1e-6]
        if len(sulla) < 2:
            raise FeatureError(f'Non trovo il lato della piega {foid}.', feature=fid)
        sulla.sort(key=lambda q: (q - A).dot(u))
        C0, C1 = sulla[0], sulla[-1]
        if (C0 - A).dot(u) < -1e-3 or (C1 - A).dot(u) > (B - A).length + 1e-3:
            raise FeatureError(f'La linea della piega {foid} non attraversa la lamiera da parte a parte: allungala fino '
                               'ai bordi (o oltre).', feature=fid)
        # la parte che si piega deve stare tutta "davanti" alla corda (la flangia è una striscia)
        us = [(bd.Vector(v) - C0).dot(u) for v in parte.vertices()]
        L = (C1 - C0).length
        # se la parte da piegare va un po' oltre i lati della linea (fianchi non perpendicolari), la flangia si
        # allarga quanto serve: quello in più lo toglie il taglio sullo sviluppo
        C0, C1 = C0 + u * min(0.0, min(us)), C0 + u * max(L, max(us))
        dmax = max((bd.Vector(v) - C0).dot(n) for v in parte.vertices())
        b = bend_values(evaluate(fo.get('angle', 90), ctx.params, what=f'l’angolo della piega {foid}'),
                        tech['radius'] if tech['radius'] is not None else 0, t, tech['method'], tech['k'], tech['bd90'], fid)
        # i lati della base tagliati dalla linea o rimasti dalla parte piegata non ci sono più
        tenuti = {}
        for lid, (P3, Q3, n3, ia, ib) in lati.items():
            if (P3 - A).dot(n) < 1e-6 and (Q3 - A).dot(n) < 1e-6 and not (abs((P3 - A).dot(n)) < 1e-6 and abs((Q3 - A).dot(n)) < 1e-6):
                tenuti[lid] = (P3, Q3, n3, ia, ib)
        # un lato tagliato a metà dalla linea resta solo se finisce sulla linea senza passarla
        lati = tenuti
        lati[foid] = (C0, C1, n, f'{foid}:a', f'{foid}:b')
        extra.append(({'id': foid, 'edge': foid, 'angle': fo.get('angle', 90), 'direction': fo.get('direction', 'up'),
                       'position': 'inside', 'length': round(dmax + b.bd, 9), 'gap': 0, 'fold': True}, parte))
    return face, lati, extra


def _folds_paralleli(fdef, face, lati, pl, tech, t, ctx, fid):
    """Più pieghe su linee parallele (calandratura a colpi, "bumping"): la striscia più grande resta la base, le
    altre diventano una catena di flange, ognuna sulla punta di quella prima. Ogni flangia è lunga quanto la sua
    striscia nello sviluppo + la deduzione della sua piega, così lo sviluppo resta quello disegnato (come per la
    piega su una linea sola). None se le linee non sono tutte parallele (si piegano una per una)."""
    folds = fdef['folds']
    if len(folds) < 2:
        return None
    righe = []
    for fo in folds:
        A, B = pl.from_local_coords(tuple(fo['a'])), pl.from_local_coords(tuple(fo['b']))
        if (B - A).length < 1e-6:
            raise FeatureError(f'La piega su linea {fo.get("id", "?")} ha la linea di lunghezza zero.', feature=fid)
        righe.append((fo, A, (B - A).normalized()))
    u = righe[0][2]
    if any(abs(r[2].cross(u).length) > 1e-6 for r in righe):
        return None
    n = u.cross(pl.z_dir).normalized()
    O = righe[0][1]
    righe.sort(key=lambda r: (r[1] - O).dot(n))
    pos = [(r[1] - O).dot(n) for r in righe]
    if any(b - a < 1e-6 for a, b in zip(pos, pos[1:])):
        raise FeatureError('Due linee di piega sono una sopra l’altra.', feature=fid)
    G = 1e5

    def striscia(s0, s1):
        P0, P1 = O + n * s0, O + n * s1
        f = bd.Face(bd.Wire.make_polygon([P0 - u * G, P0 + u * G, P1 + u * G, P1 - u * G], close=True))
        parti = _facce(face & _orienta(f, pl))
        if len(parti) != 1:
            raise FeatureError('Le linee di piega devono attraversare la lamiera da parte a parte, una volta sola.',
                               feature=fid)
        return parti[0]
    limiti = [-G] + pos + [G]
    strisce = [striscia(limiti[i], limiti[i + 1]) for i in range(len(limiti) - 1)]
    ib = max(range(len(strisce)), key=lambda i: strisce[i].area)
    base = strisce[ib]

    def bd_di(fo):
        return bend_values(evaluate(fo.get('angle', 90), ctx.params, what=f'l’angolo della piega {fo.get("id", "?")}'),
                           tech['radius'] if tech['radius'] is not None else 0, t, tech['method'], tech['k'],
                           tech['bd90'], fid).bd

    def corda(f, s0):
        sulla = sorted((bd.Vector(v) for v in f.vertices() if abs((bd.Vector(v) - O).dot(n) - s0) < 1e-6),
                       key=lambda q: (q - O).dot(u))
        return sulla
    extra = []
    nuovi_lati = {}
    # verso +n le linee dopo la base, verso -n quelle prima: ognuna è la punta della precedente
    for verso, indici in ((1, range(ib, len(righe))), (-1, range(ib - 1, -1, -1))):
        madre = None
        for j in indici:
            fo = righe[j][0]
            foid = fo.get('id', '?')
            k = j + 1 if verso > 0 else j                  # la striscia che questa piega alza
            parte = strisce[k]
            larga = parte.area / max(1e-9, (limiti[k + 1] - limiti[k])) if abs(limiti[k + 1]) < G and abs(limiti[k]) < G else None
            sulla = corda(parte, pos[j])
            if len(sulla) < 2:
                raise FeatureError(f'Non trovo il lato della piega {foid}.', feature=fid)
            Lc = (sulla[-1] - sulla[0]).length
            # le strisce in mezzo devono essere rettangoli: sulla punta si piega la prossima
            if larga is not None and abs(larga - Lc) > 1e-3:
                raise FeatureError(f'Tra la piega {foid} e la successiva la lamiera non è un rettangolo: per le pieghe '
                                   'in serie le linee devono andare da bordo a bordo su lati dritti.', feature=fid)
            dmax = max(((bd.Vector(v) - O).dot(n) - pos[j]) * verso for v in parte.vertices())
            d = dict(id=foid, angle=fo.get('angle', 90), direction=fo.get('direction', 'up'), position='inside',
                     length=round(dmax + bd_di(fo), 9), gap=0, fold=True)
            if madre is None:
                cb = corda(base, pos[j])
                if len(cb) < 2:
                    raise FeatureError(f'Non trovo il lato della piega {foid}.', feature=fid)
                d['edge'] = foid
                nuovi_lati[foid] = (cb[0], cb[-1], n * verso, f'{foid}:a', f'{foid}:b')
            else:
                d['parent'] = madre
                # sulla punta della madre "su" vuol dire dalla stessa parte in cui è girata lei: la curva continua
                # nello stesso senso (con "giù" sulla base, le figlie in "giù" andrebbero a zig-zag)
                if d['direction'] == 'down':
                    d['direction'] = 'up'
            if madre is not None:
                # la madre arriva fino a questa linea: la sua striscia è lunga quanto la distanza tra le due linee
                m = next(x for x, _ in extra if x['id'] == madre)
                m['length'] = round(abs(pos[j] - pos[j - verso]) + bd_di(next(r[0] for r in righe if r[0].get('id') == madre)), 9)
            extra.append((d, None))
            madre = foid
    # i lati della base: quelli che stanno tutti nella sua striscia (non sulle linee)
    s0, s1 = limiti[ib], limiti[ib + 1]
    tenuti = {}
    for lid, (P3, Q3, n3, ia, ib_) in lati.items():
        sp, sq = (P3 - O).dot(n), (Q3 - O).dot(n)
        if s0 - 1e-6 <= min(sp, sq) and max(sp, sq) <= s1 + 1e-6 and not (abs(sp - sq) < 1e-6 and (abs(sp - s0) < 1e-6 or abs(sp - s1) < 1e-6)):
            tenuti[lid] = (P3, Q3, n3, ia, ib_)
    tenuti.update(nuovi_lati)
    return base, tenuti, extra


def flat_size(flat, pl) -> tuple:
    """Ingombro (larghezza, altezza) dello sviluppo nel piano dello sketch, cerchi compresi."""
    if flat is None:
        return (0.0, 0.0)
    bb = [pl.to_local_coords(v) for v in flat.vertices()]
    for e in flat.edges():
        if e.geom_type == bd.GeomType.CIRCLE:
            for p in (e.arc_center - e.radius * pl.x_dir, e.arc_center + e.radius * pl.x_dir,
                      e.arc_center - e.radius * pl.y_dir, e.arc_center + e.radius * pl.y_dir):
                bb.append(pl.to_local_coords(p))
        elif e.geom_type != bd.GeomType.LINE:
            bb += [pl.to_local_coords(p) for p in e.positions([i / 16 for i in range(17)])]
    if not bb:
        return (0.0, 0.0)
    return (max(p.X for p in bb) - min(p.X for p in bb), max(p.Y for p in bb) - min(p.Y for p in bb))


def _free_edges(geos, lati, N, t) -> list:
    """I bordi liberi, a metà spessore: i lati dritti della base senza flangia e le punte delle flange
    senza figlia. [{'kind': 'edge'|'tip', 'ref': lato o flangia, 'a': [x,y,z], 'b': [...], 'length': mm}]"""
    out = []
    v = lambda p: [p.X, p.Y, p.Z]  # noqa: E731
    usati = {g.edge for g in geos if g.parent is None}
    for lid, (A3, B3, _n, _a, _b) in lati.items():
        if lid not in usati:
            out.append({'kind': 'edge', 'ref': lid, 'a': v(A3 + N * (t / 2)), 'b': v(B3 + N * (t / 2)),
                        'length': (B3 - A3).length})
    for g in geos:
        if g.child:
            continue
        q = _section_points(g, t)
        mid = ((q['ot'][0] + q['it'][0]) / 2, (q['ot'][1] + q['it'][1]) / 2)
        out.append({'kind': 'tip', 'ref': g.fid, 'a': v(g.p(g.u0, *mid)), 'b': v(g.p(g.u1, *mid)),
                    'length': g.u1 - g.u0})
    return out


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


def _geo(fl, A3, B3, n3, N, tech, t, ctx, fid) -> FlangeGeo:
    """Una flangia piegata sul bordo A3-B3 di un piano di normale N (N va dalla faccia esterna, dove sta il
    bordo, verso l'altra faccia). n3 è la direzione che esce dal piano, perpendicolare al bordo."""
    flid = fl.get('id', '?')
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
    zf = N if dirz == 'up' else -N
    a3 = (B3 - A3).normalized()
    xf = n3.cross(zf)
    rev = xf.dot(a3) < 0
    start = B3 if rev else A3
    origin = start + (N * t if dirz == 'down' else bd.Vector(0, 0, 0))
    sh = 0.0 if pos == 'inside' else b.ossb
    g = FlangeGeo(flid, None, b, L, dirz, pos, origin, xf, n3, zf, (B3 - A3).length, rev, sh - b.ossb)
    g.gap = evaluate(fl.get('gap', 0), ctx.params, what=f'la fessura d’angolo della flangia {flid}')
    g.hole_defs = fl.get('holes') or []
    g.end_tab_defs = fl.get('end_tabs') or []
    return g


def _tip_flanges(fdef, flange_defs, geos, tech, t, ctx, fid) -> list:
    """Le flange piegate sulla punta di un'altra flangia (omega, scatole bordate, Z...), anche a catena.
    Il "piano" da cui partono è il tratto dritto della madre: il bordo è la sua punta, misurata come la
    lunghezza della madre (dallo spigolo vivo), così con "quota esterna" anche la madre resta quota esterna.
    Si fanno a livelli (prima le figlie della base, poi le loro figlie...): gli angoli tra i bordi di uno
    stesso livello si chiudono come ha scelto l'utente (fdef["tip_corners"]). Ritorna le coppie che si toccano."""
    modo = fdef.get('tip_corners') or 'long'
    if modo not in TIP_CORNERS:
        raise FeatureError(f'Tipo di angolo dei bordi "{modo}" sconosciuto.', feature=fid)
    per_id = {g.fid: g for g in geos}
    da_fare = [fl for fl in flange_defs if fl.get('parent')]
    contatti = []
    while da_fare:
        pronti = [fl for fl in da_fare if fl['parent'] in per_id]
        if not pronti:
            fl = da_fare[0]
            raise FeatureError(f'La flangia {fl.get("id")} è sulla punta della flangia {fl.get("parent")}, '
                               'che non c’è più.', feature=fid)
        nuove = []
        for fl in pronti:
            p = per_id[fl['parent']]
            flid = fl.get('id', '?')
            if p.child:
                raise FeatureError(f'Sulla punta della flangia {p.fid} c’è già la flangia {p.child}.', feature=fid)
            dvec, nrm = p.frame()
            th = math.radians(p.bend.angle)
            sh = p.off + p.bend.ossb
            ext = fl.get('extend') or [0, 0]
            e0, e1 = (evaluate(x, ctx.params, what=f'il prolungamento della flangia {flid}') for x in ext)
            if e0 < 0 or e1 < 0:
                raise FeatureError(f'Il prolungamento della flangia {flid} non può essere negativo.', feature=fid)
            A3 = p.p(p.u0 - e0, sh + p.length * math.cos(th), p.length * math.sin(th))
            B3 = p.p(p.u1 + e1, sh + p.length * math.cos(th), p.length * math.sin(th))
            g = _geo(fl, A3, B3, dvec, nrm, tech, t, ctx, fid)
            g.pext = (e0, e1)
            g.edge = f'punta di {p.fid}'
            g.parent, g.depth = p.fid, p.depth + 1
            g.ends = (f'{flid}:a', f'{flid}:b')
            g.u0, g.u1, g.ext = 0.0, g.length_edge, [0.0, 0.0]
            p.child = flid
            p.tip_cut = max(0.0, -g.off)
            if p.lf <= TOL:
                raise FeatureError(f'La flangia {p.fid} è troppo corta per piegarci sopra {flid}: le due pieghe si '
                                   f'toccano. Allungala oltre {fmt_mm(round(p.bend.ossb + p.tip_cut, 2))} mm.',
                                   feature=fid)
            nuove.append(g)
            da_fare.remove(fl)
        # contro quello che c'era già (non la madre): la nuova si accorcia; con un bordo di un altro livello
        # complanare e "a 45°" scelto, si taglia a 45° anche con quello (es. il bordo di un profilo e quello
        # della parete che lo chiude)
        for g in nuove:
            altre = [h for h in geos if h.fid != g.parent]
            if modo != 'miter':
                contatti += [(h.fid, g.fid) for h in altre if h.parent is not None and _overlap(g, h, t)]
            else:
                for h in [h for h in altre if h.parent is not None and _overlap(g, h, t)]:
                    contatti.append((h.fid, g.fid))
                    if _miter(g, h, t, fid):
                        altre.remove(h)
                    else:
                        g.avviso = _perche_dritto(g, h)
            _trim_against(g, altre, t, fid)
        # tra i bordi nuovi che si incontrano negli angoli: dritti (lunghi o corti interi) o a 45°
        for i, a in enumerate(nuove):
            for b in nuove[i + 1:]:
                if not _overlap(a, b, t):
                    continue
                contatti.append((a.fid, b.fid))
                if modo == 'miter' and _miter(a, b, t, fid):
                    continue
                lunga = [x for x in (a, b) if any(x.pext) and not _complanari(a, b)]
                if lunga:                                 # il prolungamento sopra una linguetta si ferma contro l'altra
                    _trim_against(lunga[0], [b if lunga[0] is a else a], t, fid)
                    continue
                if modo == 'miter':
                    b.avviso = _perche_dritto(b, a)
                intera, corta = sorted((a, b), key=lambda x: -x.length_edge if modo != 'short' else x.length_edge)
                _trim_against(corta, [intera], t, fid)
        for g in nuove:
            geos.append(g)
            per_id[g.fid] = g
    return contatti


def _complanari(a: FlangeGeo, b: FlangeGeo) -> bool:
    na = a.frame()[1]
    Pa = a.origin + a.n * (a.off + a.bend.ossb)
    Pb = b.origin + b.n * (b.off + b.bend.ossb)
    return abs(abs(na.dot(b.frame()[1])) - 1) <= 1e-9 and abs((Pb - Pa).dot(na)) <= MITER_TOL


def _perche_dritto(a: FlangeGeo, b: FlangeGeo) -> str:
    na = a.frame()[1]
    Pa = a.origin + a.n * (a.off + a.bend.ossb)
    Pb = b.origin + b.n * (b.off + b.bend.ossb)
    if abs(abs(na.dot(b.frame()[1])) - 1) > 1e-9:
        return f'L’angolo tra {b.fid} e {a.fid} resta dritto: non sono nello stesso piano.'
    return (f'L’angolo tra {b.fid} e {a.fid} resta dritto: i due bordi non sono alla stessa altezza (differenza '
            f'{fmt_mm(round(abs((Pb - Pa).dot(na)), 2))} mm). Per il taglio a 45° le loro facce devono stare nello stesso piano.')


def _overlap(a: FlangeGeo, b: FlangeGeo, t: float) -> bool:
    """Si compenetrano? Con un po' di tolleranza: due bordi alla stessa altezza hanno facce complanari, e lì
    l'intersezione esatta a volte torna vuota."""
    return _common_volume(_flange_solid(a, t), _flange_solid(b, t)) > 1e-6


def _common_volume(A, B) -> float:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    try:
        op = BRepAlgoAPI_Common()
        op.SetFuzzyValue(1e-5)
        return A._bool_op((A,), (B,), op).volume
    except Exception:  # noqa: BLE001
        return 0.0
        return bd.Shape.cast(op.Shape()).volume
    except Exception:  # noqa: BLE001
        return 0.0


def _miter(a: FlangeGeo, b: FlangeGeo, t: float, fid) -> bool:
    """Angolo a 45° (in generale: sulla bisettrice) tra due bordi complanari che si incontrano. Il taglio passa
    per l'incrocio delle linee dove cominciano i loro tratti dritti, così non entra nelle pieghe; con la
    fessura d'angolo i bordi si accorciano quanto basta. False se non sono complanari (si fa dritto)."""
    na, nb = a.frame()[1], b.frame()[1]
    Pa = a.origin + a.n * (a.off + a.bend.ossb)            # sullo spigolo vivo, faccia esterna del bordo
    Pb = b.origin + b.n * (b.off + b.bend.ossb)
    if abs(abs(na.dot(nb)) - 1) > 1e-9 or abs((Pb - Pa).dot(na)) > MITER_TOL:
        return False
    Sa = Pa + a.frame()[0] * a.bend.ossb                   # dove comincia il tratto dritto
    Sb = Pb + b.frame()[0] * b.bend.ossb
    cr = a.xf.cross(b.xf)
    if cr.length < 1e-9:
        return False
    C = Sa + a.xf * ((Sb - Sa).cross(b.xf).dot(cr) / cr.length ** 2)
    meta = max(a.gap, b.gap) / 2
    lati = []
    for g in (a, b):
        mid = g.origin + g.xf * ((g.u0 + g.u1) / 2)
        lati.append(g.xf if (mid - C).dot(g.xf) > 0 else -g.xf)      # dall'angolo verso il resto del bordo
    m = (lati[0] - lati[1]).normalized()
    for g, e in ((a, lati[0]), (b, lati[1])):
        # prolungata sopra una linguetta ma non fin qui (es. la linguetta ha lo spigolo raccordato): arriva all'angolo
        uc = (C - g.origin).dot(g.xf)
        if e.dot(g.xf) > 0 and g.pext[0] > 0 and g.u0 > uc:
            g.u0 = uc
        elif e.dot(g.xf) < 0 and g.pext[1] > 0 and g.u1 < uc:
            g.u1 = uc
    for g, mm, e in ((a, m, lati[0]), (b, -m, lati[1])):
        # le pieghe restano intere: se la fessura le toccherebbe, il bordo si accorcia all'angolo
        q = _section_points(g, t)
        inizio = e.dot(g.xf) > 0
        u_fine = g.u0 if inizio else g.u1
        serve = max(meta - (g.p(u_fine, *q[k]) - C).dot(mm) for k in ('os', 'om', 'oe', 'is', 'im', 'ie'))
        if serve > 1e-9:
            sposta = serve / e.dot(mm) + 1e-6
            if inizio:
                g.u0 += sposta
            else:
                g.u1 -= sposta
            if g.u1 - g.u0 <= TOL:
                raise FeatureError(f'La flangia {g.fid} non ha più larghezza col taglio a 45°.', feature=fid)
        g.miters.append((C, mm, meta))
    return True


def _trim_against(g: FlangeGeo, altre, t, fid):
    """Una flangia sulla punta che si compenetra con un'altra (i bordi di una scatola che si incontrano
    nell'angolo) si accorcia, dalla parte dell'altra, fino a toccarla (più la sua fessura d'angolo)."""
    sol = _flange_solid(g, t)
    for h in altre:
        sh_ = _flange_solid(h, t)
        comune = _common_volume(sol, sh_)
        if comune <= 1e-6:
            continue
        us = [(p - g.origin).dot(g.xf) for e in sh_.edges() for p in e.positions([i / 8 for i in range(9)])]
        lo, hi = min(us), max(us)
        if hi - g.u0 < g.u1 - lo:          # l'altra sta all'inizio
            g.u0 = max(g.u0, hi + g.gap)
        else:
            g.u1 = min(g.u1, lo - g.gap)
        if g.u1 - g.u0 <= TOL:
            raise FeatureError(f'La flangia {g.fid} non ha più larghezza: la flangia {h.fid} la occupa tutta.',
                               feature=fid)
        sol = _flange_solid(g, t)


def _flat_frames(geos, pl):
    """Dove sta ogni flangia nello sviluppo: origine e assi (lungo il bordo, verso fuori) nel piano dello sketch.
    Una flangia sulla punta continua la striscia della madre, dopo il suo tratto dritto."""
    N = pl.z_dir
    per_id = {g.fid: g for g in geos}
    for g in geos:                     # le madri vengono sempre prima delle figlie
        if g.parent is None:
            g.F0 = g.origin - N * N.dot(g.origin - pl.origin)
            g.fx, g.fn = g.xf, g.n
        else:
            p = per_id[g.parent]
            fine = p.off + p.bend.ba + p.lf
            g.fx = -p.fx if g.reversed else p.fx
            g.fn = p.fn
            g.F0 = p.fp(p.u1 + g.pext[1] if g.reversed else p.u0 - g.pext[0], fine) - g.fn * g.off


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
    for C, m, meta in g.miters:                         # angoli a 45°: via la parte oltre la bisettrice
        sol = sol - _half_space(C + m * meta, -m)
    return sol


def _half_space(o: bd.Vector, verso: bd.Vector, B: float = 1e5):
    """Un cubo enorme dalla parte "verso" del piano per o: per tagliare via mezzo spazio."""
    pln = bd.Plane(origin=o, z_dir=verso)
    angolo = o - pln.x_dir * B - pln.y_dir * B
    return bd.Solid.make_box(2 * B, 2 * B, B, bd.Plane(origin=angolo, x_dir=pln.x_dir, z_dir=verso))


def _check_base_holes(face, prof, geos, pl, fid):
    for w in face.inner_wires():
        for e in w.edges():
            if e.geom_type != bd.GeomType.CIRCLE:
                continue
            c, r = e.arc_center, e.radius
            for g in geos:
                if g.parent is not None:
                    continue
                s =(c - g.origin + g.zf * g.zf.dot(g.origin - c)).dot(g.n)
                u = (c - g.origin).dot(g.xf)
                if s + r > g.off - TOL and g.u0 - r < u < g.u1 + r:
                    raise FeatureError(f'Il foro {prof.entity_of(e) or ""} è troppo vicino alla piega della flangia '
                                       f'{g.fid}: il suo bordo deve stare ad almeno {fmt_mm(round(-g.off, 2))} mm dal '
                                       'contorno (dove comincia la piega).', feature=fid)


def _hull(pts):
    """Involucro convesso di punti 2D (catena monotona), in senso antiorario."""
    pts = sorted(set((round(x, 9), round(y, 9)) for x, y in pts))
    if len(pts) < 3:
        return pts
    def giro(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    sotto, sopra = [], []
    for p in pts:
        while len(sotto) >= 2 and giro(sotto[-2], sotto[-1], p) <= 0:
            sotto.pop()
        sotto.append(p)
    for p in reversed(pts):
        while len(sopra) >= 2 and giro(sopra[-2], sopra[-1], p) <= 0:
            sopra.pop()
        sopra.append(p)
    return sotto[:-1] + sopra[:-1]


def _orienta(f, pl):
    """La faccia rivolta come lo sketch (se no unendola allo sviluppo non si fonde)."""
    return f if f.normal_at().dot(pl.z_dir) > 0 else bd.Face(f.wrapped.Reversed())


def _end_tab_parts(geos, solido, t, tech, ctx, fid, pl_sk) -> list:
    """Alette di chiusura delle testate (fl["end_tabs"] = [{"end": "u0"|"u1", "gap": g}]).

    Da una parete del profilo (una flangia) parte un'aletta piegata a 90° verso il vuoto del profilo:
    la sua faccia esterna sta a filo della testata, la sua forma è il vuoto del profilo (la faccia di
    testata ha un foro: quello) ristretto della fessura. La piega ha il raggio della lamiera; la parete si
    accorcia di (r + sp) dove parte la piega. Nello sviluppo l'aletta sta oltre la fine della striscia
    della parete: BA della piega a 90°, poi l'aletta stesa."""
    out = []
    r = tech['radius']
    for g in geos:
        for k, et in enumerate(g.end_tab_defs):
            dove = et.get('end')
            if dove not in ('u0', 'u1'):
                raise FeatureError(f'Aletta di chiusura {k + 1} della flangia {g.fid}: estremità sconosciuta.', feature=fid)
            gap = evaluate(et.get('gap', 0) or 0, ctx.params, what=f'la fessura dell’aletta di chiusura di {g.fid}')
            if gap < 0:
                raise FeatureError('La fessura dell’aletta di chiusura non può essere negativa.', feature=fid)
            b = bend_values(90, r, t, tech['method'], tech['k'], tech['bd90'], fid)
            sg = 1 if dove == 'u1' else -1
            u_end = g.u1 if dove == 'u1' else g.u0
            fuori = g.xf * sg                                   # dalla parete verso fuori, oltre la testata
            dvec, nrm = g.frame()
            sh = g.off + g.bend.ossb
            p0 = g.origin + g.n * sh                            # spigolo vivo esterno della parete (u = 0)
            q_a, q_b = g.bend.ossb, g.length - g.tip_cut          # il tratto dritto lungo la parete
            fine = p0 + g.xf * u_end                            # sulla testata, sulla faccia esterna
            # la faccia di testata del pezzo
            testata = None
            for f in solido.faces():
                if f.geom_type == bd.GeomType.PLANE and abs(abs(f.normal_at().dot(g.xf)) - 1) < 1e-6                         and abs((f.center() - fine).dot(g.xf)) < 1e-6:
                    testata = f
                    break
            if testata is None:
                raise FeatureError(f'La flangia {g.fid} non arriva alla testata da chiudere.', feature=fid)
            # il vuoto del profilo: dentro l'involucro delle pareti della catena (anche se alla giunzione resta
            # una fessura), meno il materiale della testata
            per_id = {x.fid: x for x in geos}
            catena, x = [], g
            while x is not None:
                catena.append(x)
                x = per_id.get(x.parent) if x.parent else None
            x = g
            while x.child and x.child in per_id:
                x = per_id[x.child]
                catena.append(x)
            E0 = bd.Plane(origin=fine, x_dir=nrm, z_dir=nrm.cross(dvec))
            pts2 = []
            for c in catena:
                q = _section_points(c, t)
                for kk in ('os', 'om', 'oe', 'ot', 'it', 'ie', 'im', 'is'):
                    v3 = E0.to_local_coords(c.p(u_end, *q[kk]))
                    pts2.append((v3.X, v3.Y))
            scafo = _hull(pts2)
            if len(scafo) < 3:
                raise FeatureError(f'Alla testata di {g.fid} non c’è un profilo da chiudere.', feature=fid)
            involucro = bd.Face(bd.Wire.make_polygon([E0.from_local_coords(c) for c in scafo], close=True))
            vuoti = (involucro - testata).faces()
            vuoto = None
            for f in sorted(vuoti, key=lambda x: -x.area):
                dz = [(pp - fine).dot(nrm) for e in f.edges() for pp in e.positions([i / 8 for i in range(9)])]
                if any(abs(d) < 1e-6 or abs(d - t) < 1e-6 for d in dz):
                    vuoto = f
                    break
            if vuoto is None or vuoto.area < 2 * (r + t) ** 2:     # una scheggia dentro una piega non è un vuoto
                raise FeatureError(f'Alla testata della flangia {g.fid} non c’è un vuoto da chiudere: il profilo è aperto. '
                                   'L’aletta di chiusura serve sui profili chiusi.', feature=fid)
            lato_interno = (vuoto.center() - fine).dot(nrm) > t / 2
            verso = nrm if lato_interno else -nrm               # dalla parete verso il vuoto
            muro = fine + (nrm * t if lato_interno else bd.Vector(0, 0, 0))   # faccia della parete verso il vuoto
            foro = vuoto
            if gap > 0:
                foro = max(bd.offset(foro, amount=-gap, kind=bd.Kind.INTERSECTION).faces(), key=lambda x: x.area)
            # l'aletta comincia a r dalla parete (prima c'è la piega)
            E = bd.Plane(origin=muro, x_dir=verso, z_dir=verso.cross(dvec))
            B = 1e5
            semipiano = bd.Face(bd.Wire.make_polygon([E.from_local_coords(c) for c in ((r, -B), (B, -B), (B, B), (r, B))], close=True))
            comune = foro & semipiano
            pezzi = comune.faces() if comune is not None else []
            if not pezzi:
                raise FeatureError(f'Alla testata di {g.fid} non c’è un vuoto chiuso abbastanza grande per un’aletta con raggio '
                                   f'{fmt_mm(r)}: il profilo è aperto o troppo stretto.', feature=fid)
            aletta2d = max(pezzi, key=lambda x: x.area)
            qs = [(pp - p0).dot(dvec) for e in aletta2d.edges() for pp in e.positions([i / 16 for i in range(17)])]
            s0, s1 = max(min(qs), q_a + gap), min(max(qs), q_b - gap)
            if s1 - s0 <= TOL:
                raise FeatureError(f'L’aletta di chiusura di {g.fid} non ha dove piegarsi: la parete è troppo stretta.', feature=fid)
            tab = bd.extrude(aletta2d, amount=t, dir=tuple(-fuori))
            # la piega: un quarto di corona tra la parete e l'aletta, lungo la parete da s0 a s1
            C = muro + verso * r - fuori * (t + r) + dvec * (s0 - (muro - p0).dot(dvec))
            R = r + t
            Ai, Ao, Bi, Bo = C - verso * r, C - verso * R, C + fuori * r, C + fuori * R
            m = (fuori - verso).normalized()
            lati = [bd.Edge.make_three_point_arc(Ao, C + m * R, Bo), bd.Edge.make_line(Bo, Bi)]
            if r > TOL:
                lati.append(bd.Edge.make_three_point_arc(Bi, C + m * r, Ai))
            lati.append(bd.Edge.make_line(Ai if r > TOL else Bi, Ao))
            piega = bd.extrude(bd.Face(bd.Wire(lati)), amount=s1 - s0, dir=tuple(dvec))
            # dalla parete si toglie la parte che diventa piega
            o = muro - fuori * (r + t) + dvec * (s0 - (muro - p0).dot(dvec)) - verso * (t + 0.5)
            zz = fuori.cross(dvec)
            if zz.dot(verso) < 0:
                o = o + verso * (t + 1)
            taglio = bd.Solid.make_box(r + t + 1, s1 - s0, t + 1, bd.Plane(origin=o, x_dir=fuori, z_dir=zz))
            # sviluppo: piano della faccia esterna e il suo corrispondente steso (stesse coordinate (u, q))
            src, dst = _flange_planes(g, t)
            P = lambda u, q: dst.from_local_coords((u, q))  # noqa: E731
            u_piega = u_end - sg * (r + t)
            poly = lambda pts: bd.Face(bd.Wire.make_polygon(pts, close=True))  # noqa: E731
            flat_cut = poly([P(u_piega, s0), P(u_end + sg * 1, s0), P(u_end + sg * 1, s1), P(u_piega, s1)])
            flat_bend = poly([P(u_piega, s0), P(u_piega + sg * b.ba, s0), P(u_piega + sg * b.ba, s1), P(u_piega, s1)])
            F = bd.Plane(origin=P(u_piega + sg * (b.ba - r), 0), x_dir=g.fx * sg,
                         z_dir=(g.fx * sg).cross(dst.y_dir))
            sposta = F.location * bd.Plane(origin=muro - dvec * (muro - p0).dot(dvec), x_dir=verso,
                                           z_dir=verso.cross(dvec)).location.inverse()
            flat_tab = aletta2d.moved(sposta)
            um = u_piega + sg * b.ba / 2
            a2, b2 = P(um, s0), P(um, s1)
            loc = lambda v: (pl_sk.to_local_coords(v).X, pl_sk.to_local_coords(v).Y)  # noqa: E731
            out.append({'g': g, 'tab': tab, 'bend': piega, 'cut': taglio,
                        'flat_cut': _orienta(flat_cut, pl_sk), 'flat_bend': _orienta(flat_bend, pl_sk),
                        'flat_tab': _orienta(flat_tab, pl_sk),
                        'line': (loc(a2), loc(b2), f'{g.fid} chiusura 90° R{fmt_mm(r)}')})
    return out


def _flat(face, geos, pl, t, tabs=()):
    """Lo sviluppo sul piano dello sketch: base accorciata + strisce lunghe BA + tratto dritto."""
    def pf(g, u, s):            # punto sul piano dello sketch (z = 0), anche per le flange "giù" e sulle punte
        return g.fp(u, s)

    def poly(pts):              # stessa faccia rivolta come lo sketch, se no l'unione non si fonde
        f = bd.Face(bd.Wire.make_polygon(pts, close=True))
        return f if f.normal_at().dot(pl.z_dir) > 0 else bd.Face(bd.Wire.make_polygon(pts[::-1], close=True))

    flat = face
    for g in geos:
        if g.parent is None and g.off < -TOL:
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
        for C, m, meta in g.miters:                     # angoli a 45°: lo stesso taglio, portato in piano
            src, dst = _flange_planes(g, t)
            dl = m.cross(g.frame()[1]).normalized()
            o, B = C + m * meta, 1e5
            piano = [dst.from_local_coords((q.X, q.Y)) for q in
                     (src.to_local_coords(p) for p in (o + dl * B, o - dl * B, o - dl * B - m * B, o + dl * B - m * B))]
            s1 = g.off + g.bend.ba
            rett = poly([pf(g, g.u0 - 1, s1), pf(g, g.u1 + 1, s1), pf(g, g.u1 + 1, s1 + g.lf + 1),
                         pf(g, g.u0 - 1, s1 + g.lf + 1)])
            flat = flat - (rett & poly(piano))
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
    ordine = sorted(geos, key=lambda x: -x.depth)      # prima le flange sulle punte: stanno "oltre" la madre
    scatole = {g.fid: _section_box(g, t) for g in geos}
    for f in _faces_of(shape):
        bf = bd.Face(f)
        c = bf.center()
        ad = BRepAdaptor_Surface(f)
        tipo = ad.GetType()
        nome = _flange_face_name(c, bf, ad, tipo, ordine, scatole, fid, t)
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
        if nome is None and tipo == GeomAbs_Plane:
            # due flange complanari che si toccano (i bordi di una scatola nell'angolo) diventano una faccia
            # sola: il centro può cadere fuori da tutte e due, i vertici no
            for v in bf.vertices():
                nome = _flange_face_name(bd.Vector(v), bf, ad, tipo, ordine, scatole, fid, t)
                if nome:
                    break
        if nome:
            nomi.setdefault(nome, []).append(f)
    return nomi


def _section_box(g: FlangeGeo, t: float):
    """L'ingombro della sezione della flangia (s, z), piega compresa: fuori da qui la faccia non è sua."""
    q = _section_points(g, t)
    th = math.radians(g.bend.angle)
    cs, cz = q['c']
    pts = [q[k] for k in ('os', 'oe', 'ot', 'is', 'ie', 'it')]
    for rr in (g.bend.r, g.bend.r + t):
        pts += [(cs + rr * math.sin(th * i / 8), cz - rr * math.cos(th * i / 8)) for i in range(9)]
    return (min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts))


def _flange_face_name(c, bf, ad, tipo, ordine, scatole, fid, t):
    for g in ordine:
        loc = c - g.origin
        u, s, z = loc.dot(g.xf), loc.dot(g.n), loc.dot(g.zf)
        in_u = g.u0 - TOL <= u <= g.u1 + TOL or any(a - TOL <= u <= b + TOL for a, b in g.tab_ranges)
        s0, s1, z0, z1 = scatole[g.fid]
        if not (in_u and max(g.off, s0) - TOL <= s <= s1 + TOL and z0 - TOL <= z <= z1 + TOL):
            continue
        if abs(s - g.off) < TOL and -TOL <= z <= t + TOL and tipo == GeomAbs_Plane                 and abs(abs(bf.normal_at().dot(g.n)) - 1) < 1e-6:
            continue                                   # la faccia di attacco (sparisce nella fusione)
        if tipo == GeomAbs_Cylinder:
            r = ad.Cylinder().Radius()
            if abs(r - (g.bend.r + t)) < 1e-6 and abs(abs(_axis(ad).dot(g.xf)) - 1) < 1e-6:
                return f'{fid}/{g.fid}/piega_esterna'
            if abs(r - g.bend.r) < 1e-6 and abs(abs(_axis(ad).dot(g.xf)) - 1) < 1e-6:
                return f'{fid}/{g.fid}/piega_interna'
            if g.end_tab_defs and abs(_axis(ad).dot(g.xf)) < 1e-6 and (abs(r - g.bend.r) < 1e-6 or abs(r - g.bend.r - t) < 1e-6):
                return f'{fid}/{g.fid}/chiusura'               # la piega dell'aletta che chiude la testata
            k = next((i for i, (_, _, d) in enumerate(g.holes) if abs(d / 2 - r) < 1e-6), 0)
            return f'{fid}/{g.fid}/foro{k + 1}'
        if tipo == GeomAbs_Plane:
            nv = bf.normal_at()
            dvec, nrm = g.frame()
            if abs(abs(nv.dot(g.xf)) - 1) < 1e-6:
                return f'{fid}/{g.fid}/fianco'
            if abs(abs(nv.dot(dvec)) - 1) < 1e-6:
                return f'{fid}/{g.fid}/punta'
            if abs(abs(nv.dot(nrm)) - 1) < 1e-6:
                # esterna: passa per lo spigolo vivo esterno
                sh = g.off + g.bend.ossb
                dist = abs((s - sh) * nrm.dot(g.n) + z * nrm.dot(g.zf))
                if dist < 1e-6:
                    return f'{fid}/{g.fid}/esterno'
                if abs(dist - t) < 1e-6:
                    return f'{fid}/{g.fid}/interno'
                continue                               # parallela ma fuori dallo spessore: è di un'altra parte
    return None


def _axis(ad) -> bd.Vector:
    d = ad.Cylinder().Axis().Direction()
    return bd.Vector(d.X(), d.Y(), d.Z())


__all__ = ['bend_values', 'build', 'Bend', 'SheetData', 'METODI', 'VERSI', 'POSIZIONI', 'TIP_CORNERS', 'cap']


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
    t, N = data.thickness, data.plane.z_dir
    if isinstance(piano, dict) and piano.get('flat'):
        # disegnato sullo sviluppo: ogni contorno va riportato sulla faccia dove cade, nel pezzo piegato
        if piano['flat'] != data.feature:
            raise FeatureError('Questo sketch sta sullo sviluppo di un’altra lamiera.', feature=fid)
        if fdef.get('mode') != 'add':
            return _cut_from_flat(fdef, body, data, prof.faces, t)
        lavori = [_from_flat(f, data, fid) for f in prof.faces]
    else:
        nome = piano.get('face', '') if isinstance(piano, dict) else ''
        parti = nome.split('/')
        if not parti or parti[0] != data.feature:
            raise FeatureError('Il taglio di lamiera va disegnato su una faccia della lamiera.', feature=fid)
        piani = _face_planes(parti, data, fid)
        if fdef.get('mode') != 'add':
            # il contorno portato sullo sviluppo (stesse coordinate locali): così può anche uscire dalla faccia e
            # passare la piega (uno scasso dal bordo che taglia anche il bordo piegato dopo)
            sul_piano, ritorni = [], []
            for f in prof.faces:
                src, dst, dentro, g = _pick_flange(f, piani, parti, data)
                sul_piano.append(_orienta(f.moved(dst.location * src.location.inverse()), data.plane))
                ritorni.append((src.location * dst.location.inverse(), dentro, g))
            nuovo = _cut_from_flat(fdef, body, data, sul_piano, t, ritorni)
            return _countersinks(nuovo, ss, prof, ritorni, t, fid)
        lavori = []                                                    # (sul pezzo, verso, nello sviluppo)
        ritorni = []                                                   # dallo sviluppo al pezzo
        for f in prof.faces:
            src, dst, dentro, g = _pick_flange(f, piani, parti, data)
            _check_on_face([f], src, g, data, fid)
            if fdef.get('mode') == 'add':
                f = _sotto_la_piega_in_punta(f, src, g, data)
                if f is None:
                    continue
            lavori.append((f, dentro, f.moved(dst.location * src.location.inverse())))
            ritorni.append(src.location * dst.location.inverse())

    if fdef.get('mode') == 'add':
        if piano.get('flat') if isinstance(piano, dict) else False:
            raise FeatureError('Il materiale si aggiunge disegnando su una faccia del pezzo, non sullo sviluppo.', feature=fid)
        return _add_tab(fdef, body, data, _fuori_dallo_sviluppo(lavori, ritorni, data), t)
    # 3D: attraverso lo spessore
    attrezzo = None
    for f3, dentro, _ in lavori:
        s = bd.extrude(f3.moved(bd.Location(-dentro * 0.01)), amount=t + 0.02, dir=tuple(dentro))
        attrezzo = s if attrezzo is None else attrezzo + s
    op = BRepAlgoAPI_Cut(body.shape, attrezzo.wrapped)
    if not op.IsDone():
        raise FeatureError('Il kernel non è riuscito a fare il taglio.', feature=fid)
    nuovo = body.after(op, op.Shape())
    from ..features.base import volume
    tolto = volume(body.shape) - volume(nuovo.shape)
    if tolto < 1e-6:
        raise FeatureError('Il contorno disegnato non tocca la lamiera: non toglie niente.', feature=fid)
    for f in _faces_of(nuovo.shape):
        if not nuovo.names_of(f):
            nuovo.names.setdefault(f'{fid}/parete', []).append(f)
    # sviluppo: lo stesso contorno, in piano
    flat = data.flat
    for _, _, f2 in lavori:
        flat = flat.cut(f2)
    flat = flat.clean() if hasattr(flat, 'clean') else flat
    facce = flat.faces() if not isinstance(flat, bd.Face) else [flat]
    if len(facce) != 1:
        raise FeatureError('Il taglio divide lo sviluppo in più pezzi.', feature=fid)
    # i tagli stanno solo nei tratti piani: quello che sparisce dallo sviluppo × spessore = quello che sparisce
    # dal pezzo. Se no il contorno ha preso anche altro (una piega, un'altra flangia)
    if abs((data.flat.area - facce[0].area) * t - tolto) > 1e-6 * max(tolto, 1) + 1e-3:
        raise FeatureError('Il contorno prende anche una piega o un’altra parte del pezzo: sviluppo e pezzo '
                           'piegato non tornerebbero. Tienilo dentro un solo tratto piano.', feature=fid)
    nuovo.sheet = dataclasses.replace(data, flat=facce[0], flat_area=facce[0].area, flat_size=flat_size(facce[0], data.plane))
    return nuovo


def _sotto_la_piega_in_punta(f, src, g, data):
    """Una linguetta su una parete con una flangia sulla punta prolungata sopra di lei: la parte che sale nella
    piega di quella flangia non c'è (lì c'è la piega). Si toglie la fascia oltre la fine del tratto dritto, sulla
    larghezza della flangia in punta: nelle coordinate della faccia, quindi uguale nel pezzo e nello sviluppo."""
    if g is None or not g.child:
        return f
    c = next((h for h in data.flanges if h.fid == g.child), None)
    if c is None or not any(c.pext):
        return f
    y0 = g.length - g.tip_cut
    us = [(c.p(u, 0) - g.origin).dot(g.xf) for u in (c.u0, c.u1)]     # dove arriva davvero (dopo i tagli negli angoli)
    x0, x1 = min(us + [g.u0]) - 1e-6, max(us + [g.u1]) + 1e-6
    alto = y0 + c.length + 1000
    fascia = bd.Face(bd.Wire.make_polygon([src.from_local_coords(q) for q in
                                           ((x0, y0), (x1, y0), (x1, alto), (x0, alto))], close=True))
    resto = f - fascia
    pezzi = [x for x in (resto.faces() if resto is not None and hasattr(resto, 'faces') else []) if x.area > 1e-6]
    if not pezzi:
        return None
    return max(pezzi, key=lambda x: x.area)


def _fuori_dallo_sviluppo(lavori, ritorni, data):
    """La parte della linguetta che nello sviluppo cade sopra lamiera che c'è già (di solito sotto il bordo della
    faccia, dentro la zona della piega, dove nello sviluppo c'è la striscia di un'altra parete) si toglie:
    lì la linguetta non si può fare. Resta il resto, uguale nel pezzo e nello sviluppo."""
    out = []
    for (f3, dentro, f2), ritorno in zip(lavori, ritorni):
        g = _orienta(f2, data.plane)
        resto = g - data.flat
        pezzi = [] if resto is None else [x for x in (resto.faces() if hasattr(resto, 'faces') else [resto]) if x.area > 1e-6]
        if abs(sum(x.area for x in pezzi) - g.area) < 1e-6:
            out.append((f3, dentro, f2))
            continue
        for x in pezzi:
            out.append((x.moved(ritorno), dentro, x))
    if not out:
        raise FeatureError('Il contorno sta tutto dentro la faccia: non aggiunge niente. Disegnalo fuori, attaccato al bordo.')
    return out


def _add_tab(fdef, body, data, lavori, t):
    """Linguetta: il contorno disegnato su una faccia piana della lamiera diventa materiale dello stesso spessore,
    nel piano di quella faccia (senza pieghe), attaccato al pezzo. Entra nello sviluppo nella posizione giusta.
    Controllo: area aggiunta allo sviluppo × spessore = volume aggiunto (se no tocca un'altra parte del pezzo)."""
    import dataclasses

    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse

    from ..features.base import volume
    fid = fdef['id']
    pezzo = None
    for f3, dentro, _ in lavori:
        s = bd.extrude(f3, amount=t, dir=tuple(dentro))      # nello spessore della faccia, a filo
        pezzo = s if pezzo is None else pezzo + s
    op = BRepAlgoAPI_Fuse(body.shape, pezzo.wrapped)
    if not op.IsDone():
        raise FeatureError('Il kernel non è riuscito ad aggiungere la linguetta.', feature=fid)
    nuovo = body.after(op, op.Shape())
    if len(bd.Shape.cast(nuovo.shape).solids()) != 1:
        raise FeatureError('La linguetta non tocca la lamiera: deve attaccarsi al bordo della faccia.', feature=fid)
    messo = volume(nuovo.shape) - volume(body.shape)
    if messo < 1e-6:
        raise FeatureError('Il contorno sta tutto dentro la faccia: non aggiunge niente. Disegnalo fuori, attaccato al bordo.',
                           feature=fid)
    for f in _faces_of(nuovo.shape):
        if not nuovo.names_of(f):
            nuovo.names.setdefault(f'{fid}/linguetta', []).append(f)
    nuovo = _unisci_facce(nuovo)                # la linguetta e la faccia su cui è disegnata diventano una faccia sola
    flat = data.flat
    for _, _, f2 in lavori:
        flat = flat.fuse(_orienta(f2, data.plane))         # girata come lo sviluppo, se no non si fonde
    flat = flat.clean() if hasattr(flat, 'clean') else flat
    facce = flat.faces() if not isinstance(flat, bd.Face) else [flat]
    if len(facce) != 1:
        raise FeatureError('Nello sviluppo la linguetta resta staccata o si sovrappone ad altro.', feature=fid)
    if abs((facce[0].area - data.flat.area) * t - messo) > 1e-6 * max(messo, 1) + 1e-3:
        raise FeatureError('La linguetta tocca un’altra parte del pezzo o una piega: nello sviluppo non tornerebbe. '
                           'Tienila nel piano della faccia, lontana dalle altre pareti.', feature=fid)
    nuovo.sheet = dataclasses.replace(data, flat=facce[0], flat_area=facce[0].area, flat_size=flat_size(facce[0], data.plane))
    return nuovo


class _Storico:
    """Lo storico di ShapeUpgrade_UnifySameDomain con l'interfaccia di un'operazione booleana (per i nomi)."""
    def __init__(self, h):
        self.h = h

    def IsDeleted(self, s):
        return self.h.IsRemoved(s)

    def Modified(self, s):
        return self.h.Modified(s)


def _unisci_facce(ns):
    """Fonde le facce complanari che si toccano (come fa la lamiera all'inizio), tenendo i nomi: la faccia
    unita risponde a tutti i nomi che aveva, il primo è quello più vecchio (es. la faccia della flangia)."""
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    u = ShapeUpgrade_UnifySameDomain(ns.shape, True, True, False)
    u.Build()
    nuovo = ns.after(_Storico(u.History()), u.Shape())
    nuovo.sheet = getattr(ns, 'sheet', None)
    return nuovo


def _flange_planes(g: FlangeGeo, t: float, interno: bool = False):
    """Il piano della faccia esterna (o interna) del tratto dritto e il suo corrispondente nello sviluppo:
    stesse coordinate locali, così un contorno passa dall'uno all'altro senza cambiare."""
    dvec, nrm = g.frame()
    sh = g.off + g.bend.ossb
    p0 = g.origin + g.n * sh + (nrm * t if interno else bd.Vector(0, 0, 0))
    src = bd.Plane(origin=p0, x_dir=g.xf, z_dir=g.xf.cross(dvec))
    dst = bd.Plane(origin=g.fp(0, g.off + g.bend.ba - g.bend.ossb), x_dir=g.fx, z_dir=g.fx.cross(g.fn))
    return src, dst


def _face_planes(parti, data, fid):
    t, pl, N = data.thickness, data.plane, data.plane.z_dir
    if len(parti) == 2 and parti[1] in ('sopra', 'sotto'):
        h = t if parti[1] == 'sopra' else 0.0
        src = bd.Plane(origin=pl.origin + N * h, x_dir=pl.x_dir, z_dir=N)
        return src, pl, (-N if parti[1] == 'sopra' else N), None
    if len(parti) == 3 and parti[2] in ('esterno', 'interno'):
        g = next((x for x in data.flanges if x.fid == parti[1]), None)
        if g is None:
            raise FeatureError(f'La flangia {parti[1]} non c’è più.', feature=fid)
        src, dst = _flange_planes(g, t, parti[2] == 'interno')
        nrm = g.frame()[1]                                     # dalla faccia esterna verso l'interna
        return src, dst, (nrm if parti[2] == 'esterno' else -nrm), g
    raise FeatureError('Si può tagliare sulla faccia sopra/sotto della base o sulla faccia esterna/interna '
                       'di una flangia (non sulle pieghe né sui fianchi).', feature=fid)


def _pick_flange(f, piani, parti, data):
    """Su una faccia di flangia: le flange complanari che si toccano (i bordi di una scatola) sono una faccia
    sola, con il nome di una delle due. Il contorno va alla flangia nel cui tratto dritto cade davvero."""
    src, dst, dentro, g = piani
    if g is None:
        return piani
    t = data.thickness
    pts = [p for e in f.edges() for p in e.positions([i / 16 for i in range(17)])]
    for h in [g] + [x for x in data.flanges if x is not g]:
        s_h, d_h = _flange_planes(h, t, parti[2] == 'interno')
        if abs(abs(s_h.z_dir.dot(src.z_dir)) - 1) > 1e-9 or abs((s_h.origin - src.origin).dot(src.z_dir)) > 1e-6:
            continue
        dentro_ok = True
        for p in pts:
            q = s_h.to_local_coords(p)
            in_u = h.u0 - TOL <= q.X <= h.u1 + TOL or any(a - TOL <= q.X <= b + TOL for a, b in h.tab_ranges)
            if not (in_u and h.bend.ossb - TOL <= q.Y <= h.length - h.tip_cut + TOL):
                dentro_ok = False
                break
        if dentro_ok:
            nrm = h.frame()[1]
            return s_h, d_h, (nrm if parti[2] == 'esterno' else -nrm), h
    return piani


def _check_on_face(faces, src, g, data, fid):
    """Niente tagli nelle pieghe: controllo su punti presi lungo i contorni disegnati."""
    pl, N = data.plane, data.plane.z_dir

    def proj(p):
        return p - N * N.dot(p - pl.origin)

    for f in faces:
        for e in f.edges():
            for p in e.positions([i / 16 for i in range(17)]):
                q = src.to_local_coords(p)
                if g is not None and not (g.u0 + TOL < q.X < g.u1 - TOL):
                    pass                                    # accanto alla flangia (o sul suo fianco), non sulla piega
                elif g is not None:
                    if q.Y < g.bend.ossb - TOL:
                        raise FeatureError(f'Il taglio cade nella piega della flangia {g.fid}: deve stare ad almeno '
                                           f'{fmt_mm(round(g.bend.ossb, 2))} mm dallo spigolo esterno.', feature=fid)
                    if g.child and q.Y > g.length - g.tip_cut + TOL:
                        raise FeatureError(f'Il taglio cade nella piega della flangia {g.child}, in punta a {g.fid}.',
                                           feature=fid)
                else:
                    for h_ in data.flanges:
                        if h_.parent is not None:
                            continue
                        loc = proj(p) - proj(h_.origin)
                        if loc.dot(h_.n) > h_.off + TOL and h_.u0 - TOL <= loc.dot(h_.xf) <= h_.u1 + TOL:
                            raise FeatureError(f'Il taglio cade nella piega della flangia {h_.fid}: sulla base deve '
                                               f'stare ad almeno {fmt_mm(round(-h_.off, 2))} mm dal contorno.',
                                               feature=fid)


def _facce(x) -> list:
    """Le facce (con area) di un risultato booleano 2D, qualunque forma abbia."""
    if x is None:
        return []
    fs = x.faces() if hasattr(x, 'faces') else [x]
    return [f for f in fs if f.area > 1e-6]


def _bend_rect(g: FlangeGeo):
    """La striscia della piega di g nello sviluppo."""
    b = g.bend
    return bd.Face(bd.Wire.make_polygon([g.fp(g.u0, g.off), g.fp(g.u1, g.off), g.fp(g.u1, g.off + b.ba),
                                         g.fp(g.u0, g.off + b.ba)], close=True))


def _catena(edges, passo: float):
    """I punti di un giro chiuso di lati (in ordine), fitti sulle curve."""
    pezzi = []
    for e in edges:
        n = 1 if e.geom_type == bd.GeomType.LINE else max(8, math.ceil(e.length / passo))
        pezzi.append([e.position_at(i / n) for i in range(n + 1)])
    out = list(pezzi.pop(0))
    while pezzi:
        k = min(range(len(pezzi)), key=lambda i: min((pezzi[i][0] - out[-1]).length, (pezzi[i][-1] - out[-1]).length))
        q = pezzi.pop(k)
        if (q[-1] - out[-1]).length < (q[0] - out[-1]).length:
            q = q[::-1]
        out += q[1:]
    return out[:-1] if (out[0] - out[-1]).length < 1e-6 else out


def _bend_tool(g: FlangeGeo, piece, t: float):
    """Il pezzo di contorno che nello sviluppo cade nella striscia della piega, avvolto sulla piega: un tratto di
    guscio cilindrico attraverso lo spessore. Sullo sviluppo la distanza dall'inizio della piega è misurata sulla
    fibra neutra (BA = angolo × raggio neutro), quindi l'angolo è sf / BA × angolo della piega."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.BRepLib import BRepLib
    from OCP.Geom2d import Geom2d_Line
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.gp import gp_Ax3, gp_Dir, gp_Dir2d, gp_Pnt, gp_Pnt2d
    from OCP.ShapeFix import ShapeFix_Face
    b = g.bend
    th = math.radians(b.angle)
    q = _section_points(g, t)
    cs, cz = q['c']
    C = g.p(0, cs, cz)
    D, X = g.xf.normalized(), (-g.zf).normalized()
    segno = 1.0 if D.cross(X).dot(g.n) > 0 else -1.0       # verso dell'angolo sul cilindro
    rho = b.r + t / 2
    surf = Geom_CylindricalSurface(gp_Ax3(gp_Pnt(C.X, C.Y, C.Z), gp_Dir(D.X, D.Y, D.Z), gp_Dir(X.X, X.Y, X.Z)), rho)

    def uv(p):
        u = (p - g.F0).dot(g.fx)
        sf = (p - g.F0).dot(g.fn) - g.off
        return gp_Pnt2d(segno * sf / b.ba * th, u)

    def giro(w):
        pts = [uv(p) for p in _catena(w.edges(), 0.25)]
        mw = BRepBuilderAPI_MakeWire()
        for a, c in zip(pts, pts[1:] + pts[:1]):
            if a.Distance(c) < 1e-9:
                continue
            L = a.Distance(c)
            riga = Geom2d_Line(a, gp_Dir2d(c.X() - a.X(), c.Y() - a.Y()))
            mw.Add(BRepBuilderAPI_MakeEdge(riga, surf, 0.0, L).Edge())
        return mw.Wire()

    mf = BRepBuilderAPI_MakeFace(surf, giro(piece.outer_wire()), True)
    for w in piece.inner_wires():
        mf.Add(giro(w))
    faccia = mf.Face()
    BRepLib.BuildCurves3d_s(faccia)
    fix = ShapeFix_Face(faccia)
    fix.Perform()
    return bd.thicken(bd.Face(fix.Face()), amount=t / 2 + 0.05, both=True)


def _hole_specs(ss, prof) -> list:
    """I contorni che sono un cerchio con un tipo di foro (svasato, filettato): [(indice faccia, cerchio, dati)]."""
    out = []
    for i, f in enumerate(prof.faces):
        es = f.outer_wire().edges()
        if len(es) == 1 and es[0].geom_type == bd.GeomType.CIRCLE:
            spec = ss.sketch.entities.get(prof.entity_of(es[0]) or '', {}).get('hole')
            if spec:
                out.append((i, es[0], spec))
    return out


def _countersinks(ns, ss, prof, ritorni, t, fid):
    """Le svasature (fori per viti a testa piana): un cono coassiale al foro, che si apre sulla faccia dove si è
    disegnato. Sono una lavorazione: lo sviluppo resta quello del foro dritto."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    for i, cerchio, spec in _hole_specs(ss, prof):
        if spec.get('tipo') != 'svasato':
            continue
        d, D = 2 * cerchio.radius, float(spec.get('D', 0))
        ang = math.radians(float(spec.get('angolo', 90)))
        if D <= d:
            raise FeatureError(f'La svasatura (Ø{fmt_mm(D)}) deve essere più larga del foro (Ø{fmt_mm(d)}).', feature=fid)
        h = (D - d) / 2 / math.tan(ang / 2)
        if h > t + 1e-6:
            raise FeatureError(f'La svasatura Ø{fmt_mm(D)} a {fmt_mm(math.degrees(ang))}° è profonda {fmt_mm(round(h, 2))} mm: più '
                               f'dello spessore ({fmt_mm(t)}). Riduci il diametro della svasatura.', feature=fid)
        asse = bd.Vector(*ritorni[i][1]).normalized()
        c = cerchio.arc_center
        e = 0.05
        cono = bd.Solid.make_cone(D / 2 + e * math.tan(ang / 2), d / 2, h + e,
                                  plane=bd.Plane(origin=c - asse * e, z_dir=asse))
        op = BRepAlgoAPI_Cut(ns.shape, cono.wrapped)
        if not op.IsDone():
            raise FeatureError('Il kernel non è riuscito a fare la svasatura.', feature=fid)
        sheet = ns.sheet
        ns = ns.after(op, op.Shape())
        ns.sheet = sheet
        for f in _faces_of(ns.shape):
            if not ns.names_of(f):
                ns.names.setdefault(f'{fid}/svasatura', []).append(f)
    return ns


def _in_striscia(x, g: FlangeGeo, data) -> bool:
    """Il pezzo (nello sviluppo) sta tutto, dove c'è lamiera, nel tratto dritto della flangia g?"""
    s1 = g.off + g.bend.ba
    s2 = s1 + g.lf
    # uscita rapida: gli spigoli dell'ingombro contengono il pezzo; se in (u, s) cadono tutti fuori dal tratto
    # dritto, nessun punto del pezzo ci sta e la risposta è no (qualunque punto nello sviluppo direbbe no)
    bb = x.bounding_box()
    us = [((q - g.F0).dot(g.fx), (q - g.F0).dot(g.fn)) for q in
          (bd.Vector(cx, cy, cz) for cx in (bb.min.X, bb.max.X) for cy in (bb.min.Y, bb.max.Y) for cz in (bb.min.Z, bb.max.Z))]
    if (max(u for u, _ in us) < g.u0 - TOL or min(u for u, _ in us) > g.u1 + TOL
            or max(v for _, v in us) < s1 - TOL or min(v for _, v in us) > s2 + TOL):
        return False
    dentro = False
    for e in x.edges():
        for p in e.positions([i / 8 for i in range(9)]):
            # prima il conto facile; "sta nello sviluppo?" (lento) solo quando cambia la risposta
            u, s = (p - g.F0).dot(g.fx), (p - g.F0).dot(g.fn)
            if not (g.u0 - TOL <= u <= g.u1 + TOL and s1 - TOL <= s <= s2 + TOL):
                if data.flat.is_inside(p):
                    return False
            elif not dentro and data.flat.is_inside(p):
                dentro = True
    return dentro


def _cut_from_flat(fdef, body, data, contorni, t, ritorni=None):
    """Un taglio disegnato sullo sviluppo, anche attraverso le pieghe: i pezzi nei tratti piani vanno al loro posto
    nel pezzo piegato, quelli nelle strisce di piega si avvolgono sulla piega. Lo sviluppo perde il contorno intero."""
    import dataclasses

    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut

    from ..features.base import volume
    fid = fdef['id']
    attrezzi, atteso = [], 0.0
    strisce = [(g, _bend_rect(g)) for g in data.flanges]
    strisce = [(g, r, r.bounding_box()) for g, r in strisce]
    for i, f in enumerate(contorni):
        resto = [f]
        bf = f.bounding_box()
        for g, rett, br in strisce:
            # contorno lontano dalla piega (il caso di quasi tutte le asole di una serie): niente booleane
            if (bf.max.X < br.min.X - TOL or br.max.X < bf.min.X - TOL or bf.max.Y < br.min.Y - TOL
                    or br.max.Y < bf.min.Y - TOL or bf.max.Z < br.min.Z - TOL or br.max.Z < bf.min.Z - TOL):
                continue
            for x in _facce(f & rett):
                dentro = sum(y.area for y in _facce(x & data.flat))
                if dentro < 1e-6:
                    continue
                attrezzi.append(_bend_tool(g, x, t))
                atteso += dentro * t * (g.bend.r + t / 2) / (g.bend.ba / math.radians(g.bend.angle))
            resto = [y for z in resto for y in _facce(z - rett)]
        # solo dove c'è lamiera: la parte fuori dallo sviluppo, portata nel pezzo piegato, taglierebbe altro
        resto = [y for x in resto for y in _facce(x & data.flat)]
        for x in resto:
            dentro = x.area
            if ritorni:
                # disegnato su una faccia: il pezzo torna sulla faccia da cui viene, a meno che stia tutto nel
                # tratto dritto di un'altra flangia (è uscito dalla faccia e ha passato una piega)
                altra = next((h for h in data.flanges if h is not ritorni[i][2] and _in_striscia(x, h, data)), None)
                if altra is None:
                    f3, verso = x.moved(ritorni[i][0]), ritorni[i][1]
                else:
                    src, dst = _flange_planes(altra, t)
                    f3, verso = x.moved(src.location * dst.location.inverse()), altra.frame()[1]
            else:
                f3, verso, _ = _from_flat(x, data, fid)
            attrezzi.append(bd.extrude(f3, amount=t + 0.02, dir=tuple(verso)))   # dalla faccia: sopra può appoggiare altro
            atteso += dentro * t
    if not attrezzi:
        raise FeatureError('Il contorno disegnato è fuori dallo sviluppo: non toglie niente.', feature=fid)
    from OCP.collections import List_TopoDS_Shape
    argomenti, utensili = List_TopoDS_Shape(), List_TopoDS_Shape()
    argomenti.Append(body.shape)
    for a in attrezzi:
        for so in (a.solids() if hasattr(a, 'solids') else [a]):
            utensili.Append(so.wrapped)
    op = BRepAlgoAPI_Cut()
    op.SetArguments(argomenti)
    op.SetTools(utensili)
    op.Build()
    if not op.IsDone():
        raise FeatureError('Il kernel non è riuscito a fare il taglio.', feature=fid)
    nuovo = body.after(op, op.Shape())
    tolto = volume(body.shape) - volume(nuovo.shape)
    if tolto < 1e-6:
        raise FeatureError('Il contorno disegnato non tocca la lamiera: non toglie niente.', feature=fid)
    for f in _faces_of(nuovo.shape):
        if not nuovo.names_of(f):
            nuovo.names.setdefault(f'{fid}/parete', []).append(f)
    flat = data.flat.cut(*contorni)                       # tutti i contorni in un colpo solo
    flat = flat.clean() if hasattr(flat, 'clean') else flat
    facce = flat.faces() if not isinstance(flat, bd.Face) else [flat]
    if len(facce) != 1:
        raise FeatureError('Il taglio divide lo sviluppo in più pezzi.', feature=fid)
    # controllo: nei tratti piani area × spessore; nelle pieghe la lamiera è più lunga dentro e più corta fuori
    # della fibra neutra, quindi area × spessore × (raggio medio / raggio neutro)
    if abs(tolto - atteso) > 2e-3 * max(atteso, 1) + 1e-3:
        raise FeatureError('Il taglio nel pezzo piegato non corrisponde allo sviluppo (tocca un’altra parte del '
                           'pezzo?): non lo applico.', feature=fid)
    nuovo.sheet = dataclasses.replace(data, flat=facce[0], flat_area=facce[0].area, flat_size=flat_size(facce[0], data.plane))
    return nuovo


def _from_flat(f, data, fid):
    """Un contorno disegnato sullo sviluppo: in quale tratto piano cade (la base o una flangia) e dove va
    nel pezzo piegato. Un contorno che tocca una piega, o che passa da un tratto all'altro, è rifiutato."""
    t, N = data.thickness, data.plane.z_dir
    possibili = None
    for e in f.edges():
        for p in e.positions([i / 16 for i in range(17)]):
            if not data.flat.is_inside(p):
                continue                       # fuori dal pezzo (o in un foro): va bene per qualsiasi tratto
            qui, in_striscia = set(), False
            for g in data.flanges:
                u, s = (p - g.F0).dot(g.fx), (p - g.F0).dot(g.fn)
                in_piega = g.u0 - TOL <= u <= g.u1 + TOL
                in_dritto = in_piega or any(a - TOL <= u <= b + TOL for a, b in g.tab_ranges)
                s0, s1 = g.off, g.off + g.bend.ba
                s2 = s1 + g.lf
                if in_piega and s0 + TOL < s < s1 - TOL:
                    raise FeatureError(f'Il contorno cade nella piega della flangia {g.fid}: sullo sviluppo deve '
                                       'stare fuori dalla striscia della piega.', feature=fid)
                if in_dritto and s1 - TOL <= s <= s2 + TOL:
                    qui.add(g.fid)
                    in_striscia = in_striscia or s > s0 + TOL
            if not in_striscia:
                qui.add(None)                   # la base
            possibili = qui if possibili is None else possibili & qui
            if not possibili:
                raise FeatureError('Il contorno passa da un tratto piano a un altro attraverso una piega: '
                                   'disegnalo dentro un solo tratto (la base o una flangia).', feature=fid)
    if possibili is None:
        raise FeatureError('Il contorno disegnato è fuori dallo sviluppo: non toglie niente.', feature=fid)
    if None in possibili:
        return f, N, f                          # lo sviluppo sta sul piano della faccia di sotto della base
    g = next(x for x in data.flanges if x.fid == sorted(possibili)[0])
    src, dst = _flange_planes(g, t)
    return f.moved(src.location * dst.location.inverse()), g.frame()[1], f
