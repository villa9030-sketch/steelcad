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
        if t == 'fillet':
            return f'{nome or "Raccordo"} R{f.get("radius")}'
        if t == 'chamfer':
            return f'{nome or "Smusso"} {f.get("distance")} mm'
        if t == 'sheet':
            sp = f.get('thickness')
            try:
                sp = fmt_mm(evaluate(sp, doc.resolved_parameters(), 'spessore'))
            except SteelCADError:
                pass
            return f'Lamiera sp. {sp}'
        if t == 'sheet_cut':
            return f'{nome or "Taglio"} attraverso la lamiera'
    except (KeyError, ValueError):
        pass
    return nome or f['id']


def project_tree(doc, result) -> dict:
    root = _n(doc.meta.get('name', 'Progetto'), 'project')
    stati = {fr.id: fr for fr in result.features}
    # il pezzo
    solid_feats = [f for f in doc.features if not isinstance(f, Sketch) and f['type'] != 'structure']
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
                if any(x.get('sketch') == fid for x in solid_feats) or isinstance(f.plane, dict):
                    st = (fr.sketch_status or {}).get('state') if fr else None
                    part['children'].append(_n(f'{f.name or "Sketch"}', 'sketch', fid,
                                               status=None if fr and fr.ok else 'errore',
                                               ))
                    if st and st != 'completo':
                        part['children'][-1]['status'] = 'errore' if not fr.ok else st
                continue
            if f in solid_feats:
                part['children'].append(_n(_feature_label(doc, f, fr), f['type'], fid,
                                           status=None if fr and fr.ok else 'errore'))
                if f['type'] == 'sheet':
                    sk = doc.sketch(f['sketch']) if f.get('sketch') else None
                    for fl in f.get('flanges') or []:
                        lato = sk.describe(fl.get('edge')) if sk else fl.get('edge')
                        verso = 'su' if fl.get('direction', 'up') == 'up' else 'giù'
                        ang = fl.get('angle', 90)
                        part['children'].append(_n(f'{fl["id"]}: flangia {fl.get("length")} a {ang}° {verso}, {lato}',
                                                   'flange', f'{fid}/{fl["id"]}'))
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
                righe.setdefault((m.profile.name, round(m.length, 1)), []).append(m)
            ng = _n(g, 'group')
            for (prof, lung), ms in righe.items():
                ng['children'].append(_n(f'{len(ms)} × {prof} — {fmt_mm(lung)}', 'members',
                                         [f'{st.id}/{m.id}' for m in ms]))
            nodo_st['children'].append(ng)
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
        if not fr.ok and fr.type == 'structure':
            root['children'].append(_n(f'{fr.id}: {fr.message}', 'structure', fr.id, status='errore'))
    return root


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
