"""Il porta punte e maschi della vetrina (21/10): pieghe in catena in ordine lungo lo sviluppo, tavola con la
tabella fori quando i tipi di foro sono tanti, assieme senza interferenze."""
import importlib.util
from pathlib import Path

from cad_engine import drawings as D

QUI = Path(__file__).resolve().parents[1]


def _vetrina(cartella):
    spec = importlib.util.spec_from_file_location('vetrina_portapunte', QUI / 'tools' / 'vetrina_portapunte.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.D = cartella
    return m


def test_porta_punte(tmp_path):
    m = _vetrina(tmp_path)
    s, f = m.corpo()
    sh = s.result.body.sheet
    assert [g.fid for g in sh.in_ordine()] == ['FL2', 'FL1', 'FL3', 'FL4', 'FL5', 'FL6', 'FL7', 'FL8']
    assert [b['flange'] for b in sh.summary()['bends']][:3] == ['FL2', 'FL1', 'FL3']
    foglio = D.tavola_pezzo(s.result.body.shape, {'titolo': 'x'}, D.etichette_fori(s.doc))
    testi = [t[2] if isinstance(t, tuple) else str(t) for t in foglio.testi]
    assert any('TABELLA FORI' in str(t) for t in testi)
    assert not any('svasato' in str(t) and '×' in str(t) and str(t).startswith(('2×', '3×')) for t in testi)
    _, ff = m.fianco('Fianco')
    a = m.assieme(f, ff)
    assert not a.asm.warnings and not a.asm_interferences().get('interferences')
