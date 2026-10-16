"""Cut list: le aste raggruppate come le taglia l'officina.

Stessa riga se: stesso profilo, stesso materiale, stessa lunghezza di taglio
(al decimo di mm) e stessi tagli alle estremità. Il peso è quello commerciale:
kg/m del profilo × lunghezza di taglio (come si compra e si pesa la barra).
"""
from __future__ import annotations

from collections import OrderedDict

from .frame import describe_cut


def cut_list(structures) -> dict:
    righe: OrderedDict = OrderedDict()
    for st in structures:
        for m in st.members:
            tagli = tuple(sorted(round(a, 1) for a in m.cuts))
            key = (m.profile.name, m.material, round(m.length, 1), tagli)
            r = righe.get(key)
            if r is None:
                r = righe[key] = {
                    'profile': m.profile.name, 'description': m.profile.description, 'material': m.material,
                    'length_mm': round(m.length, 1), 'cuts': [describe_cut(a) for a in tagli],
                    'qty': 0, 'members': [], 'kg_each': m.kg(), 'groups': [],
                }
            r['qty'] += 1
            r['members'].append(f'{st.id}/{m.id}')
            if m.group and m.group not in r['groups']:
                r['groups'].append(m.group)
    lista = sorted(righe.values(), key=lambda r: (r['profile'], r['material'], -r['length_mm']))
    for r in lista:
        r['kg_total'] = r['kg_each'] * r['qty']
    per_profilo: OrderedDict = OrderedDict()
    for r in lista:
        k = (r['profile'], r['material'])
        p = per_profilo.setdefault(k, {'profile': r['profile'], 'material': r['material'], 'pieces': 0,
                                       'total_length_mm': 0.0, 'kg': 0.0})
        p['pieces'] += r['qty']
        p['total_length_mm'] += r['length_mm'] * r['qty']
        p['kg'] += r['kg_total']
    return {'rows': lista, 'totals': list(per_profilo.values()),
            'pieces': sum(r['qty'] for r in lista), 'kg': sum(r['kg_total'] for r in lista)}


def as_text(cl: dict) -> str:
    """La cut list come la si stampa per l'officina."""
    out = []
    for t in cl['totals']:
        out.append(f'{t["profile"]} {t["material"]}')
        for r in cl['rows']:
            if (r['profile'], r['material']) != (t['profile'], t['material']):
                continue
            tagli = '/'.join(r['cuts'])
            out.append(f'  {r["qty"]} × {r["length_mm"]:g} mm   tagli {tagli}')
        out.append(f'  totale {t["pieces"]} pezzi, {t["total_length_mm"] / 1000:.3f} m, {t["kg"]:.2f} kg')
    return '\n'.join(out).replace('.', ',')
