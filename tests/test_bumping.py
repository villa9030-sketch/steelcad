"""Bumping (piegatura a colpi) nelle pieghe su linea: raggio grande con N colpi piccoli a passo costante."""
import math
import os
import tempfile

import build123d as bd
import numpy as np
import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


def piegata(colpi=10, raggio=100, angolo=90, y=300):
    s = Service()
    assert s.new_project('lamiera', {'name': 'B', 'larghezza': 300, 'profondita': 500, 'spessore': 2, 'raggio': 2, 'k': 0.4})['ok']
    sid = s.sketch_on_flat('SM1')['sketch']
    s.sketch_add_polyline(sid, [[-5, y], [305, y]], False)
    r = s.sheet_fold(sid, angolo, 'up', False, {'colpi': colpi, 'raggio': raggio} if colpi else None)
    return s, r


def test_sviluppo_uguale_al_disegno_e_raggio_vero():
    s, r = piegata()
    assert r['ok'], r.get('message')
    d = s.result.body.sheet
    assert d.flat_size[0] == pytest.approx(300, abs=1e-3) and d.flat_size[1] == pytest.approx(500, abs=1e-3)
    assert len(d.flanges) == 10
    assert all(g.bend.angle == pytest.approx(9) for g in d.flanges)
    sh = bd.Shape.cast(s.result.body.shape)
    assert sh.is_valid and len(sh.solids()) == 1
    # gli spigoli esterni dei colpi stanno su un cerchio di raggio ≈ R + t (poligono attorno all'arco)
    P = np.array([(g.origin.Y, g.origin.Z) for g in d.flanges])
    a, b, c = P[0], P[len(P) // 2], P[-1]
    A = np.array([[b[0] - a[0], b[1] - a[1]], [c[0] - a[0], c[1] - a[1]]])
    cen = np.linalg.solve(A, 0.5 * np.array([b @ b - a @ a, c @ c - a @ a]))
    r_ = np.linalg.norm(a - cen)
    assert r_ == pytest.approx(102 / math.cos(math.radians(4.5)), rel=0.01)
    assert max(abs(np.linalg.norm(p - cen) - r_) for p in P) < 1e-3


def test_quote_di_battuta_a_passo_costante():
    s, _ = piegata()
    f = s._fold_selection('SM1', 'PL1')
    c = f['colpi']
    assert len(c) == 10
    passi = np.diff(c)
    assert np.allclose(passi, math.radians(9) * (100 + 0.4 * 2), atol=0.011)       # quote al centesimo


def test_troppi_colpi_o_raggio_troppo_grande():
    _, r = piegata(colpi=15, raggio=200, y=150)
    assert not r['ok'] and 'meno colpi' in r['message']
    _, r = piegata(colpi=6, raggio=1)                       # raggio più piccolo di quello del punzone
    assert not r['ok'] and 'punzone' in r['message']
    _, r = piegata(colpi='abc')
    assert not r['ok'] and 'Errore interno' not in r['message']


def test_modifica_e_flangia_sulla_punta(tmp_path):
    s, _ = piegata()
    assert s.add_flange('SM1', None, {'length': '30'}, 'PL1')['ok']
    assert s.edit_fold('SM1', 'PL1', {'bump': {'colpi': 6, 'raggio': 80}})['ok']
    assert len(s.result.body.sheet.flanges) == 7                    # 6 colpi + la flangia sulla punta
    assert s.edit_fold('SM1', 'PL1', {'bump': None})['ok']           # torna una piega normale
    assert len(s.result.body.sheet.flanges) == 2
    s.undo()
    assert len(s.result.body.sheet.flanges) == 7
    assert s.save(str(tmp_path / 'b.steelcad'))['ok']
    s2 = Service()
    assert s2.open(str(tmp_path / 'b.steelcad'))['ok'] and not s2.state()['errors']
    assert s.export_dxf(str(tmp_path / 'b.dxf'))['ok']
