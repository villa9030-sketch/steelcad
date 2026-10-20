"""Una linea sciolta dimenticata nello sketch (anche fuori dallo schermo) non blocca più il taglio.

Caso vero del 19/10: 9 rettangoli in serie sulla faccia di sopra e una linea di 1030 mm sotto la lamiera, rimasta
da un clic: "Prima chiudi il contorno: c'è un'estremità libera in (40; -780)" e nessun taglio."""
from app.service import Service
from cad_engine.features.base import volume


def _faccia_sopra():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 300, 'spessore': 2})['ok']
    f = next(x for x in s.scene()['objects'][0]['faces'] if x['name'] and x['name'].endswith('sopra'))
    return s, s.sketch_on_face(f['name'])['sketch']


def test_linea_sciolta_non_blocca_il_taglio():
    s, sid = _faccia_sopra()
    v0 = volume(s.result.body.shape)
    assert s.sketch_add_rectangle(sid, [20, 20], [40, 60])['ok']
    assert s.sketch_add_rectangle(sid, [100, 20], [120, 60])['ok']
    assert s.sketch_add_polyline(sid, [[40, -780], [1070, -780]], False)['ok']
    v = s.sketch_view(sid)['sketch']
    assert v['ok'] and v['profiles'] == 2
    assert len(v['sciolte']) == 1 and 'linea sciolta' in v['status']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')
    assert abs((v0 - volume(s.result.body.shape)) - 2 * 20 * 40 * 2) < 1e-3


def test_coda_che_sporge_dal_contorno_non_conta():
    """Un rettangolo con una linea in più attaccata a uno spigolo: prima "contorno ambiguo", ora si taglia il rettangolo."""
    s, sid = _faccia_sopra()
    v0 = volume(s.result.body.shape)
    assert s.sketch_add_rectangle(sid, [50, 50], [100, 80])['ok']
    assert s.sketch_add_polyline(sid, [[100, 80], [130, 110]], False)['ok']
    v = s.sketch_view(sid)['sketch']
    assert v['ok'] and v['profiles'] == 1 and len(v['sciolte']) == 1
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    assert abs((v0 - volume(s.result.body.shape)) - 50 * 30 * 2) < 1e-3


def test_solo_linee_aperte_resta_contorno_aperto():
    """Se non c'è niente di chiuso il messaggio resta quello di prima (o è uno scheletro di struttura)."""
    s, sid = _faccia_sopra()
    assert s.sketch_add_polyline(sid, [[60, 60], [90, 60], [90, 90]], False)['ok']
    v = s.sketch_view(sid)['sketch']
    assert v['profiles'] == 0            # niente di chiuso (le linee aperte sono «disegno in corso», non un errore)
    r = s.create_from_sketch(sid, 'cut', {})
    assert not r['ok'] and 'aperta' in r['message']


def test_pieghe_in_serie_bumping():
    """19/10: 10 linee parallele e «Piega su questa linea» → «Disegna una sola linea». Ora ogni linea è un colpo:
    la striscia più grande resta ferma, le altre in catena dallo stesso verso; lo sviluppo non cambia."""
    import build123d as bd
    for verso in ('up', 'down'):
        s, sid = _faccia_sopra()
        assert s.set_sheet_tech('SM1', {'radius': 1, 'method': 'k', 'k': 0.33})['ok']
        prima = s.result.body.sheet.flat_size
        for y in (120, 130, 140, 150, 160):
            assert s.sketch_add_polyline(sid, [[0, y], [300, y]], False)['ok']
        r = s.sheet_fold(sid, 18, verso)
        assert r['ok'], r.get('message')
        sh = s.result.body.sheet
        assert len(sh.flanges) == 5
        assert all(abs(a - b) < 1e-6 for a, b in zip(sh.flat_size, prima))
        # 5 × 18° = 90°: la parte piegata sale (o scende) di parecchio, non a zig-zag
        bb = bd.Solid(s.result.body.shape).bounding_box()
        assert bb.size.Z > 100


def test_tabella_pieghe_in_ordine_lungo_il_pezzo():
    """19/10: pieghe aggiunte in tempi diversi uscivano in tabella nell'ordine di costruzione (PL11, PL10…PL1, PL12).
    Ora PL1… vanno da un bordo all'altro e la tabella dice dove sta ogni linea sullo sviluppo."""
    s, sid = _faccia_sopra()
    assert s.set_sheet_tech('SM1', {'radius': 1, 'method': 'k', 'k': 0.33})['ok']
    for y in (150, 160, 170):
        assert s.sketch_add_polyline(sid, [[0, y], [300, y]], False)['ok']
    assert s.sheet_fold(sid, 10, 'up')['ok']
    f = next(x for x in s.scene()['objects'][0]['faces'] if x['name'] and x['name'].endswith('sopra'))
    sid2 = s.sketch_on_face(f['name'])['sketch']
    assert s.sketch_add_polyline(sid2, [[0, 20], [300, 20]], False)['ok']
    assert s.sheet_fold(sid2, 30, 'up')['ok'], 'seconda piega'
    righe = s.result.body.sheet.summary()['bends']
    assert [r['flange'] for r in righe] == ['PL1', 'PL2', 'PL3', 'PL4']
    pos = [r['line_at'] for r in righe]
    assert pos == sorted(pos) and all(r['edge'].startswith('linea a ') for r in righe)


def test_due_linee_da_bordo_a_bordo_e_un_foro():
    """19/10: due linee da bordo a bordo (offset a 190 dalle testate, per accorciare) davano "estremità libera":
    la chiusura lungo il bordo ne faceva una sola. Ora ognuna toglie il suo pezzo più piccolo, e il foro resta foro."""
    s, sid = _faccia_sopra()
    v0 = volume(s.result.body.shape)
    assert s.sketch_add_polyline(sid, [[0, 40], [300, 40]], False)['ok']
    assert s.sketch_add_polyline(sid, [[0, 250], [300, 250]], False)['ok']
    assert s.sketch_add_circle(sid, [150, 150], 10)['ok']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')
    import math
    atteso = (40 * 300 + 50 * 300 + math.pi * 10 ** 2) * 2
    assert abs((v0 - volume(s.result.body.shape)) - atteso) < 1.0
