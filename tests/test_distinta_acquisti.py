"""Pezzi da acquistare e distinta materiali in Excel (21/10, Stefano: «una BOM con anche le guide da acquistare»)."""
import zipfile

from app.service import Service


def _piastra(cart, nome):
    s = Service()
    assert s.new_project('piastra', {'name': nome, 'larghezza': 200, 'altezza': 100, 'spessore': 5, 'foro': 10})['ok']
    f = cart / f'{nome}.steelcad'
    assert s.save(str(f))['ok']
    return f


def test_acquisto_in_distinta_e_excel(tmp_path):
    a, g = _piastra(tmp_path, 'Base'), _piastra(tmp_path, 'Guida')
    s = Service()
    assert s.new_assembly('Prova')['ok']
    for f in (a, g, g):
        assert s.asm_insert(str(f))['ok']
    assert s.save(str(tmp_path / 'prova.steelcad-asm'))['ok']
    r = s.asm_set_acquisto('I2', {'descrizione': 'Guida a sfere L200', 'codice': 'GS200', 'fornitore': 'Rossi'})
    assert r['ok'], r.get('message')
    bom = s._asm_state()['bom']
    guida = next(x for x in bom if 'Guida a sfere' in x['description'])
    assert guida['acquisto'] and guida['qty'] == 2 and 'GS200' in guida['description']
    assert s.select('I3')['selection']['acquisto']['codice'] == 'GS200'      # vale per tutte le copie
    p = tmp_path / 'distinta.xlsx'
    r = s.asm_export_bom(str(p))
    assert r['ok'], r.get('message')
    with zipfile.ZipFile(p) as z:
        assert {'xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml', 'xl/worksheets/sheet3.xml'} <= set(z.namelist())
        ordine = z.read('xl/worksheets/sheet2.xml').decode('utf-8')
        assert 'Guida a sfere L200' in ordine and 'GS200' in ordine and 'Rossi' in ordine and 'Base' not in ordine
    assert s.asm_set_acquisto('I2', None)['ok']
    assert not any(x['acquisto'] for x in s._asm_state()['bom'])
