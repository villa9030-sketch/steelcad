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
from cad_engine.structures.frame import SEP_PEZZO, _classe
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


def _t(v) -> tuple:
    return (v.X, v.Y, v.Z)


def _senza_quota(nome: str) -> str:
    """«Traverso in mezzo, da davanti a dietro, in alto» → «Traverso in mezzo, da davanti a dietro»: nell'incrocio
    i due tubi stanno alla stessa altezza, conta solo che tubo è (03/11: le due scelte si chiamavano uguali)."""
    parti = [x for x in nome.split(', ') if not (x in ('in alto', 'in basso') or (x.startswith('a ') and x.endswith(' da terra')))]
    return ', '.join(parti) or nome


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

    def _scelta(self, obj_id: str) -> str:
        """Il tubo appena fatto da scegliere: se un incrocio l'ha tagliato in pezzi («D1» → «D1~1»), il primo pezzo
        (03/11: dopo «Dividi» con la croce usciva «Quello che hai cliccato non c'è più»)."""
        st_id, mid = obj_id.split('/', 1)
        st = next((s for s in self.result.structures if s.id == st_id), None)
        if st is None or any(m.id == mid for m in st.members):
            return obj_id
        pezzo = next((m.id for m in st.members if m.id.split(SEP_PEZZO)[0] == mid), None)
        return f'{st_id}/{pezzo}' if pezzo else obj_id

    def _limiti(self, st):
        b = bd.Compound([m.solid for m in st.members]).bounding_box() if st.members else None
        return b

    def struttura_cosa_fare(self, st_id: str) -> dict:
        """Per il pannello della struttura appena creata: fuori tutto, tubi, peso e «Cosa puoi fare adesso»."""
        st = self._st(st_id)
        from cad_engine.structures import cut_list
        cl = cut_list([st])
        solidi = [m.solid for m in st.members] + [a.solid for a in st.accessori or []]    # coi piedi e i tappi
        b = bd.Compound(solidi).bounding_box() if solidi else None
        fuori = [round(v) for v in (b.size.X, b.size.Y, b.size.Z)] if b else []
        kg = cl['kg'] + sum(a['kg_total'] for a in cl.get('accessori') or [])          # coi piedi e i lamierini
        return {'fuori_tutto': fuori, 'tubi': cl['pieces'], 'misure': len(cl['rows']), 'kg': round(kg, 1),
                'esterno': bool(self.doc.feature(st_id).get('esterno'))}

    def tubo_info(self, st, m) -> dict:
        """Il tubo cliccato, in parole d'officina."""
        nomi = self.nomi_tubi(st)
        gruppo = [x for x in st.members if x.group == m.group and m.group]
        verticale = abs(m.w.Z) > 0.95
        a, b = m.start, m.end
        if verticale:
            basso = a if a.Z <= b.Z else b
        else:
            basso = min((a, b), key=lambda v: (round(v.X, 3), round(v.Y, 3), round(v.Z, 3)))
        w = ((b if basso is a else a) - basso).normalized()
        z0 = min(p.Z for x in st.members for p in (x.start, x.end))
        # per misurare col mouse il punto sul tubo (03/11): da dove e in che verso si conta, come punto_su_tubo
        misura = {'da': list(_t(basso)), 'dir': list(_t(w)), 'z0': z0, 'lunghezza': m.axis_length}
        return {'nome': nomi[m.id], 'contro': [nomi[i] for i in m.contro if i in nomi],
                'gruppo_n': len(gruppo), 'verticale': verticale, 'misura': misura,
                'facce': [self.NOMI_FACCE[f] for f in self._facce_di(st, m)]}

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
        if key in (st.incroci or {}):
            return self._incrocio_info(st, key)
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

    def _nome_tubo(self, st, mid):
        """Il nome d'officina di un tubo, anche se un incrocio l'ha tagliato in pezzi (il nome del primo pezzo)."""
        nomi = self.nomi_tubi(st)
        if mid in nomi:
            return nomi[mid]
        pezzo = next((k for k in nomi if k.split(SEP_PEZZO)[0] == mid), None)
        return nomi[pezzo] if pezzo else mid

    def _incrocio_info(self, st, key):
        """Due tubi che si attraversano (03/11): chi passa intero e chi si taglia in due pezzi che gli battono contro."""
        inc = st.incroci[key]
        scelte = []
        # il disegnino (03/11: i due erano uguali): la croce vista da dove si capisce, il tubo che passa intero e
        # l'altro in due pezzi. In piedi = in verticale nel disegnino; tra due sdraiati (visti dall'alto) quello da
        # davanti a dietro è il verticale
        rango = {'verticali': 0, 'y': 1, 'x': 2}
        ra, rb = (rango.get(self._classe_tubo(st, x) or '', 3) for x in (inc['a'], inc['b']))
        in_verticale = inc['a'] if ra <= rb else inc['b']
        for mid in (inc['a'], inc['b']):
            nome = self._nome_tubo(st, mid)
            nome = nome.split(' (')[0] if nome.endswith(')') else nome      # «Fianco in alto (1)»: il tubo è uno
            scelte.append({'key': f'passa:{mid}', 'label': f'Passa intero: {_senza_quota(nome).lower()}',
                           'disegno': 'croce_v' if mid == in_verticale else 'croce_o'})
        righe = [[self._nome_tubo(st, x.id), f'{fmt_mm(round(x.length, 1))} dritto']
                 for x in st.members if x.id.split(SEP_PEZZO)[0] in (inc['a'], inc['b'])]
        return _ok(nome='Incrocio', quanti=2, scelte=scelte, ora=f'passa:{inc["passa"]}',
                   simili=len(self._incroci_simili(st, key)), righe=righe, incrocio=True)

    @staticmethod
    def _classe_tubo(st, mid):
        """La direzione (verticali, x, y) del tubo mid, anche se un incrocio l'ha tagliato in pezzi."""
        m = next((x for x in st.members if x.id.split(SEP_PEZZO)[0] == mid), None)
        return _classe(m.w) if m is not None else None

    def _incroci_simili(self, st, key) -> list:
        """Gli incroci tra tubi nelle stesse direzioni (in uno scaffale: tutti i montanti coi traversi davanti)."""
        firma = lambda k: tuple(sorted((self._classe_tubo(st, st.incroci[k]['a']) or '',
                                        self._classe_tubo(st, st.incroci[k]['b']) or '')))
        f = firma(key)
        return [k for k in st.incroci if firma(k) == f]

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
        if info.get('incrocio'):
            st = self._st(st_id)
            scelto = scelta.split(':', 1)[1]
            chiavi = {key: scelto}
            if tutti:                # 03/11: su tutti gli incroci uguali passa il tubo nella stessa direzione
                c = self._classe_tubo(st, scelto)
                for k in self._incroci_simili(st, key):
                    inc = st.incroci[k]
                    chiavi[k] = inc['a'] if self._classe_tubo(st, inc['a']) == c else inc['b']

            def scegli():
                self.doc.feature(st_id).setdefault('incroci', {}).update(chiavi)
            r = self._change(f'Incrocio: {nome}' + (f' (tutti i {len(chiavi)})' if len(chiavi) > 1 else ''), scegli)
            if r.get('ok'):
                r['message'] = (f'{nome}: l’altro tubo è tagliato in due pezzi che gli battono contro.' if len(chiavi) == 1
                                else f'Su {len(chiavi)} incroci passa intero il tubo nella stessa direzione.')
            return r
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
        """Un traverso tra due tubi cliccati. Tubi in piedi: `quota` = altezza da terra (fuori tutto), `rif` dice
        se è il sotto, la metà o il sopra del traverso; sdraiati: distanza dall'inizio del tubo (da sinistra o da
        davanti) al centro del traverso (`rif` 'centro', anche 'sotto' come prima) o al suo bordo ('bordo').
        `quota` = 'mezzo': in mezzo al tubo (a metà altezza per i tubi in piedi). Con `opposto` anche dall'altra
        parte."""
        try:
            st = self._st(st_id)
            ma = next((m for m in st.members if m.id == a_id), None)
            mb = next((m for m in st.members if m.id == b_id), None)
            if ma is None or mb is None or ma is mb:
                raise SteelCADError('Clicca due tubi diversi.', code='traverso')
            prof = str(profile or ma.profile.name.replace('×', 'x'))
            parse(prof)
            z0 = min(p.Z for m in st.members for p in (m.start, m.end))
            in_piedi = abs(ma.w.Z) > 0.95
            al_bordo = rif == 'bordo' and not in_piedi
            mezzo = str(quota).strip().lower() in ('mezzo', 'in mezzo', 'metà', 'meta')
            if mezzo:
                q = self._mezzo(ma, z0)
                if in_piedi:
                    rif = 'meta'
                al_bordo = False
            else:
                q = _num(quota, 'Altezza' if in_piedi else 'Distanza')
            if rif not in ('sotto', 'meta', 'sopra'):
                rif = 'sotto'
            aggancio = [self._su_tubo(st, m, q, z0) for m in (ma, mb)]
            if al_bordo:          # la misura arriva al bordo del traverso: il suo centro è mezzo tubo più in là
                t = self._spessore_lungo(parse(prof), (aggancio[1][2] - aggancio[0][2]).normalized(), ma.w)
                q = q + t / 2
                aggancio = [self._su_tubo(st, m, q, z0) for m in (ma, mb)]
            pa, pb = aggancio[0][2], aggancio[1][2]
            if abs(ma.w.Z) < 0.05 and abs(mb.w.Z) < 0.05 and abs(pa.Z - pb.Z) < 1e-6:
                # tra due tubi sdraiati (la croce sopra un telaio) il traverso sta a filo con loro, non appoggiato
                # sopra (03/11: il telaio da 795 veniva alto 825)
                bz = ma.solid.bounding_box()
                rif = 'sopra' if abs(bz.max.Z - pa.Z) < 1e-3 else ('sotto' if abs(bz.min.Z - pa.Z) < 1e-3 else 'meta')
            if (pa - pb).length < 1:
                raise SteelCADError('I due punti coincidono: scegli due tubi distanti.', code='traverso')
            if mezzo:        # il punto resta in mezzo al tubo anche cambiando le misure del modello
                aggancio = [x + (self._capi_tubo(st, t),) for x, t in zip(aggancio, (ma, mb))]
            coppie = [aggancio]
            if opposto:
                altro_a = self._tubo_tra(st, *self._specchio(st, [ma.start, ma.end], pb - pa))
                altro_b = self._tubo_tra(st, *self._specchio(st, [mb.start, mb.end], pb - pa))
                if altro_a is None or altro_b is None:
                    raise SteelCADError('Dall’altra parte non ci sono due tubi uguali: togli «anche dietro».',
                                        code='traverso')
                altra = [self._su_tubo(st, altro_a, q, z0), self._su_tubo(st, altro_b, q, z0)]
                if mezzo:
                    altra = [x + (self._capi_tubo(st, t),) for x, t in zip(altra, (altro_a, altro_b))]
                # in mezzo l'altra parte è lo stesso traverso (03/11: «In mezzo» con «anche dietro» lo faceva doppio)
                if not any((x[2] - y[2]).length < 1 for x in altra for y in aggancio):
                    coppie.append(altra)
        except SteelCADError as ex:
            return _err(ex.message, ex.code)
        nuovi = []

        def fn():
            fdef = self.doc.feature(st_id)
            punti = fdef.setdefault('points', {})
            aste = fdef.setdefault('members', [])
            usati = {m.id for m in st.members} | {m['id'] for m in aste}
            for ga, gb in coppie:
                chiavi = []
                for g in (ga, gb):
                    k, off = g[0], g[1]
                    capi = g[3] if len(g) > 3 else None
                    nk = self._free_id(fdef, 'P', punti)
                    punti[nk] = {'mezzo': list(capi)} if capi else {'from': k, 'offset': [round(c, 3) for c in off]}
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
            r['select'] = self._scelta(nuovi[0])
            r['message'] = 'Traverso aggiunto.' if len(nuovi) == 1 else f'{len(nuovi)} traversi aggiunti.'
        return r

    def _capi_tubo(self, st, m):
        """Le chiavi dei due angoli alle teste del tubo m (per un punto «in mezzo»); None se una testa non è un
        angolo fisso (un pezzo di tubo tagliato da un incrocio): allora il punto si mette a misura come prima."""
        ka, kb = self._punto_di(st, m.start), self._punto_di(st, m.end)
        if not ka or not kb or '×' in ka or '×' in kb:
            return None
        return (ka, kb)

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

    @staticmethod
    def _mezzo(m, z0) -> float:
        """La misura del punto in mezzo al tubo: per un tubo in piedi da terra, per uno sdraiato dall'inizio."""
        if abs(m.w.Z) > 0.95:
            return (m.start.Z + m.end.Z) / 2 - z0
        return m.axis_length / 2

    def traverso_info(self, st_id: str, a_id: str, b_id: str) -> dict:
        """Per il pannello del traverso: in piedi o sdraiati, e la misura «in mezzo» da scrivere nel campo."""
        try:
            st = self._st(st_id)
            ma = next((m for m in st.members if m.id == a_id), None)
            if ma is None:
                raise SteelCADError('Quel tubo non c’è più: riprova.', code='tubo')
        except SteelCADError as ex:
            return _err(ex.message, ex.code)
        z0 = min(p.Z for m in st.members for p in (m.start, m.end))
        return _ok(in_piedi=abs(ma.w.Z) > 0.95, mezzo=round(self._mezzo(ma, z0), 1), profilo=ma.profile.name.replace('×', 'x'),
                   lunghezza=round(ma.axis_length, 1))

    def punto_su_tubo(self, st_id: str, mid: str, quota) -> dict:
        """Un punto su un tubo, da cui far partire un tubo nuovo con le frecce (03/11: «dai montanti non posso nemmeno
        creare il tubo»). Tubo in piedi: `quota` = altezza da terra; sdraiato: distanza dall'inizio (da sinistra o da
        davanti). Il tubo nuovo che parte da qui batte contro questo (giunto a T)."""
        try:
            st = self._st(st_id)
            m = next((x for x in st.members if x.id == mid), None)
            if m is None:
                raise SteelCADError('Quel tubo non c’è più: riprova.', code='tubo')
            q = _num(quota, 'Distanza')
            z0 = min(p.Z for x in st.members for p in (x.start, x.end))
            k, off, p = self._su_tubo(st, m, q, z0)
        except SteelCADError as ex:
            return _err(ex.message, ex.code)
        gia = self._punto_di(st, p)
        if gia:                                            # c'è già un punto lì (un incrocio, un traverso): quello
            return _ok(state=self.state(), node=f'{st_id}:{gia}', message='Su quel punto c’è già un nodo: parti da lì.')
        nuovo = {}

        def fn():
            fdef = self.doc.feature(st_id)
            punti = fdef.setdefault('points', {})
            nk = self._free_id(fdef, 'P', punti)
            punti[nk] = {'from': k, 'offset': [round(c, 3) for c in off]}
            nuovo['node'] = f'{st_id}:{nk}'
        verticale = abs(m.w.Z) > 0.95
        r = self._change(f'Punto a {fmt_mm(q)} {"da terra" if verticale else "dall’inizio"}', fn)
        if r.get('ok'):
            r['node'] = nuovo['node']
            r['message'] = 'Punto messo: scegli la freccia per il tubo nuovo.'
        return r

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

    # ------------------------------------------------------------------ come sta il profilo (03/11)
    # Tubi rettangolari e profili aperti (angolari, piatti, UPN): «girarli di 90° e scegliere da che parte stanno deve
    # essere chiaro». Le posizioni possibili, ognuna col disegnino della sezione vista di testa, «su» in alto e
    # «fuori» (verso l'esterno della struttura) a destra.
    POSIZIONI = {'RHS': (0, 90), 'FLAT': (0, 90), 'IPE': (0, 90), 'HEA': (0, 90), 'HEB': (0, 90),
                 'L': (0, 90, 180, 270), 'UPN': (0, 90, 180, 270), 'U': (0, 90, 180, 270), 'C': (0, 90, 180, 270)}

    def _vista_testa(self, st, m):
        """Gli assi del disegnino: (destra, su, parole). Tubo sdraiato: su = in alto, destra = verso fuori; in piedi:
        visto da sopra, destra = verso destra, su = verso dietro."""
        if abs(m.w.Z) > 0.95:
            return bd.Vector(1, 0, 0), bd.Vector(0, 1, 0), ('dietro', 'destra')
        su = bd.Vector(0, 0, 1)
        destra = su.cross(m.w).normalized()
        lim = self._limiti_linee(st)
        c = bd.Vector(*[(a + b) / 2 for a, b in lim])
        mezzo = (m.start + m.end) * 0.5
        if (mezzo - c).dot(destra) < 0:
            destra = -destra
        return destra, su, ('su', 'fuori')

    @staticmethod
    def _contorni(prof) -> list:
        """I contorni della sezione (fuori e dentro), punti 2D nel piano del profilo."""
        f = prof.section()
        out = []
        for w in [f.outer_wire()] + list(f.inner_wires()):
            pts = []
            for e in w.order_edges():
                n = 1 if e.geom_type == bd.GeomType.LINE else 6
                pts += [e @ (k / n) for k in range(n)]
            out.append([(p.X, p.Y) for p in pts])
        return out

    @staticmethod
    def _parola_posizione(prof, pts2d, rot):
        fam = prof.family
        xs = [x for x, _ in pts2d]
        ys = [y for _, y in pts2d]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        cx = sum(xs) / len(xs) - (max(xs) + min(xs)) / 2
        cy = sum(ys) / len(ys) - (max(ys) + min(ys)) / 2
        if fam in ('RHS', 'FLAT'):
            return f'{"In piedi" if h > w + 1e-6 else "Sdraiato"} (alto {fmt_mm(round(h, 1))})'
        if fam in ('IPE', 'HEA', 'HEB'):
            return 'Anima in piedi' if h > w + 1e-6 else 'Anima sdraiata'
        return None

    def member_posizioni(self, obj_id: str) -> dict:
        """Le posizioni del profilo cliccato (girato di 90°, 180°…), col disegnino della sezione vista di testa."""
        from cad_engine.structures.frame import _section_axes
        try:
            st_id, mid = obj_id.split('/', 1)
            st = self._st(st_id)
            m = next((x for x in st.members if x.id == mid), None)
            if m is None:
                raise SteelCADError('Quel tubo non c’è più: riprova.', code='tubo')
        except (SteelCADError, ValueError) as ex:
            return _err(getattr(ex, 'message', str(ex)))
        rots = self.POSIZIONI.get(m.profile.family)
        if not rots:
            return _ok(posizioni=[])
        fdef = self.doc.feature(st_id)
        base = mid.split(SEP_PEZZO)[0]
        d = next((x for x in fdef.get('members') or [] if x['id'] == base), None) or \
            (fdef.get('overrides') or {}).get(base) or {}
        ora_r, flip = float(d.get('rotate', 0)) % 360, bool(d.get('flip', False))
        destra, su, (n_su, n_destra) = self._vista_testa(st, m)
        contorni = self._contorni(m.profile)
        out = []
        for r in rots:
            x, y = _section_axes(m.w, r, flip)
            disegno = [[(round((x * px + y * py).dot(destra), 2), round((x * px + y * py).dot(su), 2)) for px, py in c]
                       for c in contorni]
            fam = m.profile.family
            testo = self._parola_posizione(m.profile, disegno[0], r)
            if testo is None:
                # angolari e U: dove sta lo spigolo (o la schiena) — il baricentro sta da quella parte
                xs = [p[0] for p in disegno[0]]
                ys = [p[1] for p in disegno[0]]
                cx = sum(xs) / len(xs) - (max(xs) + min(xs)) / 2
                cy = sum(ys) / len(ys) - (max(ys) + min(ys)) / 2
                alto = {'su': ('in alto', 'in basso'), 'dietro': ('dietro', 'davanti')}[n_su]
                lato = {'fuori': ('fuori', 'dentro'), 'destra': ('a destra', 'a sinistra')}[n_destra]
                if fam == 'L':
                    testo = f'Spigolo {alto[0] if cy > 0 else alto[1]}, {lato[0] if cx > 0 else lato[1]}'
                else:
                    aperta = (lato[1] if cx > 0 else lato[0]) if abs(cx) > abs(cy) else (alto[1] if cy > 0 else alto[0])
                    testo = f'Aperto {"verso " + aperta if aperta in ("fuori", "dentro") else aperta}'
            giro = 180 if len(rots) == 2 else 360          # un rettangolo girato di 180° è uguale
            out.append({'rotate': r, 'flip': flip, 'disegno': disegno, 'testo': testo,
                        'ora': abs(((ora_r - r) + giro / 2) % giro - giro / 2) < 1e-6})
        if not any(p['ora'] for p in out):
            out[0]['ora'] = True
        return _ok(posizioni=out, su=n_su, destra=n_destra, ribalta=m.profile.family == 'L' and
                   abs(m.profile.width - m.profile.height) > 1e-6)

    # ------------------------------------------------------------------ piedi e tappi (03/11)
    # In officina, finito il telaio: sotto le gambe la piastra coi fori (o il piedino regolabile), sulle teste dei
    # tubi rimaste aperte il tappo. Un comando per tutte le gambe a terra, uno per tutte le teste libere.
    def piedi_info(self, st_id: str) -> dict:
        """Per il pannello «Piedi e tappi»: quante gambe a terra e teste libere, cosa c'è già, le misure proposte."""
        from cad_engine.structures.accessori import PIEDINI, _teste_libere, gambe_a_terra
        try:
            st = self._st(st_id)
        except SteelCADError as ex:
            return _err(ex.message, ex.code)
        fdef = self.doc.feature(st_id)
        gambe = gambe_a_terra(st.members)
        tubo = max((max(m.profile.width, m.profile.height) for m in gambe), default=30)
        lato = max(80, int(-(-(tubo + 50) // 10) * 10))
        coperte = {(m.id, 0 if m.start.Z < m.end.Z else 1) for m in gambe} if fdef.get('piedi') else set()
        teste = _teste_libere(st.members, coperte)
        return _ok(gambe=len(gambe), teste=len(teste), piedi=fdef.get('piedi'), tappi=fdef.get('tappi'),
                   proposta={'tipo': 'piastra', 'lato': lato, 'sp': 6 if tubo <= 50 else 8, 'fori': 4, 'foro': 9,
                             'dal_bordo': 15 if lato <= 100 else 20, 'misura': 'M10'},
                   piedini=list(PIEDINI))

    def _altezza(self, st) -> float:
        solidi = [m.solid for m in st.members] + [a.solid for a in st.accessori or []]
        return bd.Compound(solidi).bounding_box().size.Z

    def set_piedi(self, st_id: str, spec: dict | None = None) -> dict:
        """Piastra o piedino regolabile sotto tutte le gambe a terra (spec None: si tolgono)."""
        from cad_engine.structures.accessori import gambe_a_terra
        try:
            st = self._st(st_id)
            if spec and not gambe_a_terra(st.members):
                raise SteelCADError('Non ci sono gambe a terra: servono tubi in piedi che arrivano giù.', code='piedi')
        except SteelCADError as ex:
            return _err(ex.message, ex.code)
        spec = {k: v for k, v in (spec or {}).items() if v not in (None, '')} or None

        def fn():
            fdef = self.doc.feature(st_id)
            if spec:
                fdef['piedi'] = spec
            else:
                fdef.pop('piedi', None)
        cosa = 'Piedi tolti' if not spec else ('Piastre sotto le gambe' if spec.get('tipo', 'piastra') == 'piastra'
                                                else 'Piedini sotto le gambe')
        r = self._change(cosa, fn)
        if r.get('ok') and spec:
            st = self._st(st_id)
            piedi = [a for a in st.accessori or [] if a.id.startswith('PIEDE-')]
            h = self._altezza(st)
            r['message'] = (f'{len(piedi)} × {piedi[0].descrizione[0].lower()}{piedi[0].descrizione[1:]}' + (
                f' e piedino {spec.get("misura", "M10")}' if spec.get('tipo') == 'piedino' else '') +
                f'. Altezza fuori tutto coi piedi: {fmt_mm(round(h, 1))}.') if piedi else cosa + '.'
        elif r.get('ok'):
            r['message'] = 'Piedi tolti.'
        return r

    def set_tappi(self, st_id: str, spec: dict | None = None) -> dict:
        """Tappo in plastica (da comprare) o lamierino saldato su tutte le teste libere dei tubi (None: si tolgono)."""
        try:
            self._st(st_id)
        except SteelCADError as ex:
            return _err(ex.message, ex.code)
        spec = {k: v for k, v in (spec or {}).items() if v not in (None, '')} or None

        def fn():
            fdef = self.doc.feature(st_id)
            if spec:
                fdef['tappi'] = spec
            else:
                fdef.pop('tappi', None)
        r = self._change('Tappi sulle teste dei tubi' if spec else 'Tappi tolti', fn)
        if r.get('ok') and spec:
            tappi = [a for a in self._st(st_id).accessori or [] if a.id.startswith('TAPPO-')]
            d = tappi[0].descrizione if tappi else ''
            r['message'] = (f'{len(tappi)} × {d[0].lower()}{d[1:]}.' if tappi
                            else 'Non ci sono teste di tubo aperte: niente tappi da mettere.')
        elif r.get('ok'):
            r['message'] = 'Tappi tolti.'
        return r

    # ------------------------------------------------------------------ dividi una faccia (03/11)
    # «Complicatissimo, il contrario di intuitivo»: per il fianco 2×2 e la croce sopra servivano punti, frecce e
    # misure tolte a mano. Ora: clic su un tubo del fianco (o del telaio sopra) → «Dividi in 2 / in 3» → montanti e
    # traversi a filo della faccia, quadri uguali; dove si incrociano uno passa e l'altro si taglia (incroci).
    FACCE = {'sinistra': (0, -1), 'destra': (0, 1), 'davanti': (1, -1), 'dietro': (1, 1), 'sotto': (2, -1),
             'sopra': (2, 1)}
    NOMI_FACCE = {'sinistra': 'Il fianco a sinistra', 'destra': 'Il fianco a destra', 'davanti': 'Il davanti',
                  'dietro': 'Il dietro', 'sopra': 'Il telaio sopra', 'sotto': 'Il telaio sotto'}
    OPPOSTA = {'sinistra': 'destra', 'destra': 'sinistra', 'davanti': 'dietro', 'dietro': 'davanti',
               'sopra': 'sotto', 'sotto': 'sopra'}

    @staticmethod
    def _assi_faccia(asse):
        """(asse u, asse v) nella faccia: in piedi u = in larghezza/profondità e v = in altezza; sopra u = X, v = Y."""
        return {0: (1, 2), 1: (0, 2), 2: (0, 1)}[asse]

    @staticmethod
    def _limiti_linee(st):
        pts = [_t(p) for m in st.members for p in (m.start, m.end)]
        return [(min(p[i] for p in pts), max(p[i] for p in pts)) for i in range(3)]

    def _facce_di(self, st, m) -> list:
        """Le facce della struttura (i sei lati del fuori tutto) su cui sta il tubo m."""
        lim = self._limiti_linee(st)
        out = []
        for nome, (asse, verso) in self.FACCE.items():
            if lim[asse][1] - lim[asse][0] < 1:
                continue
            val = lim[asse][1 if verso > 0 else 0]
            if all(abs(_t(p)[asse] - val) < 1e-3 for p in (m.start, m.end)):
                out.append(nome)
        return out

    def _faccia(self, st, nome):
        """Com'è fatta una faccia: piano, estensione in u e v, quanto sono grossi i tubi sui quattro bordi."""
        asse, verso = self.FACCE[nome]
        lim = self._limiti_linee(st)
        val = lim[asse][1 if verso > 0 else 0]
        iu, iv = self._assi_faccia(asse)
        sopra = [m for m in st.members if all(abs(_t(p)[asse] - val) < 1e-3 for p in (m.start, m.end))]
        if not sopra:
            return None
        pts = [_t(p) for m in sopra for p in (m.start, m.end)]
        u0, u1 = min(p[iu] for p in pts), max(p[iu] for p in pts)
        v0, v1 = min(p[iv] for p in pts), max(p[iv] for p in pts)

        def bordo(i, x):
            """Lo spessore del tubo che corre sul bordo (i = u o v, a quota x), 0 se lì non c'è un tubo."""
            grossi = []
            for m in sopra:
                if all(abs(_t(p)[i] - x) < 1e-3 for p in (m.start, m.end)):
                    b = m.solid.bounding_box()
                    grossi.append(_t(b.max)[i] - _t(b.min)[i])
            return max(grossi, default=0.0)
        return {'asse': asse, 'verso': verso, 'val': val, 'iu': iu, 'iv': iv, 'u': (u0, u1), 'v': (v0, v1),
                'bu': (bordo(iu, u0), bordo(iu, u1)), 'bv': (bordo(iv, v0), bordo(iv, v1)), 'tubi': sopra}

    @staticmethod
    def _spessore_lungo(prof, w: bd.Vector, d: bd.Vector) -> float:
        """Quanto è grosso il tubo (profilo prof, lungo w) misurato in direzione d."""
        from cad_engine.structures.frame import _section_axes
        x, y = _section_axes(w, 0, False)
        return abs(x.dot(d)) * prof.width + abs(y.dot(d)) * prof.height

    @staticmethod
    def _centri(a, b, ba, bb, t, spec) -> list:
        """I centri dei tubi nuovi tra a e b (bordi grossi ba, bb). spec: {'parti': n} = quadri uguali;
        {'misure': [..], 'rif': 'centro'|'bordo'} = a misura dal bordo esterno (fuori tutto)."""
        if not spec:
            return []
        if spec.get('misure'):
            out = []
            for q in spec['misure']:
                q = _num(q, 'Misura')
                c = a + q + (t / 2 if spec.get('rif') == 'bordo' else 0)
                if not a + ba + t / 2 - 1e-6 <= c <= b - bb - t / 2 + 1e-6:
                    raise SteelCADError(f'A {fmt_mm(q)} il tubo esce dalla faccia (va da 0 a {fmt_mm(round(b - a))}).',
                                        code='dividi')
                out.append(c)
            return out
        n = int(spec.get('parti') or 1)
        if n < 2:
            return []
        if n > 20:
            raise SteelCADError('Al massimo 20 parti.', code='dividi')
        luce = (b - a - ba - bb - (n - 1) * t) / n
        if luce <= 1:
            raise SteelCADError(f'In {n} parti non ci stanno: i tubi si toccano.', code='dividi')
        return [a + ba + k * luce + (k - 1) * t + t / 2 for k in range(1, n)]

    def dividi_info(self, st_id: str, mid: str, normale=None) -> dict:
        """Per il pannello «Dividi»: le facce su cui sta il tubo cliccato, con le misure. La prima è il lato più
        probabile: quello verso cui guarda la faccia del tubo cliccata (`normale`, nel 3D). 03/11: su un tubo dello
        spigolo in alto veniva sempre prima «Il telaio sopra», anche cliccando il davanti del tubo."""
        try:
            st = self._st(st_id)
            m = next((x for x in st.members if x.id == mid), None)
            if m is None:
                raise SteelCADError('Quel tubo non c’è più: riprova.', code='tubo')
        except SteelCADError as ex:
            return _err(ex.message, ex.code)
        facce = []
        ordine = ['sopra', 'sinistra', 'destra', 'dietro', 'davanti', 'sotto']
        for nome in sorted(self._facce_di(st, m), key=ordine.index):
            f = self._faccia(st, nome)
            if f is None:
                continue
            altra = self.OPPOSTA[nome]
            aperti = [k for k, x in zip(('u0', 'u1', 'v0', 'v1'), f['bu'] + f['bv']) if not x]
            if aperti == ['v0'] and f['asse'] != 2:
                aperti = 'Metti anche il tubo a terra (sotto è aperto)'
            elif aperti:
                aperti = 'Chiudi i bordi aperti con un tubo'
            facce.append({'key': nome, 'label': self.NOMI_FACCE[nome], 'u': round(f['u'][1] - f['u'][0], 1),
                          'v': round(f['v'][1] - f['v'][0], 1), 'in_piedi': f['asse'] != 2,
                          'opposta': self.NOMI_FACCE[altra].lower() if self._faccia(st, altra) else '',
                          'aperti': aperti or '',
                          # i tubi del lato e il lato stesso (4 angoli, un filo fuori): nel 3D si vede quale si divide
                          'tubi': [f'{st_id}/{x.id}' for x in f['tubi']], 'rett': self._rettangolo(f)})
        if not facce:
            return _err('Questo tubo non sta su un lato della struttura: clicca un tubo del fianco o del telaio sopra.')
        if normale and len(normale) == 3:
            verso = {k: [0, 0, 0] for k in self.FACCE}
            for k, (asse, s_) in self.FACCE.items():
                verso[k][asse] = s_
            dot = lambda k: sum(a * float(b) for a, b in zip(verso[k], normale))    # noqa: E731
            facce.sort(key=lambda f: -round(dot(f['key']), 3))
        return _ok(facce=facce, profilo=m.profile.name.replace('×', 'x'))

    @staticmethod
    def _rettangolo(f) -> list:
        """I quattro angoli del lato (sul fuori dei tubi, mezzo millimetro fuori) per colorarlo nel 3D."""
        out = []
        for a, b in ((0, 0), (1, 0), (1, 1), (0, 1)):
            p = [0.0, 0.0, 0.0]
            p[f['asse']] = f['val'] + 0.5 * f['verso']
            p[f['iu']] = f['u'][a]
            p[f['iv']] = f['v'][b]
            out.append([round(c, 3) for c in p])
        return out

    def dividi(self, st_id: str, mid: str, faccia: str, larghezza=None, altezza=None, opposta: bool = False,
               profile: str | None = None, chiudi: bool = False) -> dict:
        """Divide la faccia su cui sta il tubo cliccato. `larghezza`: in quante parti (o a che misure) si divide la
        larghezza (montanti; sopra: i tubi da davanti a dietro); `altezza`: l'altezza (traversi; sopra: la
        profondità, tubi da sinistra a destra). Ognuno {'parti': n} o {'misure': [..], 'rif': 'centro'|'bordo'};
        un numero = parti. I tubi nuovi stanno a filo della faccia, battono contro i tubi del bordo e dove si
        incrociano uno passa e l'altro si taglia in due. `chiudi`: prima mette i tubi che mancano sui bordi della
        faccia (il tubo a terra di un fianco aperto sotto). `opposta`: lo stesso anche sul lato di fronte."""
        def spec(x):
            if x in (None, '', 0, 1, '1'):
                return None
            if isinstance(x, (int, float, str)):
                return {'parti': int(_num(x, 'Parti'))}
            return dict(x)
        try:
            st = self._st(st_id)
            m = next((x for x in st.members if x.id == mid), None)
            if m is None:
                raise SteelCADError('Quel tubo non c’è più: riprova.', code='tubo')
            if faccia not in self.FACCE or faccia not in self._facce_di(st, m):
                raise SteelCADError('Scegli il lato da dividere.', code='dividi')
            prof = parse(str(profile or m.profile.name.replace('×', 'x')))
            su, sv = self._spec_dividi(larghezza), self._spec_dividi(altezza)
            if not su and not sv and not chiudi:
                raise SteelCADError('Scegli in quante parti dividere.', code='dividi')
            linee, quadri = self._linee_dividi(st, faccia, su, sv, opposta, prof, chiudi)
        except SteelCADError as ex:
            return _err(ex.message, ex.code)
        nuovi = []

        def fn():
            fdef = self.doc.feature(st_id)
            tubi, punti = self._metti_linee(fdef, st, linee, prof)
            nuovi.extend(f'{st_id}/{x}' for x in tubi)
            # ricordata: cambiando le misure del modello la divisione si rifà uguale (quadri uguali sulle misure nuove)
            fdef.setdefault('divisioni', []).append({
                'faccia': faccia, 'larghezza': su, 'altezza': sv, 'opposta': bool(opposta),
                'profile': prof.name.replace('×', 'x'), 'chiudi': bool(chiudi), 'tubi': tubi, 'punti': punti})
        quanti = len(linee)
        r = self._change(f'{self.NOMI_FACCE[faccia]}: diviso' + (' (anche l’altro lato)' if opposta else ''), fn)
        if r.get('ok'):
            r['select'] = self._scelta(nuovi[0])
            lu, lv = quadri
            dim = (lambda xs: fmt_mm(round(xs[0], 1)) if max(xs) - min(xs) < 0.05 else ' / '.join(fmt_mm(round(x, 1)) for x in xs))
            n = len(lu) * len(lv)
            r['message'] = (f'{quanti} {"tubo aggiunto" if quanti == 1 else "tubi aggiunti"}, a filo. '
                            f'{"Viene" if n == 1 else "Vengono"} {n} {"quadro" if n == 1 else "quadri"} '
                            f'{dim(lu)} × {dim(lv)} (luce tra i tubi)'
                            + (' per lato.' if opposta else '.'))
            r['quadri'] = [[round(x, 1) for x in lu], [round(x, 1) for x in lv]]
        return r

    @staticmethod
    def _spec_dividi(x):
        if x in (None, '', 0, 1, '1'):
            return None
        if isinstance(x, (int, float, str)):
            return {'parti': int(_num(x, 'Parti'))}
        return dict(x)

    def _linee_dividi(self, st, faccia, su, sv, opposta, prof, chiudi):
        """Le linee dei tubi nuovi (p0, p1, verso dentro o None = come i vicini, gruppo) e i quadri che vengono."""
        facce = [faccia] + ([self.OPPOSTA[faccia]] if opposta else [])
        linee = []
        quadri = None
        for nome in facce:
            f = self._faccia(st, nome)
            if f is None:
                raise SteelCADError(f'{self.NOMI_FACCE[nome]} non ha tubi: togli «anche l’altro».', code='dividi')
            iu, iv, asse = f['iu'], f['iv'], f['asse']
            eu, ev, ea = (bd.Vector(*[1 if i == k else 0 for i in range(3)]) for k in (iu, iv, asse))
            dentro = ea * -f['verso']
            base = [0.0, 0.0, 0.0]
            base[asse] = f['val']
            base = bd.Vector(*base)
            bu, bv = list(f['bu']), list(f['bv'])
            if chiudi:                                 # i bordi senza tubo: si chiudono, il tubo sta dentro
                for bordi, (c0, c1), e_lungo, e_div, (x0, x1) in ((bu, f['v'], ev, eu, f['u']),
                                                                  (bv, f['u'], eu, ev, f['v'])):
                    for k, x in enumerate((x0, x1)):
                        if bordi[k]:
                            continue
                        bordi[k] = self._spessore_lungo(prof, e_lungo, e_div)
                        linee.append((base + e_div * x + e_lungo * c0, base + e_div * x + e_lungo * c1, None,
                                      'Montanti' if abs(e_lungo.Z) > 0.9 else 'Traversi'))
            luci = []
            for sp, (a, b), (ba, bb), (c0, c1), e_lungo, e_div, idx in (
                    (su, f['u'], bu, f['v'], ev, eu, iu), (sv, f['v'], bv, f['u'], eu, ev, iv)):
                t = self._spessore_lungo(prof, e_lungo, e_div)
                centri = self._centri(a, b, ba, bb, t, sp)
                # i quadri che vengono: tra i bordi, i tubi che ci sono già in mezzo (i ripiani di uno scaffale)
                # e quelli nuovi
                pezzi = {(round(c - t / 2, 3), round(c + t / 2, 3)) for c in centri}
                for x in f['tubi']:
                    if abs(x.w.dot(e_lungo)) > 0.999:
                        bx = x.solid.bounding_box()
                        lo, hi = _t(bx.min)[idx], _t(bx.max)[idx]
                        if lo > a + ba - 1e-3 and hi < b - bb + 1e-3:
                            pezzi.add((round(lo, 3), round(hi, 3)))
                bordi = [a + ba] + [x for pz in sorted(pezzi) for x in pz] + [b - bb]
                luci.append([bordi[k + 1] - bordi[k] for k in range(0, len(bordi), 2)])
                for c in centri:
                    p0 = base + e_div * c + e_lungo * c0
                    p1 = base + e_div * c + e_lungo * c1
                    gia = any(abs(x.w.dot(e_lungo)) > 0.999 and (x.start - p0).cross(e_lungo).length < 1e-3
                              for x in f['tubi'])
                    if not gia:
                        linee.append((p0, p1, dentro, 'Montanti' if abs(e_lungo.Z) > 0.9 else 'Traversi'))
            if quadri is None:
                quadri = luci
        if not linee:
            raise SteelCADError('Lì i tubi ci sono già.', code='dividi')
        return linee, quadri

    def _metti_linee(self, fdef, st, linee, prof):
        """Le linee diventano punti e tubi della struttura: ritorna (id dei tubi, chiavi dei punti nuovi)."""
        punti = fdef.setdefault('points', {})
        aste = fdef.setdefault('members', [])
        usati = {x.id.split(SEP_PEZZO)[0] for x in st.members} | {x['id'] for x in aste}
        tubi, chiavi_nuove = [], []
        for p0, p1, dentro, gruppo in linee:
            chiavi = []
            for p in (p0, p1):
                gia = self._punto_di(st, p) if dentro is None else None     # i bordi: dagli angoli che ci sono
                if gia and '×' not in gia:
                    chiavi.append(gia)
                    continue
                nk = self._free_id(fdef, 'P', punti)
                punti[nk] = self._punto_relativo(st, p)
                chiavi.append(nk)
                chiavi_nuove.append(nk)
            nid = self._free_id(fdef, 'D', usati)
            usati.add(nid)
            d = {'id': nid, 'from': chiavi[0], 'to': chiavi[1], 'profile': prof.name.replace('×', 'x'),
                 'group': gruppo}
            if dentro is not None:
                d.update(anchor='center', offset=self._a_filo(prof, p1 - p0, dentro))
            aste.append(d)
            tubi.append(nid)
        return tubi, chiavi_nuove

    def _riporta_aggiunte(self, old: dict, new_st: dict) -> list:
        """Cambiando le misure di un modello (structure_template_apply): i tubi aggiunti a mano (traversi, tubi dalle
        frecce, punti) restano, e le divisioni («Dividi il lato») si rifanno sulle misure nuove, coi quadri uguali
        (03/11: prima cambiando l'altezza si perdeva tutto). Va chiamata dentro la modifica, con new_st già al suo
        posto nel progetto. Ritorna le divisioni che non si possono rifare (frasi)."""
        divisioni = old.get('divisioni') or []
        fatti = {x for d in divisioni for x in d.get('tubi', [])}
        punti_div = {k for d in divisioni for k in d.get('punti', [])}
        punti = new_st.setdefault('points', {})
        for k, v in (old.get('points') or {}).items():
            if k not in punti and k not in punti_div:
                punti[k] = v
        del_modello = {m['id'] for m in new_st.get('members') or []}
        for m in old.get('members') or []:
            if m['id'] not in del_modello and m['id'] not in fatti:
                new_st.setdefault('members', []).append(m)
        if old.get('incroci'):
            new_st['incroci'] = dict(old['incroci'])
        for k in ('piedi', 'tappi'):                       # piedi e tappi restano (03/11)
            if old.get(k):
                new_st[k] = dict(old[k])
        persi = []
        if not divisioni:
            return persi
        self._rebuild()
        for d in divisioni:
            try:
                st = self._st(new_st['id'])
                prof = parse(d['profile'])
                linee, _ = self._linee_dividi(st, d['faccia'], d.get('larghezza'), d.get('altezza'), d.get('opposta'),
                                              prof, d.get('chiudi'))
            except SteelCADError as ex:
                persi.append(f'{self.NOMI_FACCE.get(d["faccia"], d["faccia"])}: {ex.message}')
                continue
            tubi, chiavi = self._metti_linee(new_st, st, linee, prof)
            new_st.setdefault('divisioni', []).append({**d, 'tubi': tubi, 'punti': chiavi})
            self._rebuild()
        return persi

    @staticmethod
    def _a_filo(prof, w: bd.Vector, dentro: bd.Vector) -> list:
        """Lo spostamento (nella sezione) che porta il tubo dentro la faccia: la linea resta lo spigolo esterno."""
        from cad_engine.structures.frame import _section_axes
        x, y = _section_axes(w.normalized(), 0, False)
        ox = (prof.width / 2) * (1 if x.dot(dentro) > 0 else -1) if abs(x.dot(dentro)) > 0.9 else 0
        oy = (prof.height / 2) * (1 if y.dot(dentro) > 0 else -1) if abs(y.dot(dentro)) > 0.9 else 0
        return [round(ox, 4), round(oy, 4)]

    def _punto_relativo(self, st, p: bd.Vector):
        """Un punto nuovo legato all'angolo più vicino della struttura (se l'angolo si sposta, il punto lo segue)."""
        cand = [(k, bd.Vector(*v['xyz'])) for k, v in (st.nodes or {}).items() if '×' not in k]
        if not cand:
            return [round(c, 3) for c in _t(p)]
        k, q = min(cand, key=lambda kv: ((kv[1] - p).length, kv[0]))
        return {'from': k, 'offset': [round(c, 3) for c in _t(p - q)]}

    def _punti_a_t(self, sid) -> set:
        """I punti della sagoma dove una linea finisce a metà di un'altra (il montante in mezzo al fianco che arriva
        sul tubo sopra) o le attraversa: lì «collega» non mette un traverso tra i due lati (03/11: col fianco 2×2
        disegnato si collegavano anche il montante e il traverso di mezzo, una croce sopra non voluta)."""
        try:
            ss = self.doc.solved_sketch(sid)
        except Exception:  # noqa: BLE001 - senza sagoma risolta si collega come prima
            return set()
        ents = self.doc.sketch(sid).entities
        linee = [ab for lid, ab in ss.lines.items() if not ents.get(lid, {}).get('construction')]
        out = set()
        for lid_ab in linee:
            for pid in lid_ab:
                x, y = ss.points[pid]
                for a, b in linee:
                    if pid in (a, b):
                        continue
                    (xa, ya), (xb, yb) = ss.points[a], ss.points[b]
                    dx, dy = xb - xa, yb - ya
                    n2 = dx * dx + dy * dy
                    if not n2:
                        continue
                    t = ((x - xa) * dx + (y - ya) * dy) / n2
                    if 1e-3 < t < 1 - 1e-3 and abs((x - xa) * dy - (y - ya) * dx) / n2 ** 0.5 < 1e-2:
                        out.add(pid)
        return out

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
        punti_t = self._punti_a_t(sid) if collega else set()
        r = self._structure_from_sketch(sid, sk, {
            'connect_points': punti_t,
            'profile': v.get('profile') or '40x40x3', 'copies': 2 if ripeti else 1, 'distance': dist,
            'side': 'back' if sk.plane == 'XZ' else 'front', 'connect': collega,
            'connect_profile': v.get('collega_profile') or v.get('profile'), 'group': 'Sagoma',
            'connect_group': 'Collegamenti', 'esterno': True})
        if r.get('ok'):
            st = next((f for f in self.doc.features if not isinstance(f, Sketch) and f.get('type') == 'structure'), None)
            if st is not None and st['id'] not in prima:
                r['message'] = 'Tubi fatti: ora cambiali cliccando tubi e angoli.'
        return r
