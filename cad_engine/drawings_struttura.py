"""Tavole delle strutture in tubo (03/11): la distinta di taglio con i nomi da officina («Gamba», «Fianco in alto»,
mai le sigle M3 o A3~1 dei pezzi degli incroci), i numeri di posizione sull'isometrica e le luci tra i tubi nelle
viste (la misura che l'officina prende col metro tra un tubo e l'altro), accanto al fuori tutto. I numeri di posizione
si mettono con drawings.palloncini_colonne.
"""
from __future__ import annotations

import math
import re

from .drawings import Foglio, _tabella, _taglia, _cornice, fmt, proietta_punto, quota, TESTO

PLURALI = {'Gamba': 'Gambe', 'Montante': 'Montanti', 'Traverso': 'Traversi', 'Fianco': 'Fianchi',
           'Diagonale': 'Diagonali', 'Sbarra': 'Sbarre'}


def _base(nome: str) -> str:
    """«Fianco in alto (2)» → «Fianco in alto»: il numero distingue due tubi uguali, nella distinta non serve."""
    return re.sub(r'\s*\(\d+\)$', '', str(nome or '')).strip()


def nome_riga(nomi: list) -> str:
    """Il nome di una riga della distinta di taglio dai nomi dei suoi tubi: uno solo → quello; tutti dello stesso
    tipo → «Gambe» o «Fianchi: in alto; a destra, a 383 da terra»; tipi diversi → i nomi in fila."""
    distinti = list(dict.fromkeys(_base(n) for n in nomi if _base(n)))
    if not distinti:
        return 'Tubo'
    if len(distinti) == 1:
        return distinti[0]
    tipi = {n.split(' ')[0] for n in distinti}
    if len(tipi) == 1:
        tipo = next(iter(tipi))
        plurale = PLURALI.get(tipo, tipo)
        if len(distinti) >= 4 or tipo not in PLURALI:
            return plurale
        resto = [n[len(tipo):].strip(' ,') for n in distinti]
        return f'{plurale}: ' + '; '.join(r for r in resto if r)
    return '; '.join(distinti)


def _tagli(cuts: list) -> str:
    if all(c == 'dritto' for c in cuts):
        return 'dritti'
    return ' / '.join(cuts)


def righe_taglio(structures, cl: dict | None = None) -> list:
    """La distinta di taglio per l'officina: [{pos, nome, profilo, materiale, lunghezza, tagli, qty, kg, kg_tot,
    punto (il centro del primo tubo, per il numero sull'isometrica), lavorata}], nell'ordine della cut list."""
    from .structures import cut_list
    from .structures.nomi import nomi_aste
    nomi, centri = {}, {}
    for st in structures:
        n = nomi_aste(st.members)
        for m in st.members:
            nomi[f'{st.id}/{m.id}'] = n.get(m.id, '')
            c = (m.start + m.end) * 0.5
            centri[f'{st.id}/{m.id}'] = (c.X, c.Y, c.Z)
    cl = cl if cl is not None else cut_list(structures)
    out = []
    for i, r in enumerate(cl['rows'], 1):
        out.append({'pos': i, 'nome': nome_riga([nomi.get(x, '') for x in r['members']]), 'profilo': r['profile'],
                    'materiale': r['material'], 'lunghezza': r['length_mm'], 'tagli': _tagli(r['cuts']),
                    'qty': r['qty'], 'kg': r['kg_each'], 'kg_tot': r['kg_total'], 'lavorata': r.get('lavorata'),
                    'punti': [centri[x] for x in r['members'] if x in centri], 'members': list(r['members'])})
    return out


def scatole_tubi(structures) -> list:
    """Per le luci: di ogni tubo l'ingombro (xmin, ymin, zmin, xmax, ymax, zmax) e la direzione dell'asse."""
    out = []
    for st in structures:
        for m in st.members:
            try:
                b = m.solid.bounding_box()
            except Exception:  # noqa: BLE001 - un tubo senza solido non ha luci
                continue
            d = m.end - m.start
            L = d.length or 1.0
            out.append(((b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z), (d.X / L, d.Y / L, d.Z / L)))
    return out


def luci_vista(scatole: list, vista: str, max_luci: int = 8, bordi=None) -> dict:
    """{0: [(a, b), ...] in orizzontale, 1: [...] in verticale} nelle coordinate della vista. Con i bordi: la catena
    completa dal bordo al bordo, tubi e luci, che somma esattamente il fuori tutto; senza: solo le luci, gli spazi vuoti
    tra i tubi messi di traverso a quella direzione (i tubi lungo la direzione la coprono tutta e non contano, quelli
    inclinati nemmeno), e dal bordo della struttura al primo tubo (il traverso «a 368 da terra»). Troppe luci (le
    sbarre di un cancello) le dicono già le catene a passo costante. bordi: l'ingombro della vista (x0, y0, x1, y1)."""
    o = proietta_punto(vista, (0, 0, 0))
    out = {}
    for c in (0, 1):
        tratti = []
        for (x0, y0, z0, x1, y1, z1), d in scatole:
            q = proietta_punto(vista, d)
            if abs(q[c] - o[c]) > 0.02:                   # il tubo va (anche) in questa direzione: non fa luce
                continue
            vals = [proietta_punto(vista, (x, y, z))[c] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
            tratti.append((min(vals), max(vals)))
        if len(tratti) < 2:
            continue
        tratti.sort()
        uniti = [list(tratti[0])]
        for a, b in tratti[1:]:
            if a <= uniti[-1][1] + 0.5:
                uniti[-1][1] = max(uniti[-1][1], b)
            else:
                uniti.append([a, b])
        if bordi is not None:                          # dal bordo della struttura al primo tubo (e dall'ultimo)
            lo, hi = bordi[c], bordi[c + 2]
            uniti = [[lo, lo]] + uniti + [[hi, hi]]
        luci = [(p[1], q[0]) for p, q in zip(uniti, uniti[1:]) if q[0] - p[1] > 0.5]
        if not luci or len(luci) > max_luci:
            continue
        if bordi is None:
            out[c] = luci
            continue
        # 03/11: la catena intera, tubo e luce uno dopo l'altro dal bordo al bordo (30 | 343,5 | 30 | 373,5 | 30):
        # prima c'erano solo le luci e la somma non tornava col fuori tutto (mancavano i tubi)
        tappe = [lo]
        for x in sorted(min(max(x, lo), hi) for u in uniti for x in u):
            if x - tappe[-1] > 0.05:                   # le tappe vicinissime (tolleranze) sono una
                tappe.append(x)
        tappe[-1] = hi                                 # l'ultima è il bordo: la somma è il fuori tutto, esatta
        out[c] = list(zip(tappe, tappe[1:]))
    return out


def quote_luci(f: Foglio, v: dict, T, luci: dict, distanza: float):
    """Le luci tra i tubi, sotto la vista (orizzontali) e a sinistra (verticali), vicino alla vista: il fuori tutto va una fila più in là."""
    x0, y0, x1, y1 = v['bbox']
    h = 2.8 * f.u
    for c, lista in ((0, luci.get(0, [])), (1, luci.get(1, []))):
        for i, (a, b) in enumerate(lista):
            pa, pb = (T((a, y0)), T((b, y0))) if c == 0 else (T((x0, a)), T((x0, b)))
            # 03/11: il numero di un tratto corto (lo spessore del tubo) non ci sta tra le frecce: il primo va prima
            # della catena, l'ultimo dopo, quelli in mezzo di fianco dalla parte della vista (non sopra la luce dopo).
            # In verticale il primo (in basso) sta come quelli in mezzo: sotto c'è l'angolo con la catena orizzontale
            corto = math.hypot(pb[0] - pa[0], pb[1] - pa[1]) < len(fmt(b - a)) * h * 0.55 + 2 * f.u
            primo = i == 0 and c == 0
            fianco = 0 if not corto else (-1 if primo else 1)
            dentro = corto and not primo and i < len(lista) - 1
            quota(f, pa, pb, -distanza if c == 0 else distanza, b - a, dentro=dentro, di_fianco=fianco)


def tavola_taglio(campi: dict, righe: list, totali: list, formato: str = 'A3') -> Foglio:
    """La distinta di taglio di una struttura, grande come le quote delle tavole: posizione (quella sull'isometrica),
    nome da officina, profilo, lunghezza, tagli, quantità, peso; sotto i totali per profilo (le barre da comprare).
    righe: le righe di righe_taglio()."""
    f = Foglio(formato, campi.get('titolo', ''))
    f.u = k = TESTO
    area, cart = _cornice(f, {**campi, 'scala': '—'})
    col = [c * k for c in (0, 12, 100, 128, 154, 176, 190, 210, 230)]
    intest = ['Pos.', 'Nome', 'Profilo', 'Lunghezza mm', 'Tagli', 'Q.tà', 'kg cad.', 'kg tot.']
    h = 7.0 * k
    th = 2.4 * k
    x = area[0] + 10
    y = area[3] - 12 - 4 * k
    f.text('testo', (x, y + 2 * k), 'DISTINTA DI TAGLIO', 2.8 * k)
    tabella = [intest] + [[str(r['pos']), r['nome'], r['profilo'], fmt(r['lunghezza']), r['tagli'], str(r['qty']),
                           fmt(round(r['kg'], 2)), fmt(round(r['kg_tot'], 2))] for r in righe]
    for i, riga in enumerate(tabella):
        # il nome può andare su due righe (i tubi uguali di posti diversi): la riga si fa alta il doppio
        w_nome = col[2] - col[1]
        n_max = max(4, int((w_nome - 3) / (th * 0.55)))
        nome = riga[1]
        righe_nome = [nome] if len(nome) <= n_max else _a_capo(nome, n_max)[:2]
        hr = h * (1 if len(righe_nome) == 1 else 1.7)
        f.line('tabella', (x, y), (x + col[-1], y))
        for j, val in enumerate(riga):
            if j == 1 and len(righe_nome) > 1:
                for m, t in enumerate(righe_nome):
                    f.text('tabella' if i else 'testo', (x + col[j] + 1.2, y - h * 0.72 - m * th * 1.35),
                           _taglia(t, w_nome, th), th)
                continue
            f.text('tabella' if i else 'testo', (x + col[j] + 1.2, y - h * 0.72), _taglia(str(val), col[j + 1] - col[j], th), th)
        for c in col:
            f.line('tabella', (x + c, y), (x + c, y - hr))
        y -= hr
    f.line('tabella', (x, y), (x + col[-1], y))
    y2 = y - 18 * k
    _tabella(f, x, y2, [c * k for c in (0, 40, 60, 85, 110)], [['Profilo', 'Pezzi', 'Metri', 'kg']] + totali,
             'TOTALI PER PROFILO (barre da comprare)', h=h, k=k)
    y3 = y2 - h * (len(totali) + 1) - 8 * k
    f.text('testo', (x, y3), 'Il numero di posizione è quello nei cerchi della vista isometrica.', 2.2 * k)
    return f


def _a_capo(t: str, n: int) -> list:
    out, riga = [], ''
    for parola in t.split(' '):
        if riga and len(riga) + 1 + len(parola) > n:
            out.append(riga)
            riga = parola
        else:
            riga = f'{riga} {parola}'.strip()
    if riga:
        out.append(riga)
    return out
