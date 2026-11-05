"""I pezzi che si muovono nell'assieme (05/11, idee da SolidCraft): cerniera, guida, perno.

Si creano come gli altri accoppiamenti (due clic: l'asse, poi l'altro pezzo). Poi il pezzo si muove col mouse o
scrivendo il valore («90», «aperta 300»): la posizione di movimento sta solo in memoria (self.asm_moto) e non cambia
il file né l'annulla; «Torna com'era» la toglie, «Tieni questa posizione» la scrive nel giunto (con l'annulla).
Finecorsa (da/a), «Trova da solo» (fin dove arriva prima di toccare) e «Controlla che non sbatta» (percorre la corsa).
"""
from __future__ import annotations

import copy
import functools
import math
import re

import numpy as np

from cad_engine import assembly as A
from cad_engine import assembly_moto as M
from cad_engine.errors import SteelCADError
from cad_engine.units import fmt_mm


def _ok(**kw):
    return {'ok': True, **kw}


def _no(ex) -> dict:
    return {'ok': False, 'message': ex.message, 'code': ex.code}


def _in_assieme(fn):
    @functools.wraps(fn)
    def dentro(self, *a, **kw):
        if self.asm is None:
            return {'ok': False, 'code': 'assieme', 'message': 'Questo comando è per gli assiemi: apri o crea un assieme.'}
        try:
            return fn(self, *a, **kw)
        except SteelCADError as ex:
            return _no(ex)
    return dentro


NOMI = {'cerniera': 'Cerniera', 'guida': 'Guida', 'perno': 'Perno'}
ASSI = ('cilindrica', 'spigolo', 'conica')


def valore_scritto(v, cosa='il valore') -> float:
    """«90», «90°», «aperta 300», «-12,5»: il primo numero che c'è."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if not math.isfinite(v):
            raise A.AssemblyError(f'Scrivi {cosa} con un numero (per esempio 90).')
        return float(v)
    t = re.search(r'[-+−]?\s*\d+(?:[.,]\d+)?', str(v or ''))
    if not t:
        raise A.AssemblyError(f'Scrivi {cosa} con un numero (per esempio 90).')
    return float(t.group(0).replace('−', '-').replace(' ', '').replace(',', '.'))


def testo_valore(q: str, v) -> str:
    if v is None:
        return 'libero'
    return f'{fmt_mm(round(float(v), 1))}{"°" if q == "angolo" else " mm"}'


class MotoMixin:
    # ------------------------------------------------------------------ riferimenti
    def _moto(self) -> dict:
        if getattr(self, 'asm_moto', None) is None:
            self.asm_moto = {}
        return self.asm_moto

    def _ref_giunto(self, c: dict) -> dict:
        """Il riferimento di un clic: il foro o il tubo cliccato (anche vicino al foro), uno spigolo dritto, o la
        faccia piana."""
        if not c or not c.get('inst'):
            raise A.AssemblyError('Clicca un pezzo.')
        if c.get('face') is not None:
            f = self._asm_face(c['inst'], c['face'])
            if f['kind'] in ('cilindrica', 'conica'):
                return f
        if c.get('edge_pt') is not None:
            try:
                return self._asm_edge(c['inst'], c['edge_pt'])
            except A.AssemblyError:
                # gli spigoli dei tubi di una struttura non hanno nome: lo spigolo dritto più vicino, ritrovato da dov'è
                i = self.asm.instance(c['inst'])
                part = self.asm_parts.get(i['file'])
                q = np.array(i['R'], dtype=float).T @ (np.array(c['edge_pt'], dtype=float) - np.array(i['T'], dtype=float))
                sp = A.spigolo_vicino(part, q, entro=2.0) if part is not None else None
                if sp is not None:
                    return {'inst': c['inst'], **sp}
        if c.get('pt') is not None:
            foro = self._foro_da_clic(c)
            if foro.get('face') is not None:
                f = self._asm_face(c['inst'], foro['face'])
                if f['kind'] == 'cilindrica':
                    return f
        if c.get('face') is None:
            raise A.AssemblyError('Clicca proprio sullo spigolo (la linea del bordo), o dentro il foro.')
        return self._asm_face(c['inst'], c['face'])

    @staticmethod
    def _fa_asse(kind: str, r: dict) -> bool:
        return r['kind'] in ASSI or (kind == 'guida' and r['kind'] == 'piana')

    def _asse_ref_mondo(self, r: dict):
        i = self.asm.instance(r['inst'])
        R, T = np.array(i['R'], dtype=float), np.array(i['T'], dtype=float)
        n = R @ np.array(r['n'], dtype=float)
        return R @ np.array(r['p'], dtype=float) + T, n / np.linalg.norm(n)

    @staticmethod
    def _frase_asse(kind: str) -> str:
        return ('Clicca un foro, un tubo o uno spigolo dritto: è l’asse attorno a cui gira.' if kind != 'guida' else
                'Clicca uno spigolo dritto, un tubo o una faccia: scorre lungo lo spigolo (o di fronte alla faccia).')

    @_in_assieme
    def asm_giunto_asse(self, kind: str, c: dict) -> dict:
        """Il primo clic di cerniera, guida o perno: l'asse che ne viene, nel mondo (per vederlo subito)."""
        if kind not in M.GIUNTI:
            return {'ok': False, 'message': f'«{kind}» non è un giunto.'}
        r = self._ref_giunto(c)
        if not self._fa_asse(kind, r):
            raise A.AssemblyError(self._frase_asse(kind))
        p, d = self._asse_ref_mondo(r)
        cosa = {'cilindrica': 'il foro', 'conica': 'il foro', 'spigolo': 'lo spigolo', 'piana': 'la faccia'}[r['kind']]
        return _ok(asse={'p': p.tolist(), 'd': d.tolist(), 'cosa': cosa, 'inst': r['inst']})

    # ------------------------------------------------------------------ crea
    def _aggiungi_giunto(self, kind: str, a: dict, b: dict) -> dict:
        """Cerniera, guida o perno: a = il primo clic (l'asse), b = l'altro pezzo. Si muove il secondo, a meno che sia
        il pezzo fermo dell'assieme. Due fori (o due spigoli) di una cerniera o di un perno si mettono in asse."""
        def fn():
            ra, rb = self._ref_giunto(a), self._ref_giunto(b)
            if ra['inst'] == rb['inst']:
                raise A.AssemblyError('I due clic sono sullo stesso pezzo: il secondo va sull’altro pezzo.')
            asse = ra if self._fa_asse(kind, ra) else rb if self._fa_asse(kind, rb) else None
            if asse is None:
                raise A.AssemblyError(self._frase_asse(kind))
            fermo, mobile = (rb, ra) if rb['inst'] == self._terra() else (ra, rb)
            for x in self.asm.mates:
                if M.e_giunto(x) and {x['a']['inst'], x['b']['inst']} == {fermo['inst'], mobile['inst']}:
                    raise A.AssemblyError(f'Tra questi due pezzi c’è già una {x["type"]}: ne basta una (cambiala o '
                                          'toglila).')
            ia, ib = self.asm.instance(fermo['inst']), self.asm.instance(mobile['inst'])
            RA, TA = np.array(ia['R'], dtype=float), np.array(ia['T'], dtype=float)
            RB, TB = np.array(ib['R'], dtype=float), np.array(ib['T'], dtype=float)
            allinea = kind != 'guida' and fermo['kind'] in ASSI and mobile['kind'] in ASSI and (
                (fermo['kind'] == 'spigolo') == (mobile['kind'] == 'spigolo'))
            if allinea:
                # foro su foro (o spigolo su spigolo): il pezzo che si muove gira il meno possibile e va sull'asse,
                # all'altezza dove sta
                pa, na = self._asse_ref_mondo(fermo)
                pb, nb = self._asse_ref_mondo(mobile)
                Q = A._rot_min(nb, na if np.dot(nb, na) >= 0 else -na)
                RB, TB = Q @ RB, Q @ (TB - pb) + pb
                TB = TB + A._perp(pa - pb, na)
            m = {'id': self.asm.new_id('M', {x['id'] for x in self.asm.mates}), 'type': kind, 'a': fermo, 'b': mobile,
                 'asse_da': 'a' if asse is fermo else 'b', 'verso': 1,
                 'rel_R': (RA.T @ RB).tolist(), 'rel_T': (RA.T @ (TB - TA)).tolist(), **{q: 0.0 for q in M.GIUNTI[kind]}}
            # gli accoppiamenti di prima tra gli stessi due pezzi lo terrebbero fermo: sospesi (si riattivano dal loro
            # pannello). Senza, la cerniera non gira
            sospesi = []
            for x in self.asm.mates:
                if not x.get('off') and {x['a']['inst'], x['b']['inst']} == {fermo['inst'], mobile['inst']}:
                    x['off'] = True
                    sospesi.append(x['id'])
            self.asm.mates.append(m)
            self._moto().pop(m['id'], None)             # un giunto tolto prima con lo stesso nome non lo muove
            nomi = {i['id']: i['name'] for i in self.asm.instances}
            msg = (f'{NOMI[kind]}: «{nomi[mobile["inst"]]}» {"gira" if kind == "cerniera" else "scorre" if kind == "guida" else "gira e scorre"} '
                   f'su «{nomi[fermo["inst"]]}». Trascinalo col mouse o scrivi di quanto.')
            if sospesi:
                msg += (f' {"L’accoppiamento" if len(sospesi) == 1 else "Gli accoppiamenti"} di prima tra i due pezzi '
                        f'{"è sospeso" if len(sospesi) == 1 else "sono sospesi"}: ora li tiene il giunto.')
            return {'select': 'mate=' + m['id'], 'message': msg}
        return self._asm_change(NOMI[kind], fn)

    # ------------------------------------------------------------------ muovi
    def _giunto(self, mid: str) -> dict:
        return M._mate(self.asm, mid)

    def _pose_adesso(self) -> dict:
        pose = {}
        for i in self.asm.instances:
            R, T = i['R'], i['T']
            pose[i['id']] = [R[0][0], R[0][1], R[0][2], T[0], R[1][0], R[1][1], R[1][2], T[1], R[2][0], R[2][1], R[2][2], T[2], 0, 0, 0, 1]
        return pose

    def _risolvi_moto(self):
        self.asm.moto = self._moto()
        self._asm_reload()

    @_in_assieme
    def asm_muovi_giunto(self, mid: str, vals: dict, fine: bool = False) -> dict:
        """Muove il giunto a questi valori ({'angolo': '90'} o {'corsa': 'aperta 300'}), dentro il finecorsa. Non cambia
        il disegno: è solo la posizione di adesso. fine=False (mentre si trascina o si scrive): solo le posizioni dei
        pezzi; fine=True: lo stato intero."""
        m = self._giunto(mid)
        mv = dict(self._moto().get(mid) or {})
        for q, v in (vals or {}).items():
            if q in M.GIUNTI[m['type']]:
                mv[q] = M.dentro_i_limiti(m, q, valore_scritto(v, 'l’angolo' if q == 'angolo' else 'la corsa'))
        self._moto()[mid] = mv
        self._risolvi_moto()
        vv = M.valori(m, self._moto())
        if not fine:
            return _ok(pose=self._pose_adesso(), valori=vv)
        self.scene_version += 1
        return _ok(state=self.state(), valori=vv)

    @_in_assieme
    def asm_giunto_torna(self, mid: str) -> dict:
        """Torna com'era: il pezzo nella posizione disegnata."""
        self._giunto(mid)
        self._moto().pop(mid, None)
        self._risolvi_moto()
        self.scene_version += 1
        return _ok(state=self.state(), message='Tornato com’era disegnato.')

    @_in_assieme
    def asm_giunto_tieni(self, mid: str) -> dict:
        """Tieni questa posizione: quella di adesso diventa quella disegnata (si salva; Annulla torna indietro)."""
        m = self._giunto(mid)
        vv = M.valori(m, self._moto())

        def fn():
            mm = self._giunto(mid)
            mm.update({q: round(v, 6) for q, v in vv.items()})
            self._moto().pop(mid, None)
            return {'message': 'Questa posizione ora è quella disegnata: ' + ', '.join(testo_valore(q, v) for q, v in vv.items()) + '.'}
        return self._asm_change(f'{NOMI[m["type"]]}: tieni questa posizione', fn)

    # ------------------------------------------------------------------ finecorsa
    def _limiti_da_campi(self, m: dict, fields: dict):
        for q in M.GIUNTI[m['type']]:
            k = 'lim_' + q
            if k not in fields:
                continue
            lim = fields[k]
            if lim is None:
                m.pop(k, None)
                continue
            lo, hi = [None if x is None or str(x).strip() == '' else valore_scritto(x, 'il finecorsa') for x in lim]
            if lo is not None and hi is not None and lo > hi:
                lo, hi = hi, lo
            if lo is None and hi is None:
                m.pop(k, None)
            else:
                m[k] = [lo, hi]
        if fields.get('verso_contrario'):
            self._gira_verso(m)

    def _gira_verso(self, m: dict):
        """Il verso dell'asse al contrario: stessa posizione, i valori col segno cambiato."""
        m['verso'] = -1 if m.get('verso', 1) > 0 else 1
        mv = self._moto().get(m['id']) or {}
        for q in M.GIUNTI[m['type']]:
            m[q] = -float(m.get(q) or 0)
            if q in mv:
                mv[q] = -mv[q]
            lo, hi = M.limiti(m, q)
            if lo is not None or hi is not None:
                m['lim_' + q] = [None if hi is None else -hi, None if lo is None else -lo]

    @_in_assieme
    def asm_giunto_limiti(self, mid: str) -> dict:
        """Trova da solo: fin dove arriva, da una parte e dall'altra, prima di toccare un altro pezzo. Si parte dalla
        posizione disegnata (lì i pezzi stanno bene), anche se adesso il pezzo è mosso; poi torna dov'era."""
        m = self._giunto(mid)
        mosso = self._moto().pop(mid, None)
        try:
            self._risolvi_moto()
            ris = M.trova_limiti(self.asm, self.asm_parts, mid)
        finally:
            if mosso:
                self._moto()[mid] = mosso
            self._risolvi_moto()
        if ris['bloccato']:
            raise A.AssemblyError('Il pezzo è tenuto anche da altri accoppiamenti a pezzi fermi: il giunto non lo può '
                                  'muovere. Sospendi o togli quegli accoppiamenti.')
        frasi, avvisi = [], []
        v_adesso = {q: float(m.get(q) or 0) for q in M.GIUNTI[m['type']]}       # da dove si è cercato

        def fn():
            mm = self._giunto(mid)
            for q, r in ris['valori'].items():
                lo0, hi0 = M.limiti(mm, q)
                lo = r['da'] if r['da'] is not None else lo0
                hi = r['a'] if r['a'] is not None else hi0
                if lo is not None or hi is not None:
                    mm['lim_' + q] = [lo, hi]
            # l'anta si apre in positivo: da −3 a 106 e non da −106 a 3 (si scrive «90», non «−90»). Si gira il verso
            # se da dove sta va molto più in là in negativo che in positivo (o in positivo non va per niente)
            for q, r in ris['valori'].items():
                v0 = v_adesso[q]
                if r['a'] is None:
                    continue
                pos, neg = r['a'] - v0, (math.inf if r['da'] is None else v0 - r['da'])
                if (pos < 0.5 and neg > 1) or (r['da'] is not None and neg > 1.5 * pos and neg > 1):
                    self._gira_verso(mm)
                    break
            # il pezzo mosso fuori dal finecorsa trovato (trascinato dentro un altro pezzo) torna dentro
            mv = self._moto().get(mid)
            if mv:
                for q in list(mv):
                    mv[q] = M.dentro_i_limiti(mm, q, mv[q])
            return {}
        r = self._asm_change(f'{NOMI[m["type"]]}: trova il finecorsa', fn)
        if not r.get('ok'):
            return r
        m = self._giunto(mid)
        for q, x in ris['valori'].items():
            lo, hi = M.limiti(m, q)
            nome = 'gira' if q == 'angolo' else 'scorre'
            frasi.append(f'{nome.capitalize()} da {testo_valore(q, lo)} a {testo_valore(q, hi)}.')
            chi = [c for c in (x.get('da_chi'), x.get('a_chi')) if c]
            if chi:
                frasi.append('Si ferma contro ' + ' e '.join(f'«{c["fermo"]}»' for c in
                                                                {c['fermo']: c for c in chi}.values()) + '.')
            if x['da'] is None and x['a'] is None and not (x['da_tempo'] or x['a_tempo']):
                avvisi.append(('Gira tutto il giro senza toccare niente' if q == 'angolo' else
                               f'Scorre {testo_valore(q, abs(x["a_fino"] - v_adesso[q]))} da tutte e due le parti senza toccare niente')
                              + ': scrivi tu il finecorsa.')
            elif x['da'] is None or x['a'] is None:
                if not (x['da_tempo'] or x['a_tempo']):
                    avvisi.append(f'Da una parte {"gira" if q == "angolo" else "scorre"} senza toccare niente: lì il '
                                  'finecorsa scrivilo tu.')
            if x['da_tempo'] or x['a_tempo']:
                avvisi.append('Non ho finito di cercare (ci metteva troppo): da quella parte scrivi tu il finecorsa.')
        if ris.get('gia'):
            avvisi.append('Si toccano già: ' + ', '.join(f'«{a}» e «{b}»' for a, b in ris['gia'])
                          + ' (li conto solo se entrano di più).')
        r.update(message=' '.join(frasi + avvisi), limiti=ris['valori'], avvisi=avvisi)
        return r

    @_in_assieme
    def asm_giunto_controlla(self, mid: str) -> dict:
        """Controlla che non sbatta: dalla posizione disegnata (lì i pezzi stanno bene) percorre la corsa fino a un
        finecorsa e poi fino all'altro (senza finecorsa: fino a dove è adesso) e dice se e dove tocca un altro pezzo.
        Se tocca, il pezzo resta lì (posizione di movimento) col punto."""
        m = self._giunto(mid)
        disegnato = {q: float(m.get(q) or 0) for q in M.GIUNTI[m['type']]}
        adesso = M.valori(m, self._moto())
        corse = []
        for q in M.GIUNTI[m['type']]:
            lo, hi = M.limiti(m, q)
            lo = lo if lo is not None else min(disegnato[q], adesso[q])
            hi = hi if hi is not None else max(disegnato[q], adesso[q])
            via = min(max(disegnato[q], lo), hi)
            for fino in (hi, lo):
                if abs(fino - via) > 1e-6:
                    corse.append((q, via, fino))
        if not corse:
            raise A.AssemblyError('Non c’è una corsa da controllare: metti il finecorsa (o «Trova da solo»), oppure porta '
                                  'il pezzo dove deve arrivare e controllo da com’era a lì.')

        def rimetti():
            self._moto()[mid] = adesso
            self._risolvi_moto()
            self.scene_version += 1
        for q, da, a in corse:
            # il controllo parte con il giunto a «da» (gli altri valori come disegnati)
            self._moto()[mid] = {**disegnato, q: da}
            self._risolvi_moto()
            ris = M.controlla(self.asm, self.asm_parts, mid, q, da, a)
            if ris['bloccato']:
                rimetti()
                raise A.AssemblyError('Il pezzo è tenuto anche da altri accoppiamenti a pezzi fermi: il giunto non lo '
                                      'può muovere.')
            if ris.get('tocca'):
                t = ris['tocca']
                self._moto()[mid] = {**disegnato, q: t['valore']}
                self._risolvi_moto()
                self.scene_version += 1
                testo = (f'Sbatte: a {testo_valore(q, t["valore"])} «{t["mobile"]}» tocca «{t["fermo"]}» (in rosso). '
                         'Il pezzo è fermo lì: cambia il finecorsa o sposta il pezzo.')
                return _ok(state=self.state(), message=testo, tocca={**t, 'q': q, 'testo': testo_valore(q, t['valore'])})
            if ris['tempo']:
                rimetti()
                return _ok(state=self.state(), message=f'Controllato fino a {testo_valore(q, ris["fino"])}: oltre ci metteva '
                           'troppo. Fin lì non tocca niente.', tocca=None)
        rimetti()
        tratti = {}
        for q, da, a in corse:
            tratti.setdefault(q, []).extend([da, a])
        frase = '; '.join(f'da {testo_valore(q, min(v))} a {testo_valore(q, max(v))}' for q, v in tratti.items())
        return _ok(state=self.state(), message=f'Non sbatte: {frase} non tocca niente.', tocca=None)

    # ------------------------------------------------------------------ per il pannello e il mouse
    def _giunto_info(self, m: dict) -> dict:
        ids, bloccato = M.mobili(self.asm, m['id'])
        try:
            p, d = M.asse_mondo(m, self.asm_parts, self.asm)
            asse = {'p': p.tolist(), 'd': d.tolist()}
        except (SteelCADError, KeyError, ValueError):
            asse = None
        vv = M.valori(m, self._moto())
        dis = {q: float(m.get(q) or 0) for q in M.GIUNTI[m['type']]}
        return {'id': m['id'], 'tipo': m['type'], 'a': m['a']['inst'], 'b': m['b']['inst'], 'mobili': ids,
                'bloccato': bloccato, 'off': bool(m.get('off')), 'asse': asse, 'valori': vv, 'disegnato': dis,
                'mosso': any(abs(vv[q] - dis[q]) > 1e-6 for q in vv),
                'limiti': {q: list(M.limiti(m, q)) for q in M.GIUNTI[m['type']]}}

    def _giunti_stato(self) -> list:
        out = []
        for m in self.asm.mates:
            if M.e_giunto(m) and not m.get('off'):
                try:
                    out.append(self._giunto_info(m))
                except (SteelCADError, KeyError, StopIteration):
                    continue
        return out

    def _asm_salvabile(self):
        """L'assieme da scrivere nel file: i pezzi nella posizione disegnata, non in quella di movimento."""
        if not any(self._moto().values()):
            return self.asm
        copia = A.Assembly(self.asm.name, copy.deepcopy(self.asm.instances), copy.deepcopy(self.asm.mates), self.asm.path,
                           copy.deepcopy(self.asm.meta))
        ids = {i['id'] for i in copia.instances if i['file'] in self.asm_parts}
        validi = A.Assembly(copia.name, [i for i in copia.instances if i['file'] in self.asm_parts],
                            [m for m in copia.mates if m['a']['inst'] in ids and m['b']['inst'] in ids], copia.path)
        A.solve(validi, self.asm_parts)
        return copia
