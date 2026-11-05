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

Sottoassiemi (05/11, Stefano: «in un assieme posso mettere un altro assieme?»): un'istanza può richiamare un altro
`.steelcad-asm`. Si legge come un pezzo solo (Part con `sotto` = il suo assieme e `figli` = i suoi pezzi messi): la
forma è l'insieme dei suoi pezzi al loro posto, le facce si chiamano «istanza:nome» e si accoppiano come quelle di un
pezzo. Si muove tutto insieme; la distinta di base conta i pezzi dentro (foglie()), quella per sottoassiemi tiene il
blocco con i suoi pezzi sotto. Un assieme non può stare dentro se stesso.

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
              'spigolo': 'spigolo su spigolo', 'spigolo_faccia': 'spigolo su faccia', 'cono': 'cono su cono',
              'testa': 'testa a testa (angolo a cornice)'}


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
    sotto: object = None                # sottoassieme: il suo Assembly (None per un pezzo)
    figli: list = field(default_factory=list)   # sottoassieme: (Part, R, T, id dell'istanza, nome), nelle sue coordinate
    gruppi: list = field(default_factory=list)  # sottoassieme: (prima faccia, quante, Part) per l'aspetto di ogni pezzo


class _DocAssieme:
    """Quello che chi usa un pezzo chiede al suo documento, per un sottoassieme."""
    material = ''
    features: list = []
    parameters: dict = {}

    def __init__(self, nome):
        self.meta = {'name': nome}
        self.figli = []

    def describe_face(self, nome) -> str:
        """«istanza:nome» → «Plexiglass, la faccia di sopra»: il pezzo dentro e la sua faccia."""
        iid, _, resto = str(nome or '').partition(':')
        for cp, _, _, fid, fnome in self.figli:
            if fid == iid:
                return f'{fnome}, {cp.doc.describe_face(resto) if resto else "faccia"}'
        return 'faccia'


class _RisAssieme:
    body = None
    structures: list = []
    errors: list = []


_PEZZI: dict = {}

# 03/11: i nomi con cui nasce un pezzo (dai modelli). Chi salva «Piastra base.steelcad» senza cambiare il nome dentro
# vedeva «Lamiera» nell'assieme, in distinta e nelle tavole: con uno di questi nomi conta il nome del file
NOMI_DI_PARTENZA = {'', 'Lamiera', 'Pezzo', 'Pezzo nuovo', 'Piastra', 'Struttura', 'Telaio', 'Telaio armadio', 'Scaffale',
                    'Cancello', 'Tronco di cono', 'Raccordo quadro-tondo', 'Tramoggia con cassone', 'Staffa a L',
                    'Profilo a U', 'Scatola', 'Coperchio', 'Progetto', 'Senza nome'}


def nome_di_partenza(nome) -> bool:
    return str(nome or '').strip() in NOMI_DI_PARTENZA


def nome_visibile(doc, path) -> str:
    """Il nome del pezzo come lo si vede: il suo, se gliel'hai dato; se no quello del file."""
    n = str(doc.meta.get('name') or '').strip()
    if (not n or n in NOMI_DI_PARTENZA) and path is not None and Path(path).stem.lower() != n.lower():
        return Path(path).stem
    return n or 'Pezzo'


def _firma(p: Path, pila=()):
    """Quando rileggere: la data del file e, per un sottoassieme, quelle di tutti i suoi pezzi (anche dentro)."""
    try:
        mt = p.stat().st_mtime
    except OSError:
        return (str(p), None)
    if not p.name.endswith(EXT) or str(p) in pila:
        return (str(p), mt)
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError, UnicodeDecodeError):
        return (str(p), mt)
    figli = []
    for f in dict.fromkeys(str(i.get('file')) for i in d.get('instances') or []):
        q = Path(f) if Path(f).is_absolute() else (p.parent / f)
        figli.append(_firma(q.resolve(), pila + (str(p),)))
    return (str(p), mt, tuple(figli))


def _compound(solidi):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    forma = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(forma)
    for s in solidi:
        b.Add(forma, s)
    return forma


def _load_sotto(p: Path, pila) -> Part:
    """Un sottoassieme letto come un pezzo solo: i suoi pezzi al loro posto in una forma, le facce coi nomi."""
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape

    from .topology.naming import _faces_of
    if str(p) in pila:
        raise AssemblyError(f'«{p.stem}» finirebbe dentro se stesso: un assieme non può contenere sé stesso, '
                            'nemmeno passando da un altro.')
    firma = _firma(p, pila)
    vecchio = _PEZZI.get(str(p))
    if vecchio is not None and vecchio.mtime == firma:
        return vecchio
    asm = load(p)
    parti, errori = {}, []
    for i in asm.instances:
        if i['file'] in parti:
            continue
        try:
            parti[i['file']] = load_part(i['file'], pila + (str(p),))
        except AssemblyError as ex:
            if 'dentro se stesso' in ex.message:
                raise
            errori.append(f'In «{p.stem}»: {ex.message}')
    asm.instances = [i for i in asm.instances if i['file'] in parti]
    if not asm.instances:
        raise AssemblyError(f'Il sottoassieme {p.name} è vuoto: non c’è niente da mettere nell’assieme.')
    asm.mates = [m for m in asm.mates if m['a']['inst'] in {i['id'] for i in asm.instances}
                 and m['b']['inst'] in {i['id'] for i in asm.instances}]
    solve(asm, parti)
    figli, solidi, nomi, gruppi, off = [], [], {}, [], 0
    for i in asm.instances:
        part = parti[i['file']]
        R, T = _R(i), _T(i)
        figli.append((part, R, T, i['id'], i.get('name') or part.doc.meta.get('name') or i['id']))
        solidi.append(placed_shape(part, R.tolist(), T.tolist()).wrapped)
        m = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(part.shape, TopAbs_FACE, m)
        n = len(_faces_of(part.shape))
        gruppi.append((off, n, part))
        for nome, fs in (part.names or {}).items():
            for f in fs:
                k = m.FindIndex(f)
                if k:
                    nomi.setdefault(f'{i["id"]}:{nome}', []).append(off + k - 1)
        off += n
    forma = _compound(solidi)
    facce = _faces_of(forma)
    nomi = {k: [facce[j] for j in v] for k, v in nomi.items()}
    nome = asm.name if asm.name and asm.name != 'Assieme' else p.stem
    doc = _DocAssieme(nome)
    doc.figli = figli
    part = Part(p, firma, doc, _RisAssieme(), forma, nomi, errors=errori + [str(w) for w in asm.warnings],
                sotto=asm, figli=figli, gruppi=gruppi)
    _PEZZI[str(p)] = part
    return part


def load_part(path, pila=()) -> Part:
    """Legge (e ricostruisce) un pezzo, o un sottoassieme (.steelcad-asm); lo ricorda finché il file non cambia.
    pila: gli assiemi che lo stanno già leggendo (un assieme non può stare dentro se stesso)."""
    from . import project_io
    p = Path(path).resolve()
    if not p.exists():
        raise AssemblyError(f'Il pezzo {p.name} non si trova più ({p}).')
    if p.name.endswith(EXT):
        return _load_sotto(p, tuple(str(Path(x).resolve()) for x in pila))
    mt = p.stat().st_mtime
    vecchio = _PEZZI.get(str(p))
    if vecchio is not None and vecchio.mtime == mt:
        return vecchio
    doc = project_io.load(p)
    doc.meta['name'] = nome_visibile(doc, p)          # solo in memoria: distinta e tavole col nome giusto
    res = doc.rebuild()
    solidi = []
    nomi = {}
    if res.body is not None:
        solidi.append(res.body.shape)
        nomi = res.body.names
    for st in res.structures:
        solidi += [m.solid.wrapped for m in st.members]
        solidi += [a.solid.wrapped for a in getattr(st, 'accessori', None) or []]      # piedi e tappi
    if not solidi:
        raise AssemblyError(f'Il pezzo {p.name} è vuoto: non c’è niente da mettere nell’assieme.')
    forma = solidi[0] if len(solidi) == 1 else _compound(solidi)
    part = Part(p, mt, doc, res, forma, nomi, errors=[e.message for e in res.errors])
    _PEZZI[str(p)] = part
    return part


def _gruppi_di(part: Part, off: int = 0) -> list:
    """Le facce di ogni pezzo vero dentro un sottoassieme (anche dentro un altro): (prima, quante, Part)."""
    out = []
    for o, n, cp in part.gruppi:
        out += _gruppi_di(cp, off + o) if cp.sotto is not None else [(off + o, n, cp)]
    return out


def part_mesh(part: Part) -> dict:
    from .mesh import tessellate
    if part.mesh is None:
        part.mesh = tessellate(part.shape, part.names)
        if part.sotto is not None:
            # ogni pezzo col suo aspetto (il plexiglass trasparente, il verniciato col suo RAL): i triangoli per pezzo
            from . import finiture
            gr = []
            for o, n, cp in _gruppi_di(part):
                fs = [f for f in part.mesh['faces'] if o <= f['index'] < o + n]
                if fs:
                    a = min(f['start'] for f in fs)
                    gr.append({'start': a, 'count': max(f['start'] + f['count'] for f in fs) - a,
                               'look': finiture.aspetto(cp.doc.material, cp.doc.meta.get('finitura'))})
            part.mesh['gruppi'] = gr
    return part.mesh


def part_props(part: Part) -> dict:
    from .analysis import properties
    if part.props is None and part.sotto is not None:
        base = properties(part.shape, 'S235')          # volume e ingombro; il peso è la somma dei suoi pezzi
        part.props = {**base, 'material': '', 'mass_kg': sum(part_props(c[0])['mass_kg'] for c in part.figli)}
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
    meta: dict = field(default_factory=dict)           # 28/10: dati dell'assieme (le tavole ritoccate…)
    gruppi: list = field(default_factory=list)         # 05/11: pezzi bloccati insieme {'id','name','pezzi':[id…]}

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
        out = {'format': 'steelcad-asm', 'version': FORMAT_VERSION, 'name': self.name,
               'instances': ist, 'mates': copy.deepcopy(self.mates)}
        if self.meta:
            out['meta'] = copy.deepcopy(self.meta)
        if self.gruppi:
            out['gruppi'] = copy.deepcopy(self.gruppi)
        return out

    @classmethod
    def from_dict(cls, d: dict, path: Path | None = None) -> 'Assembly':
        if d.get('format') != 'steelcad-asm':
            raise ProjectFileError('Questo file non è un assieme Radius.')
        if d.get('version', 0) > FORMAT_VERSION:
            raise ProjectFileError('L’assieme è stato salvato da una versione più nuova di Radius.')
        a = cls(d.get('name') or 'Assieme', copy.deepcopy(d.get('instances') or []), copy.deepcopy(d.get('mates') or []), path,
                copy.deepcopy(d.get('meta') or {}))
        a.gruppi = copy.deepcopy(d.get('gruppi') or [])
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
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane
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
    if ad.GetType() == GeomAbs_Cone:
        cono = ad.Cone()
        ap, d = cono.Apex(), cono.Axis().Direction()
        apice = np.array([ap.X(), ap.Y(), ap.Z()])
        d = np.array([d.X(), d.Y(), d.Z()])
        if np.dot(np.array([c.X, c.Y, c.Z]) - apice, d) < 0:     # verso dove il cono si allarga (dove sta la faccia)
            d = -d
        return {'kind': 'conica', 'name': nome, 'p': apice.tolist(), 'n': d.tolist(),
                'r': abs(math.degrees(cono.SemiAngle()))}
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
    tipo = ref.get('kind') if ref.get('kind') in ('piana', 'conica') else 'cilindrica'
    cand = []
    nome = ref.get('name')
    tutte = list(_faces_of(part.shape))
    # le facce col nome, ma prese dal solido: quella salvata col nome può avere il verso rovesciato (la normale
    # verso l'interno) e il pezzo si girava sottosopra pur rispettando l'accoppiamento (21/10)
    facce = [next((g for g in tutte if g.IsSame(f)), f)
             for fs in ([part.names.get(nome)] if nome and part.names.get(nome) else []) for f in fs] or tutte
    p0 = np.array(ref['p'], dtype=float)
    for f in facce:
        info = face_info(part, f)
        if info['kind'] != tipo:
            continue
        if tipo in ('cilindrica', 'conica') and ref.get('r') and abs(info['r'] - ref['r']) > 1e-3:
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
    if getattr(asm, 'gruppi', None):
        return _solve_gruppi(asm, parts)
    asm.warnings = []
    pose = {i['id']: (_R(i), _T(i)) for i in asm.instances}
    if not asm.instances:
        return pose
    terra = {i['id'] for i in asm.instances if i.get('fixed')} or {asm.instances[0]['id']}
    fatti = set(terra)
    mates = [m for m in asm.mates if not m.get('off')]
    nomi = {i['id']: i.get('name') or i['id'] for i in asm.instances}

    def metti():
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
    metti()
    # gruppi di pezzi accoppiati tra loro ma non al resto (22/10: le viti nelle svasature di un rinforzo non ancora
    # accoppiato al cassone): si mettono a posto lo stesso, attorno al pezzo che ha più accoppiamenti, che resta dove
    # sta. Prima le viti restavano ferme e l'accoppiamento «aspettava» senza che si capisse perché
    liberi = []
    while True:
        conta, fermo = {}, {}
        for m in mates:
            a, b = m['a']['inst'], m['b']['inst']
            if a not in fatti and b not in fatti and a != b:
                conta[a] = conta.get(a, 0) + 1
                conta[b] = conta.get(b, 0) + 1
                fermo[a] = fermo.get(a, 0) + 1       # 'a' è il pezzo cliccato come fermo
        if not conta:
            break
        ordine = {i['id']: k for k, i in enumerate(asm.instances)}
        # a parità resta fermo quello scelto come fermo negli accoppiamenti (03/11, Appoggia tra due pezzi liberi:
        # si muoveva quello sotto invece di quello da appoggiare)
        radice = max(conta, key=lambda x: (conta[x], fermo.get(x, 0), -ordine.get(x, 0)))
        fatti.add(radice)
        liberi.append(radice)
        metti()
    for r in liberi:
        asm.warnings.append(f'«{nomi.get(r, r)}» non è accoppiato al resto dell’assieme: sta dove l’hai messo, e i pezzi '
                            'accoppiati a lui (viti…) gli si mettono attorno. Accoppialo al resto per portarlo al suo posto.')
    for ist in asm.instances:
        R, T = pose[ist['id']]
        ist['R'], ist['T'] = R.tolist(), T.tolist()
    # controllo: quanto sono rispettati
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
    part = parts[asm.instance(ref.get('_da', ref['inst']))['file']]
    chiave = (id(part), ref.get('name'), ref.get('kind'), tuple(round(float(x), 9) for x in ref['p']),
              round(float(ref.get('r') or 0), 9))
    trovato = _INFO_CACHE.get(chiave)
    if trovato is not None and trovato[0] is part:
        return _nel_capo(trovato[1], ref)
    i = resolve_ref(part, ref)
    n = np.array(i['n'], dtype=float)
    out = {'kind': i['kind'], 'p': np.array(i['p'], dtype=float), 'n': n / np.linalg.norm(n), 'r': float(i.get('r') or 0)}
    if len(_INFO_CACHE) > 50000:
        _INFO_CACHE.clear()
    _INFO_CACHE[chiave] = (part, out)
    return _nel_capo(out, ref)


def _nel_capo(info, ref) -> dict:
    """La faccia di un pezzo di un gruppo bloccato, nelle coordinate del primo pezzo del gruppo (vedi _solve_gruppi)."""
    rel = ref.get('_rel')
    if rel is None:
        return info
    Rr, Tr = rel
    return {**info, 'p': Rr @ info['p'] + Tr, 'n': Rr @ info['n']}


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
    if t == 'cono':
        return np.concatenate([(nB - nA) * PESO_DIR, B['p'] - A['p']])
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
    if t == 'testa':
        # angolo a cornice (21/10, il cassone): le due facce dei tagli di testa una davanti all'altra, centrate, a
        # distanza del gioco. Le due teste tagliate uguali sono una lo specchio dell'altra: i loro centri si
        # guardano lungo la normale. Fissa tutto tranne il giro attorno alla normale (lo fissa la seconda testa)
        return np.concatenate([(nB + nA) * PESO_DIR, B['p'] - A['p'] - off * nA])
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
    # i versi decisi senza dubbi (cono su cono: la testa della vite nella svasatura) valgono anche per gli assi
    # paralleli dello stesso pezzo: foro su foro accetta i due versi, e partendo da quello sbagliato la vite
    # restava capovolta (22/10, il cassone: seconda vite TSPEI)
    certi = []
    for m, ferme, mie_f in dati:
        if ferme is not None and m['type'] == 'cono':
            kf, km = ('a', 'b') if 'a' in ferme else ('b', 'a')
            certi.append((mie_f[km]['n'], ferme[kf]['n']))
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
        if t in ('faccia', 'distanza', 'testa'):
            dst.append(nA if m.get('flip') and t != 'testa' else -nA)
            src.append(nB)
        elif t == 'cono':
            dst.append(nA)
            src.append(nB)
        elif t in ('asse', 'parallelo', 'centra'):
            v = nA if np.dot(R0 @ nB, nA) >= 0 else -nA
            for s_c, d_c in certi:
                if abs(np.dot(nB, s_c)) > 0.999 and abs(np.dot(nA, d_c)) > 0.999:
                    v = d_c * float(np.sign(np.dot(nB, s_c)))
                    break
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
        elif m['type'] == 'cono':
            for e in np.eye(3):
                righe.append(e)
                valori.append(float(np.dot(e, pA) - np.dot(e, pB)))
        elif m['type'] == 'testa':
            meta = pA + float(m.get('offset') or 0) * nA            # il centro dell'altra testa, davanti a questa
            for e in np.eye(3):
                righe.append(e)
                valori.append(float(np.dot(e, meta) - np.dot(e, pB)))
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
def foglie(asm: Assembly, parts: dict):
    """I pezzi veri dell'assieme, anche quelli dentro i sottoassiemi, al loro posto nel mondo: (Part, R, T, chi),
    chi = gli id delle istanze dalla più esterna."""
    def giu(part, R, T, chi):
        if part.sotto is None:
            yield part, R, T, chi
            return
        for cp, r, t, iid, _ in part.figli:
            yield from giu(cp, R @ r, R @ t + T, chi + (iid,))
    for i in asm.instances:
        part = parts.get(i['file'])
        if part is not None:
            yield from giu(part, _R(i), _T(i), (i['id'],))


def _riga(part: Part) -> dict:
    pr = part_props(part)
    sheet = getattr(part.result.body, 'sheet', None) if part.result.body is not None else None
    return {'file': str(part.path), 'name': part.doc.meta.get('name') or part.path.stem, 'qty': 0,
            'material': part.doc.material, 'mass_kg': pr['mass_kg'],
            'thickness': sheet.thickness if sheet else None,
            'flat': list(sheet.flat_size) if sheet else None,
            'acquisto': part.doc.meta.get('acquisto') or None,
            'finitura': part.doc.meta.get('finitura') or None}


def bom(asm: Assembly, parts: dict, gruppi: bool = False) -> list:
    """Una riga per file di pezzo: quante copie, peso, spessore e sviluppo della lamiera. I pezzi dentro i
    sottoassiemi si contano coi loro (e finiscono anche in parts, per chi cerca il pezzo di una riga); con gruppi il
    sottoassieme resta una riga sola ('sottoassieme': True) con i suoi pezzi in 'figli'."""
    righe: dict = {}
    if gruppi:
        for i in asm.instances:
            part = parts.get(i['file'])
            if part is None:
                continue
            r = righe.get(i['file'])
            if r is None:
                r = righe[i['file']] = _riga(part)
                if part.sotto is not None:
                    sotto = {str(c[0].path): c[0] for c in part.figli}
                    r.update(sottoassieme=True, figli=bom(part.sotto, sotto, gruppi=True))
                    parts.update({k: v for k, v in sotto.items() if k not in parts})
            r['qty'] += 1
    else:
        for part, _, _, _ in foglie(asm, parts):
            k = str(part.path)
            parts.setdefault(k, part)
            r = righe.get(k)
            if r is None:
                r = righe[k] = _riga(part)
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


def interferences(asm: Assembly, parts: dict, tol: float = 1e-3, forme: bool = False) -> list:
    """Le coppie di istanze che si compenetrano, con il volume in comune (mm³); con forme anche il pezzo in comune
    ('forma', nel mondo: per farlo vedere in rosso)."""
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
            c, v = _in_comune(sa, sb)
            if c is not None and v > tol:
                out.append({'a': ia, 'b': ib, 'volume': v, **({'forma': c} if forme else {})})
    return out


def _in_comune(sa, sb):
    """Il pezzo in comune tra due forme (quello che entra), col volume in mm³; (None, 0) se il conto non riesce."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    try:
        c = sa._bool_op((sa,), (sb,), BRepAlgoAPI_Common())
        return c, c.volume
    except Exception:  # noqa: BLE001
        return None, 0.0


def _forma_scelta(asm: Assembly, parts: dict, scelta: dict):
    """Il pezzo (o la sua faccia, se c'è 'face') di un'istanza, al suo posto nell'assieme."""
    import build123d as bd
    from .topology.naming import _faces_of
    i = asm.instance(scelta['inst'])
    part = parts.get(i['file'])
    if part is None:
        raise AssemblyError(f'Il pezzo di {i["id"]} non si legge.')
    s = placed_shape(part, i['R'] if i.get('R') else np.eye(3).tolist(), i.get('T') or [0, 0, 0])
    if scelta.get('face') is None:
        return s, None
    facce = _faces_of(s.wrapped)                    # stesso ordine del pezzo: lo spostamento non cambia le facce
    k = int(scelta['face'])
    if not 0 <= k < len(facce):
        raise AssemblyError('Clicca una faccia del pezzo.')
    return s, bd.Face(facce[k])


def gioco(asm: Assembly, parts: dict, a: dict, b: dict, tol: float = 1e-3) -> dict:
    """Il gioco tra due pezzi dell'assieme (idea da SolidCraft, inspect.clearance): la distanza più corta e i due
    punti dove si misura, tra i pezzi interi e, se si sono cliccate, tra le due facce. Se i pezzi si toccano o uno
    entra nell'altro lo dice (col pezzo in comune, lo stesso conto delle interferenze).
    'pezzi': {'mm', 'p', 'q', 'stato': 'gioco' | 'tocca' | 'dentro', 'volume', 'forma'}; 'facce': {'mm', 'p', 'q'}."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    if a['inst'] == b['inst']:
        raise AssemblyError('Scegli due pezzi diversi.')
    sa, fa = _forma_scelta(asm, parts, a)
    sb, fb = _forma_scelta(asm, parts, b)

    def dist(x, y):
        d = BRepExtrema_DistShapeShape(x.wrapped, y.wrapped)
        if not d.IsDone() or d.NbSolution() < 1:
            raise AssemblyError('Non riesco a misurare la distanza tra questi due pezzi.')
        p, q = d.PointOnShape1(1), d.PointOnShape2(1)
        return {'mm': d.Value(), 'p': [p.X(), p.Y(), p.Z()], 'q': [q.X(), q.Y(), q.Z()]}

    pezzi = dist(sa, sb)
    pezzi['stato'] = 'gioco' if pezzi['mm'] > tol else 'tocca'
    if pezzi['stato'] == 'tocca':
        c, v = _in_comune(sa, sb)
        if c is not None and v > tol:
            pezzi.update(stato='dentro', volume=v, forma=c)
    out = {'pezzi': pezzi}
    if fa is not None and fb is not None:
        fc = dist(fa, fb)
        # due facce parallele hanno il gioco uguale dappertutto: la linea dove si è cliccato, non in un angolo
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.gp import gp_Pnt
        for pt, altra, giro in ((a.get('pt'), fb, False), (b.get('pt'), fa, True)):
            if pt is None:
                continue
            v = BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float, pt))).Vertex()
            d = BRepExtrema_DistShapeShape(v, altra.wrapped)
            if d.IsDone() and d.NbSolution() and abs(d.Value() - fc['mm']) < 1e-4:
                q = d.PointOnShape2(1)
                p, q = [float(x) for x in pt], [q.X(), q.Y(), q.Z()]
                fc.update(p=q if giro else p, q=p if giro else q)
                break
        out['facce'] = fc
    return out


# ------------------------------------------------------------------------------------------- pezzi bloccati insieme
# 05/11 (da SolidCraft, joint.rigid_group): due o più pezzi «Bloccati insieme» si muovono come uno solo, anche negli
# accoppiamenti, senza farne un sottoassieme (la distinta resta com'è). Nel file solo l'elenco dei pezzi del gruppo:
# come stanno tra loro lo dicono le loro posizioni salvate (si muovono sempre tutti insieme, e restano così).
class _Corpi(Assembly):
    """L'assieme visto dal risolutore: un gruppo bloccato è un pezzo solo (il suo primo pezzo, il «capo»)."""
    tutte: dict = None

    def instance(self, iid: str) -> dict:
        if self.tutte and iid in self.tutte:
            return self.tutte[iid]
        return super().instance(iid)


def capi_dei_gruppi(asm: Assembly) -> dict:
    """{id del pezzo: id del capo del suo gruppo} per i pezzi bloccati insieme (il capo: il primo nell'assieme).
    Un gruppo con meno di due pezzi che ci sono ancora non conta; un pezzo sta in un gruppo solo (il primo)."""
    ordine = {i['id']: k for k, i in enumerate(asm.instances)}
    capo = {}
    for g in getattr(asm, 'gruppi', None) or []:
        dentro = sorted({x for x in g.get('pezzi') or [] if x in ordine and x not in capo}, key=ordine.get)
        if len(dentro) < 2:
            continue
        for x in dentro:
            capo[x] = dentro[0]
    return capo


def gruppo_di(asm: Assembly, iid: str) -> dict | None:
    """Il gruppo bloccato del pezzo (quello che conta), o None."""
    capo = capi_dei_gruppi(asm).get(iid)
    if capo is None:
        return None
    return next(g for g in asm.gruppi if capo in (g.get('pezzi') or []) and iid in (g.get('pezzi') or []))


def compagni(asm: Assembly, iid: str) -> list:
    """I pezzi che si muovono insieme a iid (lui compreso), nell'ordine dell'assieme."""
    capo = capi_dei_gruppi(asm)
    c = capo.get(iid)
    return [i['id'] for i in asm.instances if c is not None and capo.get(i['id']) == c] or [iid]


def _solve_gruppi(asm: Assembly, parts: dict) -> dict:
    capo = capi_dei_gruppi(asm)
    ist = {i['id']: i for i in asm.instances}
    rel = {}
    for x, c in capo.items():
        if x != c:
            RL, TL = _R(ist[c]), _T(ist[c])
            rel[x] = (RL.T @ _R(ist[x]), RL.T @ (_T(ist[x]) - TL))
    nome_g = {}
    for g in asm.gruppi:
        for x in g.get('pezzi') or []:
            if x in capo:
                nome_g.setdefault(capo[x], g.get('name') or 'Gruppo')
    corpi = []
    for i in asm.instances:
        if capo.get(i['id'], i['id']) != i['id']:
            continue
        d = dict(i)
        if i['id'] in nome_g:
            d['name'] = nome_g[i['id']]
            if any(ist[x].get('fixed') for x, c in capo.items() if c == i['id']):
                d['fixed'] = True
        corpi.append(d)

    def rif(r):
        x = r['inst']
        if x not in rel:
            return r
        return {**r, 'inst': capo[x], '_da': x, '_rel': rel[x]}
    mates = []
    for m in asm.mates:
        a, b = m['a']['inst'], m['b']['inst']
        if capo.get(a, a) == capo.get(b, b):
            continue                                 # dentro lo stesso gruppo: stanno già insieme
        v = {**m, **{k: rif(m[k]) for k in CHIAVI if m.get(k)}}
        if m['type'] == 'blocca':
            Rr, Tr = np.array(m['rel_R'], dtype=float), np.array(m['rel_T'], dtype=float)
            if a in rel:                             # A = capo ∘ relA
                RrA, TrA = rel[a]
                Rr, Tr = RrA @ Rr, RrA @ Tr + TrA
            if b in rel:                             # B = capo ∘ relB
                RrB, TrB = rel[b]
                Rr = Rr @ RrB.T
                Tr = Tr - Rr @ TrB
            v['rel_R'], v['rel_T'] = Rr.tolist(), Tr.tolist()
        mates.append(v)
    vista = _Corpi(asm.name, corpi, mates, asm.path)
    vista.tutte = ist
    pv = solve(vista, parts)
    asm.warnings = vista.warnings
    pose = {}
    for i in asm.instances:
        RL, TL = pv[capo.get(i['id'], i['id'])]
        if i['id'] in rel:
            Rr, Tr = rel[i['id']]
            R, T = RL @ Rr, RL @ Tr + TL
        else:
            R, T = RL, TL
        i['R'], i['T'] = R.tolist(), T.tolist()
        pose[i['id']] = (R, T)
    return pose
