"""Impostazioni con un solo «Applica», salvate in un file (il tema chiaro restava solo fino alla chiusura), e il materiale
del pezzo scelto da te: peso e distinta lo seguono; i pezzi nuovi nascono col materiale predefinito (23/10)."""
from app.service import Service


def test_impostazioni_restano(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path))
    s = Service()
    r = s.set_impostazioni({'tema': 'chiaro', 'materiale': 'AISI304', 'radius': '2', 'k': '0,4', 'azienda': 'Officina'})
    assert r['ok'], r
    i = Service().impostazioni()                         # un altro avvio
    assert i['tema'] == 'chiaro' and i['materiale'] == 'AISI304' and i['cartiglio']['azienda'] == 'Officina'
    assert i['bend_default']['radius'] == 2
    assert not s.set_impostazioni({'tema': 'rosa'})['ok']
    assert not s.set_impostazioni({'materiale': 'oro'})['ok']


def test_materiale_del_pezzo(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path))
    s = Service()
    assert s.new_project('lamiera', {'name': 'L', 'larghezza': 500, 'profondita': 300, 'spessore': 2})['ok']
    assert s.state()['materiale'] == 'S235'
    kg_ferro = s.state()['bom_kg']
    r = s.set_material('AL5754')
    assert r['ok'] and s.state()['materiale'] == 'AL5754'
    assert abs(s.state()['bom_kg'] / kg_ferro - 2.67 / 7.85) < 0.01   # l'alluminio pesa un terzo
    assert s.undo()['ok'] and s.state()['materiale'] == 'S235'
    assert not s.set_material('legno')['ok']


def test_pezzi_nuovi_col_predefinito(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path))
    s = Service()
    assert s.set_impostazioni({'materiale': 'AISI316L'})['ok']
    assert s.new_project('lamiera', {'name': 'L', 'larghezza': 100, 'profondita': 100, 'spessore': 2})['ok']
    assert s.state()['materiale'] == 'AISI316L'
    assert s.new_project('telaio', {'name': 'T'})['ok']
    st = next(f for f in s.doc.features if not hasattr(f, 'entities') and f.get('type') == 'structure')
    assert st['material'] == 'AISI316L'
