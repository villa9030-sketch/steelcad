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


def _n(label, kind, ref=None, children=None, status=None):
    return {'label': label, 'kind': kind, 'ref': ref, 'children': children or [], 'status': status}


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
                return f'{nome or "Marcatura"} laser: ' + (', '.join(f'«{t}»' for t in testi[:3]) or 'testi') +                     (' …' if len(testi) > 3 else '')
            extra = []
            try:
                sk = doc.sketch(f['sketch'])
                fil, sva = {}, {}
                for e in sk.entities.values():
                    h = e.get('hole') if e['kind'] == 'circle' and not e.get('construction') else None
                    if h and h.get('tipo') == 'filettato':
                        fil[h['M']] = fil.get(h['M'], 0) + 1
                    elif h and h.get('tipo') == 'svasato':
                        k = f'Ø{fmt_mm(h["D"])}'
                        sva[k] = sva.get(k, 0) + 1
                    elif h and h.get('tipo') == 'inserto':
                        k = f'inserti {h["codice"]}'
                        sva[k] = sva.get(k, 0) + 1
                extra = [f'{n} × {m}' for m, n in fil.items()] + [f'{n} × {"" if k.startswith("inserti") else "svasati "}{k}'
                                                                  for k, n in sva.items()]
            except (SteelCADError, KeyError):
                pass
            return f'{nome or "Taglio"} attraverso la lamiera' + (f' ({", ".join(extra)})' if extra else '')
    except (KeyError, ValueError):
        pass
    return nome or f['id']


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
        for f in doc.features:
            fid = Document_id(f)
            fr = stati.get(fid)
            if isinstance(f, Sketch):
                if any(x.get('sketch') == fid for x in solid_feats) or (isinstance(f.plane, dict) and not f.plane.get('tube')):
                    st = (fr.sketch_status or {}).get('state') if fr else None
                    part['children'].append(_n(f'{f.name or "Sketch"}', 'sketch', fid,
                                               status=None if fr and fr.ok else 'errore',
                                               ))
                    if st and st != 'completo':
                        part['children'][-1]['status'] = 'errore' if not fr.ok else st
                continue
            if f in solid_feats:
                part['children'].append(_n(f.get('etichetta') or _feature_label(doc, f, fr), f['type'], fid,
                                           status='disattivata' if f.get('disattiva') else (None if fr and fr.ok else 'errore')))
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
                        part['children'].append(_n(f'Piega in mezzo al pezzo{_ang(fo.get("angle", 90)) or " a 90°"} {verso}',
                                                   'flange', f'{fid}/{fo["id"]}'))
                    for fl in f.get('flanges') or []:
                        verso = 'in su' if fl.get('direction', 'up') == 'up' else 'in giù'
                        ang = fl.get('angle', 90)
                        if fl.get('parent'):
                            sopra = dove.get(fl['parent'], fl['parent'])
                            cosa = 'Orlo' if abs(_v(ang) or 0) >= 170 else 'Piega'
                            testo = f'{cosa} sulla piega {sopra}, {_mm(fl.get("length"))} mm' + ('' if cosa == 'Orlo' else f'{_ang(ang)} {verso}')
                        else:
                            lato = sk.describe(fl.get('edge')) if sk else fl.get('edge')
                            nome = {'lato sotto': 'davanti', 'lato sopra': 'dietro', 'lato destro': 'a destra',
                                    'lato sinistro': 'a sinistra'}.get(lato, f'sul {lato}' if str(lato).startswith('lato') else f'su {lato}')
                            dove[fl['id']] = nome
                            testo = f'Piega {nome}, {_mm(fl.get("length"))} mm{_ang(ang)} {verso}'
                        part['children'].append(_n(testo, 'flange', f'{fid}/{fl["id"]}'))
                        for e in fl.get('ears') or []:
                            verso_e = 'verso fuori' if e.get('side') == 'out' else 'verso dentro'
                            part['children'].append(_n(f'Piega {_mm(e.get("length"))} mm{_ang(e.get("angle", 90))} {verso_e}',
                                                       'flange', f'{fid}/{fl["id"]}/{e.get("end")}'))
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
                testo = f'{f.get("name") or "Lavorazione"} su {aste}' + (' (passante)' if f.get('through') else '')
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
