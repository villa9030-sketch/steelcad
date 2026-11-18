"""18/11 (carrello di Stefano, assieme lento): i pezzi già costruiti si tengono su disco. Riaprendo l'assieme il pezzo
non si ricostruisce, ma è identico (facce coi nomi, peso, riga di distinta); cambiando il file si ricostruisce."""
import json

import numpy as np
import pytest

from app.service import Service
from cad_engine import assembly as A
from cad_engine import assembly_cache as AC


@pytest.fixture()
def casa(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path / 'home'))
    return tmp_path


def _lamiera(cart):
    s = Service()
    assert s.new_project('lamiera', {'name': 'Vasca', 'larghezza': 300, 'profondita': 200, 'spessore': 2,
                                     'raggio': 1, 'k': 0.33})['ok']
    for lato in ('L1', 'L3'):
        assert s.add_flange('SM1', lato, {'length': 40})['ok']
    fid = s.doc.feature('SM1')['flanges'][0]['id']
    sid = s.sketch_on_face(f'SM1/{fid}/esterno')['sketch']
    assert s.sketch_add_circle(sid, [50, 20], 4.5)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    f = cart / 'Vasca.steelcad'
    assert s.save(str(f))['ok']
    return f


def _fresco(f):
    A._PEZZI.pop(str(f.resolve()), None)
    return A.load_part(f)


def test_riaperto_dal_disco_e_uguale(casa):
    f = _lamiera(casa)
    primo = _fresco(f)
    assert not isinstance(primo.result, A._RisultatoPigro)             # la prima volta si costruisce
    secondo = _fresco(f)
    assert isinstance(secondo.result, A._RisultatoPigro) and secondo.result._res is None   # poi dal disco
    assert set(secondo.names) == set(primo.names)
    for nome in primo.names:
        a = [A.face_info(primo, x) for x in primo.names[nome]]
        b = [A.face_info(secondo, x) for x in secondo.names[nome]]
        assert len(a) == len(b), nome
        for x, y in zip(a, b):
            assert x['kind'] == y['kind'] and np.allclose(x['p'], y['p']) and np.allclose(x['n'], y['n']), nome
    assert abs(A.part_props(primo)['mass_kg'] - A.part_props(secondo)['mass_kg']) < 1e-9
    assert A._riga(primo) == A._riga(secondo)                           # spessore e sviluppo senza ricostruire
    assert A.segni_laser(primo) == A.segni_laser(secondo)
    assert secondo.result._res is None                                 # niente di tutto questo l'ha ricostruito
    assert secondo.result.body.sheet.thickness == 2                     # chi chiede la lamiera la ottiene


def test_file_cambiato_si_ricostruisce(casa):
    f = _lamiera(casa)
    _fresco(f)
    d = json.loads(f.read_text(encoding='utf-8'))
    d['parameters'] = {**d.get('parameters', {}), 'nuovo': 5}
    f.write_text(json.dumps(d), encoding='utf-8')
    assert not isinstance(_fresco(f).result, A._RisultatoPigro)


def test_pezzo_che_legge_altri_file_non_si_tiene(casa):
    f = casa / 'x.steelcad'
    f.write_text('{"features": [{"file": "disegno.dxf"}]}', encoding='utf-8')
    assert AC.chiave(f) is None
    f.write_text('{"features": []}', encoding='utf-8')
    assert AC.chiave(f)


def test_assieme_riaperto_uguale(casa):
    f = _lamiera(casa)
    s = Service()
    assert s.new_assembly('Prova')['ok'] and s.asm_insert(str(f))['ok'] and s.asm_insert(str(f))['ok']
    a = casa / 'Prova.steelcad-asm'
    assert s.save(str(a))['ok']
    prima = s.scene()
    A._PEZZI.clear()
    s2 = Service()
    assert s2.open(str(a))['ok']
    dopo = s2.scene()
    assert [o['positions'] for o in prima['objects']] == [o['positions'] for o in dopo['objects']]
    assert [[x['name'] for x in o['faces']] for o in prima['objects']] == [[x['name'] for x in o['faces']] for o in dopo['objects']]


def test_torna_all_assieme_senza_ricostruire(casa, monkeypatch):
    """Modificato il pezzo nell'editor, tornando all'assieme non si ricostruisce una seconda volta."""
    f = _lamiera(casa)
    s = Service()
    assert s.new_assembly('Prova')['ok'] and s.asm_insert(str(f))['ok']
    assert s.save(str(casa / 'Prova.steelcad-asm'))['ok']
    assert s.asm_open_part('I1')['ok']
    fl = s.doc.feature('SM1')['flanges'][0]['id']
    assert s.edit_flange('SM1', fl, {'length': 55})['ok']
    assert s.save()['ok']
    from cad_engine.document import Document
    chiamate = []
    vero = Document.rebuild
    monkeypatch.setattr(Document, 'rebuild', lambda self, *a, **k: chiamate.append(1) or vero(self, *a, **k))
    assert s.asm_back()['ok']
    assert not chiamate                                                 # niente seconda ricostruzione
    part = s.asm_parts[s.asm.instance('I1')['file']]
    assert part.mtime == f.stat().st_mtime
