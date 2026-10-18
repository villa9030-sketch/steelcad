"""Due contorni che si sovrappongono (uno esce dall'altro) danno un messaggio chiaro, non un errore interno."""
import os
import tempfile

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402


def test_cerchio_e_rettangolo_che_esce():
    s = Service()
    assert s.new_project('lamiera', {'name': 'x', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_circle(sid, [100, 50], 11)['ok']
    r = s.sketch_add_rectangle(sid, [98, 59], [102, 63.5])
    if r['ok']:
        r = s.create_from_sketch(sid, 'cut', {})
    assert not r['ok']
    assert 'sovrappongono' in r['message'] and 'interno' not in r['message'].lower()
