"""03/11 (secondo giro) — «Incastri» nella barra: le pieghe la cui punta appoggia su un'altra parete, coi nomi
dell'albero; linguette e asole con anteprima. Prima si trovavano solo aprendo la piega giusta."""
import build123d as bd
import pytest

from app.service import Service


@pytest.fixture
def u_chiusa():
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.5})
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    assert s.add_flange('SM1', None, {'length': '30'}, 'FL1')['ok']
    assert s.add_flange('SM1', None, {'length': '38'}, 'FL2')['ok']
    return s


def test_trova_la_piega_che_appoggia(u_chiusa):
    r = u_chiusa.incastri_possibili()
    assert r['ok'] and [p['flange'] for p in r['pieghe']] == ['FL3']
    p = r['pieghe'][0]
    assert p['nome'].startswith('Piega') and 'faccia di sopra' in p['contro'] and p['lunga'] == 200 and not p['fatti']


def test_anteprima_e_incastri_fatti(u_chiusa):
    s = u_chiusa
    v0 = bd.Solid(s.result.body.shape).volume
    a = s.anteprima('auto_tabs', ['SM1', 'FL3', 3, 15, '0,2', 0])
    assert a['ok'], a
    assert bd.Solid(s.result.body.shape).volume == v0                  # l'anteprima non tocca il pezzo
    assert s.auto_tabs('SM1', 'FL3', 3, 15, '0,2', 0)['ok']
    assert s.incastri_possibili()['pieghe'][0]['fatti']
    # troppe linguette: l'anteprima è rossa e dice perché
    a = s.anteprima('auto_tabs', ['SM1', 'FL3', 20, 15, '0,2', 0])
    assert not a['ok'] and 'non stanno' in a['message']


def test_lamiera_senza_appoggi_lista_vuota():
    s = Service()
    s.new_project('lamiera', {'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.5})
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    assert s.incastri_possibili() == {'ok': True, 'pieghe': []}
