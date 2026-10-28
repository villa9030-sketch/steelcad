"""Tavole ritoccate a mano (23/10): viste spostate, quote cambiate/nascoste/aggiunte, note, altezza dei testi; cartiglio
con i campi nuovi e il logo. I ritocchi stanno nel progetto, con Annulla."""
from PIL import Image

from app.service import Service


def _cassa():
    s = Service()
    s.new_project('lamiera', {'name': 'Cassa', 'larghezza': 420, 'profondita': 260, 'spessore': 2})
    return s


def _foglio(s, campi=None):
    p = s.drawing_preview(campi)
    assert p['ok']
    return p['sheets'][0]


def test_oggetti_della_tavola():
    f = _foglio(_cassa())
    assert f['chiave'] == 'pezzo' and f['ritocchi'] == {}
    tipi = {o['id']: o['kind'] for o in f['oggetti']}
    assert {'vista:fronte', 'vista:alto', 'vista:sinistra', 'cartiglio'} <= set(tipi)
    assert any(k == 'quota' for k in tipi.values())
    alto = next(o for o in f['oggetti'] if o['id'] == 'vista:alto')
    assert len(alto['T']) == 3 and len(alto['punti']) >= 4
    assert 'data-el="vista:alto"' in f['svg']


def test_ritocchi_salvati_con_annulla(monkeypatch, tmp_path):
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path))
    s = _cassa()
    f = _foglio(s)
    q = next(o for o in f['oggetti'] if o['kind'] == 'quota' and o['testo'] == '420')
    alto = next(o for o in f['oggetti'] if o['id'] == 'vista:alto')
    s_, tx, ty = alto['T']
    rit = {'viste': {'vista:alto': [10, -5]},
           'quote': {q['id']: {'testo': '420 ±0,5', 'd': 3}},
           'aggiunte': [{'vista': 'vista:alto', 'a': [0, 0], 'b': [420, 0], 'dir': 'h', 'd': -8}],
           'note': [{'x': 30, 'y': 40, 'testo': 'Sbavare tutti i bordi'}],
           'testi': {'quote': 4}}
    p = s.tavola_ritocchi('pezzo', rit)
    assert p['ok']
    f2 = p['sheets'][0]
    assert '420 ±0,5' in f2['svg'] and 'Sbavare tutti i bordi' in f2['svg']
    assert f2['ritocchi'] == rit and s.doc.meta['tavole']['pezzo'] == rit
    alto2 = next(o for o in f2['oggetti'] if o['id'] == 'vista:alto')
    # la vista si è spostata in giù; di lato no: resta sotto la fronte (viste allineate, 28/10)
    assert abs(alto2['T'][1] - tx) < 1e-6 and abs(alto2['T'][2] - ty + 5) < 1e-6
    agg = [o for o in f2['oggetti'] if o.get('aggiunta') is not None]
    assert len(agg) == 1 and agg[0]['testo'] == '420' and agg[0]['h'] == 4
    # nascondere una quota
    p = s.tavola_ritocchi('pezzo', {**rit, 'quote': {q['id']: {'via': True}}})
    assert q['id'] not in {o['id'] for o in p['sheets'][0]['oggetti']}
    # Annulla torna indietro, «Rimetti automatico» toglie tutto
    s.undo()
    assert s.doc.meta['tavole']['pezzo'] == rit
    s.tavola_ritocchi('pezzo', {})
    assert 'tavole' not in s.doc.meta and _foglio(s)['ritocchi'] == {}


def test_ritocchi_nel_pdf(monkeypatch, tmp_path):
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path))
    s = _cassa()
    s.tavola_ritocchi('pezzo', {'note': [{'x': 30, 'y': 40, 'testo': 'NOTA-PDF'}]})
    assert s.export_drawings(str(tmp_path / 't.pdf'), s.drawing_fields()['fields'])['ok']
    assert (tmp_path / 't.pdf').read_bytes().startswith(b'%PDF')


def test_cartiglio_campi_e_logo(monkeypatch, tmp_path):
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path / 'home'))
    s = _cassa()
    campi = {**s.drawing_fields()['fields'], 'cliente': 'Officine Rossi', 'tolleranze': 'ISO 2768-m'}
    svg = _foglio(s, campi)['svg']
    assert 'Officine Rossi' in svg and 'ISO 2768-m' in svg                # i campi nuovi compaiono se scritti
    nascosto = _foglio(s, {**campi, 'mostra': ['revisione', 'data']})['svg']
    assert 'Officine Rossi' not in nascosto                              # e si possono togliere
    assert s.set_logo(str(tmp_path / 'non-esiste.gif'))['ok'] is False
    Image.new('RGB', (200, 80), (200, 40, 40)).save(tmp_path / 'logo.png')
    r = s.set_logo(str(tmp_path / 'logo.png'))
    assert r['ok'] and r['logo'] and s.drawing_fields()['logo'] == r['logo']
    assert '<image' in _foglio(s, campi)['svg']
    assert s.export_drawings(str(tmp_path / 'l.pdf'), campi)['ok']
    assert b'/Subtype /Image' in (tmp_path / 'l.pdf').read_bytes()
    assert s.set_logo(None)['ok'] and s.drawing_fields()['logo'] is None


def test_dxf_sempre_1_a_1(monkeypatch, tmp_path):
    """24/10: «l'esportazione dei DXF deve essere sempre in scala 1:1» — su ogni formato le viste e lo sviluppo
    misurano quanto il pezzo; un layout per foglio per stamparlo in scala."""
    import ezdxf
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path))
    s = _cassa()
    for fmt in ('A4', 'A3', 'A2'):
        campi = {**s.drawing_fields()['fields'], 'formato': fmt}
        assert s.export_drawings(str(tmp_path / f'{fmt}.dxf'), campi)['ok']
        d = ezdxf.readfile(str(tmp_path / f'{fmt}.dxf'))
        lun = {round(abs(e.dxf.end.x - e.dxf.start.x), 3) for e in d.modelspace() if e.dxftype() == 'LINE' and e.dxf.layer == 'contorno'}
        assert 420.0 in lun, (fmt, sorted(lun)[-4:])
        sv = [e for e in d.modelspace() if e.dxftype() == 'LWPOLYLINE' and e.dxf.layer == 'contorno']
        xs = [p[0] for e in sv for p in e.get_points()]
        assert abs(max(xs) - min(xs) - 420) < 0.01                     # lo sviluppo, anche lui a misura vera
        assert [l.name for l in d.layouts if l.name != 'Model'] == ['1 Cassa', '2 Cassa — sviluppo']


def _frecce(svg, nome):
    """Le frecce (triangoli) di una quota nello SVG: la loro lunghezza."""
    import re
    out = []
    for m in re.finditer(r'<polygon[^>]*data-el="' + re.escape(nome) + r'"[^>]*>', svg):
        pts = [tuple(map(float, p.split(','))) for p in re.search(r'points="([^"]+)"', m.group(0)).group(1).split()]
        out.append(max(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for a in pts for b in pts))
    return out


def test_quote_aggiunte_come_le_altre_e_frecce(monkeypatch, tmp_path):
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path))
    s = _cassa()
    campi = {**s.drawing_fields()['fields'], 'formato': 'A4'}
    f = _foglio(s, campi)
    assert abs(f['fattore'] - 0.5) < 1e-9
    auto = next(o for o in f['oggetti'] if o['kind'] == 'quota' and o['testo'] == '420')
    p = s.tavola_ritocchi('pezzo', {'aggiunte': [{'vista': 'vista:alto', 'a': [0, 0], 'b': [100, 0], 'dir': 'h', 'd': -20}]}, campi)
    f = p['sheets'][0]
    agg = next(o for o in f['oggetti'] if o.get('aggiunta') is not None)
    assert abs(agg['h'] - auto['h']) < 1e-6 and abs(agg['freccia'] - auto['freccia']) < 1e-6   # uguale alle altre
    assert _frecce(f['svg'], agg['id']) and all(abs(x - _frecce(f['svg'], auto['id'])[0]) < 0.05 for x in _frecce(f['svg'], agg['id']))
    # frecce più grandi per tutta la tavola e per una quota sola
    f = s.tavola_ritocchi('pezzo', {'testi': {'frecce': 4}, 'quote': {auto['id']: {'freccia': 6}}}, campi)['sheets'][0]
    altra = next(o for o in f['oggetti'] if o['kind'] == 'quota' and o['testo'] == '260')
    assert _frecce(f['svg'], altra['id']) and all(abs(x - 4) < 0.3 for x in _frecce(f['svg'], altra['id']))
    assert all(abs(x - 6) < 0.3 for x in _frecce(f['svg'], auto['id']))


def test_quota_corta_frecce_fuori():
    from cad_engine import drawings as D
    f = D.Foglio('A3')
    D.quota(f, (0, 0), (2, 0), 5, 2, nome='q')
    (_, pts), = [(l, p) for (l, p), t in zip(f.pieni, f.pieni.tag) if t == 'q'][:1]
    # la freccia in A sta fuori (x < 0), puntata verso dentro
    assert min(p[0] for p in pts) < -1
    (_, (x, y), testo, h, al), = [(l, p, tx, h, al) for (l, p, tx, h, al), t in zip(f.testi, f.testi.tag) if t == 'q']
    assert testo == '2' and x > 2                                       # il numero di fianco, non sopra le frecce


def _T(f, nome):
    return next(o for o in f['oggetti'] if o['id'] == nome)['T']


def test_viste_allineate_alla_fronte():
    """28/10: l'alto resta sotto la fronte, il fianco accanto; la fronte se li porta dietro. «libere»: no."""
    s = _cassa()
    f0 = _foglio(s)
    a = s.tavola_ritocchi('pezzo', {'viste': {'vista:alto': [40, -10], 'vista:sinistra': [15, 30]}})['sheets'][0]
    assert _T(a, 'vista:alto')[1] == _T(f0, 'vista:alto')[1]                  # di lato non si sposta
    assert abs(_T(a, 'vista:alto')[2] - _T(f0, 'vista:alto')[2] + 10) < 1e-6
    assert _T(a, 'vista:sinistra')[2] == _T(f0, 'vista:sinistra')[2]          # in su e in giù no
    b = s.tavola_ritocchi('pezzo', {'viste': {'vista:fronte': [20, 5]}})['sheets'][0]
    for v in ('vista:fronte', 'vista:alto', 'vista:sinistra'):
        assert abs(_T(b, v)[1] - _T(f0, v)[1] - 20) < 1e-6 and abs(_T(b, v)[2] - _T(f0, v)[2] - 5) < 1e-6
    c = s.tavola_ritocchi('pezzo', {'viste': {'vista:alto': [40, 0]}, 'libere': ['vista:alto']})['sheets'][0]
    assert abs(_T(c, 'vista:alto')[1] - _T(f0, 'vista:alto')[1] - 40) < 1e-6


def test_fianco_da_destra_senza_isometrica_e_vista_tolta():
    s = _cassa()
    f = _foglio(s, {**s.drawing_fields()['fields'], 'fianco': 'destra', 'isometrica': 'no'})
    ids = {o['id'] for o in f['oggetti']}
    assert 'vista:destra' in ids and 'vista:sinistra' not in ids and 'vista:iso' not in ids
    assert _T(f, 'vista:destra')[1] < _T(f, 'vista:fronte')[1]               # europea: a sinistra della fronte
    assert 'VISTA DA DESTRA' in f['svg']
    g = s.tavola_ritocchi('pezzo', {'tolte': ['vista:iso']})['sheets'][0]
    assert 'vista:iso' not in {o['id'] for o in g['oggetti']} and 'ISOMETRICA' not in g['svg']


def test_dettaglio_ingrandito():
    s = _cassa()
    f0 = _foglio(s)
    s_, tx, ty = _T(f0, 'vista:fronte')
    bb = next(o for o in f0['oggetti'] if o['id'] == 'vista:fronte')['bbox']
    angolo = ((bb[2] - tx) / s_, (bb[3] - ty) / s_)                         # l'angolo in alto a destra della fronte
    f = s.tavola_ritocchi('pezzo', {'dettagli': [{'vista': 'vista:fronte', 'c': list(angolo), 'r': 8, 'k': 3,
                                                  'p': [bb[2] + 60, bb[3]], 'lettera': 'A'}]})['sheets'][0]
    d = next(o for o in f['oggetti'] if o['id'] == 'dettaglio:A')
    assert abs(d['T'][0] - 3 * s_) < 1e-9 and 'DETTAGLIO A (' in f['svg']
    assert d['punti']                                                        # dentro ci sono spigoli (si quota)
    assert not f['persi']


def test_ritocchi_persi_si_dicono():
    s = _cassa()
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    s.sketch_add_circle(sid, [300, 130], 20)
    s.create_from_sketch(sid, 'cut', {})
    f = _foglio(s)
    q = next(o['id'] for o in f['oggetti'] if o['kind'] == 'quota' and o['id'].startswith('vista:alto/'))
    s.tavola_ritocchi('pezzo', {'quote': {q: {'testo': 'XX'}, 'vista:alto/q99': {'testo': 'perso'}},
                                'viste': {'vista:destra': [5, 5]}})
    p = _foglio(s)
    testi = ' | '.join(x['testo'] for x in p['persi'])
    assert '«perso»' in testi and 'vista da destra' in testi and '«XX»' not in testi
