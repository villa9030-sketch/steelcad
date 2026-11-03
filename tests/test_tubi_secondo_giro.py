"""Strutture in tubo, secondo giro (03/11 pomeriggio): il traverso «In mezzo» resta in mezzo cambiando le misure,
«Dividi» propone il lato cliccato, i disegnini dell'incrocio dicono chi passa, negli scaffali passano i montanti."""
import pytest

from app.service import Service
from cad_engine import templates


def _telaio():
    s = Service()
    s._set(templates.telaio('Telaio', L=807, P=725, H=795, ripiano=0, profilo='30x30x2', gambe='30x30x2'))
    return s


def _tubo(s, nome):
    st = s.result.structures[0]
    return next(m.id for m in st.members if s.nomi_tubi(st)[m.id].startswith(nome))


def _centro(s, mid):
    b = next(m for m in s.result.structures[0].members if m.id == mid).solid.bounding_box()
    return [round((a + c) / 2, 1) for a, c in ((b.min.X, b.max.X), (b.min.Y, b.max.Y), (b.min.Z, b.max.Z))]


def test_traverso_in_mezzo_resta_in_mezzo_cambiando_le_misure():
    s = _telaio()
    r = s.add_traverso('ST1', _tubo(s, 'Traverso davanti'), _tubo(s, 'Traverso dietro'), 'mezzo', 'centro', '30x30x2')
    assert r['ok'], r.get('message')
    croce = r['select'].split('/')[1]
    g1, g2 = _tubo(s, 'Gamba davanti a sinistra'), _tubo(s, 'Gamba davanti a destra')
    r = s.add_traverso('ST1', g1, g2, 'mezzo', 'sotto', '30x30x2')
    assert r['ok'], r.get('message')
    meta = r['select'].split('/')[1]
    assert _centro(s, croce)[0] == 403.5 and _centro(s, meta)[2] == 397.5
    # il modello più largo e più alto: il traverso sopra torna in mezzo alla larghezza, quello delle gambe a metà altezza
    r = s.structure_template_apply('ST1', {'L': 1007, 'H': 995})
    assert r['ok'], r.get('message')
    st = s.result.structures[0]
    assert st.warnings == []
    assert _centro(s, croce)[0] == 503.5
    assert _centro(s, meta)[2] == 497.5
    # una misura scritta a mano invece resta quella
    assert s.add_traverso('ST1', _tubo(s, 'Gamba dietro a sinistra'), _tubo(s, 'Gamba dietro a destra'), 200, 'sotto',
                          '30x30x2')['ok']
    assert s.undo()['ok'] and s.undo()['ok']
    assert _centro(s, croce)[0] == 403.5


def test_dividi_propone_il_lato_cliccato_e_lo_accende():
    s = _telaio()
    davanti = _tubo(s, 'Traverso davanti')
    # clic sul davanti del tubo (la faccia guarda verso -Y): prima il davanti
    info = s.dividi_info('ST1', davanti, [0, -1, 0])
    assert [f['key'] for f in info['facce']] == ['davanti', 'sopra']
    # clic sul sopra del tubo: prima il telaio sopra
    info = s.dividi_info('ST1', davanti, [0, 0, 1])
    assert [f['key'] for f in info['facce']] == ['sopra', 'davanti']
    # i tubi del lato proposto, da accendere nel 3D: il davanti ha il traverso e le due gambe
    f = info['facce'][1]
    nomi = s.nomi_tubi(s.result.structures[0])
    assert sorted(nomi[x.split('/')[1]].split(',')[0] for x in f['tubi']) == [
        'Gamba davanti a destra', 'Gamba davanti a sinistra', 'Traverso davanti']
    # senza punto cliccato: come prima (sopra per primo)
    assert s.dividi_info('ST1', davanti)['facce'][0]['key'] == 'sopra'


def test_disegnini_dell_incrocio_diversi():
    s = _telaio()
    assert s.dividi('ST1', _tubo(s, 'Traverso davanti'), 'sopra', 2, 2)['ok']
    st = s.result.structures[0]
    k = next(iter(st.incroci))
    info = s.angolo_info('ST1', k)
    disegni = {x['label']: x['disegno'] for x in info['scelte']}
    assert sorted(disegni.values()) == ['croce_o', 'croce_v']          # uno per tubo, diversi
    # visto dall'alto, il tubo da davanti a dietro è quello in verticale nel disegnino
    assert disegni['Passa intero: traverso in mezzo, da davanti a dietro'] == 'croce_v'
    # sul fianco: il montante (in piedi) è il verticale
    assert s.dividi('ST1', _tubo(s, 'Fianco a sinistra'), 'sinistra', 2, 2, False, None, True)['ok']
    st = s.result.structures[0]
    k = next(x for x in st.incroci if x != k)
    info = s.angolo_info('ST1', k)
    assert next(x['disegno'] for x in info['scelte'] if 'montante' in x['label']) == 'croce_v'


def test_negli_scaffali_passano_i_montanti():
    s = Service()
    s._set(templates.scaffale('S', L=3000, P=600, H=2500, ripiani=8))
    st = s.result.structures[0]
    dav = next(m.id for m in st.members if s.nomi_tubi(st)[m.id].startswith('Traverso davanti, in alto'))
    r = s.dividi('ST1', dav, 'davanti', 4, None, True)
    assert r['ok'], r.get('message')
    st = s.result.structures[0]
    assert st.warnings == [] and len(st.incroci) == 36
    # senza scegliere niente: i montanti nuovi interi (lunghi quanto lo scaffale), i traversi a pezzi
    mont = [m for m in st.members if m.group == 'Montanti']
    assert len(mont) == 6 and all('~' not in m.id for m in mont)
    assert all(st.incroci[x]['passa'].startswith('D') for x in st.incroci)
    # la croce sopra un telaio (due tubi sdraiati): passa ancora il più lungo
    t = _telaio()
    assert t.dividi('ST1', _tubo(t, 'Traverso davanti'), 'sopra', 2, 2)['ok']
    st = t.result.structures[0]
    inc = next(iter(st.incroci.values()))
    passa = next(m for m in st.members if m.id == inc['passa'])
    assert passa.length == pytest.approx(747)


def _con_profilo(prof):
    s = Service()
    s._set(templates.telaio('Telaio', L=1000, P=600, H=800, ripiano=0, profilo=prof, gambe='40x40x3'))
    st = s.result.structures[0]
    dav = next(m.id for m in st.members if s.nomi_tubi(st)[m.id].startswith('Traverso davanti'))
    return s, dav


def _scatola_t(s, mid):
    b = next(m for m in s.result.structures[0].members if m.id == mid).solid.bounding_box()
    return [round(v, 1) for v in (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)]


def test_tubo_rettangolare_in_piedi_o_sdraiato_col_disegnino():
    s, dav = _con_profilo('40x20x2')
    r = s.member_posizioni('ST1/' + dav)
    assert [(p['testo'], p['ora']) for p in r['posizioni']] == [('In piedi (alto 40)', True), ('Sdraiato (alto 20)', False)]
    assert r['su'] == 'su' and r['destra'] == 'fuori'
    sdraiato = r['posizioni'][1]
    assert s.edit_member('ST1/' + dav, {'rotate': sdraiato['rotate'], 'flip': sdraiato['flip']}, True)['ok']
    # sdraiato e a filo: sopra a 800, fuori a 0 (davanti), largo 40 verso dentro; fuori tutto uguale, niente avvisi
    assert _scatola_t(s, dav) == [40, 0, 780, 960, 40, 800]
    st = s.result.structures[0]
    b = st.compound().bounding_box()
    assert [round(v) for v in (b.size.X, b.size.Y, b.size.Z)] == [1000, 600, 800] and st.warnings == []
    assert s.member_posizioni('ST1/' + dav)['posizioni'][1]['ora']
    # la distinta: i traversi sono lunghi uguale (battono contro le gambe)
    from cad_engine.structures import cut_list
    assert sorted((r_['length_mm'], r_['qty']) for r_ in cut_list(s.result.structures)['rows']) == [(520, 2), (800, 4), (920, 2)]
    # tubo quadro: niente da girare
    s2, dav2 = _con_profilo('30x30x2')
    assert s2.member_posizioni('ST1/' + dav2)['posizioni'] == []


def test_angolare_e_upn_dicono_dove_sta_lo_spigolo():
    s, dav = _con_profilo('L 40x40x4')
    r = s.member_posizioni('ST1/' + dav)
    testi = [p['testo'] for p in r['posizioni']]
    assert sorted(testi) == ['Spigolo in alto, dentro', 'Spigolo in alto, fuori', 'Spigolo in basso, dentro',
                             'Spigolo in basso, fuori']
    p = next(p for p in r['posizioni'] if p['testo'] == 'Spigolo in alto, fuori')
    assert s.edit_member('ST1/' + dav, {'rotate': p['rotate'], 'flip': p['flip']}, False)['ok']
    assert _scatola_t(s, dav) == [40, 0, 760, 960, 40, 800]          # resta a filo
    # il disegnino e la realtà: lo spigolo dell'L sta davvero in alto davanti (il materiale vicino a Y=0, Z=800)
    m = next(x for x in s.result.structures[0].members if x.id == dav)
    c = m.solid.center()
    assert c.Y < 20 and c.Z > 780
    s, dav = _con_profilo('UPN 80')
    testi = [p['testo'] for p in s.member_posizioni('ST1/' + dav)['posizioni']]
    assert sorted(testi) == ['Aperto in alto', 'Aperto in basso', 'Aperto verso dentro', 'Aperto verso fuori']
