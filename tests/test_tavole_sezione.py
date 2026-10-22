"""Tavole: le quote messe col tasto Quota finiscono nella vista giusta, e il foglio della sezione A-A (22/10)."""
from app.service import Service


def _staffa():
    s = Service()
    assert s.new_project('lamiera', {'name': 'Staffa', 'larghezza': 120, 'profondita': 80, 'spessore': 3,
                                     'raggio': 1, 'k': 0.4})['ok']
    assert s.add_flange('SM1', 'L2', {'length': '40'})['ok']
    return s


def test_quote_a_mano_nella_tavola_e_nel_file(tmp_path):
    s = _staffa()
    assert s.set_quote([{'a': [0, 0, 3], 'b': [60, 0, 3], 'testo': '60'}])['ok']
    assert s.state()['quote'][0]['testo'] == '60'
    p = s.drawing_preview({})
    assert p['ok'] and '>60<' in p['sheets'][0]['svg']
    assert s.save(str(tmp_path / 'a.steelcad'))['ok']
    t = Service()
    assert t.open(str(tmp_path / 'a.steelcad'))['ok'] and t.state()['quote'][0]['testo'] == '60'


def test_foglio_sezione():
    s = _staffa()
    assert [x['title'] for x in s.drawing_preview({})['sheets']] == ['Staffa', 'Staffa — sviluppo']
    for asse in ('X', 'Y'):
        p = s.drawing_preview({'sezione': asse})
        titoli = [x['title'] for x in p['sheets']]
        assert titoli == ['Staffa', 'Staffa — sezione A-A', 'Staffa — sviluppo']
        assert 'SEZIONE A-A' in p['sheets'][1]['svg']
