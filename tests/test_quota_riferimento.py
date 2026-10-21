"""Quota su un pezzo finito: il bordo del pezzo è già deciso, la quota si mette lo stesso, di riferimento."""
import pytest

from app.service import Service


@pytest.fixture()
def s(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path))
    s = Service()
    s.new_project('piastra', {'name': 'P', 'larghezza': 300, 'altezza': 200, 'spessore': 10, 'foro': 20})
    return s


def test_quota_sul_bordo_del_pezzo(s):
    sid = s.sketch_on_face('E1/fine')['sketch']
    r = s.sketch_dimension(sid, 'length', ['L1'])
    assert r['ok'] and r['guidata']
    d = next(x for x in s._dimensions() if x['sketch'] == sid and x['dim'] == r['dim'])
    assert d['driven'] and d['label'] == '(300)'
    assert s.doc.solved_sketch(sid).status.state in ('completo', 'parziale')   # non diventa sovra-vincolato
    assert not s.set_dimension(sid, r['dim'], '150')['ok']                      # non comanda
    assert s.set_dimension(sid, r['dim'], '300')['ok']                          # stessa misura: niente


def test_quota_di_riferimento_segue_il_disegno(s):
    sid = s.sketch_on_face('E1/fine')['sketch']
    sk = s.doc.sketch(sid)
    a, b = sk.point(10, 10), sk.point(60, 10)
    lid = sk.line(a, b)
    sk.constrain('fix', a); sk.constrain('fix', b)
    r = s.sketch_dimension(sid, 'length', [lid])
    assert r['ok'] and r['guidata']
    from cad_engine.sketch.solver import solve
    sk.entities[b]['x'] = 80.0
    assert abs(solve(sk, s.doc.resolved_parameters()).values[r['dim']] - 70) < 1e-6
