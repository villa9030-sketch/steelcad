"""Unità e tolleranze. Tutto il motore lavora in mm e gradi; i radianti restano interni."""
import math

# Tolleranza per confrontare punti e misure (mm). Molto sotto la precisione
# del taglio laser (~0,05 mm) ma sopra il rumore numerico del kernel.
TOL = 1e-6
# Sotto questa lunghezza un segmento DXF è un "microsegmento" da segnalare (mm).
MICRO_SEGMENT = 0.01


def rad(deg: float) -> float:
    return math.radians(deg)


def deg(rad_: float) -> float:
    return math.degrees(rad_)


def fmt_mm(v: float) -> str:
    """300 -> '300', 2.5 -> '2,5'. Per i messaggi all'utente."""
    s = f'{v:.3f}'.rstrip('0').rstrip('.')
    return s.replace('.', ',')


def cap(s: str) -> str:
    """Prima lettera maiuscola, il resto com'è (str.capitalize abbasserebbe i nomi propri)."""
    return s[:1].upper() + s[1:]
