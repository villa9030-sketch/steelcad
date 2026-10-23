r"""Lavori e pezzi spostati a mano in un'altra cartella (bug di Stefano, 22/10): l'assieme li ritrova da solo (accanto
a sé e in Documenti\SteelCAD), quelli che non trova li elenca con «Cerca…»; i recenti non spariscono."""
import shutil
from pathlib import Path

import pytest

from app.service import Service


@pytest.fixture
def casa(tmp_path, monkeypatch):
    monkeypatch.setenv('USERPROFILE', str(tmp_path / 'utente'))
    monkeypatch.setenv('HOME', str(tmp_path / 'utente'))
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path / 'impostazioni'))
    (tmp_path / 'utente' / 'Documents' / 'SteelCAD').mkdir(parents=True)
    return tmp_path


def _pezzo(path, nome, w):
    s = Service()
    assert s.new_project('lamiera', {'name': nome, 'larghezza': w, 'profondita': 100, 'spessore': 2})['ok']
    assert s.save(str(path))['ok']


def _assieme(casa):
    pezzi = casa / 'utente' / 'Desktop' / 'pezzi'
    pezzi.mkdir(parents=True)
    _pezzo(pezzi / 'Parete A.steelcad', 'Parete A', 300)
    _pezzo(pezzi / 'Fondo.steelcad', 'Fondo', 400)
    asm = casa / 'utente' / 'Desktop' / 'Scatola.steelcad-asm'
    s = Service()
    assert s.new_assembly_con_pezzi('Scatola', [{'path': str(pezzi / 'Fondo.steelcad'), 'n': 1},
                                                {'path': str(pezzi / 'Parete A.steelcad'), 'n': 2}])['ok']
    assert s.save(str(asm))['ok']
    return pezzi, asm


def test_ritrovati_da_soli_in_documenti(casa):
    pezzi, asm = _assieme(casa)
    nuova = casa / 'utente' / 'Documents' / 'SteelCAD' / 'Scatola'
    shutil.move(str(pezzi), str(nuova))                    # spostati a mano, l'assieme no
    s = Service()
    r = s.open(str(asm))
    assert r['ok'], r.get('message')
    st = s.state()
    assert not st['mancanti'] and len(st['instances']) == 3 and not st['errors']
    assert {x['name'] for x in st['ritrovati']} == {'Fondo', 'Parete A'} and st['dirty']
    assert all(Path(i['file']).parent == nuova.resolve() for i in st['instances'])


def test_non_trovati_poi_cerca(casa):
    pezzi, asm = _assieme(casa)
    altrove = casa / 'archivio' / 'vecchi lavori'
    altrove.parent.mkdir()
    shutil.move(str(pezzi), str(altrove))                  # fuori da dove si cerca da soli
    s = Service()
    assert s.open(str(asm))['ok']
    st = s.state()
    assert {x['name'] for x in st['mancanti']} == {'Fondo', 'Parete A'}
    assert next(x for x in st['mancanti'] if x['name'] == 'Parete A')['n'] == 2
    vecchio = next(x['file'] for x in st['mancanti'] if x['name'] == 'Fondo')
    r = s.asm_ritrova_in(vecchio, str(altrove / 'Fondo.steelcad'))
    assert r['ok'] and not s.state()['mancanti']           # la Parete A ritrovata nella stessa cartella
    assert 'Ritrovati 2 pezzi' in r['message']


def test_recenti_spostati_restano(casa):
    _pezzo(casa / 'Staffa.steelcad', 'Staffa', 200)
    s = Service()
    assert s.open(str(casa / 'Staffa.steelcad'))['ok']
    (casa / 'nuova').mkdir()
    shutil.move(str(casa / 'Staffa.steelcad'), str(casa / 'nuova' / 'Staffa.steelcad'))
    rec = s.home_info()['recent']
    x = next(r for r in rec if r['name'] == 'Staffa')
    assert x.get('manca')
    rec = s.recent_ritrovato(x['path'], str(casa / 'nuova' / 'Staffa.steelcad'))['recent']
    y = next(r for r in rec if r['name'] == 'Staffa')
    assert not y.get('manca') and Path(y['path']).parent.name == 'nuova'
