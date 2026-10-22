"""Strutture in tubolare, lato applicazione, col flusso nuovo (22/10, tela «SteelCAD tubi: flusso nuovo»):
nomi da officina al posto delle sigle, angoli scelti col disegnino («A 45°», «Passa la gamba»…) anche su tutti
gli angoli uguali, traverso tra due tubi cliccati, tubo nuovo con le frecce (Su, Giù, Avanti…), «Fai i tubi»
dalla sagoma disegnata con «ripeti dietro» e «collega». Misure sempre fuori tutto.
"""
from __future__ import annotations

import build123d as bd

from cad_engine import SteelCADError
from cad_engine.profiles import parse
from cad_engine.sketch import Sketch
from cad_engine.structures.frame import _classe
from cad_engine.structures.nomi import nome_punto, nomi_aste
from cad_engine.units import fmt_mm

# le frecce come le dice l'officina, guardando la struttura di fronte
FRECCE = {'destra': 'X+', 'sinistra': 'X-', 'dietro': 'Y+', 'avanti': 'Y-', 'su': 'Z+', 'giu': 'Z-'}
PAROLA = {'verticali': 'la gamba', 'x': 'il traverso', 'y': 'il fianco'}


def _tocca_dir(m, p) -> bd.Vector:
    """Da che parte parte il tubo m dal punto p (un suo estremo); a metà tubo: nessuna direzione sola."""
    if (m.start - p).length < 1e-6:
        return m.w
    if (m.end - p).length < 1e-6:
        return -m.w
    return bd.Vector(0, 0, 0)


def _ok(**kw):
    return {'ok': True, **kw}


def _err(msg, code='tubi'):
    return {'ok': False, 'code': code, 'message': msg}


def _num(v, nome):
    try:
        x = float(str(v).replace(',', '.'))
    except (TypeError, ValueError):
        raise SteelCADError(f'{nome}: «{v}» non è un numero.', code='misura') from None
    return x


class StruttureMixin:
    # ------------------------------------------------------------------ letture
    def _st(self, st_id):
        st = next((s for s in self.result.structures if s.id == st_id), None)
        if st is None:
            raise SteelCADError('La struttura non c’è più.', code='struttura')
        return st

    def nomi_tubi(self, st) -> dict:
        return nomi_aste(st.members)

    def _punto_di(self, st, p: bd.Vector):
        """La chiave del nodo che sta in p (estremo di un'asta)."""
        for k, v in (st.nodes or {}).items():
            if (bd.Vector(*v['xyz']) - p).length < 1e-6:
                return k
        return None

    def _limiti(self, st):
        b = bd.Compound([m.solid for m in st.members]).bounding_box() if st.members else None
        return b

    def struttura_cosa_fare(self, st_id: str) -> dict:
        """Per il pannello della struttura appena creata: fuori tutto, tubi, peso e «Cosa puoi fare adesso»."""
        st = self._st(st_id)
        from cad_engine.structures import cut_list
        cl = cut_list([st])
        b = self._limiti(st)
        fuori = [round(v) for v in (b.size.X, b.size.Y, b.size.Z)] if b else []
        return {'fuori_tutto': fuori, 'tubi': cl['pieces'], 'misure': len(cl['rows']), 'kg': round(cl['kg'], 1),
                'esterno': bool(self.doc.feature(st_id).get('esterno'))}

    def tubo_info(self, st, m) -> dict:
        """Il tubo cliccato, in parole d'officina."""
        nomi = self.nomi_tubi(st)
        gruppo = [x for x in st.members if x.group == m.group and m.group]
        return {'nome': nomi[m.id], 'contro': [nomi[i] for i in m.contro if i in nomi],
                'gruppo_n': len(gruppo), 'verticale': abs(m.w.Z) > 0.95}

    def _parola(self, nomi, m):
        tipo = nomi[m.id].split()[0].lower()
        return ('la' if tipo in ('gamba', 'sbarra', 'diagonale', 'mensola') else 'il'), tipo

    def _in_linea(self, aste, p):
        """Coppie di tubi che finiscono qui uno di seguito all'altro (lo stesso traverso spezzato in due)."""
        out = []
        for a_ in aste:
            for b_ in aste:
                if a_.id < b_.id and _tocca_dir(a_, p).dot(_tocca_dir(b_, p)) < -0.999:
                    out.append((a_, b_))
        return out

    @staticmethod
    def _chi_passa(aste):
        """Dividendo un tubo lungo, passa quello in piedi (la gamba), se c'è."""
        return next((m for m in aste if _classe(m.w) == 'verticali'), aste[0])

    def _passanti(self, st, p):
        """I tubi su cui l'angolo sta a metà (un traverso unico con la gamba sotto)."""
        out = []
        for m in st.members:
            w = m.end - m.start
            t = (p - m.start).dot(w) / w.length ** 2
            if 1e-6 < t < 1 - 1e-6 and (m.start + w * t - p).length < 1e-6:
                out.append(m)
        return out

    def angolo_info(self, st_id: str, key: str) -> dict:
        """Le scelte per l'angolo cliccato, ognuna col suo disegnino, e quanti angoli sono uguali a lui.
        Due tubi in linea qui: «Passa il traverso, tubo unico» li fa diventare uno; un tubo lungo che passa di qui:
        «Passa la gamba» lo divide in due (23/10, Stefano: «avrebbe più senso il tubo unico lungo sopra»)."""
        try:
            st = self._st(st_id)
            info = st.nodes[key]
        except (SteelCADError, KeyError):
            return _err('Quell’angolo non c’è più: riprova.')
        p = bd.Vector(*info['xyz'])
        aste = [m for m in st.members if m.id in info['members']]
        passanti = self._passanti(st, p)
        nomi = self.nomi_tubi(st)
        fdef = self.doc.feature(st_id)
        spec = (fdef.get('joints') or {}).get(key) or fdef.get('angoli') or {'type': 'auto'}
        scelte, ora, coppie = [], None, []
        if passanti and aste:
            lungo = passanti[0]
            art, tipo = self._parola(nomi, lungo)
            art2, tipo2 = self._parola(nomi, self._chi_passa(aste))
            v = _classe(lungo.w) == 'verticali'
            scelte = [{'key': 'unico', 'label': f'Passa {art} {tipo}, tubo unico', 'disegno': 'verticale' if v else 'orizzontale'},
                      {'key': 'dividi', 'label': f'Passa {art2} {tipo2}', 'disegno': 'orizzontale' if v else 'verticale'}]
            ora = 'unico'
        elif len(aste) >= 2:
            coppie = self._in_linea(aste, p)
            in_linea = {_classe(a_.w) for a_, _ in coppie}
            orizz = [m for m in aste if _classe(m.w) != 'verticali']
            sez = {(m.profile.width, m.profile.height) for m in (orizz if len(aste) > 2 else aste)}
            if (len(aste) == 2 or len(orizz) == 2) and len(sez) == 1 and not coppie:
                scelte.append({'key': '45', 'label': 'A 45°', 'disegno': 'miter'})
            classi = []
            for m in aste:
                c = _classe(m.w)
                if c not in classi:
                    classi.append(c)
            for c in sorted(classi, key=lambda c: c != 'verticali'):
                m = next(m for m in aste if _classe(m.w) == c)
                art, tipo = self._parola(nomi, m)
                disegno = 'verticale' if c == 'verticali' else 'orizzontale'
                if c in in_linea:            # due pezzi in linea: si possono fare diventare uno solo
                    scelte.append({'key': f'unisci:{c}', 'label': f'Passa {art} {tipo}, tubo unico', 'disegno': disegno})
                elif len(classi) > 1:
                    scelte.append({'key': c, 'label': f'Passa {art} {tipo}', 'disegno': disegno})
            ora = spec.get('passa') or ({'miter': '45'}.get(spec.get('type')))
            if spec.get('type') == 'butt' and spec.get('through'):
                ora = next((_classe(m.w) for m in aste if m.id in spec['through']), None)
            if ora is None and '45' in info.get('auto', ''):
                ora = '45'
        simili = self._angoli_simili(st, key) if not (passanti or coppie) else [key]   # unire/dividere: solo qui
        righe = [[nomi[m.id], f'{fmt_mm(round(m.length, 1))} {"dritto" if not any(m.cuts) else "a 45°"}']
                 for m in passanti + aste]
        return _ok(nome=nome_punto(p, st.members), quanti=len(aste), scelte=scelte, ora=ora, simili=len(simili),
                   righe=righe)

    def _firma_angolo(self, st, key):
        info = st.nodes[key]
        p = bd.Vector(*info['xyz'])
        parti = []
        for m in st.members:
            if m.id not in info['members']:
                continue
            parti.append((_classe(m.w), m.profile.name))
        return tuple(sorted(parti))

    def _angoli_simili(self, st, key) -> list:
        f = self._firma_angolo(st, key)
        return [k for k in st.nodes if st.nodes[k]['members'] and self._firma_angolo(st, k) == f]

    # ------------------------------------------------------------------ modifiche
    def set_angolo(self, st_id: str, key: str, scelta: str, tutti: bool = False) -> dict:
        """«A 45°» ('45'), «Passa la gamba / il traverso / il fianco» ('verticali', 'x', 'y'), «tubo unico»
        ('unisci:<direzione>': due pezzi in linea diventano un tubo solo) o «dividi» (il tubo lungo si spezza qui)."""
        info = self.angolo_info(st_id, key)
        if not info.get('ok'):
            return info
        if scelta not in [s['key'] for s in info['scelte']]:
            return _err('Questa scelta non va bene per questo angolo.')
        nome = next(s['label'] for s in info['scelte'] if s['key'] == scelta)
        if scelta == 'unico':
            return _ok(state=self.state(), message=f'{nome}: è già così.')
        if scelta.startswith('unisci:') or scelta == 'dividi':
            return self._unisci_dividi(st_id, key, scelta, nome)
        st = self._st(st_id)
        chiavi = self._angoli_simili(st, key) if tutti else [key]
        quanti = info['quanti']

        def fn():
            joints = self.doc.feature(st_id).setdefault('joints', {})
            for k in chiavi:
                if scelta == '45':
                    joints[k] = {'type': 'miter'} if quanti == 2 else {'type': 'auto', 'scelto': True}
                else:
                    joints[k] = {'type': 'butt', 'passa': scelta}
        r = self._change(f'{info["nome"]}: {nome}' + (f' (tutti i {len(chiavi)})' if len(chiavi) > 1 else ''), fn)
        if r.get('ok'):
            r['message'] = f'{nome}' + (f' su {len(chiavi)} angoli uguali.' if len(chiavi) > 1 else '.')
        return r

    def _togli_tubo(self, fdef, mid):
        """Toglie un tubo: dalla lista se fatto a mano, spento se nasce da una sagoma o da un modello."""
        membri = fdef.setdefault('members', [])
        if any(m['id'] == mid for m in membri):
            fdef['members'] = [m for m in membri if m['id'] != mid]
        else:
            fdef.setdefault('overrides', {}).setdefault(mid, {})['deleted'] = True

    def _def_tubo(self, fdef, m):
        """Profilo, gruppo e nome di un tubo, per rifarlo uguale."""
        d = {'profile': m.profile.name.replace('×', 'x'), 'group': m.group}
        if m.material != fdef.get('material', 'S235'):
            d['material'] = m.material
        return d

    def _unisci_dividi(self, st_id, key, scelta, nome):
        st = self._st(st_id)
        info = st.nodes[key]
        p = bd.Vector(*info['xyz'])
        aste = [m for m in st.members if m.id in info['members']]
        if scelta == 'dividi':
            lungo = self._passanti(st, p)[0]
            ka, kb = self._punto_di(st, lungo.start), self._punto_di(st, lungo.end)
            classe = _classe(self._chi_passa(aste).w)
        else:
            c = scelta.split(':', 1)[1]
            a_, b_ = next((x, y) for x, y in self._in_linea(aste, p) if _classe(x.w) == c)
            ka = self._punto_di(st, a_.start if (a_.end - p).length < 1e-6 else a_.end)
            kb = self._punto_di(st, b_.end if (b_.start - p).length < 1e-6 else b_.start)
        if not ka or not kb:
            return _err('Non trovo i capi del tubo: riprova.')

        def fn():
            fdef = self.doc.feature(st_id)
            usati = {m.id for m in st.members} | {m['id'] for m in fdef.get('members') or []}
            joints = fdef.setdefault('joints', {})
            if scelta == 'dividi':
                self._togli_tubo(fdef, lungo.id)
                base = self._def_tubo(fdef, lungo)
                for da, a in ((ka, key), (key, kb)):
                    mid = self._free_id(fdef, 'U', usati)
                    usati.add(mid)
                    fdef.setdefault('members', []).append({'id': mid, 'from': da, 'to': a, **base})
                joints[key] = {'type': 'butt', 'passa': classe}       # la gamba passa, i due pezzi ci battono
            else:
                for m in (a_, b_):
                    self._togli_tubo(fdef, m.id)
                mid = self._free_id(fdef, 'U', usati)
                fdef.setdefault('members', []).append({'id': mid, 'from': ka, 'to': kb, **self._def_tubo(fdef, a_)})
                joints[key] = {'type': 'auto'}       # il nodo sta a metà del tubo unico: gli altri ci battono contro
        r = self._change(f'{nome_punto(p, st.members)}: {nome}', fn)
        if r.get('ok'):
            r['message'] = f'{nome}.'
        return r

    def _specchio(self, st, punti: list, d: bd.Vector):
        """I punti specchiati dall'altra parte della struttura (davanti ↔ dietro, o sinistra ↔ destra)."""
        b = self._limiti(st)
        c = b.center()
        dz = bd.Vector(d.X, d.Y, 0)
        if dz.length < 1e-6:                          # in piedi: si specchia davanti ↔ dietro
            n = bd.Vector(0, 1, 0)
        else:
            n = bd.Vector(0, 0, 1).cross(dz.normalized()).normalized()
        return [p - n * (2 * (p - c).dot(n)) for p in punti]

    def add_traverso(self, st_id: str, a_id: str, b_id: str, quota, rif: str = 'sotto', profile: str | None = None,
                     opposto: bool = False, nome: str = '') -> dict:
        """Un traverso tra due tubi cliccati. Tubi in piedi: `quota` = altezza da terra (fuori tutto); sdraiati:
        distanza dall'inizio del tubo (da sinistra o da davanti). Con `opposto` anche dall'altra parte."""
        try:
            st = self._st(st_id)
            ma = next((m for m in st.members if m.id == a_id), None)
            mb = next((m for m in st.members if m.id == b_id), None)
            if ma is None or mb is None or ma is mb:
                raise SteelCADError('Clicca due tubi diversi.', code='traverso')
            q = _num(quota, 'Altezza')
            prof = str(profile or ma.profile.name.replace('×', 'x'))
            parse(prof)
            if rif not in ('sotto', 'meta', 'sopra'):
                rif = 'sotto'
            z0 = min(p.Z for m in st.members for p in (m.start, m.end))
            aggancio = []
            for m in (ma, mb):
                aggancio.append(self._su_tubo(st, m, q, z0))
            pa, pb = aggancio[0][2], aggancio[1][2]
            if (pa - pb).length < 1:
                raise SteelCADError('I due punti coincidono: scegli due tubi distanti.', code='traverso')
            coppie = [aggancio]
            if opposto:
                altro_a = self._tubo_tra(st, *self._specchio(st, [ma.start, ma.end], pb - pa))
                altro_b = self._tubo_tra(st, *self._specchio(st, [mb.start, mb.end], pb - pa))
                if altro_a is None or altro_b is None:
                    raise SteelCADError('Dall’altra parte non ci sono due tubi uguali: togli «anche dietro».',
                                        code='traverso')
                coppie.append([self._su_tubo(st, altro_a, q, z0), self._su_tubo(st, altro_b, q, z0)])
        except SteelCADError as ex:
            return _err(ex.message, ex.code)
        nuovi = []

        def fn():
            fdef = self.doc.feature(st_id)
            punti = fdef.setdefault('points', {})
            aste = fdef.setdefault('members', [])
            usati = {m.id for m in st.members} | {m['id'] for m in aste}
            for (ka, offa, _), (kb, offb, _) in coppie:
                chiavi = []
                for k, off in ((ka, offa), (kb, offb)):
                    nk = self._free_id(fdef, 'P', punti)
                    punti[nk] = {'from': k, 'offset': [round(c, 3) for c in off]}
                    chiavi.append(nk)
                mid = self._free_id(fdef, 'A', usati)
                usati.add(mid)
                d = {'id': mid, 'from': chiavi[0], 'to': chiavi[1], 'profile': prof, 'group': 'Traversi', 'rif': rif}
                if nome:
                    d['name'] = nome if len(coppie) == 1 else f'{nome} ({len(nuovi) + 1})'
                aste.append(d)
                nuovi.append(f'{st_id}/{mid}')
        r = self._change('Traverso' if len(coppie) == 1 else f'{len(coppie)} traversi', fn)
        if r.get('ok'):
            r['select'] = nuovi[0]
            r['message'] = 'Traverso aggiunto.' if len(nuovi) == 1 else f'{len(nuovi)} traversi aggiunti.'
        return r

    def _tubo_tra(self, st, p, q):
        for m in st.members:
            if ((m.start - p).length < 1e-3 and (m.end - q).length < 1e-3) or \
               ((m.start - q).length < 1e-3 and (m.end - p).length < 1e-3):
                return m
        return None

    def _su_tubo(self, st, m, q, z0):
        """(chiave del nodo di partenza, spostamento, punto) del punto sul tubo m a quota q."""
        a, b = m.start, m.end
        if abs(m.w.Z) > 0.95:                                # in piedi: da terra
            basso = a if a.Z <= b.Z else b
            p = bd.Vector(basso.X, basso.Y, z0 + q)
            lo, hi = sorted((a.Z, b.Z))
            if not lo + 1e-6 < p.Z < hi - 1e-6:
                raise SteelCADError(f'A {fmt_mm(q)} da terra il tubo {self.nomi_tubi(st)[m.id]} non c’è: va da '
                                    f'{fmt_mm(round(lo - z0))} a {fmt_mm(round(hi - z0))}.', code='traverso')
        else:                                               # sdraiato: da sinistra o da davanti
            basso = min((a, b), key=lambda v: (round(v.X, 3), round(v.Y, 3), round(v.Z, 3)))
            alto = b if basso is a else a
            w = (alto - basso).normalized()
            p = basso + w * q
            if not 1e-6 < q < (alto - basso).length - 1e-6:
                raise SteelCADError(f'Il tubo {self.nomi_tubi(st)[m.id]} è lungo {fmt_mm(round((alto - basso).length))}: '
                                    f'{fmt_mm(q)} è fuori.', code='traverso')
        k = self._punto_di(st, basso)
        if k is None:
            raise SteelCADError('Non trovo l’angolo da cui misurare: riprova.', code='traverso')
        off = p - basso
        return k, [off.X, off.Y, off.Z], p

    def tubo_da_angolo(self, st_id: str, key: str, freccia: str, lunghezza, profile: str | None = None,
                       nome: str = '') -> dict:
        """Tubo nuovo dall'angolo, con la freccia (su, giù, avanti, dietro, destra, sinistra): lunghezza fuori tutto."""
        if freccia not in FRECCE:
            return _err('Scegli una freccia: su, giù, avanti, dietro, destra o sinistra.')
        try:
            lung = _num(lunghezza, 'Lunghezza')
            if lung <= 0:
                raise SteelCADError('La lunghezza deve essere maggiore di zero.', code='misura')
            if profile:
                parse(str(profile))
            st = next((s for s in self.result.structures if s.id == st_id), None)
            info = (st.nodes or {}).get(key) if st else None
            if info is None:
                raise SteelCADError('Quell’angolo non c’è più: riprova.', code='nodo')
        except SteelCADError as ex:
            return _err(ex.message, ex.code)
        asse, segno = {'X': 0, 'Y': 1, 'Z': 2}[FRECCE[freccia][0]], 1 if FRECCE[freccia][1] == '+' else -1
        d = bd.Vector(*[segno if i == asse else 0 for i in range(3)])
        p = bd.Vector(*info['xyz'])
        aste = [m for m in st.members if m.id in info['members']]
        # il tubo nuovo continua un tubo che c'è già oltre l'angolo (una mensola): la gamba passa e tutti ci battono
        continua = any(_tocca_dir(m, p).dot(d) < -0.99 for m in aste)
        verticale = any(_classe(m.w) == 'verticali' for m in aste)
        nuovo = {}

        def fn():
            fdef = self.doc.feature(st_id)
            punti = fdef.setdefault('points', {})
            membri = fdef.setdefault('members', [])
            arrivo = self._free_id(fdef, 'N', punti)
            punti[arrivo] = {'from': key, 'offset': [lung * d.X, lung * d.Y, lung * d.Z]}
            mid = self._free_id(fdef, 'M', {m.id for m in st.members} | {m['id'] for m in membri})
            prof = str(profile or (aste[0].profile.name.replace('×', 'x') if aste else '40x40x3'))
            m = {'id': mid, 'from': key, 'to': arrivo, 'profile': prof}
            if nome:
                m['name'] = nome
            membri.append(m)
            if continua and verticale:
                fdef.setdefault('joints', {})[key] = {'type': 'butt', 'passa': 'verticali'}
            nuovo['id'] = f'{st_id}/{mid}'
            nuovo['node'] = f'{st_id}:{arrivo}'
        r = self._change(f'{nome or "Tubo"} verso {freccia}', fn)
        if r.get('ok'):
            r['select'] = nuovo['id']
            r['node'] = nuovo['node']
            if continua and verticale:
                r['message'] = 'Tubo aggiunto. In quell’angolo ora la gamba passa e i tubi ci battono contro.'
        return r

    def sagoma_nuova(self, piano: str = 'XZ') -> dict:
        """Uno sketch vuoto per disegnare una sagoma di tubi dentro il progetto: di fronte, di fianco o dall'alto."""
        if piano not in ('XY', 'XZ', 'YZ'):
            return _err('Scegli da dove la guardi: di fronte, di fianco o dall’alto.')
        nuovo = {}

        def fn():
            nomi = {'XZ': 'di fronte', 'YZ': 'di fianco', 'XY': 'dall’alto'}
            nuovo['id'] = self.doc.add_sketch(piano, f'Sagoma {nomi[piano]}').id
        r = self._change('Sagoma nuova', fn)
        if r.get('ok'):
            r['sketch'] = nuovo['id']
        return r

    def fai_tubi(self, sid: str, values: dict) -> dict:
        """Dalla sagoma disegnata: ogni linea un tubo; «ripeti dietro a …» (fuori tutto) e «collega in ogni angolo».
        Dietro = verso il fondo guardando lo sketch: di fronte → dietro, dall'alto → sopra, di fianco → a destra."""
        try:
            sk = self.doc.sketch(sid)
        except SteelCADError as ex:
            return _err(ex.message)
        v = dict(values or {})
        ripeti = str(v.get('ripeti', '')).lower() in ('1', 'true', 'sì', 'si', 'on')
        collega = str(v.get('collega', '')).lower() in ('1', 'true', 'sì', 'si', 'on')
        try:
            dist = _num(v.get('distanza') or 0, 'Distanza') if ripeti else 0
            if ripeti and dist <= 0:
                raise SteelCADError('Scrivi a che distanza va ripetuta la sagoma.', code='misura')
        except SteelCADError as ex:
            return _err(ex.message, ex.code)
        prima = {f['id'] for f in self.doc.features if not isinstance(f, Sketch) and f.get('type') == 'structure'}
        r = self._structure_from_sketch(sid, sk, {
            'profile': v.get('profile') or '40x40x3', 'copies': 2 if ripeti else 1, 'distance': dist,
            'side': 'back' if sk.plane == 'XZ' else 'front', 'connect': collega,
            'connect_profile': v.get('collega_profile') or v.get('profile'), 'group': 'Sagoma',
            'connect_group': 'Collegamenti', 'esterno': True})
        if r.get('ok'):
            st = next((f for f in self.doc.features if not isinstance(f, Sketch) and f.get('type') == 'structure'), None)
            if st is not None and st['id'] not in prima:
                r['message'] = 'Tubi fatti: ora cambiali cliccando tubi e angoli.'
        return r
