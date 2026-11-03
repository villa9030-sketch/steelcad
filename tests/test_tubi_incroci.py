"""Tubi che si incrociano e tubi che partono a metà di un altro (03/11, il telaio 807 × 725 × 795 in 30×30×2 di
Stefano: «dai montanti non posso nemmeno creare il tubo che si interseca e l'intersezione dei tubi non è
contemplata»)."""
import pytest

from app.service import Service
from cad_engine import templates
from cad_engine.structures import cut_list


def _righe(s):
    return sorted((x['length_mm'], x['qty']) for x in cut_list(s.result.structures)['rows'])


def _telaio():
    s = Service()
    s._set(templates.telaio('Telaio', L=807, P=725, H=795, ripiano=0, profilo='30x30x2', gambe='30x30x2'))
    return s


def _tubo(s, nome):
    st = s.result.structures[0]
    return next(m.id for m in st.members if s.nomi_tubi(st)[m.id].startswith(nome))


def test_croce_sopra_un_tubo_passa_l_altro_in_due_pezzi():
    s = _telaio()
    st = s.result.structures[0]
    davanti, dietro = _tubo(s, 'Traverso davanti'), _tubo(s, 'Traverso dietro')
    sx, dx = _tubo(s, 'Fianco a sinistra'), _tubo(s, 'Fianco a destra')
    assert s.add_traverso('ST1', davanti, dietro, 388.5, 'sotto', '30x30x2')['ok']      # in mezzo, da davanti a dietro
    assert s.add_traverso('ST1', sx, dx, 347.5, 'sotto', '30x30x2')['ok']               # in mezzo, da sinistra a destra
    st = s.result.structures[0]
    assert st.warnings == []                                    # niente tubi uno dentro l'altro
    assert len(st.incroci) == 1
    assert max(m.solid.bounding_box().max.Z for m in st.members) == pytest.approx(795)   # la croce a filo, non sopra
    k, inc = next(iter(st.incroci.items()))
    # passa il più lungo (747), l'altro (665) diventa due pezzi che gli battono contro: pezzo + 30 + pezzo = 665
    def pezzi(lungo):
        st = s.result.structures[0]
        return sorted(m.length for m in st.members if '~' in m.id), next(m.length for m in st.members if m.id == lungo)
    p, intero = pezzi(inc['passa'])
    assert intero == pytest.approx(747) and len(p) == 2 and sum(p) + 30 == pytest.approx(665)
    info = s.angolo_info('ST1', k)
    assert info['ok'] and len(info['scelte']) == 2 and info['ora'] == f'passa:{inc["passa"]}'
    altro = next(x['key'] for x in info['scelte'] if x['key'] != info['ora'])
    assert s.set_angolo('ST1', k, altro)['ok']                  # passa l'altro: 665 intero, 747 in due
    p, intero = pezzi(altro.split(':')[1])
    assert intero == pytest.approx(665) and len(p) == 2 and sum(p) + 30 == pytest.approx(747)
    assert s.result.structures[0].warnings == []


def test_tubo_da_un_punto_del_montante_e_incrocio_sul_fianco():
    s = _telaio()
    gamba = _tubo(s, 'Gamba davanti a sinistra')
    r = s.punto_su_tubo('ST1', gamba, 265)
    assert r['ok'] and r['node']
    st = s.result.structures[0]
    assert st.nodes[r['node'].split(':')[1]]['xyz'][2] == pytest.approx(265)
    # dal punto a 265 un tubo verso dietro lungo tutto il fianco: batte contro le due gambe
    r = s.tubo_da_angolo('ST1', r['node'].split(':')[1], 'dietro', 725, '30x30x2')
    assert r['ok'], r.get('message')
    assert s.result.structures[0].warnings == []
    # il montante in mezzo al fianco, dall'alto a terra: incrocia il tubo a 265
    fianco = _tubo(s, 'Fianco a sinistra')
    r = s.punto_su_tubo('ST1', fianco, 347.5)
    assert r['ok']
    r = s.tubo_da_angolo('ST1', r['node'].split(':')[1], 'giu', 795, '30x30x2')
    assert r['ok'], r.get('message')
    st = s.result.structures[0]
    assert st.warnings == [] and len(st.incroci) == 1
    # un pezzo del tubo tagliato si seleziona e si cambia come il tubo intero
    pezzo = next(m.id for m in st.members if '~' in m.id)
    sel = s.select(f'ST1/{pezzo}')
    assert sel['ok'] and sel['selection']['kind'] == 'member'
    assert s.edit_member(f'ST1/{pezzo}', {'profile': '30x30x3'})['ok']
    st = s.result.structures[0]
    assert {m.profile.name for m in st.members if m.id.split('~')[0] == pezzo.split('~')[0]} == {'30×30×3'}
