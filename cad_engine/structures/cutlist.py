"""Cut list: le aste raggruppate come le taglia l'officina.

Stessa riga se: stesso profilo, stesso materiale, stessa lunghezza di taglio
(al decimo di mm) e stessi tagli alle estremità. Il peso è quello commerciale:
kg/m del profilo × lunghezza di taglio (come si compra e si pesa la barra).
"""
from __future__ import annotations

from collections import OrderedDict

from ..units import fmt_mm
from .frame import describe_cut


def _base(nome: str) -> str:
    """«Fianco in alto (2)» → «Fianco in alto»: i pezzi uguali si contano insieme."""
    if nome.endswith(')') and ' (' in nome:
        testa, coda = nome.rsplit(' (', 1)
        if coda[:-1].isdigit():
            return testa
    return nome


_FORME: dict = {}          # id(solido) -> (solido, forma): la forma dei tagli non cambia se il tubo è lo stesso


def forma_tagli(m) -> dict:
    """Com'è fatto il pezzo coi tagli inclinati, per chi taglia (03/11): «a trapezio» (le due punte dallo stesso lato,
    la cornice) o «a parallelogramma» (punte da lati opposti), e su che lato del tubo si vede l'angolo (per un
    rettangolare: «sul lato da 40»). Si guarda il pezzo vero: dove stanno le punte alle due teste.
    {'forma': 'trapezio' | 'parallelo' | 'una' | '', 'lato': mm o None, 'punte': [(x, y) | None, …]}"""
    if not any(abs(a) > 1e-6 for a in m.cuts) or m.solid is None:
        return {'forma': '', 'lato': None, 'punte': [None, None]}
    hit = _FORME.get(id(m.solid))
    if hit is not None and hit[0] is m.solid:
        return hit[1]
    import build123d as bd
    local = bd.Plane(origin=m.start, x_dir=m.x, z_dir=m.w).to_local_coords(m.solid)
    vs = [(v.X, v.Y, v.Z) for v in local.vertices()]
    cx, cy = m.origin_shift.dot(m.x), m.origin_shift.dot(m.y)
    z0, z1 = min(v[2] for v in vs), max(v[2] for v in vs)
    punte = []
    for i, zz in ((0, z0), (1, z1)):
        if abs(m.cuts[i]) < 1e-6:
            punte.append(None)
            continue
        qui = [v for v in vs if abs(v[2] - zz) < 0.05]
        px, py = sum(v[0] for v in qui) / len(qui) - cx, sum(v[1] for v in qui) / len(qui) - cy
        punte.append((px, py) if abs(px) + abs(py) > 1e-3 else None)
    ok = [p for p in punte if p]
    if len(ok) == 2:
        forma = 'trapezio' if ok[0][0] * ok[1][0] + ok[0][1] * ok[1][1] > 0 else 'parallelo'
    else:
        forma = 'una' if ok else ''
    lato = None
    if ok:
        px, py = ok[0]
        # la punta spostata lungo la larghezza: l'angolo si vede sulle facce larghe (sopra e sotto), e viceversa
        lato = m.profile.width if abs(px) > abs(py) else m.profile.height
    out = {'forma': forma, 'lato': round(lato, 1) if lato else None, 'punte': punte}
    if len(_FORME) > 3000:
        _FORME.clear()
    _FORME[id(m.solid)] = (m.solid, out)
    return out


def descrivi_tagli(r) -> str:
    """«45° / 45° a trapezio, angolo sul lato da 40» (il lato solo per i tubi non quadri)."""
    t = ' / '.join(r['cuts'])
    if r.get('forma') == 'trapezio':
        t += ' a trapezio'
    elif r.get('forma') == 'parallelo':
        t += ' a parallelogramma'
    if r.get('lato_taglio') and r.get('quadro') is False:
        t += f', angolo sul lato da {fmt_mm(r["lato_taglio"])}'
    return t


def cut_list(structures) -> dict:
    """Le righe hanno anche «dove» (03/11): i nomi da officina dei pezzi di quella riga («Montante a sinistra»,
    «Fianco in alto × 2»), così chi taglia sa a cosa serve ogni misura."""
    from .nomi import nomi_aste
    righe: OrderedDict = OrderedDict()
    for st in structures:
        nomi = nomi_aste(st.members)
        for m in st.members:
            tagli = tuple(sorted(round(a, 1) for a in m.cuts))
            fo = forma_tagli(m) if any(tagli) else {'forma': '', 'lato': None}
            key = (m.profile.name, m.material, round(m.length, 1), tagli, m.lavorazioni, fo['forma'], fo['lato'])
            r = righe.get(key)
            if r is None:
                r = righe[key] = {
                    'profile': m.profile.name, 'description': m.profile.description, 'material': m.material,
                    'length_mm': round(m.length, 1), 'cuts': [describe_cut(a) for a in tagli],
                    'qty': 0, 'members': [], 'kg_each': m.kg(), 'groups': [], 'lavorata': bool(m.lavorazioni),
                    'forma': fo['forma'], 'lato_taglio': fo['lato'],
                    'quadro': m.profile.family in ('SHS', 'CHS') or abs(m.profile.width - m.profile.height) < 1e-6,
                    '_dove': OrderedDict(),
                }
            r['qty'] += 1
            b = _base(nomi.get(m.id, m.id))
            r['_dove'][b] = r['_dove'].get(b, 0) + 1
            r['members'].append(f'{st.id}/{m.id}')
            if m.group and m.group not in r['groups']:
                r['groups'].append(m.group)
    lista = sorted(righe.values(), key=lambda r: (r['profile'], r['material'], -r['length_mm']))
    for r in lista:
        r['kg_total'] = r['kg_each'] * r['qty']
        r['dove'] = [n if k == 1 else f'{n} × {k}' for n, k in r.pop('_dove').items()]
        r['tagli_testo'] = descrivi_tagli(r)
    per_profilo: OrderedDict = OrderedDict()
    for r in lista:
        k = (r['profile'], r['material'])
        p = per_profilo.setdefault(k, {'profile': r['profile'], 'material': r['material'], 'pieces': 0,
                                       'total_length_mm': 0.0, 'kg': 0.0})
        p['pieces'] += r['qty']
        p['total_length_mm'] += r['length_mm'] * r['qty']
        p['kg'] += r['kg_total']
    from .accessori import righe as righe_accessori
    return {'rows': lista, 'totals': list(per_profilo.values()),
            'pieces': sum(r['qty'] for r in lista), 'kg': sum(r['kg_total'] for r in lista),
            'accessori': righe_accessori(structures)}


def as_text(cl: dict) -> str:
    """La cut list come la si stampa per l'officina."""
    out = []
    for t in cl['totals']:
        out.append(f'{t["profile"]} {t["material"]}')
        for r in cl['rows']:
            if (r['profile'], r['material']) != (t['profile'], t['material']):
                continue
            tagli = r.get('tagli_testo') or '/'.join(r['cuts'])
            out.append(f'  {r["qty"]} × {r["length_mm"]:g} mm   tagli {tagli}' + ('   con lavorazioni' if r.get('lavorata') else ''))
        out.append(f'  totale {t["pieces"]} pezzi, {t["total_length_mm"] / 1000:.3f} m, {t["kg"]:.2f} kg')
    return '\n'.join(out).replace('.', ',')
