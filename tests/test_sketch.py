import math

import pytest

from cad_engine.errors import ExpressionError, SketchError
from cad_engine.expressions import evaluate, names_in
from cad_engine.sketch import Sketch, solve
from cad_engine.sketch import profile


def rect(w=300, h=200):
    sk = Sketch('S1')
    r = sk.rectangle(0, 0, w * 0.9, h * 1.1)
    sk.constrain('coincident', r['corners'][0], 'O')
    return sk, r


def test_stati_e_messaggi():
    sk, r = rect()
    st = solve(sk).status
    assert (st.state, st.dof) == ('parziale', 2)
    assert st.message == 'Lo sketch ha ancora 2 gradi di libertà: mancano quote o vincoli.'
    sk.dimension('length', r['bottom'], value=300)
    assert solve(sk).status.message == 'Lo sketch ha ancora 1 grado di libertà: mancano quote o vincoli.'
    sk.dimension('length', r['left'], value=200)
    assert solve(sk).status.state == 'completo'


def test_quota_in_conflitto_detta_chiaramente():
    sk, r = rect()
    sk.dimension('length', r['bottom'], value=300)
    sk.dimension('length', r['left'], value=200)
    d3 = sk.dimension('length', r['top'], value=350)
    st = solve(sk).status
    assert st.state == 'sovra-vincolato'
    assert d3 in st.conflicting
    assert st.message.startswith('La quota 350 (lunghezza di lato sopra) è in conflitto con la quota 300 '
                                 '(lunghezza di lato sotto)')


def test_quota_superflua():
    sk, r = rect()
    sk.dimension('length', r['bottom'], value=300)
    sk.dimension('length', r['left'], value=200)
    d3 = sk.dimension('length', r['top'], value=300)
    st = solve(sk).status
    assert st.state == 'ridondante' and st.redundant == [d3]
    assert 'non serve' in st.message


def test_asola_vincolata_senza_falsi_ridondanti():
    sk = Sketch('S1')
    s = sk.slot((0, 0), (100, 0), 10)
    st = solve(sk).status
    assert st.state == 'parziale' and st.dof == 5 and not st.redundant
    sk.constrain('coincident', s['centers'][0], 'O')
    sk.constrain('horizontal', s['centers'][0], s['centers'][1])
    sk.dimension('distance', s['centers'][0], s['centers'][1], value=80)
    sk.dimension('radius', s['arcs'][0], value=6)
    ss = solve(sk)
    assert ss.status.state == 'completo'
    f = profile.build(ss, profile.PLANES['XY']).faces[0]
    assert f.area == pytest.approx(80 * 12 + math.pi * 36, rel=1e-9)


def test_quote_orizzontale_verticale_angolo():
    sk = Sketch('S1')
    p = sk.point(10, 10)
    l1 = sk.line('O', (100, 5))
    l2 = sk.line('O', p)
    sk.constrain('horizontal', l1)
    sk.dimension('length', l1, value=100)
    sk.dimension('hdistance', 'O', p, value=40)
    sk.dimension('vdistance', 'O', p, value=30)
    ss = solve(sk)
    assert ss.points[p] == pytest.approx((40, 30), abs=1e-9)
    sk2 = Sketch('S2')
    a = sk2.line('O', (100, 2))
    b = sk2.line('O', (50, 60))
    sk2.constrain('horizontal', a)
    sk2.dimension('angle', a, b, value=60)
    sk2.dimension('length', b, value=50)
    ss2 = solve(sk2)
    x, y = ss2.points[sk2.entities[b]['b']]
    assert math.degrees(math.atan2(y, x)) == pytest.approx(60, abs=1e-6)


def test_tangente_concentrico_uguale_parallelo_perpendicolare():
    sk = Sketch('S1')
    c1 = sk.circle((0, 0), 10)
    c2 = sk.circle((1, 1), 20)
    sk.constrain('concentric', c1, c2)
    sk.constrain('fix', sk.entities[c1]['center'])
    ss = solve(sk)
    assert ss.points[sk.entities[c2]['center']] == pytest.approx(ss.points[sk.entities[c1]['center']], abs=1e-9)
    l1 = sk.line((0, 30), (100, 32))
    l2 = sk.line((0, 50), (100, 60))
    l3 = sk.line((0, 70), (5, 120))
    sk.constrain('parallel', l1, l2)
    sk.constrain('perpendicular', l1, l3)
    sk.constrain('equal', l1, l2)
    t = sk.line((-30, -20), (30, -21))
    sk.constrain('tangent', t, c2)
    ss = solve(sk)
    assert ss.status.state in ('parziale', 'completo')
    (ax, ay), (bx, by) = (ss.points[x] for x in ss.lines[l1])
    (cx, cy), (dx, dy) = (ss.points[x] for x in ss.lines[l2])
    assert (bx - ax) * (dy - cy) - (by - ay) * (dx - cx) == pytest.approx(0, abs=1e-6)
    (ex, ey), (fx, fy) = (ss.points[x] for x in ss.lines[t])
    cx0, cy0 = ss.points[sk.entities[c2]['center']]
    dist = abs((fx - ex) * (ey - cy0) - (ex - cx0) * (fy - ey)) / math.hypot(fx - ex, fy - ey)
    assert dist == pytest.approx(ss.circles[c2][1], abs=1e-6)


def test_valori_con_parametri_ed_espressioni():
    sk, r = rect()
    sk.dimension('length', r['bottom'], value='larghezza')
    sk.dimension('length', r['left'], value='larghezza / 2 - 10')
    ss = solve(sk, {'larghezza': 300})
    assert ss.points[r['corners'][2]] == pytest.approx((300, 140), abs=1e-9)
    assert names_in('larghezza / 2 - 10') == {'larghezza'}
    assert evaluate('2,5 * 4', {}) == 10
    with pytest.raises(ExpressionError, match='non esiste'):
        evaluate('altezza', {})
    with pytest.raises(ExpressionError):
        evaluate('__import__("os")', {})


def test_quota_zero_o_negativa():
    sk, r = rect()
    sk.dimension('length', r['bottom'], value=0)
    with pytest.raises(SketchError, match='maggiore di zero'):
        solve(sk)


def test_quote_impossibili():
    sk = Sketch('S1')
    c = sk.circle('O', 10)
    p = sk.point(5, 0)
    sk.constrain('fix', p)
    sk.dimension('diameter', c, value=20)
    sk.constrain('coincident', p, sk.entities[c]['center'])    # il centro è l'origine (fissa), p è fisso in (5,0)
    st = solve(sk).status
    assert st.state in ('sovra-vincolato', 'non risolto')


def test_profilo_aperto_e_ambiguo():
    sk = Sketch('S1')
    sk.polyline([(0, 0), (100, 0), (100, 50)])
    ss = solve(sk)
    with pytest.raises(SketchError, match='non è chiuso'):
        profile.build(ss, profile.PLANES['XY'])
    sk2 = Sketch('S2')
    sk2.polyline([(0, 0), (100, 0), (100, 50), (0, 50)], closed=True)
    sk2.line(sk2.entities['L1']['a'], (50, -40))
    sk2.line((50, -40), sk2.entities['L1']['b'])
    with pytest.raises(SketchError, match='si incontrano 3 linee'):
        profile.build(solve(sk2), profile.PLANES['XY'])


def test_fori_e_isole():
    sk = Sketch('S1')
    sk.polyline([(0, 0), (100, 0), (100, 100), (0, 100)], closed=True)
    sk.polyline([(20, 20), (80, 20), (80, 80), (20, 80)], closed=True)
    sk.circle((50, 50), 10)
    faces = profile.build(solve(sk), profile.PLANES['XY']).faces
    aree = sorted(f.area for f in faces)
    assert aree == pytest.approx(sorted([100 * 100 - 60 * 60, math.pi * 100]), rel=1e-9)


def test_linee_di_costruzione_escluse():
    sk = Sketch('S1')
    sk.polyline([(0, 0), (100, 0), (100, 100), (0, 100)], closed=True)
    sk.line((0, 0), (100, 100), construction=True)
    faces = profile.build(solve(sk), profile.PLANES['XY']).faces
    assert len(faces) == 1 and faces[0].area == pytest.approx(10000)


def test_json_e_coordinate_non_modificate():
    sk, r = rect()
    sk.dimension('length', r['bottom'], value=300)
    prima = sk.to_dict()
    solve(sk)
    assert sk.to_dict() == prima                  # il risolutore non scrive nella definizione
    assert Sketch.from_dict(prima).to_dict() == prima


def test_piani():
    for nome, normale in (('XY', (0, 0, 1)), ('XZ', (0, -1, 0)), ('YZ', (1, 0, 0))):
        sk = Sketch('S1', plane=nome)
        sk.polyline([(0, 0), (10, 0), (10, 10), (0, 10)], closed=True)
        f = profile.build(solve(sk), profile.PLANES[nome]).faces[0]
        n = f.normal_at()
        assert (n.X, n.Y, n.Z) == pytest.approx(normale, abs=1e-9)
    with pytest.raises(SketchError):
        Sketch.from_dict({'id': 'S9', 'plane': 'AB'})
