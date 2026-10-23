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
    assert abs(alto2['T'][1] - tx - 10) < 1e-6 and abs(alto2['T'][2] - ty + 5) < 1e-6   # la vista si è spostata
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
