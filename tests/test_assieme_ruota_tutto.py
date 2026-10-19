"""Ruotare tutto l'assieme: i pezzi girano insieme, gli accoppiamenti restano rispettati, si annulla."""
import os
import tempfile

import numpy as np
import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402
from cad_engine import assembly as A  # noqa: E402


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


def assieme(tmp_path):
    p = Service()
    assert p.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 120, 'spessore': 2, 'raggio': 2, 'k': 0.4})['ok']
    p.save(str(tmp_path / 'p.steelcad'))
    s = Service()
    s.new_assembly('A')
    s.asm_insert(str(tmp_path / 'p.steelcad'))
    s.asm_insert(str(tmp_path / 'p.steelcad'))
    assert s.asm_move('I2', 300, 50, 0)['ok']
    return s


def posa(s):
    return {i['id']: (np.array(i['R']), np.array(i['T'])) for i in s.asm.instances}


def test_ruota_tutto_rigido_e_annulla(tmp_path):
    s = assieme(tmp_path)
    prima = posa(s)
    sel = s.select('assieme')
    assert sel['ok'] and sel['selection']['kind'] == 'assembly'
    assert s.asm_rotate_all('z', 90)['ok']
    dopo = posa(s)
    # la posizione relativa dei due pezzi non cambia
    rel = lambda P: P['I1'][0].T @ (P['I2'][1] - P['I1'][1])  # noqa: E731
    assert np.allclose(rel(prima), rel(dopo), atol=1e-6)
    assert not np.allclose(prima['I1'][0], dopo['I1'][0])
    for _ in range(3):
        assert s.asm_rotate_all('z', 90)['ok']
    giro = posa(s)
    for k in prima:
        assert np.allclose(prima[k][0], giro[k][0], atol=1e-9) and np.allclose(prima[k][1], giro[k][1], atol=1e-6)
    s.undo()
    s.undo()
    s.undo()
    s.undo()
    for k in prima:
        assert np.allclose(prima[k][1], posa(s)[k][1], atol=1e-6)


def test_ruota_tutto_valori_sbagliati(tmp_path):
    s = assieme(tmp_path)
    for r in (s.asm_rotate_all('w', 90), s.asm_rotate_all('x', 'abc'), s.asm_rotate_all('x', float('nan'))):
        assert not r['ok'] and 'Errore interno' not in r['message']
    assert not Service().asm_rotate_all('x', 90)['ok']


def test_ruota_tutto_con_accoppiamento(tmp_path):
    s = assieme(tmp_path)
    from tests.test_assembly import _faccia
    assert s.asm_add_mate('faccia', {'inst': 'I1', 'face': _faccia(s, 'I1', 'SM1/sopra')}, {'inst': 'I2', 'face': _faccia(s, 'I2', 'SM1/sotto')})['ok']
    prima = posa(s)
    assert s.asm_rotate_all('x', 90)['ok']
    assert not s.asm.warnings
    m = s.asm.mates[0]
    err = A.mate_error(m, posa(s), s.asm_parts, s.asm)
    assert err is None or err < 1e-6
    rel = lambda P: P['I1'][0].T @ (P['I2'][1] - P['I1'][1])  # noqa: E731
    assert np.allclose(rel(prima), rel(posa(s)), atol=1e-6)
