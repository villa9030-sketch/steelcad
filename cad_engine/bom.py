"""Distinta materiali (BOM) del progetto: parti, aste delle strutture, componenti.

Campi: codice, descrizione, quantità, tipo, profilo, materiale, spessore,
lunghezza, dimensioni, peso unitario, peso totale. Si ricalcola a ogni
ricostruzione: non c'è niente da tenere allineato a mano.
"""
from __future__ import annotations

from .analysis import properties
from .errors import SteelCADError
from .structures.cutlist import cut_list


def bom(doc, result) -> list[dict]:
    righe = []
    if result.body is not None:
        p = properties(result.body.shape, doc.material)
        size = sorted(p['bbox_mm']['size'], reverse=True)
        spessore = None
        tipo = 'parte'
        try:
            from .exporters.dxf import flat_reference
            spessore = flat_reference(result.body.shape)[2]
            tipo = 'piastra'
        except SteelCADError:
            pass
        righe.append({
            'code': doc.meta.get('code') or 'P1', 'description': doc.meta.get('name', 'Parte'), 'qty': 1,
            'type': tipo, 'profile': None, 'material': doc.material, 'thickness_mm': spessore, 'length_mm': None,
            'dims_mm': [round(v, 1) for v in size], 'kg_each': p['mass_kg'], 'kg_total': p['mass_kg'],
        })
    cl = cut_list(result.structures)
    for i, r in enumerate(cl['rows'], start=1):
        righe.append({
            'code': f'A{i}', 'description': f'{r["description"]} L={r["length_mm"]:g} ({"/".join(r["cuts"])})',
            'qty': r['qty'], 'type': 'profilo', 'profile': r['profile'], 'material': r['material'],
            'thickness_mm': None, 'length_mm': r['length_mm'], 'dims_mm': None,
            'kg_each': r['kg_each'], 'kg_total': r['kg_total'], 'groups': r['groups'],
        })
    return righe


def total_kg(righe) -> float:
    return sum(r['kg_total'] for r in righe)
