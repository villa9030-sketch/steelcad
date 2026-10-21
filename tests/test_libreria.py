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
