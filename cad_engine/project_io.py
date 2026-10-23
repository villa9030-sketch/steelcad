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
        return Document.from_dict(d)
    except SteelCADError:
        raise
    except Exception:  # noqa: BLE001 - un progetto scritto male (a mano o da un'altra versione)
        raise ProjectFileError(f'Il file {path.name} non è un progetto Radius valido (forse di una versione '
                               f'diversa). Prova la copia {path.name}.bak.') from None


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
