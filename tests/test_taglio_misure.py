"""22/10: cliccando la parete di un taglio non tondo (rettangolo raccordato, asola) si cambiano le sue misure lì:
larghezza, altezza, posizione, raggi; il taglio si rifà."""
import os
import tempfile

import build123d as bd
import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


def piastra_con_finestra(raccordo=8):
    s = Service()
    assert s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 4, 'raggio': 1, 'k': 0.4})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_rectangle(sid, [40, 30], [120, 70])['ok']
    if raccordo:
        v = s.sketch_view(sid)['sketch']
        for p in v['points']:
            if (abs(p['xy'][0] - 40) < 1e-6 or abs(p['xy'][0] - 120) < 1e-6) and (abs(p['xy'][1] - 30) < 1e-6 or abs(p['xy'][1] - 70) < 1e-6):
                if p['id'] not in {x for l in v['lines'] if l['ref'] for x in (l['a'], l['b'])}:
                    assert s.sketch_fillet(sid, p['id'], raccordo)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    return s, sid


def clic_sul_taglio(s):
    o = next(o for o in s.scene()['objects'] if o['id'] == 'body')
    for f in o['faces']:
        sel = s.select('body', f['index'])['selection']
        if sel.get('contorno'):
            return sel
    raise AssertionError('nessun taglio riconosciuto')


def finestra(s):
    sol = bd.Shape.cast(s.result.body.shape)
    piane = [f for f in sol.faces() if f.geom_type == bd.GeomType.PLANE and abs(f.normal_at().Z) < 1e-6]
    xs = [v.X for f in piane for v in f.vertices() if 1 < v.X < 199]
    ys = [v.Y for f in piane for v in f.vertices() if 1 < v.Y < 99]
    raggi = sorted({round(f.radius, 3) for f in sol.faces() if f.geom_type == bd.GeomType.CYLINDER})
    return (round(min(xs), 3), round(max(xs), 3)), (round(min(ys), 3), round(max(ys), 3)), raggi


def test_rettangolo_raccordato_si_cambia_dal_pezzo():
    s, sid = piastra_con_finestra()
    sel = clic_sul_taglio(s)
    assert sel['title'] == 'Taglio rettangolare'
    campi = {c['label']: c for c in sel['contorno']['campi']}
    assert campi['Larghezza']['value'] == pytest.approx(80) and campi['Altezza']['value'] == pytest.approx(40)
    assert campi['Da sinistra (dall’origine)']['value'] == pytest.approx(40)
    raggio = next(c for k, c in campi.items() if k.startswith('Raggio'))
    assert raggio['value'] == pytest.approx(8)
    nuovi = [{**campi['Larghezza'], 'value': '100'}, {**campi['Altezza'], 'value': '50'},
             {**campi['Da sinistra (dall’origine)'], 'value': '30'}, {**raggio, 'value': '12'}]
    r = s.cut_contour_set(sel['contorno']['sketch'], nuovi)
    assert r['ok'], r
    assert s.state()['errors'] == []
    (x0, x1), (y0, y1), raggi = finestra(s)
    assert (x0, x1) == (30, 130) and y1 - y0 == pytest.approx(50) and 12 in raggi
    # di nuovo dal pezzo: le misure nuove
    campi2 = {c['label']: c['value'] for c in clic_sul_taglio(s)['contorno']['campi']}
    assert campi2['Larghezza'] == pytest.approx(100) and campi2['Altezza'] == pytest.approx(50)


def test_rettangolo_senza_raggi_e_valori_sbagliati():
    s, sid = piastra_con_finestra(raccordo=0)
    sel = clic_sul_taglio(s)
    campi = {c['label']: c for c in sel['contorno']['campi']}
    assert s.cut_contour_set(sid, [{**campi['Larghezza'], 'value': '60'}])['ok']
    (x0, x1), _, _ = finestra(s)
    assert x1 - x0 == pytest.approx(60)
    for v in ('0', '-5', 'abc'):
        r = s.cut_contour_set(sid, [{**campi['Altezza'], 'value': v}])
        assert not r['ok'] and 'Errore interno' not in r['message']


def test_asola_raggio_dal_pezzo():
    s = Service()
    assert s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 4, 'raggio': 1, 'k': 0.4})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_slot(sid, [60, 50], [140, 50], 6)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    sel = clic_sul_taglio(s)
    raggio = next(c for c in sel['contorno']['campi'] if c['label'].startswith('Raggio'))
    assert raggio['value'] == pytest.approx(6)
    r = s.cut_contour_set(sid, [{**raggio, 'value': '9'}])
    assert r['ok'], r
    assert 9 in finestra(s)[2] and s.state()['errors'] == []
