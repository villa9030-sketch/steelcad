"""Comando «Foro» e «Asola» diretti sul pezzo (03/11): dove vanno, come lo dice l'officina.

Le misure sono dal fuori tutto del pezzo visto sulla faccia: x dal bordo sinistro, y dal bordo davanti. Qui solo i
conti (dove cadono i centri); il taglio vero lo fa ``Service.fori_guidati`` con lo sketch su faccia di sempre.
"""
from __future__ import annotations

from cad_engine.errors import SteelCADError

DISPOSIZIONI = ('centro', 'angoli', 'fila', 'punti')


def _num(v, cosa: str) -> float:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    try:
        return float(str(v).strip().replace(',', '.'))
    except (TypeError, ValueError):
        raise SteelCADError(f'Scrivi {cosa} con un numero.', code='fori') from None


def posizioni(spec: dict, w: float, h: float) -> list[tuple[float, float]]:
    """I centri, dal fuori tutto (w × h): «Uno al centro», «4 agli angoli» (a tot dai bordi), «In fila» (quanti,
    passo, centrata sulla faccia e a tot da un bordo o in mezzo), «Dove clicco» (i punti dati)."""
    disp = spec.get('disposizione') or 'centro'
    if disp not in DISPOSIZIONI:
        raise SteelCADError(f'Disposizione «{disp}» sconosciuta.', code='fori')
    if disp == 'centro':
        return [(w / 2, h / 2)]
    if disp == 'angoli':
        bx = _num(spec.get('bordo', 20), 'la distanza dai bordi')
        by = spec.get('bordo_y')
        by = bx if by in (None, '') else _num(by, 'la distanza dai bordi davanti e dietro')
        if bx <= 0 or by <= 0:
            raise SteelCADError('La distanza dai bordi deve essere più di zero.', code='fori')
        if 2 * bx >= w or 2 * by >= h:
            raise SteelCADError('Con questa distanza dai bordi i fori si toccano o escono dal pezzo.', code='fori')
        return [(bx, by), (w - bx, by), (bx, h - by), (w - bx, h - by)]
    if disp == 'fila':
        n = int(round(_num(spec.get('n', 2), 'quanti fori')))
        p = _num(spec.get('passo', 0), 'il passo')
        if n < 1:
            raise SteelCADError('Ne serve almeno uno.', code='fori')
        if n > 1 and p <= 0:
            raise SteelCADError('Scrivi ogni quanto va un foro della fila (il passo).', code='fori')
        verso = spec.get('verso') or 'x'
        lungo, largo = (w, h) if verso == 'x' else (h, w)
        primo = lungo / 2 - (n - 1) * p / 2                      # la fila centrata sulla faccia
        d = spec.get('dal')
        lato = spec.get('lato') or ''
        if d in (None, '') or lato in ('', 'mezzo'):
            q = largo / 2
        else:
            d = _num(d, 'la distanza dal bordo')
            q = largo - d if lato in ('dietro', 'destra') else d
        return [(primo + i * p, q) if verso == 'x' else (q, primo + i * p) for i in range(n)]
    pts = spec.get('punti') or []
    if not pts:
        raise SteelCADError('Clicca sul pezzo dove va il foro.', code='fori')
    return [(_num(x, 'la distanza dal bordo sinistro'), _num(y, 'la distanza dal bordo davanti')) for x, y in pts]


def misure_asola(spec: dict) -> tuple[float, float, bool]:
    """Larghezza × altezza vere dell'asola (fuori tutto, come la si misura col calibro): torna lunghezza, larghezza
    (il diametro delle teste) e se è in piedi."""
    lx = _num(spec.get('larg'), 'la larghezza dell’asola')
    ly = _num(spec.get('alt'), 'l’altezza dell’asola')
    if lx <= 0 or ly <= 0:
        raise SteelCADError('L’asola ha bisogno di larghezza e altezza.', code='fori')
    if abs(lx - ly) < 1e-6:
        raise SteelCADError('Larghezza e altezza uguali: è un foro tondo, non un’asola.', code='fori')
    return max(lx, ly), min(lx, ly), ly > lx


def ingombri(spec: dict) -> tuple[float, float]:
    """Mezza larghezza e mezza altezza di un foro o di un'asola: per vedere se esce dal pezzo."""
    if (spec.get('tipo') or 'tondo') == 'asola':
        lun, lar, piedi = misure_asola(spec)
        return (lar / 2, lun / 2) if piedi else (lun / 2, lar / 2)
    d = _num(spec.get('d'), 'il diametro')
    if d <= 0:
        raise SteelCADError('Il diametro deve essere più di zero.', code='fori')
    return d / 2, d / 2
