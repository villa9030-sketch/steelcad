"""Ritocchi a mano sulle tavole (23/10: «se una cosa è hardcoded non può essere aperta a un pubblico ampio").

La tavola nasce automatica; i ritocchi si applicano sopra, ogni volta che si rifà, così restano anche se il pezzo
cambia. Si salvano nel progetto (meta['tavole'][chiave del foglio]) come:

    {'viste':  {'vista:alto': [dx, dy]},                      spostamento in mm sul foglio
     'quote':  {'vista:alto/q1': {'d': 4, 'testo': '420 ±0,5', 'h': 3.5, 'via': False}},
     'aggiunte': [{'vista': 'vista:alto', 'a': [x, y], 'b': [x, y], 'dir': 'h'|'v'|'a', 'd': 8}],   punti nella vista
     'note':   [{'x': 30, 'y': 40, 'testo': 'Sbavare', 'h': 3.5}],
     'diametri': [{'vista': 'vista:alto', 'c': [x, y], 'r': 10, 'tipo': 'Ø'|'R', 'ang': 45, 'd': 10}],  centro e raggio
                                                                nella vista, angolo e lunghezza della linea sul foglio
     'angoli': [{'vista': 'vista:fronte', 'a': [x, y], 'v': [x, y], 'b': [x, y], 'r': 15}],   tre punti nella vista
     'saldature': [{'vista': 'vista:fronte', 'p': [x, y], 'dx': 15, 'dy': 12, 'tipo': 'angolo'|'V'|'I', 'a': '4',
                    'l': '', 'giro': False, 'opera': False}],   la punta nella vista, il gomito spostato sul foglio
     'testi':  {'quote': 3.5, 'note': 3.5, 'titoli': 5, 'frecce': 3},   altezze (e frecce) in mm sul foglio stampato
     'libere': ['vista:alto'],                                   viste non allineate alla fronte (28/10)
     'tolte':  ['vista:iso'],                                    viste tolte dal foglio
     'dettagli': [{'vista': 'vista:fronte', 'c': [x, y], 'r': 12, 'k': 2, 'p': [x, y], 'lettera': 'A'}]}
                                                                centro e raggio nella vista, ingrandimento, centro sul foglio

Una quota può avere anche 'freccia' (mm). Senza ritocchi testi e frecce sono quelli della tavola: impaginata in A2 e
rimpicciolita sul foglio (f.fattore), così una quota aggiunta è uguale alle altre su ogni formato.

Gli oggetti hanno un nome fisso dato dal disegno (drawings.Foglio.oggetto): «vista:fronte», le sue quote
«vista:fronte/q1»…, «cartiglio». Le quote aggiunte stanno nelle coordinate della vista (non del foglio): se la vista
si sposta o il pezzo cambia scala, restano attaccate ai loro punti.
"""
from __future__ import annotations

import math

from .drawings import STRATI, Foglio, _disegna_quota, _freccia, disegna_angolo, fmt, scala_testo


def _dentro(tag: str, nome: str) -> bool:
    return tag == nome or tag.startswith(nome + '/')


def _trasla(f: Foglio, ok, dx: float, dy: float):
    S = lambda p: (p[0] + dx, p[1] + dy)  # noqa: E731
    f.linee[:] = [(l, [S(p) for p in pts]) if ok(t) else (l, pts) for (l, pts), t in zip(f.linee, f.linee.tag)]
    f.cerchi[:] = [(l, S(c), r) if ok(t) else (l, c, r) for (l, c, r), t in zip(f.cerchi, f.cerchi.tag)]
    f.pieni[:] = [(l, [S(p) for p in pts]) if ok(t) else (l, pts) for (l, pts), t in zip(f.pieni, f.pieni.tag)]
    f.ombre[:] = [(c, [S(p) for p in pts]) if ok(t) else (c, pts) for (c, pts), t in zip(f.ombre, f.ombre.tag)]
    f.testi[:] = [(l, S(p), tx, h, al) if ok(t) else (l, p, tx, h, al) for (l, p, tx, h, al), t in zip(f.testi, f.testi.tag)]


def _togli(f: Foglio, nome: str):
    for s in STRATI:
        getattr(f, s).tieni(lambda t: t != nome)


def ritocca(f: Foglio, r: dict | None) -> Foglio:
    """Applica i ritocchi al foglio (già nel suo formato). I nomi che non ci sono più (la quota di un foro tolto) si
    saltano: la tavola esce comunque."""
    r = r or {}
    testi = r.get('testi') or {}
    f.persi = persi(f, r)
    # 0. viste tolte e dettagli ingranditi (28/10): prima degli spostamenti, così il cerchio del dettaglio segue la
    # sua vista e il dettaglio si sposta per conto suo
    for vista in r.get('tolte') or []:
        if vista in f.elementi and f.elementi[vista]['kind'] == 'vista':
            for st in STRATI:
                getattr(f, st).tieni(lambda t, v=vista: not _dentro(t, v))
            for nome in [n for n in f.elementi if _dentro(n, vista)]:
                del f.elementi[nome]
    for i, d in enumerate(r.get('dettagli') or []):
        _dettaglio(f, d, i)
    # 1. le viste spostate, con tutto quello che sta dentro (quote, note dei fori, titolo)
    for vista, (dx, dy) in viste_allineate(r, f.elementi).items():
        if vista not in f.elementi:
            continue
        _trasla(f, lambda t, v=vista: _dentro(t, v), dx, dy)
        for nome, e in f.elementi.items():
            if e['kind'] == 'vista' and _dentro(nome, vista):
                e['T'] = [e['T'][0], e['T'][1] + dx, e['T'][2] + dy]
            elif e['kind'] == 'quota' and _dentro(nome, vista):
                e['a'] = [e['a'][0] + dx, e['a'][1] + dy]
                e['b'] = [e['b'][0] + dx, e['b'][1] + dy]
    # 2. le quote aggiunte a mano, nei punti della loro vista
    for i, q in enumerate(r.get('aggiunte') or []):
        v = f.elementi.get(q.get('vista'))
        if not v or v['kind'] != 'vista':
            continue
        s, tx, ty = v['T']
        T = lambda p: (p[0] * s + tx, p[1] * s + ty)  # noqa: E731
        a, b = q['a'], q['b']
        A, B = T(a), T(b)
        modo = q.get('dir', 'a')
        if modo == 'h':
            B, valore = (B[0], A[1]), abs(b[0] - a[0])
        elif modo == 'v':
            B, valore = (A[0], B[1]), abs(b[1] - a[1])
        else:
            valore = math.hypot(b[0] - a[0], b[1] - a[1])
        if math.hypot(B[0] - A[0], B[1] - A[1]) < 1e-6:
            continue
        nome = f'{q["vista"]}/mano{i + 1}'
        h = 2.8 * f.fattore                         # come le quote della tavola, rimpicciolite col foglio
        f.elementi[nome] = {'kind': 'quota', 'a': list(A), 'b': list(B), 'distanza': float(q.get('d', 8)), 'valore': valore,
                            'h': h, 'prefisso': '', 'testo': None, 'padre': q['vista'], 'aggiunta': i}
        with f.oggetto(nome):
            _disegna_quota(f, A, B, float(q.get('d', 8)), valore, h)
    # 3. le quote ritoccate (spostate, testo, altezza, frecce, nascoste) e quelle che seguono testi e frecce della tavola
    hq, fr = testi.get('quote'), testi.get('frecce')
    q_r = r.get('quote') or {}
    for nome, e in list(f.elementi.items()):
        if e['kind'] != 'quota':
            continue
        m = q_r.get(nome) or {}
        if not (m or hq or fr):
            continue
        _togli(f, nome)
        if m.get('via'):
            e['nascosta'] = True
            continue
        e['distanza'] = e['distanza'] + float(m.get('d') or 0)
        if m.get('testo') not in (None, ''):
            e['testo'] = str(m['testo'])
        if m.get('h') or hq:                        # la sua altezza, se no quella della tavola
            e['h'] = float(m.get('h') or hq)
        if m.get('freccia') or fr:
            e['freccia'] = float(m.get('freccia') or fr)
        with f.oggetto(nome):
            _disegna_quota(f, e['a'], e['b'], e['distanza'], e['valore'], e['h'], e.get('prefisso', ''), e.get('testo'),
                           e.get('freccia'))
    # 4. i titoli delle viste
    ht = testi.get('titoli')
    if ht:
        f.testi[:] = [(l, p, tx, float(ht) if t.endswith('/titolo') else h, al) for (l, p, tx, h, al), t in zip(f.testi, f.testi.tag)]
    # 5. le note
    hn = float(testi.get('note') or 3.5 * f.fattore)
    for i, n in enumerate(r.get('note') or []):
        if not str(n.get('testo') or '').strip():
            continue
        nome = f'nota:{i + 1}'
        f.elementi[nome] = {'kind': 'nota', 'testo': n['testo'], 'x': float(n['x']), 'y': float(n['y']), 'h': float(n.get('h') or hn),
                            'indice': i}
        with f.oggetto(nome):
            for k, riga in enumerate(str(n['testo']).split('\n')):
                f.text('testo', (float(n['x']), float(n['y']) - k * float(n.get('h') or hn) * 1.4), riga, float(n.get('h') or hn))
    # 6. diametri e raggi, angoli, saldature (24/10)
    k = f.fattore
    hq = float(testi.get('quote') or 2.8 * k)
    frq = float(testi.get('frecce') or 2.5 * hq / 2.8)
    for i, q in enumerate(r.get('diametri') or []):
        T = _trasformazione(f, q.get('vista'))
        if T is None:
            continue
        s_, tx, ty = T
        C = (q['c'][0] * s_ + tx, q['c'][1] * s_ + ty)
        R = float(q['r']) * s_
        a = math.radians(float(q.get('ang', 45)))
        ca, sa = math.cos(a), math.sin(a)
        E = (C[0] + R * ca, C[1] + R * sa)
        L = (C[0] + (R + float(q.get('d', 10 * k))) * ca, C[1] + (R + float(q.get('d', 10 * k))) * sa)
        verso = 1 if ca >= 0 else -1
        testo = q.get('testo') or (('R' if q.get('tipo') == 'R' else 'Ø') + fmt(float(q['r']) * (1 if q.get('tipo') == 'R' else 2)))
        w = len(testo) * hq * 0.6 + 2 * k
        nome = f'{q["vista"]}/dia{i + 1}'
        f.elementi[nome] = {'kind': 'diametro', 'indice': i, 'C': list(C), 'R': R, 'testo': testo}
        with f.oggetto(nome):
            if q.get('tipo') == 'R':
                f.line('quote', C, L, (L[0] + verso * w, L[1]))   # dal centro, freccia sull'arco
            else:
                f.line('quote', E, L, (L[0] + verso * w, L[1]))
            _freccia(f, E, (ca, sa) if q.get('tipo') == 'R' else (-ca, -sa), L=frq)
            f.text('quote', (L[0] + verso * 1 * k, L[1] + 0.8 * k), testo, hq, 'l' if verso > 0 else 'r')
    for i, q in enumerate(r.get('angoli') or []):
        T = _trasformazione(f, q.get('vista'))
        if T is None:
            continue
        s_, tx, ty = T
        P = lambda u: (u[0] * s_ + tx, u[1] * s_ + ty)  # noqa: E731
        A, V, B = P(q['a']), P(q['v']), P(q['b'])
        a1 = math.atan2(A[1] - V[1], A[0] - V[0])
        a2 = math.atan2(B[1] - V[1], B[0] - V[0])
        da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
        if abs(da) < 1e-6:
            continue
        testo = q.get('testo') or (fmt(round(math.degrees(abs(da)), 1)) + '°')
        nome = f'{q["vista"]}/ang{i + 1}'
        f.elementi[nome] = {'kind': 'angolo', 'indice': i, 'V': list(V), 'testo': testo}
        with f.oggetto(nome):
            disegna_angolo(f, A, V, B, float(q.get('r', 15 * k)), testo, k, hq, frq)
    for i, q in enumerate(r.get('saldature') or []):
        T = _trasformazione(f, q.get('vista'))
        if T is None:
            continue
        s_, tx, ty = T
        P0 = (q['p'][0] * s_ + tx, q['p'][1] * s_ + ty)
        K = (P0[0] + float(q.get('dx', 15 * k)), P0[1] + float(q.get('dy', 12 * k)))
        verso = 1 if float(q.get('dx', 15)) >= 0 else -1
        lung = 20 * k
        Fn = (K[0] + verso * lung, K[1])
        nome = f'{q["vista"]}/sal{i + 1}'
        f.elementi[nome] = {'kind': 'saldatura', 'indice': i, 'P': list(P0), 'K': list(K)}
        with f.oggetto(nome):
            _saldatura(f, P0, K, Fn, verso, q, k, hq, frq)
    return f


def _taglia_nel_cerchio(pts, C, R) -> list:
    """I tratti della polilinea che stanno dentro il cerchio (C, R): una lista di polilinee."""
    out, cur = [], []

    def dentro(p):
        return (p[0] - C[0]) ** 2 + (p[1] - C[1]) ** 2 <= R * R

    def tagli(a, b):                          # i parametri 0..1 dove il tratto a-b passa il cerchio
        dx, dy = b[0] - a[0], b[1] - a[1]
        fx, fy = a[0] - C[0], a[1] - C[1]
        A = dx * dx + dy * dy
        if A < 1e-18:
            return []
        B = 2 * (fx * dx + fy * dy)
        D = B * B - 4 * A * (fx * fx + fy * fy - R * R)
        if D <= 0:
            return []
        q = math.sqrt(D)
        return sorted(t for t in ((-B - q) / (2 * A), (-B + q) / (2 * A)) if 0 < t < 1)
    for a, b in zip(pts[:-1], pts[1:]):
        ta = [0.0] + tagli(a, b) + [1.0]
        for t0, t1 in zip(ta[:-1], ta[1:]):
            m = (a[0] + (b[0] - a[0]) * (t0 + t1) / 2, a[1] + (b[1] - a[1]) * (t0 + t1) / 2)
            p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
            p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
            if dentro(m):
                if not cur:
                    cur = [p0]
                cur.append(p1)
            elif cur:
                out.append(cur)
                cur = []
    if cur:
        out.append(cur)
    return [x for x in out if len(x) > 1]


def _dettaglio(f: Foglio, d: dict, i: int):
    """La vista di dettaglio: quello che sta nel cerchio di una vista, ingrandito k volte con centro in d['p'] sul
    foglio, col cerchio, la lettera e la scala. Sul foglio è una vista come le altre («dettaglio:A»): si sposta, ci si
    mettono quote."""
    v = f.elementi.get(d.get('vista'))
    if not v or v['kind'] != 'vista':
        return
    s_, tx, ty = v['T']
    C = (d['c'][0] * s_ + tx, d['c'][1] * s_ + ty)
    R = float(d['r']) * s_
    k = max(1.0, float(d.get('k') or 2))
    P = (float(d['p'][0]), float(d['p'][1]))
    lettera = str(d.get('lettera') or chr(65 + i))[:3]
    kf = f.fattore
    M = lambda q: (P[0] + (q[0] - C[0]) * k, P[1] + (q[1] - C[1]) * k)  # noqa: E731
    linee = [(lay, pts) for (lay, pts), t in zip(f.linee, f.linee.tag) if t == d['vista'] and lay in ('contorno', 'nascoste', 'tangenti')]
    for (lay, c, rr), t in zip(f.cerchi, f.cerchi.tag):
        if t == d['vista']:
            n = 72
            linee.append((lay, [(c[0] + rr * math.cos(2 * math.pi * j / n), c[1] + rr * math.sin(2 * math.pi * j / n)) for j in range(n + 1)]))

    def giro(c, r, n=96):
        return [(c[0] + r * math.cos(2 * math.pi * j / n), c[1] + r * math.sin(2 * math.pi * j / n)) for j in range(n + 1)]
    with f.oggetto(f'{d["vista"]}/det{lettera}'):          # il cerchio sulla vista, con la lettera
        f.line('quote', *giro(C, R))
        f.text('testo', (C[0] + R * 0.75, C[1] + R * 0.75), lettera, 3.5 * kf)
    nome = f'dettaglio:{lettera}'
    f.elementi[nome] = {'kind': 'vista', 'T': [s_ * k, P[0] + (tx - C[0]) * k, P[1] + (ty - C[1]) * k],
                        'label': f'Dettaglio {lettera}', 'dettaglio': i}
    with f.oggetto(nome):
        for lay, pts in linee:
            for tratto in _taglia_nel_cerchio(pts, C, R):
                f.line(lay, *[M(q) for q in tratto])
        f.line('tangenti', *giro(P, R * k))
    scala = scala_testo(f.scala * k) if f.scala else f'× {fmt(k)}'
    with f.oggetto(f'{nome}/titolo'):
        f.text('testo', (P[0] - R * k, P[1] + R * k + 3 * kf), f'DETTAGLIO {lettera} ({scala})', 2.5 * kf)


def persi(f: Foglio, r: dict) -> list:
    """I ritocchi che non trovano più il loro oggetto (28/10): il pezzo è cambiato e la quota ritoccata non c'è più
    (un foro tolto), la vista è sparita… La tavola esce lo stesso; questi si dicono, per toglierli o rifarli.
    [{'tipo', 'chiave' (dove sta nei ritocchi), 'testo'}]"""
    el = f.elementi
    nomi_v = {'vista:fronte': 'vista di fronte', 'vista:alto': 'vista dall’alto', 'vista:sinistra': 'vista da sinistra',
              'vista:destra': 'vista da destra', 'vista:iso': 'isometrica'}
    dettagli = {f'dettaglio:{d.get("lettera")}' for d in r.get('dettagli') or []}
    c_e = lambda v: v in el or v in dettagli  # noqa: E731
    out = []
    for q, m in (r.get('quote') or {}).items():
        if q not in el:
            out.append({'tipo': 'quote', 'chiave': q, 'testo': f'quota ritoccata{" «" + str(m.get("testo")) + "»" if m.get("testo") else ""} '
                        f'della {nomi_v.get(q.split("/")[0], q.split("/")[0])}: non c’è più'})
    for v in (r.get('viste') or {}):
        if not c_e(v):
            out.append({'tipo': 'viste', 'chiave': v, 'testo': f'{nomi_v.get(v, v)} spostata: la vista non c’è più'})
    for tipo, cosa in (('aggiunte', 'quota aggiunta'), ('diametri', 'diametro'), ('angoli', 'angolo'),
                       ('saldature', 'saldatura'), ('dettagli', 'dettaglio')):
        for i, q in enumerate(r.get(tipo) or []):
            if not c_e(q.get('vista')):
                out.append({'tipo': tipo, 'chiave': i, 'testo': f'{cosa} sulla {nomi_v.get(q.get("vista"), q.get("vista"))}: la vista non c’è più'})
    # le quote aggiunte che non stanno più sugli spigoli (il pezzo ha cambiato misura)
    for i, q in enumerate(r.get('aggiunte') or []):
        v = el.get(q.get('vista'))
        if not v or v['kind'] != 'vista':
            continue
        s_, tx, ty = v['T']
        estremi = [p for (lay, pts), t in zip(f.linee, f.linee.tag) if t == q['vista'] and lay in ('contorno', 'tangenti', 'nascoste')
                   for p in (pts[0], pts[-1])]
        estremi += [c for (lay, c, rr), t in zip(f.cerchi, f.cerchi.tag) if t == q['vista']]     # i centri dei fori
        if not estremi:
            continue
        for punto in (q['a'], q['b']):
            P = (punto[0] * s_ + tx, punto[1] * s_ + ty)
            if min(math.dist(P, e) for e in estremi) > 0.05 * max(s_, 1):
                out.append({'tipo': 'aggiunte', 'chiave': i, 'testo': f'quota aggiunta sulla {nomi_v.get(q["vista"], q["vista"])}: '
                            'non è più attaccata agli spigoli (il pezzo è cambiato)'})
                break
    return out


def viste_allineate(r: dict, elementi) -> dict:
    """Gli spostamenti veri delle viste (28/10, viste allineate come in ogni CAD): la vista dall'alto resta sotto
    quella di fronte (si sposta solo in su e in giù), quella da sinistra accanto (solo di lato), e tutte e due seguono
    la vista di fronte. Quelle in r['libere'] si spostano libere."""
    viste = {k: list(v) for k, v in (r.get('viste') or {}).items()}
    libere = set(r.get('libere') or [])
    if 'vista:fronte' not in elementi:
        return viste
    fx, fy = viste.get('vista:fronte', [0.0, 0.0])
    if 'vista:alto' in elementi and 'vista:alto' not in libere:
        viste['vista:alto'] = [fx, fy + viste.get('vista:alto', [0.0, 0.0])[1]]
    for fianco in ('vista:sinistra', 'vista:destra'):
        if fianco in elementi and fianco not in libere:
            viste[fianco] = [fx + viste.get(fianco, [0.0, 0.0])[0], fy]
    return {k: v for k, v in viste.items() if v[0] or v[1]}


def _trasformazione(f: Foglio, vista):
    v = f.elementi.get(vista)
    return v['T'] if v and v['kind'] == 'vista' else None


def _saldatura(f: Foglio, P0, K, Fn, verso, q, k, h, frq):
    """Il simbolo di saldatura (ISO 2553, sistema A): freccia sul giunto, linea di riferimento continua e quella
    tratteggiata sotto; il simbolo sopra la continua (lato freccia) o sotto la tratteggiata (lato opposto); a sinistra la misura
    (a = gola), a destra la lunghezza; cerchietto al gomito = tutto intorno, bandierina = in opera."""
    ux, uy = K[0] - P0[0], K[1] - P0[1]
    L = math.hypot(ux, uy) or 1
    f.line('quote', P0, K)
    _freccia(f, P0, (-ux / L, -uy / L), L=frq)
    f.line('quote', K, Fn)
    # la tratteggiata, 1 mm sotto (a trattini)
    y = K[1] - 1.2 * k
    x0, x1 = sorted((K[0], Fn[0]))
    x = x0
    while x < x1:
        f.line('quote', (x, y), (min(x + 2 * k, x1), y))
        x += 3 * k
    # lato freccia: il simbolo sopra la linea continua (dalla parte opposta alla tratteggiata); lato opposto: sotto,
    # appoggiato alla tratteggiata
    sopra = q.get('lato') != 'altro'
    c = (K[0] + Fn[0]) / 2                                     # il simbolo a metà della linea
    base = K[1] if sopra else K[1] - 1.2 * k
    dz = 1 if sopra else -1
    hs = 3 * k
    t = q.get('tipo', 'angolo')
    if t == 'angolo':                                           # triangolo rettangolo, il lato verticale a sinistra
        f.line('quote', (c - hs / 2, base), (c - hs / 2, base + dz * hs), (c + hs / 2, base), (c - hs / 2, base))
    elif t == 'V':
        f.line('quote', (c - hs / 2, base + dz * hs), (c, base), (c + hs / 2, base + dz * hs))
    elif t == 'I':
        f.line('quote', (c - hs / 4, base), (c - hs / 4, base + dz * hs))
        f.line('quote', (c + hs / 4, base), (c + hs / 4, base + dz * hs))
    ty = base + (0.4 * k if sopra else -h - 0.4 * k)
    if q.get('a'):
        f.text('quote', (c - hs / 2 - 1 * k, ty), ('a' if t == 'angolo' else 's') + str(q['a']), h, 'r')
    if q.get('l'):
        f.text('quote', (c + hs / 2 + 1 * k, ty), str(q['l']), h, 'l')
    if q.get('giro'):                                           # tutto intorno
        f.cerchi.append(('quote', (K[0], K[1]), 1.5 * k))
    if q.get('opera'):                                          # in opera: la bandierina
        f.line('quote', K, (K[0], K[1] + 5 * k))
        f.pieni.append(('quote', [(K[0], K[1] + 5 * k), (K[0] + verso * 3.5 * k, K[1] + 4 * k), (K[0], K[1] + 3 * k)]))


def _cerchi_vista(f: Foglio, nome: str) -> list:
    """I cerchi e gli archi di una vista (sul foglio sono polilinee): [{'c': [x, y], 'r', 'chiuso'}], per la quota di
    diametro o raggio con un clic."""
    out = []
    for (l, pts), t in zip(f.linee, f.linee.tag):
        if t != nome or l not in ('contorno', 'tangenti', 'nascoste') or len(pts) < 8:
            continue
        a, b, c = pts[0], pts[len(pts) // 3], pts[2 * len(pts) // 3]
        d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
        if abs(d) < 1e-9:
            continue
        ux = ((a[0] ** 2 + a[1] ** 2) * (b[1] - c[1]) + (b[0] ** 2 + b[1] ** 2) * (c[1] - a[1]) + (c[0] ** 2 + c[1] ** 2) * (a[1] - b[1])) / d
        uy = ((a[0] ** 2 + a[1] ** 2) * (c[0] - b[0]) + (b[0] ** 2 + b[1] ** 2) * (a[0] - c[0]) + (c[0] ** 2 + c[1] ** 2) * (b[0] - a[0])) / d
        r = math.dist((ux, uy), a)
        if r < 0.2 or any(abs(math.dist((ux, uy), p) - r) > max(0.02 * r, 0.05) for p in pts):
            continue
        out.append({'c': [ux, uy], 'r': r, 'chiuso': math.dist(pts[0], pts[-1]) < 1e-3})
    return out


def _ingombro(punti):
    xs, ys = [p[0] for p in punti], [p[1] for p in punti]
    return [min(xs), min(ys), max(xs), max(ys)] if xs else None


def oggetti(f: Foglio) -> list:
    """Per l'editor: gli oggetti cliccabili del foglio, col loro riquadro (mm sul foglio, y in su) e i dati per
    ritoccarli; per le viste anche i punti dove si aggancia una quota nuova."""
    per_tag: dict = {}

    def metti(t, pts):
        if t:
            per_tag.setdefault(t, []).extend(pts)
    for (l, pts), t in zip(f.linee, f.linee.tag):
        metti(t, pts)
    for (l, c, r), t in zip(f.cerchi, f.cerchi.tag):
        metti(t, [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)])
    for (l, pts), t in zip(f.pieni, f.pieni.tag):
        metti(t, pts)
    for (l, p, tx, h, al), t in zip(f.testi, f.testi.tag):
        w = len(tx) * h * 0.55
        if al == 'cv':
            metti(t, [(p[0] - h, p[1] - w / 2), (p[0], p[1] + w / 2)])
        else:
            x0 = p[0] - {'l': 0, 'c': w / 2, 'r': w}.get(al, 0)
            metti(t, [(x0, p[1]), (x0 + w, p[1] + h)])
    out = []
    for nome, e in f.elementi.items():
        if e.get('nascosta'):
            continue
        if e['kind'] == 'vista':
            pts = [p for t, ps in per_tag.items() if _dentro(t, nome) and '/q' not in t[len(nome):] and '/mano' not in t[len(nome):]
                   for p in ps]
            bb = _ingombro(pts)
            if bb is None:
                continue
            # i punti per agganciare una quota: gli estremi delle linee della vista (non dei titoli e delle quote)
            aggancio, visti = [], set()
            for (l, ps), t in zip(f.linee, f.linee.tag):
                if t != nome or l not in ('contorno', 'tangenti', 'nascoste'):
                    continue
                for p in (ps[0], ps[-1]):
                    k = (round(p[0], 2), round(p[1], 2))
                    if k not in visti:          # il punto vero, non arrotondato: la quota nuova deve dire 420, non 420,01
                        visti.add(k)
                        aggancio.append([float(p[0]), float(p[1])])
            out.append({'id': nome, 'kind': 'vista', 'label': e.get('label', nome), 'bbox': bb, 'T': e['T'], 'punti': aggancio[:800],
                        'cerchi': _cerchi_vista(f, nome)[:300]})
        elif e['kind'] == 'quota':
            bb = _ingombro(per_tag.get(nome, []))
            if bb is None:
                continue
            testo = e.get('testo') or (e.get('prefisso', '') + fmt(e['valore']))
            out.append({'id': nome, 'kind': 'quota', 'label': f'Quota {testo}', 'bbox': bb, 'a': e['a'], 'b': e['b'],
                        'distanza': e['distanza'], 'testo': testo, 'h': e['h'], 'aggiunta': e.get('aggiunta'),
                        'freccia': e.get('freccia') or 2.5 * e['h'] / 2.8})
        elif e['kind'] == 'nota':
            bb = _ingombro(per_tag.get(nome, []))
            if bb is not None:
                out.append({'id': nome, 'kind': 'nota', 'label': 'Nota', 'bbox': bb, 'testo': e['testo'], 'indice': e['indice'],
                            'x': e['x'], 'y': e['y'], 'h': e['h']})
        elif e['kind'] in ('diametro', 'angolo', 'saldatura'):
            bb = _ingombro(per_tag.get(nome, []))
            if bb is not None:
                etich = {'diametro': f'Quota {e.get("testo", "")}', 'angolo': f'Angolo {e.get("testo", "")}',
                         'saldatura': 'Saldatura'}[e['kind']]
                out.append({'id': nome, 'kind': e['kind'], 'label': etich, 'bbox': bb, 'indice': e['indice'],
                            **({'P': e['P'], 'K': e['K']} if e['kind'] == 'saldatura' else {}),
                            **({'C': e['C'], 'R': e['R']} if e['kind'] == 'diametro' else {})})
    bb = _ingombro(per_tag.get('cartiglio', []) + [(x, y) for _, x, y, w, h in f.immagini] +
                   [(x + w, y + h) for _, x, y, w, h in f.immagini])
    if bb:
        out.append({'id': 'cartiglio', 'kind': 'cartiglio', 'label': 'Cartiglio', 'bbox': bb})
    return out
