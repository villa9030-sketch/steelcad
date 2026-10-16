"""Materiali e densità.

Densità nominali (g/cm³): acciai al carbonio EN 10025 7,85; inox austenitici
EN 10088-1 (1.4301 = AISI 304: 7,90; 1.4404 = AISI 316L: 8,00); alluminio
EN 573 (6082: 2,70; 5754: 2,67). Il catalogo si estende senza toccare il codice
passando un dizionario a `Material.catalog_from`.
"""
from __future__ import annotations

from dataclasses import dataclass

from .errors import SteelCADError


@dataclass(frozen=True)
class Material:
    code: str
    description: str
    density_g_cm3: float

    def mass_kg(self, volume_mm3: float) -> float:
        # 1 cm³ = 1000 mm³; g -> kg / 1000
        return volume_mm3 / 1000.0 * self.density_g_cm3 / 1000.0


CATALOG: dict[str, Material] = {m.code: m for m in (
    Material('S235', 'Acciaio S235JR', 7.85),
    Material('S275', 'Acciaio S275JR', 7.85),
    Material('S355', 'Acciaio S355J2', 7.85),
    Material('DC01', 'Lamiera DC01 laminata a freddo', 7.85),
    Material('DX51D', 'Lamiera zincata DX51D', 7.85),
    Material('AISI304', 'Inox 1.4301 (AISI 304)', 7.90),
    Material('AISI316L', 'Inox 1.4404 (AISI 316L)', 8.00),
    Material('AL6082', 'Alluminio EN AW-6082', 2.70),
    Material('AL5754', 'Alluminio EN AW-5754', 2.67),
)}


def get(code: str) -> Material:
    try:
        return CATALOG[code]
    except KeyError:
        noti = ', '.join(sorted(CATALOG))
        raise SteelCADError(f'Il materiale "{code}" non è nel catalogo. Materiali disponibili: {noti}.',
                            code='materiale_sconosciuto') from None
