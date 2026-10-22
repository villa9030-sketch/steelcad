"""Versione specchiata del pezzo (22/10): il 3D specchiato riletto, sviluppo uguale, salvata accanto."""
import os
import tempfile

import build123d as bd
import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


def test_staffa_specchiata(tmp_path):
    s = Service()
    s.new_project('lamiera', {'name': 'Staffa', 'larghezza': 120, 'profondita': 80, 'spessore': 2, 'raggio': 1, 'k': 0.4})
    s.add_flange('SM1', 'L2', {'length': '40'})
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    s.sketch_add_circle(sid, [30, 30], 4)
    s.create_from_sketch(sid, 'cut', {})
    assert not s.crea_specchiato()['ok']                       # prima va salvato
    assert s.save(str(tmp_path / 'Staffa.steelcad'))['ok']
    a0, bb0 = s.result.body.sheet.flat_area, bd.Shape.cast(s.result.body.shape).bounding_box()
    r = s.crea_specchiato()
    assert r['ok'], r.get('message')
    assert (tmp_path / 'Staffa specchiato.steelcad').exists() and 'uguale' in r['message']
    assert s.result.body.sheet.flat_area == pytest.approx(a0, abs=1e-3)
    bb = bd.Shape.cast(s.result.body.shape).bounding_box()
    assert bb.min.X == pytest.approx(-bb0.max.X, abs=1e-3) and bb.size.Z == pytest.approx(bb0.size.Z, abs=1e-3)
