"""Il nome del pezzo aperto da solo (03/11: clic sul nome in alto): va nel file, nella distinta dell'assieme, nel
cartiglio delle tavole e nel nome dei DXF; si annulla come le altre modifiche."""
from app.service import Service


def _lamiera():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 200, 'profondita': 100, 'spessore': 3})['ok']
    return s


def test_rinomina_il_pezzo_e_si_annulla():
    s = _lamiera()
    assert s.state()['name'] == 'Lamiera'
    r = s.rinomina_pezzo('  Staffa   sinistra ')
    assert r['ok'] and r['state']['name'] == 'Staffa sinistra' and r['state']['dirty']
    assert '«Staffa sinistra»' in r['message']
    assert s.undo()['state']['name'] == 'Lamiera'
    assert s.redo()['state']['name'] == 'Staffa sinistra'


def test_nomi_che_non_vanno():
    s = _lamiera()
    assert not s.rinomina_pezzo('')['ok']
    assert not s.rinomina_pezzo('a/b')['ok']
    assert s.state()['name'] == 'Lamiera'


def test_il_nome_va_nel_file_nelle_tavole_nel_dxf_e_in_distinta(tmp_path):
    s = _lamiera()
    assert s.save(str(tmp_path / 'lam1.steelcad'))['ok']
    r = s.rinomina_pezzo('Fianco destro')
    assert 'Il file resta lam1.steelcad' in r['message']
    assert s.save()['ok']
    # nel file: riaperto si chiama così (anche se il file si chiama lam1)
    t = Service()
    assert t.open(str(tmp_path / 'lam1.steelcad'))['ok'] and t.state()['name'] == 'Fianco destro'
    # DXF e «Prepara»: il nome del file
    assert t._nome_file() == 'Fianco destro'
    assert any(v['file'].startswith('Fianco destro') for v in t.prepara_info()['voci'])
    # cartiglio della tavola
    p = t.drawing_preview(t.drawing_fields()['fields'])
    assert p['ok'] and p['sheets'][0]['title'].startswith('Fianco destro')
    # distinta dell'assieme
    a = Service()
    assert a.new_assembly_con_pezzi('Prova', [{'path': str(tmp_path / 'lam1.steelcad')}])['ok']
    assert a.state()['bom'][0]['description'].startswith('Fianco destro')


def test_nell_assieme_si_rinomina_dal_pannello(tmp_path):
    s = _lamiera()
    assert s.save(str(tmp_path / 'Base.steelcad'))['ok']
    a = Service()
    assert a.new_assembly_con_pezzi('Prova', [{'path': str(tmp_path / 'Base.steelcad')}])['ok']
    assert not a.rinomina_pezzo('Altro')['ok']


def test_l_assieme_segue_il_pezzo_rinominato_da_solo(tmp_path):
    s = _lamiera()
    assert s.save(str(tmp_path / 'Base.steelcad'))['ok']
    a = Service()
    assert a.new_assembly_con_pezzi('Prova', [{'path': str(tmp_path / 'Base.steelcad'), 'n': 2}])['ok']
    assert a.asm_rinomina('I2', 'Piastra base')['ok']
    assert [i['name'] for i in a.asm.instances] == ['Piastra base', 'Piastra base (2)']
    assert a.save(str(tmp_path / 'Prova.steelcad-asm'))['ok']
    # il pezzo aperto da solo e rinominato
    p = Service()
    assert p.open(str(tmp_path / 'Base.steelcad'))['ok']
    assert p.rinomina_pezzo('Fondo')['ok'] and p.save()['ok']
    b = Service()
    assert b.open(str(tmp_path / 'Prova.steelcad-asm'))['ok']
    assert [i['name'] for i in b.asm.instances] == ['Fondo', 'Fondo (2)']
    assert b.state()['bom'][0]['description'].startswith('Fondo')


def test_il_nome_dato_a_mano_alla_copia_resta(tmp_path):
    s = _lamiera()
    assert s.save(str(tmp_path / 'Base.steelcad'))['ok']
    a = Service()
    assert a.new_assembly_con_pezzi('Prova', [{'path': str(tmp_path / 'Base.steelcad')}])['ok']
    a.asm.instances[0]['name'] = 'Coperchio sinistro'
    assert a.save(str(tmp_path / 'Prova.steelcad-asm'))['ok']
    p = Service()
    assert p.open(str(tmp_path / 'Base.steelcad'))['ok']
    assert p.rinomina_pezzo('Fondo')['ok'] and p.save()['ok']
    b = Service()
    assert b.open(str(tmp_path / 'Prova.steelcad-asm'))['ok']
    assert b.asm.instances[0]['name'] == 'Coperchio sinistro'
