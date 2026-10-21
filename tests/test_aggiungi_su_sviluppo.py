"""Aggiungi materiale disegnando sullo sviluppo (21/10, Stefano: «dov'è aggiungi materiale?»)."""
import os
import tempfile

import build123d as bd
import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


def _base():
    s = Service()
    assert s.new_project('lamiera', {'name': 'B', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.4})['ok']
    return s


def _aggiungi(s, rett):
    sid = s.sketch_on_flat('SM1')['sketch']
    assert s.sketch_add_rectangle(sid, *rett)['ok']
    a0 = s.result.body.sheet.flat_area
    r = s.sheet_tab(sid)
    return r, a0


def test_linguetta_sulla_base_dallo_sviluppo():
    s = _base()
    r, a0 = _aggiungi(s, ([100, 200], [200, 230]))          # fuori dal bordo di sopra, attaccata
    assert r['ok'], r.get('message')
    d = s.result.body.sheet
    assert d.flat_area == pytest.approx(a0 + 100 * 30, abs=1e-3)
    assert len(bd.Shape.cast(s.result.body.shape).solids()) == 1


def test_linguetta_su_una_flangia_dallo_sviluppo():
    s = _base()
    assert s.add_flange('SM1', 'L2', {'length': '100'})['ok']   # il lato destro sale
    fl = s.result.body.sheet.flat.bounding_box()
    # attaccata al bordo di sopra della flangia, nello sviluppo
    x0 = fl.max.X - 60
    r, a0 = _aggiungi(s, ([x0, fl.max.Y], [x0 + 40, fl.max.Y + 20]))
    assert r['ok'], r.get('message')
    assert s.result.body.sheet.flat_area == pytest.approx(a0 + 40 * 20, abs=1e-3)
    assert len(bd.Shape.cast(s.result.body.shape).solids()) == 1
