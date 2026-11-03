"""Piedi e tappi (03/11): sotto tutte le gambe a terra la piastra 80×80 sp. 6 coi 4 fori o il piedino regolabile,
sulle teste aperte dei tubi il tappo in plastica o il lamierino saldato. Un comando ciascuno, in distinta."""
import pytest

from app.service import Service
from cad_engine import templates
from cad_engine.bom import bom
from cad_engine.structures import cut_list


def _telaio():
    s = Service()
    s._set(templates.telaio('Telaio', L=807, P=725, H=795, ripiano=0, profilo='30x30x2', gambe='30x30x2'))
    return s


def test_piastre_sotto_le_gambe_in_un_comando():
    s = _telaio()
    info = s.piedi_info('ST1')
    assert info['ok'] and info['gambe'] == 4 and info['proposta']['lato'] == 80 and info['proposta']['sp'] == 6
    r = s.set_piedi('ST1', {'tipo': 'piastra', 'lato': 80, 'sp': 6, 'fori': 4, 'foro': 9, 'dal_bordo': 15})
    assert r['ok'], r.get('message')
    assert r['message'] == '4 × piastra 80×80 sp. 6 con 4 fori Ø9. Altezza fuori tutto coi piedi: 801.'
    st = s.result.structures[0]
    piastre = [a for a in st.accessori if a.tipo == 'piastra']
    assert len(piastre) == 4
    b = piastre[0].solid.bounding_box()
    assert [round(v, 3) for v in (b.min.Z, b.max.Z, b.size.X, b.size.Y)] == [-6, 0, 80, 80]
    assert piastre[0].kg == pytest.approx((80 * 80 - 4 * 3.14159 * 4.5 ** 2) * 6 * 7.85e-6, rel=1e-3)
    # in distinta: una riga per le 4 piastre, con dove vanno
    acc = cut_list(s.result.structures)['accessori']
    assert len(acc) == 1 and acc[0]['qty'] == 4 and not acc[0]['acquisto']
    assert 'Gamba davanti a sinistra' in acc[0]['dove']
    righe = bom(s.doc, s.result)
    assert any(r['description'] == 'Piastra 80×80 sp. 6 con 4 fori Ø9' and r['qty'] == 4 and r['thickness_mm'] == 6
               for r in righe)
    # nella scena (si clicca) e il clic apre il pannello dei piedi
    ids = [o['id'] for o in s.scene()['objects'] if o['kind'] == 'accessorio']
    assert len(ids) == 4
    sel = s.select(ids[0])['selection']
    assert sel['kind'] == 'accessorio' and sel['cosa'] == 'piedi' and sel['title'].startswith('Piastra sotto gamba')
    # cambiando le misure del modello i piedi restano
    assert s.structure_template_apply('ST1', {'H': 900})['ok']
    assert len(s.result.structures[0].accessori) == 4
    # e si tolgono
    assert s.set_piedi('ST1', None)['ok'] and not s.result.structures[0].accessori


def test_fori_sotto_il_tubo_e_piastra_piccola_dicono_perche():
    s = _telaio()
    r = s.set_piedi('ST1', {'tipo': 'piastra', 'lato': 40, 'sp': 6, 'fori': 4, 'foro': 9, 'dal_bordo': 8})
    assert not r['ok'] and 'fori' in r['message']
    r = s.set_piedi('ST1', {'tipo': 'piastra', 'lato': 20, 'sp': 6, 'fori': 0})
    assert not r['ok'] and 'più piccola del tubo' in r['message']
    assert not s.result.structures[0].accessori                  # il progetto resta com'era


def test_piedino_regolabile_da_comprare():
    s = _telaio()
    r = s.set_piedi('ST1', {'tipo': 'piedino', 'misura': 'M10'})
    assert r['ok'], r.get('message')
    acc = {a['description']: a for a in cut_list(s.result.structures)['accessori']}
    assert acc['Piedino regolabile M10, base Ø40']['acquisto'] and acc['Piedino regolabile M10, base Ø40']['qty'] == 4
    assert acc['Lamierino 30×30 sp. 5 con foro filettato M10']['qty'] == 4
    assert any(x['description'] == 'Piedino regolabile M10, base Ø40 (da acquistare)' and x['type'] == 'acquisto'
               for x in bom(s.doc, s.result))
    assert '801' not in r['message'] and 'Altezza fuori tutto coi piedi: 830' in r['message']


def test_tappi_su_tutte_le_teste_aperte():
    s = _telaio()
    assert s.piedi_info('ST1')['teste'] == 8               # 4 gambe: aperte sopra e sotto
    r = s.set_tappi('ST1', {'tipo': 'plastica'})
    assert r['ok'] and r['message'] == '8 × tappo in plastica per tubo 30×30×2.'
    # coi piedi le teste sotto sono chiuse dalla piastra: restano le 4 sopra
    assert s.set_piedi('ST1', {'tipo': 'piastra'})['ok']
    st = s.result.structures[0]
    tappi = [a for a in st.accessori if a.tipo == 'tappo']
    assert len(tappi) == 4 and all(a.solid.bounding_box().min.Z == pytest.approx(795) for a in tappi)
    acc = {a['description']: a for a in cut_list(s.result.structures)['accessori']}
    assert acc['Tappo in plastica per tubo 30×30×2']['acquisto']
    # lamierino saldato al posto del tappo
    assert s.set_tappi('ST1', {'tipo': 'lamierino', 'sp': 3})['ok']
    acc = {a['description']: a for a in cut_list(s.result.structures)['accessori']}
    lam = acc['Lamierino 30×30 sp. 3 (chiusura testa tubo)']
    assert lam['qty'] == 4 and not lam['acquisto'] and lam['kg_each'] == pytest.approx(30 * 30 * 3 * 7.85e-6, rel=0.02)


def test_scaffale_teste_dei_montanti_e_step():
    """Scaffale: i montanti passano fino in cima (i traversi ci battono contro), le loro teste sono aperte."""
    import tempfile
    from pathlib import Path
    s = Service()
    s._set(templates.scaffale('S', L=1000, P=400, H=1800, ripiani=4))
    assert s.piedi_info('ST1')['gambe'] == 4
    assert s.set_piedi('ST1', {'tipo': 'piastra'})['ok'] and s.set_tappi('ST1', {'tipo': 'plastica'})['ok']
    st = s.result.structures[0]
    tappi = [a for a in st.accessori if a.tipo == 'tappo']
    assert len(tappi) == 4 and st.warnings == []
    # lo STEP del progetto ha anche piastre e tappi
    from cad_engine.exporters.step import export_project
    with tempfile.TemporaryDirectory() as d:
        out = export_project(s.doc, s.result, Path(d) / 'scaffale.step')
    assert out['solids'] == len(st.members) + 8
