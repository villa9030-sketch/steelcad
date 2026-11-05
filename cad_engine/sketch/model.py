"""Sketch 2D parametrico: soli dati (entità, vincoli, quote), serializzabili in JSON.

Le coordinate salvate sono quelle disegnate dall'utente: il risolutore parte
da lì ogni volta e non le riscrive (niente deriva, undo pulito).

Id stabili: punti P1.., linee L1.., cerchi C1.., archi A1.., ellissi EL1.., curve libere SP1.., vincoli K1..,
quote D1... Il punto "O" è l'origine, sempre presente e fissa.

05/11: ellissi (centro, fine dell'asse grande, fine dell'asse piccolo; anche archi di ellisse) e curve libere che
passano per i punti cliccati. Tutti i loro punti sono punti normali dello sketch (ci si aggancia, si quotano).
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
    'on_line': 'sulla linea',
    'rotated': 'girato attorno al centro',    # [punto, copia, centro], 'value' = angolo in gradi (serie attorno a un centro)
}
DIMENSIONS = {
    'distance': 'distanza', 'length': 'lunghezza', 'hdistance': 'distanza orizzontale',
    'vdistance': 'distanza verticale', 'angle': 'angolo', 'diameter': 'diametro', 'radius': 'raggio',
    'pldistance': 'distanza dalla linea',
    'major_axis': 'asse grande', 'minor_axis': 'asse piccolo',     # di un'ellisse: tutto l'asse, da parte a parte
    'tilt': 'inclinazione',                                          # dell'asse grande di un'ellisse, dall'orizzontale
}

# le chiavi con cui un'entità usa i punti (più 'points', la lista dei punti di una curva libera)
CHIAVI_PUNTI = ('a', 'b', 'center', 'start', 'end', 'major', 'minor')


def punti_entita(e: dict) -> list:
    """Tutti i punti usati da un'entità (linea, arco, cerchio, ellisse, curva libera, testo)."""
    out = [e[k] for k in CHIAVI_PUNTI if k in e]
    return out + list(e.get('points') or [])


def rimappa_punti(e: dict, mappa) -> None:
    """Cambia i punti di un'entità secondo la mappa (dizionario o funzione), sul posto."""
    f = mappa if callable(mappa) else (lambda p: mappa.get(p, p))
    for k in CHIAVI_PUNTI:
        if k in e:
            e[k] = f(e[k])
    if 'points' in e:
        e['points'] = [f(p) for p in e['points']]


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
        # l'ultimo numero dato si ricorda: rifare il massimo su tutte le chiavi a ogni elemento nuovo costava
        # milioni di confronti in una serie grande. Vale finché l'ultimo id dato c'è ancora e il successivo è
        # libero (dopo un annulla o un caricamento si ricalcola)
        memo = self.__dict__.setdefault('_ultimi_id', {})
        chiave = (prefix, id(where))
        n = memo.get(chiave)
        if n is None or f'{prefix}{n}' not in where or f'{prefix}{n + 1}' in where:
            n = max((int(k[len(prefix):]) for k in where if k.startswith(prefix) and k[len(prefix):].isdigit()),
                    default=0)
        memo[chiave] = n + 1
        return f'{prefix}{n + 1}'

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
        nomi = {'point': 'punto', 'line': 'linea', 'circle': 'cerchio', 'arc': 'arco', 'text': 'testo',
                'ellipse': 'ellisse', 'spline': 'curva libera'}
        if eid == ORIGIN:
            return "l'origine"
        # 05/11: niente nomi interni («punto P6»): dove sta o quanto è lungo, come lo vede l'officina
        try:
            k = e.get('kind')
            if k == 'point':
                return f"punto in {fmt_mm(e['x'])}; {fmt_mm(e['y'])}"
            if k == 'line':
                a, b = self.entities[e['a']], self.entities[e['b']]
                return f"linea lunga {fmt_mm(math.hypot(b['x'] - a['x'], b['y'] - a['y']))}"
            if k == 'circle':
                return f"cerchio Ø{fmt_mm(2 * e['r'])}"
            if k == 'arc' and isinstance(e.get('r'), (int, float)):
                return f"arco R{fmt_mm(e['r'])}"
            if k == 'ellipse':
                c, m, n = (self.entities[e[x]] for x in ('center', 'major', 'minor'))
                a2 = 2 * math.hypot(m['x'] - c['x'], m['y'] - c['y'])
                b2 = 2 * math.hypot(n['x'] - c['x'], n['y'] - c['y'])
                return f"{'arco di ellisse' if 'start' in e else 'ellisse'} {fmt_mm(a2)}×{fmt_mm(b2)}"
            if k == 'spline':
                return f"curva libera per {len(e['points'])} punti"
        except (KeyError, TypeError):
            pass
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

    def text(self, anchor, testo: str, h: float, angolo: float = 0.0, stencil: str | None = None) -> str:
        """Un testo da marcare: il punto in basso a sinistra (anchor), il testo, l'altezza delle maiuscole, l'angolo."""
        if not str(testo).strip():
            raise SketchError('Scrivi il testo da marcare.')
        if h <= 0:
            raise SketchError('L’altezza del testo deve essere maggiore di zero.')
        tid = self._new_id('T', self.entities)
        self.entities[tid] = {'kind': 'text', 'center': self._pt(anchor), 'text': str(testo), 'h': float(h),
                              'angle': float(angolo)}
        if stencil:
            self.entities[tid]['stencil'] = stencil          # da tagliare: contorni chiusi (non da marcare)
        return tid

    def arc(self, center, start, end, *, construction: bool = False) -> str:
        """Arco in senso antiorario da start a end."""
        aid = self._new_id('A', self.entities)
        self.entities[aid] = {'kind': 'arc', 'center': self._pt(center), 'start': self._pt(start),
                              'end': self._pt(end), 'construction': construction}
        return aid

    def ellipse(self, center, major, b: float, *, start=None, end=None, construction: bool = False) -> str:
        """Ellisse: centro, fine di un asse (punto o [x, y]) e metà dell'altro asse. Il più lungo diventa l'asse
        grande. Con start e end (punti o [x, y], portati sull'ellisse) è l'arco di ellisse in senso antiorario."""
        pc = self._pt(center)
        cx, cy = self.entities[pc]['x'], self.entities[pc]['y']
        if isinstance(major, str):
            mx, my = self.entities[self._pt(major)]['x'], self.entities[self._pt(major)]['y']
        else:
            mx, my = float(major[0]), float(major[1])
        a = math.hypot(mx - cx, my - cy)
        b = float(b)
        if a <= 0 or b <= 0:
            raise SketchError('Un’ellisse ha bisogno di due assi più lunghi di zero.')
        if abs(a - b) < 1e-6 * max(a, b):
            raise SketchError('Con i due assi uguali è un cerchio: usa Cerchio.')
        ux, uy = (mx - cx) / a, (my - cy) / a
        if b > a:                                  # l'asse dato è il piccolo: il grande sta a 90°
            if isinstance(major, str):
                raise SketchError('Il punto scelto deve stare sull’asse grande dell’ellisse.')
            ux, uy, a, b = -uy, ux, b, a
            pm = self.point(cx + a * ux, cy + a * uy)
        else:
            pm = major if isinstance(major, str) else self.point(mx, my)
        pn = self.point(cx - b * uy, cy + b * ux)
        eid = self._new_id('EL', self.entities)
        ent = {'kind': 'ellipse', 'center': pc, 'major': pm, 'minor': pn, 'construction': construction}
        if (start is None) != (end is None):
            raise SketchError('Per un arco di ellisse servono il punto di partenza e quello di arrivo.')
        if start is not None:
            from .curve import ellisse_parametro, ellisse_punto
            ang = math.atan2(uy, ux)

            def sull_ellisse(p):
                if isinstance(p, str):
                    return self._pt(p)
                u = ellisse_parametro((cx, cy), a, b, ang, (float(p[0]), float(p[1])))
                return self.point(*ellisse_punto((cx, cy), a, b, ang, u))
            ent['start'], ent['end'] = sull_ellisse(start), sull_ellisse(end)
            if ent['start'] == ent['end']:
                raise SketchError('L’arco di ellisse ha bisogno di due punti diversi.')
        self.entities[eid] = ent
        return eid

    def spline(self, pts, *, closed: bool = False, construction: bool = False) -> str:
        """Curva libera che passa per i punti (punti esistenti o [x, y]), aperta o chiusa."""
        ids = [self._pt(p) for p in pts]
        ids = [p for i, p in enumerate(ids) if i == 0 or p != ids[i - 1]]
        if closed and len(ids) > 1 and ids[0] == ids[-1]:
            ids.pop()
        if len(ids) < (3 if closed else 2):
            raise SketchError('Una curva libera ha bisogno di almeno ' + ('tre punti per chiudersi.' if closed else 'due punti.'))
        sid = self._new_id('SP', self.entities)
        self.entities[sid] = {'kind': 'spline', 'points': ids, 'closed': bool(closed), 'construction': construction}
        return sid

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
    def to_dict(self, copia: bool = True) -> dict:
        # copia=False: senza copiare entità e vincoli, solo per farne il testo JSON (storia, impronte; 03/11)
        cp = copy.deepcopy if copia else (lambda x: x)
        return {'id': self.id, 'type': 'sketch', 'name': self.name, 'plane': self.plane,
                'entities': cp(self.entities), 'constraints': cp(self.constraints)}

    @classmethod
    def from_dict(cls, d: dict) -> 'Sketch':
        s = cls(id=d['id'], name=d.get('name', ''), plane=d.get('plane', 'XY'),
                entities=copy.deepcopy(d.get('entities') or {}), constraints=copy.deepcopy(d.get('constraints') or {}))
        if isinstance(s.plane, str) and s.plane not in PLANES:
            raise SketchError(f'Il piano "{s.plane}" non esiste: usa XY, XZ o YZ, oppure una faccia piana.')
        return s
