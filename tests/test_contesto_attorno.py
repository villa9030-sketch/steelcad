"""Il pezzo aperto dall'assieme con gli altri attorno (05/11): si vedono anche le altre copie dello stesso pezzo, e
nello sketch «Vedi attraverso» porta anche i bordi dei pezzi attorno (per allungare una staffa fino alla piastra)."""
from app.service import Service


def _assieme(tmp_path):
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 400, 'profondita': 300, 'spessore': 8})['ok']
    assert s.save(str(tmp_path / 'Piastra.steelcad'))['ok']
    s = Service()
    assert s.crea_da_modello('staffa', {'larghezza': 100, 'profondita': 80, 'altezza': 80, 'spessore': 3,
                                        'raggio': 3, 'k': 0.33})['ok']
    assert s.save(str(tmp_path / 'Staffa.steelcad'))['ok']
    s = Service()
    assert s.new_assembly_con_pezzi('Prova', [{'path': str(tmp_path / 'Piastra.steelcad')},
                                              {'path': str(tmp_path / 'Staffa.steelcad'), 'n': 2}])['ok']
    assert s.save(str(tmp_path / 'prova.steelcad-asm'))['ok']
    return s


def test_si_vedono_anche_le_altre_copie(tmp_path):
    s = _assieme(tmp_path)
    assert s.asm_open_part('I2')['ok']
    ctx = [o for o in s.scene()['objects'] if o['kind'] == 'context']
    assert len(ctx) == 2                                   # la piastra e l'altra staffa (stesso file)
    assert s.asm_back()['ok'] and s.asm is not None


def test_vedi_attraverso_porta_i_bordi_dei_pezzi_attorno(tmp_path):
    s = _assieme(tmp_path)
    assert s.asm_open_part('I2')['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    larga = lambda: (lambda xs: max(xs) - min(xs))([p['xy'][0] for p in s.sketch_view(sid)['sketch']['points'] if p['id'] != 'O'])  # noqa: E731
    prima = larga()
    r = s.sketch_xray(sid, True)
    assert r['ok'] and 'pezzi attorno' in r['message']
    assert prima < 150 and larga() > 390                   # il bordo della piastra (400) per agganciarsi
    assert s.sketch_xray(sid, False)['ok']
    assert larga() == prima


def test_pezzo_aperto_da_solo_come_prima(tmp_path):
    _assieme(tmp_path)
    s = Service()
    assert s.open(str(tmp_path / 'Staffa.steelcad'))['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    r = s.sketch_xray(sid, True)
    assert r['ok'] and 'pezzi attorno' not in r.get('message', '')
