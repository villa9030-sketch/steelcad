"""Strato applicativo: tiene il progetto aperto e risponde alla UI solo con dati JSON.

La UI chiama questi metodi (attraverso pywebview); qui non c'è niente di
grafico e niente di OpenCascade esposto all'esterno.
"""
from __future__ import annotations

import math
import re
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
from cad_engine.sheetmetal import METODI, POSIZIONI, TIP_CORNERS, VERSI  # noqa: E402
from app import sketch_edit, sketch_more, sketch_ops, sketch_trim  # noqa: E402
from app.assembly_service import AssemblyMixin  # noqa: E402
from app.drawings_service import DrawingsMixin  # noqa: E402
from app.import_service import ImportMixin  # noqa: E402
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


class Service(AssemblyMixin, DrawingsMixin, ImportMixin):
    def __init__(self):
        self.path: Path | None = None
        self._set(Document('Nuovo progetto'))
        self.blank = True                  # appena aperto, niente progetto: la UI mostra la pagina iniziale

    def _set(self, doc: Document):
        self.doc = doc
        self.history = History(doc)
        self.result = doc.rebuild()
        # sempre crescente, anche cambiando progetto: se ripartisse da 1 la UI crederebbe di avere
        # già la scena giusta e lascerebbe a video il pezzo vecchio
        self.scene_version = getattr(self, 'scene_version', 0) + 1

    def _rebuild(self):
        self.result = self.doc.rebuild()
        # la scena 3D si rifà (e l'interfaccia la ricarica) solo se il pezzo è cambiato davvero: disegnando in uno
        # sketch il pezzo resta lo stesso oggetto, e ritriangolare centinaia di facce a ogni linea era lento
        firma = self._scene_signature()
        if firma != getattr(self, '_firma_scena', None):
            self.scene_version += 1
            self._firma_scena = firma

    def _scene_signature(self):
        r = self.result
        return (id(r.body), id(r.body.shape) if r.body is not None else None,
                tuple(id(st) for st in r.structures), self.doc.meta.get('name'))

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
        if self.asm is not None:
            return self._asm_state()
        r, doc = self.result, self.doc
        info = {'rebuild_ms': round(r.seconds * 1000, 1), 'rebuilt': r.rebuilt, 'cached': r.cached,
                'material': doc.material}
        if r.body is not None:
            p = properties(r.body.shape, doc.material)
            info['part'] = {'mass_kg': p['mass_kg'], 'volume_mm3': p['volume_mm3'], 'size_mm': p['bbox_mm']['size']}
        cl = cut_list(r.structures)
        righe = bom(doc, r)
        avvisi = [w for st in r.structures for w in (st.warnings or [])]
        sd = getattr(r.body, 'sheet', None) if r.body is not None else None
        avvisi += list(getattr(sd, 'warnings', None) or [])
        sheet = self._sheet_state()
        return {
            'name': doc.meta.get('name'), 'path': str(self.path) if self.path else None,
            'dirty': self.history.dirty, 'undo': self.history.labels()['undo'][:1],
            'redo': self.history.labels()['redo'][:1],
            'tree': project_tree(doc, r), 'parameters': self._parameters(), 'mode': 'part',
            'can_back': bool(getattr(self, '_asm_ritorno', None)),
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
            if not isinstance(f, Sketch):
                continue
            try:
                ss = self.doc.solved_sketch(f.id)
                if isinstance(f.plane, str):
                    pl = PLANES[f.plane]
                else:
                    # su una faccia o sullo sviluppo: le quote si vedono solo con lo sketch aperto
                    fatto = self.doc._sketch_results.get(f.id)
                    pl = fatto[1].plane if fatto and fatto[1] is not None else self.doc._plane(f, self.result.body)
            except SteelCADError:
                continue
            visti = set()
            for did, c in f.constraints.items():
                if c['type'] not in ('length', 'distance', 'diameter', 'radius', 'hdistance', 'vdistance', 'pldistance'):
                    continue
                if _guida_secondaria(f, c):
                    continue                    # delle linee di costruzione si mostra solo la distanza che conta
                # offset e serie: la stessa misura su tanti tratti/copie si mostra una volta sola
                expr = c['value']
                param = expr if isinstance(expr, str) and expr.isidentifier() else None
                m = re.fullmatch(r'\s*(\d+)\s*\*\s*([A-Za-z_]\w*)\s*', expr) if isinstance(expr, str) else None
                if m:
                    if m.group(1) != '1':
                        continue
                    param = m.group(2)
                if param and c['type'] in ('pldistance', 'length') and f.entities.get(c['refs'][-1], {}).get('construction', c['type'] == 'pldistance'):
                    if param in visti:
                        continue
                    visti.add(param)
                if c['type'] == 'length':
                    a, b = ss.lines[c['refs'][0]]
                    pa, pb = ss.points[a], ss.points[b]
                elif c['type'] == 'diameter':
                    centro, r = ss.circles.get(c['refs'][0], (None, None))
                    if centro is None:
                        continue
                    cx, cy = ss.points[centro]
                    pa, pb = (cx - r, cy), (cx + r, cy)
                elif c['type'] == 'radius':
                    if c['refs'][0] in ss.arcs:
                        centro, a_, b_, r = ss.arcs[c['refs'][0]]
                        (cx, cy), (ax, ay), (bx, by) = ss.points[centro], ss.points[a_], ss.points[b_]
                        t0 = math.atan2(ay - cy, ax - cx)
                        t1 = math.atan2(by - cy, bx - cx)
                        while t1 <= t0:
                            t1 += 2 * math.pi
                        tm = (t0 + t1) / 2                      # la scritta a metà dell'arco
                    elif c['refs'][0] in ss.circles:
                        centro, r = ss.circles[c['refs'][0]]
                        (cx, cy), tm = ss.points[centro], math.pi / 4
                    else:
                        continue
                    pa, pb = (cx, cy), (cx + r * math.cos(tm), cy + r * math.sin(tm))
                elif c['type'] == 'pldistance':
                    pa = ss.points[c['refs'][0]]
                    la, lb = (ss.points[x] for x in ss.lines[c['refs'][1]])
                    ux, uy = lb[0] - la[0], lb[1] - la[1]
                    tt = ((pa[0] - la[0]) * ux + (pa[1] - la[1]) * uy) / ((ux * ux + uy * uy) or 1)
                    pb = (la[0] + ux * tt, la[1] + uy * tt)          # il piede sulla linea
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
                            'local': not isinstance(f.plane, str),
                            'param': param,
                            # le distanze orizzontali/verticali "all'indietro" si leggono senza il meno: il verso
                            # lo dice la quota stessa
                            'value': v, 'shown': abs(v) if v is not None and c['type'] in ('hdistance', 'vdistance') else v,
                            'label': ({'diameter': 'Ø', 'radius': 'R'}.get(c['type'], ''))
                            + fmt_mm(abs(v or 0) if c['type'] in ('hdistance', 'vdistance') else (v or 0)),
                            'a': [ga.X, ga.Y, ga.Z], 'b': [gb.X, gb.Y, gb.Z]})
        return out

    def scene(self) -> dict:
        if self.asm is not None:
            return self._asm_scene()
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
        # i bordi dove si può piegare: passandoci sopra col mouse si accendono, clic = flangia lì
        data = getattr(r.body, 'sheet', None) if r.body is not None else None
        bordi = []
        if data is not None:
            sk = self.doc.sketch(self._sheet_def(data.feature)['sketch'])
            for e in data.free_edges:
                testo = (f'punta di {e["ref"]}' if e['kind'] == 'tip' else sk.describe(e['ref']))
                bordi.append({**e, 'feature': data.feature, 'id': f'{e["kind"]}:{e["ref"]}',
                              'label': f'{testo} ({fmt_mm(round(e["length"], 1))} mm)', 'thickness': data.thickness})
        return {'version': self.scene_version, 'objects': objs, 'nodes': nodi, 'bend_edges': bordi}

    def select(self, obj_id: str, face_index: int | None = None, face_name: str | None = None) -> dict:
        if self.asm is not None:
            try:
                return self._asm_select(obj_id, face_index)
            except SteelCADError as ex:
                return _err(ex)
        """Cosa mostrare nel pannello proprietà e quali comandi hanno senso per ciò che è stato cliccato.
        Con il nome della faccia: se intanto il pezzo è stato ricostruito, il numero della faccia cliccata
        (preso dalla scena vecchia) può essere cambiato; il nome no, e vince lui."""
        try:
            if obj_id == 'body' and face_index is not None and face_name and self.result.body is not None:
                from cad_engine.topology.naming import _faces_of
                facce = _faces_of(self.result.body.shape)
                if face_index >= len(facce) or face_name not in self.result.body.names_of(facce[face_index]):
                    giusta = self._face_indices(face_name)
                    giusta = [i for i in giusta if face_name in self.result.body.names_of(facce[i])]
                    if giusta:
                        face_index = giusta[0]
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
                    dati['face'] = {'name': nomi[0] if nomi else None, 'index': face_index,
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
                    elif sm is not None and len(parti) == 3 and any(x['id'] == parti[1] for x in sm.get('folds') or []):
                        fs = self._fold_selection(parti[0], parti[1])
                        fs['face'] = dati['face']
                        fs['highlight'] = []
                        return _ok(selection=fs)
                    elif sm is not None and len(parti) == 3 and any(x['id'] == parti[1] for x in sm.get('flanges') or []):
                        fs = self._flange_selection(parti[0], parti[1])
                        fs['face_label'] = dati['face']['label']
                        fs['face'] = dati['face']
                        fs['highlight'] = []             # hai cliccato una faccia: si accende quella sola
                        if parti[2] == 'punta' and not any(x.get('parent') == parti[1] for x in sm['flanges']):
                            fs['tip_form'] = {'feature': parti[0], 'parent': parti[1]}
                        return _ok(selection=fs)
                dati['commands'] = [{'id': 'export_dxf', 'label': 'Esporta DXF di taglio'},
                                    {'id': 'export_step', 'label': 'Esporta STEP'}]
                if getattr(self.result.body, 'sheet', None) is not None:
                    dati['commands'] += [{'id': 'unfold', 'label': 'Spiega'},
                                         {'id': 'flat_sketch', 'label': 'Disegna sullo sviluppo'}]
                return _ok(selection=dati)
            if ':' in obj_id:
                return _ok(selection=self._node_selection(obj_id))
            if obj_id.startswith('flange='):
                fid_, flid_ = obj_id[7:].split('/')
                if any(x['id'] == flid_ for x in (self._sheet_def(fid_) or {}).get('folds') or []):
                    return _ok(selection=self._fold_selection(fid_, flid_))
                return _ok(selection=self._flange_selection(fid_, flid_))
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
        if fl.get('parent'):
            rows = [['Piegata sulla punta di', fl['parent']]]
        else:
            rows = [['Lato', self.doc.sketch(sm['sketch']).describe(fl['edge'])]]
        figlia = next((x['id'] for x in sm['flanges'] if x.get('parent') == flid), None)
        if figlia:
            rows.append(['Sulla sua punta', figlia])
        if geo:
            b = geo.bend
            rows += [['Piega', f'{fmt_mm(b.angle)}° {"su" if geo.direction == "up" else "giù"}, R{fmt_mm(b.r)}, K {b.k:.3f}'.replace('.', ',')],
                     ['Larghezza', f'{fmt_mm(round(geo.u1 - geo.u0, 2))} mm'],
                     ['BA / BD', f'{b.ba:.3f} / {b.bd:.3f} mm'.replace('.', ',')]]
        return {'kind': 'flange', 'feature': fid, 'flange': flid, 'title': f'Flangia {flid}', 'rows': rows,
                'tip_child': figlia, 'parent': fl.get('parent'), 'extend': fl.get('extend') or [0, 0],
                'tip_contact': (lambda c: self.doc.describe_face(c[3]) if c else None)(self._tip_contact(fid, flid)) if not figlia else None,
                'can_extend': bool(fl.get('parent')) and any(self._tab_extension(fid, fl['parent'])) and
                (fl.get('extend') or [0, 0]) != self._tab_extension(fid, fl['parent']),
                'end_tabs': fl.get('end_tabs') or [], 'tab_ends': self._tab_ends(geo),
                'tip_corners': ({'mode': sm.get('tip_corners') or 'long', 'modes': TIP_CORNERS,
                                 'others': [c[0] if c[1] == flid else c[1] for c in data.tip_contacts if flid in c]}
                                if data is not None and any(flid in c for c in data.tip_contacts) else None),
                'def': {k: fl.get(k, d) for k, d in (('length', None), ('angle', 90), ('direction', 'up'),
                                                      ('position', 'inside'), ('gap', 0))},
                'holes': fl.get('holes') or [], 'directions': VERSI, 'positions': POSIZIONI,
                'corners': self._corners_of(sm, flid, data),
                'highlight': self._face_indices(f'{fid}/{flid}') if self.result.body is not None else []}

    @staticmethod
    def _tab_ends(geo) -> list:
        """Le due estremità di una flangia, dette con la direzione verso cui guardano (per le alette di chiusura)."""
        if geo is None:
            return []
        out = []
        for end, sg in (('u0', -1), ('u1', 1)):
            d = geo.xf * sg
            asse = max(range(3), key=lambda i: abs((d.X, d.Y, d.Z)[i]))
            v = (d.X, d.Y, d.Z)[asse]
            out.append({'end': end, 'label': f'estremità {"XYZ"[asse]}{"+" if v > 0 else "−"}'})
        return out

    def set_end_tab(self, fid: str, flid: str, end: str, on: bool, gap=0) -> dict:
        """Aletta di chiusura della testata del profilo, piegata da questa flangia (on=False la toglie)."""
        if end not in ('u0', 'u1'):
            return {'ok': False, 'message': 'Estremità sconosciuta.'}

        def fn(sm):
            fl = next(x for x in sm['flanges'] if x['id'] == flid)
            tabs = [t for t in fl.get('end_tabs') or [] if t.get('end') != end]
            if on:
                g = _number(gap) if str(gap).strip() != '' else 0
                tabs.append({'end': end, 'gap': g})
            fl['end_tabs'] = tabs
        return self._edit_sheet(fid, f'{flid}: {"chiudi" if on else "apri"} la testata', fn)

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

    # ---------------------------------------------------------------- regole di lamiera
    # I dati di piega della tua piegatrice (per materiale e spessore) salvati con un nome e riusati in ogni
    # progetto. Stanno in un file nei Documenti, non nel progetto.
    @staticmethod
    def _rules_path() -> Path:
        import os
        p = os.environ.get('STEELCAD_RULES')
        return Path(p) if p else Path.home() / 'Documents' / 'SteelCAD' / 'regole_lamiera.json'

    def _rules(self) -> list:
        import json
        try:
            return json.loads(self._rules_path().read_text(encoding='utf-8')).get('rules', [])
        except (OSError, ValueError):
            return []

    def _save_rules(self, rules: list):
        import json
        p = self._rules_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({'format': 'steelcad-regole', 'rules': rules}, ensure_ascii=False, indent=1), encoding='utf-8')

    def sheet_rules(self) -> dict:
        return _ok(rules=self._rules(), material=self.doc.material)

    def save_sheet_rule(self, fid: str, name: str) -> dict:
        try:
            nome = str(name or '').strip()
            if not nome:
                raise SteelCADError('Dai un nome alla regola, per esempio "S235 sp. 2 – matrice 16".', code='nome')
            sm = self._sheet_def(fid)
            if sm is None:
                raise SteelCADError('Non c’è una lamiera da cui prendere i dati di piega.', code='lamiera')
            data = getattr(self.result.body, 'sheet', None) if self.result.body is not None else None
            sp = data.thickness if data is not None else _number(sm.get('thickness'))
            if not isinstance(sp, (int, float)):
                sp = self.doc.resolved_parameters().get(str(sp))
            regola = {'name': nome, 'material': self.doc.material, 'thickness': sp,
                      **{k: sm.get(k) for k in ('radius', 'method', 'k', 'bd90')}}
            if regola['radius'] in (None, '') or not regola['method']:
                raise SteelCADError('Mancano dei dati di piega (raggio o metodo): completali nella scheda Lamiera.', code='dati')
            rules = [r for r in self._rules() if r['name'] != nome] + [regola]
            self._save_rules(sorted(rules, key=lambda r: (str(r.get('material')), r.get('thickness') or 0, r['name'])))
            return _ok(rules=self._rules(), message=f'Regola "{nome}" salvata.')
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def delete_sheet_rule(self, name: str) -> dict:
        try:
            self._save_rules([r for r in self._rules() if r['name'] != name])
            return _ok(rules=self._rules())
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def apply_sheet_rule(self, fid: str, name: str) -> dict:
        regola = next((r for r in self._rules() if r['name'] == name), None)
        if regola is None:
            return {'ok': False, 'message': f'La regola "{name}" non c’è più.'}

        def fn():
            sm = self._sheet_def(fid)
            if sm is None:
                raise SteelCADError('Questa lamiera non esiste più.', code='lamiera')
            sp = sm.get('thickness')
            if isinstance(sp, str) and sp.isidentifier() and sp in self.doc.parameters:
                self.doc.set_parameter(sp, regola['thickness'])        # lo spessore è un parametro: cambia quello
            else:
                sm['thickness'] = regola['thickness']
            for k in ('radius', 'method', 'k', 'bd90'):
                sm[k] = regola.get(k)
            if regola.get('material'):
                self.doc.material = regola['material']
        return self._change(f'Regola di lamiera: {name}', fn, keep_broken=True)

    def export_bend_table(self, path: str) -> dict:
        """La tabella delle pieghe per la piegatrice, in CSV (punto e virgola, virgola decimale: si apre in Excel)."""
        try:
            data = getattr(self.result.body, 'sheet', None) if self.result.body is not None else None
            if data is None:
                raise SteelCADError('La tabella pieghe si fa da una lamiera costruita.', code='lamiera')
            n = lambda v, d=3: f'{v:.{d}f}'.replace('.', ',')  # noqa: E731
            righe = ['Piega;Flangia;Su;Lunghezza esterna mm;Angolo °;Verso;Raggio interno mm;K;BA mm;BD mm;Larghezza mm']
            for i, g in enumerate(data.flanges, 1):
                b = g.bend
                righe.append(';'.join([str(i), g.fid, g.edge, n(g.length, 2), n(b.angle, 1),
                                       'su' if g.direction == 'up' else 'giù', n(b.r, 2), n(b.k), n(b.ba), n(b.bd), n(g.u1 - g.u0, 2)]))
            righe.append('')
            righe.append(f'Spessore mm;{n(data.thickness, 2)};Materiale;{self.doc.material};Sviluppo mm;'
                         f'{n(data.flat_size[0], 2)} x {n(data.flat_size[1], 2)}')
            Path(path).write_text('\n'.join(righe) + '\n', encoding='utf-8-sig')
            return _ok(message=f'Tabella pieghe salvata: {len(data.flanges)} pieghe.', path=path)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def _edit_sheet(self, fid: str, label: str, fn) -> dict:
        def wrap():
            sm = self._sheet_def(fid)
            if sm is None:
                raise SteelCADError('Questa lamiera non esiste più.', code='lamiera')
            fn(sm)
        return self._change(label, wrap)

    def add_flange(self, fid: str, edge: str | None, fields: dict, parent: str | None = None) -> dict:
        """Una flangia su un lato del contorno (edge) oppure sulla punta di un'altra flangia (parent)."""
        nuovo = {}
        prolunga = self._tab_extension(fid, parent) if parent else [0, 0]

        def fn(sm):
            fls = sm.setdefault('flanges', [])
            if parent:
                if not any(x['id'] == parent for x in fls + list(sm.get('folds') or [])):
                    raise SteelCADError(f'La flangia {parent} non c’è più.', code='flangia')
                if any(x.get('parent') == parent for x in fls):
                    raise SteelCADError(f'Sulla punta di {parent} c’è già una flangia: cliccala per cambiarla.',
                                        code='doppia')
            elif any(x.get('edge') == edge for x in fls):
                raise SteelCADError('Su questo lato c’è già una flangia: cliccala per cambiarla.', code='doppia')
            flid = self._free_id(sm, 'FL', {x['id'] for x in fls} | {x['id'] for x in sm.get('folds') or []})
            fl = {'id': flid, 'parent': parent} if parent else {'id': flid, 'edge': edge}
            if parent and any(prolunga):
                fl['extend'] = prolunga                 # continua anche sopra la linguetta attaccata alla madre
            fl.update(_flange_fields(fields))
            fl.setdefault('length', 30)
            fl.setdefault('angle', 90)
            fls.append(fl)
            nuovo['flange'] = flid
        r = self._edit_sheet(fid, f'Flangia sulla punta di {parent}' if parent else f'Flangia su {edge}', fn)
        if r['ok']:
            r['select'] = f'flange={fid}/{nuovo["flange"]}'
            # il primo angolo tra due bordi sulle punte: si chiede come chiuderlo (dritti o a 45°)
            data = getattr(self.result.body, 'sheet', None)
            sm = self._sheet_def(fid)
            if parent and data is not None and not sm.get('tip_corners')                     and any(nuovo['flange'] in c for c in data.tip_contacts):
                r['ask_tip_corners'] = {'feature': fid, 'modes': TIP_CORNERS}
        return r

    def set_tip_corners(self, fid: str, mode: str) -> dict:
        """Come si chiudono gli angoli tra i bordi piegati sulle punte: dritti con i lati lunghi interi,
        dritti con i lati corti interi, oppure tagliati a 45°."""
        if mode not in TIP_CORNERS:
            return {'ok': False, 'message': 'Tipo di angolo sconosciuto.'}

        def fn(sm):
            sm['tip_corners'] = mode
        return self._edit_sheet(fid, f'Angoli dei bordi: {TIP_CORNERS[mode]}', fn)

    def _tab_extension(self, fid: str, parent: str) -> list:
        """Se sulla parete (parent) c'è una linguetta che arriva fino alla sua punta, di quanto una flangia sulla
        punta deve andare oltre l'inizio e la fine della parete per coprirla: [inizio, fine] in mm."""
        import build123d as bd
        body = self.result.body
        data = getattr(body, 'sheet', None) if body is not None else None
        p = next((g for g in data.flanges if g.fid == parent), None) if data else None
        nome = f'{fid}/{parent}/esterno'
        if p is None or nome not in body.names:
            return [0, 0]
        dvec = p.frame()[0]
        vs = [bd.Vector(v) for f in body.face(nome) for v in bd.Face(f).vertices()]
        alto = max((v - p.origin).dot(dvec) for v in vs)
        us = [(v - p.origin).dot(p.xf) for v in vs if (v - p.origin).dot(dvec) > alto - 1e-3]
        e0, e1 = max(0.0, p.u0 - min(us)), max(0.0, max(us) - p.u1)
        return [round(e0, 3) if e0 > 1e-3 else 0, round(e1, 3) if e1 > 1e-3 else 0]

    def extend_over_tab(self, fid: str, flid: str) -> dict:
        """La flangia sulla punta continua sopra la linguetta attaccata alla parete madre (per un bordo unico)."""
        sm = self._sheet_def(fid)
        fl = next((x for x in (sm or {}).get('flanges') or [] if x['id'] == flid), None)
        if fl is None or not fl.get('parent'):
            return {'ok': False, 'code': 'flangia', 'message': 'Si prolunga solo una flangia piegata sulla punta di un’altra.'}
        prolunga = self._tab_extension(fid, fl['parent'])
        if not any(prolunga):
            return {'ok': False, 'code': 'linguetta', 'message': f'Sulla punta di {fl["parent"]} non c’è una linguetta '
                    'da coprire: la flangia arriva già fino in fondo.'}

        def fn(sm):
            next(x for x in sm['flanges'] if x['id'] == flid)['extend'] = prolunga
        return self._edit_sheet(fid, f'{flid}: prolungata sopra la linguetta', fn)

    def edit_flange(self, fid: str, flid: str, fields: dict) -> dict:
        def fn(sm):
            fl = next(x for x in sm['flanges'] if x['id'] == flid)
            fl.update(_flange_fields(fields))
        return self._edit_sheet(fid, f'{flid}: modifica', fn)

    def delete_flange(self, fid: str, flid: str) -> dict:
        if any(x['id'] == flid for x in (self._sheet_def(fid) or {}).get('folds') or []):
            return self.delete_fold(fid, flid)
        def fn(sm):
            via = {flid}                       # con lei se ne vanno le flange piegate sulla sua punta
            while True:
                altre = {x['id'] for x in sm['flanges'] if x.get('parent') in via} - via
                if not altre:
                    break
                via |= altre
            sm['flanges'] = [x for x in sm['flanges'] if x['id'] not in via]
            sm['corners'] = [c for c in sm.get('corners') or [] if not {c.get('over'), c.get('under')} & via]
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

    def sketch_add_polyline(self, sid: str, pts: list, closed: bool, construction: bool = False,
                            angles: list | None = None) -> dict:
        n = len(pts) - (0 if closed else 1)
        cosa = 'Linee di costruzione' if construction else ('Contorno' if closed else 'Linee')
        return self._sketch_change(f'{cosa} ({n} tratti)',
                                   lambda: sketch_ops.add_polyline(self.doc, sid, pts, closed, construction, angles))

    def sketch_add_rectangle(self, sid: str, p0, p1, construction: bool = False) -> dict:
        return self._sketch_change('Rettangolo' + (' di costruzione' if construction else ''),
                                   lambda: sketch_ops.add_rectangle(self.doc, sid, p0, p1, construction))

    def sketch_add_circle(self, sid: str, center, r, construction: bool = False) -> dict:
        return self._sketch_change(f'Cerchio Ø{fmt_mm(round(2 * float(r), 2))}',
                                   lambda: sketch_ops.add_circle(self.doc, sid, center, r, construction))

    def sketch_add_slot(self, sid: str, c1, c2, r, construction: bool = False) -> dict:
        return self._sketch_change(f'Asola larga {fmt_mm(round(2 * float(r), 2))}',
                                   lambda: sketch_ops.add_slot(self.doc, sid, c1, c2, r, construction))

    def sketch_add_arc3(self, sid: str, p1, p2, p3, construction: bool = False) -> dict:
        return self._sketch_change('Arco per tre punti', lambda: sketch_more.add_arc3(self.doc, sid, p1, p2, p3, construction))

    def sketch_add_polygon(self, sid: str, center, vertex, n, construction: bool = False) -> dict:
        return self._sketch_change(f'Poligono a {int(_number(n))} lati',
                                   lambda: sketch_more.add_polygon(self.doc, sid, center, vertex, int(_number(n)), construction))

    def sheet_fold(self, sid: str, angle, direction: str = 'up', flip: bool = False) -> dict:
        """Piega lungo la linea disegnata (sulla faccia sopra/sotto della base o sullo sviluppo): la lamiera si piega
        lì, la parte più piccola sale; lo sviluppo resta quello disegnato. Lo sketch si consuma."""
        try:
            sk = self.doc.sketch(sid)
            piano = sk.plane if isinstance(sk.plane, dict) else {}
            fid = piano.get('flat') or (piano.get('face') or '').split('/')[0]
            sm = self._sheet_def(fid)
            data = getattr(self.result.body, 'sheet', None) if self.result.body is not None else None
            if sm is None or data is None or not (piano.get('flat') or (piano.get('face') or '').split('/')[-1] in ('sopra', 'sotto')):
                raise SteelCADError('La piega su linea si disegna sulla base: sulla faccia di sopra o di sotto, oppure sullo '
                                    'sviluppo.', code='piega')
            linee = [k for k, e in sk.entities.items() if e['kind'] == 'line' and not e.get('ref') and not e.get('construction')]
            if len(linee) != 1:
                raise SteelCADError('Disegna una sola linea: è dove si piega (lo spigolo esterno della piega).', code='piega')
            ss = self.doc.solved_sketch(sid)
            fatto = self.doc._sketch_results.get(sid)
            pl_sk = fatto[1].plane if fatto and fatto[1] is not None else self.doc._plane(sk, self.result.body)
            e = sk.entities[linee[0]]
            pts = []
            for p in (e['a'], e['b']):
                q = data.plane.to_local_coords(pl_sk.from_local_coords(ss.points[p]))
                pts.append([round(q.X, 6), round(q.Y, 6)])
            if direction not in VERSI:
                raise SteelCADError('Verso della piega: su o giù.', code='piega')
        except SteelCADError as ex:
            return _err(ex)

        def fn():
            folds = sm.setdefault('folds', [])
            usati = {x['id'] for x in folds} | {x['id'] for x in sm.get('flanges') or []}
            n = 1
            while f'PL{n}' in usati:
                n += 1
            folds.append({'id': f'PL{n}', 'a': pts[0], 'b': pts[1], 'angle': _number(angle), 'direction': direction,
                          'flip': bool(flip)})
            self.doc.features = [f for f in self.doc.features if f is not sk]   # la linea è diventata la piega
        r = self._change('Piega su linea', fn)
        if r['ok']:
            r['message'] = 'Piegata lungo la linea: lo sviluppo resta quello disegnato.'
        return r

    def edit_fold(self, fid: str, foid: str, fields: dict) -> dict:
        def fn(sm):
            fo = next(x for x in sm.get('folds') or [] if x['id'] == foid)
            if 'angle' in fields and str(fields['angle']).strip() != '':
                fo['angle'] = _number(fields['angle'])
            if fields.get('direction') in VERSI:
                fo['direction'] = fields['direction']
            if 'flip' in fields:
                fo['flip'] = bool(fields['flip'])
        return self._edit_sheet(fid, f'{foid}: modifica', fn)

    def delete_fold(self, fid: str, foid: str) -> dict:
        def fn(sm):
            via = {foid}
            while True:
                altre = {x['id'] for x in sm.get('flanges') or [] if x.get('parent') in via} - via
                if not altre:
                    break
                via |= altre
            sm['folds'] = [x for x in sm.get('folds') or [] if x['id'] != foid]
            sm['flanges'] = [x for x in sm.get('flanges') or [] if x['id'] not in via]
        return self._edit_sheet(fid, f'Elimina {foid}', fn)

    def _tip_contact(self, fid: str, flid: str):
        """La punta della flangia appoggia su un'altra faccia piana del pezzo? La punta si calcola dalla flangia (se
        tocca, nella fusione la sua faccia sparisce). Ritorna (centro della punta, u0, u1, nome dell'altra faccia, altra)."""
        import build123d as bd
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Plane
        from cad_engine.sheetmetal import _section_points
        body = self.result.body
        data = getattr(body, 'sheet', None) if body is not None else None
        g = next((x for x in data.flanges if x.fid == flid), None) if data else None
        if g is None or g.child:
            return None
        q = _section_points(g, data.thickness)
        um = (g.u0 + g.u1) / 2
        centro = (g.p(um, *q['ot']) + g.p(um, *q['it'])) * 0.5
        dvec = g.frame()[0].normalized()
        xf = g.xf.normalized()
        for nome, fs in body.names.items():
            if nome.startswith(f'{fid}/{flid}/'):
                continue
            for f in fs:
                if BRepAdaptor_Surface(f).GetType() != GeomAbs_Plane:
                    continue
                bf = bd.Face(f)
                m = bf.normal_at()
                if m.dot(dvec) > -0.999999 or abs((bf.center() - centro).dot(m)) > 1e-3:
                    continue
                # vicina alla punta (la punta può stare nel solco tra due pezzi della stessa faccia)
                if bf.distance_to(centro) <= data.thickness + 1e-3:
                    return centro, g.u0, g.u1, nome, bf
        return None

    def auto_tabs(self, fid: str, flid: str, n, w, gioco, sporgenza=0) -> dict:
        """Incastri automatici: la punta della flangia appoggia su un'altra faccia del pezzo. Sulla punta n linguette
        larghe w che passano attraverso la lamiera di sotto (sporgono di "sporgenza"), sull'altra faccia le asole
        (w + 2 gioco) × (spessore + 2 gioco). Si fanno con uno sketch e un taglio per le asole e uno sketch e
        "Aggiungi materiale" per le linguette: restano modificabili."""
        import build123d as bd
        from cad_engine.sketch.face_plane import plane_of
        try:
            n, w, c, sp = int(_number(n)), _number(w), _number(gioco), _number(sporgenza or 0)
            if n < 1 or w <= 0 or c < 0 or sp < 0:
                raise SteelCADError('Numero di linguette almeno 1, larghezza maggiore di zero, gioco e sporgenza non negativi.',
                                    code='incastri')
            contatto = self._tip_contact(fid, flid)
            if contatto is None:
                raise SteelCADError(f'La punta di {flid} non appoggia su un’altra faccia del pezzo: gli incastri si fanno dove '
                                    'una flangia finisce contro un’altra parete.', code='incastri')
            centro, u0, u1, altra_nome, altra = contatto
            data = self.result.body.sheet
            g = next(x for x in data.flanges if x.fid == flid)
            t = data.thickness
            xf = g.xf.normalized()
            if (u1 - u0) / (n + 1) < w + 2 * c + 2:
                raise SteelCADError(f'{n} linguette da {fmt_mm(w)} non stanno sulla punta lunga {fmt_mm(round(u1 - u0, 1))} mm.',
                                    code='incastri')
            base_u = (centro - g.origin).dot(xf)
            centri = [centro + xf * (u0 + (u1 - u0) * (i + 1) / (n + 1) - base_u) for i in range(n)]
            dvec, nrm = g.frame()
            dvec, nrm = dvec.normalized(), nrm.normalized()
            body = self.result.body
            nome_est = f'{fid}/{flid}/esterno'
            if nome_est not in body.names:
                raise SteelCADError(f'Non trovo la faccia esterna di {flid}.', code='incastri')
            est = bd.Face(body.face(nome_est)[0])
            ne, oe = est.normal_at(), est.center()
            sul_est = lambda p: p - ne * (p - oe).dot(ne)  # noqa: E731
        except SteelCADError as ex:
            return _err(ex)

        def fn():
            # 1) le asole sulla faccia dove appoggia la punta
            sk1 = self.doc.add_sketch({'face': altra_nome}, f'Sketch: asole per le linguette di {flid}')
            pl1 = plane_of(body, altra_nome, sk1)
            sketch_ops.add_reference_edges(sk1, altra, pl1, body.shape)
            for C in centri:
                q = [pl1.to_local_coords(C + xf * a * (w / 2 + c) + nrm * b * (t / 2 + c)) for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                ids = [sk1.point(p.X, p.Y) for p in q]
                for pid in ids:
                    sk1.constrain('fix', pid)
                for a_, b_ in zip(ids, ids[1:] + ids[:1]):
                    sk1.line(a_, b_)
            self.doc.add_feature('sheet_cut', f'Asole per {flid}', sketch=sk1.id)
            # 2) le linguette sulla punta, nel piano della flangia, attraverso le asole
            sk2 = self.doc.add_sketch({'face': nome_est}, f'Sketch: linguette di {flid}')
            pl2 = plane_of(body, nome_est, sk2)
            sketch_ops.add_reference_edges(sk2, est, pl2, body.shape)
            lungo = t + sp                                    # attraverso la lamiera di sotto, più la sporgenza
            for C in centri:
                q = [pl2.to_local_coords(sul_est(C + xf * a * (w / 2) + dvec * d)) for a, d in ((-1, -1), (1, -1), (1, lungo), (-1, lungo))]
                ids = [sk2.point(p.X, p.Y) for p in q]
                for pid in ids:
                    sk2.constrain('fix', pid)
                for a_, b_ in zip(ids, ids[1:] + ids[:1]):
                    sk2.line(a_, b_)
            self.doc.add_feature('sheet_cut', f'Linguette di {flid}', sketch=sk2.id, mode='add')
        r = self._change(f'Incastri su {flid}', fn)
        if r['ok']:
            dove = self.doc.describe_face(altra_nome)
            for art, prep in (('la ', 'sulla '), ('il ', 'sul '), ('l’', 'sull’')):
                if dove.startswith(art):
                    dove = prep + dove[len(art):]
                    break
            r['message'] = f'{n} linguette su {flid} e {n} asole {dove}.'
        return r

    def _fold_selection(self, fid: str, foid: str) -> dict:
        sm = self._sheet_def(fid)
        fo = next(x for x in sm.get('folds') or [] if x['id'] == foid)
        data = getattr(self.result.body, 'sheet', None)
        geo = next((g for g in data.flanges if g.fid == foid), None) if data else None
        rows = [['Piega su linea', foid]]
        if geo:
            b = geo.bend
            rows += [['Lunghezza (calcolata)', f'{fmt_mm(round(geo.length, 2))} mm'],
                     ['Piega', f'{fmt_mm(b.angle)}°, R{fmt_mm(b.r)}, K {b.k:.3f}'.replace('.', ',')]]
        figlia = next((x['id'] for x in sm.get('flanges') or [] if x.get('parent') == foid), None)
        return {'kind': 'fold', 'feature': fid, 'fold': foid, 'title': f'Piega {foid}', 'rows': rows,
                'def': {'angle': fo.get('angle', 90), 'direction': fo.get('direction', 'up'), 'flip': bool(fo.get('flip'))},
                'tip_child': figlia,
                'highlight': self._face_indices(f'{fid}/{foid}') if self.result.body is not None else []}

    def _part_corner(self, sid, pid, v, tool):
        """Spigolo del pezzo (bordi arancio): si arrotonda/smussa il pezzo vero, non lo sketch."""
        cosa = f'Raccordo spigolo R{v}' if tool == 'fillet' else f'Smusso spigolo {v}'
        out = {}

        def fn():
            out.update(sketch_more.part_corner(self.doc, sid, pid, _number(v), tool))
        r = self._change(cosa, fn)
        if r['ok']:
            r['message'] = (f'{cosa}: ' + ('aggiunto materiale nello spigolo verso dentro.' if out.get('added')
                                           else 'tolta la punta dal pezzo.'))
        return r

    def _ref_corner(self, sid, l1, l2):
        try:
            return sketch_more.ref_corner_of_lines(self.doc.sketch(sid), l1, l2)
        except SteelCADError as ex:
            return ex

    def sketch_fillet(self, sid: str, pid: str, r) -> dict:
        if sketch_more.is_part_corner(self.doc.sketch(sid), pid):
            return self._part_corner(sid, pid, r, 'fillet')
        return self._sketch_change(f'Raccordo R{r}', lambda: sketch_more.fillet(self.doc, sid, pid, _number(r)))

    def sketch_fillet_lines(self, sid: str, l1: str, l2: str, c1, c2, r) -> dict:
        pid = self._ref_corner(sid, l1, l2)
        if isinstance(pid, Exception):
            return _err(pid)
        if pid:
            return self._part_corner(sid, pid, r, 'fillet')
        return self._sketch_change(f'Raccordo R{r}', lambda: sketch_more.fillet_lines(self.doc, sid, l1, l2, c1, c2, _number(r)))

    def sketch_chamfer_lines(self, sid: str, l1: str, l2: str, c1, c2, d) -> dict:
        pid = self._ref_corner(sid, l1, l2)
        if isinstance(pid, Exception):
            return _err(pid)
        if pid:
            return self._part_corner(sid, pid, d, 'chamfer')
        return self._sketch_change(f'Smusso {d}', lambda: sketch_more.chamfer_lines(self.doc, sid, l1, l2, c1, c2, _number(d)))

    def sketch_chamfer(self, sid: str, pid: str, d) -> dict:
        if sketch_more.is_part_corner(self.doc.sketch(sid), pid):
            return self._part_corner(sid, pid, d, 'chamfer')
        return self._sketch_change(f'Smusso {d}', lambda: sketch_more.chamfer(self.doc, sid, pid, _number(d)))

    def sketch_hole_type(self, sid: str, eids: list, spec: dict | None) -> dict:
        """Tipo di foro per i cerchi scelti: semplice (None), svasato {'tipo': 'svasato', 'D': 12, 'angolo': 90}
        o filettato {'tipo': 'filettato', 'M': 'M6'} (il cerchio diventa il preforo della filettatura)."""
        def fn():
            sk = self.doc.sketch(sid)
            cerchi = [e for e in eids if sk.entities.get(e, {}).get('kind') == 'circle' and not sk.entities[e].get('ref')]
            if not cerchi:
                raise SteelCADError('Scegli uno o più cerchi (i fori).', code='foro')
            for e in cerchi:
                ent = sk.entities[e]
                if not spec:
                    ent.pop('hole', None)
                    continue
                tipo = spec.get('tipo')
                if tipo == 'filettato':
                    m = str(spec.get('M', '')).upper().replace(' ', '')
                    if m not in FILETTI:
                        raise SteelCADError(f'Filettatura "{m}" non in tabella: {", ".join(FILETTI)}.', code='foro')
                    ent['hole'] = {'tipo': 'filettato', 'M': m}
                    self._set_diameter(sk, e, FILETTI[m][0])
                elif tipo == 'inserto':
                    codice = str(spec.get('codice', '')).strip()
                    D = _number(spec.get('D'))
                    if not codice:
                        raise SteelCADError('Scrivi il codice dell’inserto (es. quello del catalogo del fornitore).', code='foro')
                    if not D or D <= 0:
                        raise SteelCADError('Scrivi il diametro del foro per l’inserto, preso dal catalogo.', code='foro')
                    ent['hole'] = {'tipo': 'inserto', 'codice': codice, 'D': D}
                    self._set_diameter(sk, e, D)
                elif tipo == 'svasato':
                    D, ang = _number(spec.get('D')), _number(spec.get('angolo', 90))
                    if not 0 < ang < 180:
                        raise SteelCADError('L’angolo della svasatura va tra 0° e 180° (di solito 90°).', code='foro')
                    ent['hole'] = {'tipo': 'svasato', 'D': D, 'angolo': ang}
                else:
                    raise SteelCADError(f'Tipo di foro "{tipo}" sconosciuto.', code='foro')
        testo = ('Foro semplice' if not spec else 'Foro filettato ' + str(spec.get('M', '')) if spec.get('tipo') == 'filettato'
                 else 'Foro per inserto ' + str(spec.get('codice', '')) if spec.get('tipo') == 'inserto'
                 else f'Foro svasato Ø{spec.get("D")}')
        return self._sketch_change(testo, fn)

    @staticmethod
    def _set_diameter(sk, cid, d):
        q = next((k for k, c in sk.constraints.items() if c['type'] == 'diameter' and c['refs'] == [cid]), None)
        if q:
            sk.constraints[q]['value'] = d
        else:
            sk.entities[cid]['r'] = d / 2
            sk.dimension('diameter', cid, value=d)

    def sketch_construction(self, sid: str, eids: list, flag: bool) -> dict:
        return self._sketch_change('In costruzione' if flag else 'Da costruzione a normale',
                                   lambda: sketch_edit.set_construction(self.doc, sid, eids, flag))

    def sketch_offset_preview(self, sid: str, eids: list, dist, side: str) -> dict:
        try:
            return _ok(preview=sketch_edit.offset_preview(self.doc, sid, eids, _number(dist), side))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def sketch_offset_side(self, sid: str, eids: list, dist, point) -> dict:
        try:
            return _ok(**sketch_edit.offset_side(self.doc, sid, eids, _number(dist), point))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def sketch_offset(self, sid: str, eids: list, dist, side: str) -> dict:
        return self._sketch_change(f'Offset {dist}', lambda: sketch_edit.offset(self.doc, sid, eids, _number(dist), side))

    def sketch_trim_preview(self, sid: str, eid: str, click) -> dict:
        try:
            return _ok(**sketch_trim.trim_preview(self.doc, sid, eid, click))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def sketch_trim(self, sid: str, eid: str, click) -> dict:
        return self._sketch_change(f'Taglia {eid}', lambda: sketch_trim.trim(self.doc, sid, eid, click))

    def sketch_extend_preview(self, sid: str, eid: str, click) -> dict:
        try:
            return _ok(**sketch_trim.extend_preview(self.doc, sid, eid, click))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def sketch_extend(self, sid: str, eid: str, click) -> dict:
        return self._sketch_change(f'Allunga {eid}', lambda: sketch_trim.extend(self.doc, sid, eid, click))

    def sketch_mirror(self, sid: str, eids: list, axis: str) -> dict:
        return self._sketch_change(f'Specchia su {axis}', lambda: sketch_edit.mirror(self.doc, sid, eids, axis))

    def sketch_copy(self, sid: str, eids: list, dx, dy) -> dict:
        return self._sketch_change('Copia', lambda: sketch_edit.copy(self.doc, sid, eids, _number(dx), _number(dy)))

    def sketch_move(self, sid: str, eids: list, dx, dy) -> dict:
        return self._sketch_change('Sposta', lambda: sketch_edit.move(self.doc, sid, eids, _number(dx), _number(dy)))

    def sketch_pattern(self, sid: str, eids: list, cols, px, rows, py) -> dict:
        return self._sketch_change(f'Serie {cols} × {rows}', lambda: sketch_edit.pattern(
            self.doc, sid, eids, int(_number(cols)), _number(px), int(_number(rows)), _number(py)))

    def sketch_dimension(self, sid: str, kind: str, refs: list) -> dict:
        return self._sketch_change('Quota', lambda: sketch_edit.add_dimension(self.doc, sid, kind, refs))

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
            import build123d as bd
            from cad_engine.sketch.face_plane import plane_of
            faccia = bd.Face(self.result.body.face(face_name)[0])
            piano = plane_of(self.result.body, face_name, sk)
            sketch_ops.add_reference_edges(sk, faccia, piano, self.result.body.shape)
            # le sagome delle parti che arrivano a pochi mm dalla faccia (es. la testata di un profilo)
            data = getattr(self.result.body, 'sheet', None)
            from app import sketch_border
            sketch_border.add_nearby_edges(sk, self.result.body, faccia, piano, 3 * data.thickness if data else 5.0)
        r = self._change('Sketch su faccia', fn)
        if r['ok']:
            r['sketch'] = nuovo['id']
        return r

    def sketch_close(self, sid: str) -> dict:
        """Uscendo da uno sketch su faccia o sullo sviluppo appena aperto e lasciato vuoto, lo si toglie: era
        solo un clic su "Disegna qui", non deve restare nell'albero (si annulla la sua creazione)."""
        try:
            sk = self.doc.sketch(sid)
        except SteelCADError:
            return _ok(state=self.state())
        vuoto = not any(e['kind'] in ('line', 'circle', 'arc') and not e.get('ref') for e in sk.entities.values())
        usato = any(not isinstance(f, Sketch) and f.get('sketch') == sid for f in self.doc.features)
        ultimo = self.history.labels()['undo'][:1]
        if isinstance(sk.plane, dict) and vuoto and not usato and ultimo and ultimo[0] in ('Sketch su faccia',
                                                                                           'Sketch sullo sviluppo'):
            self.history.undo()
            self.history.undone.pop()
            self._rebuild()
        return _ok(state=self.state())

    def sketch_on_flat(self, fid: str | None = None) -> dict:
        """"Spiega": uno sketch nuovo sullo sviluppo della lamiera. Quello che ci disegni si taglia nel tratto
        piano dove cade e torna nel pezzo piegato al posto giusto."""
        data = getattr(self.result.body, 'sheet', None) if self.result.body is not None else None
        if data is None or (fid and data.feature != fid):
            return {'ok': False, 'code': 'lamiera', 'message': 'La lamiera non è costruita: prima sistema la scheda '
                    'Lamiera, poi si può disegnare sullo sviluppo.'}
        nuovo = {}

        def fn():
            sk = self.doc.add_sketch({'flat': data.feature}, 'Sketch: sullo sviluppo')
            nuovo['id'] = sk.id
            sketch_ops.add_reference_edges(sk, data.flat, data.plane)
        r = self._change('Sketch sullo sviluppo', fn)
        if r['ok']:
            r['sketch'] = nuovo['id']
        return r

    def create_from_sketch(self, sid: str, kind: str, values: dict) -> dict:
        """Dal contorno disegnato: lamiera (spessore + dati di piega) o piastra (estrusione)."""
        v = {k: _number(x) for k, x in (values or {}).items() if str(x).strip() != ''}
        sk = self.doc.sketch(sid)
        if isinstance(sk.plane, dict) and kind in ('louver', 'dimple'):
            if not sk.plane.get('face') or self._sheet_def(sk.plane['face'].split('/')[0]) is None:
                return {'ok': False, 'code': 'forma', 'message': 'Persiane e imbutiture si disegnano su una faccia della lamiera.'}
            campi = {'louver': ('width', 'height'), 'dimple': ('depth',)}[kind]
            if any(c not in v for c in campi):
                return {'ok': False, 'code': 'forma', 'message': 'Scrivi le misure della forma.'}

            def fn():
                self.doc.add_feature('sheet_form', 'Persiane' if kind == 'louver' else 'Imbutiture', sketch=sid, kind=kind,
                                     **{c: v[c] for c in campi})
            return self._change('Persiane' if kind == 'louver' else 'Imbutiture', fn)
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

    def sheet_tab(self, sid: str) -> dict:
        """Aggiungi materiale (linguetta): il contorno disegnato su una faccia piana della lamiera diventa lamiera
        dello stesso spessore nel piano della faccia. Se la spezzata parte e finisce sullo stesso bordo della faccia
        (le linee arancio), la si chiude lungo quel bordo."""
        import math as _m
        try:
            sk = self.doc.sketch(sid)
            if not isinstance(sk.plane, dict) or not (sk.plane.get('face') or '').startswith(tuple(
                    f['id'] + '/' for f in self.doc.features if not isinstance(f, Sketch) and f.get('type') == 'sheet')):
                raise SteelCADError('La linguetta si disegna su una faccia di una lamiera.', code='linguetta')
            ss = self.doc.solved_sketch(sid)
            P = ss.points
            linee = [k for k, e in sk.entities.items() if e['kind'] == 'line' and not e.get('construction')]
            chiudi = None
            if linee and not any(e['kind'] in ('circle', 'arc') and not e.get('construction') for e in sk.entities.values()):
                from app.sketch_edit import _chain
                try:
                    ordine, _, chiusa = _chain(sk, linee)
                except SteelCADError:
                    ordine, chiusa = None, True
                if ordine and not chiusa:
                    a, b = ordine[0], ordine[-1]
                    for k, e in sk.entities.items():
                        if e['kind'] != 'line' or not e.get('ref'):
                            continue
                        A, B = P[e['a']], P[e['b']]
                        L = _m.dist(A, B) or 1
                        sul = lambda q: abs((B[0] - A[0]) * (q[1] - A[1]) - (B[1] - A[1]) * (q[0] - A[0])) / L < 1e-4  # noqa: E731
                        if sul(P[a]) and sul(P[b]):
                            chiudi = (a, b)
                            break
                    if chiudi is None:
                        raise SteelCADError('Il contorno è aperto: chiudilo, oppure fallo partire e finire sullo stesso bordo '
                                            'della faccia (la linea arancio), e lo chiudo io lungo quel bordo.', code='linguetta')
        except SteelCADError as ex:
            return _err(ex)

        def fn():
            if chiudi:
                lid = sk.line(*chiudi)
                sk.entities[lid]['label'] = f'lato {lid}'
            self.doc.add_feature('sheet_cut', 'Linguetta', sketch=sid, mode='add')
        r = self._change('Aggiungi materiale (linguetta)', fn)
        if r['ok']:
            r['message'] = 'Linguetta aggiunta: lamiera dello stesso spessore nel piano della faccia, anche nello sviluppo.'
        return r

    def contour_flange(self, sid: str) -> dict:
        """Lamiera a contorno: la sezione disegnata (linee aperte, su una faccia di testata, che parte da un bordo
        libero della lamiera) diventa una catena di flange: ogni tratto una flangia, con l'angolo e il verso del
        disegno e la sua lunghezza (dallo spigolo vivo di una piega al successivo, come le quote esterne).
        Lo sketch viene consumato: dopo si modificano le flange come tutte le altre."""
        import math as _m
        import build123d as bd
        try:
            sk = self.doc.sketch(sid)
            data = getattr(self.result.body, 'sheet', None) if self.result.body is not None else None
            if not isinstance(sk.plane, dict) or not sk.plane.get('face') or data is None:
                raise SteelCADError('La lamiera a contorno si disegna su una faccia di una lamiera.', code='contorno')
            fatto = self.doc._sketch_results.get(sid)
            pl = fatto[1].plane if fatto and fatto[1] is not None else self.doc._plane(sk, self.result.body)
            ss = self.doc.solved_sketch(sid)
            linee = [k for k, e in sk.entities.items() if e['kind'] == 'line' and not e.get('construction')]
            if not linee or any(e['kind'] in ('circle', 'arc') and not e.get('construction') for e in sk.entities.values()):
                raise SteelCADError('Disegna la sezione della lamiera con linee (una spezzata aperta, senza cerchi).', code='contorno')
            from app.sketch_edit import _chain
            ordine_pt, _, chiusa = _chain(sk, linee)
            if chiusa:
                raise SteelCADError('La sezione è chiusa: per la lamiera a contorno serve una spezzata aperta, che parte '
                                    'da un bordo della lamiera.', code='contorno')
            pts = [pl.from_local_coords(ss.points[p]) for p in ordine_pt]
            n = pl.z_dir
            t = data.thickness
            centro = bd.Solid(self.result.body.shape).center()
            # il bordo libero da cui parte: perpendicolare alla faccia, con lo spigolo nel primo (o ultimo) punto
            scelta = None
            for e in data.free_edges:
                a, b = bd.Vector(*e['a']), bd.Vector(*e['b'])
                asse = (b - a).normalized()
                if abs(asse.dot(n)) < 0.999:
                    continue
                q = a + asse * ((pl.origin - a).dot(n) / asse.dot(n))      # il bordo visto in sezione (a metà spessore)
                if e['kind'] == 'edge':
                    normale = data.plane.z_dir
                else:
                    g = next(x for x in data.flanges if x.fid == e['ref'])
                    normale = g.frame()[1]
                for rovescia in (False, True):
                    p0 = pts[-1] if rovescia else pts[0]
                    for lato in (-1, 1):
                        if (p0 - (q + normale * (lato * t / 2))).length < 0.6:
                            scelta = (e, rovescia, q, normale, asse)
                            break
                    if scelta:
                        break
                if scelta:
                    break
            if scelta is None:
                raise SteelCADError('La sezione deve partire dallo spigolo di un bordo libero della lamiera (il lato della '
                                    'base o la punta di una flangia), su una faccia di testata, cioè perpendicolare a quel '
                                    'bordo. Se invece vuoi allargare la faccia su cui stai disegnando (materiale nel suo '
                                    'piano), usa «Aggiungi materiale».', code='contorno')
            e, rovescia, q, N, asse = scelta
            if rovescia:
                pts = pts[::-1]
            # la direzione "fuori" del bordo: nel piano, perpendicolare al bordo, lontano dal pezzo
            if e['kind'] == 'edge':
                fuori = asse.cross(N)
                if fuori.dot(q - centro) < 0:
                    fuori = -fuori
            else:
                g = next(x for x in data.flanges if x.fid == e['ref'])
                fuori = g.frame()[0]                                   # oltre la punta, lungo la flangia
            tratti = []
            n_cur, N_cur = fuori, N
            for i in range(len(pts) - 1):
                d = pts[i + 1] - pts[i]
                L = d.length
                if L < 1e-6:
                    raise SteelCADError('Due punti della sezione coincidono.', code='contorno')
                d = d / L
                cos_t = max(-1.0, min(1.0, n_cur.dot(d)))
                th = _m.degrees(_m.acos(cos_t))
                if th < 0.5:
                    raise SteelCADError(f'Il tratto {i + 1} della sezione continua dritto il precedente: unisci i due tratti '
                                        '(o allunga la base).', code='contorno')
                if th > 170:
                    raise SteelCADError(f'Al tratto {i + 1} la sezione torna indietro (oltre 170°): i risvolti schiacciati non '
                                        'sono ancora gestiti.', code='contorno')
                su = d.dot(N_cur) > 0
                zf = N_cur if su else -N_cur
                r = _m.radians(th)
                bello = lambda v: int(round(v)) if abs(v - round(v)) < 1e-3 else round(v, 2)  # noqa: E731
                tratti.append({'length': bello(L), 'angle': bello(th), 'direction': 'up' if su else 'down'})
                n_cur, N_cur = n_cur * _m.cos(r) + zf * _m.sin(r), n_cur * -_m.sin(r) + zf * _m.cos(r)
        except SteelCADError as ex:
            return _err(ex)
        nuove = []

        def fn():
            sm = self._sheet_def(data.feature)
            fls = sm.setdefault('flanges', [])
            usati = {x['id'] for x in fls}
            prima = None
            for i, tr in enumerate(tratti):
                flid = self._free_id(sm, 'FL', usati)
                usati.add(flid)
                fl = {'id': flid, **tr}
                if i == 0:
                    fl.update({'edge': e['ref']} if e['kind'] == 'edge' else {'parent': e['ref']})
                else:
                    fl['parent'] = prima
                fls.append(fl)
                nuove.append(flid)
                prima = flid
            self.doc.remove_feature(sid)                  # la sezione è diventata flange: lo sketch non serve più
        r = self._change(f'Lamiera a contorno ({len(tratti)} tratti)', fn)
        if r['ok']:
            r['message'] = f'Lamiera a contorno: {len(tratti)} flange ({", ".join(nuove)}), modificabili come le altre.'
        return r

    def sketch_xray(self, sid: str, on: bool) -> dict:
        """Vedi attraverso: i bordi e i fori di tutte le facce parallele (dietro e davanti) proiettati sulla
        faccia dello sketch, in arancio tratteggiato: ci si aggancia per riprendere fori o rifilare."""
        import build123d as bd
        from app import sketch_border
        from cad_engine.sketch.face_plane import plane_of
        sk = self.doc.sketch(sid)
        nome = sk.plane.get('face') if isinstance(sk.plane, dict) else None
        body = self.result.body
        if on and (not nome or body is None or nome not in body.names):
            return {'ok': False, 'code': 'xray', 'message': 'Vedi attraverso vale disegnando su una faccia del pezzo.'}

        def fn():
            if on:
                if any(e.get('xray') for e in sk.entities.values()):
                    return
                data = getattr(body, 'sheet', None)
                sketch_border.project_edges(sk, body, bd.Face(body.face(nome)[0]), plane_of(body, nome, sk), xray=True,
                                            salta='/'.join(nome.split('/')[:-1]), spessore=data.thickness if data else 0.0)
            else:
                sketch_border.remove_xray(sk)
        return self._change('Vedi attraverso' if on else 'Vedi attraverso: spento', fn, keep_broken=True)

    def _oltre(self) -> float | None:
        """Quanto oltre un bordo di piega chiudere uno scasso aperto: più di tutto lo sviluppo, così passa la piega
        e le flange che seguono (quello che esce dal pezzo non taglia niente)."""
        data = getattr(self.result.body, 'sheet', None) if self.result.body is not None else None
        return (max(data.flat_size) + 10.0) if data is not None else None

    def _refresh_face_refs(self, sid, sk) -> bool:
        """I bordi arancio di uno sketch su faccia rifatti dalla faccia del pezzo (ne mancava un pezzo)."""
        import build123d as bd
        from cad_engine.sketch.face_plane import plane_of
        nome = sk.plane.get('face') if isinstance(sk.plane, dict) else None
        body = self.result.body
        if not nome or body is None or nome not in body.names:
            return False

        def fn():
            sketch_ops.refresh_reference_edges(sk, bd.Face(body.face(nome)[0]), plane_of(body, nome, sk), body.shape)
        return self._change('Bordi del pezzo rifatti', fn, keep_broken=True)['ok']

    def _from_face_sketch(self, sid, sk, kind, v) -> dict:
        chiudi = None
        if kind == 'cut':
            # una spezzata da bordo a bordo: la chiudo lungo il bordo, dalla parte del pezzo più piccolo
            from app import sketch_border
            try:
                chiudi = sketch_border.border_closure(sk, self.doc.solved_sketch(sid).points, self._oltre())
            except SteelCADError as ex:
                if 'interrotto' not in ex.message or not self._refresh_face_refs(sid, sk):
                    return _err(ex)
                try:                                     # bordo rifatto dalla faccia vera: si riprova
                    chiudi = sketch_border.border_closure(sk, self.doc.solved_sketch(sid).points, self._oltre())
                except SteelCADError as ex2:
                    return _err(ex2)
        fr = next((f for f in self.result.features if f.id == sid), None)
        if not chiudi and (fr is None or not fr.ok):
            return {'ok': False, 'code': 'sketch', 'message': 'Prima chiudi il contorno: '
                    + (fr.message if fr else 'lo sketch non è costruibile.')}
        su = self._sheet_def(sk.plane.get('flat') or sk.plane['face'].split('/')[0])

        def fn():
            nuovi = {}

            def punto(p):
                if isinstance(p, tuple):                    # un punto nuovo, oltre il bordo
                    if p not in nuovi:
                        nuovi[p] = sk.point(p[1], p[2])
                        sk.constrain('fix', nuovi[p])
                    return nuovi[p]
                return p
            chiudi_ok = [(punto(a), punto(b), arco) for a, b, arco in chiudi or []]
            for a, b, arco in chiudi_ok:
                if arco:                                    # lungo uno spigolo raccordato: un arco uguale
                    e = sk.entities[arco]
                    sk.arc(e['center'], a, b) if e['start'] == a else sk.arc(e['center'], b, a)
                else:
                    lid = sk.line(a, b)
                    sk.entities[lid]['label'] = f'lato {lid}'
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
        if d and d['type'] in ('hdistance', 'vdistance') and (d['value'] or 0) < 0 and isinstance(v, (int, float)) and v > 0:
            v = -v                              # mostrata senza il meno: si tiene il verso di prima
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
        if self.asm is not None:
            return self._asm_undo(False)
        try:
            self.history.undo()
            self._rebuild()
            return _ok(state=self.state())
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def redo(self) -> dict:
        if self.asm is not None:
            return self._asm_undo(True)
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
            self.blank = False
            self.asm = None
            self._asm_ritorno = None
            return _ok(state=self.state())
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    # ================================================================ pagina iniziale
    def home_info(self) -> dict:
        """Per la pagina iniziale: i progetti recenti (quelli che esistono ancora) e il lavoro non salvato."""
        from datetime import datetime
        recenti = []
        for p in _read_recent():
            q = Path(p)
            if q.exists():
                recenti.append({'path': str(q), 'name': q.stem, 'folder': str(q.parent),
                                'when': datetime.fromtimestamp(q.stat().st_mtime).strftime('%d/%m/%Y %H:%M')})
        auto = project_io.autosave_path(_UNSAVED)
        nonsalvato = None
        if auto.exists():
            nonsalvato = {'when': datetime.fromtimestamp(auto.stat().st_mtime).strftime('%d/%m/%Y %H:%M')}
        return _ok(show=self.blank, recent=recenti, unsaved=nonsalvato)

    def recover_unsaved(self) -> dict:
        """Riapre il salvataggio automatico del progetto mai salvato (va poi salvato con un nome)."""
        try:
            doc = project_io.recover(_UNSAVED)
            self._set(doc)
            self.path = None
            self.history.dirty = True
            self.blank = False
            return _ok(state=self.state())
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def forget_recent(self, path: str) -> dict:
        _write_recent([p for p in _read_recent() if p != str(Path(path))])
        return self.home_info()

    # ================================================================ file
    def save(self, path: str | None = None) -> dict:
        if self.asm is not None:
            try:
                return self._asm_save(path)
            except SteelCADError as ex:
                return _err(ex)
        try:
            p = Path(path) if path else self.path
            if p is None:
                return {'ok': False, 'code': 'serve_percorso', 'message': 'Scegli dove salvare.'}
            self.path = project_io.save(self.doc, p)
            self.history.dirty = False
            _add_recent(self.path)
            return _ok(state=self.state(), path=str(self.path))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def open(self, path: str, recover: bool = False) -> dict:
        try:
            if str(path).endswith('.steelcad-asm'):
                return self._asm_open(path)
            self.asm = None
            self._asm_ritorno = None
            doc = project_io.recover(path) if recover else project_io.load(path)
            self._set(doc)
            self.path = Path(path)
            self.blank = False
            _add_recent(self.path)
            return _ok(state=self.state())
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def recovery_available(self, path: str) -> bool:
        return project_io.recovery_available(path)

    def autosave(self) -> dict:
        if self.asm is not None:
            return _ok(saved=False)
        if not self.history.dirty:
            return _ok(saved=False)
        try:
            dest = self.path or _UNSAVED
            project_io.autosave(self.doc, dest)
            return _ok(saved=True)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def export_step(self, path: str) -> dict:
        if self.asm is not None:
            try:
                return self.asm_export_step(path)
            except Exception as ex:  # noqa: BLE001
                return _err(ex)
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


def _guida_secondaria(sk, c) -> bool:
    """Quote "di servizio" delle linee di costruzione: la lunghezza e la coordinata lungo la guida.
    Di una guida verticale conta solo quanto dista dall'origine in orizzontale (e viceversa)."""
    ent = sk.entities
    if c['type'] == 'length':
        if isinstance(c['value'], str) and c['value'].isidentifier():
            return False                # la guida dell'offset: la sua lunghezza è "off1", si mostra
        return bool(ent.get(c['refs'][0], {}).get('construction'))
    if c['type'] not in ('hdistance', 'vdistance') or len(c['refs']) != 2:
        return False
    p = c['refs'][1]
    linee = [e for e in ent.values() if e['kind'] == 'line' and p in (e.get('a'), e.get('b'))]
    if not linee or not all(e.get('construction') for e in linee):
        return False
    for l in linee:
        a, b = ent[l['a']], ent[l['b']]
        verticale = abs(a['x'] - b['x']) < 1e-6
        orizzontale = abs(a['y'] - b['y']) < 1e-6
        if (verticale and c['type'] == 'hdistance') or (orizzontale and c['type'] == 'vdistance'):
            return False
    return True


_UNSAVED = Path.home() / 'Documents' / 'SteelCAD senza nome.steelcad'

# filettature metriche a passo grosso: (preforo, diametro nominale) in mm (UNI/ISO, valori di tabella)
FILETTI = {'M3': (2.5, 3), 'M4': (3.3, 4), 'M5': (4.2, 5), 'M6': (5.0, 6), 'M8': (6.8, 8), 'M10': (8.5, 10),
           'M12': (10.2, 12), 'M16': (14.0, 16)}


def _recent_file() -> Path:
    import os
    base = os.environ.get('STEELCAD_HOME') or os.path.join(os.environ.get('APPDATA') or str(Path.home()), 'SteelCAD')
    return Path(base) / 'recenti.json'


def _read_recent() -> list:
    import json
    try:
        v = json.loads(_recent_file().read_text(encoding='utf-8'))
        return [str(x) for x in v if isinstance(x, str)]
    except (OSError, ValueError):
        return []


def _write_recent(lista: list) -> None:
    import json
    try:
        f = _recent_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(lista[:10], ensure_ascii=False, indent=1), encoding='utf-8')
    except OSError:
        pass                                # i recenti sono una comodità: se non si scrive, pazienza


def _add_recent(path) -> None:
    p = str(Path(path).resolve())
    _write_recent([p] + [x for x in _read_recent() if x != p])


def _flange_fields(fields: dict) -> dict:
    out = {}
    for k in ('length', 'angle', 'gap'):
        if k in fields and str(fields[k]).strip() != '':
            out[k] = _number(fields[k])
    if 'extend' in fields:
        ext = [_number(x) if str(x).strip() != '' else 0 for x in (fields['extend'] or [0, 0])]
        if len(ext) != 2:
            raise SteelCADError('Il prolungamento vuole due misure: all’inizio e alla fine.', code='campo')
        out['extend'] = ext
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
