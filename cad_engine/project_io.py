"""File di progetto .steelcad: salvataggio sicuro, copia precedente, autosave, recupero.

- si scrive su un file temporaneo e poi lo si sostituisce: un file a metà non esiste mai;
- prima di sovrascrivere, la versione precedente diventa "<nome>.steelcad.bak";
- l'autosave va in "<nome>.steelcad.autosave";
- all'apertura, `recovery_available` dice se l'autosave è più nuovo del file.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .document import Document
from .errors import SteelCADError, ProjectFileError

EXT = '.steelcad'


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + '.tmp')
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def save(doc: Document, path, *, backup: bool = True) -> Path:
    path = Path(path)
    if path.suffix != EXT:
        path = path.with_suffix(EXT)
    text = json.dumps(doc.to_dict(), ensure_ascii=False, indent=1)
    if backup and path.exists():
        bak = path.with_name(path.name + '.bak')
        os.replace(path, bak)
    _atomic_write(path, text)
    auto = autosave_path(path)
    if auto.exists():
        auto.unlink()
    return path


def load(path) -> Document:
    path = Path(path)
    try:
        d = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise ProjectFileError(f'Il file {path} non esiste.') from None
    except (ValueError, UnicodeDecodeError):
        raise ProjectFileError(f'Il file {path.name} è rovinato e non si può leggere. Prova la copia '
                               f'{path.name}.bak o il recupero automatico.') from None
    if not isinstance(d, dict) or not isinstance(d.get('features', []), list):
        raise ProjectFileError(f'Il file {path.name} non è un progetto Radius.')
    try:
        doc = Document.from_dict(d)
    except SteelCADError:
        raise
    except Exception:  # noqa: BLE001 - un progetto scritto male (a mano o da un'altra versione)
        raise ProjectFileError(f'Il file {path.name} non è un progetto Radius valido (forse di una versione '
                               f'diversa). Prova la copia {path.name}.bak.') from None
    ripara_raccordi(doc)
    return doc


def su_faccia_di_lamiera(doc: Document, plane) -> bool:
    """Lo sketch sta su una faccia (o sullo sviluppo) di una lamiera: lamiera piegata, profilo in lamiera, lamiera da
    STEP, piega su bordo libero. Lì raccordi e smussi degli spigoli sono tagli della lamiera (02/11: sul profilo
    erano tagli di un pezzo pieno, e il pezzo smetteva di essere lamiera: niente sviluppo nelle tavole)."""
    if not isinstance(plane, dict):
        return False
    faccia = plane.get('face') or ''
    fid = plane.get('flat') or faccia.split('/')[0]
    f = next((x for x in doc.features if not hasattr(x, 'entities') and x.get('id') == fid), None)
    if f is None:
        return False
    tipo = f.get('type')
    if tipo == 'sheet':
        return True
    if plane.get('flat'):
        return False
    if tipo in ('sheet_shape', 'step_lamiera'):
        return not faccia.endswith('/testa')
    return tipo == 'sheet_edge_flange' and faccia.endswith(('/interno', '/esterno'))


def ripara_raccordi(doc: Document) -> int:
    """I raccordi/smussi degli spigoli fatti prima del 02/11 sulle facce di un profilo in lamiera (o da STEP, o di una
    piega su bordo): erano tagli di un pezzo pieno, diventano tagli della lamiera. Lo stesso per i tagli passanti
    (04/11, porta ugelli: la tasca passante su una piega faceva smettere il pezzo di essere lamiera, e ogni «Togli
    materiale» dopo dava errore). Ritorna quanti ne ha cambiati."""
    piani = {x.id: x.plane for x in doc.features if hasattr(x, 'entities')}
    n = 0
    for f in doc.features:
        if hasattr(f, 'entities') or f.get('type') != 'extrude' or f.get('operation') != 'cut':
            continue
        if not (f.get('through_all') or str(f.get('name', '')).startswith(('Raccordo spigolo', 'Smusso spigolo'))):
            continue
        if not su_faccia_di_lamiera(doc, piani.get(f.get('sketch'))):
            continue
        for k in ('operation', 'through_all', 'reverse', 'distance'):
            f.pop(k, None)
        f['type'] = 'sheet_cut'
        n += 1
    return n


def autosave_path(path) -> Path:
    path = Path(path)
    return path.with_name(path.name + '.autosave')


def autosave(doc: Document, path) -> Path:
    auto = autosave_path(path)
    _atomic_write(auto, json.dumps(doc.to_dict(), ensure_ascii=False))
    return auto


def recovery_available(path) -> bool:
    path, auto = Path(path), autosave_path(path)
    if not auto.exists():
        return False
    return not path.exists() or auto.stat().st_mtime > path.stat().st_mtime


def recover(path) -> Document:
    return load(autosave_path(path))
