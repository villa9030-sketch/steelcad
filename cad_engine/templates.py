"""Punti di partenza veloci, costruiti con le stesse feature del motore (niente modelli finti).

- telaio: scheletro rettangolare in uno sketch (L × P), telaio sopra all'altezza H, 4 gambe;
- piastra: la piastra della Milestone 1 (larghezza × altezza × spessore, foro al centro).
Tutte le misure sono parametri: si cambiano dopo, e il modello si rigenera.
"""
from __future__ import annotations

from .document import Document
from .errors import SteelCADError


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
    doc.add_feature('structure', 'Telaio', points=pts, members=mem, material=material,
                    template={'kind': 'telaio', 'values': {'L': L, 'P': P, 'H': H, 'profilo': profilo, 'gambe': gambe}})
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


def struttura_vuota(name: str = 'Struttura', material='S235') -> Document:
    """Un nodo nell'origine: da lì si tirano le aste (direzione + lunghezza) e si collegano i nodi."""
    doc = Document(name, material)
    doc.add_feature('structure', 'Struttura', points={'A': [0, 0, 0]}, members=[], material=material)
    return doc


def lamiera(name: str = 'Lamiera', larghezza=500, profondita=300, spessore=2, raggio=None, k=None,
            material='S235') -> Document:
    """Base rettangolare in lamiera. Raggio e K-factor non hanno default: se non li dai tu, la scheda
    Lamiera li chiede prima della prima flangia."""
    doc = Document(name, material)
    for kk, v in (('W', larghezza), ('P', profondita), ('sp', spessore)):
        doc.set_parameter(kk, v)
    sk = doc.add_sketch('XY', 'Base')
    r = sk.rectangle(0, 0, float(larghezza) * 0.97, float(profondita) * 0.97)
    sk.constrain('coincident', r['corners'][0], 'O')
    sk.dimension('length', r['bottom'], value='W')
    sk.dimension('length', r['left'], value='P')
    vuoto = lambda v: v is None or str(v).strip() == ''  # noqa: E731
    doc.add_feature('sheet', name, sketch=sk.id, thickness='sp', radius=None if vuoto(raggio) else raggio,
                    method='k', k=None if vuoto(k) else k, flanges=[])
    return doc


def da_zero(name: str = 'Pezzo', material='S235') -> Document:
    """Solo uno sketch vuoto sul piano XY: si disegna il contorno, poi si sceglie lamiera o piastra."""
    doc = Document(name, material)
    doc.add_sketch('XY', 'Contorno')
    return doc


# =============================================================================== strutture a misure
# Spalla disegnata su un piano, ripetuta a distanza e collegata nodo per nodo (vedi frame._skeletons).
# Tutte le misure sono parametri: cambi H o L e la struttura si ricalcola.

def _spalla(sk, larg: str, alt: str, livelli: list[str]):
    """Due montanti alti `alt` a distanza `larg`, traversi alle altezze `livelli` (espressioni).
    Il primo livello deve essere 0 (a terra) e l'ultimo l'altezza piena."""
    O = 'O'
    br = sk.point(1, 0)                       # in basso a destra
    tl = sk.point(0, 1)                       # in alto a sinistra
    tr = sk.point(1, 1)
    sk.dimension('hdistance', O, br, value=larg)
    sx = sk.line(O, tl, label='montante sinistro')
    dx = sk.line(br, tr, label='montante destro')
    sk.constrain('vertical', sx, auto=True)
    sk.constrain('vertical', dx, auto=True)
    sk.dimension('length', sx, value=alt)
    sk.dimension('length', dx, value=alt)
    for i, h in enumerate(livelli):
        if i == 0:
            a, b = O, br
        elif i == len(livelli) - 1:
            a, b = tl, tr
        else:
            a, b = sk.point(0, i), sk.point(1, i)
            sk.constrain('on_line', a, sx)
            sk.constrain('on_line', b, dx)
            sk.dimension('vdistance', O, a, value=h)
        t = sk.line(a, b, label=f'traverso {i + 1}')
        if i < len(livelli) - 1:              # quello in cima è già orizzontale: montanti uguali e verticali
            sk.constrain('horizontal', t, auto=True)


def scaffale(name: str = 'Scaffale', L=1000, P=400, H=1800, ripiani=4, montanti='30x30x2',
             traversi='40x20x2', material='S235') -> Document:
    """Scaffale: due spalle (montanti + traversi di fianco) a distanza L, collegate a ogni ripiano."""
    n = int(ripiani)
    if n < 2:
        raise SteelCADError('Uno scaffale ha almeno 2 ripiani (a terra e in cima).', code='ripiani')
    doc = Document(name, material)
    for k, v in (('L', L), ('P', P), ('H', H)):
        doc.set_parameter(k, v)
    doc.set_parameter('pr', f'H/{n - 1}')              # passo dei ripiani: uguali, seguono H
    sk = doc.add_sketch('YZ', 'Spalla')
    _spalla(sk, 'P', 'H', ['0'] + [f'{i}*pr' for i in range(1, n - 1)] + ['H'])
    doc.add_feature('structure', name, points={}, members=[], material=material, skeletons=[{
        'id': 'K1', 'sketch': sk.id, 'profile': montanti, 'group': 'Spalle',
        'copies': [[0, 0, 0], ['L', 0, 0]], 'connect': {'profile': traversi, 'group': 'Traversi ripiani'}}],
        template={'kind': 'scaffale', 'values': {'L': L, 'P': P, 'H': H, 'ripiani': n, 'montanti': montanti,
                                                 'traversi': traversi}})
    return doc


def armadio(name: str = 'Telaio armadio', L=800, P=600, H=2000, ripiani=3, profilo='40x40x2',
            material='S235') -> Document:
    """Telaio di un armadio: come lo scaffale, tutto nello stesso profilo (poi si chiude con la lamiera)."""
    doc = scaffale(name, L, P, H, ripiani, profilo, profilo, material)
    st = next(f for f in doc.features if not hasattr(f, 'entities') and f.get('type') == 'structure')
    st['template'] = {'kind': 'armadio', 'values': {'L': L, 'P': P, 'H': H, 'ripiani': ripiani, 'profilo': profilo}}
    return doc


def cancello(name: str = 'Cancello', L=1500, H=1200, telaio='60x60x3', sbarre='20x20x2', passo=120,
             material='S235') -> Document:
    """Cancello: telaio rettangolare e sbarre verticali a passo uguale (sul piano di fronte, XZ)."""
    doc = Document(name, material)
    for k, v in (('L', L), ('H', H)):
        doc.set_parameter(k, v)
    n = max(1, int(round(float(L) / float(passo))) - 1)        # sbarre
    doc.set_parameter('ps', f'L/{n + 1}')              # passo delle sbarre: uguali, seguono L
    sk = doc.add_sketch('XZ', 'Cancello')
    r = sk.rectangle(0, 0, float(L) * 0.97, float(H) * 0.97)
    sk.constrain('coincident', r['corners'][0], 'O')
    sk.dimension('length', r['bottom'], value='L')
    sk.dimension('length', r['left'], value='H')
    ritocchi = {}
    for i in range(1, n + 1):
        a = sk.point(float(L) * i / (n + 1), 0)
        b = sk.point(float(L) * i / (n + 1), float(H))
        sk.constrain('on_line', a, r['bottom'])
        sk.constrain('on_line', b, r['top'])
        sk.dimension('hdistance', 'O', a, value=f'{i}*ps')
        lid = sk.line(a, b, label=f'sbarra {i}')
        sk.constrain('vertical', lid, auto=True)
        ritocchi[f'K1.1.{lid}'] = {'profile': sbarre, 'group': 'Sbarre'}
    doc.add_feature('structure', name, points={}, members=[], material=material, overrides=ritocchi,
                    skeletons=[{'id': 'K1', 'sketch': sk.id, 'profile': telaio, 'group': 'Telaio'}],
                    template={'kind': 'cancello', 'values': {'L': L, 'H': H, 'telaio': telaio, 'sbarre': sbarre,
                                                             'passo': passo}})
    return doc


def struttura_disegno(name: str = 'Struttura', piano='XZ', material='S235') -> Document:
    """Sketch vuoto sul piano scelto: disegni lo scheletro, poi "Crea struttura" mette i tubolari."""
    if piano not in ('XY', 'XZ', 'YZ'):
        raise SteelCADError('Piano sconosciuto: XY (pianta), XZ (fronte) o YZ (fianco).', code='piano')
    doc = Document(name, material)
    doc.add_sketch(piano, 'Scheletro')
    return doc
