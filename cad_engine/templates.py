"""Punti di partenza veloci, costruiti con le stesse feature del motore (niente modelli finti).

- telaio: scheletro rettangolare in uno sketch (L × P), telaio sopra all'altezza H, 4 gambe;
- piastra: la piastra della Milestone 1 (larghezza × altezza × spessore, foro al centro).
Tutte le misure sono parametri: si cambiano dopo, e il modello si rigenera.
"""
from __future__ import annotations

from .document import Document


def telaio(name: str = 'Telaio', L=2000, P=1000, H=900, profilo='40x40x3', gambe='40x40x3',
           material='S235') -> Document:
    doc = Document(name, material)
    for k, v in (('L', L), ('P', P), ('H', H)):
        doc.set_parameter(k, v)
    sk = doc.add_sketch('XY', 'Scheletro')
    r = sk.rectangle(0, 0, float(L) * 0.97, float(P) * 0.97)
    sk.constrain('coincident', r['corners'][0], 'O')
    sk.dimension('length', r['bottom'], value='L')
    sk.dimension('length', r['left'], value='P')
    pts = {f'T{i}': {'sketch': sk.id, 'point': c, 'offset': [0, 0, 'H']} for i, c in enumerate(r['corners'])}
    pts.update({f'F{i}': {'sketch': sk.id, 'point': c} for i, c in enumerate(r['corners'])})
    mem = [{'id': f'M{i + 1}', 'group': 'Telaio superiore', 'from': f'T{i}', 'to': f'T{(i + 1) % 4}',
            'profile': profilo} for i in range(4)]
    mem += [{'id': f'G{i + 1}', 'group': 'Gambe', 'from': f'F{i}', 'to': f'T{i}', 'profile': gambe}
            for i in range(4)]
    doc.add_feature('structure', 'Telaio', points=pts, members=mem, material=material)
    return doc


def piastra(name: str = 'Piastra', larghezza=300, altezza=200, spessore=5, foro=30, material='S235') -> Document:
    doc = Document(name, material)
    for k, v in (('larghezza', larghezza), ('altezza', altezza), ('spessore', spessore), ('foro', foro)):
        doc.set_parameter(k, v)
    sk = doc.add_sketch('XY', 'Profilo')
    r = sk.rectangle(0, 0, float(larghezza) * 0.97, float(altezza) * 0.97)
    sk.constrain('coincident', r['corners'][0], 'O')
    sk.dimension('length', r['bottom'], value='larghezza')
    sk.dimension('length', r['left'], value='altezza')
    c = sk.circle((float(larghezza) / 2, float(altezza) / 2), float(foro) / 2 * 0.9)
    sk.dimension('diameter', c, value='foro')
    sk.constrain('symmetric', r['corners'][0], r['corners'][2], sk.entities[c]['center'])
    doc.add_feature('extrude', 'Piastra', sketch=sk.id, distance='spessore', operation='new')
    return doc
