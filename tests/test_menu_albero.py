"""Tasto destro sull'albero (21/10): rinomina, disattiva/attiva, elimina con chi dipende, piega con i disegni sopra."""
import os
import tempfile

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402


def _pezzo():
    s = Service()
    s.new_project('lamiera', {'name': 'C', 'larghezza': 200, 'profondita': 150, 'spessore': 2, 'raggio': 1, 'k': 0.21})
    s.add_flange('SM1', 'L2', {'length': '50'})
    s.set_ear('SM1', 'FL1', 'u0', True, {'length': '20'})
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    s.sketch_add_circle(sid, [50, 50], 3)
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    taglio = next(f['id'] for f in s.doc.features if not hasattr(f, 'entities') and f['type'] == 'sheet_cut')
    return s, sid, taglio


def test_rinomina_disattiva_elimina():
    s, sid, taglio = _pezzo()
    m = s.tree_menu('sheet_cut', taglio)
    assert m['ok'] and set(m['voci']) >= {'modifica', 'rinomina', 'disattiva', 'elimina'} and m['sketch'] == sid
    assert s.tree_action('sheet_cut', taglio, 'rinomina', 'Foro centrale')['ok']
    nodo = lambda: next(n for n in s.state()['tree']['children'][0]['children'] if n['ref'] == taglio)  # noqa: E731
    assert nodo()['label'] == 'Foro centrale'
    a0 = s.result.body.sheet.flat_area
    assert s.tree_action('sheet_cut', taglio, 'disattiva')['ok']
    assert nodo()['status'] == 'disattivata' and s.result.body.sheet.flat_area > a0      # il foro non c'è più
    assert s.tree_action('sheet_cut', taglio, 'attiva')['ok'] and abs(s.result.body.sheet.flat_area - a0) < 1e-6
    assert s.tree_menu('sketch', sid)['dipendenti']                                      # lo usa il taglio
    assert s.tree_action('sketch', sid, 'elimina')['ok']
    assert not any(getattr(f, 'id', None) == sid or (isinstance(f, dict) and f['id'] == taglio) for f in s.doc.features)
    assert s.undo()['ok'] and any(isinstance(f, dict) and f['id'] == taglio for f in s.doc.features)


def test_elimina_piega_con_disegni_sopra():
    s, _, _ = _pezzo()
    sid = s.sketch_on_face('SM1/FL1/u0/esterno')['sketch']
    s.sketch_add_circle(sid, [8, 25], 2)
    assert s.tree_menu('flange', 'SM1/FL1/u0')['dipendenti']
    assert s.tree_action('flange', 'SM1/FL1/u0', 'elimina')['ok']
    assert not s._sheet_def('SM1')['flanges'][0].get('ears')
    assert not any(getattr(f, 'id', None) == sid for f in s.doc.features)


def test_clic_sulla_faccia_della_piega_apre_la_piega():
    """La faccia di una piega sul bordo, cliccata sul pezzo, apre il pannello di quella piega (per toglierla)."""
    s, _, _ = _pezzo()
    f = next(f for f in s.scene()['objects'][0]['faces'] if f['name'] == 'SM1/FL1/u0/esterno')
    sel = s.select('body', f['index'], f['name'])['selection']
    assert sel['kind'] == 'sidebend' and sel['end'] == 'u0' and sel['face']['name'] == 'SM1/FL1/u0/esterno'
