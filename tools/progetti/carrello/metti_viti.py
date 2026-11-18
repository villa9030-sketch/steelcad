import sys, shutil, time, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # la cartella di Radius
from app.service import Service
from cad_engine import assembly as A
from cad_engine.topology.naming import _faces_of
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
shutil.copy(src, dst)
s = Service(); r = s.open(str(dst)); assert r['ok'], r
fori = []
for i in s.asm.instances:
    part = s.asm_parts[i['file']]; R, T = np.array(i['R']), np.array(i['T'])
    visti = []
    for k, f in enumerate(_faces_of(part.shape)):
        inf = A.face_info(part, f)
        if inf['kind'] != 'cilindrica' or abs(2 * inf['r'] - 9) > 1e-3: continue
        n = R @ np.array(inf['n']); p = R @ np.array(inf['p']) + T
        q = p - n * np.dot(p, n)
        if any(np.linalg.norm(q - v[0]) < 1e-3 and abs(np.dot(p - v[1], n)) < 12 for v in visti): continue   # stesso foro (le due facce)
        visti.append((q, p)); fori.append((i['id'], k, p, n))
coppie = []
for a in fori:
    if not a[0].startswith('I') or a[0] not in ('I1', 'I2', 'I3', 'I4'): continue     # dalla gamba
    for b in fori:
        if b[0] in ('I1', 'I2', 'I3', 'I4'): continue
        if np.linalg.norm(np.cross(a[3], b[3])) < 1e-4 and np.linalg.norm(A._perp(b[2] - a[2], a[3])) < 0.05 and abs(np.dot(b[2] - a[2], a[3])) < 12:
            coppie.append((a, b))
print(len(coppie), 'coppie')
centro = np.array([4100.0, 400.0, 0.0])
t0 = time.time()
for a, b in coppie:
    n = a[3] / np.linalg.norm(a[3])
    fuori = n if np.dot(a[2] - centro, n) * 1 > 0 and abs(np.dot(a[2] - centro, n)) > 1 else -n
    fuori = n if np.dot((a[2] - centro) * np.array([1, 1, 0]), n) > 0 else -n
    fa, fb = {'inst': a[0], 'face': a[1]}, {'inst': b[0], 'face': b[1]}
    pr = s.asm_bullone(fa, fb, {'verso': fuori.tolist()}, True)
    r = s.asm_bullone(fa, fb, {'tipo': 'vite_tbei', 'misura': 'M8', 'L': 16, 'dado': True, 'inox': True, 'rondella': False,
                                'verso': fuori.tolist()})
    assert r['ok'], r.get('message')
    print(b[0], np.round(a[2], 1), 'pacco', pr['proposta']['pacco'], '|', r['message'][:70])
print('tempo', round(time.time() - t0), 's; avvisi', s.asm.warnings)
viti = [i for i in s.asm.instances if 'inox' in i['name']]
print(len(viti), 'pezzi inox')
for x in A.interferences(s.asm, s.asm_parts):
    print('INTERFERENZA', s.asm.instance(x['a'])['name'], '|', s.asm.instance(x['b'])['name'], round(x['volume'], 1))
r = s.save(str(dst)); assert r['ok'], r
print('salvato', dst)
