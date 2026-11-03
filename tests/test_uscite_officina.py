"""03/11, uscite secondo giro: «Prepara per l'officina» delle strutture in tubo (distinta di taglio coi nomi da
officina anche per i pezzi degli incroci, luci tra i tubi nelle viste, numeri di posizione), tavole d'assieme
leggibili (distinta con finitura, nomi dal file), cartiglio leggibile, fori quotati nello sviluppo delle forme,
DXF che si riaprono coi layer giusti e il «Prepara» dell'assieme con i DXF di tutti i pezzi in lamiera."""
import os

import ezdxf
import pytest

from app.service import Service
from cad_engine import drawings as D
from cad_engine.drawings_struttura import nome_riga, righe_taglio


def _telaio():
    """Il telaio 807 × 725 × 795 in 30×30×2 con la croce sopra e i fianchi divisi da un montante (incroci)."""
    s = Service()
    assert s.new_project('telaio', {'name': 'Telaio 807', 'L': 807, 'P': 725, 'H': 795, 'ripiano': 0,
                                    'profilo': '30x30x2', 'gambe': '30x30x2'})['ok']
    objs = [o for o in s.scene()['objects'] if o['kind'] == 'member']
    nome = lambda pre: next(o['id'].split('/')[1] for o in objs if o['name'].startswith(pre))  # noqa: E731
    assert s.add_traverso('ST1', nome('Traverso davanti'), nome('Traverso dietro'), 388.5, 'sotto', '30x30x2', False, '')['ok']
    assert s.add_traverso('ST1', nome('Fianco a sinistra'), nome('Fianco a destra'), 347.5, 'sotto', '30x30x2', False, '')['ok']
    for lato in ('Fianco a sinistra', 'Fianco a destra'):
        r = s.punto_su_tubo('ST1', nome(lato), 347.5)
        assert s.tubo_da_angolo('ST1', r['node'].split(':')[1], 'giu', 795, '30x30x2', '')['ok']
    for g in ('Gamba davanti a sinistra', 'Gamba davanti a destra'):
        r = s.punto_su_tubo('ST1', nome(g), 383)
        assert s.tubo_da_angolo('ST1', r['node'].split(':')[1], 'dietro', 725, '30x30x2', '')['ok']
    return s


@pytest.fixture(scope='module')
def telaio():
    return _telaio()


def _testi(f, tag=None):
    return [t[2] for t, g in zip(f.testi, f.testi.tag) if tag is None or str(g).startswith(tag)]


def test_nome_riga_da_officina():
    assert nome_riga(['Gamba davanti a sinistra', 'Gamba dietro a destra', 'Gamba davanti a destra',
                      'Gamba dietro a sinistra']) == 'Gambe'
    assert nome_riga(['Fianco in alto (1)']) == 'Fianco in alto'
    assert nome_riga(['Montante a sinistra', 'Montante a destra']) == 'Montanti: a sinistra; a destra'


def test_nome_riga_corto_per_i_pezzi_degli_incroci():
    """03/11 (collaudo): un pezzo tagliato dagli incroci prendeva tutti i nomi in fila, illeggibile in officina."""
    n = nome_riga(['Traverso in mezzo, a 400 da terra', 'Fianco a sinistra, a 383 da terra', 'Fianco a destra, a 383 da terra'])
    assert n == 'Traverso e fianchi'
    assert nome_riga(['Fianco a sinistra, a 383 da terra', 'Fianco a destra, a 383 da terra']) == 'Fianchi'
    assert nome_riga(['Traverso davanti', 'Gamba dietro', 'Mensola']) == 'Traverso, gamba e mensola'
    for x in (n, nome_riga(['Fianco in alto', 'Fianco a destra, a 383 da terra'])):
        assert len(x) <= 32


def test_distinta_di_taglio_senza_sigle(telaio):
    """I pezzi degli incroci (A1~1, M7~2…) sono righe normali col nome da officina, mai con le sigle."""
    righe = righe_taglio(telaio.result.structures)
    assert sum(r['qty'] for r in righe) == 17
    for r in righe:
        assert '~' not in r['nome'] and not any(x in r['nome'] for x in ('M7', 'A1', 'G1', 'ST1'))
        assert r['tagli'] == 'dritti'
    assert righe[0]['nome'] == 'Gambe' and righe[0]['qty'] == 4 and righe[0]['lunghezza'] == 795
    assert {r['lunghezza'] for r in righe} >= {332.5, 302.5}           # i due pezzi dei tubi tagliati dagli incroci


def test_tavola_struttura_luci_e_posizioni(telaio):
    telaio._tavole_base = None
    fogli = telaio._fogli({**telaio.drawing_fields()['fields'], 'formato': 'A3'})
    assert len(fogli) == 2
    vista, taglio = fogli
    luci = _testi(vista, 'vista:fronte/luci') + _testi(vista, 'vista:alto/luci') + _testi(vista, 'vista:sinistra/luci')
    # le luci tra i tubi: sopra il traverso a metà (352) e sotto (383), tra gamba e croce, tra gamba e montante
    for v in ('352', '383', '343,5', '373,5', '332,5', '302,5'):
        assert v in luci, (v, luci)
    tutte = _testi(vista)
    for v in ('807', '725', '795'):                                    # il fuori tutto resta
        assert v in tutte
    assert sorted(_testi(vista, 'vista:iso/posizioni')) == [str(i) for i in range(1, 7)]
    t = _testi(taglio)
    assert 'Gambe' in t and not any('~' in x for x in t)
    alto = max(h for (l, p, x, h, al) in taglio.testi if x == 'Gambe')
    assert alto >= 3.0                                                 # leggibile sull'A3 (prima 1,7 mm)


def leggi_xlsx(path) -> dict:
    """{nome foglio: [[testo delle celle]]}: legge il file Excel come lo legge Excel (zip di XML), senza librerie."""
    import re
    import zipfile
    import xml.etree.ElementTree as ET
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    rel = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        wb = ET.fromstring(z.read('xl/workbook.xml'))
        rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        out = {}
        for sh in wb.find('m:sheets', ns):
            foglio = ET.fromstring(z.read('xl/' + rels[sh.get(rel)]))
            righe = []
            for row in foglio.find('m:sheetData', ns):
                riga = []
                for c in row:
                    col = sum((ord(ch) - 64) * 26 ** i for i, ch in enumerate(reversed(re.match(r'[A-Z]+', c.get('r')).group())))
                    riga += [''] * (col - 1 - len(riga))
                    v = c.find('m:v', ns)
                    t = c.find('m:is/m:t', ns)
                    riga.append(v.text if v is not None else (t.text if t is not None else ''))
                righe.append(riga)
            out[sh.get('name')] = righe
    return out


def test_lista_di_taglio_excel_dal_prepara(telaio, tmp_path):
    info = telaio.prepara_info()
    voce = next(v for v in info['voci'] if v['id'] == 'taglio')
    assert voce['si'] and voce['file'].endswith('_taglio.xlsx')
    assert voce['titolo'] == 'Per la troncatrice o il laser tubo'
    assert not any(v['file'].endswith('.csv') and 'tubi' in v['file'] for v in info['voci'])   # niente doppione CSV
    r = telaio.prepara(str(tmp_path), ['taglio', 'officina'])
    assert r['ok'], r.get('message')
    assert any(x.endswith('_taglio.xlsx') for x in r['files']) and any(x.endswith('.pdf') for x in r['files'])
    fogli = leggi_xlsx(tmp_path / voce['file'])
    tab = fogli['Lista di taglio']
    assert tab[0][:6] == ['Pos.', 'Nome', 'Dove va', 'Profilo', 'Materiale', 'Lunghezza mm']
    assert {'Taglio 1', 'Taglio 2', 'Come vengono le punte', 'Angolo sul lato da mm', 'Q.tà', 'kg tot.'} <= set(tab[0])
    gambe = dict(zip(tab[0], tab[1]))
    assert gambe['Nome'] == 'Gambe' and gambe['Q.tà'] == '4' and gambe['Lunghezza mm'] == '795'
    assert gambe['Taglio 1'] == 'dritto' and 'Gamba' in gambe['Dove va']
    assert tab[-1][1] == 'Totale' and tab[-1][10] == '17'
    assert fogli['Barre da comprare'][1][:3] == ['30×30×2', 'S235', '17']


def test_prepara_con_la_vecchia_scelta_tubi_da_l_excel(telaio, tmp_path):
    """Chi chiama ancora prepara(…, ['tubi']) (il vecchio CSV) riceve il file Excel unico."""
    r = telaio.prepara(str(tmp_path), ['tubi'])
    assert r['ok'], r.get('message')
    assert len(r['files']) == 1 and r['files'][0].endswith('_taglio.xlsx')
    assert not list(tmp_path.glob('*.csv'))


@pytest.mark.parametrize('formato,minimo', [('A3', 1.85), ('A4', 1.3)])
def test_cartiglio_leggibile(formato, minimo):
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 200, 'profondita': 100, 'spessore': 3})['ok']
    s._tavole_base = None
    f = s._fogli({**s.drawing_fields()['fields'], 'formato': formato})[0]
    cart = [(t, h) for (l, p, t, h, al), g in zip(f.testi, f.testi.tag) if g == 'cartiglio']
    assert min(h for t, h in cart) >= minimo                           # le etichette (prima 1 mm sull'A3)
    assert max(h for t, h in cart) >= 2 * minimo                       # il titolo
    # e niente esce dal foglio
    W, H = f.size
    for _, pts in f.linee:
        for x, y in pts:
            assert -0.01 <= x <= W + 0.01 and -0.01 <= y <= H + 0.01


def test_fori_quotati_nello_sviluppo_della_tramoggia():
    s = Service()
    assert s.new_project('tramoggia_cassone', {'raggio': 3, 'k': 0.4})['ok']
    assert s.fori_guidati('FM1/cassone_destra/fuori', {'tipo': 'tondo', 'd': 12, 'x': 100, 'y': 60, 'fila': True,
                                                       'n': 3, 'passo': 50})['ok']
    s._tavole_base = None
    svil = s._fogli({**s.drawing_fields()['fields'], 'formato': 'A3'})[-1]
    t = _testi(svil, 'fori_sviluppo')
    assert '3× Ø12' in t and '2 × 50 = 100' in t


def _layer(path):
    doc = ezdxf.readfile(path)
    out = {}
    for e in doc.modelspace():
        out.setdefault(e.dxf.layer, []).append(e.dxftype())
    return out


def test_dxf_si_riaprono_coi_layer_giusti(tmp_path):
    """Lamiera con pieghe, profilo calandrato, cono e tramoggia: il DXF si riapre, il taglio è su CUT, le pieghe su
    BEND (una linea per piega), niente su layer sconosciuti."""
    from tests.test_tavole_leggibili import _collare, _staffa
    os.environ['STEELCAD_RULES'] = str(tmp_path / 'r.json')
    casi = [('staffa', _staffa())]
    casi.append(('collare', _collare()))
    for kind in ('cono', 'tramoggia'):
        s = Service()
        assert s.new_project(kind, {})['ok']
        casi.append((kind, s))
    for nome, s in casi:
        p = tmp_path / f'{nome}.dxf'
        r = s.export_dxf(str(p))
        assert r['ok'], (nome, r.get('message'))
        lay = _layer(p)
        assert set(lay) <= {'CUT', 'BEND', 'MARK', 'ENGRAVE'}, (nome, set(lay))
        assert lay.get('CUT'), nome
        pieghe = s.result.body.sheet.bend_lines
        assert lay.get('BEND', []).count('LINE') == len(pieghe), nome


def test_dxf_con_marcatura_sul_layer_mark(tmp_path):
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 120, 'spessore': 2, 'raggio': 1, 'k': 0.4})['ok']
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_text(sid, [150, 30], 'PORTA UGELLI', 10, 0, None, True)['ok']
    assert s.create_from_sketch(sid, 'mark', {})['ok']
    p = tmp_path / 'marcata.dxf'
    assert s.export_dxf(str(p))['ok']
    lay = _layer(p)
    assert lay.get('MARK') and lay.get('CUT') and lay.get('BEND', []).count('LINE') == 1


def _pezzo(cartella, nome_file, nome, larg, finitura=None, piega=True):
    s = Service()
    s.new_project('lamiera', {'name': nome, 'larghezza': larg, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    if piega:
        assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    if finitura:
        s.doc.meta['finitura'] = finitura
    p = cartella / nome_file
    assert s.save(str(p))['ok']
    return p


def test_assieme_distinta_tavole_e_dxf_di_tutti_i_pezzi(tmp_path):
    a = _pezzo(tmp_path, 'Fianco sinistro.steelcad', 'Lamiera', 200, {'tipo': 'zincato'})
    b = _pezzo(tmp_path, 'piastra.steelcad', 'Piastra di base', 300, piega=False)
    s = Service()
    s.new_assembly('Banchetto')
    assert s.asm_insert(str(a))['ok'] and s.asm_insert(str(a))['ok'] and s.asm_insert(str(b))['ok']
    s._tavole_base = None
    fogli = s._fogli({**s.drawing_fields()['fields'], 'formato': 'A3'}, True)
    distinta = fogli[0].elementi['distinta']
    assert distinta['intest'][5] == 'Finitura'
    nomi = [r[1] for r in distinta['righe']]
    assert 'Fianco sinistro' in nomi and 'Lamiera' not in nomi          # il nome dal file, non «Lamiera»
    assert any('Zincat' in r[5] for r in distinta['righe'])
    # le tavole di tutti i pezzi, col nome giusto nel cartiglio
    titoli = [f.titolo for f in fogli]
    assert any(t.startswith('Fianco sinistro') for t in titoli) and any(t.startswith('Piastra di base') for t in titoli)
    # i numeri di posizione dentro il foglio e uno per riga
    pos = [t for (l, p, t, h, al), g in zip(fogli[0].testi, fogli[0].testi.tag) if g == 'vista:iso' and t.isdigit()]
    assert sorted(pos) == ['1', '2']
    # il Prepara dell'assieme: i DXF di tutti i pezzi in lamiera nella cartella «DXF laser»
    info = s.prepara_info()
    laser = next(v for v in info['voci'] if v['id'] == 'laser')
    assert laser['si'] and laser['scelta']
    r = s.prepara(str(tmp_path / 'uscita'), ['laser'])
    assert r['ok'], r.get('message')
    fatti = sorted(x.name for x in (tmp_path / 'uscita' / 'DXF laser').iterdir())
    assert fatti == ['01 Fianco sinistro - sp 2 - 2 pz.dxf', '02 Piastra di base - sp 2 - 1 pz.dxf'], fatti
    lay = _layer(tmp_path / 'uscita' / 'DXF laser' / fatti[0])
    assert lay.get('CUT') and lay.get('BEND', []).count('LINE') == 1


def test_passi_uguali_in_una_quota_e_numeri_corti_alternati():
    assert D._passi_uguali([0, 25, 255, 485, 715, 945]) == [(0, 25, None), (25, 945, '4 × 230 = 920')]
    f = D.Foglio('A2')
    f.u = 1.8
    D.catena_quote(f, lambda p: (p[0] * 0.1, p[1] * 0.1), [0, 5, 10, 15, 60], lambda x: (x, 0), -10)
    dentro = [e.get('dentro', False) for e in f.elementi.values() if e['kind'] == 'quota']
    assert dentro == [False, True]           # «3 × 5 = 15» e «45», corte tutte e due: la seconda dall’altra parte
