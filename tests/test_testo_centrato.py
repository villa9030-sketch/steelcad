"""Scritte centrate sul punto cliccato e cambiate col doppio clic (30/10, «che fatica centrare una scritta in un foro»)."""
from app import sketch_ops
from app.service import Service


def _bbox(v, tid):
    t = next(x for x in v['texts'] if x['id'] == tid)
    xs = [q[0] for s in t['strokes'] for q in s]
    ys = [q[1] for s in t['strokes'] for q in s]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(xs) - min(xs), max(ys) - min(ys)


def test_centrata_e_cambiata():
    s = Service()
    assert s.new_project('zero', {'name': 'Testi'})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    assert s.sketch_add_text(sid, [60, 30], 'NK 10/15', 6, 0, None, True)['ok']
    tid = next(k for k, e in s.doc.sketch(sid).entities.items() if e['kind'] == 'text')
    cx, cy, w, h = _bbox(sketch_ops.view(s.doc, sid), tid)
    assert abs(cx - 60) < 0.05 and abs(cy - 30) < 0.05 and w > h
    assert s.sketch_edit_text(sid, tid, 'NK 10/15', 4, 90)['ok']
    cx, cy, w, h = _bbox(sketch_ops.view(s.doc, sid), tid)
    assert abs(cx - 60) < 0.05 and abs(cy - 30) < 0.05 and h > w           # girata, ancora sul centro
    # stencil centrato: anche i contorni da tagliare
    assert s.sketch_edit_text(sid, tid, 'NK 10/15', 6, 0, 'saira')['ok']
    cx, cy, w, h = _bbox(sketch_ops.view(s.doc, sid), tid)
    assert abs(cx - 60) < 0.05 and abs(cy - 30) < 0.5


def test_anteprima_non_cambia_niente():
    s = Service()
    assert s.new_project('zero', {'name': 'Testi'})['ok']
    prima = s.history.dirty
    r = s.testo_anteprima('10/15', 5, 0, None, True)
    assert r['ok'] and r['tratti'] and s.history.dirty == prima
