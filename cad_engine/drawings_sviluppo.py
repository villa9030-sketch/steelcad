"""La tavola dello sviluppo per l'officina (22/10: «le tavole di sviluppo vanno sistemate»).

- Lo sviluppo il più grande possibile: si prova la tabella pieghe sopra il cartiglio o accanto, e si tiene la
  sistemazione con la scala più grande.
- Ogni linea di piega ha il suo numero nel cerchio (P1, P2…), lo stesso della tabella: niente più scritte lunghe
  sulle linee che si accavallano quando le pieghe sono vicine.
- Le quote progressive delle linee di piega dal bordo (quello che serve al piegatore per il riscontro), sul
  disegno e nella colonna «Quota» della tabella. Le scritte vicine si allargano con una linea di richiamo.
"""
from __future__ import annotations

import math

from .drawings import Foglio, TESTO, _cornice, _scegli_scala, _tabella, fmt, quota, scala_testo, SCALE, SCALE_FITTE

R_CERCHIO = 2.6          # mm sul foglio
PASSO_TESTO = 3.6        # distanza minima tra due scritte impilate


def _allarga(pos: list, minimo: float, lo: float, hi: float) -> list:
    """Posizioni ordinate (coordinate sul foglio) spostate il meno possibile perché distino almeno «minimo»,
    dentro [lo, hi] se ci stanno."""
    if not pos:
        return []
    out = list(pos)
    for i in range(1, len(out)):
        out[i] = max(out[i], out[i - 1] + minimo)
    if out[-1] > hi:                                  # sfora in cima: si spinge tutto giù
        out[-1] = hi
        for i in range(len(out) - 2, -1, -1):
            out[i] = min(out[i], out[i + 1] - minimo)
    if out[0] < lo:                                   # e se così sfora sotto, si torna su (meglio sovrapposti fuori)
        out[0] = lo
        for i in range(1, len(out)):
            out[i] = max(out[i], out[i - 1] + minimo)
    return out


def _fid(testo: str) -> str:
    return str(testo).split(' ')[0] if testo else ''


def tavola_sviluppo(data, campi: dict, piegature: list, formato: str = 'A3') -> Foglio:
    """piegature: righe [P, flangia, lunghezza esterna, angolo, verso, R int., K, larghezza] nell'ordine lungo il pezzo."""
    from . import drawings as D
    if piegature and getattr(data, 'shape_info', None):
        return D._sviluppo_forme(data, campi, piegature, formato)          # coni e tramogge: la tavola delle forme
    f = Foglio(formato, campi.get('titolo', ''))
    f.u = u = TESTO
    RC, PT = R_CERCHIO * u, PASSO_TESTO * u
    poly = []
    for pl in data.outline():
        pts = [(pl[i], pl[i + 1]) for i in range(0, len(pl) - 1, 2)]
        if pts and pts[0] != pts[-1]:
            pts.append(pts[0])
        poly.append(pts)
    xs = [p[0] for pl in poly for p in pl]
    ys = [p[1] for pl in poly for p in pl]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)

    # le linee di piega con il loro numero (quello della tabella) e la quota dal bordo
    per_fid = {r[1]: r[0] for r in piegature}
    linee = []                                        # (P, a, b, 'h'|'v'|'o', quota)
    for k, (a, b, testo) in enumerate(data.bend_lines, 1):
        num = per_fid.get(_fid(testo), str(k))
        if abs(a[1] - b[1]) < 1e-6:
            linee.append((num, a, b, 'h', a[1] - y0))
        elif abs(a[0] - b[0]) < 1e-6:
            linee.append((num, a, b, 'v', a[0] - x0))
        else:
            linee.append((num, a, b, 'o', None))
    quote_di = {}
    for num, a, b, kind, q in linee:
        if q is not None:
            quote_di.setdefault(num, f'{"↑" if kind == "h" else "→"} {fmt(q)}')
    intest, righe, titolo_tab = tabella_pieghe(piegature, quote_di)
    n = len(righe)
    h_riga = (5.0 if n <= 14 else max(3.6, min(5.0, 110 / (n + 1)))) * u
    col = colonne(intest, righe, min(2.4 * u, h_riga * 0.55), u)

    area, cart = _cornice(f, {**campi, 'scala': ''})
    larg_tab, alto_tab = col[-1], (h_riga * (n + 1) + 6 * u if n else 0)
    # margini attorno allo sviluppo: a sinistra quota totale e cerchi, a destra le quote delle pieghe, sotto la
    # quota totale (e i cerchi delle pieghe in verticale), sopra la didascalia e le quote delle pieghe in verticale
    ci_h = any(k == 'h' for _, _, _, k, _ in linee)
    ci_v = any(k == 'v' for _, _, _, k, _ in linee)
    from .drawings import fori_e_asole, quote_fori_sviluppo, tappe_fori, catena_ci_sta, largo_progressive, MAX_TAPPE
    fori = fori_e_asole(poly)                         # 03/11: fori e asole quotati anche nello sviluppo
    fx, fy = tappe_fori(fori, (x0, y0, x1, y1)) if fori else ([], [])
    m_dx = (6 + (18 if ci_h else 0)) * u
    m_sopra = (16 + (12 if ci_v else 0)) * u          # + la riga della legenda

    def margini(sc):
        """Sotto e a sinistra: la quota totale, le quote dei fori (catena, o progressive se i fori sono fitti
        e la catena alla scala sc non ci sta: allora più posto per i numeri) e i cerchi delle pieghe."""
        cs = cl = 0.0
        if fori and max(len(fx), len(fy)) <= MAX_TAPPE:     # con troppi fori niente quote (solo le note)
            cs = 9 * u if len(fx) <= 16 and catena_ci_sta(fx, sc, u) else largo_progressive(fx, u) + 1.5 * u
            cl = 9 * u if len(fy) <= 16 and catena_ci_sta(fy, sc, u) else largo_progressive(fy, u) + 1.5 * u
        return (14 * u + cl + (10 * u if ci_h else 0), 14 * u + cs + (10 * u if ci_v else 0), cs, cl)
    sistemazioni = []
    if n:
        # A) tabella sopra il cartiglio
        tx, tt = area[2] - larg_tab, cart[3] + 8 + alto_tab
        sistemazioni.append(((tx, tt), [(area[0], area[1], min(cart[0], tx) - 6, area[3]), (area[0], tt + 4, area[2], area[3])]))
        # B) tabella a sinistra del cartiglio, in basso
        tx = cart[0] - 6 - larg_tab
        if tx > area[0] + 20:
            tt = area[1] + alto_tab
            sistemazioni.append(((tx, tt), [(area[0], max(cart[3], tt) + 4, area[2], area[3]), (area[0], area[1], tx - 6, area[3])]))
    else:
        sistemazioni.append((None, [(area[0], area[1], cart[0] - 6, area[3]), (area[0], cart[3] + 4, area[2], area[3])]))

    def scala_zona(z):
        sc = None
        for _ in range(3):                            # i margini dipendono dalla scala (quote dei fori): si riprova
            m_sx, m_sotto = margini(sc if sc else SCALE[0])[:2]
            aw, ah = (z[2] - z[0]) - m_sx - m_dx, (z[3] - z[1]) - m_sotto - m_sopra
            if aw <= 0 or ah <= 0:
                return 0.0
            nuova = _scegli_scala((x1 - x0, y1 - y0), aw, ah, SCALE_FITTE)
            if nuova == sc:
                break
            sc = nuova
        return sc if (x1 - x0) * sc <= aw and (y1 - y0) * sc <= ah else 0.0
    migliore = max(((scala_zona(z), (z[2] - z[0]) * (z[3] - z[1]), tab, z) for tab, zone in sistemazioni for z in zone),
                   key=lambda x: (x[0], x[1]))
    s, _, tab, zona = migliore
    s = s or SCALE[-1]
    m_sx, m_sotto, cs, cl = margini(s)
    f.testi, f.linee, f.cerchi, f.pieni = [], [], [], []
    campi = {**campi, 'scala': scala_testo(s), '_s': s}
    area, cart = _cornice(f, campi)
    # lo sviluppo centrato nella sua zona
    aw = (zona[2] - zona[0]) - m_sx - m_dx
    ah = (zona[3] - zona[1]) - m_sotto - m_sopra
    ox = zona[0] + m_sx + max(0.0, (aw - (x1 - x0) * s) / 2)
    oy = zona[1] + m_sotto + max(0.0, (ah - (y1 - y0) * s) / 2)
    T = lambda p: (ox + (p[0] - x0) * s, oy + (p[1] - y0) * s)  # noqa: E731
    for pl in poly:
        f.line('contorno', *[T(p) for p in pl])
    for num, a, b, kind, q in linee:
        f.line('piega', T(a), T(b))
    for m in getattr(data, 'marks', None) or []:      # marcature laser: i tratti delle lettere
        import build123d as bd
        pts = [tuple(data.plane.to_local_coords(bd.Vector(*q)))[:2] for q in m['flat']]
        if len(pts) > 1:
            f.line('marca', *[T(q) for q in pts])
    X0, Y0 = T((x0, y0))
    X1, Y1 = T((x1, y1))
    quota(f, (X0, Y0), (X1, Y0), -8 * u - cs - (10 * u if ci_v else 0), x1 - x0)
    quota(f, (X0, Y0), (X0, Y1), 8 * u + cl + (10 * u if ci_h else 0), y1 - y0)

    # pieghe orizzontali: cerchi a sinistra, quote progressive a destra (dal bordo in basso)
    oriz = sorted(((num, a, b, q) for num, a, b, k, q in linee if k == 'h'), key=lambda x: x[3])
    if oriz:
        yl = [T((0, a[1]))[1] for _, a, _, _ in oriz]
        yc = _allarga(yl, 2 * RC + 0.6 * u, area[1] + RC, area[3] - RC)
        xc = X0 - 4 * u - RC
        for (num, a, b, q), y, c in zip(oriz, yl, yc):
            xa = T((min(a[0], b[0]), 0))[0]
            f.line('quote', (xa, y), (X0 - 1.5 * u, y), (xc + RC, c))
            f.cerchi.append(('piega', (xc, c), RC))
            f.text('piega', (xc, c - 1.0 * u), num, 2.2 * u, 'c')
        # quote progressive: lo zero sul bordo in basso, poi ogni linea
        yt = _allarga([Y0] + yl, PT, area[1] + 2, area[3] - 2)
        xq = X1 + 3 * u
        for k, (y, t) in enumerate(zip([Y0] + yl, yt)):
            testo = '0' if k == 0 else fmt(oriz[k - 1][3])
            xb = T((max(oriz[k - 1][1][0], oriz[k - 1][2][0]), 0))[0] if k else X1
            f.line('quote', (xb + 0.8 * u, y), (xq, y), (xq + 3 * u, t), (xq + 4.5 * u, t))
            f.text('quote', (xq + 5 * u, t - 1.0 * u), testo, 2.5 * u)
    # pieghe verticali: cerchi sotto, quote progressive sopra (dal bordo a sinistra)
    vert = sorted(((num, a, b, q) for num, a, b, k, q in linee if k == 'v'), key=lambda x: x[3])
    if vert:
        xl = [T((a[0], 0))[0] for _, a, _, _ in vert]
        xc_ = _allarga(xl, 2 * RC + 0.6 * u, area[0] + RC, area[2] - RC)
        yc = Y0 - 4 * u - RC
        for (num, a, b, q), x, c in zip(vert, xl, xc_):
            ya = T((0, min(a[1], b[1])))[1]
            f.line('quote', (x, ya), (x, Y0 - 1.5 * u), (c, yc + RC))
            f.cerchi.append(('piega', (c, yc), RC))
            f.text('piega', (c, yc - 1.0 * u), num, 2.2 * u, 'c')
        larghezze = [(len(fmt(q)) * 2.2 * 0.6 + 1.5) * u for _, _, _, q in vert]
        xt = _allarga([X0] + xl, max([PT] + larghezze), area[0] + 2, area[2] - 8)
        yq = Y1 + 3 * u
        for k, (x, t) in enumerate(zip([X0] + xl, xt)):
            testo = '0' if k == 0 else fmt(vert[k - 1][3])
            yb = T((0, max(vert[k - 1][1][1], vert[k - 1][2][1])))[1] if k else Y1
            f.line('quote', (x, yb + 0.8 * u), (x, yq), (t, yq + 3 * u), (t, yq + 4.5 * u))
            f.text('quote', (t, yq + 5 * u), testo, 2.5 * u, 'c')
    # i fori dopo le pieghe: le loro note si mettono dove non coprono le quote delle pieghe
    quote_fori_sviluppo(f, T, (x0, y0, x1, y1), fori, (-8 - (10 if ci_v else 0)) * u, (8 + (10 if ci_h else 0)) * u, u)
    # pieghe oblique: solo il numero, in fondo alla linea
    for num, a, b, k, q in linee:
        if k != 'o':
            continue
        A, B = T(a), T(b)
        L = math.dist(A, B) or 1
        c = (A[0] - (B[0] - A[0]) / L * (RC + 2 * u), A[1] - (B[1] - A[1]) / L * (RC + 2 * u))
        f.cerchi.append(('piega', c, RC))
        f.text('piega', (c[0], c[1] - 1.0 * u), num, 2.2 * u, 'c')

    didascalia = ('SVILUPPO visto dal lato dello sketch · linee di piega in rosso col numero della tabella · quote '
                  'progressive dal bordo ' + ' e '.join(x for x, ok in (('in basso (↑)', bool(oriz)), ('a sinistra (→)', bool(vert))) if ok))
    if not oriz and not vert:
        didascalia = 'SVILUPPO visto dal lato dello sketch'
    cw = 1.4 * u
    righe_did = [didascalia]
    if len(didascalia) * cw >= zona[2] - zona[0] and ' · quote' in didascalia:     # 03/11: a capo, non tagliata
        a, b = didascalia.split(' · quote', 1)
        righe_did = [a, 'quote' + b]
    for i, riga in enumerate(righe_did):
        f.text('testo', (zona[0] + 2, zona[3] - (4 + 3.6 * i) * u),
               riga if len(riga) * cw < zona[2] - zona[0] else riga[:int((zona[2] - zona[0]) / cw)], 2.5 * u)
    from .drawings import legenda, voci_legenda
    legenda(f, zona[0] + 2, zona[3] - (9.5 + 3.6 * (len(righe_did) - 1)) * u, voci_legenda(data), u)
    if n and tab is not None:
        _tabella(f, tab[0], tab[1], col, [intest] + righe, 'TABELLA PIEGHE', h=h_riga, k=u)
        if titolo_tab != 'TABELLA PIEGHE':            # raggio e K uguali per tutte: accanto al titolo
            f.text('testo', (tab[0] + len('TABELLA PIEGHE') * 2.8 * u * 0.6 + 3 * u, tab[1] + 2 * u),
                   titolo_tab.replace('TABELLA PIEGHE · ', ''), 2.8 * u)
    return f


def tabella_pieghe(piegature: list, quote_di: dict) -> tuple:
    """03/11: la tabella pieghe stretta (rubava metà foglio allo sviluppo): raggio e K, se sono gli stessi per tutte
    le pieghe (quasi sempre), vanno nel titolo invece che in due colonne ripetute."""
    intest = ['P', 'Flangia', 'Quota', 'Angolo', 'Verso', 'R int.', 'K', 'Lungh. est.', 'Largh.']
    righe = [[r[0], r[1], quote_di.get(r[0], '—'), r[3], r[4], r[5], r[6], r[2], r[7]] for r in piegature]
    titolo = 'TABELLA PIEGHE'
    uguali = [j for j in (5, 6) if righe and len({r[j] for r in righe}) == 1]
    if uguali:
        titolo += ''.join(f' · {intest[j]} {righe[0][j]}' for j in uguali if righe[0][j] not in ('', None))
        intest = [c for j, c in enumerate(intest) if j not in uguali]
        righe = [[c for j, c in enumerate(r) if j not in uguali] for r in righe]
    return intest, righe, titolo


def colonne(intest: list, righe: list, th: float, u: float) -> list:
    """Le colonne larghe quanto la scritta più lunga (non più larghe a occhio)."""
    col = [0.0]
    for j in range(len(intest)):
        n = max(len(str(r[j])) for r in [intest] + righe)
        col.append(col[-1] + max(6 * u, n * th * 0.6 + 2.6))
    return col
