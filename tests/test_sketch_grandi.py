"""Sketch grandi (serie di asole) e vincoli doppi: veloci, stessi risultati, niente rifiuti muti."""
import math
import time

from app.service import Service
from cad_engine.features.base import volume
from cad_engine.sketch import solver as SV


def _lamiera_con_asole(cols, rows):
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 1000, 'profondita': 500, 'spessore': 2})['ok']
    f = next(x for x in s.scene()['objects'][0]['faces'] if x['name'] and x['name'].endswith('sopra'))
    sid = s.sketch_on_face(f['name'])['sketch']
    prima = set(s.doc.sketch(sid).entities)
    assert s.sketch_add_slot(sid, [50, 100], [90, 100], 8)['ok']
    sk = s.doc.sketch(sid)
    asola = [k for k in sk.entities if k not in prima and sk.entities[k]['kind'] != 'point']
    t0 = time.perf_counter()
    assert s.sketch_pattern(sid, asola, cols, 60, rows, 40)['ok']
    return s, sid, time.perf_counter() - t0


def test_serie_grande_veloce_e_uguale_al_calcolo_intero():
    """75 asole (760 vincoli): prima 5,7 s e la modifica dopo altrettanto; a blocchi meno di 2 s, e la soluzione
    a blocchi è la stessa del calcolo intero (stato, gradi di libertà, punti)."""
    s, sid, dt = _lamiera_con_asole(15, 5)
    assert dt < 2.5
    sk = s.doc.sketch(sid)
    par = s.doc.resolved_parameters()
    bl, intero = SV._solve_a_blocchi(sk, par), SV._solve(sk, par)
    assert bl is not None
    assert (bl.status.state, bl.status.dof) == (intero.status.state, intero.status.dof)
    assert all(math.dist(p, bl.points[k]) < 1e-6 for k, p in intero.points.items())
    t0 = time.perf_counter()
    assert s.sketch_add_circle(sid, [500, 300], 10)['ok']
    assert time.perf_counter() - t0 < 1.5


def test_taglio_con_tante_asole_toglie_il_materiale_giusto():
    s, sid, _ = _lamiera_con_asole(6, 3)
    v0 = volume(s.result.body.shape)
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')
    asola = 2 * 8 * 40 + math.pi * 8 ** 2                    # rettangolo 40 × 16 più i due mezzi tondi
    assert abs((v0 - volume(s.result.body.shape)) - 18 * asola * 2) < 1.0
    assert len(s.result.body.sheet.flat.inner_wires()) == 18


def test_vincolo_doppio_non_blocca_il_taglio():
    """Un vincolo che ripete quello che dicono già gli altri (qui: verticale su una linea i cui estremi hanno già
    la stessa X) rendeva lo sketch "ridondante" e il taglio veniva rifiutato con "non è costruibile". Ora si
    toglie da solo e lo si dice."""
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 200, 'profondita': 100, 'spessore': 2})['ok']
    f = next(x for x in s.scene()['objects'][0]['faces'] if x['name'] and x['name'].endswith('sopra'))
    sid = s.sketch_on_face(f['name'])['sketch']
    assert s.sketch_add_rectangle(sid, [20, 20], [60, 50])['ok']
    sk = s.doc.sketch(sid)
    lato = next(k for k, e in sk.entities.items() if e['kind'] == 'line' and not e.get('ref')
                and abs(sk.entities[e['a']]['x'] - sk.entities[e['b']]['x']) < 1e-9)
    # due quote di X uguali sui due estremi del lato verticale: il "verticale" diventa doppio
    a, b = sk.entities[lato]['a'], sk.entities[lato]['b']
    x = sk.entities[a]['x']
    sk.dimension('hdistance', 'O', a, value=x)
    sk.dimension('hdistance', 'O', b, value=x)
    s._rebuild()
    assert s.doc.solved_sketch(sid).status.state == 'ridondante'
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')
    assert 'Ho tolto' in r['message'] and 'doppi' in r['message'] or 'doppio' in r['message']
