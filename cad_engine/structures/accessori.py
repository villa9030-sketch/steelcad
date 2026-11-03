"""Piedi e tappi delle strutture in tubo (03/11): quello che in officina si mette dopo aver saldato il telaio.

Nella definizione della struttura:

    "piedi": {"tipo": "piastra", "lato": 80, "sp": 6, "fori": 4, "foro": 9, "dal_bordo": 15}
    "piedi": {"tipo": "piedino", "misura": "M10"}             (lamierino filettato saldato + piedino da comprare)
    "tappi": {"tipo": "plastica"}                              (da comprare)
    "tappi": {"tipo": "lamierino", "sp": 3}                    (saldato sulla testa)

I piedi vanno sotto tutte le gambe a terra (tubi in piedi che arrivano più in basso di tutti), i tappi su tutte le
teste libere dei tubi (una testa tagliata dritta che non batte contro niente). Entrano in distinta con le loro righe.
"""
from __future__ import annotations

from dataclasses import dataclass

import build123d as bd

from .. import materials
from ..errors import FeatureError
from ..profiles import outer_envelope
from ..units import fmt_mm

# piedini regolabili a vite: misura → (Ø base, altezza con la vite a metà)
PIEDINI = {'M8': (30, 25), 'M10': (40, 30), 'M12': (50, 35), 'M16': (60, 45)}
TUBI = ('SHS', 'RHS', 'CHS')


@dataclass
class Accessorio:
    id: str               # «PIEDE-G1», «TAPPO-M3-1»
    tipo: str             # piastra | lamierino | piedino | tappo
    nome: str             # dove va, in parole d'officina
    solid: object
    descrizione: str      # la riga di distinta
    acquisto: bool        # da comprare (piedini, tappi in plastica) o da fare (piastre, lamierini)
    kg: float
    material: str
    tubo: str             # l'asta su cui va
    spessore: float | None = None
    dove: str = ''        # il nome del tubo su cui va («Gamba davanti a sinistra»)


def _kg(solid, mat) -> float:
    return solid.volume * materials.get(mat).density_g_cm3 / 1e6


def _num(spec, k, default, nome, minimo=0.0) -> float:
    v = spec.get(k, default)
    try:
        x = float(str(v).replace(',', '.'))
    except (TypeError, ValueError):
        raise FeatureError(f'{nome}: «{v}» non è un numero.') from None
    if x < minimo:
        raise FeatureError(f'{nome}: deve essere almeno {fmt_mm(minimo)}.')
    return x


def gambe_a_terra(members) -> list:
    """Le gambe che toccano terra: tubi in piedi che arrivano giù quanto il tubo più basso."""
    if not members:
        return []
    boxes = {m.id: m.solid.bounding_box() for m in members}
    z0 = min(b.min.Z for b in boxes.values())
    return [m for m in members if abs(m.w.Z) > 0.95 and boxes[m.id].min.Z < z0 + 0.5]


def _piede(m, spec, mat, nome) -> list:
    b = m.solid.bounding_box()
    cx, cy, z = (b.min.X + b.max.X) / 2, (b.min.Y + b.max.Y) / 2, b.min.Z
    hx, hy = (b.max.X - b.min.X) / 2, (b.max.Y - b.min.Y) / 2
    tipo = spec.get('tipo', 'piastra')
    if tipo == 'piastra':
        lato = _num(spec, 'lato', 80, 'Lato della piastra', 10)
        sp = _num(spec, 'sp', 6, 'Spessore della piastra', 1)
        fori = int(_num(spec, 'fori', 4, 'Fori'))
        d = _num(spec, 'foro', 9, 'Diametro dei fori', 0)
        e = _num(spec, 'dal_bordo', 15, 'Fori dal bordo', 0)
        if lato < 2 * max(hx, hy) - 1e-6:
            raise FeatureError(f'La piastra da {fmt_mm(lato)} è più piccola del tubo: almeno {fmt_mm(round(2 * max(hx, hy)))}.')
        s = bd.Box(lato, lato, sp, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)).moved(bd.Location((cx, cy, z)))
        if fori and d > 0:
            a = lato / 2 - e
            if a - d / 2 < max(hx, hy) - 1e-6 or e < d / 2:
                raise FeatureError(f'I fori Ø{fmt_mm(d)} a {fmt_mm(e)} dal bordo finiscono sotto il tubo o fuori dalla '
                                   'piastra: fai la piastra più grande o i fori più verso il bordo.')
            posti = {4: [(a, a), (-a, a), (a, -a), (-a, -a)], 2: [(a, a), (-a, -a)]}.get(fori)
            if posti is None:
                raise FeatureError('Fori: 0, 2 (in diagonale) o 4 (negli angoli).')
            for px, py in posti:
                s = s - bd.Cylinder(d / 2, sp * 3).moved(bd.Location((cx + px, cy + py, z - sp / 2)))
        s = s.solids()[0] if not isinstance(s, bd.Solid) else s
        fo = f' con {fori} fori Ø{fmt_mm(d)}' if fori and d > 0 else ''
        return [Accessorio(f'PIEDE-{m.id}', 'piastra', f'Piastra sotto {nome}', s,
                           f'Piastra {fmt_mm(lato)}×{fmt_mm(lato)} sp. {fmt_mm(sp)}{fo}', False, _kg(s, mat), mat, m.id, sp)]
    if tipo == 'piedino':
        mis = str(spec.get('misura') or 'M10').upper().replace(' ', '')
        if mis not in PIEDINI:
            raise FeatureError(f'Piedino {mis}: scegli tra {", ".join(PIEDINI)}.')
        dbase, h = PIEDINI[mis]
        dv = float(mis[1:])
        sp = 5.0
        # il lamierino con la madrevite, saldato sotto il tubo (grande quanto il tubo)
        lam = bd.Box(2 * hx, 2 * hy, sp, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)).moved(
            bd.Location((cx, cy, z)))
        lam = lam - bd.Cylinder(dv * 0.85 / 2, sp * 3).moved(bd.Location((cx, cy, z - sp / 2)))
        lam = lam.solids()[0] if not isinstance(lam, bd.Solid) else lam
        zb = z - sp
        vite = bd.Cylinder(dv / 2, h - 8, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)).moved(
            bd.Location((cx, cy, zb)))
        base = bd.Cylinder(dbase / 2, 8, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)).moved(
            bd.Location((cx, cy, zb - (h - 8))))
        piedino = bd.Compound([vite, base])
        return [Accessorio(f'PIEDE-{m.id}', 'lamierino', f'Lamierino sotto {nome}', lam,
                           f'Lamierino {fmt_mm(round(2 * hx, 1))}×{fmt_mm(round(2 * hy, 1))} sp. {fmt_mm(sp)} con foro '
                           f'filettato {mis}', False, _kg(lam, mat), mat, m.id, sp),
                Accessorio(f'PIEDINO-{m.id}', 'piedino', f'Piedino sotto {nome}', piedino,
                           f'Piedino regolabile {mis}, base Ø{fmt_mm(dbase)}', True, 0.0, '', m.id)]
    raise FeatureError('Piedi: piastra o piedino regolabile.')


def _teste_libere(members, coperte: set) -> list:
    """(asta, 0|1, centro della testa, verso fuori) delle teste dei tubi tagliate dritte che non battono contro
    niente: lì va un tappo. `coperte`: (id, 0|1) già chiuse (da un piede)."""
    boxes = [(o, o.solid.bounding_box()) for o in members]
    out = []
    for m in members:
        if m.profile.family not in TUBI:
            continue
        w = m.w
        for i in (0, 1):
            if (m.id, i) in coperte or abs(m.cuts[i]) > 1e-6:
                continue
            fuori = -w if i == 0 else w
            asse = m.start + m.origin_shift
            c = asse + w * (m.testa if i == 0 else m.testa + m.length)
            sonda = c + fuori * 1.0
            chiusa = False
            for o, b in boxes:
                if o is m:
                    continue
                if (b.min.X - 1e-3 <= sonda.X <= b.max.X + 1e-3 and b.min.Y - 1e-3 <= sonda.Y <= b.max.Y + 1e-3
                        and b.min.Z - 1e-3 <= sonda.Z <= b.max.Z + 1e-3):
                    chiusa = True
                    break
            if not chiusa:
                out.append((m, i, c, fuori))
    return out


def _tappo(m, i, c, fuori, spec, mat, nome) -> Accessorio:
    tipo = spec.get('tipo', 'plastica')
    sez = outer_envelope(m.profile)
    if tipo == 'lamierino':
        sp = _num(spec, 'sp', 3, 'Spessore del lamierino', 1)
    elif tipo == 'plastica':
        sp = 2.0
    else:
        raise FeatureError('Tappi: in plastica o lamierino saldato.')
    plane = bd.Plane(origin=c, x_dir=m.x, z_dir=fuori)
    s = bd.extrude(plane.location * sez, amount=sp)
    s = s if isinstance(s, bd.Solid) else s.solids()[0]
    if tipo == 'lamierino':
        if m.profile.family == 'CHS':
            dim = f'Ø{fmt_mm(round(m.profile.width, 1))}'
        else:
            dim = f'{fmt_mm(round(m.profile.width, 1))}×{fmt_mm(round(m.profile.height, 1))}'
        return Accessorio(f'TAPPO-{m.id}-{i}', 'lamierino', f'Lamierino in testa a {nome}', s,
                          f'Lamierino {dim} sp. {fmt_mm(sp)} (chiusura testa tubo)', False, _kg(s, mat), mat, m.id, sp)
    return Accessorio(f'TAPPO-{m.id}-{i}', 'tappo', f'Tappo in testa a {nome}', s,
                      f'Tappo in plastica per tubo {m.profile.name}', True, 0.0, '', m.id)


def calcola(members, fdef, nomi) -> list:
    """Gli accessori della struttura (piedi e tappi), dalla definizione."""
    out = []
    mat = fdef.get('material', 'S235')
    coperte = set()
    piedi = fdef.get('piedi')
    if piedi:
        gambe = gambe_a_terra(members)
        for m in gambe:
            out += _piede(m, piedi, mat, _minuscolo(nomi.get(m.id, m.id)))
            coperte.add((m.id, 0 if m.start.Z < m.end.Z else 1))
    tappi = fdef.get('tappi')
    if tappi:
        for m, i, c, fuori in _teste_libere(members, coperte):
            out.append(_tappo(m, i, c, fuori, tappi, mat, _minuscolo(nomi.get(m.id, m.id))))
    for a in out:
        a.dove = nomi.get(a.tubo, a.tubo)
    return out


def _minuscolo(nome: str) -> str:
    """«Gamba davanti a sinistra» → «gamba davanti a sinistra» (dentro una frase)."""
    return nome[:1].lower() + nome[1:] if nome else nome


def righe(structures) -> list:
    """Le righe di distinta degli accessori: uguali insieme, con dove vanno."""
    from collections import OrderedDict
    gruppi: OrderedDict = OrderedDict()
    for st in structures:
        for a in getattr(st, 'accessori', None) or []:
            k = (a.descrizione, a.material, a.acquisto)
            r = gruppi.get(k)
            if r is None:
                r = gruppi[k] = {'description': a.descrizione, 'material': a.material, 'acquisto': a.acquisto,
                                 'tipo': a.tipo, 'qty': 0, 'kg_each': a.kg, 'thickness_mm': a.spessore, 'ids': [],
                                 'dove': []}
            r['qty'] += 1
            r['ids'].append(f'{st.id}/{a.id}')
            r['dove'].append(a.dove)
    for r in gruppi.values():
        r['kg_total'] = r['kg_each'] * r['qty']
    return list(gruppi.values())
