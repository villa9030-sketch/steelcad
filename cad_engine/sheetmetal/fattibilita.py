"""Controlli di fattibilità della lamiera (24/10): avvisi in parole semplici, mai blocchi. Si vedono in «Info» con gli
altri avvisi; decide chi disegna.

Le soglie sono le regole d'officina più comuni (piegatura in aria, matrice a V di 8 × spessore):
- flangia corta: il tratto che appoggia sulla matrice (tratto dritto + raggio + spessore) sotto 4 × spessore;
- foro vicino alla piega: il bordo del foro a meno di 2 × spessore dalla striscia della piega (si deforma piegando);
- raggio stretto: sotto 0,5 × spessore per ferro e inox, sotto 1 × spessore per l'alluminio (si crepa);
- U stretta: due flange affacciate più alte della distanza tra loro (piegando la seconda, la prima tocca il punzone).
"""
from __future__ import annotations

from ..units import fmt_mm

V_SU_T = 8                  # matrice a V: 8 × spessore
APPOGGIO_T = V_SU_T / 2     # sulla matrice serve almeno mezza V
FORO_T = 2                  # distanza minima foro-piega, × spessore


def _raggio_minimo(materiale: str, t: float) -> float:
    return (1.0 if str(materiale or '').upper().startswith('AL') else 0.5) * t


def _nome(g) -> str:
    return getattr(g, 'fid', '') or 'la piega'


def controlla(data, materiale: str = '') -> list[str]:
    """Gli avvisi di fattibilità di una lamiera (SheetData). Si calcolano una volta per sviluppo e materiale."""
    memo = data.__dict__.get('_fattibilita')
    if memo is not None and memo[0] == materiale and memo[1] is data.flat:
        return memo[2]
    try:
        out = _controlla(data, materiale)
    except Exception:  # noqa: BLE001 - un controllo che non riesce non deve fermare niente
        out = []
    data.__dict__['_fattibilita'] = (materiale, data.flat, out)
    return out


def _controlla(data, materiale: str) -> list[str]:
    t = data.thickness
    out = []
    pieghe = [g for g in data.flanges if hasattr(g, 'F0') and getattr(g.bend, 'angle', 0) and g.bend.ba > 1e-6]
    # --- flange corte e raggi stretti
    rmin = _raggio_minimo(materiale, t)
    for g in pieghe:
        appoggio = g.lf + g.bend.r + t
        if appoggio < APPOGGIO_T * t - 1e-6:
            out.append(f'Fattibilità: la flangia {_nome(g)} è corta per la piegatrice: appoggia {fmt_mm(round(appoggio, 1))} mm '
                       f'sulla matrice, ne servono almeno {fmt_mm(round(APPOGGIO_T * t, 1))} (matrice a V da '
                       f'{fmt_mm(V_SU_T * t)} mm). Allungala o chiedi una matrice più stretta.')
        if g.bend.r < rmin - 1e-6:
            out.append(f'Fattibilità: raggio interno di {_nome(g)} molto stretto ({fmt_mm(g.bend.r)} mm con spessore '
                       f'{fmt_mm(t)}): rischio di crepe sul lato esterno. Consigliato almeno {fmt_mm(round(rmin, 1))} mm.')
    # --- fori vicino alle pieghe (nello sviluppo)
    if data.flat is not None and pieghe:
        lim = FORO_T * t
        vicini: dict = {}
        for w in data.flat.inner_wires():
            ingombri = _ingombri_su(w, pieghe)
            for g in pieghe:
                s_min, s_max, u_min, u_max = ingombri[id(g)]
                if u_max < g.u0 or u_min > g.u1:
                    continue                                  # il foro non sta di fronte alla piega
                a, b = g.off, g.off + g.bend.ba
                if s_max > a and s_min < b:
                    continue                                  # dentro la striscia: è uno scarico, non un foro
                d = a - s_max if s_max <= a else s_min - b
                if d < lim - 1e-6:
                    vicini.setdefault(_nome(g), []).append(d)
        for nome, ds in vicini.items():
            n = len(ds)
            out.append(f'Fattibilità: {"un foro è" if n == 1 else f"{n} fori sono"} a meno di {fmt_mm(round(lim, 1))} mm '
                       f'dalla piega {nome} ({"a" if n == 1 else "il più vicino a"} {fmt_mm(round(max(min(ds), 0), 1))} mm): '
                       + ('piegando si deforma. Spostalo o fallo dopo la piega.' if n == 1
                          else 'piegando si deformano. Spostali o falli dopo la piega.'))
    # --- U strette: flange affacciate, piegate dalla stessa parte, sui bordi del tratto di base
    base = [g for g in pieghe if not getattr(g, 'parent', None)]
    for i, a in enumerate(base):
        for b in base[i + 1:]:
            if a.direction != b.direction or a.fn.dot(b.fn) > -0.99:
                continue
            gap = abs((b.F0 - a.F0).dot(a.fn)) - a.off - b.off
            if gap <= 0:
                continue
            ua = sorted(((b.fp(b.u0, 0) - a.F0).dot(a.fx), (b.fp(b.u1, 0) - a.F0).dot(a.fx)))
            if ua[1] < a.u0 or ua[0] > a.u1:
                continue                                      # non sono una di fronte all'altra
            alta = max(a.length, b.length)
            if alta > gap + 1e-6:
                out.append(f'Fattibilità: {_nome(a)} e {_nome(b)} fanno una U stretta ({fmt_mm(round(gap, 1))} mm tra le '
                           f'pieghe, flange alte {fmt_mm(round(alta, 1))}): piegando la seconda la prima può toccare il '
                           'punzone. Verifica gli utensili (punzone a collo d’oca) o abbassa le flange.')
    return out


def _ingombri_su(w, pieghe) -> dict:
    """Per ogni piega: s_min, s_max (traverso alla piega) e u_min, u_max (lungo la piega) del foro w. Dagli angoli
    della scatola del foro nello sviluppo (largo, mai stretto). 28/10: prima punto per punto sui lati, 0,35 s con 300
    fori a ogni modifica."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box()
    BRepBndLib.Add_s(w.wrapped, b)
    lo, hi = b.CornerMin(), b.CornerMax()
    angoli = [(x, y, z) for x in (lo.X(), hi.X()) for y in (lo.Y(), hi.Y()) for z in (lo.Z(), hi.Z())]
    out = {}
    for g in pieghe:
        F, n_, x_ = g.F0, g.fn, g.fx
        ss = [(p[0] - F.X) * n_.X + (p[1] - F.Y) * n_.Y + (p[2] - F.Z) * n_.Z for p in angoli]
        uu = [(p[0] - F.X) * x_.X + (p[1] - F.Y) * x_.Y + (p[2] - F.Z) * x_.Z for p in angoli]
        out[id(g)] = (min(ss), max(ss), min(uu), max(uu))
    return out
