"""03/11: la prima pagina del PDF di un assieme grande: l'elenco dei fogli (che foglio è, di che pezzo, che cosa),
così in officina si trova il foglio giusto senza sfogliare trenta pagine."""
from __future__ import annotations

from .drawings import Foglio, TESTO, _cornice, _taglia

QUANTI_PER_ELENCO = 8          # da quanti fogli in su il PDF dell'assieme comincia con l'elenco


def tavola_elenco(campi: dict, righe: list, formato: str = 'A2') -> Foglio:
    """righe: [foglio, titolo, che cosa]. Una tabella (due colonne di tabella se non ci sta: a sinistra tutta
    l'altezza, a destra sopra il cartiglio), scritte grandi come quelle delle altre tavole."""
    f = Foglio(formato, campi.get('titolo', ''))
    f.u = k = TESTO
    area, cart = _cornice(f, {**campi, 'scala': '—', 'tipo_doc': 'ELENCO DEI FOGLI'})
    intest = ['Foglio', 'Pezzo', 'Che cosa']
    x = area[0] + 10
    largo = (area[2] - area[0] - 30) / 2
    col = [0, 18 * k, largo - 42 * k, largo]
    th = 2.4 * k
    ytop = area[3] - 14 - 4 * k
    # quante righe stanno: la colonna di sinistra fino in fondo, quella di destra fino al cartiglio
    h = 6.5 * k
    while True:
        n_sx = int((ytop - area[1] - 4) / h) - 1
        n_dx = int((ytop - cart[3] - 8) / h) - 1
        if n_sx + max(0, n_dx) >= len(righe) or h <= 3.6 * k:
            break
        h *= 0.92
    f.text('testo', (x, ytop + 2 * k), 'ELENCO DEI FOGLI', 2.8 * k)
    colonne = [(x, righe[:n_sx]), (x + largo + 10, righe[n_sx:])]
    for x0, parte in colonne:
        if not parte:
            continue
        tab = [intest] + parte
        y = ytop
        for i, r in enumerate(tab):
            f.line('tabella', (x0, y), (x0 + col[-1], y))
            for j, val in enumerate(r):
                f.text('tabella' if i else 'testo', (x0 + col[j] + 1.2, y - h * 0.72),
                       _taglia(str(val), col[j + 1] - col[j], min(th, h * 0.55)), min(th, h * 0.55))
            y -= h
        f.line('tabella', (x0, y), (x0 + col[-1], y))
        for c in col:
            f.line('tabella', (x0 + c, ytop), (x0 + c, y))
    return f


def righe_elenco(fogli: list) -> list:
    """Dai fogli (nell'ordine del PDF) le righe dell'elenco: numero, pezzo, che cosa (dal titolo «Nome — sviluppo ·
    2 pz»)."""
    out = []
    for i, g in enumerate(fogli, 1):
        t = str(g.titolo or '')
        # nel cartiglio il titolo può avere in fondo quanti pezzi («Staffa — sviluppo · 2 pz»)
        t = next((x[2] for x in g.testi if x[2].startswith(t + ' · ')), t) if t else t
        nome, _, resto = t.partition(' — ')
        cosa, _, quanti = (resto or '').partition(' · ')
        if not resto:
            nome, _, quanti = t.partition(' · ')
        cosa = cosa or ('assieme' if i == 1 else 'disegno del pezzo')
        out.append([str(i), nome, cosa + (f' · {quanti}' if quanti else '')])
    return out
