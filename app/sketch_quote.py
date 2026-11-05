"""Quote che cambiano tipo con un clic (05/11, idee da SolidCraft):

- raggio ↔ diametro (su cerchi e archi) e, sugli archi, lo sviluppo (la lunghezza lungo l'arco: il pezzo da
  calandrare o il nastro da tagliare);
- quota normale ↔ quota di riferimento (tra parentesi: mostra la misura, non comanda).

Il disegno non si muove: la quota nuova parte dalla misura che c'è adesso. Se la misura nuova la decidono già le
altre quote, resta di riferimento (come quando la si mette a mano).
"""
from __future__ import annotations

from cad_engine.errors import SketchError
from cad_engine.sketch import solve
from cad_engine.sketch.solver import misura

from app import sketch_ops

_r = sketch_ops._r
TONDE = ('radius', 'diameter', 'arclength')


def _quota(sk, did):
    c = sk.constraints.get(did)
    if c is None:
        raise SketchError('Questa quota non c’è più.')
    return c


def _misura_ora(doc, sk, c):
    return misura(solve(sk, doc.resolved_parameters()), c)


def _guai(doc, sk, did):
    st = solve(sk, doc.resolved_parameters()).status
    return did in st.conflicting or did in st.redundant


def _scritta(v, fattore):
    """Una quota scritta come formula (W, «2*W») cambiata di un fattore, ancora leggibile."""
    if fattore == 1:
        return v
    if fattore == 2:
        return f'2*{v}' if str(v).isidentifier() else f'2*({v})'
    if fattore == 0.5:
        return f'{v}/2' if str(v).isidentifier() else f'({v})/2'
    return None


def change_kind(doc, sid: str, did: str, kind: str, info: dict | None = None) -> str:
    """Cambia una quota tonda in raggio, diametro o sviluppo. info['riferimento'] = True se è rimasta (o diventata)
    di riferimento perché la misura la decidono già le altre quote."""
    info = {} if info is None else info
    sk = doc.sketch(sid)
    c = _quota(sk, did)
    if c['type'] not in TONDE or kind not in TONDE:
        raise SketchError('Si passa da raggio a diametro (o allo sviluppo) solo sulle quote di cerchi e archi.')
    if c['type'] == kind:
        return did
    ref = c['refs'][0]
    tipo = sk.entities.get(ref, {}).get('kind')
    if kind == 'arclength' and tipo != 'arc':
        raise SketchError('Lo sviluppo si misura su un arco: un cerchio intero è la circonferenza (π × diametro).')
    vecchio = dict(c)
    nuovo = {**c, 'type': kind}
    v = c['value']
    if isinstance(v, (int, float)) and not isinstance(v, bool) or c.get('driven') or kind == 'arclength' \
            or c['type'] == 'arclength':
        nuovo['value'] = _r(_misura_ora(doc, sk, nuovo))            # la misura che c'è adesso: niente si muove
    else:
        fattore = {('radius', 'diameter'): 2, ('diameter', 'radius'): 0.5}[(c['type'], kind)]
        nuovo['value'] = _scritta(v, fattore)
    sk.constraints[did] = nuovo
    if not nuovo.get('driven') and _guai(doc, sk, did):
        nuovo['driven'] = True
        info['riferimento'] = True
        if _guai(doc, sk, did):                                      # non dovrebbe: si torna com'era
            sk.constraints[did] = vecchio
            raise SketchError('Non riesco a cambiare questa quota senza bloccare il disegno.')
    return did


def set_reference(doc, sid: str, did: str, rif: bool) -> str:
    """Quota di riferimento (tra parentesi, non comanda) o normale. Tornando normale parte dalla misura che c'è
    adesso; se quella misura la decidono già le altre quote, resta di riferimento e lo si dice."""
    sk = doc.sketch(sid)
    c = _quota(sk, did)
    if c['type'] not in ('length', 'distance', 'hdistance', 'vdistance', 'pldistance', 'angle') + TONDE:
        raise SketchError('Questa non è una quota.')
    if bool(c.get('driven')) == bool(rif):
        return did
    if rif:
        c['driven'] = True
        return did
    vecchio = dict(c)
    v = c['value']
    try:
        ora = misura(solve(sk, doc.resolved_parameters()), c)
    except (KeyError, ZeroDivisionError):
        ora = None
    del c['driven']
    if ora is not None and (isinstance(v, (int, float)) and not isinstance(v, bool)):
        c['value'] = _r(ora)
    if _guai(doc, sk, did):
        sk.constraints[did] = vecchio
        raise SketchError('Questa misura la decidono già le altre quote (o i bordi del pezzo): resta di riferimento. '
                          'Per farla comandare togli prima la quota che la decide.')
    return did
