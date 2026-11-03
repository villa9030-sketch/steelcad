"""03/11 — comando «Foro» e «Asola» diretti sul pezzo: diametro e dove (al centro, 4 agli angoli, in fila, dove clicco),
con le distanze dal fuori tutto del pezzo anche dal lato della piega. Dietro resta il taglio vero (sketch + taglio)."""
import build123d as bd
import pytest

from app import fori_rapidi
from app.service import Service
from cad_engine import SteelCADError


@pytest.fixture
def staffa():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 200, 'profondita': 100, 'spessore': 3, 'raggio': 1.5, 'k': 0.4})['ok']
    assert s.add_flange('SM1', 'L1', {'length': '60'})['ok']
    return s


def _fori_3d(s):
    """Centri (x, y) dei fori della base, nel 3D, misurati dal fuori tutto del pezzo."""
    corpo = bd.Shape.cast(s.result.body.shape)
    bb = corpo.bounding_box()
    out = []
    for f in corpo.faces():
        fb = f.bounding_box()
        if f.geom_type == bd.GeomType.CYLINDER and abs(fb.size.X - 2 * f.radius) < 1e-3 and abs(fb.size.Y - 2 * f.radius) < 1e-3:
            c = f.bounding_box().center()
            out.append((round(c.X - bb.min.X, 2), round(c.Y - bb.min.Y, 2), round(2 * f.radius, 2)))
    return sorted(set(out)), bb


def test_staffa_quattro_fori_a_20_dai_bordi_del_fuori_tutto(staffa):
    s = staffa
    faccia = s.fori_faccia()
    r = s.fori_guidati(faccia, {'tipo': 'tondo', 'd': '10,5', 'disposizione': 'angoli', 'bordo': 20})
    assert r['ok'] and r['message'] == 'Fatti 4 fori.', r
    fori, bb = _fori_3d(s)
    assert round(bb.size.X) == 200 and round(bb.size.Y) == 100
    assert fori == [(20.0, 20.0, 10.5), (20.0, 80.0, 10.5), (180.0, 20.0, 10.5), (180.0, 80.0, 10.5)]
    # il taglio vero: 4 cerchi sullo sviluppo e nell'albero «Fori 4 × Ø10,5»; un Annulla li toglie tutti
    assert len(s.result.body.sheet.flat.inner_wires()) == 4
    assert 'Fori 4 × Ø10,5' in str(s.state()['tree'])
    s.undo()
    assert not s.result.body.sheet.flat.inner_wires()


def test_asola_30x10_al_centro_della_faccia_piegata(staffa):
    s = staffa
    r = s.fori_guidati('SM1/FL1/esterno', {'tipo': 'asola', 'larg': 30, 'alt': 10, 'disposizione': 'centro'})
    assert r['ok'] and r['message'] == 'Fatta l’asola.', r
    fl = s.result.body.sheet.flat
    ob = fl.outer_wire().bounding_box()
    (w,) = fl.inner_wires()
    b = w.bounding_box()
    assert (round(b.size.X, 3), round(b.size.Y, 3)) == (30, 10)          # misure vere, non l'interasse
    assert round((b.min.X + b.max.X) / 2 - ob.min.X, 3) == 100
    assert round((b.min.Y + b.max.Y) / 2 - ob.min.Y, 3) == 30             # metà dei 60 fuori tutto, dalla punta
    albero = str(s.state()['tree'])
    assert 'Asola 30 × 10' in albero and 'Asola 20 × 10' not in albero


def test_foro_sulla_piega_non_si_fa_e_lo_dice(staffa):
    s = staffa
    n = len(s.doc.features)
    r = s.fori_guidati(s.fori_faccia(), {'tipo': 'tondo', 'd': 10, 'disposizione': 'angoli', 'bordo': 4})
    assert not r['ok'] and 'n. 1' in r['message'] and 'piega' in r['message']
    assert len(s.doc.features) == n                                      # niente sketch lasciato a metà


def test_fila_centrata_a_30_dal_bordo_dietro():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 120, 'spessore': 2, 'raggio': 1, 'k': 0.33})['ok']
    r = s.fori_guidati(s.fori_faccia(), {'tipo': 'tondo', 'd': '10,2', 'disposizione': 'fila', 'n': 6, 'passo': 40,
                                         'verso': 'x', 'lato': 'dietro', 'dal': 30})
    assert r['ok'] and r['message'] == 'Fatti 6 fori.', r
    fori, _ = _fori_3d(s)
    assert [f[0] for f in fori] == [50, 90, 130, 170, 210, 250] and {f[1] for f in fori} == {90}


def test_dove_clicco_e_misure_dal_bordo(staffa):
    s = staffa
    faccia = s.fori_faccia()
    from cad_engine.sketch.face_plane import plane_of
    from cad_engine.sketch import Sketch
    piano = plane_of(s.result.body, faccia, Sketch('_t', plane={'face': faccia}))
    ox, oy, _, _ = s._fuori_tutto(piano, faccia)
    p = piano.from_local_coords((ox + 60.3, oy + 70.2))
    d = s.fori_dove(faccia, [p.X, p.Y, p.Z])
    assert d['ok'] and (d['x'], d['y']) == (60, 70)
    r = s.fori_guidati(faccia, {'tipo': 'tondo', 'd': 8, 'disposizione': 'punti', 'punti': [[d['x'], d['y']], ['150', '50,5']]})
    assert r['ok'], r
    fori, _ = _fori_3d(s)
    assert fori == [(60.0, 70.0, 8.0), (150.0, 50.5, 8.0)]


def test_anteprima_del_foro_dice_cosa_toglie(staffa):
    s = staffa
    a = s.anteprima('fori_guidati', [s.fori_faccia(), {'tipo': 'tondo', 'd': '10,5', 'disposizione': 'angoli', 'bordo': 20}])
    assert a['ok'] and a['frase'] == 'Toglie dal pezzo: 4 fori Ø10,5' and a['togli']
    assert not s.doc.features[-1].__class__.__name__ == 'Sketch'          # la prova non tocca il progetto
    a = s.anteprima('fori_guidati', [s.fori_faccia(), {'tipo': 'asola', 'larg': 10, 'alt': 30, 'disposizione': 'centro'}])
    assert a['ok'] and a['frase'] == 'Toglie dal pezzo: un’asola 10 × 30'


def test_posizioni_come_le_dice_l_officina():
    assert fori_rapidi.posizioni({'disposizione': 'centro'}, 200, 100) == [(100, 50)]
    assert fori_rapidi.posizioni({'disposizione': 'angoli', 'bordo': '15', 'bordo_y': '25'}, 200, 100) == \
        [(15, 25), (185, 25), (15, 75), (185, 75)]
    assert fori_rapidi.posizioni({'disposizione': 'fila', 'n': 3, 'passo': 50, 'verso': 'y'}, 200, 100) == \
        [(100, 0), (100, 50), (100, 100)]
    assert fori_rapidi.posizioni({'disposizione': 'fila', 'n': 2, 'passo': 40, 'verso': 'y', 'lato': 'destra', 'dal': 20}, 200, 100) == \
        [(180, 30), (180, 70)]
    assert fori_rapidi.misure_asola({'larg': 10, 'alt': 30}) == (30, 10, True)
    with pytest.raises(SteelCADError, match='si toccano'):
        fori_rapidi.posizioni({'disposizione': 'angoli', 'bordo': 60}, 200, 100)
    with pytest.raises(SteelCADError, match='foro tondo'):
        fori_rapidi.misure_asola({'larg': 10, 'alt': 10})
