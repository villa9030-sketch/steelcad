"""Scheletro in 3D per i telai che non stanno su un piano solo (05/11, idea dallo «sketch 3D» di SolidCraft).

Radius aveva già le strutture coi punti nello spazio: «Telaio da zero» con le frecce (su, giù, avanti…), «Unisci a
un altro angolo», «Sposta l'angolo» con destra/dietro/su. Mancavano le linee storte: la gamba inclinata della
tramoggia, il corrimano della scala, la capriata, il tronco di piramide. Qui:

- tubo nuovo da un angolo, inclinato («parte verso su, piegato di 10° verso destra»), misurato lungo il tubo o in
  altezza;
- tubo fino a un punto scritto (destra/dietro/su da questo angolo, o da zero); se lì c'è già un angolo si aggancia;
- tubo parallelo a un altro tubo, o ad angolo con lui (a squadra = 90°), girato dalla parte di una freccia;
- le misure della linea cliccata (lunghezza, angoli coi tubi vicini) si cambiano dopo: i tubi legati seguono.

I punti nuovi si scrivono nel file con il campo "lungo" (vedi cad_engine/structures/linee3d.py): i pezzi già salvati
non li hanno e restano come erano.
"""
from __future__ import annotations

import math

import build123d as bd

from cad_engine import SteelCADError
from cad_engine.errors import FeatureError
from cad_engine.profiles import parse
from cad_engine.structures.frame import SEP_PEZZO
from cad_engine.structures.linee3d import FRECCE, PAROLE, direzione
from cad_engine.units import fmt_mm

MODI = ('inclinata', 'punto', 'parallela', 'angolo')


def _ok(**kw):
    return {'ok': True, **kw}


def _err(msg, code='linea'):
    return {'ok': False, 'code': code, 'message': msg}


def _num(v, nome):
    try:
        x = float(str(v).replace(',', '.').strip())
    except (TypeError, ValueError):
        raise SteelCADError(f'{nome}: «{v}» non è un numero.', code='misura') from None
    if not math.isfinite(x):
        raise SteelCADError(f'{nome}: «{v}» non è un numero.', code='misura')
    return int(x) if x.is_integer() else round(x, 4)


def _gradi(a: bd.Vector, b: bd.Vector) -> float:
    c = max(-1.0, min(1.0, a.normalized().dot(b.normalized())))
    return math.degrees(math.acos(c))


def _vic(a, b, tol=1e-2) -> bool:
    return (a - b).length < tol


class Scheletro3DMixin:
    # ------------------------------------------------------------------ cose comuni
    def _s3_st(self, st_id):
        st = next((s for s in self.result.structures if s.id == st_id), None)
        if st is None:
            raise SteelCADError('La struttura non c’è più.', code='struttura')
        return st

    @staticmethod
    def _s3_xyz(st, k) -> bd.Vector:
        info = (st.nodes or {}).get(k)
        if info is None:
            raise SteelCADError(f'Il punto {k} non c’è più: riprova.', code='nodo')
        return bd.Vector(*info['xyz'])

    def _s3_capi(self, st_id, st, mid):
        """Le chiavi (da, a) dei due capi del tubo intero (anche se un incrocio l'ha diviso in pezzi), o None."""
        base = mid.split(SEP_PEZZO)[0]
        fdef = self.doc.feature(st_id)
        d = next((m for m in fdef.get('members') or [] if m.get('id') == base), None)
        if d and d.get('from') and d.get('to'):
            return d['from'], d['to'], d
        pezzi = [m for m in st.members if m.id.split(SEP_PEZZO)[0] == base]
        if not pezzi:
            return None
        a = pezzi[0].start
        b = pezzi[-1].end
        ka, kb = self._punto_di(st, a), self._punto_di(st, b)
        if not ka or not kb or '×' in ka or '×' in kb:
            return None
        return ka, kb, None

    def _s3_spec(self, st_id, st, key, spec):
        """(definizione del punto nuovo, dove cade, descrizione) dal pannello."""
        spec = dict(spec or {})
        modo = spec.get('modo', 'inclinata')
        if modo not in MODI:
            raise SteelCADError('Scegli come va il tubo: inclinato, fino a un punto, parallelo o ad angolo.', code='modo')
        p0 = self._s3_xyz(st, key)
        if modo == 'punto':
            xyz = [_num(spec.get(k) if spec.get(k) not in (None, '') else 0, n)
                   for k, n in (('destra', 'Destra'), ('dietro', 'Dietro'), ('su', 'Su'))]
            if spec.get('da_zero'):
                return list(xyz), bd.Vector(*xyz), 'Punto ' + ' · '.join(fmt_mm(c) for c in xyz)
            if not any(xyz):
                raise SteelCADError('Scrivi almeno una misura: quanto va a destra, dietro o su.', code='misura')
            return {'from': key, 'offset': xyz}, p0 + bd.Vector(*xyz), 'Tubo fino al punto'
        lung = _num(spec.get('lunghezza'), 'Lunghezza')
        if lung <= 0:
            raise SteelCADError('La lunghezza deve essere maggiore di zero.', code='misura')
        if modo == 'inclinata':
            fr = spec.get('freccia', 'su')
            if fr not in FRECCE:
                raise SteelCADError('Scegli la freccia: su, giù, avanti, dietro, destra o sinistra.', code='freccia')
            piega = []
            for dove, g in spec.get('piega') or []:
                if str(g).strip() in ('', '0'):
                    continue
                g = _num(g, 'Piega')
                if dove not in FRECCE:
                    raise SteelCADError('Scegli da che parte si piega il tubo.', code='freccia')
                if g:
                    piega.append([dove, g])
            verso = {'freccia': fr, 'piega': piega} if piega else fr
            pdef = {'from': key, 'lungo': lung, 'verso': verso}
            if piega and spec.get('misura') == 'freccia':
                pdef['misura'] = 'freccia'
            testo = f'Tubo verso {PAROLE[fr]}' + (', piegato ' + ' e '.join(f'{fmt_mm(g)}° verso {PAROLE[d]}' for d, g in piega) if piega else '')
        else:
            mid = spec.get('tubo')
            if not mid:
                raise SteelCADError('Clicca il tubo da prendere come riferimento.', code='tubo')
            capi = self._s3_capi(st_id, st, mid)
            if capi is None:
                raise SteelCADError('Quel tubo non ha due angoli fissi: scegline un altro.', code='tubo')
            ka, kb = capi[0], capi[1]
            if modo == 'parallela':
                verso = {'come': [ka, kb]}
                if spec.get('inverso'):
                    verso['inverso'] = True
                testo = 'Tubo parallelo'
            else:
                g = _num(spec.get('gradi', 90), 'Angolo')
                if not 0 < g < 180:
                    raise SteelCADError('L’angolo va da 1 a 179 gradi (90 = a squadra).', code='misura')
                fr = spec.get('verso', 'su')
                verso = {'da': [ka, kb], 'gradi': g, 'verso': fr}
                testo = f'Tubo a {fmt_mm(g)}°'
            pdef = {'from': key, 'lungo': lung, 'verso': verso}
        try:
            d, rif = direzione(pdef['verso'], {}, lambda k: self._s3_xyz(st, k), 'tubo nuovo')
        except FeatureError as ex:
            raise SteelCADError(str(ex), code='direzione') from None
        L = lung
        if pdef.get('misura') == 'freccia' and rif is not None:
            c = d.dot(rif)
            if c < 1e-6:
                raise SteelCADError('Piegato così non va più verso la freccia: misura lungo il tubo.', code='misura')
            L = lung / c
        return pdef, p0 + d * L, testo

    # ------------------------------------------------------------------ tubo nuovo in 3D
    def linea_3d(self, st_id: str, key: str, spec: dict, profile: str | None = None, nome: str = '') -> dict:
        """Tubo nuovo dall'angolo `key`: inclinato, fino a un punto, parallelo o ad angolo con un altro tubo (spec).
        Con spec.solo_punto mette solo il punto (da unire dopo). Se il capo cade su un angolo che c'è già, si aggancia
        lì (il telaio si chiude)."""
        try:
            st = self._s3_st(st_id)
            if profile:
                parse(str(profile))
            pdef, dove, testo = self._s3_spec(st_id, st, key, spec)
            p0 = self._s3_xyz(st, key)
            if (dove - p0).length < 1:
                raise SteelCADError('Il tubo sarebbe lungo zero: cambia le misure.', code='misura')
            gia = next((k for k, v in (st.nodes or {}).items() if '×' not in k and _vic(bd.Vector(*v['xyz']), dove)), None)
            solo = bool((spec or {}).get('solo_punto'))
            if solo and gia:
                raise SteelCADError('Lì c’è già un angolo.', code='nodo')
        except SteelCADError as ex:
            return _err(ex.message, ex.code)
        nuovo = {}

        def fn():
            fdef = self.doc.feature(st_id)
            punti = fdef.setdefault('points', {})
            membri = fdef.setdefault('members', [])
            arrivo = gia
            if arrivo is None:
                arrivo = self._free_id(fdef, 'N', punti)
                punti[arrivo] = pdef
            nuovo['node'] = f'{st_id}:{arrivo}'
            if solo:
                return
            for m in membri:
                if {m.get('from'), m.get('to')} == {key, arrivo}:
                    raise SteelCADError('Tra questi due angoli c’è già un tubo.', code='doppia')
            usati = {m.id.split(SEP_PEZZO)[0] for m in st.members} | {m['id'] for m in membri}
            mid = self._free_id(fdef, 'M', usati)
            aste = [m for m in st.members if m.id in (st.nodes.get(key) or {}).get('members', [])]
            prof = str(profile or (aste[0].profile.name.replace('×', 'x') if aste else
                                   (st.members[0].profile.name.replace('×', 'x') if st.members else '40x40x3')))
            m = {'id': mid, 'from': key, 'to': arrivo, 'profile': prof}
            if nome:
                m['name'] = nome
            membri.append(m)
            nuovo['id'] = f'{st_id}/{mid}'
        r = self._change(nome or testo, fn)
        if r.get('ok'):
            r['node'] = nuovo.get('node')
            if nuovo.get('id'):
                r['select'] = self._scelta(nuovo['id'])
            r['message'] = ('Punto messo: ora uniscilo con «Unisci a un altro angolo».' if solo else
                            'Tubo aggiunto: si è agganciato all’angolo che c’era già.' if gia else 'Tubo aggiunto.')
        return r

    # ------------------------------------------------------------------ le misure della linea cliccata
    def _s3_mobile(self, fdef, capi, fisso):
        """Il capo che si muove quando cambi la misura dal capo `fisso`: la sua chiave e la sua definizione, se è
        legato a `fisso` (parte da lì)."""
        ka, kb = capi[0], capi[1]
        altro = kb if fisso == ka else ka
        pdef = (fdef.get('points') or {}).get(altro)
        if isinstance(pdef, dict) and pdef.get('from') == fisso and ('lungo' in pdef or 'offset' in pdef):
            return altro, pdef
        return None, None

    def misure_linea(self, obj_id: str) -> dict:
        """Per il pannello del tubo: lunghezza della linea (lo spigolo fuori tutto), inclinazione, angoli coi tubi
        che si toccano agli angoli; per ognuna se si può cambiare da qui."""
        try:
            st_id, mid = obj_id.split('/', 1)
            st = self._s3_st(st_id)
            capi = self._s3_capi(st_id, st, mid)
            if capi is None:
                raise SteelCADError('Questo tubo non ha due angoli fissi.', code='tubo')
        except (SteelCADError, ValueError) as ex:
            return _err(getattr(ex, 'message', str(ex)))
        fdef = self.doc.feature(st_id)
        ka, kb = capi[0], capi[1]
        a, b = self._s3_xyz(st, ka), self._s3_xyz(st, kb)
        w = b - a
        mobile = self._s3_mobile(fdef, capi, ka)[0] or self._s3_mobile(fdef, capi, kb)[0]
        perche = '' if mobile else ('Questa linea viene da un disegno: si cambia dal disegno.' if capi[2] is None else
                                    'I due capi sono angoli fissi: sposta uno dei due angoli (clic sul pallino).')
        nomi = self.nomi_tubi(st)
        base = mid.split(SEP_PEZZO)[0]
        angoli = []
        for k, p in ((ka, a), (kb, b)):
            lontano = b if k == ka else a
            mio = lontano - p
            for o in st.members:
                if o.id.split(SEP_PEZZO)[0] == base:
                    continue
                if _vic(o.start, p, 1e-3):
                    suo = o.end - o.start
                elif _vic(o.end, p, 1e-3):
                    suo = o.start - o.end
                else:
                    continue
                g = _gradi(mio, suo)
                if g > 179.5 or g < 0.5:
                    continue
                si = self._s3_mobile(fdef, capi, k)[0] is not None and self._s3_capi(st_id, st, o.id) is not None
                angoli.append({'nodo': k, 'tubo': o.id, 'nome': nomi.get(o.id, o.id), 'gradi': round(g, 2), 'si_cambia': si})
        incl = math.degrees(math.asin(min(1.0, abs(w.normalized().Z))))
        return _ok(lunghezza=round(w.length, 2), si_cambia=bool(mobile), perche=perche,
                   inclinazione=round(incl, 2), da_terra=round(90 - incl, 2), angoli=angoli,
                   storta=not any(abs(abs(c) - 1) < 1e-6 for c in (w.normalized().X, w.normalized().Y, w.normalized().Z)))

    def set_lunghezza_linea(self, obj_id: str, valore) -> dict:
        """Cambia la lunghezza della linea del tubo (fuori tutto): si sposta il capo legato all'altro; i tubi che
        partono da lì lo seguono."""
        try:
            st_id, mid = obj_id.split('/', 1)
            st = self._s3_st(st_id)
            L = _num(valore, 'Lunghezza')
            if L <= 0:
                raise SteelCADError('La lunghezza deve essere maggiore di zero.', code='misura')
            capi = self._s3_capi(st_id, st, mid)
            if capi is None:
                raise SteelCADError('Questo tubo non ha due angoli fissi.', code='tubo')
            fdef = self.doc.feature(st_id)
            k, pdef = self._s3_mobile(fdef, capi, capi[0])
            if k is None:
                k, pdef = self._s3_mobile(fdef, capi, capi[1])
            if k is None:
                raise SteelCADError('Questa linea non si allunga da qui: sposta uno dei suoi angoli.', code='fisso')
            if 'lungo' not in pdef:
                off = pdef['offset']
                if not all(isinstance(c, (int, float)) for c in off):
                    raise SteelCADError('Lo spostamento di quell’angolo ha una formula: cambialo da «Sposta l’angolo».',
                                        code='formula')
                n = math.sqrt(sum(c * c for c in off))
                if n < 1e-9:
                    raise SteelCADError('Quella linea è lunga zero.', code='misura')
        except (SteelCADError, ValueError) as ex:
            return _err(getattr(ex, 'message', str(ex)))

        def fn():
            p = self.doc.feature(st_id)['points'][k]
            if 'lungo' in p:
                p['lungo'] = L
                p.pop('misura', None)
            else:
                p['offset'] = [round(c * L / n, 4) for c in p['offset']]
        return self._change(f'Linea lunga {fmt_mm(L)}', fn)

    def set_angolo_linee(self, obj_id: str, nodo: str, altro: str, gradi) -> dict:
        """L'angolo tra il tubo e un altro tubo che parte dallo stesso angolo `nodo`: gira il capo lontano del tubo
        (resta lungo uguale), nel piano dei due tubi. Da qui in poi il tubo resta a quell'angolo con l'altro."""
        try:
            st_id, mid = obj_id.split('/', 1)
            st = self._s3_st(st_id)
            g = _num(gradi, 'Angolo')
            if not 0 < g < 180:
                raise SteelCADError('L’angolo va da 1 a 179 gradi (90 = a squadra).', code='misura')
            capi = self._s3_capi(st_id, st, mid)
            capo = self._s3_capi(st_id, st, altro)
            if capi is None or capo is None or nodo not in capi[:2] or nodo not in capo[:2]:
                raise SteelCADError('Questi due tubi non partono dallo stesso angolo.', code='angolo')
            fdef = self.doc.feature(st_id)
            k, pdef = self._s3_mobile(fdef, capi, nodo)
            if k is None:
                raise SteelCADError('Il tubo ha i due capi fissi: questo angolo non si cambia da qui.', code='fisso')
            lontano = capo[1] if capo[0] == nodo else capo[0]
            p, q, r = self._s3_xyz(st, nodo), self._s3_xyz(st, k), self._s3_xyz(st, lontano)
            u = (r - p).normalized()
            w = q - p
            v = w - u * w.dot(u)
            if v.length < 1e-6:
                raise SteelCADError('I due tubi sono in fila: non si capisce da che parte girare.', code='angolo')
            v = v.normalized()
            nuovo = {'from': nodo, 'lungo': round(w.length, 4),
                     'verso': {'da': [nodo, lontano], 'gradi': g, 'verso': [round(c, 6) for c in (v.X, v.Y, v.Z)]}}
        except (SteelCADError, ValueError) as ex:
            return _err(getattr(ex, 'message', str(ex)))

        def fn():
            self.doc.feature(st_id)['points'][k] = nuovo
        return self._change(f'Angolo {fmt_mm(g)}°', fn)
