"""Interfaccia nuova (04/11): al primo avvio si parte col tema chiaro anche se prima era stato salvato lo scuro;
poi vale la scelta fatta col pulsante Tema o nelle Impostazioni."""
import json

from app.service import Service


def test_primo_avvio_chiaro_poi_la_scelta(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path))
    f = tmp_path / 'impostazioni.json'
    f.write_text(json.dumps({'tema': 'scuro', 'materiale': 'AISI304'}), encoding='utf-8')   # salvate con la versione vecchia
    i = Service().impostazioni()
    assert i['tema'] == 'chiaro' and i['materiale'] == 'AISI304'          # chiaro una volta; il resto non si tocca
    salvate = json.loads(f.read_text(encoding='utf-8'))
    assert salvate['tema_nuovo_visto'] is True and salvate['tema'] == 'chiaro'
    s = Service()
    assert s.set_impostazioni({'tema': 'scuro'})['ok']                    # pulsante Tema: torna scuro
    assert Service().impostazioni()['tema'] == 'scuro'                     # e al riavvio resta scuro
    assert Service().impostazioni()['tema'] == 'scuro'


def test_scelta_prima_del_primo_avvio(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path))
    assert Service().set_impostazioni({'tema': 'scuro'})['ok']           # scelto scuro con la versione nuova
    assert Service().impostazioni()['tema'] == 'scuro'


def test_senza_impostazioni(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path))
    assert Service().impostazioni()['tema'] == 'chiaro'
