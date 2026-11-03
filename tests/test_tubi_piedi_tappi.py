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


def test_distinta_di_taglio_con_le_punte_dei_45_e_file_per_il_laser_tubo(tmp_path):
    """Cancello 60×40: i 45° a trapezio, l'angolo sul lato da 60 per tutti i pezzi del telaio (prima i montanti
    avevano il 60 di profondità e il 45° non combaciava coi traversi); la lista per la troncatrice in CSV."""
    s = Service()
    s._set(templates.cancello('C', L=1500, H=1200, telaio='60x40x3', sbarre='20x20x2', passo=120))
    righe = {r['length_mm']: r for r in cut_list(s.result.structures)['rows']}
    for lung in (1500, 1200):
        assert righe[lung]['forma'] == 'trapezio' and righe[lung]['lato_taglio'] == 60
        assert righe[lung]['tagli_testo'] == '45° / 45° a trapezio, angolo sul lato da 60'
    assert righe[1080]['tagli_testo'] == 'dritto / dritto'
    st = s.result.structures[0]
    assert st.warnings == []
    mont = next(m for m in st.members if s.nomi_tubi(st)[m.id] == 'Montante a sinistra')
    b = mont.solid.bounding_box()
    assert round(b.size.X) == 60 and round(b.size.Y) == 40            # il 60 nel piano del cancello, come i traversi
    # il file per la troncatrice / laser tubo, in Prepara per l'officina
    voci = {v['id']: v for v in s.prepara_info()['voci']}
    assert voci['tubi']['si'] and voci['tubi']['file'].endswith('_taglio_tubi.csv')
    r = s.export_taglio_tubi(str(tmp_path / 't.csv'))
    assert r['ok'], r.get('message')
    testo = (tmp_path / 't.csv').read_text(encoding='utf-8-sig').splitlines()
    assert testo[0].startswith('Pos.;Profilo;Materiale;Lunghezza mm;Taglio 1;Taglio 2;Come vengono le punte')
    riga = next(x for x in testo if ';1500,0;' in x)
    assert '45°;45°;a trapezio (punte dallo stesso lato);60,0;2;' in riga
    assert any(x.startswith(';60×40×3;S235;4;') for x in testo)          # barre da comprare
    # un parallelogramma: la diagonale tra due montanti (batte contro tutti e due): punte da lati opposti
    from cad_engine.document import Document
    doc = Document('Diag', 'S235')
    doc.add_feature('structure', 'D', points={'A': [0, 0, 0], 'B': [0, 0, 1000], 'C': [1000, 0, 0], 'D': [1000, 0, 1000],
                                              'E': [0, 0, 100], 'F': [1000, 0, 900]},
                    members=[{'id': 'M1', 'from': 'A', 'to': 'B', 'profile': '40x40x3'},
                             {'id': 'M2', 'from': 'C', 'to': 'D', 'profile': '40x40x3'},
                             {'id': 'M3', 'from': 'E', 'to': 'F', 'profile': '40x40x3'}])
    s2 = Service()
    s2._set(doc)
    m3 = next(r for r in cut_list(s2.result.structures)['rows'] if r['members'] == ['ST1/M3'])
    assert m3['forma'] == 'parallelo' and 'a parallelogramma' in m3['tagli_testo']
