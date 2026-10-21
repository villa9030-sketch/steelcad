"""Assiemi: più pezzi SteelCAD messi insieme.

Un file `.steelcad-asm` richiama i file dei pezzi (`.steelcad`, percorsi relativi all'assieme) e dice dove sta
ogni copia (istanza): una rotazione R e una traslazione T (punto nel mondo = R · punto del pezzo + T). Se un pezzo
cambia, l'assieme lo rilegge (dalla data del file).

Accoppiamenti (come in officina):
- **faccia su faccia**: due facce piane una contro l'altra (normali opposte), con una distanza;
- **foro su foro** (coassiale): gli assi di due fori (o due facce cilindriche) sulla stessa linea;
- **distanza**: due facce piane parallele a una distanza;
- **parallele**, **perpendicolari**, **angolo**: solo l'orientamento di due facce (o assi);
- **tangente**: un tubo appoggiato su una faccia, o due tubi uno contro l'altro;
- **in mezzo**: due facce di un pezzo centrate tra due facce dell'altro (un piatto in un U);
- **blocca**: il pezzo resta attaccato all'altro così com'è.

Il risolutore muove ogni istanza (tranne quella ferma) partendo da dov'è: un punto di partenza a formula (le
direzioni delle facce e degli assi, poi la traslazione minima), poi i minimi quadrati su tutti gli accoppiamenti
insieme, spostando il meno possibile. I gradi di libertà che restano liberi non si toccano: si spostano a mano.
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .errors import ProjectFileError, SteelCADError

EXT = '.steelcad-asm'
FORMAT_VERSION = 1
MATE_TYPES = {'faccia': 'faccia su faccia', 'asse': 'foro su foro (coassiale)', 'distanza': 'distanza',
              'parallelo': 'parallele', 'perpendicolare': 'perpendicolari', 'angolo': 'angolo',
              'tangente': 'tangente', 'centra': 'in mezzo', 'blocca': 'blocca',
              'spigolo': 'spigolo su spigolo', 'spigolo_faccia': 'spigolo su faccia'}


class AssemblyError(SteelCADError):
    code = 'assieme'


# ------------------------------------------------------------------------------------------- i pezzi
@dataclass
class Part:
    path: Path
    mtime: float
    doc: object
    result: object
    shape: object                       # TopoDS_Shape (pezzo + strutture), nelle coordinate del pezzo
    names: dict
    mesh: dict | None = None
    props: dict | None = None
    errors: list = field(default_factory=list)


_PEZZI: dict = {}


def load_part(path) -> Part:
    """Legge (e ricostruisce) un pezzo; lo ricorda finché il file non cambia."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    from . import project_io
    p = Path(path).resolve()
    if not p.exists():
        raise AssemblyError(f'Il pezzo {p.name} non si trova più ({p}).')
    mt = p.stat().st_mtime
    vecchio = _PEZZI.get(str(p))
    if vecchio is not None and vecchio.mtime == mt:
        return vecchio
    doc = project_io.load(p)
    res = doc.rebuild()
    solidi = []
    nomi = {}
    if res.body is not None:
        solidi.append(res.body.shape)
        nomi = res.body.names
    for st in res.structures:
        solidi += [m.solid.wrapped for m in st.members]
    if not solidi:
        raise AssemblyError(f'Il pezzo {p.name} è vuoto: non c’è niente da mettere nell’assieme.')
    if len(solidi) == 1:
        forma = solidi[0]
    else:
        forma = TopoDS_Compound()
        b = BRep_Builder()
        b.MakeCompound(forma)
        for s in solidi:
            b.Add(forma, s)
    part = Part(p, mt, doc, res, forma, nomi, errors=[e.message for e in res.errors])
    _PEZZI[str(p)] = part
    return part


def part_mesh(part: Part) -> dict:
    from .mesh import tessellate
    if part.mesh is None:
        part.mesh = tessellate(part.shape, part.names)
    return part.mesh


def part_props(part: Part) -> dict:
    from .analysis import properties
    if part.props is None:
        part.props = properties(part.shape, part.doc.material)
        strutture = getattr(part.result, 'structures', None)
        if strutture:
            # le aste si pesano come nella distinta del pezzo: kg/m del profilo × lunghezza di taglio (come si
            # compra la barra). Il volume del solido (spigoli tondi, tagli a 45°) dava 2–3% in meno, e la stessa
            # struttura pesava diverso nel pezzo e nell'assieme
            from .structures import cut_list
            corpo = properties(part.result.body.shape, part.doc.material)['mass_kg'] if part.result.body is not None else 0
            part.props = {**part.props, 'mass_kg': corpo + cut_list(strutture)['kg']}
    return part.props


# ------------------------------------------------------------------------------------------- l'assieme
@dataclass
class Assembly:
    name: str = 'Assieme'
    instances: list = field(default_factory=list)     # {'id','file','name','R':3x3,'T':[x,y,z],'fixed'}
    mates: list = field(default_factory=list)          # {'id','type','a':ref,'b':ref,'offset','flip'}
    path: Path | None = None

    def to_dict(self) -> dict:
        base = self.path.parent if self.path else None
        ist = []
        for i in self.instances:
            d = copy.deepcopy(i)
            if base is not None:
                try:
                    d['file'] = str(Path(i['file']).resolve().relative_to(base.resolve())).replace('\\', '/')
                except ValueError:
                    d['file'] = str(Path(i['file']).resolve())
            ist.append(d)
        return {'format': 'steelcad-asm', 'version': FORMAT_VERSION, 'name': self.name,
                'instances': ist, 'mates': copy.deepcopy(self.mates)}

    @classmethod
    def from_dict(cls, d: dict, path: Path | None = None) -> 'Assembly':
        if d.get('format') != 'steelcad-asm':
            raise ProjectFileError('Questo file non è un assieme SteelCAD.')
        if d.get('version', 0) > FORMAT_VERSION:
            raise ProjectFileError('L’assieme è stato salvato da una versione più nuova di SteelCAD.')
        a = cls(d.get('name') or 'Assieme', copy.deepcopy(d.get('instances') or []), copy.deepcopy(d.get('mates') or []), path)
        base = path.parent if path else Path.cwd()
        for i in a.instances:
            f = Path(i['file'])
            i['file'] = str(f if f.is_absolute() else (base / f).resolve())
        return a

    def instance(self, iid: str) -> dict:
        for i in self.instances:
            if i['id'] == iid:
                return i
        raise AssemblyError(f'Nell’assieme non c’è {iid}.')

    def new_id(self, prefix: str, esistenti) -> str:
        n = 1
        while f'{prefix}{n}' in esistenti:
            n += 1
        return f'{prefix}{n}'


def save(asm: Assembly, path) -> Path:
    from .project_io import _atomic_write
    p = Path(path)
    if not p.name.endswith(EXT):
        p = p.with_name(p.stem + EXT)
    asm.path = p
    _atomic_write(p, json.dumps(asm.to_dict(), ensure_ascii=False, indent=1))
    return p


def load(path) -> Assembly:
    p = Path(path)
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise ProjectFileError(f'Il file {p} non esiste.') from None
    except (ValueError, UnicodeDecodeError):
        raise ProjectFileError(f'Il file {p.name} è rovinato e non si può leggere.') from None
    return Assembly.from_dict(d, p)


# ------------------------------------------------------------------------------------------- riferimenti
def _R(i) -> np.ndarray:
    return np.array(i.get('R') or np.eye(3).tolist(), dtype=float)


def _T(i) -> np.ndarray:
    return np.array(i.get('T') or [0, 0, 0], dtype=float)


def face_info(part: Part, face) -> dict:
    """Cosa serve per un accoppiamento: piana (punto, normale) o cilindrica (punto sull'asse, direzione)."""
    import build123d as bd
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    from OCP.TopAbs import TopAbs_REVERSED
    ad = BRepAdaptor_Surface(face)
    bf = bd.Face(face)
    c = bf.center()
    nome = next((n for n, fs in part.names.items() if any(f.IsSame(face) for f in fs)), None)
    if ad.GetType() == GeomAbs_Plane:
        n = bf.normal_at(c)
        return {'kind': 'piana', 'name': nome, 'p': [c.X, c.Y, c.Z], 'n': [n.X, n.Y, n.Z]}
    if ad.GetType() == GeomAbs_Cylinder:
        ax = ad.Cylinder().Axis()
        o, d = ax.Location(), ax.Direction()
        o = np.array([o.X(), o.Y(), o.Z()])
        d = np.array([d.X(), d.Y(), d.Z()])
        q = o + d * np.dot(np.array([c.X, c.Y, c.Z]) - o, d)        # il punto dell'asse davanti al centro
        return {'kind': 'cilindrica', 'name': nome, 'p': q.tolist(), 'n': d.tolist(),
                'r': ad.Cylinder().Radius(), 'reversed': face.Orientation() == TopAbs_REVERSED}
    return {'kind': 'altra', 'name': nome, 'p': [c.X, c.Y, c.Z], 'n': [0, 0, 1]}


def edge_info(part: Part, edge) -> dict:
    """Uno spigolo dritto: punto di mezzo e direzione (nelle coordinate del pezzo) e il riferimento stabile (le due
    facce con nome che lo separano)."""
    import build123d as bd
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Line

    from .topology import NamedShape
    if BRepAdaptor_Curve(edge).GetType() != GeomAbs_Line:
        raise AssemblyError('Per gli accoppiamenti su spigolo scegli uno spigolo dritto.')
    be = bd.Edge(edge)
    a, b = be.position_at(0), be.position_at(1)
    d = (b - a).normalized()
    try:
        ref = NamedShape(part.shape, part.names).edge_ref(edge)
    except SteelCADError as ex:
        raise AssemblyError(f'Questo spigolo non si può usare: {ex.message}') from None
    m = (a + b) * 0.5
    return {'kind': 'spigolo', 'name': None, 'faces': ref['faces'], **({'index': ref['index']} if 'index' in ref else {}),
            'p': [m.X, m.Y, m.Z], 'n': [d.X, d.Y, d.Z], 'L': be.length}


def _resolve_edge(part: Part, ref: dict) -> dict:
    from .topology import NamedShape
    try:
        spigoli = NamedShape(part.shape, part.names).edges({'faces': ref['faces'], **({'index': ref['index']} if 'index' in ref else {})})
    except SteelCADError:
        raise AssemblyError('Un accoppiamento non trova più il suo spigolo nel pezzo (è stato tolto?).') from None
    p0 = np.array(ref['p'], dtype=float)
    cand = []
    for e in spigoli:
        try:
            info = edge_info(part, e)
        except AssemblyError:
            continue
        cand.append((np.linalg.norm(np.array(info['p']) - p0), info))
    if not cand:
        raise AssemblyError('Lo spigolo di un accoppiamento non è più dritto.')
    return min(cand, key=lambda x: x[0])[1]


def resolve_ref(part: Part, ref: dict) -> dict:
    """Ritrova la faccia di un riferimento anche se il pezzo è cambiato: tra le facce con quel nome (se c'è) e di
    quel tipo, quella più vicina al punto salvato."""
    from .topology.naming import _faces_of
    if ref.get('kind') == 'spigolo':
        return _resolve_edge(part, ref)
    tipo = 'piana' if ref.get('kind') == 'piana' else 'cilindrica'
    cand = []
    nome = ref.get('name')
    facce = [f for fs in ([part.names.get(nome)] if nome and part.names.get(nome) else []) for f in fs] or list(_faces_of(part.shape))
    p0 = np.array(ref['p'], dtype=float)
    for f in facce:
        info = face_info(part, f)
        if info['kind'] != tipo:
            continue
        if tipo == 'cilindrica' and ref.get('r') and abs(info['r'] - ref['r']) > 1e-3:
            continue
        d = np.linalg.norm(np.array(info['p']) - p0)
        if tipo == 'cilindrica':                        # distanza dall'asse, non dal punto
            v = p0 - np.array(info['p'])
            dd = np.array(info['n'])
            d = np.linalg.norm(v - dd * np.dot(v, dd))
        cand.append((d, info))
    if not cand:
        raise AssemblyError('Un accoppiamento non trova più la sua faccia nel pezzo (è stata tolta?).')
    return min(cand, key=lambda x: x[0])[1]


# ------------------------------------------------------------------------------------------- risolutore
def _rot_min(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """La rotazione più piccola che porta la direzione a sulla direzione b."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-12:
        if c > 0:
            return np.eye(3)
        perp = np.cross(a, [1, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 1, 0])
        perp /= np.linalg.norm(perp)
        return 2 * np.outer(perp, perp) - np.eye(3)            # mezzo giro attorno a una perpendicolare
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1 / (1 + c))


def _rot_axis(d: np.ndarray, ang: float) -> np.ndarray:
    d = d / np.linalg.norm(d)
    K = np.array([[0, -d[2], d[1]], [d[2], 0, -d[0]], [-d[1], d[0], 0]])
    return np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * K @ K


def _kabsch(src: list, dst: list) -> np.ndarray:
    H = sum(np.outer(s, t) for s, t in zip(src, dst))
    U, _, Vt = np.linalg.svd(H)
    D = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))])
    return Vt.T @ D @ U.T


def solve(asm: Assembly, parts: dict) -> dict:
    """Mette a posto le istanze secondo gli accoppiamenti. Ritorna {id: (R, T)} e scrive R, T nelle istanze.
    Gli accoppiamenti che non si possono rispettare finiscono in asm.warnings."""
    asm.warnings = []
    pose = {i['id']: (_R(i), _T(i)) for i in asm.instances}
    if not asm.instances:
        return pose
    terra = {i['id'] for i in asm.instances if i.get('fixed')} or {asm.instances[0]['id']}
    fatti = set(terra)
    mates = [m for m in asm.mates if not m.get('off')]
    for _giro in range(len(asm.instances) + 1):
        avanti = False
        for ist in asm.instances:
            iid = ist['id']
            if iid in fatti:
                continue
            mie = []
            for m in mates:
                if m['b']['inst'] == iid and m['a']['inst'] in fatti:
                    mie.append((m, m['a'], m['b']))
                elif m['a']['inst'] == iid and m['b']['inst'] in fatti:
                    mie.append((m, m['b'], m['a']))
            if not mie:
                continue
            try:
                pose[iid] = _place(pose, parts, asm, iid, mie)
            except AssemblyError as ex:
                asm.warnings.append(str(ex.message))
            fatti.add(iid)
            avanti = True
        if not avanti:
            break
    for ist in asm.instances:
        R, T = pose[ist['id']]
        ist['R'], ist['T'] = R.tolist(), T.tolist()
    # controllo: quanto sono rispettati
    nomi = {i['id']: i.get('name') or i['id'] for i in asm.instances}
    for m in mates:
        if m['a']['inst'] not in fatti and m['b']['inst'] not in fatti:
            # nessuno dei due è fisso né agganciato a un pezzo fisso: non c'è da dove partire (20/10: diceva «in
            # contrasto con gli altri» e si cercava la cosa sbagliata)
            asm.warnings.append(f'L’accoppiamento {m["id"]} tra {nomi.get(m["a"]["inst"])} e {nomi.get(m["b"]["inst"])} '
                                'aspetta: nessuno dei due è fisso o attaccato a un pezzo fisso. Rendi fisso uno dei due '
                                '(clic sul pezzo, «Fisso») oppure accoppialo a un pezzo fisso.')
            continue
        err = mate_error(m, pose, parts, asm)
        if err is not None and err > 1e-3:
            asm.warnings.append(f'L’accoppiamento {m["id"]} ({MATE_TYPES[m["type"]]}) non si riesce a rispettare '
                                f'(scarto {err:.3f}): controlla che non sia in contrasto con gli altri.')
    return pose


def _world(ref, pose, parts, asm):
    part = parts[asm.instance(ref['inst'])['file']]
    info = resolve_ref(part, ref)
    R, T = pose[ref['inst']]
    return info, R @ np.array(info['p']) + T, R @ np.array(info['n'])


# le facce ritrovate, per pezzo e riferimento: ritrovarle scorre tutte le facce del pezzo, e un assieme con tanti
# accoppiamenti le chiedeva migliaia di volte a ogni ricalcolo (il pezzo resta nel valore: il suo id non si ricicla)
_INFO_CACHE: dict = {}


def _info(ref, parts, asm) -> dict:
    """La faccia di un riferimento nelle coordinate del suo pezzo: tipo, p, n (versore), r."""
    part = parts[asm.instance(ref['inst'])['file']]
    chiave = (id(part), ref.get('name'), ref.get('kind'), tuple(round(float(x), 9) for x in ref['p']),
              round(float(ref.get('r') or 0), 9))
    trovato = _INFO_CACHE.get(chiave)
    if trovato is not None and trovato[0] is part:
        return trovato[1]
    i = resolve_ref(part, ref)
    n = np.array(i['n'], dtype=float)
    out = {'kind': i['kind'], 'p': np.array(i['p'], dtype=float), 'n': n / np.linalg.norm(n), 'r': float(i.get('r') or 0)}
    if len(_INFO_CACHE) > 50000:
        _INFO_CACHE.clear()
    _INFO_CACHE[chiave] = (part, out)
    return out


def _nel_mondo(info, R, T) -> dict:
    return {**info, 'p': R @ info['p'] + T, 'n': R @ info['n']}


def _perp(v, d):
    return v - d * np.dot(v, d)


PESO_DIR = 100.0                # un versore sbagliato «pesa» come 100 mm: angoli e distanze sulla stessa scala


def residui(m, F: dict, pose_ab=None, peso=PESO_DIR) -> np.ndarray:
    """Quanto l'accoppiamento m non è rispettato (tutti zero = rispettato). F: le facce nel mondo per chiave
    ('a', 'b' e per In mezzo 'a2', 'b2'); pose_ab: le pose (R, T) dei pezzi a e b (per Blocca)."""
    PESO_DIR = peso
    t = m['type']
    off = float(m.get('offset') or 0)
    s = -1.0 if m.get('flip') else 1.0
    if t == 'blocca':
        (RA, TA), (RB, TB) = pose_ab
        Rr, Tr = np.array(m['rel_R'], dtype=float), np.array(m['rel_T'], dtype=float)
        return np.concatenate([(RB - RA @ Rr).ravel() * PESO_DIR, TB - (RA @ Tr + TA)])
    A, B = F['a'], F['b']
    nA, nB = A['n'], B['n']
    if t in ('faccia', 'distanza'):
        verso = nA if m.get('flip') else -nA
        return np.concatenate([(nB - verso) * PESO_DIR, [np.dot(nA, B['p'] - A['p']) - off]])
    if t == 'asse':
        return np.concatenate([np.cross(nA, nB) * PESO_DIR, _perp(B['p'] - A['p'], nA)])
    if t == 'parallelo':
        return np.cross(nA, nB) * PESO_DIR
    if t == 'perpendicolare':
        return np.array([np.dot(nA, nB) * PESO_DIR])
    if t == 'angolo':
        # 0° = le facce una contro l'altra (come faccia su faccia), 90° = a squadra; «dall'altra parte» gira il verso
        return np.array([(np.dot(nA, nB) + s * math.cos(math.radians(float(m.get('angle') or 0)))) * PESO_DIR])
    if t == 'tangente':
        if A['kind'] == 'piana' and B['kind'] == 'cilindrica':
            return np.array([np.dot(nA, nB) * PESO_DIR, np.dot(nA, B['p'] - A['p']) - s * (B['r'] + off)])
        if A['kind'] == 'cilindrica' and B['kind'] == 'piana':
            return np.array([np.dot(nA, nB) * PESO_DIR, np.dot(nB, A['p'] - B['p']) - s * (A['r'] + off)])
        d = np.linalg.norm(_perp(B['p'] - A['p'], nA))          # due tubi: fuori (somma dei raggi) o dentro (differenza)
        voluto = (A['r'] + B['r'] if s > 0 else abs(A['r'] - B['r'])) + off
        return np.concatenate([np.cross(nA, nB) * PESO_DIR, [d - voluto]])
    if t == 'spigolo':
        # sulla stessa linea: direzioni parallele, e il punto di b sulla retta di a
        return np.concatenate([np.cross(nA, nB) * PESO_DIR, _perp(B['p'] - A['p'], nA)])
    if t == 'spigolo_faccia':
        # lo spigolo appoggiato sulla faccia: dentro il suo piano (a distanza «offset»)
        pf, sp = (A, B) if A['kind'] == 'piana' else (B, A)
        return np.array([np.dot(pf['n'], sp['n']) * PESO_DIR, np.dot(pf['n'], sp['p'] - pf['p']) - off])
    if t == 'centra':
        # le due facce di b a metà tra le due di a (un piatto in mezzo a un U, un tubo centrato su una piastra)
        mezzo_a = (np.dot(nA, A['p']) + np.dot(nA, F['a2']['p'])) / 2
        mezzo_b = (np.dot(nA, B['p']) + np.dot(nA, F['b2']['p'])) / 2
        return np.concatenate([np.cross(nA, nB) * PESO_DIR, [mezzo_b - mezzo_a - off]])
    raise AssemblyError(f'Accoppiamento «{t}» sconosciuto.')


CHIAVI = ('a', 'b', 'a2', 'b2')


def _rot_vec(w) -> np.ndarray:
    ang = float(np.linalg.norm(w))
    return np.eye(3) if ang < 1e-15 else _rot_axis(w / ang, ang)


def _place(pose, parts, asm, iid, mie):
    """Mette a posto l'istanza iid rispetto ai pezzi già a posto. Prima un punto di partenza a formula (direzioni
    e distanze lungo le normali), poi i minimi quadrati sui 6 movimenti, spostando il meno possibile."""
    from scipy.optimize import least_squares
    R0, T0 = pose[iid]
    dati = []                                   # (m, facce ferme nel mondo, facce mie nel pezzo)
    for m, _fermo, _mio in mie:
        if m['type'] == 'blocca':
            dati.append((m, None, None))
            continue
        ferme, mie_f = {}, {}
        for k in CHIAVI:
            if not m.get(k):
                continue
            if m[k]['inst'] == iid:
                mie_f[k] = _info(m[k], parts, asm)
            else:
                R, T = pose[m[k]['inst']]
                ferme[k] = _nel_mondo(_info(m[k], parts, asm), R, T)
        dati.append((m, ferme, mie_f))

    def tutti(R, T):
        out = []
        for m, ferme, mie_f in dati:
            if ferme is None:
                pa = (R, T) if m['a']['inst'] == iid else pose[m['a']['inst']]
                pb = (R, T) if m['b']['inst'] == iid else pose[m['b']['inst']]
                out.append(residui(m, {}, (pa, pb)))
            else:
                out.append(residui(m, {**ferme, **{k: _nel_mondo(v, R, T) for k, v in mie_f.items()}}))
        return np.concatenate(out) if out else np.zeros(0)

    R, T = _partenza(R0, T0, dati, pose, iid)
    if np.linalg.norm(tutti(R, T)) > 1e-9:
        scala = np.array([0.01] * 3 + [10.0] * 3)

        def f(x, reg):
            r = tutti(_rot_vec(x[:3]) @ R, T + x[3:])
            return np.concatenate([r, reg * np.concatenate([x[:3] * PESO_DIR, x[3:]])]) if reg else r
        x = least_squares(f, np.zeros(6), args=(1e-3,), method='trf', x_scale=scala).x
        if np.linalg.norm(f(x, 0)) > 1e-9:
            x = least_squares(f, x, args=(0,), method='trf', x_scale=scala, xtol=1e-15, ftol=1e-15, gtol=1e-15).x
        R, T = _rot_vec(x[:3]) @ R, T + x[3:]
        U, _, Vt = np.linalg.svd(R)                  # una rotazione pulita
        R = U @ Vt
    return R, T


def _partenza(R0, T0, dati, pose, iid):
    """Il punto di partenza a formula: la rotazione dalle direzioni da far coincidere (faccia su faccia, foro su foro,
    parallelo, in mezzo) e la traslazione minima per faccia su faccia, distanza e foro su foro."""
    src, dst, assi = [], [], []
    for m, ferme, mie_f in dati:
        if ferme is None:                            # Blocca: la posa è già scritta
            Rr, Tr = np.array(m['rel_R'], dtype=float), np.array(m['rel_T'], dtype=float)
            if m['b']['inst'] == iid:
                RA, TA = pose[m['a']['inst']]
                return RA @ Rr, RA @ Tr + TA
            RB, TB = pose[m['b']['inst']]            # RB = RA Rr, TB = RA Tr + TA
            RA = RB @ Rr.T
            return RA, TB - RA @ Tr
        kf, km = ('a', 'b') if 'a' in ferme else ('b', 'a')
        nA, nB = ferme[kf]['n'], mie_f[km]['n']
        t = m['type']
        if t in ('faccia', 'distanza'):
            dst.append(nA if m.get('flip') else -nA)
            src.append(nB)
        elif t in ('asse', 'parallelo', 'centra'):
            v = nA if np.dot(R0 @ nB, nA) >= 0 else -nA
            if m.get('flip') and t != 'centra':
                v = -v
            dst.append(v)
            src.append(nB)
            if t == 'asse':
                assi.append((ferme[kf]['p'], mie_f[km]['p']))
    rango = np.linalg.matrix_rank(np.array(dst), tol=1e-6) if dst else 0
    if rango == 0:
        R = R0
    elif rango == 1:
        R = _rot_min(R0 @ src[0], dst[0]) @ R0
        if len(assi) >= 2:                           # attorno a quell'asse resta libera: due fori paralleli la fissano
            d = dst[0] / np.linalg.norm(dst[0])
            (pA1, pB1), (pA2, pB2) = assi[0], assi[1]
            va, vb = _perp(pA2 - pA1, d), _perp(R @ (pB2 - pB1), d)
            if np.linalg.norm(va) > 1e-6 and np.linalg.norm(vb) > 1e-6:
                R = _rot_axis(d, math.atan2(np.dot(np.cross(vb, va), d), np.dot(vb, va))) @ R
    else:
        R = _kabsch(src, dst)
    righe, valori = [], []
    for m, ferme, mie_f in dati:
        kf, km = ('a', 'b') if 'a' in ferme else ('b', 'a')
        pA, nA = ferme[kf]['p'], ferme[kf]['n']
        pB = R @ mie_f[km]['p']
        if m['type'] in ('faccia', 'distanza'):
            off = float(m.get('offset') or 0) * (-1 if kf == 'b' and m.get('flip') else 1)
            righe.append(nA)
            valori.append(float(np.dot(nA, pA) + off - np.dot(nA, pB)))
        elif m['type'] == 'asse':
            u = np.cross(nA, [1, 0, 0]) if abs(nA[0]) < 0.9 else np.cross(nA, [0, 1, 0])
            u /= np.linalg.norm(u)
            for e in (u, np.cross(nA, u)):
                righe.append(e)
                valori.append(float(np.dot(e, pA) - np.dot(e, pB)))
    if not righe:
        return R, T0
    M = np.array(righe)
    return R, T0 + np.linalg.pinv(M) @ (np.array(valori) - M @ T0)


def mate_error(m, pose, parts, asm) -> float | None:
    try:
        if m['type'] == 'blocca':
            return float(np.linalg.norm(residui(m, {}, (pose[m['a']['inst']], pose[m['b']['inst']]), peso=1)))
        F = {}
        for k in CHIAVI:
            if m.get(k):
                R, T = pose[m[k]['inst']]
                F[k] = _nel_mondo(_info(m[k], parts, asm), R, T)
        r = residui(m, F, peso=1)
    except (AssemblyError, KeyError):
        return None
    return float(np.linalg.norm(r))


# ------------------------------------------------------------------------------------------- distinta, interferenze
def bom(asm: Assembly, parts: dict) -> list:
    """Una riga per file di pezzo: quante copie, peso, spessore e sviluppo della lamiera."""
    righe: dict = {}
    for i in asm.instances:
        part = parts.get(i['file'])
        if part is None:
            continue
        r = righe.get(i['file'])
        if r is None:
            pr = part_props(part)
            sheet = getattr(part.result.body, 'sheet', None) if part.result.body is not None else None
            r = righe[i['file']] = {'file': i['file'], 'name': part.doc.meta.get('name') or part.path.stem, 'qty': 0,
                                    'material': part.doc.material, 'mass_kg': pr['mass_kg'],
                                    'thickness': sheet.thickness if sheet else None,
                                    'flat': list(sheet.flat_size) if sheet else None,
                                    'acquisto': part.doc.meta.get('acquisto') or None,
                                    'finitura': part.doc.meta.get('finitura') or None}
        r['qty'] += 1
    out = list(righe.values())
    for r in out:
        r['mass_tot'] = r['mass_kg'] * r['qty']
    return out


def placed_shape(part: Part, R, T):
    import build123d as bd
    from OCP.gp import gp_Trsf
    tr = gp_Trsf()
    tr.SetValues(R[0][0], R[0][1], R[0][2], T[0], R[1][0], R[1][1], R[1][2], T[1], R[2][0], R[2][1], R[2][2], T[2])
    return bd.Shape.cast(part.shape).moved(bd.Location(tr))


def interferences(asm: Assembly, parts: dict, tol: float = 1e-3) -> list:
    """Le coppie di istanze che si compenetrano, con il volume in comune (mm³)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    forme = []
    for i in asm.instances:
        part = parts.get(i['file'])
        if part is not None:
            s = placed_shape(part, i['R'] if i.get('R') else np.eye(3).tolist(), i.get('T') or [0, 0, 0])
            forme.append((i['id'], s, s.bounding_box()))
    out = []
    for k, (ia, sa, ba) in enumerate(forme):
        for ib, sb, bb in forme[k + 1:]:
            if (ba.max.X < bb.min.X or bb.max.X < ba.min.X or ba.max.Y < bb.min.Y or bb.max.Y < ba.min.Y
                    or ba.max.Z < bb.min.Z or bb.max.Z < ba.min.Z):
                continue
            try:
                op = BRepAlgoAPI_Common()
                c = sa._bool_op((sa,), (sb,), op)
                v = c.volume
            except Exception:  # noqa: BLE001
                continue
            if v > tol:
                out.append({'a': ia, 'b': ib, 'volume': v})
    return out
