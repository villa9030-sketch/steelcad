"""03/11 (secondo giro) — a lavoro fatto i fori si cambiano dalla stessa finestra del Foro: clic sul foro, si riapre
con com'erano (4 agli angoli a 20, Ø10…) e si cambia diametro, disposizione e distanze dai bordi, con anteprima."""
import pytest

from app.service import Service
from tests.test_foro_diretto import _fori_3d


@pytest.fixture
def piastra():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 200, 'profondita': 100, 'spessore': 3, 'raggio': 1.5, 'k': 0.4})['ok']
    return s


def _taglio(s):
    return next(f for f in s.doc.features if isinstance(f, dict) and f.get('type') == 'sheet_cut')


def test_fori_del_comando_foro_si_riaprono_come_li_avevi_chiesti(piastra):
    s = piastra
    assert s.fori_guidati(s.fori_faccia(), {'tipo': 'tondo', 'd': 10, 'disposizione': 'angoli', 'bordo': 20})['ok']
    t = _taglio(s)
    r = s.fori_da_modificare(t['id'])
    assert r['ok'] and r['spec']['disposizione'] == 'angoli' and r['spec']['bordo'] == 20 and r['spec']['d'] == 10
    # anche partendo dallo sketch (il clic sul foro dà lo sketch)
    assert s.fori_da_modificare(t['sketch'])['feature'] == t['id']


def test_cambio_distanza_dai_bordi_e_diametro_stesso_taglio(piastra):
    s = piastra
    assert s.fori_guidati(s.fori_faccia(), {'tipo': 'tondo', 'd': 10, 'disposizione': 'angoli', 'bordo': 20})['ok']
    t = _taglio(s)
    n = len(s.doc.features)
    spec = {'tipo': 'tondo', 'd': '12,5', 'disposizione': 'angoli', 'bordo': 25}
    a = s.anteprima('fori_modifica', [t['id'], spec])
    assert a['ok'] and a['frase'] == 'Toglie dal pezzo: 4 fori Ø12,5', a
    r = s.fori_modifica(t['id'], spec)
    assert r['ok'] and r['message'] == 'Cambiati 4 fori.', r
    assert len(s.doc.features) == n                       # niente taglio in più: è lo stesso
    fori, _ = _fori_3d(s)
    assert fori == [(25.0, 25.0, 12.5), (25.0, 75.0, 12.5), (175.0, 25.0, 12.5), (175.0, 75.0, 12.5)]
    assert len(s.result.body.sheet.flat.inner_wires()) == 4
    assert s.fori_da_modificare(t['id'])['spec']['bordo'] == 25
    s.undo()
    fori, _ = _fori_3d(s)
    assert fori[0] == (20.0, 20.0, 10.0)


def test_da_angoli_a_fila_e_in_asole(piastra):
    s = piastra
    assert s.fori_guidati(s.fori_faccia(), {'tipo': 'tondo', 'd': 10, 'disposizione': 'centro'})['ok']
    t = _taglio(s)
    r = s.fori_modifica(t['id'], {'tipo': 'asola', 'larg': 30, 'alt': 10, 'disposizione': 'fila', 'n': 3, 'passo': 50,
                                  'verso': 'x', 'lato': 'mezzo'})
    assert r['ok'] and r['message'] == 'Cambiate 3 asole.', r
    assert len(s.result.body.sheet.flat.inner_wires()) == 3


def test_fori_fuori_dal_pezzo_non_si_cambiano_e_lo_dice(piastra):
    s = piastra
    assert s.fori_guidati(s.fori_faccia(), {'tipo': 'tondo', 'd': 10, 'disposizione': 'angoli', 'bordo': 20})['ok']
    t = _taglio(s)
    r = s.fori_modifica(t['id'], {'tipo': 'tondo', 'd': 10, 'disposizione': 'angoli', 'bordo': 3})
    assert not r['ok'] and 'esce' in r['message']
    fori, _ = _fori_3d(s)
    assert fori[0] == (20.0, 20.0, 10.0)                  # restano dov'erano


def test_fori_disegnati_a_mano_si_riaprono_come_dove_clicco(piastra):
    s = piastra
    faccia = s.fori_faccia()
    r = s.sketch_on_face(faccia)
    sid = r['sketch']
    from app import sketch_ops
    sk = s.doc.sketch(sid)
    import build123d as bd
    from cad_engine.sketch.face_plane import plane_of
    piano = plane_of(s.result.body, faccia, sk)
    ox, oy, _, _ = s._fuori_tutto(piano, faccia)
    sketch_ops.add_circle(s.doc, sid, [ox + 30, oy + 40], 4)
    sketch_ops.add_circle(s.doc, sid, [ox + 150, oy + 40], 4)
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    t = _taglio(s)
    r = s.fori_da_modificare(t['id'])
    assert r['ok'] and r['spec']['disposizione'] == 'punti' and r['spec']['d'] == 8
    assert sorted(map(tuple, r['spec']['punti'])) == [(30, 40), (150, 40)]
    spec = dict(r['spec'], punti=[[30, 50], [150, 50]])
    assert s.fori_modifica(t['id'], spec)['ok']
    fori, _ = _fori_3d(s)
    assert [(f[0], f[1]) for f in fori] == [(30.0, 50.0), (150.0, 50.0)]
    del bd
