"""Pezzi bloccati insieme nell'assieme (05/11, idea da SolidCraft «joint.rigid_group»).

Scelgo due o più pezzi e «Blocca insieme»: da lì si spostano e si girano come uno solo, anche negli accoppiamenti,
in «Appoggia» e in «Metti nel vano», senza doverne fare un sottoassieme (la distinta non cambia: sono sempre i pezzi
di prima). Nell'albero il gruppo ha i suoi pezzi sotto; «Sciogli» li rende di nuovo liberi uno per uno.
Nel file: l'elenco ``gruppi`` dell'assieme (vedi cad_engine/assembly.py, _solve_gruppi); un assieme senza gruppi
si salva e si apre come prima.
"""
from __future__ import annotations

import numpy as np

from cad_engine import assembly as A


def _ok(**kw):
    return {'ok': True, **kw}


def _riga(R, T) -> list:
    return [float(x) for x in (R[0][0], R[0][1], R[0][2], T[0], R[1][0], R[1][1], R[1][2], T[1],
                               R[2][0], R[2][1], R[2][2], T[2], 0, 0, 0, 1)]


class GruppiMixin:
    # ------------------------------------------------------------------ aiuti per gli altri comandi
    def _stesso_gruppo(self, a: str, b: str) -> bool:
        capo = A.capi_dei_gruppi(self.asm)
        return a in capo and capo.get(a) == capo.get(b)

    def _movimento(self, iid: str, R1, T1):
        """Il movimento che porta iid da dove sta a (R1, T1): (DR, DT) con nuovo = DR · vecchio + DT."""
        i = self.asm.instance(iid)
        DR = np.array(R1, dtype=float) @ np.array(i['R'], dtype=float).T
        return DR, np.array(T1, dtype=float) - DR @ np.array(i['T'], dtype=float)

    def _sposta_compagni(self, iid: str, DR, DT, anche_lui: bool = False):
        """Gli altri pezzi bloccati con iid fanno lo stesso movimento (DR, DT); con anche_lui pure iid."""
        for x in A.compagni(self.asm, iid):
            if x == iid and not anche_lui:
                continue
            j = self.asm.instance(x)
            j['R'] = (DR @ np.array(j['R'], dtype=float)).tolist()
            j['T'] = (DR @ np.array(j['T'], dtype=float) + DT).tolist()

    def _pose_insieme(self, iid: str, R1, T1) -> dict:
        """Per l'anteprima (Appoggia, Metti nel vano): dove vanno iid e i pezzi bloccati con lui se iid va in (R1, T1)."""
        DR, DT = self._movimento(iid, R1, T1)
        out = {}
        for x in A.compagni(self.asm, iid):
            j = self.asm.instance(x)
            if x == iid:
                out[x] = _riga(np.array(R1, dtype=float), np.array(T1, dtype=float))
            else:
                out[x] = _riga(DR @ np.array(j['R'], dtype=float), DR @ np.array(j['T'], dtype=float) + DT)
        return out

    def _centro_gruppo(self, ids) -> np.ndarray | None:
        """Il centro dell'ingombro di più pezzi insieme (per girarli attorno al loro centro)."""
        bb = [b for b in (self._ingombro_mondo(self.asm.instance(x)) for x in ids) if b is not None]
        if not bb:
            return None
        return (np.min([b[0] for b in bb], axis=0) + np.max([b[1] for b in bb], axis=0)) / 2

    def _info_gruppo(self, iid: str) -> dict | None:
        """Per il pannello del pezzo: con chi è bloccato."""
        g = A.gruppo_di(self.asm, iid)
        if g is None:
            return None
        nomi = {i['id']: i['name'] for i in self.asm.instances}
        altri = [x for x in A.compagni(self.asm, iid) if x != iid]
        return {'id': g['id'], 'name': g.get('name') or 'Gruppo', 'altri': [nomi[x] for x in altri], 'ids': A.compagni(self.asm, iid)}

    def _nome_gruppo(self) -> str:
        usati = {g.get('name') for g in self.asm.gruppi}
        k = 1
        while f'Gruppo {k}' in usati:
            k += 1
        return f'Gruppo {k}'

    # ------------------------------------------------------------------ comandi
    def asm_blocca_insieme(self, ids: list, nome: str = '') -> dict:
        """Blocca insieme i pezzi ids così come stanno adesso. Se uno è già in un gruppo, i gruppi si uniscono."""
        if self.asm is None:
            return {'ok': False, 'code': 'assieme', 'message': 'Questo comando è per gli assiemi: apri o crea un assieme.'}
        scelti = list(dict.fromkeys(str(x) for x in (ids or [])))
        esito = {}

        def fn():
            for x in scelti:
                self.asm.instance(x)
            if len(scelti) < 2:
                raise A.AssemblyError('Scegli almeno due pezzi da bloccare insieme.')
            vecchi = [g for g in self.asm.gruppi if set(g.get('pezzi') or []) & set(scelti)]
            ordine = {i['id']: k for k, i in enumerate(self.asm.instances)}
            pezzi = set(scelti)
            for g in vecchi:
                pezzi |= {x for x in g.get('pezzi') or [] if x in ordine}
            pezzi = sorted(pezzi, key=ordine.get)
            gid = vecchi[0]['id'] if vecchi else self.asm.new_id('G', {g['id'] for g in self.asm.gruppi})
            nome_g = (nome or '').strip() or (vecchi[0].get('name') if vecchi else '') or self._nome_gruppo()
            self.asm.gruppi = [g for g in self.asm.gruppi if g not in vecchi] + [{'id': gid, 'name': nome_g, 'pezzi': pezzi}]
            esito.update(nome=nome_g, n=len(pezzi), uniti=len(vecchi))
            return {'select': pezzi[0], 'gruppo': gid}
        r = self._asm_change('Blocca insieme', fn)
        if r.get('ok'):
            r['message'] = (f'«{esito["nome"]}»: {esito["n"]} pezzi bloccati insieme, si muovono come uno solo. '
                            'La distinta non cambia. Per liberarli: tasto destro sul gruppo nell’albero, «Sciogli il gruppo».')
        return r

    def asm_sciogli_gruppo(self, gid: str) -> dict:
        """Scioglie il gruppo: i pezzi restano dove sono, ma ognuno torna libero (con i suoi accoppiamenti)."""
        if self.asm is None:
            return {'ok': False, 'code': 'assieme', 'message': 'Questo comando è per gli assiemi: apri o crea un assieme.'}
        esito = {}

        def fn():
            g = next((x for x in self.asm.gruppi if x['id'] == gid), None)
            if g is None:
                raise A.AssemblyError('Quel gruppo non c’è più.')
            self.asm.gruppi = [x for x in self.asm.gruppi if x['id'] != gid]
            esito['nome'] = g.get('name') or 'Gruppo'
            return {'select': (g.get('pezzi') or [None])[0]}
        r = self._asm_change('Sciogli il gruppo', fn)
        if r.get('ok'):
            r['message'] = f'«{esito["nome"]}» sciolto: i pezzi restano dove sono, ognuno si muove per conto suo.'
        return r

    def _togli_dai_gruppi(self, iid: str):
        """Il pezzo tolto dall'assieme esce dal suo gruppo; un gruppo con un pezzo solo non serve più."""
        for g in self.asm.gruppi:
            g['pezzi'] = [x for x in g.get('pezzi') or [] if x != iid]
        self.asm.gruppi = [g for g in self.asm.gruppi if len(g['pezzi']) >= 2]

    def _albero_gruppi(self, figli: list) -> list:
        """Nell'albero i pezzi bloccati insieme stanno sotto il loro gruppo (al posto del primo)."""
        capo = A.capi_dei_gruppi(self.asm)
        if not capo:
            return figli
        out, nodi = [], {}
        for n in figli:
            c = capo.get(n.get('ref')) if n.get('kind') == 'instance' else None
            if c is None:
                out.append(n)
                continue
            if c not in nodi:
                g = A.gruppo_di(self.asm, c)
                nodi[c] = {'label': g.get('name') or 'Gruppo', 'kind': 'rigido', 'ref': g['id'], 'children': [],
                           'status': None}
                out.append(nodi[c])
            nodi[c]['children'].append(n)
        return out

    def _senza_accoppiamenti_tra(self, a: str, b: str) -> list:
        """Gli accoppiamenti, tolti quelli tra i due pezzi (Appoggia, Metti nel vano li rifanno). Con i pezzi bloccati
        insieme anche quelli tra i loro gruppi: tenerli farebbe due posti diversi per lo stesso gruppo."""
        ga, gb = set(A.compagni(self.asm, a)), set(A.compagni(self.asm, b))
        return [m for m in self.asm.mates if not ((m['a']['inst'] in ga and m['b']['inst'] in gb)
                                                  or (m['a']['inst'] in gb and m['b']['inst'] in ga))]
