"""Libreria della viteria (21/10): pezzi dalle norme, fatti una volta, già da acquistare; una vite nel foro."""
import build123d as bd
import numpy as np
import pytest

from app import libreria
from app.service import Service
from cad_engine import assembly as A


@pytest.mark.parametrize('tipo,misura,L,alto', [('vite_tcei', 'M6', 20, 26), ('vite_te', 'M8', 30, 35.3),
                                                ('dado', 'M8', None, 6.8), ('rondella', 'M10', None, 2),
                                                ('rivetto', '4', 10, 11.3), ('inserto', 'M6', None, 16.5)])
def test_pezzi_della_libreria(tmp_path, tipo, misura, L, alto):
    f = libreria.crea(tipo, misura, L, tmp_path)
    p = A.load_part(f)
    assert not p.errors and p.doc.meta['acquisto']['descrizione'].startswith(libreria.CATALOGO[tipo]['nome'].split(' (')[0].split()[0])
    b = bd.Compound(p.shape).bounding_box()
    assert abs((b.size.Z if tipo in ('dado', 'rondella') else b.size.Y) - alto) < 0.05      # lungo l'asse
    assert libreria.crea(tipo, misura, L, tmp_path) == f                      # la seconda volta si riusa


def test_vite_nel_foro_e_in_distinta(tmp_path, monkeypatch):
    monkeypatch.setattr(libreria.Path, 'home', lambda: tmp_path)
    s = Service()
    assert s.new_project('piastra', {'name': 'P', 'larghezza': 100, 'altezza': 60, 'spessore': 10, 'foro': 6.4})['ok']
    assert s.save(str(tmp_path / 'P.steelcad'))['ok']
    assert s.new_assembly('Prova')['ok'] and s.asm_insert(str(tmp_path / 'P.steelcad'))['ok']
    o = next(o for o in s.scene()['objects'] if o['id'] == 'I1')
    foro = next(f['index'] for f in o['faces'] if s._asm_face('I1', f['index'])['kind'] == 'cilindrica')
    r = s.asm_insert_libreria('vite_tcei', 'M6', 20, {'inst': 'I1', 'face': foro})
    assert r['ok'] and 'nel foro' in r['message'], r.get('message')
    i = s.asm.instance('I2')
    asse = np.array(i['R']) @ np.array([0, 1.0, 0])
    centro = np.array(i['R']) @ np.array([0, 0, 0]) + np.array(i['T'])
    assert abs(abs(asse[2]) - 1) < 1e-6 and abs(centro[0] - 50) < 1e-6 and abs(centro[1] - 30) < 1e-6
    righe = s._asm_state()['bom']
    assert any(x['acquisto'] and 'TCEI ISO 4762 M6x20' in x['description'] for x in righe)


def test_vite_a_testa_svasata(tmp_path):
    """TSPEI ISO 10642 (21/10, Stefano: «più che una vite svasata mi sembra a testa brugola»): testa a 90°, lunghezza
    con la testa compresa, in distinta tra gli acquisti."""
    import build123d as bd

    from app import libreria
    from app.service import Service
    assert 'vite_tspei' in libreria.CATALOGO
    f = libreria.crea('vite_tspei', 'M6', 20, tmp_path)
    s = Service()
    assert s.open(str(f))['ok']
    sh = bd.Shape.cast(s.result.body.shape)
    bb = sh.bounding_box()
    assert abs(bb.size.Y - 20) < 1e-6 and abs(bb.size.X - 13.44) < 1e-6
    assert any(x.geom_type == bd.GeomType.CONE for x in sh.faces())
    assert 'ISO 10642 M6x20' in s.doc.meta['acquisto']['descrizione']


def test_vite_svasata_seduta_nel_cono(tmp_path, monkeypatch):
    """Cono su cono (21/10): la TSPEI messa nel foro svasato si siede da sola, testa a filo della lamiera; con angoli
    diversi l'accoppiamento a mano si rifiuta."""
    import numpy as np

    from app import libreria
    from app.service import Service
    from cad_engine import assembly as A
    from cad_engine.topology.naming import _faces_of
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path))
    s = Service()
    s.new_project('lamiera', {'name': 'Piastra', 'larghezza': 120, 'profondita': 80, 'spessore': 4})
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    s.sketch_add_circle(sid, [40, 40], 3.2)
    cid = next(k for k, e in s.doc.sketch(sid).entities.items() if e['kind'] == 'circle' and not e.get('ref'))
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    assert s.sketch_hole_type(sid, [cid], {'tipo': 'svasato', 'D': '13.44', 'angolo': '90'})['ok']
    f = tmp_path / 'Piastra.steelcad'
    assert s.save(str(f))['ok']
    assert s.new_assembly('A')['ok'] and s.asm_insert(str(f))['ok']
    iid = s.asm.instances[0]['id']
    part = s.asm_parts[s.asm.instances[0]['file']]
    kc = next(k for k, ff in enumerate(_faces_of(part.shape)) if A.face_info(part, ff)['kind'] == 'cilindrica')
    monkeypatch.setattr(libreria, 'crea', (lambda orig: lambda *a, **k: orig(*a[:3], tmp_path / 'Libreria'))(libreria.crea))
    r = s.asm_insert_libreria('vite_tspei', 'M6', 20, {'inst': iid, 'face': kc})
    assert r['ok'] and 'cono su cono' in r['message']
    assert np.allclose(s.asm.instances[-1]['T'], [40, 40, 4], atol=1e-3)     # testa a filo della faccia di sopra
    # a mano con una svasatura a 60°: si rifiuta
    s2 = Service()
    s2.new_project('lamiera', {'name': 'P2', 'larghezza': 120, 'profondita': 80, 'spessore': 6})
    sid2 = s2.sketch_on_face('SM1/sopra')['sketch']
    s2.sketch_add_circle(sid2, [40, 40], 3.2)
    c2 = next(k for k, e in s2.doc.sketch(sid2).entities.items() if e['kind'] == 'circle' and not e.get('ref'))
    s2.create_from_sketch(sid2, 'cut', {})
    assert s2.sketch_hole_type(sid2, [c2], {'tipo': 'svasato', 'D': '10', 'angolo': '60'})['ok']
    f2 = tmp_path / 'P2.steelcad'
    s2.save(str(f2))
    assert s.asm_insert(str(f2))['ok']
    i2 = s.asm.instances[-1]['id']
    p2 = s.asm_parts[s.asm.instances[-1]['file']]
    ks = next(k for k, ff in enumerate(_faces_of(p2.shape)) if A.face_info(p2, ff)['kind'] == 'conica')
    vite = s.asm_parts[s.asm.instances[1]['file']]
    kt = max((bd_area(ff), k) for k, ff in enumerate(_faces_of(vite.shape)) if A.face_info(vite, ff)['kind'] == 'conica')[1]
    r = s.asm_add_mate('cono', {'inst': i2, 'face': ks}, {'inst': s.asm.instances[1]['id'], 'face': kt})
    assert not r['ok'] and 'angoli diversi' in r['message']


def bd_area(f):
    import build123d as bd
    return bd.Face(f).area
