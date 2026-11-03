"""Cose comuni alle feature: contesto di costruzione, controlli sul risultato."""
from __future__ import annotations

from dataclasses import dataclass, field

from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer

from ..errors import FeatureError
from ..expressions import evaluate
from ..topology import NamedShape
from ..units import cap


@dataclass
class Context:
    params: dict
    body: NamedShape | None          # il solido prima di questa feature
    sketches: dict = field(default_factory=dict)   # id sketch -> (SolvedSketch, Profile)
    describe: object = None                        # nome faccia -> testo per l'utente

    def __post_init__(self):
        if self.describe is None:
            from ..topology import describe
            self.describe = lambda n: f'"{describe(n)}"'

    def value(self, fdef: dict, key: str, what: str) -> float:
        if key not in fdef:
            raise FeatureError(f'Manca {what}.', feature=fdef['id'])
        return evaluate(fdef[key], self.params, what=f'{what} di {label(fdef)}')

    def sketch(self, fdef: dict, key: str = 'sketch'):
        sid = fdef.get(key)
        if sid not in self.sketches:
            raise FeatureError(f'{cap(label(fdef))} usa lo sketch "{sid}", che non esiste o non è '
                               'costruibile.', feature=fdef['id'])
        return self.sketches[sid]


def label(fdef: dict) -> str:
    nomi = {'extrude': 'estrusione', 'revolve': 'rivoluzione', 'hole': 'foro', 'fillet': 'raccordo', 'chamfer': 'smusso', 'sheet': 'lamiera', 'sheet_shape': 'forma di lamiera', 'sheet_cut': 'taglio di lamiera'}
    base = nomi.get(fdef.get('type'), fdef.get('type', 'feature'))
    return f'{base} "{fdef["name"]}"' if fdef.get('name') else f'{base} {fdef["id"]}'


_VOLUMI: dict = {}       # 29/10: la stessa forma misurata più volte (prima e dopo ogni taglio della catena)


def volume(shape) -> float:
    k = hash(shape)
    gia = _VOLUMI.get(k)
    if gia is not None and gia[0].IsSame(shape):
        return gia[1]
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    v = props.Mass()
    if len(_VOLUMI) > 400:
        _VOLUMI.clear()
    _VOLUMI[k] = (shape, v)
    return v


def n_solids(shape) -> int:
    n, ex = 0, TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        n += 1
        ex.Next()
    return n


def check_solid(shape, fdef: dict) -> None:
    if shape is None or shape.IsNull():
        raise FeatureError(f'{cap(label(fdef))} non ha prodotto geometria.', feature=fdef['id'])
    # il controllo sui core del processore (03/11): stesso esito, la metà del tempo su un pezzo con 1000 facce
    if not BRepCheck_Analyzer(shape, True, True).IsValid():
        raise FeatureError(f'{cap(label(fdef))} ha prodotto un solido non valido. Di solito succede con '
                           'misure al limite (pareti di spessore quasi zero): controlla le quote.',
                           feature=fdef['id'])
    if volume(shape) <= 1e-9:
        raise FeatureError(f'{cap(label(fdef))} ha prodotto un solido vuoto.', feature=fdef['id'])


def unisci_parti(parti: list) -> NamedShape:
    """I solidi dei contorni dello sketch (o dei fori) uniti in una volta sola, con i loro nomi (03/11: uniti uno alla volta, le
    15 lettere di una scritta erano 14 unioni una dopo l'altra, più di un secondo)."""
    if len(parti) == 1:
        return parti[0]
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.collections import List_TopoDS_Shape
    argomenti, utensili = List_TopoDS_Shape(), List_TopoDS_Shape()
    argomenti.Append(parti[0].shape)
    for p in parti[1:]:
        utensili.Append(p.shape)
    fu = BRepAlgoAPI_Fuse()
    fu.SetArguments(argomenti)
    fu.SetTools(utensili)
    fu.Build()
    nomi: dict[str, list] = {}                  # i nomi di tutti, nello stesso ordine di prima (prima il primo, poi gli altri)
    for p in parti:
        for k, fs in p.names.items():
            nomi.setdefault(k, []).extend(fs)
    return NamedShape(parti[0].shape, nomi).after(fu, fu.Shape())
