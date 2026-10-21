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
    # l'assieme e la vista esplosa (22/10: «per far capire come si monta»)
    assert p['ok'] and len(p['sheets']) == 2 and 'DISTINTA' in p['sheets'][0]['svg']
    esp = p['sheets'][1]['svg']
    assert 'VISTA ESPLOSA' in esp and 'ORDINE DI MONTAGGIO' in esp and 'è la base' in esp
    p = a.drawing_preview(campi, True)
    assert [x['title'] for x in p['sheets']] == ['Due staffe', 'Due staffe — esploso', 'Staffa', 'Staffa — sviluppo']
    assert a.export_drawings(str(tmp_path / 'a.pdf'), campi, True)['ok']
    assert (tmp_path / 'a.pdf').read_bytes().count(b'/Type /Page ') == 4


def test_formati_e_scale():
    assert D.scala_testo(0.5) == '1:2' and D.scala_testo(1 / 2.5) == '1:2,5' and D.scala_testo(2) == '2:1'
    assert D._scegli_scala((300, 200), 150, 100) == 0.5


def test_tabella_pieghe_con_piega_su_linea():
    """Una piega su linea si chiama PL1: la tabella non deve scambiarla per un cono (colonne Angolo/Linea/Correz.)."""
    s = Service()
    assert s.new_project('lamiera', {'name': 'Carter', 'larghezza': 300, 'profondita': 200, 'spessore': 1.5,
                                     'raggio': 1, 'k': 0.21})['ok']
    sid = s.sketch_on_flat('SM1')['sketch']
    assert s.sketch_add_polyline(sid, [[-5, 150], [305, 150]], False)['ok']
    assert s.sheet_fold(sid, 90, 'up')['ok']
    p = s.drawing_preview()
    sviluppo = p['sheets'][1]['svg']
    assert 'PL1' in sviluppo and 'Flangia' in sviluppo and 'Correz.' not in sviluppo


def test_sviluppo_numeri_e_quote_delle_pieghe():
    """22/10: lo sviluppo con ogni linea di piega numerata come in tabella e le quote progressive dal bordo."""
    s = Service()
    assert s.new_project('lamiera', {'name': 'Vassoio', 'larghezza': 600, 'profondita': 300, 'spessore': 2, 'raggio': 1, 'k': 0.4})['ok']
    assert s.add_flange('SM1', 'L1', {'length': '30'})['ok']
    assert s.add_flange('SM1', 'L3', {'length': '40'})['ok']
    sd = s.result.body.sheet
    f = D.tavola_sviluppo(sd, {'titolo': 'V'}, [[str(i), g.fid, D.fmt(g.length), '90°', 'su', '1', '0,4', '600']
                                               for i, g in enumerate(sd.in_ordine(), 1)])
    testi = [t[2] for t in f.testi]
    assert 'TABELLA PIEGHE' in testi and 'Quota' in testi
    y0 = min(p[1] for pl in sd.outline() for p in zip(pl[::2], pl[1::2]))
    attese = sorted(D.fmt(a[1] - y0) for a, b, _ in sd.bend_lines)
    for q in attese:
        assert q in testi and any(t.endswith(' ' + q) for t in testi)        # sul disegno e in tabella (↑ …)
    assert sum(1 for c in f.cerchi if c[0] == 'piega') == len(sd.bend_lines)   # un cerchio col numero per linea
    assert not any(t.startswith('FL') and 'SU' in t for t in testi)            # niente scritte lunghe sulle linee
