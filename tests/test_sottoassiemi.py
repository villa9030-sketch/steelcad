"""Sottoassiemi (05/11, Stefano: «in un assieme posso mettere un altro assieme?»). Il ferma plexi col plexiglass
nella scanalatura è un assieme; nell'anta dell'ufficio entra come un blocco solo (Metti nel vano), si muove insieme,
la distinta conta i pezzi dentro (o li tiene sotto il blocco), le tavole e lo STEP li disegnano, si apre e si torna.
Un assieme non entra mai dentro se stesso."""
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from app.service import Service
from cad_engine import assembly as A

DATI = Path(__file__).parent / 'data' / 'vano'


def _clic(s, iid):
    o = next(o for o in s.scene()['objects'] if o['id'] == iid)
    return {'inst': iid, 'face': o['faces'][0]['index']}


def _ingombro(s, iid):
    i = s.asm.instance(iid)
    b = A.placed_shape(s.asm_parts[i['file']], i['R'], i['T']).bounding_box()
    return [round(v, 2) for v in (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)]


@pytest.fixture()
def ufficio(tmp_path):
    for f in ('anta', 'ferma_plexi', 'plexi'):
        shutil.copy(DATI / f'{f}.steelcad', tmp_path / f'{f}.steelcad')
    s = Service()
    assert s.new_assembly_con_pezzi('Ferma con plexi', [{'path': str(tmp_path / 'ferma_plexi.steelcad')},
                                                        {'path': str(tmp_path / 'plexi.steelcad')}])['ok']
    assert s.asm_vano(_clic(s, 'I2'), _clic(s, 'I1'))['ok']
    sotto = tmp_path / 'ferma con plexi.steelcad-asm'
    assert s.save(str(sotto))['ok']
    s = Service()
    assert s.new_assembly_con_pezzi('Anta', [{'path': str(tmp_path / 'anta.steelcad')}])['ok']
    r = s.asm_insert(str(sotto))
    assert r['ok'], r.get('message')
    return s, tmp_path, sotto


def test_entra_come_un_blocco_con_i_suoi_pezzi_nell_albero(ufficio):
    s, _, _ = ufficio
    nodo = next(n for n in s.state()['tree']['children'] if n.get('ref') == 'I2')
    assert nodo['label'] == 'Ferma con plexi' and nodo.get('sotto')
    assert [c['label'] for c in nodo['children']] == ['FERMA PLEXI B', 'PLEXIGLASS']
    # 918 × 918 × 38, i due pezzi insieme
    x0, y0, z0, x1, y1, z1 = _ingombro(s, 'I2')
    assert (round(x1 - x0, 1), round(y1 - y0, 1), round(z1 - z0, 1)) == (918, 918, 38)


def test_distinta_per_pezzi_e_per_sottoassiemi(ufficio):
    s, _, _ = ufficio
    st = s.state()
    nomi = {r['description'].split(',')[0]: r['qty'] for r in st['bom']}
    assert nomi == {'ANTA UFFICIO': 1, 'FERMA PLEXI B': 1, 'PLEXIGLASS': 1}
    g = st['bom_gruppi']
    assert [(r['code'], r['description'], r['sottoassieme']) for r in g] == [('P1', 'ANTA UFFICIO', False),
                                                                           ('S2', 'Ferma con plexi', True)]
    assert [f['description'] for f in g[1]['figli']] == ['FERMA PLEXI B', 'PLEXIGLASS']
    # il peso del blocco è la somma dei suoi pezzi
    assert abs(g[1]['kg_each'] - sum(f['kg_each'] for f in g[1]['figli'])) < 1e-6


def test_due_copie_contano_due_volte_i_pezzi(ufficio):
    s, _, sotto = ufficio
    assert s.asm_insert(str(sotto))['ok']
    q = {r['description'].split(',')[0]: r['qty'] for r in s.state()['bom']}
    assert q['PLEXIGLASS'] == 2 and q['FERMA PLEXI B'] == 2
    assert s.state()['bom_gruppi'][1]['qty'] == 2


def test_il_blocco_si_accoppia_come_un_pezzo(ufficio):
    s, _, _ = ufficio
    r = s.asm_vano(_clic(s, 'I2'), _clic(s, 'I1'))           # il ferma plexi (918) nel vano dell'anta (920 × 1060)
    assert r['ok'], r.get('message')
    x0, _, z0, x1, _, z1 = _ingombro(s, 'I2')
    assert (round(x0, 2), round(x1, 2)) == (41, 959)
    # le facce del blocco hanno il nome del pezzo dentro: l'accoppiamento le ritrova
    assert all(':' in (m['a'].get('name') or 'I1:') or m['a']['inst'] == 'I1' for m in s.asm.mates)
    assert all(m['b'].get('name', '').startswith(('I1:', 'I2:')) for m in s.asm.mates if m['b'].get('name'))
    assert not s.asm.warnings


def test_la_scena_tiene_il_vetro_del_plexiglass(ufficio):
    s, _, _ = ufficio
    o = next(o for o in s.scene()['objects'] if o['id'] == 'I2')
    looks = [g['look'] for g in o['gruppi']]
    assert len(looks) == 2 and looks[0] is None and looks[1]['opacity'] < 0.5
    assert o['faces'][0]['label'].startswith('Ferma con plexi: FERMA PLEXI B, ')


def test_se_cambia_un_pezzo_dentro_il_blocco_si_aggiorna(ufficio):
    s, d, _ = ufficio
    assert s.save(str(d / 'anta.steelcad-asm'))['ok']
    kg = next(r for r in s.state()['bom'] if r['description'].startswith('PLEXIGLASS'))['kg_each']
    f = d / 'plexi.steelcad'
    j = json.loads(f.read_text(encoding='utf-8'))
    j['parameters']['sp'] = 8
    f.write_text(json.dumps(j), encoding='utf-8')
    s2 = Service()
    assert s2.open(str(d / 'anta.steelcad-asm'))['ok']
    kg2 = next(r for r in s2.state()['bom'] if r['description'].startswith('PLEXIGLASS'))['kg_each']
    assert abs(kg2 - kg / 2) < 0.01


def test_mai_dentro_se_stesso(ufficio):
    s, d, sotto = ufficio
    assert s.save(str(d / 'anta.steelcad-asm'))['ok']
    r = s.asm_insert(str(d / 'anta.steelcad-asm'))
    assert not r['ok'] and 'dentro se stesso' in r['message']
    s2 = Service()
    assert s2.open(str(sotto))['ok']
    r = s2.asm_insert(str(d / 'anta.steelcad-asm'))          # l'anta contiene già il ferma: giro chiuso
    assert not r['ok'] and 'dentro se stesso' in r['message']


def test_finitura_e_scassi_si_fanno_sui_pezzi_dentro(ufficio):
    s, _, sotto = ufficio
    prima = sotto.read_text(encoding='utf-8')
    r = s.asm_set_finitura('I2', {'tipo': 'zincato'})
    assert not r['ok'] and 'sottoassieme' in r['message']
    assert sotto.read_text(encoding='utf-8') == prima           # il file del sottoassieme non si tocca


def test_apri_il_sottoassieme_e_torna(ufficio):
    s, d, sotto = ufficio
    assert s.save(str(d / 'anta.steelcad-asm'))['ok']
    r = s.asm_open_part('I2')
    assert r['ok'] and s.state()['mode'] == 'assembly' and s.asm.name == 'Ferma con plexi'
    assert s.state()['can_back']
    assert s.asm_rinomina('I2', 'Plexi ufficio')['ok']        # una modifica dentro: si salva tornando
    r = s.asm_back()
    assert r['ok'], r.get('message')
    assert s.asm.name == 'Anta' and 'Salvato' in r.get('message', '')
    nodo = next(n for n in s.state()['tree']['children'] if n.get('ref') == 'I2')
    assert nodo['children'][1]['label'].startswith('Plexi ufficio')


def test_step_e_tavole_coi_pezzi_dentro(ufficio):
    s, d, _ = ufficio
    r = s.asm_export_step(str(d / 'anta.step'))
    assert r['ok'] and '3 pezzi' in r['message']
    fogli = s._fogli_nuovi({}, tutte=True)
    assert len(fogli) >= 3
