"""Nomi stabili di facce e spigoli (vedi docs/TOPOLOGY_STRATEGY.md).

Una faccia prende il nome dalla feature che la crea ("E1/lato/L2"); dopo ogni
operazione i nomi passano alle facce nuove attraverso lo storico di
OpenCascade (Modified / Generated / IsDeleted). Uno spigolo è l'incontro di
due facce con nome. Mai indici come "Face7".
"""
from __future__ import annotations

from dataclasses import dataclass, field

import build123d as bd
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape

from ..errors import LostReferenceError


def _faces_of(shape: TopoDS_Shape) -> list:
    out, ex = [], TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        out.append(TopoDS.Face(ex.Current()))
        ex.Next()
    return out


def _edges_of(shape: TopoDS_Shape) -> list:
    # mappa indicizzata (stesso criterio di IsSame, nello stesso ordine): confrontare ogni spigolo con tutti
    # gli altri erano un milione di confronti su un raccordo
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, m)
    return [TopoDS.Edge(m(i)) for i in range(1, m.Extent() + 1)]


def _contains(lst, s) -> bool:
    return any(s.IsSame(x) for x in lst)


def _list(occ_list) -> list:
    # una lista vuota di OCC costa mezzo millesimo a scorrerla (finisce con un'eccezione dentro OCP): con centinaia
    # di facce era mezzo secondo per ogni aggiunta di materiale (22/10)
    return [x for x in occ_list] if occ_list.Size() else []


@dataclass
class NamedShape:
    """Un solido con i nomi delle sue facce. Un nome può indicare più frammenti."""
    shape: TopoDS_Shape
    names: dict = field(default_factory=dict)      # nome -> [TopoDS_Face]

    # ------------------------------------------------------------- lettura
    @property
    def solid(self) -> bd.Shape:
        return bd.Shape.cast(self.shape) if hasattr(bd.Shape, 'cast') else bd.Solid(self.shape)

    def faces(self) -> list:
        return _faces_of(self.shape)

    def senza_nome(self) -> list:
        """Le facce del solido che non hanno ancora un nome (con una mappa indicizzata: chiedere names_of a ogni faccia
        erano milioni di confronti dopo un taglio con tante lettere o tanti fori, 22/10)."""
        con = TopTools_IndexedMapOfShape()
        for fs in self.names.values():
            for f in fs:
                con.Add(f)
        return [f for f in _faces_of(self.shape) if not con.Contains(f)]

    def names_of(self, face) -> list[str]:
        return sorted(n for n, fs in self.names.items() if _contains(fs, face))

    def face(self, name: str, *, feature: str | None = None) -> list:
        fs = self.names.get(name) or []
        if not fs:
            raise LostReferenceError(f'La faccia "{describe(name)}" non esiste più nel pezzo: forse una modifica '
                                     'l\'ha tolta. Scegli di nuovo la faccia.', feature=feature)
        return fs

    def edge_ref(self, edge) -> dict:
        """Dal clic su uno spigolo al riferimento stabile da salvare."""
        adj = [f for f in self.faces() if _contains(_edges_of(f), edge)]
        nomi = []
        for f in adj:
            n = self.names_of(f)
            if not n:
                raise LostReferenceError('Lo spigolo scelto confina con una faccia senza nome: non posso '
                                         'riconoscerlo dopo una modifica.')
            nomi.append(n[0])
        if len(nomi) != 2:
            raise LostReferenceError('Lo spigolo scelto non separa esattamente due facce.')
        ref = {'faces': sorted(nomi)}
        tutti = self._common_edges(*ref['faces'])
        if len(tutti) > 1:
            ref['index'] = next(i for i, e in enumerate(tutti) if e.IsSame(edge))
        return ref

    def _common_edges(self, a: str, b: str) -> list:
        ea = [e for f in self.names.get(a, []) for e in _edges_of(f)]
        eb = [e for f in self.names.get(b, []) for e in _edges_of(f)]
        comuni = []
        for e in ea:
            if _contains(eb, e) and not _contains(comuni, e):
                comuni.append(e)
        comuni.sort(key=_edge_sort_key)
        return comuni

    def edges(self, ref: dict, *, feature: str | None = None) -> list:
        a, b = ref['faces']
        comuni = self._common_edges(a, b)
        if not comuni:
            raise LostReferenceError(f'Lo spigolo tra "{describe(a)}" e "{describe(b)}" non esiste più dopo la '
                                     'modifica. Scegli di nuovo lo spigolo.', feature=feature)
        if 'index' in ref:
            i = ref['index']
            if i >= len(comuni):
                raise LostReferenceError(f'Lo spigolo tra "{describe(a)}" e "{describe(b)}" è cambiato: '
                                         'scegli di nuovo lo spigolo.', feature=feature)
            return [comuni[i]]
        return comuni

    # ---------------------------------------------------------- scrittura
    def after(self, maker, new_shape: TopoDS_Shape, tool: 'NamedShape | None' = None) -> 'NamedShape':
        """Nomi dopo un'operazione con storico (booleana, raccordo, …)."""
        # le facce nuove in una mappa indicizzata, e lo storico di ogni faccia chiesto una volta sola (una faccia
        # sta sotto più nomi): prima erano milioni di confronti uno a uno, 12 dei 18 secondi della cassa del quadro
        mappa = TopTools_IndexedMapOfShape()
        for g in _faces_of(new_shape):
            mappa.Add(g)
        nuove = [TopoDS.Face(mappa(i)) for i in range(1, mappa.Extent() + 1)]
        visti = TopTools_IndexedMapOfShape()
        storia: list = []

        def dove(f) -> list:
            k = visti.FindIndex(f)
            if k:
                return storia[k - 1]
            if maker.IsDeleted(f):
                idx = []
            else:
                mod = [x for x in _list(maker.Modified(f)) if x.ShapeType() == TopAbs_FACE]
                idx = sorted({mappa.FindIndex(x) for x in mod} - {0}) if mod else \
                    ([mappa.FindIndex(f)] if mappa.FindIndex(f) else [])
            visti.Add(f)
            storia.append(idx)
            return idx

        out: dict[str, list] = {}
        for src in (self, tool):
            if src is None:
                continue
            for nome, fs in src.names.items():
                presi: set = set()
                for f in fs:
                    for i in dove(f):
                        if i not in presi:
                            presi.add(i)
                            out.setdefault(nome, []).append(nuove[i - 1])
        return NamedShape(new_shape, out)


def _propagate(maker, face, nuove) -> list:
    if maker.IsDeleted(face):
        return []
    mod = [TopoDS.Face(x) for x in _list(maker.Modified(face)) if x.ShapeType() == TopAbs_FACE]
    if mod:
        return [g for g in nuove if _contains(mod, g)]
    return [g for g in nuove if g.IsSame(face)]


def _edge_sort_key(e) -> tuple:
    m = bd.Edge(e).position_at(0.5)
    return (round(m.X, 6), round(m.Y, 6), round(m.Z, 6))


def describe(name: str) -> str:
    """'E1/lato/L2' -> 'lato L2 di E1'. Per i messaggi."""
    parti = name.split('/')
    if len(parti) == 3:
        return f'{parti[1]} {parti[2]} di {parti[0]}'
    if len(parti) == 2:
        return f'{parti[1]} di {parti[0]}'
    return name
