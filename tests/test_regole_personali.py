"""Spessori preferiti salvati una volta sola (05/11, idea dalle «personal Sheet Metal Rules» di SolidCraft).

Una regola personale = materiale + spessore + raggio + K (o deduzione). Sta nel file delle regole dell'utente, si
offre nei pezzi nuovi e nel cambio spessore; il pezzo tiene la sua copia dei valori: rinominare o cancellare la
regola non cambia i pezzi già fatti."""
import json

from app.service import Service


def _regola(s, nome, **valori):
    """Una regola salvata come la salva l'utente: da una lamiera con quei dati."""
    v = {'name': 'L', 'larghezza': 400, 'profondita': 300, 'spessore': 2, 'raggio': 2, 'k': 0.4} | valori
    assert s.new_project('lamiera', v)['ok']
    assert s.save_sheet_rule('SM1', nome)['ok']


def test_la_regola_si_vede_in_parole(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))
    s = Service()
    assert s.new_project('lamiera', {'name': 'L', 'larghezza': 400, 'profondita': 300, 'spessore': 2, 'raggio': 2, 'k': 0.4})['ok']
    assert s.set_material('AISI304')['ok']
    assert s.save_sheet_rule('SM1', 'Inox 2')['ok']
    st = s.state()
    assert [r['name'] for r in st['regole']] == ['Inox 2']
    assert st['regole'][0]['descrizione'] == 'Inox 304 sp. 2 · R 2 · K 0,4'
    assert st['sheet']['regola'] == 'Inox 2'                 # la lamiera ha proprio quei dati


def test_lamiera_nuova_prende_tutto_dalla_regola(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))
    s = Service()
    _regola(s, 'Inox 3', spessore=3, raggio=3, k=0.42, material='AISI316L')
    assert s.new_project('lamiera', {'name': 'N', 'larghezza': 500, 'profondita': 300, 'spessore': 2, 'regola': 'Inox 3'})['ok']
    st = s.state()
    d = st['sheet']['def']
    assert st['materiale'] == 'AISI316L' and d['radius'] == 3 and d['k'] == 0.42
    assert next(p for p in st['parameters'] if p['name'] == 'sp')['value'] == 3
    assert st['sheet']['regola'] == 'Inox 3'
    assert not s.new_project('lamiera', {'name': 'N', 'larghezza': 500, 'profondita': 300, 'regola': 'Non c’è'})['ok']


def test_modello_pronto_con_la_regola(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))
    s = Service()
    _regola(s, 'Allu 1,5', spessore=1.5, raggio=1.5, k=0.35, material='AL5754')
    r = s.crea_da_modello('staffa', {'larghezza': 300, 'profondita': 200, 'altezza': 120, 'spessore': 1.5, 'regola': 'Allu 1,5'})
    assert r['ok'], r
    st = s.state()
    assert st['materiale'] == 'AL5754' and st['sheet']['def']['radius'] == 1.5 and st['sheet']['def']['k'] == 0.35
    assert st['sheet']['regola'] == 'Allu 1,5' and st['sheet']['flanges'] == 1


def test_cambio_spessore_con_la_regola_e_annulla(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))
    s = Service()
    _regola(s, 'Ferro 3', spessore=3, raggio=4, k=0.45)
    assert s.new_project('lamiera', {'name': 'L', 'larghezza': 400, 'profondita': 300, 'spessore': 2, 'raggio': 2, 'k': 0.4})['ok']
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    assert s.state()['sheet']['regola'] is None
    assert s.apply_sheet_rule('SM1', 'Ferro 3')['ok']          # un passo solo: spessore, raggio e K insieme
    st = s.state()
    assert st['sheet']['regola'] == 'Ferro 3' and st['sheet']['def']['radius'] == 4
    assert next(p for p in st['parameters'] if p['name'] == 'sp')['value'] == 3
    assert s.undo()['ok']
    assert s.state()['sheet']['def']['radius'] == 2


def test_rinomina_e_cancella_non_cambiano_i_pezzi(tmp_path, monkeypatch):
    regole = tmp_path / 'regole.json'
    monkeypatch.setenv('STEELCAD_RULES', str(regole))
    s = Service()
    _regola(s, 'Inox 2', material='AISI304')
    _regola(s, 'Ferro 2')
    assert s.new_project('lamiera', {'name': 'P', 'larghezza': 400, 'profondita': 300, 'regola': 'Inox 2'})['ok']

    assert not s.rename_sheet_rule('Inox 2', 'Ferro 2')['ok']   # due regole con lo stesso nome no
    assert not s.rename_sheet_rule('Inox 2', '  ')['ok']
    assert not s.rename_sheet_rule('Non c’è', 'X')['ok']
    r = s.rename_sheet_rule('Inox 2', 'Inox 304 sp. 2')
    assert r['ok'] and 'Inox 304 sp. 2' in [x['name'] for x in r['rules']]
    assert s.state()['sheet']['regola'] == 'Inox 304 sp. 2'     # il pezzo non è cambiato: coincide con la regola rinominata
    assert s.delete_sheet_rule('Inox 304 sp. 2')['ok']
    st = s.state()
    assert st['sheet']['regola'] is None and st['materiale'] == 'AISI304' and st['sheet']['def']['k'] == 0.4
    assert [x['name'] for x in json.loads(regole.read_text(encoding='utf-8'))['rules']] == ['Ferro 2']


def test_pezzo_si_apre_uguale_senza_le_regole(tmp_path, monkeypatch):
    """Il pezzo ha i valori dentro: su un altro PC, senza il file delle regole, si apre uguale."""
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))
    s = Service()
    _regola(s, 'Inox 3', spessore=3, raggio=3, k=0.42, material='AISI304')
    assert s.new_project('lamiera', {'name': 'P', 'larghezza': 400, 'profondita': 300, 'regola': 'Inox 3'})['ok']
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    pezzo = tmp_path / 'pezzo.steelcad'
    assert s.save(str(pezzo))['ok']
    sviluppo = s.state()['sheet']['data']['flat_size']

    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'altro_pc.json'))
    t = Service()
    assert t.open(str(pezzo))['ok']
    st = t.state()
    assert st['materiale'] == 'AISI304' and st['sheet']['def']['radius'] == 3 and st['sheet']['def']['k'] == 0.42
    assert st['sheet']['data']['flat_size'] == sviluppo and st['regole'] == [] and st['sheet']['regola'] is None
