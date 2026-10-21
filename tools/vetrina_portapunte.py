"""Vetrina: porta punte e maschi da banco in lamiera inox, disegnato con i comandi di SteelCAD.

    python tools/vetrina_portapunte.py [cartella]      (di default Documenti/SteelCAD/Porta punte e maschi)

Corpo a tre gradini (una lamiera sola, 8 pieghe in catena, piedini rivolti dentro), fori svasati per le punte
Ø1–Ø13 (passo 0,5) e i maschi M3–M12, i gradini alti in modo che ogni punta sporga quanto serve per prenderla.
Due fianchi sagomati con il bordo raccordato. Assieme con gli accoppiamenti (faccia su faccia, distanza), controllo
interferenze, distinta, sviluppi DXF per il laser, STEP e tavole.
"""
import os
import sys
from pathlib import Path

QUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(QUI))
import numpy as np  # noqa: E402

from app.service import Service  # noqa: E402
from cad_engine import assembly as A  # noqa: E402

D = Path(os.path.expanduser('~')) / 'Documents' / 'SteelCAD' / 'Porta punte e maschi'   # la cartella dei file
MAT = 'AISI304'
SP, R, K = 2, 1, 0.21                  # i dati della piegatrice di Stefano
LARGO = 300
PEDATA = 60                            # profondità di ogni gradino
ALZATA = 30                            # tra un gradino e l'altro
H1 = 24                                # il primo gradino sopra il banco (la punta Ø1, lunga 34, sporge 10)
GIOCO = 0.2                            # foro = punta + gioco

# punte DIN 338 (Ø) e maschi (Ø del gambo, DIN 371 fino a M10, DIN 376 per M12)
PUNTE_1 = [1 + 0.5 * i for i in range(9)]                 # Ø1 … Ø5      gradino basso, fila davanti
MASCHI = [('M3', 3.5), ('M4', 4.5), ('M5', 6), ('M6', 6), ('M8', 8), ('M10', 10), ('M12', 9)]   # fila dietro
PUNTE_2 = [5.5 + 0.5 * i for i in range(9)]               # Ø5,5 … Ø9,5  gradino di mezzo
PUNTE_3 = [10 + 0.5 * i for i in range(7)]                # Ø10 … Ø13    gradino alto


def ok(r, cosa):
    if not r.get('ok'):
        raise SystemExit(f'{cosa}: {r.get("message")}')
    return r


def cerchi(s, sid):
    return {c['id'] for c in s.sketch_view(sid)['sketch']['circles'] if not c.get('ref')}


def fila(s, faccia, diametri, y_rel, nome):
    """Una fila di fori svasati sulla faccia, da sinistra a destra, equidistanti; y_rel = 0 davanti, 1 dietro."""
    sid = ok(s.sketch_on_face(faccia), f'sketch su {faccia}')['sketch']
    v = s.sketch_view(sid)['sketch']
    pts = [q['xy'] for q in v['points'] if q['id'] != 'O']
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    return sid, x0, x1, y0, y1


def fori(s, sid, xy_d):
    for (x, y), d in xy_d:
        prima = cerchi(s, sid)
        ok(s.sketch_add_circle(sid, [round(x, 3), round(y, 3)], round((d + GIOCO) / 2, 3)), f'foro Ø{d}')
        nuovo = list(cerchi(s, sid) - prima)
        ok(s.sketch_hole_type(sid, nuovo, {'tipo': 'svasato', 'D': round(d + GIOCO + 2 * SP * 0.6, 2), 'angolo': 90}),
           f'svasatura Ø{d}')
    ok(s.create_from_sketch(sid, 'cut', {}), 'togli materiale')


def passo_fila(n, x0, x1, margine=22):
    return [x0 + margine + i * (x1 - x0 - 2 * margine) / (n - 1) for i in range(n)]


def corpo():
    s = Service()
    ok(s.new_project('lamiera', {'name': 'Porta punte - corpo', 'larghezza': LARGO, 'profondita': PEDATA,
                                 'spessore': SP, 'raggio': R, 'k': K, 'material': MAT}), 'lamiera')

    def fl(edge=None, parent=None, **f):
        return ok(s.add_flange('SM1', edge, f, parent), f'piega {f}')['select'].split('/')[-1]
    davanti = fl('L1', length=H1, direction='down')               # il frontale giù fino al banco
    fl(parent=davanti, length=20, direction='up')                  # piedino dentro
    a1 = fl('L3', length=ALZATA, direction='up')                   # alzata
    p2 = fl(parent=a1, length=PEDATA, direction='down')            # gradino di mezzo
    a2 = fl(parent=p2, length=ALZATA, direction='down')            # alzata
    p3 = fl(parent=a2, length=PEDATA, direction='down')            # gradino alto
    dietro = fl(parent=p3, length=H1 + 2 * ALZATA - 2 * SP, direction='up')   # lo schienale giù fino al banco
    fl(parent=dietro, length=20, direction='up')                   # piedino dentro
    # gradino basso: maschi dietro, punte piccole davanti
    sid, x0, x1, y0, y1 = fila(s, 'SM1/sopra', None, 0, 'basso')
    xs = passo_fila(len(PUNTE_1), x0, x1)
    xm = passo_fila(len(MASCHI), x0, x1, 30)
    # quale lato è il davanti nello sketch: il frontale piega su L1 (y del pezzo = 0)
    davanti_basso = y0 if _y_mondo(s, sid, y0) < _y_mondo(s, sid, y1) else y1
    dietro_basso = y1 if davanti_basso == y0 else y0
    yf = davanti_basso + (dietro_basso - davanti_basso) * 0.30
    yb = davanti_basso + (dietro_basso - davanti_basso) * 0.72
    fori(s, sid, [((x, yf), d) for x, d in zip(xs, PUNTE_1)] + [((x, yb), d) for x, (_, d) in zip(xm, MASCHI)])
    for faccia, punte in ((f'SM1/{p2}/esterno', PUNTE_2), (f'SM1/{p3}/esterno', PUNTE_3)):
        if faccia not in s.result.body.names or not _in_su(s, faccia):
            faccia = faccia.replace('esterno', 'interno')
        sid, x0, x1, y0, y1 = fila(s, faccia, None, 0.5, faccia)
        fori(s, sid, [((x, (y0 + y1) / 2), d) for x, d in zip(passo_fila(len(punte), x0, x1), punte)])
    f = D / 'Porta punte - corpo.steelcad'
    ok(s.save(str(f)), 'salva corpo')
    return s, f


def _y_mondo(s, sid, y):
    """La y del pezzo di un punto dello sketch (per sapere quale bordo è il davanti)."""
    from cad_engine.sketch.face_plane import plane_of
    sk = s.doc.sketch(sid)
    piano = plane_of(s.result.body, sk.plane['face'], sk)
    return piano.from_local_coords((0, y)).Y


def _in_su(s, faccia):
    import build123d as bd
    f = bd.Face(s.result.body.face(faccia)[0])
    return f.normal_at(f.center()).Z > 0.99


def fianco(nome):
    """Il fianco: segue i gradini con una diagonale, bordo raccordato. Disegnato di lato (x = profondità, y = altezza)."""
    s = Service()
    ok(s.new_project('zero', {'name': nome, 'material': MAT}), 'pezzo nuovo')
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    prof = 3 * PEDATA - 4                                   # 176: dal frontale allo schienale
    alto = H1 + 2 * ALZATA - 2 * SP + 30                    # 30 sopra il gradino alto
    davanti = H1 + 14
    pts = [[-3, 0], [prof + 3, 0], [prof + 3, alto], [prof - 40, alto], [-3, davanti]]
    ok(s.sketch_add_polyline(sid, pts, True), 'contorno del fianco')
    v = s.sketch_view(sid)['sketch']
    for q in v['points']:
        x, y = q['xy']
        if (abs(x - (prof - 40)) < 1e-6 and abs(y - alto) < 1e-6) or (abs(x + 3) < 1e-6 and abs(y - davanti) < 1e-6):
            ok(s.sketch_fillet(sid, q['id'], 25 if y == alto else 12), 'raccordo')
        elif abs(x - (prof + 3)) < 1e-6 and abs(y - alto) < 1e-6:
            ok(s.sketch_fillet(sid, q['id'], 8), 'raccordo')
    # presa per le dita: un'asola nella parte alta dietro
    ok(s.sketch_add_slot(sid, [prof - 45, alto - 14], [prof - 15, alto - 14], 7), 'asola presa')
    ok(s.create_from_sketch(sid, 'sheet', {'spessore': SP}), 'crea lamiera')
    f = D / f'{nome}.steelcad'
    ok(s.save(str(f)), 'salva fianco')
    return s, f


def faccia(s, iid, n, piu=True, kind='piana', grande=False):
    i = s.asm.instance(iid)
    Rm, T = np.array(i['R']), np.array(i['T'])
    o = next(o for o in s.scene()['objects'] if o['id'] == iid)
    cand = []
    for f in o['faces']:
        inf = s._asm_face(iid, f['index'])
        if inf['kind'] != kind:
            continue
        nw, pw = Rm @ np.array(inf['n']), Rm @ np.array(inf['p']) + T
        if np.dot(nw, n) < 0.999:
            continue
        cand.append((f['count'] if grande else (1 if piu else -1) * np.dot(pw, n), f['index']))
    return {'inst': iid, 'face': max(cand)[1]}


def assieme(fc, ff):
    s = Service()
    ok(s.new_assembly('Porta punte e maschi'), 'assieme')
    ok(s.asm_insert(str(fc)), 'inserisci corpo')
    ok(s.asm_insert(str(ff)), 'inserisci fianco')
    ok(s.asm_insert(str(ff)), 'inserisci fianco')
    ok(s.save(str(D / 'Porta punte e maschi.steelcad-asm')), 'salva assieme')
    X, Y, Z = np.eye(3)
    for iid, lato in (('I2', X), ('I3', -X)):
        ok(s.asm_rotate(iid, 'x', 90), 'ruota fianco')
        ok(s.asm_rotate(iid, 'z', 90), 'ruota fianco')
        # il fianco contro la testata del corpo, la base sul banco, il davanti 3 mm più avanti del frontale
        ok(s.asm_add_mate('faccia', faccia(s, 'I1', lato), faccia(s, iid, -lato, grande=True)), 'faccia su faccia')
        ok(s.asm_add_mate('faccia', faccia(s, 'I1', -Z), faccia(s, iid, -Z), 0, True), 'allinea sotto')
        ok(s.asm_add_mate('distanza', faccia(s, 'I1', -Y, piu=True), faccia(s, iid, -Y, piu=True), 3, True), 'distanza davanti')
    ok(s.save(str(D / 'Porta punte e maschi.steelcad-asm')), 'salva assieme')
    return s


if __name__ == '__main__':
    _arg = [a for a in sys.argv[1:] if not a.startswith('--')]
    if _arg:
        D = Path(_arg[0])
    D.mkdir(parents=True, exist_ok=True)
    sc, fc = corpo()
    print('corpo:', fc.name, 'sviluppo', [round(x, 1) for x in sc.result.body.sheet.flat_size])
    sf, ff = fianco('Porta punte - fianco')
    s = assieme(fc, ff)
    print('avvisi:', s.asm.warnings)
    print('interferenze:', s.asm_interferences().get('interferences'))
    # per l'officina: sviluppi DXF per il laser, pieghe per la piegatrice, disegni, STEP
    for x, num in ((sc, 'PP-001'), (sf, 'PP-002')):
        print(ok(x.prepara(str(D / 'Per officina'), ['laser', 'piegatrice', 'officina', 'step'], {'numero': num}), 'prepara')['message'])
    print(ok(s.prepara(str(D / 'Per officina'), ['officina', 'step'], {'numero': 'PP-000'}), 'prepara assieme')['message'])
