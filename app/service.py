"""Strato applicativo: tiene il progetto aperto e risponde alla UI solo con dati JSON.

La UI chiama questi metodi (attraverso pywebview); qui non c'è niente di
grafico e niente di OpenCascade esposto all'esterno.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cad_engine import History, SteelCADError, project_io, templates  # noqa: E402
from cad_engine.analysis import properties  # noqa: E402
from cad_engine.bom import bom, total_kg  # noqa: E402
from cad_engine.document import Document  # noqa: E402
from cad_engine.exporters import dxf, step  # noqa: E402
from cad_engine.mesh import tessellate  # noqa: E402
from cad_engine.profiles import catalog, parse  # noqa: E402
from cad_engine.sketch import Sketch  # noqa: E402
from cad_engine.sketch.model import DIMENSIONS  # noqa: E402
from cad_engine.sketch.profile import PLANES  # noqa: E402
from cad_engine.structures import cut_list  # noqa: E402
from cad_engine.structures.frame import JOINT_LABELS  # noqa: E402
from cad_engine.topology import describe  # noqa: E402
from cad_engine.tree import project_tree  # noqa: E402
from cad_engine.units import fmt_mm  # noqa: E402

DIREZIONI = {'X+': (0, 1), 'X-': (0, -1), 'Y+': (1, 1), 'Y-': (1, -1), 'Z+': (2, 1), 'Z-': (2, -1)}
ANCORAGGI = {'center': 'centro', 'top': 'sopra', 'bottom': 'sotto', 'left': 'sinistra', 'right': 'destra',
             'top-left': 'sopra a sinistra', 'top-right': 'sopra a destra', 'bottom-left': 'sotto a sinistra',
             'bottom-right': 'sotto a destra'}


def _ok(**kw):
    return {'ok': True, **kw}


def _err(ex: Exception):
    if isinstance(ex, SteelCADError):
        return {'ok': False, 'message': ex.message, 'code': ex.code}
    traceback.print_exc()
    return {'ok': False, 'message': f'Errore interno ({type(ex).__name__}): {ex}. Segnalalo con il file del progetto.',
            'code': 'interno'}


class Service:
    def __init__(self):
        self.path: Path | None = None
        self._set(templates.telaio('Tavolo officina'))

    def _set(self, doc: Document):
        self.doc = doc
        self.history = History(doc)
        self.result = doc.rebuild()
        self.scene_version = 1

    def _rebuild(self):
        self.result = self.doc.rebuild()
        self.scene_version += 1

    def _change(self, label: str, fn, keep_broken: bool = False):
        """Applica una modifica. Se rompe qualcosa che prima funzionava, la annulla e dice perché:
        il progetto non resta mai rotto per un clic (keep_broken=True per lasciarla comunque)."""
        try:
            prima = {f.id for f in self.result.errors}
            n = len(self.history.done)
            with self.history.change(label):
                fn()
            if len(self.history.done) == n:
                return _ok(state=self.state())          # nessun cambiamento vero
            self._rebuild()
            nuovi = [f for f in self.result.errors if f.id not in prima]
            if nuovi and not keep_broken:
                self.history.undo()
                self.history.undone.pop()
                self._rebuild()
                return {'ok': False, 'code': 'rompe', 'message': f'Non applicato: {nuovi[0].message}'}
            return _ok(state=self.state())
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    # ================================================================ lettura
    def state(self) -> dict:
        r, doc = self.result, self.doc
        info = {'rebuild_ms': round(r.seconds * 1000, 1), 'rebuilt': r.rebuilt, 'cached': r.cached,
                'material': doc.material}
        if r.body is not None:
            p = properties(r.body.shape, doc.material)
            info['part'] = {'mass_kg': p['mass_kg'], 'volume_mm3': p['volume_mm3'], 'size_mm': p['bbox_mm']['size']}
        cl = cut_list(r.structures)
        righe = bom(doc, r)
        avvisi = [w for st in r.structures for w in (st.warnings or [])]
        return {
            'name': doc.meta.get('name'), 'path': str(self.path) if self.path else None,
            'dirty': self.history.dirty, 'undo': self.history.labels()['undo'][:1],
            'redo': self.history.labels()['redo'][:1],
            'tree': project_tree(doc, r), 'parameters': self._parameters(),
            'errors': [f.to_dict() for f in r.errors], 'warnings': avvisi,
            'bom': righe, 'bom_kg': total_kg(righe), 'cutlist': cl, 'info': info,
            'dimensions': self._dimensions(), 'scene_version': self.scene_version,
        }

    def _parameters(self):
        try:
            risolti = self.doc.resolved_parameters()
        except SteelCADError:
            risolti = {}
        return [{'name': k, 'value': v, 'resolved': risolti.get(k)} for k, v in self.doc.parameters.items()]

    def _dimensions(self):
        """Le quote degli sketch da mostrare sul modello: clic, scrivi, Invio."""
        out = []
        for f in self.doc.features:
            if not isinstance(f, Sketch) or not isinstance(f.plane, str):
                continue
            try:
                ss = self.doc.solved_sketch(f.id)
            except SteelCADError:
                continue
            pl = PLANES[f.plane]
            for did, c in f.constraints.items():
                if c['type'] not in ('length', 'distance', 'diameter', 'hdistance', 'vdistance'):
                    continue
                if c['type'] == 'length':
                    a, b = ss.lines[c['refs'][0]]
                    pa, pb = ss.points[a], ss.points[b]
                elif c['type'] == 'diameter':
                    centro, r = ss.circles.get(c['refs'][0], (None, None))
                    if centro is None:
                        continue
                    cx, cy = ss.points[centro]
                    pa, pb = (cx - r, cy), (cx + r, cy)
                else:
                    pa, pb = ss.points[c['refs'][0]], ss.points[c['refs'][1]]
                ga, gb = pl.from_local_coords(pa), pl.from_local_coords(pb)
                v = ss.values.get(did)
                out.append({'sketch': f.id, 'dim': did, 'type': c['type'], 'expr': c['value'],
                            'param': c['value'] if isinstance(c['value'], str) and c['value'].isidentifier() else None,
                            'value': v, 'label': ('Ø' if c['type'] == 'diameter' else '') + fmt_mm(v or 0),
                            'a': [ga.X, ga.Y, ga.Z], 'b': [gb.X, gb.Y, gb.Z]})
        return out

    def scene(self) -> dict:
        objs = []
        r = self.result
        if r.body is not None:
            m = tessellate(r.body.shape, r.body.names)
            for f in m['faces']:
                f['label'] = self.doc.describe_face(f['name']) if f['name'] else 'faccia'
            objs.append({'id': 'body', 'kind': 'body', 'name': self.doc.meta.get('name'), **m})
        for st in r.structures:
            for mem in st.members:
                m = tessellate(mem.solid.wrapped)
                objs.append({'id': f'{st.id}/{mem.id}', 'kind': 'member',
                             'name': f'{mem.group or "Asta"} {mem.id} — {mem.profile.name} L={fmt_mm(round(mem.length, 1))}',
                             'group': mem.group, **m})
        nodi = [{'id': f'{st.id}:{k}', 'structure': st.id, 'key': k, **v}
                for st in r.structures for k, v in (st.nodes or {}).items()]
        return {'version': self.scene_version, 'objects': objs, 'nodes': nodi}

    def select(self, obj_id: str, face_index: int | None = None) -> dict:
        """Cosa mostrare nel pannello proprietà e quali comandi hanno senso per ciò che è stato cliccato."""
        try:
            if obj_id == 'body':
                p = properties(self.result.body.shape, self.doc.material)
                dati = {'kind': 'body', 'title': self.doc.meta.get('name'),
                        'rows': [['Materiale', self.doc.material], ['Peso', f'{p["mass_kg"]:.3f} kg'],
                                 ['Ingombro', ' × '.join(fmt_mm(round(v, 1)) for v in p['bbox_mm']['size'])]]}
                if face_index is not None:
                    from cad_engine.topology.naming import _faces_of
                    f = _faces_of(self.result.body.shape)[face_index]
                    nomi = self.result.body.names_of(f)
                    import build123d as bd
                    dati['face'] = {'name': nomi[0] if nomi else None,
                                    'label': self.doc.describe_face(nomi[0]) if nomi else 'faccia',
                                    'area': bd.Face(f).area}
                    dati['rows'].append(['Faccia', dati['face']['label']])
                    dati['rows'].append(['Area faccia', f'{dati["face"]["area"]:.1f} mm²'])
                dati['commands'] = [{'id': 'export_dxf', 'label': 'Esporta DXF di taglio'},
                                    {'id': 'export_step', 'label': 'Esporta STEP'}]
                return _ok(selection=dati)
            if ':' in obj_id:
                return _ok(selection=self._node_selection(obj_id))
            st_id, mid = obj_id.split('/')
            st = next(s for s in self.result.structures if s.id == st_id)
            m = next(x for x in st.members if x.id == mid)
            fdef = self.doc.feature(st_id)
            mdef = next(x for x in fdef['members'] if x['id'] == mid)
            return _ok(selection={
                'kind': 'member', 'id': obj_id, 'title': f'{m.group or "Asta"} {m.id}',
                'profile': mdef.get('profile'), 'group': m.group, 'material': m.material,
                'rotate': mdef.get('rotate', 0), 'flip': bool(mdef.get('flip')), 'anchor': mdef.get('anchor', 'center'),
                'anchors': ANCORAGGI,
                'rows': [['Profilo', m.profile.description], ['Materiale', m.material],
                         ['Lunghezza di taglio', f'{fmt_mm(round(m.length, 1))} mm'],
                         ['Tagli', ' / '.join(_cut_text(a) for a in m.cuts)],
                         ['Peso', f'{m.kg():.2f} kg ({m.kg() / m.length * 1000:.2f} kg/m)'.replace('.', ',')]],
                'commands': [{'id': 'rotate', 'label': 'Ruota di 90°'}, {'id': 'flip', 'label': 'Inverti'},
                             {'id': 'profile', 'label': 'Cambia profilo'}],
            })
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def profile_suggestions(self) -> list[str]:
        out = ['30x30x2', '40x40x3', '50x50x3', '60x60x3', '70x70x4', '80x80x4', '60x40x3', '80x40x3',
               '100x50x4', 'Ø33.7x2.6', 'Ø48.3x3.2', 'Ø60.3x3', 'piatto 40x5', 'piatto 50x8']
        cat = catalog()
        out += [f'L {k}' for k in cat['L']] + [f'{fam} {k}' for fam in ('IPE', 'HEA', 'HEB') for k in cat[fam]]
        return out

    # ================================================================ modifiche
    def set_parameter(self, name: str, value) -> dict:
        v = _number(value)
        return self._change(f'{name} = {value}', lambda: self.doc.set_parameter(name, v))

    def set_dimension(self, sketch_id: str, dim_id: str, value) -> dict:
        d = next((x for x in self._dimensions() if x['sketch'] == sketch_id and x['dim'] == dim_id), None)
        v = _number(value)
        if d and d['param']:
            return self.set_parameter(d['param'], v)
        return self._change(f'Quota {value}', lambda: self.doc.sketch(sketch_id).set_value(dim_id, v))

    def edit_member(self, obj_id: str, fields: dict, whole_group: bool = False) -> dict:
        st_id, mid = obj_id.split('/')
        if 'profile' in fields:
            try:
                parse(str(fields['profile']))         # profilo scritto male: errore chiaro subito
            except Exception as ex:  # noqa: BLE001
                return _err(ex)

        def fn():
            fdef = self.doc.feature(st_id)
            target = next(x for x in fdef['members'] if x['id'] == mid)
            gruppo = target.get('group')
            for x in fdef['members']:
                if x is target or (whole_group and gruppo and x.get('group') == gruppo):
                    for k, v in fields.items():
                        if k == 'rotate_by':
                            x['rotate'] = (float(x.get('rotate', 0)) + float(v)) % 360
                        elif k == 'toggle_flip':
                            x['flip'] = not x.get('flip', False)
                        else:
                            x[k] = v
        nomi = {'profile': 'profilo', 'rotate_by': 'ruota', 'toggle_flip': 'inverti', 'anchor': 'asse'}
        etichetta = ', '.join(nomi.get(k, k) + ('' if k == 'toggle_flip' else f' {v}') for k, v in fields.items())
        return self._change(f'{mid}: {etichetta}', fn)

    # ---------------------------------------------------------------- scheletro
    def _node_selection(self, node_id: str) -> dict:
        st_id, key = node_id.split(':', 1)
        st = next(s for s in self.result.structures if s.id == st_id)
        info = st.nodes[key]
        pdef = (self.doc.feature(st_id).get('points') or {}).get(key)
        if isinstance(pdef, dict) and 'from' in pdef:
            pos = {'mode': 'from', 'base': pdef['from'], 'values': list(pdef.get('offset') or [0, 0, 0])}
        elif isinstance(pdef, dict) and 'sketch' in pdef:
            pos = {'mode': 'sketch', 'base': f'{pdef["sketch"]}.{pdef.get("point")}',
                   'values': list(pdef.get('offset') or [0, 0, 0])}
        elif isinstance(pdef, (list, tuple)):
            pos = {'mode': 'abs', 'values': list(pdef)}
        else:
            pos = {'mode': 'fixed', 'values': []}       # punto preso da una linea di sketch
        tipo = info['joint'].get('type', 'auto')
        n = len(info['members'])
        possibili = ['auto', 'square'] + (['miter'] if n == 2 else []) + (['butt'] if n >= 2 else []) + ['angle']
        profilo = '40x40x3'
        for m in self.doc.feature(st_id).get('members') or []:
            if m['id'] in info['members'] or not info['members']:
                profilo = m.get('profile', profilo)
                break
        return {
            'kind': 'node', 'id': node_id, 'structure': st_id, 'key': key, 'title': f'Nodo {key}',
            'rows': [['Posizione', ' ; '.join(fmt_mm(round(c, 1)) for c in info['xyz']) + ' mm'],
                     ['Aste', ', '.join(info['members']) or 'nessuna'],
                     ['Giunto', JOINT_LABELS[tipo] + (f' (ora: {info["auto"]})' if tipo == 'auto' and info['auto'] else '')]],
            'position': pos, 'joint': info['joint'], 'joint_types': {k: JOINT_LABELS[k] for k in possibili},
            'members': info['members'], 'default_profile': profilo,
        }

    def _free_id(self, fdef, prefix: str, used) -> str:
        i = 1
        while f'{prefix}{i}' in used:
            i += 1
        return f'{prefix}{i}'

    def add_member(self, st_id: str, from_key: str, to_key: str | None = None, direction: str | None = None,
                   length=None, profile: str | None = None, group: str | None = None) -> dict:
        """Una nuova asta: dal nodo a un altro nodo, oppure dal nodo in una direzione per una lunghezza
        (il nodo nuovo resta legato a quello di partenza: se sposti quello, lo segue)."""
        try:
            if profile:
                parse(str(profile))
            if to_key is None:
                if direction not in DIREZIONI:
                    raise SteelCADError('Scegli la direzione della nuova asta.', code='direzione')
                lung = _number(length if length not in (None, '') else 500)
                if isinstance(lung, (int, float)) and lung <= 0:
                    raise SteelCADError('La lunghezza della nuova asta deve essere maggiore di zero.', code='lunghezza')
            elif to_key == from_key:
                raise SteelCADError("Un'asta deve unire due nodi diversi.", code='stesso_nodo')
        except SteelCADError as ex:
            return _err(ex)
        nuovo = {}

        def fn():
            fdef = self.doc.feature(st_id)
            punti = fdef.setdefault('points', {})
            aste = fdef.setdefault('members', [])
            arrivo = to_key
            if arrivo is None:
                asse, segno = DIREZIONI[direction]
                comp = lung if segno > 0 else (-lung if isinstance(lung, (int, float)) else f'-({lung})')
                off = [0, 0, 0]
                off[asse] = comp
                arrivo = self._free_id(fdef, 'N', punti)
                punti[arrivo] = {'from': from_key, 'offset': off}
            for m in aste:
                if {m.get('from'), m.get('to')} == {from_key, arrivo}:
                    raise SteelCADError(f'Tra {from_key} e {arrivo} c’è già l’asta {m["id"]}.', code='doppia')
            mid = self._free_id(fdef, 'M', {m['id'] for m in aste})
            prof = profile or self._node_selection(f'{st_id}:{from_key}')['default_profile']
            m = {'id': mid, 'from': from_key, 'to': arrivo, 'profile': prof}
            if group:
                m['group'] = group
            aste.append(m)
            nuovo['id'] = f'{st_id}/{mid}'
            nuovo['node'] = f'{st_id}:{arrivo}'
        r = self._change(f'Nuova asta da {from_key}', fn)
        if r['ok']:
            r['select'] = nuovo.get('id')
            r['node'] = nuovo.get('node')
        return r

    def delete_members(self, obj_ids: list[str]) -> dict:
        """Toglie le aste; i nodi rimasti senza aste spariscono, se nessun altro nodo parte da loro."""
        def fn():
            for st_id in {o.split('/')[0] for o in obj_ids}:
                fdef = self.doc.feature(st_id)
                via = {o.split('/')[1] for o in obj_ids if o.startswith(st_id + '/')}
                fdef['members'] = [m for m in fdef.get('members') or [] if m['id'] not in via]
                for j in (fdef.get('joints') or {}).values():
                    if 'through' in j:
                        j['through'] = [t for t in j['through'] if t not in via]
                for k, j in list((fdef.get('joints') or {}).items()):
                    if j.get('type') == 'butt' and not j.get('through'):
                        del fdef['joints'][k]
                punti = fdef.get('points') or {}
                while True:
                    usati = {m.get(x) for m in fdef['members'] for x in ('from', 'to')}
                    usati |= {v['from'] for v in punti.values() if isinstance(v, dict) and 'from' in v}
                    orfani = [k for k in punti if k not in usati]
                    if not orfani or len(punti) <= 1:
                        break
                    for k in orfani[:len(punti) - 1]:
                        del punti[k]
                        (fdef.get('joints') or {}).pop(k, None)
        nomi = ', '.join(o.split('/')[1] for o in obj_ids)
        return self._change(f'Elimina {nomi}', fn)

    def set_joint(self, st_id: str, key: str, spec: dict) -> dict:
        tipo = spec.get('type', 'auto')
        try:
            membri = self.result_node(st_id, key)['members']
            if tipo == 'butt' and not spec.get('through'):
                raise SteelCADError('Per il giunto a battuta scegli quale asta passa: le altre ci battono contro.',
                                    code='giunto')
            if tipo == 'butt' and set(spec['through']) >= set(membri):
                raise SteelCADError('Almeno un’asta deve battere contro le altre: non possono passare tutte.',
                                    code='giunto')
            if tipo == 'miter' and len(membri) != 2:
                raise SteelCADError(f'Il taglio a 45° vale per due aste; nel nodo {key} ce ne sono {len(membri)}.',
                                    code='giunto')
        except SteelCADError as ex:
            return _err(ex)

        def fn():
            fdef = self.doc.feature(st_id)
            joints = fdef.setdefault('joints', {})
            if tipo == 'auto':
                joints.pop(key, None)
            else:
                pulito = {'type': tipo}
                if tipo == 'butt':
                    pulito['through'] = list(spec['through'])
                if tipo == 'angle':
                    pulito['angle'] = _number(spec.get('angle', 0))
                joints[key] = pulito
        return self._change(f'Giunto {key}: {JOINT_LABELS[tipo]}', fn)

    def result_node(self, st_id: str, key: str) -> dict:
        st = next(s for s in self.result.structures if s.id == st_id)
        return st.nodes[key]

    def move_node(self, st_id: str, key: str, values: list) -> dict:
        vals = [_number(v) if str(v).strip() != '' else 0 for v in values]

        def fn():
            punti = self.doc.feature(st_id)['points']
            d = punti[key]
            if isinstance(d, dict):
                d['offset'] = vals
            else:
                punti[key] = vals
        return self._change(f'Sposta {key}', fn)

    def undo(self) -> dict:
        try:
            self.history.undo()
            self._rebuild()
            return _ok(state=self.state())
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def redo(self) -> dict:
        try:
            self.history.redo()
            self._rebuild()
            return _ok(state=self.state())
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def new_project(self, kind: str, values: dict | None = None) -> dict:
        try:
            values = {k: _number(v) for k, v in (values or {}).items()}
            doc = {'telaio': templates.telaio, 'piastra': templates.piastra,
                   'vuoto': templates.struttura_vuota}[kind](**values)
            self._set(doc)
            self.path = None
            return _ok(state=self.state())
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    # ================================================================ file
    def save(self, path: str | None = None) -> dict:
        try:
            p = Path(path) if path else self.path
            if p is None:
                return {'ok': False, 'code': 'serve_percorso', 'message': 'Scegli dove salvare.'}
            self.path = project_io.save(self.doc, p)
            self.history.dirty = False
            return _ok(state=self.state(), path=str(self.path))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def open(self, path: str, recover: bool = False) -> dict:
        try:
            doc = project_io.recover(path) if recover else project_io.load(path)
            self._set(doc)
            self.path = Path(path)
            return _ok(state=self.state())
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def recovery_available(self, path: str) -> bool:
        return project_io.recovery_available(path)

    def autosave(self) -> dict:
        if not self.history.dirty:
            return _ok(saved=False)
        try:
            dest = self.path or (Path.home() / 'Documents' / 'SteelCAD senza nome.steelcad')
            project_io.autosave(self.doc, dest)
            return _ok(saved=True)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def export_step(self, path: str) -> dict:
        try:
            out = step.export_project(self.doc, self.result, path)
            return _ok(message=f'STEP salvato: {out["solids"]} solidi, controllato rileggendo il file.', path=path)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def export_dxf(self, path: str) -> dict:
        try:
            if self.result.body is None:
                return {'ok': False, 'message': 'Il DXF di taglio si fa per un pezzo piano (una piastra): questo '
                                                'progetto ha solo strutture. Per i tubolari c’è la cut list.'}
            rep = dxf.export_flat(self.result.body.shape, path)
            return _ok(message=f'DXF salvato: {rep["contours"]} contorni, {fmt_mm(rep["size_mm"][0])} × '
                               f'{fmt_mm(rep["size_mm"][1])} mm, spessore {fmt_mm(rep["thickness_mm"])}. '
                               'Controlli superati.', path=path)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)


def _cut_text(a: float) -> str:
    return 'dritto' if abs(a) < 1e-6 else f'{fmt_mm(round(a, 1))}°'


def _number(v):
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace(',', '.')
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except ValueError:
        return str(v).strip()       # un'espressione: "L/2 + 10"


__all__ = ['Service', 'describe', 'DIMENSIONS']
