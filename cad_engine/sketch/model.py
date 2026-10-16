"""Sketch 2D parametrico: soli dati (entità, vincoli, quote), serializzabili in JSON.

Le coordinate salvate sono quelle disegnate dall'utente: il risolutore parte
da lì ogni volta e non le riscrive (niente deriva, undo pulito).

Id stabili: punti P1.., linee L1.., cerchi C1.., archi A1.., vincoli K1..,
quote D1... Il punto "O" è l'origine, sempre presente e fissa.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

from ..errors import SketchError
from ..units import fmt_mm

ORIGIN = 'O'
PLANES = ('XY', 'XZ', 'YZ')

# tipi di vincolo geometrico e di quota, con nome leggibile
CONSTRAINTS = {
    'coincident': 'coincidente', 'horizontal': 'orizzontale', 'vertical': 'verticale',
    'parallel': 'parallelo', 'perpendicular': 'perpendicolare', 'tangent': 'tangente',
    'equal': 'uguale', 'concentric': 'concentrico', 'symmetric': 'simmetrico', 'fix': 'fisso',
}
DIMENSIONS = {
    'distance': 'distanza', 'length': 'lunghezza', 'hdistance': 'distanza orizzontale',
    'vdistance': 'distanza verticale', 'angle': 'angolo', 'diameter': 'diametro', 'radius': 'raggio',
}


@dataclass
class Sketch:
    id: str
    name: str = ''
    plane: object = 'XY'        # 'XY' | 'XZ' | 'YZ' | {'face': '<nome faccia>'}
    entities: dict = field(default_factory=dict)      # id -> {'kind': ..., ...}
    constraints: dict = field(default_factory=dict)   # id -> {'type': ..., 'refs': [...], 'value': ...}

    def __post_init__(self):
        if ORIGIN not in self.entities:
            self.entities = {ORIGIN: {'kind': 'point', 'x': 0.0, 'y': 0.0, 'fixed': True}, **self.entities}

    # ---------------------------------------------------------------- id
    def _new_id(self, prefix: str, where: dict) -> str:
        n = 1 + max((int(k[len(prefix):]) for k in where if k.startswith(prefix) and k[len(prefix):].isdigit()),
                    default=0)
        return f'{prefix}{n}'

    def kind(self, eid: str) -> str:
        if eid not in self.entities:
            raise SketchError(f'Nello sketch "{self.label()}" non c\'è l\'elemento {eid}.')
        return self.entities[eid]['kind']

    def label(self) -> str:
        return self.name or self.id

    def describe(self, eid: str) -> str:
        e = self.entities.get(eid, {})
        if e.get('label'):
            return e['label']
        nomi = {'point': 'punto', 'line': 'linea', 'circle': 'cerchio', 'arc': 'arco'}
        if eid == ORIGIN:
            return "l'origine"
        return f"{nomi.get(e.get('kind'), 'elemento')} {eid}"

    # ---------------------------------------------------------- geometria
    def _pt(self, p) -> str:
        if isinstance(p, str):
            if self.kind(p) != 'point':
                raise SketchError(f'{p} non è un punto.')
            return p
        x, y = p
        return self.point(x, y)

    def point(self, x: float, y: float, *, construction: bool = False) -> str:
        pid = self._new_id('P', self.entities)
        self.entities[pid] = {'kind': 'point', 'x': float(x), 'y': float(y), 'construction': construction}
        return pid

    def line(self, a, b, *, construction: bool = False, label: str | None = None) -> str:
        pa, pb = self._pt(a), self._pt(b)
        if pa == pb:
            raise SketchError('Una linea ha bisogno di due punti diversi.')
        lid = self._new_id('L', self.entities)
        self.entities[lid] = {'kind': 'line', 'a': pa, 'b': pb, 'construction': construction}
        if label:
            self.entities[lid]['label'] = label
        return lid

    def polyline(self, pts, *, closed: bool = False) -> list[str]:
        ids = [self._pt(p) for p in pts]
        if closed:
            ids.append(ids[0])
        return [self.line(ids[i], ids[i + 1]) for i in range(len(ids) - 1)]

    def rectangle(self, x0: float, y0: float, x1: float, y1: float) -> dict:
        """Rettangolo con lati orizzontali/verticali. Gli angoli sono punti condivisi."""
        xa, xb = sorted((x0, x1))
        ya, yb = sorted((y0, y1))
        if xb - xa <= 0 or yb - ya <= 0:
            raise SketchError('Il rettangolo ha bisogno di larghezza e altezza maggiori di zero.')
        c = [self.point(xa, ya), self.point(xb, ya), self.point(xb, yb), self.point(xa, yb)]
        nomi = ('lato sotto', 'lato destro', 'lato sopra', 'lato sinistro')
        lati = [self.line(c[i], c[(i + 1) % 4], label=nomi[i]) for i in range(4)]
        self.constrain('horizontal', lati[0], auto=True)
        self.constrain('vertical', lati[1], auto=True)
        self.constrain('horizontal', lati[2], auto=True)
        self.constrain('vertical', lati[3], auto=True)
        return {'lines': lati, 'corners': c, 'bottom': lati[0], 'right': lati[1], 'top': lati[2], 'left': lati[3]}

    def circle(self, center, r: float, *, construction: bool = False) -> str:
        if r <= 0:
            raise SketchError('Il raggio di un cerchio deve essere maggiore di zero.')
        cid = self._new_id('C', self.entities)
        self.entities[cid] = {'kind': 'circle', 'center': self._pt(center), 'r': float(r), 'construction': construction}
        return cid

    def arc(self, center, start, end, *, construction: bool = False) -> str:
        """Arco in senso antiorario da start a end."""
        aid = self._new_id('A', self.entities)
        self.entities[aid] = {'kind': 'arc', 'center': self._pt(center), 'start': self._pt(start),
                              'end': self._pt(end), 'construction': construction}
        return aid

    def slot(self, c1, c2, r: float) -> dict:
        """Asola: due semicerchi di raggio r con centri c1, c2 e due tratti tangenti."""
        (x1, y1), (x2, y2) = c1, c2
        lungo = math.hypot(x2 - x1, y2 - y1)
        if lungo <= 0 or r <= 0:
            raise SketchError("L'asola ha bisogno di due centri diversi e di un raggio maggiore di zero.")
        ux, uy = (x2 - x1) / lungo, (y2 - y1) / lungo
        nx, ny = -uy, ux
        k1, k2 = self.point(x1, y1, construction=True), self.point(x2, y2, construction=True)
        a = self.point(x1 + nx * r, y1 + ny * r)
        b = self.point(x2 + nx * r, y2 + ny * r)
        c = self.point(x2 - nx * r, y2 - ny * r)
        d = self.point(x1 - nx * r, y1 - ny * r)
        arc2 = self.arc(k2, c, b)       # semicerchio dalla parte di c2
        arc1 = self.arc(k1, a, d)       # semicerchio dalla parte di c1
        top, bottom = self.line(a, b), self.line(c, d)
        for ln in (top, bottom):
            self.constrain('tangent', ln, arc1, auto=True)
            self.constrain('tangent', ln, arc2, auto=True)
        self.constrain('equal', arc1, arc2, auto=True)
        return {'arcs': [arc1, arc2], 'lines': [top, bottom], 'centers': [k1, k2]}

    def move_point(self, pid: str, x: float, y: float) -> None:
        if pid == ORIGIN:
            raise SketchError("L'origine non si può spostare.")
        if self.kind(pid) != 'point':
            raise SketchError(f'{pid} non è un punto.')
        self.entities[pid]['x'], self.entities[pid]['y'] = float(x), float(y)

    # ------------------------------------------------------------ vincoli
    def constrain(self, ctype: str, *refs: str, auto: bool = False) -> str:
        if ctype not in CONSTRAINTS:
            raise SketchError(f'Vincolo "{ctype}" sconosciuto.')
        for r in refs:
            self.kind(r)
        kid = self._new_id('K', self.constraints)
        self.constraints[kid] = {'type': ctype, 'refs': list(refs), 'auto': auto}
        return kid

    def dimension(self, dtype: str, *refs: str, value) -> str:
        if dtype not in DIMENSIONS:
            raise SketchError(f'Quota "{dtype}" sconosciuta.')
        for r in refs:
            self.kind(r)
        did = self._new_id('D', self.constraints)
        self.constraints[did] = {'type': dtype, 'refs': list(refs), 'value': value}
        return did

    def set_value(self, did: str, value) -> None:
        c = self.constraints.get(did)
        if not c or c['type'] not in DIMENSIONS:
            raise SketchError(f'Nello sketch "{self.label()}" non c\'è la quota {did}.')
        c['value'] = value

    def remove(self, cid: str) -> None:
        if cid not in self.constraints:
            raise SketchError(f'Nello sketch "{self.label()}" non c\'è il vincolo {cid}.')
        del self.constraints[cid]

    def describe_constraint(self, cid: str, value: float | None = None) -> str:
        c = self.constraints[cid]
        oggetti = ' e '.join(self.describe(r) for r in c['refs'])
        if c['type'] in DIMENSIONS:
            v = c['value'] if value is None else value
            testo = f'{fmt_mm(v)}°' if c['type'] == 'angle' and isinstance(v, (int, float)) else (
                fmt_mm(v) if isinstance(v, (int, float)) else str(v))
            if c['type'] == 'diameter' and isinstance(v, (int, float)):
                testo = 'Ø' + testo
            return f'la quota {testo} ({DIMENSIONS[c["type"]]} di {oggetti})'
        return f'il vincolo {CONSTRAINTS[c["type"]]} su {oggetti}'

    # --------------------------------------------------------------- JSON
    def to_dict(self) -> dict:
        return {'id': self.id, 'type': 'sketch', 'name': self.name, 'plane': self.plane,
                'entities': copy.deepcopy(self.entities), 'constraints': copy.deepcopy(self.constraints)}

    @classmethod
    def from_dict(cls, d: dict) -> 'Sketch':
        s = cls(id=d['id'], name=d.get('name', ''), plane=d.get('plane', 'XY'),
                entities=copy.deepcopy(d.get('entities') or {}), constraints=copy.deepcopy(d.get('constraints') or {}))
        if isinstance(s.plane, str) and s.plane not in PLANES:
            raise SketchError(f'Il piano "{s.plane}" non esiste: usa XY, XZ o YZ, oppure una faccia piana.')
        return s
