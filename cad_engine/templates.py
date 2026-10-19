"""Punti di partenza veloci, costruiti con le stesse feature del motore (niente modelli finti).

- telaio: scheletro rettangolare in uno sketch (L × P), telaio sopra all'altezza H, 4 gambe;
- piastra: la piastra della Milestone 1 (larghezza × altezza × spessore, foro al centro).
Tutte le misure sono parametri: si cambiano dopo, e il modello si rigenera.
"""
from __future__ import annotations

import math

from .document import Document
from .errors import SteelCADError


def _misura(v, nome: str, zero: bool = False) -> float:
    """Una misura scritta dall'utente: un numero, maggiore di zero (o almeno zero se zero=True)."""
    try:
        x = float(str(v).replace(',', '.'))
    except (TypeError, ValueError):
        raise SteelCADError(f'{nome}: "{v}" non è un numero.', code='misura') from None
    if not math.isfinite(x) or x < 0 or (x == 0 and not zero):
        raise SteelCADError(f'{nome}: {v} non va, serve una misura maggiore di zero.', code='misura')
    return x


def _intero(v, nome: str, minimo: int) -> int:
    x = _misura(v, nome, zero=True)
    if x != int(x) or x < minimo:
        raise SteelCADError(f'{nome}: serve un numero intero, almeno {minimo}.', code='misura')
    return int(x)


def telaio(name: str = 'Telaio', L=2000, P=1000, H=900, profilo='40x40x3', gambe='40x40x3',
           material='S235') -> Document:
    for k, v in (('Lunghezza', L), ('Profondità', P), ('Altezza', H)):
        _misura(v, k)
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
    for k, v in (('Larghezza', larghezza), ('Altezza', altezza), ('Spessore', spessore), ('Foro', foro)):
        _misura(v, k)
    if float(foro) >= min(float(larghezza), float(altezza)):
        raise SteelCADError('Il foro è più grande della piastra.', code='misura')
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
            material='S235', metodo='k', bd90=None) -> Document:
    """Base rettangolare in lamiera. Raggio e K-factor non hanno default: se non li dai tu, la scheda
    Lamiera li chiede prima della prima flangia. metodo: k, din6935 o bd90 (con la deduzione bd90)."""
    for kk, v in (('Larghezza', larghezza), ('Profondità', profondita), ('Spessore', spessore)):
        _misura(v, kk)
    if float(spessore) >= min(float(larghezza), float(profondita)) / 2:
        raise SteelCADError('Lo spessore è troppo grande per una lamiera così piccola.', code='misura')
    if raggio not in (None, ''):
        _misura(raggio, 'Raggio interno', zero=True)
    if k not in (None, '') and not 0 <= _misura(k, 'K-factor', zero=True) <= 1:
        raise SteelCADError('Il K-factor deve stare tra 0 e 1 (di solito 0,3–0,5).', code='misura')
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
                    method=metodo or 'k', k=None if vuoto(k) else k, bd90=None if vuoto(bd90) else bd90, flanges=[])
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
    for k, v in (('Lunghezza', L), ('Profondità', P), ('Altezza', H)):
        _misura(v, k)
    n = _intero(ripiani, 'Ripiani', 2)
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
    for k, v in (('Lunghezza', L), ('Altezza', H), ('Passo delle sbarre', passo)):
        _misura(v, k)
    if float(passo) >= float(L):
        raise SteelCADError('Il passo delle sbarre è più lungo del cancello.', code='misura')
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


# =============================================================================== forme di lamiera
def tramoggia_cassone(name: str = 'Tramoggia con cassone', A=1000, B=1000, Hc=700, a=250, b=250, Ht=700, ex=0, ey=0,
                      bordo=40, angoli_bordo='aperti', flangia=0, smusso=0, spessore=3, riferimento='esterno',
                      divisione='auto', foglio='1500x3000', raggio=None, k=None, material='S235') -> Document:
    """Cassone a pareti verticali (A × B, alto Hc; Hc = 0: solo tramoggia) sopra una tramoggia a falde piane fino
    allo scarico a × b (alto Ht, centro spostato di ex, ey). Bordo superiore piegato in fuori e flangia dello
    scarico (0 = niente), angoli smussati (0 = vivi). La forma si divide in pezzi da piegare: più pieghe possibile,
    ogni pezzo nel foglio; le scelte piega/saldatura si cambiano spigolo per spigolo."""
    for kk, v in (('Lato A', A), ('Lato B', B), ('Scarico a', a), ('Scarico b', b), ('Altezza tramoggia', Ht),
                  ('Spessore', spessore)):
        _misura(v, kk)
    for kk, v in (('Altezza cassone', Hc), ('Bordo', bordo), ('Flangia scarico', flangia), ('Smusso', smusso)):
        _misura(v, kk, zero=True)
    for kk, v in (('Spostamento X', ex), ('Spostamento Y', ey)):
        try:
            float(str(v).replace(',', '.'))
        except ValueError:
            raise SteelCADError(f'{kk}: "{v}" non è un numero.', code='misura') from None
    try:
        foglio_l = [float(x) for x in str(foglio).lower().replace('×', 'x').replace(' ', '').split('x')]
        assert len(foglio_l) == 2 and min(foglio_l) > 0
    except (ValueError, AssertionError):
        raise SteelCADError('Foglio: scrivilo come 1500x3000.', code='misura') from None
    angoli_bordo = str(angoli_bordo)
    if angoli_bordo not in ('aperti', '45'):
        raise SteelCADError('Angoli del bordo: aperti (scasso) o a 45°.', code='misura')
    doc = Document(name, material)
    for kk, v in (('A', A), ('B', B), ('Hc', Hc), ('a', a), ('b', b), ('Ht', Ht), ('ex', ex), ('ey', ey),
                  ('bordo', bordo), ('flangia', flangia), ('smusso', smusso), ('sp', spessore)):
        doc.set_parameter(kk, v)
    sez, fasce = [], []
    if float(flangia) > 0:
        sez.append({'w': 'a+2*flangia', 'd': 'b+2*flangia', 'z': 0, 'ex': 'ex', 'ey': 'ey', 'smusso': 'smusso*a/A', 'nome': 'flangia scarico'})
        fasce.append('flangia scarico')
    sez.append({'w': 'a', 'd': 'b', 'z': 0, 'ex': 'ex', 'ey': 'ey', 'smusso': 'smusso*a/A', 'nome': 'scarico'})
    fasce.append('tramoggia')
    sez.append({'w': 'A', 'd': 'B', 'z': 'Ht', 'smusso': 'smusso', 'nome': 'cambio di pendenza'})
    if float(Hc) > 0:
        fasce.append('cassone')
        sez.append({'w': 'A', 'd': 'B', 'z': 'Ht+Hc', 'smusso': 'smusso', 'nome': 'bocca'})
    if float(bordo) > 0:
        fasce.append('bordo')
        sez.append({'w': 'A+2*bordo', 'd': 'B+2*bordo', 'z': 'Ht+Hc', 'smusso': 'smusso', 'nome': 'bordo'})
    vuoto = lambda v: v is None or str(v).strip() == ''  # noqa: E731
    aperte = [f for f in ('bordo', 'flangia scarico') if f in fasce] if angoli_bordo == 'aperti' else []
    doc.add_feature('sheet_shape', name, kind='sezioni', sezioni=sez, fasce=fasce, aperte=aperte, thickness='sp',
                    ref=riferimento, foglio=foglio_l, divisione=divisione, spigoli={},
                    radius=None if vuoto(raggio) else raggio, k=None if vuoto(k) else k,
                    template={'kind': 'tramoggia_cassone', 'values': {
                        'A': A, 'B': B, 'Hc': Hc, 'a': a, 'b': b, 'Ht': Ht, 'ex': ex, 'ey': ey, 'bordo': bordo,
                        'angoli_bordo': angoli_bordo, 'flangia': flangia, 'smusso': smusso, 'spessore': spessore,
                        'riferimento': riferimento, 'divisione': divisione, 'foglio': foglio}})
    return doc



def cono(name: str = 'Tronco di cono', D1=400, D2=200, H=300, spessore=2, riferimento='esterno', modo='press',
         passo='', raggio=None, k=None, material='S235') -> Document:
    """Cono o tronco di cono (D2 = 0: a punta), misure finite. modo: press (a pieghe) o rolled (calandrato)."""
    doc = Document(name, material)
    for kk, v in (('D1', D1), ('D2', D2), ('H', H), ('sp', spessore)):
        doc.set_parameter(kk, v)
    vuoto = lambda v: v is None or str(v).strip() == ''  # noqa: E731
    doc.add_feature('sheet_shape', name, kind='cone', d1='D1', d2='D2', height='H', thickness='sp',
                    ref=riferimento, mode=modo, pitch=None if vuoto(passo) else passo,
                    radius=None if vuoto(raggio) else raggio, k=None if vuoto(k) else k,
                    template={'kind': 'cono', 'values': {'D1': D1, 'D2': D2, 'H': H, 'spessore': spessore,
                                                         'riferimento': riferimento, 'modo': modo, 'passo': passo}})
    return doc


def tramoggia(name: str = 'Raccordo quadro-tondo', A=600, B=400, D=250, H=300, ex=0, ey=0, spessore=2,
              rif_base='esterno', rif_tondo='esterno', passo='', raggio=None, k=None, material='S235') -> Document:
    """Raccordo rettangolo A × B → tondo Ø D a altezza H, centro del tondo spostato di (ex, ey); misure finite."""
    doc = Document(name, material)
    for kk, v in (('A', A), ('B', B), ('D', D), ('H', H), ('ex', ex), ('ey', ey), ('sp', spessore)):
        doc.set_parameter(kk, v)
    vuoto = lambda v: v is None or str(v).strip() == ''  # noqa: E731
    doc.add_feature('sheet_shape', name, kind='transition', a='A', b='B', d='D', height='H', ex='ex', ey='ey',
                    thickness='sp', ref_base=rif_base, ref_round=rif_tondo, pitch=None if vuoto(passo) else passo,
                    radius=None if vuoto(raggio) else raggio, k=None if vuoto(k) else k,
                    template={'kind': 'tramoggia', 'values': {'A': A, 'B': B, 'D': D, 'H': H, 'ex': ex, 'ey': ey,
                                                              'spessore': spessore, 'rif_base': rif_base,
                                                              'rif_tondo': rif_tondo, 'passo': passo}})
    return doc
