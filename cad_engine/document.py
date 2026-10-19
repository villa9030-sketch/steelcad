"""Il modello parametrico di una parte: parametri, feature in ordine, ricostruzione con cache.

La definizione (parametri + feature) è JSON puro e si salva nel file
.steelcad. La geometria non si salva: si ricostruisce, e la cache evita di
rifare le feature che non sono cambiate (impronta = definizione + parametri
usati + impronta di ciò da cui dipende).
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime

from . import materials
from .errors import FeatureError, SketchError, SteelCADError
from .expressions import evaluate, names_in
from .features import BUILDERS, VALUE_FIELDS
from .features.base import Context
from .sketch import Sketch, solve
from .sketch import profile as profile_mod
from .sketch.model import DIMENSIONS
from .topology import NamedShape

FORMAT_VERSION = 1
PREFIX = {'sketch': 'S', 'extrude': 'E', 'hole': 'H', 'fillet': 'F', 'chamfer': 'CH', 'structure': 'ST', 'sheet': 'SM', 'sheet_shape': 'FM', 'sheet_cut': 'TG', 'sheet_form': 'FM'}
NOMI = {'sketch': 'Sketch', 'extrude': 'Estrusione', 'hole': 'Foro', 'fillet': 'Raccordo', 'chamfer': 'Smusso',
        'structure': 'Struttura', 'sheet': 'Lamiera', 'sheet_shape': 'Forma', 'sheet_cut': 'Taglio', 'sheet_form': 'Forma'}


@dataclass
class FeatureResult:
    id: str
    type: str
    ok: bool
    message: str = ''
    from_cache: bool = False
    sketch_status: dict | None = None

    def to_dict(self) -> dict:
        return {'id': self.id, 'type': self.type, 'ok': self.ok, 'message': self.message,
                'from_cache': self.from_cache, 'sketch_status': self.sketch_status}


@dataclass
class RebuildResult:
    features: list = field(default_factory=list)
    body: NamedShape | None = None
    structures: list = field(default_factory=list)     # StructureResult
    rebuilt: int = 0
    cached: int = 0
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return all(f.ok for f in self.features)

    @property
    def errors(self) -> list:
        return [f for f in self.features if not f.ok]


class Document:
    def __init__(self, name: str = 'Parte', material: str = 'S235'):
        materials.get(material)
        now = datetime.now().isoformat(timespec='seconds')
        self.meta = {'name': name, 'created': now, 'modified': now}
        self.material = material
        self.parameters: dict[str, object] = {}
        self.features: list = []          # Sketch oppure dict
        self._cache: dict[str, object] = {}
        self.last: RebuildResult | None = None
        self._sketch_results: dict = {}

    # ============================================================ modifica
    def _new_id(self, ftype: str) -> str:
        p = PREFIX[ftype]
        usati = [self._fid(f) for f in self.features]
        n = 1 + max((int(u[len(p):]) for u in usati if u.startswith(p) and u[len(p):].isdigit()), default=0)
        return f'{p}{n}'

    @staticmethod
    def _fid(f) -> str:
        return f.id if isinstance(f, Sketch) else f['id']

    def add_sketch(self, plane='XY', name: str = '') -> Sketch:
        sk = Sketch(self._new_id('sketch'), name=name, plane=plane)
        self.features.append(sk)
        return sk

    def add_feature(self, ftype: str, name: str = '', **fields) -> str:
        if ftype not in BUILDERS and ftype != 'structure':
            raise FeatureError(f'Tipo di feature "{ftype}" sconosciuto.')
        fid = self._new_id(ftype)
        self.features.append({'id': fid, 'type': ftype, 'name': name, **fields})
        return fid

    def feature(self, fid: str):
        for f in self.features:
            if self._fid(f) == fid:
                return f
        raise SteelCADError(f'Nel progetto non c\'è "{fid}".', code='feature_sconosciuta')

    def sketch(self, sid: str) -> Sketch:
        f = self.feature(sid)
        if not isinstance(f, Sketch):
            raise SteelCADError(f'"{sid}" non è uno sketch.')
        return f

    def edit_feature(self, fid: str, **fields) -> None:
        f = self.feature(fid)
        if isinstance(f, Sketch):
            raise SteelCADError('Per uno sketch si cambiano entità e quote, non i campi.')
        f.update(fields)

    def set_parameter(self, name: str, value) -> None:
        if not name.isidentifier():
            raise SteelCADError(f'"{name}" non va bene come nome di parametro: usa lettere, cifre e _ '
                                '(senza spazi, non all\'inizio una cifra).', code='parametro_non_valido')
        if name in names_in(value):
            raise SteelCADError(f'Il parametro "{name}" non può dipendere da sé stesso.')
        existed, previous = name in self.parameters, self.parameters.get(name)
        self.parameters[name] = value
        try:
            self.resolved_parameters()
        except SteelCADError:
            if existed:
                self.parameters[name] = previous
            else:
                del self.parameters[name]
            raise

    def remove_feature(self, fid: str) -> None:
        dip = [self._fid(f) for f in self.features if fid in self._deps(f)]
        if dip:
            raise SteelCADError(f'"{fid}" non si può togliere: lo usano {", ".join(dip)}.', code='in_uso')
        self.features = [f for f in self.features if self._fid(f) != fid]

    @staticmethod
    def _deps(f) -> set:
        if isinstance(f, Sketch):
            if isinstance(f.plane, dict) and 'flat' in f.plane:
                return {f.plane['flat']}
            return {f.plane['face'].split('/')[0]} if isinstance(f.plane, dict) and 'face' in f.plane else set()
        out = set()
        if f.get('sketch'):
            out.add(f['sketch'])
        if f.get('type') == 'structure':
            out |= Document._sketch_refs(f)
        for ref in f.get('edges') or []:
            out.update(n.split('/')[0] for n in ref['faces'])
        return out

    def resolved_parameters(self) -> dict[str, float]:
        """I parametri possono riferirsi ad altri parametri: si risolvono in ordine di dipendenza."""
        out, pending = {}, dict(self.parameters)
        while pending:
            progress = False
            for k, v in list(pending.items()):
                if names_in(v) <= set(out):
                    out[k] = evaluate(v, out, what=f'parametro "{k}"')
                    del pending[k]
                    progress = True
            if not progress:
                mancanti = ', '.join(sorted(pending))
                raise SteelCADError(f'I parametri {mancanti} dipendono l\'uno dall\'altro in cerchio, oppure da '
                                    'parametri che non esistono.', code='parametri_circolari')
        return out

    # ======================================================= ricostruzione
    def rebuild(self) -> RebuildResult:
        t0 = time.perf_counter()
        try:
            params = self.resolved_parameters()
        except SteelCADError as ex:
            res = RebuildResult(features=[FeatureResult('parametri', 'parameters', False, ex.message)])
            self.last = res
            return res
        res = RebuildResult()
        body: NamedShape | None = None
        body_hash = 'vuoto'
        sketch_hash: dict[str, str] = {}
        ctx_sketches: dict = {}
        blocked_by: str | None = None
        nuova_cache: dict[str, object] = {}
        usi = self._usi_degli_sketch()
        for f in self.features:
            fid = self._fid(f)
            if isinstance(f, Sketch):
                on_face = isinstance(f.plane, dict)
                # chi usa lo sketch decide se un contorno aperto è un errore: entra nella chiave della cache,
                # se no il risultato dipenderebbe da cosa c'era in memoria
                h = _hash(f.to_dict(), self._used(f, params), body_hash if on_face else '', sorted(usi.get(fid, ())))
                sketch_hash[fid] = h
                cached = self._cache.get(h)
                if cached is not None:
                    solved, prof = cached
                    res.cached += 1
                    from_cache = True
                else:
                    from_cache = False
                    try:
                        plane = self._plane(f, body)
                        solved = solve(f, params)
                        prof = None
                        if solved.status.ok_for_features:
                            try:
                                prof = profile_mod.build(solved, plane)
                            except SteelCADError as ex_aperto:
                                # le persiane si disegnano con linee aperte: per loro il contorno chiuso non serve,
                                # e così gli scheletri delle strutture; uno sketch che nessuno usa ancora è un disegno
                                # in corso (linee per una piega, una persiana…), non un errore
                                if usi.get(fid, set()) - {'louver', 'structure'}:
                                    raise
                                prof = profile_mod.Profile(plane, [], [], aperto=ex_aperto.message)
                    except SteelCADError as ex:
                        res.features.append(FeatureResult(fid, 'sketch', False, ex.message))
                        continue
                    res.rebuilt += 1
                nuova_cache[h] = (solved, prof)
                ok = prof is not None
                if ok:
                    ctx_sketches[fid] = (solved, prof)
                res.features.append(FeatureResult(fid, 'sketch', ok, (prof.aperto if prof is not None else '')
                                                  or solved.status.message, from_cache, solved.status.to_dict()))
                continue
            ftype = f['type']
            if ftype == 'structure':
                usati = sorted(self._sketch_refs(f))
                h = _hash(f, self._used(f, params), [sketch_hash.get(x, 'manca') for x in usati])
                cached = self._cache.get(h)
                if cached is not None:
                    res.cached += 1
                    st_res, from_cache = cached, True
                else:
                    try:
                        from .structures import build as build_structure
                        st_res = build_structure(f, params, ctx_sketches)
                    except SteelCADError as ex:
                        if not ex.feature:
                            ex.feature = fid
                        res.features.append(FeatureResult(fid, ftype, False, ex.message))
                        continue
                    res.rebuilt += 1
                    from_cache = False
                nuova_cache[h] = st_res
                res.structures.append(st_res)
                res.features.append(FeatureResult(fid, ftype, True, '', from_cache))
                continue
            if blocked_by:
                res.features.append(FeatureResult(fid, ftype, False,
                                                  f'Non costruita: prima va sistemato l\'errore in {blocked_by}.'))
                continue
            h = _hash(f, self._used(f, params), body_hash, sketch_hash.get(f.get('sketch'), ''))
            cached = self._cache.get(h)
            if cached is not None:
                body = cached
                res.cached += 1
                nuova_cache[h] = cached
                body_hash = h
                res.features.append(FeatureResult(fid, ftype, True, '', True))
                continue
            try:
                ctx = Context(params, body, ctx_sketches, self.describe_face)
                body = BUILDERS[ftype](f, ctx)
            except SteelCADError as ex:
                blocked_by = fid
                res.features.append(FeatureResult(fid, ftype, False, ex.message))
                continue
            except Exception as ex:  # noqa: BLE001 - errore del kernel non previsto: si dice, non si nasconde
                blocked_by = fid
                res.features.append(FeatureResult(fid, ftype, False,
                                                  f'Il kernel CAD non è riuscito a costruire {fid} ({type(ex).__name__}). '
                                                  'Segnalalo con il file del progetto.'))
                continue
            res.rebuilt += 1
            nuova_cache[h] = body
            body_hash = h
            res.features.append(FeatureResult(fid, ftype, True, ''))
        self._cache = nuova_cache
        res.body = body
        res.seconds = time.perf_counter() - t0
        self.last = res
        self._sketch_results = dict(ctx_sketches)
        return res

    def _usi_degli_sketch(self) -> dict:
        """Per ogni sketch, chi lo usa: 'louver', 'structure' o il tipo della feature."""
        usi: dict = {}
        for x in self.features:
            if isinstance(x, Sketch):
                continue
            if x.get('type') == 'structure':
                for sid in self._sketch_refs(x):
                    usi.setdefault(sid, set()).add('structure')
            if x.get('sketch'):
                tipo = 'louver' if x.get('type') == 'sheet_form' and x.get('kind') == 'louver' else x.get('type')
                usi.setdefault(x['sketch'], set()).add(tipo)
        return usi

    @staticmethod
    def _sketch_refs(f) -> set:
        out = set()
        for v in (f.get('points') or {}).values():
            if isinstance(v, dict) and v.get('sketch'):
                out.add(v['sketch'])
        for m in f.get('members') or []:
            if m.get('sketch'):
                out.add(m['sketch'])
        for k in f.get('skeletons') or []:
            if k.get('sketch'):
                out.add(k['sketch'])
        return out

    def _used(self, f, params: dict) -> dict:
        nomi: set[str] = set()
        if isinstance(f, Sketch):
            for c in f.constraints.values():
                if c['type'] in DIMENSIONS:
                    nomi |= names_in(c.get('value'))
        elif f['type'] == 'structure':
            for v in (f.get('points') or {}).values():
                for c in (v.get('offset') or [] if isinstance(v, dict) else v):
                    nomi |= names_in(c)
            for m in f.get('members') or []:
                for c in m.get('offset') or []:
                    nomi |= names_in(c)
            for k in f.get('skeletons') or []:
                for off in k.get('copies') or []:
                    for c in off:
                        nomi |= names_in(c)
            for r in (f.get('overrides') or {}).values():
                for c in r.get('offset') or []:
                    nomi |= names_in(c)
        else:
            for k in VALUE_FIELDS.get(f['type'], ()):
                nomi |= names_in(f.get(k))
            for fl in f.get('flanges') or []:             # lamiera: valori delle flange e dei loro fori
                for k in ('length', 'angle', 'gap'):
                    nomi |= names_in(fl.get(k))
                for h in fl.get('holes') or []:
                    for k in ('u', 'v', 'd'):
                        nomi |= names_in(h.get(k))
                for et in fl.get('end_tabs') or []:
                    nomi |= names_in(et.get('gap'))
            for c in f.get('corners') or []:
                nomi |= names_in(c.get('gap'))
        return {n: params.get(n) for n in sorted(nomi)}

    def _plane(self, sk: Sketch, body: NamedShape | None):
        if isinstance(sk.plane, str):
            return profile_mod.PLANES[sk.plane]
        nome = sk.plane.get('face')
        if body is None:
            raise SketchError(f'Lo sketch "{sk.label()}" sta su una faccia, ma in quel punto il pezzo non esiste.')
        if sk.plane.get('flat'):
            # sullo sviluppo: il piano dello sketch della lamiera, dove sta lo sviluppo
            sheet = getattr(body, 'sheet', None)
            if sheet is None or sheet.feature != sk.plane['flat']:
                raise SketchError(f'Lo sketch "{sk.label()}" sta sullo sviluppo di {sk.plane["flat"]}, che non c’è.')
            return sheet.plane
        from .sketch.face_plane import plane_of
        return plane_of(body, nome, sk)

    # ============================================================== utilità
    def describe_face(self, name: str) -> str:
        """'E1/lato/L1' -> 'il fianco sul lato sotto di "Piastra"'. Per i messaggi all'utente."""
        parti = name.split('/')
        try:
            f = self.feature(parti[0])
        except SteelCADError:
            return f'"{name}"'
        nome_f = f'"{f["name"]}"' if not isinstance(f, Sketch) and f.get('name') else parti[0]
        if len(parti) == 3 and parti[1] == 'lato' and not isinstance(f, Sketch) and f.get('sketch'):
            try:
                ent = self.sketch(f['sketch']).describe(parti[2])
            except SteelCADError:
                ent = parti[2]
            return f'il fianco sul {ent} di {nome_f}' if ent.startswith('lato') else f'il fianco su {ent} di {nome_f}'
        testi = {'fine': 'la faccia finale', 'inizio': 'la faccia iniziale', 'foro': 'la parete del foro',
                 'fondo': 'il fondo del foro', 'raccordo': 'il raccordo', 'smusso': 'lo smusso',
                 'sopra': 'la faccia di sopra', 'sotto': 'la faccia di sotto', 'parete': 'la parete del taglio'}
        flangia = {'esterno': 'la faccia esterna', 'interno': 'la faccia interna', 'punta': 'la punta',
                   'fianco': 'il fianco', 'piega_esterna': 'la piega (fuori)', 'piega_interna': 'la piega (dentro)',
                   'chiusura': 'la piega di chiusura'}
        if len(parti) == 3 and (parti[2] in flangia or parti[2].startswith('foro')):
            cosa = flangia.get(parti[2]) or f'il {parti[2].replace("foro", "foro ")}'
            return f'{cosa} della flangia {parti[1]} di {nome_f}'
        if len(parti) >= 2 and parti[1] in testi:
            return f'{testi[parti[1]]} di {nome_f}'
        return f'"{name}"'

    def solved_sketch(self, sid: str):
        """Lo sketch risolto dall'ultima ricostruzione (per la UI: punti, stato)."""
        if self.last is None:
            self.rebuild()
        if sid in self._sketch_results:
            return self._sketch_results[sid][0]
        return solve(self.sketch(sid), self.resolved_parameters())

    # ================================================================= JSON
    def to_dict(self) -> dict:
        return {'format': 'steelcad', 'version': FORMAT_VERSION, 'meta': dict(self.meta),
                'units': {'length': 'mm', 'angle': 'deg', 'mass': 'kg'},
                'parameters': copy.deepcopy(self.parameters), 'material': self.material,
                'features': [f.to_dict() if isinstance(f, Sketch) else copy.deepcopy(f) for f in self.features]}

    @classmethod
    def from_dict(cls, d: dict) -> 'Document':
        if d.get('format') != 'steelcad':
            raise SteelCADError('Questo file non è un progetto SteelCAD.', code='file_progetto')
        if d.get('version', 0) > FORMAT_VERSION:
            raise SteelCADError('Il progetto è stato salvato da una versione più nuova di SteelCAD: aggiorna il '
                                'programma per aprirlo.', code='file_progetto')
        doc = cls(d.get('meta', {}).get('name', 'Parte'), d.get('material', 'S235'))
        doc.meta.update(d.get('meta') or {})
        doc.parameters = dict(d.get('parameters') or {})
        doc.features = [Sketch.from_dict(f) if f.get('type') == 'sketch' else dict(f) for f in d.get('features') or []]
        return doc

    def load_definition(self, d: dict) -> None:
        """Rimette una definizione (undo/redo) tenendo la cache della geometria."""
        other = Document.from_dict(d)
        self.meta, self.material, self.parameters, self.features = (other.meta, other.material,
                                                                    other.parameters, other.features)


def _hash(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()
