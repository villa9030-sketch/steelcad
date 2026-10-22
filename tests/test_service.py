"""Lo strato applicativo che usa l'interfaccia: solo dati JSON, errori chiari, undo."""
import json
import math

import pytest

from app.service import Service
from cad_engine.mesh import tessellate
from cad_engine import templates


def _tavolo():
    s = Service()
    assert s.new_project('telaio', {'name': 'Tavolo officina'})['ok']
    return s


def test_si_parte_dalla_pagina_iniziale_e_i_recenti(tmp_path):
    """Appena aperto non c'è un progetto di esempio: la UI mostra la pagina iniziale. Aprire o salvare mette il
    file nei recenti (in cima), un file che non esiste più non si mostra."""
    s = Service()
    info = s.home_info()
    assert info['show'] and s.result.body is None and not s.result.structures
    assert s.new_project('lamiera', {'name': 'A', 'larghezza': 100, 'profondita': 50, 'spessore': 2, 'raggio': 2, 'k': 0.4})['ok']
    assert not s.home_info()['show']
    a, b = tmp_path / 'a.steelcad', tmp_path / 'b.steelcad'
    assert s.save(str(a))['ok'] and s.save(str(b))['ok']
    assert [r['name'] for r in s.home_info()['recent']][:2] == ['b', 'a']
    s2 = Service()
    assert s2.open(str(a))['ok']
    assert [r['name'] for r in s2.home_info()['recent']][:2] == ['a', 'b']
    b.unlink()
    assert [r['name'] for r in s2.home_info()['recent']] == ['a']
    assert s2.forget_recent(str(a))['recent'] == []


def test_stato_e_scena_sono_json():
    s = _tavolo()
    st = s.state()
    json.dumps(st)
    sc = s.scene()
    json.dumps(sc)
    assert len(sc['objects']) == 8
    o = sc['objects'][0]
    assert len(o['positions']) % 3 == 0 and max(o['indices']) < len(o['positions']) // 3
    assert sum(f['count'] for f in o['faces']) == len(o['indices'])


def test_mesh_piastra_con_nomi_di_faccia():
    d = templates.piastra()
    r = d.rebuild()
    m = tessellate(r.body.shape, r.body.names)
    assert len(m['faces']) == 7                     # 2 grandi, 4 fianchi, il foro
    assert all(f['name'] for f in m['faces'])
    assert m['edges']


def test_quote_sul_modello_e_modifica():
    s = _tavolo()
    dims = {d['param']: d for d in s.state()['dimensions']}
    assert set(dims) == {'L', 'P'} and dims['L']['value'] == 2000
    r = s.set_dimension(dims['L']['sketch'], dims['L']['dim'], '2200')
    assert r['ok']
    lung = [x['length_mm'] for x in r['state']['cutlist']['rows']]
    assert 2120 in lung                              # fuori tutto: 2200 − 2 gambe da 40
    assert r['state']['undo'] == ['L = 2200']
    s.undo()
    assert 1920 in [x['length_mm'] for x in s.state()['cutlist']['rows']]


def test_modifica_asta_di_gruppo_e_rotazione():
    s = _tavolo()
    r = s.edit_member('ST1/G1', {'profile': '60x40x3'}, whole_group=True)
    assert r['ok']
    gambe = [x for x in r['state']['cutlist']['rows'] if x['groups'] == ['Gambe']]
    assert gambe[0]['qty'] == 4 and '60' in gambe[0]['profile']
    r = s.edit_member('ST1/G1', {'rotate_by': 90})
    assert r['ok']
    assert s.doc.feature('ST1')['members'][4]['rotate'] == 90


def test_errori_chiari_non_rompono_il_progetto():
    s = Service()
    prima = s.state()['bom_kg']
    r = s.set_parameter('P', 'P*2')
    assert not r['ok'] and 'sé stesso' in r['message']
    r = s.edit_member('ST1/M1', {'profile': '40x40'})
    assert not r['ok'] and r['message']
    assert s.state()['bom_kg'] == prima
    assert s.state()['undo'] == []


def test_dxf_solo_per_piastra(tmp_path):
    s = Service()
    r = s.export_dxf(str(tmp_path / 'x.dxf'))
    assert not r['ok'] and 'cut list' in r['message']
    s.new_project('piastra', {'larghezza': '250'})
    r = s.export_dxf(str(tmp_path / 'p.dxf'))
    assert r['ok'] and '250' in r['message']
    r = s.export_step(str(tmp_path / 'p.step'))
    assert r['ok']


def test_salva_apri(tmp_path):
    s = Service()
    s.set_parameter('H', 800)
    p = tmp_path / 't.steelcad'
    assert s.save(str(p))['ok'] and not s.state()['dirty']
    s2 = Service()
    assert s2.open(str(p))['ok']
    assert next(x for x in s2.state()['parameters'] if x['name'] == 'H')['value'] == 800


def _cancello():
    s = Service()
    s.new_project('vuoto', {'name': 'Cancello'})
    assert s.add_member('ST1', 'A', direction='Z+', length=1000, profile='40x40x3', group='Montanti')['ok']
    assert s.add_member('ST1', 'N1', direction='X+', length='B', group='Traversi')['ok'] is False  # B non esiste
    s.set_parameter('B', 1500)
    assert s.add_member('ST1', 'N1', direction='X+', length='B', group='Traversi')['ok']
    assert s.add_member('ST1', 'N2', direction='Z-', length=1000, group='Montanti')['ok']
    r = s.add_member('ST1', 'N3', to_key='A', group='Traversi')
    assert r['ok'] and r['select'] == 'ST1/M4' and r['node'] == 'ST1:A'
    return s


def test_scheletro_da_zero_e_parametrico():
    s = _cancello()
    righe = sorted((x['length_mm'], tuple(x['cuts']), x['qty']) for x in s.state()['cutlist']['rows'])
    assert righe == [(1000.0, ('45°', '45°'), 2), (1500.0, ('45°', '45°'), 2)]     # fuori tutto (22/10)
    s.set_parameter('B', 2000)                       # i nodi seguono il parametro
    assert sorted(x['length_mm'] for x in s.state()['cutlist']['rows']) == [1000.0, 2000.0]
    assert {n['key'] for n in s.scene()['nodes']} == {'A', 'N1', 'N2', 'N3'}


def test_giunti_dal_pannello():
    s = _cancello()
    sel = s.select('ST1:N1')['selection']
    assert set(sel['joint_types']) == {'auto', 'square', 'miter', 'butt', 'angle'}
    assert not s.set_joint('ST1', 'N1', {'type': 'butt'})['ok']             # manca chi passa
    assert not s.set_joint('ST1', 'N1', {'type': 'butt', 'through': ['M1', 'M2']})['ok']
    assert s.set_joint('ST1', 'N1', {'type': 'butt', 'through': ['M2']})['ok']
    tagli = {x['length_mm']: x['cuts'] for x in s.state()['cutlist']['rows']}
    assert 'dritto' in tagli[960.0]                  # il montante batte sotto il traverso (1000 − 40)
    assert s.set_joint('ST1', 'N1', {'type': 'auto'})['ok']
    assert 'N1' not in (s.doc.feature('ST1').get('joints') or {})


def test_elimina_e_modifiche_che_rompono():
    s = _cancello()
    assert s.delete_members(['ST1/M2'])['ok']
    assert s.state()['cutlist']['pieces'] == 3
    s.undo()
    r = s.move_node('ST1', 'N1', [0, 0, 0])           # N1 sopra A: asta lunga zero
    assert not r['ok'] and r['message'].startswith('Non applicato')
    assert s.state()['cutlist']['pieces'] == 4 and s.state()['errors'] == []
    assert not s.add_member('ST1', 'A', to_key='N1')['ok']                   # c'è già


def test_nuovo_progetto_cambia_sempre_la_scena():
    """Bug 16/10: appena aperta l'app (versione 1) un progetto nuovo ripartiva da 1 e la UI non ridisegnava."""
    s = Service()
    v = s.state()['scene_version']
    r = s.new_project('piastra', {})
    assert r['state']['scene_version'] > v
    assert s.new_project('zero', {})['state']['scene_version'] > r['state']['scene_version']


def test_lamiera_da_zero_disegnata():
    s = Service()
    s.new_project('zero', {'name': 'Staffa'})
    # una L: si parte dall'origine, l'ultimo tratto torna all'origine
    r = s.sketch_add_polyline('S1', ['O', [300, 0], [300, 100], [120, 100], [120, 250], [0, 250]], True)
    v = s.sketch_view('S1')['sketch']
    assert r['ok'] and v['ok'] and 'completamente' in v['status']
    assert sorted(d['label'] for d in s.state()['dimensions']) == ['100', '150', '180', '300']
    assert s.sketch_add_circle('S1', [60, 50], 7)['ok']
    r = s.create_from_sketch('S1', 'sheet', {'thickness': 3, 'radius': 3, 'k': 0.42})
    assert r['ok']
    assert s.add_flange('SM1', 'L1', {'length': 40})['ok']
    d = next(x for x in s.state()['dimensions'] if x['label'] == '300')
    assert s.set_dimension(d['sketch'], d['dim'], 350)['ok']
    import build123d as bd
    assert bd.Solid(s.result.body.shape).bounding_box().size.X == 350


def test_disegno_aperto_poi_chiuso_senza_quote_doppie():
    s = Service()
    s.new_project('zero', {})
    assert s.sketch_add_polyline('S1', ['O', [100, 0], [100, 60]], False)['ok']
    assert not s.create_from_sketch('S1', 'plate', {'thickness': 5})['ok']       # aperto: prima chiudi
    ultimo = s.sketch_view('S1')['sketch']['points'][-1]['id']
    assert s.sketch_add_polyline('S1', [ultimo, [0, 60], 'O'], False)['ok']
    v = s.sketch_view('S1')['sketch']
    assert v['ok'] and 'completamente' in v['status']                            # niente quote doppie
    assert s.create_from_sketch('S1', 'plate', {'thickness': 5})['ok']
    assert s.state()['bom'][0]['type'] == 'piastra'


def test_rettangolo_cerchio_elimina():
    s = Service()
    s.new_project('zero', {})
    assert s.sketch_add_rectangle('S1', 'O', [200, 120])['ok']
    assert s.sketch_add_circle('S1', [50, 60], 5)['ok']
    v = s.sketch_view('S1')['sketch']
    assert 'completamente' in v['status'] and len(v['circles']) == 1
    assert s.sketch_delete('S1', [v['circles'][0]['id']])['ok']
    v = s.sketch_view('S1')['sketch']
    assert v['circles'] == [] and 'completamente' in v['status']
    assert len(v['points']) == 5                                                 # 4 angoli + origine


def _lamiera_con_parete():
    s = Service()
    s.new_project('lamiera', {'name': 'S', 'larghezza': 400, 'profondita': 300, 'spessore': 2, 'raggio': 2, 'k': 0.5})
    assert s.add_flange('SM1', 'L1', {'length': '60'})['ok']
    return s


def test_sulla_faccia_ci_sono_i_bordi_del_pezzo_e_ci_si_fa_l_offset():
    """Disegnando su una faccia, i suoi bordi entrano come guide fisse: offset 10 dal bordo e taglio."""
    s = _lamiera_con_parete()
    sid = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    v = s.sketch_view(sid)['sketch']
    bordi = [l['id'] for l in v['lines'] if l['label'] == 'bordo del pezzo']
    assert len(bordi) == 4 and all(l['construction'] for l in v['lines'])
    assert 'completamente vincolato' in v['status']
    assert s.sketch_offset(sid, bordi, 10, 'in')['ok']
    v0 = s.state()['info']['part']['volume_mm3']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    # la faccia esterna dritta di FL1 è 400 × 56 (60 − setback 4): la finestra è (400 − 20) × (56 − 20), sp. 2
    assert v0 - s.state()['info']['part']['volume_mm3'] == pytest.approx(380 * 36 * 2, rel=1e-9)


def test_sketch_vuoto_su_faccia_sparisce():
    s = _lamiera_con_parete()
    sid = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    s.sketch_close(sid)
    assert all(not hasattr(f, 'entities') or f.id != sid for f in s.doc.features)


def test_linea_con_angolo_scritto_resta_a_quell_angolo():
    s = Service()
    s.new_project('zero', {'name': 'P'})
    c, sn = math.cos(math.radians(30)), math.sin(math.radians(30))
    assert s.sketch_add_polyline('S1', [[0, 0], [100, 0], [100 + 80 * c, 80 * sn]], False, False, [None, 30])['ok']
    sk = s.doc.sketch('S1')
    did = next(k for k, x in sk.constraints.items() if x['type'] == 'length' and x['value'] == 80)
    assert s.set_dimension('S1', did, 150)['ok']
    l = [x for x in s.sketch_view('S1')['sketch']['lines'] if not x['construction']][1]
    (ax, ay), (bx, by) = l['xa'], l['xb']
    assert math.degrees(math.atan2(by - ay, bx - ax)) == pytest.approx(30, abs=1e-6)
    assert math.dist(l['xa'], l['xb']) == pytest.approx(150, abs=1e-6)


def test_offset_dalla_parte_del_mouse():
    """Come in AutoCAD: il lato dell'offset è quello dove clicchi."""
    s = Service()
    s.new_project('zero', {'name': 'P'})
    assert s.sketch_add_rectangle('S1', [0, 0], [200, 100])['ok']
    lati = [k for k, e in s.doc.sketch('S1').entities.items() if e['kind'] == 'line']
    assert s.sketch_offset_side('S1', lati, 10, [100, 50])['side'] == 'in'
    assert s.sketch_offset_side('S1', lati, 10, [100, 130])['side'] == 'out'
    linea = [lati[0]]
    a, b = (s.doc.sketch('S1').entities[s.doc.sketch('S1').entities[linea[0]][k]] for k in ('a', 'b'))
    sopra = s.sketch_offset_side('S1', linea, 10, [100, 30])['preview']['lines'][0]
    sotto = s.sketch_offset_side('S1', linea, 10, [100, -30])['preview']['lines'][0]
    assert sopra[0][1] == pytest.approx(10) and sotto[0][1] == pytest.approx(-10)


def test_sketch_su_faccia_assi_come_lo_schermo_e_origine_nell_angolo():
    """Sulla faccia esterna di una parete: X a destra, Y in su, (0;0) nell'angolo in basso a sinistra,
    e le quote del disegno ci sono (si vedono con lo sketch aperto)."""
    s = _lamiera_con_parete()
    sid = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    v = s.sketch_view(sid)['sketch']
    assert v['x_dir'] == pytest.approx([1, 0, 0], abs=1e-9) and v['y_dir'] == pytest.approx([0, 0, 1], abs=1e-9)
    assert v['origin'] == pytest.approx([0, 0, 4], abs=1e-9)       # il tratto dritto comincia a 4 (R + sp)
    assert v['where'].startswith('sulla faccia esterna')
    assert s.sketch_add_rectangle(sid, [50, -5], [150, -25])['ok']   # sotto l'origine: quote negative
    quote = [d for d in s.state()['dimensions'] if d['sketch'] == sid]
    assert quote and all(d['local'] for d in quote)
    neg = next(d for d in quote if d['type'] == 'vdistance')
    assert neg['value'] < 0 and not neg['label'].startswith('-')
    assert s.set_dimension(sid, neg['dim'], 30)['ok']                 # scritta positiva: resta sotto
    assert next(d for d in s.state()['dimensions'] if d['dim'] == neg['dim'] and d['sketch'] == sid)['value'] == -30


def _linee(s, sid='S1'):
    return {l['id']: (tuple(l['xa']), tuple(l['xb'])) for l in s.sketch_view(sid)['sketch']['lines'] if not l['construction']}


def test_taglia_come_autocad():
    """Taglia: il pezzo cliccato si toglie fino alle intersezioni più vicine; senza intersezioni sparisce."""
    s = Service()
    s.new_project('zero', {'name': 'P'})
    assert s.sketch_add_rectangle('S1', [0, 0], [100, 50])['ok']
    assert s.sketch_add_polyline('S1', [[20, 20], [20, 80]], False)['ok']
    L = max(_linee(s), key=lambda k: int(k[1:]))
    assert s.sketch_trim_preview('S1', L, [20, 70])['remove'] == [pytest.approx([20, 50]), pytest.approx([20, 80])]
    assert s.sketch_trim('S1', L, [20, 70])['ok']
    a, b = _linee(s)[L]
    assert sorted([a[1], b[1]]) == pytest.approx([20, 50])
    # il lato di sopra tagliato tra due linee: restano i due pezzi, allineati
    alto = next(k for k, (p, q) in _linee(s).items() if abs(p[1] - 50) < 1e-6 and abs(q[1] - 50) < 1e-6)
    assert s.sketch_trim('S1', alto, [60, 50])['ok']
    pezzi = [v for v in _linee(s).values() if abs(v[0][1] - 50) < 1e-6 and abs(v[1][1] - 50) < 1e-6]
    assert sorted(sorted([p[0], q[0]]) for p, q in pezzi) == [pytest.approx([0, 20]), pytest.approx([100, 100])] or \
        len(pezzi) == 1
    # una linea che non incontra niente si cancella
    assert s.sketch_add_polyline('S1', [[200, 0], [250, 0]], False)['ok']
    sola = max(_linee(s), key=lambda k: int(k[1:]))
    assert s.sketch_trim('S1', sola, [220, 0])['ok'] and sola not in _linee(s)


def test_taglia_cerchio_diventa_arco_e_il_contorno_si_chiude():
    """Un rettangolo con un cerchio sull'angolo: tagliando le parti interne resta un contorno con l'arco."""
    s = Service()
    s.new_project('zero', {'name': 'P'})
    assert s.sketch_add_rectangle('S1', [0, 0], [100, 50])['ok']
    assert s.sketch_add_circle('S1', [100, 50], 20)['ok']
    C = next(k for k, e in s.doc.sketch('S1').entities.items() if e['kind'] == 'circle')
    assert s.sketch_trim('S1', C, [85, 40])['ok']          # via il quarto dentro al rettangolo
    v = s.sketch_view('S1')['sketch']
    assert not v['circles'] and len(v['arcs']) == 1 and v['arcs'][0]['r'] == pytest.approx(20)
    # ora si tolgono i pezzi di lato che restano dentro l'arco: contorno chiuso con l'arco
    destro = next(k for k, (p, q) in _linee(s).items() if abs(p[0] - 100) < 1e-6 and abs(q[0] - 100) < 1e-6)
    assert s.sketch_trim('S1', destro, [100, 40])['ok']
    alto = next(k for k, (p, q) in _linee(s).items() if abs(p[1] - 50) < 1e-6 and abs(q[1] - 50) < 1e-6)
    assert s.sketch_trim('S1', alto, [90, 50])['ok']
    v = s.sketch_view('S1')['sketch']
    assert v['ok'] and v['profiles'] == 1, v['status']


def test_allunga_come_autocad():
    s = Service()
    s.new_project('zero', {'name': 'P'})
    assert s.sketch_add_rectangle('S1', [0, 0], [100, 50])['ok']
    assert s.sketch_add_polyline('S1', [[40, 10], [60, 10]], False)['ok']
    L = max(_linee(s), key=lambda k: int(k[1:]))
    assert s.sketch_extend_preview('S1', L, [58, 10])['add'] == [pytest.approx([60, 10]), pytest.approx([100, 10])]
    assert s.sketch_extend('S1', L, [58, 10])['ok']
    assert sorted(p[0] for p in _linee(s)[L]) == pytest.approx([40, 100])
    assert s.sketch_extend('S1', L, [42, 10])['ok']                  # e dall'altra parte, fino al lato sinistro
    assert sorted(p[0] for p in _linee(s)[L]) == pytest.approx([0, 100])
    r = s.sketch_extend('S1', L, [99, 10])                           # oltre il lato destro non c'è niente
    assert not r['ok'] and 'non incontra niente' in r['message']


def test_asola_fatta_a_mano_con_i_quadranti_e_taglia():
    """Due cerchi, due linee agganciate ai quadranti (in cima e in fondo), poi Taglia le metà interne:
    resta un contorno chiuso, unito davvero (gli archi usano gli stessi punti delle linee)."""
    s = Service()
    s.new_project('zero', {'name': 'P'})
    assert s.sketch_add_circle('S1', [0, 0], 10)['ok'] and s.sketch_add_circle('S1', [60, 0], 10)['ok']
    C1, C2 = [k for k, e in s.doc.sketch('S1').entities.items() if e['kind'] == 'circle']
    for k, y in ((1, 10), (3, -10)):
        assert s.sketch_add_polyline('S1', [{'quad': C1, 'k': k, 'xy': [0, y]}, {'quad': C2, 'k': k, 'xy': [60, y]}], False)['ok']
    assert s.sketch_trim('S1', C1, [10, 0])['ok'] and s.sketch_trim('S1', C2, [50, 0])['ok']
    v = s.sketch_view('S1')['sketch']
    assert v['ok'] and v['profiles'] == 1 and len(v['arcs']) == 2, v['status']
    estremi = {p for a in v['arcs'] for p in (a['start'], a['end'])}
    linee = {p for l in v['lines'] for p in (l['a'], l['b'])}
    assert estremi == linee                                         # stessi punti: contorno unito


def test_strumento_asola():
    s = Service()
    s.new_project('zero', {'name': 'P'})
    assert s.sketch_add_slot('S1', [0, 0], [80, 0], 6)['ok']
    v = s.sketch_view('S1')['sketch']
    assert v['ok'] and v['profiles'] == 1 and 'completamente' in v['status']
    quote = sorted(d['label'] for d in s.state()['dimensions'] if d['sketch'] == 'S1')
    assert quote == ['80', 'R6']
    r = next(d for d in s.state()['dimensions'] if d['type'] == 'radius')
    assert s.set_dimension('S1', r['dim'], 10)['ok']                 # più larga: entrambe le teste seguono
    v = s.sketch_view('S1')['sketch']
    assert all(a['r'] == pytest.approx(10) for a in v['arcs']) and v['profiles'] == 1


def test_agganci_tangente_perpendicolare_puntamento_restano_vincoli():
    """Tangente, perpendicolare e puntamento diventano vincoli: cambiando le misure restano veri."""
    s = Service()
    s.new_project('zero', {'name': 'P'})
    assert s.sketch_add_rectangle('S1', [0, 0], [100, 50])['ok']
    assert s.sketch_add_circle('S1', [70, 25], 15)['ok']
    C = next(k for k, e in s.doc.sketch('S1').entities.items() if e['kind'] == 'circle')
    P, c = (10, 10), (70, 25)
    d = math.dist(P, c); th = math.atan2(P[1] - c[1], P[0] - c[0]); al = math.acos(15 / d)
    T = [c[0] + 15 * math.cos(th - al), c[1] + 15 * math.sin(th - al)]
    assert s.sketch_add_polyline('S1', [list(P), {'tan': C, 'xy': T}], False)['ok']
    sotto = next(k for k, e in s.doc.sketch('S1').entities.items() if e['kind'] == 'line'
                 and abs(s.doc.sketch('S1').entities[e['a']]['y']) < 1e-9 and abs(s.doc.sketch('S1').entities[e['b']]['y']) < 1e-9)
    assert s.sketch_add_polyline('S1', [[40, 45], {'perp': sotto, 'xy': [40, 0]}], False)['ok']
    centro = s.doc.sketch('S1').entities[C]['center']
    assert s.sketch_add_polyline('S1', [[90, 5], {'track': {'x': centro, 'y': None}, 'xy': [70, 5]}], False)['ok']
    # il cerchio diventa Ø40: la tangente resta tangente, il puntamento resta sotto il centro
    dia = next(d for d in s.state()['dimensions'] if d['sketch'] == 'S1' and d['type'] == 'diameter')
    assert s.set_dimension('S1', dia['dim'], 40)['ok']
    v = s.sketch_view('S1')['sketch']
    circ = v['circles'][0]
    tl = next(l for l in v['lines'] if abs(l['xa'][0] - 10) < 1e-6 and abs(l['xa'][1] - 10) < 1e-6)
    (ax, ay), (bx, by) = tl['xa'], tl['xb']
    cx, cy = circ['xc']
    assert abs((bx - ax) * (ay - cy) - (ax - cx) * (by - ay)) / math.hypot(bx - ax, by - ay) == pytest.approx(20, abs=1e-6)
    pl = next(l for l in v['lines'] if abs(l['xa'][0] - 40) < 1e-6 and abs(l['xa'][1] - 45) < 1e-6)
    assert pl['xb'][0] == pytest.approx(40, abs=1e-6) and pl['xb'][1] == pytest.approx(0, abs=1e-6)
    tr = next(l for l in v['lines'] if abs(l['xa'][0] - 90) < 1e-6)
    assert tr['xb'][0] == pytest.approx(cx, abs=1e-6)


def _spigolo(s, x, y):
    return next(k for k, e in s.doc.sketch('S1').entities.items() if e['kind'] == 'point' and abs(e['x'] - x) < 1e-6 and abs(e['y'] - y) < 1e-6)


def test_raccordo_e_smusso_nello_sketch():
    s = Service()
    s.new_project('zero', {'name': 'P'})
    assert s.sketch_add_rectangle('S1', [0, 0], [100, 50])['ok']
    assert s.sketch_fillet('S1', _spigolo(s, 100, 50), 10)['ok']
    v = s.sketch_view('S1')['sketch']
    assert v['ok'] and v['profiles'] == 1 and v['arcs'][0]['r'] == pytest.approx(10)
    # l'arco è tangente: le linee arrivano a 10 dallo spigolo
    assert any(abs(l['xa'][0] - 90) < 1e-6 or abs(l['xb'][0] - 90) < 1e-6 for l in v['lines'])
    r = next(d for d in s.state()['dimensions'] if d['type'] == 'radius')
    assert s.set_dimension('S1', r['dim'], 20)['ok']                    # il raccordo segue la quota
    assert s.sketch_view('S1')['sketch']['arcs'][0]['r'] == pytest.approx(20)
    assert s.sketch_chamfer('S1', _spigolo(s, 0, 50), 8)['ok']
    v = s.sketch_view('S1')['sketch']
    assert v['ok'] and v['profiles'] == 1 and len(v['lines']) == 5
    r = s.sketch_fillet('S1', _spigolo(s, 100, 0), 80)                  # più grande dello spigolo: rifiutato
    assert not r['ok'] and 'Troppo grande' in r['message']


def test_poligono_e_arco_per_tre_punti():
    s = Service()
    s.new_project('zero', {'name': 'P'})
    assert s.sketch_add_polygon('S1', [0, 0], [20, 0], 6)['ok']
    v = s.sketch_view('S1')['sketch']
    lati = [math.dist(l['xa'], l['xb']) for l in v['lines'] if not l['construction']]
    assert len(lati) == 6 and all(x == pytest.approx(20) for x in lati) and v['profiles'] == 1
    assert s.sketch_add_arc3('S1', [100, 0], [120, 20], [140, 0])['ok']
    a = s.sketch_view('S1')['sketch']['arcs'][0]
    assert a['r'] == pytest.approx(20) and a['xc'] == pytest.approx([120, 0])


def test_regole_di_lamiera_e_tabella_pieghe(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))
    s = Service()
    s.new_project('lamiera', {'name': 'L', 'larghezza': 400, 'profondita': 300, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    assert s.save_sheet_rule('SM1', 'S235 sp2')['ok']
    assert s.set_sheet_tech('SM1', {'radius': 5, 'k': 0.3})['ok']
    assert s.apply_sheet_rule('SM1', 'S235 sp2')['ok']
    assert s.state()['sheet']['def']['radius'] == 2 and s.state()['sheet']['def']['k'] == 0.4
    csv = tmp_path / 't.csv'
    assert s.export_bend_table(str(csv))['ok']
    riga = csv.read_text(encoding='utf-8-sig').splitlines()[1].split(';')
    assert riga[1] == 'FL1' and riga[8] == '4,398' and riga[9] == '3,602'          # BA e BD come nel gate M3


def test_raccordo_cliccando_due_linee_come_autocad():
    """Spigolo sull'origine raccordato cliccando le due linee; linee staccate unite con R0 o raccordate."""
    s = Service()
    s.new_project('zero', {'name': 'P'})
    assert s.sketch_add_rectangle('S1', 'O', [100, 50])['ok']
    lati = {tuple(sorted([tuple(l['xa']), tuple(l['xb'])])): l['id'] for l in s.sketch_view('S1')['sketch']['lines']}
    sotto, sinistra = lati[((0, 0), (100, 0))], lati[((0, 0), (0, 50))]
    assert s.sketch_fillet_lines('S1', sotto, sinistra, [30, 0], [0, 20], 10)['ok']
    v = s.sketch_view('S1')['sketch']
    assert v['ok'] and v['profiles'] == 1 and v['arcs'][0]['r'] == pytest.approx(10)
    t = Service()
    t.new_project('zero', {'name': 'Q'})
    assert t.sketch_add_polyline('S1', [[0, 0], [80, 0]], False)['ok']
    assert t.sketch_add_polyline('S1', [[100, 20], [100, 90]], False)['ok']
    a, b = [l['id'] for l in t.sketch_view('S1')['sketch']['lines']]
    assert t.sketch_fillet_lines('S1', a, b, [40, 0], [100, 60], 0)['ok']           # R0: spigolo vivo in (100; 0)
    v = t.sketch_view('S1')['sketch']
    assert sorted(tuple(p) for l in v['lines'] for p in (l['xa'], l['xb'])).count((100.0, 0.0)) == 2
    assert t.sketch_chamfer_lines('S1', a, b, [40, 0], [100, 60], 5)['ok']          # e poi uno smusso lì
    assert len(t.sketch_view('S1')['sketch']['lines']) == 3
    r = t.sketch_fillet_lines('S1', a, a, [10, 0], [20, 0], 5)
    assert not r['ok']


def test_lamiera_a_contorno_dalla_sezione_disegnata():
    """La sezione disegnata sulla testata della base, dallo spigolo del lato L1, diventa una catena di flange."""
    import build123d as bd
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    sid = s.sketch_on_face('SM1/lato/L4')['sketch']
    pl = s.doc._sketch_results[sid][1].plane
    loc = lambda *p: [pl.to_local_coords(bd.Vector(*p)).X, pl.to_local_coords(bd.Vector(*p)).Y]  # noqa: E731
    assert s.sketch_add_polyline(sid, [loc(0, 0, 0), loc(0, 0, 60), loc(0, -40, 60), loc(0, -40, 20), loc(0, -12, 0)], False)['ok']
    r = s.contour_flange(sid)
    assert r['ok'], r.get('message')
    b = s.state()['sheet']['data']['bends']
    assert [(x['length'], x['angle'], x['direction']) for x in b[:3]] == [(60, 90, 'up'), (40, 90, 'down'), (40, 90, 'up')]
    assert b[3]['angle'] == pytest.approx(math.degrees(math.acos(20 / math.hypot(28, 20))), abs=0.01)   # ritorno: 54,46°
    assert b[3]['length'] == pytest.approx(math.hypot(28, 20), abs=0.01)
    assert [x['parent'] for x in b] == [None, 'FL1', 'FL2', 'FL3'] and not s.state()['errors']
    assert all(not hasattr(f, 'entities') or f.id != sid for f in s.doc.features)                  # lo sketch è consumato
    # una sezione che non parte da un bordo è rifiutata con il motivo
    sid2 = s.sketch_on_face('SM1/lato/L2')['sketch']
    assert s.sketch_add_polyline(sid2, [[10, 10], [30, 40], [50, 10]], False)['ok']
    r = s.contour_flange(sid2)
    assert not r['ok'] and 'spigolo di un bordo libero' in r['message']


def test_aggiungi_materiale_linguetta_nel_piano_della_faccia():
    """Una spezzata disegnata sulla faccia di una parete, che parte e finisce sul suo bordo, diventa lamiera dello
    stesso spessore nel piano della faccia: volume aggiunto = area aggiunta allo sviluppo × spessore."""
    import build123d as bd
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    v0, a0 = bd.Solid(s.result.body.shape).volume, s.result.body.sheet.flat_area
    sid = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    v = s.sketch_view(sid)['sketch']
    xs = sorted({round(p['xy'][0], 6) for p in v['points'] if p['id'] != 'O'})
    bordo = xs[-1]                                                   # il bordo destro della faccia (la fine della parete)
    assert s.sketch_add_polyline(sid, [[bordo, 5], [bordo + 30, 5], [bordo + 30, 30], [bordo, 30]], False)['ok']
    r = s.sheet_tab(sid)
    assert r['ok'], r.get('message')
    b = s.result.body
    assert len(bd.Shape.cast(b.shape).solids()) == 1
    assert bd.Solid(b.shape).volume - v0 == pytest.approx(30 * 25 * 2, rel=1e-6)
    assert (b.sheet.flat_area - a0) * 2 == pytest.approx(30 * 25 * 2, rel=1e-6)
    assert not s.state()['errors']
    # un contorno tutto dentro la faccia non aggiunge niente: rifiutato
    sid2 = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    assert s.sketch_add_rectangle(sid2, [20, 10], [60, 20])['ok']
    r = s.sheet_tab(sid2)
    assert not r['ok'] and 'non aggiunge niente' in r['message']


def test_linguetta_diventa_una_faccia_sola_con_la_parete():
    """Dopo "Aggiungi materiale" la parete e la linguetta sono una faccia sola, con il nome della parete:
    ci si ridisegna sopra e i bordi arancio sono il contorno intero."""
    import build123d as bd
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    sid = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    bordo = max(p['xy'][0] for p in s.sketch_view(sid)['sketch']['points'])
    assert s.sketch_add_polyline(sid, [[bordo, 5], [bordo + 30, 5], [bordo + 30, 30], [bordo, 30]], False)['ok']
    assert s.sheet_tab(sid)['ok']
    facce = s.result.body.face('SM1/FL1/esterno')
    assert len(facce) == 1
    assert bd.Face(facce[0]).area > 30 * 25
    sid2 = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    xs = [p['xy'][0] for p in s.sketch_view(sid2)['sketch']['points']]
    assert max(xs) == pytest.approx(bordo + 30, abs=1e-6)


def test_raccordo_degli_spigoli_del_pezzo_disegnando_sulla_faccia():
    """Nello sketch su faccia gli spigoli del pezzo (bordi arancio) si raccordano: lo spigolo verso fuori perde la
    punta, quello verso dentro (dove la linguetta incontra la parete) prende materiale. Sviluppo e pezzo d'accordo."""
    import math
    import build123d as bd
    from app import sketch_more
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    sid = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    bordo = max(p['xy'][0] for p in s.sketch_view(sid)['sketch']['points'])
    assert s.sketch_add_polyline(sid, [[bordo, 5], [bordo + 30, 5], [bordo + 30, 30], [bordo, 30]], False)['ok']
    assert s.sheet_tab(sid)['ok']
    sid2 = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    sk = s.doc.sketch(sid2)
    xy = lambda k: (sk.entities[k]['x'], sk.entities[k]['y'])  # noqa: E731
    spigoli = [k for k in sk.entities if sketch_more.is_part_corner(sk, k)]
    fuori = next(k for k in spigoli if xy(k) == pytest.approx((bordo + 30, 30), abs=1e-6))
    dentro = next(k for k in spigoli if xy(k) == pytest.approx((bordo, 30), abs=1e-6))
    r = 5
    punta = r * r * (1 - math.pi / 4)                                  # l'area tolta/aggiunta da un raccordo a 90°
    for k, segno in ((fuori, -1), (dentro, +1)):
        v0, a0 = bd.Solid(s.result.body.shape).volume, s.result.body.sheet.flat_area
        res = s.sketch_fillet(sid2, k, r)
        assert res['ok'], res.get('message')
        assert bd.Solid(s.result.body.shape).volume - v0 == pytest.approx(segno * punta * 2, rel=1e-4)
        assert (s.result.body.sheet.flat_area - a0) * 2 == pytest.approx(segno * punta * 2, rel=1e-4)
    assert not s.state()['errors']
    assert len([e for e in sk.entities.values() if e['kind'] == 'arc' and e.get('ref')]) == 2
    # lo smusso cliccando i due bordi che fanno lo spigolo in fondo a destra della linguetta
    giu = (bordo + 30, 5)
    bordi = [k for k, e in sk.entities.items() if e['kind'] == 'line' and e.get('ref')
             and giu in [pytest.approx(xy(e['a']), abs=1e-6), pytest.approx(xy(e['b']), abs=1e-6)]]
    assert len(bordi) == 2
    v0 = bd.Solid(s.result.body.shape).volume
    res = s.sketch_chamfer_lines(sid2, bordi[0], bordi[1], [bordo + 29, 5], [bordo + 30, 6], 4)
    assert res['ok'], res.get('message')
    assert bd.Solid(s.result.body.shape).volume - v0 == pytest.approx(-4 * 4 / 2 * 2, rel=1e-4)


def test_linguetta_di_chiusura_che_scende_nella_zona_della_piega():
    """Il caso dell'utente: sulla parete FL6 una linguetta che chiude la sezione del profilo FL3-FL4-FL5 e scende
    sotto il bordo della faccia (dentro la zona della piega). Nello sviluppo un pezzettino cadeva sopra la striscia
    di FL3 e tutto era rifiutato: ora quel pezzettino si toglie e il resto si fa, uguale nel pezzo e nello sviluppo."""
    import shutil
    import tempfile
    from pathlib import Path
    import build123d as bd
    tmp = Path(tempfile.mkdtemp()) / 'p.steelcad'
    shutil.copy(Path(__file__).parent / 'data' / 'linguetta_testata.steelcad', tmp)
    s = Service()
    assert s.open(str(tmp))['ok']
    v0, a0 = bd.Solid(s.result.body.shape).volume, s.result.body.sheet.flat_area
    r = s.sheet_tab('S2')
    assert r['ok'], r.get('message')
    b = s.result.body
    messo = bd.Solid(b.shape).volume - v0
    assert len(bd.Shape.cast(b.shape).solids()) == 1
    assert 285.5 * 2 - 2 < messo <= 285.5 * 2                        # quasi tutto il disegno
    assert (b.sheet.flat_area - a0) * 2 == pytest.approx(messo, rel=1e-6)
    assert len(b.face('SM1/FL6/esterno')) == 1


@pytest.mark.parametrize('verso', ['up', 'down'])
def test_piega_in_punta_dopo_la_linguetta(verso):
    """Il caso dell'utente: parete FL4 con linguetta (attaccata al suo fianco) e raccordo sullo spigolo; poi una
    piega sulla punta di FL4. Il fianco dove si attacca la linguetta arriva fino alla punta: non è "un taglio nella
    piega" della flangia nuova, che sta solo sulla larghezza della parete."""
    import shutil
    import tempfile
    from pathlib import Path
    import build123d as bd
    tmp = Path(tempfile.mkdtemp()) / 'p.steelcad'
    shutil.copy(Path(__file__).parent / 'data' / 'linguetta_poi_piega_in_punta.steelcad', tmp)
    s = Service()
    assert s.open(str(tmp))['ok']
    r = s.add_flange('SM1', None, {'length': '20', 'angle': 90, 'direction': verso}, 'FL4')
    assert r['ok'], r.get('message')
    assert not s.state()['errors']
    assert len(bd.Shape.cast(s.result.body.shape).solids()) == 1


def test_bordo_unico_a_45_sopra_la_linguetta():
    """Il caso dell'utente: profilo FL1-FL2-FL3 (bordo in cima) chiuso in testata da una linguetta sulla parete FL4.
    La flangia sulla punta di FL4 continua da sola sopra la linguetta; con "a 45°" e i due bordi alla stessa
    altezza si incontra con FL3 tagliata a 45° (bordo unico). A altezze diverse resta dritto e lo dice."""
    import math
    import shutil
    import tempfile
    from pathlib import Path
    import build123d as bd
    tmp = Path(tempfile.mkdtemp()) / 'p.steelcad'
    shutil.copy(Path(__file__).parent / 'data' / 'linguetta_poi_piega_in_punta.steelcad', tmp)
    s = Service()
    assert s.open(str(tmp))['ok']
    r = s.add_flange('SM1', None, {'length': '20', 'angle': 90, 'direction': 'up'}, 'FL4')
    assert r['ok'], r.get('message')
    fl5 = next(f for f in s._sheet_def('SM1')['flanges'] if f.get('parent') == 'FL4')
    assert fl5['extend'][1] > 10                                     # prolungata sopra la linguetta
    assert s.set_tip_corners('SM1', 'miter')['ok']
    assert any('stessa altezza' in w for w in s.state()['warnings'])  # 34 contro 34,14: resta dritto
    assert s.edit_flange('SM1', 'FL4', {'length': round(20 * math.sin(math.radians(45)) + 20, 2)})['ok']
    st = s.state()
    assert not st['errors'] and not st['warnings']
    geos = {g.fid: g for g in s.result.body.sheet.flanges}
    assert geos[fl5['id']].miters and geos['FL3'].miters
    assert len(bd.Shape.cast(s.result.body.shape).solids()) == 1


def test_prolunga_sopra_la_linguetta_dal_pannello():
    """Una flangia sulla punta già fatta si prolunga sopra la linguetta con il pulsante del pannello."""
    import shutil
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp()) / 'p.steelcad'
    shutil.copy(Path(__file__).parent / 'data' / 'linguetta_poi_piega_in_punta.steelcad', tmp)
    s = Service()
    assert s.open(str(tmp))['ok']
    r = s.add_flange('SM1', None, {'length': '20', 'angle': 90, 'direction': 'up', 'extend': [0, 0]}, 'FL4')
    assert r['ok']
    flid = r['select'].split('/')[-1]
    assert s._flange_selection('SM1', flid)['can_extend']
    r = s.extend_over_tab('SM1', flid)
    assert r['ok'], r.get('message')
    assert not s._flange_selection('SM1', flid)['can_extend']
    assert not s.extend_over_tab('SM1', 'FL1')['ok']                 # non è sulla punta di un'altra


def test_rifila_la_parete_sulla_sagoma_del_profilo():
    """Il caso dell'utente: la parete FL5 è più alta del profilo FL1-FL4 e davanti sporge. Sulla faccia interna di
    FL5 si vede la sagoma del profilo (linee arancio della testata vicina); basta una spezzata a L da bordo a bordo
    e "Taglia attraverso": la chiudo lungo il bordo dalla parte del pezzo più piccolo e lo tolgo."""
    import shutil
    import tempfile
    from pathlib import Path
    import build123d as bd
    tmp = Path(tempfile.mkdtemp()) / 'p.steelcad'
    shutil.copy(Path(__file__).parent / 'data' / 'parete_che_sporge.steelcad', tmp)
    s = Service()
    assert s.open(str(tmp))['ok']
    # la testata del profilo (a 1 mm dalla parete) non si chiama più "faccia interna di FL5"
    facce = s.result.body.face('SM1/FL5/interno')
    assert len(facce) == 1 and bd.Face(facce[0]).area > 10000
    sid = s.sketch_on_face('SM1/FL5/interno')['sketch']
    sk = s.doc.sketch(sid)
    sagoma = {(round(sk.entities[e[k]]['x'], 3), round(sk.entities[e[k]]['y'], 3))
              for e in sk.entities.values() if e['kind'] == 'line' and e.get('proj') for k in ('a', 'b')}
    assert (16.0, 28.0) in sagoma and (15.0, 27.0) in sagoma          # FL3 e FL2 del profilo
    v0 = bd.Solid(s.result.body.shape).volume
    assert s.sketch_add_polyline(sid, [[0, 27], [16, 27], [16, 44.5]], False)['ok']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')
    assert v0 - bd.Solid(s.result.body.shape).volume == pytest.approx(16 * 17.5 * 2, rel=1e-6)
    assert not s.state()['errors']
    # una spezzata che non arriva al bordo: messaggio chiaro
    sid2 = s.sketch_on_face('SM1/FL5/interno')['sketch']
    assert s.sketch_add_polyline(sid2, [[100, 10], [120, 10], [120, 20]], False)['ok']
    r = s.create_from_sketch(sid2, 'cut', {})
    assert not r['ok'] and 'bordo' in r['message']


def test_taglio_aperto_con_bordo_rotto_e_spigolo_raccordato():
    """Il caso dell'utente: nello sketch sulla faccia esterna di FL5 mancavano due linee arancio del bordo (cancellate)
    e uno spigolo è raccordato (arco). La spezzata da bordo a bordo si chiude lo stesso: il bordo si rifà dalla faccia
    vera (archi compresi) e il taglio va. I bordi arancio non si possono più cancellare né tagliare."""
    import shutil
    import tempfile
    from pathlib import Path
    import build123d as bd
    tmp = Path(tempfile.mkdtemp()) / 'p.steelcad'
    shutil.copy(Path(__file__).parent / 'data' / 'parete_bordo_rotto.steelcad', tmp)
    s = Service()
    assert s.open(str(tmp))['ok']
    v0 = bd.Solid(s.result.body.shape).volume
    r = s.create_from_sketch('S3', 'cut', {})
    assert r['ok'], r.get('message')
    assert v0 - bd.Solid(s.result.body.shape).volume == pytest.approx(2 * 17.5 * 2, rel=1e-6)
    assert not s.state()['errors']
    # uno sketch nuovo sulla faccia raccordata: l'arco del raccordo c'è tra i bordi
    sid = s.sketch_on_face('SM1/FL5/esterno')['sketch']
    sk = s.doc.sketch(sid)
    assert any(e['kind'] == 'arc' and e.get('ref') for e in sk.entities.values())
    assert [f for f in s.result.features if f.id == sid][0].ok
    bordo = next(k for k, e in sk.entities.items() if e['kind'] == 'line' and e.get('ref'))
    r = s.sketch_delete(sid, [bordo])
    assert not r['ok'] and 'arancio' in r['message'] and bordo in s.doc.sketch(sid).entities


def test_vedi_attraverso_fori_della_flangia_di_fronte():
    """Vedi attraverso: disegnando sulla flangia di fronte si vedono (e si agganciano) i fori dell'altra, al posto
    giusto; un foro ripreso lì è coassiale. Spento, le linee proiettate se ne vanno ma il disegno agganciato resta."""
    import build123d as bd
    s = Service()
    s.new_project('lamiera', {'name': 'U', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    assert s.add_flange('SM1', 'L2', {'length': '50'})['ok'] and s.add_flange('SM1', 'L4', {'length': '50'})['ok']
    sid = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    assert s.sketch_add_circle(sid, [30, 25], 4)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    sid2 = s.sketch_on_face('SM1/FL2/interno')['sketch']
    assert s.sketch_xray(sid2, True)['ok']
    v = s.sketch_view(sid2)['sketch']
    fori = [c for c in v['circles'] if c['xray']]
    assert v['xray'] and len(fori) == 1 and fori[0]['r'] == pytest.approx(4)
    # il foro ripreso agganciato al centro di quello visto attraverso: stesso asse
    assert s.sketch_add_circle(sid2, fori[0]['center_id'], 4)['ok']
    assert s.create_from_sketch(sid2, 'cut', {})['ok'] and not s.state()['errors']
    b = s.result.body
    fori3d = sorted((round(f.center().Y, 6), round(f.center().Z, 6)) for f in bd.Shape.cast(b.shape).faces()
                    if f.geom_type == bd.GeomType.CYLINDER and abs(f.radius - 4) < 1e-6 and f.center().Z > 10)
    assert len(fori3d) == 2 and len(set(fori3d)) == 1                # i due fori sullo stesso asse
    assert s.sketch_xray(sid2, False)['ok']
    v = s.sketch_view(sid2)['sketch']
    assert not v['xray'] and not any(c['xray'] for c in v['circles'])
    assert [f for f in s.result.features if f.id == sid2][0].ok      # il foro disegnato resta a posto


@pytest.mark.parametrize('k', [0.5, 0.33])
def test_taglio_sullo_sviluppo_attraverso_la_piega(k):
    """Un contorno sullo sviluppo che attraversa una piega: nel pezzo piegato il taglio segue la piega (pezzo nei
    tratti piani al suo posto, pezzo nella striscia avvolto sul cilindro). Con K 0,5 volume = area × spessore."""
    import build123d as bd
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': k})
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    v0, a0 = bd.Solid(s.result.body.shape).volume, s.result.body.sheet.flat_area
    sid = s.sketch_on_flat('SM1')['sketch']
    assert s.sketch_add_rectangle(sid, [80, -20], [120, 15])['ok']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')
    b = s.result.body
    assert (a0 - b.sheet.flat_area) == pytest.approx(40 * 35, rel=1e-9)
    tolto = v0 - bd.Solid(b.shape).volume
    if k == 0.5:
        assert tolto == pytest.approx(40 * 35 * 2, rel=1e-4)
    else:
        assert tolto > 40 * 35 * 2                                  # fibra neutra verso dentro: la piega pesa di più
    assert len(bd.Shape.cast(b.shape).solids()) == 1 and not s.state()['errors']


def test_asola_sullo_sviluppo_su_tre_pieghe():
    """Il caso dell'utente: un'asola sullo sviluppo che attraversa le pieghe del profilo FL1-FL2-FL3."""
    import shutil
    import tempfile
    from pathlib import Path
    import build123d as bd
    tmp = Path(tempfile.mkdtemp()) / 'p.steelcad'
    shutil.copy(Path(__file__).parent / 'data' / 'asola_sulle_pieghe.steelcad', tmp)
    s = Service()
    assert s.open(str(tmp))['ok']
    v0 = bd.Solid(s.result.body.shape).volume
    r = s.create_from_sketch('S12', 'cut', {})
    assert r['ok'], r.get('message')
    assert v0 - bd.Solid(s.result.body.shape).volume > 500
    assert not s.state()['errors'] and len(bd.Shape.cast(s.result.body.shape).solids()) == 1


def test_scasso_aperto_dal_bordo_della_piega():
    """Una spezzata a U che parte e finisce sul bordo dove comincia la piega in punta: lo scasso è aperto, passa la
    piega e il bordo piegato (prima restava una finestra sotto la piega). Volume = 60 × (20 + BA + tratto dritto) × sp."""
    import math
    import build123d as bd
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.5})
    assert s.add_flange('SM1', 'L1', {'length': '50'})['ok']
    assert s.add_flange('SM1', None, {'length': '15'}, 'FL1')['ok']
    sid = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    sk = s.doc.sketch(sid)
    piega = [e for e in sk.entities.values() if e.get('piega')]
    assert len(piega) == 2                                          # i bordi verso la base e verso il bordo in punta
    top = max(sk.entities[e['a']]['y'] for e in piega)
    v0 = bd.Solid(s.result.body.shape).volume
    assert s.sketch_add_polyline(sid, [[70, top], [70, top - 20], [130, top - 20], [130, top]], False)['ok']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')
    ba = math.pi / 2 * (2 + 0.5 * 2)
    assert v0 - bd.Solid(s.result.body.shape).volume == pytest.approx(60 * (20 + ba + 11) * 2, rel=1e-4)
    assert not s.state()['errors']


def test_orlo_a_180_gradi():
    """Orlo (risvolto) sulla punta: 180°, la lunghezza della parete resta la quota al bordo esterno della piega."""
    import build123d as bd
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 1, 'k': 0.5})
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    r = s.add_flange('SM1', None, {'length': '12', 'angle': 180, 'direction': 'up'}, 'FL1')
    assert r['ok'], r.get('message')
    b = s.result.body
    assert bd.Shape.cast(b.shape).bounding_box().max.Z == pytest.approx(40, abs=1e-6)
    assert bd.Solid(b.shape).volume == pytest.approx(b.sheet.flat_area * 2, rel=1e-6)    # K 0,5
    assert not s.add_flange('SM1', None, {'length': '12', 'angle': 175}, 'FL2')['ok']    # tra 170 e 180: no


def test_fori_svasati_filettati_e_per_inserti():
    import math
    import build123d as bd
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 3, 'raggio': 2, 'k': 0.5})
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    for x in (30, 60, 90, 120, 150):
        assert s.sketch_add_circle(sid, [x, 50], 3.2)['ok']
    cs = [c['id'] for c in s.sketch_view(sid)['sketch']['circles'] if not c['ref']]
    assert s.sketch_hole_type(sid, cs[:2], {'tipo': 'svasato', 'D': 8, 'angolo': 90})['ok']
    assert s.sketch_hole_type(sid, cs[2:4], {'tipo': 'filettato', 'M': 'M6'})['ok']
    assert s.sketch_hole_type(sid, cs[4:], {'tipo': 'inserto', 'codice': 'XYZ-M4', 'D': 5.4})['ok']
    diam = sorted(round(2 * c['r'], 3) for c in s.sketch_view(sid)['sketch']['circles'] if not c['ref'])
    assert diam == [5.0, 5.0, 5.4, 6.4, 6.4]                       # M6 → preforo 5; inserto → Ø dal catalogo
    v0 = bd.Solid(s.result.body.shape).volume
    assert s.create_from_sketch(sid, 'cut', {})['ok'] and not s.state()['errors']
    tolto = v0 - bd.Solid(s.result.body.shape).volume
    fori = math.pi * 3 * (2 * 3.2 ** 2 + 2 * 2.5 ** 2 + 2.7 ** 2)
    cono = math.pi * 0.8 / 3 * (16 + 12.8 + 3.2 ** 2) - math.pi * 3.2 ** 2 * 0.8
    assert tolto == pytest.approx(fori + 2 * cono, rel=1e-4)
    assert len([f for f in bd.Shape.cast(s.result.body.shape).faces() if f.geom_type == bd.GeomType.CONE]) == 2
    voce = next(n['label'] for n in s.state()['tree']['children'][0]['children'] if n['label'].startswith('Taglio'))
    assert '2 × M6' in voce and 'svasati Ø8' in voce and 'XYZ-M4' in voce
    # svasatura più profonda dello spessore (21/10): il pezzo non si blocca, il foro si fa dritto, la svasatura resta
    # in rosso con l'avviso
    sid2 = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_circle(sid2, [180, 50], 2)['ok']
    c2 = [c['id'] for c in s.sketch_view(sid2)['sketch']['circles'] if not c['ref']]
    r = s.sketch_hole_type(sid2, c2, {'tipo': 'svasato', 'D': 14, 'angolo': 90})
    assert not r['ok'] and 'profonda' in r['message']                  # Applica la rifiuta, col perché
    s.doc.sketch(sid2).entities[c2[0]]['hole'] = {'tipo': 'svasato', 'D': 14, 'angolo': 90}   # come in un progetto vecchio
    r = s.create_from_sketch(sid2, 'cut', {})
    assert r['ok'] and not s.state()['errors']
    assert any('spessore' in w for w in s.state()['warnings'])
    assert len(s.scene()['svasature_ko']) == 1


def test_persiane_e_imbutiture():
    import build123d as bd
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 120, 'spessore': 1.5, 'raggio': 1.5, 'k': 0.4})
    a0 = s.result.body.sheet.flat_area
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    for j in range(3):
        assert s.sketch_add_polyline(sid, [[40, 30 + j * 20], [100, 30 + j * 20]], False)['ok']
    r = s.create_from_sketch(sid, 'louver', {'width': '8', 'height': '4'})
    assert r['ok'], r.get('message')
    assert s.result.body.sheet.flat_area == pytest.approx(a0 - 3 * 60 * 0.2, rel=1e-9)      # i tagli di lancia
    bb = bd.Shape.cast(s.result.body.shape).bounding_box()
    assert bb.max.Z == pytest.approx(1.5 + 4, abs=1e-6)                                       # le cappe sporgono di 4
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_circle(sid, [150, 60], 8)['ok']
    assert s.create_from_sketch(sid, 'dimple', {'depth': '3'})['ok']
    st = s.state()
    assert not st['errors'] and len(bd.Shape.cast(s.result.body.shape).solids()) == 1
    assert len(s.scene()['objects']) == 1                             # la scena si triangola (la sfera ha un polo)
    voci = [n['label'] for n in st['tree']['children'][0]['children']]
    assert any(v.startswith('Persiane: 3 ×') for v in voci) and any(v.startswith('Imbutiture: 1 ×') for v in voci)


def test_scasso_aperto_su_due_pieghe_di_seguito():
    """Lo scasso dal bordo della parete passa il bordo da 15 e il ritorno da 8 (due pieghe di seguito)."""
    import math
    import build123d as bd
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.5})
    assert s.add_flange('SM1', 'L1', {'length': '60'})['ok']
    assert s.add_flange('SM1', None, {'length': '15'}, 'FL1')['ok']
    assert s.add_flange('SM1', None, {'length': '8'}, 'FL2')['ok']
    sid = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    sk = s.doc.sketch(sid)
    top = max(sk.entities[e['a']]['y'] for e in sk.entities.values() if e.get('piega'))
    v0 = bd.Solid(s.result.body.shape).volume
    assert s.sketch_add_polyline(sid, [[70, top], [70, top - 20], [130, top - 20], [130, top]], False)['ok']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')
    ba = math.pi / 2 * 3
    atteso = 60 * (20 + ba + (15 - 4 - 4) + ba + (8 - 4)) * 2
    assert v0 - bd.Solid(s.result.body.shape).volume == pytest.approx(atteso, rel=1e-4)


def test_piega_lungo_una_linea():
    """Piega su linea disegnata sullo sviluppo: la parte più piccola sale, lo sviluppo resta quello disegnato (stessa
    area), la linea è lo spigolo esterno. Dritta, obliqua, dall'altra parte, con una flangia sulla sua punta."""
    import build123d as bd
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.5})
    sid = s.sketch_on_flat('SM1')['sketch']
    assert s.sketch_add_polyline(sid, [[150, -5], [150, 105]], False)['ok']
    r = s.sheet_fold(sid, 90, 'up')
    assert r['ok'], r.get('message')
    b = s.result.body
    assert b.sheet.flat_area == pytest.approx(200 * 100, rel=1e-9)
    assert bd.Solid(b.shape).volume == pytest.approx(200 * 100 * 2, rel=1e-6)            # K 0,5
    bb = bd.Shape.cast(b.shape).bounding_box()
    assert bb.max.X == pytest.approx(150, abs=1e-6) and bb.max.Z > 50                     # piegata sulla linea
    assert s.add_flange('SM1', None, {'length': '15'}, 'PL1')['ok']                       # sulla sua punta
    assert s.select('flange=SM1/PL1')['selection']['kind'] == 'fold'
    assert s.edit_fold('SM1', 'PL1', {'flip': True})['ok']
    assert bd.Shape.cast(s.result.body.shape).bounding_box().max.X == pytest.approx(200, abs=1e-6)
    assert s.delete_flange('SM1', 'PL1')['ok']                                            # via anche la flangia figlia
    assert not s._sheet_def('SM1').get('folds') and not s._sheet_def('SM1')['flanges']
    # obliqua: la parte che si piega non è rettangolare, la flangia si rifila sullo sviluppo
    sid = s.sketch_on_flat('SM1')['sketch']
    assert s.sketch_add_polyline(sid, [[0, 20], [200, 60]], False)['ok']          # 11°: resta obliqua
    assert s.sheet_fold(sid, 90, 'up')['ok']
    assert s.result.body.sheet.flat_area == pytest.approx(200 * 100, rel=1e-6)
    assert not s.state()['errors'] and len(bd.Shape.cast(s.result.body.shape).solids()) == 1
    r = s.add_flange('SM1', None, {'length': '12'}, 'PL1')          # piega obliqua: niente punta dritta
    assert not r['ok'] and 'non è rettangolare' in r['message']
    # una linea che non attraversa la lamiera
    sid = s.sketch_on_flat('SM1')['sketch']
    assert s.sketch_add_polyline(sid, [[50, 60], [80, 70]], False)['ok']
    r = s.sheet_fold(sid, 90, 'up')
    assert not r['ok'] and 'attraversa' in r['message']


def test_incastri_automatici_sulla_punta():
    """Profilo chiuso: la punta di FL3 appoggia sulla base. Incastri: 3 linguette sulla punta che passano nelle asole
    della base (con gioco). Volume: + linguette (15 × 2 × sp) − asole (15,4 × 2,4 × sp)."""
    import build123d as bd
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.5})
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    assert s.add_flange('SM1', None, {'length': '30'}, 'FL1')['ok']
    assert s.add_flange('SM1', None, {'length': '38'}, 'FL2')['ok']
    assert s._flange_selection('SM1', 'FL3')['tip_contact'] and not s._flange_selection('SM1', 'FL1').get('tip_contact')
    v0 = bd.Solid(s.result.body.shape).volume
    r = s.auto_tabs('SM1', 'FL3', 3, 15, '0,2', 0)
    assert r['ok'], r.get('message')
    assert 'sulla faccia di sopra' in r['message']
    assert bd.Solid(s.result.body.shape).volume - v0 == pytest.approx(3 * 15 * 2 * 2 - 3 * 15.4 * 2.4 * 2, rel=1e-6)
    assert not s.state()['errors']
    r = s.auto_tabs('SM1', 'FL1', 3, 15, 0.2, 0)
    assert not r['ok'] and 'non appoggia' in r['message']
    r = s.auto_tabs('SM1', 'FL3', 20, 15, 0.2, 0)
    assert not r['ok']


def test_dati_di_piega_predefiniti():
    """Raggio e K predefiniti (dell'utente): li prende ogni lamiera nuova se non scrivi niente."""
    s = Service()
    s.new_project('lamiera', {})
    assert s.state()['sheet']['missing']                       # senza predefinito non si inventa niente
    assert s.set_bend_default({'radius': 1, 'method': 'k', 'k': '0,21'})['ok']
    s.new_project('lamiera', {})
    sm = s.doc.feature('SM1')
    assert (sm['radius'], sm['method'], sm['k']) == (1, 'k', 0.21) and not s.state()['sheet']['missing']
    s.new_project('lamiera', {'raggio': 2, 'k': 0.4})            # scritto a mano: vince quello
    assert (s.doc.feature('SM1')['radius'], s.doc.feature('SM1')['k']) == (2, 0.4)
    assert not s.set_bend_default({'method': 'k', 'k': 0.21})['ok']   # manca il raggio


def test_pagina_iniziale_anteprime_e_date(tmp_path, monkeypatch):
    """La pagina iniziale mostra i lavori recenti con l'anteprima (scattata dall'interfaccia) e la data detta come
    la si dice: "oggi, 11:02", "ieri"."""
    import base64
    import os
    import time
    from app import service as S
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path / 'casa'))
    s = Service()
    assert s.new_project('lamiera', {'name': 'Staffa', 'larghezza': 80, 'profondita': 50, 'spessore': 3})['ok']
    p = tmp_path / 'staffa.steelcad'
    assert s.save(str(p))['ok']
    png = base64.b64encode(b'\x89PNG\r\n\x1a\n finto').decode()
    assert s.save_thumbnail(str(p), 'data:image/png;base64,' + png)['ok']
    assert not s.save_thumbnail(str(p), 'javascript:alert(1)')['ok']
    r = s.home_info()['recent'][0]
    assert r['name'] == 'staffa' and r['thumb'] == 'data:image/png;base64,' + png and r['when'].startswith('oggi, ')
    ieri = time.time() - 86400
    os.utime(p, (ieri, ieri))
    assert s.home_info()['recent'][0]['when'] == 'ieri'
    assert S._quando(time.time() - 40 * 86400)[0].isdigit()


def test_pezzo_nuovo_il_riassunto_a_parole():
    """Mentre si scrivono le misure: cosa viene fuori, a parole, senza toccare il progetto aperto."""
    s = Service()
    r = s.new_project_preview('cancello', {'L': 1500, 'H': 1200, 'telaio': '60x60x3', 'sbarre': '20x20x2', 'passo': 120})
    assert r['ok'] and 'Escono 9 sbarre ogni 140 mm: tra una e l’altra restano 120 mm di luce' in r['text'] and 'Fuori tutto 1500 × 1200 mm' in r['text']
    assert 'Sviluppo 500 × 300 mm' in s.new_project_preview('lamiera', {'larghezza': 500, 'profondita': 300, 'spessore': 2})['text']
    assert 'Calandrato' in s.new_project_preview('cono', {'modo': 'rolled'})['text']
    male = s.new_project_preview('telaio', {'L': -5})
    assert male['ok'] and not male['text'] and male['warning']
    assert s.result.body is None and not s.result.structures            # il progetto aperto non è cambiato


def test_prepara_per_il_laser(tmp_path):
    """Un pulsante solo: si sceglie a chi serve (laser, piegatrice, officina, altro CAD) e i file finiscono insieme
    nella cartella del lavoro, con i nomi già fatti; il controllo del laser si vede prima."""
    s = Service()
    assert s.new_project('lamiera', {'name': 'Canalina 500 × 300', 'larghezza': 500, 'profondita': 300, 'spessore': 2,
                                     'raggio': 1, 'k': 0.21})['ok']
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    info = s.prepara_info()
    voci = {v['id']: v for v in info['voci']}
    assert info['controllo']['ok'] and voci['laser']['si'] and voci['piegatrice']['scelta']
    assert voci['laser']['file'] == 'Canalina 500 x 300_sviluppo.dxf'
    r = s.prepara(str(tmp_path / 'out'), ['laser', 'piegatrice', 'officina', 'step'])
    assert r['ok'], r.get('message')
    assert sorted(p.name for p in (tmp_path / 'out').iterdir()) == sorted(v['file'] for v in info['voci'])
    s2 = Service()
    assert s2.new_project('cancello', {})['ok']
    v2 = {v['id']: v for v in s2.prepara_info()['voci']}
    assert not v2['laser']['si'] and v2['officina']['scelta'] and 'lista di taglio' in v2['officina']['desc']


def test_fori_guidati_dal_bordo_esterno_e_un_annulla():
    """Fori come si segnano sul pezzo: centro dal bordo sinistro e dal bordo davanti, fuori tutto (anche con la
    piega davanti); una fila di 5 si fa e si toglie con un Annulla solo."""
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 500, 'profondita': 300, 'spessore': 2, 'raggio': 1, 'k': 0.21})['ok']
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    faccia = s.fori_faccia()
    info = s.fori_info(faccia)
    assert faccia == 'SM1/sopra' and info['outer'] == [500.0, 300.0]
    r = s.fori_guidati(faccia, {'tipo': 'tondo', 'd': 10, 'x': 60, 'y': 100, 'fila': True, 'n': 5, 'passo': 80, 'verso': 'x'})
    assert r['ok'] and r['message'] == 'Fatti 5 fori.'
    fl = s.result.body.sheet.flat
    ob = fl.outer_wire().bounding_box()
    centri = sorted(round((w.bounding_box().min.X + w.bounding_box().max.X) / 2 - ob.min.X, 3) for w in fl.inner_wires())
    assert centri == [60, 140, 220, 300, 380]
    assert {p['name']: p['label'] for p in s.state()['parameters']}.get('px1') == 'Distanza tra i fori della fila'
    s.undo()
    assert not s.result.body.sheet.flat.inner_wires()


def test_fori_guidati_filettati_e_svasati():
    """20/10: svasatura e filettatura erano solo nello sketch (Tipo di foro, a cerchi selezionati). Ora si scelgono
    in «Fori e asole»: filettato M5 → il preforo Ø4,2 sullo sviluppo e il filetto segnato; svasato con il suo Ø."""
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 200, 'spessore': 3, 'raggio': 1, 'k': 0.21})['ok']
    faccia = s.fori_faccia()
    r = s.fori_guidati(faccia, {'tipo': 'tondo', 'foro': 'filettato', 'M': 'M5', 'x': 50, 'y': 50,
                                'fila': True, 'n': 4, 'passo': 40, 'verso': 'x'})
    assert r['ok'], r.get('message')
    sk = next(f for f in s.doc.features if hasattr(f, 'entities') and f.name == 'Fori')
    cerchi = [e for e in sk.entities.values() if e['kind'] == 'circle' and not e.get('ref')]
    assert len(cerchi) == 4 and all(e.get('hole') == {'tipo': 'filettato', 'M': 'M5'} for e in cerchi)
    fori = s.result.body.sheet.flat.inner_wires()
    assert len(fori) == 4
    assert all(abs((w.bounding_box().max.X - w.bounding_box().min.X) - 4.2) < 1e-3 for w in fori)
    r = s.fori_guidati(faccia, {'tipo': 'tondo', 'foro': 'svasato', 'd': 6.5, 'sD': 12, 'sang': 90, 'x': 150, 'y': 150})
    assert r['ok'], r.get('message')
    r = s.fori_guidati(faccia, {'tipo': 'tondo', 'foro': 'svasato', 'd': 6.5, 'sD': 5, 'x': 200, 'y': 150})
    assert not r['ok'] and 'più larga del foro' in r['message']


def test_clic_sul_foro_del_pezzo_lo_filetta():
    """20/10: svasare e filettare si fa cliccando il foro sul pezzo, come negli altri CAD: la parete del foro porta al
    cerchio che l'ha fatto e ai fori uguali dello stesso disegno."""
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 200, 'spessore': 3, 'raggio': 1, 'k': 0.21})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    for x in (50, 100, 150):
        assert s.sketch_add_circle(sid, [x, 60], 5)['ok']
    assert s.sketch_add_circle(sid, [250, 150], 8)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    pareti = [x for x in s.scene()['objects'][0]['faces'] if x['name'] == 'TG1/parete']
    fori = [s.select('body', x['index'], x['name'])['selection']['foro'] for x in pareti]
    assert sorted(round(f['d'], 3) for f in fori) == [10, 10, 10, 16]
    dieci = next(f for f in fori if round(f['d']) == 10)
    assert len(dieci['uguali']) == 3
    assert s.sketch_hole_type(dieci['sketch'], dieci['uguali'], {'tipo': 'filettato', 'M': 'M5'})['ok']
    diam = sorted(round(w.bounding_box().max.X - w.bounding_box().min.X, 3) for w in s.result.body.sheet.flat.inner_wires())
    assert diam == [4.2, 4.2, 4.2, 16]
