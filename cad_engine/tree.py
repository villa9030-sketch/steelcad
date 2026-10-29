"""L'albero del progetto scritto come lo direbbe l'officina, non come lo vede il kernel.

    TAVOLO OFFICINA
    ├── Piano 2000×1000×10
    ├── Telaio superiore
    │   ├── 2 × 40×40×3 — 2040
    │   └── 2 × 40×40×3 — 1040
    └── Gambe
        └── 4 × 40×40×3 — 880
"""
from __future__ import annotations

from collections import OrderedDict

from .analysis import properties
from .errors import SteelCADError
from .expressions import evaluate
from .sketch import Sketch
from .units import fmt_mm


def _n(label, kind, ref=None, children=None, status=None, **extra):
    return {'label': label, 'kind': kind, 'ref': ref, 'children': children or [], 'status': status, **extra}


def _punti(doc, sk) -> dict:
    """I punti dello sketch dove stanno davvero (risolti), o quelli scritti se lo sketch non è risolto."""
    try:
        return {k: tuple(v) for k, v in doc.solved_sketch(sk.id).points.items()}
    except Exception:  # noqa: BLE001 - per un nome: mai fermare l'albero
        return {k: (e['x'], e['y']) for k, e in sk.entities.items() if e['kind'] == 'point'}


def _misura(pts) -> str:
    """«156 × 15»: l'ingombro di un gruppo di punti."""
    if not pts:
        return ''
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    a, b = sorted((max(xs) - min(xs), max(ys) - min(ys)), reverse=True)
    return f'{fmt_mm(round(a, 1))} × {fmt_mm(round(b, 1))}' if b > 1e-6 else ''


def _cosa_disegnato(doc, sk) -> str:
    """Il nome di uno sketch senza lavorazione da quello che c'è dentro: «Linea 154», «2 linee, cerchio Ø10»."""
    import math
    pts = _punti(doc, sk)
    linee = [e for e in sk.entities.values() if e['kind'] == 'line' and not e.get('ref') and not e.get('construction')]
    cerchi = [e for e in sk.entities.values() if e['kind'] == 'circle' and not e.get('ref') and not e.get('construction')]
    archi = [e for e in sk.entities.values() if e['kind'] == 'arc' and not e.get('ref') and not e.get('construction')]
    testi = [e for e in sk.entities.values() if e['kind'] == 'text']
    parti = []
    if len(linee) == 1 and linee[0]['a'] in pts and linee[0]['b'] in pts:
        (ax, ay), (bx, by) = pts[linee[0]['a']], pts[linee[0]['b']]
        parti.append(f'Linea {fmt_mm(round(math.hypot(bx - ax, by - ay), 1))}')
    elif linee:
        parti.append(f'{len(linee)} linee')
    if len(cerchi) == 1:
        parti.append(f'cerchio Ø{fmt_mm(round(2 * cerchi[0]["r"], 2))}')
    elif cerchi:
        parti.append(f'{len(cerchi)} cerchi')
    if archi:
        parti.append('1 arco' if len(archi) == 1 else f'{len(archi)} archi')
    if testi:
        parti.append(f'testo «{testi[0].get("text", "")}»')
    t = ', '.join(parti) or 'vuoto'
    return t[0].upper() + t[1:]


def _vuoto(sk) -> bool:
    return not any(e['kind'] in ('line', 'circle', 'arc', 'text') and not e.get('ref') for e in sk.entities.values())


def _feature_label(doc, f, fr) -> str:
    t = f['type']
    nome = f.get('name') or ''
    try:
        if t == 'extrude':
            op = {'new': '', 'add': 'aggiunta ', 'cut': 'tasca '}[f.get('operation', 'new')]
            d = f.get('distance')
            if f.get('through_all'):
                dist = 'passante'
            elif isinstance(d, (int, float)):
                dist = f'{fmt_mm(float(d))} mm'
            else:
                try:
                    dist = f'{d} = {fmt_mm(evaluate(d, doc.resolved_parameters(), "distanza"))} mm'
                except SteelCADError:
                    dist = str(d)
            return f'{nome or "Estrusione"}: {op}{dist}'.replace(': ', ': ', 1)
        if t == 'hole':
            d = f.get('diameter')
            n = len(f.get('points') or [])
            prof = 'passante' if f.get('through', True) else f'prof. {f.get("depth")}'
            return f'{nome or "Foro"}: {n} × Ø{fmt_mm(d) if isinstance(d, (int, float)) else d} {prof}'
        if t == 'step_lamiera':
            return f'{nome or "Lamiera da STEP"}: {f.get("file") or ""} (K {f.get("k")})'
        if t == 'solido_step':
            return f'{nome or "Pezzo importato"}: {f.get("file") or ""}'
        if t == 'revolve':
            op = {'new': '', 'add': ' (aggiunta)', 'cut': ' (tolta)'}.get(f.get('operation', 'new'), '')
            a = f.get('angle')
            giro = 'giro intero' if a in (None, '', 360, 360.0) else f'{a}°'
            return f'{nome or "Rivoluzione"}: {giro}{op}'
        if t == 'fillet':
            return f'{nome or "Raccordo"} R{f.get("radius")}'
        if t == 'sheet_miter':
            teste = {'fine': 'alla fine', 'inizio': 'all’inizio'}.get(f.get('end'), 'alle due teste')
            gioco = f.get('gap')
            return (f'{nome or "Taglio di testa"} a {f.get("angle", 45)}° {teste}'
                    + (f', gioco {gioco}' if gioco not in (None, '', 0, 0.0) else ''))
        if t == 'sheet_tab_fold':
            altre = ''.join(f', poi {x.get("angle", 90)}° {"giù" if x.get("direction") == "down" else "su"}'
                            for x in f.get('altre') or [])
            return f'{nome or "Linguetta piegata"} {f.get("angle", 90)}° {"giù" if f.get("direction") == "down" else "su"}{altre}'
        if t == 'sheet_edge_flange':
            a = f.get('angle', 90)
            ang = '' if a in (None, '', 90, 90.0) else f' a {a}°'
            return f'Piega {f.get("length")} mm{ang} {"verso fuori" if f.get("side") == "out" else "verso dentro"}'
        if t == 'chamfer':
            return f'{nome or "Smusso"} {f.get("distance")} mm'
        if t == 'sheet':
            sp = f.get('thickness')
            try:
                sp = fmt_mm(evaluate(sp, doc.resolved_parameters(), 'spessore'))
            except SteelCADError:
                pass
            return f'Lamiera sp. {sp}'
        if t == 'sheet_form':
            try:
                sk = doc.sketch(f['sketch'])
                n = sum(1 for e in sk.entities.values() if e['kind'] == ('line' if f.get('kind') == 'louver' else 'circle')
                        and not e.get('construction') and not e.get('ref'))
            except SteelCADError:
                n = 0
            if f.get('kind') == 'louver':
                return f'{nome or "Persiane"}: {n} × {f.get("width")} alta {f.get("height")}'
            return f'{nome or "Imbutiture"}: {n} × profonde {f.get("depth")}'
        if t == 'sheet_cut':
            if f.get('mode') == 'add':
                return f'{nome or "Linguetta"}: materiale aggiunto nel piano della faccia'
            if f.get('mode') == 'mark':
                try:
                    testi = [e['text'] for e in doc.sketch(f['sketch']).entities.values() if e['kind'] == 'text']
                except Exception:  # noqa: BLE001
                    testi = []
                return f'{nome if nome not in ("", "Marcatura") else "Scritta"} ' + (', '.join(f'«{t}»' for t in testi[:3]) or 'laser') + (' …' if len(testi) > 3 else '')
            try:
                sk_t = doc.sketch(f['sketch'])
                return _cosa_taglia(sk_t, nome, _punti(doc, sk_t))
            except (SteelCADError, KeyError):
                return f'{nome or "Taglio"} attraverso la lamiera'

    except (KeyError, ValueError):
        pass
    return nome or f['id']


def _cosa_taglia(sk, nome, coord=None) -> str:
    """Il nome di un taglio da quello che c'è nel disegno (28/10: tutti si chiamavano «Taglio attraverso la
    lamiera»): «Fori 3 × Ø10», «Fori 2 × M6, 2 × svasati Ø8», «Taglio sagomato», «Fori 4 × Ø8 e 2 tagli sagomati»."""
    fori = {}
    for e in sk.entities.values():
        if e['kind'] != 'circle' or e.get('construction') or e.get('ref'):
            continue
        h = e.get('hole') or {}
        if h.get('tipo') == 'filettato':
            k = h['M']
        elif h.get('tipo') == 'svasato':
            k = f'svasati Ø{fmt_mm(h["D"])}' if h.get('D') else f'svasati Ø{fmt_mm(round(2 * e["r"], 2))}'
        elif h.get('tipo') == 'inserto':
            k = f'inserti {h.get("codice") or ""}'.strip()
        else:
            k = f'Ø{fmt_mm(round(2 * e["r"], 2))}'
        fori[k] = fori.get(k, 0) + 1
    # i contorni fatti di linee e archi: gruppi di elementi attaccati per i punti
    segni = [e for e in sk.entities.values() if e['kind'] in ('line', 'arc') and not e.get('construction') and not e.get('ref')]
    padre: dict = {}

    def radice(x):
        while padre.get(x, x) != x:
            x = padre[x]
        return x
    for e in segni:
        pts = [e[k] for k in ('a', 'b', 'start', 'end') if k in e]
        for q in pts[1:]:
            padre[radice(q)] = radice(pts[0])
    gruppi: dict = {}
    punti_g: dict = {}
    for e in segni:
        r = radice(next(e[k] for k in ('a', 'start') if k in e))
        g = gruppi.setdefault(r, [0, 0])
        g[0 if e['kind'] == 'line' else 1] += 1
        if coord:
            punti_g.setdefault(r, []).extend(coord[q] for q in (e.get(k) for k in ('a', 'b', 'start', 'end')) if q in coord)
    tipi = {'asola': 0, 'rettangolo': 0, 'sagoma': 0}
    for linee, archi in gruppi.values():
        tipi['asola' if (linee, archi) == (2, 2) else 'rettangolo' if (linee, archi) == (4, 0) else 'sagoma'] += 1
    parti = [f'{n} × {k}' if n > 1 else k.replace('svasati', 'svasato') for k, n in sorted(fori.items(), key=lambda x: -x[1])]
    pezzi = []
    if parti:
        pezzi.append(('Foro ' if sum(fori.values()) == 1 else 'Fori ') + ', '.join(parti))
    for k, uno, tanti in (('asola', 'asola', 'asole'), ('rettangolo', 'finestra', 'finestre'),
                          ('sagoma', 'taglio sagomato', 'tagli sagomati')):
        n = tipi[k]
        if n:
            pezzi.append(uno if n == 1 else f'{n} {tanti}')
    if len(pezzi) == 1 and not parti and len(punti_g) == 1:            # una cosa sola: con la sua misura (29/10)
        m = _misura(next(iter(punti_g.values())))
        if m:
            pezzi[0] += f' {m}'
    testo = ' e '.join([', '.join(pezzi[:-1]), pezzi[-1]] if len(pezzi) > 1 else pezzi) if pezzi else ''
    testo = testo[0].upper() + testo[1:] if testo else 'Taglio attraverso la lamiera'
    if nome and nome.startswith('Raccordo'):                          # «Raccordo spigolo R5»: dice già tutto
        return nome
    if nome and nome not in ('Taglio', 'Fori', 'Asole', 'Finestre', 'Togli materiale'):
        testo = f'{nome}: {testo[0].lower() + testo[1:]}'          # un nome dato da te resta davanti
    if isinstance(sk.plane, dict) and sk.plane.get('flat'):
        testo += ' (sullo sviluppo)'
    return testo


def project_tree(doc, result) -> dict:
    root = _n(doc.meta.get('name', 'Progetto'), 'project')
    stati = {fr.id: fr for fr in result.features}
    # il pezzo
    solid_feats = [f for f in doc.features if not isinstance(f, Sketch) and f['type'] not in ('structure', 'tube_cut')]
    if solid_feats:
        label = doc.meta.get('name', 'Pezzo')
        if result.body is not None:
            s = sorted(properties(result.body.shape, doc.material)['bbox_mm']['size'], reverse=True)
            label = f'{label} {"×".join(fmt_mm(round(v, 1)) for v in s)} {doc.material}'
        part = _n(label, 'part')
        # 29/10, «l'albero pulito»: lo sketch di una lavorazione sta dentro di lei (la freccina lo apre); quelli
        # sulle facce senza lavorazione vanno in fondo, in «Disegni non usati»; i vuoti si vedono solo mentre ci lavori
        disegni: dict = {}
        non_usati = []
        for f in doc.features:
            fid = Document_id(f)
            fr = stati.get(fid)
            if isinstance(f, Sketch):
                chi = [x for x in solid_feats if x.get('sketch') == fid]
                if not chi and not (isinstance(f.plane, dict) and not f.plane.get('tube')):
                    continue
                st = (fr.sketch_status or {}).get('state') if fr else None
                stato = None if fr and fr.ok else 'errore'
                if st and st != 'completo':
                    stato = 'errore' if not fr.ok else st
                if chi and chi[0]['type'] == 'sheet':
                    m = _misura(list(_punti(doc, f).values()))
                    part['children'].append(_n(f'{f.name or "Base"}{" " + m if m and (f.name or "Base") == "Base" else ""}',
                                               'sketch', fid, status=stato))
                elif chi:
                    disegni[fid] = _n('il suo disegno', 'sketch', fid, status=stato)
                else:
                    nome_sk = f.name if f.name and not f.name.startswith('Sketch') else _cosa_disegnato(doc, f)
                    non_usati.append(_n(nome_sk, 'sketch', fid, status=stato, vuoto=_vuoto(f)))
                continue
            if f in solid_feats:
                part['children'].append(_n(f.get('etichetta') or _feature_label(doc, f, fr), f['type'], fid,
                                           status='disattivata' if f.get('disattiva') else (None if fr and fr.ok else 'errore')))
                if f.get('sketch') in disegni:
                    part['children'][-1]['children'].append(disegni.pop(f['sketch']))
                    part['children'][-1]['chiuso'] = True
                if f['type'] == 'sheet':
                    sk = doc.sketch(f['sketch']) if f.get('sketch') else None
                    # in parole di officina: "Piega davanti, 40 mm in su", "Orlo sulla piega davanti, 10 mm"
                    # angoli e lunghezze possono essere formule ("180-64", "H/2"): si scrivono col valore vero.
                    # Prima float("180-64") faceva saltare tutto lo stato e lo schermo restava al pezzo vecchio
                    par = doc.resolved_parameters()

                    def _v(x):
                        try:
                            return float(evaluate(x, par))
                        except Exception:  # noqa: BLE001 - un nome per la scritta: non deve mai fermare niente
                            return None

                    def _mm(x):
                        v = _v(x)
                        return fmt_mm(round(v, 2)) if v is not None else str(x)

                    def _ang(a):
                        v = _v(a)
                        return '' if v == 90 else f' a {fmt_mm(round(v, 2)) if v is not None else a}°'
                    dove: dict = {}
                    for fo in f.get('folds') or []:
                        verso = 'in su' if fo.get('direction', 'up') == 'up' else 'in giù'
                        dove[fo['id']] = 'in mezzo'
                        part['children'].append(_n(f'Piega in mezzo{_ang(fo.get("angle", 90)) or " 90°"} {verso[3:]}',
                                                   'flange', f'{fid}/{fo["id"]}'))
                    for fl in f.get('flanges') or []:
                        verso = 'su' if fl.get('direction', 'up') == 'up' else 'giù'
                        ang = fl.get('angle', 90)
                        if fl.get('parent'):
                            sopra = dove.get(fl['parent'], fl['parent'])
                            cosa = 'Orlo' if abs(_v(ang) or 0) >= 170 else 'Piega'
                            testo = f'{cosa} su piega {sopra} {_mm(fl.get("length"))}' + ('' if cosa == 'Orlo' else f'{_ang(ang)} {verso}')
                        else:
                            lato = sk.describe(fl.get('edge')) if sk else fl.get('edge')
                            nome = {'lato sotto': 'davanti', 'lato sopra': 'dietro', 'lato destro': 'a destra',
                                    'lato sinistro': 'a sinistra'}.get(lato, f'sul {lato}' if str(lato).startswith('lato') else f'su {lato}')
                            dove[fl['id']] = nome
                            testo = f'Piega {nome} {_mm(fl.get("length"))}{_ang(ang)} {verso}'
                        part['children'].append(_n(testo, 'flange', f'{fid}/{fl["id"]}'))
                        for e in fl.get('ears') or []:
                            verso_e = 'verso fuori' if e.get('side') == 'out' else 'verso dentro'
                            part['children'].append(_n(f'Piega {_mm(e.get("length"))} mm{_ang(e.get("angle", 90))} {verso_e}',
                                                       'flange', f'{fid}/{fl["id"]}/{e.get("end")}'))
        if non_usati:
            pieni = [x for x in non_usati if not x.get('vuoto')]
            part['children'].append(_n('Disegni non usati', 'group', 'non_usati', non_usati, chiuso=True,
                                       qta=len(pieni), vuoto=not pieni))
        root['children'].append(part)
    # le strutture, per gruppo e per misura
    for st in result.structures:
        gruppi: OrderedDict = OrderedDict()
        for m in st.members:
            gruppi.setdefault(m.group or st.name, []).append(m)
        nodo_st = _n(st.name, 'structure', st.id)
        for g, aste in gruppi.items():
            righe: OrderedDict = OrderedDict()
            for m in aste:
                righe.setdefault((m.profile.name, round(m.length, 1), bool(m.lavorazioni)), []).append(m)
            ng = _n(g, 'group')
            for (prof, lung, lav), ms in righe.items():
                ng['children'].append(_n(f'{len(ms)} × {prof} — {fmt_mm(lung)}' + (' lavorati' if lav and len(ms) > 1 else
                                                                                   ' lavorato' if lav else ''),
                                         'members', [f'{st.id}/{m.id}' for m in ms]))
            nodo_st['children'].append(ng)
        # le lavorazioni sui tubi di questa struttura, nell'ordine in cui si fanno
        lav = [f for f in doc.features if not isinstance(f, Sketch) and f.get('type') == 'tube_cut'
               and f.get('structure') == st.id]
        if lav:
            nl = _n('Lavorazioni sui tubi', 'group')
            for f in lav:
                fr = stati.get(f['id'])
                aste = ', '.join(f.get('members') or [])
                testo = f'{f.get("etichetta") or f.get("name") or "Lavorazione"} su {aste}' + (' (passante)' if f.get('through') else '')
                nl['children'].append(_n(testo, 'tube_cut', f['id'], status='disattivata' if f.get('disattiva') else
                                         (None if fr and fr.ok else 'errore')))
            nodo_st['children'].append(nl)
        root['children'].append(nodo_st)
    usati = {f.get('sketch') for f in doc.features if not isinstance(f, Sketch)}
    for f in doc.features:
        if not isinstance(f, Sketch) and f.get('type') == 'structure':
            usati |= doc._sketch_refs(f)
    for f in doc.features:
        if isinstance(f, Sketch) and f.id not in usati and isinstance(f.plane, str):
            fr = stati.get(f.id)
            root['children'].append(_n(f.name or f.id, 'sketch', f.id,
                                       status=None if fr and fr.ok else 'da chiudere'))
    for fr in result.features:
        if not fr.ok and fr.type in ('structure', 'tube_cut') and fr.id not in {n['id'] for n in _tutti(root)}:
            root['children'].append(_n(f'{fr.id}: {fr.message}', 'structure', fr.id, status='errore'))
    return root


def _tutti(n):
    yield n
    for c in n['children']:
        yield from _tutti(c)


def Document_id(f) -> str:  # noqa: N802 - piccolo aiuto locale
    return f.id if isinstance(f, Sketch) else f['id']


def as_text(node, prefix: str = '', last: bool = True, root: bool = True) -> str:
    righe = []
    if root:
        righe.append(node['label'].upper())
    else:
        righe.append(prefix + ('└── ' if last else '├── ') + node['label'])
    figli = node['children']
    for i, c in enumerate(figli):
        nuovo = '' if root else prefix + ('    ' if last else '│   ')
        righe.append(as_text(c, nuovo, i == len(figli) - 1, False))
    return '\n'.join(righe)
