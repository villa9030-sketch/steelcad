"""Aggiornamento automatico: confronto delle versioni, release di GitHub lette bene, indirizzi accettati."""
import json

from app import aggiorna


class _Risposta:
    def __init__(self, dati):
        self._b = json.dumps(dati).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _release(tag, asset='Radius-Setup-{v}.exe'):
    v = tag.lstrip('v')
    nome = asset.format(v=v)
    return {'tag_name': tag, 'body': 'novità', 'assets': [
        {'name': 'altro.zip', 'browser_download_url': 'x', 'size': 1},
        {'name': nome, 'size': 230_000_000,
         'browser_download_url': f'https://github.com/{aggiorna.REPO}/releases/download/{tag}/{nome}'}]}


def test_dallo_sviluppo_non_controlla(monkeypatch):
    monkeypatch.delenv('RADIUS_PROVA_AGGIORNA', raising=False)
    monkeypatch.setattr(aggiorna, 'installato', lambda: False)
    assert aggiorna.controlla('0.9.0') == {'ok': True, 'nuova': None, 'motivo': 'sviluppo'}


def test_versione_nuova_e_vecchia(monkeypatch):
    monkeypatch.setattr(aggiorna, 'installato', lambda: True)
    monkeypatch.setattr(aggiorna.urllib.request, 'urlopen', lambda req, timeout=0: _Risposta(_release('v0.10.1')))
    r = aggiorna.controlla('0.9.0')
    assert r['nuova'] == '0.10.1' and r['mb'] == 230 and r['url'].endswith('Radius-Setup-0.10.1.exe')
    assert aggiorna.controlla('0.10.1')['nuova'] is None          # la stessa: niente
    assert aggiorna.controlla('1.0.0')['nuova'] is None           # più vecchia: niente


def test_senza_setup_allegato_non_propone(monkeypatch):
    monkeypatch.setattr(aggiorna, 'installato', lambda: True)
    monkeypatch.setattr(aggiorna.urllib.request, 'urlopen', lambda req, timeout=0: _Risposta(_release('v2.0.0', 'sorgenti-{v}.zip')))
    assert aggiorna.controlla('0.9.0')['nuova'] is None


def test_senza_rete(monkeypatch):
    monkeypatch.setattr(aggiorna, 'installato', lambda: True)

    def giu(req, timeout=0):
        raise OSError('rete assente')
    monkeypatch.setattr(aggiorna.urllib.request, 'urlopen', giu)
    r = aggiorna.controlla('0.9.0')
    assert not r['ok'] and 'non riuscito' in r['message']


def test_installa_solo_dalle_release_del_progetto():
    assert not aggiorna.installa('https://esempio.it/Radius-Setup-1.0.0.exe')['ok']
    assert not aggiorna.installa(f'https://github.com/altro/repo/releases/download/v1/Radius-Setup-1.0.0.exe')['ok']
