"""Comandi dello stato del disegno (05/11): «Chiudi» le estremità vicine, «Sistema il disegno».

La parte di calcolo sta in cad_engine/sketch/stato.py e sistema.py; qui si lavora sullo sketch del documento."""
from __future__ import annotations

import copy

from cad_engine.errors import SketchError
from cad_engine.sketch import sistema, solve
from cad_engine.sketch import stato as st


def _rimetti(sk, nuovo) -> None:
    sk.entities, sk.constraints = nuovo.entities, nuovo.constraints
    sk.__dict__.pop('_ultimi_id', None)


def _pulito(sk, params) -> bool:
    try:
        return solve(sk, params).status.state in ('completo', 'parziale')
    except SketchError:
        return False


def _sciogli(sk, params, toccati: set) -> list | None:
    """Dopo l'unione il contorno è chiuso e una quota di prima ora è decisa dalle altre (il disegno a mano quota
    ogni tratto): si toglie quella che litiga, tra le quote dei tratti toccati, la più nuova prima. None se non basta."""
    from cad_engine.sketch.model import DIMENSIONS
    tolte = []
    for _giro in range(4):
        try:
            stt = solve(sk, params).status
        except SketchError:
            return None
        if stt.state in ('completo', 'parziale'):
            return tolte
        male = set(stt.conflicting) | set(stt.redundant)
        cand = [k for k in male if k in sk.constraints and set(sk.constraints[k]['refs']) & toccati
                and not sk.constraints[k].get('driven')]
        if not cand:
            return None
        num = lambda k: int(k[1:]) if k[1:].isdigit() else 0  # noqa: E731
        k = max(cand, key=lambda k: (sk.constraints[k]['type'] in DIMENSIONS, num(k)))
        tolte.append(sk.describe_constraint(k))
        del sk.constraints[k]
    return None


def chiudi(doc, sid: str) -> dict:
    """Unisce le estremità aperte vicine (entro stato.CHIUDI_TOL). Se il contorno chiuso rende di troppo una quota
    dei tratti toccati, quella si toglie; se nemmeno così va, la coppia si lascia com'è.
    Rende {'unite': n, 'lasciate': n, 'tolte': [quote tolte]}."""
    sk = doc.sketch(sid)
    params = doc.resolved_parameters()
    ss = solve(sk, params)
    coppie = st.estremita_aperte(sk, ss)['coppie']
    if not coppie:
        raise SketchError('Non ci sono estremità vicine da unire.', code='niente_da_chiudere')
    prova = copy.deepcopy(sk)
    prova.__dict__.pop('_ultimi_id', None)
    era_pulito = _pulito(sk, params)
    unite, lasciate, tolte = 0, 0, []
    for c in coppie:
        dopo = copy.deepcopy(prova)
        toccati = {c['a'], c['b']} | {k for k, e in dopo.entities.items()
                                      if any(e.get(x) in (c['a'], c['b']) for x in ('a', 'b', 'start', 'end'))}
        st.unisci_estremita(dopo, [c])
        via = []
        if era_pulito:
            via = _sciogli(dopo, params, toccati)
            if via is None:
                lasciate += 1
                continue
        prova = dopo
        unite += 1
        tolte += via
    if not unite:
        raise SketchError('Queste estremità hanno già le loro quote: unirle le farebbe litigare. Cambia una quota '
                          'o sposta il punto a mano.', code='quote')
    _rimetti(sk, prova)
    return {'unite': unite, 'lasciate': lasciate, 'tolte': tolte}


def _punto_medio(nuovo, k):
    e = nuovo.entities[k]
    if e['kind'] == 'line':
        a, b = nuovo.entities[e['a']], nuovo.entities[e['b']]
        return [(a['x'] + b['x']) / 2, (a['y'] + b['y']) / 2]
    c = nuovo.entities[e['center']]
    return [c['x'], c['y']]


def _comune(nuovo, a, b):
    """Il punto in comune tra due curve (dove sono tangenti)."""
    pa = {nuovo.entities[a].get(x) for x in ('a', 'b', 'start', 'end')} - {None}
    pb = {nuovo.entities[b].get(x) for x in ('a', 'b', 'start', 'end')} - {None}
    p = next(iter(pa & pb), None)
    if p is None:
        return _punto_medio(nuovo, a)
    return [nuovo.entities[p]['x'], nuovo.entities[p]['y']]


def anteprima(doc, sid: str, tipi=sistema.TIPI) -> dict:
    """Cosa metterebbe «Sistema il disegno», con i posti (coordinate dello sketch) per l'anteprima.
    Si contano sempre tutti i tipi (per le caselle), i segni solo dei tipi scelti."""
    sk = doc.sketch(sid)
    params = doc.resolved_parameters()
    tutti, info_t = sistema.prova(sk, params, sistema.TIPI)
    nuovo, info = sistema.prova(sk, params, tipi) if set(tipi) != set(sistema.TIPI) else (tutti, info_t)
    segni = {'hv': [], 'uniti': [], 'tangenti': [], 'uguali': []}
    for kid in info['nuovi']['hv']:
        c = nuovo.constraints[kid]
        segni['hv'].append({'id': c['refs'][0], 'xy': _punto_medio(nuovo, c['refs'][0]),
                            'tipo': 'H' if c['type'] == 'horizontal' else 'V'})
    for via in info['nuovi']['uniti']:
        e = sk.entities.get(via)
        if e:
            segni['uniti'].append({'xy': [e['x'], e['y']]})
    for kid in info['nuovi']['tangenti']:
        a, b = nuovo.constraints[kid]['refs']
        segni['tangenti'].append({'ids': [a, b], 'xy': _comune(nuovo, a, b)})
    for kid in info['nuovi']['uguali']:
        a, b = nuovo.constraints[kid]['refs']
        segni['uguali'].append({'ids': [a, b], 'xy': [_punto_medio(nuovo, a), _punto_medio(nuovo, b)]})
    try:
        ss = solve(nuovo, params)
        dopo = st.frase_misure(ss.status.state, ss.status.dof)
    except SketchError:
        dopo = ''
    conti = dict(info_t['conti'])
    return {'conti': conti, 'scelti': info['conti'], 'segni': segni, 'dopo': dopo,
            'sbloccati': info_t['conti']['sbloccati']}


def applica(doc, sid: str, tipi=sistema.TIPI) -> dict:
    sk = doc.sketch(sid)
    nuovo, info = sistema.prova(sk, doc.resolved_parameters(), tipi)
    c = info['conti']
    if not any(c[t] for t in sistema.TIPI) and not c['sbloccati']:
        raise SketchError('Nel disegno non c’è niente da sistemare: le relazioni ci sono già.', code='niente')
    _rimetti(sk, nuovo)
    return c


def frase(c: dict) -> str:
    """«4 orizzontali e verticali, 8 tangenze, 3 uguali»"""
    pezzi = []
    if c.get('uniti'):
        pezzi.append('1 punto unito' if c['uniti'] == 1 else f'{c["uniti"]} punti uniti')
    if c.get('hv'):
        pezzi.append('1 orizzontale o verticale' if c['hv'] == 1 else f'{c["hv"]} orizzontali e verticali')
    if c.get('tangenti'):
        pezzi.append('1 tangenza' if c['tangenti'] == 1 else f'{c["tangenti"]} tangenze')
    if c.get('uguali'):
        pezzi.append('1 uguale' if c['uguali'] == 1 else f'{c["uguali"]} uguali')
    return ', '.join(pezzi)


# ============================================================================ nel servizio
def _tipi(tipi):
    if not tipi:
        return sistema.TIPI
    t = tuple(x for x in tipi if x in sistema.TIPI)
    return t


class StatoSketchMixin:
    """Le chiamate dell'interfaccia: Chiudi, Sistema il disegno, Importa SVG (05/11)."""
    _svg = None                       # l'ultimo SVG letto

    def sketch_chiudi(self, sid: str) -> dict:
        from app.service import _err
        fatto = {}
        r = self._sketch_change('Chiudi le estremità vicine', lambda: fatto.update(chiudi(self.doc, sid)))
        if not r.get('ok'):
            return r if r.get('message') else _err(SketchError('Non si è potuto chiudere.'))
        n, lasc = fatto.get('unite', 0), fatto.get('lasciate', 0)
        tolte = fatto.get('tolte') or []
        r['message'] = ('Unite 2 estremità: ora si toccano.' if n == 1 else f'Unite {n} coppie di estremità.') + (
            f' Tolta {tolte[0]}: ora la decide il contorno chiuso.' if len(tolte) == 1 else
            f' Tolte {len(tolte)} quote: ora le decide il contorno chiuso.' if tolte else '') + (
            f' {lasc} lasciate com’erano: unirle avrebbe fatto litigare le quote.' if lasc else '')
        return r

    def sketch_sistema_anteprima(self, sid: str, tipi=None) -> dict:
        from app.service import _err, _ok
        try:
            return _ok(**anteprima(self.doc, sid, _tipi(tipi)))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def sketch_sistema(self, sid: str, tipi=None) -> dict:
        fatto = {}
        r = self._sketch_change('Sistema il disegno', lambda: fatto.update(applica(self.doc, sid, _tipi(tipi))))
        if r.get('ok'):
            cosa = frase(fatto)
            sb = fatto.get('sbloccati', 0)
            r['message'] = 'Disegno sistemato' + (f': {cosa}' if cosa else '') + '.' + (
                ' I punti non sono più bloccati: ora si quota (resta fermo un punto solo).' if sb else '')
        return r

    # ---------------------------------------------------------------- SVG
    def svg_leggi(self, path: str) -> dict:
        from app.service import _err, _ok
        from cad_engine.importers import svg_import
        try:
            self._svg = svg_import.leggi(path)
            d = self._svg
            from pathlib import Path
            return _ok(file=d.file, name=Path(d.file).stem, w=round(float(d.larghezza_mm), 2), h=round(float(d.altezza_mm), 2),
                       testi=d.testi, tracciati=len(d.sottotracciati), cerchi=len(d.cerchi))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def _svg_geo(self, opz: dict):
        from app.service import _numero
        from cad_engine.errors import SteelCADError
        from cad_engine.importers import svg_import
        if self._svg is None:
            raise SteelCADError('Prima scegli il file SVG.', code='svg')
        o = opz or {}
        w = _numero(o.get('larghezza'), 'la larghezza')
        x0 = _numero(o.get('x') if o.get('x') not in (None, '') else 0, 'la X')
        y0 = _numero(o.get('y') if o.get('y') not in (None, '') else 0, 'la Y')
        geo = svg_import.geometria(self._svg, w, x0, y0)
        if o.get('centro'):                      # (x, y) è il centro del disegno, non l'angolo in basso a sinistra
            geo = svg_import.geometria(self._svg, w, x0 - geo['w'] / 2, y0 - geo['h'] / 2)
        return geo

    def sketch_svg_anteprima(self, sid: str, opz: dict) -> dict:
        from app.service import _err, _ok
        from cad_engine.importers import svg_import
        try:
            geo = self._svg_geo(opz)
            return _ok(polilinee=svg_import.polilinee(geo), w=round(float(geo['w']), 2), h=round(float(geo['h']), 2),
                       pezzi=sum(len(g) for g in geo['giri']) + len(geo['cerchi']))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def sketch_svg_inserisci(self, sid: str, opz: dict) -> dict:
        from app.service import _err
        from cad_engine.importers import svg_import
        try:
            geo = self._svg_geo(opz)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        n = {}
        from pathlib import Path
        nome = Path(self._svg.file).stem
        r = self._sketch_change(f'Importa SVG «{nome}»',
                                lambda: n.update(svg_import.nello_sketch(self.doc.sketch(sid), geo)))
        if r.get('ok'):
            pezzi = [f'{n[k]} {nomi[n[k] == 1]}' for k, nomi in (('linee', ('linee', 'linea')), ('archi', ('archi', 'arco')),
                                                                ('cerchi', ('cerchi', 'cerchio'))) if n.get(k)]
            r['message'] = f'Importato {nome}: ' + ', '.join(pezzi) + '. «Sistema il disegno» lo rende quotabile.'
        return r
