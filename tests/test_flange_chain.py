"""Flange sulla punta di altre flange (omega, scatola bordata, Z, catene) e tagli disegnati sullo sviluppo.
I numeri attesi sono fatti a mano con le formule, come nel gate della Milestone 3."""
import math

import build123d as bd
import pytest

from cad_engine import Document

T, R = 2.0, 2.0


def ba(theta, k, r=R, t=T):
    return math.radians(theta) * (r + k * t)


def ossb(theta, r=R, t=T):
    return (r + t) * math.tan(math.radians(theta) / 2)


def bd90(k):
    return 2 * ossb(90) - ba(90, k)


def pezzo(W, P, flanges, k=0.5, corners=None):
    doc = Document('X', 'S235')
    sk = doc.add_sketch('XY', 'B')
    r = sk.rectangle(0, 0, W, P)
    sk.constrain('coincident', r['corners'][0], 'O')
    sk.dimension('length', r['bottom'], value=W)
    sk.dimension('length', r['left'], value=P)
    doc.add_feature('sheet', 'X', sketch=sk.id, thickness=T, radius=R, method='k', k=k, flanges=flanges,
                    corners=corners or [])
    return doc, r


def omega(k=0.5):
    # base 60 (x) × 300 (y); ali su sinistra e destra alte 40, tese verso fuori da 25: tutte quote esterne
    doc = Document('Omega', 'S235')
    sk = doc.add_sketch('XY', 'B')
    r = sk.rectangle(0, 0, 60, 300)
    sk.constrain('coincident', r['corners'][0], 'O')
    sk.dimension('length', r['bottom'], value=60)
    sk.dimension('length', r['left'], value=300)
    fl = [{'id': 'FL1', 'edge': r['left'], 'length': 40}, {'id': 'FL2', 'edge': r['right'], 'length': 40},
          {'id': 'FL3', 'parent': 'FL1', 'length': 25, 'direction': 'down'},
          {'id': 'FL4', 'parent': 'FL2', 'length': 25, 'direction': 'down'}]
    doc.add_feature('sheet', 'Omega', sketch=sk.id, thickness=T, radius=R, method='k', k=k, flanges=fl)
    return doc


@pytest.mark.parametrize('k', [0.5, 0.4])
def test_omega(k):
    res = omega(k).rebuild()
    assert res.ok, res.errors[0].message
    s = bd.Solid(res.body.shape)
    assert s.is_valid
    bb = s.bounding_box()
    # fuori tutto: 25 + 60 + 25 di larghezza (le tese verso fuori), 40 di altezza, 300 di lunghezza
    assert (bb.size.X, bb.size.Y, bb.size.Z) == pytest.approx((60 + 2 * 25 - 2 * T, 300, 40), abs=1e-6)
    sh = res.body.sheet
    # sviluppo: somma delle quote esterne meno 4 deduzioni... ma le tese misurano dallo spigolo esterno
    # della loro piega, che per una piega "giù" è sulla faccia interna dell'ala: 25 + 40 + 60 + 40 + 25 − 4·BD
    # con l'ala misurata fino allo spigolo esterno della tesa (la quota esterna dell'omega)
    assert sh.flat_size[0] == pytest.approx(25 + 40 + 60 + 40 + 25 - 4 * bd90(k), abs=1e-6)
    assert sh.flat_size[1] == pytest.approx(300, abs=1e-6)
    if k == 0.5:
        assert sh.flat_area * T == pytest.approx(s.volume, rel=1e-9)
    assert len(sh.bend_lines) == 4


def test_scatola_bordata():
    """Vasca 400 × 300 con pareti da 60 e bordo verso dentro da 20 su tutti e quattro i lati: i bordi si
    incontrano negli angoli e si accorciano da soli, senza compenetrarsi."""
    fl = [{'id': f'FL{i}', 'edge': e, 'length': 60} for i, e in enumerate(('L1', 'L2', 'L3', 'L4'), 1)]
    fl += [{'id': f'B{i}', 'parent': f'FL{i}', 'length': 20} for i in range(1, 5)]
    doc, _ = pezzo(400, 300, fl)
    res = doc.rebuild()
    assert res.ok, res.errors[0].message
    s = bd.Solid(res.body.shape)
    assert s.is_valid
    assert s.bounding_box().size.Z == pytest.approx(60, abs=1e-6)
    assert res.body.sheet.flat_area * T == pytest.approx(s.volume, rel=1e-9)
    assert s.is_inside(bd.Vector(200, 10, 59))            # il bordo sopra la parete FL1, verso dentro
    assert not s.is_inside(bd.Vector(200, 25, 59))        # oltre i 20 del bordo
    nomi = res.body.names
    assert any(n.startswith('SM1/B1/') for n in nomi)


def _bordata(modo=None, gap=0):
    fl = [{'id': f'FL{i}', 'edge': e, 'length': 60} for i, e in enumerate(('L1', 'L2', 'L3', 'L4'), 1)]
    fl += [{'id': f'FL{i + 4}', 'parent': f'FL{i}', 'length': 20, 'gap': gap} for i in range(1, 5)]
    doc, _ = pezzo(400, 300, fl)
    if modo:
        doc.feature('SM1')['tip_corners'] = modo
    res = doc.rebuild()
    assert res.ok, res.errors[0].message
    s = bd.Solid(res.body.shape)
    assert s.is_valid
    assert res.body.sheet.flat_area * T == pytest.approx(s.volume, rel=1e-9)      # sviluppo giusto anche agli angoli
    larghe = {b['flange']: b['width'] for b in res.body.sheet.summary()['bends']}
    return res, s, larghe


def test_angoli_bordi_dritti_lati_lunghi_interi():
    res, s, w = _bordata()                    # di default: i lati lunghi passano, i corti si fermano contro
    assert w['FL5'] == pytest.approx(392) and w['FL7'] == pytest.approx(392)
    assert w['FL6'] < 292 - 30 and w['FL8'] < 292 - 30
    assert sorted(map(sorted, res.body.sheet.tip_contacts)) == [['FL5', 'FL6'], ['FL5', 'FL8'], ['FL6', 'FL7'], ['FL7', 'FL8']]


def test_angoli_bordi_dritti_lati_corti_interi():
    _, _, w = _bordata('short')
    assert w['FL6'] == pytest.approx(292) and w['FL8'] == pytest.approx(292)
    assert w['FL5'] < 392 - 30 and w['FL7'] < 392 - 30


def test_angoli_bordi_a_45():
    res, s, w = _bordata('miter')
    assert all(w[f] == pytest.approx(392 if f in ('FL5', 'FL7') else 292) for f in w if f in ('FL5', 'FL6', 'FL7', 'FL8'))
    assert all(len(g.miters) == 2 for g in res.body.sheet.flanges if g.parent)
    # nell'angolo (400, 0) i due bordi si incontrano sulla diagonale x + y = 400
    assert s.is_inside(bd.Vector(385, 10, 59)) and s.is_inside(bd.Vector(395, 10, 59))
    assert s.is_inside(bd.Vector(390, 10, 59))            # proprio sulla diagonale: niente buco


def test_angoli_bordi_a_45_con_fessura():
    res, s, _ = _bordata('miter', gap=1)
    assert not s.is_inside(bd.Vector(390, 10, 59))        # sulla diagonale c'è la fessura da 1 mm
    assert s.is_inside(bd.Vector(388, 10, 59)) and s.is_inside(bd.Vector(392, 10, 59))


def test_foro_sul_bordo_di_una_scatola():
    """I bordi complanari si toccano negli angoli e diventano un'unica faccia sopra (col nome di uno solo):
    un foro disegnato lì va comunque al bordo su cui cade, nel pezzo e nello sviluppo."""
    fl = [{'id': f'FL{i}', 'edge': e, 'length': 60} for i, e in enumerate(('L1', 'L2', 'L3', 'L4'), 1)]
    fl += [{'id': f'FL{i + 4}', 'parent': f'FL{i}', 'length': 20} for i in range(1, 5)]
    doc, _ = pezzo(400, 300, fl)
    res = doc.rebuild()
    nome = next(n for n in res.body.names if n.endswith('/esterno') and n.split('/')[1] in ('FL5', 'FL6', 'FL7', 'FL8'))
    s2 = doc.add_sketch({'face': nome}, 'Foro')
    doc.rebuild()
    pl = doc._sketch_results[s2.id][1].plane
    q = pl.to_local_coords(bd.Vector(200, 290, 60))         # sul bordo di FL3 (FL7), lato y = 300
    s2.circle((q.X, q.Y), 3)
    doc.add_feature('sheet_cut', 'Foro', sketch=s2.id)
    res = doc.rebuild()
    assert res.ok, res.errors[0].message
    s = bd.Solid(res.body.shape)
    assert not s.is_inside(bd.Vector(200, 290, 59))
    assert res.body.sheet.flat_area * T == pytest.approx(s.volume, rel=1e-9)


def test_z_e_catena_di_tre():
    fl = [{'id': 'FL1', 'edge': 'L1', 'length': 50},
          {'id': 'FL2', 'parent': 'FL1', 'length': 30, 'direction': 'down'},        # Z
          {'id': 'FL3', 'parent': 'FL2', 'length': 20, 'angle': 45}]
    doc, _ = pezzo(200, 100, fl)
    res = doc.rebuild()
    assert res.ok, res.errors[0].message
    s = bd.Solid(res.body.shape)
    assert s.is_valid
    assert res.body.sheet.flat_area * T == pytest.approx(s.volume, rel=1e-9)
    assert [b['parent'] for b in res.body.sheet.summary()['bends']] == [None, 'FL1', 'FL2']


def test_flangia_madre_troppo_corta():
    fl = [{'id': 'FL1', 'edge': 'L1', 'length': 7}, {'id': 'FL2', 'parent': 'FL1', 'length': 20}]
    res = pezzo(200, 100, fl)[0].rebuild()
    assert not res.ok and 'troppo corta per piegarci sopra' in res.errors[0].message


def test_madre_mancante():
    fl = [{'id': 'FL2', 'parent': 'FL9', 'length': 20}]
    res = pezzo(200, 100, fl)[0].rebuild()
    assert not res.ok and 'FL9' in res.errors[0].message


# ------------------------------------------------------------------- disegno sullo sviluppo
def _taglio_sviluppo(doc, centro, d=8):
    doc.rebuild()
    s2 = doc.add_sketch({'flat': 'SM1'}, 'Sviluppo')
    s2.circle(centro, d / 2)
    doc.add_feature('sheet_cut', 'Taglio', sketch=s2.id)
    return doc.rebuild()


def test_foro_sullo_sviluppo_sulla_base():
    doc = omega()
    res = _taglio_sviluppo(doc, (30, 150))
    assert res.ok, res.errors[0].message
    s = bd.Solid(res.body.shape)
    assert not s.is_inside(bd.Vector(30, 150, 1))
    assert res.body.sheet.flat_area * T == pytest.approx(s.volume, rel=1e-9)


def test_foro_sullo_sviluppo_su_una_tesa():
    """Un foro sulla tesa di FL1 nello sviluppo finisce sulla tesa vera, a sinistra dell'omega."""
    doc = omega()
    sh = doc.rebuild().body.sheet
    g = next(x for x in sh.flanges if x.fid == 'FL3')
    # a metà del tratto dritto della tesa nello sviluppo
    p = g.fp((g.u0 + g.u1) / 2, g.off + g.bend.ba + g.lf / 2)
    q = sh.plane.to_local_coords(p)
    res = _taglio_sviluppo(doc, (q.X, q.Y), d=6)
    assert res.ok, res.errors[0].message
    s = bd.Solid(res.body.shape)
    assert res.body.sheet.flat_area * T == pytest.approx(s.volume, rel=1e-9)
    # la tesa di sinistra è a z = 40 − sp. (sotto) … 40, x tra −23 e 0
    bb = s.bounding_box()
    vuoto = [bd.Vector(x, 150, 40 - T / 2) for x in (bb.min.X + 1, bb.min.X + 5, bb.min.X + 9)]
    assert not all(s.is_inside(v) for v in vuoto)


def test_sviluppo_taglio_nella_piega_rifiutato():
    doc = omega()
    sh = doc.rebuild().body.sheet
    g = next(x for x in sh.flanges if x.fid == 'FL1')
    q = sh.plane.to_local_coords(g.fp(150, g.off + g.bend.ba / 2))
    res = _taglio_sviluppo(doc, (q.X, q.Y), d=2)
    assert not res.ok and 'piega' in res.errors[0].message


def test_sviluppo_e_faccia_coincidono():
    """Lo stesso foro fatto dallo sviluppo o dalla faccia della flangia dà lo stesso pezzo."""
    fl = [{'id': 'FL1', 'edge': 'L1', 'length': 40}]
    doc_a, _ = pezzo(200, 100, fl)
    sh = doc_a.rebuild().body.sheet
    g = sh.flanges[0]
    q = sh.plane.to_local_coords(g.fp(70, g.off + g.bend.ba + 10))
    ra = _taglio_sviluppo(doc_a, (q.X, q.Y))
    assert ra.ok, ra.errors[0].message
    doc_b, _ = pezzo(200, 100, fl)
    doc_b.rebuild()
    s2 = doc_b.add_sketch({'face': 'SM1/FL1/esterno'}, 'F')
    doc_b.rebuild()
    pl = doc_b._sketch_results[s2.id][1].plane
    # nel 3D: 10 mm oltre l'inizio del tratto dritto, cioè a ossb + 10 dallo spigolo esterno (y = 0)
    x = (g.origin + g.xf * 70).X            # u si misura dall'inizio della flangia (qui da x = 200 indietro)
    c = pl.to_local_coords(bd.Vector(x, 0, ossb(90) + 10))
    s2.circle((c.X, c.Y), 4)
    doc_b.add_feature('sheet_cut', 'T', sketch=s2.id)
    rb = doc_b.rebuild()
    assert rb.ok, rb.errors[0].message
    a, b = bd.Solid(ra.body.shape), bd.Solid(rb.body.shape)
    assert a.volume == pytest.approx(b.volume, rel=1e-9)
    assert (a - b).volume == pytest.approx(0, abs=1e-6)


def _profilo_chiuso(tabs, k=0.5):
    """Profilo chiuso piegato da una base: parete 60, tesa 40 verso fuori, parete 40 giù, ritorno a 45°."""
    fl = [{'id': 'FL1', 'edge': 'L1', 'length': 60},
          {'id': 'FL2', 'parent': 'FL1', 'length': 40, 'direction': 'down', 'end_tabs': tabs},
          {'id': 'FL3', 'parent': 'FL2', 'length': 40, 'direction': 'up'},
          {'id': 'FL4', 'parent': 'FL3', 'length': 40, 'direction': 'up', 'angle': 45}]
    doc, _ = pezzo(200, 100, fl, k=k)
    return doc


def test_aletta_di_chiusura_della_testata():
    """L'aletta piegata dalla tesa chiude il vuoto all'estremità X−, a filo; l'altra estremità resta aperta.
    Con K 0,5 area dello sviluppo × spessore = volume: l'aletta è anche nello sviluppo, giusta."""
    aperto = bd.Solid(_profilo_chiuso([]).rebuild().body.shape)
    res = _profilo_chiuso([{'end': 'u0', 'gap': 0.5}]).rebuild()
    assert res.ok, res.errors[0].message
    s = bd.Solid(res.body.shape)
    assert s.is_valid and s.volume > aperto.volume
    assert s.bounding_box().size.X == pytest.approx(200, abs=1e-6)            # a filo: la lunghezza non cambia
    assert s.is_inside(bd.Vector(1, -20, 40)) and not s.is_inside(bd.Vector(5, -20, 40))
    assert not s.is_inside(bd.Vector(199, -20, 40))                           # l'altra estremità è aperta
    assert res.body.sheet.flat_area * T == pytest.approx(s.volume, rel=1e-9)
    assert any('chiusura' in l[2] for l in res.body.sheet.bend_lines)
    assert any(n.endswith('/chiusura') for n in res.body.names)
    res = _profilo_chiuso([{'end': 'u0', 'gap': 0.5}, {'end': 'u1', 'gap': 0.5}], k=0.4).rebuild()
    assert res.ok, res.errors[0].message                                      # tutte e due le testate, K 0,4
    assert bd.Solid(res.body.shape).is_inside(bd.Vector(199, -20, 40))


def test_aletta_di_chiusura_su_profilo_aperto_rifiutata():
    fl = [{'id': 'FL1', 'edge': 'L1', 'length': 60, 'end_tabs': [{'end': 'u0', 'gap': 0.5}]}]
    res = pezzo(200, 100, fl)[0].rebuild()
    assert not res.ok and 'profilo è aperto' in res.errors[0].message
