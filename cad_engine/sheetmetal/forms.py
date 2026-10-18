"""Forme stampate sulla lamiera: persiane (feritoie) e imbutiture (bugne tonde).

Si disegnano su una faccia piana della lamiera: una linea per ogni persiana (è il bordo aperto, la feritoia), un
cerchio per ogni imbutitura. Sono deformazioni: il materiale si stira, quindi non c'è il controllo
"sviluppo × spessore = volume". Nello sviluppo la persiana lascia il taglio di lancia lungo la linea (una fessura
sottile, quella che taglia il laser); l'imbutitura non cambia il contorno.
"""
from __future__ import annotations

import dataclasses
import math

import build123d as bd
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse

from ..errors import FeatureError
from ..expressions import evaluate
from ..topology.naming import _faces_of
from ..units import fmt_mm

LANCIA = 0.2          # larghezza della fessura di lancia nello sviluppo (il taglio del laser)


def build_form(fdef: dict, ctx):
    from . import _face_planes, _orienta, _pick_flange
    fid = fdef['id']
    body = ctx.body
    data = getattr(body, 'sheet', None) if body is not None else None
    if data is None:
        raise FeatureError('Persiane e imbutiture si fanno su una lamiera.', feature=fid)
    ss, prof = ctx.sketch(fdef)
    piano = ss.sketch.plane
    nome = piano.get('face', '') if isinstance(piano, dict) else ''
    parti = nome.split('/')
    if not nome or parti[0] != data.feature or nome not in body.names:
        raise FeatureError('Persiane e imbutiture si disegnano su una faccia piana della lamiera.', feature=fid)
    t = data.thickness
    pl = prof.plane
    fuori = bd.Face(body.face(nome)[0]).normal_at().normalized()     # verso dove esce la forma
    if fuori.dot(pl.z_dir) < 0:
        fuori = -fuori
    tipo = fdef.get('kind')
    v = lambda k, d=None: evaluate(fdef.get(k, d), ctx.params, what=k)  # noqa: E731
    togli, metti, lance = [], [], []
    if tipo == 'louver':
        w, h = v('width'), v('height')
        if not (w > 0 and 0 < h < w):
            raise FeatureError('Persiana: larghezza e altezza maggiori di zero, e l’altezza minore della larghezza.', feature=fid)
        linee = [(a, b) for k, (a, b) in ss.lines.items() if not ss.sketch.entities[k].get('construction')
                 and not ss.sketch.entities[k].get('ref')]
        if not linee:
            raise FeatureError('Disegna una linea per ogni persiana: è il bordo aperto della feritoia.', feature=fid)
        for a, b in linee:
            A, B = pl.from_local_coords(ss.points[a]), pl.from_local_coords(ss.points[b])
            L = (B - A).length
            if L <= 2 * t:
                raise FeatureError(f'Persiana troppo corta ({fmt_mm(round(L, 1))} mm).', feature=fid)
            u = (B - A).normalized()
            lato = fuori.cross(u).normalized()                         # la persiana sta a sinistra della linea
            rett = bd.Face(bd.Wire.make_polygon([A, B, B + lato * w, A + lato * w], close=True))
            togli.append(bd.extrude(rett.moved(bd.Location(fuori * 0.01)), amount=t + 0.02, dir=tuple(-fuori)))
            metti.append(_cappa(A, u, lato, fuori, L, w, h, t))
            lance.append(bd.Face(bd.Wire.make_polygon([A - lato * LANCIA / 2, B - lato * LANCIA / 2,
                                                       B + lato * LANCIA / 2, A + lato * LANCIA / 2], close=True)))
    elif tipo == 'dimple':
        h = v('depth')
        cerchi = [k for k, e in ss.sketch.entities.items() if e['kind'] == 'circle' and not e.get('construction')
                  and not e.get('ref')]
        if not cerchi:
            raise FeatureError('Disegna un cerchio per ogni imbutitura: è il suo diametro.', feature=fid)
        for k in cerchi:
            cid, r = ss.circles[k]
            if not 0 < h < r:
                raise FeatureError(f'Imbutitura Ø{fmt_mm(2 * r)}: la profondità deve essere maggiore di zero e minore del '
                                   'raggio.', feature=fid)
            C = pl.from_local_coords(ss.points[cid])
            togli.append(bd.Solid.make_cylinder(r, t + 0.02, plane=bd.Plane(origin=C + fuori * 0.01, z_dir=-fuori)))
            metti.append(_bugna(C, fuori, r, h, t))
    else:
        raise FeatureError(f'Forma "{tipo}" sconosciuta.', feature=fid)

    ns = body
    for attrezzo in togli:
        op = BRepAlgoAPI_Cut(ns.shape, attrezzo.wrapped)
        ns = ns.after(op, op.Shape())
    for pezzo in metti:
        op = BRepAlgoAPI_Fuse(ns.shape, pezzo.wrapped)
        ns = ns.after(op, op.Shape())
    if len(bd.Shape.cast(ns.shape).solids()) != 1:
        raise FeatureError('La forma stacca un pezzo o esce dalla lamiera: spostala più dentro la faccia.', feature=fid)
    for f in _faces_of(ns.shape):
        if not ns.names_of(f):
            ns.names.setdefault(f'{fid}/forma', []).append(f)
    flat = data.flat
    if lance:
        piani = _face_planes(parti, data, fid)
        for f in lance:
            src, dst, _, _ = _pick_flange(f, piani, parti, data)
            flat = flat.cut(_orienta(f.moved(dst.location * src.location.inverse()), data.plane))
        flat = flat.clean() if hasattr(flat, 'clean') else flat
        facce = flat.faces() if not isinstance(flat, bd.Face) else [flat]
        if len(facce) != 1:
            raise FeatureError('Il taglio della persiana divide lo sviluppo.', feature=fid)
        flat = facce[0]
    from . import flat_size
    ns.sheet = dataclasses.replace(data, flat=flat, flat_area=flat.area, flat_size=flat_size(flat, data.plane))
    return ns


def _cappa(A, u, lato, fuori, L, w, h, t):
    """La cappa della persiana: una lamiera che parte dal bordo lontano (a filo della faccia) e sale fino a h sul
    bordo aperto, con le due fiancate triangolari stirate."""
    P = lambda s, z: A + lato * s + fuori * z  # noqa: E731
    sez = bd.Face(bd.Wire.make_polygon([P(w, 0), P(0, h), P(0, h - t), P(w, -t)], close=True))
    cappa = bd.extrude(sez, amount=L, dir=tuple(u))
    fianco = bd.Face(bd.Wire.make_polygon([P(w, 0), P(0, h), P(0, -t), P(w, -t)], close=True))
    cappa = cappa + bd.extrude(fianco, amount=t, dir=tuple(u))
    cappa = cappa + bd.extrude(fianco.moved(bd.Location(u * (L - t))), amount=t, dir=tuple(u))
    return cappa


def _bugna(C, fuori, r, h, t):
    """L'imbutitura: una calotta sferica spessa t che sporge di h, raccordata al foro di diametro 2r."""
    Rs = (r * r + h * h) / (2 * h)
    centro = C - fuori * (Rs - h)
    guscio = bd.Solid.make_sphere(Rs).moved(bd.Location(centro)) - bd.Solid.make_sphere(Rs - t).moved(bd.Location(centro))
    limite = bd.Solid.make_cylinder(r, h + t + 1, plane=bd.Plane(origin=C - fuori * t, z_dir=fuori))
    calotta = guscio & limite
    return calotta - _semispazio(C - fuori * t, -fuori, 4 * Rs)


def _semispazio(O, n, lato):
    """Un cubo grande che sta tutto dalla parte n del piano per O (per tagliare via quello che va oltre)."""
    pl = bd.Plane(origin=O, z_dir=n)
    return bd.Solid.make_box(2 * lato, 2 * lato, lato, plane=pl).moved(bd.Location(pl.x_dir * -lato + pl.y_dir * -lato))
