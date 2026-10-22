"""23/10: «come faccio a eliminare delle quote che ho fatto?» — una quota dello sketch si toglie (tasto destro), il
disegno resta com'è, Annulla la rimette."""
import os
import tempfile

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402


def test_togli_quota_e_annulla(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'r.json'))
    s = Service()
    assert s.new_project('lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 1, 'k': 0.4})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_circle(sid, [50, 50], 5)['ok']
    quote = lambda: [x['dim'] for x in s.state()['dimensions'] if x['sketch'] == sid]  # noqa: E731
    prima = quote()
    raggio = lambda: [c['r'] for c in s.sketch_view(sid)['sketch']['circles'] if not c['ref']]  # noqa: E731
    assert s.sketch_delete_dimension(sid, prima[0])['ok']
    assert quote() == prima[1:] and raggio() == [5]
    s.undo()
    assert quote() == prima
    r = s.sketch_delete_dimension(sid, 'D99')
    assert not r['ok'] and 'Errore interno' not in r['message']
