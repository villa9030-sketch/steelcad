"""Piega su un bordo libero qualsiasi (21/10, Stefano: «aggiungo materiale su una piega, poi lo devo bordare»).

Un bordo dritto di una faccia piana della lamiera (anche del materiale aggiunto dopo) diventa una piega: altezza
«fuori tutto» dallo spigolo vivo esterno, angolo, verso dentro o fuori dal pezzo. La piega parte dal bordo (il
materiale si aggiunge oltre il bordo, come «dal bordo» delle flange); nello sviluppo oltre lo stesso bordo vanno la
striscia della piega (BA) e il tratto dritto steso. Le sue facce piane hanno un nome e la loro mappa verso lo
sviluppo: ci si disegna, si fora, e sul suo bordo si può piegare ancora.
"""
from __future__ import annotations

import dataclasses
import math

import build123d as bd

from ..errors import FeatureError
from ..expressions import evaluate
from ..units import TOL, fmt_mm


def mappa_faccia(nome: str, data, fid: str):
    """(piano sul pezzo, piano nello sviluppo, verso dentro il materiale) di una faccia piana con nome."""
    from . import _face_planes
    pannelli = getattr(data, 'pannelli', None) or {}
    if nome in pannelli:
        return pannelli[nome]
    src, dst, dentro, _g = _face_planes(nome.split('/'), data, fid)
    return src, dst, dentro


def bordo_sulla_faccia(facce, a0: bd.Vector, b0: bd.Vector):
    """Lo spigolo dritto (del contorno esterno delle facce) più vicino ai due punti salvati: (a, b) nello stesso
    ordine, o None."""
    best = None
    for f in facce:
        for e in bd.Face(f).outer_wire().edges():
            if e.geom_type != bd.GeomType.LINE:
                continue
            pa, pb = e.position_at(0), e.position_at(1)
            for x, y in ((pa, pb), (pb, pa)):
                d = (x - a0).length + (y - b0).length
                if best is None or d < best[0]:
                    best = (d, x, y)
    if best is None or best[0] > max(1.0, 0.5 * (b0 - a0).length):
        return None
    return best[1], best[2]


def mappa_spigoli(shape) -> dict:
    """spigolo -> facce che lo toccano (una volta per pezzo)."""
    # con OCP diretto: le facce e gli spigoli di ognuna senza i passaggi di build123d (0,3 s con 300 fori, 24/10);
    # stesse facce, stessi spigoli, nello stesso ordine (mappe indicizzate come fa build123d)
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as Mappa
    d: dict = {}
    mf = Mappa()
    TopExp.MapShapes_s(shape.wrapped if hasattr(shape, 'wrapped') else shape, TopAbs_FACE, mf)
    for i in range(1, mf.Extent() + 1):
        f = bd.Face(TopoDS.Face(mf(i)))
        me = Mappa()
        TopExp.MapShapes_s(f.wrapped, TopAbs_EDGE, me)
        for j in range(1, me.Extent() + 1):
            d.setdefault(bd.Edge(TopoDS.Edge(me(j))), []).append(f)
    return d


def fuori_dalla_vicina(faccia, spigolo, mappa, n):
    """Il bordo è libero se di là c'è il fianco sottile della lamiera (una faccia piana a squadra): il verso fuori è
    la sua normale. None se di là c'è una piega o altro."""
    d = (spigolo.position_at(1) - spigolo.position_at(0)).normalized()
    for g in mappa.get(spigolo, []):
        if g.wrapped.IsSame(faccia.wrapped) or g.geom_type != bd.GeomType.PLANE:
            continue
        ng = g.normal_at(g.center())
        if abs(ng.dot(n)) < 1e-6 and abs(ng.dot(d)) < 1e-6:
            return ng
    return None


def verso_fuori(faccia: bd.Face, solido, a, b, dentro, t):
    """Nel piano della faccia, perpendicolare al bordo, dalla parte dove non c'è materiale (o None se il bordo non
    è libero)."""
    e = (b - a).normalized()
    v = e.cross(dentro).normalized()
    m = (a + b) * 0.5 + dentro * (t / 2)
    pieno = lambda p: solido.is_inside(p)  # noqa: E731
    if pieno(m - v * 0.4) and not pieno(m + v * 0.4):
        return v
    if pieno(m + v * 0.4) and not pieno(m - v * 0.4):
        return -v
    return None


def build_edge_flange(fdef: dict, ctx):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse

    from ..features.base import volume
    from ..topology.naming import _faces_of
    from . import _orienta, bend_values, flat_size
    fid = fdef['id']
    body = ctx.body
    data = getattr(body, 'sheet', None) if body is not None else None
    if data is None:
        raise FeatureError('La piega su un bordo va fatta su una lamiera.', feature=fid)
    t, tech = data.thickness, data.tech
    nome = fdef.get('face', '')
    facce = body.names.get(nome) or []
    if not facce:
        raise FeatureError('La faccia di questa piega non c’è più (una modifica l’ha tolta).', feature=fid)
    src, dst, dentro = mappa_faccia(nome, data, fid)
    dentro = bd.Vector(dentro).normalized()
    trovato = bordo_sulla_faccia(facce, bd.Vector(*fdef['a']), bd.Vector(*fdef['b']))
    if trovato is None:
        raise FeatureError('Il bordo di questa piega non c’è più sulla sua faccia.', feature=fid)
    a, b = trovato
    solido = bd.Shape.cast(body.shape)
    mappa = mappa_spigoli(body.shape)
    fuori = None
    for f in facce:
        F = bd.Face(f)
        for sp in F.outer_wire().edges():
            if sp.geom_type == bd.GeomType.LINE and (sp.position_at(0) - a).length + (sp.position_at(1) - b).length < 1e-6                     or sp.geom_type == bd.GeomType.LINE and (sp.position_at(1) - a).length + (sp.position_at(0) - b).length < 1e-6:
                fuori = fuori_dalla_vicina(F, sp, mappa, -dentro)
                break
        if fuori is not None:
            break
    if fuori is None:
        if nome in (getattr(data, 'pannelli', None) or {}) and (getattr(data, 'shape_info', None) or {}).get('kind') == 'sezioni':
            raise FeatureError('Questo bordo non è libero o è tagliato di sbieco. Sulla tramoggia il bordo in alto e la '
                               'flangia dello scarico si mettono dalle misure della forma (Modifica → Bordo, Flangia '
                               'scarico).', feature=fid)
        raise FeatureError('Questo bordo non è libero: oltre c’è già lamiera.', feature=fid)

    def val(k, d, cosa):
        v = fdef.get(k)
        return d if v in (None, '') else evaluate(v, ctx.params, what=f'{cosa} della piega {fid}')
    lung, ang = val('length', None, 'l’altezza'), val('angle', 90.0, 'l’angolo')
    r = tech['radius']
    if not 0 < ang < 180:
        raise FeatureError('L’angolo della piega va da 1 a 179°.', feature=fid)
    piega = bend_values(ang, r, t, tech['method'], tech['k'], tech['bd90'], fid)
    if lung is None or lung - piega.ossb <= TOL:
        raise FeatureError(f'La piega deve essere alta più di {fmt_mm(round(piega.ossb, 2))} mm.', feature=fid)
    # verso: «dentro» = dalla parte del pezzo
    centro = bd.Vector(solido.center())
    lato = 1 if (centro - (a + b) * 0.5).dot(dentro) > 0 else -1
    sig = lato if fdef.get('side', 'in') != 'out' else -lato         # +1 = si piega verso «dentro» (lo spessore)
    e = (b - a).normalized()
    th = math.radians(ang)
    nb = dentro * sig
    w_in = t if sig > 0 else 0.0
    dir_ = lambda f: -nb * math.cos(f) + fuori * math.sin(f)  # noqa: E731
    T = nb * math.sin(th) + fuori * math.cos(th)
    R_ = r + t
    dritto = lung - piega.ossb
    v0 = volume(body.shape)

    def prova(t0, t1):
        """La piega accorciata di t0 all'inizio e t1 alla fine del bordo: (pezzo, nuovo, a, b) o None se tocca."""
        a_, b_ = a + e * t0, b - e * t1
        L = (b_ - a_).length
        if L <= TOL or (b_ - a_).dot(e) <= 0:
            return None
        C = a_ + dentro * w_in + nb * r
        Ao, Bo, Mo = C + dir_(0) * R_, C + dir_(th) * R_, C + dir_(th / 2) * R_
        Ai, Bi, Mi = C + dir_(0) * r, C + dir_(th) * r, C + dir_(th / 2) * r
        lati = [bd.Edge.make_three_point_arc(Ao, Mo, Bo), bd.Edge.make_line(Bo, Bi)]
        if r > TOL:
            lati.append(bd.Edge.make_three_point_arc(Bi, Mi, Ai))
        lati.append(bd.Edge.make_line(Ai if r > TOL else Bi, Ao))
        giro = bd.extrude(bd.Face(bd.Wire(lati)), amount=L, dir=tuple(e))
        lastra = bd.extrude(bd.Face(bd.Wire.make_polygon([Bi, Bo, Bo + T * dritto, Bi + T * dritto], close=True)),
                            amount=L, dir=tuple(e))
        pz = giro + lastra
        op = BRepAlgoAPI_Fuse(body.shape, pz.wrapped)
        if not op.IsDone():
            return None
        nv = body.after(op, op.Shape())
        if len(bd.Shape.cast(nv.shape).solids()) != 1:
            return None
        if abs(volume(nv.shape) - v0 - pz.volume) > 1e-6 * max(pz.volume, 1) + 1e-3:
            return None
        return pz, nv, a_, b_, C
    # il gioco agli angoli: scritto dall'utente, oppure automatico (22/10): se la piega piena tocca un'altra parete
    # si accorcia di raggio + spessore + 0,2 dalla parte che tocca, poi da tutte e due
    scritti = [val('trim0', None, 'il gioco all’inizio'), val('trim1', None, 'il gioco alla fine')]
    if any(x is not None and x < 0 for x in scritti):
        raise FeatureError('Il gioco agli angoli non può essere negativo.', feature=fid)
    g = r + t + 0.2
    if scritti[0] is not None or scritti[1] is not None:
        tentativi = [(scritti[0] or 0.0, scritti[1] or 0.0)]
    else:
        tentativi = [(0.0, 0.0), (g, 0.0), (0.0, g), (g, g)]
    fatto = None
    for t0, t1 in tentativi:
        fatto = prova(t0, t1)
        if fatto:
            break
    if fatto is None:
        raise FeatureError('La piega tocca un’altra parte del pezzo: accorciala, aumenta il gioco agli angoli o cambia '
                           'il verso.', feature=fid)
    pezzo, nuovo, a, b, C = fatto
    L_edge = (b - a).length

    # sviluppo: oltre lo stesso bordo, la striscia della piega e il tratto dritto
    porta = lambda p: dst.from_local_coords(src.to_local_coords(p))  # noqa: E731
    A2, B2 = porta(a), porta(b)
    F2 = (porta(a + fuori) - A2).normalized()
    E2 = (B2 - A2).normalized()
    lungo = piega.ba + dritto
    rett = _orienta(bd.Face(bd.Wire.make_polygon([A2, B2, B2 + F2 * lungo, A2 + F2 * lungo], close=True)), data.plane)
    prima = data.flat.area
    n_prima = len(data.flat.faces()) if not isinstance(data.flat, bd.Face) else 1      # tramogge: più pezzi
    unito = data.flat.fuse(rett)
    unito = unito.clean() if hasattr(unito, 'clean') else unito
    fs = unito.faces() if not isinstance(unito, bd.Face) else [unito]
    if len(fs) != n_prima or abs(sum(f.area for f in fs) - prima - rett.area) > 1e-3:
        raise FeatureError('Nello sviluppo la piega si sovrappone ad altro: accorciala o lascia uno scarico.', feature=fid)
    flat = fs[0] if len(fs) == 1 else bd.Compound(children=fs)
    pl = data.plane
    m0, m1 = pl.to_local_coords(A2 + F2 * (piega.ba / 2)), pl.to_local_coords(B2 + F2 * (piega.ba / 2))
    su = sig > 0
    linea = ((m0.X, m0.Y), (m1.X, m1.Y), f'{fid} {"SU" if su else "GIÙ"} {fmt_mm(ang)}° R{fmt_mm(r)}')

    # le facce piane della piega: nome e mappa (ci si disegna, ci si fora, si piega sul suo bordo)
    mappa = dict(getattr(data, 'pannelli', None) or {})
    p_est = C + dir_(th) * (R_ if sig > 0 else r)
    p_int = C + dir_(th) * (r if sig > 0 else R_)
    dst_p = bd.Plane(origin=A2 + F2 * piega.ba, x_dir=F2, z_dir=F2.cross(E2))
    for lato_n, p, verso in (('esterno', p_est, (p_int - p_est).normalized()), ('interno', p_int, (p_est - p_int).normalized())):
        n_f = f'{fid}/{lato_n}'
        for f in _faces_of(nuovo.shape):
            if nuovo.names_of(f):
                continue
            bf = bd.Face(f)
            c = bf.center()
            if bf.geom_type != bd.GeomType.PLANE or abs(abs(bf.normal_at(c).dot(verso)) - 1) > 1e-6 \
                    or abs((c - p).dot(verso)) > 1e-5:
                continue
            x = (c - p).dot(T)
            if -1e-6 <= x <= dritto + 1e-6:
                nuovo.names.setdefault(n_f, []).append(f)
        mappa[n_f] = (bd.Plane(origin=p, x_dir=T, z_dir=T.cross(e)), dst_p, verso)
    for f in nuovo.senza_nome():
        nuovo.names.setdefault(f'{fid}/piega', []).append(f)
    riga = {'flange': fid, 'edge': 'bordo libero', 'parent': None, 'length': lung, 'line_at': None,
            'direction': 'up' if sig > 0 else 'down', 'position': 'outside', 'width': L_edge, **piega.as_dict()}
    nuovo.sheet = dataclasses.replace(data, flat=flat, flat_area=flat.area,
                                      flat_size=flat_size(flat, data.plane) if len(fs) == 1 else data.flat_size,
                                      bend_lines=list(data.bend_lines) + [linea], pannelli=mappa,
                                      extra_bends=list(data.extra_bends or []) + [riga])
    return nuovo
