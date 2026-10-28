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

from .drawings import Foglio, _cornice, _scegli_scala, _tabella, fmt, quota, scala_testo, SCALE

R_CERCHIO = 2.6          # mm sul foglio
PASSO_TESTO = 3.4        # distanza minima tra due scritte impilate


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
    col = [0, 9, 25, 43, 57, 69, 80, 91, 110, 130]
    intest = ['P', 'Flangia', 'Quota', 'Angolo', 'Verso', 'R int.', 'K', 'Lungh. est.', 'Largh.']
    righe = [[r[0], r[1], quote_di.get(r[0], '—'), r[3], r[4], r[5], r[6], r[2], r[7]] for r in piegature]

    area, cart = _cornice(f, {**campi, 'scala': ''})
    n = len(righe)
    h_riga = 6.0 if n <= 14 else max(3.6, min(6.0, 120 / (n + 1)))
    larg_tab, alto_tab = col[-1], (h_riga * (n + 1) + 6 if n else 0)
    # margini attorno allo sviluppo: a sinistra quota totale e cerchi, a destra le quote delle pieghe, sotto la
    # quota totale (e i cerchi delle pieghe in verticale), sopra la didascalia e le quote delle pieghe in verticale
    ci_h = any(k == 'h' for _, _, _, k, _ in linee)
    ci_v = any(k == 'v' for _, _, _, k, _ in linee)
    m_sx, m_dx = 14 + (10 if ci_h else 0), 6 + (20 if ci_h else 0)
    m_sotto, m_sopra = 14 + (10 if ci_v else 0), 10 + (12 if ci_v else 0)
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
        aw, ah = (z[2] - z[0]) - m_sx - m_dx, (z[3] - z[1]) - m_sotto - m_sopra
        if aw <= 0 or ah <= 0:
            return 0.0
        sc = _scegli_scala((x1 - x0, y1 - y0), aw, ah)
        return sc if (x1 - x0) * sc <= aw and (y1 - y0) * sc <= ah else 0.0
    migliore = max(((scala_zona(z), (z[2] - z[0]) * (z[3] - z[1]), tab, z) for tab, zone in sistemazioni for z in zone),
                   key=lambda x: (x[0], x[1]))
    s, _, tab, zona = migliore
    s = s or SCALE[-1]
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
            f.line('testo', *[T(q) for q in pts])
    X0, Y0 = T((x0, y0))
    X1, Y1 = T((x1, y1))
    quota(f, (X0, Y0), (X1, Y0), -8 - (10 if ci_v else 0), x1 - x0)
    quota(f, (X0, Y0), (X0, Y1), 8 + (10 if ci_h else 0), y1 - y0)

    # pieghe orizzontali: cerchi a sinistra, quote progressive a destra (dal bordo in basso)
    oriz = sorted(((num, a, b, q) for num, a, b, k, q in linee if k == 'h'), key=lambda x: x[3])
    if oriz:
        yl = [T((0, a[1]))[1] for _, a, _, _ in oriz]
        yc = _allarga(yl, 2 * R_CERCHIO + 0.6, area[1] + R_CERCHIO, area[3] - R_CERCHIO)
        xc = X0 - 4 - R_CERCHIO
        for (num, a, b, q), y, c in zip(oriz, yl, yc):
            xa = T((min(a[0], b[0]), 0))[0]
            f.line('quote', (xa, y), (X0 - 1.5, y), (xc + R_CERCHIO, c))
            f.cerchi.append(('piega', (xc, c), R_CERCHIO))
            f.text('piega', (xc, c - 1.0), num, 2.2, 'c')
        # quote progressive: lo zero sul bordo in basso, poi ogni linea
        yt = _allarga([Y0] + yl, PASSO_TESTO, area[1] + 2, area[3] - 2)
        xq = X1 + 3
        for k, (y, t) in enumerate(zip([Y0] + yl, yt)):
            testo = '0' if k == 0 else fmt(oriz[k - 1][3])
            xb = T((max(oriz[k - 1][1][0], oriz[k - 1][2][0]), 0))[0] if k else X1
            f.line('quote', (xb + 0.8, y), (xq, y), (xq + 3, t), (xq + 4.5, t))
            f.text('quote', (xq + 5, t - 1.0), testo, 2.2)
    # pieghe verticali: cerchi sotto, quote progressive sopra (dal bordo a sinistra)
    vert = sorted(((num, a, b, q) for num, a, b, k, q in linee if k == 'v'), key=lambda x: x[3])
    if vert:
        xl = [T((a[0], 0))[0] for _, a, _, _ in vert]
        xc_ = _allarga(xl, 2 * R_CERCHIO + 0.6, area[0] + R_CERCHIO, area[2] - R_CERCHIO)
        yc = Y0 - 4 - R_CERCHIO
        for (num, a, b, q), x, c in zip(vert, xl, xc_):
            ya = T((0, min(a[1], b[1])))[1]
            f.line('quote', (x, ya), (x, Y0 - 1.5), (c, yc + R_CERCHIO))
            f.cerchi.append(('piega', (c, yc), R_CERCHIO))
            f.text('piega', (c, yc - 1.0), num, 2.2, 'c')
        larghezze = [len(fmt(q)) * 2.2 * 0.6 + 1.5 for _, _, _, q in vert]
        xt = _allarga([X0] + xl, max([PASSO_TESTO] + larghezze), area[0] + 2, area[2] - 8)
        yq = Y1 + 3
        for k, (x, t) in enumerate(zip([X0] + xl, xt)):
            testo = '0' if k == 0 else fmt(vert[k - 1][3])
            yb = T((0, max(vert[k - 1][1][1], vert[k - 1][2][1])))[1] if k else Y1
            f.line('quote', (x, yb + 0.8), (x, yq), (t, yq + 3), (t, yq + 4.5))
            f.text('quote', (t, yq + 5), testo, 2.2, 'c')
    # pieghe oblique: solo il numero, in fondo alla linea
    for num, a, b, k, q in linee:
        if k != 'o':
            continue
        A, B = T(a), T(b)
        L = math.dist(A, B) or 1
        c = (A[0] - (B[0] - A[0]) / L * (R_CERCHIO + 2), A[1] - (B[1] - A[1]) / L * (R_CERCHIO + 2))
        f.cerchi.append(('piega', c, R_CERCHIO))
        f.text('piega', (c[0], c[1] - 1.0), num, 2.2, 'c')

    didascalia = ('SVILUPPO visto dal lato dello sketch · linee di piega in rosso col numero della tabella · quote '
                  'progressive dal bordo ' + ' e '.join(x for x, ok in (('in basso (↑)', bool(oriz)), ('a sinistra (→)', bool(vert))) if ok))
    if not oriz and not vert:
        didascalia = 'SVILUPPO visto dal lato dello sketch'
    f.text('testo', (zona[0] + 2, zona[3] - 4), didascalia if len(didascalia) * 1.4 < zona[2] - zona[0] else didascalia[:int((zona[2] - zona[0]) / 1.4)], 2.5)
    if n and tab is not None:
        _tabella(f, tab[0], tab[1], col, [intest] + righe, 'TABELLA PIEGHE', h=h_riga)
    return f
