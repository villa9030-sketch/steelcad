"""La modalità assieme del servizio: più pezzi SteelCAD messi insieme con gli accoppiamenti.

Quando è aperto un assieme (self.asm), lo stato, la scena e la selezione parlano dell'assieme; aprendo un suo
pezzo si passa al pezzo e con "Torna all'assieme" si rientra (i pezzi cambiati si rileggono da soli).
"""
from __future__ import annotations

import copy
import math
import re
import time
from pathlib import Path

import numpy as np

from cad_engine import assembly as A
from cad_engine.errors import SteelCADError
from cad_engine.units import fmt_kg, fmt_mm


def _ok(**kw):
    return {'ok': True, **kw}



def _in_assieme(fn):
    """I comandi dell'assieme fuori da un assieme (dal menu comandi, mentre si lavora su un pezzo): un messaggio."""
    import functools

    @functools.wraps(fn)
    def dentro(self, *a, **kw):
        if self.asm is None:
            return {'ok': False, 'code': 'assieme', 'message': 'Questo comando è per gli assiemi: apri o crea un assieme.'}
        return fn(self, *a, **kw)
    return dentro

class AssemblyMixin:
    asm = None

    # ------------------------------------------------------------------ apertura, salvataggio, cronologia
    def _asm_set(self, asm, path=None):
        self.asm = asm
        self.asm_parts = {}
        self.asm_undo, self.asm_redo = [], []
        self.asm_dirty = False
        self._asm_ritorno = None
        self.path = Path(path) if path else None
        self.blank = False
        self.asm_ritrovati, self._asm_cercati = [], set()
        self._asm_reload()
        self.scene_version += 1

    def _ritrova_pezzo(self, vecchio: str, cartelle_prima=()) -> str | None:
        """Un pezzo che non è più dove l'assieme l'aveva lasciato (spostato a mano, 23/10): lo si cerca per nome
        nelle cartelle dove ne sono già stati ritrovati altri, accanto all'assieme e sotto, poi in Documenti\\SteelCAD.
        Se ce n'è più d'uno con quel nome non si tira a indovinare."""
        nome = Path(vecchio).name
        luoghi = [Path(c) for c in cartelle_prima]
        if self.path:
            luoghi.append(Path(self.path).parent)
        luoghi.append(Path.home() / 'Documents' / 'SteelCAD')
        visti = set()
        for base in luoghi:
            try:
                if not base.is_dir() or str(base) in visti:
                    continue
                visti.add(str(base))
                if (base / nome).is_file():
                    return str((base / nome).resolve())
                trovati = {str(x.resolve()) for _, x in zip(range(50), base.rglob(nome)) if x.is_file()}
            except OSError:
                continue
            if len(trovati) == 1:
                return trovati.pop()
            if len(trovati) > 1:
                return None
        return None

    def _sposta_pezzo(self, vecchio: str, nuovo: str):
        for i in self.asm.instances:
            if i['file'] == vecchio:
                i['file'] = nuovo
        self.asm_ritrovati = list(getattr(self, 'asm_ritrovati', [])) + [{'name': Path(nuovo).stem, 'folder': str(Path(nuovo).parent)}]
        self.asm_dirty = True

    def _asm_reload(self):
        """Rilegge i pezzi (solo quelli cambiati) e rimette a posto le istanze."""
        t0 = time.perf_counter()
        self.asm_errors = []
        # i pezzi spostati si ritrovano da soli; quelli che non si trovano restano in elenco, con «Cerca…»
        cercati = getattr(self, '_asm_cercati', set())
        cartelle = []
        for f in dict.fromkeys(i['file'] for i in self.asm.instances):
            if Path(f).exists() or f in cercati:
                continue
            nuovo = self._ritrova_pezzo(f, cartelle)
            if nuovo:
                self._sposta_pezzo(f, nuovo)
                cartelle.insert(0, str(Path(nuovo).parent))
            else:
                cercati.add(f)
        self._asm_cercati = cercati
        parti = {}
        for i in self.asm.instances:
            if i['file'] in parti:
                continue
            try:
                parti[i['file']] = A.load_part(i['file'])
            except SteelCADError as ex:
                self.asm_errors.append({'id': i['id'], 'message': ex.message})
        self.asm_parts = parti
        validi = A.Assembly(self.asm.name, [i for i in self.asm.instances if i['file'] in parti],
                            [m for m in self.asm.mates if m['a']['inst'] in self._asm_ids(parti) and m['b']['inst'] in self._asm_ids(parti)],
                            self.asm.path)
        A.solve(validi, parti)
        self.asm.warnings = getattr(validi, 'warnings', [])
        self.asm_ms = (time.perf_counter() - t0) * 1000

    def _asm_ids(self, parti):
        return {i['id'] for i in self.asm.instances if i['file'] in parti}

    def asm_ritrova_in(self, vecchio: str, nuovo: str) -> dict:
        """Il pezzo mancante indicato a mano (Cerca…): si usa quel file, e gli altri mancanti si cercano per nome nella
        stessa cartella (di solito sono stati spostati tutti insieme)."""
        q = Path(nuovo)
        if not q.is_file():
            return {'ok': False, 'message': f'{q.name} non c’è.'}
        self.asm_ritrovati = []
        self._sposta_pezzo(vecchio, str(q.resolve()))
        for f in dict.fromkeys(i['file'] for i in self.asm.instances):
            if not Path(f).exists() and (q.parent / Path(f).name).is_file():
                self._sposta_pezzo(f, str((q.parent / Path(f).name).resolve()))
        self._asm_cercati = set()
        self._asm_reload()
        self.scene_version += 1
        n = len(self.asm_ritrovati)
        self.asm_ritrovati = []                     # li hai indicati tu: non sono «ritrovati da solo»
        r = _ok(state=self.state())
        r['message'] = (f'Ritrovat{"o" if n == 1 else "i"} {n} pezz{"o" if n == 1 else "i"}: salva l’assieme per ricordare '
                        'dove stanno adesso.')
        return r

    def new_assembly(self, name: str = 'Assieme') -> dict:
        self._asm_set(A.Assembly(name or 'Assieme'))
        return _ok(state=self.state())

    def new_assembly_con_pezzi(self, name: str, pezzi: list) -> dict:
        """Assieme nuovo coi pezzi scelti e le loro quantità (22/10: una scatola = fondo 1, parete A 2, parete B 2):
        ogni copia entra a fianco della precedente; il primo pezzo resta fermo (la base)."""
        lista = []
        for p in pezzi or []:
            try:
                n = int(p.get('n') or 1)
            except (TypeError, ValueError):
                n = 0
            if not 1 <= n <= 100:
                return {'ok': False, 'message': f'Quantità di «{Path(str(p.get("path"))).stem}»: scrivi un numero da 1 a 100.'}
            lista += [str(p['path'])] * n
        r = self.new_assembly(name)
        if not r.get('ok') or not lista:
            return r
        for k, f in enumerate(lista):
            r = self.asm_insert(f)
            if not r.get('ok'):
                return r
            if k == 0:
                self.asm.instances[0]['fixed'] = True
        self.asm_undo.clear()                       # Annulla non torna all'assieme vuoto: è il punto di partenza
        r = _ok(state=self.state())
        r['message'] = f'Assieme con {len(lista)} {"pezzo" if len(lista) == 1 else "pezzi"}: il primo è fermo, gli altri sono a fianco da accoppiare.'
        return r

    def _asm_change(self, label: str, fn):
        prima = self.asm.to_dict()
        try:
            out = fn()
            self._asm_reload()
        except Exception as ex:  # noqa: BLE001 - qualunque errore: l'assieme torna com'era
            self.asm.__dict__.update(A.Assembly.from_dict(prima, self.asm.path).__dict__)
            self._asm_reload()
            if isinstance(ex, SteelCADError):
                return {'ok': False, 'message': ex.message, 'code': ex.code}
            from app.service import _err
            return _err(ex)
        self.asm_undo.append((label, prima))
        self.asm_redo.clear()
        self.asm_dirty = True
        self.scene_version += 1
        r = _ok(state=self.state())
        if isinstance(out, dict):
            r.update(out)
        return r

    def _asm_undo(self, avanti=False):
        da, a = (self.asm_redo, self.asm_undo) if avanti else (self.asm_undo, self.asm_redo)
        if not da:
            return _ok(state=self.state())
        label, d = da.pop()
        a.append((label, self.asm.to_dict()))
        self.asm = A.Assembly.from_dict(d, self.asm.path)
        self._asm_reload()
        self.asm_dirty = True
        self.scene_version += 1
        return _ok(state=self.state())

    def asm_history_goto(self, pos) -> dict:
        pos = int(pos)
        qui = len(self.asm_undo)
        if not 0 <= pos <= qui + len(self.asm_redo):
            return {'ok': False, 'message': 'Quel passo non c’è più.'}
        r = _ok(state=self.state())
        for _ in range(abs(pos - qui)):
            r = self._asm_undo(pos > qui)
        return r

    def _asm_save(self, path=None):
        p = Path(path) if path else self.path
        if p is None:
            return {'ok': False, 'code': 'serve_percorso', 'message': 'Scegli dove salvare l’assieme.'}
        self.path = A.save(self.asm, p)
        self.asm_dirty = False
        from app.service import _add_recent
        _add_recent(self.path)
        return _ok(state=self.state(), path=str(self.path))

    def _asm_open(self, path):
        asm = A.load(path)
        self._asm_set(asm, path)
        from app.service import _add_recent
        _add_recent(Path(path))
        return _ok(state=self.state())

    # ------------------------------------------------------------------ istanze
    @_in_assieme
    def asm_insert(self, path: str) -> dict:
        """Mette nell'assieme una copia del pezzo (file .steelcad), a destra di quello che c'è già."""
        p = Path(path).resolve()

        def fn():
            part = A.load_part(p)
            dx = 0.0
            if self.asm.instances:
                xs = []
                for i in self.asm.instances:
                    pp = self.asm_parts.get(i['file'])
                    if pp is not None:
                        bb = A.placed_shape(pp, i['R'], i['T']).bounding_box() if i.get('R') else None
                        if bb is not None:
                            xs.append(bb.max.X)
                bb0 = __import__('build123d').Shape.cast(part.shape).bounding_box()
                dx = (max(xs) if xs else 0) + 50 - bb0.min.X
            iid = self.asm.new_id('I', {i['id'] for i in self.asm.instances})
            nome = part.doc.meta.get('name') or p.stem
            n = sum(1 for i in self.asm.instances if i['file'] == str(p))
            self.asm.instances.append({'id': iid, 'file': str(p), 'name': f'{nome} ({n + 1})' if n else nome,
                                       'R': np.eye(3).tolist(), 'T': [dx, 0, 0]})
            return {'select': iid}
        return self._asm_change(f'Inserisci {p.stem}', fn)

    @_in_assieme
    def asm_remove(self, iid: str) -> dict:
        def fn():
            self.asm.instance(iid)
            self.asm.instances = [i for i in self.asm.instances if i['id'] != iid]
            self.asm.mates = [m for m in self.asm.mates if iid not in (m['a']['inst'], m['b']['inst'])]
        return self._asm_change(f'Togli {iid}', fn)

    @_in_assieme
    def asm_move(self, iid: str, dx, dy, dz) -> dict:
        from app.service import _numero

        def fn():
            i = self.asm.instance(iid)
            d = [_numero(v or 0, 'lo spostamento') for v in (dx, dy, dz)]
            i['T'] = (np.array(i.get('T') or [0, 0, 0]) + d).tolist()
        return self._asm_change(f'Sposta {iid}', fn)

    @_in_assieme
    def asm_rotate(self, iid: str, axis: str, deg) -> dict:
        """Ruota attorno al centro del pezzo, lungo un asse del mondo (X, Y, Z)."""
        from app.service import _numero

        def fn():
            if str(axis).lower() not in ('x', 'y', 'z'):
                raise A.AssemblyError('Si ruota attorno a X, Y o Z.')
            gradi = _numero(deg, 'l’angolo')
            i = self.asm.instance(iid)
            part = self.asm_parts[i['file']]
            R, T = np.array(i['R']), np.array(i['T'])
            bb = __import__('build123d').Shape.cast(part.shape).bounding_box()
            c = R @ np.array([(bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2]) + T
            d = {'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]}[axis.lower()]
            Q = A._rot_axis(np.array(d, dtype=float), np.radians(gradi))
            i['R'] = (Q @ R).tolist()
            i['T'] = (Q @ (T - c) + c).tolist()
        return self._asm_change(f'Ruota {iid}', fn)

    @_in_assieme
    def asm_rotate_all(self, axis: str, deg) -> dict:
        """Ruota tutto l'assieme insieme (gli accoppiamenti restano rispettati) attorno al suo centro, lungo X, Y o Z."""
        from app.service import _numero

        def fn():
            if str(axis).lower() not in ('x', 'y', 'z'):
                raise A.AssemblyError('Si ruota attorno a X, Y o Z.')
            gradi = _numero(deg, 'l’angolo')
            if not self.asm.instances:
                raise A.AssemblyError('L’assieme è vuoto: non c’è niente da ruotare.')
            punti = []
            for i in self.asm.instances:
                part = self.asm_parts.get(i['file'])
                if part is None:
                    continue
                bb = __import__('build123d').Shape.cast(part.shape).bounding_box()
                Ri, Ti = np.array(i['R']), np.array(i['T'])
                for x in (bb.min.X, bb.max.X):
                    for y in (bb.min.Y, bb.max.Y):
                        for z in (bb.min.Z, bb.max.Z):
                            punti.append(Ri @ np.array([x, y, z]) + Ti)
            c = (np.min(punti, axis=0) + np.max(punti, axis=0)) / 2 if punti else np.zeros(3)
            d = {'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]}[axis.lower()]
            Q = A._rot_axis(np.array(d, dtype=float), np.radians(gradi))
            for i in self.asm.instances:
                Ri, Ti = np.array(i['R']), np.array(i['T'])
                i['R'] = (Q @ Ri).tolist()
                i['T'] = (Q @ (Ti - c) + c).tolist()
        return self._asm_change(f'Ruota l’assieme attorno a {str(axis).upper()}', fn)

    @_in_assieme
    def asm_set(self, iid: str, fields: dict) -> dict:
        def fn():
            i = self.asm.instance(iid)
            if 'name' in fields and str(fields['name']).strip():
                i['name'] = str(fields['name']).strip()
            if 'fixed' in fields:
                for j in self.asm.instances:
                    j.pop('fixed', None)
                if fields['fixed']:
                    i['fixed'] = True
        return self._asm_change(f'{iid}: modifica', fn)

    # ------------------------------------------------------------------ accoppiamenti
    def _asm_face(self, iid, face_index):
        from cad_engine.topology.naming import _faces_of
        i = self.asm.instance(iid)
        part = self.asm_parts.get(i['file'])
        if part is None:
            raise A.AssemblyError(f'Il pezzo di {iid} non si legge.')
        facce = list(_faces_of(part.shape))
        if face_index is None or not 0 <= int(face_index) < len(facce):
            raise A.AssemblyError('Clicca una faccia del pezzo.')
        return {'inst': iid, **A.face_info(part, facce[int(face_index)])}

    # cosa vuole ogni accoppiamento: le facce da cliccare (fermo, mobile) e il messaggio se non vanno
    _SERVE = {
        'faccia': ({'piana'}, {'piana'}, 'Faccia su faccia vuole due facce piane.'),
        'distanza': ({'piana'}, {'piana'}, 'Distanza vuole due facce piane.'),
        'asse': ({'cilindrica'}, {'cilindrica'}, 'Foro su foro vuole due fori (facce cilindriche).'),
        'parallelo': ({'piana', 'cilindrica'}, {'piana', 'cilindrica'}, 'Parallele vuole facce piane o fori/tubi.'),
        'perpendicolare': ({'piana', 'cilindrica'}, {'piana', 'cilindrica'},
                           'Perpendicolari vuole facce piane o fori/tubi.'),
        'angolo': ({'piana'}, {'piana'}, 'Angolo vuole due facce piane.'),
        'tangente': ({'piana', 'cilindrica'}, {'piana', 'cilindrica'},
                     'Tangente vuole un tubo (o un foro) e una faccia piana, o due tubi.'),
        'centra': ({'piana'}, {'piana'}, 'In mezzo vuole facce piane: due del pezzo fermo, due di quello da centrare.'),
        'blocca': (None, None, ''),
        'spigolo': ({'spigolo'}, {'spigolo'}, 'Spigolo su spigolo vuole due spigoli dritti.'),
        'spigolo_faccia': ({'piana'}, {'spigolo'}, 'Spigolo su faccia: prima la faccia piana del pezzo fermo, poi lo '
                           'spigolo dritto dell’altro.'),
        'cono': ({'conica'}, {'conica'}, 'Cono su cono vuole due facce coniche: la svasatura del foro e la testa della vite.'),
        'testa': ({'piana'}, {'piana'}, 'Testa a testa vuole le due facce piane dei tagli di testa (a 45°), una per pezzo.'),
    }

    def _asm_edge(self, iid, punto):
        """Lo spigolo dritto della copia iid più vicino al punto cliccato (nel mondo)."""
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from OCP.gp import gp_Pnt

        from cad_engine.topology.naming import _edges_of
        i = self.asm.instance(iid)
        part = self.asm_parts.get(i['file'])
        if part is None:
            raise A.AssemblyError(f'Il pezzo di {iid} non si legge.')
        Rm, T = np.array(i['R'], dtype=float), np.array(i['T'], dtype=float)
        q = Rm.T @ (np.array(punto, dtype=float) - T)
        v = BRepBuilderAPI_MakeVertex(gp_Pnt(*[float(c) for c in q])).Vertex()
        migliore = None
        for e in _edges_of(part.shape):
            dd = BRepExtrema_DistShapeShape(v, e)
            if dd.IsDone() and (migliore is None or dd.Value() < migliore[0]):
                migliore = (dd.Value(), e)
        if migliore is None or migliore[0] > 2.0:
            raise A.AssemblyError('Clicca proprio sullo spigolo.')
        return {'inst': iid, **A.edge_info(part, migliore[1])}

    def _movimenti(self, iid: str) -> list:
        """Distanze e angoli che muovono questo pezzo: col cursore nel suo pannello (un cassetto si apre e si chiude
        cliccando il cassetto, senza cercare l'accoppiamento nell'albero). In avanti/indietro prima di su/giù."""
        out = []
        for m in self.asm.mates:
            if m.get('off') or m['type'] not in ('distanza', 'angolo') or m['b']['inst'] != iid:
                continue
            try:
                ia = self.asm.instance(m['a']['inst'])
                n = np.array(ia['R']) @ A._info(m['a'], self.asm_parts, self.asm)['n']
            except (A.AssemblyError, KeyError):
                continue
            if m['type'] == 'angolo':
                nome, val, campo = 'Gira', float(m.get('angle') or 0), 'angle'
            else:
                nome = 'Su / giù' if abs(n[2]) > 0.9 else 'Apri / chiudi'
                val, campo = float(m.get('offset') or 0), 'offset'
            out.append({'id': m['id'], 'nome': nome, 'campo': campo, 'valore': val})
        out.sort(key=lambda x: x['nome'] != 'Apri / chiudi')
        return out

    def _misura_mate(self, m: dict) -> float:
        """Il valore che l'accoppiamento ha adesso, per partire da lì senza spostare niente: la distanza (mm) o
        l'angolo (gradi). Tangente e in mezzo partono da 0 (appoggiato, centrato)."""
        F = {}
        for k in ('a', 'b', 'a2', 'b2'):
            if m.get(k):
                i = self.asm.instance(m[k]['inst'])
                F[k] = A._nel_mondo(A._info(m[k], self.asm_parts, self.asm), np.array(i['R']), np.array(i['T']))
        a, b = F['a'], F['b']
        if m['type'] == 'distanza':
            d = float(np.dot(a['n'], b['p'] - a['p']))
            if np.dot(a['n'], b['n']) > 0:              # le facce guardano dalla stessa parte: allineate
                m['flip'] = True
            return d
        if m['type'] == 'angolo':
            c = -float(np.dot(a['n'], b['n']))
            return math.degrees(math.acos(max(-1.0, min(1.0, c))))
        return 0.0

    @_in_assieme
    def asm_add_mate(self, kind: str, a: dict, b: dict, offset=0, flip=False, a2=None, b2=None) -> dict:
        """a: la faccia del pezzo che sta fermo, b: quella del pezzo che si muove. {'inst': id, 'face': indice}.
        In mezzo vuole anche a2 (la faccia opposta del pezzo fermo) e b2 (l'opposta di quello da centrare).
        offset: la distanza (mm) o l'angolo (gradi); None o vuoto = quello che c'è adesso (non si sposta niente)."""
        from app.service import _numero
        if kind not in A.MATE_TYPES:
            return {'ok': False, 'message': f'Accoppiamento "{kind}" sconosciuto.'}

        def fn():
            if a['inst'] == b['inst']:
                raise A.AssemblyError('Le due facce sono dello stesso pezzo: scegline una su un altro pezzo.')
            serve_a, serve_b, msg = self._SERVE[kind]
            refs = {'a': a, 'b': b}
            if kind == 'centra':
                if not a2 or not b2:
                    raise A.AssemblyError(msg)
                if a2['inst'] != a['inst'] or b2['inst'] != b['inst']:
                    raise A.AssemblyError('In mezzo: le prime due facce sono di un pezzo, le altre due dell’altro.')
                refs.update(a2=a2, b2=b2)
            if kind == 'blocca':
                rf = {'a': {'inst': a['inst']}, 'b': {'inst': b['inst']}}
            else:
                rf = {k: (self._asm_edge(v['inst'], v['edge_pt']) if v.get('edge_pt') is not None
                          else self._asm_face(v['inst'], v.get('face'))) for k, v in refs.items()}
                for k, r in rf.items():
                    if r['kind'] not in (serve_a if k.startswith('a') else serve_b):
                        raise A.AssemblyError(msg)
                if kind == 'tangente' and rf['a']['kind'] == 'piana' and rf['b']['kind'] == 'piana':
                    raise A.AssemblyError(msg)
                if kind == 'cono' and abs(rf['a']['r'] - rf['b']['r']) > 0.5:
                    raise A.AssemblyError(f'I due coni hanno angoli diversi ({2 * rf["a"]["r"]:.0f}° e {2 * rf["b"]["r"]:.0f}°): '
                                          'la vite non si appoggerebbe. Rifai la svasatura con l’angolo della vite (90°).')
                if kind == 'centra':
                    for x, y, chi in (('a', 'a2', 'del pezzo fermo'), ('b', 'b2', 'del pezzo da centrare')):
                        if abs(abs(float(np.dot(rf[x]['n'], rf[y]['n']))) - 1) > 1e-6 or rf[x]['p'] == rf[y]['p']:
                            raise A.AssemblyError(f'In mezzo: le due facce {chi} devono essere parallele e diverse '
                                                  '(i due lati di un U, le due facce di una piastra).')
            terra = next((i['id'] for i in self.asm.instances if i.get('fixed')), self.asm.instances[0]['id'])
            if rf['a']['inst'] != terra and rf['b']['inst'] == terra:      # il fermo va in a
                rf = {'a': rf['b'], 'b': rf['a'], **({'a2': rf['b2'], 'b2': rf['a2']} if 'a2' in rf else {})}
            mid = self.asm.new_id('M', {m['id'] for m in self.asm.mates})
            m = {'id': mid, 'type': kind, **rf, 'offset': 0.0, 'flip': bool(flip)}
            vuoto = offset is None or str(offset).strip() == ''
            if kind == 'blocca':
                ia, ib = self.asm.instance(rf['a']['inst']), self.asm.instance(rf['b']['inst'])
                RA, TA = np.array(ia['R'], dtype=float), np.array(ia['T'], dtype=float)
                m['rel_R'] = (RA.T @ np.array(ib['R'], dtype=float)).tolist()
                m['rel_T'] = (RA.T @ (np.array(ib['T'], dtype=float) - TA)).tolist()
            elif kind == 'angolo':
                m['angle'] = round(self._misura_mate(m), 3) if vuoto else _numero(offset, 'l’angolo')
                if not 0 <= m['angle'] <= 180:
                    raise A.AssemblyError('L’angolo va da 0° a 180°.')
            elif kind == 'testa':
                m['offset'] = self._gioco_teste(rf['a']['inst'], rf['b']['inst']) if vuoto else _numero(offset, 'il gioco')
                if m['offset'] < 0:
                    raise A.AssemblyError('Il gioco non può essere negativo.')
            elif kind in ('faccia', 'distanza', 'tangente', 'centra', 'spigolo_faccia'):
                m['offset'] = round(self._misura_mate(m), 3) if vuoto else _numero(offset, 'la distanza')
            self.asm.mates.append(m)
            return {'select': 'mate=' + mid}
        return self._asm_change(A.MATE_TYPES[kind].capitalize(), fn)

    def _gioco_teste(self, ia: str, ib: str) -> float:
        """Testa a testa senza gioco scritto: quello dei tagli di testa dei due pezzi (metà ciascuno)."""
        tot = 0.0
        for iid in (ia, ib):
            part = self.asm_parts.get(self.asm.instance(iid)['file'])
            tagli = [f for f in getattr(part.doc, 'features', []) if isinstance(f, dict) and f.get('type') == 'sheet_miter'
                     and not f.get('disattiva')] if part is not None else []
            if tagli:
                try:
                    tot += float(tagli[-1].get('gap') or 0) / 2
                except (TypeError, ValueError):
                    pass
        return round(tot, 6)

    @_in_assieme
    def asm_edit_mate(self, mid: str, fields: dict) -> dict:
        from app.service import _numero

        def fn():
            m = next((x for x in self.asm.mates if x['id'] == mid), None)
            if m is None:
                raise A.AssemblyError(f'Non c’è l’accoppiamento {mid}.')
            if 'offset' in fields and str(fields['offset']).strip() != '':
                m['offset'] = _numero(fields['offset'], 'la distanza')
            if 'angle' in fields and str(fields['angle']).strip() != '':
                ang = _numero(fields['angle'], 'l’angolo')
                if not 0 <= ang <= 180:
                    raise A.AssemblyError('L’angolo va da 0° a 180°.')
                m['angle'] = ang
            if 'flip' in fields:
                m['flip'] = bool(fields['flip'])
            if 'off' in fields:
                m['off'] = bool(fields['off'])
        return self._asm_change(f'{mid}: modifica', fn)

    @_in_assieme
    def asm_trascina_mate(self, mid: str, campo: str, valore, fine: bool = False) -> dict:
        """Il cursore di un accoppiamento (distanza, angolo) mentre lo si trascina: i pezzi si muovono subito e si
        rimandano solo le loro posizioni. A cursore lasciato (fine) la modifica si registra una volta, con l'annulla
        che torna a prima del trascinamento."""
        from app.service import _numero
        if campo not in ('offset', 'angle'):
            return {'ok': False, 'message': 'Si trascinano solo distanza e angolo.'}
        m = next((x for x in self.asm.mates if x['id'] == mid), None)
        if m is None:
            return {'ok': False, 'message': f'Non c’è l’accoppiamento {mid}.'}
        tenuti = self.__dict__.setdefault('_trascinati', {})
        if fine:
            if mid in tenuti:
                m[campo] = tenuti.pop(mid)                # si riparte da prima: l'annulla torna lì
            return self.asm_edit_mate(mid, {campo: valore})
        try:
            v = _numero(valore, 'il valore')
        except SteelCADError as ex:
            return {'ok': False, 'message': ex.message}
        tenuti.setdefault(mid, m.get(campo) or 0)
        m[campo] = v
        A.solve(self.asm, self.asm_parts)
        pose = {}
        for i in self.asm.instances:
            R, T = i['R'], i['T']
            pose[i['id']] = [R[0][0], R[0][1], R[0][2], T[0], R[1][0], R[1][1], R[1][2], T[1], R[2][0], R[2][1], R[2][2], T[2], 0, 0, 0, 1]
        return {'ok': True, 'pose': pose}

    @_in_assieme
    def asm_delete_mate(self, mid: str) -> dict:
        def fn():
            self.asm.mates = [m for m in self.asm.mates if m['id'] != mid]
        return self._asm_change(f'Togli {mid}', fn)

    @_in_assieme
    def asm_interferences(self) -> dict:
        trovate = A.interferences(self.asm, self.asm_parts)
        nomi = {i['id']: i['name'] for i in self.asm.instances}
        righe = [{**x, 'label': f'{nomi.get(x["a"], x["a"])} e {nomi.get(x["b"], x["b"])}: {fmt_mm(round(x["volume"], 1))} mm³'}
                 for x in trovate]
        return _ok(interferences=righe, message='Nessuna interferenza: i pezzi non si compenetrano.' if not righe else
                   f'{len(righe)} interferenz{"a" if len(righe) == 1 else "e"}.')

    # ------------------------------------------------------------------ incastri tra due pezzi
    def _asm_tip_contact(self, iid: str, face_index):
        """La faccia scelta è la punta di una flangia (o un fianco della base) che appoggia su una faccia piana di un
        altro pezzo? Ritorna (info punta nel mondo, altra istanza, nome dell'altra faccia, faccia nel mondo)."""
        import build123d as bd
        from cad_engine.topology.naming import _faces_of
        ra = self._asm_face(iid, face_index)
        nome = ra.get('name') or ''
        if ra['kind'] != 'piana' or not (nome.endswith('/punta') or '/lato/' in nome):
            return None
        ia = self.asm.instance(iid)
        Ra, Ta = np.array(ia['R']), np.array(ia['T'])
        pA, nA = Ra @ np.array(ra['p']) + Ta, Ra @ np.array(ra['n'])
        for ib in self.asm.instances:
            if ib['id'] == iid or ib['file'] not in self.asm_parts:
                continue
            part = self.asm_parts[ib['file']]
            Rb, Tb = np.array(ib['R']), np.array(ib['T'])
            locale = Rb.T @ (pA - Tb)                    # il centro della punta, nel pezzo B
            for f in _faces_of(part.shape):
                inf = A.face_info(part, f)
                if inf['kind'] != 'piana' or not inf['name']:
                    continue
                nB = Rb @ np.array(inf['n'])
                pB = Rb @ np.array(inf['p']) + Tb
                if np.dot(nA, nB) > -0.999999 or abs(np.dot(pA - pB, nB)) > 1e-3:
                    continue
                if bd.Face(f).distance_to(bd.Vector(*locale)) < 1e-3:
                    return ra, ib['id'], inf['name'], nome
        return None

    @_in_assieme
    def asm_tabs(self, iid: str, face_index, n, w, gioco, sporgenza=0) -> dict:
        """Incastri tra due pezzi: la punta (faccia scelta) del pezzo di iid appoggia su una faccia di un altro pezzo.
        Linguette nel file del primo pezzo, asole nel file del secondo: si modificano e si salvano i due file
        (resta la copia .bak). Tutte le copie di quei pezzi cambiano."""
        import build123d as bd
        from app.service import _number
        from cad_engine import project_io
        from cad_engine.sketch.face_plane import plane_of
        from app import sketch_ops
        try:
            n, w, c, sp = int(_number(n)), _number(w), _number(gioco), _number(sporgenza or 0)
            if n < 1 or w <= 0 or c < 0 or sp < 0:
                raise SteelCADError('Numero almeno 1, larghezza maggiore di zero, gioco e sporgenza non negativi.')
            cont = self._asm_tip_contact(iid, face_index)
            if cont is None:
                raise SteelCADError('Questa faccia non appoggia su un altro pezzo: scegli la punta di una flangia (o il fianco '
                                    'della base) che tocca una faccia di un altro pezzo.')
            ra, iidb, nome_b, nome_a = cont
            ia, ib = self.asm.instance(iid), self.asm.instance(iidb)
            if ia['file'] == ib['file']:
                raise SteelCADError('I due pezzi sono lo stesso file: gli incastri si fanno tra pezzi diversi.')
            pa, pb = self.asm_parts[ia['file']], self.asm_parts[ib['file']]
            sa = getattr(pa.result.body, 'sheet', None)
            sb = getattr(pb.result.body, 'sheet', None)
            if sa is None or sb is None:
                raise SteelCADError('Gli incastri si fanno tra due lamiere.')
            fid = nome_a.split('/')[0]
            if nome_a.endswith('/punta'):
                flid = nome_a.split('/')[1]
                g = next(x for x in sa.flanges if x.fid == flid)
                dvec, nrm = (v.normalized() for v in g.frame())
                xf = g.xf.normalized()
                nome_est = f'{fid}/{flid}/esterno'
            else:
                raise SteelCADError('Per ora gli incastri tra pezzi partono dalla punta di una flangia.')
            punta = max((bd.Face(f) for f in pa.result.body.names.get(nome_a, [])), key=lambda f: f.area)
            us = [(bd.Vector(v) - g.origin).dot(xf) for v in punta.vertices()]
            u0, u1 = min(us), max(us)
            # solo il tratto dove la punta appoggia davvero sull'altro pezzo
            Ra_, Ta_ = np.array(ia['R']), np.array(ia['T'])
            Rb_, Tb_ = np.array(ib['R']), np.array(ib['T'])
            fb = [bd.Face(f) for f in pb.result.body.names.get(nome_b, [])]
            c0 = punta.center()
            bu0 = (c0 - g.origin).dot(xf)
            sopra = []
            for k in range(201):
                u = u0 + (u1 - u0) * k / 200
                q = c0 + xf * (u - bu0)
                qb = Rb_.T @ (Ra_ @ np.array([q.X, q.Y, q.Z]) + Ta_ - Tb_)
                if any(f.distance_to(bd.Vector(*qb)) < 1e-3 for f in fb):
                    sopra.append(u)
            if not sopra:
                raise SteelCADError('La punta non appoggia sull’altro pezzo.')
            u0, u1 = min(sopra), max(sopra)
            if (u1 - u0) / (n + 1) < w + 2 * c + 2:
                raise SteelCADError(f'{n} linguette da {fmt_mm(w)} non stanno sul tratto dove la punta appoggia '
                                    f'({fmt_mm(round(u1 - u0, 1))} mm): mettine meno o più strette.')
            centro = punta.center()
            bu = (centro - g.origin).dot(xf)
            centri = [centro + xf * (u0 + (u1 - u0) * (k + 1) / (n + 1) - bu) for k in range(n)]
            tb = sb.thickness
            ta = sa.thickness
            Ra, Ta = np.array(ia['R']), np.array(ia['T'])
            Rb, Tb = np.array(ib['R']), np.array(ib['T'])
            a2b = lambda v: Rb.T @ (Ra @ np.array([v.X, v.Y, v.Z]) + Ta - Tb)  # noqa: E731
            dir_b = lambda v: Rb.T @ (Ra @ np.array([v.X, v.Y, v.Z]))  # noqa: E731
            est = bd.Face(pa.result.body.face(nome_est)[0])
            ne, oe = est.normal_at(), est.center()
            sul_est = lambda p: p - ne * (p - oe).dot(ne)  # noqa: E731
            doc_a, doc_b = project_io.load(ia['file']), project_io.load(ib['file'])
            body_a, body_b = doc_a.rebuild().body, doc_b.rebuild().body
            # linguette nel pezzo A
            sk = doc_a.add_sketch({'face': nome_est}, f'Sketch: linguette verso {ib["name"]}')
            pl = plane_of(body_a, nome_est, sk)
            sketch_ops.add_reference_edges(sk, est, pl, body_a.shape)
            for C in centri:
                q = [pl.to_local_coords(sul_est(C + xf * a_ * (w / 2) + dvec * d)) for a_, d in ((-1, -1), (1, -1), (1, tb + sp), (-1, tb + sp))]
                ids = [sk.point(p.X, p.Y) for p in q]
                for pid in ids:
                    sk.constrain('fix', pid)
                for x, y in zip(ids, ids[1:] + ids[:1]):
                    sk.line(x, y)
            doc_a.add_feature('sheet_cut', f'Linguette verso {ib["name"]}', sketch=sk.id, mode='add')
            # asole nel pezzo B
            skb = doc_b.add_sketch({'face': nome_b}, f'Sketch: asole per {ia["name"]}')
            plb = plane_of(body_b, nome_b, skb)
            sketch_ops.add_reference_edges(skb, bd.Face(body_b.face(nome_b)[0]), plb, body_b.shape)
            xb, nb = dir_b(xf), dir_b(nrm)
            for C in centri:
                cb = a2b(C)
                q = [plb.to_local_coords(bd.Vector(*(cb + xb * a_ * (w / 2 + c) + nb * b_ * (ta / 2 + c))))
                     for a_, b_ in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                ids = [skb.point(p.X, p.Y) for p in q]
                for pid in ids:
                    skb.constrain('fix', pid)
                for x, y in zip(ids, ids[1:] + ids[:1]):
                    skb.line(x, y)
            doc_b.add_feature('sheet_cut', f'Asole per {ia["name"]}', sketch=skb.id)
            for doc in (doc_a, doc_b):
                r = doc.rebuild()
                if r.errors:
                    raise SteelCADError('Gli incastri non si riescono a fare: ' + r.errors[0].message)
            project_io.save(doc_a, ia['file'])
            project_io.save(doc_b, ib['file'])
        except SteelCADError as ex:
            return {'ok': False, 'message': ex.message, 'code': ex.code}
        self._asm_reload()
        # le linguette restano nelle asole: due accoppiamenti faccia su faccia (col gioco) tra un fianco della prima
        # linguetta e la parete dell'asola davanti, e tra la faccia della flangia e l'altra parete. Se il pezzo
        # con le asole cambia, quello con le linguette lo segue.
        w0 = lambda v: Ra @ np.array([v.X, v.Y, v.Z]) + Ta  # noqa: E731
        d0 = lambda v: Ra @ np.array([v.X, v.Y, v.Z])  # noqa: E731
        C0 = centri[0]
        coppie = [(w0(C0 - xf * (w / 2) + dvec * (tb / 2)), -d0(xf), w0(C0 - xf * (w / 2 + c) + dvec * (tb / 2)), d0(xf)),
                  (w0(sul_est(C0) + dvec * (tb / 2)), d0(ne), w0(sul_est(C0) + bd.Vector(*ne) * c + dvec * (tb / 2)), -d0(ne))]
        aggiunti = 0
        for pa_, na_, pb_, nb_ in coppie:
            fa = self._asm_face_at(iid, pa_, na_)
            fb = self._asm_face_at(iidb, pb_, nb_)
            if fa is None or fb is None:
                continue
            mid = self.asm.new_id('M', {m['id'] for m in self.asm.mates})
            self.asm.mates.append({'id': mid, 'type': 'faccia', 'a': fb, 'b': fa, 'offset': c, 'flip': False})
            aggiunti += 1
        self._asm_reload()
        self.asm_dirty = True
        self.scene_version += 1
        extra = f' {aggiunti} accoppiamenti tengono le linguette nelle asole.' if aggiunti else ''
        return _ok(state=self.state(), message=f'{n} linguette su {ia["name"]} e {n} asole su {ib["name"]} (salvati i due '
                   'file dei pezzi; resta la copia .bak).' + extra)

    def _asm_face_at(self, iid, punto, normale):
        """La faccia piana dell'istanza che passa per il punto (nel mondo) con quella normale: riferimento per un
        accoppiamento, o None."""
        import build123d as bd
        from cad_engine.topology.naming import _faces_of
        i = self.asm.instance(iid)
        part = self.asm_parts[i['file']]
        R, T = np.array(i['R']), np.array(i['T'])
        loc = R.T @ (np.asarray(punto) - T)
        nloc = R.T @ np.asarray(normale)
        nloc = nloc / np.linalg.norm(nloc)
        meglio = None
        for f in _faces_of(part.shape):
            inf = A.face_info(part, f)
            if inf['kind'] != 'piana' or np.dot(inf['n'], nloc) < 0.999:
                continue
            if abs(np.dot(loc - np.array(inf['p']), nloc)) > 1e-3:
                continue
            d = bd.Face(f).distance_to(bd.Vector(*loc))
            if d < 1.0 and (meglio is None or d < meglio[0]):
                meglio = (d, inf)
        return {'inst': iid, **meglio[1]} if meglio else None

    def libreria_catalogo(self) -> dict:
        from app import libreria
        return {'ok': True, 'catalogo': libreria.CATALOGO}

    @_in_assieme
    def asm_insert_libreria(self, tipo: str, misura: str, lunghezza=None, foro: dict | None = None) -> dict:
        """Un pezzo della libreria (viti, dadi, rondelle, rivetti) nell'assieme. Se foro è un foro cliccato, ci va
        dentro (foro su foro: l'asse; la posizione lungo il foro si sistema con «Faccia su faccia»)."""
        from app import libreria
        try:
            f = libreria.crea(tipo, misura, lunghezza or None)
        except ValueError as ex:
            return {'ok': False, 'message': str(ex)}
        r = self.asm_insert(str(f))
        if not r.get('ok'):
            return r
        nuovo = self.asm.instances[-1]['id']
        msg = f'{libreria.descrizione(tipo, misura, lunghezza or None)}: inserita'
        if foro and foro.get('inst') and foro.get('face') is not None:
            try:
                fr = self._asm_face(foro['inst'], foro['face'])
            except A.AssemblyError:
                fr = None
            seduta = self._siedi_nel_cono(foro, fr, nuovo) if tipo == 'vite_tspei' and fr else None
            if seduta:
                r, fr = seduta, None
                msg += ' seduta nella svasatura (cono su cono)'
            if fr and fr['kind'] == 'cilindrica':
                from cad_engine.topology.naming import _faces_of
                part = self.asm_parts[self.asm.instance(nuovo)['file']]
                cil = [k for k, ff in enumerate(_faces_of(part.shape)) if A.face_info(part, ff)['kind'] == 'cilindrica']
                if cil:
                    r2 = self.asm_add_mate('asse', {'inst': foro['inst'], 'face': foro['face']}, {'inst': nuovo, 'face': cil[0]})
                    if r2.get('ok'):
                        r = r2
                        msg += ' nel foro (per l’altezza: «Faccia su faccia» sotto la testa)'
        r['message'] = msg + '.'
        r['select'] = nuovo
        return r

    # ------------------------------------------------------------ viteria a quantità (28/10)
    # «non stare lì a farlo una alla volta ogni volta»: in tutti i fori uguali del pezzo cliccato (ogni vite nel suo
    # foro e appoggiata sotto la testa, dal lato da cui guardi), o N pezzi affiancati; un solo passo di Annulla.
    def _fori_uguali(self, inst: str, face: int) -> list:
        """I fori del pezzo con lo stesso diametro e la stessa direzione del foro cliccato (quello per primo)."""
        from cad_engine.topology.naming import _faces_of
        part = self.asm_parts[self.asm.instance(inst)['file']]
        facce = list(_faces_of(part.shape))
        f0 = A.face_info(part, facce[int(face)])
        if f0['kind'] != 'cilindrica':
            return [{'inst': inst, 'face': int(face)}]
        d0 = np.array(f0['n'])
        perp = lambda p: np.array(p) - d0 * np.dot(np.array(p), d0)  # noqa: E731 - il punto dell'asse, tolto lo spessore
        assi, out = [perp(f0['p'])], [{'inst': inst, 'face': int(face)}]
        for k, f in enumerate(facce):
            inf = A.face_info(part, f)
            if inf['kind'] != 'cilindrica' or abs(inf['r'] - f0['r']) > 1e-4 or abs(abs(float(np.dot(inf['n'], d0))) - 1) > 1e-6:
                continue
            q = perp(inf['p'])
            if any(np.linalg.norm(q - a) < 1e-3 for a in assi):
                continue
            assi.append(q)
            out.append({'inst': inst, 'face': k})
        return out

    def asm_fori_uguali(self, inst: str, face: int) -> dict:
        try:
            return {'ok': True, 'n': len(self._fori_uguali(inst, face))}
        except Exception:  # noqa: BLE001 - è solo un conteggio per la finestra
            return {'ok': True, 'n': 1}

    def _appoggia_testa(self, foro: dict, vite: str, verso=None) -> bool:
        """La vite (asse Y, sotto della testa a y = 0) appoggiata sulla faccia dove si apre il foro: quella girata
        verso chi guarda (verso: la direzione verso la camera, nel mondo)."""
        import build123d as bd
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from OCP.GeomAbs import GeomAbs_Plane
        from OCP.gp import gp_Pnt

        from cad_engine.topology.naming import _faces_of
        ip = self.asm.instance(foro['inst'])
        parte = self.asm_parts[ip['file']]
        facce = list(_faces_of(parte.shape))
        fc = facce[int(foro['face'])]
        ad = BRepAdaptor_Surface(fc)
        ax = ad.Cylinder().Axis()
        o = np.array([ax.Location().X(), ax.Location().Y(), ax.Location().Z()])
        d = np.array([ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()])
        R = ad.Cylinder().Radius()
        capi = [o + d * ad.FirstVParameter(), o + d * ad.LastVParameter()]
        Rm = np.array(ip['R'], dtype=float)
        v = np.array(verso if verso else [0, 0, 1], dtype=float)
        scelte = []
        for k, f in enumerate(facce):
            s2 = BRepAdaptor_Surface(f)
            if s2.GetType() != GeomAbs_Plane:
                continue
            pl = s2.Plane()
            n = np.array([pl.Axis().Direction().X(), pl.Axis().Direction().Y(), pl.Axis().Direction().Z()])
            p0 = np.array([pl.Location().X(), pl.Location().Y(), pl.Location().Z()])
            if abs(abs(float(np.dot(n, d))) - 1) > 1e-6:
                continue
            for c in capi:
                if abs(float(np.dot(c - p0, n))) > 1e-3:
                    continue
                dd = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(*c)).Vertex(), f)
                if dd.IsDone() and dd.Value() < R + 0.05:          # la faccia attorno al foro (il centro dista R)
                    nn = bd.Face(f).normal_at(bd.Vector(*c))
                    scelte.append((float(np.dot(Rm @ np.array([nn.X, nn.Y, nn.Z]), v)), k))
        if not scelte:
            return False
        k_pezzo = max(scelte)[1]
        # il pacco (28/10): se sopra c'è un altro pezzo col foro allineato (la staffa sulla piastra, una rondella),
        # la vite appoggia sull'ultimo pezzo in cima, non dentro quello di mezzo
        T = np.array(ip['T'], dtype=float)
        fk = BRepAdaptor_Surface(facce[k_pezzo]).Plane()
        nk = bd.Face(facce[k_pezzo]).normal_at(bd.Vector(*capi[0]))
        su = Rm @ np.array([nk.X, nk.Y, nk.Z])                     # verso fuori dalla faccia, nel mondo
        asse_w = Rm @ o + T
        p0 = Rm @ np.array([fk.Location().X(), fk.Location().Y(), fk.Location().Z()]) + T
        h = float(np.dot(p0 - asse_w, su))                         # la quota della faccia lungo «su»
        dove = (foro['inst'], k_pezzo)
        visti = {foro['inst']}
        for _ in range(8):
            sopra = self._faccia_del_pacco(asse_w, su, h, R, visti)
            if not sopra:
                break
            dove, h = sopra[0], sopra[1]
            visti.add(dove[0])
        vp = self.asm_parts[self.asm.instance(vite)['file']]
        sotto = [(bd.Face(f).area, k) for k, f in enumerate(_faces_of(vp.shape))
                 if A.face_info(vp, f)['kind'] == 'piana' and abs(A.face_info(vp, f)['n'][1] + 1) < 1e-6
                 and abs(A.face_info(vp, f)['p'][1]) < 1e-6]
        if not sotto:
            return False
        r = self.asm_add_mate('faccia', {'inst': dove[0], 'face': dove[1]}, {'inst': vite, 'face': max(sotto)[1]}, 0)
        return bool(r.get('ok'))

    def _faccia_del_pacco(self, asse_w, su, h, R, visti):
        """Sopra la faccia a quota h (lungo «su», dall'asse del foro): un altro pezzo appoggiato lì (una sua faccia piana
        girata verso il basso a quella quota, col foro attorno all'asse) e la sua faccia di sopra. ((inst, faccia), quota)."""
        import build123d as bd
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from OCP.GeomAbs import GeomAbs_Plane
        from OCP.gp import gp_Pnt

        from cad_engine.topology.naming import _faces_of
        for i in self.asm.instances:
            if i['id'] in visti or i['file'] not in self.asm_parts:
                continue
            Rm, T = np.array(i['R'], dtype=float), np.array(i['T'], dtype=float)
            facce = list(_faces_of(self.asm_parts[i['file']].shape))
            sotto, sopra = False, []
            for k, f in enumerate(facce):
                ad = BRepAdaptor_Surface(f)
                if ad.GetType() != GeomAbs_Plane:
                    continue
                pl = ad.Plane()
                p0 = Rm @ np.array([pl.Location().X(), pl.Location().Y(), pl.Location().Z()]) + T
                c = asse_w + su * float(np.dot(p0 - asse_w, su))       # dove l'asse buca il piano della faccia
                cl = Rm.T @ (c - T)
                nn = bd.Face(f).normal_at(bd.Vector(*cl))
                n = Rm @ np.array([nn.X, nn.Y, nn.Z])
                if abs(abs(float(np.dot(n, su))) - 1) > 1e-6:
                    continue
                dd = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(*cl)).Vertex(), f)
                if not dd.IsDone() or dd.Value() > R + 0.05:            # la faccia non sta attorno all'asse
                    continue
                q = float(np.dot(p0 - asse_w, su))
                if np.dot(n, su) < 0 and abs(q - h) < 0.05:
                    sotto = True                                      # appoggia sulla faccia di prima
                elif np.dot(n, su) > 0 and q > h + 1e-3:
                    sopra.append((q, k))
            if sotto and sopra:
                q, k = min(sopra)
                return (i['id'], k), q
        return None

    def asm_insert_viteria(self, tipo: str, misura: str, lunghezza=None, foro: dict | None = None, opz: dict | None = None) -> dict:
        """opz: {'tutti': in tutti i fori uguali, 'quante': senza foro quante, 'appoggia': sotto la testa, 'verso': [x,y,z]}."""
        from app import libreria
        opz = opz or {}
        n0 = len(self.asm_undo)
        prima = self.asm.to_dict()

        def indietro(r):
            self.asm.__dict__.update(A.Assembly.from_dict(prima, self.asm.path).__dict__)
            del self.asm_undo[n0:]
            self._asm_reload()
            self.scene_version += 1
            return {**r, 'state': self.state()}
        try:
            fori = (self._fori_uguali(foro['inst'], foro['face']) if opz.get('tutti') else [foro]) if foro else []
        except Exception:  # noqa: BLE001
            fori = [foro] if foro else []
        try:
            quante = max(1, min(200, int(float(str(opz.get('quante') or 1).replace(',', '.')))))
        except ValueError:
            return {'ok': False, 'message': 'Quante: scrivi un numero.'}
        messi, appoggiate = [], 0
        for k in range(len(fori) or quante):
            fo = fori[k] if fori else None
            r = self.asm_insert_libreria(tipo, misura, lunghezza, fo)
            if not r.get('ok'):
                return indietro(r)
            messi.append(r['select'])
            if fo and opz.get('appoggia', True) and tipo in ('vite_tcei', 'vite_te', 'rivetto', 'inserto') \
                    and 'nel foro' in (r.get('message') or ''):
                try:
                    appoggiate += self._appoggia_testa(fo, r['select'], opz.get('verso'))
                except Exception:  # noqa: BLE001 - se non si appoggia resta nel foro: si sistema a mano
                    pass
        # tutto quello che è stato fatto: un solo passo di Annulla
        nome = libreria.descrizione(tipo, misura, lunghezza or None)
        del self.asm_undo[n0:]
        self.asm_undo.append((f'{len(messi)} × {nome}', prima))
        self.asm_redo.clear()
        self.asm_dirty = True
        msg = f'{len(messi)} × {nome}'
        if fori:
            msg += f' in {len(fori)} {"foro" if len(fori) == 1 else "fori"}'
            if appoggiate:
                msg += f', {"appoggiata" if appoggiate == 1 else f"{appoggiate} appoggiate"} sotto la testa'
        return {'ok': True, 'state': self.state(), 'select': messi[0], 'message': msg + '.'}

    def _siedi_nel_cono(self, foro, fr, nuovo):
        """La vite a testa svasata nel foro cliccato: la svasatura (il cono coassiale al foro, o il cono cliccato) con la
        testa conica della vite. Il risultato dell'accoppiamento, o None se il foro non è svasato."""
        from cad_engine.topology.naming import _faces_of
        parte = self.asm_parts[self.asm.instance(foro['inst'])['file']]
        facce = list(_faces_of(parte.shape))
        k_sva = None
        if fr['kind'] == 'conica':
            k_sva = int(foro['face'])
        elif fr['kind'] == 'cilindrica':
            p, n = np.array(fr['p']), np.array(fr['n'])
            for k, f in enumerate(facce):
                inf = A.face_info(parte, f)
                if inf['kind'] != 'conica':
                    continue
                v = np.array(inf['p']) - p
                if abs(abs(np.dot(inf['n'], n)) - 1) < 1e-6 and np.linalg.norm(v - n * np.dot(v, n)) < 1e-3:
                    k_sva = k
                    break
        if k_sva is None:
            return None
        vite = self.asm_parts[self.asm.instance(nuovo)['file']]
        import build123d as bd
        coni = [(bd.Face(f).area, k) for k, f in enumerate(_faces_of(vite.shape)) if A.face_info(vite, f)['kind'] == 'conica']
        if not coni:
            return None
        k_testa = max(coni)[1]                       # la testa: il cono più grande (la punta smussata è un cono piccolo)
        r = self.asm_add_mate('cono', {'inst': foro['inst'], 'face': k_sva}, {'inst': nuovo, 'face': k_testa})
        return r if r.get('ok') else None

    @_in_assieme
    def asm_set_finitura(self, iid: str, campi: dict | None) -> dict:
        """La finitura del pezzo (grezzo, zincato, inox, verniciato RAL): si scrive nel file del pezzo, vale per tutte
        le copie; colora il pezzo nel 3D e va in distinta."""
        from cad_engine import finiture, project_io
        i = self.asm.instance(iid)
        tipo = (campi or {}).get('tipo') or 'grezzo'
        if tipo not in finiture.TIPI:
            return {'ok': False, 'message': f'Finitura «{tipo}» sconosciuta.'}
        ral = str((campi or {}).get('ral') or '').replace('RAL', '').strip()
        if tipo == 'verniciato' and not ral:
            return {'ok': False, 'message': 'Scrivi il colore RAL (es. 7035).'}
        try:
            doc = project_io.load(i['file'])
            if tipo == 'grezzo':
                doc.meta.pop('finitura', None)
            else:
                doc.meta['finitura'] = {'tipo': tipo, **({'ral': ral} if tipo == 'verniciato' else {})}
            project_io.save(doc, i['file'])
        except SteelCADError as ex:
            return {'ok': False, 'message': ex.message, 'code': ex.code}
        self._asm_reload()
        r = self._asm_change('Finitura', lambda: {'select': iid})
        if r.get('ok'):
            r['message'] = f'«{Path(i["file"]).stem}»: {finiture.testo(doc.meta.get("finitura"))}.'
        return r

    @_in_assieme
    def asm_set_acquisto(self, iid: str, campi: dict | None) -> dict:
        """Il pezzo di questa copia è da comprare (guide, viti, punte…): descrizione, codice, fornitore. Si scrive nel
        file del pezzo (vale per tutte le copie e per tutti gli assiemi). None = torna un pezzo da fare."""
        from cad_engine import project_io
        try:
            i = self.asm.instance(iid)
            doc = project_io.load(i['file'])
            if campi is None:
                doc.meta.pop('acquisto', None)
            else:
                v = {k: str(campi.get(k) or '').strip() for k in ('descrizione', 'codice', 'fornitore')}
                if not v['descrizione']:
                    v['descrizione'] = doc.meta.get('name') or Path(i['file']).stem
                doc.meta['acquisto'] = v
            project_io.save(doc, i['file'])
        except SteelCADError as ex:
            return {'ok': False, 'message': ex.message, 'code': ex.code}
        self._asm_reload()
        r = self._asm_change('Da acquistare' if campi is not None else 'Da fare', lambda: {'select': iid})
        if r.get('ok'):
            r['message'] = (f'«{Path(i["file"]).stem}» è da acquistare: in distinta con codice e fornitore, niente DXF.'
                            if campi is not None else f'«{Path(i["file"]).stem}» torna un pezzo da fare.')
        return r

    def _righe_distinta(self) -> list:
        """La distinta per l'Excel: una riga per pezzo, con quello che serve a chi produce e a chi compra."""
        from cad_engine import finiture
        out = []
        for k, r in enumerate(A.bom(self.asm, self.asm_parts), 1):
            acq = r.get('acquisto')
            out.append({'pos': k, 'tipo': 'Acquisto' if acq else 'Produzione',
                        'descrizione': (acq or {}).get('descrizione') or r['name'], 'codice': (acq or {}).get('codice', ''),
                        'fornitore': (acq or {}).get('fornitore', ''), 'qty': r['qty'], 'file': Path(r['file']).name,
                        'materiale': '' if acq else r['material'], 'spessore': None if acq else r['thickness'],
                        'sviluppo': None if acq or not r['flat'] else r['flat'], 'kg': r['mass_kg'], 'kg_tot': r['mass_tot'],
                        'finitura': '' if acq else finiture.testo(r.get('finitura'))})
        return out

    @_in_assieme
    def asm_export_bom(self, path: str) -> dict:
        """La distinta materiali in Excel: tutto l'assieme, gli acquisti da ordinare, la lamiera da tagliare."""
        from cad_engine.exporters import xlsx
        try:
            righe = self._righe_distinta()
            tutto = [['Pos.', 'Tipo', 'Descrizione', 'Codice', 'Fornitore', 'Q.tà', 'Materiale', 'Spessore mm',
                      'Sviluppo mm', 'Finitura', 'Peso cad. kg', 'Peso tot. kg', 'File']]
            for r in righe:
                tutto.append([r['pos'], r['tipo'], r['descrizione'], r['codice'], r['fornitore'], r['qty'], r['materiale'],
                              r['spessore'], ' × '.join(fmt_mm(round(v, 1)) for v in r['sviluppo']) if r['sviluppo'] else '',
                              r['finitura'], r['kg'], r['kg_tot'], r['file']])
            tutto += [[], ['', '', 'Totale', '', '', sum(r['qty'] for r in righe), '', None, '', '', None,
                           sum(r['kg_tot'] for r in righe)]]
            acq = [r for r in righe if r['tipo'] == 'Acquisto']
            ordine = [['Pos.', 'Descrizione', 'Codice', 'Fornitore', 'Q.tà', 'Ordinato', 'Note']]
            ordine += [[r['pos'], r['descrizione'], r['codice'], r['fornitore'], r['qty'], '', ''] for r in acq]
            gruppi: dict = {}
            for r in righe:
                if r['tipo'] == 'Produzione' and r['sviluppo']:
                    g = gruppi.setdefault((r['materiale'], r['spessore']), {'pezzi': 0, 'm2': 0.0, 'kg': 0.0, 'nomi': []})
                    g['pezzi'] += r['qty']
                    g['m2'] += r['sviluppo'][0] * r['sviluppo'][1] / 1e6 * r['qty']
                    g['kg'] += r['kg_tot']
                    g['nomi'].append(f'{r["qty"]}× {r["descrizione"]}')
            lamiera = [['Materiale', 'Spessore mm', 'Pezzi', 'Sviluppi m² (ingombro)', 'Peso kg', 'Pezzi']]
            lamiera += [[m, t, g['pezzi'], g['m2'], g['kg'], ', '.join(g['nomi'])]
                        for (m, t), g in sorted(gruppi.items(), key=lambda x: (str(x[0][0]), x[0][1] or 0))]
            xlsx.scrivi(path, [('Distinta', tutto, [6, 12, 46, 18, 18, 7, 12, 12, 16, 26, 13, 13, 34], [0]),
                               ('Da acquistare', ordine, [6, 50, 20, 22, 7, 11, 30], [0]),
                               ('Lamiera da tagliare', lamiera, [12, 13, 8, 22, 11, 80], [0])])
        except Exception as ex:  # noqa: BLE001
            return {'ok': False, 'message': f'La distinta non si salva: {ex}'}
        return {'ok': True, 'path': str(path),
                'message': f'Distinta salvata: {len(righe)} righe, {len(acq)} da acquistare ({Path(path).name}).'}

    @_in_assieme
    def asm_export_step(self, path: str) -> dict:
        import build123d as bd
        forme = [A.placed_shape(self.asm_parts[i['file']], i['R'], i['T']) for i in self.asm.instances if i['file'] in self.asm_parts]
        if not forme:
            return {'ok': False, 'message': 'L’assieme è vuoto.'}
        if not Path(path).parent.is_dir():
            return {'ok': False, 'message': f'La cartella {Path(path).parent} non c’è: scegline un’altra.'}
        ok = bd.export_step(bd.Compound(children=forme), path)
        if ok is False or not Path(path).is_file() or Path(path).stat().st_size == 0:
            return {'ok': False, 'message': 'Il file STEP non si è scritto: forse è aperto in un altro programma.'}
        return _ok(message=f'STEP dell’assieme salvato: {len(forme)} pezzi.', path=path)

    # ------------------------------------------------------------------ aprire un pezzo e tornare
    def asm_open_part(self, iid: str) -> dict:
        if self.asm is None:
            return {'ok': False, 'message': 'Non c’è un assieme aperto.'}
        try:
            i = self.asm.instance(iid)
        except SteelCADError as ex:
            return {'ok': False, 'message': ex.message}
        altri = [(j['file'], j['R'], j['T']) for j in self.asm.instances if j['id'] != iid]
        return self._apri_nel_contesto(i['file'], i['R'], i['T'], altri)

    def _apri_nel_contesto(self, file, R, T, altri) -> dict:
        """Apre un pezzo dell'assieme per modificarlo, con gli altri pezzi attorno in trasparenza (il contesto)."""
        ritorno = (self.asm, self.path, self.asm_undo, self.asm_redo, self.asm_dirty)
        self.asm = None
        r = self.open(file)
        if not r['ok']:
            self.asm, self.path, self.asm_undo, self.asm_redo, self.asm_dirty = ritorno
            return r
        self._asm_ritorno = ritorno
        self._contesto = {'R': [list(map(float, q)) for q in R], 'T': [float(q) for q in T], 'altri': altri}
        self.scene_version += 1
        r['state'] = self.state()
        return r

    @_in_assieme
    def asm_new_part(self, iid: str, face_index, nome: str = '') -> dict:
        """Pezzo nuovo disegnato nell'assieme (21/10, Stefano: «se devo collegare due pezzi con una lamiera»): lo sketch
        sta sul piano della faccia cliccata, con in arancio i bordi di tutti i pezzi che stanno su quel piano (anche
        quelli dell'altro pezzo, per agganciarsi). Il pezzo è un file suo nella cartella dell'assieme; tornando
        all'assieme si salva e si monta da solo al suo posto."""
        import build123d as bd
        from types import SimpleNamespace

        from app import sketch_border
        from cad_engine import project_io, templates
        try:
            if self.path is None:
                raise SteelCADError('Salva prima l’assieme: il pezzo nuovo va nella sua cartella.', code='salva')
            f = self._asm_face(iid, face_index)
            if f['kind'] != 'piana':
                raise SteelCADError('Scegli una faccia piana: il pezzo nuovo si disegna sul suo piano.', code='faccia')
            i = self.asm.instance(iid)
            R, T = np.array(i['R'], dtype=float), np.array(i['T'], dtype=float)
            P = R @ np.array(f['p'], dtype=float) + T
            N = R @ np.array(f['n'], dtype=float)
            N = N / np.linalg.norm(N)
            if abs(N[2]) < 0.9:
                # faccia in piedi (una parete): nello sketch il «su» è il su vero
                y = np.array([0, 0, 1.0]) - N * N[2]
                y = y / np.linalg.norm(y)
                x = np.cross(y, N)
            else:
                a = np.array([1.0, 0, 0]) if abs(N[0]) < 0.9 else np.array([0, 1.0, 0])
                x = a - N * (a @ N)
                x = x / np.linalg.norm(x)
                y = np.cross(N, x)
            nome = (nome or '').strip() or 'Pezzo nuovo'
            cartella = Path(self.path).parent
            p = cartella / f'{nome}.steelcad'
            k = 2
            while p.exists():
                p = cartella / f'{nome} {k}.steelcad'
                k += 1
            materiale = self.asm_parts[i['file']].doc.material if i['file'] in self.asm_parts else 'S235'
            doc = templates.da_zero(p.stem, materiale)
            sk = next(x for x in doc.features if hasattr(x, 'entities'))
            dove = self.asm_parts[i['file']].doc.describe_face(f['name']) if f.get('name') and i['file'] in self.asm_parts else 'la faccia'
            dove = re.sub(r' di "[^"]*"$', '', dove)                    # «la faccia finale di "Piastra"» → «la faccia finale»
            dove = re.sub(r'^(la|il|lo|l’) ', '', dove)
            sk.name = f'Contorno sul piano {"della" if dove.startswith("faccia") else "di"} {dove} di {i["name"]}'
            piano = bd.Plane(origin=tuple(P), x_dir=tuple(x), z_dir=tuple(N))
            bordi = 0
            for j in self.asm.instances:
                pp = self.asm_parts.get(j['file'])
                if pp is None:
                    continue
                mondo = A.placed_shape(pp, j['R'], j['T'])
                bordi += sketch_border.project_edges(sk, SimpleNamespace(shape=mondo.wrapped), None, piano, entro=0.5)
            project_io.save(doc, p)
        except SteelCADError as ex:
            return {'ok': False, 'message': ex.message, 'code': ex.code}
        Rn = np.column_stack([x, y, N])
        altri = [(j['file'], j['R'], j['T']) for j in self.asm.instances]
        r = self._apri_nel_contesto(str(p), Rn.tolist(), P.tolist(), altri)
        if not r.get('ok'):
            return r
        self._asm_nuovo = {'file': str(p), 'R': Rn.tolist(), 'T': P.tolist(), 'nome': p.stem}
        r['sketch'] = sk.id
        r['message'] = (f'Pezzo nuovo «{p.stem}» sul piano della faccia: in arancio i bordi dei pezzi che ci stanno '
                        f'({bordi}). Disegna, crea la lamiera, poi «← Assieme»: si monta da solo.')
        return r

    def asm_back(self) -> dict:
        rit = getattr(self, '_asm_ritorno', None)
        if not rit:
            return {'ok': False, 'message': 'Non c’è un assieme da cui sei arrivato.'}
        nuovo = getattr(self, '_asm_nuovo', None)
        if self.history.dirty and nuovo:
            r = self.save()                              # il pezzo nuovo nato nell'assieme si salva da solo
            if not r.get('ok'):
                return r
        if self.history.dirty:
            return {'ok': False, 'code': 'non_salvato', 'message': 'Salva il pezzo prima di tornare all’assieme (l’assieme '
                    'legge il file salvato).'}
        ha_corpo = self.result.body is not None or bool(self.result.structures)
        self.asm, self.path, self.asm_undo, self.asm_redo, self.asm_dirty = rit
        self._asm_ritorno = None
        self._contesto = None
        self._asm_nuovo = None
        self._asm_reload()
        self.scene_version += 1
        if nuovo and not ha_corpo:
            return _ok(state=self.state(), message=f'«{nuovo["nome"]}» è ancora vuoto: non l’ho messo nell’assieme '
                       '(il file resta nella cartella).')
        if nuovo:
            def fn():
                iid = self.asm.new_id('I', {i['id'] for i in self.asm.instances})
                self.asm.instances.append({'id': iid, 'file': nuovo['file'], 'name': nuovo['nome'],
                                           'R': nuovo['R'], 'T': nuovo['T']})
                return {'select': iid}
            r = self._asm_change(f'Pezzo nuovo {nuovo["nome"]}', fn)
            if r.get('ok'):
                r['message'] = f'«{nuovo["nome"]}» montato al suo posto nell’assieme.'
            return r
        return _ok(state=self.state())

    # ------------------------------------------------------------------ stato, scena, selezione
    def _asm_state(self) -> dict:
        asm = self.asm
        nomi = {i['id']: i['name'] for i in asm.instances}
        figli = []
        for i in asm.instances:
            st = 'errore' if any(e['id'] == i['id'] for e in self.asm_errors) else ('fisso' if i.get('fixed') else None)
            figli.append({'label': i['name'], 'kind': 'instance', 'ref': i['id'], 'children': [], 'status': st})
        acc = [{'label': f'{m["id"]}: {A.MATE_TYPES[m["type"]]} — {nomi.get(m["a"]["inst"], "?")} / {nomi.get(m["b"]["inst"], "?")}'
                + (f', distanza {fmt_mm(m.get("offset") or 0)}' if m['type'] in ('faccia', 'distanza', 'tangente', 'centra')
                   and m.get('offset') else '')
                + (f', {fmt_mm(round(m.get("angle") or 0, 2))}°' if m['type'] == 'angolo' else '')
                + (' (sospeso)' if m.get('off') else ''),
                'kind': 'mate', 'ref': m['id'], 'children': [], 'status': None} for m in asm.mates]
        if acc:
            figli.append({'label': 'Accoppiamenti', 'kind': 'group', 'ref': None, 'children': acc, 'status': None})
        tree = {'label': asm.name, 'kind': 'assembly', 'ref': None, 'children': figli, 'status': None}
        righe = A.bom(asm, self.asm_parts)
        bom = [{'code': f'P{k + 1}', 'description': (
                    f'Acquisto: {r["acquisto"].get("descrizione") or r["name"]}'
                    + (f' — cod. {r["acquisto"]["codice"]}' if r['acquisto'].get('codice') else '')
                    if r.get('acquisto') else
                    r['name'] + (f', sviluppo {fmt_mm(round(r["flat"][0], 1))} × {fmt_mm(round(r["flat"][1], 1))}' if r['flat'] else '')),
                'qty': r['qty'], 'material': '—' if r.get('acquisto') else r['material'], 'profile': None,
                'thickness_mm': None if r.get('acquisto') else r['thickness'], 'acquisto': bool(r.get('acquisto')),
                'kg_each': r['mass_kg'], 'kg_total': r['mass_tot'], 'file': r['file']} for k, r in enumerate(righe)]
        totale = sum(r['kg_total'] for r in bom)
        nome_pezzo = {r['file']: r['name'] for r in righe}         # il gruppo delle copie nell'albero si chiama come il pezzo
        avvisi = list(getattr(asm, 'warnings', []) or [])
        for f, p in self.asm_parts.items():
            avvisi += [f'{Path(f).stem}: {e}' for e in p.errors]
        # la forma della scena: se non cambia (si è mosso solo qualcosa) l'interfaccia sposta i pezzi che ha già,
        # senza rifarsi mandare tutta la scena (2-3 MB per una cassettiera: era lento riaprire un cassetto)
        forma = '|'.join(f'{i["id"]}:{i["file"]}:{getattr(self.asm_parts.get(i["file"]), "mtime", 0)}' for i in asm.instances)
        pose = {i['id']: [i['R'][0][0], i['R'][0][1], i['R'][0][2], i['T'][0], i['R'][1][0], i['R'][1][1], i['R'][1][2], i['T'][1],
                          i['R'][2][0], i['R'][2][1], i['R'][2][2], i['T'][2], 0, 0, 0, 1] for i in asm.instances}
        return {'mode': 'assembly', 'name': asm.name, 'path': str(self.path) if self.path else None,
                'geo': forma, 'poses': pose,
                'dirty': self.asm_dirty, 'undo': [x[0] for x in self.asm_undo[-1:]], 'redo': [x[0] for x in self.asm_redo[-1:]],
                'tree': tree, 'parameters': [], 'errors': self.asm_errors, 'warnings': avvisi,
                'mancanti': [{'file': f, 'name': Path(f).stem, 'n': sum(1 for i in asm.instances if i['file'] == f)}
                             for f in dict.fromkeys(i['file'] for i in asm.instances) if f not in self.asm_parts],
                'ritrovati': list(getattr(self, 'asm_ritrovati', [])),
                'bom': bom, 'bom_kg': totale, 'cutlist': {'rows': [], 'totals': [], 'pieces': 0, 'kg': 0},
                'saldature': self._asm_saldature(),
                'storia': {'passi': [x[0] for x in self.asm_undo] + [x[0] for x in reversed(self.asm_redo)], 'qui': len(self.asm_undo)},
                'info': {'rebuild_ms': round(getattr(self, 'asm_ms', 0), 1), 'rebuilt': len(self.asm_parts), 'cached': 0,
                         'material': '—'},
                'scene_version': self.scene_version, 'dimensions': [], 'sheet': None,
                'instances': [{'id': i['id'], 'name': i['name'], 'file': i['file'], 'fixed': bool(i.get('fixed')),
                               'pezzo': nome_pezzo.get(i['file'])} for i in asm.instances],
                'mate_types': A.MATE_TYPES, 'can_back': False}

    # ------------------------------------------------------------ saldature nell'assieme (28/10)
    # «ovunque schiaccio mi da solo errori»: nell'assieme lo strumento cercava gli spigoli di un pezzo solo. Qui si
    # salda dove si salda davvero: tra i pezzi. Ogni spigolo cliccato è dello spigolo di una copia (nel pezzo, con il
    # suo riferimento stabile quando c'è, se no la sua linea): la saldatura segue la copia quando si sposta.
    def _spigolo_del_pezzo(self, part, p):
        import build123d as bd
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from OCP.gp import gp_Pnt

        from cad_engine.topology.naming import _edges_of
        v = BRepBuilderAPI_MakeVertex(gp_Pnt(*[float(c) for c in p])).Vertex()
        migliore = None
        for e in _edges_of(part.shape):
            dd = BRepExtrema_DistShapeShape(v, e)
            if dd.IsDone() and (migliore is None or dd.Value() < migliore[0]):
                migliore = (dd.Value(), e)
        if migliore is None or migliore[0] > 1.0:
            raise SteelCADError('Clicca proprio sullo spigolo (si accende).', code='spigolo')
        e = migliore[1]
        voce = {}
        body = getattr(part.result, 'body', None)
        if body is not None:
            try:
                voce['ref'] = body.edge_ref(e)
            except Exception:  # noqa: BLE001 - uno spigolo senza nome (di un tubo, di un taglio): si tiene la linea
                pass
        be = bd.Edge(e)
        n = 2 if be.geom_type == bd.GeomType.LINE else 24
        voce['linea'] = [[p.X, p.Y, p.Z] for p in be.positions([k / (n - 1) for k in range(n)])]
        return voce

    def asm_add_saldatura(self, scelti: list, spec: dict) -> dict:
        """scelti: [{'inst': id della copia, 'p': punto cliccato nelle coordinate del pezzo}]."""
        istanze = {i['id']: i for i in self.asm.instances}
        tratti = []
        try:
            for s in scelti or []:
                i = istanze.get((s or {}).get('inst'))
                part = self.asm_parts.get(i['file']) if i else None
                if part is None:
                    raise SteelCADError('Clicca proprio sullo spigolo di un pezzo (si accende).', code='spigolo')
                t = {'inst': i['id'], **self._spigolo_del_pezzo(part, s['p'])}
                if t not in tratti:
                    tratti.append(t)
        except SteelCADError as ex:
            return {'ok': False, 'code': ex.code, 'message': ex.message}
        if not tratti:
            return {'ok': False, 'code': 'spigolo', 'message': 'Scegli almeno uno spigolo.'}
        tipo = (spec or {}).get('tipo') if (spec or {}).get('tipo') in ('angolo', 'V', 'I') else 'angolo'
        a = str((spec or {}).get('a') or '').strip().replace(',', '.')[:10]
        nome = f'Saldatura {"a" + a if tipo == "angolo" and a else tipo}'.strip()
        self.asm_undo.append((nome, self.asm.to_dict()))
        self.asm_redo.clear()
        self.asm.meta['saldature'] = list(self.asm.meta.get('saldature') or []) + [{'tratti': tratti, 'tipo': tipo, 'a': a}]
        self.asm_dirty = True
        return {'ok': True, 'state': self.state(), 'message': f'{nome} su {len(tratti)} '
                f'{"spigolo" if len(tratti) == 1 else "spigoli"}: i metri sono nella distinta.'}

    def asm_del_saldatura(self, i: int) -> dict:
        lista = list(self.asm.meta.get('saldature') or [])
        if not 0 <= int(i) < len(lista):
            return {'ok': False, 'message': 'Saldatura non trovata.'}
        self.asm_undo.append(('Togli saldatura', self.asm.to_dict()))
        self.asm_redo.clear()
        lista.pop(int(i))
        if lista:
            self.asm.meta['saldature'] = lista
        else:
            self.asm.meta.pop('saldature', None)
        self.asm_dirty = True
        return {'ok': True, 'state': self.state()}

    def _asm_saldature(self) -> list:
        """Come _saldature del pezzo: i tratti al loro posto nell'assieme (per vederli) e i metri."""
        import build123d as bd
        import numpy as np
        istanze = {i['id']: i for i in self.asm.instances}
        out = []
        for k, w in enumerate(self.asm.meta.get('saldature') or []):
            linee, lung, persa = [], 0.0, False
            for t in w.get('tratti') or []:
                i = istanze.get(t.get('inst'))
                part = self.asm_parts.get(i['file']) if i else None
                if part is None:
                    persa = True
                    continue
                punti = None
                body = getattr(part.result, 'body', None)
                if t.get('ref') and body is not None:
                    try:
                        es = body.edges(t['ref'])
                    except Exception:  # noqa: BLE001 - lo spigolo non c'è più: si usa la linea di quando è stato cliccato
                        es = []
                    if es:
                        punti = []
                        for e in es:
                            be = bd.Edge(e)
                            n = 2 if be.geom_type == bd.GeomType.LINE else 24
                            punti.append([[p.X, p.Y, p.Z] for p in be.positions([j / (n - 1) for j in range(n)])])
                    else:
                        persa = True
                if punti is None:
                    punti = [t.get('linea') or []]
                R, T = np.array(i['R'], dtype=float), np.array(i['T'], dtype=float)
                for pl in punti:
                    if len(pl) < 2:
                        continue
                    q = np.array(pl, dtype=float) @ R.T + T
                    lung += float(np.linalg.norm(np.diff(q, axis=0), axis=1).sum())
                    linee.append([float(c) for c in q.ravel()])
            out.append({'i': k, 'tipo': w.get('tipo', 'angolo'), 'a': w.get('a', ''), 'm': lung / 1000, 'linee': linee,
                        'persa': persa, 'spigoli': len(w.get('tratti') or [])})
        return out

    def _asm_scene(self) -> dict:
        objs = []
        for i in self.asm.instances:
            part = self.asm_parts.get(i['file'])
            if part is None:
                continue
            m = A.part_mesh(part)
            R, T = i['R'], i['T']
            mat = [R[0][0], R[0][1], R[0][2], T[0], R[1][0], R[1][1], R[1][2], T[1], R[2][0], R[2][1], R[2][2], T[2], 0, 0, 0, 1]
            facce = [{**f, 'label': f'{i["name"]}: {part.doc.describe_face(f["name"]) if f["name"] else "faccia"}'} for f in m['faces']]
            # le marcature laser del pezzo: tratti come gli spigoli, si muovono con lui
            dati = getattr(part.result.body, 'sheet', None) if part.result.body is not None else None
            segni = [[c for q in sg['pezzo'] for c in q] for sg in (getattr(dati, 'marks', None) or []) if sg.get('pezzo')]
            from cad_engine import finiture
            objs.append({'id': i['id'], 'kind': 'instance', 'name': i['name'], 'matrix': mat,
                         'positions': m['positions'], 'indices': m['indices'], 'faces': facce, 'edges': m['edges'],
                         'marks': segni, 'look': finiture.colore(part.doc.meta.get('finitura'))})
        return {'version': self.scene_version, 'objects': objs, 'nodes': [], 'bend_edges': []}

    def _asm_select(self, obj_id: str, face_index=None) -> dict:
        if obj_id == 'assieme':
            return _ok(selection={'kind': 'assembly', 'id': 'assieme', 'title': self.asm.name,
                                  'rows': [['Pezzi', str(len(self.asm.instances))], ['Accoppiamenti', str(len(self.asm.mates))]]})
        if obj_id.startswith('mate='):
            mid = obj_id[5:]
            m = next((x for x in self.asm.mates if x['id'] == mid), None)
            if m is None:
                return {'ok': False, 'message': 'Accoppiamento non trovato.'}
            nomi = {i['id']: i['name'] for i in self.asm.instances}
            err = A.mate_error(m, {i['id']: (np.array(i['R']), np.array(i['T'])) for i in self.asm.instances}, self.asm_parts, self.asm)
            rows = [['Tipo', A.MATE_TYPES[m['type']]], ['Fermo', nomi.get(m['a']['inst'], '?')], ['Si muove', nomi.get(m['b']['inst'], '?')],
                    ['Scarto', '—' if err is None else f'{err:.4f}']]
            return _ok(selection={'kind': 'mate', 'id': mid, 'title': f'Accoppiamento {mid}', 'rows': rows,
                                  'def': {'type': m['type'], 'offset': m.get('offset') or 0, 'flip': bool(m.get('flip')),
                                          'angle': m.get('angle') or 0,
                                          'off': bool(m.get('off'))}})
        i = self.asm.instance(obj_id)
        part = self.asm_parts.get(i['file'])
        rows = [['File', Path(i['file']).name]]
        if part is not None:
            pr = A.part_props(part)
            rows += [['Materiale', part.doc.material], ['Peso', fmt_kg(pr["mass_kg"])],
                     ['Ingombro', ' × '.join(fmt_mm(round(v, 1)) for v in pr['bbox_mm']['size']) + ' mm']]
        sel = {'kind': 'instance', 'id': obj_id, 'title': i['name'], 'rows': rows, 'fixed': bool(i.get('fixed')),
               'acquisto': (part.doc.meta.get('acquisto') if part is not None else None),
               'finitura': (part.doc.meta.get('finitura') if part is not None else None),
               'T': i['T'], 'mates': [m['id'] for m in self.asm.mates if obj_id in (m['a']['inst'], m['b']['inst'])],
               'movimenti': self._movimenti(obj_id)}
        if face_index is not None and part is not None:
            try:
                f = self._asm_face(obj_id, face_index)
                sel['face'] = {'index': face_index, 'kind': f['kind'], 'name': f['name'],
                               'label': part.doc.describe_face(f['name']) if f['name'] else 'faccia'}
                cont = self._asm_tip_contact(obj_id, face_index)
                if cont:
                    sel['tabs_with'] = self.asm.instance(cont[1])['name']
            except SteelCADError:
                pass
        return _ok(selection=sel)
