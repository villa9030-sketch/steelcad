"""Salvataggio sicuro, recupero, undo/redo, controlli del DXF, riferimento allo spigolo cliccato."""
import json
import os
import time

import ezdxf
import pytest

from cad_engine import History, project_io
from cad_engine.errors import ExportError, ProjectFileError, SteelCADError
from cad_engine.exporters import dxf
from cad_engine.features.base import volume

import math

from conftest import FORO, plate

FORO40 = math.pi * 20 ** 2


def test_salvataggio_con_copia_precedente(tmp):
    doc, *_ = plate()
    p = project_io.save(doc, tmp / 'piastra.steelcad')
    doc.set_parameter('larghezza', 400)
    project_io.save(doc, p)
    bak = tmp / 'piastra.steelcad.bak'
    assert bak.exists()
    assert json.loads(bak.read_text(encoding='utf-8'))['parameters']['larghezza'] == 300
    assert json.loads(p.read_text(encoding='utf-8'))['parameters']['larghezza'] == 400
    assert not list(tmp.glob('*.tmp'))


def test_autosave_e_recupero(tmp):
    doc, *_ = plate()
    p = project_io.save(doc, tmp / 'piastra.steelcad')
    assert not project_io.recovery_available(p)
    doc.set_parameter('larghezza', 380)
    time.sleep(0.02)
    project_io.autosave(doc, p)
    os.utime(project_io.autosave_path(p), None)
    assert project_io.recovery_available(p)
    rec = project_io.recover(p)
    assert rec.parameters['larghezza'] == 380
    project_io.save(rec, p)                 # salvando, l'autosave sparisce
    assert not project_io.autosave_path(p).exists()


def test_file_rovinato_messaggio_chiaro(tmp):
    p = tmp / 'rotto.steelcad'
    p.write_text('{"format": "steelcad", "vers', encoding='utf-8')
    with pytest.raises(ProjectFileError, match='rovinato'):
        project_io.load(p)
    p.write_text('{"format": "altro"}', encoding='utf-8')
    with pytest.raises(SteelCADError, match='non è un progetto SteelCAD'):
        project_io.load(p)
    p.write_text('{"format": "steelcad", "version": 99}', encoding='utf-8')
    with pytest.raises(SteelCADError, match='versione più nuova'):
        project_io.load(p)


def test_undo_redo_e_errore_dentro_il_comando():
    doc, sk, r, c, ids, e1 = plate()
    h = History(doc)
    with h.change('Spessore 8'):
        doc.edit_feature(e1, distance=8)
    with h.change('Foro Ø40'):
        sk.set_value(ids['d'], 40)
    assert h.labels()['undo'] == ['Foro Ø40', 'Spessore 8']
    assert volume(doc.rebuild().body.shape) == pytest.approx(300 * 200 * 8 - FORO40 * 8, rel=1e-9)
    h.undo()
    h.undo()
    assert doc.feature(e1)['distance'] == 5 and doc.sketch(sk.id).constraints[ids['d']]['value'] == 30
    assert volume(doc.rebuild().body.shape) == pytest.approx(300 * 200 * 5 - FORO * 5, rel=1e-9)
    h.redo()
    assert doc.feature(e1)['distance'] == 8 and h.can_redo
    with pytest.raises(SteelCADError):
        with h.change('Parametro sbagliato'):
            doc.set_parameter('larghezza', 'altezza * 2')       # altezza non esiste
    assert doc.parameters['larghezza'] == 300 and h.labels()['undo'][0] == 'Spessore 8'
    h.redo()
    with pytest.raises(SteelCADError, match='niente da ripetere'):
        h.redo()


def test_parametri_che_dipendono_da_parametri():
    doc, *_ = plate()
    doc.set_parameter('base', 250)
    doc.set_parameter('larghezza', 'base + 50')
    assert doc.resolved_parameters()['larghezza'] == 300
    with pytest.raises(SteelCADError, match='in cerchio'):
        doc.set_parameter('base', 'larghezza - 50')
    assert doc.parameters['base'] == 250


def test_rimuovere_feature_usata():
    doc, sk, *_ = plate()
    with pytest.raises(SteelCADError, match='lo usano E1'):
        doc.remove_feature(sk.id)


def _dxf(tmp, entities):
    d = ezdxf.new('R2010')
    d.header['$INSUNITS'] = 4
    m = d.modelspace()
    for kind, *args in entities:
        getattr(m, kind)(*args)
    p = tmp / 'prova.dxf'
    d.saveas(p)
    return dxf.check(p)


def test_controlli_dxf_trovano_i_problemi(tmp):
    quadro = [('add_line', (0, 0), (100, 0)), ('add_line', (100, 0), (100, 100)),
              ('add_line', (100, 100), (0, 100)), ('add_line', (0, 100), (0, 0))]
    assert _dxf(tmp, quadro)['ok']
    aperto = _dxf(tmp, quadro[:3])
    assert not aperto['ok'] and 'contorno non chiuso' in aperto['problems'][0]
    doppio = _dxf(tmp, quadro + [('add_line', (100, 0), (0, 0))])
    assert any('doppie o sovrapposte' in p for p in doppio['problems'])
    sovrapposto = _dxf(tmp, quadro + [('add_line', (20, 0), (60, 0)), ('add_line', (60, 0), (20, 0))])
    assert any('doppie o sovrapposte' in p for p in sovrapposto['problems'])
    micro = _dxf(tmp, [('add_line', (0, 0), (100, 0)), ('add_line', (100, 0), (100.001, 0)),
                       ('add_line', (100.001, 0), (100, 100)), ('add_line', (100, 100), (0, 0))])
    assert any('microsegmenti' in p for p in micro['problems'])
    d = ezdxf.new('R2010')
    d.header['$INSUNITS'] = 1          # pollici
    d.modelspace().add_circle((0, 0), 5)
    d.saveas(tmp / 'pollici.dxf')
    assert 'le unità del file non sono millimetri' in dxf.check(tmp / 'pollici.dxf')['problems']


def test_dxf_rifiuta_pezzi_non_piani(tmp):
    doc, sk, r, c, ids, e1 = plate()
    doc.add_feature('fillet', edges=[{'faces': sorted([f'{e1}/fine', f'{e1}/lato/{r["bottom"]}'])}], radius=2)
    res = doc.rebuild()
    assert res.ok
    with pytest.raises(ExportError, match='non è una lamiera piana'):
        dxf.export_flat(res.body.shape, tmp / 'no.dxf')
    assert not (tmp / 'no.dxf').exists()


def test_clic_su_spigolo_diventa_riferimento_stabile():
    doc, sk, r, c, ids, e1 = plate()
    body = doc.rebuild().body
    # simula il clic: prendo lo spigolo comune tra faccia finale e lato destro
    target = body.edges({'faces': sorted([f'{e1}/fine', f'{e1}/lato/{r["right"]}'])})[0]
    ref = body.edge_ref(target)
    assert ref == {'faces': sorted([f'{e1}/fine', f'{e1}/lato/{r["right"]}'])}
    doc.add_feature('fillet', edges=[ref], radius=1)
    doc.set_parameter('larghezza', 500)
    res = doc.rebuild()
    assert res.ok
    rac = res.body.names['F1/raccordo/1'][0]
    from cad_engine.analysis.measure import properties
    bb = properties(rac, 'S235')['bbox_mm']
    assert bb['max'][0] == pytest.approx(500, abs=1e-6) and bb['max'][2] == pytest.approx(5, abs=1e-6)
