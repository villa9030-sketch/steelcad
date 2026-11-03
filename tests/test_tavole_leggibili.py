"""03/11: tavole leggibili e complete sui pezzi veri dei percorsi (collare calandrato, staffa con fori e asola, porta
ugelli con scritte tagliate e marcate): quote grandi abbastanza su A3 e A4, fori e asole quotati anche nello sviluppo,
R55 e gambe del collare, marcatura in verde anche nella vista dall'alto, calandratura segnata (tavola e file pieghe),
nome del pezzo dal nome del file, avviso sugli angoli quasi tondi nel profilo."""
import math

import pytest

from app.service import Service
from cad_engine import drawings as D

DATI = {'raggio': 1, 'k': 0.4}


def _collare(nome=None, storto=False):
    s = Service()
    assert s.new_project('zero', {'name': nome} if nome else {})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    if storto:                                  # l'arco preso col mouse: il centro 1 mm sotto la base
        assert s.sketch_add_polyline(sid, [[0, 0], [28, 0]], False)['ok']
        assert s.sketch_add_arc3(sid, [28, 0], [85, 55], [140, 0])['ok']
        assert s.sketch_add_polyline(sid, [[140, 0], [168, 0]], False)['ok']
    else:
        assert s.sketch_add_polyline(sid, [[-83, 0], [-55, 0]], False)['ok']
        assert s.sketch_add_arc3(sid, [-55, 0], [0, 55], [55, 0])['ok']
        assert s.sketch_add_polyline(sid, [[55, 0], [83, 0]], False)['ok']
    r = s.create_from_sketch(sid, 'profilo', {'lunghezza': 30, 'spessore': 3, 'calandra': True, 'gira': True, **DATI})
    assert r['ok'], r.get('message')
    return s


def _staffa():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 200, 'profondita': 100, 'spessore': 3, 'raggio': 1.5, 'k': 0.4})['ok']
    assert s.add_flange('SM1', 'L1', {'length': '60'})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    for x, y in ((20, 20), (180, 20), (20, 75.5), (180, 75.5)):
        assert s.sketch_add_circle(sid, [x, y], 5.25)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    sid = s.sketch_on_face('SM1/FL1/esterno')['sketch']
    assert s.sketch_add_slot(sid, [90, 27.75], [110, 27.75], 5)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    return s


def _testi(f):
    return [t[2] for t in f.testi]


def _fogli(s, formato='A3'):
    s._tavole_base = None
    return s._fogli({**s.drawing_fields()['fields'], 'formato': formato})


@pytest.mark.parametrize('formato,minimo', [('A3', 3.4), ('A4', 2.45)])
def test_quote_leggibili_su_a3_e_a4(formato, minimo):
    """Le quote stampate: 3,5 mm sull'A3, 2,5 mm sull'A4 (prima 2 e 1,4 mm: «minuscole e illeggibili»); le altre
    scritte delle quote (note dei fori, quote progressive) poco meno."""
    s = _staffa()
    for f in _fogli(s, formato):
        quote = [e['h'] for e in f.elementi.values() if e['kind'] == 'quota']
        assert quote and min(quote) >= minimo, (f.titolo, min(quote))
        hq = [h for l, _, t, h, _ in f.testi if l == 'quote']
        assert min(hq) >= minimo * 0.85, (f.titolo, min(hq))


def test_staffa_asola_quotata_e_fori_nello_sviluppo():
    s = _staffa()
    pezzo, sviluppo = _fogli(s)
    t = _testi(pezzo)
    assert 'Asola 30 × 10' in t                                   # l'asola ha la sua nota
    assert '32,25' in t                                          # e la sua posizione (centro dal bordo)
    assert '4× Ø10,5' in t
    t = _testi(sviluppo)
    assert '4× Ø10,5' in t and 'Asola 30 × 10' in t             # anche nello sviluppo
    assert {'20', '80', '27,75'} <= set(t)                       # posizioni dei fori e dell'asola dal bordo


def test_fori_e_asole_dello_sviluppo():
    giro = [(math.cos(a / 24 * 2 * math.pi) * 5, math.sin(a / 24 * 2 * math.pi) * 5) for a in range(25)]
    esterno = [(-50, -50), (50, -50), (50, 50), (-50, 50), (-50, -50)]
    lettera = [(0, 0), (10, 0), (10, 3), (3, 3), (3, 10), (0, 10), (0, 0), (0, 0)]
    asola = [(20 + 5 * math.cos(a), 5 * math.sin(a)) for a in [i * math.pi / 12 - math.pi / 2 for i in range(13)]]
    asola += [(-20 + 5 * math.cos(a), 5 * math.sin(a)) for a in [i * math.pi / 12 + math.pi / 2 for i in range(13)]]
    asola.append(asola[0])
    r = D.fori_e_asole([esterno, [(x + 20, y + 20) for x, y in giro], lettera, asola])
    assert [o['kind'] for o in r] == ['foro', 'asola']
    assert r[0]['d'] == pytest.approx(10, abs=0.01) and r[0]['c'] == pytest.approx((20, 20))
    assert r[1]['L'] == pytest.approx(50) and r[1]['W'] == pytest.approx(10) and r[1]['orizzontale']


def test_collare_raggio_gambe_e_calandratura(tmp_path):
    s = _collare()
    pezzo, sviluppo = _fogli(s)
    t = _testi(pezzo)
    assert 'R55 int.' in t                                       # il raggio interno dell'arco
    assert t.count('28') >= 2 and '110' in t                     # le gambe e la luce interna
    t = _testi(sviluppo)
    assert 'CALANDRARE R55 int.' in t and 'C1' in t
    assert sum(1 for (l, _), t in zip(sviluppo.linee, sviluppo.linee.tag) if l == 'calandra' and t != 'legenda') == 2
    assert any(r == 'calandrare R55 int.' for r in t)            # e la riga in tabella
    assert {'25,79', '27,44', '197,28', '198,93'} <= set(t)      # dove sono le linee, dal bordo
    p = tmp_path / 'p.csv'
    r = s.export_bend_table(str(p))
    assert r['ok'] and 'calandratura' in r['message']
    csv = p.read_text(encoding='utf-8-sig')
    assert 'Calandrare;Raggio interno mm' in csv and 'C1;55,00;172,23;27,44;197,28' in csv


def test_marcatura_verde_anche_nella_vista_dall_alto(tmp_path):
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 120, 'spessore': 2, 'raggio': 1, 'k': 0.4})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_text(sid, [150, 30], 'PORTA UGELLI', 10, 0, None, True)['ok']
    assert s.create_from_sketch(sid, 'mark', {})['ok']
    pezzo, sviluppo = _fogli(s)
    assert any(l == 'marca' and t == 'vista:alto/marcatura' for (l, _), t in zip(pezzo.linee, pezzo.linee.tag))
    assert not any(l == 'marca' and t.startswith('vista:fronte') for (l, _), t in zip(pezzo.linee, pezzo.linee.tag))
    assert any(l == 'marca' for l, _ in sviluppo.linee) and 'marcatura laser' in _testi(sviluppo)   # legenda
    assert not any(l == 'testo' and len(p) > 1 for l, p in sviluppo.linee)    # non più col tratto nero dei tagli
    svg = D.to_svg(sviluppo)
    assert '#1A8040' in svg
    assert s.export_drawings(str(tmp_path / 't.pdf'), s.drawing_fields()['fields'])['ok']
    assert b'0.10 0.50 0.25 RG' in (tmp_path / 't.pdf').read_bytes()


def test_nome_del_pezzo_dal_file(tmp_path):
    s = _staffa()
    assert s._nome_file() == 'Lamiera'                          # non salvato: quello di serie
    assert s.save(str(tmp_path / 'Staffa muro.steelcad'))['ok']
    assert s._nome_file() == 'Staffa muro'
    assert s.prepara_info()['voci'][0]['file'] == 'Staffa muro_sviluppo.dxf'
    p = s.drawing_preview()
    assert [x['title'] for x in p['sheets']] == ['Staffa muro', 'Staffa muro — sviluppo']
    s.doc.meta['name'] = 'Squadretta'                           # un nome dato dall'utente vince sul file
    assert s._nome_file() == 'Squadretta'
    s.doc.meta['codice'] = 'SQ-12'
    s._tavole_base = None
    assert 'SQ-12' in s.drawing_preview()['sheets'][0]['svg']   # il codice nel cartiglio


def test_avviso_angoli_quasi_tondi():
    assert _collare().avvisi_angoli() == []                      # disegnato giusto: niente
    s = _collare(storto=True)
    a = s.avvisi_angoli()
    assert len(a) == 2 and all('88,98°, non 90°' in x for x in a)
    c = s.prepara_info()['controllo']
    assert c['ok'] and c['avvisi'] == a                         # avvisa, non blocca
