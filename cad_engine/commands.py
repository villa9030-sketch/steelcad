"""Comandi con undo/redo.

Ogni modifica al documento passa da `History.change(...)`: si salva la
definizione prima e dopo (JSON piccolo, la geometria resta nella cache e si
ricostruisce). Undo e redo rimettono la definizione e ricostruiscono.

    with history.change('Larghezza 300 → 400'):
        doc.set_parameter('larghezza', 400)

Se dentro il blocco succede un errore, il documento torna com'era e nella
storia non resta niente.
"""
from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from dataclasses import dataclass

from .document import Document
from .errors import SteelCADError


@dataclass
class Step:
    label: str
    before: str
    after: str


@dataclass
class MetaStep:
    """Un passo che cambia solo un dato del progetto (i ritocchi delle tavole, 29/10): niente copia di tutto il
    progetto prima e dopo (con 4.000 elementi nello sketch erano 0,4 s a ogni ritocco), niente ricostruzione."""
    label: str
    chiave: str
    before: object
    after: object


class History:
    def __init__(self, doc: Document, limit: int = 500):
        self.doc = doc
        self.limit = limit
        self.done: list[Step] = []
        self.undone: list[Step] = []
        self.dirty = False            # modifiche non salvate (per l'autosave)

    def _snap(self) -> str:
        # l'ordine delle chiavi si conserva (i parametri compaiono come li ha messi l'utente); per sapere se è
        # cambiato qualcosa si confrontano in ordine alfabetico
        return json.dumps(self.doc.to_dict())

    @staticmethod
    def _uguali(a: str, b: str) -> bool:
        return a == b or json.dumps(json.loads(a), sort_keys=True) == json.dumps(json.loads(b), sort_keys=True)

    @contextmanager
    def change(self, label: str):
        before = self._snap()
        try:
            yield self.doc
        except Exception:
            self.doc.load_definition(json.loads(before))
            raise
        after = self._snap()
        if self._uguali(after, before):
            return
        self.done.append(Step(label, before, after))
        if len(self.done) > self.limit:
            self.done.pop(0)
        self.undone.clear()
        self.dirty = True
        self.doc.meta['modified'] = _now()

    def change_meta(self, label: str, chiave: str, valore) -> bool:
        """doc.meta[chiave] = valore (None = toglilo), come un passo della storia. False se non cambia niente."""
        prima = copy.deepcopy(self.doc.meta.get(chiave))
        if prima == valore:
            return False
        self._metti(chiave, valore)
        self.done.append(MetaStep(label, chiave, prima, copy.deepcopy(valore)))
        if len(self.done) > self.limit:
            self.done.pop(0)
        self.undone.clear()
        self.dirty = True
        self.doc.meta['modified'] = _now()
        return True

    def _metti(self, chiave, valore):
        if valore is None:
            self.doc.meta.pop(chiave, None)
        else:
            self.doc.meta[chiave] = copy.deepcopy(valore)

    def ultimo_solo_meta(self, avanti: bool = False) -> bool:
        """Il prossimo Annulla (o Rifai) tocca solo un dato del progetto: il pezzo non va ricostruito."""
        lista = self.undone if avanti else self.done
        return bool(lista) and isinstance(lista[-1], MetaStep)

    def undo(self) -> str:
        if not self.done:
            raise SteelCADError('Non c\'è niente da annullare.', code='niente_da_annullare')
        s = self.done.pop()
        if isinstance(s, MetaStep):
            self._metti(s.chiave, s.before)
            self.undone.append(s)
            self.dirty = True
            return s.label
        self.doc.load_definition(json.loads(s.before))
        self.undone.append(s)
        self.dirty = True
        return s.label

    def redo(self) -> str:
        if not self.undone:
            raise SteelCADError('Non c\'è niente da ripetere.', code='niente_da_ripetere')
        s = self.undone.pop()
        if isinstance(s, MetaStep):
            self._metti(s.chiave, s.after)
            self.done.append(s)
            self.dirty = True
            return s.label
        self.doc.load_definition(json.loads(s.after))
        self.done.append(s)
        self.dirty = True
        return s.label

    @property
    def can_undo(self) -> bool:
        return bool(self.done)

    @property
    def can_redo(self) -> bool:
        return bool(self.undone)

    def labels(self) -> dict:
        return {'undo': [s.label for s in reversed(self.done)], 'redo': [s.label for s in reversed(self.undone)]}


def _now() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec='seconds')
