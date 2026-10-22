"""Nomi da officina per tubi e angoli di una struttura (22/10): «Traverso davanti, in alto», «Gamba dietro a
destra», «Angolo davanti a sinistra, in alto». Al posto di M1, G3, K1.1.L3, T0 e S1.P1.

Si guarda la struttura di fronte: davanti = Y più piccola, destra = X più grande, in alto = Z più grande.
Un nome dato a mano (campo "name" dell'asta, «Mensola») vince sempre.
"""
from __future__ import annotations

from collections import Counter

from ..units import fmt_mm

TOL = 1.0     # mm: entro un millimetro dal bordo della struttura si è «davanti», «in alto»…


def _limiti(members):
    # i tubi col nome dato a mano (una mensola che sporge) non spostano il «davanti a sinistra» degli altri
    members = [m for m in members if not getattr(m, 'nome', '')] or members
    xs = [p.X for m in members for p in (m.start, m.end)]
    ys = [p.Y for m in members for p in (m.start, m.end)]
    zs = [p.Z for m in members for p in (m.start, m.end)]
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def _lato(v, lim, basso, alto):
    lo, hi = lim
    if hi - lo < TOL:
        return ''
    if abs(v - lo) < TOL:
        return basso
    if abs(v - hi) < TOL:
        return alto
    return ''


def _quota(z, lim):
    lo, hi = lim
    if hi - lo < TOL:
        return ''
    if abs(z - hi) < TOL:
        return 'in alto'
    if abs(z - lo) < TOL:
        return 'in basso'
    return f'a {fmt_mm(round(z - lo))} da terra'


def _tipo(m) -> str:
    """Prima com'è messo (in piedi, sdraiato, inclinato), poi il gruppo per la parola giusta: nel gruppo «Spalle»
    ci sono sia i montanti sia i traversi di fianco."""
    g = (m.group or '').strip().lower()
    w = m.w
    if abs(w.Z) > 0.95:
        return {'gambe': 'Gamba', 'sbarre': 'Sbarra'}.get(g, 'Montante')
    if abs(w.Z) > 0.1:
        return 'Diagonale'
    return 'Traverso'


def nomi_aste(members) -> dict:
    """{id asta: nome}. Nomi uguali (due traversi a metà) prendono 1, 2… da sinistra/davanti/in basso."""
    if not members:
        return {}
    lx, ly, lz = _limiti(members)
    out = {}
    for m in members:
        if getattr(m, 'nome', ''):
            out[m.id] = m.nome
            continue
        tipo, w = _tipo(m), m.w
        mid = (m.start + m.end) * 0.5
        parti = []
        if abs(w.Z) > 0.95:                                   # in piedi: dove sta in pianta
            parti = [_lato(mid.Y, ly, 'davanti', 'dietro'), _lato(mid.X, lx, 'a sinistra', 'a destra')]
            testo = ' '.join(p for p in parti if p)
        else:
            if abs(w.X) >= abs(w.Y):                          # lungo la larghezza: davanti o dietro
                dove = _lato(mid.Y, ly, 'davanti', 'dietro')
            else:                                             # lungo la profondità: a sinistra o a destra
                dove = _lato(mid.X, lx, 'a sinistra', 'a destra')
                if tipo == 'Traverso':
                    tipo = 'Fianco'
            q = _quota(min(m.start.Z, m.end.Z), lz)
            testo = ', '.join(p for p in (dove, q) if p)
        out[m.id] = f'{tipo} {testo}'.strip()
    conta = Counter(out.values())
    visti: Counter = Counter()
    for m in sorted(members, key=lambda m: (((m.start + m.end) * 0.5).X, ((m.start + m.end) * 0.5).Y,
                                            ((m.start + m.end) * 0.5).Z)):
        n = out[m.id]
        if conta[n] > 1 and not getattr(m, 'nome', ''):
            visti[n] += 1
            out[m.id] = f'{n} ({visti[n]})'
    return out


def nome_punto(p, members) -> str:
    """«Angolo davanti a sinistra, in alto» per un nodo sul bordo della struttura; «Punto a metà …» se no."""
    if not members:
        return 'Punto di partenza'
    lx, ly, lz = _limiti(members)
    pianta = ' '.join(x for x in (_lato(p.Y, ly, 'davanti', 'dietro'), _lato(p.X, lx, 'a sinistra', 'a destra')) if x)
    q = _quota(p.Z, lz)
    if pianta:
        return f'Angolo {pianta}' + (f', {q}' if q else '')
    return 'Punto' + (f' {q}' if q else ' in mezzo')
