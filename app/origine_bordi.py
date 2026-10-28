"""Da dove vengono i bordi arancio (24/10): disegnando su una faccia, i fori già tagliati compaiono come bordi del
pezzo e non si cancellano. Per correggere un taglio sbagliato bisogna arrivare al taglio che li ha fatti: qui si
trova quale (le pareti dei fori si chiamano «TG7/parete») e, se il taglio è disegnato su una faccia, quali contorni
del suo disegno hanno fatto proprio quei fori, per toglierli da lì.
"""
from __future__ import annotations

from collections import Counter

from cad_engine.errors import SteelCADError
from cad_engine.sketch.model import Sketch

TOLL = 0.05             # mm: un bordo arancio sta su uno spigolo del pezzo
MAX_CAMPIONI = 600


def _campioni(svc, sid: str, eids: list) -> list:
    """Un punto 3D per ogni bordo arancio scelto (a metà della linea, sul cerchio, a metà dell'arco)."""
    import math
    sk = svc.doc.sketch(sid)
    ss = svc.doc.solved_sketch(sid)
    pl = svc.doc._plane(sk, svc.result.body)
    out = []
    for e in eids[:MAX_CAMPIONI]:
        ent = sk.entities.get(e)
        if not ent or not ent.get('ref'):
            continue
        k = ent['kind']
        if k == 'line' and e in ss.lines:
            a, b = (ss.points[x] for x in ss.lines[e])
            xy = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        elif k == 'circle' and e in ss.circles:
            c, r = ss.circles[e]
            xy = (ss.points[c][0] + r, ss.points[c][1])
        elif k == 'arc' and e in ss.arcs:
            c, a, b, r = ss.arcs[e]
            (cx, cy), (ax, ay), (bx, by) = ss.points[c], ss.points[a], ss.points[b]
            t0, t1 = math.atan2(ay - cy, ax - cx), math.atan2(by - cy, bx - cx)
            while t1 <= t0:
                t1 += 2 * math.pi
            xy = (cx + r * math.cos((t0 + t1) / 2), cy + r * math.sin((t0 + t1) / 2))
        else:
            continue
        out.append(pl.from_local_coords(xy))
    return out


def _spigolo_vicino(body, punti):
    """Per ogni punto lo spigolo del pezzo su cui sta (o None): prima gli ingombri, poi la distanza vera."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt

    from cad_engine.topology.naming import _edges_of
    memo = body.__dict__.get('_spigoli_ingombri')       # una volta per pezzo: gli ingombri e una griglia per trovarli
    if memo is None or memo[0] is not body.shape:
        spigoli, griglia, passo = [], {}, 5.0
        for e in _edges_of(body.shape):
            b = Bnd_Box()
            BRepBndLib.Add_s(e, b)
            b.Enlarge(TOLL)
            lo, hi = b.CornerMin(), b.CornerMax()
            x0, y0, z0, x1, y1, z1 = lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()
            k = len(spigoli)
            spigoli.append((e, b))
            for i in range(int(x0 // passo), int(x1 // passo) + 1):
                for j in range(int(y0 // passo), int(y1 // passo) + 1):
                    for m in range(int(z0 // passo), int(z1 // passo) + 1):
                        griglia.setdefault((i, j, m), []).append(k)
        memo = (body.shape, spigoli, griglia, passo)
        body.__dict__['_spigoli_ingombri'] = memo
    _, spigoli, griglia, passo = memo
    out = []
    for p in punti:
        g = gp_Pnt(p.X, p.Y, p.Z)
        v = BRepBuilderAPI_MakeVertex(g).Vertex()
        best = None
        for k in griglia.get((int(p.X // passo), int(p.Y // passo), int(p.Z // passo)), ()):
            e, b = spigoli[k]
            if b.IsOut(g):
                continue
            d = BRepExtrema_DistShapeShape(v, e)
            if d.IsDone() and d.Value() < TOLL and (best is None or d.Value() < best[0]):
                best = (d.Value(), e)
        out.append(best[1] if best else None)
    return out


def _nomi_spigoli(body):
    """spigolo → i nomi delle facce che lo toccano; le mappe si fanno una volta per pezzo (chiedere a ogni spigolo
    scorrendo tutte le facce costava 30 s con 260 fori)."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as MappaListe
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as Mappa
    memo = body.__dict__.get('_nomi_spigoli')
    if memo is None or memo[0] is not body.shape:
        facce = Mappa()
        nomi_faccia: dict = {}
        for nome, fs in body.names.items():
            for f in fs:
                k = facce.Add(f)
                nomi_faccia.setdefault(k, []).append(nome)
        anc = MappaListe()
        TopExp.MapShapesAndAncestors_s(body.shape, TopAbs_EDGE, TopAbs_FACE, anc)
        memo = (body.shape, facce, nomi_faccia, anc)
        body.__dict__['_nomi_spigoli'] = memo
    _, facce, nomi_faccia, anc = memo

    def nomi(e) -> list:
        i = anc.FindIndex(e)
        if not i:
            return []
        out = []
        for f in anc.FindFromIndex(i):
            out += nomi_faccia.get(facce.FindIndex(f), [])
        return out
    return nomi


def trova(svc, sid: str, eids: list) -> dict:
    """Quale taglio ha fatto i bordi arancio scelti e, se si può, quali contorni del suo disegno."""
    body = svc.result.body
    if body is None:
        raise SteelCADError('Non c’è ancora un pezzo.', code='origine')
    punti = _campioni(svc, sid, eids)
    if not punti:
        raise SteelCADError('Scegli dei bordi arancio (i bordi del pezzo).', code='origine')
    spigoli = _spigolo_vicino(body, punti)
    tagli = {f['id']: f for f in svc.doc.features if not isinstance(f, Sketch) and f.get('sketch')}
    conta: Counter = Counter()
    da_taglio = []                                   # (punto, taglio)
    nomi_di = _nomi_spigoli(body)
    for p, e in zip(punti, spigoli):
        if e is None:
            continue
        nomi = nomi_di(e)
        fids = {n.split('/')[0] for n in nomi if n.endswith('/parete') and n.split('/')[0] in tagli}
        for fid in fids:
            conta[fid] += 1
            da_taglio.append((p, fid))
    if not conta:
        raise SteelCADError('Questi bordi non vengono da un taglio: sono il contorno del pezzo (si cambia con le sue '
                            'misure o con le pieghe).', code='origine')
    fid = conta.most_common(1)[0][0]
    src = tagli[fid]['sketch']
    fatto = svc.doc._sketch_results.get(src)
    prof = fatto[1] if fatto else None
    eid_src, contorni = [], set()
    sk_src = svc.doc.sketch(src)
    sviluppo = isinstance(sk_src.plane, dict) and bool(sk_src.plane.get('flat'))
    if prof is not None and prof.faces and sviluppo:
        # disegnato sullo sviluppo (28/10): ogni contorno portato al suo posto sul pezzo piegato, poi come sopra
        sul_pezzo = _contorni_sul_pezzo(svc, prof)
        for p, f in da_taglio:
            if f != fid:
                continue
            k = _contorno_sul_pezzo(sul_pezzo, p)
            if k is not None:
                contorni.add(k)
    elif prof is not None and prof.faces:
        n, o = prof.plane.z_dir, prof.plane.origin
        for p, f in da_taglio:
            if f != fid:
                continue
            q = p - n * (p - o).dot(n)               # sul piano del disegno del taglio (anche dall'altra faccia)
            k = _contorno_di(prof, q)
            if k is not None:
                contorni.add(k)
    for k in sorted(contorni):
        for e in prof.faces[k].edges():
            ent = prof.entity_of(e)
            if ent and ent not in eid_src:
                eid_src.append(ent)
    return {'feature': fid, 'nome': svc._etichetta(fid), 'sketch': src, 'fori': len(contorni),
            'altri': sum(conta.values()) - conta[fid],          # bordi scelti che vengono da altri tagli
            'totale': len(prof.faces) if prof is not None else 0, 'eids': eid_src,
            'tutti': prof is not None and len(contorni) == len(prof.faces)}


def _contorni_sul_pezzo(svc, prof) -> list:
    """Per ogni contorno di un disegno sullo sviluppo: la sua faccia sul pezzo piegato (None se passa una piega o non
    si sa). Si ricorda sul risultato del disegno: con tanti fori si fa una volta."""
    from cad_engine.errors import FeatureError
    from cad_engine.sheetmetal import _from_flat, _pannello_dallo_sviluppo
    body = svc.result.body
    memo = prof.__dict__.get('_sul_pezzo')
    if memo is not None and memo[0] is body.shape:
        return memo[1]
    data = body.sheet
    # le zone delle flange nello sviluppo (piega + tratto dritto): un contorno lontano da tutte sta sulla base, e la
    # base nello sviluppo è al suo posto (niente conti: con 260 fori erano 3 s)
    zone = []
    for g in data.flanges or []:
        us = [g.u0, g.u1] + [x for ab in g.tab_ranges for x in ab]
        ss = [g.off, g.off + g.bend.ba + g.lf]
        pts = [g.F0 + g.fx * u + g.fn * s_ for u in (min(us), max(us)) for s_ in ss]
        zone.append((min(q.X for q in pts) - 1, max(q.X for q in pts) + 1, min(q.Y for q in pts) - 1, max(q.Y for q in pts) + 1))
    out = []
    for f in prof.faces:
        bf = f.bounding_box()
        if not getattr(data, 'pannelli', None) and not any(
                bf.min.X <= z[1] and bf.max.X >= z[0] and bf.min.Y <= z[3] and bf.max.Y >= z[2] for z in zone):
            out.append((f, bf, data.plane.z_dir))
            continue
        try:
            if getattr(data, 'pannelli', None) and not data.flanges:
                f3 = _pannello_dallo_sviluppo(f, body, data, data.feature)[0]
            else:
                f3 = _from_flat(f, data, data.feature)[0]
            out.append((f3, f3.bounding_box(), f3.normal_at(f3.center())))
        except (FeatureError, Exception):  # noqa: BLE001
            out.append(None)
    prof.__dict__['_sul_pezzo'] = (body.shape, out)
    return out


def _contorno_sul_pezzo(sul_pezzo, p) -> int | None:
    """Il contorno (portato sul pezzo) che passa per p, guardando dentro lo spessore: p sta su una faccia, il contorno
    sull'altra o su quella."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    for k, x in enumerate(sul_pezzo):
        if x is None:
            continue
        f3, bb, n = x
        o = f3.center()
        q = p - n * (p - o).dot(n)
        if not (bb.min.X - 0.1 <= q.X <= bb.max.X + 0.1 and bb.min.Y - 0.1 <= q.Y <= bb.max.Y + 0.1
                and bb.min.Z - 0.1 <= q.Z <= bb.max.Z + 0.1):
            continue
        v = BRepBuilderAPI_MakeVertex(gp_Pnt(q.X, q.Y, q.Z)).Vertex()
        for w in f3.wires():
            d = BRepExtrema_DistShapeShape(v, w.wrapped)
            if d.IsDone() and d.Value() < TOLL:
                return k
    return None


def _contorno_di(prof, q) -> int | None:
    """Il contorno del disegno che passa per q (entro la tolleranza)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    v = BRepBuilderAPI_MakeVertex(gp_Pnt(q.X, q.Y, q.Z)).Vertex()
    for k, f in enumerate(prof.faces):
        bb = f.bounding_box()
        if not (bb.min.X - 0.1 <= q.X <= bb.max.X + 0.1 and bb.min.Y - 0.1 <= q.Y <= bb.max.Y + 0.1
                and bb.min.Z - 0.1 <= q.Z <= bb.max.Z + 0.1):
            continue
        for w in f.wires():
            d = BRepExtrema_DistShapeShape(v, w.wrapped)
            if d.IsDone() and d.Value() < TOLL:
                return k
    return None
