import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cad_engine import Document  # noqa: E402

FORO = math.pi * 15 ** 2


def plate(width=300, height=200, hole=30, thickness=5, material='S235'):
    """La piastra della Milestone 1: rettangolo quotato, foro al centro, estrusione."""
    doc = Document('Piastra', material)
    doc.set_parameter('larghezza', width)
    sk = doc.add_sketch('XY', 'Profilo piastra')
    r = sk.rectangle(0, 0, width * 0.97, height * 0.95)        # disegnata "a mano", non esatta
    sk.constrain('coincident', r['corners'][0], 'O')
    ids = {
        'w': sk.dimension('length', r['bottom'], value='larghezza'),
        'h': sk.dimension('length', r['left'], value=height),
    }
    c = sk.circle((width / 2 + 3, height / 2 - 2), hole / 2 * 0.9)
    ids['d'] = sk.dimension('diameter', c, value=hole)
    sk.constrain('symmetric', r['corners'][0], r['corners'][2], sk.entities[c]['center'])
    e1 = doc.add_feature('extrude', 'Piastra', sketch=sk.id, distance=thickness, operation='new')
    return doc, sk, r, c, ids, e1


@pytest.fixture
def tmp(tmp_path):
    return tmp_path


@pytest.fixture(autouse=True)
def _cartella_programma(tmp_path_factory, monkeypatch):
    """I progetti recenti dei test non finiscono in quelli veri dell'utente."""
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path_factory.mktemp('steelcad_home')))
