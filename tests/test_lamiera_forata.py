"""05/11 — Lamiera forata (idea da SolidCraft «sheet.perforate»): un campo di fori su una faccia piana della lamiera.
Forma (tondo, asola, quadro), passo, in fila o sfalsata a 60°, margine dai bordi e dalle pieghe, oppure solo dentro un
contorno disegnato. La serie si centra nella zona, si fanno solo fori interi, il peso e lo sviluppo (DXF) li contano,
anche sulle facce che poi si piegano. 2000 fori non devono bloccare l'app."""
import math
import time

import build123d as bd
import ezdxf
import pytest

from app.service import Service
from cad_engine.analysis import properties
from cad_engine.exporters.dxf import export_flat_pattern
from cad_engine.sheetmetal import forata as F

T, R, K = 2, 2, 0.4
BA = math.pi / 2 * (R + K * T)


@pytest.fixture
def piastra():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 200, 'profondita': 100, 'spessore': T, 'raggio': R, 'k': K})['ok']
    return s


@pytest.fixture
def piegata():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 200, 'spessore': T, 'raggio': R, 'k': K})['ok']
    assert s.add_flange('SM1', 'L1', {'length': '60'})['ok']
    return s


def _volume(s):
    return bd.Shape.cast(s.result.body.shape).volume


def _fori_sviluppo(s):
    """I centri (x, y) dei fori dello sviluppo, nel piano dello sviluppo."""
    data = s.result.body.sheet
    fs = data.flat.faces() if not isinstance(data.flat, bd.Face) else [data.flat]
    out = []
    for f in fs:
        for w in f.inner_wires():
            c = data.plane.to_local_coords(bd.Face(w).center())
            out.append((round(c.X, 3), round(c.Y, 3)))
    return sorted(out)


def test_griglia_in_fila_centrata_margini_uguali(piastra):
    s = piastra
    v0 = _volume(s)
    kg0 = properties(s.result.body.shape, s.doc.material)['mass_kg']
    a = s.forata_anteprima('SM1/sopra', {'forma': 'tondo', 'd': 5, 'px': 10, 'py': 10, 'disposizione': 'fila', 'margine': 10})
    assert a['ok'] and a['n'] == 18 * 8, a
    assert a['frase'].startswith('144 fori Ø5, in fila, passo 10'), a['frase']
    r = s.forata('SM1/sopra', {'forma': 'tondo', 'd': 5, 'px': 10, 'py': 10, 'disposizione': 'fila', 'margine': 10})
    assert r['ok'], r
    assert r['message'] == 'Fatta la lamiera forata: 144 fori (Ø5).', r['message']
    assert r['select'] == 'lf=LF1'
    assert s.history.labels()['undo'][0] == 'Lamiera forata'
    # il peso tiene conto dei fori
    tolto = 144 * math.pi * 2.5 ** 2 * T
    assert _volume(s) == pytest.approx(v0 - tolto, rel=1e-6)
    assert properties(s.result.body.shape, s.doc.material)['mass_kg'] < kg0
    # lo sviluppo ha tutti i fori, centrati: dal bordo al primo foro come dall'ultimo al bordo
    fori = _fori_sviluppo(s)
    assert len(fori) == 144
    xs, ys = sorted({x for x, _ in fori}), sorted({y for _, y in fori})
    assert xs[0] == pytest.approx(200 - xs[-1]) and ys[0] == pytest.approx(100 - ys[-1])
    assert xs[0] - 2.5 >= 10 - 1e-6 and ys[0] - 2.5 >= 10 - 1e-6       # almeno il margine
    assert s.result.body.sheet.forate['LF1']['n'] == 144
    assert s.result.body.sheet.forate['LF1']['diretto'] is True        # fatto senza booleana


def test_sfalsata_60_gradi_file_spostate_di_mezzo_passo(piastra):
    s = piastra
    r = s.forata('SM1/sopra', {'forma': 'tondo', 'd': 4, 'px': 8, 'disposizione': 'sfalsata', 'margine': 5})
    assert r['ok'], r
    fori = _fori_sviluppo(s)
    righe = sorted({y for _, y in fori})
    assert righe[1] - righe[0] == pytest.approx(8 * math.sqrt(3) / 2, abs=1e-3)   # file a passo · √3/2
    x0 = sorted(x for x, y in fori if y == righe[0])
    x1 = sorted(x for x, y in fori if y == righe[1])
    assert abs(x1[0] - x0[0]) == pytest.approx(4, abs=1e-3)                       # mezzo passo
    # i tre vicini a distanza uguale (60°)
    a, b = (x0[0], righe[0]), min(((x, righe[1]) for x in x1), key=lambda p: math.dist(p, (x0[0], righe[0])))
    assert math.dist(a, b) == pytest.approx(8, abs=1e-3)
    # centrata anche con lo spostamento
    tutte_x = [x for x, _ in fori]
    assert min(tutte_x) == pytest.approx(200 - max(tutte_x), abs=1e-3)
    assert _volume(s) == pytest.approx(200 * 100 * T - len(fori) * math.pi * 4 * T, rel=1e-6)


def test_asole_e_quadri(piastra):
    s = piastra
    r = s.forata('SM1/sopra', {'forma': 'asola', 'lung': 20, 'larg': 5, 'px': 30, 'py': 12, 'disposizione': 'fila', 'margine': 10})
    assert r['ok'], r
    n = s.result.body.sheet.forate['LF1']['n']
    area = (15 * 5 + math.pi * 2.5 ** 2) * n
    assert _volume(s) == pytest.approx(200 * 100 * T - area * T, rel=1e-6)
    assert s.result.body.sheet.forate['LF1']['foro'] == 'asole 20 × 5'
    s.undo()
    r = s.forata('SM1/sopra', {'forma': 'quadro', 'lato': 6, 'px': 10, 'py': 10, 'disposizione': 'fila', 'margine': 10})
    assert r['ok'], r
    n = s.result.body.sheet.forate['LF1']['n']
    assert _volume(s) == pytest.approx(200 * 100 * T - 36 * n * T, rel=1e-6)
    assert len(_fori_sviluppo(s)) == n


def test_fori_sulla_flangia_vanno_nello_sviluppo_al_posto_giusto(piegata):
    s = piegata
    data0 = s.result.body.sheet
    v0 = _volume(s)
    r = s.forata('SM1/FL1/esterno', {'forma': 'tondo', 'd': 5, 'px': 10, 'py': 10, 'disposizione': 'fila', 'margine': 5})
    assert r['ok'], r
    n = s.result.body.sheet.forate['LF1']['n']
    assert n > 0
    assert _volume(s) == pytest.approx(v0 - n * math.pi * 6.25 * T, rel=1e-6)
    fori = _fori_sviluppo(s)
    assert len(fori) == n
    # nello sviluppo stanno tutti sul tratto della flangia: oltre la striscia della piega, prima della punta
    zona = data0.bend_zones()[0]
    ys = [p[1] for p in zona]
    xs = [p[0] for p in zona]
    lo, hi = min(ys), max(ys)
    for x, y in fori:
        dentro_striscia = lo - 2.5 < y < hi + 2.5 and min(xs) < x < max(xs)
        assert not dentro_striscia, (x, y)
    # e nessun foro sulla base (la striscia della piega divide la base dalla flangia)
    sopra = sum(1 for _, y in fori if y > hi) if fori[0][1] > hi else sum(1 for _, y in fori if y < lo)
    assert sopra == n


def test_fori_che_toccano_le_pieghe_sono_esclusi(piegata):
    s = piegata
    # sulla base, margine 0: i fori arrivano fino al bordo della piega ma non ci entrano
    r = s.forata('SM1/sopra', {'forma': 'tondo', 'd': 6, 'px': 10, 'py': 10, 'disposizione': 'fila', 'margine': 0})
    assert r['ok'], r
    data = s.result.body.sheet
    zona = s.result.body.sheet.bend_zones()[0]
    ys = [p[1] for p in zona]
    for x, y in _fori_sviluppo(s):
        assert not (min(ys) - 3 + 1e-6 < y < max(ys) + 3 - 1e-6), (x, y)
    assert data.forate['LF1']['n'] == len(_fori_sviluppo(s))


def test_zona_dentro_un_disegno(piastra):
    s = piastra
    r = s.sketch_on_face('SM1/sopra')
    sid = r['sketch']
    from app import sketch_ops
    import build123d as bd_
    from cad_engine.sketch.face_plane import plane_of
    sk = s.doc.sketch(sid)
    piano = plane_of(s.result.body, 'SM1/sopra', sk)
    ox, oy, _, _ = s._fuori_tutto(piano, 'SM1/sopra')
    sketch_ops.add_circle(s.doc, sid, [ox + 100, oy + 50], 30)
    s._rebuild()
    info = s.forata_info('SM1/sopra')
    assert info['ok'] and [x['id'] for x in info['schizzi']] == [sid]
    r = s.forata('SM1/sopra', {'forma': 'tondo', 'd': 5, 'px': 8, 'disposizione': 'sfalsata', 'margine': 10, 'sketch': sid})
    assert r['ok'], r
    fori = _fori_sviluppo(s)
    assert fori
    for x, y in fori:
        assert math.dist((x, y), (100, 50)) <= 30 - 2.5 + 1e-6
    # lo sketch non è più tra quelli liberi
    assert s.forata_info('SM1/sopra')['schizzi'] == []


def test_si_cambia_dopo_e_si_riapre(piastra):
    s = piastra
    assert s.forata('SM1/sopra', {'forma': 'tondo', 'd': 5, 'px': 10, 'py': 10, 'disposizione': 'fila', 'margine': 10})['ok']
    m = s.forata_da_modificare('LF1')
    assert m['ok'] and m['spec']['d'] == 5 and m['spec']['disposizione'] == 'fila' and m['face'] == 'SM1/sopra'
    # l'anteprima del cambio non vede i fori di adesso (altrimenti non ci starebbe più niente)
    a = s.forata_anteprima('SM1/sopra', {**m['spec'], 'd': '6,5'}, 'LF1')
    assert a['ok'] and a['n'] == 144, a
    n = len(s.doc.features)
    r = s.forata_modifica('LF1', {**m['spec'], 'd': '6,5', 'px': 12, 'py': 12})
    assert r['ok'] and r['message'].startswith('Cambiata la lamiera forata'), r
    assert len(s.doc.features) == n
    assert s.result.body.sheet.forate['LF1']['foro'] == 'Ø6,5'
    sel = s.select('lf=LF1')['selection']
    assert sel['kind'] == 'forata' and sel['n'] == s.result.body.sheet.forate['LF1']['n']
    assert ['Fori fatti', str(sel['n'])] in sel['rows']
    # dall'albero: «Modifica» porta al pannello
    m = s.tree_menu('sheet_perforate', 'LF1')
    assert m['ok'] and 'modifica' in m['voci'] and m['seleziona'] == 'lf=LF1'
    s.undo()
    assert s.result.body.sheet.forate['LF1']['foro'] == 'Ø5'


def test_si_salva_e_si_riapre_uguale(piastra, tmp_path):
    s = piastra
    assert s.forata('SM1/sopra', {'forma': 'tondo', 'd': 5, 'px': 10, 'disposizione': 'sfalsata', 'margine': 10})['ok']
    v = _volume(s)
    p = tmp_path / 'forata.steelcad'
    assert s.save(str(p))['ok']
    s2 = Service()
    assert s2.open(str(p))['ok']
    assert _volume(s2) == pytest.approx(v)
    assert s2.result.body.sheet.forate['LF1']['n'] == s.result.body.sheet.forate['LF1']['n']


def test_dxf_con_tutti_i_fori(piastra, tmp_path):
    s = piastra
    assert s.forata('SM1/sopra', {'forma': 'tondo', 'd': 5, 'px': 10, 'py': 10, 'disposizione': 'fila', 'margine': 10})['ok']
    out = tmp_path / 'forata.dxf'
    export_flat_pattern(s.result.body.sheet, out)
    msp = ezdxf.readfile(out).modelspace()
    cerchi = [e for e in msp if e.dxftype() == 'CIRCLE' and e.dxf.layer == 'CUT']
    assert len(cerchi) == 144
    assert all(e.dxf.radius == pytest.approx(2.5) for e in cerchi)


def test_errori_in_parole_semplici(piastra):
    s = piastra
    r = s.forata('SM1/sopra', {'forma': 'tondo', 'd': 10, 'px': 8, 'disposizione': 'fila', 'margine': 10})
    assert not r['ok'] and 'si toccano' in r['message'], r
    r = s.forata('SM1/sopra', {'forma': 'tondo', 'd': 5, 'px': 10, 'disposizione': 'fila', 'margine': 60})
    assert not r['ok'] and 'nessun foro intero' in r['message'], r
    r = s.forata('SM1/sopra', {'forma': 'asola', 'lung': 5, 'larg': 5, 'px': 10, 'disposizione': 'fila', 'margine': 10})
    assert not r['ok'] and 'più lunga che larga' in r['message'], r
    a = s.forata_anteprima('SM1/sopra', {'forma': 'tondo', 'd': 5, 'px': 6, 'disposizione': 'fila', 'margine': 10})
    assert a['ok'] and a['avvisi'] and 'meno dello spessore' in a['avvisi'][0], a
    assert len(s.doc.features) == 2                           # niente lasciato a metà


def test_taglio_di_riserva_da_lo_stesso_pezzo(piastra, monkeypatch):
    """Se il modo veloce non riesce si fa il taglio booleano di sempre: stesso volume, stesso sviluppo."""
    s = piastra
    monkeypatch.setattr(F, '_fori_diretti', lambda *a, **k: None)
    r = s.forata('SM1/sopra', {'forma': 'tondo', 'd': 5, 'px': 20, 'py': 20, 'disposizione': 'fila', 'margine': 10})
    assert r['ok'], r
    n = s.result.body.sheet.forate['LF1']['n']
    assert s.result.body.sheet.forate['LF1']['diretto'] is False
    assert _volume(s) == pytest.approx(200 * 100 * T - n * math.pi * 6.25 * T, rel=1e-6)
    assert len(_fori_sviluppo(s)) == n


def test_duemila_fori_non_bloccano(tmp_path):
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 600, 'profondita': 400, 'spessore': 1.5, 'raggio': 1.5, 'k': 0.4})['ok']
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    spec = {'forma': 'tondo', 'd': 5, 'px': 11, 'disposizione': 'sfalsata', 'margine': 10}
    t0 = time.perf_counter()
    a = s.forata_anteprima('SM1/sopra', spec)
    t_ant = time.perf_counter() - t0
    assert a['ok'] and a['n'] > 2000, a['n']
    assert t_ant < 2.0, t_ant
    t0 = time.perf_counter()
    r = s.forata('SM1/sopra', spec)
    t_fatto = time.perf_counter() - t0
    assert r['ok'], r
    assert s.result.body.sheet.forate['LF1']['n'] == a['n']
    assert t_fatto < 15.0, t_fatto                  # col taglio booleano erano più di 20 secondi
    t0 = time.perf_counter()
    assert s.select('lf=LF1')['ok']
    assert time.perf_counter() - t0 < 2.0


def test_su_una_faccia_storta_della_tramoggia():
    """Su una forma a facce (la tramoggia col cassone) la faccia è un trapezio: i fori vicino ai lati storti che non ci
    stanno interi saltano (e si contano), il volume tolto è quello dei fori."""
    s = Service()
    assert s.new_project('tramoggia_cassone', {'name': 'T', 'A': 1000, 'B': 800, 'Hc': 500, 'a': 250, 'b': 300, 'Ht': 600,
                                               'ex': 80, 'spessore': 3, 'raggio': 3, 'k': 0.4})['ok']
    v0 = _volume(s)
    faccia = 'FM1/tramoggia_davanti/dentro'
    r = s.forata(faccia, {'forma': 'tondo', 'd': 8, 'px': 20, 'disposizione': 'sfalsata', 'margine': 20})
    assert r['ok'], r
    info = s.result.body.sheet.forate['LF1']
    assert info['n'] > 500 and 0 < info['scartati'] < info['n']
    assert v0 - _volume(s) == pytest.approx(info['n'] * math.pi * 16 * 3, rel=1e-6)


def test_togliendo_la_piega_va_via_anche_la_sua_lamiera_forata(piegata):
    s = piegata
    assert s.forata('SM1/FL1/esterno', {'forma': 'tondo', 'd': 5, 'px': 10, 'disposizione': 'fila', 'margine': 5})['ok']
    m = s.tree_menu('flange', 'SM1/FL1')
    assert m['ok'] and any('forata' in x.lower() for x in m['dipendenti']), m
    r = s.tree_action('flange', 'SM1/FL1', 'elimina')
    assert r['ok'], r
    assert not any(isinstance(f, dict) and f.get('type') == 'sheet_perforate' for f in s.doc.features)
