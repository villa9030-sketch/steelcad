"""Misure del pezzo: volume, superficie, ingombro, peso, baricentro."""
from __future__ import annotations

from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from .. import materials
from ..features.measure_util import bbox


_ULTIME: list = []          # [(forma, materiale, risultato)] le ultime calcolate


def properties(shape, material_code: str) -> dict:
    for f, m, r in _ULTIME:
        if f is shape and m == material_code:
            return r
    r = _properties(shape, material_code)
    _ULTIME.insert(0, (shape, material_code, r))
    del _ULTIME[4:]
    return r


def _properties(shape, material_code: str) -> dict:
    vp = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, vp)
    sp = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, sp)
    (x0, y0, z0), (x1, y1, z1) = bbox(shape)
    c = vp.CentreOfMass()
    mat = materials.get(material_code)
    vol = vp.Mass()
    return {
        'volume_mm3': vol,
        'area_mm2': sp.Mass(),
        'bbox_mm': {'min': [x0, y0, z0], 'max': [x1, y1, z1], 'size': [x1 - x0, y1 - y0, z1 - z0]},
        'center_mm': [c.X(), c.Y(), c.Z()],
        'material': mat.code,
        'density_g_cm3': mat.density_g_cm3,
        'mass_kg': mat.mass_kg(vol),
    }
