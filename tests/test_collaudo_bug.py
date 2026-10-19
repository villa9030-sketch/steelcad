"""I bug trovati dal collaudo (tools/collaudo.py): ognuno ha la sua prova, perché non tornino."""
import math
import os
import tempfile

import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402

LAM = {'name': 'P', 'larghezza': 200, 'profondita': 120, 'spessore': 2, 'raggio': 2, 'k': 0.4}


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


def lamiera():
    s = Service()
    assert s.new_project('lamiera', LAM)['ok']
    return s


def interno(r):
    return 'Errore interno' in (r.get('message') or '')


def test_annulla_conserva_l_ordine_delle_misure():
    s = lamiera()
    nomi = lambda: [p['name'] for p in s.state()['parameters']]  # noqa: E731
    prima = nomi()
    assert not s.add_flange('SM1', 'L1', {'length': '-10'})['ok']       # rifiutata: torna com'era
    assert nomi() == prima
    assert s.add_flange('SM1', 'L1', {'length': '30'})['ok']
    s.undo()
    assert nomi() == prima
    s.redo()
    assert nomi() == prima


def test_sketch_aperto_non_usato_non_e_un_errore_e_non_dipende_dalla_cache(tmp_path):
    s = lamiera()
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_polyline(sid, [[120, 30], [170, 30]], False)['ok']
    assert s.state()['errors'] == []
    v = s.sketch_view(sid)['sketch']
    assert v['open'] and 'piega su linea' in v['status']
    assert s.create_from_sketch(sid, 'louver', {'width': 6, 'height': 3})['ok']
    s.undo()
    assert s.state()['errors'] == []
    s.save(str(tmp_path / 'a.steelcad'))
    s2 = Service()
    assert s2.open(str(tmp_path / 'a.steelcad'))['ok']
    assert s2.state()['errors'] == []


def test_metodo_di_piega_predefinito_vale_per_la_lamiera_nuova():
    s = Service()
    assert s.set_bend_default({'radius': 2, 'method': 'din6935'})['ok']
    assert s.new_project('lamiera', {'name': 'x', 'larghezza': 100, 'profondita': 80, 'spessore': 2})['ok']
    assert s.doc.feature('SM1')['method'] == 'din6935'
    assert s.add_flange('SM1', 'L1', {'length': '20'})['ok']


@pytest.mark.parametrize('valori', [{'radius': 'x', 'k': 0.4}, {'radius': -2, 'k': 0.4}, {'radius': 2, 'k': 5}])
def test_predefiniti_di_piega_assurdi_rifiutati(valori):
    r = Service().set_bend_default(valori)
    assert not r['ok'] and not interno(r)


@pytest.mark.parametrize('kind,valori', [
    ('cancello', {'passo': 0}), ('cancello', {'passo': -10}), ('scaffale', {'ripiani': 2.5}),
    ('telaio', {'L': -500}), ('armadio', {'P': 0}), ('lamiera', {**LAM, 'spessore': 0}),
    ('lamiera', {**LAM, 'k': 2}), ('piastra', {'larghezza': 100, 'altezza': 100, 'spessore': 5, 'foro': 150}),
    ('inesistente', {}),
])
def test_modelli_con_misure_assurde(kind, valori):
    r = Service().new_project(kind, valori)
    assert not r['ok'] and not interno(r), r


def test_cono_con_raggio_scritto_male_dice_cosa_non_va():
    s = Service()
    assert s.new_project('cono', {'raggio': 'abc', 'k': 0.4})['ok']
    msg = ' '.join(e['message'] for e in s.state()['errors'])
    assert 'abc' in msg and 'kernel' not in msg.lower()


def test_numeri_non_numeri_nell_assieme(tmp_path):
    a = lamiera()
    a.save(str(tmp_path / 'p.steelcad'))
    s = Service()
    s.new_assembly('A')
    s.asm_insert(str(tmp_path / 'p.steelcad'))
    s.asm_insert(str(tmp_path / 'p.steelcad'))
    for r in (s.asm_move('I2', 'a', 0, 0), s.asm_move('I2', float('nan'), 0, 0), s.asm_rotate('I2', 'w', 90),
              s.asm_rotate('I2', 'x', 'abc')):
        assert not r['ok'] and not interno(r)
    assert all(math.isfinite(x) for i in s.asm.instances for x in i['T'])


def test_comandi_dell_assieme_fuori_da_un_assieme():
    s = lamiera()
    for r in (s.asm_interferences(), s.asm_move('I1', 1, 0, 0), s.asm_remove('I1'), s.asm_open_part('I1')):
        assert not r['ok'] and not interno(r)


def test_riferimenti_spariti_messaggi_chiari():
    s = lamiera()
    s.add_flange('SM1', 'L1', {'length': '30'})
    for r in (s.select('body', 99999), s.select('flange=SM1/FL99'), s.select('boh'), s.edit_flange('SM1', 'FL99', {'length': '5'}),
              s.delete_flange_hole('SM1', 'FL1', 7)):
        assert not r['ok'] and not interno(r)
    t = Service()
    t.new_project('telaio', {})
    for r in (t.set_joint('ST1', 'T0', {'type': 'boh'}), t.set_joint('ST1', 'T999', {'type': 'auto'}),
              t.move_node('ST1', 'T999', [1, 0, 0]), t.select('ST1/M999')):
        assert not r['ok'] and not interno(r)


def test_sketch_valori_sbagliati():
    s = lamiera()
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    s.sketch_add_rectangle(sid, [10, 10], [50, 40])
    linee = [x['id'] for x in s.sketch_view(sid)['sketch']['lines'] if not x['ref']]
    for r in (s.sketch_add_circle(sid, ['a', 60], 5), s.sketch_add_circle(sid, [60, 60], 'r'),
              s.sketch_move(sid, linee, 'a', 5), s.sketch_dimension(sid, 'distance', linee[:2]),
              s.sketch_dimension(sid, 'length', [])):
        assert not r['ok'] and not interno(r)


def test_svasatura_piu_piccola_del_foro():
    s = lamiera()
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    s.sketch_add_circle(sid, [50, 50], 2.75)
    c = [x['id'] for x in s.sketch_view(sid)['sketch']['circles'] if not x['ref']]
    r = s.sketch_hole_type(sid, c, {'tipo': 'svasato', 'D': 3, 'angolo': 90})
    assert not r['ok'] and 'più larga' in r['message']
    assert s.sketch_hole_type(sid, c, {'tipo': 'svasato', 'D': 9, 'angolo': 90})['ok']


def test_file_rovinati_e_cartelle_che_non_ci_sono(tmp_path):
    s = Service()
    (tmp_path / 'caso.dxf').write_bytes(os.urandom(3000))
    r = s.import_dxf(str(tmp_path / 'caso.dxf'))
    assert not r['ok'] and not interno(r) and all(c.isprintable() for c in r['message'])
    (tmp_path / 'lista.steelcad').write_text('[1, 2, 3]', encoding='utf-8')
    r = s.open(str(tmp_path / 'lista.steelcad'))
    assert not r['ok'] and not interno(r)
    s = lamiera()
    for r in (s.save(str(tmp_path / 'non_c_e' / 'x.steelcad')), s.export_step(str(tmp_path / 'non_c_e' / 'x.step'))):
        assert not r['ok'] and not interno(r)


def test_import_angolo_zero_non_diventa_90(tmp_path):
    import ezdxf
    d = ezdxf.new()
    d.layers.add('PIEGA')
    m = d.modelspace()
    m.add_lwpolyline([(0, 0), (300, 0), (300, 100), (0, 100)], close=True)
    m.add_line((0, 20), (300, 20), dxfattribs={'layer': 'PIEGA'})
    d.saveas(tmp_path / 'b.dxf')
    s = Service()
    r = s.import_dxf(str(tmp_path / 'b.dxf'))
    x = s.import_dxf_create(r['scelto'], {'thickness': 2, 'radius': 2, 'k': 0.4, 'angle': 0})
    assert not x['ok'] and not interno(x)
    assert not s.import_dxf_giro(-1)['ok']
