"""Taglio di testa inclinato (a 45° per le cornici e i cassoni a quattro lati).

Un profilo di lamiera piegata (tutte le pieghe parallele alla sua lunghezza) si taglia alle teste con un piano unico
inclinato: il piano passa per lo spigolo esterno della testa (la faccia esterna del fondo) e scende verso
l'interno con l'angolo scelto. Tutte le facce e tutte le pieghe sono tagliate dallo stesso piano, quindi due pezzi
tagliati così combaciano davvero (21/10, il cassone: a mano, faccia per faccia sullo sviluppo, i tagli non stavano
su un piano e gli accoppiamenti non chiudevano per qualche decimo).

Il laser taglia a 90° sulla lamiera: dove la lamiera è di traverso al piano (il fondo, gli orli) si taglia al punto
più lontano dalla testa tra le due facce, così niente esce dal piano e non tocca il pezzo accanto. Sulle pareti
che stanno di taglio al piano il taglio coincide col piano. Il gioco di saldatura scritto è il totale tra i due
pezzi: ognuno si accorcia della metà (misurata perpendicolare al piano).

Si calcola sullo sviluppo: per ogni punto dello sviluppo si trova dov'è nel pezzo piegato (faccia esterna e
interna; nelle pieghe sull'arco), da lì la sua altezza sopra il fondo, e la linea di taglio è
x = testa − altezza · tan(angolo) − gioco/2 / cos(angolo). Il contorno da togliere passa poi dal taglio sullo
sviluppo di sempre (che avvolge i pezzi sulle pieghe).
"""
from __future__ import annotations

import math

import build123d as bd

from ..errors import FeatureError
from ..expressions import evaluate

ESTREMI = {'fine': 'alla fine', 'inizio': 'all’inizio', 'entrambe': 'alle due teste'}
VERSI = {'fuori': 'il fondo è il lato esterno (le pieghe vanno verso l’interno)',
         'dentro': 'il fondo è il lato interno (le pieghe vanno verso l’esterno)'}


def _num(fdef, key, ctx, cosa, fid, default):
    v = fdef.get(key)
    if v is None or v == '':
        return default
    return evaluate(v, ctx.params, what=f'{cosa} del taglio di testa {fid}')


def _due_punti(p, data, t):
    """I punti del pezzo piegato (faccia esterna, faccia interna) che nello sviluppo stanno in p."""
    for g in sorted(data.flanges, key=lambda g: -g.depth):
        u = (p - g.F0).dot(g.fx)
        sf = (p - g.F0).dot(g.fn) - g.off
        b = g.bend
        th = math.radians(b.angle)
        r, R = b.r, b.r + t
        if -1e-9 <= sf <= b.ba + 1e-9 and b.ba > 1e-9:
            ph = sf / b.ba * th
            return [g.p(u, g.off + rho * math.sin(ph), R - rho * math.cos(ph)) for rho in (R, r)]
        if b.ba < sf <= b.ba + g.lf + 1e-6:
            d = (math.cos(th), math.sin(th))
            dist = sf - b.ba
            return [g.p(u, q[0] + dist * d[0], q[1] + dist * d[1])
                    for q in ((g.off + R * math.sin(th), R - R * math.cos(th)),
                              (g.off + r * math.sin(th), R - r * math.cos(th)))]
    g = next(g for g in data.flanges if g.depth == 0)
    u = (p - g.F0).dot(g.fx)
    s = (p - g.F0).dot(g.fn)
    return [g.p(u, s, 0), g.p(u, s, t)]


def linee_di_taglio(data, angolo: float, gioco: float, estremi: str, verso: str = 'fuori'):
    """I contorni da togliere sullo sviluppo (facce nel piano dello sviluppo), uno per testa."""
    from . import _orienta
    t = data.thickness
    radici = [g for g in data.flanges if g.depth == 0 and hasattr(g, 'F0')]
    if not radici:
        raise FeatureError('Il taglio di testa serve su una lamiera piegata: prima fai le pieghe lungo il profilo.')
    e = radici[0].fx.normalized()                    # la lunghezza del profilo, nello sviluppo
    for g in data.flanges:
        if hasattr(g, 'fx') and abs(abs(g.fx.normalized().dot(e)) - 1) > 1e-6:
            raise FeatureError(f'Il taglio di testa vuole tutte le pieghe parallele alla lunghezza del profilo: la '
                               f'piega {g.fid} va di traverso.')
    N = data.plane.z_dir
    w = N.cross(e).normalized()                      # di traverso, nello sviluppo
    H = radici[0].zf.normalized()                    # verso dove salgono le pieghe del fondo
    O3 = radici[0].p(0, 0, 0)                        # sulla faccia esterna del fondo
    vertici = [bd.Vector(v) for v in data.flat.vertices()] or [data.flat.center()]
    xs = [v.dot(e) for v in vertici]
    ws = [v.dot(w) for v in vertici]
    x_lo, x_hi, w_lo, w_hi = min(xs), max(xs), min(ws), max(ws)
    z0 = data.flat.center().dot(N)
    xm = (x_lo + x_hi) / 2

    def punto(x, wv):
        return e * x + w * wv + N * z0

    # dove cambia la forma della sezione: inizio e fine di ogni piega (fitta sull'arco) e di ogni tratto dritto
    tagli = {w_lo, w_hi}
    for g in data.flanges:
        if not hasattr(g, 'F0'):
            continue
        for s_ in [g.off + g.bend.ba * i / 24 for i in range(25)] + [g.off + g.bend.ba + g.lf]:
            wv = g.fp(0, s_).dot(w)
            if w_lo - 1e-6 <= wv <= w_hi + 1e-6:
                tagli.add(wv)
    ordinati = sorted(tagli)
    altezze = []
    for wv in ordinati:
        pts = _due_punti(punto(xm, wv), data, t)
        hh = [(q - O3).dot(H) for q in pts]
        altezze.append(hh)
    if verso == 'dentro':
        cima = max(max(h) for h in altezze)
        altezze = [[cima - x for x in h] for h in altezze]
    tg = math.tan(math.radians(angolo))
    meta = gioco / 2 / math.cos(math.radians(angolo))
    fuori = 10 + t
    contorni = []
    for lato in (['inizio', 'fine'] if estremi == 'entrambe' else [estremi]):
        linea = []
        for wv, h in zip(ordinati, altezze):
            rientro = max(h) * tg + meta
            linea.append((x_hi - rientro) if lato == 'fine' else (x_lo + rientro))
        x_oltre = x_hi + fuori if lato == 'fine' else x_lo - fuori        # fuori dalla lamiera, oltre la testa
        giro = ([punto(linea[0], w_lo - fuori)] + [punto(x, wv) for x, wv in zip(linea, ordinati)]
                + [punto(linea[-1], w_hi + fuori), punto(x_oltre, w_hi + fuori), punto(x_oltre, w_lo - fuori)])
        pulito = [giro[0]]
        for q in giro[1:]:
            if (q - pulito[-1]).length > 1e-7:
                pulito.append(q)
        contorni.append(_orienta(bd.Face(bd.Wire.make_polygon(pulito, close=True)), data.plane))
    return contorni


def build_end_miter(fdef: dict, ctx):
    from . import _cut_from_flat
    fid = fdef['id']
    body = ctx.body
    data = getattr(body, 'sheet', None) if body is not None else None
    if data is None:
        raise FeatureError('Il taglio di testa va fatto su una lamiera piegata.', feature=fid)
    angolo = _num(fdef, 'angle', ctx, 'l’angolo', fid, 45)
    gioco = _num(fdef, 'gap', ctx, 'il gioco', fid, 0)
    if not 0 < angolo < 80:
        raise FeatureError(f'L’angolo del taglio di testa va tra 0 e 80° (scritto {angolo}).', feature=fid)
    if gioco < 0:
        raise FeatureError('Il gioco di saldatura non può essere negativo.', feature=fid)
    estremi = fdef.get('end', 'entrambe')
    if estremi not in ESTREMI:
        raise FeatureError(f'Testa «{estremi}» sconosciuta: inizio, fine o entrambe.', feature=fid)
    verso = fdef.get('side', 'fuori')
    if verso not in VERSI:
        raise FeatureError(f'Verso «{verso}» sconosciuto.', feature=fid)
    try:
        contorni = linee_di_taglio(data, angolo, gioco, estremi, verso)
    except FeatureError as ex:
        raise FeatureError(ex.message, feature=fid) from None
    return _cut_from_flat(fdef, body, data, contorni, data.thickness)
