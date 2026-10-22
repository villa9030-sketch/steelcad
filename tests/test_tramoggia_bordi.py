"""Tramoggia con cassone: bordo in alto e flangia allo scarico anche verso dentro (angoli dritti con lo scasso o a
45°), e si disegna sulle facce: il taglio va nel 3D e al suo posto nello sviluppo (22/10)."""
import math

import build123d as bd
import pytest

import cad_engine.sheetmetal.shapes as SH
from app.service import Service

BASE = {'name': 'T', 'A': 1000, 'B': 800, 'Hc': 500, 'a': 250, 'b': 300, 'Ht': 600, 'ex': 80, 'spessore': 3,
        'bordo': 60, 'raggio': 3, 'k': 0.4}


def _tramoggia(**extra):
    s = Service()
    r = s.new_project('tramoggia_cassone', {**BASE, **extra})
    assert r['ok'], r.get('message')
    return s


@pytest.mark.parametrize('extra', [{}, {'verso_bordo': 'dentro'}, {'verso_bordo': 'dentro', 'angoli_bordo': '45'},
                                   {'flangia': 30, 'verso_flangia': 'dentro'}])
def test_bordi_e_volume(extra):
    s = _tramoggia(**extra)
    d = s.result.body.sheet
    vol = bd.Shape.cast(s.result.body.shape).volume
    assert abs(vol - d.flat_area * 3) < 0.01 * vol                     # il solido torna con lo sviluppo
    assert not d.warnings


def test_bordo_dentro_va_dentro():
    fuori, dentro = _tramoggia(), _tramoggia(verso_bordo='dentro')
    bb = lambda s: bd.Shape.cast(s.result.body.shape).bounding_box()   # noqa: E731
    assert bb(fuori).size.X > 1000 + 100 and abs(bb(dentro).size.X - 1000) < 1


def test_bordo_dentro_troppo_largo():
    s = Service()
    r = s.new_project('tramoggia_cassone', {**BASE, 'bordo': 450, 'verso_bordo': 'dentro'})
    assert not r['ok']


def test_facce_al_posto_giusto_nello_sviluppo(monkeypatch):
    preso = {}
    vero = SH._nomi_sezioni

    def spia(fid, shape, mappe, t, rif):
        preso['mappe'] = mappe
        return vero(fid, shape, mappe, t, rif)
    monkeypatch.setattr(SH, '_nomi_sezioni', spia)
    s = _tramoggia(verso_bordo='dentro')
    pan = s.result.body.sheet.pannelli
    peggio = 0.0
    for m in preso['mappe']:
        for lato in ('fuori', 'dentro'):
            nome = f"FM1/{m['nome'].replace(' ', '_')}/{lato}"
            if lato == 'fuori':
                assert nome in pan, nome
            if nome not in pan:
                continue
            src, dst, _ = pan[nome]
            n = bd.Vector(*m['normale'])
            for P, q in zip(m['pts3'], m['pts2']):
                P = bd.Vector(*P)
                P = P + n * (src.origin - P).dot(n)                    # sul piano della faccia
                w = dst.from_local_coords(src.to_local_coords(P))
                peggio = max(peggio, math.hypot(w.X - q[0], w.Y - q[1]), abs(w.Z))
    assert peggio < 0.1                                                # mm
    assert s.doc.describe_face('FM1/cassone_davanti/fuori') == 'cassone davanti, faccia esterna'


@pytest.mark.parametrize('faccia', ['FM1/cassone_davanti/fuori', 'FM1/tramoggia_destra/fuori', 'FM1/cassone_dietro/dentro'])
def test_foro_su_una_faccia(faccia):
    s = _tramoggia(verso_bordo='dentro')
    d0 = s.result.body.sheet
    sk = s.sketch_on_face(faccia)
    assert sk['ok'], sk.get('message')
    c = bd.Face(s.result.body.names[faccia][0]).center()
    loc = s.doc._plane(s.doc.sketch(sk['sketch']), s.result.body).to_local_coords(c)
    assert s.sketch_add_circle(sk['sketch'], [loc.X, loc.Y], 30)['ok']
    r = s.create_from_sketch(sk['sketch'], 'cut', {})
    assert r['ok'], r.get('message')
    d = s.result.body.sheet
    assert abs((d0.flat_area - d.flat_area) - math.pi * 900) < 1
    assert sum(1 for e in d.flat.edges() if e.geom_type == bd.GeomType.CIRCLE) == 1
