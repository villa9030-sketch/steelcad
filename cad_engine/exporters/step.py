"""Export STEP (AP214, mm) e verifica rileggendo il file."""
from __future__ import annotations

from pathlib import Path

import build123d as bd

from ..errors import ExportError
from ..features.base import volume


def export(shape, path, *, name: str = 'SteelCAD') -> dict:
    path = Path(path)
    if shape is None:
        raise ExportError('Non c\'è niente da esportare: il pezzo non è ancora stato costruito.')
    s = bd.Shape.cast(shape)
    s.label = name
    tmp = path.with_suffix(path.suffix + '.tmp')
    ok = bd.export_step(s, str(tmp), unit=bd.Unit.MM)
    if not ok or not tmp.exists() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise ExportError(f'Lo STEP non è stato scritto in {path}.')
    tmp.replace(path)
    return verify(path, volume(shape))


def verify(path, expected_volume: float | None = None) -> dict:
    """Rilegge lo STEP e confronta il volume: lo STEP deve contenere geometria vera, uguale al modello."""
    back = bd.import_step(str(path))
    vol = sum(s.volume for s in back.solids())
    out = {'path': str(path), 'solids': len(back.solids()), 'volume_mm3': vol}
    if expected_volume is not None:
        diff = abs(vol - expected_volume) / max(expected_volume, 1e-9)
        out['volume_diff_rel'] = diff
        if diff > 1e-6:
            raise ExportError(f'Lo STEP riletto ha volume {vol:.3f} mm³ invece di {expected_volume:.3f} mm³: '
                              'il file non è affidabile.')
    return out
