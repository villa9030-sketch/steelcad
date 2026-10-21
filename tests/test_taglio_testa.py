"""Taglio di testa inclinato (21/10, il cassone a cornice): un piano unico taglia tutte le facce e le pieghe, passa per
lo spigolo esterno della testa; il gioco scritto è il totale, metà per pezzo."""
import math
import os
import tempfile

import build123d as bd
import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


def vassoio():
    """Fondo 1000 × 500, pieghe di 30 sui lati lunghi, un orlo di 20 su una: come una parete del cassone."""
    s = Service()
    assert s.new_project('lamiera', {'name': 'C', 'larghezza': 1000, 'profondita': 500, 'spessore': 2, 'raggio': 1, 'k': 0.21})['ok']
    assert s.add_flange('SM1', 'L1', {'length': '30'})['ok']
    assert s.add_flange('SM1', None, {'length': '20'}, 'FL1')['ok']
    assert s.add_flange('SM1', 'L3', {'length': '30'})['ok']
    return s


def facce_a_45(s):
    sol = bd.Shape.cast(s.result.body.shape)
    out = []
    for f in sol.faces():
        n = f.normal_at()
        if abs(abs(n.X) - math.sqrt(0.5)) < 1e-4 and abs(abs(n.Z) - math.sqrt(0.5)) < 1e-4:
            c = f.center()
            out.append(round((c.X + c.Z - 1000) / math.sqrt(2) if c.X > 500 else (c.Z - c.X) / math.sqrt(2), 6))
    return sol, out


@pytest.mark.parametrize('gioco', [0, 2])
def test_tutte_le_facce_tagliate_su_un_piano_solo(gioco):
    s = vassoio()
    r = s.add_end_miter({'angle': '45', 'gap': str(gioco), 'end': 'entrambe'})
    assert r['ok'], r
    assert r['select'].startswith('tt=')
    assert s.state()['errors'] == []
    sol, piani = facce_a_45(s)
    # le due pareti alte 30, alle due teste: tagliate a 45° proprio sul piano, spostato della metà del gioco
    # (il fondo e l'orlo stanno di traverso: il laser li taglia dritti, dentro il piano)
    assert len(piani) == 4 and all(abs(p + gioco / 2) < 1e-6 for p in piani), piani
    # niente esce dal piano (non tocca il pezzo dell'angolo accanto)
    for v in sol.vertices():
        p = bd.Vector(v)
        assert (p.X + p.Z - 1000) / math.sqrt(2) <= -gioco / 2 + 1e-6
        assert (p.Z - p.X) / math.sqrt(2) <= -gioco / 2 + 1e-6


def test_una_testa_sola_modifica_ed_elimina():
    s = vassoio()
    prima = s.state()['sheet']['data']['flat_area']
    r = s.add_end_miter({'angle': 45, 'gap': 0, 'end': 'fine'})
    assert r['ok'], r
    tid = r['select'][3:]
    sel = s.select('tt=' + tid)['selection']
    assert sel['kind'] == 'endmiter' and sel['def']['end'] == 'fine'
    una = prima - s.state()['sheet']['data']['flat_area']
    assert s.edit_end_miter(tid, {'end': 'entrambe'})['ok']
    due = prima - s.state()['sheet']['data']['flat_area']
    assert due == pytest.approx(2 * una, rel=1e-6)
    assert 'Taglio di testa' in str(s.state()['tree'])
    assert s.tree_action('sheet_miter', tid, 'elimina')['ok']
    assert s.state()['sheet']['data']['flat_area'] == pytest.approx(prima)


@pytest.mark.parametrize('campi', [{'angle': 0}, {'angle': 95}, {'gap': -1}, {'end': 'boh'}, {'angle': 'abc'}])
def test_valori_sbagliati(campi):
    s = vassoio()
    r = s.add_end_miter(campi)
    assert not r['ok'] and 'Errore interno' not in r['message'], r


def test_senza_pieghe_si_dice():
    s = Service()
    assert s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 1, 'k': 0.21})['ok']
    r = s.add_end_miter({})
    assert not r['ok'] and 'pieghe' in r['message']


def test_cornice_di_quattro_testa_a_testa_si_chiude(tmp_path):
    """Quattro vassoi tagliati a 45° (due lunghi, due corti) accoppiati «testa a testa» col gioco: tutti gli
    accoppiamenti rispettati e anche l'ultimo angolo, non accoppiato, chiuso esatto al gioco."""
    import numpy as np

    from cad_engine import assembly as A
    from cad_engine.topology.naming import _faces_of
    gioco = 2
    for nome, L in (('lungo', 400), ('corto', 200)):
        p = Service()
        assert p.new_project('lamiera', {'name': nome, 'larghezza': L, 'profondita': 150, 'spessore': 2, 'raggio': 1, 'k': 0.21})['ok']
        assert p.add_flange('SM1', 'L1', {'length': '30'})['ok']
        assert p.add_flange('SM1', 'L3', {'length': '30'})['ok']
        assert p.add_end_miter({'gap': gioco})['ok']
        assert p.save(str(tmp_path / f'{nome}.steelcad'))['ok']
    s = Service()
    s.new_assembly('Cornice')
    for nome in ('lungo', 'corto', 'lungo', 'corto'):
        assert s.asm_insert(str(tmp_path / f'{nome}.steelcad'))['ok']

    def teste(iid, fine):
        i = s.asm.instance(iid)
        part = s.asm_parts[i['file']]
        mezzo = (part.doc.parameters.get('W') or 0) / 2 if hasattr(part.doc, 'parameters') else 0
        out = []
        for k, f in enumerate(_faces_of(part.shape)):
            inf = A.face_info(part, f)
            n = np.array(inf['n'])
            if inf['kind'] == 'piana' and abs(abs(n[0]) - 0.7071) < 1e-3 and abs(abs(n[2]) - 0.7071) < 1e-3:
                out.append((k, np.array(inf['p']), n))
        xm = (min(x[1][0] for x in out) + max(x[1][0] for x in out)) / 2
        return sorted((x for x in out if (x[1][0] > xm) == fine), key=lambda x: x[1][1])

    for a, b in (('I1', 'I2'), ('I2', 'I3'), ('I3', 'I4')):
        for x, y in zip(teste(a, True), teste(b, False)):
            assert s.asm_add_mate('testa', {'inst': a, 'face': x[0]}, {'inst': b, 'face': y[0]}, None)['ok']   # il gioco dai tagli
    pose = {i['id']: (np.array(i['R']), np.array(i['T'])) for i in s.asm.instances}
    assert s.state()['warnings'] == []
    assert all(A.mate_error(m, pose, s.asm_parts, s.asm) < 1e-6 for m in s.asm.mates)
    for x, y in zip(teste('I4', True), teste('I1', False)):                 # l'angolo che chiude l'anello
        (RA, TA), (RB, TB) = pose['I4'], pose['I1']
        assert float(np.dot(RA @ x[2], RB @ y[2])) == pytest.approx(-1, abs=1e-6)
        assert float(np.linalg.norm((RB @ y[1] + TB) - (RA @ x[1] + TA))) == pytest.approx(gioco, abs=1e-4)
    assert 'Nessuna interferenza' in s.asm_interferences()['message']
