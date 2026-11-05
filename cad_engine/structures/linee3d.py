"""Linee dello scheletro che escono dal piano (05/11, idea dallo «sketch 3D» di SolidCraft): un punto che parte da un
altro punto lungo una direzione, per una lunghezza. Serve per i telai che non stanno su un piano solo: le gambe
inclinate di una tramoggia, il corrimano di una scala, una capriata, un tronco di piramide.

Il punto (nei "points" della struttura):

    {"from": "A", "lungo": 800, "verso": ...}             # 800 mm da A, nella direzione detta da "verso"
    {"from": "A", "lungo": 800, "misura": "freccia", ...}  # 800 = quanto sale (o va) nel verso della freccia

"verso" come lo dice l'officina:
- una freccia: "su", "giu", "avanti", "dietro", "destra", "sinistra";
- inclinata: {"freccia": "su", "piega": [["destra", 15], ["dietro", 10]]} = parte verso su, piegata di 15° verso
  destra e di 10° verso dietro (ogni piega si conta dalla freccia, come l'inclinazione di una gamba);
- come un'altra linea: {"come": ["A", "B"]} = parallela alla linea da A a B (con "inverso": true al contrario);
- ad angolo con un'altra linea: {"da": ["A", "B"], "gradi": 90, "verso": "su"} = a 90° dalla linea da A a B,
  girata dalla parte della freccia (o di un vettore [x, y, z]). 90 = a squadra, 0 = parallela.

Le lunghezze e gli angoli possono essere numeri o nomi di misure del modello. Le linee legate ad altre linee le
seguono: cambia la linea da A a B, cambia anche quella parallela.
"""
from __future__ import annotations

import math

import build123d as bd

from ..errors import FeatureError
from ..expressions import evaluate

FRECCE = {'destra': (1, 0, 0), 'sinistra': (-1, 0, 0), 'dietro': (0, 1, 0), 'avanti': (0, -1, 0),
          'su': (0, 0, 1), 'giu': (0, 0, -1)}
PAROLE = {'destra': 'destra', 'sinistra': 'sinistra', 'dietro': 'dietro', 'avanti': 'avanti', 'su': 'su', 'giu': 'giù'}


def freccia(v, what='la direzione') -> bd.Vector:
    """Una freccia ("su") o un vettore [x, y, z], come vettore lungo 1."""
    if isinstance(v, str):
        k = v.strip().lower().replace('ù', 'u')
        if k not in FRECCE:
            raise FeatureError(f'{what[0].upper() + what[1:]}: «{v}» non è una freccia (su, giù, avanti, dietro, '
                               'destra, sinistra).')
        return bd.Vector(*FRECCE[k])
    if isinstance(v, (list, tuple)) and len(v) == 3:
        d = bd.Vector(*(float(c) for c in v))
        if d.length < 1e-9:
            raise FeatureError(f'{what[0].upper() + what[1:]} è nulla.')
        return d.normalized()
    raise FeatureError(f'{what[0].upper() + what[1:]} non si capisce.')


def direzione(verso, params, resolve, what) -> tuple[bd.Vector, bd.Vector | None]:
    """(direzione lunga 1, freccia di riferimento per "misura": "freccia" o None)."""
    if isinstance(verso, (str, list, tuple)):
        d = freccia(verso, what)
        return d, d
    if not isinstance(verso, dict):
        raise FeatureError(f'La direzione del {what} non si capisce.')
    if 'come' in verso:
        a, b = (resolve(k) for k in verso['come'])
        if (b - a).length < 1e-9:
            raise FeatureError(f'La linea da copiare per il {what} è lunga zero.')
        d = (b - a).normalized()
        return (-d if verso.get('inverso') else d), None
    if 'da' in verso:
        a, b = (resolve(k) for k in verso['da'])
        if (b - a).length < 1e-9:
            raise FeatureError(f'La linea di riferimento del {what} è lunga zero.')
        u = (b - a).normalized()
        g = math.radians(evaluate(verso.get('gradi', 90), params, what=f'l’angolo del {what}'))
        v = freccia(verso.get('verso', 'su'), f'il verso del {what}')
        v = v - u * v.dot(u)
        if v.length < 1e-6:
            raise FeatureError(f'Il {what}: la freccia scelta va lungo la linea di riferimento, scegline un’altra.')
        v = v.normalized()
        return (u * math.cos(g) + v * math.sin(g)).normalized(), None
    base = freccia(verso.get('freccia', 'su'), f'la freccia del {what}')
    d = bd.Vector(base.X, base.Y, base.Z)
    for k, (dove, gradi) in enumerate(verso.get('piega') or []):
        g = evaluate(gradi, params, what=f'la piega del {what}')
        if not -89 <= g <= 89:
            raise FeatureError(f'Il {what}: la piega di {g:g}° è troppa, va da 0 a 89°.')
        p = freccia(dove, f'la piega del {what}')
        if abs(p.dot(base)) > 1e-6:
            raise FeatureError(f'Il {what}: la piega va di lato alla freccia (non {PAROLE.get(dove, dove)}).')
        d = d + p * math.tan(math.radians(g))
    return d.normalized(), base


def punto(k, v, params, resolve, nome) -> bd.Vector:
    what = f'punto {k} di "{nome}"'
    base = resolve(v['from'])
    d, rif = direzione(v.get('verso', 'su'), params, resolve, what)
    lung = evaluate(v['lungo'], params, what=f'la lunghezza del {what}')
    if v.get('misura') == 'freccia' and rif is not None:
        c = d.dot(rif)
        if c < 1e-6:
            raise FeatureError(f'Il {what} non va nel verso della freccia: misura la lunghezza lungo il tubo.')
        lung = lung / c
    if lung <= 0:
        raise FeatureError(f'La lunghezza del {what} deve essere maggiore di zero.')
    return base + d * lung
