"""Coni e raccordi quadro-tondo: sviluppi controllati con conti indipendenti dal codice del motore."""
import math
import os
from types import SimpleNamespace

import build123d as bd
import pytest

from app.service import Service
from cad_engine.sheetmetal import shapes as F

CTX = SimpleNamespace(params={})


def _area3d(S):
    tot = 0.0
    for f in S.facce:
        p = [S.punti[i] for i in f]
        for k in range(1, len(p) - 1):         # ventaglio di triangoli dal primo vertice
            u = [p[k][j] - p[0][j] for j in range(3)]
            v = [p[k + 1][j] - p[0][j] for j in range(3)]
            c = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            tot += math.sqrt(sum(x * x for x in c)) / 2
    return tot


def test_tronco_calandrato_come_a_mano():
    """Ø400/Ø200 esterni, h 300, sp. 2: asse lamiera spostato di t/(2·cos α) in pianta; corona esatta."""
    ns = F.build_shape({'id': 'FM1', 'kind': 'cone', 'd1': 400, 'd2': 200, 'height': 300, 'thickness': 2,
                        'ref': 'esterno', 'mode': 'rolled'}, CTX)
    a = math.atan2(100, 300)
    rg, rp = 200 - 1 / math.cos(a), 100 - 1 / math.cos(a)
    s = math.hypot(300, rg - rp)
    Lg = rg * s / (rg - rp)
    info = ns.sheet.shape_info
    assert info['raggio_grande'] == pytest.approx(Lg, abs=1e-9)
    assert info['raggio_piccolo'] == pytest.approx(Lg - s, abs=1e-9)
    assert info['angolo_settore'] == pytest.approx(math.degrees(2 * math.pi * rg / Lg), abs=1e-9)
    assert ns.sheet.flat.area == pytest.approx(math.radians(info['angolo_settore']) / 2 * (Lg ** 2 - (Lg - s) ** 2), rel=1e-6)
    bb = bd.Shape.cast(ns.shape).bounding_box().size
    assert (bb.X, bb.Z) == pytest.approx((400, 300), abs=0.3)         # misure finite esterne


@pytest.mark.parametrize('fdef', [
    {'kind': 'cone', 'd1': 400, 'd2': 200, 'height': 300},
    {'kind': 'cone', 'd1': 300, 'd2': 0, 'height': 200},
    {'kind': 'transition', 'a': 600, 'b': 400, 'd': 250, 'height': 300},
    {'kind': 'transition', 'a': 500, 'b': 500, 'd': 300, 'height': 350, 'ex': 60, 'ey': -40},
])
def test_sviluppo_a_facce_e_isometrico(fdef):
    """Senza correzione di piega lo sviluppo è la superficie 'aperta': stessa area delle facce 3D e ogni faccia
    ribaltata con i suoi lati veri."""
    ns = F.build_shape({'id': 'FM1', 'thickness': 2, **fdef}, CTX)
    if fdef['kind'] == 'cone':
        S, _ = F.cono_facce(fdef['d1'], fdef['d2'], fdef['height'], 2, 'esterno',
                            max(12, math.ceil(2 * math.pi * fdef['d1'] / 2 / F._passo_auto(fdef['d1'] / 2))))
    else:
        r = fdef['d'] / 2
        n = max(3, math.ceil((math.pi * r / 2) / F._passo_auto(r)))
        S, _ = F.raccordo_facce(fdef['a'], fdef['b'], fdef['d'], fdef['height'], 2, fdef.get('ex', 0), fdef.get('ey', 0),
                                'esterno', 'esterno', n)
    assert ns.sheet.flat.area == pytest.approx(_area3d(S), rel=1e-8)
    piani, _ = F.sviluppa(S)
    for f, poly in zip(S.facce, piani):
        for i in range(len(f)):
            a3, b3 = S.punti[f[i]], S.punti[f[(i + 1) % len(f)]]
            assert math.dist(poly[i], poly[(i + 1) % len(f)]) == pytest.approx(math.dist(a3, b3), abs=1e-9)


def test_correzione_di_piega_nello_sviluppo():
    """Con raggio e K lo sviluppo cambia della correzione di ogni piega: Δ = θ(r + K·t) − 2(r + t/2)·tan(θ/2)."""
    base = {'id': 'FM1', 'kind': 'transition', 'a': 600, 'b': 400, 'd': 250, 'height': 300, 'thickness': 2}
    senza = F.build_shape(base, CTX).sheet
    con = F.build_shape({**base, 'radius': 1, 'k': 0.21}, CTX).sheet
    righe = con.bend_rows
    for r in righe:
        th = math.radians(r['angle'])
        assert r['correction'] == pytest.approx(th * (1 + 0.21 * 2) - 2 * (1 + 1) * math.tan(th / 2), abs=1e-12)
    atteso = sum(r['correction'] * r['length'] for r in righe)       # una striscia larga Δ per piega
    assert con.flat.area - senza.flat.area == pytest.approx(atteso, rel=0.02)
    assert con.shape_info['correzione_totale'] == pytest.approx(sum(r['correction'] for r in righe))
    assert all(0 < r['angle'] < 20 for r in righe)


def test_dal_servizio_con_dxf_tabella_tavole(tmp_path):
    os.environ['STEELCAD_RULES'] = str(tmp_path / 'r.json')
    s = Service()
    s.set_bend_default({'radius': 1, 'method': 'k', 'k': 0.21})
    for kind, vals in (('cono', {}), ('cono', {'modo': 'rolled'}), ('tramoggia', {'ex': 50, 'ey': -30})):
        r = s.new_project(kind, vals)
        assert r['ok'] and not r['state']['errors']
        sm = r['state']['sheet']
        assert sm['shape'] and not sm['missing']
        assert s.export_dxf(str(tmp_path / f'{kind}.dxf'))['ok']
        assert s.export_bend_table(str(tmp_path / f'{kind}.csv'))['ok']
        assert s.export_drawings(str(tmp_path / f'{kind}.pdf'), {'formato': 'A3'})['ok']
    sel = s.select('body')['selection']
    r = s.structure_template_apply(sel['tpl_id'], {'D': 300, 'H': 400})
    assert r['ok'] and next(p for p in r['state']['parameters'] if p['name'] == 'D')['value'] == 300
    assert s.undo()['ok']


@pytest.mark.parametrize('a, b, d, h, t, ex, ey, n', [
    (800, 500, 250, 300, 1.5, 0, 0, 8), (800, 500, 250, 400, 1.5, 0, 60, 8), (600, 400, 200, 300, 5, 80, 40, 6),
    (600, 400, 250, 300, 2, 0, 0, 12),
])
def test_spessore_del_raccordo_agli_angoli(a, b, d, h, t, ex, ey, n):
    """Sugli angoli della base arriva tutto il ventaglio: il solido deve avere il peso giusto (area in asse ×
    spessore) e non sporgere oltre le misure esterne. Prima o l'angolo usciva di 2 mm (cappa da 800 → 802,4)
    o le facce si assottigliavano (−5% di peso)."""
    S, _ = F.raccordo_facce(a, b, d, h, t, ex, ey, 'esterno', 'esterno', n)
    so = F._solido(S, t)
    assert so.volume == pytest.approx(_area3d(S) * t, rel=1e-3)
    bb = so.bounding_box().size
    assert bb.X <= a + 1e-6 and bb.Y <= b + 1e-6
    assert bb.X >= a - 2 and bb.Y >= b - 2
