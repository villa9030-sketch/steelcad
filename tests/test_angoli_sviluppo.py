"""03/11 (secondo giro) — raccordi e smussi sugli spigoli vivi dello sviluppo in un comando: tutti o quelli scelti,
con anteprima. Diventano un taglio sullo sviluppo: tornano nel pezzo piegato e vanno nel DXF."""
import build123d as bd
import ezdxf
import pytest

from app.service import Service
from cad_engine.exporters.dxf import export_flat_pattern


@pytest.fixture
def piastra():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.4})['ok']
    return s


def _archi(fl):
    return [e for e in fl.outer_wire().edges() if e.geom_type == bd.GeomType.CIRCLE]


def test_piastra_quattro_angoli_r10(piastra, tmp_path):
    s = piastra
    info = s.angoli_sviluppo_info()
    assert info['ok'] and len(info['angoli']) == 4
    a = s.anteprima('angoli_sviluppo', [None, 'raggio', '10'])
    assert a['ok'], a
    r = s.angoli_sviluppo(None, 'raggio', '10')
    assert r['ok'] and r['message'] == 'Arrotondati 4 angoli dello sviluppo.', r
    fl = s.result.body.sheet.flat
    archi = _archi(fl)
    assert len(archi) == 4 and all(abs(e.radius - 10) < 1e-6 for e in archi)
    bb = fl.bounding_box()
    assert (round(bb.size.X, 3), round(bb.size.Y, 3)) == (300, 200)     # il fuori tutto resta
    out = export_flat_pattern(s.result.body.sheet, tmp_path / 'p.dxf')
    assert not out.get('warnings'), out
    d = ezdxf.readfile(tmp_path / 'p.dxf')
    assert len([e for e in d.modelspace() if e.dxftype() == 'ARC' and e.dxf.layer == 'CUT']) == 4
    assert 'Angoli R10' in str(s.state()['tree'])
    s.undo()
    assert not _archi(s.result.body.sheet.flat)


def test_solo_gli_angoli_scelti_e_smusso(piastra):
    s = piastra
    info = s.angoli_sviluppo_info()
    due = [c['xy'] for c in info['angoli'][:2]]
    r = s.angoli_sviluppo(None, 'smusso', 15, due)
    assert r['ok'] and r['message'] == 'Smussati 2 angoli dello sviluppo.', r
    fl = s.result.body.sheet.flat
    assert len(fl.outer_wire().edges()) == 6 and not _archi(fl)


def test_vaschetta_punte_delle_pieghe_arrotondate(piastra):
    s = piastra
    assert s.piega_bordi('SM1', [{'kind': 'edge', 'ref': f'L{i}'} for i in range(1, 5)], {'length': '30'})['ok']
    info = s.angoli_sviluppo_info()
    assert len(info['angoli']) == 8                        # le punte delle 4 pieghe, non gli angoli scantonati
    r = s.angoli_sviluppo(None, 'raggio', 5)
    assert r['ok'], r
    assert len(_archi(s.result.body.sheet.flat)) == 8
    corpo = bd.Shape.cast(s.result.body.shape)
    assert len(corpo.solids()) == 1
    bb = corpo.bounding_box()
    assert (round(bb.size.X, 3), round(bb.size.Y, 3), round(bb.size.Z, 3)) == (300, 200, 30)


def test_raggio_troppo_grande_lo_dice(piastra):
    s = piastra
    r = s.angoli_sviluppo(None, 'raggio', 150)
    assert not r['ok'] and 'troppo grande' in r['message']
    a = s.anteprima('angoli_sviluppo', [None, 'raggio', 150])
    assert not a['ok'] and 'troppo grande' in a['message']
