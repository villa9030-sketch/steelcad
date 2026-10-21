"""Testi da marcare col laser (21/10): lettere a tratto singolo sul layer MARK dello sviluppo, nella posizione giusta
anche sulle flange; avviso se la faccia nello sviluppo sta sotto (marcatura specchiata); niente testi nel vuoto."""
import ezdxf

from app.service import Service
from cad_engine.sketch import testo


def _targa():
    s = Service()
    assert s.new_project('lamiera', {'name': 'Targa', 'larghezza': 200, 'profondita': 100, 'spessore': 2,
                                     'raggio': 1, 'k': 0.21})['ok']
    assert s.add_flange('SM1', 'L1', {'length': 40})['ok']
    return s


def test_lettere_a_tratto_singolo():
    a = testo.tratti('A', 10)
    assert len(a) == 2 and all(t[0] != t[-1] for t in a)              # due tratti aperti, non contorni
    assert abs(max(y for t in a for _x, y in t) - 10) < 0.5            # alta 10 (le maiuscole)
    assert testo.larghezza('PP-001', 5) > testo.larghezza('P', 5)


def test_marcatura_nel_dxf_anche_sulla_flangia(tmp_path):
    s = _targa()
    sk = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_text(sk, [20, 40], 'PP-001 Ø10', 8)['ok']
    r = s.create_from_sketch(sk, 'mark', {})
    assert r['ok'], r.get('message')
    assert 'Marcatura laser: «PP-001 Ø10»' in str(s.state()['tree'])
    sk2 = s.sketch_on_face('SM1/FL1/interno')['sketch']
    assert s.sketch_add_text(sk2, [10, 8], 'LATO A', 6)['ok']
    assert s.create_from_sketch(sk2, 'mark', {})['ok']
    d = s.result.body.sheet
    assert len(d.marks) > 10 and not d.warnings and s.scene()['marks']
    p = tmp_path / 't.dxf'
    r = s.export_dxf(str(p))
    assert r['ok'] and 'Controlli superati' in r['message']
    segni = [e for e in ezdxf.readfile(p).modelspace() if e.dxf.layer == 'MARK']
    assert len(segni) == len(d.marks)
    ys = [y for e in segni for _x, y, *_ in e.get_points()]
    b = d.flat.bounding_box()
    assert min(ys) > b.min.Y and max(ys) < b.max.Y and min(ys) < 0          # una parte sta sulla flangia (y < 0)


def test_specchiata_e_fuori_dalla_lamiera():
    s = _targa()
    sk = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    s.sketch_add_text(sk, [10, 8], 'AB', 6)
    assert s.create_from_sketch(sk, 'mark', {})['ok']
    assert any('specchiata' in w for w in s.result.body.sheet.warnings)
    sk = s.sketch_on_face('SM1/sopra')['sketch']
    s.sketch_add_text(sk, [-40, 40], 'FUORI', 8)
    r = s.create_from_sketch(sk, 'mark', {})
    assert not r['ok'] or s.state()['errors']
