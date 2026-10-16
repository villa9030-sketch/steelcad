"""Errori del motore: messaggio per l'utente in italiano, codice stabile, dettagli tecnici a parte.

La UI mostra `message`; `code` serve a decidere cosa evidenziare; `details`
va nel registro, mai a schermo.
"""
from __future__ import annotations


class SteelCADError(Exception):
    code = 'errore'

    def __init__(self, message: str, *, code: str | None = None, feature: str | None = None,
                 details: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.feature = feature
        self.details = details

    def to_dict(self) -> dict:
        return {'code': self.code, 'message': self.message, 'feature': self.feature}


class ExpressionError(SteelCADError):
    code = 'espressione'


class SketchError(SteelCADError):
    code = 'sketch'


class FeatureError(SteelCADError):
    code = 'feature'


class LostReferenceError(FeatureError):
    """Un riferimento a faccia o spigolo non trova più la geometria."""
    code = 'riferimento_perso'


class ExportError(SteelCADError):
    code = 'export'


class ProjectFileError(SteelCADError):
    code = 'file_progetto'
