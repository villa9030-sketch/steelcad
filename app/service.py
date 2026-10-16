"""Strato applicativo: tiene il progetto aperto e risponde alla UI solo con dati JSON.

La UI chiama questi metodi (attraverso pywebview); qui non c'è niente di
grafico e niente di OpenCascade esposto all'esterno.
"""
from __future__ import annotations

import math
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
from cad_engine.sheetmetal import METODI, POSIZIONI, VERSI  # noqa: E402
from app import sketch_ops  # noqa: E402
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
        # sempre crescente, anche cambiando progetto: se ripartisse da 1 la UI crederebbe di avere
        # già la scena giusta e lascerebbe a video il pezzo vecchio
        self.scene_version = getattr(self, 'scene_version', 0) + 1

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
        sheet = self._sheet_state()
        return {
            'name': doc.meta.get('name'), 'path': str(self.path) if self.path else None,
            'dirty': self.history.dirty, 'undo': self.history.labels()['undo'][:1],
            'redo': self.history.labels()['redo'][:1],
            'tree': project_tree(doc, r), 'parameters': self._parameters(),
            'errors': [f.to_dict() for f in r.errors], 'warnings': avvisi,
            'bom': righe, 'bom_kg': total_kg(righe), 'cutlist': cl, 'info': info,
            'dimensions': self._dimensions(), 'scene_version': self.scene_version, 'sheet': sheet,
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
                    if c['type'] == 'hdistance':
                        pb = (pb[0], pa[1])
                    elif c['type'] == 'vdistance':
                        pb = (pa[0], pb[1])
                    if math.dist(pa, pb) < 1e-9:
                        continue                        # quota zero: niente da mostrare
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
                    from OCP.BRepAdaptor import BRepAdaptor_Surface
                    from OCP.GeomAbs import GeomAbs_Plane
                    dati['face']['planar'] = BRepAdaptor_Surface(f).GetType() == GeomAbs_Plane
                    dati['rows'].append(['Area faccia', f'{dati["face"]["area"]:.1f} mm²'])
                    nome = dati['face']['name'] or ''
                    parti = nome.split('/')
                    sm = self._sheet_def(parti[0]) if parti else None
                    if sm is not None and len(parti) == 3 and parti[1] == 'lato':
                        dati['flange_form'] = {'feature': parti[0], 'edge': parti[2],
                                               'label': self.doc.sketch(sm['sketch']).describe(parti[2])}
                    elif sm is not None and len(parti) == 3 and parti[1].startswith('FL'):
                        fs = self._flange_selection(parti[0], parti[1])
                        fs['face_label'] = dati['face']['label']
                        fs['face'] = dati['face']
                        return _ok(selection=fs)
                dati['commands'] = [{'id': 'export_dxf', 'label': 'Esporta DXF di taglio'},
                                    {'id': 'export_step', 'label': 'Esporta STEP'}]
                return _ok(selection=dati)
            if ':' in obj_id:
                return _ok(selection=self._node_selection(obj_id))
            if obj_id.startswith('flange='):
                return _ok(selection=self._flange_selection(*obj_id[7:].split('/')))
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

    # ---------------------------------------------------------------- lamiera
    def _sheet_def(self, fid: str):
        try:
            f = self.doc.feature(fid)
        except SteelCADError:
            return None
        return f if not isinstance(f, Sketch) and f.get('type') == 'sheet' else None

    def _sheet_state(self):
        sm = next((f for f in self.doc.features if not isinstance(f, Sketch) and f.get('type') == 'sheet'), None)
        if sm is None:
            return None
        out = {'feature': sm['id'], 'def': {k: sm.get(k) for k in ('thickness', 'radius', 'method', 'k', 'bd90')},
               'methods': METODI, 'data': None, 'flanges': len(sm.get('flanges') or []),
               'after': [f['id'] for f in self.doc.features[self.doc.features.index(sm) + 1:]
                         if not isinstance(f, Sketch) and f.get('type') not in ('structure', 'sheet_cut')]}
        data = getattr(self.result.body, 'sheet', None) if self.result.body is not None else None
        if data is not None:
            out['data'] = data.summary()
            out['missing'] = data.tech['missing']
        else:
            out['missing'] = [m for m, k in (('raggio interno', 'radius'),) if sm.get(k) in (None, '')]
        return out

    def _face_indices(self, prefix: str) -> list[int]:
        from cad_engine.topology.naming import _faces_of
        facce = _faces_of(self.result.body.shape)
        out = []
        for nome, fs in self.result.body.names.items():
            if nome == prefix or nome.startswith(prefix + '/'):
                out += [i for i, f in enumerate(facce) if any(f.IsSame(g) for g in fs)]
        return sorted(set(out))

    def _flange_selection(self, fid: str, flid: str) -> dict:
        sm = self._sheet_def(fid)
        fl = next(x for x in sm['flanges'] if x['id'] == flid)
        data = getattr(self.result.body, 'sheet', None)
        geo = next((g for g in data.flanges if g.fid == flid), None) if data else None
        rows = [['Lato', self.doc.sketch(sm['sketch']).describe(fl['edge'])]]
        if geo:
            b = geo.bend
            rows += [['Piega', f'{fmt_mm(b.angle)}° {"su" if geo.direction == "up" else "giù"}, R{fmt_mm(b.r)}, K {b.k:.3f}'.replace('.', ',')],
                     ['Larghezza', f'{fmt_mm(round(geo.u1 - geo.u0, 2))} mm'],
                     ['BA / BD', f'{b.ba:.3f} / {b.bd:.3f} mm'.replace('.', ',')]]
        return {'kind': 'flange', 'feature': fid, 'flange': flid, 'title': f'Flangia {flid}', 'rows': rows,
                'def': {k: fl.get(k, d) for k, d in (('length', None), ('angle', 90), ('direction', 'up'),
                                                      ('position', 'inside'), ('gap', 0))},
                'holes': fl.get('holes') or [], 'directions': VERSI, 'positions': POSIZIONI,
                'corners': self._corners_of(sm, flid, data),
                'highlight': self._face_indices(f'{fid}/{flid}') if self.result.body is not None else []}

    def _corners_of(self, sm, flid, data) -> list:
        """Le flange che hanno un angolo in comune con questa, e com'è chiuso l'angolo."""
        if data is None:
            return []
        g = next((x for x in data.flanges if x.fid == flid), None)
        if g is None:
            return []
        out = []
        for h in data.flanges:
            if h is g or not set(h.ends) & set(g.ends):
                continue
            c = next((c for c in sm.get('corners') or [] if {c.get('over'), c.get('under')} == {flid, h.fid}), None)
            mode = 'open' if c is None else ('over' if c['over'] == flid else 'under')
            out.append({'other': h.fid, 'mode': mode, 'gap': (c or {}).get('gap', 0)})
        return out

    def set_corner(self, fid: str, flid: str, other: str, mode: str, gap=0) -> dict:
        if mode not in ('open', 'over', 'under'):
            return {'ok': False, 'message': 'Tipo di angolo sconosciuto.'}

        def fn(sm):
            cs = [c for c in sm.get('corners') or [] if {c.get('over'), c.get('under')} != {flid, other}]
            if mode != 'open':
                over, under = (flid, other) if mode == 'over' else (other, flid)
                g = _number(gap) if str(gap).strip() != '' else 0
                cs.append({'over': over, 'under': under, 'gap': g})
            sm['corners'] = cs
        testo = {'open': 'aperto', 'over': f'{flid} sopra', 'under': f'{other} sopra'}[mode]
        return self._edit_sheet(fid, f'Angolo {flid}/{other}: {testo}', fn)

    def _edit_sheet(self, fid: str, label: str, fn) -> dict:
        def wrap():
            sm = self._sheet_def(fid)
            if sm is None:
                raise SteelCADError('Questa lamiera non esiste più.', code='lamiera')
            fn(sm)
        return self._change(label, wrap)

    def add_flange(self, fid: str, edge: str, fields: dict) -> dict:
        nuovo = {}

        def fn(sm):
            fls = sm.setdefault('flanges', [])
            if any(x['edge'] == edge for x in fls):
                raise SteelCADError('Su questo lato c’è già una flangia: cliccala per cambiarla.', code='doppia')
            flid = self._free_id(sm, 'FL', {x['id'] for x in fls})
            fl = {'id': flid, 'edge': edge}
            fl.update(_flange_fields(fields))
            fl.setdefault('length', 30)
            fl.setdefault('angle', 90)
            fls.append(fl)
            nuovo['flange'] = flid
        r = self._edit_sheet(fid, f'Flangia su {edge}', fn)
        if r['ok']:
            r['select'] = f'flange={fid}/{nuovo["flange"]}'
        return r

    def edit_flange(self, fid: str, flid: str, fields: dict) -> dict:
        def fn(sm):
            fl = next(x for x in sm['flanges'] if x['id'] == flid)
            fl.update(_flange_fields(fields))
        return self._edit_sheet(fid, f'{flid}: modifica', fn)

    def delete_flange(self, fid: str, flid: str) -> dict:
        def fn(sm):
            sm['flanges'] = [x for x in sm['flanges'] if x['id'] != flid]
            sm['corners'] = [c for c in sm.get('corners') or [] if flid not in (c.get('over'), c.get('under'))]
        return self._edit_sheet(fid, f'Elimina {flid}', fn)

    def add_flange_hole(self, fid: str, flid: str, u, v, d) -> dict:
        def fn(sm):
            fl = next(x for x in sm['flanges'] if x['id'] == flid)
            fl.setdefault('holes', []).append({'u': _number(u), 'v': _number(v), 'd': _number(d)})
        return self._edit_sheet(fid, f'Foro su {flid}', fn)

    def delete_flange_hole(self, fid: str, flid: str, index: int) -> dict:
        def fn(sm):
            fl = next(x for x in sm['flanges'] if x['id'] == flid)
            del fl['holes'][int(index)]
        return self._edit_sheet(fid, f'Togli foro da {flid}', fn)

    def set_sheet_tech(self, fid: str, fields: dict) -> dict:
        # spessore, raggio interno, metodo, K-factor, deduzione: i dati della piegatrice
        def fn(sm):
            for k in ('thickness', 'radius', 'k', 'bd90'):
                if k in fields:
                    v = fields[k]
                    sm[k] = None if v is None or str(v).strip() == '' else _number(v)
            if 'method' in fields:
                if fields['method'] not in METODI:
                    raise SteelCADError('Metodo di piega sconosciuto.', code='metodo')
                sm['method'] = fields['method']
        # qui una modifica può lasciare la lamiera senza un dato: va bene, la scheda lo dice
        return self._change('Dati di piega', lambda: fn(self._sheet_def(fid)), keep_broken=True)

    # ---------------------------------------------------------------- disegno libero
    def sketch_view(self, sid: str) -> dict:
        try:
            return _ok(sketch=sketch_ops.view(self.doc, sid, self.result.body))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def _sketch_change(self, label, fn):
        # mentre si disegna lo sketch può restare aperto: la modifica si tiene comunque
        r = self._change(label, fn, keep_broken=True)
        return r

    def sketch_add_polyline(self, sid: str, pts: list, closed: bool) -> dict:
        n = len(pts) - (0 if closed else 1)
        return self._sketch_change(f'{"Contorno" if closed else "Linee"} ({n} tratti)',
                                   lambda: sketch_ops.add_polyline(self.doc, sid, pts, closed))

    def sketch_add_rectangle(self, sid: str, p0, p1) -> dict:
        return self._sketch_change('Rettangolo', lambda: sketch_ops.add_rectangle(self.doc, sid, p0, p1))

    def sketch_add_circle(self, sid: str, center, r) -> dict:
        return self._sketch_change(f'Cerchio Ø{fmt_mm(round(2 * float(r), 2))}',
                                   lambda: sketch_ops.add_circle(self.doc, sid, center, r))

    def sketch_delete(self, sid: str, eids: list) -> dict:
        return self._sketch_change(f'Elimina {", ".join(eids)}', lambda: sketch_ops.delete(self.doc, sid, eids))

    def sketch_on_face(self, face_name: str) -> dict:
        """La faccia cliccata diventa il piano di lavoro: uno sketch nuovo su di lei."""
        if self.result.body is None or face_name not in self.result.body.names:
            return {'ok': False, 'code': 'faccia', 'message': 'Questa faccia non ha un nome stabile: non ci si può '
                    'disegnare sopra (succede con facce nate da tagli). Scegline un’altra.'}
        nuovo = {}

        def fn():
            sk = self.doc.add_sketch({'face': face_name}, 'Sketch: ' + self.doc.describe_face(face_name).replace('"', ''))
            nuovo['id'] = sk.id
        r = self._change('Sketch su faccia', fn)
        if r['ok']:
            r['sketch'] = nuovo['id']
        return r

    def create_from_sketch(self, sid: str, kind: str, values: dict) -> dict:
        """Dal contorno disegnato: lamiera (spessore + dati di piega) o piastra (estrusione)."""
        v = {k: _number(x) for k, x in (values or {}).items() if str(x).strip() != ''}
        sk = self.doc.sketch(sid)
        if isinstance(sk.plane, dict) and kind in ('cut', 'boss'):
            return self._from_face_sketch(sid, sk, kind, v)
        fr = next((f for f in self.result.features if f.id == sid), None)
        if fr is None or not fr.ok:
            return {'ok': False, 'code': 'sketch', 'message': 'Prima chiudi il contorno: '
                    + (fr.message if fr else 'lo sketch non è costruibile.')}
        if any(not isinstance(f, Sketch) and f.get('sketch') == sid for f in self.doc.features):
            return {'ok': False, 'code': 'usato', 'message': 'Questo sketch ha già un pezzo: modificalo da lì.'}

        def fn():
            if 'sp' not in self.doc.parameters:
                self.doc.set_parameter('sp', v.get('thickness', 2))
            if kind == 'sheet':
                self.doc.add_feature('sheet', self.doc.meta.get('name') or 'Lamiera', sketch=sid, thickness='sp',
                                     radius=v.get('radius'), method='k', k=v.get('k'), flanges=[])
            else:
                self.doc.add_feature('extrude', self.doc.meta.get('name') or 'Piastra', sketch=sid,
                                     distance='sp', operation='new')
        return self._change('Crea lamiera' if kind == 'sheet' else 'Crea piastra', fn)

    def _from_face_sketch(self, sid, sk, kind, v) -> dict:
        fr = next((f for f in self.result.features if f.id == sid), None)
        if fr is None or not fr.ok:
            return {'ok': False, 'code': 'sketch', 'message': 'Prima chiudi il contorno: '
                    + (fr.message if fr else 'lo sketch non è costruibile.')}
        su = self._sheet_def(sk.plane['face'].split('/')[0])

        def fn():
            if kind == 'cut' and su is not None:
                self.doc.add_feature('sheet_cut', 'Taglio', sketch=sid)
            elif kind == 'cut':
                self.doc.add_feature('extrude', 'Taglio', sketch=sid, operation='cut', through_all=True, reverse=True)
            else:
                if su is not None:
                    raise SteelCADError('Sulla lamiera non si aggiunge materiale estrudendo: lo sviluppo non '
                                        'lo conterrebbe. Usa le flange.', code='lamiera')
                if 'distance' not in v:
                    raise SteelCADError('Scrivi di quanto estrudere.', code='distanza')
                self.doc.add_feature('extrude', 'Estrusione', sketch=sid, operation='add', distance=v['distance'])
        return self._change('Taglio dalla faccia' if kind == 'cut' else 'Estrusione dalla faccia', fn)

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
                   'vuoto': templates.struttura_vuota, 'lamiera': templates.lamiera,
                   'zero': templates.da_zero}[kind](**values)
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
            sheet = getattr(self.result.body, 'sheet', None) if self.result.body is not None else None
            stato = self._sheet_state()
            if sheet is not None:
                rep = dxf.export_flat_pattern(sheet, path)
                return _ok(message=f'Sviluppo salvato: {fmt_mm(round(rep["size_mm"][0], 2))} × '
                                   f'{fmt_mm(round(rep["size_mm"][1], 2))} mm, {rep["contours"]} contorni, '
                                   f'{rep["bend_lines"]} pieghe sul layer BEND. Controlli superati.', path=path)
            if stato is not None and stato['after']:
                return {'ok': False, 'message': 'Dopo la lamiera ci sono altre lavorazioni ('
                        + ', '.join(stato['after']) + '): lo sviluppo non le conterrebbe. I fori sulla base vanno '
                        'nello sketch, quelli sulle flange nel pannello della flangia.'}
            if stato is not None:
                return {'ok': False, 'message': 'La lamiera non è costruita: guarda la scheda Lamiera.'}
            if self.result.body is None:
                return {'ok': False, 'message': 'Il DXF di taglio si fa per un pezzo piano (una piastra): questo '
                                                'progetto ha solo strutture. Per i tubolari c’è la cut list.'}
            rep = dxf.export_flat(self.result.body.shape, path)
            return _ok(message=f'DXF salvato: {rep["contours"]} contorni, {fmt_mm(rep["size_mm"][0])} × '
                               f'{fmt_mm(rep["size_mm"][1])} mm, spessore {fmt_mm(rep["thickness_mm"])}. '
                               'Controlli superati.', path=path)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)


def _flange_fields(fields: dict) -> dict:
    out = {}
    for k in ('length', 'angle', 'gap'):
        if k in fields and str(fields[k]).strip() != '':
            out[k] = _number(fields[k])
    for k, ok in (('direction', VERSI), ('position', POSIZIONI)):
        if k in fields:
            if fields[k] not in ok:
                raise SteelCADError(f'Valore "{fields[k]}" non valido.', code='campo')
            out[k] = fields[k]
    return out


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
