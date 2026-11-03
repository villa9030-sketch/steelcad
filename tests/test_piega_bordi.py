"""03/11 (secondo giro) — «Piega» su più bordi in un colpo: la vaschetta (4 bordi, alta 30, Fatto) con gli angoli
aperti (scantonati) o chiusi (il lato lungo copre il corto, con il gioco). Lo sviluppo e il DXF devono uscire giusti."""
import math

import build123d as bd
import ezdxf
import pytest

from app.service import Service
from cad_engine.exporters.dxf import export_flat_pattern

T, R, K = 2, 2, 0.4
BA = math.pi / 2 * (R + K * T)                    # la piega a 90° nello sviluppo


@pytest.fixture
def lamiera():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 200, 'spessore': T, 'raggio': R, 'k': K})['ok']
    return s


QUATTRO = [{'kind': 'edge', 'ref': f'L{i}'} for i in range(1, 5)]


def _sviluppo_atteso(lato):
    # fuori tutto 30 su ogni lato: il piano perde raggio + spessore per parte, la piega ci mette BA
    return lato + 2 * 30 - 4 * (R + T) + 2 * BA


def test_vaschetta_quattro_bordi_in_un_colpo_angoli_aperti(lamiera, tmp_path):
    s = lamiera
    a = s.anteprima('piega_bordi', ['SM1', QUATTRO, {'length': '30'}, 'aperti'])
    assert a['ok'], a
    r = s.piega_bordi('SM1', QUATTRO, {'length': '30', 'angle': 90, 'direction': 'up'}, 'aperti')
    assert r['ok'] and r['message'] == 'Fatte 4 pieghe da 30 mm, angoli aperti (scantonati).', r
    assert s.history.labels()['undo'][0] == 'Pieghe su 4 bordi'
    corpo = bd.Shape.cast(s.result.body.shape)
    assert len(corpo.solids()) == 1
    bb = corpo.bounding_box()
    assert (round(bb.size.X, 3), round(bb.size.Y, 3), round(bb.size.Z, 3)) == (300, 200, 30)
    fl = s.result.body.sheet.flat
    fb = fl.bounding_box()
    assert round(fb.size.X, 3) == round(_sviluppo_atteso(300), 3)
    assert round(fb.size.Y, 3) == round(_sviluppo_atteso(200), 3)
    # angoli scantonati: lo spigolo del rettangolo di ingombro non è lamiera
    assert len(fl.outer_wire().edges()) > 4
    angolo = bd.Vector(fb.min.X + 1, fb.min.Y + 1, fb.min.Z)
    assert not fl.is_inside(angolo)
    # il DXF: 4 linee di piega sul livello BEND, il contorno chiuso sul CUT, nessun avviso
    out = export_flat_pattern(s.result.body.sheet, tmp_path / 'vaschetta.dxf')
    assert out.get('bend_lines') == 4
    d = ezdxf.readfile(tmp_path / 'vaschetta.dxf')
    assert len([e for e in d.modelspace() if e.dxftype() == 'LINE' and e.dxf.layer == 'BEND']) == 4
    assert not out.get('warnings'), out
    s.undo()
    assert not s._sheet_def('SM1')['flanges']                 # un Annulla le toglie tutte


def test_vaschetta_angoli_chiusi_il_lungo_copre_il_corto(lamiera, tmp_path):
    s = lamiera
    r = s.piega_bordi('SM1', QUATTRO, {'length': '30'}, 'chiusi', '0,5')
    assert r['ok'] and r['message'] == 'Fatte 4 pieghe da 30 mm, angoli chiusi.', r
    sm = s._sheet_def('SM1')
    lati = {f['id']: f['edge'] for f in sm['flanges']}
    assert len(sm['corners']) == 4
    for c in sm['corners']:                                      # sopra sempre il lato da 300 (L1, L3)
        assert lati[c['over']] in ('L1', 'L3') and lati[c['under']] in ('L2', 'L4') and c['gap'] == 0.5
    corpo = bd.Shape.cast(s.result.body.shape)
    assert len(corpo.solids()) == 1
    bb = corpo.bounding_box()
    assert (round(bb.size.X, 3), round(bb.size.Y, 3), round(bb.size.Z, 3)) == (300, 200, 30)
    out = export_flat_pattern(s.result.body.sheet, tmp_path / 'chiusa.dxf')
    assert out.get('bend_lines') == 4 and not out.get('warnings'), out
    # chiusi: le alette dei lati lunghi entrano negli angoli, lo sviluppo pesa di più che con gli angoli aperti
    area_chiusa = s.result.body.sheet.flat.area
    s.undo()
    assert s.piega_bordi('SM1', QUATTRO, {'length': '30'}, 'aperti')['ok']
    assert area_chiusa > s.result.body.sheet.flat.area


def test_bordo_gia_piegato_lo_dice(lamiera):
    s = lamiera
    assert s.add_flange('SM1', 'L1', {'length': '30'})['ok']
    r = s.piega_bordi('SM1', QUATTRO, {'length': '30'})
    assert not r['ok'] and 'c’è già una piega' in r['message']
    assert len(s._sheet_def('SM1')['flanges']) == 1


def test_bordini_sulle_punte_in_un_colpo(lamiera):
    s = lamiera
    assert s.piega_bordi('SM1', QUATTRO, {'length': '30'})['ok']
    punte = [{'kind': 'tip', 'ref': f['id']} for f in s._sheet_def('SM1')['flanges']]
    r = s.piega_bordi('SM1', punte, {'length': '15', 'direction': 'down'})
    assert r['ok'], r
    assert len([f for f in s._sheet_def('SM1')['flanges'] if f.get('parent')]) == 4
    assert len(bd.Shape.cast(s.result.body.shape).solids()) == 1


def test_nessun_bordo_scelto():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 100, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})['ok']
    r = s.piega_bordi('SM1', [], {'length': '30'})
    assert not r['ok'] and 'Clicca almeno un bordo' in r['message']
