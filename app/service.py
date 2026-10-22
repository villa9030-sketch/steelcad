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
from app.tubi_service import TubiMixin  # noqa: E402
from cad_engine.topology import describe  # noqa: E402
from cad_engine.tree import project_tree  # noqa: E402
from cad_engine.units import fmt_mm  # noqa: E402

DIREZIONI = {'X+': (0, 1), 'X-': (0, -1), 'Y+': (1, 1), 'Y-': (1, -1), 'Z+': (2, 1), 'Z-': (2, -1)}
ANCORAGGI = {'center': 'centro', 'top': 'sopra', 'bottom': 'sotto', 'left': 'sinistra', 'right': 'destra',
             'top-left': 'sopra a sinistra', 'top-right': 'sopra a destra', 'bottom-left': 'sotto a sinistra',
             'bottom-right': 'sotto a destra'}


from cad_engine import __version__ as _VERSIONE  # noqa: E402


def _ok(**kw):
    return {'ok': True, **kw}


def _err(ex: Exception):
    if isinstance(ex, SteelCADError):
        return {'ok': False, 'message': ex.message, 'code': ex.code}
    # problemi di file: cartella che non c'è, file aperto in un altro programma, disco pieno
    nome = Path(getattr(ex, 'filename', '') or '').name
    if isinstance(ex, (FileNotFoundError, NotADirectoryError)):
        return {'ok': False, 'code': 'file', 'message': f'Il file o la cartella non c’è{": " + nome if nome else ""}. '
                'Scegli un’altra posizione.'}
    if isinstance(ex, PermissionError):
        return {'ok': False, 'code': 'file', 'message': f'Windows non mi lascia usare il file{" " + nome if nome else ""}: '
                'forse è aperto in un altro programma, o la cartella è protetta.'}
    if isinstance(ex, OSError):
        return {'ok': False, 'code': 'file', 'message': f'Non riesco a leggere o scrivere il file ({ex.strerror or ex}).'}
    traceback.print_exc()
    return {'ok': False, 'message': f'Errore interno ({type(ex).__name__}): {ex}. Segnalalo con il file del progetto.',
            'code': 'interno'}


class Service(AssemblyMixin, DrawingsMixin, ImportMixin, TubiMixin):
    def __init__(self):
        self.path: Path | None = None
        self._set(Document('Nuovo progetto'))
        self.blank = True                  # appena aperto, niente progetto: la UI mostra la pagina iniziale

    @staticmethod
    def _albero(doc, r) -> dict:
        """L'albero del progetto. Un errore in una scritta non deve mai bloccare lo stato: se no il pezzo cambia ma lo
        schermo resta al vecchio, e l'utente rifà la stessa cosa sentendosi dire che c'è già (19/10, angolo "180-64")."""
        try:
            return project_tree(doc, r)
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            from cad_engine.tree import _n
            figli = [_n(f.name or f.id, 'sketch', f.id) if isinstance(f, Sketch) else _n(f.get('name') or f['id'], f['type'], f['id'])
                     for f in doc.features]
            return _n(doc.meta.get('name') or 'Progetto', 'project', children=figli)

    def _set(self, doc: Document):
        self._contesto = None                      # un progetto aperto da solo non ha pezzi attorno
        for f in doc.features:                     # file fatti prima: pieghe su linea in ordine lungo il pezzo
            if not isinstance(f, Sketch) and f.get('type') == 'sheet':
                _rinumera_pieghe(f)
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
            return {**self._asm_state(), 'version': _VERSIONE}
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
            'version': _VERSIONE,
            'name': doc.meta.get('name'), 'path': str(self.path) if self.path else None,
            'quote': doc.meta.get('quote') or [],
            'dirty': self.history.dirty, 'undo': self.history.labels()['undo'][:1],
            'redo': self.history.labels()['redo'][:1],
            'tree': self._albero(doc, r), 'parameters': self._parameters(), 'mode': 'part',
            'can_back': bool(getattr(self, '_asm_ritorno', None)),
            'errors': [f.to_dict() for f in r.errors], 'warnings': avvisi,
            'bom': righe, 'bom_kg': total_kg(righe), 'cutlist': cl, 'info': info,
            'dimensions': self._dimensions(), 'scene_version': self.scene_version, 'sheet': sheet,
            'bend_default': self.bend_default(), 'from_template': bool(self._modelli()),
        }

    def _parameters(self):
        try:
            risolti = self.doc.resolved_parameters()
        except SteelCADError:
            risolti = {}
        nomi = self._etichette_parametri()

        def nome(k):
            if k in nomi:
                return nomi[k]
            # i parametri che nascono dai comandi: la fila di fori (px1, py1), l'offset (off1)
            m = re.fullmatch(r'(px|py|off)(\d+)', k)
            if m:
                return {'px': 'Distanza tra i fori della fila', 'py': 'Distanza tra le file',
                        'off': 'Distanza dal contorno'}[m.group(1)]
            return None
        return [{'name': k, 'value': v, 'resolved': risolti.get(k), 'label': nome(k)}
                for k, v in self.doc.parameters.items()]

    # le sigle dei parametri in parole, per il pannello: prima quelle dei campi del modello, poi le solite
    ETICHETTE_PARAMETRI = {'W': 'Larghezza', 'P': 'Profondità', 'L': 'Lunghezza', 'H': 'Altezza', 'sp': 'Spessore',
                           'ps': 'Passo sbarre', 'pr': 'Passo ripiani', 'D1': 'Ø grande', 'D2': 'Ø piccolo',
                           'D': 'Distanza', 'A': 'Lato A', 'B': 'Lato B', 'ex': 'Spostamento X', 'ey': 'Spostamento Y'}

    def _etichette_parametri(self) -> dict:
        nomi = dict(self.ETICHETTE_PARAMETRI)
        for t in self._modelli():
            for c in self.MODELLI_ST[t['kind']][1]:
                nomi[{'spessore': 'sp'}.get(c[0], c[0])] = c[1].split(' (')[0]
        return nomi

    def _modelli(self) -> list:
        """I modelli a misure (cancello, scaffale, cono…) da cui nasce il progetto."""
        return [f['template'] for f in self.doc.features if not isinstance(f, Sketch)
                and (f.get('template') or {}).get('kind') in self.MODELLI_ST]

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
                if not c.get('driven') and _guida_secondaria(f, c):
                    continue                    # delle linee di costruzione si mostra solo la distanza che conta
                # offset e serie: la stessa misura su tanti tratti/copie si mostra una volta sola
                expr = c['value']
                param = expr if isinstance(expr, str) and expr.isidentifier() else None
                m = re.fullmatch(r'\s*(\d+)\s*\*\s*([A-Za-z_]\w*)\s*', expr) if isinstance(expr, str) else None
                if m:
                    if m.group(1) != '1':
                        continue
                    param = m.group(2)
                if param:                       # la stessa misura (stesso parametro) si mostra una volta sola
                    if (param, c['type']) in visti:
                        continue
                    visti.add((param, c['type']))
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
                rif = bool(c.get('driven'))
                out.append({'sketch': f.id, 'dim': did, 'type': c['type'], 'expr': c['value'], 'driven': rif,
                            'local': not isinstance(f.plane, str),
                            'param': param,
                            # le distanze orizzontali/verticali "all'indietro" si leggono senza il meno: il verso
                            # lo dice la quota stessa
                            'value': v, 'shown': abs(v) if v is not None and c['type'] in ('hdistance', 'vdistance') else v,
                            'label': ('(' if rif else '') + ({'diameter': 'Ø', 'radius': 'R'}.get(c['type'], ''))
                            + fmt_mm(abs(v or 0) if c['type'] in ('hdistance', 'vdistance') else (v or 0)) + (')' if rif else ''),
                            'a': [ga.X, ga.Y, ga.Z], 'b': [gb.X, gb.Y, gb.Z]})
        return out

    def scene(self) -> dict:
        if self.asm is not None:
            return self._asm_scene()
        objs = []
        r = self.result
        if r.body is not None:
            m = self._mesh_del_pezzo(r.body)
            for f in m['faces']:
                f['label'] = self.doc.describe_face(f['name']) if f['name'] else 'faccia'
            from cad_engine import finiture
            objs.append({'id': 'body', 'kind': 'body', 'name': self.doc.meta.get('name'), **m,
                         'look': finiture.colore(self.doc.meta.get('finitura'))})
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
        if data is not None and data.free_edges and self._sheet_def(data.feature) is not None:   # coni e raccordi: niente
            sk = self.doc.sketch(self._sheet_def(data.feature)['sketch'])
            bordi_noti = []
            for e in data.free_edges:
                bordi_noti.append(e)
                testo = (f'punta di {e["ref"]}' if e['kind'] == 'tip' else
                         f'bordo di {e["ref"].split("/")[0]}' if e['kind'] == 'side' else sk.describe(e['ref']))
                bordi.append({**e, 'feature': data.feature, 'id': f'{e["kind"]}:{e["ref"]}',
                              'label': f'{testo} ({fmt_mm(round(e["length"], 1))} mm)', 'thickness': data.thickness})
            for e in self._bordi_liberi(r.body, data, bordi_noti):
                bordi.append({**e, 'feature': data.feature, 'thickness': data.thickness,
                              'label': f'bordo ({fmt_mm(round(e["length"], 1))} mm)'})
        return {'version': self.scene_version, 'objects': objs + self._oggetti_contesto(), 'nodes': nodi,
                'bend_edges': bordi, 'threads': self._filettature(), 'svasature_ko': self._svasature_ko(),
                'marks': [m['pezzo'] for m in (getattr(data, 'marks', None) or []) if m.get('pezzo')] if data is not None else []}

    def _mesh_del_pezzo(self, body) -> dict:
        """I triangoli del pezzo, tenuti per le ultime versioni: dopo Annulla/Rifai il pezzo è lo stesso oggetto di prima
        e non si ritriangola (con 400 fori era un secondo, 22/10). Si tiene anche il pezzo, così il suo id non torna."""
        tenute = getattr(self, '_mesh_tenute', [])
        for b, m in tenute:
            if b is body:
                return m
        m = tessellate(body.shape, body.names)
        self._mesh_tenute = ([(body, m)] + tenute)[:4]
        return m

    def _bordi_liberi(self, body, data, noti) -> list:
        """Gli altri bordi dritti liberi delle facce piane (materiale aggiunto, pieghe sui bordi…): dove si può
        piegare. Quelli che sono già bordi di base, punte o fianchi di parete restano a loro."""
        import build123d as bd
        import numpy as np
        from cad_engine.sheetmetal.edge_flange import fuori_dalla_vicina, mappa_spigoli
        t = data.thickness
        mappa = mappa_spigoli(body.shape)
        facce = [n for n in body.names if n.endswith('/esterno') or n.endswith('/sopra')]
        noti_seg = [(np.array(e['a'], dtype=float), np.array(e['b'], dtype=float)) for e in noti]

        def gia(p, q):
            m, d = (p + q) / 2, (q - p) / (np.linalg.norm(q - p) or 1)
            for a, b in noti_seg:
                u = (b - a) / (np.linalg.norm(b - a) or 1)
                if abs(abs(np.dot(u, d)) - 1) > 1e-4:
                    continue
                v = m - a
                if np.linalg.norm(v - u * np.dot(v, u)) < 1.5 * t and -t <= np.dot(v, u) <= np.linalg.norm(b - a) + t:
                    return True
            return False
        out, visti = [], set()
        for nome in facce:
            for f in body.names[nome]:
                F = bd.Face(f)
                if F.geom_type != bd.GeomType.PLANE:
                    continue
                n = F.normal_at()
                for e in F.outer_wire().edges():
                    if e.geom_type != bd.GeomType.LINE or e.length < 5:
                        continue
                    a, b = e.position_at(0), e.position_at(1)
                    if fuori_dalla_vicina(F, e, mappa, n) is None:
                        continue
                    pa = np.array([a.X, a.Y, a.Z]) - np.array([n.X, n.Y, n.Z]) * t / 2
                    pb = np.array([b.X, b.Y, b.Z]) - np.array([n.X, n.Y, n.Z]) * t / 2
                    if gia(pa, pb):
                        continue
                    chiave = tuple(np.round((pa + pb) / 2, 2))
                    if chiave in visti:
                        continue
                    visti.add(chiave)
                    out.append({'kind': 'libero', 'ref': nome, 'id': f'libero:{nome}:{chiave}', 'face': nome,
                                'ea': [a.X, a.Y, a.Z], 'eb': [b.X, b.Y, b.Z],
                                'a': pa.tolist(), 'b': pb.tolist(), 'length': e.length})
        return out

    def add_edge_flange(self, face: str, ea: list, eb: list, fields: dict) -> dict:
        """Piega sul bordo libero (ea, eb sulla faccia face): altezza, angolo, verso dentro/fuori."""
        nuovo = {}

        def fn():
            v = _edge_flange_fields(fields)
            v.setdefault('length', 20)
            nuovo['id'] = self.doc.add_feature('sheet_edge_flange', '', face=face, a=list(ea), b=list(eb), **v)
        r = self._change('Piega su un bordo', fn)
        if r.get('ok'):
            r['select'] = f'pb={nuovo["id"]}'
        return r

    def add_end_miter(self, fields: dict) -> dict:
        """Taglio di testa inclinato su tutto il profilo (a 45° per i cassoni a cornice): un piano unico per tutte le
        facce e le pieghe, che passa per lo spigolo esterno della testa."""
        if self.result.body is None or getattr(self.result.body, 'sheet', None) is None:
            return {'ok': False, 'message': 'Il taglio di testa si fa su una lamiera piegata.'}
        nuovo = {}

        def fn():
            v = {'angle': 45, 'gap': 0, 'end': 'entrambe', 'side': 'fuori', **_end_miter_fields(fields)}
            nuovo['id'] = self.doc.add_feature('sheet_miter', '', **v)
        r = self._change('Taglio di testa', fn)
        if r.get('ok'):
            r['select'] = f'tt={nuovo["id"]}'
        return r

    def edit_end_miter(self, fid: str, fields: dict) -> dict:
        def fn():
            self.doc.feature(fid).update(_end_miter_fields(fields))
        r = self._change(f'Cambia il taglio di testa {fid}', fn)
        if r.get('ok'):
            r['select'] = f'tt={fid}'
        return r

    def edit_edge_flange(self, fid: str, fields: dict) -> dict:
        def fn():
            self.doc.feature(fid).update(_edge_flange_fields(fields))
        r = self._change(f'Cambia la piega {fid}', fn)
        if r.get('ok'):
            r['select'] = f'pb={fid}'
        return r

    def _oggetti_contesto(self) -> list:
        """Aperto dall'assieme: gli altri pezzi attorno, nelle coordinate di questo pezzo (si vedono, non si cliccano)."""
        ctx = getattr(self, '_contesto', None)
        if not ctx:
            return []
        import numpy as np

        from cad_engine import assembly as A
        Rp, Tp = np.array(ctx['R'], dtype=float), np.array(ctx['T'], dtype=float)
        cache = self.__dict__.setdefault('_ctx_parti', {})
        out = []
        for k, (file, R, T) in enumerate(ctx['altri']):
            if file == str(self.path):
                continue                                 # il pezzo stesso (nuovo, ancora nell'elenco)
            try:
                chiave = (file, Path(file).stat().st_mtime)
                if chiave not in cache:
                    cache[chiave] = A.part_mesh(A.load_part(file))
                m = cache[chiave]
            except Exception:  # noqa: BLE001 - un pezzo vicino che non si legge: si va avanti senza
                continue
            M = Rp.T @ np.array(R, dtype=float)
            t = Rp.T @ (np.array(T, dtype=float) - Tp)
            mat = [M[0][0], M[0][1], M[0][2], t[0], M[1][0], M[1][1], M[1][2], t[1], M[2][0], M[2][1], M[2][2], t[2], 0, 0, 0, 1]
            out.append({'id': f'contesto{k}', 'kind': 'context', 'name': Path(file).stem, 'matrix': [float(v) for v in mat],
                        'positions': m['positions'], 'indices': m['indices'], 'faces': [], 'edges': m['edges']})
        return out

    def _svasature_ko(self) -> list:
        """Le svasature impossibili (più profonde dello spessore, o non più larghe del foro): il motore fa il foro dritto,
        qui dove disegnarle in rosso."""
        import math as _m
        out = []
        r = self.result
        sp = getattr(getattr(r.body, 'sheet', None), 'thickness', None) if r.body is not None else None
        if sp is None:
            return out
        for t in self.doc.features:
            if isinstance(t, Sketch) or t.get('type') not in ('sheet_cut', 'sheet') or not t.get('sketch'):
                continue
            fatto = (self.doc._sketch_results or {}).get(t['sketch'])
            if not fatto or fatto[1] is None:
                continue
            ss, pl = fatto[0], fatto[1].plane
            sk = self.doc.sketch(t['sketch'])
            for cid, (c, rr) in ss.circles.items():
                h = sk.entities[cid].get('hole') or {}
                if h.get('tipo') != 'svasato':
                    continue
                try:
                    D, ang = float(h.get('D', 0)), _m.radians(float(h.get('angolo', 90)))
                except (TypeError, ValueError):
                    continue
                prof = (D - 2 * rr) / 2 / _m.tan(ang / 2) if 0 < ang < _m.pi else 0
                if D > 2 * rr and prof <= sp + 1e-6:
                    continue
                q, n = pl.from_local_coords(ss.points[c]), (pl.z_dir if t.get('type') == 'sheet' else -pl.z_dir)
                out.append({'c': [q.X, q.Y, q.Z], 'n': [n.X, n.Y, n.Z], 'D': max(D, 2 * rr + 0.5), 'd': 2 * rr,
                            'h': min(max(prof, 0.3), sp * 2)})
        return out

    def _filettature(self) -> list:
        """I fori filettati da far vedere nel 3D: centro sulla faccia dello sketch, verso (dentro il pezzo), raggio
        nominale e quanto è lungo il foro (lo spessore della lamiera, o il pezzo attraversato)."""
        out = []
        r = self.result
        if r.body is None:
            return out
        import build123d as bd
        bb = bd.Solid(r.body.shape).bounding_box() if hasattr(r.body.shape, 'ShapeType') else None
        diag = (bb.size.X ** 2 + bb.size.Y ** 2 + bb.size.Z ** 2) ** 0.5 if bb is not None else 0.0
        sp = getattr(getattr(r.body, 'sheet', None), 'thickness', None)
        for t in self.doc.features:
            if isinstance(t, Sketch) or not t.get('sketch'):
                continue
            if not (t.get('type') == 'sheet_cut' or (t.get('type') == 'extrude' and t.get('operation') == 'cut')):
                continue
            fatto = (self.doc._sketch_results or {}).get(t['sketch'])
            if not fatto or fatto[1] is None:
                continue
            ss, pl = fatto[0], fatto[1].plane
            sk = self.doc.sketch(t['sketch'])
            for cid, (c, rr) in ss.circles.items():
                h = sk.entities[cid].get('hole') or {}
                if h.get('tipo') != 'filettato' or h.get('M') not in FILETTI:
                    continue
                q = pl.from_local_coords(ss.points[c])
                n = -pl.z_dir                                   # il foro entra nel pezzo dalla faccia dello sketch
                lungo = sp if sp else min(diag, 200.0)
                out.append({'c': [q.X, q.Y, q.Z], 'n': [n.X, n.Y, n.Z], 'r': FILETTI[h['M']][1] / 2, 'r0': rr, 'len': lungo,
                            'M': h['M'], 'passo': PASSI.get(h['M'], 1.0), 'faces': self._facce_del_foro(q, n, rr)})
        return out

    def _facce_del_foro(self, q, n, rr) -> list:
        """Le facce (indici della scena) della parete liscia del foro: nel 3D al loro posto si disegnano i filetti."""
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder
        from cad_engine.topology.naming import _faces_of
        out = []
        for i, f in enumerate(_faces_of(self.result.body.shape)):
            su = BRepAdaptor_Surface(f)
            if su.GetType() != GeomAbs_Cylinder or abs(su.Cylinder().Radius() - rr) > 1e-3:
                continue
            o, d = su.Cylinder().Axis().Location(), su.Cylinder().Axis().Direction()
            v = (q.X - o.X(), q.Y - o.Y(), q.Z - o.Z())
            lungo = v[0] * d.X() + v[1] * d.Y() + v[2] * d.Z()
            if max(0.0, v[0] ** 2 + v[1] ** 2 + v[2] ** 2 - lungo ** 2) < 1e-6:
                out.append(i)
        return out

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
                    foro = self._foro_della_faccia(f, dati['face']['name'] or '')
                    if foro:
                        dati['foro'] = foro
                        dati['title'] = f'Foro Ø{fmt_mm(round(foro["d"], 2))}'
                        h = foro['hole'] or {}
                        dati['rows'] = [['Tipo', {'filettato': f'filettato {h.get("M")} (preforo)', 'svasato': f'svasato Ø{h.get("D")} a {h.get("angolo")}°',
                                                  'inserto': f'per inserto {h.get("codice")}'}.get(h.get('tipo'), 'semplice')],
                                        ['Fori uguali nel disegno', str(len(foro['uguali']))]]
                    dati['rows'].append(['Area faccia', f'{dati["face"]["area"]:.1f} mm²'])
                    nome = dati['face']['name'] or ''
                    parti = nome.split('/')
                    sm = self._sheet_def(parti[0]) if parti else None
                    # la faccia di una piega sul bordo (di una parete o di un bordo libero): il pannello di quella piega
                    if sm is not None and len(parti) == 4 and parti[2] in ('u0', 'u1'):
                        fs = self._side_selection(parti[0], parti[1], parti[2])
                        fs['face'] = dati['face']
                        return _ok(selection=fs)
                    if parti and parti[0].startswith('PB') and len(parti) >= 2:
                        try:
                            pb = self.doc.feature(parti[0])
                        except SteelCADError:
                            pb = None
                        if pb is not None and not isinstance(pb, Sketch) and pb.get('type') == 'sheet_edge_flange':
                            fs = self.select('pb=' + parti[0])['selection']
                            fs['face'] = dati['face']
                            return _ok(selection=fs)
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
                forma = self._shape_template()
                if forma:
                    dati['tpl_id'], dati['template'] = forma
                    info = getattr(getattr(self.result.body, 'sheet', None), 'shape_info', None) or {}
                    if info.get('kind') == 'sezioni':
                        dati['forma'] = {k: info.get(k) for k in ('pezzi', 'spigoli', 'saldature_m', 'giunti_m',
                                                                  'divisione', 'foglio', 'avvisi', 'pieghe')}
                # esporta, spiega, sullo sviluppo: stanno nella barra in alto, non qui
                return _ok(selection=dati)
            if ':' in obj_id:
                return _ok(selection=self._node_selection(obj_id))
            if obj_id.startswith('struct='):
                return _ok(selection=self._structure_selection(obj_id[7:]))
            if obj_id.startswith('tt='):
                f_ = self.doc.feature(obj_id[3:])
                righe = []
                sd = getattr(self.result.body, 'sheet', None) if self.result.body is not None else None
                if sd is not None:
                    righe.append(['Sviluppo', ' × '.join(fmt_mm(round(v, 1)) for v in sd.flat_size) + ' mm'])
                return _ok(selection={'kind': 'endmiter', 'feature': f_['id'], 'title': 'Taglio di testa', 'rows': righe,
                                      'def': {'angle': f_.get('angle', 45), 'gap': f_.get('gap', 0),
                                              'end': f_.get('end', 'entrambe'), 'side': f_.get('side', 'fuori')}})
            if obj_id.startswith('pb='):
                f_ = self.doc.feature(obj_id[3:])
                return _ok(selection={'kind': 'edgeflange', 'feature': f_['id'], 'title': 'Piega sul bordo', 'rows': [],
                                      'def': {'length': f_.get('length', 20), 'angle': f_.get('angle', 90),
                                              'direction': 'down' if f_.get('side') == 'out' else 'up',
                                              'trim0': f_.get('trim0'), 'trim1': f_.get('trim1')},
                                      'highlight': self._face_indices(f_['id']) if self.result.body is not None else []})
            if obj_id.startswith('flange=') and obj_id.count('/') == 2:
                return _ok(selection=self._side_selection(*obj_id[7:].split('/')))
            if obj_id.startswith('flange='):
                fid_, flid_ = obj_id[7:].split('/')
                if any(x['id'] == flid_ for x in (self._sheet_def(fid_) or {}).get('folds') or []):
                    return _ok(selection=self._fold_selection(fid_, flid_))
                return _ok(selection=self._flange_selection(fid_, flid_))
            st_id, mid = obj_id.split('/')
            st = next(s for s in self.result.structures if s.id == st_id)
            m = next(x for x in st.members if x.id == mid)
            fdef = self.doc.feature(st_id)
            mdef = next((x for x in fdef.get('members') or [] if x['id'] == mid), None)
            if mdef is None:            # asta dello scheletro: profilo dello scheletro + le sue eccezioni
                k = next((x for x in fdef.get('skeletons') or [] if mid.startswith(x.get('id', '') + '.')), {})
                base = {'profile': k.get('profile')}
                if '-' in mid.split('.')[1] and k.get('connect'):
                    base['profile'] = k['connect'].get('profile') or base['profile']
                mdef = {**base, **(fdef.get('overrides') or {}).get(mid, {})}
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
                **self._info_lavorazioni(st, m),
            })
        except (KeyError, IndexError, StopIteration, ValueError):
            # un clic su qualcosa che intanto è sparito (pezzo ricostruito, asta cancellata): niente di grave
            return {'ok': False, 'code': 'sparito', 'message': 'Quello che hai cliccato non c’è più: riprova.'}
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
            fm = next((f for f in self.doc.features if not isinstance(f, Sketch) and f.get('type') in ('sheet_shape', 'step_lamiera')), None)
            if fm is None:
                return None
            data = getattr(self.result.body, 'sheet', None) if self.result.body is not None else None
            return {'feature': fm['id'], 'shape': True, 'methods': {'k': METODI['k']}, 'flanges': 0, 'after': [],
                    'def': {k: fm.get(k) for k in ('thickness', 'radius', 'method', 'k', 'bd90')} | {'method': 'k'},
                    'data': data.summary() if data is not None else None,
                    'missing': [] if fm.get('type') == 'step_lamiera' else      # raggio e spessore dallo STEP, K scritto
                    [m for m, k in (('raggio interno', 'radius'), ('K-factor', 'k')) if fm.get(k) in (None, '')]}
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

    def _side_selection(self, fid: str, flid: str, end: str) -> dict:
        sm = self._sheet_def(fid)
        fl = next(x for x in sm['flanges'] if x['id'] == flid)
        e = next((x for x in fl.get('ears') or [] if x.get('end') == end), None)
        if e is None:
            raise SteelCADError('Questa piega non c’è più.', code='piega')
        return {'kind': 'sidebend', 'feature': fid, 'flange': flid, 'end': end, 'title': 'Piega sul bordo', 'rows': [],
                'def': {'length': e.get('length', 20), 'angle': e.get('angle', 90),
                        'direction': 'down' if e.get('side') == 'out' else 'up'},
                'highlight': self._face_indices(f'{fid}/{flid}/{end}') if self.result.body is not None else []}

    # ================================================================ tasto destro sull'albero
    def _dipendenti_piega(self, ref: str) -> list:
        """Chi sparisce togliendo una piega (ref = 'SM1/FL1' o 'SM1/FL1/u0'): i disegni sulle sue facce (e sulle flange
        piegate sulla sua punta) e chi li usa."""
        parti = ref.split('/')
        sm = self._sheet_def(parti[0]) or {}
        if len(parti) == 3:
            prefissi = [ref + '/']
        else:
            via = {parti[1]}
            while True:
                altre = {x['id'] for x in sm.get('flanges') or [] if x.get('parent') in via} - via
                if not altre:
                    break
                via |= altre
            prefissi = [f'{parti[0]}/{x}/' for x in via]
        sopra = [Document._fid(f) for f in self.doc.features if isinstance(f, Sketch) and isinstance(f.plane, dict)
                 and any(str(f.plane.get('face', '')).startswith(px) for px in prefissi)]
        tutti = []
        for x in sopra:
            for y in [x] + self._dipendenti(x):
                if y not in tutti:
                    tutti.append(y)
        return [Document._fid(f) for f in self.doc.features if Document._fid(f) in tutti]

    def _dipendenti(self, fid: str) -> list:
        """Le lavorazioni che sparirebbero togliendo fid (chi la usa, e chi usa quelle), nell'ordine del progetto."""
        via, cambia = {fid}, True
        while cambia:
            cambia = False
            for f in self.doc.features:
                x = Document._fid(f)
                if x not in via and Document._deps(f) & via:
                    via.add(x)
                    cambia = True
        return [Document._fid(f) for f in self.doc.features if Document._fid(f) in via and Document._fid(f) != fid]

    def _etichetta(self, fid: str) -> str:
        f = self.doc.feature(fid)
        if isinstance(f, Sketch):
            return f.name if (f.name or '').startswith('Sketch') else f'Sketch «{f.name or fid}»'
        from cad_engine.tree import _feature_label
        fr = next((x for x in self.result.features if x.id == fid), None)
        return f.get('etichetta') or _feature_label(self.doc, f, fr)

    def tree_menu(self, kind: str, ref: str) -> dict:
        """Cosa si può fare su una voce dell'albero: modifica, rinomina, disattiva, elimina, perché è rossa."""
        try:
            if kind == 'flange':
                return _ok(voci=['modifica', 'elimina'], nome=None, errore=None, seleziona='flange=' + ref, sketch=None,
                           dipendenti=[self._etichetta(x) for x in self._dipendenti_piega(ref)])
            f = self.doc.feature(ref)
            fr = next((x for x in self.result.features if x.id == ref), None)
            sketch = ref if isinstance(f, Sketch) else f.get('sketch')
            pb = not isinstance(f, Sketch) and f.get('type') == 'sheet_edge_flange'
            tt = not isinstance(f, Sketch) and f.get('type') == 'sheet_miter'
            voci = ['modifica'] if sketch or pb or tt else []
            voci += ['rinomina']
            if not isinstance(f, Sketch) and f.get('sketch') and f.get('type') in ('sheet_cut', 'extrude', 'revolve')                     and (f.get('type') != 'extrude' or f.get('operation') == 'cut'):
                voci.append('serie')
            if not isinstance(f, Sketch) and f.get('type') != 'sheet':
                voci.append('attiva' if f.get('disattiva') else 'disattiva')
            voci.append('elimina')
            errore = fr.message if fr is not None and not fr.ok else None
            if errore:
                voci.append('perche')
            nome = (f.name if isinstance(f, Sketch) else f.get('etichetta')) or ''
            return _ok(voci=voci, nome=nome, errore=errore, sketch=sketch,
                       seleziona=('pb=' + ref) if pb else ('tt=' + ref) if tt else None,
                       dipendenti=[self._etichetta(x) for x in self._dipendenti(ref)])
        except SteelCADError as ex:
            return _err(ex)

    def tree_action(self, kind: str, ref: str, azione: str, valore=None) -> dict:
        if kind == 'flange':
            parti = ref.split('/')
            if azione != 'elimina':
                return {'ok': False, 'message': 'Azione sconosciuta.'}
            via = self._dipendenti_piega(ref)
            if not via:
                return self.set_ear(parti[0], parti[1], parti[2], False) if len(parti) == 3 else self.delete_flange(parti[0], parti[1])
            if any(x['id'] == parti[1] for x in (self._sheet_def(parti[0]) or {}).get('folds') or []):
                return {'ok': False, 'message': 'Su questa piega ci sono disegni: eliminali prima (tasto destro).'}

            def fn():                                   # prima i disegni sopra, poi la piega
                for x in reversed(via):
                    self.doc.features = [g for g in self.doc.features if Document._fid(g) != x]
                sm = self._sheet_def(parti[0])
                if len(parti) == 3:
                    fl = next(x for x in sm['flanges'] if x['id'] == parti[1])
                    fl['ears'] = [e for e in fl.get('ears') or [] if e.get('end') != parti[2]]
                else:
                    tolte = {parti[1]}
                    while True:
                        altre = {x['id'] for x in sm['flanges'] if x.get('parent') in tolte} - tolte
                        if not altre:
                            break
                        tolte |= altre
                    sm['flanges'] = [x for x in sm['flanges'] if x['id'] not in tolte]
                    sm['corners'] = [c for c in sm.get('corners') or [] if not {c.get('over'), c.get('under')} & tolte]
            r = self._change(f'Elimina la piega {ref}', fn)
            if r.get('ok'):
                r['message'] = f'Eliminata la piega e {len(via)} voci che stavano sopra.'
            return r
        try:
            f = self.doc.feature(ref)
        except SteelCADError as ex:
            return _err(ex)
        if azione == 'rinomina':
            nome = str(valore or '').strip()

            def fn():
                if isinstance(f, Sketch):
                    f.name = nome or None
                elif nome:
                    f['etichetta'] = nome
                else:
                    f.pop('etichetta', None)
            return self._change(f'Rinomina {ref}', fn)
        if azione in ('disattiva', 'attiva'):
            def fn():
                if azione == 'disattiva':
                    f['disattiva'] = True
                else:
                    f.pop('disattiva', None)
            return self._change(f'{"Disattiva" if azione == "disattiva" else "Attiva"} {ref}', fn, keep_broken=True)
        if azione == 'elimina':
            via = self._dipendenti(ref) + [ref]

            def fn():
                for x in reversed(via):                     # prima chi dipende, poi lei
                    self.doc.features = [g for g in self.doc.features if Document._fid(g) != x]
            r = self._change(f'Elimina {ref}', fn)
            if r.get('ok') and len(via) > 1:
                r['message'] = f'Eliminate {len(via)} voci (con quelle che dipendevano da questa).'
            return r
        return {'ok': False, 'message': 'Azione sconosciuta.'}

    def fold_frames(self, n: int = 6) -> dict:
        """Per l'animazione Spiega/Ripiega: il pezzo con le pieghe aperte a metà strada (angoli × k/n, k = n-1 … 1),
        dal piegato verso il piano. Solo la lamiera (le lavorazioni dopo non servono per vederla aprirsi). Coni e
        raccordi: niente (l'interfaccia fa una dissolvenza)."""
        import copy as _copy

        from cad_engine.expressions import evaluate
        from cad_engine.mesh import tessellate
        data = getattr(self.result.body, 'sheet', None) if self.result.body is not None else None
        sm = self._sheet_def(data.feature) if data is not None else None
        if sm is None:
            return _ok(frames=[])
        chiave = (self.scene_version, n)
        fatto = getattr(self, '_passi_piega', None)
        if fatto and fatto[0] == chiave:             # stesso pezzo: Spiega e poi Ripiega usano gli stessi passi
            return _ok(frames=fatto[1])
        d = self.doc.to_dict()
        k_sm = next(i for i, f in enumerate(d['features']) if f.get('id') == sm['id'])
        d['features'] = d['features'][:k_sm + 1]
        par = self.doc.resolved_parameters()

        def angolo(v, base=90.0):
            try:
                return float(evaluate(v, par, what='l’angolo')) if v not in (None, '') else base
            except Exception:  # noqa: BLE001
                return None
        frames = []
        for k in range(n - 1, 0, -1):
            dd = _copy.deepcopy(d)
            f = dd['features'][-1]
            f['_animazione'] = True
            ok = True
            for fl in (f.get('flanges') or []) + (f.get('folds') or []):
                a = angolo(fl.get('angle'))
                if a is None:
                    ok = False
                    break
                fl['angle'] = max(1.0, a * k / n)
                for e in fl.get('ears') or []:
                    a2 = angolo(e.get('angle'))
                    e['angle'] = max(1.0, (a2 or 90.0) * k / n)
            if not ok:
                return _ok(frames=[])
            try:
                doc2 = Document.from_dict(dd)
                r = doc2.rebuild()
            except Exception:  # noqa: BLE001
                break
            if r.body is None:
                break
            m = tessellate(r.body.shape)
            frames.append({'positions': m['positions'], 'indices': m['indices']})
        self._passi_piega = (chiave, frames)
        return _ok(frames=frames)

    def set_ear(self, fid: str, flid: str, end: str, on: bool, fields: dict | None = None) -> dict:
        """Piega sul fianco della parete, a 90° verso l'interno (on=False la toglie): altezza, quanto è lunga lungo
        il fianco (vuoto = tutto), distanza dal basso (vuota = dalla piega), gioco verso la parete vicina (0,2)."""
        if end not in ('u0', 'u1'):
            return {'ok': False, 'message': 'Fianco sconosciuto.'}
        fields = fields or {}

        def fn(sm):
            fl = next(x for x in sm['flanges'] if x['id'] == flid)
            if fl.get('parent'):
                raise SteelCADError('Le pieghe sul fianco si fanno sulle pareti piegate dalla base.', code='fianco')
            ears = [e for e in fl.get('ears') or [] if e.get('end') != end]
            if on:
                e = {'end': end}
                for k in ('length', 'height', 'from', 'gap', 'angle'):
                    v = str(fields.get(k, '')).strip()
                    if v != '':
                        e[k] = _number(v)
                if fields.get('side') in ('in', 'out'):
                    e['side'] = fields['side']
                elif fields.get('direction') in ('up', 'down'):     # dal pannello delle pieghe: su = verso dentro
                    e['side'] = 'in' if fields['direction'] == 'up' else 'out'
                e.setdefault('length', 20)
                e.setdefault('gap', 0.2)
                ears.append(e)
            fl['ears'] = ears
        r = self._edit_sheet(fid, f'Piega sul bordo di {flid}' if on else f'Via la piega sul bordo di {flid}', fn)
        if r.get('ok') and on:
            r['select'] = f'flange={fid}/{flid}/{end}'
        return r

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

    def _rules_file(self) -> dict:
        import json
        try:
            return json.loads(self._rules_path().read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def _save_rules(self, rules: list, default: dict | None = None):
        import json
        p = self._rules_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        d = default if default is not None else self._rules_file().get('default')
        out = {'format': 'steelcad-regole', 'rules': rules}
        if d:
            out['default'] = d
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')

    def bend_default(self) -> dict:
        """I dati di piega predefiniti (raggio, metodo, K o deduzione): valgono per ogni lamiera nuova
        quando non scrivi niente. Li decide l'utente (sono della sua piegatrice): senza, non c'è default."""
        d = self._rules_file().get('default') or {}
        return {k: d.get(k) for k in ('radius', 'method', 'k', 'bd90') if d.get(k) not in (None, '')}

    def set_bend_default(self, values: dict) -> dict:
        try:
            nomi = {'radius': 'il raggio interno', 'k': 'il K-factor', 'bd90': 'la deduzione a 90°'}
            # i predefiniti valgono per ogni lamiera nuova: numeri veri, niente espressioni
            v = {k: _numero(values.get(k), nomi[k]) for k in ('radius', 'k', 'bd90') if str(values.get(k, '')).strip() != ''}
            if v.get('radius', 0) < 0:
                raise SteelCADError('Il raggio interno non può essere negativo.', code='raggio')
            if not 0 <= v.get('k', 0.5) <= 1:
                raise SteelCADError('Il K-factor deve stare tra 0 e 1 (di solito 0,3–0,5).', code='k')
            if v.get('bd90', 1) <= 0:
                raise SteelCADError('La deduzione a 90° deve essere maggiore di zero.', code='bd90')
            v['method'] = values.get('method') or 'k'
            if v['method'] not in METODI:
                raise SteelCADError('Metodo di piega sconosciuto.', code='metodo')
            if 'radius' not in v:
                raise SteelCADError('Scrivi il raggio interno predefinito.', code='raggio')
            if v['method'] == 'k' and 'k' not in v:
                raise SteelCADError('Scrivi il K-factor predefinito.', code='k')
            self._save_rules(self._rules(), v)
            return _ok(default=self.bend_default(), message='Dati di piega predefiniti salvati.')
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def _con_default(self, values: dict, chiavi=('radius', 'k')) -> dict:
        """I campi di piega vuoti prendono il predefinito."""
        d = self.bend_default()
        out = dict(values or {})
        for k in chiavi:
            if str(out.get(k, '') or '').strip() == '' and d.get(k) is not None:
                out[k] = d[k]
        if not out.get('method') and d.get('method'):
            out['method'] = d['method']
        return out

    def sheet_rules(self) -> dict:
        return _ok(rules=self._rules(), material=self.doc.material, default=self.bend_default())

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
            if getattr(data, 'bend_rows', None) is not None:
                righe = ['Piega;Angolo °;Lunghezza linea mm;Correzione mm (già nello sviluppo)']
                for r_ in data.bend_rows:
                    righe.append(';'.join([str(r_['n']), n(r_['angle'], 2), n(r_['length'], 1),
                                           n(r_['correction']) if r_['correction'] is not None else '']))
                info = data.shape_info or {}
                righe += ['', f'{info.get("nome", "Forma")};Spessore mm;{n(data.thickness, 2)};Raggio interno mm;'
                              f'{n(data.tech.get("radius") or 0, 2)};K;{n(data.tech.get("k") or 0)};Sviluppo mm;'
                              f'{n(data.flat_size[0], 2)} x {n(data.flat_size[1], 2)}']
                Path(path).write_text('\n'.join(righe) + '\n', encoding='utf-8-sig')
                return _ok(message=f'Tabella pieghe salvata: {len(data.bend_rows)} pieghe.', path=path)
            righe = ['Piega;Flangia;Su;Lunghezza esterna mm;Angolo °;Verso;Raggio interno mm;K;BA mm;BD mm;Larghezza mm']
            for i, g in enumerate(data.in_ordine(), 1):
                b = g.bend
                righe.append(';'.join([str(i), g.fid, data.lato_di(g), n(g.length, 2), n(b.angle, 1),
                                       'su' if g.direction == 'up' else 'giù', n(b.r, 2), n(b.k), n(b.ba), n(b.bd), n(g.u1 - g.u0, 2)]))
            for i, e in enumerate(data.extra_bends or [], len(righe)):     # pieghe sui fianchi e sui bordi liberi
                righe.append(';'.join([str(i), e['flange'], e['edge'], n(e['length'], 2), n(e['angle'], 1),
                                       'su' if e['direction'] == 'up' else 'giù', n(e['r'], 2), n(e['k']), n(e['ba']), n(e['bd']),
                                       n(e['width'], 2)]))
            righe.append('')
            righe.append(f'Spessore mm;{n(data.thickness, 2)};Materiale;{self.doc.material};Sviluppo mm;'
                         f'{n(data.flat_size[0], 2)} x {n(data.flat_size[1], 2)}')
            Path(path).write_text('\n'.join(righe) + '\n', encoding='utf-8-sig')
            return _ok(message=f'Tabella pieghe salvata: {len(data.flanges) + len(data.extra_bends or [])} pieghe.', path=path)
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

    def gradino(self, fid: str, flid: str, altezza, angolo=45, lunghezza=20, verso: str = 'dentro') -> dict:
        """Gradino (joggle) sulla punta della parete flid: un tratto inclinato e una parete che torna parallela, spostata
        di «altezza» verso dentro o fuori (per sovrapporre due lamiere a filo, 22/10). La lunghezza del tratto inclinato
        si trova provando sul pezzo vero (lo spostamento misurato tra le due facce dalla stessa parte)."""
        import copy as _copy

        import build123d as bd
        import numpy as np
        try:
            h, ang, L = _numero(altezza, 'l’altezza del gradino'), _numero(angolo, 'l’angolo'), _numero(lunghezza, 'la lunghezza dopo il gradino')
            if h <= 0 or not 0 < ang < 90 or L <= 0:
                raise SteelCADError('Il gradino vuole un’altezza maggiore di zero, un angolo tra 1 e 89° e una lunghezza.', code='gradino')
            sm = self._sheet_def(fid)
            if sm is None or not any(x['id'] == flid for x in sm.get('flanges') or []):
                raise SteelCADError('Il gradino si fa sulla punta di una piega.', code='gradino')
            if any(x.get('parent') == flid for x in sm['flanges']):
                raise SteelCADError(f'Sulla punta di {flid} c’è già una piega.', code='gradino')
        except SteelCADError as ex:
            return _err(ex)
        par = self.doc.resolved_parameters()

        def costruisci(lung_a, dA, dB):
            """Le due pieghe nel progetto copiato: lo spostamento con segno (+ verso fuori) o None se non torna parallela."""
            d = _copy.deepcopy(self.doc.to_dict())
            f = next(x for x in d['features'] if x.get('id') == fid)
            usati = {x['id'] for x in f['flanges']} | {x['id'] for x in f.get('folds') or []}
            ida = next(f'FL{n}' for n in range(1, 999) if f'FL{n}' not in usati)
            idb = next(f'FL{n}' for n in range(1, 999) if f'FL{n}' not in usati | {ida})
            f['flanges'] += [{'id': ida, 'parent': flid, 'length': lung_a, 'angle': ang, 'direction': dA, 'position': 'inside'},
                             {'id': idb, 'parent': ida, 'length': L, 'angle': ang, 'direction': dB, 'position': 'inside'}]
            try:
                doc2 = Document.from_dict(d)
                r = doc2.rebuild()
            except Exception:  # noqa: BLE001
                return None, (ida, idb)
            if r.body is None or any(not x.ok for x in r.features):
                return None, (ida, idb)
            g = {x.fid: x for x in r.body.sheet.flanges}
            if abs(abs(g[idb].frame()[0].dot(g[flid].frame()[0])) - 1) > 1e-6:
                return None, (ida, idb)
            fa = bd.Face(r.body.names[f'{fid}/{flid}/esterno'][0])
            na = fa.normal_at(fa.center())
            for nome in (f'{fid}/{idb}/esterno', f'{fid}/{idb}/interno'):
                fb = bd.Face(r.body.names[nome][0])
                if fb.normal_at(fb.center()).dot(na) > 0.999:          # la faccia dalla stessa parte
                    return (fb.center() - fa.center()).dot(na), (ida, idb)
            return None, (ida, idb)
        voluto = h if verso == 'fuori' else -h
        scelta = None
        for dA, dB in (('up', 'down'), ('down', 'up'), ('down', 'down'), ('up', 'up')):
            la = h / math.sin(math.radians(ang)) + 4 * self.result.body.sheet.thickness
            s0, _ = costruisci(la, dA, dB)
            if s0 is not None and np.sign(s0) == np.sign(voluto):
                scelta = (dA, dB, la, s0)
                break
        if scelta is None:
            return {'ok': False, 'message': 'Il gradino non viene: prova un angolo diverso o una parete più lunga.'}
        dA, dB, la, s0 = scelta
        la1 = la + 2.0
        s1, _ = costruisci(la1, dA, dB)
        for _ in range(6):                                       # secanti: lo spostamento cresce dritto col tratto
            if s1 is None or abs(s1 - s0) < 1e-9:
                break
            la, s0, la1 = la1, s1, la1 + (voluto - s1) * (la1 - la) / (s1 - s0)
            s1, _ = costruisci(la1, dA, dB)
            if s1 is not None and abs(s1 - voluto) < 1e-4:
                break
        if s1 is None or abs(s1 - voluto) > 1e-3:
            return {'ok': False, 'message': 'Il gradino non viene con queste misure: prova un angolo più aperto o un gradino più alto.'}
        lung_a = round(la1, 4)

        def fn(sm_):
            usati = {x['id'] for x in sm_['flanges']} | {x['id'] for x in sm_.get('folds') or []}
            ida = next(f'FL{n}' for n in range(1, 999) if f'FL{n}' not in usati)
            idb = next(f'FL{n}' for n in range(1, 999) if f'FL{n}' not in usati | {ida})
            sm_['flanges'] += [{'id': ida, 'parent': flid, 'length': lung_a, 'angle': ang, 'direction': dA, 'position': 'inside'},
                               {'id': idb, 'parent': ida, 'length': L, 'angle': ang, 'direction': dB, 'position': 'inside'}]
        r = self._edit_sheet(fid, f'Gradino {fmt_mm(h)} mm sulla punta di {flid}', fn)
        if r.get('ok'):
            r['message'] = (f'Gradino di {fmt_mm(h)} mm verso {verso}: tratto inclinato {fmt_mm(round(lung_a, 2))} mm a {fmt_mm(ang)}°, '
                            f'poi {fmt_mm(L)} mm. Sono due pieghe sulla punta: si cambiano come le altre.')
        return r

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

    @staticmethod
    def _flangia(sm, flid):
        fl = next((x for x in sm['flanges'] if x['id'] == flid), None)
        if fl is None:
            raise SteelCADError(f'La flangia {flid} non c’è più.', code='flangia')
        return fl

    def edit_flange(self, fid: str, flid: str, fields: dict) -> dict:
        def fn(sm):
            fl = self._flangia(sm, flid)
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
            fl = self._flangia(sm, flid)
            fl.setdefault('holes', []).append({'u': _numero(u, 'la posizione'), 'v': _numero(v, 'la posizione'),
                                               'd': _numero(d, 'il diametro')})
        return self._edit_sheet(fid, f'Foro su {flid}', fn)

    def delete_flange_hole(self, fid: str, flid: str, index: int) -> dict:
        def fn(sm):
            fl = self._flangia(sm, flid)
            fori = fl.get('holes') or []
            i = int(_numero(index, 'il foro'))
            if not 0 <= i < len(fori):
                raise SteelCADError('Quel foro non c’è più.', code='foro')
            del fori[i]
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
        def forma_o_lamiera():
            f = self._sheet_def(fid)
            if f is None:
                g = self.doc.feature(fid)
                f = g if not isinstance(g, Sketch) and g.get('type') == 'sheet_shape' else None
            fn(f)
        return self._change('Dati di piega', forma_o_lamiera, keep_broken=True)

    # ---------------------------------------------------------------- disegno libero
    def sketch_view(self, sid: str) -> dict:
        try:
            return _ok(sketch=sketch_ops.view(self.doc, sid, self.result.body))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def _sketch_change(self, label, fn):
        # mentre si disegna lo sketch può restare aperto: la modifica si tiene comunque
        cambiate = []

        def con_rimedio():
            fn()
            # quote che litigano per un arrotondamento: la più recente diventa di riferimento (non blocca lo sketch)
            from app.sketch_edit import quasi_uguali_di_riferimento
            for f in self.doc.features:
                if isinstance(f, Sketch):
                    try:
                        cambiate.extend(quasi_uguali_di_riferimento(self.doc, f))
                    except SteelCADError:
                        pass
        r = self._change(label, con_rimedio, keep_broken=True)
        if r.get('ok') and cambiate:
            r['message'] = ('Quota di riferimento: ' + ', '.join(cambiate) + ' (la misura era già decisa dal disegno, '
                            'diversa solo per un arrotondamento).')
        return r

    def sketch_add_polyline(self, sid: str, pts: list, closed: bool, construction: bool = False,
                            angles: list | None = None) -> dict:
        try:
            if not isinstance(pts, (list, tuple)) or len(pts) < 2:
                raise SteelCADError('Per una linea servono almeno due punti.', code='punti')
            pts = [_punto(q) for q in pts]
        except SteelCADError as ex:
            return _err(ex)
        n = len(pts) - (0 if closed else 1)
        cosa = 'Linee di costruzione' if construction else ('Contorno' if closed else 'Linee')
        return self._sketch_change(f'{cosa} ({n} tratti)',
                                   lambda: sketch_ops.add_polyline(self.doc, sid, pts, closed, construction, angles))

    def sketch_add_rectangle(self, sid: str, p0, p1, construction: bool = False) -> dict:
        try:
            p0, p1 = _punto(p0, 'l’angolo'), _punto(p1, 'l’angolo')
        except SteelCADError as ex:
            return _err(ex)
        return self._sketch_change('Rettangolo' + (' di costruzione' if construction else ''),
                                   lambda: sketch_ops.add_rectangle(self.doc, sid, p0, p1, construction))

    def sketch_add_circle(self, sid: str, center, r, construction: bool = False) -> dict:
        try:
            center, r = _punto(center, 'il centro'), _numero(r, 'il raggio')
        except SteelCADError as ex:
            return _err(ex)
        return self._sketch_change(f'Cerchio Ø{fmt_mm(round(2 * float(r), 2))}',
                                   lambda: sketch_ops.add_circle(self.doc, sid, center, r, construction))

    def sketch_add_text(self, sid: str, pos, testo: str, h, angolo=0, stencil=None) -> dict:
        """Un testo da marcare col laser (numeri, codici, sigle): poi «Marca col laser». Con stencil ('saira' o
        'allerta') le lettere sono contorni chiusi da tagliare: poi «Togli materiale»."""
        try:
            pos, h = _punto(pos, 'la posizione'), _numero(h, 'l’altezza')
            angolo = _numero(angolo or 0, 'l’angolo')
            if stencil and stencil not in ('saira', 'allerta'):
                raise SteelCADError(f'Carattere «{stencil}» sconosciuto.', code='testo')
        except SteelCADError as ex:
            return _err(ex)
        return self._sketch_change(f'Testo «{str(testo)[:20]}»',
                                   lambda: sketch_ops.add_text(self.doc, sid, pos, testo, h, angolo, stencil or None))

    def sketch_add_slot(self, sid: str, c1, c2, r, construction: bool = False) -> dict:
        try:
            c1, c2, r = _punto(c1, 'il centro'), _punto(c2, 'il centro'), _numero(r, 'il raggio')
        except SteelCADError as ex:
            return _err(ex)
        return self._sketch_change(f'Asola larga {fmt_mm(round(2 * float(r), 2))}',
                                   lambda: sketch_ops.add_slot(self.doc, sid, c1, c2, r, construction))

    def sketch_add_arc3(self, sid: str, p1, p2, p3, construction: bool = False) -> dict:
        try:
            p1, p2, p3 = _punto(p1), _punto(p2), _punto(p3)
        except SteelCADError as ex:
            return _err(ex)
        return self._sketch_change('Arco per tre punti', lambda: sketch_more.add_arc3(self.doc, sid, p1, p2, p3, construction))

    def sketch_add_polygon(self, sid: str, center, vertex, n, construction: bool = False) -> dict:
        try:
            center, vertex, n = _punto(center, 'il centro'), _punto(vertex, 'il vertice'), _numero(n, 'il numero di lati')
            if n != int(n) or n < 3:
                raise SteelCADError('Un poligono ha almeno 3 lati (numero intero).', code='lati')
        except SteelCADError as ex:
            return _err(ex)
        return self._sketch_change(f'Poligono a {int(_number(n))} lati',
                                   lambda: sketch_more.add_polygon(self.doc, sid, center, vertex, int(_number(n)), construction))

    def sheet_fold(self, sid: str, angle, direction: str = 'up', flip: bool = False, bump: dict | None = None) -> dict:
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
            if not linee:
                raise SteelCADError('Disegna una linea dove si piega (lo spigolo esterno della piega); più linee = più '
                                    'pieghe, anche in serie per la calandratura a colpi (bumping).', code='piega')
            ss = self.doc.solved_sketch(sid)
            fatto = self.doc._sketch_results.get(sid)
            pl_sk = fatto[1].plane if fatto and fatto[1] is not None else self.doc._plane(sk, self.result.body)
            # una piega per linea, in ordine lungo il pezzo (così PL1, PL2... vanno da una parte all'altra)
            tratti = []
            for lid in linee:
                e = sk.entities[lid]
                pts = []
                for p in (e['a'], e['b']):
                    q = data.plane.to_local_coords(pl_sk.from_local_coords(ss.points[p]))
                    pts.append([round(q.X, 6), round(q.Y, 6)])
                tratti.append(pts)
            (ax, ay), (bx, by) = tratti[0]
            nx, ny = -(by - ay), bx - ax
            tratti.sort(key=lambda t: (t[0][0] + t[1][0]) * nx + (t[0][1] + t[1][1]) * ny)
            if direction not in VERSI:
                raise SteelCADError('Verso della piega: su o giù.', code='piega')
            colpi = self._bump(bump)
            if colpi and len(tratti) > 1:
                raise SteelCADError('I colpi col raggio grande si danno su una linea sola. Con più linee disegnate ogni linea è già un colpo: '
                                    'lascia vuoti colpi e raggio.', code='bump')
        except SteelCADError as ex:
            return _err(ex)

        def fn():
            folds = sm.setdefault('folds', [])
            for a, b in tratti:
                usati = {x['id'] for x in folds} | {x['id'] for x in sm.get('flanges') or []}
                n = 1
                while f'PL{n}' in usati:
                    n += 1
                folds.append({'id': f'PL{n}', 'a': a, 'b': b, 'angle': _number(angle), 'direction': direction,
                              'flip': bool(flip), **({'bump': colpi} if colpi else {})})
            _rinumera_pieghe(sm)
            self.doc.features = [f for f in self.doc.features if f is not sk]   # la linea è diventata la piega
        r = self._change('Piega su linea' if len(tratti) == 1 else f'{len(tratti)} pieghe su linea', fn)
        if r['ok']:
            r['message'] = ('Piegata lungo la linea' if len(tratti) == 1 else f'{len(tratti)} pieghe, una per linea') \
                + ': lo sviluppo resta quello disegnato.'
        return r

    @staticmethod
    def _bump(v) -> dict | None:
        """{'colpi', 'raggio'} scritti dall'utente; vuoti o 0 colpi: piega normale."""
        if not v or str(v.get('colpi', '')).strip() in ('', '0', '1'):
            return None
        colpi = _numero(v.get('colpi'), 'i colpi')
        if colpi != int(colpi) or not 2 <= colpi <= 200:
            raise SteelCADError('I colpi del bumping sono un numero intero da 2 a 200.', code='bump')
        raggio = _number(v.get('raggio'))
        if str(raggio).strip() == '':
            raise SteelCADError('Scrivi il raggio grande che vuoi ottenere con i colpi.', code='bump')
        return {'colpi': int(colpi), 'raggio': raggio}

    def edit_fold(self, fid: str, foid: str, fields: dict) -> dict:
        if 'bump' in fields:
            try:
                fields = {**fields, 'bump': self._bump(fields['bump'])}
            except SteelCADError as ex:
                return _err(ex)

        def fn(sm):
            fo = next((x for x in sm.get('folds') or [] if x['id'] == foid), None)
            if fo is None:
                raise SteelCADError(f'La piega {foid} non c’è più.', code='piega')
            if 'bump' in fields:
                if fields['bump']:
                    fo['bump'] = fields['bump']
                else:
                    fo.pop('bump', None)
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
        colpi = []
        if geo and fo.get('bump'):
            # i colpi: quota della battuta di ognuno, misurata nello sviluppo dalla linea disegnata (asse della piega)
            catena = [geo]
            while catena[-1].child:
                nxt = next((g for g in data.flanges if g.fid == catena[-1].child), None)
                if nxt is None or not nxt.fid.startswith(foid + '.'):
                    break
                catena.append(nxt)
            b1 = geo.bend
            passo = catena[0].length - 2 * b1.ossb + b1.ba if len(catena) > 1 else 0.0
            c1 = b1.ba / 2 - b1.ossb
            colpi = [round(c1 + i * passo, 2) for i in range(len(catena))]
            rows += [['Colpi', f'{len(catena)} × {fmt_mm(round(b1.angle, 2))}°'],
                     ['Passo nello sviluppo', f'{fmt_mm(round(passo, 2))} mm'],
                     ['Punzone', f'R{fmt_mm(b1.r)}, K {b1.k:.3f}'.replace('.', ',')]]
        elif geo:
            b = geo.bend
            rows += [['Lunghezza (calcolata)', f'{fmt_mm(round(geo.length, 2))} mm'],
                     ['Piega', f'{fmt_mm(b.angle)}°, R{fmt_mm(b.r)}, K {b.k:.3f}'.replace('.', ',')]]
        figlia = next((x['id'] for x in sm.get('flanges') or [] if x.get('parent') == foid), None)
        return {'kind': 'fold', 'feature': fid, 'fold': foid, 'title': f'Piega {foid}', 'rows': rows,
                'def': {'angle': fo.get('angle', 90), 'direction': fo.get('direction', 'up'), 'flip': bool(fo.get('flip')),
                        'bump': fo.get('bump')}, 'colpi': colpi,
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
        try:
            r = _numero(r, 'il raggio')
            if r < 0:                       # R0: le due linee si incontrano in uno spigolo vivo
                raise SteelCADError('Il raggio del raccordo non può essere negativo.', code='raccordo')
        except SteelCADError as ex:
            return _err(ex)
        return self._sketch_change(f'Raccordo R{r}', lambda: sketch_more.fillet_lines(self.doc, sid, l1, l2, c1, c2, r))

    def sketch_chamfer_lines(self, sid: str, l1: str, l2: str, c1, c2, d) -> dict:
        pid = self._ref_corner(sid, l1, l2)
        if isinstance(pid, Exception):
            return _err(pid)
        if pid:
            return self._part_corner(sid, pid, d, 'chamfer')
        try:
            d = _numero(d, 'lo smusso')
            if d < 0:                       # 0: le due linee si incontrano in uno spigolo vivo
                raise SteelCADError('Lo smusso non può essere negativo.', code='smusso')
        except SteelCADError as ex:
            return _err(ex)
        return self._sketch_change(f'Smusso {d}', lambda: sketch_more.chamfer_lines(self.doc, sid, l1, l2, c1, c2, d))

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
                self._applica_foro(sk, e, spec)
            # una svasatura impossibile si rifiuta qui, col perché (il motore non la blocca più: farebbe il foro dritto)
            sp = getattr(getattr(self.result.body, 'sheet', None), 'thickness', None) if self.result.body is not None else None
            if spec and spec.get('tipo') == 'svasato' and sp:
                import math as _m
                D, ang = float(_number(spec.get('D'))), _m.radians(float(_number(spec.get('angolo', 90))))
                try:
                    raggi = self.doc.solved_sketch(sid).circles
                except SteelCADError:
                    raggi = {}
                for e in cerchi:
                    d = 2 * (raggi[e][1] if e in raggi else sk.entities[e].get('r', 0))
                    if D <= d:
                        raise SteelCADError(f'La svasatura (Ø{fmt_mm(D)}) deve essere più larga del foro (Ø{fmt_mm(d)}).', code='foro')
                    h = (D - d) / 2 / _m.tan(ang / 2)
                    if h > sp + 1e-6:
                        raise SteelCADError(f'La svasatura Ø{fmt_mm(D)} a {fmt_mm(_m.degrees(ang))}° è profonda {fmt_mm(round(h, 2))} mm: '
                                            f'più dello spessore ({fmt_mm(sp)}). Riduci il diametro della svasatura.', code='foro')
        testo = ('Foro semplice' if not spec else 'Foro filettato ' + str(spec.get('M', '')) if spec.get('tipo') == 'filettato'
                 else 'Foro per inserto ' + str(spec.get('codice', '')) if spec.get('tipo') == 'inserto'
                 else f'Foro svasato Ø{spec.get("D")}')
        # su un foro già fatto (lo sketch è di un taglio) un tipo che rompe il pezzo si rifiuta e il pezzo resta com'era
        # (20/10: una svasatura più profonda dello spessore restava applicata e il pezzo in errore)
        if any(not isinstance(f, Sketch) and f.get('sketch') == sid for f in self.doc.features):
            return self._change(testo, fn)
        return self._sketch_change(testo, fn)

    def _applica_foro(self, sk, e, spec):
        """Il tipo di foro su un cerchio: semplice (spec vuoto), filettato, svasato, per inserto."""
        ent = sk.entities[e]
        if not spec:
            ent.pop('hole', None)
            return
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
            D, ang = _numero(spec.get('D'), 'il Ø della svasatura'), _numero(spec.get('angolo', 90), 'l’angolo')
            if not 0 < ang < 180:
                raise SteelCADError('L’angolo della svasatura va tra 0° e 180° (di solito 90°).', code='foro')
            foro = 2 * float(ent.get('r') or 0)
            if D <= foro:
                raise SteelCADError(f'La svasatura (Ø{fmt_mm(D)}) deve essere più larga del foro '
                                    f'(Ø{fmt_mm(round(foro, 2))}).', code='foro')
            ent['hole'] = {'tipo': 'svasato', 'D': D, 'angolo': ang}
        else:
            raise SteelCADError(f'Tipo di foro "{tipo}" sconosciuto.', code='foro')

    def _foro_della_faccia(self, f, nome: str) -> dict | None:
        """Hai cliccato la parete di un foro sul pezzo: quale cerchio di quale sketch l'ha fatto (centro sull'asse del
        cilindro, stesso raggio), così lo si fa svasato o filettato come in ogni CAD. None se non è un foro tondo."""
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder
        su = BRepAdaptor_Surface(f)
        if su.GetType() != GeomAbs_Cylinder:
            return None
        cil = su.Cylinder()
        R = cil.Radius()
        o, d = cil.Axis().Location(), cil.Axis().Direction()
        prima = nome.split('/')[0] if nome else None
        tagli = [x for x in self.doc.features if not isinstance(x, Sketch) and x.get('sketch')
                 and (x.get('type') in ('sheet_cut', 'sheet') or (x.get('type') == 'extrude' and x.get('operation') == 'cut'))]
        tagli.sort(key=lambda x: x.get('id') != prima)              # prima il taglio che ha fatto questa faccia
        for t in tagli:
            sid = t['sketch']
            fatto = (self.doc._sketch_results or {}).get(sid)
            if not fatto or fatto[1] is None:
                continue
            ss, pl = fatto[0], fatto[1].plane
            sk = self.doc.sketch(sid)
            for cid, (c, r) in ss.circles.items():
                if sk.entities[cid].get('construction') or abs(r - R) > 1e-3:
                    continue
                q = pl.from_local_coords(ss.points[c])
                v = (q.X - o.X(), q.Y - o.Y(), q.Z - o.Z())
                along = v[0] * d.X() + v[1] * d.Y() + v[2] * d.Z()
                fuori = (v[0] ** 2 + v[1] ** 2 + v[2] ** 2 - along ** 2) ** 0.5 if v[0] ** 2 + v[1] ** 2 + v[2] ** 2 > along ** 2 else 0.0
                if fuori < 1e-3:
                    uguali = [k for k, (_, r2) in ss.circles.items() if abs(r2 - r) < 1e-6 and not sk.entities[k].get('construction')]
                    # per l'anteprima della svasatura: dove sono i centri sulla faccia e da che parte è il materiale
                    centri = {k: (lambda q: [q.X, q.Y, q.Z])(pl.from_local_coords(ss.points[ss.circles[k][0]])) for k in uguali}
                    dentro = pl.z_dir if t.get('type') == 'sheet' else -pl.z_dir   # la base cresce dallo sketch verso z
                    data = getattr(self.result.body, 'sheet', None)
                    return {'sketch': sid, 'cerchio': cid, 'd': 2 * r, 'hole': sk.entities[cid].get('hole'), 'uguali': uguali,
                            'centri': centri, 'dentro': [dentro.X, dentro.Y, dentro.Z],
                            'spessore': data.thickness if data is not None else None}
        return None

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
        if side not in ('out', 'in', 'left', 'right'):
            return {'ok': False, 'message': 'Scegli da che parte fare l’offset.'}
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
        return self._sketch_change('Specchia' + (f' su {axis}' if isinstance(axis, str) else ''), lambda: sketch_edit.mirror(self.doc, sid, eids, axis))

    def sketch_copy(self, sid: str, eids: list, dx, dy) -> dict:
        try:
            dx, dy = _numero(dx, 'lo spostamento'), _numero(dy, 'lo spostamento')
        except SteelCADError as ex:
            return _err(ex)
        return self._sketch_change('Copia', lambda: sketch_edit.copy(self.doc, sid, eids, dx, dy))

    def sketch_move(self, sid: str, eids: list, dx, dy) -> dict:
        try:
            dx, dy = _numero(dx, 'lo spostamento'), _numero(dy, 'lo spostamento')
        except SteelCADError as ex:
            return _err(ex)
        return self._sketch_change('Sposta', lambda: sketch_edit.move(self.doc, sid, eids, dx, dy))

    def feature_serie(self, fid: str, cols, px, rows, py) -> dict:
        """Ripete in serie una lavorazione che viene da un disegno (un taglio, una tasca): tutto il suo disegno copiato
        a griglia, colonne lungo X e righe lungo Y del disegno, originale compreso (22/10). I passi diventano misure."""
        try:
            f = self.doc.feature(fid)
            sid = f.get('sketch') if not isinstance(f, Sketch) else None
            if not sid:
                raise SteelCADError('Si ripetono in serie le lavorazioni fatte da un disegno (tagli, tasche).', code='serie')
            sk = self.doc.sketch(sid)
            ids = [k for k, e in sk.entities.items() if e['kind'] in ('line', 'circle', 'arc', 'text')
                   and not e.get('ref') and not e.get('construction')]
            if not ids:
                raise SteelCADError('Il disegno di questa lavorazione è vuoto.', code='serie')
        except SteelCADError as ex:
            return _err(ex)
        r = self._change(f'Serie {cols} × {rows} di {fid}', lambda: sketch_edit.pattern(
            self.doc, sid, ids, int(_number(cols)), _number(px), int(_number(rows)), _number(py)))
        if r.get('ok'):
            r['message'] = f'{fid} ripetuto {int(_number(cols))} × {int(_number(rows))}: i passi sono le misure px, py (a sinistra).'
        return r

    def sketch_pattern(self, sid: str, eids: list, cols, px, rows, py) -> dict:
        return self._sketch_change(f'Serie {cols} × {rows}', lambda: sketch_edit.pattern(
            self.doc, sid, eids, int(_number(cols)), _number(px), int(_number(rows)), _number(py)))

    def sketch_dimension(self, sid: str, kind: str, refs: list) -> dict:
        try:
            sk = self.doc.sketch(sid)
            if not refs:
                raise SteelCADError('Scegli cosa quotare: una linea, un cerchio o due elementi.', code='quota')
            mancano = [r for r in refs if r not in sk.entities and r != 'O']
            if mancano:
                raise SteelCADError(f'Nello sketch non c’è {", ".join(mancano)}.', code='quota')
        except SteelCADError as ex:
            return _err(ex)
        info = {}
        r = self._sketch_change('Quota', lambda: info.update(did=sketch_edit.add_dimension(self.doc, sid, kind, refs,
                                                                                          info=info)))
        if r.get('ok'):
            r['dim'] = info.get('did')
            if info.get('tolta'):
                r['message'] = f'Tolta {info["tolta"]}: ora comanda la tua. Scrivi la misura e Invio.'
            if info.get('guidata'):
                r['guidata'] = True
                r['message'] = ('Questa misura la decide già il pezzo: la quota resta di riferimento, tra parentesi. '
                                'Per cambiarla cambia la misura del pezzo (fuori dallo sketch, clic sulla sua quota).')
        return r

    def sketch_delete(self, sid: str, eids: list) -> dict:
        return self._sketch_change(f'Elimina {", ".join(eids)}', lambda: sketch_ops.delete(self.doc, sid, eids))

    def sketch_on_face(self, face_name: str) -> dict:
        """La faccia cliccata diventa il piano di lavoro: uno sketch nuovo su di lei."""
        if self.result.body is None or face_name not in self.result.body.names:
            return {'ok': False, 'code': 'faccia', 'message': 'Questa faccia non ha un nome stabile: non ci si può '
                    'disegnare sopra (succede con facce nate da tagli). Scegline un’altra.'}
        nuovo = {}

        def fn():
            nuovo['id'] = self._crea_sketch_faccia(face_name).id
        r = self._change('Sketch su faccia', fn)
        if r['ok']:
            r['sketch'] = nuovo['id']
        return r

    def _crea_sketch_faccia(self, face_name: str, nome: str | None = None):
        sk = self.doc.add_sketch({'face': face_name}, nome or 'Sketch: ' + self.doc.describe_face(face_name).replace('"', ''))
        import build123d as bd
        from cad_engine.sketch.face_plane import plane_of
        faccia = bd.Face(self.result.body.face(face_name)[0])
        piano = plane_of(self.result.body, face_name, sk)
        sketch_ops.add_reference_edges(sk, faccia, piano, self.result.body.shape)
        # le sagome delle parti che arrivano a pochi mm dalla faccia (es. la testata di un profilo)
        data = getattr(self.result.body, 'sheet', None)
        from app import sketch_border
        sketch_border.add_nearby_edges(sk, self.result.body, faccia, piano, 3 * data.thickness if data else 5.0)
        return sk

    # ------------------------------------------------------------ fori e asole guidati (senza sketch)
    def fori_faccia(self) -> str | None:
        """La faccia dove si fanno i fori di solito: quella di sopra della lamiera, o quella di sopra della piastra."""
        body = self.result.body
        if body is None:
            return None
        data = getattr(body, 'sheet', None)
        if data is not None and f'{data.feature}/sopra' in body.names:
            return f'{data.feature}/sopra'
        return next((n for n in body.names if n.endswith('/fine')), None)

    def fori_info(self, face_name: str | None = None) -> dict:
        """Il contorno della faccia visto da sopra (coordinate della faccia: x dal bordo sinistro, y dal bordo
        davanti), per l'anteprima dei fori; più spessore e raggio, per l'avviso "troppo vicino alla piega"."""
        try:
            import build123d as bd
            from cad_engine.sketch.face_plane import plane_of
            face_name = face_name or self.fori_faccia()
            if not face_name or self.result.body is None or face_name not in self.result.body.names:
                return {'ok': False, 'message': 'Prima serve una lamiera o una piastra.'}
            sk = Sketch('_anteprima', plane={'face': face_name})
            faccia = bd.Face(self.result.body.face(face_name)[0])
            piano = plane_of(self.result.body, face_name, sk)
            sketch_ops.add_reference_edges(sk, faccia, piano, self.result.body.shape)
            ox, oy, w, h = self._fuori_tutto(piano)
            P = {k: (e['x'] - ox, e['y'] - oy) for k, e in sk.entities.items() if e['kind'] == 'point'}
            linee = [[*P[e['a']], *P[e['b']]] for e in sk.entities.values() if e['kind'] == 'line' and e.get('ref')]
            cerchi = [[*P[e['center']], e['r']] for e in sk.entities.values() if e['kind'] == 'circle' and e.get('ref')]
            archi = [[*P[e['center']], math.dist(P[e['center']], P[e['start']])] for e in sk.entities.values()
                     if e['kind'] == 'arc' and e.get('ref')]
            data = getattr(self.result.body, 'sheet', None)
            return {'ok': True, 'face': face_name, 'label': self.doc.describe_face(face_name), 'lines': linee,
                    'circles': cerchi + archi, 'outer': [w, h], 'thickness': data.thickness if data else None,
                    'radius': (data.tech.get('radius') if data else None)}
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def _fuori_tutto(self, piano) -> tuple:
        """Dove comincia il pezzo, fuori tutto, nelle coordinate della faccia: le distanze dei fori si misurano dal bordo
        esterno (com'è in officina), non dall'inizio della parte piana dopo la piega."""
        import build123d as bd
        pts = [piano.to_local_coords(v.center()) for v in bd.Shape.cast(self.result.body.shape).vertices()]
        xs, ys = [q.X for q in pts], [q.Y for q in pts]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)

    def fori_guidati(self, face_name: str, spec: dict) -> dict:
        """Fori tondi, asole o finestre come si segnano sul pezzo: misura, centro dal bordo sinistro e dal bordo
        davanti, e se serve una fila (quanti, ogni quanto, verso destra o verso dietro). Dietro c'è lo stesso
        sketch di sempre (con le quote, si modifica dopo), ma in un'operazione sola: un Annulla li toglie tutti."""
        try:
            n = lambda k, d=None: _number(spec.get(k, d))  # noqa: E731
            tipo = spec.get('tipo', 'tondo')
            x, y = float(n('x')), float(n('y'))
            quanti = max(1, int(n('n', 1) or 1)) if spec.get('fila') else 1
            passo = float(n('passo', 0) or 0)
            if quanti > 1 and passo <= 0:
                raise SteelCADError('Scrivi ogni quanto va un foro della fila.', code='fori')
            if face_name not in (self.result.body.names if self.result.body is not None else {}):
                raise SteelCADError('Questa faccia non c’è più: riapri «Fai fori o asole».', code='fori')
        except SteelCADError as ex:
            return _err(ex)
        except (TypeError, ValueError):
            return {'ok': False, 'code': 'fori', 'message': 'Scrivi le misure con i numeri.'}
        nomi = {'tondo': 'Fori', 'asola': 'Asole', 'finestra': 'Finestre'}

        def fn():
            nonlocal x, y
            sk = self._crea_sketch_faccia(face_name, nomi.get(tipo, 'Fori'))
            from cad_engine.sketch.face_plane import plane_of
            ox, oy, _, _ = self._fuori_tutto(plane_of(self.result.body, face_name, sk))
            x, y = x + ox, y + oy                          # dal bordo esterno del pezzo alle coordinate della faccia
            prima = set(sk.entities)
            if tipo == 'tondo':
                foro = spec.get('foro') or 'semplice'
                if foro == 'filettato':
                    m = str(spec.get('M', '')).upper().replace(' ', '')
                    if m not in FILETTI:
                        raise SteelCADError(f'Filettatura "{m}" non in tabella: {", ".join(FILETTI)}.', code='fori')
                    d = FILETTI[m][0]                     # il cerchio è il preforo
                else:
                    d = float(n('d'))
                sketch_ops.add_circle(self.doc, sk.id, [x, y], d / 2)
            elif tipo == 'asola':
                lun, lar = float(n('lungh')), float(n('larg'))
                if lar <= 0 or lun <= lar:
                    raise SteelCADError('L’asola deve essere più lunga che larga.', code='fori')
                h = (lun - lar) / 2
                c1, c2 = ([x, y - h], [x, y + h]) if spec.get('verticale') else ([x - h, y], [x + h, y])
                sketch_ops.add_slot(self.doc, sk.id, c1, c2, lar / 2)
            elif tipo == 'finestra':
                lun, lar = float(n('lungh')), float(n('larg'))
                sketch_ops.add_rectangle(self.doc, sk.id, [x - lun / 2, y - lar / 2], [x + lun / 2, y + lar / 2])
            else:
                raise SteelCADError(f'Forma "{tipo}" sconosciuta.', code='fori')
            if quanti > 1:
                nuove = [k for k, e in sk.entities.items() if k not in prima and e['kind'] != 'point' and not e.get('ref')]
                if spec.get('verso') == 'y':
                    sketch_edit.pattern(self.doc, sk.id, nuove, 1, 0, quanti, passo)
                else:
                    sketch_edit.pattern(self.doc, sk.id, nuove, quanti, passo, 1, 0)
            if tipo == 'tondo' and (spec.get('foro') or 'semplice') != 'semplice':
                foro = spec['foro']
                tf = {'tipo': 'filettato', 'M': spec.get('M')} if foro == 'filettato' else \
                    {'tipo': 'svasato', 'D': spec.get('sD'), 'angolo': spec.get('sang') or 90}
                for e in [k for k, x in sk.entities.items() if k not in prima and x['kind'] == 'circle' and not x.get('ref')]:
                    self._applica_foro(sk, e, tf)
            if self._sheet_def(face_name.split('/')[0]) is not None:
                self.doc.add_feature('sheet_cut', nomi.get(tipo, 'Fori'), sketch=sk.id)
            else:
                self.doc.add_feature('extrude', nomi.get(tipo, 'Fori'), sketch=sk.id, operation='cut', through_all=True, reverse=True)
        cosa = {'tondo': 'foro', 'asola': 'asola', 'finestra': 'finestra'}.get(tipo, 'foro')
        r = self._change(f'{quanti} {cosa}' if quanti > 1 else cosa.capitalize(), fn)
        if r.get('ok'):
            plur = {'foro': 'fori', 'asola': 'asole', 'finestra': 'finestre'}[cosa]
            r['message'] = f'Fatt{"i" if cosa == "foro" else "e"} {quanti} {plur}.' if quanti > 1 else f'Fatt{"o" if cosa == "foro" else "a"} {"il foro" if cosa == "foro" else "l’" + cosa if cosa == "asola" else "la finestra"}.'
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
                                                                                           'Sketch sullo sviluppo',
                                                                                           'Sketch sul tubo'):
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
            sketch_ops.add_bend_references(sk, data)
        r = self._change('Sketch sullo sviluppo', fn)
        if r['ok']:
            r['sketch'] = nuovo['id']
        return r

    def _togli_doppi(self, sid: str) -> str:
        """Se lo sketch ha solo vincoli doppi (nessun conflitto), li toglie: torna la loro descrizione ('' se niente)."""
        try:
            st = self.doc.solved_sketch(sid).status
        except SteelCADError:
            return ''
        if st.state != 'ridondante' or st.conflicting:
            return ''
        sk = self.doc.sketch(sid)
        nomi = {c: sk.describe_constraint(c) for c in sk.constraints}
        tolti = []

        def fn():
            tolti.extend(sketch_ops._prune(self.doc, sid, set()))
        r = self._change('Tolti vincoli doppi', fn, keep_broken=True)
        if not r.get('ok') or not tolti:
            return ''
        return ' e '.join(nomi.get(c, c) for c in tolti)

    def create_from_sketch(self, sid: str, kind: str, values: dict) -> dict:
        """Dal contorno disegnato: lamiera (spessore + dati di piega) o piastra (estrusione)."""
        v = {k: _number(x) for k, x in (values or {}).items() if str(x).strip() != ''}
        sk = self.doc.sketch(sid)
        # vincoli doppi (che dicono la stessa cosa di altri, senza contraddirli) non cambiano il disegno: si tolgono
        # da soli, lo si dice, e si va avanti. Prima il pezzo veniva rifiutato con "lo sketch non è costruibile"
        tolti = self._togli_doppi(sid)
        if tolti:
            r = self.create_from_sketch(sid, kind, values)
            if r.get('ok'):
                r['message'] = f'Ho tolto {tolti}: {"era doppio" if " e " not in tolti else "erano doppi"}. ' \
                    + (r.get('message') or '')
            return r
        try:
            st = self.doc.solved_sketch(sid).status
            if not st.ok_for_features and st.state != 'parziale':
                return {'ok': False, 'code': 'sketch', 'message': 'Lo sketch non va: ' + st.message}
        except SteelCADError:
            pass                                         # lo dicono i controlli sotto, con le loro parole
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
        if kind == 'mark':
            return self._marcatura(sid, sk)
        if kind == 'revolve':
            return self._rivoluzione(sid, sk, v)
        if isinstance(sk.plane, dict) and kind in ('cut', 'boss'):
            return self._from_face_sketch(sid, sk, kind, v)
        if kind == 'profilo':
            return self._profilo_da_sketch(sid, values or {})
        if kind == 'structure':
            return self._structure_from_sketch(sid, sk, v)
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
                dv = self._con_default(v)
                self.doc.add_feature('sheet', self.doc.meta.get('name') or 'Lamiera', sketch=sid, thickness='sp',
                                     radius=dv.get('radius'), method=dv.get('method') or 'k', k=dv.get('k'),
                                     bd90=dv.get('bd90'), flanges=[])
            else:
                self.doc.add_feature('extrude', self.doc.meta.get('name') or 'Piastra', sketch=sid,
                                     distance='sp', operation='new')
        return self._change('Crea lamiera' if kind == 'sheet' else 'Crea piastra', fn)

    def _profilo_da_sketch(self, sid: str, valori: dict) -> dict:
        """Profilo estruso in lamiera: il profilo disegnato (linee e archi, aperto) estruso di «lunghezza»; gli spigoli
        sono pieghe, gli archi colpi (bumping). Spessore dalla parte convessa (la linea è la faccia interna), «gira»
        lo mette dall'altra. Raggio e K: quelli scritti o quelli della piegatrice."""
        try:
            n = lambda k, cosa: _numero(valori[k], cosa) if str(valori.get(k, '')).strip() else None  # noqa: E731
            L = n('lunghezza', 'la lunghezza')
            if not L or L <= 0:
                raise SteelCADError('Scrivi di quanto estrudere il profilo (la lunghezza del pezzo).', code='profilo')
            sp = n('spessore', 'lo spessore') or 2
            colpi, passo = n('colpi', 'i colpi per arco'), n('passo', 'il passo dei colpi')
            d = self.bend_default()
            raggio = n('raggio', 'il raggio') if n('raggio', 'il raggio') is not None else d.get('radius')
            k = n('k', 'il K') if n('k', 'il K') is not None else d.get('k')
        except SteelCADError as ex:
            return _err(ex)
        if any(not isinstance(f, Sketch) and f.get('sketch') == sid for f in self.doc.features):
            return {'ok': False, 'code': 'usato', 'message': 'Questo sketch ha già un pezzo: modificalo da lì.'}

        def fn():
            nomi = {'lunghezza': L, 'sp': sp}
            for kk, vv in nomi.items():
                if kk not in self.doc.parameters:
                    self.doc.set_parameter(kk, vv)
            self.doc.add_feature('sheet_shape', 'Profilo in lamiera', kind='profilo', sketch=sid,
                                 length='lunghezza' if self.doc.parameters.get('lunghezza') == L else L,
                                 thickness='sp' if self.doc.parameters.get('sp') == sp else sp,
                                 radius=raggio, k=k, hits=colpi, pitch=passo, flip=bool(valori.get('gira')))
        r = self._change('Profilo estruso in lamiera', fn)
        if r.get('ok') and self.result.body is not None:
            info = getattr(self.result.body.sheet, 'shape_info', {}) or {}
            r['message'] = (f'Profilo in lamiera: {info.get("pieghe", "?")} pieghe'
                            + (f' (archi a {", ".join(str(c) for c in info.get("colpi") or [])} colpi)' if info.get('colpi') else '')
                            + f', sviluppo {fmt_mm(round(info.get("sviluppo", 0), 1))} × {fmt_mm(round(L, 1))}.')
        return r

    def sheet_tab(self, sid: str) -> dict:
        """Aggiungi materiale (linguetta): il contorno disegnato su una faccia piana della lamiera diventa lamiera
        dello stesso spessore nel piano della faccia. Se la spezzata parte e finisce sullo stesso bordo della faccia
        (le linee arancio), la si chiude lungo quel bordo."""
        import math as _m
        try:
            sk = self.doc.sketch(sid)
            lamiere = [f['id'] for f in self.doc.features if not isinstance(f, Sketch) and f.get('type') == 'sheet']
            if not isinstance(sk.plane, dict) or not (sk.plane.get('flat') in lamiere or (sk.plane.get('face') or '').startswith(
                    tuple(x + '/' for x in lamiere))):
                raise SteelCADError('La linguetta si disegna su una faccia di una lamiera.', code='linguetta')
            ss = self.doc.solved_sketch(sid)
            P = ss.points
            linee = [k for k, e in sk.entities.items() if e['kind'] == 'line' and not e.get('construction')]
            # due linee uguali sugli stessi punti (rimaste da prove): ne basta una
            visti, uniche = set(), []
            for k in linee:
                chiave = frozenset((sk.entities[k]['a'], sk.entities[k]['b']))
                if chiave not in visti:
                    visti.add(chiave)
                    uniche.append(k)
            linee = uniche
            chiudi = []
            if linee and not any(e['kind'] in ('circle', 'arc') and not e.get('construction') for e in sk.entities.values()):
                from app.sketch_edit import _chain
                # più alette nello stesso disegno: ogni gruppo di linee attaccate si chiude per conto suo
                gruppi, di = [], {}
                for k in linee:
                    e = sk.entities[k]
                    g = {k} | {x for p in (e['a'], e['b']) for x in di.get(p, set())}
                    for x in list(g):
                        for gg in [y for y in gruppi if x in y]:
                            g |= gg
                            gruppi.remove(gg)
                    gruppi.append(g)
                    for x in g:
                        for p in (sk.entities[x]['a'], sk.entities[x]['b']):
                            di.setdefault(p, set()).add(x)
                for g in gruppi:
                    try:
                        ordine, _, chiusa = _chain(sk, sorted(g))
                    except SteelCADError:
                        ordine, chiusa = None, True
                    if not ordine or chiusa:
                        continue
                    a, b, fatto = ordine[0], ordine[-1], False
                    for k, e in sk.entities.items():
                        if e['kind'] != 'line' or not e.get('ref') or e.get('linea_piega'):
                            continue
                        A, B = P[e['a']], P[e['b']]
                        L = _m.dist(A, B) or 1
                        sul = lambda q: abs((B[0] - A[0]) * (q[1] - A[1]) - (B[1] - A[1]) * (q[0] - A[0])) / L < 1e-4  # noqa: E731
                        if sul(P[a]) and sul(P[b]):
                            chiudi.append((a, b))
                            fatto = True
                            break
                    if not fatto:
                        raise SteelCADError('Un contorno è aperto: chiudilo, oppure fallo partire e finire sullo stesso bordo '
                                            'della faccia (la linea arancio), e lo chiudo io lungo quel bordo.', code='linguetta')
        except SteelCADError as ex:
            return _err(ex)

        def fn():
            for k in [k for k, e in sk.entities.items() if e['kind'] == 'line' and not e.get('construction') and k not in linee]:
                del sk.entities[k]                      # i doppioni (e i loro vincoli)
                for c in [c for c, v in sk.constraints.items() if k in v['refs']]:
                    del sk.constraints[c]
            for a, b in chiudi:
                lid = sk.line(a, b)
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

    # i campi dei modelli a misure, come nella finestra "Nuovo progetto"
    MODELLI_ST = {
        'telaio': ('Telaio / tavolo', [('L', 'Lunghezza'), ('P', 'Profondità'), ('H', 'Altezza'),
                                       ('profilo', 'Profilo telaio'), ('gambe', 'Profilo gambe')]),
        'scaffale': ('Scaffale', [('L', 'Lunghezza'), ('P', 'Profondità'), ('H', 'Altezza'),
                                  ('ripiani', 'Ripiani (a terra e in cima compresi)'), ('montanti', 'Profilo montanti'),
                                  ('traversi', 'Profilo traversi')]),
        'armadio': ('Telaio armadio', [('L', 'Larghezza'), ('P', 'Profondità'), ('H', 'Altezza'),
                                       ('ripiani', 'Livelli (sotto e sopra compresi)'), ('profilo', 'Profilo')]),
        'cancello': ('Cancello', [('L', 'Larghezza'), ('H', 'Altezza'), ('telaio', 'Profilo telaio'),
                                  ('sbarre', 'Profilo sbarre'), ('passo', 'Passo sbarre (circa)')]),
        'cono': ('Cono / tronco di cono', [('D1', 'Ø grande'), ('D2', 'Ø piccolo (0 = a punta)'), ('H', 'Altezza'),
                                           ('spessore', 'Spessore'), ('riferimento', 'Misure', {'esterno': 'esterne (finite)', 'interno': 'interne', 'asse': 'in asse lamiera'}),
                                           ('modo', 'Lavorazione', {'press': 'a pieghe (piegatrice)', 'rolled': 'calandrato'}),
                                           ('passo', 'Passo pieghe sul bordo (vuoto = dal raggio)')]),
        'tramoggia': ('Raccordo quadro-tondo', [('A', 'Lato A (X)'), ('B', 'Lato B (Y)'), ('D', 'Ø tondo'), ('H', 'Altezza'),
                                                ('ex', 'Spostamento tondo X'), ('ey', 'Spostamento tondo Y'),
                                                ('spessore', 'Spessore'), ('rif_base', 'Misure base', {'esterno': 'esterne (finite)', 'interno': 'interne', 'asse': 'in asse lamiera'}),
                                                ('rif_tondo', 'Misure tondo', {'esterno': 'esterne (finite)', 'interno': 'interne', 'asse': 'in asse lamiera'}),
                                                ('passo', 'Passo pieghe sul tondo (vuoto = dal raggio)')]),
        'tramoggia_cassone': ('Tramoggia con cassone', [
            ('A', 'Bocca: lato A (X)'), ('B', 'Bocca: lato B (Y)'), ('Hc', 'Altezza cassone (0 = solo tramoggia)'),
            ('a', 'Scarico: lato a'), ('b', 'Scarico: lato b'), ('Ht', 'Altezza tramoggia'),
            ('ex', 'Scarico spostato in X'), ('ey', 'Scarico spostato in Y'), ('bordo', 'Bordo in alto (0 = niente)'),
            ('angoli_bordo', 'Angoli dei bordi', {'aperti': 'aperti (scasso, più pieghe)', '45': 'a 45° (da saldare)'}),
            ('flangia', 'Flangia allo scarico (0 = niente)'), ('smusso', 'Angoli smussati (0 = vivi)'),
            ('spessore', 'Spessore'), ('riferimento', 'Misure', {'esterno': 'esterne (finite)', 'interno': 'interne', 'asse': 'in asse lamiera'}),
            ('divisione', 'Divisione in pezzi', {'auto': 'automatica (meno saldature)',
                                                 'verticali': 'pieghe sugli spigoli verticali',
                                                 'tramoggia': 'pieghe sugli spigoli della tramoggia',
                                                 'lati': 'un pezzo per lato'}),
            ('foglio', 'Foglio (es. 1500x3000)')]),
    }
    _PARAM_MODELLO = {'L', 'P', 'H', 'D1', 'D2', 'A', 'B', 'D', 'ex', 'ey', 'Hc', 'Ht', 'a', 'b', 'bordo', 'flangia',
                      'smusso'}   # vivono anche come parametri

    def _structure_selection(self, st_id: str) -> dict:
        fdef = self.doc.feature(st_id)
        st = next((s for s in self.result.structures if s.id == st_id), None)
        aste = st.members if st else []
        metri = sum(m.length for m in aste) / 1000
        kg = sum(m.kg() for m in aste)
        out = {'kind': 'structure', 'id': st_id, 'title': fdef.get('name') or st_id,
               'rows': [['Aste', str(len(aste))], ['Metri di tubolare', f'{metri:.2f}'.replace('.', ',')],
                        ['Peso', f'{kg:.2f} kg'.replace('.', ',')]],
               'members': [f'{st_id}/{m.id}' for m in aste]}
        t = fdef.get('template')
        if t and t.get('kind') in self.MODELLI_ST:
            titolo, campi = self.MODELLI_ST[t['kind']]
            par = self.doc.parameters
            valori = {c[0]: (par[c[0]] if c[0] in self._PARAM_MODELLO and c[0] in par else t['values'].get(c[0]))
                      for c in campi}
            out['template'] = self._tpl_info(t, titolo, campi, valori)
        return out

    def _tpl_info(self, t, titolo, campi, valori):
        return {'kind': t['kind'], 'title': titolo,
                'fields': [[c[0], c[1], valori.get(c[0]), c[2] if len(c) > 2 else None] for c in campi]}

    def _shape_template(self):
        """La forma di lamiera (cono, raccordo) del progetto e i dati del suo modello, per la scheda."""
        f = next((x for x in self.doc.features if not isinstance(x, Sketch) and x.get('type') == 'sheet_shape'), None)
        if f is None or not f.get('template') or f['template'].get('kind') not in self.MODELLI_ST:
            return None
        t = f['template']
        titolo, campi = self.MODELLI_ST[t['kind']]
        par = self.doc.parameters
        alias = {'spessore': 'sp'}
        valori = {}
        for c in campi:
            k = c[0]
            nome_par = alias.get(k, k)
            valori[k] = par[nome_par] if (k in self._PARAM_MODELLO or k in alias) and nome_par in par else t['values'].get(k)
        return f['id'], self._tpl_info(t, titolo, campi, valori)

    def set_shape_edge(self, fid: str, key: str, scelta: str) -> dict:
        """Uno spigolo della forma: 'piega', 'saldatura' o 'auto' (decide la proposta)."""
        if scelta not in ('piega', 'saldatura', 'auto'):
            return {'ok': False, 'message': 'Uno spigolo è una piega o una saldatura.'}
        info = getattr(getattr(self.result.body, 'sheet', None), 'shape_info', None) or {}
        spigolo = next((x for x in info.get('spigoli') or [] if x['key'] == key), None)
        if spigolo is None:
            return {'ok': False, 'message': 'Quello spigolo non c’è più: riprova.'}
        if spigolo['scelta'] == 'taglio':
            return {'ok': False, 'message': 'Qui le due facce sono nello stesso piano: è un taglio, non si piega.'}

        def fn():
            f = self.doc.feature(fid)
            scelte = f.setdefault('spigoli', {})
            if scelta == 'auto':
                scelte.pop(key, None)
            else:
                scelte[key] = scelta
        r = self._change(f'{spigolo["nome"]}: {"proposta" if scelta == "auto" else scelta}', fn)
        if r.get('ok'):
            dopo = getattr(getattr(self.result.body, 'sheet', None), 'shape_info', None) or {}
            nuovo = next((x for x in dopo.get('spigoli') or [] if x['key'] == key), None)
            if scelta == 'piega' and nuovo and nuovo['scelta'] != 'piega':
                r['message'] = ('Qui una piega non si può fare: chiuderebbe un giro di pieghe o il pezzo non starebbe '
                                'nel foglio. Resta saldato.')
        return r

    def structure_template_apply(self, st_id: str, values: dict) -> dict:
        """Rifà la struttura di un modello a misure con i dati nuovi (anche ripiani, profili, passo).
        Le modifiche fatte a mano sulle singole aste restano, per le aste che ci sono ancora."""
        try:
            old = self.doc.feature(st_id)
            t = old.get('template')
            if not t or t.get('kind') not in self.MODELLI_ST:
                raise SteelCADError('Questa struttura non nasce da un modello a misure: si modifica dallo sketch '
                                    'o cliccando le aste.', code='modello')
            for k in ('profilo', 'gambe', 'montanti', 'traversi', 'telaio', 'sbarre'):
                if k in values:
                    parse(str(values[k]))
            vals = {**t['values'], **{k: _number(v) for k, v in values.items() if str(v).strip() != '' or k == 'passo'}}
            if old.get('type') == 'sheet_shape':           # i dati di piega restano quelli della forma
                vals.update({'raggio': old.get('radius'), 'k': old.get('k')})
            try:
                nuovo = getattr(templates, t['kind'])(old.get('name') or self.MODELLI_ST[t['kind']][0], **vals)
            except (ValueError, TypeError, ZeroDivisionError):
                raise SteelCADError('Una delle misure non va: scrivi numeri maggiori di zero.', code='misura') from None
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

        def fn():
            vecchi_sketch = self.doc._sketch_refs(old)
            new_st = next(f for f in nuovo.features if not isinstance(f, Sketch) and f.get('type') == old.get('type'))
            new_sk = [f for f in nuovo.features if isinstance(f, Sketch)]
            # le aste ritoccate a mano restano (se esistono ancora), e anche i giunti scelti a mano
            if old.get('overrides'):
                new_st.setdefault('overrides', {})
                for mid, r in old['overrides'].items():
                    new_st['overrides'].setdefault(mid, {}).update(r)
            if old.get('joints'):
                new_st['joints'] = old['joints']
            if old.get('spigoli'):                       # le scelte piega/saldatura restano
                new_st['spigoli'] = old['spigoli']
            new_st['id'] = st_id
            pos = self.doc.features.index(old)
            resto = [f for f in self.doc.features if f is not old
                     and not (isinstance(f, Sketch) and f.id in vecchi_sketch)]
            pos = sum(1 for f in self.doc.features[:pos] if f in resto)
            self.doc.features = resto[:pos] + new_sk + [new_st] + resto[pos:]
            for k, v in nuovo.parameters.items():
                self.doc.parameters[k] = v
        return self._change(f'{self.MODELLI_ST[t["kind"]][0]}: nuove misure', fn)

    def _structure_from_sketch(self, sid, sk, v) -> dict:
        """Le linee dello sketch diventano tubolari. Con "ripetizioni" lo scheletro si ripete a distanza
        (perpendicolare al piano dello sketch) e i nodi si collegano con i traversi: scaffali, armadi."""
        if not isinstance(sk.plane, str):
            return {'ok': False, 'code': 'piano', 'message': 'Le strutture si disegnano sui piani XY, XZ o YZ.'}
        try:
            parse(str(v.get('profile', '')))
            if v.get('connect') and v.get('connect_profile'):
                parse(str(v['connect_profile']))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        n = int(v.get('copies', 1) or 1)
        normale = {'XY': (2, 1), 'XZ': (1, -1), 'YZ': (0, 1)}[sk.plane]      # asse e segno della normale
        verso = -1 if v.get('side') == 'back' else 1

        def fn():
            copie = [[0, 0, 0]]
            if n > 1:
                nome = 'D'
                i = 1
                while nome in self.doc.parameters:
                    i += 1
                    nome = f'D{i}'
                self.doc.set_parameter(nome, v.get('distance', 500))
                for k in range(1, n):
                    off = [0, 0, 0]
                    off[normale[0]] = f'{k * normale[1] * verso}*{nome}'
                    copie.append(off)
            sk_def = {'id': 'K1', 'sketch': sid, 'profile': str(v['profile']), 'group': v.get('group') or 'Telaio',
                      'copies': copie}
            if n > 1 and v.get('connect'):
                sk_def['connect'] = {'profile': str(v.get('connect_profile') or v['profile']),
                                     'group': v.get('connect_group') or 'Collegamenti'}
            st = next((f for f in self.doc.features if not isinstance(f, Sketch) and f.get('type') == 'structure'), None)
            if st is None:
                self.doc.add_feature('structure', self.doc.meta.get('name') or 'Struttura', points={}, members=[],
                                     skeletons=[sk_def])
            else:                       # nella stessa struttura: i giunti tra vecchio e nuovo funzionano
                usati = {k['id'] for k in st.get('skeletons') or []}
                j = 1
                while f'K{j}' in usati:
                    j += 1
                sk_def['id'] = f'K{j}'
                st.setdefault('skeletons', []).append(sk_def)
        return self._change('Crea struttura dallo sketch', fn)

    def set_quote(self, quote: list) -> dict:
        """Le quote messe col tasto Quota sul pezzo: si salvano nel progetto e vanno nelle tavole."""
        if self.asm is not None:
            return _ok()
        pulite = []
        for q in quote or []:
            try:
                pulite.append({'a': [float(x) for x in q['a']][:3], 'b': [float(x) for x in q['b']][:3],
                               'testo': str(q.get('testo', ''))[:40], **({'dett': str(q['dett'])[:80]} if q.get('dett') else {})})
            except (KeyError, TypeError, ValueError):
                continue
        if pulite != (self.doc.meta.get('quote') or []):
            self.doc.meta['quote'] = pulite
            self.history.dirty = True
        return _ok()

    def crea_specchiato(self) -> dict:
        """La versione specchiata del pezzo (la staffa destra dalla sinistra, 22/10): il 3D specchiato riletto come un pezzo
        di lamiera da STEP, con il suo sviluppo; si salva accanto all'originale come «… specchiato» e si apre."""
        import tempfile

        import build123d as bd
        if self.asm is not None or self.result.body is None:
            return {'ok': False, 'message': 'Apri il pezzo da specchiare.'}
        data = getattr(self.result.body, 'sheet', None)
        if data is None:
            return {'ok': False, 'message': 'Lo specchio si fa sui pezzi di lamiera.'}
        if self.path is None:
            return {'ok': False, 'code': 'serve_percorso', 'message': 'Salva prima il pezzo: lo specchiato va accanto a lui.'}
        if self.history.dirty:
            r = self.save()
            if not r.get('ok'):
                return r
        originale = Path(self.path)
        dest = originale.with_name(f'{originale.stem} specchiato.steelcad')
        k = 2
        while dest.exists():
            dest, k = originale.with_name(f'{originale.stem} specchiato ({k}).steelcad'), k + 1
        nome_step = Path(tempfile.mkdtemp()) / f'{dest.stem}.step'
        bd.export_step(bd.Shape.cast(self.result.body.shape).mirror(bd.Plane.YZ), str(nome_step))
        kk = data.tech.get('k') if data.tech.get('k') is not None else None
        a0 = data.flat_area
        materiale = self.doc.material
        r = self.import_step(str(nome_step), kk)
        if not r.get('ok'):
            return r
        self.doc.material = materiale
        self.doc.meta['name'] = dest.stem
        r = self.save(str(dest))
        if not r.get('ok'):
            return r
        diff = abs(self.result.body.sheet.flat_area - a0)
        r['message'] = (f'Versione specchiata salvata e aperta: {dest.name}. Sviluppo ' +
                        ('uguale all’originale, rovesciato.' if diff < 1 else
                         f'con {fmt_mm(round(diff, 1))} mm² di differenza dall’originale: controlla gli angoli e gli scarichi.') +
                        ' Le pieghe sono quelle del 3D: per cambiarle, cambia l’originale e rifai lo specchio.')
        return r

    def import_step(self, path: str, k=None) -> dict:
        """Uno STEP di lamiera piegata del cliente: diventa un pezzo con lo sviluppo (K della piegatrice, o quello
        scritto). Lo STEP si salva dentro il progetto: il file può poi spostarsi."""
        import base64
        import zlib

        from cad_engine.document import Document
        p = Path(path)
        try:
            dati = p.read_bytes()
        except OSError as ex:
            return {'ok': False, 'message': f'Lo STEP non si legge: {ex}'}
        kk = k if k not in (None, '') else self.bend_default().get('k') or 0.33
        try:
            kk = _numero(kk, 'il K')
        except SteelCADError as ex:
            return _err(ex)
        doc = Document(p.stem, 'S235')
        doc.add_feature('step_lamiera', 'Lamiera da STEP', file=p.name, k=kk,
                        dati=base64.b64encode(zlib.compress(dati, 9)).decode('ascii'))
        prova = doc.rebuild()
        fr = next((f for f in prova.features if f.id == 'IM1'), None)
        if fr is None or not fr.ok:
            return {'ok': False, 'code': 'step', 'message': fr.message if fr else 'Lo STEP non si apre.'}
        self._set(doc)
        self.path = None
        self.blank = False
        self.asm = None
        self._asm_ritorno = None
        data = self.result.body.sheet
        return _ok(state=self.state(), message=f'{p.name}: lamiera sp. {fmt_mm(round(data.thickness, 2))}, {len(data.bend_rows)} pieghe, '
                           f'sviluppo {fmt_mm(round(data.flat_size[0], 1))} × {fmt_mm(round(data.flat_size[1], 1))} '
                           f'(K {fmt_mm(kk)}).' + (' ' + ' '.join(data.warnings) if data.warnings else ''))

    def _rivoluzione(self, sid, sk, v) -> dict:
        """Il contorno chiuso fatto girare attorno alla linea di costruzione: nuovo pezzo, o aggiunto/tolto."""
        if any(not isinstance(f, Sketch) and f.get('sketch') == sid for f in self.doc.features):
            return {'ok': False, 'code': 'usato', 'message': 'Questo sketch è già usato: modificalo da lì.'}
        op = 'new' if self.result.body is None else ('cut' if v.get('togli') else 'add')
        ang = v.get('angle', 360)

        def fn():
            self.doc.add_feature('revolve', 'Rivoluzione', sketch=sid, angle=ang, operation=op)
        r = self._change('Rivoluzione', fn)
        if r.get('ok'):
            r['message'] = f'Rivoluzione: {"giro intero" if ang >= 360 else f"{fmt_mm(ang)}°"}' + \
                {'new': '.', 'add': ', aggiunta al pezzo.', 'cut': ', tolta dal pezzo.'}[op]
        return r

    def add_edge_dress(self, tipo: str, punti: list, valore) -> dict:
        """Raccordo o smusso sugli spigoli del pezzo: punti cliccati sugli spigoli (x, y, z), uno per spigolo."""
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from OCP.gp import gp_Pnt

        from cad_engine.topology.naming import _edges_of
        if tipo not in ('fillet', 'chamfer'):
            return {'ok': False, 'message': f'Lavorazione «{tipo}» sconosciuta.'}
        body = self.result.body
        if body is None:
            return {'ok': False, 'message': 'Prima serve un pezzo.'}
        if getattr(body, 'sheet', None) is not None:
            return {'ok': False, 'code': 'lamiera', 'message': 'Sulla lamiera gli spigoli si arrotondano nel disegno '
                    '(Raccordo dello sketch sull’angolo del contorno): così vanno anche nello sviluppo.'}
        try:
            val = _numero(valore, 'il raggio' if tipo == 'fillet' else 'la misura')
            refs = []
            spigoli = list(_edges_of(body.shape))
            for p in punti or []:
                v = BRepBuilderAPI_MakeVertex(gp_Pnt(*[float(c) for c in p])).Vertex()
                migliore = None
                for e in spigoli:
                    dd = BRepExtrema_DistShapeShape(v, e)
                    if dd.IsDone() and (migliore is None or dd.Value() < migliore[0]):
                        migliore = (dd.Value(), e)
                if migliore is None or migliore[0] > 1.0:
                    raise SteelCADError('Clicca proprio sullo spigolo (si accende).', code='spigolo')
                ref = body.edge_ref(migliore[1])
                if ref not in refs:
                    refs.append(ref)
            if not refs:
                raise SteelCADError('Scegli almeno uno spigolo.', code='spigolo')
        except SteelCADError as ex:
            return _err(ex)
        nome = f'Raccordo R{fmt_mm(val)}' if tipo == 'fillet' else f'Smusso {fmt_mm(val)} mm'

        def fn():
            campi = {'radius': val} if tipo == 'fillet' else {'distance': val}
            self.doc.add_feature(tipo, 'Raccordo' if tipo == 'fillet' else 'Smusso', edges=refs, **campi)
        r = self._change(nome, fn)
        if r.get('ok'):
            r['message'] = f'{nome} su {len(refs)} {"spigolo" if len(refs) == 1 else "spigoli"}.'
        return r

    def _marcatura(self, sid, sk) -> dict:
        """I testi dello sketch marcati col laser: sul layer di marcatura dello sviluppo, nella posizione giusta."""
        if not any(e['kind'] == 'text' for e in sk.entities.values()):
            return {'ok': False, 'code': 'testo', 'message': 'Nello sketch non c’è nessun testo: usa «Testo» e clicca '
                                                              'dove va.'}
        if not isinstance(sk.plane, dict):
            return {'ok': False, 'code': 'testo', 'message': 'La marcatura si disegna su una faccia della lamiera o '
                                                              'sullo sviluppo.'}
        if any(not isinstance(f, Sketch) and f.get('sketch') == sid for f in self.doc.features):
            return {'ok': False, 'code': 'testo', 'message': 'Questo sketch è già usato da un’altra lavorazione: per '
                                                              'i testi fanne uno nuovo sulla stessa faccia.'}

        def fn():
            self.doc.add_feature('sheet_cut', 'Marcatura', sketch=sid, mode='mark')
        r = self._change('Marca col laser', fn)
        if r.get('ok'):
            n = sum(1 for e in sk.entities.values() if e['kind'] == 'text')
            r['message'] = f'Marcatura: {n} {"testo" if n == 1 else "testi"} sul layer MARK dello sviluppo.'
        return r

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
        if su is None and not sk.plane.get('flat'):          # una forma di lamiera (profilo a colpi…): taglio di lamiera
            try:
                f_ = self.doc.feature(sk.plane['face'].split('/')[0])
                su = f_ if not isinstance(f_, Sketch) and f_.get('type') in ('sheet_shape', 'step_lamiera') else None
            except SteelCADError:
                su = None

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
            elif kind == 'cut' and v.get('distance'):           # tasca di quella profondità (non passante)
                self.doc.add_feature('extrude', 'Tasca', sketch=sid, operation='cut', distance=v['distance'], reverse=True)
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
        if d and d.get('driven'):
            if isinstance(v, (int, float)) and abs(abs(v) - abs(d['value'] or 0)) < 1e-6:
                return {'ok': True, 'state': self.state()}
            return _err(SteelCADError('Questa è una quota di riferimento (tra parentesi): la misura la decide il pezzo. '
                                      'Per cambiarla esci dallo sketch e clicca la quota sul pezzo, oppure cancellala.',
                                      code='quota'))
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
            st = next(s for s in self.result.structures if s.id == st_id)
            gruppo = next((m.group for m in st.members if m.id == mid), None)
            ids = [m.id for m in st.members if m.id == mid or (whole_group and gruppo and m.group == gruppo)]
            a_mano = {x['id']: x for x in fdef.get('members') or []}
            for i in ids:
                # un'asta dello scheletro (nata da una linea di sketch) si cambia con un'eccezione:
                # resta anche quando lo sketch cambia
                x = a_mano.get(i) or fdef.setdefault('overrides', {}).setdefault(i, {})
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
                a_mano = {m['id'] for m in fdef.get('members') or []}
                for i in via - a_mano:                      # aste dello scheletro: si spengono
                    fdef.setdefault('overrides', {}).setdefault(i, {})['deleted'] = True
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
        tipo = (spec or {}).get('type', 'auto')
        try:
            if tipo not in JOINT_LABELS:
                raise SteelCADError(f'Giunto "{tipo}" sconosciuto.', code='giunto')
            try:
                membri = self.result_node(st_id, key)['members']
            except (KeyError, IndexError, StopIteration):
                raise SteelCADError(f'Il nodo {key} non c’è più.', code='nodo') from None
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
        try:
            vals = [_number(v) if str(v).strip() != '' else 0 for v in values]
            if len(vals) != 3:
                raise SteelCADError('Servono le tre coordinate X, Y, Z.', code='nodo')
            if key not in (self.doc.feature(st_id).get('points') or {}):
                raise SteelCADError(f'Il nodo {key} non si sposta da qui (non c’è, o nasce da uno sketch).', code='nodo')
        except SteelCADError as ex:
            return _err(ex)

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

    TIPI_PROGETTO = ('telaio', 'piastra', 'vuoto', 'lamiera', 'zero', 'scaffale', 'armadio', 'cancello', 'disegno',
                     'cono', 'tramoggia', 'tramoggia_cassone')

    def _doc_modello(self, kind: str, values: dict | None) -> Document:
        if kind in ('lamiera', 'cono', 'tramoggia', 'tramoggia_cassone'):
            d = self.bend_default()
            values = dict(values or {})
            scritti = any(str(values.get(c, '') or '').strip() for c in ('raggio', 'k', 'metodo', 'bd90'))
            for campo, k in (('raggio', 'radius'), ('k', 'k')):
                if str(values.get(campo, '') or '').strip() == '' and d.get(k) is not None:
                    values[campo] = d[k]
            # il metodo predefinito (DIN 6935, deduzione a 90°) vale solo se l'utente non ha scritto i suoi dati
            if kind == 'lamiera' and not scritti and d.get('method'):
                values['metodo'] = d['method']
                if d.get('bd90') is not None:
                    values['bd90'] = d['bd90']
        values = {k: _number(v) for k, v in (values or {}).items()}
        if kind not in self.TIPI_PROGETTO:
            raise SteelCADError(f'Tipo di progetto "{kind}" sconosciuto.', code='tipo')
        return {'telaio': templates.telaio, 'piastra': templates.piastra,
                'vuoto': templates.struttura_vuota, 'lamiera': templates.lamiera,
                'zero': templates.da_zero, 'scaffale': templates.scaffale, 'armadio': templates.armadio,
                'cancello': templates.cancello, 'disegno': templates.struttura_disegno,
                'cono': templates.cono, 'tramoggia': templates.tramoggia,
                'tramoggia_cassone': templates.tramoggia_cassone}[kind](**values)

    def new_project_preview(self, kind: str, values: dict | None = None) -> dict:
        """Mentre si scrivono le misure di un pezzo nuovo: cosa viene fuori, a parole (quante sbarre e che luce,
        quanto pesa, quanto è lo sviluppo). Il pezzo si costruisce a parte: il progetto aperto non cambia."""
        def kg(v):
            return f'{v:.1f}'.replace('.', ',')
        try:
            doc = self._doc_modello(kind, values)
            r = doc.rebuild()
            if r.errors:
                return {'ok': True, 'text': None, 'warning': r.errors[0].message}
            frasi = []
            if r.structures:
                cl = cut_list(r.structures)
                if kind == 'cancello':
                    sbarre = [m for st in r.structures for m in st.members if m.group == 'Sbarre']
                    xs = sorted({round((m.start.X + m.end.X) / 2, 3) for m in sbarre})
                    if len(xs) >= 2:
                        passo = xs[1] - xs[0]
                        luce = passo - sbarre[0].profile.width
                        frasi.append(f'Escono {len(xs)} sbarre ogni {fmt_mm(round(passo, 1))} mm: tra una e l’altra restano '
                                     f'{fmt_mm(round(luce, 1))} mm di luce.')
                if kind in ('scaffale', 'armadio'):
                    t = (doc.features[-1].get('template') or {}).get('values', {}) if doc.features else {}
                    n, h = int(_number(t.get('ripiani', 0)) or 0), _number(t.get('H', 0))
                    if n > 1 and h:
                        frasi.append(f'{n} piani, uno ogni {fmt_mm(round(h / (n - 1), 1))} mm.')
                import build123d as bd
                bb = bd.Compound([m.solid for st in r.structures for m in st.members]).bounding_box().size
                fuori = [round(v) for v in (bb.X, bb.Y, bb.Z) if v > 1e-6]
                if kind == 'cancello':
                    fuori = [round(bb.X), round(bb.Z)]
                frasi.append('Fuori tutto ' + ' × '.join(fmt_mm(v) for v in fuori) + ' mm.')
                frasi.append(f'Circa {kg(cl["kg"])} kg: {cl["pieces"]} pezzi di tubo da tagliare, {len(cl["rows"])} misure diverse.')
            if r.body is not None:
                massa = properties(r.body.shape, doc.material)['mass_kg']
                sd = getattr(r.body, 'sheet', None)
                if sd is not None:
                    info = getattr(sd, 'shape_info', None) or {}
                    if info.get('kind') == 'cone' and not info.get('pieghe'):
                        frasi.append(f'Calandrato: lo sviluppo è una corona di {fmt_mm(round(sd.flat_size[0], 1))} × '
                                     f'{fmt_mm(round(sd.flat_size[1], 1))} mm.')
                    else:
                        n_pieghe = info.get('pieghe') if info else len(sd.flanges)
                        frasi.append(f'Sviluppo {fmt_mm(round(sd.flat_size[0], 1))} × {fmt_mm(round(sd.flat_size[1], 1))} mm'
                                     + (f', {n_pieghe} pieghe' if n_pieghe else '') + '.')
                frasi.append(f'Circa {kg(massa)} kg.')
            return {'ok': True, 'text': ' '.join(frasi) or None}
        except Exception as ex:  # noqa: BLE001 - misure a metà mentre si scrive: niente riassunto, niente errore
            msg = ex.message if isinstance(ex, SteelCADError) else None
            return {'ok': True, 'text': None, 'warning': msg}

    def new_project(self, kind: str, values: dict | None = None) -> dict:
        try:
            doc = self._doc_modello(kind, values)
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
        recenti = []
        for p in _read_recent():
            q = Path(p)
            if q.exists():
                recenti.append({'path': str(q), 'name': q.stem, 'folder': str(q.parent),
                                'assembly': q.suffix == '.steelcad-asm',
                                'when': _quando(q.stat().st_mtime), 'thumb': _anteprima(q)})
        auto = project_io.autosave_path(_UNSAVED)
        nonsalvato = None
        if auto.exists():
            nonsalvato = {'when': _quando(auto.stat().st_mtime)}
        return _ok(show=self.blank, recent=recenti, unsaved=nonsalvato)

    def impostazioni(self) -> dict:
        """Le impostazioni che c'erano già, sparse (piegatrice, cartiglio, cartelle), lette in un colpo per la loro
        finestra (22/10)."""
        from app.drawings_service import _leggi_fissi
        cartella = Path.home() / 'Documents' / 'SteelCAD'
        r = self.sheet_rules()
        return _ok(bend_default=self.bend_default(), rules=r.get('rules', []), cartiglio=_leggi_fissi(),
                   cartelle={'lavori': str(cartella), 'libreria': str(cartella / 'Libreria')})

    def set_cartiglio(self, valori: dict) -> dict:
        from app.drawings_service import FISSI, _scrivi_fissi
        _scrivi_fissi({k: str((valori or {}).get(k) or '').strip() for k in FISSI})
        return {'ok': True, 'message': 'Cartiglio salvato: vale per le prossime tavole.'}

    def info_pezzo(self, path: str) -> dict:
        """Nome, cartella e anteprima di un file pezzo scelto con Sfoglia (per il nuovo assieme)."""
        q = Path(path)
        return _ok(path=str(q), name=q.stem, folder=str(q.parent), thumb=_anteprima(q))

    def save_thumbnail(self, path: str, data_url: str) -> dict:
        """L'anteprima del lavoro (la vista 3D, presa dall'interfaccia quando apri o salvi) per la pagina iniziale.
        Sta accanto alla lista dei recenti, non nel file del progetto."""
        import base64
        try:
            testa = 'data:image/png;base64,'
            if not isinstance(data_url, str) or not data_url.startswith(testa) or len(data_url) > 2_000_000:
                return {'ok': False, 'message': 'Anteprima non valida.'}
            f = _file_anteprima(Path(path))
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(base64.b64decode(data_url[len(testa):]))
            return {'ok': True}
        except (OSError, ValueError) as ex:
            return {'ok': False, 'message': str(ex)}

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
    def viti_dal_pezzo(self, nome: str, centro: list, asse: list, d: float, tipo: str, misura: str, lunghezza=None) -> dict:
        """Una vite nel foro cliccato sul pezzo, senza passare a mano dall'assieme (22/10): salva il pezzo (col nome dato
        se non è ancora salvato), apre un assieme nuovo col pezzo e ci mette la vite nel foro."""
        import numpy as np

        from cad_engine import assembly as A
        from cad_engine.topology.naming import _faces_of
        if self.asm is not None:
            return {'ok': False, 'message': 'Sei già in un assieme: usa Viteria.'}
        if self.path is None:
            nome = (str(nome or '').strip() or self.doc.meta.get('name') or 'Pezzo').replace('/', '-').replace('\\', '-')
            cartella = Path.home() / 'Documents' / 'SteelCAD'
            cartella.mkdir(parents=True, exist_ok=True)
            p, k = cartella / f'{nome}.steelcad', 2
            while p.exists():
                p, k = cartella / f'{nome} ({k}).steelcad', k + 1
            r = self.save(str(p))
        else:
            r = self.save()
        if not r.get('ok'):
            return r
        pezzo = str(self.path)
        self.new_assembly(f'{Path(pezzo).stem} con viti')
        r = self.asm_insert(pezzo)
        if not r.get('ok'):
            return r
        iid = self.asm.instances[0]['id']
        part = self.asm_parts[self.asm.instances[0]['file']]
        c, n = np.array(centro, dtype=float), np.array(asse, dtype=float)
        n /= np.linalg.norm(n) or 1
        k_foro = None
        for k, f in enumerate(_faces_of(part.shape)):
            inf = A.face_info(part, f)
            if inf['kind'] != 'cilindrica' or abs(inf['r'] - d / 2) > 1e-3 or abs(abs(np.dot(inf['n'], n)) - 1) > 1e-6:
                continue
            v = c - np.array(inf['p'])
            if np.linalg.norm(v - n * np.dot(v, n)) < 1e-3:
                k_foro = k
                break
        r = self.asm_insert_libreria(tipo, misura, lunghezza, {'inst': iid, 'face': k_foro} if k_foro is not None else None)
        if r.get('ok'):
            r['message'] = f'Pezzo salvato in {Path(pezzo).name}; assieme nuovo: ' + r.get('message', '')
        return r

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

    # ================================================================ prepara per il laser / l'officina
    def _nome_file(self) -> str:
        nome = (self.asm.name if self.asm is not None else self.doc.meta.get('name')) or (self.path.stem if self.path else 'pezzo')
        nome = str(nome).replace('×', 'x')             # il segno × nei nomi dei file non piace a tutti i programmi
        return re.sub(r'[\\/:*?"<>|]+', '-', nome).strip() or 'pezzo'

    def prepara_info(self) -> dict:
        """Cosa si può preparare per questo pezzo, a chi serve, in che cartella, e se i controlli sono passati."""
        import tempfile
        nome = self._nome_file()
        base = self.path.parent if self.path else Path.home() / 'Documents' / 'SteelCAD'
        corpo = self.result.body if self.asm is None else None
        sheet = getattr(corpo, 'sheet', None) if corpo is not None else None
        strutture = bool(self.result.structures) if self.asm is None else False
        pieghe = bool(sheet is not None and ((getattr(sheet, 'bend_rows', None) or []) or sheet.flanges
                                             or getattr(sheet, 'folds', None)))
        controllo = None
        if corpo is not None:
            with tempfile.TemporaryDirectory() as d:
                r = self.export_dxf(str(Path(d) / 'prova.dxf'))
            controllo = {'ok': bool(r.get('ok')), 'testo': r.get('message', '')}
        laser = controllo is not None and controllo['ok']
        voci = [
            {'id': 'laser', 'titolo': 'Per il laser', 'desc': 'Lo sviluppo piano da tagliare, con i fori. Si apre in Lantek.',
             'file': f'{nome}_sviluppo.dxf', 'si': laser, 'scelta': laser,
             'motivo': None if laser else (controllo['testo'] if controllo else 'serve una lamiera o una piastra')},
            {'id': 'piegatrice', 'titolo': 'Per la piegatrice', 'desc': 'Le pieghe in ordine: angolo, misura, correzione (si apre con Excel).',
             'file': f'{nome}_pieghe.csv', 'si': pieghe, 'scelta': pieghe, 'motivo': None if pieghe else 'il pezzo non ha pieghe'},
            {'id': 'officina', 'titolo': 'Per l’officina o il cliente',
             'desc': 'I disegni quotati con il cartiglio, da stampare' + (', con la lista di taglio dei tubi.' if strutture else '.'),
             'file': f'{nome}_disegni.pdf', 'si': corpo is not None or strutture or self.asm is not None,
             'scelta': strutture or self.asm is not None, 'motivo': None},
            {'id': 'step', 'titolo': 'Per un altro programma 3D', 'desc': 'Il pezzo in 3D (STEP), per chi usa SolidWorks, Inventor e simili.',
             'file': f'{nome}.step', 'si': corpo is not None or strutture or self.asm is not None, 'scelta': False, 'motivo': None},
        ]
        return {'ok': True, 'nome': nome, 'cartella': str(base / nome), 'voci': voci, 'controllo': controllo}

    def prepara(self, cartella: str, scelte: list, campi: dict | None = None) -> dict:
        """Salva insieme i file scelti nella cartella del lavoro, con i nomi già fatti."""
        try:
            info = self.prepara_info()
            d = Path(cartella)
            d.mkdir(parents=True, exist_ok=True)
            fatti, problemi = [], []
            for v in info['voci']:
                if v['id'] not in scelte or not v['si']:
                    continue
                p = d / v['file']
                if v['id'] == 'laser':
                    r = self.export_dxf(str(p))
                elif v['id'] == 'piegatrice':
                    r = self.export_bend_table(str(p))
                elif v['id'] == 'officina':
                    c = {**self.drawing_fields().get('fields', {}), **(campi or {})}
                    r = self.export_drawings(str(p), c, True)
                else:
                    r = self.export_step(str(p))
                (fatti if r.get('ok') else problemi).append(v['file'] if r.get('ok') else f'{v["titolo"]}: {r.get("message")}')
            if not fatti and not problemi:
                return {'ok': False, 'message': 'Scegli almeno una cosa da preparare.'}
            msg = (f'Salvati {len(fatti)} file in {d}.' if fatti else '') + (' Non riusciti: ' + '; '.join(problemi) if problemi else '')
            return {'ok': not problemi, 'files': fatti, 'cartella': str(d), 'message': msg.strip()}
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def export_step(self, path: str) -> dict:
        if self.asm is not None:
            try:
                return self.asm_export_step(path)
            except Exception as ex:  # noqa: BLE001
                return _err(ex)
        try:
            if not Path(path).parent.is_dir():
                raise SteelCADError(f'La cartella {Path(path).parent} non c’è: scegline un’altra.', code='file')
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


def _rinumera_pieghe(sm: dict) -> None:
    """Le pieghe su linea numerate in ordine lungo il pezzo (PL1 a un'estremità, poi la successiva...), non
    nell'ordine in cui sono state disegnate: così la tabella pieghe e le etichette vanno da una parte all'altra.
    I riferimenti delle flange (lato o madre) seguono il nuovo nome."""
    folds = sm.get('folds') or []
    if len(folds) < 2:
        return
    (ax, ay), (bx, by) = folds[0]['a'], folds[0]['b']
    orizz = abs(bx - ax) >= abs(by - ay)
    i, j = (1, 0) if orizz else (0, 1)
    ordinate = sorted(folds, key=lambda f: (round(f['a'][i] + f['b'][i], 6), round(f['a'][j] + f['b'][j], 6)))
    mappa = {f['id']: f'PL{k}' for k, f in enumerate(ordinate, 1)}
    if ordinate == folds and all(a == b for a, b in mappa.items()):
        return
    for f in ordinate:
        f['id'] = mappa[f['id']]
    sm['folds'] = ordinate
    for fl in sm.get('flanges') or []:
        for k in ('edge', 'parent'):
            if fl.get(k) in mappa:
                fl[k] = mappa[fl[k]]

# passo grosso ISO (mm), per far vedere i filetti nel 3D
PASSI = {'M3': 0.5, 'M4': 0.7, 'M5': 0.8, 'M6': 1.0, 'M8': 1.25, 'M10': 1.5, 'M12': 1.75, 'M16': 2.0}
# filettature metriche a passo grosso: (preforo, diametro nominale) in mm (UNI/ISO, valori di tabella)
FILETTI = {'M3': (2.5, 3), 'M4': (3.3, 4), 'M5': (4.2, 5), 'M6': (5.0, 6), 'M8': (6.8, 8), 'M10': (8.5, 10),
           'M12': (10.2, 12), 'M16': (14.0, 16)}


def _recent_file() -> Path:
    import os
    base = os.environ.get('STEELCAD_HOME') or os.path.join(os.environ.get('APPDATA') or str(Path.home()), 'SteelCAD')
    return Path(base) / 'recenti.json'


def _file_anteprima(path: Path) -> Path:
    import hashlib
    chiave = hashlib.sha1(str(Path(path).resolve()).lower().encode('utf-8')).hexdigest()[:20]
    return _recent_file().parent / 'anteprime' / f'{chiave}.png'


def _anteprima(path: Path) -> str | None:
    import base64
    try:
        return 'data:image/png;base64,' + base64.b64encode(_file_anteprima(path).read_bytes()).decode('ascii')
    except OSError:
        return None


def _quando(ts: float) -> str:
    """Quando, come lo si dice: "oggi, 11:02", "ieri", "lunedì", "17 ottobre"."""
    from datetime import date, datetime
    d = datetime.fromtimestamp(ts)
    giorni = (date.today() - d.date()).days
    if giorni == 0:
        return f'oggi, {d:%H:%M}'
    if giorni == 1:
        return 'ieri'
    if 1 < giorni < 7:
        return ('lunedì', 'martedì', 'mercoledì', 'giovedì', 'venerdì', 'sabato', 'domenica')[d.weekday()]
    mesi = ('gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 'luglio', 'agosto', 'settembre', 'ottobre',
            'novembre', 'dicembre')
    return f'{d.day} {mesi[d.month - 1]}' + (f' {d.year}' if d.year != date.today().year else '')


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


def _end_miter_fields(fields: dict) -> dict:
    from cad_engine.sheetmetal.taglio_testa import ESTREMI, VERSI
    out = {}
    if 'angle' in fields and str(fields['angle']).strip() != '':
        a = _number(fields['angle'])
        if isinstance(a, (int, float)) and not 0 < a < 80:
            raise SteelCADError('L’angolo del taglio di testa va tra 0 e 80° (45° per gli angoli a cornice).', code='campo')
        out['angle'] = a
    if 'gap' in fields:
        g = _number(fields['gap']) if str(fields['gap']).strip() != '' else 0
        if isinstance(g, (int, float)) and g < 0:
            raise SteelCADError('Il gioco di saldatura non può essere negativo.', code='campo')
        out['gap'] = g
    if 'end' in fields:
        if fields['end'] not in ESTREMI:
            raise SteelCADError('Scegli la testa: inizio, fine o tutte e due.', code='campo')
        out['end'] = fields['end']
    if 'side' in fields:
        if fields['side'] not in VERSI:
            raise SteelCADError('Verso sconosciuto.', code='campo')
        out['side'] = fields['side']
    return out


def _edge_flange_fields(fields: dict) -> dict:
    out = {}
    for k in ('length', 'angle'):
        if k in fields and str(fields[k]).strip() != '':
            out[k] = _number(fields[k])
    for k in ('trim0', 'trim1'):                                  # gioco agli angoli: vuoto = automatico
        if k in fields:
            out[k] = _number(fields[k]) if str(fields[k]).strip() != '' else None
    if fields.get('direction') in ('up', 'down'):                 # dal pannello delle pieghe: su = verso dentro
        out['side'] = 'in' if fields['direction'] == 'up' else 'out'
    return out


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
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        if not math.isfinite(v):
            raise SteelCADError(f'"{v}" non è una misura.', code='numero')
        return v
    s = str(v).strip().replace(',', '.')
    try:
        f = float(s)
    except ValueError:
        return str(v).strip()       # un'espressione: "L/2 + 10"
    if not math.isfinite(f):
        raise SteelCADError(f'"{v}" non è una misura.', code='numero')
    return int(f) if f.is_integer() else f


def _numero(v, cosa: str = 'il valore') -> float:
    """Per i campi che vogliono proprio un numero (spostamenti, coordinate, angoli): niente espressioni."""
    x = _number(v if v not in (None, '') else 'vuoto')
    if not isinstance(x, (int, float)):
        raise SteelCADError(f'{cosa[0].upper() + cosa[1:]}: "{v}" non è un numero.', code='numero')
    return x


def _punto(p, cosa: str = 'il punto'):
    if isinstance(p, (str, dict)):          # un punto che c'è già, o un aggancio (tangente, quadrante…)
        return p
    if not isinstance(p, (list, tuple)) or len(p) != 2:
        raise SteelCADError(f'{cosa[0].upper() + cosa[1:]} va dato con due coordinate.', code='numero')
    return [_numero(p[0], cosa), _numero(p[1], cosa)]


__all__ = ['Service', 'describe', 'DIMENSIONS']
