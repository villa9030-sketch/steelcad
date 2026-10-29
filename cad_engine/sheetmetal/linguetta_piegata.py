"""Linguetta tagliata e piegata (29/10, Stefano: «ho fatto questo taglio a U nella lamiera, poi ho disegnato la linea
dove piegare per creare una specie di maniglia ma non lo posso fare»).

La linea di piega non attraversa tutta la lamiera: le sue punte toccano un taglio (a U, a C…) e la parte chiusa tra
il taglio e la linea è la linguetta. Si piega solo lei, sulla linea; il resto della lamiera resta fermo e lo sviluppo
resta quello disegnato. La linea, come nelle altre pieghe su linea, è lo spigolo vivo esterno della piega.

Come si fa: sullo sviluppo si toglie la linguetta più la striscia tra la linea e l'inizio della piega (l'arretramento
esterno), poi sul bordo libero che ne nasce si fa la piega su un bordo, alta quanto serve perché lo sviluppo torni
quello di prima. Se la punta della linguetta non è dritta (U con il fondo tondo) quello che la striscia ha in più si
toglie sulla faccia della piega.
"""
from __future__ import annotations

import types

import build123d as bd

from ..errors import FeatureError
from ..expressions import evaluate
from ..units import TOL, fmt_mm


def _punti(f, n=16):
    """Punti sul contorno di una faccia, anche a metà degli archi (il fondo tondo di una U)."""
    return [p for e in f.edges() for p in e.positions([i / n for i in range(n + 1)])]


def trova(flat, pl, a2, b2, flip=False):
    """La linguetta della linea a2–b2 (coordinate dello sviluppo): (pezzo, C0, C1, u, n) con n verso la linguetta,
    oppure None se la linea non chiude nessuna parte (allora è una piega che attraversa la lamiera)."""
    from . import _facce, _orienta
    A, B = pl.from_local_coords(tuple(a2)), pl.from_local_coords(tuple(b2))
    L = (B - A).length
    if L < 1e-6:
        return None
    u = (B - A).normalized()
    n0 = u.cross(pl.z_dir).normalized()
    G = 1e5
    lati = []
    for sgn in (1, -1):
        n = n0 * sgn
        meta = _orienta(bd.Face(bd.Wire.make_polygon([A - u * G, A + u * G, A + u * G + n * G, A - u * G + n * G],
                                                     close=True)), pl)
        toccano, chiuse = 0, []
        for p in _facce(flat & meta):
            sulla = [bd.Vector(v) for v in p.vertices() if abs((bd.Vector(v) - A).dot(n)) < 1e-6]
            if len(sulla) < 2:
                continue
            toccano += 1
            us = [(q - A).dot(u) for q in sulla]
            if min(us) >= -1e-3 and max(us) <= L + 1e-3:     # tocca la linea solo dentro il tratto disegnato
                chiuse.append((p, A + u * min(us), A + u * max(us), u, n))
        # una linguetta solo se di qua dalla linea c'è anche altra lamiera (oltre il taglio): se no la linea
        # attraversa la lamiera ed è una piega normale
        if toccano >= 2:
            lati.extend(chiuse)
    if not lati:
        return None
    lati.sort(key=lambda x: x[0].area)
    if flip:
        if len(lati) < 2:
            raise FeatureError('Dall’altra parte della linea non c’è una linguetta chiusa dal taglio: togli «piega '
                               'l’altra parte».')
        return lati[1]
    return lati[0]


def build(fdef: dict, ctx):
    from . import _cut_from_flat, _facce, _orienta, bend_values
    from .edge_flange import build_edge_flange, mappa_faccia
    fid = fdef['id']
    body = ctx.body
    data = getattr(body, 'sheet', None) if body is not None else None
    if data is None or data.flat is None:
        raise FeatureError('La linguetta piegata si fa su una lamiera.', feature=fid)
    t, tech, pl = data.thickness, data.tech, data.plane
    # tutte le linee della linguetta; la prima piega è quella alla radice (la linguetta più grande), anche se è stata
    # disegnata dopo (29/10: prima la piega a metà, poi quella dove finisce il taglio)
    linee = [{'a': fdef['a'], 'b': fdef['b'], 'angle': fdef.get('angle', 90), 'direction': fdef.get('direction', 'up'),
              'flip': fdef.get('flip')}] + [dict(x) for x in fdef.get('altre') or []]
    trovate = []
    for k, x in enumerate(linee):
        try:
            tr = trova(data.flat, pl, x['a'], x['b'], bool(x.get('flip')) if k == 0 else False)
        except FeatureError as ex:
            raise FeatureError(ex.message, feature=fid) from None
        if tr is not None:
            trovate.append((tr[0].area, k, tr))
    if not trovate:
        raise FeatureError('Le punte della linea devono toccare il taglio che fa la linguetta (a U): allungala fino al '
                           'taglio, da tutte e due le parti.', feature=fid)
    _area, radice, trovata = max(trovate, key=lambda x: x[0])
    tab, C0, C1, u, n = trovata
    prima = linee.pop(radice)
    fdef = {**fdef, 'angle': prima['angle'], 'direction': prima['direction'], 'altre': linee}
    ang = evaluate(fdef.get('angle', 90), ctx.params, what=f'l’angolo della linguetta {fid}')
    if not 0 < ang < 180:
        raise FeatureError('L’angolo della piega va da 1 a 179°.', feature=fid)
    if tech['radius'] is None:
        from . import _manca
        raise FeatureError(_manca('il raggio interno di piega (quello del punzone)'), feature=fid, code='manca_tecnologia')
    b = bend_values(ang, tech['radius'], t, tech['method'], tech['k'], tech['bd90'], fid)
    pts = _punti(tab)
    us = [(p - C0).dot(u) for p in pts]
    corda = (C1 - C0).length
    if min(us) < -1e-3 or max(us) > corda + 1e-3:
        raise FeatureError('La linguetta è più larga della linea di piega: la linea va dove la linguetta è più larga '
                           '(di solito dove finisce il taglio).', feature=fid)
    dmax = max((p - C0).dot(n) for p in pts)
    # 29/10: altre linee dentro la linguetta (parallele alla prima): pieghe in catena sulla sua punta (la maniglia)
    pieghe = [(0.0, ang, fdef.get('direction', 'up'), b)]
    for k, x in enumerate(fdef.get('altre') or [], 2):
        A2, B2 = pl.from_local_coords(tuple(x['a'])), pl.from_local_coords(tuple(x['b']))
        if (B2 - A2).length < 1e-6 or abs((B2 - A2).normalized().dot(n)) > 1e-3:
            raise FeatureError(f'La piega {k} della linguetta va parallela alla prima.', feature=fid)
        a_k = evaluate(x.get('angle', 90), ctx.params, what=f'l’angolo della piega {k} della linguetta {fid}')
        if not 0 < a_k < 180:
            raise FeatureError('L’angolo della piega va da 1 a 179°.', feature=fid)
        if (A2 - C0).dot(n) <= 1e-6:
            raise FeatureError(f'La piega {k} della linguetta va dentro la linguetta, oltre la prima piega.', feature=fid)
        pieghe.append(((A2 - C0).dot(n), a_k, x.get('direction', 'up'),
                       bend_values(a_k, tech['radius'], t, tech['method'], tech['k'], tech['bd90'], fid)))
    pieghe.sort(key=lambda x: x[0])
    bordi = [s_ - bb.ossb for s_, _a, _d, bb in pieghe]           # dove comincia ogni piega, sullo sviluppo
    fine = bordi[1:] + [dmax]
    for k, (s_, _a, _d, bb) in enumerate(pieghe):
        if fine[k] - bordi[k] - bb.ba <= TOL or (k and s_ >= dmax):
            raise FeatureError('La linguetta è troppo corta per queste pieghe: tra una piega e l’altra (e fino alla '
                               'punta) ci vuole un tratto dritto.', feature=fid)
    # la piega parte prima della linea (arretramento esterno): quella striscia va via insieme alla linguetta
    E0, E1 = C0 + n * bordi[0], C1 + n * bordi[0]
    striscia = _orienta(bd.Face(bd.Wire.make_polygon([E0, E1, C1, C0], close=True)), pl)
    regione = _facce(tab.fuse(striscia).clean())
    avvisi = []
    for P, s in ((E0 * 0.5 + C0 * 0.5, -1), (E1 * 0.5 + C1 * 0.5, 1)):
        if data.flat.is_inside(P + u * (s * 0.3)):
            avvisi.append(P)
    tagliato = _cut_from_flat({'id': fid}, body, data, regione, t)
    base = data.feature
    if not tagliato.names.get(f'{base}/sopra'):
        raise FeatureError('La linguetta piegata si fa sulla base della lamiera.', feature=fid)
    fascia = lambda d0, d1, largo=0.0: _orienta(bd.Face(bd.Wire.make_polygon(  # noqa: E731
        [C0 + n * d0 - u * largo, C1 + n * d0 + u * largo, C1 + n * d1 + u * largo, C0 + n * d1 - u * largo], close=True)), pl)
    nuovo, faccia, ids = tagliato, f'{base}/sopra', []
    for k, (s_, a_k, verso, bb) in enumerate(pieghe):
        id_k = fid if k == 0 else f'{fid}.{k + 1}'
        ids.append(id_k)
        # la prima sul bordo nato dal taglio (faccia di sopra della base), le altre sulla punta della precedente
        src, dst, dentro = mappa_faccia(faccia, nuovo.sheet, fid)
        dentro = bd.Vector(dentro).normalized()
        sul_pezzo = lambda p, src=src, dst=dst: src.from_local_coords(dst.to_local_coords(p))  # noqa: E731
        a3, b3 = sul_pezzo(C0 + n * bordi[k]), sul_pezzo(C1 + n * bordi[k])
        # verso: «su» = dalla parte della faccia di sopra dello sketch (la normale dello sviluppo, girata dalle pieghe)
        voglio = sul_pezzo(pl.origin + pl.z_dir * (1 if verso == 'up' else -1)) - sul_pezzo(pl.origin)
        centro = bd.Vector(bd.Shape.cast(nuovo.shape).center())
        lato = 1 if (centro - (a3 + b3) * 0.5).dot(dentro) > 0 else -1
        sig = 1 if voglio.dot(dentro) > 0 else -1
        pezzo = [y for x in regione for y in _facce(x & fascia(bordi[k], fine[k] if k + 1 < len(pieghe) else dmax + 10, 10))]
        fl = {'id': id_k, 'face': faccia, 'a': list(a3), 'b': list(b3), 'length': fine[k] - bordi[k] - bb.ba + bb.ossb,
              'angle': a_k, 'side': 'in' if sig == lato else 'out', 'trim0': 0, 'trim1': 0,
              '_sviluppo': pezzo[0] if len(pezzo) == 1 else None}
        try:
            nuovo = build_edge_flange(fl, types.SimpleNamespace(params=ctx.params, body=nuovo))
        except FeatureError as ex:
            msg = ex.message
            if 'tocca' in msg:
                msg = 'La linguetta piegata tocca un’altra parte del pezzo: cambia il verso o l’angolo.'
            raise FeatureError(msg, feature=fid) from None
        faccia = f'{id_k}/esterno'
    # la punta non dritta: quello che le strisce delle pieghe hanno in più rispetto al disegno, tolto nel pezzo
    # piegato nei tratti dritti; dentro le pieghe (pochi decimi se i lati si stringono subito) resta pieno: lo
    # sviluppo per il laser ha comunque la forma esatta
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec

    from . import _taglia_ricordando
    attrezzi = []
    tutta = bd.Compound(children=regione) if len(regione) > 1 else regione[0]
    for k, (s_, a_k, verso, bb) in enumerate(pieghe):
        pieno = fascia(bordi[k], fine[k])
        via = [y for x in _facce(pieno - tutta) for y in _facce(x & fascia(bordi[k] + bb.ba, fine[k] + 10, 10))
               if y.area > 1e-4]
        if not via:
            continue
        s3, d3, v3 = nuovo.sheet.pannelli[f'{ids[k]}/esterno']
        loc, v = s3.location * d3.location.inverse(), bd.Vector(v3).normalized() * (t + 0.02)
        attrezzi += [bd.Shape.cast(BRepPrimAPI_MakePrism(x.moved(loc).wrapped, gp_Vec(v.X, v.Y, v.Z)).Shape()) for x in via]
    if attrezzi:
        sheet = nuovo.sheet
        nuovo, ricorda = _taglia_ricordando(fid, nuovo, attrezzi)
        ricorda()
        nuovo.sheet = sheet
    if avvisi:
        import dataclasses
        nuovo.sheet = dataclasses.replace(nuovo.sheet, warnings=list(nuovo.sheet.warnings) + [
            f'Linguetta {fid}: il taglio finisce sulla linea di piega; per piegare senza strappare allunga i tagli '
            f'ai lati di almeno {fmt_mm(round(b.ossb + t, 1))} mm oltre la linea (scarico).'])
    # su / giù come li ha scelti l'utente (verso la faccia di sopra dello sviluppo): quello della piega su un bordo è
    # verso lo spessore, e nel DXF per la piegatrice risultava rovesciato
    versi = {id_k: pieghe[k][2] for k, id_k in enumerate(ids)}
    linee = []
    for a_, b_, testo in nuovo.sheet.bend_lines:
        parti = str(testo).split(' ')
        if parti[0] in versi and len(parti) > 1:
            parti[1] = 'SU' if versi[parti[0]] == 'up' else 'GIÙ'
            testo = ' '.join(parti)
        linee.append((a_, b_, testo))
    righe = []
    for r in nuovo.sheet.extra_bends or []:
        if r.get('flange') in ids:
            r = {**r, 'edge': 'linguetta', 'direction': versi[r['flange']]}
        righe.append(r)
    import dataclasses
    nuovo.sheet = dataclasses.replace(nuovo.sheet, bend_lines=linee, extra_bends=righe)
    return nuovo
