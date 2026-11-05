"""Lamiera forata, lato applicazione (05/11): la finestra, l'anteprima leggera, il pannello.

Clic su una faccia piana della lamiera → «Lamiera forata» (nella barra in alto, o tra le azioni della faccia): forma
dei fori, passo, in fila o sfalsata a 60°, margine dai bordi e dalle pieghe. Mentre si scrive, l'anteprima mostra i
fori sulla faccia (solo i contorni, calcolati senza rifare il pezzo: anche 2000 fori si vedono subito) e quanti sono.
«Fai» aggiunge la feature sheet_perforate (cad_engine/sheetmetal/forata.py): un taglio solo, nel pezzo e nello sviluppo.
Si cambia dopo dal pannello (clic su un foro o sulla voce dell'albero).
"""
from __future__ import annotations

from cad_engine import SteelCADError
from cad_engine.sketch import Sketch
from cad_engine.units import fmt_mm

CAMPI = ('forma', 'd', 'lung', 'larg', 'lato', 'verticale', 'px', 'py', 'disposizione', 'margine')
PREDEFINITI = {'forma': 'tondo', 'd': 5, 'lung': 20, 'larg': 5, 'lato': 5, 'verticale': False, 'px': 8, 'py': 8,
               'disposizione': 'sfalsata', 'margine': 10}
NOMI_FORME = {'tondo': 'fori tondi', 'asola': 'asole', 'quadro': 'fori quadri'}


def _err(ex) -> dict:
    return {'ok': False, 'message': getattr(ex, 'message', None) or str(ex), 'code': getattr(ex, 'code', None) or 'forata'}


def _campi(spec: dict) -> dict:
    """I campi della feature dalla finestra: numeri con la virgola, espressioni sui parametri, il resto com'è."""
    from app.service import _number
    out = {}
    for k in CAMPI:
        if k not in spec:
            continue
        v = spec[k]
        if k in ('forma', 'disposizione'):
            out[k] = str(v)
        elif k == 'verticale':
            out[k] = bool(v)
        elif v in (None, ''):
            continue
        else:
            out[k] = _number(v)
    if out.get('forma', 'tondo') not in ('tondo', 'asola', 'quadro'):
        raise SteelCADError(f'Forma «{out["forma"]}» sconosciuta.', code='forata')
    if out.get('disposizione', 'fila') not in ('fila', 'sfalsata'):
        raise SteelCADError(f'Disposizione «{out["disposizione"]}» sconosciuta.', code='forata')
    return out


def frase(info: dict, fdef: dict, px, py, sfalsata: bool) -> str:
    """«1728 fori Ø5, sfalsati a 60°, passo 8 · ponticello 3 mm»."""
    n = info['n']
    cosa = info['foro']
    if cosa.startswith('Ø'):
        cosa = f'{"foro" if n == 1 else "fori"} {cosa}'
    elif cosa.startswith('asole'):
        cosa = ('asola' if n == 1 else 'asole') + cosa[5:]
    else:
        cosa = ('foro quadro' if n == 1 else 'fori quadri') + cosa[6:]
    disp = f'sfalsati a 60°, passo {fmt_mm(round(px, 2))}' if sfalsata else (
        f'in fila, passo {fmt_mm(round(px, 2))}' + (f' × {fmt_mm(round(py, 2))}' if abs(px - py) > 1e-9 else ''))
    return f'{n} {cosa}, {disp} · ponticello {fmt_mm(round(info["ponticello"], 2))} mm'


class ForataMixin:
    # ------------------------------------------------------------------ cosa serve alla finestra
    def _corpo_prima_di(self, fid: str | None):
        """Il pezzo prima della lamiera forata fid (per cambiarla: i suoi fori non devono contare), o quello di adesso."""
        if not fid:
            return self.result.body
        from cad_engine.document import Document
        import copy as _copy
        i = next((k for k, f in enumerate(self.doc.features) if Document._fid(f) == fid), None)
        if i is None:
            raise SteelCADError('Questa lamiera forata non c’è più.', code='forata')
        prova = Document.from_dict(_copy.deepcopy(self.doc.to_dict()))
        prova.features = prova.features[:i]
        prova._cache = self.doc._cache                  # tutto quello prima è già fatto: si riprende dalla memoria
        prova._cache_vecchie = list(getattr(self.doc, '_cache_vecchie', []))
        r = prova.rebuild()
        return r.body

    def _schizzi_sulla_faccia(self, face_name: str, tranne: str | None = None) -> list:
        """Gli sketch disegnati su questa faccia con contorni chiusi e che nessun'altra lavorazione usa: la zona dei fori."""
        usati = {f.get('sketch') for f in self.doc.features if not isinstance(f, Sketch) and f.get('id') != tranne}
        out = []
        for f in self.doc.features:
            if not isinstance(f, Sketch) or f.id in usati or not isinstance(f.plane, dict) or f.plane.get('face') != face_name:
                continue
            fatto = (self.doc._sketch_results or {}).get(f.id)
            if fatto and fatto[1] is not None and fatto[1].faces:
                out.append({'id': f.id, 'nome': f.label(), 'n': len(fatto[1].faces)})
        return out

    def forata_info(self, face_name: str | None = None, fid: str | None = None) -> dict:
        """La faccia per la lamiera forata: nome, misure fuori tutto (vista di fronte), spessore e gli sketch disegnati
        sopra che possono fare da zona."""
        try:
            from cad_engine.sheetmetal import forata as F
            body = self._corpo_prima_di(fid)
            data = getattr(body, 'sheet', None) if body is not None else None
            if data is None:
                return {'ok': False, 'message': 'La lamiera forata si fa su una lamiera: prima crea la lamiera.'}
            face_name = face_name or self.fori_faccia()
            if not face_name or face_name not in body.names:
                return {'ok': False, 'message': 'Clicca una faccia piana della lamiera (sopra, sotto o di una piega).'}
            piano = F.piano_faccia(body, face_name)
            facce = F._facce_sul_piano(body, face_name, piano, '')
            _t, (x0, y0, x1, y1) = F.tratti_della_faccia(facce, piano, solo_esterni=True)
            F.mappa(body, data, face_name, '')            # la faccia deve potersi portare nello sviluppo
            return {'ok': True, 'face': face_name, 'label': self.doc.describe_face(face_name),
                    'outer': [round(x1 - x0, 2), round(y1 - y0, 2)], 'thickness': data.thickness,
                    'schizzi': self._schizzi_sulla_faccia(face_name, fid)}
        except SteelCADError as ex:
            return _err(ex)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    # ------------------------------------------------------------------ anteprima leggera
    def forata_anteprima(self, face_name: str, spec: dict, fid: str | None = None) -> dict:
        """I centri dei fori (nel 3D, sulla faccia) e quanti sono, senza rifare il pezzo: la finestra li disegna come
        contorni sottili. Anche con 2000 fori è un attimo."""
        try:
            from cad_engine.features.base import Context
            from cad_engine.sheetmetal import forata as F
            body = self._corpo_prima_di(fid)
            data = getattr(body, 'sheet', None) if body is not None else None
            if data is None:
                return {'ok': False, 'message': 'Prima serve una lamiera.'}
            fdef = {'id': fid or 'LF', 'type': 'sheet_perforate', **PREDEFINITI, **_campi(spec)}
            ctx = Context(self.doc.resolved_parameters(), body, dict(self.doc._sketch_results or {}),
                          self.doc.describe_face)
            sid = spec.get('sketch') or None
            fdef['face'] = face_name
            fdef['sketch'] = sid
            foro, px, py, sfalsata, margine = F.misure(fdef, ctx)
            face, prof = F.faccia_e_zona(fdef, ctx, body)
            pieni, piano, scartati, _s, _g = F.centri(body, data, face, prof, foro, px, py, sfalsata, margine, fdef['id'])
            F.piani_sviluppo(body, data, face, piano, fdef['id'])
            info = {'n': len(pieni), 'scartati': scartati, 'foro': foro.testo(),
                    'ponticello': F.ponticello(foro, px, py, sfalsata)}
            n = piano.z_dir
            centri = []
            for x, y in pieni:
                p = piano.from_local_coords((x, y)) + n * 0.05      # appena sopra la faccia, se no si confonde
                centri += [round(p.X, 3), round(p.Y, 3), round(p.Z, 3)]
            avvisi = []
            t = data.thickness
            if info['ponticello'] < t - 1e-6:
                avvisi.append(f'Tra un foro e l’altro restano {fmt_mm(round(info["ponticello"], 2))} mm: meno dello '
                              f'spessore ({fmt_mm(t)}), col laser si storce. Allarga il passo.')
            if min(foro.mezzi()) * 2 < t - 1e-6:
                avvisi.append(f'Fori più piccoli dello spessore ({fmt_mm(t)}): il laser li fa male.')
            testo = frase(info, fdef, px, py, sfalsata) if pieni else 'Nella zona non ci sta nessun foro intero.'
            if pieni and scartati:
                testo += f' · {scartati} saltati (non ci stavano interi)'
            return {'ok': bool(pieni), 'n': len(pieni), 'scartati': scartati, 'frase': testo, 'avvisi': avvisi,
                    'message': '' if pieni else 'Nella zona non ci sta nessun foro intero: riduci il margine, il passo o i fori.',
                    'centri': centri, 'x': [piano.x_dir.X, piano.x_dir.Y, piano.x_dir.Z],
                    'y': [piano.y_dir.X, piano.y_dir.Y, piano.y_dir.Z], 'n_dir': [n.X, n.Y, n.Z],
                    'forma': foro.forma, 'a': foro.a, 'b': foro.b, 'verticale': foro.verticale}
        except SteelCADError as ex:
            return _err(ex)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    # ------------------------------------------------------------------ fare e cambiare
    def _messaggio_forata(self, fid: str, cambiata: bool = False) -> str:
        data = getattr(self.result.body, 'sheet', None) if self.result.body is not None else None
        info = (getattr(data, 'forate', None) or {}).get(fid) if data is not None else None
        if not info:
            return 'Lamiera forata cambiata.' if cambiata else 'Lamiera forata fatta.'
        n = info['n']
        m = f'{"Cambiata" if cambiata else "Fatta"} la lamiera forata: {n} {"foro" if n == 1 else "fori"} ({info["foro"]}).'
        if info.get('scartati'):
            m += f' {info["scartati"]} non ci stavano interi e sono saltati.'
        return m

    def forata(self, face_name: str, spec: dict) -> dict:
        """La lamiera forata nuova su questa faccia (un Annulla la toglie tutta)."""
        try:
            campi = _campi(spec)
            if self.result.body is None or face_name not in self.result.body.names:
                raise SteelCADError('Questa faccia non c’è più: clicca di nuovo la faccia.', code='forata')
        except SteelCADError as ex:
            return _err(ex)
        nuovo = {}

        def fn():
            extra = {'sketch': spec['sketch']} if spec.get('sketch') else {}
            nuovo['id'] = self.doc.add_feature('sheet_perforate', 'Lamiera forata', face=face_name,
                                               **{**PREDEFINITI, **campi}, **extra)
        r = self._change('Lamiera forata', fn)
        if r.get('ok'):
            r['message'] = self._messaggio_forata(nuovo['id'])
            r['select'] = f'lf={nuovo["id"]}'
        return r

    def forata_modifica(self, fid: str, spec: dict) -> dict:
        """Cambia una lamiera forata fatta: stesso posto nella storia, misure nuove."""
        try:
            f = self.doc.feature(fid)
            if isinstance(f, Sketch) or f.get('type') != 'sheet_perforate':
                raise SteelCADError('Questa non è una lamiera forata.', code='forata')
            campi = _campi(spec)
        except SteelCADError as ex:
            return _err(ex)

        def fn():
            f.update(campi)
            if 'sketch' in spec:
                if spec.get('sketch'):
                    f['sketch'] = spec['sketch']
                else:
                    f.pop('sketch', None)
        r = self._change('Lamiera forata cambiata', fn)
        if r.get('ok'):
            r['message'] = self._messaggio_forata(fid, cambiata=True)
            r['select'] = f'lf={fid}'
        return r

    def forata_da_modificare(self, fid: str) -> dict:
        """Per riaprire la finestra con com'è adesso."""
        try:
            f = self.doc.feature(fid)
            if isinstance(f, Sketch) or f.get('type') != 'sheet_perforate':
                raise SteelCADError('Questa non è una lamiera forata.', code='forata')
            info = self.forata_info(f.get('face'), fid)
            if not info.get('ok'):
                return info
            spec = {k: f.get(k, PREDEFINITI[k]) for k in CAMPI}
            spec['sketch'] = f.get('sketch') or ''
            return {'ok': True, 'feature': fid, 'face': f.get('face'), 'info': info, 'spec': spec}
        except SteelCADError as ex:
            return _err(ex)

    def _e_forata(self, fid: str) -> bool:
        try:
            f = self.doc.feature(fid)
        except SteelCADError:
            return False
        return not isinstance(f, Sketch) and f.get('type') == 'sheet_perforate'

    def _forata_selection(self, fid: str, faccia: dict | None = None) -> dict:
        """Il pannello di una lamiera forata (clic su un suo foro o sulla voce dell'albero)."""
        f = self.doc.feature(fid)
        data = getattr(self.result.body, 'sheet', None) if self.result.body is not None else None
        info = (getattr(data, 'forate', None) or {}).get(fid) or {}
        sfalsata = f.get('disposizione') == 'sfalsata'
        righe = []
        if info:
            righe.append(['Fori fatti', str(info['n'])])
            if info.get('scartati'):
                righe.append(['Saltati (non ci stavano interi)', str(info['scartati'])])
            righe.append(['Forma', info['foro']])
            righe.append(['Ponticello', f'{fmt_mm(round(info["ponticello"], 2))} mm'])
        righe.append(['Disposizione', 'sfalsata a 60°' if sfalsata else 'in fila'])
        righe.append(['Passo', f'{f.get("px")}' + ('' if sfalsata or f.get('py') in (None, '', f.get('px')) else f' × {f.get("py")}')])
        righe.append(['Margine dai bordi', f'{f.get("margine", 0)} mm'])
        righe.append(['Faccia', self.doc.describe_face(f.get('face', '')) if f.get('face') else ''])
        if f.get('sketch'):
            righe.append(['Zona', f'dentro il disegno {self.doc.sketch(f["sketch"]).label()}'])
        out = {'kind': 'forata', 'feature': fid, 'title': f.get('etichetta') or 'Lamiera forata',
               'n': info.get('n'), 'foro': info.get('foro'), 'rows': righe,
               'highlight': self._face_indices(fid) if self.result.body is not None else []}
        if faccia:
            out['face'] = faccia
        return out
