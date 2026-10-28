"""La tramoggia fatta è un pezzo come gli altri (28/10, Stefano: «devo avere tutte le possibilità di un disegno
normale»): fori e tagli su una parete e sullo sviluppo, fori guidati, linguette, flange sui bordi liberi. E lo
sviluppo ha tutte le facce intere, il 3D lo spessore giusto anche dove si incontrano quattro facce."""
import math
import os
import tempfile

import build123d as bd
import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402
from cad_engine.features.base import volume  # noqa: E402
from cad_engine.sheetmetal import poliedro as P  # noqa: E402

T = 3.0


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


@pytest.fixture
def s():
    sv = Service()
    assert sv.new_project('tramoggia_cassone', {'raggio': 3, 'k': 0.4})['ok']
    return sv


def test_sviluppo_con_tutte_le_facce_intere(monkeypatch):
    """La giunzione che chiude l'anello delle falde nello stesso pezzo: prima il rifilo «lungo il bordo dell'altra»
    tagliava via metà della falda davanti (496 324 → 275 135 mm²) perché nello sviluppo l'altra sta lontana."""
    visti = {}
    orig = P.pezzi

    def spia(G, pieghe, tec):
        ps = orig(G, pieghe, tec)
        for p in ps:
            for f, poly in p.poligoni.items():
                visti[G.nomi[f]] = (abs(P._area2(poly)), P._area3(G, f))
        return ps
    monkeypatch.setattr(P, 'pezzi', spia)
    sv = Service()
    sv.new_project('tramoggia_cassone', {'raggio': 3, 'k': 0.4})
    assert len(visti) == 12
    for nome, (a2, a3) in visti.items():
        assert a2 == pytest.approx(a3, rel=0.02), nome         # al più i rifili delle saldature (lo spessore)


def test_pareti_dello_spessore_giusto(s):
    """Agli angoli del cambio di pendenza si incontrano quattro facce: la parete restava storta e sottile (2,84)."""
    b = s.result.body
    fuori = bd.Face(b.names['FM1/cassone_destra/fuori'][0])
    dentro = bd.Face(b.names['FM1/cassone_destra/dentro'][0])
    xs_f = {round(v.X, 3) for v in fuori.vertices()}
    xs_d = {round(v.X, 3) for v in dentro.vertices()}
    assert xs_f == {500.0} and xs_d == {497.0}


def _centro_nello_sviluppo(s, nome):
    b = s.result.body
    src, dst, _ = b.sheet.pannelli[nome]
    c3 = bd.Face(b.names[nome][0]).center()
    return dst.from_local_coords(src.to_local_coords(c3)), c3


def test_foro_disegnato_sullo_sviluppo_va_sulla_sua_falda(s):
    cf, c3 = _centro_nello_sviluppo(s, 'FM1/tramoggia_davanti/fuori')
    v0, a0 = volume(s.result.body.shape), s.result.body.sheet.flat_area
    sid = s.sketch_on_flat('FM1')['sketch']
    s.sketch_add_circle(sid, [cf.X, cf.Y], 40)
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')
    b = s.result.body
    assert v0 - volume(b.shape) == pytest.approx(math.pi * 40 ** 2 * T, rel=0.02)
    assert a0 - b.sheet.flat_area == pytest.approx(math.pi * 40 ** 2, rel=0.01)
    pareti = [bd.Face(f) for f in b.names['TG1/parete']]
    assert len(pareti) <= 2                                      # solo la parete del foro, non le pieghe
    centro = sum((p.center() for p in pareti), bd.Vector()) / len(pareti)
    assert (centro - c3).length < 45                             # sulla falda davanti, dove cade nello sviluppo


def test_fori_guidati_su_una_parete_anche_vicino_al_cambio_di_pendenza(s):
    r = s.fori_guidati('FM1/cassone_destra/fuori', {'tipo': 'tondo', 'd': 12, 'x': 100, 'y': 60,
                                                    'fila': True, 'n': 3, 'passo': 50})
    assert r['ok'], r.get('message')
    assert any('Fori' in str(c) for c in str(s.state()['tree']).split(','))


def test_linguetta_sul_bordo(s):
    v0, a0 = volume(s.result.body.shape), s.result.body.sheet.flat_area
    sid = s.sketch_on_face('FM1/bordo_davanti/fuori')['sketch']
    s.sketch_add_rectangle(sid, [400, 30], [600, 90])
    r = s.sheet_tab(sid)
    assert r['ok'], r.get('message')
    b = s.result.body
    aggiunta = b.sheet.flat_area - a0
    assert aggiunta == pytest.approx(200 * 48.5, abs=1)
    assert volume(b.shape) - v0 == pytest.approx(aggiunta * T, rel=0.01)
    assert len(b.sheet.flat.faces()) == 3                        # i pezzi restano tre


def test_flangia_sul_bordo_esterno_e_avviso_sullo_scarico(s):
    b = s.result.body
    f = bd.Face(b.names['FM1/bordo_davanti/fuori'][0])
    bordo = max((e for e in f.outer_wire().edges()), key=lambda e: abs(e.center().Y))      # il bordo esterno, y = −540
    a, c = bordo.start_point(), bordo.end_point()
    r = s.add_edge_flange('FM1/bordo_davanti/fuori', [a.X, a.Y, a.Z], [c.X, c.Y, c.Z], {'length': 25})
    assert r['ok'], r.get('message')
    s.undo()
    f = bd.Face(b.names['FM1/tramoggia_davanti/fuori'][0])
    basso = min(f.outer_wire().edges(), key=lambda e: e.center().Z)
    a, c = basso.start_point(), basso.end_point()
    r = s.add_edge_flange('FM1/tramoggia_davanti/fuori', [a.X, a.Y, a.Z], [c.X, c.Y, c.Z], {'length': 25})
    assert not r['ok'] and 'Flangia scarico' in r['message']


def test_bordi_liberi_nella_scena(s):
    bordi = s.scene()['bend_edges']
    assert len(bordi) >= 4 and all(e['face'].endswith('/fuori') for e in bordi)


def test_piega_su_linea_spiega_cosa_fare(s):
    sid = s.sketch_on_face('FM1/cassone_destra/fuori')['sketch']
    s.sketch_add_polyline(sid, [[0, 300], [997, 300]], False)
    r = s.sheet_fold(sid, 30)
    assert not r['ok'] and 'spigoli' in r['message']


def test_smusso_piccolo_avvisa_delle_schegge():
    """28/10: smusso di 2 mm → facce di 2,8 mm tra due pieghe e pezzi a scheggia: si dice, con la misura minima."""
    s = Service()
    assert s.new_project('tramoggia_cassone', {'raggio': 3, 'k': 0.4, 'smusso': 2})['ok']
    avv = ' '.join(s.result.body.sheet.warnings)
    assert 'Smusso troppo piccolo' in avv and 'almeno 9 mm' in avv
    s2 = Service()
    assert s2.new_project('tramoggia_cassone', {'raggio': 3, 'k': 0.4, 'smusso': 10})['ok']
    assert 'Smusso troppo piccolo' not in ' '.join(s2.result.body.sheet.warnings)


def test_fori_sul_bordo_con_angoli_a_45():
    """29/10 (schermata di Stefano): con gli angoli del bordo a 45° le quattro facce del bordo sono un anello solo nel
    3D e restava senza nome: niente sketch, niente fori. Ora ha il nome dei lati e ogni foro va nel suo pezzo."""
    s = Service()
    assert s.new_project('tramoggia_cassone', dict(A=600, B=600, Hc=600, a=250, b=250, Ht=400, bordo=20, verso_bordo='dentro',
                                                   flangia=50, verso_flangia='fuori', angoli_bordo='45', spessore=2,
                                                   raggio=2, k=0.4, divisione='lati'))['ok']
    from cad_engine.sketch.face_plane import plane_of
    for anello in ('bordo', 'flangia_scarico'):
        nome = f'FM1/{anello}_davanti/fuori'
        assert nome in s.result.body.names
        v0 = volume(s.result.body.shape)
        sid = s.sketch_on_face(nome)['sketch']
        pl = plane_of(s.result.body, nome, s.doc.sketch(sid))
        sag = s.result.body.sheet.sagome
        lati = [n for n in sag if n.startswith(f'FM1/{anello}_') and n.endswith('/fuori')]
        assert len(lati) == 4
        for n in lati:
            pts = [bd.Vector(*q) for q in sag[n]]
            q = pl.to_local_coords(sum(pts, bd.Vector()) / len(pts))
            s.sketch_add_circle(sid, [q.X, q.Y], 4)
        assert s.create_from_sketch(sid, 'cut', {})['ok']
        assert v0 - volume(s.result.body.shape) == pytest.approx(4 * math.pi * 16 * 2, rel=0.02)
    d = s.result.body.sheet
    cerchi = [e.arc_center for f in d.flat.faces() for e in f.edges() if e.geom_type == bd.GeomType.CIRCLE]
    for n in (x for x in d.sagome if x.endswith('/fuori') and ('bordo' in x or 'flangia' in x)):
        src, dst, _ = d.pannelli[n]
        pts = [bd.Vector(*q) for q in d.sagome[n]]
        atteso = dst.from_local_coords(src.to_local_coords(sum(pts, bd.Vector()) / len(pts)))
        assert min((c - atteso).length for c in cerchi) < 0.01, n              # nel pezzo giusto dello sviluppo
