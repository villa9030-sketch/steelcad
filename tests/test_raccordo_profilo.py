"""Raccordo degli spigoli su un profilo in lamiera (02/11, «nelle tavole non ci sono più gli sviluppi»): era un taglio di
un pezzo pieno e il pezzo smetteva di essere lamiera. Ora è un taglio della lamiera: lo sviluppo resta, col raggio;
i file fatti prima si sistemano da soli all'apertura."""
import math

import build123d as bd
import pytest

from app import sketch_more
from app.service import Service
from cad_engine import project_io


def _profilo():
    s = Service()
    assert s.new_project('zero', {'name': 'L'})['ok']
    assert s.sketch_add_polyline('S1', [[0, 0], [60, 0], [60, 40]], False)['ok']
    assert s.create_from_sketch('S1', 'profilo', {'lunghezza': 50, 'spessore': 3, 'raggio': 1, 'k': 0.4})['ok']
    return s


def _spigolo_esterno(s, sid):
    sk = s.doc.sketch(sid)
    spigoli = [k for k in sk.entities if sketch_more.is_part_corner(sk, k)]
    assert spigoli
    return spigoli[0]


def test_raccordo_sul_profilo_resta_lamiera():
    s = _profilo()
    a0 = s.result.body.sheet.flat_area
    sid = s.sketch_on_face('FM1/tratto1/dentro')['sketch']
    r = s.sketch_fillet(sid, _spigolo_esterno(s, sid), 5)
    assert r['ok'], r.get('message')
    f = next(x for x in s.doc.features if isinstance(x, dict) and x.get('name', '').startswith('Raccordo spigolo'))
    assert f['type'] == 'sheet_cut'
    sh = getattr(s.result.body, 'sheet', None)
    assert sh is not None and not s.state()['errors']
    assert a0 - sh.flat_area == pytest.approx(25 * (1 - math.pi / 4), rel=1e-3)   # la punta tolta anche nello sviluppo
    assert [x['title'] for x in s.drawing_preview({})['sheets']][-1].endswith('sviluppo')


def test_file_vecchi_si_sistemano(tmp_path):
    s = _profilo()
    sid = s.sketch_on_face('FM1/tratto1/dentro')['sketch']
    assert s.sketch_fillet(sid, _spigolo_esterno(s, sid), 5)['ok']
    # com'era prima del 02/11: taglio passante di un pezzo pieno
    f = next(x for x in s.doc.features if isinstance(x, dict) and x.get('name', '').startswith('Raccordo spigolo'))
    f.update(type='extrude', operation='cut', through_all=True, reverse=True)
    p = project_io.save(s.doc, tmp_path / 'vecchio')
    s2 = Service()
    assert s2.open(str(p))['ok']
    f2 = next(x for x in s2.doc.features if isinstance(x, dict) and x.get('name', '').startswith('Raccordo spigolo'))
    assert f2['type'] == 'sheet_cut' and 'through_all' not in f2
    assert getattr(s2.result.body, 'sheet', None) is not None
    assert bd.Solid(s2.result.body.shape).volume == pytest.approx(bd.Solid(s.result.body.shape).volume, rel=1e-6)
