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


def export_project(doc, result, path) -> dict:
    """Tutto il progetto in uno STEP: il pezzo e ogni asta delle strutture, ognuno col suo nome."""
    from ..features.base import volume as vol
    figli, totale = [], 0.0
    if result.body is not None:
        b = bd.Shape.cast(result.body.shape)
        b.label = doc.meta.get('name', 'Pezzo')
        figli.append(b)
        totale += vol(result.body.shape)
    for st in result.structures:
        for m in st.members:
            s = m.solid.copy() if hasattr(m.solid, 'copy') else m.solid
            s.label = f'{st.name} - {m.group or "asta"} {m.id} - {m.profile.name} L={m.length:.1f}'
            figli.append(s)
            totale += m.solid.volume
    if not figli:
        raise ExportError("Il progetto è vuoto: non c'è niente da esportare.")
    asm = bd.Compound(children=figli)
    asm.label = doc.meta.get('name', 'Progetto')
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    if not bd.export_step(asm, str(tmp), unit=bd.Unit.MM):
        tmp.unlink(missing_ok=True)
        raise ExportError(f'Lo STEP non è stato scritto in {path}.')
    tmp.replace(path)
    out = verify(path, totale)
    if out['solids'] != len(figli):
        raise ExportError(f'Lo STEP riletto ha {out["solids"]} solidi invece di {len(figli)}.')
    return out
