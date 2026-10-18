"""Progetto di prova con più componenti (python tools/prova_assieme_completo.py [cartella vuota]): telaio con staffe, traversa, spalla con incastri, supporto piegato.
Ogni passo controlla il risultato e stampa OK/NO."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np  # noqa: E402

from app.service import Service  # noqa: E402

D = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='steelcad_assieme_'))
D.mkdir(parents=True, exist_ok=True)
if any(D.iterdir()):
    raise SystemExit(f'La cartella {D} non è vuota: dammene una vuota (i file dei pezzi vengono scritti lì).')
esiti = []


def ok(t, c, extra=''):
    esiti.append(bool(c))
    extra = str(extra) if extra is not None else ''
    print(('OK   ' if c else 'NO   ') + t + (f'  [{extra}]' if extra else ''), flush=True)
    return c


def must(r, t):
    if not r.get('ok'):
        print('ERRORE', t, r.get('message'))
        raise SystemExit(1)
    return r


TECH = {'raggio': 2, 'k': 0.4}


def pezzo(nome, L, P, sp, passi):
    s = Service()
    must(s.new_project('lamiera', {'name': nome, 'larghezza': L, 'profondita': P, 'spessore': sp, **TECH}), nome)
    passi(s)
    errori = s.state()['errors']
    must(s.save(str(D / f'{nome.lower()}.steelcad')), 'salva ' + nome)
    ok(f'pezzo {nome}: costruito senza errori', not errori, ', '.join(e['message'] for e in errori))
    return D / f'{nome.lower()}.steelcad'


def fori(s, faccia, centri, r):
    sid = must(s.sketch_on_face(faccia), 'sketch')['sketch']
    for c in centri:
        must(s.sketch_add_circle(sid, c, r), 'cerchio')
    must(s.create_from_sketch(sid, 'cut', {}), 'fori')


t0 = time.time()
# ------------------------------------------------------------------ i pezzi
def p_fondo(s):
    must(s.add_flange('SM1', 'L2', {'length': '25', 'direction': 'down'}), 'piede')
    must(s.add_flange('SM1', 'L4', {'length': '25', 'direction': 'down'}), 'piede')
    fori(s, 'SM1/sopra', [[50, 150], [90, 150], [310, 150], [350, 150]], 4.25)


def p_staffa(s):
    fori(s, 'SM1/sopra', [[20, 20], [60, 20]], 4.25)
    must(s.add_flange('SM1', 'L3', {'length': '100'}), 'flangia staffa')
    sid = must(s.sketch_on_face('SM1/FL1/esterno'), 'sk')['sketch']
    must(s.sketch_add_circle(sid, [20, 60], 3.25), 'c')
    must(s.sketch_add_circle(sid, [60, 60], 3.25), 'c')
    must(s.create_from_sketch(sid, 'cut', {}), 'fori flangia')


def p_traversa(s):
    fori(s, 'SM1/sopra', [[20, 30], [60, 30], [280, 30], [320, 30]], 3.25)
    must(s.add_flange('SM1', 'L1', {'length': '25'}), 'ala')
    must(s.add_flange('SM1', 'L3', {'length': '25'}), 'ala')


def p_spalla(s):
    must(s.add_flange('SM1', 'L1', {'length': '40'}), 'flangia spalla')
    fori(s, 'SM1/sopra', [[50, 60], [150, 60]], 10)


def p_supporto(s):
    sid = must(s.sketch_on_flat('SM1'), 'sv')['sketch']
    must(s.sketch_add_polyline(sid, [[-5, 40], [125, 40]], False), 'linea')
    must(s.sheet_fold(sid, 90, 'up'), 'piega su linea')
    must(s.add_flange('SM1', None, {'length': '8', 'angle': 180, 'direction': 'up'}, 'PL1'), 'orlo')
    fori(s, 'SM1/sopra', [[30, 20], [90, 20]], 3.25)


F = {'fondo': pezzo('Fondo', 400, 300, 3, p_fondo), 'staffa': pezzo('Staffa', 80, 40, 2, p_staffa),
     'traversa': pezzo('Traversa', 340, 60, 2, p_traversa), 'spalla': pezzo('Spalla', 200, 120, 2, p_spalla),
     'supporto': pezzo('Supporto', 120, 60, 2, p_supporto)}

# ------------------------------------------------------------------ l'assieme
s = Service()
must(s.new_assembly('Telaio con spalla'), 'nuovo assieme')
for k in ('fondo', 'staffa', 'staffa', 'traversa', 'spalla', 'supporto'):
    must(s.asm_insert(str(F[k])), 'inserisci ' + k)
ist = {i['id']: i['name'] for i in s.asm.instances}
ok('6 copie inserite (staffa due volte)', len(s.asm.instances) == 6, ', '.join(f'{k}={v}' for k, v in ist.items()))


def faccia(iid, nome=None, kind='piana', vicino=None):
    best = None
    for o in s.scene()['objects']:
        if o['id'] != iid:
            continue
        for f in o['faces']:
            inf = s._asm_face(iid, f['index'])
            if inf['kind'] != kind or (nome and inf['name'] != nome):
                continue
            d = np.linalg.norm(np.array(inf['p']) - np.array(vicino)) if vicino is not None else 0
            if best is None or d < best[0]:
                best = (d, f['index'], inf)
    if best is None:
        raise SystemExit(f'faccia non trovata: {iid} {nome} {kind}')
    return best[1]


def mate(tipo, a, b, **kw):
    return must(s.asm_add_mate(tipo, {'inst': a[0], 'face': a[1]}, {'inst': b[0], 'face': b[1]}, kw.get('offset', 0), kw.get('flip', False)), f'{tipo} {a[0]}-{b[0]}')


def mondo(iid, p):
    i = s.asm.instance(iid)
    return np.array(i['R']) @ np.array(p) + np.array(i['T'])


# staffe sul fondo: faccia su faccia + i due fori
for iid, (xa, xb) in (('I2', (50, 90)), ('I3', (310, 350))):
    mate('faccia', ('I1', faccia('I1', 'SM1/sopra')), (iid, faccia(iid, 'SM1/sotto')))
    mate('asse', ('I1', faccia('I1', None, 'cilindrica', [xa, 150, 1.5])), (iid, faccia(iid, None, 'cilindrica', [20, 20, 1])))
    mate('asse', ('I1', faccia('I1', None, 'cilindrica', [xb, 150, 1.5])), (iid, faccia(iid, None, 'cilindrica', [60, 20, 1])))
def fori_fondo():
    out = []
    for o in s.scene()['objects']:
        if o['id'] == 'I1':
            for f in o['faces']:
                inf = s._asm_face('I1', f['index'])
                if inf['kind'] == 'cilindrica' and abs(inf['r'] - 4.25) < 1e-6:
                    q = mondo('I1', inf['p'])
                    out.append((round(q[0], 6), round(q[1], 6)))
    return sorted(set(out))


def fori_staffe():
    out = []
    for iid in ('I2', 'I3'):
        for o in s.scene()['objects']:
            if o['id'] == iid:
                for f in o['faces']:
                    inf = s._asm_face(iid, f['index'])
                    if inf['kind'] == 'cilindrica' and abs(inf['r'] - 4.25) < 1e-6:
                        q = mondo(iid, inf['p'])
                        out.append((round(q[0], 6), round(q[1], 6)))
    return sorted(set(out))
ff, fs = fori_fondo(), fori_staffe()
zs = [mondo(i, [40, 20, 0])[2] for i in ('I2', 'I3')]
ok('staffe: i loro 4 fori coincidono con i 4 del fondo, appoggiate sul fondo (z = 3)', ff == fs and np.allclose(zs, 3, atol=1e-6), f'{ff} / z {np.round(zs, 4)}')

# traversa contro le flange delle staffe: faccia + fori (uno in più del necessario: deve tornare lo stesso)
fl = lambda iid, x: mondo(iid, [x, 42, 62])  # noqa: E731 - circa dove sono i fori della flangia (solo per scegliere)
def foro_flangia(iid, k):
    centri = []
    for o in s.scene()['objects']:
        if o['id'] == iid:
            for f in o['faces']:
                inf = s._asm_face(iid, f['index'])
                if inf['kind'] == 'cilindrica' and abs(inf['r'] - 3.25) < 1e-6:
                    centri.append((inf['p'][0], f['index']))
    centri.sort()
    return centri[k][1]
mate('faccia', ('I2', faccia('I2', 'SM1/FL1/esterno')), ('I4', faccia('I4', 'SM1/sotto')))
mate('asse', ('I2', foro_flangia('I2', 0)), ('I4', faccia('I4', None, 'cilindrica', [20, 30, 1])))
mate('asse', ('I2', foro_flangia('I2', 1)), ('I4', faccia('I4', None, 'cilindrica', [60, 30, 1])))
mate('asse', ('I3', foro_flangia('I3', 1)), ('I4', faccia('I4', None, 'cilindrica', [320, 30, 1])))
avv = s.state()['warnings']
ok('traversa sulle due staffe, con un foro in più: nessun contrasto', not avv, '; '.join(avv))

# spalla: la punta della flangia appoggia sul fondo, poi la si sposta a mano dove serve
mate('faccia', ('I1', faccia('I1', 'SM1/sopra')), ('I5', faccia('I5', 'SM1/FL1/punta')))
def centro_faccia(iid, nome):
    return mondo(iid, s._asm_face(iid, faccia(iid, nome))['p'])
c, cb = centro_faccia('I5', 'SM1/FL1/punta'), centro_faccia('I5', 'SM1/sotto')
if cb[1] < c[1]:                                   # il pannello deve andare verso l'interno del telaio (+Y)
    must(s.asm_rotate('I5', 'z', 180), 'giro la spalla')
    c = centro_faccia('I5', 'SM1/FL1/punta')
must(s.asm_move('I5', 205 - c[0], 25 - c[1], 0), 'spalla sul fondo, davanti, col pannello verso l’interno')

# supporto sulla traversa: faccia su faccia, poi spostato sopra la traversa
mate('faccia', ('I4', faccia('I4', 'SM1/sopra')), ('I6', faccia('I6', 'SM1/sotto')))
ct, cs_ = centro_faccia('I4', 'SM1/sopra'), centro_faccia('I6', 'SM1/sotto')
d = ct - cs_
must(s.asm_move('I6', d[0], d[1], d[2]), 'supporto sopra la traversa')
st = s.state()
ok('assieme risolto senza avvisi', not st['warnings'], '; '.join(st['warnings']))

# ------------------------------------------------------------------ controlli
inter = s.asm_interferences()['interferences']
ok('nessuna interferenza dopo il montaggio', not inter, '; '.join(x['label'] for x in inter))
mid = next(m['id'] for m in s.asm.mates if m['b']['inst'] == 'I6')
must(s.asm_edit_mate(mid, {'offset': -1.5}), 'spingo dentro il supporto')
inter = s.asm_interferences()['interferences']
ok('interferenza voluta (supporto 1,5 mm dentro la traversa) trovata', len(inter) == 1 and {'I4', 'I6'} == {inter[0]['a'], inter[0]['b']},
   '; '.join(x['label'] for x in inter))
must(s.asm_edit_mate(mid, {'offset': 0}), 'rimetto a posto')

# incastri tra spalla e fondo
punta = faccia('I5', 'SM1/FL1/punta')
sel = s.select('I5', punta)['selection']
ok('la punta della spalla appoggia sul fondo (incastri possibili)', sel.get('tabs_with') == 'Fondo', sel.get('tabs_with'))
r = s.asm_tabs('I5', punta, 4, 20, 0.2, 0)
ok('incastri spalla → fondo: 4 linguette e 4 asole', r['ok'], r.get('message'))
inter = s.asm_interferences()['interferences']
ok('nessuna interferenza dopo gli incastri (le linguette passano nelle asole)', not inter, '; '.join(x['label'] for x in inter))

# distinta
bom = {b['description'].split(',')[0]: b for b in s.state()['bom']}
ok('distinta: 5 pezzi diversi, staffa × 2', len(bom) == 5 and bom['Staffa']['qty'] == 2,
   ', '.join(f'{k} ×{v["qty"]} {v["kg_total"]:.2f} kg' for k, v in bom.items()))

# modifica di un pezzo dall'assieme: il fondo passa da 3 a 4 mm, le staffe devono seguire
must(s.save(str(D / 'telaio.steelcad-asm')), 'salva assieme')
must(s.asm_open_part('I1'), 'apri fondo')
must(s.set_parameter('sp', 4), 'spessore 4')
must(s.save(), 'salva fondo')
must(s.asm_back(), 'torna')
zs = [mondo(i, [40, 20, 0])[2] for i in ('I2', 'I3')]
ok('fondo a 4 mm: le staffe salgono a z = 4 restando sui fori', np.allclose(zs, 4, atol=1e-6) and fori_fondo() == fori_staffe(), np.round(zs, 4))
ok('dopo la modifica: niente avvisi né interferenze', not s.state()['warnings'] and not s.asm_interferences()['interferences'])

# annulla / ripeti, salva / riapri, STEP
n = len(s.asm.mates)
must(s.asm_delete_mate(s.asm.mates[-1]['id']), 'togli un accoppiamento')
must(s.undo(), 'annulla')
ok('annulla rimette l’accoppiamento', len(s.asm.mates) == n)
must(s.save(), 'salva')
s2 = Service()
must(s2.open(str(D / 'telaio.steelcad-asm')), 'riapri')
ok('riaperto: stesse copie e accoppiamenti, nessun avviso', len(s2.asm.instances) == 6 and len(s2.asm.mates) == n and not s2.state()['warnings'])
r = s2.export_step(str(D / 'telaio.step'))
ok('STEP dell’assieme', r['ok'] and (D / 'telaio.step').stat().st_size > 10000, r.get('message'))
print(f'\n{sum(esiti)}/{len(esiti)} ok in {time.time() - t0:.0f} s — file in {D}')
