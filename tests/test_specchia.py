"""Specchia come Copia/Sposta: asse = una linea oppure due punti (anche la metà di un bordo); si disegna da una parte
e si specchia dall'altra (21/10: gli angoli a 45° del cassone, sullo sviluppo)."""
import math
import os
import tempfile

import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


def lamiera():
    s = Service()
    assert s.new_project('lamiera', {'name': 'C', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 1, 'k': 0.21})['ok']
    assert s.add_flange('SM1', 'L1', {'length': '30'})['ok']
    return s


def mie(s, sid):
    v = s.sketch_view(sid)['sketch']
    P = {p['id']: p['xy'] for p in v['points']}
    return [(P[l['a']], P[l['b']]) for l in v['lines'] if not l['ref'] and not l['construction']], v


def test_specchia_con_due_punti_a_meta_dei_bordi_e_taglia_tutti_e_due_gli_angoli():
    s = lamiera()
    prima = s.state()['sheet']['data']['flat_area']
    sid = s.sketch_on_flat('SM1')['sketch']
    v = s.sketch_view(sid)['sketch']
    P = {p['id']: p['xy'] for p in v['points']}
    bordi = [l for l in v['lines'] if l['ref'] and not l.get('piega')]
    orizz = sorted((l for l in bordi if abs(P[l['a']][1] - P[l['b']][1]) < 1e-9), key=lambda l: P[l['a']][1])
    basso, alto = orizz[0], orizz[-1]
    y0 = P[basso['a']][1]
    # un triangolo d'angolo a sinistra, da bordo a bordo
    assert s.sketch_add_polyline(sid, [[0, y0 + 20], [20, y0]], False)['ok']
    ids = [l for l in s.sketch_view(sid)['sketch']['lines'] if not l['ref']]
    r = s.sketch_mirror(sid, [l['id'] for l in ids], [{'mid': basso['id']}, {'mid': alto['id']}])
    assert r['ok'], r
    tratti, v = mie(s, sid)
    xs = sorted(round(max(a[0], b[0]), 6) for a, b in tratti)
    assert xs == [20, 200]                                    # l'originale e lo specchio, dall'altra parte
    assert 'conflitto' not in v['status']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r
    assert prima - s.state()['sheet']['data']['flat_area'] == pytest.approx(2 * 20 * 20 / 2, rel=1e-6)


def test_specchia_arco_e_asse_sbagliato():
    s = lamiera()
    sid = s.sketch_on_flat('SM1')['sketch']
    assert s.sketch_add_arc3(sid, [50, 40], [60, 50], [70, 40])['ok']
    arco = [a['id'] for a in s.sketch_view(sid)['sketch']['arcs'] if not a['ref']]
    r = s.sketch_mirror(sid, arco, [[100, 0], [100, 80]])
    assert r['ok'], r
    archi = [a for a in s.sketch_view(sid)['sketch']['arcs'] if not a['ref']]
    assert len(archi) == 2
    centri = sorted(round(a['xc'][0], 4) for a in archi)
    assert centri == [pytest.approx(60, abs=1e-3), pytest.approx(140, abs=1e-3)]
    r = s.sketch_mirror(sid, arco, [[100, 0], [100, 0]])
    assert not r['ok'] and 'coincidono' in r['message']
