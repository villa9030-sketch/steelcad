"""Lavorazioni sui tubi: uno sketch disegnato su una faccia di un'asta buca la parete.

Lo sketch sta sulla faccia di un'asta (piano {"tube": "ST1", "member": "M3", "side": "y+"}):
- X lungo il tubo, con lo zero sulla testa (la punta più indietro dell'asta, come si misura in officina:
  "a 150 dalla testa"); se la struttura cambia misura, le lavorazioni restano a quella distanza dalla testa;
- Y attraverso la faccia, con lo zero sul bordo della faccia (fuori tutto, spigolo arrotondato compreso).

La feature che taglia:

    {"id": "LT1", "type": "tube_cut", "name": "Fori", "sketch": "S5", "structure": "ST1",
     "members": ["M3", "M4"], "through": false}

"members": l'asta dello sketch e le altre uguali dove ripetere la stessa lavorazione (stesso profilo,
stessa faccia, stessa distanza dalla testa). "through": anche la parete di fronte (passante).
Una sagoma che esce dal bordo della faccia o dalla testa diventa un intaglio: niente comando a parte.

Per ora: tubolari quadri e rettangolari e piatti. I tubi tondi non hanno facce piane (verranno dopo).
"""
from __future__ import annotations

from dataclasses import replace

import build123d as bd

from ..errors import FeatureError
from ..units import fmt_mm

SIDES = ('y+', 'y-', 'x+', 'x-')
FAMIGLIE = ('SHS', 'RHS', 'FLAT')


def _side_axes(m, side: str):
    """Normale uscente della faccia, semi-spessore del tubo in quella direzione, mezza larghezza della faccia."""
    if side not in SIDES:
        raise FeatureError(f'Faccia "{side}" sconosciuta per l\'asta {m.id}.')
    p = m.profile
    if side[0] == 'y':
        n, meta, larga = m.y, p.height / 2, p.width / 2
    else:
        n, meta, larga = m.x, p.width / 2, p.height / 2
    return (n if side[1] == '+' else -n), meta, larga


def check(m) -> None:
    if m.profile.family not in FAMIGLIE:
        cosa = 'i tubi tondi' if m.profile.family == 'CHS' else f'i profili {m.profile.description.split()[0].lower()}'
        raise FeatureError(f'Le lavorazioni disegnate per ora si fanno su tubolari quadri, rettangolari e piatti: '
                           f'{cosa} verranno dopo ({m.label()}).')
    if m.solid is None:
        raise FeatureError(f'L\'asta {m.id} non è costruita.')


def face_plane(m, side: str) -> bd.Plane:
    """Il piano dello sketch sulla faccia `side` dell'asta: X lungo il tubo dalla testa, Y dal bordo della faccia,
    Z fuori dal tubo."""
    check(m)
    n, meta, larga = _side_axes(m, side)
    w = m.w
    y = n.cross(w).normalized()                  # Y = Z × X
    asse = m.start + m.origin_shift
    origin = asse + w * m.testa + n * meta - y * larga
    return bd.Plane(origin=origin, x_dir=w, z_dir=n)


def side_from_normal(m, normal) -> str:
    """La faccia dell'asta più rivolta come la normale cliccata."""
    v = bd.Vector(*normal) if not isinstance(normal, bd.Vector) else normal
    return max(SIDES, key=lambda s: _side_axes(m, s)[0].dot(v))


def describe_side(m, side: str) -> str:
    """La faccia come la direbbe l'officina, guardando la struttura: sopra, sotto, davanti, dietro, a destra, a
    sinistra."""
    n = _side_axes(m, side)[0]
    nomi = [(bd.Vector(0, 0, 1), 'sopra'), (bd.Vector(0, 0, -1), 'sotto'), (bd.Vector(0, -1, 0), 'davanti'),
            (bd.Vector(0, 1, 0), 'dietro'), (bd.Vector(1, 0, 0), 'destra'), (bd.Vector(-1, 0, 0), 'sinistra')]
    return max(nomi, key=lambda c: c[0].dot(n))[1]


def face_of(m, side: str) -> bd.Face | None:
    """La faccia piana vera del solido su quel lato (per i bordi arancio dello sketch)."""
    pl = face_plane(m, side)
    n = pl.z_dir
    migliore, area = None, 0.0
    for f in m.solid.faces():
        if f.geom_type != bd.GeomType.PLANE:
            continue
        if f.normal_at().dot(n) < 1 - 1e-6 or abs((f.center() - pl.origin).dot(n)) > 1e-4:
            continue
        if f.area > area:
            migliore, area = f, f.area
    return migliore


def apply(fdef: dict, st, prof, sketch_label: str):
    """Ritorna una StructureResult nuova con le aste bucate (quella di prima resta com'era: sta in cache)."""
    fid = fdef['id']
    nomi = fdef.get('members') or []
    if not nomi:
        raise FeatureError(f'La lavorazione {fid} non dice su quale asta va.', feature=fid)
    by_id = {m.id: m for m in st.members}
    mancano = [x for x in nomi if x not in by_id]
    if mancano:
        raise FeatureError(f'La lavorazione {fid} va sull\'asta {", ".join(mancano)}, che non c\'è più nella '
                           f'struttura "{st.name}".', feature=fid)
    if not prof.faces:
        raise FeatureError(f'Lo sketch "{sketch_label}" non ha contorni chiusi: disegna fori, asole o sagome chiuse.',
                           feature=fid, code='nessun_profilo')
    side = fdef.get('side')
    primo = by_id[nomi[0]]
    for x in nomi:
        check(by_id[x])
        if by_id[x].profile != primo.profile:
            raise FeatureError(f'La lavorazione {fid} si ripete solo su aste dello stesso tubo: {x} è '
                               f'{by_id[x].profile.name}, {primo.id} è {primo.profile.name}.', feature=fid)
    # le sagome, nel sistema della faccia (sketch a z=0)
    sagome = [prof.plane.to_local_coords(f) for f in prof.faces]
    passante = bool(fdef.get('through'))
    _, meta, _ = _side_axes(primo, side)
    fondo = 2 * meta + 1.0 if passante else meta          # fino all'asse: solo la parete vicina (il tubo è vuoto)
    utensile_locale = []
    for s in sagome:
        su = s.moved(bd.Location((0, 0, 1.0)))            # parte da 1 mm fuori: niente facce coincidenti
        utensile_locale.append(bd.extrude(su, amount=fondo + 1.0, dir=(0, 0, -1)))
    firma = f'{fid}:{side}:{"P" if passante else "1"}'
    nuove = []
    for m in st.members:
        if m.id not in nomi:
            nuove.append(m)
            continue
        loc = bd.Location(face_plane(m, side))
        solid = m.solid
        prima = solid.volume
        for u in utensile_locale:
            solid = solid.cut(u.moved(loc))
        pezzi = solid.solids() if hasattr(solid, 'solids') else [solid]
        if not pezzi:
            raise FeatureError(f'La lavorazione {fid} si mangia tutta l\'asta {m.id}.', feature=fid)
        if len(pezzi) > 1:
            raise FeatureError(f'La lavorazione {fid} taglia l\'asta {m.id} in {len(pezzi)} pezzi staccati: '
                               'controlla la sagoma.', feature=fid)
        solid = pezzi[0]
        if prima - solid.volume < 1e-6:
            raise FeatureError(f'La lavorazione {fid} non tocca l\'asta {m.id}: la sagoma sta fuori dalla faccia '
                               f'(la faccia è lunga {fmt_mm(round(m.length, 1))} mm).', feature=fid)
        nuove.append(replace(m, solid=solid, lavorazioni=m.lavorazioni + (firma,)))
    return replace(st, members=nuove)
