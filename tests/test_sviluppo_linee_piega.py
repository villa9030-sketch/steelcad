"""Sullo sviluppo le pieghe sono guide dello sketch: linea di piega e bordi della striscia, fisse, ci si aggancia,
ci si quota e le linee disegnate si accorciano lì (21/10: il taglio a 45° del cassone attraverso le pieghe)."""
import math
import os
import tempfile

import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402

T, R, K = 2, 1, 0.21
BA = math.pi / 2 * (R + K * T)


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


def cassone():
    s = Service()
    assert s.new_project('lamiera', {'name': 'C', 'larghezza': 200, 'profondita': 100, 'spessore': T, 'raggio': R, 'k': K})['ok']
    assert s.add_flange('SM1', 'L1', {'length': '30'})['ok']
    assert s.add_flange('SM1', None, {'length': '20'}, 'FL1')['ok']
    return s


def guide(v):
    P = {p['id']: p['xy'] for p in v['points']}
    return [(l['piega'], P[l['a']], P[l['b']], l['id']) for l in v['lines'] if l.get('piega')]


def test_sullo_sviluppo_ci_sono_le_pieghe_come_guide():
    s = cassone()
    sid = s.sketch_on_flat('SM1')['sketch']
    g = guide(s.sketch_view(sid)['sketch'])
    assert sorted(x[0] for x in g) == ['bordo'] * 4 + ['centro'] * 2
    for tipo, a, b, _ in g:
        assert abs(a[1] - b[1]) < 1e-6 and abs(abs(a[0] - b[0]) - 200) < 1e-6     # da bordo a bordo
    # i bordi di una striscia distano BA
    ys = sorted(a[1] for tipo, a, b, _ in g if tipo == 'bordo')
    assert ys[1] - ys[0] == pytest.approx(BA, abs=1e-3) and ys[3] - ys[2] == pytest.approx(BA, abs=1e-3)
    st = s.state()
    assert st['errors'] == []
    # sono guide: non si cancellano, lo sketch resta vuoto (niente da tagliare)
    assert s.sketch_view(sid)['sketch']['drawn'] == 0


def test_linea_disegnata_si_accorcia_sul_bordo_della_piega_e_si_quota():
    s = cassone()
    sid = s.sketch_on_flat('SM1')['sketch']
    g = guide(s.sketch_view(sid)['sketch'])
    ys = sorted(a[1] for tipo, a, b, _ in g if tipo == 'bordo')
    y_lo, y_hi = min(ys) - 5, max(ys) + 5
    assert s.sketch_add_polyline(sid, [[100, y_lo], [100, y_hi]], False)['ok']
    v = s.sketch_view(sid)['sketch']
    mia = next(l for l in v['lines'] if not l['ref'])
    # clic sul tratto in basso: si accorcia fino al primo bordo di piega
    r = s.sketch_trim(sid, mia['id'], [100, y_lo + 1])
    assert r['ok'], r
    v = s.sketch_view(sid)['sketch']
    P = {p['id']: p['xy'] for p in v['points']}
    tratti = [sorted((P[l['a']][1], P[l['b']][1])) for l in v['lines'] if not l['ref']]
    assert min(t[0] for t in tratti) == pytest.approx(min(ys), abs=1e-6)
    # quota dalla linea di piega a un punto disegnato
    centro = next(x for x in g if x[0] == 'centro')
    p_mio = next(p for p in v['points'] if abs(p['xy'][1] - y_hi) < 1e-6)
    r = s.sketch_dimension(sid, 'pldistance', [p_mio['id'], centro[3]])
    assert r['ok'], r


def test_taglio_sullo_sviluppo_attraverso_le_pieghe_con_le_guide():
    """Un contorno chiuso che passa sopra le pieghe si taglia come prima: le guide non lo spezzano."""
    s = cassone()
    prima = s.state()['sheet']['data']['flat_area']
    sid = s.sketch_on_flat('SM1')['sketch']
    v = s.sketch_view(sid)['sketch']
    ys = [p['xy'][1] for p in v['points']]
    y0 = min(ys)
    assert s.sketch_add_rectangle(sid, [170, y0 - 5], [200 + 5, 20])['ok']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r
    assert s.state()['errors'] == []
    assert prima - s.state()['sheet']['data']['flat_area'] == pytest.approx(30 * (20 - y0), abs=0.5)


def test_le_guide_si_fermano_dove_la_lamiera_e_tagliata():
    # flangia e orlo tagliati da 170 a 200: la piega tra i due lì non c'è più, la sua linea arriva a 170
    s = cassone()
    sid = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    assert s.sketch_add_rectangle(sid, [0, 0], [30, 24])['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    sid = s.sketch_on_face('SM1/FL2/esterno')['sketch']
    assert s.sketch_add_rectangle(sid, [0, 0], [30, 17])['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    sid = s.sketch_on_flat('SM1')['sketch']
    g = guide(s.sketch_view(sid)['sketch'])
    centri = sorted(round(abs(a[0] - b[0]), 3) for tipo, a, b, _ in g if tipo == 'centro')
    assert centri == [170, 200]


def test_spezzata_aperta_dal_bordo_agganciata_alle_guide_si_chiude_lungo_il_bordo():
    """21/10, il cassone: spezzata a 45° sullo sviluppo che parte e finisce sugli estremi delle guide (sul bordo del
    pezzo): «il bordo arancio della faccia è interrotto», le guide venivano prese per bordo."""
    s = cassone()
    prima = s.state()['sheet']['data']['flat_area']
    sid = s.sketch_on_flat('SM1')['sketch']
    v = s.sketch_view(sid)['sketch']
    P = {p['id']: p['xy'] for p in v['points']}
    estremi = sorted({(round(P[l['a']][0], 6), round(P[l['a']][1], 6)) for l in v['lines'] if l.get('piega')}
                     | {(round(P[l['b']][0], 6), round(P[l['b']][1], 6)) for l in v['lines'] if l.get('piega')})
    a_sx = sorted(p for p in estremi if abs(p[0]) < 1e-6)          # sul bordo x = 0, dal basso
    y_lo, y_hi = a_sx[0][1], a_sx[-1][1]
    h = y_hi - y_lo
    pts = [[0, y_lo], [h / 2, y_lo + h / 2], [0, y_hi]]
    assert s.sketch_add_polyline(sid, pts, False)['ok']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r
    assert s.state()['errors'] == []
    assert prima - s.state()['sheet']['data']['flat_area'] == pytest.approx(h * h / 4, rel=1e-3)


def test_spezzata_con_punti_doppi_e_bordo_ripassato_si_taglia():
    """21/10, il cassone (file vero): la punta a 45° con due punti sovrapposti a pochi decimillesimi (uno agganciato alla
    guida, l'altro dalla quota) e il bordo chiuso a mano due volte: «si incontrano 3 linee», poi il filo non chiuso."""
    s = cassone()
    prima = s.state()['sheet']['data']['flat_area']
    sid = s.sketch_on_flat('SM1')['sketch']
    v = s.sketch_view(sid)['sketch']
    P = {p['id']: p['xy'] for p in v['points']}
    rif = {x for l in v['lines'] if l['ref'] for x in (l['a'], l['b'])}
    bordo = sorted((xy[1], k) for k, xy in P.items() if abs(xy[0]) < 1e-9 and k in rif)
    (y0, pa), (y1, pb) = bordo[0], bordo[-1]
    h = y1 - y0
    assert s.sketch_add_polyline(sid, [pa, [h / 3, y0 + h / 3], [h / 3, y1 - h / 3]], False)['ok']
    assert s.sketch_add_polyline(sid, [[h / 3 + 3e-7, y1 - h / 3 + 6e-7], pb], False)['ok']   # quasi lo stesso punto
    assert s.sketch_add_polyline(sid, [pb, pa], False)['ok']
    assert s.sketch_add_polyline(sid, [pa, pb], False)['ok']                                   # il bordo ripassato
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r
    assert s.state()['errors'] == []
    attesa = (h + h / 3) * (h / 3) / 2
    assert prima - s.state()['sheet']['data']['flat_area'] == pytest.approx(attesa, rel=1e-3)


def test_quote_che_litigano_per_un_arrotondamento_diventano_di_riferimento():
    """21/10, il cassone: punto sulla guida della piega e in più una quota verticale col valore arrotondato
    (1119,267919 contro 1119,268251): «la quota … è in conflitto», lo sketch bloccato. Alla modifica dopo, la quota
    più recente diventa di riferimento e lo sketch torna buono."""
    s = cassone()
    sid = s.sketch_on_flat('SM1')['sketch']
    v = s.sketch_view(sid)['sketch']
    P = {p['id']: p['xy'] for p in v['points']}
    guida = next(l for l in v['lines'] if l.get('piega') == 'centro')
    yg = P[guida['a']][1]
    assert s.sketch_add_polyline(sid, [[50, yg - 30], [80, yg]], False)['ok']
    v = s.sketch_view(sid)['sketch']
    pid = next(p['id'] for p in v['points'] if abs(p['xy'][0] - 80) < 1e-6 and abs(p['xy'][1] - yg) < 1e-6
               and p['id'] not in {x for l in v['lines'] if l['ref'] for x in (l['a'], l['b'])})
    sk = s.doc.sketch(sid)
    sk.constrain('on_line', pid, guida['id'])
    sk.dimension('vdistance', 'O', pid, value=round(yg + 0.0003, 6))     # la stessa misura, arrotondata male
    s._rebuild()
    assert s.sketch_view(sid)['sketch']['status'].startswith('La quota')    # in conflitto
    r = s.sketch_add_polyline(sid, [[120, 40], [150, 40]], False, True)
    assert r['ok'] and 'riferimento' in (r.get('message') or ''), r
    assert 'conflitto' not in s.sketch_view(sid)['sketch']['status']
    assert any(c.get('driven') for c in s.doc.sketch(sid).constraints.values() if c['type'] == 'vdistance')


def test_linea_tra_due_punti_sovrapposti_non_blocca_lo_sketch():
    """21/10, CASSONE A: «collegare» due punti diversi che stanno nello stesso posto (uno sulla guida, uno dalle
    quote) faceva una linea lunga zero: «Con queste quote lato L53 ha lunghezza zero», tutto lo sketch bloccato."""
    s = cassone()
    sid = s.sketch_on_flat('SM1')['sketch']
    assert s.sketch_add_polyline(sid, [[40, 10], [60, 10]], False)['ok']
    assert s.sketch_add_polyline(sid, [[60, 10 + 3e-7], [60, 30]], False)['ok']       # parte quasi dallo stesso punto
    v = s.sketch_view(sid)['sketch']
    P = {p['id']: p['xy'] for p in v['points']}
    a = next(l['b'] for l in v['lines'] if not l['ref'] and abs(P[l['a']][0] - 40) < 1e-9)
    b = next(l['a'] for l in v['lines'] if not l['ref'] and abs(P[l['b']][1] - 30) < 1e-9)
    assert a != b
    n = len(v['lines'])
    r = s.sketch_add_polyline(sid, [a, b], False)            # il tratto non si fa: sono già insieme
    assert r['ok'], r
    assert len(s.sketch_view(sid)['sketch']['lines']) == n
    # e se c'è già (file vecchio), non blocca
    s.doc.sketch(sid).line(a, b)
    s._rebuild()
    assert 'lunghezza zero' not in s.sketch_view(sid)['sketch']['status']
    assert s.state()['errors'] == []
