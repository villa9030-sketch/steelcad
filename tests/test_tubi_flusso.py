"""Flusso nuovo delle strutture in tubolare (22/10, tela «SteelCAD tubi: flusso nuovo"): misure fuori tutto, nomi da
officina, angoli col disegnino anche su tutti gli angoli uguali, traverso tra due tubi, frecce, sagoma ripetuta."""
import build123d as bd
import pytest

from app.service import Service
from cad_engine import templates
from cad_engine.structures import cut_list


def _righe(r):
    return sorted((x['profile'], x['length_mm'], x['qty']) for x in cut_list(r.structures)['rows'])


def _fuori(st):
    b = bd.Compound([m.solid for m in st.members]).bounding_box()
    return [round(v, 3) for v in (b.size.X, b.size.Y, b.size.Z)]


def _nodo(s, xyz):
    return next(k for k, v in s.result.structures[0].nodes.items() if [round(c, 3) for c in v['xyz']] == xyz)


def _banco():
    s = Service()
    s._set(templates.telaio('Banco officina', L=1600, P=700, H=850, ripiano=150))
    return s


def test_banco_fuori_tutto_come_sulla_tela():
    s = _banco()
    st = s.result.structures[0]
    assert _fuori(st) == [1600, 700, 850] and st.warnings == []
    assert _righe(s.result) == [('30×30×2', 620.0, 2), ('30×30×2', 1520.0, 2), ('40×40×3', 620.0, 2),
                                ('40×40×3', 850.0, 4), ('40×40×3', 1520.0, 2)]
    rip = [m for m in st.members if m.group == 'Ripiano sotto']
    assert min(m.solid.bounding_box().min.Z for m in rip) == pytest.approx(150)      # il sotto del ripiano a 150
    assert s.struttura_cosa_fare('ST1')['fuori_tutto'] == [1600, 700, 850]


def test_nomi_da_officina():
    s = _banco()
    sel = s.select('ST1/M1')['selection']
    assert sel['title'] == 'Traverso davanti, in alto'
    assert sel['tubo']['contro'] == ['Gamba davanti a sinistra', 'Gamba davanti a destra']
    nomi = set(s.nomi_tubi(s.result.structures[0]).values())
    assert {'Gamba dietro a destra', 'Fianco a sinistra, a 150 da terra'} <= nomi
    assert s.select(f'ST1:{_nodo(s, [1600, 0, 850])}')['selection']['title'] == 'Angolo davanti a destra, in alto'
    assert not any('M1' in o['name'] or 'G1' in o['name'] for o in s.scene()['objects'] if o['kind'] == 'member')


def test_angoli_col_disegnino_su_tutti_gli_uguali():
    s = _banco()
    k = _nodo(s, [1600, 0, 850])
    a = s.angolo_info('ST1', k)
    assert [x['key'] for x in a['scelte']] == ['45', 'verticali', 'x', 'y'] and a['ora'] == 'verticali'
    assert a['simili'] == 4
    r = s.set_angolo('ST1', k, '45', tutti=True)
    assert r['ok'] and '4 angoli' in r['message']
    assert ('40×40×3', 1600.0, 2) in _righe(s.result) and ('40×40×3', 810.0, 4) in _righe(s.result)
    assert s.angolo_info('ST1', k)['ora'] == '45'
    assert s.set_angolo('ST1', k, 'x', tutti=True)['ok']                 # passa il traverso
    assert ('40×40×3', 1600.0, 2) in _righe(s.result) and ('40×40×3', 620.0, 2) in _righe(s.result)
    assert _fuori(s.result.structures[0]) == [1600, 700, 850]


def test_traverso_tra_le_gambe_anche_dietro():
    s = _banco()
    r = s.add_traverso('ST1', 'G1', 'G2', 400, 'sotto', '40x40x3', opposto=True)
    assert r['ok'] and r['message'] == '2 traversi aggiunti.'
    st = s.result.structures[0]
    nuovi = [m for m in st.members if m.group == 'Traversi']
    assert len(nuovi) == 2 and st.warnings == []
    assert all(m.length == pytest.approx(1520) for m in nuovi)
    assert all(m.solid.bounding_box().min.Z == pytest.approx(400) for m in nuovi)     # il sotto a 400 da terra
    assert {s.nomi_tubi(st)[m.id] for m in nuovi} == {'Traverso davanti, a 400 da terra', 'Traverso dietro, a 400 da terra'}
    assert not s.add_traverso('ST1', 'G1', 'G2', 900)['ok']                         # oltre la gamba


def test_mensola_con_le_frecce():
    s = _banco()
    s.set_angolo('ST1', _nodo(s, [0, 0, 850]), '45', tutti=True)
    r = s.tubo_da_angolo('ST1', _nodo(s, [0, 0, 850]), 'sinistra', 300, None, 'Mensola')
    assert r['ok'] and 'la gamba passa' in r['message']
    st = s.result.structures[0]
    mensola = next(m for m in st.members if m.nome == 'Mensola')
    assert mensola.length == pytest.approx(300) and st.warnings == []
    assert s.nomi_tubi(st)[mensola.id] == 'Mensola'
    b = bd.Compound([m.solid for m in st.members]).bounding_box()
    assert b.min.X == pytest.approx(-300) and b.max.Z == pytest.approx(850)


def test_da_zero_con_le_frecce():
    s = Service()
    assert s.new_project('vuoto', {'name': 'Telaio'})['ok']
    r = s.tubo_da_angolo('ST1', 'A', 'destra', 1600, '40x40x3')
    assert r['ok']
    r = s.tubo_da_angolo('ST1', r['node'].split(':')[1], 'dietro', 700)
    assert r['ok']
    st = s.result.structures[0]
    assert _fuori(st) == [1600, 700, 40]                 # sul pavimento, dentro la sagoma
    assert set(s.nomi_tubi(st).values()) == {'Traverso davanti', 'Fianco a destra'}


def test_sagoma_ripetuta_dietro_e_collegata():
    s = Service()
    assert s.new_project('disegno', {'name': 'Scaffale cantina', 'piano': 'XZ'})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    sk = s.doc.sketch(sid)
    a, b, c, d = sk.point(0, 0), sk.point(600, 0), sk.point(600, 2000), sk.point(0, 2000)
    e, f = sk.point(0, 800), sk.point(600, 800)
    sk.line(a, e), sk.line(e, d), sk.line(b, f), sk.line(f, c), sk.line(d, c), sk.line(e, f)
    s._rebuild()
    r = s.fai_tubi(sid, {'profile': '30x30x2', 'ripeti': True, 'distanza': 1000, 'collega': True,
                         'collega_profile': '40x20x2'})
    assert r['ok'], r.get('message')
    st = s.result.structures[0]
    assert _fuori(st) == [600, 1000, 2000] and st.warnings == []
    b = bd.Compound([m.solid for m in st.members]).bounding_box()
    assert b.min.Y == pytest.approx(0)                    # ripetuta dietro (verso +Y), non davanti
    assert sum(1 for m in st.members if m.group == 'Collegamenti') == 6


def test_tubo_unico_o_diviso_nell_angolo():
    """23/10, screenshot di Stefano: il traverso spezzato dalla gamba nel mezzo → «tubo unico lungo sopra e la gamba
    sotto»; e il contrario, «Passa la gamba», lo ridivide."""
    s = Service()
    s.new_project('vuoto', {'name': 'T'})
    r = s.tubo_da_angolo('ST1', 'A', 'su', 500, '40x40x3')
    r = s.tubo_da_angolo('ST1', r['node'].split(':')[1], 'destra', 500)
    mezzo = r['node'].split(':')[1]
    for d in ('destra', 'giu', 'dietro'):              # traverso che continua, gamba sotto, fianco: 4 tubi qui
        assert s.tubo_da_angolo('ST1', mezzo, d, 500)['ok']
    assert s.result.structures[0].warnings == []
    a = s.angolo_info('ST1', mezzo)
    assert ('unisci:x', 'Passa il traverso, tubo unico') in [(x['key'], x['label']) for x in a['scelte']]
    r = s.set_angolo('ST1', mezzo, 'unisci:x')
    assert r['ok']
    assert ('40×40×3', 1000.0, 1) in _righe(s.result) and s.result.structures[0].warnings == []
    a = s.angolo_info('ST1', mezzo)
    assert [x['key'] for x in a['scelte']] == ['unico', 'dividi'] and a['ora'] == 'unico'
    assert s.set_angolo('ST1', mezzo, 'dividi')['ok']
    assert not any(x[1] == 1000.0 for x in _righe(s.result)) and s.result.structures[0].warnings == []
    s.undo()
    assert ('40×40×3', 1000.0, 1) in _righe(s.result)


def test_montante_dello_scaffale_diviso_ai_piani():
    s = Service()
    s._set(templates.scaffale())
    st = s.result.structures[0]
    k = next(k for k, v in st.nodes.items() if 500 < v['xyz'][2] < 700 and abs(v['xyz'][0]) < 1e-6 and abs(v['xyz'][1]) < 1e-6)
    a = s.angolo_info('ST1', k)
    assert [x['key'] for x in a['scelte']] == ['unico', 'dividi']
    assert s.set_angolo('ST1', k, 'dividi')['ok']
    st = s.result.structures[0]
    assert st.warnings == [] and _fuori(st) == [1000, 400, 1800]
