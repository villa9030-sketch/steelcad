"""«Appoggia» (03/11, Stefano: appoggiare e centrare in un comando solo).

Clic su una faccia del pezzo da muovere, poi su quella del pezzo fermo: il pezzo si appoggia SENZA capovolgersi né
entrare nell'altro e parte al centro della faccia. Qui solo i conti: dove va il pezzo e con quali facce fare gli
accoppiamenti veri (faccia su faccia per l'appoggio, in mezzo o distanza per la posizione sulla faccia), così se un
pezzo cambia l'assieme lo rimette a posto da solo col risolutore di sempre.

La regola contro il capovolgimento: se la faccia cliccata del pezzo da muovere guarda dalla stessa parte di quella
del pezzo fermo (si clicca quella che si vede, sopra), il pezzo NON si gira: appoggia con la sua faccia più in fondo
dalla parte opposta (la faccia sotto). Se invece la faccia cliccata guarda già verso l'altro pezzo (si è girata la
vista e cliccata quella sotto), appoggia quella. In ogni caso la faccia d'appoggio è quella più esterna del pezzo da
quella parte: il pezzo resta fuori dall'altro.
"""
from __future__ import annotations

import math

import numpy as np

from . import assembly as A

TOL = 0.02                           # mm: una faccia «sta sull'estremo» del pezzo
PARALLELA = 0.9999

# i nomi dei lati come li dice l'officina, per la direzione del mondo verso cui stanno
_LATI = (((-1, 0, 0), 'sinistra'), ((1, 0, 0), 'destra'), ((0, -1, 0), 'davanti'), ((0, 1, 0), 'dietro'),
         ((0, 0, -1), 'sotto'), ((0, 0, 1), 'sopra'))


def nome_lato(v) -> str:
    v = np.asarray(v, dtype=float)
    return max(_LATI, key=lambda x: float(np.dot(v, x[0])))[1]


class _Pezzo:
    """Le facce di un pezzo con i punti della maglia (per gli estremi), nelle coordinate del pezzo."""

    def __init__(self, part):
        from .topology.naming import _faces_of
        self.part = part
        self.facce = list(_faces_of(part.shape))
        m = A.part_mesh(part)
        P = np.array(m['positions'], dtype=float).reshape(-1, 3)
        idx = np.array(m['indices'], dtype=int)
        self.punti = P
        self.per_faccia = {}
        for f in m['faces']:
            sel = idx[f['start']:f['start'] + f['count']]
            self.per_faccia[f['index']] = P[np.unique(sel)] if len(sel) else np.zeros((0, 3))
        self._info = {}

    def info(self, k):
        if k not in self._info:
            self._info[k] = A.face_info(self.part, self.facce[k])
        return self._info[k]

    def piane(self):
        for k in range(len(self.facce)):
            i = self.info(k)
            if i['kind'] == 'piana':
                yield k, i

    def vicine(self, k) -> list:
        """Le facce che toccano la faccia k lungo un suo spigolo."""
        from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as MappaListe
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        from OCP.TopExp import TopExp, TopExp_Explorer
        if getattr(self, '_anc', None) is None:
            self._anc = MappaListe()
            TopExp.MapShapesAndAncestors_s(self.part.shape, TopAbs_EDGE, TopAbs_FACE, self._anc)
        out = set()
        ex = TopExp_Explorer(self.facce[k], TopAbs_EDGE)
        while ex.More():
            i = self._anc.FindIndex(ex.Current())
            if i:
                for g in self._anc.FindFromIndex(i):
                    for j, f in enumerate(self.facce):
                        if j != k and f.IsSame(g):
                            out.add(j)
            ex.Next()
        return sorted(out)

    def estremi(self, d, punti=None):
        q = (self.punti if punti is None else punti) @ d
        return float(q.min()), float(q.max())

    def faccia_estrema(self, d, verso, vicino=None):
        """La faccia piana più esterna del pezzo lungo d: verso=-1 quella in fondo (normale -d), +1 in cima (normale
        +d). Se ce n'è più d'una a quel livello, quella più vicina al punto «vicino»."""
        lo, hi = self.estremi(d)
        livello = lo if verso < 0 else hi
        cand = []
        for k, i in self.piane():
            n = np.array(i['n'])
            if np.dot(n, d) * verso < PARALLELA:
                continue
            pts = self.per_faccia.get(k)
            if pts is None or not len(pts) or abs(float((pts @ d).mean()) - livello) > TOL:
                continue
            c = pts.mean(axis=0)
            cand.append((0 if vicino is None else float(np.linalg.norm(A._perp(c - vicino, d))), -len(pts), k))
        return min(cand)[2] if cand else None


_CACHE: dict = {}


def _pezzo(part) -> _Pezzo:
    """Lo stesso pezzo tra un'anteprima e l'altra (ogni scelta nel pannello rifà i conti): le facce si leggono una volta."""
    c = _CACHE.get(id(part))
    if c is None or c.part is not part:
        if len(_CACHE) > 64:
            _CACHE.clear()
        c = _CACHE[id(part)] = _Pezzo(part)
    return c


def _assi_della_faccia(pa: _Pezzo, ka: int, n_loc):
    """Le due direzioni sulla faccia del pezzo fermo (nelle sue coordinate): dai lati che la bordano, se no dagli
    assi del pezzo."""
    cand = []
    for j in pa.vicine(ka):
        i = pa.info(j)
        if i['kind'] == 'piana' and abs(np.dot(i['n'], n_loc)) < 1e-6:
            cand.append(np.array(i['n'], dtype=float))
    for e in np.eye(3):
        cand.append(e)
    for c in cand:
        u = A._perp(c, n_loc)
        if np.linalg.norm(u) > 0.5:
            u = u / np.linalg.norm(u)
            return u, np.cross(n_loc, u)
    raise A.AssemblyError('Non trovo le direzioni di questa faccia.')


def _bordi(pa: _Pezzo, ka: int, u):
    """I due lati della faccia del pezzo fermo lungo u (le facce piane che la bordano, a squadra): (basso, alto)
    come indici di faccia, o None se da quella parte non c'è una faccia piana."""
    pts = pa.per_faccia[ka]
    lo, hi = pa.estremi(u, pts)
    basso = alto = None
    for j in pa.vicine(ka):
        i = pa.info(j)
        if i['kind'] != 'piana' or abs(abs(float(np.dot(i['n'], u))) - 1) > 1e-4:
            continue
        q = float(np.dot(i['p'], u))
        if abs(q - lo) < TOL:
            basso = j
        elif abs(q - hi) < TOL:
            alto = j
    return lo, hi, basso, alto


def _piane_lungo(p: _Pezzo, d):
    """Le facce piane del pezzo a squadra con la direzione d: [(posizione lungo d, indice)]."""
    out = []
    for k, i in p.piane():
        if abs(float(np.dot(i['n'], d))) > PARALLELA:
            pts = p.per_faccia.get(k)
            q = float((pts @ d).mean()) if pts is not None and len(pts) else float(np.dot(i['p'], d))
            out.append((q, k))
    return out


def _ripiego(p: _Pezzo, d, lo, hi, basso, alto):
    """Quando un lato non ha una faccia piana proprio sul bordo (03/11: i pannelli piegati, dove la faccia finisce
    in una piega): le facce piane a squadra più vicine ai bordi (l'interno o l'esterno delle ali, i fianchi), così
    l'accoppiamento tiene lo stesso. Per «al centro» una coppia messa simmetrica rispetto al centro se c'è (le due
    ali interne di una vaschetta): se il pezzo cambia, resta al centro davvero. Ritorna (basso, alto, coppia)."""
    cand = _piane_lungo(p, d)
    if not cand:
        return basso, alto, (basso, alto) if None not in (basso, alto) else None
    b = basso if basso is not None else min(cand, key=lambda x: (abs(x[0] - lo), x[1]))[1]
    a = alto if alto is not None else min(cand, key=lambda x: (abs(x[0] - hi), x[1]))[1]
    if basso is not None and alto is not None:
        return b, a, (b, a)
    c = (lo + hi) / 2
    coppie = [(round(abs((q1 + q2) / 2 - c), 2), round(abs(q1 - lo) + abs(q2 - hi), 2), k1, k2)
              for q1, k1 in cand for q2, k2 in cand if q1 <= q2 + 1e-9]
    _, _, k1, k2 = min(coppie)
    return b, a, (k1, k2)


def appoggia(part_a, Ra, Ta, ka: int, part_b, Rb, Tb, kb: int, opz: dict | None = None) -> dict:
    """Dove va il pezzo b (R, T) appoggiato sulla faccia ka del pezzo a, e le facce per gli accoppiamenti.

    opz: capovolgi (bool), gira (quanti quarti di giro attorno alla normale), e per le due direzioni della faccia
    'u' e 'v': {'modo': 'centro' | 'basso' | 'alto', 'mm': distanza dal bordo}. Ritorna R, T, la faccia d'appoggio
    (kb2), le direzioni con i nomi dei lati e, per ogni direzione, le facce da accoppiare (o None)."""
    opz = opz or {}
    Ra, Ta, Rb, Tb = (np.array(x, dtype=float) for x in (Ra, Ta, Rb, Tb))
    pa, pb = _pezzo(part_a), _pezzo(part_b)
    fa, fb = pa.info(ka), pb.info(kb)
    if fa['kind'] != 'piana' or fb['kind'] != 'piana':
        raise A.AssemblyError('Appoggia vuole due facce piane: una del pezzo da mettere, una di quello fermo. '
                              'Per un tubo su una faccia usa «Tangente».')
    na_loc = np.array(fa['n'], dtype=float)
    nA = Ra @ na_loc
    pA = Ra @ np.array(fa['p'], dtype=float) + Ta
    nb_loc = np.array(fb['n'], dtype=float)
    # il «su» del pezzo da muovere (nelle sue coordinate): la faccia cliccata se guarda come quella ferma
    su = nb_loc if float(np.dot(Rb @ nb_loc, nA)) > 0.01 else -nb_loc
    if opz.get('capovolgi'):
        su = -su
    centro_b = pb.per_faccia[kb].mean(axis=0) if len(pb.per_faccia.get(kb, [])) else np.array(fb['p'])
    kb2 = pb.faccia_estrema(su, -1, centro_b)
    if kb2 is None:
        raise A.AssemblyError('Da quella parte il pezzo non ha una faccia piana su cui appoggiare: prova «Capovolgi», '
                              'o per un tubo usa «Tangente».')
    # rotazione: il «su» del pezzo va sulla normale della faccia ferma, girando il meno possibile
    R1 = A._rot_min(Rb @ su, nA) @ Rb
    # le direzioni della faccia ferma (nel mondo), in ordine come le pensa l'officina: prima sinistra/destra
    u_loc, v_loc = _assi_della_faccia(pa, ka, na_loc)
    U, V = Ra @ u_loc, Ra @ v_loc
    if abs(U[0]) < abs(V[0]) or (abs(abs(U[0]) - abs(V[0])) < 1e-6 and abs(U[1]) < abs(V[1])):
        U, V, u_loc, v_loc = V, U, v_loc, u_loc
    if U[np.argmax(np.abs(U))] < 0:
        U, u_loc = -U, -u_loc
    if V[np.argmax(np.abs(V))] < 0:
        V, v_loc = -V, -v_loc
    # il giro attorno alla normale: a squadra con i lati della faccia ferma (il quarto di giro più vicino), più quelli
    # chiesti con «Gira di 90°»
    dirs_b = []
    for k, i in pb.piane():
        w = np.array(i['n'], dtype=float)
        if abs(np.dot(w, su)) < 1e-6:
            dirs_b.append(w)
    if not dirs_b:
        dirs_b = [A._perp(e, su) for e in np.eye(3) if np.linalg.norm(A._perp(e, su)) > 0.5]
    w0 = R1 @ dirs_b[0]
    w0 = w0 / np.linalg.norm(w0)
    ang = math.atan2(float(np.dot(np.cross(w0, U), nA)), float(np.dot(w0, U)))
    ang = ang - round(ang / (math.pi / 2)) * (math.pi / 2) + (math.pi / 2) * int(opz.get('gira') or 0)   # il resto: a squadra girando poco
    R = A._rot_axis(nA, ang) @ R1
    # dove sta il pezzo, ruotato, prima di spostarlo: estremi lungo U, V e la faccia d'appoggio lungo nA
    Pb = pb.punti @ R.T
    pc = R @ np.array(pb.info(kb2)['p'], dtype=float)
    T = np.zeros(3) + nA * float(np.dot(nA, pA) - np.dot(nA, pc))
    dirs = {}
    for chiave, Dw, Dloc in (('u', U, u_loc), ('v', V, v_loc)):
        lo_a, hi_a, basso, alto = _bordi(pa, ka, Dloc)
        lo_a += float(np.dot(Dw, Ta))
        hi_a += float(np.dot(Dw, Ta))
        q = Pb @ Dw
        lo_b, hi_b = float(q.min()), float(q.max())
        scelta = (opz.get(chiave) or {})
        modo = scelta.get('modo') or 'centro'
        try:
            mm = float(str(scelta.get('mm') if scelta.get('mm') not in (None, '') else 0).replace(',', '.'))
        except ValueError:
            raise A.AssemblyError('Scrivi la distanza dal bordo in mm (un numero).') from None
        if modo == 'basso':
            sp = lo_a + mm - lo_b
        elif modo == 'alto':
            sp = hi_a - mm - hi_b
        else:
            modo = 'centro'
            sp = (lo_a + hi_a) / 2 - (lo_b + hi_b) / 2
        T = T + Dw * sp
        # le facce del pezzo che si muove agli estremi lungo questa direzione (nelle sue coordinate)
        d_loc = R.T @ Dw
        fb_basso = pb.faccia_estrema(d_loc, -1)
        fb_alto = pb.faccia_estrema(d_loc, +1)
        esatti = None not in (basso, alto, fb_basso, fb_alto)
        lo_al, hi_al = pa.estremi(Dloc, pa.per_faccia[ka])
        basso, alto, coppia_a = _ripiego(pa, Dloc, lo_al, hi_al, basso, alto)
        lo_bl, hi_bl = pb.estremi(d_loc)
        fb_basso, fb_alto, coppia_b = _ripiego(pb, d_loc, lo_bl, hi_bl, fb_basso, fb_alto)
        dirs[chiave] = {'modo': modo, 'mm': mm, 'dir': Dw.tolist(), 'basso': nome_lato(-Dw), 'alto': nome_lato(Dw),
                        'lungo_a': hi_a - lo_a, 'lungo_b': hi_b - lo_b, 'esatti': esatti,
                        'fermo': (basso, alto), 'mobile': (fb_basso, fb_alto),
                        'coppia_fermo': coppia_a, 'coppia_mobile': coppia_b,
                        # distanze dai due bordi, a pezzo messo (per il pannello)
                        'da_basso': lo_b + sp - lo_a, 'da_alto': hi_a - (hi_b + sp)}
    return {'R': R, 'T': T, 'kb2': kb2, 'su': su.tolist(), 'dirs': dirs}


# ------------------------------------------------------------------ mai dentro l'altro (03/11, secondo giro)
def _posato(part, R, T):
    return A.placed_shape(part, np.asarray(R, dtype=float).tolist(), np.asarray(T, dtype=float).tolist())


def _comune(sa, sb):
    """Il pezzo in comune tra due forme già messe (None se non si toccano nemmeno come ingombro)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    ba, bb = sa.bounding_box(), sb.bounding_box()
    if (ba.max.X < bb.min.X or bb.max.X < ba.min.X or ba.max.Y < bb.min.Y or bb.max.Y < ba.min.Y
            or ba.max.Z < bb.min.Z or bb.max.Z < ba.min.Z):
        return None
    try:
        return sa._bool_op((sa,), (sb,), BRepAlgoAPI_Common())
    except Exception:  # noqa: BLE001 - se l'operazione non riesce: come se non entrasse
        return None


DENTRO = 1.0                    # mm³: sotto questo è solo il contatto tra le due facce


def entra(part_a, Ra, Ta, part_b, R, T) -> float:
    """Quanto il pezzo b, messo in (R, T), entra nel pezzo a (mm³)."""
    c = _comune(_posato(part_a, Ra, Ta), _posato(part_b, R, T))
    try:
        return float(c.volume) if c is not None else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def _estremi_forma(sh, n):
    n = np.asarray(n, dtype=float)
    if np.max(np.abs(n)) > 0.99999:                 # lungo un asse: basta l'ingombro
        b = sh.bounding_box()
        k = int(np.argmax(np.abs(n)))
        lo, hi = (b.min.X, b.min.Y, b.min.Z)[k], (b.max.X, b.max.Y, b.max.Z)[k]
        return (lo, hi) if n[k] > 0 else (-hi, -lo)
    v, _ = sh.tessellate(0.05)
    q = np.array([[p.X, p.Y, p.Z] for p in v]) @ n
    return float(q.min()), float(q.max())


def _livelli(p: _Pezzo, R, T, n, verso):
    """I livelli lungo n delle facce piane del pezzo messo in (R, T) che guardano come n (verso=+1) o contro (-1)."""
    R, T = np.asarray(R, dtype=float), np.asarray(T, dtype=float)
    out = set()
    for k, i in p.piane():
        if float(np.dot(R @ np.array(i['n']), n)) * verso > PARALLELA:
            pts = p.per_faccia.get(k)
            if pts is not None and len(pts):
                out.add(round(float(((pts @ R.T + T) @ n).mean()), 4))
    return sorted(out)


def solleva(part_a, Ra, Ta, part_b, R, T, n, giri: int = 8):
    """Se il pezzo b entra nell'a, lo alza lungo n (la normale della faccia su cui appoggia) finché non entra più:
    si posa su quello che tocca prima, come quando lo si appoggia davvero (una piastra più grande del fondo di una
    vaschetta resta sui bordi). Prima prova le altezze dove una faccia del pezzo va a toccarne una dell'altro (i bordi
    della vaschetta sotto la piastra), dalla più bassa; se nessuna va, sale a passi. Ritorna (T nuovo, di quanto l'ha
    alzato, quanto entra ancora)."""
    T = np.array(T, dtype=float)
    n = np.asarray(n, dtype=float)
    sa = _posato(part_a, Ra, Ta)

    def dentro(TT):
        c = _comune(sa, _posato(part_b, R, TT))
        try:
            return (float(c.volume) if c is not None else 0.0), c
        except Exception:  # noqa: BLE001
            return 0.0, None
    v, c = dentro(T)
    if v <= DENTRO:
        return T, 0.0, v
    su = _livelli(_pezzo(part_a), Ra, Ta, n, +1)
    giu = _livelli(_pezzo(part_b), R, T, n, -1)
    for h in sorted({round(la - lb, 4) for la in su for lb in giu if la - lb > 1e-6})[:12]:
        vv, _ = dentro(T + n * h)
        if vv <= DENTRO:
            return T + n * h, h, vv
    alzato = 0.0
    for _ in range(giri):
        lo, hi = _estremi_forma(c, n)
        passo = max(hi - lo, 0.01)
        T = T + n * passo
        alzato += passo
        v, c = dentro(T)
        if v <= DENTRO:
            break
    return T, alzato, v


def _contatto(pa: _Pezzo, Ra, Ta, pb: _Pezzo, R, T, n):
    """Dopo averlo alzato: la faccia del pezzo fermo (che guarda come n) e quella del pezzo mosso (che guarda
    contro) allo stesso livello, per l'accoppiamento faccia su faccia (i bordi della vaschetta sotto la piastra)."""
    Ra, Ta, R, T = (np.asarray(x, dtype=float) for x in (Ra, Ta, R, T))
    sotto = {}
    for k, i in pa.piane():
        if float(np.dot(Ra @ np.array(i['n']), n)) > PARALLELA:
            pts = pa.per_faccia.get(k)
            if pts is not None and len(pts):
                sotto[k] = float(((pts @ Ra.T + Ta) @ n).max())
    for k, i in pb.piane():
        if float(np.dot(R @ np.array(i['n']), n)) < -PARALLELA:
            pts = pb.per_faccia.get(k)
            if pts is None or not len(pts):
                continue
            liv = float(((pts @ R.T + T) @ n).min())
            for ka, la in sorted(sotto.items(), key=lambda x: x[0]):
                if abs(la - liv) < 0.05:
                    return ka, k
    return None


# le prove quando il pezzo entra: girato, capovolto, tutti e due (in quest'ordine)
_ALTERNATIVE = (({'gira': 1}, 'Gira di 90°'), ({'capovolgi': True}, 'Capovolgi'),
                ({'gira': 1, 'capovolgi': True}, 'Capovolgi e gira di 90°'))


def _con(opz: dict, cambio: dict) -> dict:
    o = {k: (dict(v) if isinstance(v, dict) else v) for k, v in (opz or {}).items()}
    o['gira'] = (int(o.get('gira') or 0) + int(cambio.get('gira') or 0)) % 4
    if cambio.get('capovolgi'):
        o['capovolgi'] = not o.get('capovolgi')
    o.pop('auto', None)
    return o


def appoggia_senza_entrare(part_a, Ra, Ta, ka: int, part_b, Rb, Tb, kb: int, opz: dict | None = None) -> dict:
    """Come appoggia(), ma il pezzo non entra mai nell'altro (03/11, Stefano). Se così entra (una faccia interna,
    una vaschetta più piccola del pezzo):
    - alla prima prova (opz['auto']) prova da solo a girarlo / capovolgerlo e tiene il primo modo in cui ci sta
      ('scelto': le opzioni usate, 'cambio': cosa ha fatto, per il pannello);
    - se no lo alza finché si posa su quello che tocca ('alzato': di quanto, 'contatto': le due facce che si
      toccano) e dice quali modi lo farebbero stare giù ('proposte': [{'testo', 'opz'}])."""
    opz = dict(opz or {})
    auto = bool(opz.pop('auto', False))
    r = appoggia(part_a, Ra, Ta, ka, part_b, Rb, Tb, kb, opz)
    r.update(dentro=0.0, alzato=0.0, contatto=None, proposte=[], scelto=None, cambio=None)
    if entra(part_a, Ra, Ta, part_b, r['R'], r['T']) <= DENTRO:
        return r
    puliti = []
    for cambio, testo in _ALTERNATIVE:
        o = _con(opz, cambio)
        try:
            r2 = appoggia(part_a, Ra, Ta, ka, part_b, Rb, Tb, kb, o)
        except A.AssemblyError:
            continue
        if entra(part_a, Ra, Ta, part_b, r2['R'], r2['T']) <= DENTRO:
            if auto:
                r2.update(dentro=0.0, alzato=0.0, contatto=None, proposte=[], scelto=o, cambio=testo)
                return r2
            puliti.append({'testo': testo, 'opz': o})
    n = np.asarray(Ra, dtype=float) @ np.array(_pezzo(part_a).info(ka)['n'], dtype=float)
    T, alzato, dentro = solleva(part_a, Ra, Ta, part_b, r['R'], r['T'], n)
    r.update(T=T, alzato=alzato, dentro=dentro, proposte=puliti,
             contatto=_contatto(_pezzo(part_a), Ra, Ta, _pezzo(part_b), r['R'], T, n) if dentro <= DENTRO else None)
    return r
