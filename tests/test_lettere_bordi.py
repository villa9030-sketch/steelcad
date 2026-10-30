"""I contorni delle lettere tagliate non diventano bordi arancio (30/10: «10/15» stencil = 540 linee, tutto bloccato)."""
import math

from app import sketch_border
from cad_engine.sketch import testo
from cad_engine.sketch.model import Sketch


def test_lettere_si_riconoscono_fori_no():
    lettere = [c for c in testo.contorni('10/15', 5, 0, 0, 90, 'allerta') if len(c) >= 16]
    assert lettere and all(sketch_border.e_lettera(c) for c in lettere)
    poligono = [(20 * math.cos(i / 16 * 2 * math.pi), 20 * math.sin(i / 16 * 2 * math.pi)) for i in range(16)]
    assert not sketch_border.e_lettera(poligono)
    assert not sketch_border.e_lettera([(0, 0), (40, 0), (40, 20), (0, 20)])


def _bordo(sk, pts):
    ids = []
    for x, y in pts:
        p = sk.point(x, y, construction=True)
        sk.entities[p]['ref'] = True
        sk.constrain('fix', p)
        ids.append(p)
    for i in range(len(ids)):
        sk.entities[sk.line(ids[i], ids[(i + 1) % len(ids)], construction=True)]['ref'] = True
    return ids


def test_vecchi_bordi_delle_lettere_via():
    sk = Sketch('S1', 'XY')
    _bordo(sk, [(0, 0), (300, 0), (300, 120), (0, 120)])                       # il bordo del pezzo resta
    for c in testo.contorni('10/15', 5, 50, 50, 0, 'allerta'):
        _bordo(sk, c)
    attaccata = _bordo(sk, [(q[0] + 100, q[1]) for q in max(testo.contorni('0', 5, 0, 0, 0, 'allerta'), key=len)])
    sk.line(attaccata[0], sk.point(200, 100))                                 # una linea disegnata attaccata: resta
    tolte = sketch_border.togli_lettere(sk)
    assert tolte > 100
    resta = [e for e in sk.entities.values() if e['kind'] == 'line' and e.get('ref')]
    assert 4 + len(attaccata) <= len(resta) < 4 + len(attaccata) + 40      # restano bordo, lettera attaccata, pezzetti
    assert all(sk.entities[c['refs'][0]] for c in sk.constraints.values() if c['type'] == 'fix')
