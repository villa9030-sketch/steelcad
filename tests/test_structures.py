"""GATE della Milestone 2 (motore): scheletro → 40×40×3 → tubolari → gambe → tagli automatici →
modifica dimensioni → rigenerazione → BOM → cut list → STEP. Più catalogo profili e giunti."""
import math

import pytest

from cad_engine import Document, History, project_io
from cad_engine.bom import bom, total_kg
from cad_engine.errors import SteelCADError
from cad_engine.exporters import step
from cad_engine.profiles import parse
from cad_engine.structures import cut_list, frame
from cad_engine.tree import as_text, project_tree


# ------------------------------------------------------------ catalogo
@pytest.mark.parametrize('nome, area_cm2, kg_m', [
    ('40x40x3', 4.21, 3.30),          # EN 10219-2
    ('60x40x3', 5.41, 4.25),
    ('Ø48.3x3.2', 4.53, 3.56),
    ('piatto 50x5', 2.50, 1.96),
    ('L 40x40x4', 3.08, 2.42),        # EN 10056-1
    ('L 50x50x5', 4.80, 3.77),
    ('IPE 100', 10.3, 8.10),          # EN 10365
    ('IPE 200', 28.5, 22.4),
    ('HEA 100', 21.2, 16.7),
    ('HEB 200', 78.1, 61.3),
])
def test_aree_e_pesi_come_le_tabelle(nome, area_cm2, kg_m):
    p = parse(nome)
    # le tabelle arrotondano: aree con 2 cifre significative dopo la virgola sotto i 10 cm², 1 sopra
    tol = 0.006 if area_cm2 < 10 else 0.05
    assert p.area_mm2 / 100 == pytest.approx(area_cm2, abs=tol)
    assert p.kg_m(7.85) == pytest.approx(kg_m, abs=0.05)


def test_profili_piegati_area_dalla_linea_media():
    p = parse('U 80x40x3')         # raggio interno = spessore
    t, ri = 3, 3
    media = 2 * (40 - ri - t) + (80 - 2 * (ri + t)) + 2 * (math.pi / 2) * (ri + t / 2)
    assert p.area_mm2 == pytest.approx(media * t, rel=1e-9)
    assert parse('70x70x4').family == 'SHS' and parse('60x40x3').family == 'RHS'


def test_profili_scritti_male():
    for testo in ('40x40', 'IPE 105', 'L 33x33x3', '40x40x25', 'tubo', 'Ø20x12'):
        with pytest.raises(SteelCADError):
            parse(testo)


# ----------------------------------------------------- tavolo (gate)
def tavolo(gambe='40x40x3'):
    doc = Document('Tavolo officina')
    h = History(doc)
    with h.change('Misure'):
        for k, v in (('L', 2000), ('P', 1000), ('H', 900)):
            doc.set_parameter(k, v)
    with h.change('Scheletro'):
        sk = doc.add_sketch('XY', 'Scheletro')
        r = sk.rectangle(0, 0, 1900, 950)
        sk.constrain('coincident', r['corners'][0], 'O')
        sk.dimension('length', r['bottom'], value='L')
        sk.dimension('length', r['left'], value='P')
        pts = {f'T{i}': {'sketch': sk.id, 'point': c, 'offset': [0, 0, 'H']} for i, c in enumerate(r['corners'])}
        pts.update({f'F{i}': {'sketch': sk.id, 'point': c} for i, c in enumerate(r['corners'])})
        mem = [{'id': f'M{i + 1}', 'group': 'Telaio superiore', 'from': f'T{i}', 'to': f'T{(i + 1) % 4}',
                'profile': '40x40x3'} for i in range(4)]
        mem += [{'id': f'G{i + 1}', 'group': 'Gambe', 'from': f'F{i}', 'to': f'T{i}', 'profile': gambe}
                for i in range(4)]
        st = doc.add_feature('structure', 'Telaio tavolo', points=pts, members=mem)
    return doc, h, st


def righe(cl):
    return [(r['profile'], r['qty'], r['length_mm'], tuple(r['cuts'])) for r in cl['rows']]


def test_gate_milestone_2(tmp):
    doc, h, st = tavolo()
    res = doc.rebuild()
    assert res.ok, [f.message for f in res.errors]
    cl = cut_list(res.structures)
    # telaio centrato sullo scheletro: traverse 2000 + 40 all'esterno, tagli a 45°; gambe sotto il telaio
    assert righe(cl) == [('40×40×3', 2, 2040.0, ('45°', '45°')), ('40×40×3', 2, 1040.0, ('45°', '45°')),
                         ('40×40×3', 4, 880.0, ('dritto', 'dritto'))]
    a = parse('40x40x3').area_mm2
    assert cl['totals'][0]['total_length_mm'] == pytest.approx(2 * 2040 + 2 * 1040 + 4 * 880)
    assert cl['kg'] == pytest.approx(a * 7.85 / 1e6 * (2 * 2040 + 2 * 1040 + 4 * 880), rel=1e-9)
    # i solidi sono veri: volume delle traverse = area × lunghezza d'asse (i 45° si compensano)
    m1 = res.structures[0].members[0]
    assert m1.solid.is_valid and m1.solid.volume == pytest.approx(a * 2000, rel=1e-9)
    assert not res.structures[0].warnings

    # modifica delle dimensioni: si rigenera tutto ciò che dipende
    with h.change('Tavolo 2200 × 800 × 750'):
        doc.set_parameter('L', 2200)
        doc.set_parameter('P', 800)
        doc.set_parameter('H', 750)
    res = doc.rebuild()
    assert righe(cut_list(res.structures)) == [
        ('40×40×3', 2, 2240.0, ('45°', '45°')), ('40×40×3', 2, 840.0, ('45°', '45°')),
        ('40×40×3', 4, 730.0, ('dritto', 'dritto'))]

    # BOM e albero in linguaggio da officina
    b = bom(doc, res)
    assert [(r['code'], r['qty'], r['length_mm']) for r in b] == [('A1', 2, 2240.0), ('A2', 2, 840.0),
                                                                   ('A3', 4, 730.0)]
    assert total_kg(b) == pytest.approx(cut_list(res.structures)['kg'])
    testo = as_text(project_tree(doc, res))
    assert 'TAVOLO OFFICINA' in testo and '4 × 40×40×3 — 730' in testo and 'Telaio superiore' in testo

    # STEP con un solido per asta, stesso volume rileggendo
    out = step.export_project(doc, res, tmp / 'tavolo.step')
    assert out['solids'] == 8

    # undo torna al tavolo 2000 × 1000 × 900
    h.undo()
    assert righe(cut_list(doc.rebuild().structures))[0] == ('40×40×3', 2, 2040.0, ('45°', '45°'))
    # e il progetto salvato si riapre uguale
    doc2 = project_io.load(project_io.save(doc, tmp / 'tavolo'))
    assert righe(cut_list(doc2.rebuild().structures)) == righe(cut_list(doc.rebuild().structures))


def test_gambe_piu_larghe_del_telaio_tagliate_sotto():
    doc, _, _ = tavolo(gambe='70x70x4')
    rows = righe(cut_list(doc.rebuild().structures))
    assert ('70×70×4', 4, 880.0, ('dritto', 'dritto')) in rows


def test_si_ricostruiscono_solo_le_aste_toccate():
    doc, _, _ = tavolo()
    doc.rebuild()
    frame.STATS['members_built'] = 0
    doc.set_parameter('L', 2300)
    doc.rebuild()
    # si muovono la traversa sotto, quella destra, quella sopra e le due gambe a destra: 5 aste su 8
    assert frame.STATS['members_built'] == 5
    frame.STATS['members_built'] = 0
    doc.rebuild()
    assert frame.STATS['members_built'] == 0


def _struttura(points, members, joints=None):
    return frame.build({'id': 'ST1', 'name': 'Prova', 'points': points, 'members': members,
                        'joints': joints or {}}, {})


def test_taglio_sulla_bisettrice_con_angolo_qualsiasi():
    a, b = (0, 0, 0), (1000, 0, 0)
    c = (1000 + 1000 * math.cos(math.radians(120)), 1000 * math.sin(math.radians(120)), 0)
    r = _struttura({'A': a, 'B': b, 'C': list(c)},
                   [{'id': 'M1', 'from': 'A', 'to': 'B', 'profile': '40x40x3'},
                    {'id': 'M2', 'from': 'B', 'to': 'C', 'profile': '40x40x3'}])
    m1, m2 = r.members
    # due aste che formano un angolo interno di 60°: il taglio è a 60° dalla perpendicolare all'asse
    assert m1.cuts[1] == pytest.approx(60, abs=1e-6) and m2.cuts[0] == pytest.approx(60, abs=1e-6)
    assert m1.cuts[0] == 0
    assert m1.solid.volume == pytest.approx(parse('40x40x3').area_mm2 * 1000, rel=1e-9)


def test_giunto_a_t_e_tubo_tondo_a_sella():
    r = _struttura({'A': [0, 0, 0], 'B': [1000, 0, 0], 'P': [500, 0, 0], 'Q': [500, 500, 0]},
                   [{'id': 'T', 'from': 'A', 'to': 'B', 'profile': 'Ø60.3x3'},
                    {'id': 'S', 'from': 'P', 'to': 'Q', 'profile': 'Ø33.7x2.6'}])
    s = r.members[1]
    # taglio a sella: il punto più lungo è dove il bordo del tubo piccolo (r 16,85) tocca il tubo grande
    # (R 30,15), cioè a sqrt(R² - r²) dall'asse; il più corto è sull'asse, a R
    R, rr = 60.3 / 2, 33.7 / 2
    assert s.length == pytest.approx(500 - math.sqrt(R * R - rr * rr), abs=1e-3)
    assert s.solid.is_valid


def test_giunto_a_battuta_a_mano():
    pts = {'A': [0, 0, 0], 'B': [1000, 0, 0], 'C': [1000, 600, 0]}
    mem = [{'id': 'M1', 'from': 'A', 'to': 'B', 'profile': '40x40x3'},
           {'id': 'M2', 'from': 'B', 'to': 'C', 'profile': '40x40x3'}]
    r = _struttura(pts, mem, {'B': {'type': 'butt', 'through': ['M1']}})
    m1, m2 = r.members
    assert m1.length == pytest.approx(1020) and m1.cuts == (0, 0)     # M1 passa e arriva al filo esterno
    assert m2.length == pytest.approx(580) and m2.cuts == (0, 0)      # M2 batte contro M1


def test_ancoraggio_rotazione_e_peso():
    r = _struttura({'A': [0, 0, 0], 'B': [1000, 0, 0]},
                   [{'id': 'M1', 'from': 'A', 'to': 'B', 'profile': '60x40x3', 'anchor': 'bottom'}])
    bb = r.members[0].solid.bounding_box()
    assert bb.min.Z == pytest.approx(0) and bb.max.Z == pytest.approx(60)     # appoggiato sotto la linea
    r = _struttura({'A': [0, 0, 0], 'B': [1000, 0, 0]},
                   [{'id': 'M1', 'from': 'A', 'to': 'B', 'profile': '60x40x3', 'rotate': 90}])
    bb = r.members[0].solid.bounding_box()
    assert bb.size.Z == pytest.approx(40) and bb.size.Y == pytest.approx(60)  # ruotato: alto 40
    assert r.members[0].kg() == pytest.approx(parse('60x40x3').kg_m(7.85))


def test_errori_chiari():
    with pytest.raises(SteelCADError, match='lunghezza zero'):
        _struttura({'A': [0, 0, 0]}, [{'id': 'M1', 'from': 'A', 'to': 'A', 'profile': '40x40x3'}])
    with pytest.raises(SteelCADError, match='non esiste'):
        _struttura({'A': [0, 0, 0]}, [{'id': 'M1', 'from': 'A', 'to': 'Z', 'profile': '40x40x3'}])
    with pytest.raises(SteelCADError, match='Non capisco il profilo'):
        _struttura({'A': [0, 0, 0], 'B': [1, 0, 0]}, [{'id': 'M1', 'from': 'A', 'to': 'B', 'profile': 'boh'}])


def test_aste_che_si_compenetrano_segnalate():
    r = _struttura({'A': [0, 0, 0], 'B': [1000, 0, 0], 'C': [500, -300, 0], 'D': [500, 300, 0]},
                   [{'id': 'M1', 'from': 'A', 'to': 'B', 'profile': '40x40x3', 'anchor': 'bottom'},
                    {'id': 'M2', 'from': 'C', 'to': 'D', 'profile': '40x40x3', 'anchor': 'bottom'}])
    assert any('si compenetrano' in w for w in r.warnings)
