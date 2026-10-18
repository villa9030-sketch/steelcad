"""Tavole: pezzo (viste quotate, note dei fori), sviluppo (tabella pieghe), assieme (palloncini, distinta); PDF e DXF."""
import ezdxf
import pytest

from app.service import Service
from cad_engine import drawings as D


def _pezzo():
    s = Service()
    s.new_project('lamiera', {'name': 'Staffa', 'larghezza': 120, 'profondita': 60, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    for x in (30, 90):
        assert s.sketch_add_circle(sid, [x, 30], 2.5)['ok']
    cs = [c['id'] for c in s.sketch_view(sid)['sketch']['circles'] if not c['ref']]
    assert s.sketch_hole_type(sid, cs, {'tipo': 'filettato', 'M': 'M6'})['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    return s


def test_tavola_del_pezzo_e_dello_sviluppo(tmp_path):
    s = _pezzo()
    campi = {**s.drawing_fields()['fields'], 'azienda': 'Prova S.r.l.', 'numero': 'D-1'}
    p = s.drawing_preview(campi)
    assert p['ok'] and [x['title'] for x in p['sheets']] == ['Staffa', 'Staffa — sviluppo']
    pezzo, sviluppo = p['sheets'][0]['svg'], p['sheets'][1]['svg']
    assert 'VISTA DI FRONTE' in pezzo and 'VISTA DALL’ALTO' in pezzo and 'VISTA DA SINISTRA' in pezzo
    assert '2× M6 (preforo Ø5)' in pezzo                               # la nota del foro dallo sketch
    assert '>120<' in pezzo and 'Prova S.r.l.' in pezzo
    assert 'TABELLA PIEGHE' in sviluppo and 'FL1' in sviluppo
    r = s.export_drawings(str(tmp_path / 't.pdf'), campi)
    assert r['ok']
    pdf = (tmp_path / 't.pdf').read_bytes()
    assert pdf.startswith(b'%PDF-1.4') and pdf.count(b'/Type /Page ') == 2 and pdf.rstrip().endswith(b'%%EOF')
    assert s.export_drawings(str(tmp_path / 't.dxf'), campi)['ok']
    doc = ezdxf.readfile(str(tmp_path / 't.dxf'))
    layers = {e.dxf.layer for e in doc.modelspace()}
    assert {'contorno', 'quote', 'piega', 'cartiglio'} <= layers
    assert Service().drawing_fields()['fields']['azienda'] == 'Prova S.r.l.'   # ricordata
    assert s.doc.meta['disegno']['numero'] == 'D-1'                           # nel progetto


def test_tavole_dell_assieme(tmp_path):
    s = _pezzo()
    assert s.save(str(tmp_path / 'staffa.steelcad'))['ok']
    a = Service()
    a.new_assembly('Due staffe')
    assert a.asm_insert(str(tmp_path / 'staffa.steelcad'))['ok'] and a.asm_insert(str(tmp_path / 'staffa.steelcad'))['ok']
    campi = a.drawing_fields()['fields']
    p = a.drawing_preview(campi, False)
    assert p['ok'] and len(p['sheets']) == 1 and 'DISTINTA' in p['sheets'][0]['svg']
    p = a.drawing_preview(campi, True)
    assert [x['title'] for x in p['sheets']] == ['Due staffe', 'Staffa', 'Staffa — sviluppo']
    assert a.export_drawings(str(tmp_path / 'a.pdf'), campi, True)['ok']
    assert (tmp_path / 'a.pdf').read_bytes().count(b'/Type /Page ') == 3


def test_formati_e_scale():
    assert D.scala_testo(0.5) == '1:2' and D.scala_testo(1 / 2.5) == '1:2,5' and D.scala_testo(2) == '2:1'
    assert D._scegli_scala((300, 200), 150, 100) == 0.5
