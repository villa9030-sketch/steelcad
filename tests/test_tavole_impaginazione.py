"""Le tavole in A4, A3 e A2: niente disegni, quote o testi dentro il cartiglio, niente fuori dalla cornice.
(Su A4 il cartiglio, che ha misura fissa, occupa più di metà larghezza: le viste devono spostarsi.)"""
import os

import pytest

from app.service import Service
from cad_engine import drawings as D


def _fuori_posto(f):
    W, H = f.size
    k = W / 594.0             # 22/10: le tavole si impaginano in A2 e si scalano tali e quali (cartiglio compreso)
    cart = (W - 190 * k + 0.5, 10 * k + 0.5, W - 10 * k - 0.5, 60 * k - 0.5)
    pagina = (20 * k - 0.5, 10 * k - 0.5, W - 10 * k + 0.5, H - 10 * k + 0.5)
    dentro = lambda p, r: r[0] < p[0] < r[2] and r[1] < p[1] < r[3]  # noqa: E731
    male = []
    for layer, pts in f.linee:
        if layer in ('cornice', 'cartiglio'):
            continue
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            for t in (0, 0.25, 0.5, 0.75, 1):
                q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                if dentro(q, cart):
                    male.append(f'linea {layer} nel cartiglio {q}')
                if not dentro(q, pagina):
                    male.append(f'linea {layer} fuori dal foglio {q}')
    for layer, (x, y), t, h, al in f.testi:
        if layer in ('cartiglio',):
            continue
        L = len(t) * h * 0.5
        x0 = {'l': x, 'c': x - L / 2, 'r': x - L, 'cv': x - h}[al]
        box = (x0, y, x0 + L, y + h) if al != 'cv' else (x - h, y - L / 2, x, y + L / 2)
        angoli = [(box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3]), ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)]
        if any(dentro(q, cart) for q in angoli):
            male.append(f'testo "{t}" nel cartiglio')
        if layer == 'testo' and len(t) > 25:      # didascalie e note: non sopra le tabelle
            for lay2, pts in f.linee:
                if lay2 != 'tabella':
                    continue
                for q in pts:
                    if box[0] + 1 < q[0] < box[2] - 1 and box[1] - 0.5 < q[1] < box[3] + 0.5:
                        male.append(f'testo "{t[:30]}" sopra una tabella')
                        break
    return male


@pytest.fixture(scope='module')
def progetti(tmp_path_factory):
    d = tmp_path_factory.mktemp('tav')
    os.environ['STEELCAD_RULES'] = str(d / 'r.json')
    s = Service()
    s.set_bend_default({'radius': 1, 'method': 'k', 'k': 0.21})
    out = {}
    s.new_project('cancello', {'L': 2969, 'H': 1390, 'telaio': '40x40x3', 'sbarre': '20x20x2', 'passo': 120})
    out['cancello'] = s.doc.to_dict()
    s.new_project('tramoggia', {})
    out['raccordo'] = s.doc.to_dict()
    s.new_project('lamiera', {})
    for e in ('L1', 'L3'):
        s.add_flange('SM1', e, {'length': 30})
    out['lamiera'] = s.doc.to_dict()
    s.save(str(d / 'u.steelcad'))
    s.new_project('scaffale', {})
    s.save(str(d / 'scaffale.steelcad'))
    s.new_assembly('Prova')
    s.asm_insert(str(d / 'scaffale.steelcad'))
    s.asm_insert(str(d / 'u.steelcad'))
    out['assieme'] = s
    return out


@pytest.mark.parametrize('formato', ['A4', 'A3', 'A2'])
@pytest.mark.parametrize('nome', ['cancello', 'raccordo', 'lamiera', 'assieme'])
def test_niente_nel_cartiglio(progetti, nome, formato):
    if nome == 'assieme':
        s = progetti['assieme']
        fogli = s._fogli({'formato': formato}, True)
    else:
        from cad_engine.document import Document
        s = Service()
        s._set(Document.from_dict(progetti[nome]))
        fogli = s._fogli({'formato': formato})
    assert fogli
    for f in fogli:
        male = _fuori_posto(f)
        assert not male, f'{f.titolo} ({formato}): {male[:5]}'
