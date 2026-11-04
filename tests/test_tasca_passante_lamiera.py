"""04/11, porta ugelli: una tasca passante fatta il 02/11 sulla faccia di una piega su bordo era un taglio di pezzo
pieno; il pezzo smetteva di essere lamiera e ogni «Togli materiale» dopo dava «va disegnato su una faccia di una
lamiera». All'apertura diventa un taglio di lamiera, e il comando sulla piega fa già un taglio di lamiera."""
import json
from pathlib import Path

from app.service import Service

DATI = Path(__file__).parent / 'data'


def _apri(tmp_path, extra=()):
    d = json.loads((DATI / 'porta_ugelli_tasca.steelcad').read_text(encoding='utf-8'))
    d['features'] += list(extra)
    p = tmp_path / 'porta.steelcad'
    p.write_text(json.dumps(d), encoding='utf-8')
    s = Service()
    assert s.open(str(p))['ok']
    return s


def test_tasca_passante_vecchia_diventa_lamiera(tmp_path):
    s = _apri(tmp_path, [{'id': 'TG9', 'type': 'sheet_cut', 'name': 'Taglio', 'sketch': 'S16'}])
    e1 = s.doc.feature('E1')
    assert e1['type'] == 'sheet_cut' and 'through_all' not in e1
    falliti = [f.message for f in s.result.features if not f.ok]
    assert not falliti, falliti
    assert getattr(s.result.body, 'sheet', None) is not None


def test_taglio_sulla_piega_e_di_lamiera(tmp_path):
    s = _apri(tmp_path)
    prima = {(f.id if hasattr(f, 'entities') else f['id']) for f in s.doc.features}
    r = s.create_from_sketch('S12', 'cut', {})
    assert r['ok'], r.get('message')
    nuovi = [f for f in s.doc.features if not hasattr(f, 'entities') and f['id'] not in prima]
    assert nuovi and all(f['type'] == 'sheet_cut' for f in nuovi), nuovi
    assert getattr(s.result.body, 'sheet', None) is not None


def test_messaggio_dice_quale_lavorazione(tmp_path):
    d = json.loads((DATI / 'porta_ugelli_tasca.steelcad').read_text(encoding='utf-8'))
    for f in d['features']:
        if f['id'] == 'E1':                 # una tasca non passante resta di pezzo pieno
            f.pop('through_all'); f['distance'] = 1; f['name'] = 'Tasca'
    d['features'].append({'id': 'TG9', 'type': 'sheet_cut', 'name': 'Taglio', 'sketch': 'S16'})
    p = tmp_path / 'porta.steelcad'
    p.write_text(json.dumps(d), encoding='utf-8')
    s = Service()
    assert s.open(str(p))['ok']
    m = next(f.message for f in s.result.features if f.id == 'TG9')
    assert '«Tasca»' in m, m
