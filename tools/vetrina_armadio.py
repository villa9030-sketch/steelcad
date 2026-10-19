"""Vetrina di SteelCAD: armadio 800 × 500 × 1800 con telaio in tubolare, ripiani e due ante, chiuso con la lamiera.

    python tools/vetrina_armadio.py [cartella]          (di default Documenti/SteelCAD/vetrina_armadio)
    python tools/vetrina_armadio.py --live [cartella]   in diretta: si apre Chrome e si vede crescere ogni pezzo

Pezzi: telaio (modello "Telaio armadio", 40×40×2), fianco (×2), schiena, cielo e fondo in lamiera sp. 1,5 con i fori
di fissaggio sui tubi; 3 ripiani a vaschetta sp. 1,5 con angoli chiusi; anta sp. 1 con i bordi di rinforzo e il foro
della serratura (×2, la destra è la sinistra girata). Poi l'assieme, le interferenze, la distinta, le tavole e lo STEP.
Raggi e K-factor sono valori di esempio (r = spessore, K 0,4): per la produzione vanno quelli della tua piegatrice.

Coordinate dell'assieme: X larghezza, Y profondità (davanti a y = −20), Z altezza. Il telaio ha gli assi dei tubi a
x = 0…L, y = 0…P, z = 0…H, quindi l'ingombro esterno dei tubi è −20…L+20 (e così via).
"""
import importlib.util
import os
import sys
import time
from pathlib import Path

import numpy as np

QUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(QUI))
import build123d as bd  # noqa: E402

from app.service import Service  # noqa: E402

LIVE = '--live' in sys.argv
_arg = [a for a in sys.argv[1:] if not a.startswith('--')]
D = Path(_arg[0]) if _arg else Path(os.path.expanduser('~')) / 'Documents' / 'SteelCAD' / 'vetrina_armadio'
D.mkdir(parents=True, exist_ok=True)
T0 = time.time()

L, P, H = 800, 500, 1800          # assi dei tubi
TUBO = 20                         # metà del 40×40
SP = 1.5                          # pannelli e ripiani
SP_ANTA = 1.0
LIVELLI = (0, 600, 1200)          # ripiani appoggiati sui traversi
GIOCO_ANTA = 3                    # tra le ante e tra anta e struttura
BORDO_ANTA = 15                   # bordi di rinforzo delle ante, verso l'interno

s = None
DIRETTA = None
SKETCH = [None]
NUOVI = ('new_project', 'new_assembly')
CHIUDONO = ('create_from_sketch',)


# ------------------------------------------------------------------------------ diretta e comandi
def servizio():
    return DIRETTA.svc if DIRETTA else Service()


def mostra(nuovo=False, key=None):
    if DIRETTA:
        DIRETTA.manda({'type': 'refresh', 'sketch': SKETCH[0], 'nuovo': nuovo, 'key': key})
        time.sleep(0.12)


def avvisa(testo):
    if DIRETTA:
        DIRETTA.manda({'type': 'toast', 'text': testo})
        time.sleep(1.4)


def ok(nome, *a):
    r = getattr(s, nome)(*a)
    if not r.get('ok'):
        raise SystemExit(f'\nERRORE {nome}{a}: {r.get("message")}')
    if DIRETTA and nome not in ('sketch_view', 'save', 'export_drawings', 'asm_export_step'):
        if nome == 'sketch_on_face':
            SKETCH[0] = r['sketch']
        elif nome in CHIUDONO:
            SKETCH[0] = None
        mostra(nuovo=nome in NUOVI)
    return r


def titolo(t):
    print(f'\n[{time.time() - T0:5.1f}s] {t}', flush=True)
    avvisa(t)


def passo(t):
    print(f'   · {t}', flush=True)
    avvisa(t[0].upper() + t[1:])


def salva(nome):
    st = s.state()
    if st['errors']:
        raise SystemExit(f'{nome}: ' + '; '.join(e['message'] for e in st['errors']))
    p = D / f'{nome}.steelcad'
    ok('save', str(p))
    if s.result.body is not None:
        b = s.result.body
        sz = [round(x, 1) for x in bd.Shape.cast(b.shape).bounding_box().size]
        sv = [round(x, 1) for x in b.sheet.flat_size] if getattr(b, 'sheet', None) else '-'
        print(f'   = {nome}: ingombro {sz}, sviluppo {sv}', flush=True)
    return p


def lamiera(nome, larg, prof, sp):
    global s
    s = servizio()
    ok('new_project', 'lamiera', {'name': nome, 'larghezza': larg, 'profondita': prof, 'spessore': sp,
                                  'raggio': sp, 'k': 0.4})


def fori(xy, d, faccia='SM1/sopra'):
    """Fori passanti disegnati sulla faccia (coordinate del pezzo: sulla faccia di sopra coincidono)."""
    sid = ok('sketch_on_face', faccia)['sketch']
    for x, y in xy:
        ok('sketch_add_circle', sid, [x, y], d / 2)
    ok('create_from_sketch', sid, 'cut', {})


# ============================================================================== pezzi
def telaio():
    global s
    titolo('1. TELAIO 800 × 500 × 1800 in tubolare 40×40×2 (modello Telaio armadio)')
    s = servizio()
    ok('new_project', 'armadio', {'name': 'Telaio armadio', 'L': L, 'P': P, 'H': H, 'ripiani': 4,
                                  'profilo': '40x40x2'})
    cl = s.state()['cutlist']
    passo(f'{cl["pieces"]} aste, {cl["kg"]:.1f} kg: montanti dritti, traversi a 45° in cima e a terra, '
          'a battuta ai livelli intermedi')
    return salva('telaio')


def pannelli():
    titolo('2. PANNELLI sp. 1,5: fianchi, schiena, cielo, fondo, con i fori Ø6 sui tubi')
    z_fori = (100 + TUBO, H / 2 + TUBO, H - 100 + TUBO)           # nel pezzo: y = z + 20
    F = {}
    passo('fianco: copre il telaio di lato (P + 40 × H + 40); un solo pezzo per destra e sinistra')
    lamiera('Fianco', P + 2 * TUBO, H + 2 * TUBO, SP)
    fori([(TUBO, z) for z in z_fori] + [(P + TUBO, z) for z in z_fori], 6)
    F['fianco'] = salva('fianco')
    passo('schiena: copre anche lo spessore dei fianchi')
    W = L + 2 * TUBO + 2 * SP
    lamiera('Schiena', W, H + 2 * TUBO, SP)
    fori([(TUBO + SP, z) for z in z_fori] + [(L + TUBO + SP, z) for z in z_fori], 6)
    F['schiena'] = salva('schiena')
    passo('cielo e fondo: coprono fianchi e schiena')
    for nome in ('Cielo', 'Fondo'):
        lamiera(nome, W, P + 2 * TUBO + SP, SP)
        fori([(TUBO + SP + x, TUBO + y) for x in (0, L) for y in (0, P)], 6)
        F[nome.lower()] = salva(nome.lower())
    return F


def ripiano():
    titolo('3. RIPIANO a vaschetta sp. 1,5: bordi da 20 in su, angoli chiusi')
    lamiera('Ripiano', L - 2 * TUBO, P + 2 * TUBO, SP)
    for e in ('L1', 'L2', 'L3', 'L4'):
        ok('add_flange', 'SM1', e, {'length': '20'})
    for a, b in (('FL1', 'FL2'), ('FL1', 'FL4'), ('FL3', 'FL2'), ('FL3', 'FL4')):
        ok('set_corner', 'SM1', a, b, 'over', 0.5)
    passo('appoggia sui traversi davanti e dietro, tra i montanti')
    return salva('ripiano')


def anta():
    titolo('4. ANTA sp. 1: bordi di rinforzo da 15 verso l’interno, angoli chiusi, foro serratura Ø22')
    W = L + 2 * TUBO + 2 * SP
    larg = (W - GIOCO_ANTA) / 2
    alt = H + 2 * TUBO + 2 * SP
    lamiera('Anta', larg, alt, SP_ANTA)
    for e in ('L1', 'L2', 'L3', 'L4'):
        ok('add_flange', 'SM1', e, {'length': str(BORDO_ANTA)})
    for a, b in (('FL1', 'FL2'), ('FL1', 'FL4'), ('FL3', 'FL2'), ('FL3', 'FL4')):
        ok('set_corner', 'SM1', a, b, 'over', 0.5)
    passo('serratura vicino al bordo dove si incontrano le ante (la destra è la sinistra girata)')
    fori([(40, alt / 2)], 22)
    return salva('anta'), larg, alt


# ============================================================================== assieme
def assieme(F, larg_anta, alt_anta):
    global s
    titolo('5. ASSIEME: telaio, pannelli, ripiani e ante al loro posto')
    s = servizio()
    ok('new_assembly', 'Armadio 800x500x1800')
    ordine = [('telaio', 'Telaio'), ('fianco', 'Fianco sinistro'), ('fianco', 'Fianco destro'),
              ('schiena', 'Schiena'), ('cielo', 'Cielo'), ('fondo', 'Fondo')]
    ordine += [('ripiano', f'Ripiano a {z}') for z in LIVELLI]
    ordine += [('anta', 'Anta sinistra'), ('anta', 'Anta destra')]
    for k, _ in ordine:
        ok('asm_insert', str(F[k]))
    ids = [i['id'] for i in s.asm.instances]
    for iid, (_, nome) in zip(ids, ordine):
        ok('asm_set', iid, {'name': nome})
    ok('asm_set', ids[0], {'fixed': True})

    def posa(iid, R, punto_locale, punto_mondo):
        R = np.array(R, dtype=float)
        T = np.array(punto_mondo, dtype=float) - R @ np.array(punto_locale, dtype=float)

        def fn():
            i = s.asm.instance(iid)
            i['R'], i['T'] = R.tolist(), T.tolist()
        r = s._asm_change(f'Posa {iid}', fn)
        if not r.get('ok'):
            raise SystemExit(r.get('message'))
        mostra()

    I3 = np.eye(3)
    t, e = TUBO, SP
    passo('fianchi fuori dai montanti (lo stesso pezzo, girato per la destra)')
    posa(ids[1], [[0, 0, 1], [1, 0, 0], [0, 1, 0]], [0, 0, 0], [-t - e, -t, -t])            # X→Y, Y→Z, Z→X
    posa(ids[2], [[0, 0, -1], [-1, 0, 0], [0, 1, 0]], [0, 0, 0], [L + t + e, P + t, -t])     # X→−Y, Y→Z, Z→−X
    passo('schiena dietro, cielo sopra e fondo sotto')
    posa(ids[3], [[1, 0, 0], [0, 0, -1], [0, 1, 0]], [0, 0, 0], [-t - e, P + t + e, -t])     # Y→Z, Z→−Y
    posa(ids[4], I3, [0, 0, 0], [-t - e, -t, H + t])
    posa(ids[5], I3, [0, 0, 0], [-t - e, -t, -t - e])
    passo('ripiani sui traversi a 0, 600 e 1200')
    for iid, z in zip(ids[6:9], LIVELLI):
        posa(iid, I3, [0, 0, 0], [t, -t, z + t])
    passo('ante davanti, 3 mm dalla struttura e 3 mm tra loro: la destra è la sinistra capovolta')
    y_anta = -t - GIOCO_ANTA - BORDO_ANTA                       # faccia esterna dell'anta
    x0 = -t - e
    posa(ids[9], [[-1, 0, 0], [0, 0, 1], [0, 1, 0]], [larg_anta, 0, 0], [x0, y_anta, -t - e])           # X→−X, Y→Z, Z→Y
    posa(ids[10], [[1, 0, 0], [0, 0, 1], [0, -1, 0]], [0, 0, 0], [x0 + larg_anta + GIOCO_ANTA, y_anta, H + t + e])
    mostra(nuovo=True)
    return ids


def controlli():
    titolo('6. CONTROLLI: interferenze, distinta, tavole, STEP')
    inter = s.asm_interferences().get('interferences', [])
    passo('interferenze: ' + ('nessuna, i pezzi si toccano soltanto' if not inter else
                              '; '.join(x['label'] for x in inter)))
    from cad_engine import assembly as A
    righe = A.bom(s.asm, s.asm_parts)
    print('   DISTINTA')
    tot = 0
    for k, r in enumerate(righe, 1):
        print(f'   {k:2d}  {r["name"]:<20} {r["qty"]:>2} ×  {r["material"]:<6} sp. {r["thickness"] or "":<4} '
              f'{r["mass_tot"]:7.2f} kg')
        tot += r['mass_tot']
    print(f'       {"totale":<20}{"":>27}{tot:7.2f} kg')
    ok('save', str(D / 'armadio.steelcad-asm'))
    campi = {'azienda': 'Prova SteelCAD', 'disegnatore': 'SteelCAD', 'numero': 'AR-800-1800', 'revisione': 'A',
             'note': 'Vetrina: raggi e K di esempio', 'formato': 'A3'}
    r = ok('export_drawings', str(D / 'armadio_tavole.pdf'), campi, True)
    passo(r['message'])
    r = ok('asm_export_step', str(D / 'armadio.step'))
    passo(r.get('message') or 'STEP salvato')
    return inter, tot


def main():
    global DIRETTA
    if LIVE:
        spec = importlib.util.spec_from_file_location('vetrina_quadro', QUI / 'tools' / 'vetrina_quadro.py')
        vq = importlib.util.module_from_spec(spec)
        sys.argv = [sys.argv[0], str(D)]            # la vetrina del quadro legge gli argomenti: niente --live
        spec.loader.exec_module(vq)
        vq.D = D

        class Diretta(vq.Diretta):
            def apri(self):
                import glob
                import subprocess
                import webbrowser
                chrome = next(iter(glob.glob(r'C:\Program Files*\Google\Chrome\Application\chrome.exe')), None)
                if chrome:
                    subprocess.Popen([chrome, '--new-window', '--start-maximized', self.url])
                else:
                    webbrowser.open(self.url)
                print(f'Diretta su {self.url} - aspetto il browser...', flush=True)
                self.manda({'type': 'toast', 'text': 'Diretta SteelCAD: armadio 800 × 500 × 1800, costruito da zero'})
                time.sleep(2)
        DIRETTA = Diretta(5151)
        DIRETTA.apri()
    F = {'telaio': telaio(), **pannelli(), 'ripiano': ripiano()}
    F['anta'], larg, alt = anta()
    assieme(F, larg, alt)
    inter, kg = controlli()
    print(f'\nFatto in {time.time() - T0:.0f} s. File in {D}')
    if DIRETTA:
        mostra(key='0')
        DIRETTA.manda({'type': 'toast', 'text': f'Fatto: 11 pezzi, {kg:.0f} kg, '
                       + ('nessuna interferenza' if not inter else f'{len(inter)} interferenze')
                       + f'. Tavole PDF e STEP in {D}'})
        print('La pagina resta viva: chiudi questa finestra (Ctrl+C) quando hai finito di guardare.', flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
