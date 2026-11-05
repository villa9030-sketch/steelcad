"""Scheletro in 3D (05/11, idea dallo «sketch 3D» di SolidCraft): tubi inclinati, fino a un punto, paralleli o ad
angolo con un altro tubo; misure della linea da cambiare dopo, coi tubi legati che seguono."""
import math

import pytest

from app.service import Service
from cad_engine import templates
from cad_engine.document import Document
from cad_engine.structures import cut_list

SP = 800 * math.tan(math.radians(14))


def _ok(r):
    assert r.get('ok'), r.get('message')
    return r


def _xyz(s, k):
    return [round(c, 2) for c in s.result.structures[0].nodes[k]['xyz']]


def _coseno(s, a, b, c):
    n = s.result.structures[0].nodes
    w1 = [p - q for p, q in zip(n[b]['xyz'], n[a]['xyz'])]
    w2 = [p - q for p, q in zip(n[c]['xyz'], n[b]['xyz'])]
    return sum(x * y for x, y in zip(w1, w2)) / math.hypot(*w1) / math.hypot(*w2)


def _nodo(r):
    return r['node'].split(':')[1]


def _nodo_in(s, xyz):
    return next(k for k, v in s.result.structures[0].nodes.items() if math.dist(v['xyz'], xyz) < 0.5)


def _tronco():
    """Il telaio di una tramoggia: base 600 × 600, gambe inclinate 14° verso fuori alte 800, telaio sopra."""
    s = Service()
    s._set(templates.struttura_vuota('Tronco'))
    b = _nodo(_ok(s.tubo_da_angolo('ST1', 'A', 'destra', 600, '40x40x3')))
    c = _nodo(_ok(s.tubo_da_angolo('ST1', b, 'dietro', 600)))
    d = _nodo(_ok(s.tubo_da_angolo('ST1', c, 'sinistra', 600)))
    _ok(s.linea_3d('ST1', d, {'modo': 'punto', 'dietro': -600}))
    alti = []
    for k, (u, v) in zip(('A', b, c, d), (('sinistra', 'avanti'), ('destra', 'avanti'), ('destra', 'dietro'), ('sinistra', 'dietro'))):
        r = _ok(s.linea_3d('ST1', k, {'modo': 'inclinata', 'freccia': 'su', 'lunghezza': 800, 'misura': 'freccia',
                                       'piega': [[u, 14], [v, 14]]}))
        alti.append(_nodo(r))
    _ok(s.linea_3d('ST1', alti[0], {'modo': 'parallela', 'tubo': 'M1', 'lunghezza': round(600 + 2 * SP, 4)}))
    for a, b_ in zip(alti[1:], alti[2:] + alti[:1]):
        pa, pb = s.result.structures[0].nodes[a]['xyz'], s.result.structures[0].nodes[b_]['xyz']
        _ok(s.linea_3d('ST1', a, {'modo': 'punto', 'destra': round(pb[0] - pa[0], 4), 'dietro': round(pb[1] - pa[1], 4)}))
    return s, alti


def test_tronco_di_piramide_coi_tagli_e_la_distinta():
    s, alti = _tronco()
    st = s.result.structures[0]
    assert len(st.members) == 12 and len(st.nodes) == 8 and st.warnings == []
    assert _xyz(s, alti[0]) == [round(-SP, 2), round(-SP, 2), 800]
    righe = sorted((r['length_mm'], r['qty'], tuple(r['cuts'])) for r in cut_list(s.result.structures)['rows'])
    assert [q for _, q, _ in righe] == [4, 4, 4]
    gambe = [r for r in righe if 700 < r[0] < 900]
    assert gambe and all(c not in ('45°', '0°') for c in gambe[0][2])        # le gambe hanno i tagli storti
    nomi = set(s.nomi_tubi(st).values())
    assert 'Gamba inclinata davanti a sinistra' in nomi and 'Traverso davanti, in basso' in nomi


def test_il_capo_si_aggancia_all_angolo_che_c_e():
    s = Service()
    s._set(templates.struttura_vuota('Q'))
    b = _nodo(_ok(s.tubo_da_angolo('ST1', 'A', 'destra', 500, '30x30x2')))
    c = _nodo(_ok(s.tubo_da_angolo('ST1', b, 'dietro', 500)))
    r = _ok(s.linea_3d('ST1', c, {'modo': 'punto', 'destra': -500, 'dietro': -500}))
    assert _nodo(r) == 'A' and 'agganciato' in r['message']                 # la diagonale chiude sul primo angolo
    assert len(s.result.structures[0].nodes) == 3


def test_solo_il_punto_e_misure_da_zero():
    s = Service()
    s._set(templates.struttura_vuota('P'))
    r = _ok(s.linea_3d('ST1', 'A', {'modo': 'punto', 'destra': 100, 'dietro': 200, 'su': 300, 'da_zero': True,
                                     'solo_punto': True}))
    assert _xyz(s, _nodo(r)) == [100, 200, 300] and not s.result.structures[0].members
    assert s.doc.feature('ST1')['points'][_nodo(r)] == [100, 200, 300]


def test_inclinato_misurato_lungo_il_tubo_o_in_altezza():
    s = Service()
    s._set(templates.struttura_vuota('G'))
    n1 = _nodo(_ok(s.linea_3d('ST1', 'A', {'modo': 'inclinata', 'freccia': 'su', 'lunghezza': 1000,
                                            'piega': [['destra', 30]]})))
    assert _xyz(s, n1) == [500, 0, round(1000 * math.cos(math.radians(30)), 2)]
    s._set(templates.struttura_vuota('G'))
    n2 = _nodo(_ok(s.linea_3d('ST1', 'A', {'modo': 'inclinata', 'freccia': 'su', 'lunghezza': 1000, 'misura': 'freccia',
                                            'piega': [['destra', 30]]})))
    assert _xyz(s, n2)[2] == 1000
    assert not s.linea_3d('ST1', 'A', {'modo': 'inclinata', 'freccia': 'su', 'lunghezza': 500, 'piega': [['giu', 10]]})['ok']


def test_parapetto_cambio_angolo_e_tutto_segue():
    s = Service()
    s._set(templates.struttura_vuota('Parapetto'))
    fine = _nodo(_ok(s.linea_3d('ST1', 'A', {'modo': 'punto', 'destra': 2400, 'su': 1500}, '40x40x2')))   # cosciale
    m1 = _nodo(_ok(s.tubo_da_angolo('ST1', 'A', 'su', 1000)))
    _ok(s.tubo_da_angolo('ST1', fine, 'su', 1000))
    r = _ok(s.linea_3d('ST1', m1, {'modo': 'punto', 'destra': 2400, 'su': 1500}))               # corrimano agganciato
    assert 'agganciato' in r['message'] and len(s.result.structures[0].members) == 4
    info = _ok(s.misure_linea('ST1/M1'))
    assert info['si_cambia'] and info['lunghezza'] == pytest.approx(2830.19, abs=0.01)
    assert info['inclinazione'] == pytest.approx(32.01, abs=0.01)
    a = next(x for x in info['angoli'] if x['si_cambia'])
    assert a['gradi'] == pytest.approx(57.99, abs=0.01)
    _ok(s.set_angolo_linee('ST1/M1', a['nodo'], a['tubo'], 55))
    z = 2830.19 * math.cos(math.radians(55))
    assert _xyz(s, fine)[2] == pytest.approx(z, abs=0.05)
    assert max(v['xyz'][2] for v in s.result.structures[0].nodes.values()) == pytest.approx(1000 + z, abs=0.05)
    _ok(s.set_lunghezza_linea('ST1/M1', 3000))                                                  # i montanti seguono
    assert math.dist(_xyz(s, 'A'), _xyz(s, fine)) == pytest.approx(3000, abs=0.05)
    assert _ok(s.misure_linea('ST1/M1'))['angoli'][0]['gradi'] == pytest.approx(55, abs=0.01)
    s.undo()
    assert math.dist(_xyz(s, 'A'), _xyz(s, fine)) == pytest.approx(2830.19, abs=0.05)


def test_parallelo_e_a_squadra_seguono_il_riferimento():
    s = Service()
    s._set(templates.struttura_vuota('Capriata'))
    b = _nodo(_ok(s.linea_3d('ST1', 'A', {'modo': 'inclinata', 'freccia': 'destra', 'lunghezza': 2000,
                                           'piega': [['su', 20]]}, '50x50x3')))
    c = _nodo(_ok(s.linea_3d('ST1', 'A', {'modo': 'parallela', 'tubo': 'M1', 'lunghezza': 1000, 'inverso': True})))
    assert _xyz(s, c)[0] == pytest.approx(-1000 * math.cos(math.radians(20)), abs=0.01)
    d = _nodo(_ok(s.linea_3d('ST1', b, {'modo': 'angolo', 'tubo': 'M1', 'gradi': 90, 'verso': 'giu', 'lunghezza': 300})))
    assert _coseno(s, 'A', b, d) == pytest.approx(0, abs=1e-6)                  # a squadra
    # giro il riferimento (la falda a 30°): il parallelo e quello a squadra lo seguono
    s.doc.feature('ST1')['points'][b]['verso']['piega'][0][1] = 30
    s._rebuild()
    assert _xyz(s, c)[2] == pytest.approx(-1000 * math.sin(math.radians(30)), abs=0.01)
    assert _coseno(s, 'A', b, d) == pytest.approx(0, abs=1e-6)


def test_con_le_misure_del_modello_e_salvato_riaperto():
    s, alti = _tronco()
    d = s.doc.to_dict()
    s2 = Service()
    s2._set(Document.from_dict(d))
    assert [round(c, 3) for c in s2.result.structures[0].nodes[alti[2]]['xyz']] == \
           [round(c, 3) for c in s.result.structures[0].nodes[alti[2]]['xyz']]
    # la lunghezza con un nome di misura: la gamba segue la misura
    s2.doc.set_parameter('H', 900)
    s2.doc.feature('ST1')['points'][alti[0]]['lungo'] = 'H'
    s2._rebuild()
    assert s2.result.structures[0].nodes[alti[0]]['xyz'][2] == pytest.approx(900, abs=0.01)


def test_anteprima_e_errori_chiari():
    s, _ = _tronco()
    k = _nodo_in(s, [0, 0, 0])
    r = s.anteprima('linea_3d', ['ST1', k, {'modo': 'angolo', 'tubo': 'M1', 'gradi': 120, 'verso': 'su', 'lunghezza': 400}])
    assert r['ok'] and r['objects']
    assert len(s.result.structures[0].members) == 12                                          # l'anteprima non tocca
    assert not s.linea_3d('ST1', k, {'modo': 'parallela', 'lunghezza': 300})['ok']            # manca il tubo
    assert not s.linea_3d('ST1', k, {'modo': 'angolo', 'tubo': 'M1', 'gradi': 200, 'lunghezza': 300})['ok']
    assert not s.linea_3d('ST1', k, {'modo': 'punto'})['ok']
    # la fine di una linea non si sposta con destra/dietro/su: si cambia dal tubo
    alto = next(x for x, v in s.doc.feature('ST1')['points'].items() if isinstance(v, dict) and 'lungo' in v)
    assert not s.move_node('ST1', alto, [0, 0, 10])['ok']
    assert s.select(f'ST1:{alto}')['selection']['position']['linea']


def test_pezzi_vecchi_uguali():
    """Un telaio fatto coi modelli (punti fissi e spostamenti) non cambia geometria."""
    s = Service()
    s._set(templates.telaio('Banco officina', L=1600, P=700, H=850, ripiano=150))
    righe = sorted((x['profile'], x['length_mm'], x['qty']) for x in cut_list(s.result.structures)['rows'])
    assert righe == [('30×30×2', 620.0, 2), ('30×30×2', 1520.0, 2), ('40×40×3', 620.0, 2),
                     ('40×40×3', 850.0, 4), ('40×40×3', 1520.0, 2)]
