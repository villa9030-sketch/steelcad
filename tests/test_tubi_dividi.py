"""«Dividi il lato», traverso «in mezzo» e misura al centro o al bordo (03/11, il telaio 807 × 725 × 795 in 30×30×2 di
Stefano: «complicatissimo, il contrario di intuitivo»). Sopra la croce (4 quadri 358 × 317), i fianchi col montante in
mezzo e il traverso a metà (4 quadri 317 × 353), un traverso a 265 da terra: tre comandi."""
import pytest

from app.service import Service
from cad_engine import templates
from cad_engine.structures import cut_list


def _telaio():
    s = Service()
    s._set(templates.telaio('Telaio', L=807, P=725, H=795, ripiano=0, profilo='30x30x2', gambe='30x30x2'))
    return s


def _tubo(s, nome):
    st = s.result.structures[0]
    return next(m.id for m in st.members if s.nomi_tubi(st)[m.id].startswith(nome))


def _righe(s):
    return sorted((x['length_mm'], x['qty']) for x in cut_list(s.result.structures)['rows'])


def _scatola(s, mid):
    b = next(m for m in s.result.structures[0].members if m.id == mid).solid.bounding_box()
    return [round(v, 1) for v in (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)]


def test_le_facce_del_tubo_cliccato():
    s = _telaio()
    info = s.dividi_info('ST1', _tubo(s, 'Fianco a sinistra'))
    assert info['ok'] and [f['key'] for f in info['facce']] == ['sopra', 'sinistra']
    fianco = info['facce'][1]
    assert fianco['u'] == 725 and fianco['v'] == 795 and fianco['opposta'] == 'il fianco a destra'
    assert fianco['aperti'].startswith('Metti anche il tubo a terra')        # il fianco del banco è aperto sotto
    assert 'Il fianco a sinistra' in s.select('ST1/' + _tubo(s, 'Gamba davanti a sinistra'))['selection']['tubo']['facce']


def test_telaio_di_stefano_in_tre_comandi():
    s = _telaio()
    # 1. sopra: la croce, 4 quadri uguali
    r = s.dividi('ST1', _tubo(s, 'Traverso davanti'), 'sopra', 2, 2)
    assert r['ok'], r.get('message')
    assert r['quadri'] == [[358.5, 358.5], [317.5, 317.5]] and '4 quadri 358,5 × 317,5' in r['message']
    st = s.result.structures[0]
    assert len(st.incroci) == 1 and st.warnings == []
    assert max(m.solid.bounding_box().max.Z for m in st.members) == pytest.approx(795)     # a filo, non sopra
    # 2. i fianchi: montante in mezzo e traverso a metà, col tubo a terra, tutti e due i lati
    r = s.dividi('ST1', _tubo(s, 'Fianco a sinistra, in alto'), 'sinistra', 2, 2, True, None, True)
    assert r['ok'], r.get('message')
    assert r['quadri'] == [[317.5, 317.5], [352.5, 352.5]]
    # 3. un traverso a 265 da terra sul dietro (misura al sotto del tubo)
    r = s.dividi('ST1', _tubo(s, 'Gamba dietro a sinistra'), 'dietro', None, {'misure': [265], 'rif': 'bordo'})
    assert r['ok'], r.get('message')
    st = s.result.structures[0]
    assert st.warnings == [] and len(st.incroci) == 3
    b = st.compound().bounding_box()
    assert [round(v, 3) for v in (b.size.X, b.size.Y, b.size.Z)] == [807, 725, 795]          # fuori tutto uguale
    nomi = s.nomi_tubi(st)
    t265 = next(k for k, v in nomi.items() if v.startswith('Traverso dietro, a 265 da terra'))
    assert _scatola(s, t265) == [30, 695, 265, 777, 725, 295]
    # la distinta: stesse misure raggruppate
    assert _righe(s) == [(317.5, 6), (665.0, 4), (735.0, 2), (747.0, 4), (795.0, 4)]
    # il montante del fianco sinistro: a filo fuori, in mezzo alla profondità
    mont = next(k for k, v in nomi.items() if v == 'Montante a sinistra')
    assert _scatola(s, mont) == [0, 347.5, 30, 30, 377.5, 765]


def test_dividi_in_tre_quadri_uguali_e_a_misura():
    s = _telaio()
    r = s.dividi('ST1', _tubo(s, 'Traverso davanti'), 'davanti', 3, None)
    assert r['ok'] and r['quadri'][0] == [229.0, 229.0, 229.0]               # (807 - 4 × 30) / 3
    r = s.dividi('ST1', _tubo(s, 'Traverso dietro'), 'dietro', {'misure': [200, 500], 'rif': 'centro'}, None)
    assert r['ok']
    xs = sorted(round((m.solid.bounding_box().min.X + m.solid.bounding_box().max.X) / 2, 1)
                for m in s.result.structures[0].members if m.group == 'Montanti' and m.start.Y > 700)
    assert xs == [200, 500]
    assert not s.dividi('ST1', _tubo(s, 'Traverso dietro'), 'dietro', {'misure': [5]}, None)['ok']      # fuori
    assert not s.dividi('ST1', _tubo(s, 'Traverso dietro'), 'dietro', 30, None)['ok']    # non ci stanno
    assert not s.dividi('ST1', _tubo(s, 'Traverso dietro'), 'sinistra', 2, None)['ok']   # non è su quel lato


def test_traverso_in_mezzo_e_al_bordo():
    s = _telaio()
    davanti, dietro = _tubo(s, 'Traverso davanti'), _tubo(s, 'Traverso dietro')
    info = s.traverso_info('ST1', davanti, dietro)
    assert info['mezzo'] == 403.5 and not info['in_piedi'] and info['profilo'] == '30x30x2'
    # «In mezzo» con «anche dall'altra parte»: un traverso solo, non due uno sopra l'altro
    r = s.add_traverso('ST1', davanti, dietro, 'mezzo', 'centro', '30x30x2', True, '')
    assert r['ok'] and r['message'] == 'Traverso aggiunto.'
    assert _scatola(s, r['select'].split('/')[1]) == [388.5, 30, 765, 418.5, 695, 795]
    # al bordo: la misura arriva al bordo del traverso (da 100 a 130)
    r = s.add_traverso('ST1', _tubo(s, 'Fianco a sinistra'), _tubo(s, 'Fianco a destra'), 100, 'bordo', '30x30x2')
    assert r['ok']
    assert _scatola(s, r['select'].split('/')[1])[1] == 100
    # tubi in piedi: a metà altezza (la metà del traverso a metà della gamba)
    g1, g2 = _tubo(s, 'Gamba davanti a sinistra'), _tubo(s, 'Gamba davanti a destra')
    assert s.traverso_info('ST1', g1, g2)['mezzo'] == 397.5
    r = s.add_traverso('ST1', g1, g2, 'mezzo', 'sotto', '30x30x2')
    assert r['ok']
    assert _scatola(s, r['select'].split('/')[1])[2] == 382.5
    assert s.result.structures[0].warnings == []


def test_misura_del_punto_col_mouse():
    s = _telaio()
    sel = s.select('ST1/' + _tubo(s, 'Gamba davanti a destra'))['selection']
    m = sel['tubo']['misura']
    assert sel['tubo']['verticale'] and m['z0'] == 0 and m['da'][:2] == [807, 0] and m['lunghezza'] == 795
    sel = s.select('ST1/' + _tubo(s, 'Traverso dietro'))['selection']
    m = sel['tubo']['misura']
    assert m['da'] == [0, 725, 795] and m['dir'] == [1, 0, 0]           # dall'inizio = da sinistra, come il campo


def test_anteprima_di_dividi():
    s = _telaio()
    r = s.anteprima('dividi', ['ST1', _tubo(s, 'Traverso davanti'), 'sopra', {'parti': 2}, {'parti': 2}, False, None,
                               False])
    assert r['ok'] and 'quadri' in r['message'] and len(r['objects']) == 8 + 3
    assert len(s.result.structures[0].members) == 8                     # il progetto non cambia


def test_distinta_con_i_nomi_da_officina():
    s = _telaio()
    s.dividi('ST1', _tubo(s, 'Traverso davanti'), 'sopra', 2, 2)
    righe = {r['length_mm']: r for r in cut_list(s.result.structures)['rows']}
    # i due pezzi della croce: una riga, col nome del tubo e quanti sono
    assert righe[317.5]['qty'] == 2 and righe[317.5]['dove'] == ['Traverso in mezzo, da davanti a dietro, in alto × 2']
    assert 'Traverso in mezzo, in alto' in righe[747.0]['dove']
    # nell'incrocio le due scelte hanno nomi diversi (prima: «Passa intero: traverso in mezzo» due volte)
    k = next(iter(s.result.structures[0].incroci))
    assert sorted(x['label'] for x in s.angolo_info('ST1', k)['scelte']) == [
        'Passa intero: traverso in mezzo', 'Passa intero: traverso in mezzo, da davanti a dietro']


def test_scaffale_grande_incroci_tutti_uguali_e_maglie_tenute():
    s = Service()
    s._set(templates.scaffale('S', L=3000, P=600, H=2500, ripiani=8))
    st = s.result.structures[0]
    dav = next(m.id for m in st.members if s.nomi_tubi(st)[m.id].startswith('Traverso davanti, in alto'))
    r = s.dividi('ST1', dav, 'davanti', 4, None, True)
    assert r['ok'] and r['quadri'][1] == [311.4] * 7 and '28 quadri' in r['message']
    st = s.result.structures[0]
    assert st.warnings == [] and len(st.incroci) == 36
    k = next(iter(st.incroci))
    info = s.angolo_info('ST1', k)
    assert info['incrocio'] and info['simili'] == 36
    # passano interi i montanti, su tutti gli incroci in un colpo
    mont = next(x['key'] for x in info['scelte'] if x['disegno'] == 'verticale')
    r = s.set_angolo('ST1', k, mont, True)
    assert r['ok'] and '36 incroci' in r['message']
    st = s.result.structures[0]
    assert all(st.incroci[x]['passa'].startswith('D') for x in st.incroci)          # i montanti nuovi
    assert sum(1 for m in st.members if m.group == 'Montanti') == 6                  # interi, non a pezzi
    # la scena: i tubi che non cambiano non si rifanno
    from app import service as sv
    s.scene()
    prima = len(sv._MAGLIE_TUBI)
    s.scene()
    assert len(sv._MAGLIE_TUBI) == prima


def test_cambiando_le_misure_le_divisioni_si_rifanno():
    s = _telaio()
    assert s.dividi('ST1', _tubo(s, 'Traverso davanti'), 'sopra', 2, 2)['ok']
    assert s.dividi('ST1', _tubo(s, 'Fianco a sinistra'), 'sinistra', 2, 2, True, None, True)['ok']
    assert s.add_traverso('ST1', _tubo(s, 'Gamba davanti a sinistra'), _tubo(s, 'Gamba davanti a destra'), 150,
                          'sotto', '30x30x2')['ok']
    prima = _righe(s)
    r = s.structure_template_apply('ST1', {'L': 1007, 'H': 895})
    assert r['ok'], r.get('message')
    st = s.result.structures[0]
    assert st.warnings == []
    nomi = s.nomi_tubi(st)
    # la croce sopra di nuovo in mezzo alla larghezza nuova, i montanti dei fianchi lunghi quanto serve
    croce = next(k for k, v in nomi.items() if v.startswith('Traverso in mezzo, da davanti'))
    b = _scatola(s, croce)
    assert (b[0] + b[3]) / 2 == pytest.approx(503.5)
    assert ('Montante a sinistra' in nomi.values()) and _scatola(s, next(k for k, v in nomi.items()
                                                                       if v == 'Montante a sinistra'))[5] == 865
    # il traverso messo a mano resta
    assert any(v.startswith('Traverso davanti, a 150 da terra') for v in nomi.values())
    assert s.undo()['ok'] and _righe(s) == prima
