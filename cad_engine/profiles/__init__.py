"""Profili da carpenteria: sezione 2D vera (con i raggi), area, peso al metro, nome leggibile.

Come si scrive un profilo (come lo direbbe l'officina):

    "40x40x3"            tubolare quadro       (anche "SHS 40x40x3", "Q 40x40x3")
    "60x40x3"            tubolare rettangolare (anche "RHS 60x40x3")
    "Ø48.3x3.2"          tubo tondo            (anche "CHS 48.3x3.2", "tondo 48.3x3.2")
    "piatto 50x5"        piatto 50 x 5
    "L 40x40x4"          angolare laminato (da catalogo)
    "IPE 100", "HEA 120", "HEB 200"   (da catalogo)
    "UPN 100"            U laminata (da catalogo, ali col loro spessore medio)
    "U 80x40x3"          U piegata a freddo (h x b x spessore), raggio interno = spessore
    "C 100x50x20x2"      C piegata con risvolto (h x b x risvolto x spessore)

Sistema di riferimento della sezione: X = larghezza (b), Y = altezza (h),
centro = centro dell'ingombro. Le misure tecniche (raggi dei tubolari) seguono
EN 10219-2: raggio esterno 2t fino a 6 mm, 2,5t fino a 10 mm, 3t oltre.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import build123d as bd

from ..errors import SteelCADError
from ..units import fmt_mm

CATALOGO = Path(__file__).with_name('catalog.json')


@dataclass(frozen=True)
class Profile:
    family: str                  # SHS RHS CHS FLAT L IPE HEA HEB UPN U C
    name: str                    # come si mostra: "40×40×3", "IPE 100"
    dims: tuple                  # misure principali, per il confronto
    width: float                 # ingombro X
    height: float                # ingombro Y
    params: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def description(self) -> str:
        nomi = {'SHS': 'Tubolare quadro', 'RHS': 'Tubolare rettangolare', 'CHS': 'Tubo tondo', 'FLAT': 'Piatto',
                'L': 'Angolare', 'IPE': 'Trave', 'HEA': 'Trave', 'HEB': 'Trave', 'UPN': 'Profilato',
                'U': 'U piegata', 'C': 'C piegata'}
        return f'{nomi[self.family]} {self.name}'      # "Trave IPE 100", non "Trave IPE IPE 100"

    def section(self) -> bd.Face:
        return _section(self)

    @property
    def area_mm2(self) -> float:
        return _area(self)

    def kg_m(self, density_g_cm3: float) -> float:
        # mm² * 1000 mm = mm³ per metro; mm³ -> cm³ / 1000; g -> kg / 1000
        return self.area_mm2 * density_g_cm3 / 1000.0


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads(CATALOGO.read_text(encoding='utf-8'))


def _num(s: str) -> float:
    return float(s.replace(',', '.'))


def parse(text: str) -> Profile:
    """Dal nome scritto dall'utente al profilo. Errore chiaro se non si capisce."""
    t = ' '.join(str(text).strip().replace('×', 'x').replace('X', 'x').split())
    low = t.lower()
    m = re.fullmatch(r'(ipe|hea|heb)\s*(\d+)', low)
    if m:
        fam, size = m.group(1).upper(), m.group(2)
        voce = catalog()[fam].get(size)
        if not voce:
            disponibili = ', '.join(catalog()[fam])
            raise SteelCADError(f'{fam} {size} non è nel catalogo. Misure disponibili: {disponibili}.',
                                code='profilo_sconosciuto')
        return Profile(fam, f'{fam} {size}', (voce['h'], voce['b'], voce['tw'], voce['tf'], voce['r']),
                       voce['b'], voce['h'], dict(voce))
    m = re.fullmatch(r'upn\s*(\d+)', low)
    if m:
        voce = catalog()['UPN'].get(m.group(1))
        if not voce:
            raise SteelCADError(f'UPN {m.group(1)} non è nel catalogo. Misure disponibili: {", ".join(catalog()["UPN"])}.',
                                code='profilo_sconosciuto')
        return Profile('UPN', f'UPN {m.group(1)}', (voce['h'], voce['b'], voce['tw'], voce['tf']), voce['b'], voce['h'], dict(voce))
    m = re.fullmatch(r'l\s*([\d.,]+)x([\d.,]+)x([\d.,]+)', low)
    if m:
        chiave = 'x'.join(fmt_mm(_num(g)).replace(',', '.') for g in m.groups())
        voce = catalog()['L'].get(chiave)
        if not voce:
            raise SteelCADError(f'L’angolare L {chiave} non è nel catalogo. Aggiungilo in catalog.json '
                                f'(disponibili: {", ".join(catalog()["L"])}).', code='profilo_sconosciuto')
        return Profile('L', f'L {chiave.replace("x", "×")}', (voce['a'], voce['b'], voce['t']),
                       voce['b'], voce['a'], dict(voce))
    m = re.fullmatch(r'(?:piatto|flat|pl)\s*([\d.,]+)x([\d.,]+)', low)
    if m:
        b, s = map(_num, m.groups())
        _pos(text, b, s)
        return Profile('FLAT', f'{fmt_mm(b)}×{fmt_mm(s)}', (b, s), b, s, {'b': b, 't': s})
    m = re.fullmatch(r'(?:ø|chs\s*|tondo\s*|d\s*)([\d.,]+)x([\d.,]+)', low)
    if m:
        d, s = map(_num, m.groups())
        _pos(text, d, s)
        if s * 2 >= d:
            raise SteelCADError(f'Il tubo {text}: lo spessore {fmt_mm(s)} è troppo grande per il diametro '
                                f'{fmt_mm(d)}.', code='profilo_non_valido')
        return Profile('CHS', f'Ø{fmt_mm(d)}×{fmt_mm(s)}', (d, s), d, d, {'d': d, 't': s})
    m = re.fullmatch(r'u\s*([\d.,]+)x([\d.,]+)x([\d.,]+)', low)
    if m:
        h, b, s = map(_num, m.groups())
        _pos(text, h, b, s)
        _cold(text, s, h, b)
        return Profile('U', f'U {fmt_mm(h)}×{fmt_mm(b)}×{fmt_mm(s)}', (h, b, s), b, h, {'h': h, 'b': b, 't': s, 'ri': s})
    m = re.fullmatch(r'c\s*([\d.,]+)x([\d.,]+)x([\d.,]+)x([\d.,]+)', low)
    if m:
        h, b, c, s = map(_num, m.groups())
        _pos(text, h, b, c, s)
        _cold(text, s, h, b, c)
        return Profile('C', f'C {fmt_mm(h)}×{fmt_mm(b)}×{fmt_mm(c)}×{fmt_mm(s)}', (h, b, c, s), b, h,
                       {'h': h, 'b': b, 'c': c, 't': s, 'ri': s})
    m = re.fullmatch(r'(?:shs|rhs|q|r|tubolare)?\s*([\d.,]+)x([\d.,]+)x([\d.,]+)', low)
    if m:
        h, b, s = map(_num, m.groups())
        _pos(text, h, b, s)
        if 2 * s >= min(h, b):
            raise SteelCADError(f'Il tubolare {text}: lo spessore {fmt_mm(s)} è troppo grande per il lato '
                                f'{fmt_mm(min(h, b))}.', code='profilo_non_valido')
        ro = 2 * s if s <= 6 else (2.5 * s if s <= 10 else 3 * s)
        fam = 'SHS' if h == b else 'RHS'
        return Profile(fam, f'{fmt_mm(h)}×{fmt_mm(b)}×{fmt_mm(s)}', (h, b, s), b, h,
                       {'h': h, 'b': b, 't': s, 'ro': ro, 'ri': ro - s})
    raise SteelCADError(f'Non capisco il profilo "{text}". Esempi: 40x40x3, 60x40x3, Ø48.3x3.2, piatto 50x5, '
                        'L 40x40x4, IPE 100, HEA 120, UPN 100, U 80x40x3.', code='profilo_sconosciuto')


def _pos(text, *vals):
    if any(v <= 0 for v in vals):
        raise SteelCADError(f'Il profilo {text} ha misure a zero o negative.', code='profilo_non_valido')


def _cold(text, s, *lati):
    if any(2 * s >= l for l in lati):
        raise SteelCADError(f'Il profilo piegato {text}: lo spessore è troppo grande per le ali.',
                            code='profilo_non_valido')


def _poly(pts) -> bd.Face:
    return bd.Face(bd.Wire.make_polygon([bd.Vector(x, y) for x, y in pts], close=True))


def _corners(face: bd.Face, pts, r) -> bd.Face:
    if r <= 0:
        return face
    vs = [v for v in face.vertices() if any(abs(v.X - x) < 1e-9 and abs(v.Y - y) < 1e-9 for x, y in pts)]
    return face.fillet_2d(r, vs)


@lru_cache(maxsize=256)
def _section(p: Profile) -> bd.Face:
    q = p.params
    f = p.family
    if f in ('SHS', 'RHS'):
        o = bd.RectangleRounded(q['b'], q['h'], q['ro'])
        i = bd.RectangleRounded(q['b'] - 2 * q['t'], q['h'] - 2 * q['t'], q['ri']) if q['ri'] > 0 else \
            bd.Rectangle(q['b'] - 2 * q['t'], q['h'] - 2 * q['t'])
        return (o - i).faces()[0]
    if f == 'CHS':
        return (bd.Circle(q['d'] / 2) - bd.Circle(q['d'] / 2 - q['t'])).faces()[0]
    if f == 'FLAT':
        return bd.Rectangle(q['b'], q['t']).faces()[0]
    if f in ('IPE', 'HEA', 'HEB'):
        h, b, tw, tf, r = q['h'], q['b'], q['tw'], q['tf'], q['r']
        pts = [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, -h / 2 + tf), (tw / 2, -h / 2 + tf), (tw / 2, h / 2 - tf),
               (b / 2, h / 2 - tf), (b / 2, h / 2), (-b / 2, h / 2), (-b / 2, h / 2 - tf), (-tw / 2, h / 2 - tf),
               (-tw / 2, -h / 2 + tf), (-b / 2, -h / 2 + tf)]
        inner = [(s1 * tw / 2, s2 * (h / 2 - tf)) for s1 in (-1, 1) for s2 in (-1, 1)]
        return _corners(_poly(pts), inner, r)
    if f == 'UPN':                         # la U laminata: anima a sinistra, ali verso destra
        # ali inclinate dell'8% (EN 10279), lo spessore tf a metà dell'ala: più spesse verso l'anima
        h, b, tw, tf = q['h'], q['b'], q['tw'], q['tf']
        xm = tw + (b - tw) / 2
        sp = lambda x: tf + 0.08 * (xm - x)  # noqa: E731
        pts = [(0, 0), (b, 0), (b, sp(b)), (tw, sp(tw)), (tw, h - sp(tw)), (b, h - sp(b)), (b, h), (0, h)]
        cx, cy = b / 2, h / 2
        face = _poly([(x - cx, y - cy) for x, y in pts])
        face = _corners(face, [(tw - cx, sp(tw) - cy), (tw - cx, h - sp(tw) - cy)], q['r1'])
        return _corners(face, [(b - cx, sp(b) - cy), (b - cx, h - sp(b) - cy)], q['r2'])
    if f == 'L':
        a, b, t, r1, r2 = q['a'], q['b'], q['t'], q['r1'], q['r2']
        cx, cy = b / 2, a / 2
        pts = [(0, 0), (b, 0), (b, t), (t, t), (t, a), (0, a)]
        face = _poly([(x - cx, y - cy) for x, y in pts])
        face = _corners(face, [(t - cx, t - cy)], r1)
        face = _corners(face, [(b - cx, t - cy), (t - cx, a - cy)], r2)
        return face
    if f in ('U', 'C'):
        h, b, t, ri = q['h'], q['b'], q['t'], q['ri']
        if f == 'U':
            pts = [(0, 0), (b, 0), (b, t), (t, t), (t, h - t), (b, h - t), (b, h), (0, h)]
            fuori, dentro = [(0, 0), (0, h)], [(t, t), (t, h - t)]
        else:
            c = q['c']
            pts = [(0, 0), (b, 0), (b, c), (b - t, c), (b - t, t), (t, t), (t, h - t), (b - t, h - t),
                   (b - t, h - c), (b, h - c), (b, h), (0, h)]
            fuori, dentro = [(0, 0), (0, h), (b, 0), (b, h)], [(t, t), (t, h - t), (b - t, t), (b - t, h - t)]
        cx, cy = b / 2, h / 2
        face = _poly([(x - cx, y - cy) for x, y in pts])
        face = _corners(face, [(x - cx, y - cy) for x, y in fuori], ri + t)
        face = _corners(face, [(x - cx, y - cy) for x, y in dentro], ri)
        return face
    raise SteelCADError(f'Famiglia di profilo {f} sconosciuta.')


def _area(p: Profile) -> float:
    return _section(p).area


def outer_envelope(p: Profile) -> bd.Face:
    """La sagoma contro cui si taglia un'asta "a battuta".

    Tubolari quadri/rettangolari e profilati: il rettangolo d'ingombro, cioè
    taglio dritto sulla faccia piana (come in officina: lo spigolo arrotondato
    lascia solo un piccolo spazio). Tubo tondo: il cerchio, cioè taglio a sella.
    """
    q = p.params
    if p.family == 'CHS':
        return bd.Circle(q['d'] / 2).faces()[0]
    return bd.Rectangle(p.width, p.height).faces()[0]
