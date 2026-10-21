"""Libreria dei pezzi commerciali: viteria e rivetti con le misure delle norme, fatti con i comandi di SteelCAD la
prima volta che servono e salvati in Documenti/SteelCAD/Libreria (poi si riusano). Ogni pezzo è già «da acquistare»
con la descrizione completa: in distinta va tra gli acquisti, niente DXF.

Misure (mm), dai cataloghi delle norme:
- vite TCEI ISO 4762: testa Ø dk, alta k, esagono incassato s;
- vite TE ISO 4017: esagono s, testa alta k;
- vite TSPEI ISO 10642 (testa svasata piana a 90°, esagono incassato): testa Ø dk, alta k, esagono s; la lunghezza
  nominale comprende la testa;
- dado esagonale ISO 4032: chiave s, alto m;
- rondella piana ISO 7089: foro d1, esterno d2, spessore h;
- rivetto a strappo (testa tonda): Ø, testa D × spessore;
- rivetto filettato (inserto a testa piana): foro di montaggio, testa D × spessore, filetto interno.
"""
from __future__ import annotations

import math
from pathlib import Path

TCEI = {'M3': (5.5, 3, 2.5), 'M4': (7, 4, 3), 'M5': (8.5, 5, 4), 'M6': (10, 6, 5), 'M8': (13, 8, 6), 'M10': (16, 10, 8),
        'M12': (18, 12, 10)}
TSPEI = {'M3': (6.72, 1.86, 2), 'M4': (8.96, 2.48, 2.5), 'M5': (11.2, 3.1, 3), 'M6': (13.44, 3.72, 4),
         'M8': (17.92, 4.96, 5), 'M10': (22.4, 6.2, 6), 'M12': (26.88, 7.44, 8)}
TE = {'M5': (8, 3.5), 'M6': (10, 4), 'M8': (13, 5.3), 'M10': (16, 6.4), 'M12': (18, 7.5), 'M16': (24, 10)}
DADO = {'M3': (5.5, 2.4), 'M4': (7, 3.2), 'M5': (8, 4.7), 'M6': (10, 5.2), 'M8': (13, 6.8), 'M10': (16, 8.4),
        'M12': (18, 10.8), 'M16': (24, 14.8)}
RONDELLA = {'M3': (3.2, 7, 0.5), 'M4': (4.3, 9, 0.8), 'M5': (5.3, 10, 1), 'M6': (6.4, 12, 1.6), 'M8': (8.4, 16, 1.6),
            'M10': (10.5, 20, 2), 'M12': (13, 24, 2.5), 'M16': (17, 30, 3)}
RIVETTO = {'3,2': (3.2, 6.4, 1.0), '4': (4.0, 8.0, 1.3), '4,8': (4.8, 9.6, 1.5)}
INSERTO = {'M4': (6, 9, 1.0, 3.3), 'M5': (7, 10, 1.0, 4.2), 'M6': (9, 12, 1.5, 5.0), 'M8': (11, 15, 1.5, 6.8)}

CATALOGO = {
    'vite_tcei': {'nome': 'Vite TCEI ISO 4762', 'misure': list(TCEI), 'lunghezze': [6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 50, 60]},
    'vite_tspei': {'nome': 'Vite a testa svasata TSPEI ISO 10642', 'misure': list(TSPEI),
                   'lunghezze': [8, 10, 12, 16, 20, 25, 30, 35, 40, 50, 60]},
    'vite_te': {'nome': 'Vite TE ISO 4017', 'misure': list(TE), 'lunghezze': [10, 12, 16, 20, 25, 30, 35, 40, 50, 60, 80]},
    'dado': {'nome': 'Dado esagonale ISO 4032', 'misure': list(DADO), 'lunghezze': []},
    'rondella': {'nome': 'Rondella piana ISO 7089', 'misure': list(RONDELLA), 'lunghezze': []},
    'rivetto': {'nome': 'Rivetto a strappo testa tonda', 'misure': list(RIVETTO), 'lunghezze': [6, 8, 10, 12, 16]},
    'inserto': {'nome': 'Rivetto filettato testa piana', 'misure': list(INSERTO), 'lunghezze': []},
}


def nome_file(tipo: str, misura: str, L=None) -> str:
    base = {'vite_tcei': f'TCEI {misura}x{L}', 'vite_tspei': f'TSPEI {misura}x{L}', 'vite_te': f'TE {misura}x{L}', 'dado': f'Dado {misura}',
            'rondella': f'Rondella {misura}', 'rivetto': f'Rivetto {misura}x{L}', 'inserto': f'Rivetto filettato {misura}'}
    return base[tipo]


def descrizione(tipo: str, misura: str, L=None) -> str:
    return {'vite_tcei': f'Vite TCEI ISO 4762 {misura}x{L} cl. 8.8 zincata',
            'vite_tspei': f'Vite TSPEI ISO 10642 {misura}x{L} cl. 10.9 zincata',
            'vite_te': f'Vite TE ISO 4017 {misura}x{L} cl. 8.8 zincata',
            'dado': f'Dado esagonale ISO 4032 {misura} cl. 8 zincato',
            'rondella': f'Rondella piana ISO 7089 {misura} zincata',
            'rivetto': f'Rivetto a strappo testa tonda Ø{misura}x{L} alluminio/acciaio',
            'inserto': f'Rivetto filettato (inserto) testa piana {misura} acciaio zincato'}[tipo]


def _ok(r, cosa):
    if not r.get('ok'):
        raise ValueError(f'{cosa}: {r.get("message")}')
    return r


def _sketch(s):
    return next(f.id for f in s.doc.features if hasattr(f, 'entities'))


def _faccia(s, n, piu=True):
    """Il nome della faccia piana con normale n (la più avanti lungo n)."""
    import build123d as bd
    best = None
    for nome, fs in s.result.body.names.items():
        f = bd.Face(fs[0])
        if f.geom_type != bd.GeomType.PLANE:
            continue
        c = f.center()
        nn = f.normal_at(c)
        if nn.X * n[0] + nn.Y * n[1] + nn.Z * n[2] < 0.999:
            continue
        q = (c.X * n[0] + c.Y * n[1] + c.Z * n[2]) * (1 if piu else -1)
        if best is None or q > best[0]:
            best = (q, nome)
    return best[1]


def _gira(s, sezione, asse_y=(-1e3, 1e3)):
    """Mezza sezione (x = raggio, y = lungo l'asse) fatta girare attorno all'asse y."""
    sid = _sketch(s)
    _ok(s.sketch_add_polyline(sid, [[round(x, 4), round(y, 4)] for x, y in sezione], True), 'sezione')
    _ok(s.sketch_add_polyline(sid, [[0, asse_y[0]], [0, asse_y[1]]], False, True), 'asse')
    _ok(s.create_from_sketch(sid, 'revolve', {'angle': 360}), 'rivoluzione')


def _esagono(s, faccia, centro_y, s_chiave, op, profondita):
    """Un esagono (chiave s) centrato sull'asse, su una faccia piana perpendicolare all'asse y: tasca o rilievo."""
    import build123d as bd

    from cad_engine.sketch.face_plane import plane_of
    sid = _ok(s.sketch_on_face(faccia), 'sketch sulla faccia')['sketch']
    pl = plane_of(s.result.body, faccia, s.doc.sketch(sid))
    c = pl.to_local_coords(bd.Vector(0, centro_y, 0))
    r = s_chiave / 2 / math.cos(math.radians(30))
    _ok(s.sketch_add_polygon(sid, [round(c.X, 4), round(c.Y, 4)], [round(c.X + r, 4), round(c.Y, 4)], 6), 'esagono')
    _ok(s.create_from_sketch(sid, op, {'distance': profondita}), 'esagono')


def crea(tipo: str, misura: str, L=None, cartella=None) -> Path:
    """Il file del pezzo (lo fa se non c'è)."""
    from app.service import Service
    if tipo not in CATALOGO:
        raise ValueError(f'Pezzo «{tipo}» sconosciuto.')
    if misura not in CATALOGO[tipo]['misure']:
        raise ValueError(f'Misura {misura} non in catalogo per {CATALOGO[tipo]["nome"]}.')
    if CATALOGO[tipo]['lunghezze'] and not L:
        raise ValueError('Scegli la lunghezza.')
    cartella = Path(cartella) if cartella else Path.home() / 'Documents' / 'SteelCAD' / 'Libreria'
    cartella.mkdir(parents=True, exist_ok=True)
    nome = nome_file(tipo, misura, L)
    f = cartella / f'{nome}.steelcad'
    if f.exists():
        return f
    L0 = L
    s = Service()
    _ok(s.new_project('zero', {'name': nome, 'material': 'S235'}), nome)
    d = float(misura[1:]) if misura.startswith('M') else float(misura.replace(',', '.'))
    r = d / 2
    if tipo == 'vite_tcei':
        dk, k, sc = TCEI[misura]
        L = float(L)
        _gira(s, [(0, -L), (r * 0.8, -L), (r, -L + r * 0.2), (r, 0), (dk / 2, 0), (dk / 2, k - k * 0.08),
                  (dk / 2 - k * 0.08, k), (0, k)])
        _esagono(s, _faccia(s, (0, 1, 0)), k, sc, 'cut', k * 0.6)
    elif tipo == 'vite_tspei':
        # la faccia piana della testa a y = 0 (a filo della lamiera), il cono a 90° sotto, il gambo fino a -L
        dk, k, sc = TSPEI[misura]
        L = float(L)
        _gira(s, [(0, -L), (r * 0.8, -L), (r, -L + r * 0.2), (r, -k), (dk / 2, 0), (0, 0)])
        _esagono(s, _faccia(s, (0, 1, 0)), 0, sc, 'cut', k * 0.7)
    elif tipo == 'vite_te':
        sc, k = TE[misura]
        L = float(L)
        _gira(s, [(0, -L), (r * 0.8, -L), (r, -L + r * 0.2), (r, 0), (0, 0)])
        _esagono(s, _faccia(s, (0, 1, 0)), 0, sc, 'boss', k)
    elif tipo == 'dado':
        sc, m = DADO[misura]
        sid = _sketch(s)
        rr = sc / 2 / math.cos(math.radians(30))
        _ok(s.sketch_add_polygon(sid, [0, 0], [round(rr, 4), 0], 6), 'esagono')
        _ok(s.sketch_add_circle(sid, [0, 0], r), 'foro')
        _ok(s.create_from_sketch(sid, 'plate', {'thickness': m}), 'dado')
    elif tipo == 'rondella':
        d1, d2, h = RONDELLA[misura]
        sid = _sketch(s)
        _ok(s.sketch_add_circle(sid, [0, 0], d2 / 2), 'esterno')
        _ok(s.sketch_add_circle(sid, [0, 0], d1 / 2), 'foro')
        _ok(s.create_from_sketch(sid, 'plate', {'thickness': h}), 'rondella')
    elif tipo == 'rivetto':
        dd, D, h = RIVETTO[misura]
        L = float(L)
        _gira(s, [(0, -L), (dd / 2, -L), (dd / 2, 0), (D / 2, 0), (D / 2 * 0.7, h), (0, h)])
    elif tipo == 'inserto':
        dfo, D, h, dint = INSERTO[misura]
        L = 2.5 * d
        _gira(s, [(dint / 2, -L), (dfo / 2, -L), (dfo / 2, 0), (D / 2, 0), (D / 2, h), (dint / 2, h)])
    s.doc.meta['acquisto'] = {'descrizione': descrizione(tipo, misura, L0),
                              'codice': '', 'fornitore': ''}
    _ok(s.save(str(f)), 'salva')
    return f
