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
     'testi':  {'quote': 3.5, 'note': 3.5, 'titoli': 5, 'frecce': 3}}   altezze (e frecce) in mm sul foglio stampato

Una quota può avere anche 'freccia' (mm). Senza ritocchi testi e frecce sono quelli della tavola: impaginata in A2 e
rimpicciolita sul foglio (f.fattore), così una quota aggiunta è uguale alle altre su ogni formato.

Gli oggetti hanno un nome fisso dato dal disegno (drawings.Foglio.oggetto): «vista:fronte», le sue quote
«vista:fronte/q1»…, «cartiglio». Le quote aggiunte stanno nelle coordinate della vista (non del foglio): se la vista
si sposta o il pezzo cambia scala, restano attaccate ai loro punti.
"""
from __future__ import annotations

import math

from .drawings import STRATI, Foglio, _disegna_quota, _freccia, fmt


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
    # 1. le viste spostate, con tutto quello che sta dentro (quote, note dei fori, titolo)
    for vista, (dx, dy) in (r.get('viste') or {}).items():
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
        da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi        # l'angolo più piccolo, col suo verso
        if abs(da) < 1e-6:
            continue
        R = float(q.get('r', 15 * k))
        n = max(8, int(abs(da) / math.radians(5)))
        arco = [(V[0] + R * math.cos(a1 + da * j / n), V[1] + R * math.sin(a1 + da * j / n)) for j in range(n + 1)]
        gradi = math.degrees(abs(da))
        testo = q.get('testo') or (fmt(round(gradi, 1)) + '°')
        nome = f'{q["vista"]}/ang{i + 1}'
        f.elementi[nome] = {'kind': 'angolo', 'indice': i, 'V': list(V), 'testo': testo}
        sg = 1 if da > 0 else -1
        with f.oggetto(nome):
            # le linee di richiamo, se l'arco va oltre i lati disegnati
            for ang, P0 in ((a1, A), (a2, B)):
                if math.dist(V, P0) < R:
                    f.line('quote', P0, (V[0] + (R + 1.5 * k) * math.cos(ang), V[1] + (R + 1.5 * k) * math.sin(ang)))
            f.line('quote', *arco)
            _freccia(f, arco[0], (math.sin(a1) * sg, -math.cos(a1) * sg), L=frq)      # le punte verso fuori dall'arco
            _freccia(f, arco[-1], (-math.sin(a2) * sg, math.cos(a2) * sg), L=frq)
            am = a1 + da / 2
            f.text('quote', (V[0] + (R + 1.2 * k) * math.cos(am), V[1] + (R + 1.2 * k) * math.sin(am)), testo, hq,
                   'l' if math.cos(am) > 0.3 else 'r' if math.cos(am) < -0.3 else 'c')
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
