"""Bordi arancio che vengono da un taglio (24/10): da dove vengono e come toglierli senza rifare il pezzo."""
from app.service import Service
from cad_engine.features.base import volume


def _pezzo_con_fori():
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    for x in (50, 150, 250):
        assert s.sketch_add_circle(sid, [x, 100], 10)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    nuovo = s.sketch_on_face('SM1/sopra')['sketch']
    sk = s.doc.sketch(nuovo)
    cerchi = [k for k, e in sk.entities.items() if e['kind'] == 'circle' and e.get('ref')]
    assert len(cerchi) == 3
    return s, nuovo, cerchi


def test_da_quale_taglio_vengono():
    s, nuovo, cerchi = _pezzo_con_fori()
    r = s.origine_bordi(nuovo, cerchi[:2])
    assert r['ok'], r
    assert r['feature'].startswith('TG') and r['fori'] == 2 and r['totale'] == 3 and not r['tutti'] and r['eids']
    assert s.origine_bordi(nuovo, cerchi)['tutti']


def test_togli_due_fori_dal_taglio_e_annulla():
    s, nuovo, cerchi = _pezzo_con_fori()
    prima = volume(s.result.body.shape)
    r = s.togli_fori_da_taglio(nuovo, cerchi[:2])
    assert r['ok'], r
    assert volume(s.result.body.shape) > prima + 1                       # i due fori non ci sono più
    sk = s.doc.sketch(nuovo)
    assert len([k for k, e in sk.entities.items() if e['kind'] == 'circle' and e.get('ref')]) == 1   # bordi rifatti
    s.undo()
    assert abs(volume(s.result.body.shape) - prima) < 1e-6
    assert len([k for k, e in s.doc.sketch(nuovo).entities.items() if e['kind'] == 'circle' and e.get('ref')]) == 3


def test_contorno_del_pezzo_non_viene_da_un_taglio():
    s, nuovo, _ = _pezzo_con_fori()
    sk = s.doc.sketch(nuovo)
    linee = [k for k, e in sk.entities.items() if e['kind'] == 'line' and e.get('ref')]
    r = s.origine_bordi(nuovo, linee[:1])
    assert not r['ok'] and 'non vengono da un taglio' in r['message']


def test_fori_disegnati_sullo_sviluppo_si_tolgono_uno_per_uno():
    """28/10: prima i fori di un taglio fatto sullo sviluppo si toglievano solo aprendo il suo disegno."""
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    sid = s.sketch_on_flat()['sketch']
    for x in (50, 150, 250):
        assert s.sketch_add_circle(sid, [x, 100], 10)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    nuovo = s.sketch_on_face('SM1/sopra')['sketch']
    sk = s.doc.sketch(nuovo)
    cerchi = [k for k, e in sk.entities.items() if e['kind'] == 'circle' and e.get('ref')]
    assert len(cerchi) == 3
    r = s.origine_bordi(nuovo, cerchi[:1])
    assert r['ok'] and r['fori'] == 1 and r['eids'] and not r['tutti'], r
    prima = volume(s.result.body.shape)
    assert s.togli_fori_da_taglio(nuovo, cerchi[:1])['ok']
    assert volume(s.result.body.shape) > prima + 1
    assert len([k for k, e in s.doc.sketch(sid).entities.items() if e['kind'] == 'circle' and not e.get('ref')]) == 2


def test_togli_dal_taglio_cliccato_sul_pezzo():
    s, nuovo, _ = _pezzo_con_fori()
    tg = next(f for f in s.doc.features if not hasattr(f, 'entities') and f.get('type') == 'sheet_cut')
    sk = s.doc.sketch(tg['sketch'])
    cerchi = [k for k, e in sk.entities.items() if e['kind'] == 'circle' and not e.get('ref')]
    assert s.togli_dal_taglio(tg['sketch'], cerchi[:1])['ok']
    assert s.togli_dal_taglio(tg['sketch'], cerchi[1:2])['ok']
    r = s.togli_dal_taglio(tg['sketch'], cerchi[2:])
    assert not r['ok'] and r['code'] == 'ultimo' and r['feature'] == tg['id']
