"""Le tavole degli assiemi si ritoccano come quelle dei pezzi (28/10): viste spostate, note; i ritocchi stanno nel
file dell'assieme, con Annulla; i fogli dei pezzi dentro le tavole dell'assieme hanno ognuno i suoi."""
import os
import tempfile

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


def test_tavola_assieme_si_ritocca_e_si_salva(tmp_path):
    s = assieme(tmp_path)
    p = s.drawing_preview({**s.drawing_fields()['fields']})
    assert p['ok'] and p['modificabili']
    f = p['sheets'][0]
    ids = {o['id'] for o in f['oggetti']}
    assert {'vista:fronte', 'vista:alto', 'vista:iso'} <= ids
    T0 = next(o['T'] for o in f['oggetti'] if o['id'] == 'vista:fronte')
    r = s.tavola_ritocchi(f['chiave'], {'viste': {'vista:fronte': [10, 0]}, 'note': [{'x': 40, 'y': 40, 'testo': 'Zincare'}]})
    assert r['ok']
    g = r['sheets'][0]
    T1 = next(o['T'] for o in g['oggetti'] if o['id'] == 'vista:fronte')
    assert abs(T1[1] - T0[1] - 10) < 1e-6 and 'Zincare' in g['svg']
    assert s.asm.meta['tavole'][f['chiave']]['note'][0]['testo'] == 'Zincare'
    import json
    salvato = A.save(s.asm, tmp_path / 'a')                              # nel file dell'assieme, e si rilegge
    letto = A.Assembly.from_dict(json.loads(salvato.read_text(encoding='utf-8')), salvato)
    assert letto.meta['tavole'][f['chiave']]['note'][0]['testo'] == 'Zincare'
    s.undo()
    assert not (s.asm.meta.get('tavole') or {})
    s.redo()
    assert s.asm.meta['tavole'][f['chiave']]


def test_fogli_dei_pezzi_con_chiavi_diverse(tmp_path):
    s = assieme(tmp_path)
    p = s.drawing_preview({**s.drawing_fields()['fields']}, True)
    chiavi = [f['chiave'] for f in p['sheets']]
    assert len(chiavi) == len(set(chiavi))
    assert any(c.startswith('p:') for c in chiavi)
