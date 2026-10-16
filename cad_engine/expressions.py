"""Valori di quota: un numero oppure un'espressione sui parametri del documento.

Ammessi soltanto numeri, nomi di parametri, + - * / ** e parentesi. Niente
chiamate di funzione né attributi: l'espressione non può eseguire codice.
"""
from __future__ import annotations

import ast
import operator

from .errors import ExpressionError

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def names_in(value) -> set[str]:
    """I nomi di parametro usati da un valore (per il grafo delle dipendenze)."""
    if not isinstance(value, str):
        return set()
    try:
        tree = ast.parse(value.replace(',', '.'), mode='eval')
    except SyntaxError:
        return set()
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def evaluate(value, params: dict[str, float], what: str = 'valore') -> float:
    if isinstance(value, bool):
        raise ExpressionError(f'Il {what} deve essere un numero, non vero/falso.')
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        raise ExpressionError(f'Il {what} è vuoto.')
    testo = value.strip().replace(',', '.')
    try:
        tree = ast.parse(testo, mode='eval')
    except SyntaxError:
        raise ExpressionError(f'Non capisco "{value}" come {what}. Scrivi un numero o un nome di parametro.') from None

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.Name):
            if n.id not in params:
                raise ExpressionError(f'Il parametro "{n.id}" usato in "{value}" non esiste.')
            return float(params[n.id])
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Div) and b == 0:
                raise ExpressionError(f'In "{value}" c\'è una divisione per zero.')
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _UNARY:
            return _UNARY[type(n.op)](ev(n.operand))
        raise ExpressionError(f'In "{value}" si possono usare solo numeri, parametri e + - * / ( ).')

    return ev(tree)
