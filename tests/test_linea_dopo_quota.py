"""Una linea scritta a misura, che parte da un punto spostato da una quota, è lunga quanto scritto (02/11, il collare:
arco fatto R56 coi clic, corretto a R55, poi la gamba scritta 28 veniva 25,982)."""
import math

from app.service import Service


def test_linea_scritta_da_un_punto_spostato():
    s = Service()
    s.new_project('zero', {'name': 'P'})
    assert s.sketch_add_polyline('S1', [[0, 0], [28, 0]], False)['ok']
    assert s.sketch_add_arc3('S1', [28, 0], [85, 55], [140, 0])['ok']
    r = next(d for d in s.state()['dimensions'] if d['type'] == 'radius')
    assert s.set_dimension('S1', r['dim'], 55)['ok']
    v = s.sketch_view('S1')['sketch']
    xy = {p['id']: p['xy'] for p in v['points']}
    arco = v['arcs'][0]
    fid = max((arco['start'], arco['end']), key=lambda k: xy[k][0])               # la fine lontana dalla prima gamba
    fine = xy[fid]
    assert abs(fine[0] - 140) > 1                                                 # la quota l'ha spostata
    assert s.sketch_add_polyline('S1', [fid, [fine[0] + 28, fine[1]]], False)['ok']
    v = s.sketch_view('S1')['sketch']
    lunghe = sorted(round(math.dist(*[next(p['xy'] for p in v['points'] if p['id'] == k) for k in (l['a'], l['b'])]), 3)
                    for l in v['lines'] if not l.get('construction') and not l.get('ref'))
    assert lunghe == [28, 28]
