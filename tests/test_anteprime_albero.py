"""29/10: anteprime per ogni lavorazione (rosse quando non si può, con quello che hai chiesto) e l'albero pulito
(gli sketch dentro la loro lavorazione, quelli non usati in fondo, i vuoti tolti uscendo)."""
from app.service import Service


def _lamiera():
    s = Service()
    s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.5})
    return s


def test_piega_rossa_con_il_fantasma():
    s = _lamiera()
    sid = s.sketch_on_flat('SM1')['sketch']
    s.sketch_add_polyline(sid, [[50, 60], [80, 70]], False)
    r = s.anteprima('sheet_fold', [sid, '90', 'up', False, None])
    assert not r['ok'] and r['vero'] and 'attraversa' in r['message']
    assert r['fantasma'] and r['fantasma'][0]['indices']          # la linea, in rosso
    assert not s._sheet_def('SM1').get('folds')                    # il progetto vero non cambia


def test_taglio_dice_cosa_toglie():
    s = _lamiera()
    sid = s.sketch_on_flat('SM1')['sketch']
    s.sketch_add_polyline(sid, [[20, 20], [70, 20], [70, 40], [20, 40]], True)
    r = s.anteprima('create_from_sketch', [sid, 'cut', {}])
    assert r['ok'] and r['frase'] == 'Toglie dal pezzo: finestra 50 × 20'
    assert r['togli'] and r['togli'][0]['indices']                 # quello che va via, in arancio


def test_togli_un_foro_in_anteprima():
    s = _lamiera()
    sid = s.sketch_on_flat('SM1')['sketch']
    s.sketch_add_circle(sid, [50, 50], 5)
    s.sketch_add_circle(sid, [100, 50], 5)
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    cerchi = [k for k, e in s.doc.sketch(sid).entities.items() if e['kind'] == 'circle']
    r = s.anteprima('togli_dal_taglio', [sid, cerchi[:1]])
    assert r['ok'] and r['frase'].startswith('Chiude il foro')
    assert len([e for e in s.doc.sketch(sid).entities.values() if e['kind'] == 'circle']) == 2


def test_albero_pulito():
    s = _lamiera()
    sid = s.sketch_on_flat('SM1')['sketch']
    s.sketch_add_polyline(sid, [[20, 20], [70, 20], [70, 40], [20, 40]], True)
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    resto = s.sketch_on_flat('SM1')['sketch']
    s.sketch_add_polyline(resto, [[150, 10], [150, 90]], False)           # una linea senza lavorazione
    parte = s.state()['tree']['children'][0]
    nomi = [n['label'] for n in parte['children']]
    assert nomi[0] == 'Base 200 × 100'
    taglio = next(n for n in parte['children'] if n['kind'] == 'sheet_cut')
    assert taglio['label'] == 'Finestra 50 × 20 (sullo sviluppo)' and taglio['chiuso']
    assert [c['label'] for c in taglio['children']] == ['il suo disegno']
    assert not any(n['kind'] == 'sketch' and n['ref'] == sid for n in parte['children'])
    gruppo = parte['children'][-1]
    assert gruppo['label'] == 'Disegni non usati' and [c['label'] for c in gruppo['children']] == ['Linea 80']


def test_sketch_vuoto_tolto_uscendo():
    s = _lamiera()
    sid = s.sketch_on_flat('SM1')['sketch']
    s.sketch_add_polyline(sid, [[150, 10], [150, 90]], False)
    linee = [k for k, e in s.doc.sketch(sid).entities.items() if e['kind'] == 'line']
    s.sketch_delete(sid, linee)                                          # ci ha lavorato, poi ha cancellato tutto
    assert s.sketch_close(sid)['ok']
    assert sid not in [getattr(f, 'id', None) for f in s.doc.features]
    assert s.undo()['ok'] and sid in [getattr(f, 'id', None) for f in s.doc.features]
