"""Vetrina di SteelCAD: persiana a due ante in lamiera per un vano 1200 × 1400, costruita da zero.

    python tools/vetrina_persiana.py [cartella]          (di default Documenti/SteelCAD/persiana)
    python tools/vetrina_persiana.py --live [cartella]   in diretta: si apre Chrome e si vede crescere ogni pezzo

Telaio fisso a muro sp. 2 (cornice di battuta attorno al vano, aletta esterna), due ante a vassoio sp. 1,5 con
l'aletta verso il muro che batte sulla cornice, lamelle a 45° e battuta centrale (coprifilo) sull'anta destra.
Assieme, tavole PDF (con l'esploso) e file. Raggio e K-factor sono
valori di esempio (raggio = spessore, K 0,4): per la produzione vanno quelli della tua piegatrice.
"""
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('STEELCAD_HOME', __import__('tempfile').mkdtemp(prefix='steelcad_vetrina_'))

from app.service import Service  # noqa: E402

LIVE = '--live' in sys.argv
_arg = [a for a in sys.argv[1:] if not a.startswith('--')]
D = Path(_arg[0]) if _arg else Path(os.path.expanduser('~')) / 'Documents' / 'SteelCAD' / 'persiana'
D.mkdir(parents=True, exist_ok=True)
T0 = time.time()

# misure (esempio)
VANO_L, VANO_H = 1200.0, 1400.0       # luce del vano muro
SP_T, SP_A = 2.0, 1.5                 # spessori: telaio fisso, ante (lamelle e coprifilo come le ante)
BATTUTA, ALETTA_T = 50.0, 35.0        # telaio fisso: cornice su cui battono le ante, aletta esterna
STILE, PROF_A = 50.0, 30.0            # anta: larghezza del telaio davanti, profondità (aletta verso il muro)
GIOCO, GIOCO_C = 3.0, 4.0             # attorno alle ante, tra le due ante
LARG_LAM, PASSO, INCLINAZIONE = 36.0, 34.0, 45.0
COPRI = 40.0                          # battuta centrale (coprifilo) sull'anta destra

s = None
DIRETTA = None
SKETCH = [None]
PAUSA = {'passo': 1.4, 'comando': 0.15}


def mostra(nuovo=False, key=None):
    if DIRETTA:
        DIRETTA.manda({'type': 'refresh', 'sketch': SKETCH[0], 'nuovo': nuovo, 'key': key})
        time.sleep(PAUSA['comando'])


def avvisa(testo):
    if DIRETTA:
        DIRETTA.manda({'type': 'toast', 'text': testo})
        time.sleep(PAUSA['passo'])


def titolo(t):
    print(f'\n[{time.time() - T0:5.1f}s] {t}', flush=True)
    avvisa(t)


def passo(t):
    print(f'   · {t}', flush=True)
    avvisa(t[0].upper() + t[1:])


def ok(nome, *a):
    r = getattr(s, nome)(*a)
    if not r.get('ok'):
        raise SystemExit(f'\nERRORE {nome}{a}: {r.get("message")}')
    if DIRETTA and nome not in ('sketch_view', 'save', 'export_drawings'):
        if nome in ('sketch_on_face', 'sketch_on_flat'):
            SKETCH[0] = r['sketch']
        elif nome in ('create_from_sketch',):
            SKETCH[0] = None
        mostra(nuovo=nome in ('new_project', 'new_assembly'))
    return r


def servizio():
    return DIRETTA.svc if DIRETTA else Service()


def salva(nome):
    st = s.state()
    if st['errors']:
        raise SystemExit(f'{nome}: ' + '; '.join(e['message'] for e in st['errors']))
    p = D / f'{nome}.steelcad'
    ok('save', str(p))
    print(f'   = {nome}: sviluppo {[round(x, 1) for x in s.result.body.sheet.flat_size]}', flush=True)
    return p


def bordi(sid):
    v = s.sketch_view(sid)['sketch']
    xs, ys = [], []
    for ln in v['lines']:
        if ln['ref'] and not ln.get('xray') and not ln.get('piega'):
            xs += [ln['xa'][0], ln['xb'][0]]
            ys += [ln['xa'][1], ln['xb'][1]]
    return min(xs), min(ys), max(xs), max(ys)


def telaio():
    """Telaio fisso a muro: cornice attorno al vano (la battuta delle ante) e aletta esterna su cui stanno di fianco."""
    global s
    W, H = VANO_L + 2 * BATTUTA, VANO_H + 2 * BATTUTA
    titolo(f'Telaio fisso: lamiera sp. {SP_T:g}, {W:g} × {H:g} attorno al vano {VANO_L:g} × {VANO_H:g}')
    s = servizio()
    ok('new_project', 'lamiera', {'name': 'Telaio fisso', 'larghezza': W, 'profondita': H, 'spessore': SP_T,
                                  'raggio': SP_T, 'k': 0.4})
    passo(f'il vano: la cornice di {BATTUTA:g} è la battuta su cui chiudono le ante')
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    x0, y0, x1, y1 = bordi(sid)
    ok('sketch_add_rectangle', sid, [x0 + BATTUTA, y0 + BATTUTA], [x1 - BATTUTA, y1 - BATTUTA])
    ok('create_from_sketch', sid, 'cut', {})
    for lato, nome in (('L1', 'sotto'), ('L3', 'sopra'), ('L2', 'a destra'), ('L4', 'a sinistra')):
        passo(f'aletta esterna {nome}: {ALETTA_T:g} verso fuori')
        ok('add_flange', 'SM1', lato, {'length': str(ALETTA_T), 'angle': '90', 'direction': 'up', 'position': 'inside'})
    return salva('telaio_fisso')


def misure_ante():
    luce = VANO_L + 2 * BATTUTA - 2 * SP_T            # tra le alette del telaio fisso
    W = (luce - 2 * GIOCO - GIOCO_C) / 2
    H = VANO_H + 2 * BATTUTA - 2 * SP_T - 2 * GIOCO
    return W, H


def anta():
    """Un'anta: telaio a vassoio (stile davanti, aletta verso il muro che batte sulla cornice del telaio fisso)."""
    global s
    W, H = misure_ante()
    titolo(f'Anta: lamiera sp. {SP_A:g}, {W:g} × {H:g}, stile {STILE:g} e aletta di {PROF_A:g} verso il muro')
    s = servizio()
    ok('new_project', 'lamiera', {'name': 'Anta', 'larghezza': W, 'profondita': H, 'spessore': SP_A,
                                  'raggio': SP_A, 'k': 0.4})
    passo('la finestra dell’anta: dentro vanno le lamelle')
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    x0, y0, x1, y1 = bordi(sid)
    ok('sketch_add_rectangle', sid, [x0 + STILE, y0 + STILE], [x1 - STILE, y1 - STILE])
    ok('create_from_sketch', sid, 'cut', {})
    for lato, nome in (('L1', 'sotto'), ('L3', 'sopra'), ('L2', 'a destra'), ('L4', 'a sinistra')):
        passo(f'aletta {nome}: {PROF_A:g} verso il muro (batte sulla cornice del telaio fisso)')
        ok('add_flange', 'SM1', lato, {'length': str(PROF_A), 'angle': '90', 'direction': 'up', 'position': 'inside'})
    return salva('anta')


def lamella():
    global s
    W, _ = misure_ante()
    lung = W - 2 * SP_A - 2 * 1.0
    titolo(f'Lamella: lamiera sp. {SP_A:g}, {lung:g} × {LARG_LAM:g}')
    s = servizio()
    ok('new_project', 'lamiera', {'name': 'Lamella', 'larghezza': lung, 'profondita': LARG_LAM, 'spessore': SP_A,
                                  'raggio': SP_A, 'k': 0.4})
    return salva('lamella')


def coprifilo():
    global s
    _, H = misure_ante()
    titolo(f'Battuta centrale: coprifilo sp. {SP_A:g}, {COPRI:g} × {H:g}, sull’anta destra')
    s = servizio()
    ok('new_project', 'lamiera', {'name': 'Battuta centrale', 'larghezza': COPRI, 'profondita': H, 'spessore': SP_A,
                                  'raggio': SP_A, 'k': 0.4})
    return salva('battuta_centrale')


def assieme(f_telaio, f_anta, f_lamella, f_copri):
    """Tutto steso col muro sotto (z = 0): il telaio fisso sul muro, le ante girate con l'aletta verso il muro che batte
    sulla cornice, le lamelle dentro le ante, il coprifilo davanti sull'anta destra."""
    global s
    import numpy as np
    W, H = misure_ante()
    titolo('Assieme: telaio fisso, due ante con le lamelle e la battuta centrale')
    s = servizio()
    ok('new_assembly', 'Persiana a due ante')
    ok('save', str(D / 'persiana.steelcad-asm'))

    def metti(f, R, T, vedi=True):
        r = ok('asm_insert', str(f)) if vedi else s.asm_insert(str(f))
        i = s.asm.instances[-1]
        i['R'], i['T'] = np.array(R, dtype=float).tolist(), [float(x) for x in T]
        if vedi:
            s._asm_reload()
            s.scene_version += 1
            mostra()
        return i['id']
    I = np.eye(3)
    giu = np.diag([1.0, -1.0, -1.0])               # girata: l'aletta verso il muro
    t = metti(f_telaio, I, [0, 0, 0])
    s.asm.instance(t)['fixed'] = True
    passo('il telaio fisso sul muro: la cornice è la battuta, l’aletta tiene le ante di fianco')
    zf = SP_T + PROF_A + SP_A                       # la faccia davanti delle ante
    x_sx = SP_T + GIOCO
    x_dx = x_sx + W + GIOCO_C
    y0 = SP_T + GIOCO
    ante = []
    for nome, x in (('sinistra', x_sx), ('destra', x_dx)):
        ante.append(metti(f_anta, giu, [x, y0 + H, zf]))
        passo(f'anta {nome}: l’aletta batte sulla cornice, gioco {GIOCO:g} attorno')
    # le lamelle: dentro ogni anta, inclinate (davanti in basso, verso il muro in alto), passo costante
    a = math.radians(INCLINAZIONE)
    R = np.array([[1, 0, 0], [0, math.cos(a), math.sin(a)], [0, -math.sin(a), math.cos(a)]])
    y_da, y_a = y0 + STILE * 0.6, y0 + H - STILE * 0.6 - LARG_LAM * math.cos(a)
    n = int((y_a - y_da) // PASSO) + 1
    passo(f'{2 * n} lamelle a {INCLINAZIONE:g}°, passo {PASSO:g}')
    for x, an in zip((x_sx, x_dx), ante):
        for k in range(n):
            lam = metti(f_lamella, R, [x + SP_A + 1.0, y_da + k * PASSO, zf - SP_A - SP_A * math.cos(a) - 0.5], vedi=(k == n - 1))
            s.asm_add_mate('blocca', {'inst': an}, {'inst': lam})      # saldata nell'anta: si muove con lei
    cp = metti(f_copri, I, [x_dx - COPRI / 2 - GIOCO_C / 2, y0, zf])
    s.asm_add_mate('blocca', {'inst': ante[1]}, {'inst': cp})
    passo(f'la battuta centrale: copre la fessura di {GIOCO_C:g} e si sovrappone all’anta sinistra')
    r = s.asm_interferences()
    passo(r.get('message') or 'interferenze controllate')
    ok('save', str(D / 'persiana.steelcad-asm'))
    return r


def tavole():
    titolo('Tavole: assieme, esploso, telaio e lamella con gli sviluppi')
    campi = {'azienda': 'Prova SteelCAD', 'disegnatore': 'SteelCAD', 'numero': 'PER-1200-1400', 'revisione': 'A',
             'note': 'Esempio: raggi e K di esempio', 'formato': 'A3'}
    r = ok('export_drawings', str(D / 'persiana_tavole.pdf'), campi, True)
    passo(r['message'])


class Diretta:
    """Server dell'interfaccia nello stesso processo, sullo stesso servizio (come le altre vetrine)."""

    def __init__(self, porta=5151):
        import threading
        from app.dev_server import ApiProva, crea_server
        diretta = self

        class ApiLive(ApiProva):
            def live_next(self):
                return diretta._prossimi()

            def live_ack(self, n):
                with diretta.cv:
                    diretta.visti = max(diretta.visti, int(n))
                    diretta.cv.notify_all()
                return {'ok': True}

        self.api = ApiLive(D)
        self.svc = self.api._svc
        self.cv = threading.Condition()
        self.coda, self.n, self.visti, self.fine = [], 0, 0, False
        self.srv = crea_server(self.api, porta)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{porta}/?dev&live'

    def _prossimi(self):
        with self.cv:
            self.cv.wait_for(lambda: self.coda or self.fine, timeout=10)
            ev, self.coda = self.coda, []
            return {'ok': bool(ev) or self.fine, 'events': ev, 'n': self.n, 'end': self.fine and not ev}

    def manda(self, ev, aspetta=True):
        with self.cv:
            self.n += 1
            n = self.n
            self.coda.append(ev)
            self.cv.notify_all()
            if aspetta and not self.cv.wait_for(lambda: self.visti >= n, timeout=300):
                raise SystemExit('Il browser non risponde più: diretta interrotta.')

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
        self.manda({'type': 'toast', 'text': 'Diretta SteelCAD: persiana a due ante per vano 1200 × 1400, costruita da zero'})
        time.sleep(2)


def main():
    global DIRETTA
    if LIVE:
        DIRETTA = Diretta()
        DIRETTA.apri()
    ft = telaio()
    fa = anta()
    fl = lamella()
    fc = coprifilo()
    assieme(ft, fa, fl, fc)
    tavole()
    print(f'\nFatto in {time.time() - T0:.0f} s. File in {D}')
    if DIRETTA:
        mostra(key='0')
        DIRETTA.manda({'type': 'toast', 'text': f'Fatto: telaio fisso, due ante con le lamelle e la battuta centrale; tavole PDF in {D}'})
        print('La pagina resta viva: chiudi questa finestra (Ctrl+C) quando hai finito di guardare.', flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
