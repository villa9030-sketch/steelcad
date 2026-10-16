"""SteelCAD — motore CAD parametrico per carpenteria metallica.

Usabile senza interfaccia grafica:

    from cad_engine import Document, History
    doc = Document('Piastra', 'S235')
"""
from .commands import History  # noqa: F401
from .document import Document  # noqa: F401
from .errors import SteelCADError  # noqa: F401

__version__ = '0.1.0'
