"""22/10: «dopo una foratura non posso più né stringerla né allargarla». Dal foro cliccato sul pezzo si cambia il
diametro (uno o tutti quelli uguali del disegno), anche di un foro svasato."""
import os
import tempfile

import build123d as bd
import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


def raggi(s):
    return sorted(round(f.radius, 4) for f in bd.Shape.cast(s.result.body.shape).faces() if f.geom_type == bd.GeomType.CYLINDER)


def piastra_con_fori():
    s = Service()
    assert s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 4, 'raggio': 1, 'k': 0.4})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    for x in (40, 100, 160):
        assert s.sketch_add_circle(sid, [x, 50], 5)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    return s, sid


def foro_cliccato(s):
    o = next(o for o in s.scene()['objects'] if o['id'] == 'body')
    for f in o['faces']:
        sel = s.select('body', f['index'])['selection']
        if sel.get('foro'):
            return sel['foro']
    raise AssertionError('nessun foro')


def test_allarga_un_foro_e_poi_tutti():
    s, sid = piastra_con_fori()
    fo = foro_cliccato(s)
    assert len(fo['uguali']) == 3 and fo['d'] == pytest.approx(10)
    r = s.sketch_hole_diameter(fo['sketch'], [fo['cerchio']], '14')
    assert r['ok'], r
    assert raggi(s) == [5, 5, 7]
    assert s.sketch_hole_diameter(fo['sketch'], fo['uguali'], '8,5')['ok']
    assert raggi(s) == [4.25, 4.25, 4.25]
    assert s.state()['errors'] == []


def test_foro_svasato_si_stringe_e_valori_sbagliati():
    s, sid = piastra_con_fori()
    fo = foro_cliccato(s)
    assert s.sketch_hole_type(fo['sketch'], fo['uguali'], {'tipo': 'svasato', 'D': '16', 'angolo': '90'})['ok']
    assert s.sketch_hole_diameter(fo['sketch'], fo['uguali'], 9)['ok']
    assert s.state()['errors'] == []
    for v in (0, -3, 'abc'):
        r = s.sketch_hole_diameter(fo['sketch'], fo['uguali'], v)
        assert not r['ok'] and 'Errore interno' not in r['message']
    assert s.sketch_hole_type(fo['sketch'], [fo['cerchio']], {'tipo': 'filettato', 'M': 'M6'})['ok']
    r = s.sketch_hole_diameter(fo['sketch'], [fo['cerchio']], 12)
    assert not r['ok'] and 'filettat' in r['message']
