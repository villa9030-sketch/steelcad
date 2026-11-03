"""Difetti trovati dal collaudo del 03/11 (lamiera): la finestra a 10 dai bordi di una parete piegata, togliere
l'ultimo foro con una conferma sola."""
import pytest

from app.service import Service


def _scatola_bordata():
    """Come la prova dell'interfaccia: scatola 400×300, pareti da 60, bordi da 20 sulle punte, angoli a 45°."""
    s = Service()
    s.new_project('lamiera', {'name': 'Scatola', 'larghezza': 400, 'profondita': 300, 'spessore': 2, 'raggio': 2, 'k': 0.5})
    for lato in ('L1', 'L2', 'L3', 'L4'):
        assert s.add_flange('SM1', lato, {'length': '60'})['ok']
    for madre in ('FL1', 'FL2', 'FL3', 'FL4'):
        assert s.add_flange('SM1', None, {'length': '20'}, madre)['ok']
    assert s.set_tip_corners('SM1', 'miter')['ok']
    sid = s.sketch_on_face('SM1/FL3/esterno')['sketch']
    v = s.sketch_view(sid)['sketch']
    bordi = [l['id'] for l in v['lines'] if l['label'] == 'bordo del pezzo']
    assert len(bordi) == 4
    return s, sid, bordi


def test_finestra_a_10_dai_bordi_sulla_parete_piegata():
    """Offset 10 dai bordi della parete, il mouse in mezzo alla faccia, «Togli materiale»: la finestra nella parete.
    (Il collaudo la vedeva diventare tutta rossa: il clic arrivava mentre la vista finiva di entrare nella faccia,
    fuori dalla faccia, e l'offset andava fuori dai bordi; ora il lato è quello dell'anteprima vista col mouse fermo.)"""
    s, sid, bordi = _scatola_bordata()
    # la faccia dritta di FL3 è 392 × 52: in mezzo si sceglie «dentro», fuori dalla faccia «fuori»
    assert s.sketch_offset_side(sid, bordi, 10, [196, 26])['side'] == 'in'
    assert s.sketch_offset_side(sid, bordi, 10, [292.7, 65.2])['side'] == 'out'
    assert s.sketch_offset(sid, bordi, 10, 'in')['ok']
    v0 = s.state()['info']['part']['volume_mm3']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')
    assert not s.state()['errors']
    assert v0 - s.state()['info']['part']['volume_mm3'] == pytest.approx(372 * 32 * 2, rel=1e-9)


def test_offset_fuori_dai_bordi_non_taglia_la_parete():
    """Il contorno a 10 FUORI dai bordi prende tutta la parete: il taglio non si fa e il pezzo resta com'era."""
    s, sid, bordi = _scatola_bordata()
    assert s.sketch_offset(sid, bordi, 10, 'out')['ok']
    v0 = s.state()['info']['part']['volume_mm3']
    r = s.create_from_sketch(sid, 'cut', {})
    assert not r['ok'] and 'divide lo sviluppo' in r['message']
    assert s.state()['info']['part']['volume_mm3'] == pytest.approx(v0)


def _pezzo_con_un_foro():
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_circle(sid, [150, 100], 10)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    tg = next(f for f in s.doc.features if not hasattr(f, 'entities') and f.get('type') == 'sheet_cut')
    cerchio = next(k for k, e in s.doc.sketch(sid).entities.items() if e['kind'] == 'circle' and not e.get('ref'))
    return s, sid, tg, cerchio


def test_ultimo_foro_la_barra_sa_gia_cosa_sparisce():
    """L'ultimo foro di un taglio: la barra di conferma dice già cosa sparisce insieme (prima si apriva dopo anche
    la finestra «Elimina», due conferme per un foro)."""
    s, sid, tg, cerchio = _pezzo_con_un_foro()
    sopra = s.sketch_on_face('SM1/sopra')['sketch']            # un disegno sopra, che usa i bordi del foro
    assert s.sketch_add_circle(sopra, [50, 50], 5)['ok']
    r = s.togli_dal_taglio(sid, [cerchio])
    assert not r['ok'] and r['code'] == 'ultimo' and r['feature'] == tg['id']
    assert isinstance(r['dipendenti'], list)
    a = s.anteprima('togli_dal_taglio', [sid, [cerchio]])        # quello che legge la barra
    assert a['code'] == 'ultimo' and a.get('dipendenti', []) == r['dipendenti']
    # la conferma della barra toglie subito il taglio (la stessa azione che faceva la finestra «Elimina»)
    v0 = s.state()['info']['part']['volume_mm3']
    assert s.tree_action('feature', r['feature'], 'elimina')['ok']
    assert s.state()['info']['part']['volume_mm3'] > v0 + 1
    assert not any(f.get('id') == tg['id'] for f in s.doc.features if not hasattr(f, 'entities'))
