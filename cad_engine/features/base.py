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
    nomi = {'extrude': 'estrusione', 'hole': 'foro', 'fillet': 'raccordo', 'chamfer': 'smusso', 'sheet': 'lamiera', 'sheet_cut': 'taglio di lamiera'}
    base = nomi.get(fdef.get('type'), fdef.get('type', 'feature'))
    return f'{base} "{fdef["name"]}"' if fdef.get('name') else f'{base} {fdef["id"]}'


def volume(shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def n_solids(shape) -> int:
    n, ex = 0, TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        n += 1
        ex.Next()
    return n


def check_solid(shape, fdef: dict) -> None:
    if shape is None or shape.IsNull():
        raise FeatureError(f'{cap(label(fdef))} non ha prodotto geometria.', feature=fdef['id'])
    if not BRepCheck_Analyzer(shape).IsValid():
        raise FeatureError(f'{cap(label(fdef))} ha prodotto un solido non valido. Di solito succede con '
                           'misure al limite (pareti di spessore quasi zero): controlla le quote.',
                           feature=fdef['id'])
    if volume(shape) <= 1e-9:
        raise FeatureError(f'{cap(label(fdef))} ha prodotto un solido vuoto.', feature=fdef['id'])
