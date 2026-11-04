"""Plexiglass (04/11, Stefano: «l'ufficio: azzurro molto chiaro, che simuli il vetro»): materiale PMMA 1,19 g/cm³,
nel 3D trasparente anche se ha una finitura; niente avvisi della piegatrice pensati per il metallo."""
import json
import shutil
from pathlib import Path

from app.service import Service
from cad_engine import finiture, materials

DATI = Path(__file__).parent / 'data' / 'vano'


def test_plexiglass_nell_elenco_con_il_suo_peso():
    m = materials.get('PMMA')
    assert m.density_g_cm3 == 1.19
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 1000, 'profondita': 500, 'spessore': 5})['ok']
    assert any(x['code'] == 'PMMA' and x['nome'] == 'Plexiglass' for x in s.state()['materiali'])
    assert s.set_material('PMMA')['ok']
    # 1000 × 500 × 5 = 2,5 dm³ → 2,975 kg
    import build123d as bd
    assert abs(materials.get('PMMA').mass_kg(bd.Solid(s.result.body.shape).volume) - 2.975) < 0.01


def test_nel_3D_e_vetro_anche_con_una_finitura():
    v = finiture.aspetto('PMMA', {'tipo': 'verniciato', 'ral': '3020'})
    assert v['opacity'] < 0.5 and v['color'] == '#DCEFF8'
    assert 'opacity' not in (finiture.aspetto('S235', {'tipo': 'zincato'}) or {})
    assert finiture.aspetto('S235', None) is None


def test_la_scena_del_pezzo_e_dell_assieme_porta_il_vetro(tmp_path):
    for f in ('anta', 'pannello'):
        shutil.copy(DATI / f'{f}.steelcad', tmp_path / f'{f}.steelcad')
    f = tmp_path / 'pannello.steelcad'
    j = json.loads(f.read_text(encoding='utf-8'))
    j['material'] = 'PMMA'
    f.write_text(json.dumps(j), encoding='utf-8')
    s = Service()
    assert s.open(str(f))['ok']
    body = next(o for o in s.scene()['objects'] if o['kind'] == 'body')
    assert body['look']['opacity'] == finiture.VETRO['opacity']
    assert not [w for w in s.state().get('warnings', []) if 'Fattibilità' in str(w)]
    s = Service()
    assert s.new_assembly_con_pezzi('Ufficio', [{'path': str(tmp_path / 'anta.steelcad')}, {'path': str(f)}])['ok']
    looks = {o['id']: o.get('look') for o in s.scene()['objects']}
    assert looks['I2']['opacity'] == finiture.VETRO['opacity'] and not (looks['I1'] or {}).get('opacity')
