"""Assiemi: più pezzi SteelCAD messi insieme.

Un file `.steelcad-asm` richiama i file dei pezzi (`.steelcad`, percorsi relativi all'assieme) e dice dove sta
ogni copia (istanza): una rotazione R e una traslazione T (punto nel mondo = R · punto del pezzo + T). Se un pezzo
cambia, l'assieme lo rilegge (dalla data del file).

Accoppiamenti (come in officina):
- **faccia su faccia**: due facce piane una contro l'altra (normali opposte), con una distanza;
- **foro su foro** (coassiale): gli assi di due fori (o due facce cilindriche) sulla stessa linea.

Il risolutore muove ogni istanza (tranne la prima, che sta ferma) partendo da dov'è: prima la rotazione (le
direzioni delle facce e degli assi), poi la traslazione con il minimo spostamento che rispetta tutti gli
accoppiamenti. I gradi di libertà che restano liberi non si toccano: si spostano a mano.
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
MATE_TYPES = {'faccia': 'faccia su faccia', 'asse': 'foro su foro (coassiale)'}


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


def resolve_ref(part: Part, ref: dict) -> dict:
    """Ritrova la faccia di un riferimento anche se il pezzo è cambiato: tra le facce con quel nome (se c'è) e di
    quel tipo, quella più vicina al punto salvato."""
    from .topology.naming import _faces_of
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
    for m in mates:
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


def _place(pose, parts, asm, iid, mie):
    R0, T0 = pose[iid]
    part = parts[asm.instance(iid)['file']]
    # 1) rotazione: direzioni da far coincidere
    src, dst, assi = [], [], []
    for m, fermo, mio in mie:
        _, pA, nA = _world(fermo, pose, parts, asm)
        info = resolve_ref(part, mio)
        nB = np.array(info['n'])
        if m['type'] == 'faccia':
            t = nA if m.get('flip') else -nA
            src.append(nB)
            dst.append(t)
        else:
            nBw = R0 @ nB
            t = nA if np.dot(nBw, nA) >= 0 else -nA
            if m.get('flip'):
                t = -t
            src.append(nB)
            dst.append(t)
            assi.append((pA, nA, np.array(info['p'])))
    M = np.array(dst)
    rango = np.linalg.matrix_rank(M, tol=1e-6) if len(dst) else 0
    if rango == 0:
        R = R0
    elif rango == 1:
        R = _rot_min(R0 @ src[0], dst[0]) @ R0
        # attorno a quell'asse resta libera: due fori paralleli la fissano
        if len(assi) >= 2:
            d = dst[0] / np.linalg.norm(dst[0])
            (pA1, _, pB1), (pA2, _, pB2) = assi[0], assi[1]
            va, vb = pA2 - pA1, R @ (pB2 - pB1)
            va -= d * np.dot(va, d)
            vb -= d * np.dot(vb, d)
            if np.linalg.norm(va) > 1e-6 and np.linalg.norm(vb) > 1e-6:
                ang = math.atan2(np.dot(np.cross(vb, va), d), np.dot(vb, va))
                R = _rot_axis(d, ang) @ R
    else:
        R = _kabsch([s / np.linalg.norm(s) for s in src], [t / np.linalg.norm(t) for t in dst])
    # 2) traslazione: il minimo spostamento da dov'era che rispetta tutto
    righe, valori = [], []
    for m, fermo, mio in mie:
        _, pA, nA = _world(fermo, pose, parts, asm)
        info = resolve_ref(part, mio)
        pB = R @ np.array(info['p'])
        if m['type'] == 'faccia':
            n = nA / np.linalg.norm(nA)
            righe.append(n)
            valori.append(float(np.dot(n, pA) + float(m.get('offset') or 0) - np.dot(n, pB)))
        else:
            d = nA / np.linalg.norm(nA)
            u = np.cross(d, [1, 0, 0]) if abs(d[0]) < 0.9 else np.cross(d, [0, 1, 0])
            u /= np.linalg.norm(u)
            v = np.cross(d, u)
            for e in (u, v):
                righe.append(e)
                valori.append(float(np.dot(e, pA) - np.dot(e, pB)))
    A = np.array(righe)
    b = np.array(valori)
    T = T0 + np.linalg.pinv(A) @ (b - A @ T0)
    return R, T


def mate_error(m, pose, parts, asm) -> float | None:
    try:
        _, pA, nA = _world(m['a'], pose, parts, asm)
        _, pB, nB = _world(m['b'], pose, parts, asm)
    except (AssemblyError, KeyError):
        return None
    nA, nB = nA / np.linalg.norm(nA), nB / np.linalg.norm(nB)
    if m['type'] == 'faccia':
        ang = abs(np.dot(nA, nB) - (1 if m.get('flip') else -1))
        return float(ang + abs(np.dot(nA, pB - pA) - float(m.get('offset') or 0)))
    v = pB - pA
    return float(1 - abs(np.dot(nA, nB)) + np.linalg.norm(v - nA * np.dot(v, nA)))


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
                                    'flat': list(sheet.flat_size) if sheet else None}
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
