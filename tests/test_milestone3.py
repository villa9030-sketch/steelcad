"""GATE Milestone 3 — lamiera: rettangolo → sp. 2 → flangia 30 a 90° → seconda flangia → fori →
sviluppo → DXF. I numeri attesi sono calcolati qui a mano con le formule, non col codice del motore."""
import math

import build123d as bd
import pytest

from cad_engine import Document, History
from cad_engine.exporters import dxf, step
from cad_engine.sheetmetal import bend_values

T, R, K = 2.0, 2.0, 0.4          # dati di piega del pezzo di riferimento (scelti per il test, non default)


def ba(theta, r=R, t=T, k=K):
    return math.radians(theta) * (r + k * t)


def ossb(theta, r=R, t=T):
    return (r + t) * math.tan(math.radians(theta) / 2)


def u_part(W=500, P=300, k=K, foro_base=True, foro_flangia=True):
    doc = Document('Canalina U', 'S235')
    hist = History(doc)
    with hist.change('Parametri'):
        doc.set_parameter('W', W)
        doc.set_parameter('P', P)
    with hist.change('Rettangolo'):
        sk = doc.add_sketch('XY', 'Base')
        r = sk.rectangle(0, 0, 480, 290)
        sk.constrain('coincident', r['corners'][0], 'O')
        sk.dimension('length', r['bottom'], value='W')
        sk.dimension('length', r['left'], value='P')
    with hist.change('Lamiera sp. 2'):
        fid = doc.add_feature('sheet', 'Canalina', sketch=sk.id, thickness=T, radius=R, method='k', k=k, flanges=[])
    sm = doc.feature(fid)
    with hist.change('Flangia 30 a 90°'):
        sm['flanges'].append({'id': 'FL1', 'edge': r['bottom'], 'length': 30, 'angle': 90})
    with hist.change('Seconda flangia'):
        sm['flanges'].append({'id': 'FL2', 'edge': r['top'], 'length': 30, 'angle': 90})
    with hist.change('Fori'):
        if foro_base:
            c = sk.circle((250, 150), 10)
            sk.dimension('diameter', c, value=20)
            sk.constrain('symmetric', r['corners'][0], r['corners'][2], sk.entities[c]['center'])
        if foro_flangia:
            sm['flanges'][0]['holes'] = [{'u': 100, 'v': 18, 'd': 8}]
    return doc, hist


def test_gate_milestone_3(tmp_path):
    doc, hist = u_part()
    res = doc.rebuild()
    assert res.ok, [f.message for f in res.errors]
    sh = res.body.sheet
    # --- sviluppo, a mano: 300 + 2 · (30 − BD), BD = 2·(r+t) − π/2·(r + K t)
    BD = 2 * ossb(90) - ba(90)
    assert BD == pytest.approx(3.6017702849742896, abs=1e-12)
    assert sh.flat_size[0] == pytest.approx(500, abs=1e-6)
    assert sh.flat_size[1] == pytest.approx(300 + 2 * (30 - BD), abs=1e-6)      # 352,796
    # --- solido: ingombro e volume a mano
    s = bd.Solid(res.body.shape)
    assert s.is_valid
    bb = s.bounding_box().size
    assert (bb.X, bb.Y, bb.Z) == pytest.approx((500, 300, 30), abs=1e-6)
    piano = 500 * (300 - 2 * ossb(90)) * T
    pieghe = 2 * (math.pi / 4) * ((R + T) ** 2 - R ** 2) * 500
    dritti = 2 * (30 - ossb(90)) * T * 500
    fori = math.pi * 10 ** 2 * T + math.pi * 4 ** 2 * T
    assert s.volume == pytest.approx(piano + pieghe + dritti - fori, rel=1e-9)
    # --- DXF: contorno + foro della base + foro della flangia, 2 pieghe, controlli
    rep = dxf.export_flat_pattern(sh, tmp_path / 'u.dxf')
    assert rep['problems'] == []
    assert rep['contours'] == 3 and rep['circles'] == 2
    assert rep['circle_diameters'] == [8, 20]
    assert rep['bend_lines'] == rep['bend_lines_found'] == 2
    assert rep['size_mm'] == pytest.approx([500, 300 + 2 * (30 - BD)], abs=1e-6)
    # il foro della flangia nello sviluppo: dal bordo del piano a v − BD/… → v + BA − 2·setback dal contorno
    st = step.export(res.body.shape, tmp_path / 'u.step')
    assert st['volume_mm3'] == pytest.approx(s.volume, rel=1e-9)
    # --- modifica: W 500 → 600, tutto si rigenera
    with hist.change('W 600'):
        doc.set_parameter('W', 600)
    res = doc.rebuild()
    assert res.ok
    assert res.body.sheet.flat_size[0] == pytest.approx(600, abs=1e-6)
    assert bd.Solid(res.body.shape).bounding_box().size.X == pytest.approx(600, abs=1e-6)
    hist.undo()
    assert doc.rebuild().body.sheet.flat_size[0] == pytest.approx(500, abs=1e-6)


def test_verifica_incrociata_volume_sviluppo():
    """Con K = 0,5 la fibra neutra sta a metà spessore: area dello sviluppo × spessore = volume 3D, esatto."""
    doc, _ = u_part(k=0.5)
    res = doc.rebuild()
    assert res.body.sheet.flat_area * T == pytest.approx(bd.Solid(res.body.shape).volume, rel=1e-9)


def test_posizione_foro_flangia_nello_sviluppo(tmp_path):
    doc, _ = u_part(foro_base=False)
    sh = doc.rebuild().body.sheet
    # FL1 sul lato sotto (y = 0): nello sviluppo la flangia va verso y negative.
    # foro a v = 18 dallo spigolo esterno → nello sviluppo a 18 − BD dalla linea del contorno
    BD = 2 * ossb(90) - ba(90)
    centri = [e.arc_center for e in sh.flat.edges() if e.geom_type == bd.GeomType.CIRCLE]
    assert len(centri) == 1
    y_min = min(sh.plane.to_local_coords(v).Y for v in sh.flat.vertices())
    c = sh.plane.to_local_coords(centri[0])
    assert c.Y == pytest.approx(-(18 - BD), abs=1e-9)
    assert y_min == pytest.approx(-(30 - BD), abs=1e-9)


@pytest.mark.parametrize('angolo', [30, 45, 60, 90, 120, 135])
def test_formule_piega(angolo):
    b = bend_values(angolo, R, T, 'k', K)
    assert b.ba == pytest.approx(ba(angolo), abs=1e-12)
    assert b.ossb == pytest.approx(ossb(angolo), abs=1e-12)
    assert b.bd == pytest.approx(2 * ossb(angolo) - ba(angolo), abs=1e-12)


def test_din_6935_e_deduzione():
    # DIN 6935: k = 0,65 + 0,5·log10(r/s) per r/s < 5 → per r = s: k = 0,65, K-factor = k/2
    assert bend_values(90, 2, 2, 'din6935').k == pytest.approx(0.325)
    assert bend_values(90, 12, 2, 'din6935').k == pytest.approx(0.5)     # r/s ≥ 5 → k = 1
    b = bend_values(90, 2, 2, 'bd90', bd90=3.6)
    assert b.bd == pytest.approx(3.6)
    from cad_engine.errors import FeatureError
    with pytest.raises(FeatureError, match='solo per pieghe a 90'):
        bend_values(60, 2, 2, 'bd90', bd90=3.6)


def test_dati_mancanti_non_si_inventano():
    from cad_engine.errors import FeatureError
    with pytest.raises(FeatureError, match='Manca il K-factor'):
        bend_values(90, 2, 2, 'k', None)
    doc = Document('X', 'S235')
    sk = doc.add_sketch('XY', 'B')
    r = sk.rectangle(0, 0, 100, 100)
    doc.add_feature('sheet', 'X', sketch=sk.id, thickness=2, radius=None, method='k', k=0.4,
                    flanges=[{'id': 'FL1', 'edge': r['bottom'], 'length': 20}])
    res = doc.rebuild()
    assert not res.ok and 'raggio interno' in res.errors[0].message


def test_vasca_quattro_flange_e_flange_giu():
    for flanges in (
        [{'id': f'FL{i}', 'edge': e, 'length': 40} for i, e in enumerate(('L1', 'L2', 'L3', 'L4'), 1)],
        [{'id': 'FL1', 'edge': 'L1', 'length': 40, 'direction': 'down'}, {'id': 'FL2', 'edge': 'L3', 'length': 40}],
        [{'id': 'FL1', 'edge': 'L1', 'length': 40, 'position': 'outside'},
         {'id': 'FL2', 'edge': 'L2', 'length': 40, 'position': 'outside'}],
    ):
        doc = Document('X', 'S235')
        sk = doc.add_sketch('XY', 'B')
        r = sk.rectangle(0, 0, 400, 300)
        sk.constrain('coincident', r['corners'][0], 'O')
        sk.dimension('length', r['bottom'], value=400)
        sk.dimension('length', r['left'], value=300)
        doc.add_feature('sheet', 'X', sketch=sk.id, thickness=2, radius=2, method='k', k=0.5, flanges=flanges)
        res = doc.rebuild()
        assert res.ok, res.errors[0].message
        s = bd.Solid(res.body.shape)
        assert s.is_valid
        assert res.body.sheet.flat_area * 2 == pytest.approx(s.volume, rel=1e-9)


def test_fori_nella_piega_rifiutati():
    doc, _ = u_part(foro_base=False, foro_flangia=False)
    doc.feature('SM1')['flanges'][0]['holes'] = [{'u': 100, 'v': 5, 'd': 8}]
    res = doc.rebuild()
    assert not res.ok and 'cade nella piega' in res.errors[0].message
