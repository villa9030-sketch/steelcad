"""STEP con pieghe una dopo l'altra senza tratto piano (colpi fitti, raggi diversi di fila, S): si spiegano una per
una (22/10). I pezzi si fanno qui: una sezione (lato interno + lato esterno) tirata per 100 mm."""
import math

import build123d as bd
import pytest

from app.service import Service
from cad_engine.importers.step_lamiera import spiega

T, K, W, L0, L1 = 2.0, 0.33, 100.0, 50.0, 40.0


def _pezzo(archi):
    """archi: [(R interno, gradi)] uno dopo l'altro (gradi < 0: dall'altra parte), ('L', mm) per un tratto dritto."""
    def lato(off):
        p, d, eds = bd.Vector(0, -off, 0), bd.Vector(1, 0, 0), []
        eds.append(bd.Edge.make_line(p, p + d * L0))
        p = p + d * L0
        for R, g in archi:
            if R == 'L':
                eds.append(bd.Edge.make_line(p, p + d * g))
                p = p + d * g
                continue
            nrm = bd.Vector(-d.Y, d.X, 0)
            if g > 0:
                c = p + nrm * (R + off)
                a0 = math.degrees(math.atan2(p.Y - c.Y, p.X - c.X))
                e = bd.Edge.make_circle(R + off, bd.Plane(origin=c), start_angle=a0, end_angle=a0 + g)
                p = e.position_at(1)
            else:
                c = p - nrm * (R - off)
                a0 = math.degrees(math.atan2(p.Y - c.Y, p.X - c.X))
                e = bd.Edge.make_circle(R - off, bd.Plane(origin=c), start_angle=a0 + g, end_angle=a0)
                p = e.position_at(0)
            eds.append(e)
            th = math.radians(g)
            d = bd.Vector(d.X * math.cos(th) - d.Y * math.sin(th), d.X * math.sin(th) + d.Y * math.cos(th), 0)
        eds.append(bd.Edge.make_line(p, p + d * L1))
        return eds
    a, b = lato(0), lato(T)
    w = bd.Wire(a + [bd.Edge.make_line(a[-1].position_at(1), b[-1].position_at(1))] + list(reversed(b))
                + [bd.Edge.make_line(b[0].position_at(0), a[0].position_at(0))])
    return bd.extrude(bd.Face(w), amount=W)


def _atteso(archi):
    return L0 + L1 + sum(g if R == 'L' else math.radians(abs(g)) * ((R if g > 0 else R - T) + K * T) for R, g in archi)


@pytest.mark.parametrize('archi, n', [
    ([(5, 45), (20, 45)], 2),                          # due raggi di fila
    ([(5, 30), (30, 30), (10, 30)], 3),                # tre
    ([(8, 30), (8, 60)], 1),                           # la stessa piega spezzata in due facce: una piega sola
    ([(3, 15), ('L', 4)] * 5 + [(3, 15)], 6),          # colpi fitti con un tratto corto in mezzo
    ([(5, 45), (20, -45)], 2),                         # S senza tratto piano
])
def test_sviluppo_delle_catene(archi, n):
    r = spiega(_pezzo(archi), k=K)
    bb = r['flat'].bounding_box()
    lungo = next(x for x in (bb.size.X, bb.size.Y) if abs(x - W) > 1e-6)
    assert abs(lungo - _atteso(archi)) < 1e-3
    assert len(r['pieghe']) == n


def test_s_dallo_step_con_versi(tmp_path):
    p = tmp_path / 's.step'
    bd.export_step(_pezzo([(4, 60), (6, -60)]), str(p))
    s = Service()
    r = s.import_step(str(p), K)
    assert r['ok'], r.get('message')
    righe = s.result.body.sheet.bend_rows
    assert [x['verso'] for x in righe] in (['su', 'giù'], ['giù', 'su'])
    assert any('senza tratto piano' in a for a in s.result.body.sheet.warnings)
    assert abs(s.result.body.sheet.flat_size[0] - _atteso([(4, 60), (6, -60)])) < 1e-3 or \
        abs(s.result.body.sheet.flat_size[1] - _atteso([(4, 60), (6, -60)])) < 1e-3
