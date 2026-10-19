"""Strutture: uno scheletro di linee che diventa tubolari e profilati veri, con i giunti.

Definizione (feature "structure"):

    {"id": "ST1", "type": "structure", "name": "Telaio tavolo",
     "points": {"A": [0, 0, "altezza"], "B": ["larghezza", 0, "altezza"], ...},
     "members": [
        {"id": "M1", "group": "Telaio superiore", "from": "A", "to": "B",
         "profile": "40x40x3", "material": "S235",
         "rotate": 0, "flip": false, "anchor": "center", "offset": [0, 0]}
     ],
     "joints": {"A": {"type": "miter"}, "C": {"type": "butt", "through": ["M2"]}}}

Giunti, se non si dice niente ("auto"):
- due aste che finiscono nello stesso nodo: taglio a 45° (in generale sulla bisettrice);
- tre o più: quelle più verticali vanno "a battuta" contro le altre (le gambe
  sotto il telaio), le ultime due si tagliano sulla bisettrice;
- un'asta che finisce a metà di un'altra: a battuta contro quella (giunto a T);
- un'estremità libera: taglio dritto.
Giunti a mano: "miter" (bisettrice), "butt" (a battuta: "through" dice quali
aste passano), "square" (taglio dritto sul nodo), "angle" con "angle": gradi.

Ogni asta è un solido BREP vero: sezione del profilo estrusa e tagliata con
piani o con la sagoma piena delle aste contro cui batte.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import build123d as bd

from .. import materials
from ..errors import FeatureError
from ..expressions import evaluate
from ..profiles import Profile, outer_envelope, parse
from ..units import cap, fmt_mm

ANCHORS = {'center': (0, 0), 'top': (0, 1), 'bottom': (0, -1), 'left': (-1, 0), 'right': (1, 0),
           'top-left': (-1, 1), 'top-right': (1, 1), 'bottom-left': (-1, -1), 'bottom-right': (1, -1)}


@dataclass
class Member:
    id: str
    group: str
    profile: Profile
    material: str
    start: bd.Vector
    end: bd.Vector
    x: bd.Vector            # asse X della sezione (larghezza) nello spazio
    y: bd.Vector            # asse Y della sezione (altezza)
    origin_shift: bd.Vector  # spostamento dell'asse dovuto ad ancoraggio e offset
    solid: bd.Solid | None = None
    cuts: tuple = (0.0, 0.0)    # angolo di taglio all'inizio e alla fine (0 = dritto)
    length: float = 0.0         # lunghezza di taglio (massimo ingombro lungo l'asse)

    @property
    def w(self) -> bd.Vector:
        return (self.end - self.start).normalized()

    @property
    def axis_length(self) -> float:
        return (self.end - self.start).length

    def kg(self) -> float:
        return self.profile.kg_m(materials.get(self.material).density_g_cm3) * self.length / 1000.0

    def label(self) -> str:
        return f'{self.group or "asta"} {self.id} ({self.profile.name})'


@dataclass
class StructureResult:
    id: str
    name: str
    members: list            # Member
    warnings: list = None    # frasi per l'utente (aste che si compenetrano, …)
    nodes: dict = None       # {punto: {'xyz', 'members', 'joint', 'auto'}} per l'interfaccia

    def compound(self) -> bd.Compound:
        return bd.Compound([m.solid for m in self.members])


def _vec(v, params, what) -> bd.Vector:
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        raise FeatureError(f'{cap(what)} deve avere tre coordinate (x, y, z).')
    return bd.Vector(*(evaluate(c, params, what=what) for c in v))


def _skeletons(fdef, params, sketches, pts, nome, fid) -> list:
    righe = []
    for sk_def in fdef.get('skeletons') or []:
        kid, sid = sk_def.get('id', 'K'), sk_def.get('sketch')
        if not sketches or sid not in sketches:
            raise FeatureError(f'Lo scheletro {kid} di "{nome}" usa lo sketch {sid}, che non esiste o ha un errore.',
                               feature=fid)
        solved, prof = sketches[sid]
        ents = solved.sketch.entities
        linee = {lid: ab for lid, ab in solved.lines.items() if not ents.get(lid, {}).get('construction')}
        if not linee:
            raise FeatureError(f'Lo sketch {sid} non ha linee: disegna lo scheletro (le linee di costruzione non '
                               'diventano aste).', feature=fid)
        copie = sk_def.get('copies') or [[0, 0, 0]]
        # punti nello stesso posto (disegnati due volte senza aggancio) sono lo stesso nodo
        uguale = {}
        for p in sorted({p for ab in linee.values() for p in ab}):
            x, y = solved.points[p]
            chiave = (round(x, 4), round(y, 4))
            uguale.setdefault(chiave, p)
        canon = {p: uguale[(round(solved.points[p][0], 4), round(solved.points[p][1], 4))]
                 for ab in linee.values() for p in ab}
        linee = {lid: (canon[a], canon[b]) for lid, (a, b) in linee.items() if canon[a] != canon[b]}
        doppie, viste = [], set()
        for lid, (a, b) in list(linee.items()):
            if frozenset((a, b)) in viste:
                doppie.append(lid)
                del linee[lid]
            viste.add(frozenset((a, b)))
        usati = sorted({p for ab in linee.values() for p in ab})
        for k, off in enumerate(copie, start=1):
            d = _vec(off, params, f'lo spostamento della ripetizione {k} di {kid}')
            for p in usati:
                pts[f'{kid}.{k}.{p}'] = prof.plane.from_local_coords(solved.points[p]) + d
            for lid, (a, b) in linee.items():
                righe.append({'id': f'{kid}.{k}.{lid}', 'from': f'{kid}.{k}.{a}', 'to': f'{kid}.{k}.{b}',
                              'profile': sk_def.get('profile'), 'group': sk_def.get('group', ''),
                              **({'material': sk_def['material']} if sk_def.get('material') else {})})
        con = sk_def.get('connect')
        if con and len(copie) > 1:
            quali = usati if con.get('points', 'all') == 'all' else [p for p in con['points'] if p in usati]
            for k in range(1, len(copie)):
                for p in quali:
                    righe.append({'id': f'{kid}.{k}-{k + 1}.{p}', 'from': f'{kid}.{k}.{p}', 'to': f'{kid}.{k + 1}.{p}',
                                  'profile': con.get('profile') or sk_def.get('profile'),
                                  'group': con.get('group', 'Collegamenti')})
    for m in fdef.get('members') or []:
        if 'line' in m and 'sketch' in m:
            sid, lid = m['sketch'], m['line']
            if not sketches or sid not in sketches or lid not in sketches[sid][0].lines:
                raise FeatureError(f"L'asta {m.get('id')} di \"{nome}\" usa la linea {lid} dello sketch {sid}, che non esiste.",
                                   feature=fid)
            a, b = sketches[sid][0].lines[lid]
            for q in (a, b):
                pts.setdefault(f'{sid}.{q}', _point(q, {'sketch': sid, 'point': q}, params, sketches, nome, fid))
            m = {**m, 'from': f'{sid}.{a}', 'to': f'{sid}.{b}'}
        righe.append(m)
    return righe


def _point(k, v, params, sketches, nome, fid, _resolve=None) -> bd.Vector:
    """Un punto dello scheletro: [x, y, z], un punto di uno sketch, oppure un altro punto
    dello scheletro ("from"); negli ultimi due casi con uno spostamento [dx, dy, dz]."""
    if isinstance(v, dict) and 'from' in v:
        base = _resolve(v['from'])
        if v.get('offset'):
            base = base + _vec(v['offset'], params, f'lo spostamento del punto {k}')
        return base
    if isinstance(v, dict) and 'sketch' in v:
        sid = v['sketch']
        if not sketches or sid not in sketches:
            raise FeatureError(f'Il punto {k} di "{nome}" usa lo sketch {sid}, che non esiste o ha un errore.',
                               feature=fid)
        solved, prof = sketches[sid]
        pid = v.get('point')
        if pid not in solved.points:
            raise FeatureError(f'Il punto {k} di "{nome}" usa il punto {pid} dello sketch {sid}, che non esiste più.',
                               feature=fid)
        base = prof.plane.from_local_coords(solved.points[pid])
        if v.get('offset'):
            base = base + _vec(v['offset'], params, f'lo spostamento del punto {k}')
        return base
    return _vec(v, params, f'il punto {k} di "{nome}"')


def build(fdef: dict, params: dict, sketches: dict | None = None) -> StructureResult:
    fid = fdef['id']
    nome = fdef.get('name') or fid
    defs = fdef.get('points') or {}
    pts: dict = {}
    in_corso: list = []

    def _resolve(k):
        if k in pts:
            return pts[k]
        if k not in defs:
            raise FeatureError(f'Il punto {in_corso[-1] if in_corso else k} di "{nome}" parte dal punto {k}, '
                               'che non esiste.', feature=fid)
        if k in in_corso:
            giro = ' → '.join(in_corso[in_corso.index(k):] + [k])
            raise FeatureError(f'I punti di "{nome}" dipendono uno dall’altro in cerchio: {giro}.', feature=fid)
        in_corso.append(k)
        pts[k] = _point(k, defs[k], params, sketches, nome, fid, _resolve)
        in_corso.pop()
        return pts[k]

    # scheletri: tutte le linee (non di costruzione) di uno sketch diventano aste, anche ripetute a distanza
    # (la seconda spalla di uno scaffale) e collegate nodo per nodo. Cambi lo sketch, cambia la struttura.
    # Vengono prima dei punti a mano: un nodo aggiunto dopo può partire da un nodo dello scheletro.
    righe = _skeletons(fdef, params, sketches, pts, nome, fid)
    for k in defs:
        _resolve(k)
    # eccezioni per singola asta (profilo, rotazione, gruppo, tolta): restano anche se lo sketch cambia
    ritocchi = fdef.get('overrides') or {}
    righe = [{**m, **{k: v for k, v in ritocchi.get(m['id'], {}).items() if k != 'deleted'}}
             for m in righe if not ritocchi.get(m['id'], {}).get('deleted')]
    members = []
    for m in righe:
        mid = m.get('id')
        if m.get('from') not in pts or m.get('to') not in pts:
            raise FeatureError(f'L\'asta {mid} di "{nome}" usa un punto che non esiste.', feature=fid)
        a, b = pts[m['from']], pts[m['to']]
        if (b - a).length < 1e-6:
            raise FeatureError(f'L\'asta {mid} di "{nome}" ha lunghezza zero: i suoi punti coincidono.', feature=fid)
        prof = parse(m.get('profile') or '')
        mat = m.get('material', fdef.get('material', 'S235'))
        materials.get(mat)
        x, y = _section_axes((b - a).normalized(), m.get('rotate', 0), m.get('flip', False))
        anc = m.get('anchor', 'center')
        if anc not in ANCHORS:
            raise FeatureError(f'Ancoraggio "{anc}" sconosciuto per l\'asta {mid}: usa centro, sopra, sotto, '
                               'sinistra, destra o gli angoli.', feature=fid)
        ax, ay = ANCHORS[anc]
        ox, oy = (evaluate(v, params, what=f'offset dell\'asta {mid}') for v in (m.get('offset') or [0, 0]))
        shift = x * (-ax * prof.width / 2 + ox) + y * (-ay * prof.height / 2 + oy)
        members.append(Member(mid, m.get('group', ''), prof, mat, a, b, x, y, shift))
    if not members:       # si parte da un nodo e si costruisce: nessuna asta va bene
        return StructureResult(fid, nome, [], [], _node_info(pts, [], {}, fdef))
    ids = [m.id for m in members]
    if len(set(ids)) != len(ids):
        raise FeatureError(f'Nella struttura "{nome}" due aste hanno lo stesso nome.', feature=fid)

    by_id = {m.id: m for m in members}
    nodes = _nodes(members, pts, fdef.get('joints') or {}, by_id, fid)
    for m in members:
        key = _member_key(m, nodes)
        hit = _CACHE.get(key)
        if hit is None:
            solid, cuts = _member_solid(m, nodes, by_id, fid)
            m.solid, m.cuts = solid, cuts
            hit = (solid, cuts, _extent(m))
            if len(_CACHE) > 2000:
                _CACHE.clear()
            _CACHE[key] = hit
        m.solid, m.cuts, m.length = hit
    legati = set()
    for (mid, _), (kind, _, info) in nodes.items():
        altri = [info[0]] if kind == 'miter' else ([o for o, _ in info] if kind == 'extend' else
                                                  (info if kind == 'butt' else []))
        for o in altri:
            legati.add(frozenset((mid, o.id)))
    chiavi = {m.id: _member_key(m, nodes) for m in members}
    return StructureResult(fid, nome, members, _interferences(members, legati, chiavi),
                           _node_info(pts, members, nodes, fdef))


JOINT_LABELS = {'auto': 'automatico', 'miter': 'a 45° (bisettrice)', 'butt': 'a battuta', 'extend': 'passante',
                'square': 'taglio dritto', 'angle': 'ad angolo'}


def _node_info(pts, members, nodes, fdef) -> dict:
    joints = fdef.get('joints') or {}
    out = {}
    for k, p in pts.items():
        if '.' in k and k not in (fdef.get('points') or {}):
            continue                          # punti interni presi dalle linee di uno sketch
        su = [m.id for m in members if (m.start - p).length < 1e-6 or (m.end - p).length < 1e-6]
        tipi = sorted({nodes[(m.id, i)][0] for m in members for i, q in ((0, m.start), (1, m.end))
                       if (q - p).length < 1e-6 and (m.id, i) in nodes})
        out[k] = {'xyz': [p.X, p.Y, p.Z], 'members': su, 'joint': dict(joints.get(k) or {'type': 'auto'}),
                  'auto': ' + '.join(JOINT_LABELS.get(t, t) for t in tipi)}
    return out


_CACHE: dict = {}
STATS = {'members_built': 0}


def _sig(m: Member) -> tuple:
    r = lambda v: (round(v.X, 9), round(v.Y, 9), round(v.Z, 9))  # noqa: E731
    return (m.profile.family, m.profile.dims, r(m.start), r(m.end), r(m.x), r(m.y), r(m.origin_shift))


def _nsig(o: Member, node: bd.Vector) -> tuple:
    """Di un'asta vicina conta solo come passa dal nodo (profilo, direzione, assi, retta), non dove finisce:
    allungare una traversa non deve ricostruire le gambe dall'altra parte."""
    r = lambda v: (round(v.X, 9), round(v.Y, 9), round(v.Z, 9))  # noqa: E731
    w = o.w
    base = o.start + w * (node - o.start).dot(w)          # punto della retta più vicino al nodo
    return (o.profile.family, o.profile.dims, r(w), r(o.x), r(o.y), r(o.origin_shift), r(base))


def _member_key(m: Member, nodes) -> tuple:
    """La geometria di un'asta dipende da lei e da come le aste vicine passano dai suoi due estremi."""
    parti = [_sig(m)]
    for i in (0, 1):
        kind, node, info = nodes[(m.id, i)]
        if kind == 'miter':
            o, j = info
            uo = o.w if j == 0 else -o.w
            altri = (_nsig(o, node), (round(uo.X, 9), round(uo.Y, 9), round(uo.Z, 9)))
        elif kind in ('butt',):
            altri = tuple(_nsig(o, node) for o in info)
        elif kind == 'extend':
            altri = tuple(_nsig(o, node) for o, _ in info)
        else:
            altri = tuple(info) if isinstance(info, list) else info
        parti.append((kind, (round(node.X, 9), round(node.Y, 9), round(node.Z, 9)), altri))
    return tuple(parti)


def _section_axes(w: bd.Vector, rotate_deg: float, flip: bool):
    """Altezza del profilo verso l'alto (Z) per le aste orizzontali; per quelle verticali verso Y."""
    up = bd.Vector(0, 0, 1)
    if abs(w.dot(up)) > 0.999:
        up = bd.Vector(0, 1, 0)
    y = (up - w * w.dot(up)).normalized()
    x = y.cross(w).normalized()
    if rotate_deg:
        a = math.radians(rotate_deg)
        x, y = x * math.cos(a) + y * math.sin(a), y * math.cos(a) - x * math.sin(a)
    if flip:
        x = -x
    return x, y


def _nodes(members, pts, joints, by_id, fid):
    """Per ogni estremità di ogni asta: che taglio fare. Ritorna {(id asta, 0|1): istruzione}."""
    ends = {}
    for k, p in pts.items():
        ends[k] = [(m, i) for m in members for i, q in ((0, m.start), (1, m.end)) if (q - p).length < 1e-6]
    out = {}
    for k, lst in ends.items():
        if not lst:
            continue
        spec = dict(joints.get(k) or {})
        tipo = spec.get('type', 'auto')
        node = pts[k]
        if tipo == 'square':
            for m, i in lst:
                out[(m.id, i)] = ('square', node, [])
            continue
        if tipo == 'angle':
            ang = float(spec.get('angle', 0))
            for m, i in lst:
                out[(m.id, i)] = ('angle', node, ang)
            continue
        if tipo == 'butt':
            through = [by_id[t] for t in spec.get('through', []) if t in by_id]
            if not through:
                raise FeatureError(f'Il giunto a battuta nel nodo {k} deve dire quali aste passano.', feature=fid)
            for m, i in lst:
                if m in through:
                    out[(m.id, i)] = ('extend', node, [x for x in lst if x[0] not in through])
                else:
                    out[(m.id, i)] = ('butt', node, through)
            continue
        if tipo == 'miter' and len(lst) != 2:
            raise FeatureError(f'Il taglio a 45° nel nodo {k} vale per due aste, qui ce ne sono {len(lst)}.',
                               feature=fid)
        # automatico
        finiscono_qui = [m for m, _ in lst]
        passanti = [o for o in _lies_on(node, members, None) if o not in finiscono_qui]
        if passanti:
            # il nodo sta a metà di un'altra asta: tutte le aste che arrivano qui le battono contro
            for m, i in lst:
                out[(m.id, i)] = ('butt', node, passanti)
            continue
        resto = sorted(lst, key=lambda e: (-abs(e[0].w.dot(bd.Vector(0, 0, 1))), e[0].id))
        batte = []
        while len(resto) > 2:
            batte.append(resto.pop(0))
        if len(resto) == 2:
            (a, ia), (b, ib) = resto
            out[(a.id, ia)] = ('miter', node, (b, ib))
            out[(b.id, ib)] = ('miter', node, (a, ia))
        else:
            m, i = resto[0]
            interno = _lies_on(node, members, m)
            if interno:
                out[(m.id, i)] = ('butt', node, interno)
            else:
                out[(m.id, i)] = ('square', node, [])
        for m, i in batte:
            out[(m.id, i)] = ('butt', node, [x[0] for x in resto])
    # estremità senza un punto in comune con altre aste ma appoggiate a metà di un'asta
    for m in members:
        for i in (0, 1):
            if (m.id, i) not in out:
                p = m.start if i == 0 else m.end
                interno = _lies_on(p, members, m)
                out[(m.id, i)] = ('butt', p, interno) if interno else ('square', p, [])
    return out


def _lies_on(p, members, skip):
    """Aste su cui il punto p cade a metà (non agli estremi): giunto a T."""
    res = []
    for o in members:
        if o is skip:
            continue
        w = o.end - o.start
        t = (p - o.start).dot(w) / w.length ** 2
        if 1e-6 < t < 1 - 1e-6 and (o.start + w * t - p).length < 1e-6:
            res.append(o)
    return res


def _cut_keep(solid, origin, normal):
    """Tiene la parte di solido dal lato verso cui punta la normale."""
    res = solid.split(bd.Plane(origin=origin, z_dir=normal), keep=bd.Keep.TOP)
    if isinstance(res, list):
        res = max(res, key=lambda s: s.volume) if res else None
    if res is None or res.volume < 1e-9:
        return None
    return res if isinstance(res, bd.Solid) else (res.solids()[0] if res.solids() else None)


def _member_solid(m: Member, nodes, by_id, fid):
    STATS['members_built'] += 1
    prof = m.profile
    ext = max(prof.width, prof.height) * 3 + 20
    w = m.w
    start = m.start + m.origin_shift - w * ext
    plane = bd.Plane(origin=start, x_dir=m.x, z_dir=w)
    solid = bd.extrude(plane.location * prof.section(), amount=m.axis_length + 2 * ext)
    if isinstance(solid, bd.Compound):
        solid = solid.solids()[0]
    angoli = []
    for i in (0, 1):
        kind, node, info = nodes[(m.id, i)]
        u = w if i == 0 else -w          # verso dall'estremità dentro l'asta
        p_end = node + m.origin_shift
        if kind == 'square':
            solid = _cut_keep(solid, p_end, u)
            angoli.append(0.0)
        elif kind == 'angle':
            a = math.radians(info)
            n = (u * math.cos(a) + m.x * math.sin(a)).normalized()
            solid = _cut_keep(solid, p_end, n)
            angoli.append(abs(info))
        elif kind == 'miter':
            other, j = info
            uo = other.w if j == 0 else -other.w
            n = u - uo
            if n.length < 1e-9:
                n = u
            n = n.normalized()
            solid = _cut_keep(solid, node, n)
            angoli.append(round(math.degrees(math.acos(min(1.0, abs(n.dot(w))))), 6))
        elif kind == 'butt':
            solid = _cut_keep(solid, p_end, u)
            angolo = 0.0
            for o in info:
                if solid is None:
                    break
                if o.profile.family == 'CHS':
                    # contro un tubo tondo: taglio a sella (si toglie la sagoma del tubo)
                    cut = solid.cut(_envelope_solid(o))
                    pezzi = cut.solids() if hasattr(cut, 'solids') else [cut]
                    if not pezzi:
                        raise FeatureError(f"L'asta {m.id} sparisce dentro {o.id}: controlla i punti.", feature=fid)
                    mid = m.start + m.origin_shift + w * (m.axis_length / 2)
                    solid = min(pezzi, key=lambda s: (s.center() - mid).length)
                else:
                    # contro tubolari e profilati: taglio piano sulla faccia rivolta verso l'asta
                    q, n = _facing_plane(o, node, u)
                    solid = _cut_keep(solid, q, n)
                    angolo = max(angolo, round(math.degrees(math.acos(min(1.0, abs(n.dot(w))))), 6))
            angoli.append(angolo)
        elif kind == 'extend':
            extra = 0.0
            for o, _ in info:
                extra = max(extra, abs(o.x.dot(w)) * o.profile.width / 2 + abs(o.y.dot(w)) * o.profile.height / 2)
            solid = _cut_keep(solid, p_end - u * extra, u)
            angoli.append(0.0)
        if solid is None:
            raise FeatureError(f'L\'asta {m.id} si annulla con i tagli alle estremità: è più corta dei profili che '
                               'la tagliano.', feature=fid)
    return solid, tuple(angoli)


def _facing_plane(o: Member, node: bd.Vector, u: bd.Vector):
    """La faccia dell'asta passante o rivolta verso l'asta che le batte contro (u: verso quell'asta)."""
    asse_o = o.start + o.origin_shift
    centro = asse_o + o.w * (node - asse_o).dot(o.w)       # punto dell'asse passante più vicino al nodo
    candidati = [(o.x, o.profile.width / 2), (-o.x, o.profile.width / 2),
                 (o.y, o.profile.height / 2), (-o.y, o.profile.height / 2)]
    asse, meta = max(candidati, key=lambda c: c[0].dot(u))
    return centro + asse * meta, asse


def _envelope_solid(o: Member) -> bd.Solid:
    ext = max(o.profile.width, o.profile.height) * 3 + 20
    w = o.w
    plane = bd.Plane(origin=o.start + o.origin_shift - w * ext, x_dir=o.x, z_dir=w)
    s = bd.extrude(plane.location * outer_envelope(o.profile), amount=o.axis_length + 2 * ext)
    return s if isinstance(s, bd.Solid) else s.solids()[0]


def _extent(m: Member) -> float:
    """Lunghezza di taglio: l'ingombro esatto dell'asta lungo il suo asse (punte dei 45° comprese)."""
    from ..features.measure_util import bbox
    local = bd.Plane(origin=m.start, x_dir=m.x, z_dir=m.w).to_local_coords(m.solid)
    (_, _, z0), (_, _, z1) = bbox(local.wrapped)
    return z1 - z0


def describe_cut(angle: float) -> str:
    return 'dritto' if abs(angle) < 1e-6 else f'{fmt_mm(round(angle, 1))}°'


_COMUNE: dict = {}


def _interferences(members, legati=frozenset(), chiavi=None) -> list[str]:
    """Aste che si compenetrano (materiale in comune): di solito manca un giunto.
    Le coppie unite da un giunto non si controllano (il giunto le separa già)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from ..features.measure_util import bbox
    from ..features.base import volume
    avvisi = []
    boxes = [bbox(m.solid.wrapped) for m in members]
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            if frozenset((members[i].id, members[j].id)) in legati:
                continue
            (a0, a1), (b0, b1) = boxes[i], boxes[j]
            if any(a1[k] < b0[k] - 1e-6 or b1[k] < a0[k] - 1e-6 for k in range(3)):
                continue
            key = (chiavi[members[i].id], chiavi[members[j].id]) if chiavi else None
            v = _COMUNE.get(key) if key else None
            if v is None:
                op = BRepAlgoAPI_Common(members[i].solid.wrapped, members[j].solid.wrapped)
                op.Build()
                v = volume(op.Shape()) if op.IsDone() else 0.0
                if key:
                    if len(_COMUNE) > 5000:
                        _COMUNE.clear()
                    _COMUNE[key] = v
            if v > 1.0:
                avvisi.append(f"Le aste {members[i].id} e {members[j].id} si compenetrano ({fmt_mm(round(v))} mm³ "
                              "in comune): aggiungi un giunto o sposta un punto.")
    return avvisi
