"""Tavole e uscite, terzo giro (03/11): distinta Excel col nome del file, sviluppo più grande, «2 pz»/«specchiato»
nel cartiglio, avvisi del DXF, PDF con l'elenco dei fogli."""
from app.service import Service
from tests.test_uscite_officina import _pezzo


def test_distinta_excel_col_nome_del_file(tmp_path):
    a = _pezzo(tmp_path, 'Fianco sinistro.steelcad', 'Lamiera', 200)
    b = _pezzo(tmp_path, 'piastra.steelcad', 'Piastra di base', 300, piega=False)
    s = Service()
    s.new_assembly('Banchetto')
    assert s.asm_insert(str(a))['ok'] and s.asm_insert(str(b))['ok']
    righe = s._righe_distinta()
    nomi = [r['descrizione'] for r in righe]
    assert nomi == ['Fianco sinistro', 'Piastra di base'], nomi
    p = tmp_path / 'distinta.xlsx'
    assert s.asm_export_bom(str(p))['ok']
    import zipfile
    testo = zipfile.ZipFile(p).read('xl/sharedStrings.xml').decode('utf-8') if 'xl/sharedStrings.xml' in zipfile.ZipFile(p).namelist() \
        else ''.join(zipfile.ZipFile(p).read(n).decode('utf-8', 'ignore') for n in zipfile.ZipFile(p).namelist() if n.startswith('xl/worksheets'))
    assert 'Fianco sinistro' in testo and '>Lamiera<' not in testo


from cad_engine import drawings as D
from cad_engine import drawings_sviluppo as DS


def _scritte(f, gruppo):
    return [t for t, g in zip(f.testi, f.testi.tag) if str(g).startswith(gruppo)]


def test_tabella_pieghe_stretta_raggio_e_k_nel_titolo():
    righe = [['1', 'FL1', '40', '90°', 'su', '1', '0,21', '965'], ['2', 'FL2', '40', '90°', 'su', '1', '0,21', '1055']]
    intest, r, titolo = DS.tabella_pieghe(righe, {'1': '↑ 38,53'})
    assert 'R int.' not in intest and 'K' not in intest and len(r[0]) == len(intest) == 7
    assert titolo == 'TABELLA PIEGHE · R int. 1 · K 0,21'
    righe[1][5] = '2'                                     # raggi diversi: la colonna resta
    intest, r, titolo = DS.tabella_pieghe(righe, {})
    assert 'R int.' in intest and 'K' not in intest and titolo == 'TABELLA PIEGHE · K 0,21'


def test_fori_vicini_quote_progressive_senza_accavallarsi():
    """03/11: fori a 20, 42 e 47 dal bordo (vicino alle pieghe): la catena di quote corte si accavallava; ora quote
    progressive dal bordo, coi numeri allargati."""
    f = D.Foglio('A2')
    f.u = u = 1.8
    T = lambda p: (100 + p[0] * 0.2, 100 + p[1] * 0.2)  # noqa: E731
    fori = [{'kind': 'foro', 'd': 6.5, 'c': (x, y)} for x in (20, 42, 47, 500, 980) for y in (20, 25, 300, 1100)]
    D.quote_fori_sviluppo(f, T, (0, 0, 1000, 1134), fori, -8 * u, 8 * u, u)
    testi = _scritte(f, 'fori_sviluppo')
    nomi = [t[2] for t in testi]
    for v in ('20', '42', '47', '500', '980', '25', '300', '1100'):
        assert v in nomi, (v, nomi)
    scatole = [D._box_testo(t) for t in testi]
    for i in range(len(scatole)):
        for j in range(i + 1, len(scatole)):
            assert not D._tocca(scatole[i], scatole[j]), (testi[i][2], testi[j][2])
    # fori ben distanziati: resta la catena con «n × passo»
    g = D.Foglio('A2')
    g.u = u
    D.quote_fori_sviluppo(g, T, (0, 0, 1000, 600), [{'kind': 'foro', 'd': 9, 'c': (x, 300)} for x in (100, 350, 600, 850)],
                          -8 * u, 8 * u, u)
    assert '3 × 250 = 750' in [t[2] for t in _scritte(g, 'fori_sviluppo')]


def test_pannello_da_un_metro_sviluppo_piu_grande():
    """03/11: «Pannello finestra 970» (sviluppo 1044 × 1134 con fori sulle ali) usciva a 1:10 in A2 (1:14 in A3)
    con mezzo foglio vuoto: ora 1:7,5, la tabella pieghe stretta sopra il cartiglio."""
    s = Service()
    assert s.new_project('lamiera', {'name': 'Pannello', 'larghezza': 965, 'profondita': 1055, 'spessore': 1.5,
                                     'raggio': 1, 'k': 0.21})['ok']
    for lato in ('L1', 'L2', 'L3', 'L4'):
        assert s.add_flange('SM1', lato, {'length': '40'})['ok'], lato
    s._tavole_base = None
    fogli = s._fogli({**s.drawing_fields()['fields'], 'formato': 'A2'})
    svil = fogli[-1]
    scala = next(t[2] for t in svil.testi if t[2].startswith('1:'))
    assert scala in ('1:7,5', '1:5'), scala
    testi = [t[2] for t in svil.testi]
    assert 'TABELLA PIEGHE' in testi and 'R int.' not in testi


def _con_estrusione(cartella, nome, piega=True):
    s = Service()
    s.new_project('lamiera', {'name': nome, 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    if piega:
        assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']

    def fn():
        sk = s.doc.add_sketch('XY', 'boss')
        p = [sk.point(*q) for q in ((10, 10), (40, 10), (40, 40), (10, 40))]
        for a, b in zip(p, p[1:] + p[:1]):
            sk.line(a, b)
        s.doc.add_feature('extrude', 'Estrusione', sketch=sk.id, operation='add', distance=20)
    assert s._change('Estrusione', fn)['ok']
    p = cartella / f'{nome}.steelcad'
    assert s.save(str(p))['ok']
    return s, p


def test_lavorazioni_dopo_la_lamiera_avvisate_in_prepara(tmp_path):
    """03/11: dopo la lamiera un'estrusione sul pezzo pieno: lo sviluppo non la contiene. Il pezzo da solo lo dice
    coi nomi (non «E1»); nell'assieme «Prepara» lo dice pezzo per pezzo prima di salvare, e il DXF non esce
    (prima: «Milestone 3», «più spessori» solo dopo aver salvato)."""
    s1, a = _con_estrusione(tmp_path, 'Staffa')
    r = s1.export_dxf(str(tmp_path / 'x.dxf'))
    assert not r['ok'] and '«Estrusione»' in r['message'] and 'E1' not in r['message']
    _, b = _con_estrusione(tmp_path, 'Piatto', piega=False)
    c = _pezzo(tmp_path, 'Buona.steelcad', 'Buona', 200)
    s = Service()
    s.new_assembly('Prova')
    for p in (a, b, c):
        assert s.asm_insert(str(p))['ok']
    info = s.prepara_info()
    laser = info['voci'][0]
    assert laser['si'] and laser['file'] == '1 DXF, ne mancano 2'
    avvisi = info['controllo']['avvisi']
    assert len(avvisi) == 2 and avvisi[0].startswith('Staffa: ') and '«Estrusione»' in avvisi[0]
    r = s.prepara(str(tmp_path / 'uscita'), ['laser'])
    assert r['files'] == ['DXF laser\\03 Buona - sp 2 - 1 pz.dxf'] and 'Milestone' not in r['message']


def test_tavole_assieme_quanti_pezzi_e_specchiato(tmp_path):
    """03/11: nelle tavole dei pezzi dell'assieme il titolo dice quanti ne servono e se c'è lo specchiato."""
    a = _pezzo(tmp_path, 'Staffa.steelcad', 'Lamiera', 200)
    b = _pezzo(tmp_path, 'Staffa specchiato.steelcad', 'Staffa specchiato', 200)
    c = _pezzo(tmp_path, 'Piastra.steelcad', 'Piastra', 300, piega=False)
    s = Service()
    s.new_assembly('Banco')
    for p in (a, a, b, b, c):
        assert s.asm_insert(str(p))['ok']
    s._tavole_base = None
    fogli = s._fogli({**s.drawing_fields()['fields'], 'formato': 'A3'}, True)
    assert [f.titolo for f in fogli][2:4] == ['Staffa', 'Staffa — sviluppo']      # il nome del foglio resta corto
    titoli = [next((t[2] for t in f.testi if t[2].startswith(f.titolo)), f.titolo) for f in fogli]   # nel cartiglio
    assert 'Staffa · 2 pz + 2 specchiati' in titoli, titoli
    assert 'Staffa — sviluppo · 2 pz + 2 specchiati' in titoli
    assert 'Staffa specchiato — sviluppo · 2 pz' in titoli
    assert 'Piastra' in titoli                                    # uno solo: non si scrive
    assert titoli[0] == 'Banco'                                   # l'assieme resta com'era


def test_pdf_assieme_grande_con_elenco_dei_fogli(tmp_path):
    """03/11: il PDF di un assieme con tanti fogli comincia con l'elenco dei fogli (foglio, pezzo, che cosa)."""
    import re
    from cad_engine import drawings_elenco as DE
    pezzi = [_pezzo(tmp_path, f'{n}.steelcad', n, 150 + 20 * i) for i, n in enumerate(('Fianco', 'Ripiano', 'Schiena', 'Cielo'))]
    s = Service()
    s.new_assembly('Armadio')
    for p in pezzi:
        assert s.asm_insert(str(p))['ok']
    campi = {**s.drawing_fields()['fields'], 'formato': 'A3'}
    fogli = s._fogli(campi, True)
    assert len(fogli) == 10                                    # assieme, esploso, 4 × (pezzo, sviluppo)
    righe = DE.righe_elenco(fogli)
    assert righe[0] == ['1', 'Armadio', 'assieme'] and righe[1] == ['2', 'Armadio', 'esploso']
    assert righe[2] == ['3', 'Fianco', 'disegno del pezzo'] and righe[3] == ['4', 'Fianco', 'sviluppo']
    p = tmp_path / 'armadio.pdf'
    r = s.export_drawings(str(p), campi, True)
    assert r['ok'], r.get('message')
    assert len(re.findall(rb'/Type\s*/Page[^s]', p.read_bytes())) == 11
    el = DE.tavola_elenco({**campi, 'titolo': 'Armadio — elenco dei fogli'}, righe)
    testi = [t[2] for t in el.testi]
    assert 'ELENCO DEI FOGLI' in testi and 'Schiena' in testi and '10' in testi
    # un pezzo solo: niente elenco
    s2 = Service()
    s2.open(str(pezzi[0]))
    p2 = tmp_path / 'fianco.pdf'
    assert s2.export_drawings(str(p2), {**s2.drawing_fields()['fields'], 'formato': 'A3'}, True)['ok']
    assert len(re.findall(rb'/Type\s*/Page[^s]', p2.read_bytes())) == 2
