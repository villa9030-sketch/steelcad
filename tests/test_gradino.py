"""Gradino (joggle) sulla punta di una parete (22/10): la parete continua parallela, spostata esattamente di h."""
import os
import tempfile

import build123d as bd
import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


@pytest.mark.parametrize('verso,h', [('dentro', 2), ('fuori', 2), ('dentro', 5)])
def test_gradino(verso, h):
    s = Service()
    s.new_project('lamiera', {'name': 'J', 'larghezza': 100, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    assert s.add_flange('SM1', 'L2', {'length': '60'})['ok']
    r = s.gradino('SM1', 'FL1', h, 45, 30, verso)
    assert r['ok'], r.get('message')
    b = s.result.body
    assert len(bd.Shape.cast(b.shape).solids()) == 1
    fa = bd.Face(b.names['SM1/FL1/esterno'][0])
    na = fa.normal_at(fa.center())
    ultima = s._sheet_def('SM1')['flanges'][-1]['id']
    fb = next(bd.Face(b.names[f'SM1/{ultima}/{x}'][0]) for x in ('esterno', 'interno')
              if bd.Face(b.names[f'SM1/{ultima}/{x}'][0]).normal_at().dot(na) > 0.999)
    assert (fb.center() - fa.center()).dot(na) == pytest.approx(h if verso == 'fuori' else -h, abs=1e-3)
    assert not s.gradino('SM1', 'FL1', h, 45, 30, verso)['ok']           # sulla punta c'è già
