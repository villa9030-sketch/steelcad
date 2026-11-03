"""Profilo in lamiera con l'arco calandrato (02/11, Stefano: il collare porta tubi «questo lo calandro, ad oggi non c'è
un'opzione per farlo»): l'arco resta liscio col raggio disegnato, nello sviluppo la fibra a metà spessore e due linee
dove la calandratura comincia e finisce; nella tabella della piegatrice solo le pieghe vere."""
import math

import build123d as bd

from app.service import Service

DATI = {'raggio': 1, 'k': 0.4}


def _collare(s, sid):
    """Gambe da 28, arco R55 (mezzo giro) che parte a 90° dalle gambe."""
    assert s.sketch_add_polyline(sid, [[-83, 0], [-55, 0]], False)['ok']
    assert s.sketch_add_arc3(sid, [-55, 0], [0, 55], [55, 0])['ok']
    assert s.sketch_add_polyline(sid, [[55, 0], [83, 0]], False)['ok']


def _nuovo():
    s = Service()
    assert s.new_project('zero', {'name': 'Collare'})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    _collare(s, sid)
    return s, sid


def test_collare_calandrato():
    s, sid = _nuovo()
    # la linea disegnata è l'interno del collare (il collare simmetrico non ha un lato convesso: si sceglie)
    r = s.create_from_sketch(sid, 'profilo', {'lunghezza': 30, 'spessore': 3, 'calandra': True, 'gira': True, **DATI})
    assert r['ok'], r.get('message')
    assert 'calandrato R55' in r['message']
    sh = s.result.body.sheet
    info = sh.shape_info
    # la linea disegnata è l'interno: R55 dentro, 180°; nella tabella solo le due pieghe a 90° delle gambe
    assert len(info['calandrature']) == 1
    c = info['calandrature'][0]
    assert abs(c['r_interno'] - 55) < 1e-6
    # le pieghe delle gambe si mangiano un pezzetto d'arco (il loro raggio): la gamba piega un po' meno di 90°,
    # la calandratura un po' meno di 180°, uguale di qua e di là
    assert len(sh.bend_rows) == 2
    mangiato = [90 - x['angle'] for x in sh.bend_rows]
    assert 0 < mangiato[0] < 10 and abs(mangiato[0] - mangiato[1]) < 1e-6
    assert abs(c['angolo'] - (180 - 2 * mangiato[0])) < 1e-6
    assert abs((c['a'] - c['da']) - math.radians(c['angolo']) * (55 + 1.5)) < 1e-6   # fibra a metà spessore
    assert sum(1 for *_, t in sh.bend_lines if t.startswith('C1')) == 2  # inizio e fine nello sviluppo
    # il pezzo: superficie dell'arco liscia (cilindri dello stesso raggio, niente facce piane dei colpi)
    so = bd.Solid(s.result.body.shape)
    cil = [f for f in so.faces() if f.geom_type == bd.GeomType.CYLINDER]
    assert {round(f.radius, 6) for f in cil} >= {55.0, 58.0}
    piane = [f for f in so.faces() if f.geom_type == bd.GeomType.PLANE]
    assert len(piane) == 2 + 2 * 3                                        # le due teste + gambe, e niente in mezzo
    b = so.bounding_box()
    assert abs(b.size.X - (166 + 0)) < 0.01 and abs(b.size.Y - 58) < 0.01  # fuori tutto come il collare di Stefano


def test_da_colpi_a_calandrato_e_ritorno():
    s, sid = _nuovo()
    assert s.create_from_sketch(sid, 'profilo', {'lunghezza': 30, 'spessore': 3, **DATI})['ok']
    colpi = len(s.result.body.sheet.bend_rows)
    assert colpi > 10
    v = s.profilo_valori(sid)['valori']
    assert v['lunghezza'] == 30 and not v['calandra']
    # di nuovo «Estrudi in lamiera» sullo stesso sketch: cambia il profilo, non ne fa un altro
    assert s.create_from_sketch(sid, 'profilo', {**v, 'calandra': True})['ok']
    assert len([f for f in s.doc.features if not hasattr(f, 'entities')]) == 1
    assert len(s.result.body.sheet.bend_rows) == 2 and s.profilo_valori(sid)['valori']['calandra']
    assert s.create_from_sketch(sid, 'profilo', {**v, 'calandra': False})['ok']
    assert len(s.result.body.sheet.bend_rows) == colpi


def test_dxf_del_calandrato(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path))
    s, sid = _nuovo()
    assert s.create_from_sketch(sid, 'profilo', {'lunghezza': 30, 'spessore': 3, 'calandra': True, **DATI})['ok']
    r = s.export_dxf(str(tmp_path / 'c.dxf'))
    assert r['ok'] and 'Controlli superati' in r['message'], r


def test_calandrato_senza_raggio_e_k():
    """02/11: con raggio e K vuoti «Il raggio di piega 58 non sta sul tratto 2»: ora si fa, da una parte e dall'altra."""
    for gira in (False, True):
        s, sid = _nuovo()
        s.bend_default = lambda: {}                                     # nessuna piegatrice impostata
        r = s.create_from_sketch(sid, 'profilo', {'lunghezza': 30, 'spessore': 3, 'calandra': True, 'gira': gira,
                                                  'raggio': '', 'k': ''})
        assert r['ok'], (gira, r.get('message'))
        assert len(s.result.body.sheet.shape_info['calandrature']) == 1


def test_raggio_troppo_piccolo_con_la_linea_fuori():
    s = Service()
    assert s.new_project('zero', {'name': 'Stretto'})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    assert s.sketch_add_polyline(sid, [[-10, 0], [-2, 0]], False)['ok']
    assert s.sketch_add_arc3(sid, [-2, 0], [0, 2], [2, 0])['ok']
    assert s.sketch_add_polyline(sid, [[2, 0], [10, 0]], False)['ok']
    r = s.create_from_sketch(sid, 'profilo', {'lunghezza': 30, 'spessore': 3, 'calandra': True, 'gira': True, **DATI})
    assert not r['ok'] or s.state()['errors']
