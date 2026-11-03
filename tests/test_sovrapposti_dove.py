"""03/11 — «Due contorni dello sketch si sovrappongono» dice quali (in rosso sul disegno) e, se sono cose disegnate
due volte (la scritta messa due volte col tasto Invio, porta ugelli del 02/11), «Tienine una» le sistema. Nella Storia
e nell'albero niente parole da programma («Elimina T2», «ridondante», «parziale»)."""
from app.service import Service


def _porta_ugelli():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 120, 'spessore': 2, 'raggio': 1, 'k': 0.33})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_circle(sid, [50, 90], 5.1)['ok']
    return s, sid


def test_scritta_doppia_si_vede_e_tienine_una():
    s, sid = _porta_ugelli()
    for _ in range(2):
        assert s.sketch_add_text(sid, [50, 78], '1.2', 5, 0, 'saira', True)['ok']
    r = s.create_from_sketch(sid, 'cut', {})
    assert not r['ok'] and 'si sovrappongono' in r['message']
    d = s.sketch_sovrapposti(sid)
    assert d['ok'] and d['doppioni'] == 1 and len(d['contorni']) == 2
    assert 'la scritta «1.2»' in d['frase'] and 'Tienine una' in d['frase']
    # i contorni rossi stanno dove c'è la scritta (coordinate dello sketch)
    xs = [p[0] for c in d['contorni'] for p in c]
    ys = [p[1] for c in d['contorni'] for p in c]
    assert 40 < min(xs) and max(xs) < 60 and 70 < min(ys) and max(ys) < 86
    t = s.sketch_togli_doppioni(sid)
    assert t['ok'] and t['message'].startswith('Tolta 1 copia doppia')
    assert s.history.labels()['undo'][0] == 'Tolte le copie doppie'
    assert s.create_from_sketch(sid, 'cut', {})['ok']


def test_due_cerchi_accavallati_in_rosso_senza_tienine_una():
    s, sid = _porta_ugelli()
    assert s.sketch_add_circle(sid, [56, 90], 5.1)['ok']
    d = s.sketch_sovrapposti(sid)
    assert d['ok'] and d['doppioni'] == 0 and len(d['contorni']) == 2
    assert d['frase'].startswith('In rosso i due contorni')
    assert not s.sketch_togli_doppioni(sid)['ok']


def test_storia_e_albero_in_parole_di_officina():
    s, sid = _porta_ugelli()
    assert s.sketch_add_text(sid, [50, 78], '1.2', 5, 0, 'saira', True)['ok']
    tid = next(k for k, e in s.doc.sketch(sid).entities.items() if e['kind'] == 'text')
    assert s.sketch_delete(sid, [tid])['ok']
    assert s.history.labels()['undo'][0] == 'Togli il testo «1.2»'
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    taglio = s.doc.features[-1]['id']
    assert s.tree_action('sheet_cut', taglio, 'elimina')['ok']
    assert s.history.labels()['undo'][0].startswith('Togli foro Ø10,2')
    albero = str(s.state()['tree'])
    for parola in ('ridondante', 'parziale', 'sovra-vincolato'):
        assert parola not in albero


def test_scritte_sotto_sei_fori_in_una_volta():
    """Porta ugelli: 6 fori in fila, una scritta tagliata sotto ognuno (da sinistra a destra), un Annulla le toglie."""
    s, sid = _porta_ugelli()
    c0 = next(k for k, e in s.doc.sketch(sid).entities.items() if e['kind'] == 'circle' and not e.get('ref'))
    assert s.sketch_pattern(sid, [c0], 6, 40, 1, 0)['ok']
    cerchi = [k for k, e in s.doc.sketch(sid).entities.items() if e['kind'] == 'circle' and not e.get('ref')]
    numeri = ['1.0', '1.2', '1.5', '2.0', '2.5', '3.0']
    r = s.sketch_scritte_sotto(sid, list(reversed(cerchi)), numeri, 5, 'saira', 2)
    assert r['ok'] and r['message'] == '6 scritte messe sotto i fori.', r
    sk = s.doc.sketch(sid)
    pts = s.doc.solved_sketch(sid).points
    testi = sorted((pts[e['center']][0], pts[e['center']][1], e['text']) for e in sk.entities.values() if e['kind'] == 'text')
    assert [t[2] for t in testi] == numeri                              # da sinistra a destra, come i fori
    assert [round(t[0], 6) for t in testi] == [50, 90, 130, 170, 210, 250]
    assert all(abs(t[1] - (90 - 5.1 - 2 - 2.5)) < 1e-6 for t in testi)   # centrate sotto, a 2 mm dal foro
    assert s.history.labels()['undo'][0] == 'Scritte sotto 6 fori'
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    s.undo()
    s.undo()
    assert not any(e['kind'] == 'text' for e in s.doc.sketch(sid).entities.values())
