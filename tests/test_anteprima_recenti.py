"""Pagina iniziale (04/11): i lavori recenti senza anteprima (salvati senza passare dall'interfaccia, o da una versione
vecchia) si fanno dare i triangoli per scattarla; il lavoro aperto non cambia."""
from app.service import Service


def test_anteprima_di_pezzo_e_assieme(tmp_path):
    s = Service()
    assert s.new_project('piastra', {'name': 'Base', 'larghezza': 300, 'altezza': 200, 'spessore': 8, 'foro': 14})['ok']
    assert s.save(str(tmp_path / 'Base.steelcad'))['ok']
    assert s.new_assembly('Supporto')['ok']
    assert s.asm_insert(str(tmp_path / 'Base.steelcad'))['ok']
    assert s.asm_insert(str(tmp_path / 'Base.steelcad'))['ok']
    assert s.save(str(tmp_path / 'Supporto.steelcad-asm'))['ok']
    assert s.new_project('lamiera', {'name': 'Aperto', 'larghezza': 500, 'profondita': 300, 'spessore': 2})['ok']
    r = s.anteprima_maglia(str(tmp_path / 'Base.steelcad'))
    assert r['ok'] and len(r['objects']) == 1 and r['objects'][0]['indices'] and 'matrix' not in r['objects'][0]
    r = s.anteprima_maglia(str(tmp_path / 'Supporto.steelcad-asm'))
    assert r['ok'] and len(r['objects']) == 2 and len(r['objects'][1]['matrix']) == 16
    assert s.state()['name'] == 'Aperto'                       # il lavoro aperto è sempre quello
    assert not s.anteprima_maglia(str(tmp_path / 'non_c_e.steelcad'))['ok']
