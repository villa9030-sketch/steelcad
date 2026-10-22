"""Lavorazioni sui tubi, lato applicazione: clic su una faccia di un'asta → sketch su quella faccia → buca.

Come sulla lamiera: si disegna sulla faccia (zero sulla testa del tubo e sul bordo della faccia, bordi in arancio),
si esce e la sagoma buca la parete (o le due pareti, passante). Si può ripetere sui tubi uguali.
"""
from __future__ import annotations

from cad_engine import SteelCADError
from cad_engine.structures import lavorazioni
from cad_engine.units import fmt_mm


class TubiMixin:
    def _asta(self, obj_id: str):
        st_id, _, mid = obj_id.partition('/')
        st = next((s for s in self.result.structures if s.id == st_id), None)
        m = next((x for x in st.members if x.id == mid), None) if st else None
        if m is None:
            raise SteelCADError(f'L’asta {obj_id} non c’è.', code='asta')
        return st, m

    def tubi_uguali(self, obj_id: str) -> list[str]:
        """Le aste uguali a questa (stesso tubo, stessa lunghezza e stessi tagli): dove ripetere una lavorazione."""
        st, m = self._asta(obj_id)
        firma = (m.profile, round(m.length, 1), tuple(sorted(round(a, 1) for a in m.cuts)))
        return [x.id for x in st.members
                if (x.profile, round(x.length, 1), tuple(sorted(round(a, 1) for a in x.cuts))) == firma]

    def sketch_on_tube(self, obj_id: str, normal) -> dict:
        """La faccia del tubo cliccata (quella più rivolta come `normal`) diventa il piano di uno sketch nuovo."""
        try:
            st, m = self._asta(obj_id)
            lavorazioni.check(m)
            side = lavorazioni.side_from_normal(m, normal)
        except SteelCADError as ex:
            return {'ok': False, 'code': ex.code or 'tubo', 'message': ex.message}
        nuovo = {}

        def fn():
            from app import sketch_ops
            dove = lavorazioni.describe_side(m, side)
            sk = self.doc.add_sketch({'tube': st.id, 'member': m.id, 'side': side},
                                     f'Lavorazione {m.id} ({dove})')
            faccia = lavorazioni.face_of(m, side)
            if faccia is not None:          # i bordi della faccia in arancio: ci si aggancia e ci si quota
                sketch_ops.add_reference_edges(sk, faccia, lavorazioni.face_plane(m, side))   # niente pieghe: gli spigoli tondi del tubo non lo sono
            nuovo['id'] = sk.id
        r = self._change('Sketch sul tubo', fn)
        if r['ok']:
            r['sketch'] = nuovo['id']
            r['message'] = (f'Disegna sulla faccia {lavorazioni.describe_side(m, side)} di {m.label()}: lo zero è la '
                            f'testa del tubo e il bordo della faccia. Il tubo è lungo {fmt_mm(round(m.length, 1))} mm.')
        return r

    def lavora_tubo(self, sid: str, through: bool = False, anche_uguali: bool = False, nome: str = '') -> dict:
        """Dallo sketch sul tubo: la sagoma buca la parete (passante: anche quella di fronte)."""
        try:
            sk = self.doc.sketch(sid)
            pl = sk.plane if isinstance(sk.plane, dict) else {}
            if not pl.get('tube'):
                return {'ok': False, 'code': 'tubo', 'message': 'Questo sketch non sta su un tubo.'}
            obj = f'{pl["tube"]}/{pl["member"]}'
            aste = self.tubi_uguali(obj) if anche_uguali else [pl['member']]
            aste = [pl['member']] + [a for a in aste if a != pl['member']]
        except SteelCADError as ex:
            return {'ok': False, 'code': ex.code or 'tubo', 'message': ex.message}

        def fn():
            self.doc.add_feature('tube_cut', nome or 'Lavorazione', sketch=sid, structure=pl['tube'], side=pl['side'],
                                 members=aste, through=bool(through))
        r = self._change('Lavorazione sul tubo', fn)
        if r['ok']:
            r['message'] = ('Fatto' + (f' su {len(aste)} tubi uguali' if len(aste) > 1 else '') +
                            (', passante.' if through else '.') + ' Nella cut list il tubo lavorato ha la sua riga.')
        return r
