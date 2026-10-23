"""Ritocchi a mano sulle tavole (23/10: «se una cosa è hardcoded non può essere aperta a un pubblico ampio").

La tavola nasce automatica; i ritocchi si applicano sopra, ogni volta che si rifà, così restano anche se il pezzo
cambia. Si salvano nel progetto (meta['tavole'][chiave del foglio]) come:

    {'viste':  {'vista:alto': [dx, dy]},                      spostamento in mm sul foglio
     'quote':  {'vista:alto/q1': {'d': 4, 'testo': '420 ±0,5', 'h': 3.5, 'via': False}},
     'aggiunte': [{'vista': 'vista:alto', 'a': [x, y], 'b': [x, y], 'dir': 'h'|'v'|'a', 'd': 8}],   punti nella vista
     'note':   [{'x': 30, 'y': 40, 'testo': 'Sbavare', 'h': 3.5}],
     'testi':  {'quote': 3.5, 'note': 3.5, 'titoli': 5}}       altezze in mm sul foglio stampato

Gli oggetti hanno un nome fisso dato dal disegno (drawings.Foglio.oggetto): «vista:fronte», le sue quote
«vista:fronte/q1»…, «cartiglio». Le quote aggiunte stanno nelle coordinate della vista (non del foglio): se la vista
si sposta o il pezzo cambia scala, restano attaccate ai loro punti.
"""
from __future__ import annotations

import math

from .drawings import STRATI, Foglio, _disegna_quota, fmt


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
        h = float(testi.get('quote') or 2.8)
        f.elementi[nome] = {'kind': 'quota', 'a': list(A), 'b': list(B), 'distanza': float(q.get('d', 8)), 'valore': valore,
                            'h': h, 'prefisso': '', 'testo': None, 'padre': q['vista'], 'aggiunta': i}
        with f.oggetto(nome):
            _disegna_quota(f, A, B, float(q.get('d', 8)), valore, h)
    # 3. le quote ritoccate: spostate, testo cambiato, altezza, nascoste
    for nome, m in (r.get('quote') or {}).items():
        e = f.elementi.get(nome)
        if not e or e['kind'] != 'quota':
            continue
        _togli(f, nome)
        if m.get('via'):
            e['nascosta'] = True
            continue
        e['distanza'] = e['distanza'] + float(m.get('d') or 0)
        if m.get('testo') not in (None, ''):
            e['testo'] = str(m['testo'])
        if m.get('h'):
            e['h'] = float(m['h'])
        with f.oggetto(nome):
            _disegna_quota(f, e['a'], e['b'], e['distanza'], e['valore'], e['h'], e.get('prefisso', ''), e.get('testo'))
    # 4. le altezze dei testi per tutta la tavola
    hq, ht = testi.get('quote'), testi.get('titoli')
    if hq or ht:
        q_r = r.get('quote') or {}
        nuovi = []
        for (l, p, tx, h, al), t in zip(f.testi, f.testi.tag):
            # tutte le quote prendono l'altezza della tavola, tranne quelle a cui hai dato la loro
            if hq and l == 'quote' and f.elementi.get(t, {}).get('kind') == 'quota' and not q_r.get(t, {}).get('h'):
                h = float(hq)
            elif ht and t.endswith('/titolo'):
                h = float(ht)
            nuovi.append((l, p, tx, h, al))
        f.testi[:] = nuovi
    # 5. le note
    hn = float(testi.get('note') or 3.5)
    for i, n in enumerate(r.get('note') or []):
        if not str(n.get('testo') or '').strip():
            continue
        nome = f'nota:{i + 1}'
        f.elementi[nome] = {'kind': 'nota', 'testo': n['testo'], 'x': float(n['x']), 'y': float(n['y']), 'h': float(n.get('h') or hn),
                            'indice': i}
        with f.oggetto(nome):
            for k, riga in enumerate(str(n['testo']).split('\n')):
                f.text('testo', (float(n['x']), float(n['y']) - k * float(n.get('h') or hn) * 1.4), riga, float(n.get('h') or hn))
    return f


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
            out.append({'id': nome, 'kind': 'vista', 'label': e.get('label', nome), 'bbox': bb, 'T': e['T'], 'punti': aggancio[:800]})
        elif e['kind'] == 'quota':
            bb = _ingombro(per_tag.get(nome, []))
            if bb is None:
                continue
            testo = e.get('testo') or (e.get('prefisso', '') + fmt(e['valore']))
            out.append({'id': nome, 'kind': 'quota', 'label': f'Quota {testo}', 'bbox': bb, 'a': e['a'], 'b': e['b'],
                        'distanza': e['distanza'], 'testo': testo, 'h': e['h'], 'aggiunta': e.get('aggiunta')})
        elif e['kind'] == 'nota':
            bb = _ingombro(per_tag.get(nome, []))
            if bb is not None:
                out.append({'id': nome, 'kind': 'nota', 'label': 'Nota', 'bbox': bb, 'testo': e['testo'], 'indice': e['indice'],
                            'x': e['x'], 'y': e['y'], 'h': e['h']})
    bb = _ingombro(per_tag.get('cartiglio', []) + [(x, y) for _, x, y, w, h in f.immagini] +
                   [(x + w, y + h) for _, x, y, w, h in f.immagini])
    if bb:
        out.append({'id': 'cartiglio', 'kind': 'cartiglio', 'label': 'Cartiglio', 'bbox': bb})
    return out
