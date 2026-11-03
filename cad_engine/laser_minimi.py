"""Misure minime per il laser (03/11): avvisi in parole d'officina, mai blocchi. Si leggono in «Prepara per il laser».

Le regole sono quelle di tutti i giorni per il taglio laser della lamiera (ferro, inox, alluminio):
- un foro più piccolo dello spessore viene male (il fascio non lo passa pulito, si brucia o resta attaccato);
- tra due fori, o tra un foro e il bordo, deve restare almeno lo spessore di lamiera (se no si scalda e si storce);
- una linguetta (una parte che sporge) più stretta dello spessore si storce o si stacca.
Si guarda la faccia piana da tagliare (lo sviluppo della lamiera o la faccia della piastra), non il 3D.
"""
from __future__ import annotations

import math

import build123d as bd

from .units import fmt_mm

_MM = lambda v: fmt_mm(round(v, 1))  # noqa: E731


def _larghezza_foro(w) -> float | None:
    """La misura più stretta di un foro: il diametro per un tondo, la larghezza per un'asola (2 × raggio delle teste),
    il lato corto per un rettangolo. None se non si capisce (un contorno libero)."""
    ed = w.edges()
    archi = [e for e in ed if e.geom_type == bd.GeomType.CIRCLE]
    if len(ed) == 1 and archi:
        return 2 * archi[0].radius
    if archi and len(archi) == 2 and all(e.geom_type in (bd.GeomType.CIRCLE, bd.GeomType.LINE) for e in ed):
        return 2 * min(e.radius for e in archi)
    linee = [e for e in ed if e.geom_type == bd.GeomType.LINE]
    if len(ed) == 4 and len(linee) == 4:
        return min(e.length for e in linee)
    return None


def _distanza(a, b) -> float:
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    return d.Value() if d.IsDone() else math.inf


def _scatola(w, gioco: float):
    bb = w.bounding_box()
    return (bb.min.X - gioco, bb.min.Y - gioco, bb.min.Z - gioco, bb.max.X + gioco, bb.max.Y + gioco, bb.max.Z + gioco)


def _si_toccano(a, b) -> bool:
    return not (a[3] < b[0] or b[3] < a[0] or a[4] < b[1] or b[4] < a[1] or a[5] < b[2] or b[5] < a[2])


def controlla(faccia, spessore: float) -> list[str]:
    """Gli avvisi del laser per una faccia piana da tagliare (con i suoi fori) di quello spessore."""
    try:
        return _controlla(faccia, float(spessore))
    except Exception:  # noqa: BLE001 - un controllo che non riesce non deve fermare la preparazione
        return []


def _controlla(faccia, t: float) -> list[str]:
    if faccia is None or t <= 0:
        return []
    out = []
    fuori = faccia.outer_wire()
    fori = list(faccia.inner_wires())
    # --- fori più piccoli dello spessore
    piccoli = []
    for w in fori:
        L = _larghezza_foro(w)
        if L is not None and L < t - 1e-6:
            piccoli.append(L)
    if piccoli:
        n = len(piccoli)
        if n == 1:
            out.append(f'Laser: un foro è più piccolo dello spessore ({_MM(piccoli[0])} mm, spessore {_MM(t)}): il laser '
                       f'lo fa male, bruciato o non passante. Fallo almeno da {_MM(t)} mm, oppure col trapano dopo.')
        else:
            out.append(f'Laser: {n} fori sono più piccoli dello spessore (il più piccolo {_MM(min(piccoli))} mm, spessore '
                       f'{_MM(t)}): il laser li fa male, bruciati o non passanti. Falli almeno da {_MM(t)} mm, oppure col '
                       'trapano dopo.')
    # --- ponticelli: tra due fori e tra un foro e il bordo deve restare almeno lo spessore
    scatole = [_scatola(w, t) for w in fori]
    sf = _scatola(fuori, 0)
    stretti = []                                   # (distanza, 'fori' | 'bordo')
    for i, w in enumerate(fori):
        a = scatole[i]
        # il bordo: solo se la scatola del foro arriva a meno dello spessore dal bordo esterno
        vicino_bordo = (a[0] < sf[0] + 2 * t or a[3] > sf[3] - 2 * t or a[1] < sf[1] + 2 * t or a[4] > sf[4] - 2 * t
                        or a[2] < sf[2] + 2 * t or a[5] > sf[5] - 2 * t)
        if vicino_bordo or len(fuori.edges()) > 4:
            d = _distanza(w, fuori)
            if 1e-6 < d < t - 1e-6:
                stretti.append((d, 'bordo'))
        for j in range(i + 1, len(fori)):
            if not _si_toccano(a, scatole[j]):
                continue
            d = _distanza(w, fori[j])
            if 1e-6 < d < t - 1e-6:
                stretti.append((d, 'fori'))
    if stretti:
        d = min(x[0] for x in stretti)
        tra_fori = sum(1 for x in stretti if x[1] == 'fori')
        al_bordo = len(stretti) - tra_fori
        dove = ' e '.join(x for x in (
            (f'tra {tra_fori} coppi{"a" if tra_fori == 1 else "e"} di fori' if tra_fori else ''),
            (f'tra {al_bordo} for{"o" if al_bordo == 1 else "i"} e il bordo' if al_bordo else '')) if x)
        out.append(f'Laser: {dove} resta un ponticello di lamiera troppo sottile (il più stretto {_MM(d)} mm, ne serve '
                   f'almeno lo spessore, {_MM(t)}): col calore si storce o si rompe. Allontana i fori.')
    # --- linguette strette: due lati dritti affacciati del contorno, vicini, con la lamiera in mezzo
    linee = [e for e in fuori.edges() if e.geom_type == bd.GeomType.LINE and e.length > 1e-3]
    strette = []
    for i, a in enumerate(linee):
        da = (a.end_point() - a.start_point()).normalized()
        for b in linee[i + 1:]:
            db = (b.end_point() - b.start_point()).normalized()
            if abs(abs(da.dot(db)) - 1) > 1e-4:
                continue                            # non parallele
            # distanza tra le due rette e quanto si sovrappongono lungo la direzione
            v = b.start_point() - a.start_point()
            dist = (v - da * v.dot(da)).length
            if not 1e-6 < dist < t - 1e-6:
                continue
            s0, s1 = sorted(((b.start_point() - a.start_point()).dot(da), (b.end_point() - a.start_point()).dot(da)))
            sov = min(a.length, s1) - max(0.0, s0)
            if sov < max(dist, 0.5):
                continue                            # appena si toccano di punta (un angolo), non sono affacciate
            centro = a.start_point() + da * (max(0.0, s0) + sov / 2)
            m = centro + (v - da * v.dot(da)) * 0.5
            if faccia.is_inside(m, 1e-4):           # in mezzo c'è lamiera: è una linguetta stretta (non una fessura)
                strette.append(dist)
    if strette:
        n = len(strette)
        out.append(f'Laser: {"una parte che sporge è larga" if n == 1 else f"{n} parti che sporgono sono larghe"} solo '
                   f'{_MM(min(strette))} mm, meno dello spessore ({_MM(t)}): si storce o si stacca durante il taglio. '
                   f'Allargala almeno a {_MM(t)} mm.')
    return out


def faccia_da_tagliare(shape):
    """Per una piastra (non lamiera piegata): la faccia piana più grande e lo spessore (quanto è alto il pezzo lungo
    la sua normale)."""
    corpo = bd.Shape.cast(shape) if not isinstance(shape, bd.Shape) else shape
    piane = [f for f in corpo.faces() if f.geom_type == bd.GeomType.PLANE]
    if not piane:
        return None, 0.0
    f = max(piane, key=lambda x: x.area)
    n = f.normal_at()
    ds = [v.center().dot(n) for v in corpo.vertices()]
    return f, max(ds) - min(ds)
