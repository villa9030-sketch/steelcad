"""Il set di icone nuovo (23/10, polish): tutte a tratto, griglia 24, spessore 1,8, estremi tondi; grigio scuro per la
forma e un solo accento blu sul dettaglio che conta. Scrive app/ui/icons_nuove/*.svg (le stesse 70 di app/ui/icons,
stessi nomi) e una pagina di confronto vecchie/nuove su sfondo chiaro e scuro.

    python tools/icone_nuove.py            → app/ui/icons_nuove/ + app/ui/icons_nuove/confronto.html
"""
from pathlib import Path

R = Path(__file__).resolve().parents[1] / 'app' / 'ui'
OUT = R / 'icons_nuove'
INK, ACC, FILL = '#2B3542', '#2F7DE1', '#DCE6F2'

# ogni icona: lista di elementi (tag, attributi); 'a' = accento (blu), 'f' = riempito chiaro, 'd' = tratteggiato
I = {}


def ic(nome, *el):
    I[nome] = el


def P(d, *stili):
    return ('path', d, stili)


def C(cx, cy, r, *stili):
    return ('circle', (cx, cy, r), stili)


def Rt(x, y, w, h, rx=0, *stili):
    return ('rect', (x, y, w, h, rx), stili)


def T(x, y, t, size=7, *stili):
    return ('text', (x, y, t, size), stili)


# ---------------------------------------------------------------------------------------------- disegno
ic('line', P('M5 19 L19 5'), C(5, 19, 1.9, 'a', 'pieno'), C(19, 5, 1.9, 'a', 'pieno'))
ic('rect', Rt(4, 6, 16, 12, 1), C(4, 6, 1.6, 'a', 'pieno'), C(20, 18, 1.6, 'a', 'pieno'))
ic('rect_center', Rt(4, 6, 16, 12, 1), P('M12 10.5v3 M10.5 12h3', 'a'))
ic('circle', C(12, 12, 8), C(12, 12, 1.6, 'a', 'pieno'))
ic('arc3', P('M4 17 A9 9 0 0 1 20 17'), C(4, 17, 1.6, 'a', 'pieno'), C(12, 8.6, 1.6, 'a', 'pieno'), C(20, 17, 1.6, 'a', 'pieno'))
ic('arc_tangent', P('M3 18 H11'), P('M11 18 A7 7 0 0 0 18 11 V5', 'a'), C(11, 18, 1.6, 'pieno'))
ic('slot', P('M8 8 H16 A4 4 0 0 1 16 16 H8 A4 4 0 0 1 8 8 Z'), P('M8 12 H16', 'a', 'd'))
ic('polygon', P('M12 3.5 L19.4 7.8 V16.2 L12 20.5 L4.6 16.2 V7.8 Z'), C(12, 12, 1.5, 'a', 'pieno'))
ic('point', P('M12 6 V18 M6 12 H18', 'fine'), C(12, 12, 2.4, 'a', 'pieno'))
ic('text', P('M6 6 H18 M12 6 V19'), P('M9.5 19 H14.5', 'a'))
ic('construction', P('M4 20 L20 4', 'd'), C(4, 20, 1.6, 'a', 'pieno'), C(20, 4, 1.6, 'a', 'pieno'))
ic('sketch', Rt(3.5, 3.5, 17, 17, 2, 'fine'), P('M7 17 L7 17 L9.5 16.5 L17.5 8.5 L15.5 6.5 L7.5 14.5 Z', 'a'))
ic('project', P('M3 15 L12 19.5 L21 15 L12 10.5 Z', 'f'), P('M12 4 V13', 'a'), P('M9.5 10.5 L12 13 L14.5 10.5', 'a'))
ic('dimension', P('M4 7 V17 M20 7 V17'), P('M4 12 H20', 'a'), P('M7 9.5 L4 12 L7 14.5 M17 9.5 L20 12 L17 14.5', 'a'))
ic('measure', Rt(2.5, 8, 19, 8, 1.2, 'f'), P('M6 8 V11 M9.5 8 V12.5 M13 8 V11 M16.5 8 V12.5', 'a'))
ic('select', P('M6 4 L18 12.5 L12.5 13.5 L9.5 19 Z', 'f'), P('M12.5 13.5 L16 18', 'a'))

# modifica dello sketch
ic('offset', P('M4 18 C4 9 9 5 18 5'), P('M8 19 C8 12.5 11.5 9 18 9', 'a'))
ic('trim', P('M3 12 H9'), P('M9 12 H21', 'a', 'd'), P('M14 4 V20'), C(9, 12, 1.5, 'a', 'pieno'))
ic('extend', P('M3 12 H11'), P('M11 12 H18', 'a'), P('M15.5 9 L18.5 12 L15.5 15', 'a'), P('M20.5 4 V20'))
ic('fillet', P('M5 19 V12 A7 7 0 0 1 12 5 H19', 'a'), P('M5 5 V9 M5 5 H9', 'd', 'fine'))
ic('chamfer', P('M5 19 V11 L11 5 H19'), P('M5 11 L11 5', 'a'), P('M5 5 V8 M5 5 H8', 'd', 'fine'))
ic('mirror', P('M12 3 V21', 'd'), P('M9 7 L3 16 H9 Z', 'f'), P('M15 7 L21 16 H15 Z', 'a'))
ic('copy', Rt(8, 8, 12, 12, 2), Rt(4, 4, 12, 12, 2, 'f'), P('M10 14 H14 M12 12 V16', 'a'))
ic('move', P('M12 3 V21 M3 12 H21', 'a'), P('M9.5 5.5 L12 3 L14.5 5.5 M9.5 18.5 L12 21 L14.5 18.5 M5.5 9.5 L3 12 L5.5 14.5 M18.5 9.5 L21 12 L18.5 14.5'))
ic('pattern_rect', Rt(3.5, 3.5, 6, 6, 1, 'a'), Rt(14.5, 3.5, 6, 6, 1), Rt(3.5, 14.5, 6, 6, 1), Rt(14.5, 14.5, 6, 6, 1))
ic('delete', P('M4 7 H20 M9 7 V4.5 H15 V7'), P('M6.5 7 L7.5 20 H16.5 L17.5 7'), P('M10.5 11 V16 M13.5 11 V16', 'a'))
ic('cut', C(7, 17, 2.8), C(17, 17, 2.8), P('M8.8 15 L17 4 M15.2 15 L7 4', 'a'))

# vincoli
ic('c_coincident', P('M4 19 L12 12 M20 19 L12 12'), C(12, 12, 2.3, 'a', 'pieno'))
ic('c_collinear', P('M3 18 L21 6', 'd', 'fine'), P('M4.5 17 L10 13.3 M14 10.7 L19.5 7', 'a'))
ic('c_parallel', P('M5 18 L13 5 M11 19 L19 6', 'a'))
ic('c_perpendicular', P('M5 19 H19 M12 19 V5'), P('M12 15 H16 V19', 'a', 'fine'))
ic('c_tangent', C(10, 13, 6), P('M3 7 H21', 'a'), C(10, 7, 1.5, 'a', 'pieno'))
ic('c_symmetry', P('M12 3 V21', 'd'), C(6, 12, 2, 'a', 'pieno'), C(18, 12, 2, 'a', 'pieno'), P('M8.5 12 H10 M14 12 H15.5', 'fine'))
ic('c_fix', Rt(6, 11, 12, 9, 2, 'f'), P('M8.5 11 V8 A3.5 3.5 0 0 1 15.5 8 V11'), C(12, 15.5, 1.4, 'a', 'pieno'))
ic('plane_angle', P('M4 19 H20'), P('M4 19 L16 7', 'a'), P('M10 19 A6 6 0 0 0 8.2 14.8', 'fine'))

# lamiera
ic('fold', P('M3 17 H13'), P('M13 17 L20 6', 'a'), P('M13 17 A3 3 0 0 0 14.5 14.5', 'fine'))
ic('flange', P('M2.5 15 L12 20 L21.5 15 L12 10 Z', 'f'), P('M12 10 L21.5 15 V8 L12 3 Z', 'a'))
ic('hem', P('M3 15 H17 A3 3 0 0 0 17 9 H9'), P('M17 15 A3 3 0 0 0 17 9', 'a'), P('M9 9 H12', 'a'))
ic('flat', Rt(3, 5, 18, 14, 1, 'f'), P('M3 10 H21 M3 14 H21', 'a', 'd'))
ic('refold', P('M3 19 H10'), P('M14 19 H21 V11', 'a'), P('M6 15 C6 9 12 7.5 16 10', 'fine'), P('M13.4 9.2 L16 10 L15.1 12.6', 'fine'))
ic('convert_sheet', P('M3 8 L7 6 L11 8 V16 L7 18 L3 16 Z', 'f'), P('M12.5 12 H15.5', 'fine'), P('M14 10 L16 12 L14 14', 'fine'), P('M18 6 V18 H22', 'a'))
ic('perforate', Rt(3, 4, 18, 16, 2, 'f'), P('M6.5 8.5 H17.5 M6.5 12 H17.5 M6.5 15.5 H17.5', 'a'))
ic('hole', Rt(4, 4, 16, 16, 2, 'f'), C(12, 12, 4.2, 'a'), P('M12 6.5 V8 M12 16 V17.5 M6.5 12 H8 M16 12 H17.5', 'fine'))
ic('bendtable', Rt(3.5, 4, 17, 16, 1.5), P('M3.5 9 H20.5 M3.5 14.5 H20.5 M9 4 V20'), P('M12 18 H15 L18 15.5', 'a', 'fine'))
ic('extrude', P('M4 16 L12 20 L20 16 L12 12 Z', 'f'), P('M12 12 V4', 'a'), P('M9 7 L12 4 L15 7', 'a'), P('M4 16 V12 L12 8 L20 12 V16', 'd', 'fine'))
ic('section', P('M4 8 L12 3.5 L20 8 V16 L12 20.5 L4 16 Z'), P('M4 8 L12 12.5 L20 8 M12 12.5 V20.5', 'fine'), P('M3 12 L12 7.5 L21 12 L12 16.5 Z', 'a'))

# 3D, vista, assiemi
ic('box', P('M12 3 L20 7.5 V16.5 L12 21 L4 16.5 V7.5 Z'), P('M4 7.5 L12 12 L20 7.5 M12 12 V21', 'a'))
ic('joint', P('M4 20 V9 A5 5 0 0 1 9 4 H20'), P('M8 20 V10 A2 2 0 0 1 10 8 H20'), C(6, 6, 1.6, 'a', 'pieno'))
ic('explode', Rt(4, 13, 7, 7, 1, 'f'), Rt(13, 4, 7, 7, 1, 'a'), P('M11 13 L13 11', 'd', 'fine'))
ic('fastener', P('M8 4 H16 L18 7 L16 10 H8 L6 7 Z', 'f'), P('M10 10 V20 H14 V10'), P('M10 13 L14 14.5 M10 16 L14 17.5', 'a', 'fine'))
ic('fit', P('M4 9 V4 H9 M15 4 H20 V9 M20 15 V20 H15 M9 20 H4 V15'), Rt(8.5, 8.5, 7, 7, 1, 'a'))
ic('lookat', Rt(3, 6, 18, 12, 1.5, 'f'), C(12, 12, 3.2, 'a'), C(12, 12, 1, 'a', 'pieno'))
ic('orbit', C(12, 12, 2.2, 'a', 'pieno'), P('M20 12 A8 8 0 1 1 16 5.1'), P('M16.4 1.9 L16 5.1 L19.2 5.6'))
ic('pan', P('M12 3 V21 M3 12 H21', 'fine'), P('M9.5 5.5 L12 3 L14.5 5.5 M9.5 18.5 L12 21 L14.5 18.5 M5.5 9.5 L3 12 L5.5 14.5 M18.5 9.5 L21 12 L18.5 14.5'), C(12, 12, 2.2, 'a', 'pieno'))
ic('zoom', C(10.5, 10.5, 6.5), P('M15.5 15.5 L20.5 20.5'), P('M10.5 8 V13 M8 10.5 H13', 'a'))
ic('search', C(10.5, 10.5, 6.5), P('M15.5 15.5 L20.5 20.5', 'a'))
ic('eye', P('M2.5 12 C5.5 6.5 18.5 6.5 21.5 12 C18.5 17.5 5.5 17.5 2.5 12 Z'), C(12, 12, 3, 'a'))
ic('home', P('M4 11 L12 4 L20 11 V20 H4 Z'), Rt(10, 14, 4, 6, 0.5, 'a'))
ic('params', P('M4 7 H20 M4 12 H20 M4 17 H20', 'fine'), C(8, 7, 2, 'a', 'pieno'), C(15, 12, 2, 'a', 'pieno'), C(10, 17, 2, 'a', 'pieno'))
ic('settings', P('M12 2.8 L14 5.2 L17.1 4.7 L17.6 7.8 L20.4 9.4 L19.2 12 L20.4 14.6 L17.6 16.2 L17.1 19.3 L14 18.8 L12 21.2 L10 18.8 L6.9 19.3 L6.4 16.2 L3.6 14.6 L4.8 12 L3.6 9.4 L6.4 7.8 L6.9 4.7 L10 5.2 Z'), C(12, 12, 3, 'a'))
ic('library', Rt(3.5, 4, 4, 16, 1), Rt(9, 4, 4, 16, 1, 'a'), P('M15.5 5.5 L19.3 4.6 L22 19 L18.2 19.9 Z'))
ic('list', P('M9 6 H20 M9 12 H20 M9 18 H20'), C(5, 6, 1.4, 'a', 'pieno'), C(5, 12, 1.4, 'a', 'pieno'), C(5, 18, 1.4, 'a', 'pieno'))

# file e azioni
ic('new', P('M6 3 H14 L19 8 V21 H6 Z'), P('M14 3 V8 H19', 'fine'), P('M12.5 11.5 V17.5 M9.5 14.5 H15.5', 'a'))
ic('open', P('M3 6 V19 H19 L21 10 H7 L5 19'), P('M3 6 H9 L11 8 H17 V10', 'a'))
ic('save', P('M5 4 H16 L20 8 V20 H4 V4 Z'), Rt(8, 4, 7, 5, 0.5), Rt(7.5, 13, 9, 7, 0.8, 'a'))
ic('export', P('M4 14 V20 H20 V14'), P('M12 4 V15', 'a'), P('M8 8 L12 4 L16 8', 'a'))
ic('dxf', P('M6 3 H14 L19 8 V21 H6 Z', 'f'), P('M14 3 V8 H19', 'fine'), T(12.4, 17.3, 'DXF', 5.4, 'a'))
ic('undo', P('M9 6 L4.5 10.5 L9 15'), P('M4.5 10.5 H14 A5.5 5.5 0 0 1 14 21.5 H11', 'a'))
ic('redo', P('M15 6 L19.5 10.5 L15 15'), P('M19.5 10.5 H10 A5.5 5.5 0 0 0 10 21.5 H13', 'a'))
ic('finish', C(12, 12, 9), P('M7.5 12.5 L10.7 15.5 L16.5 9', 'a'))


# ---------------------------------------------------------------------------------------------- scrittura
def svg(nome, el):
    parti = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke-linecap="round" '
             f'stroke-linejoin="round"><title>{nome}</title>']
    for tag, g, stili in el:
        col = ACC if 'a' in stili else INK
        w = 1.4 if 'fine' in stili else 1.8
        tratto = f' stroke="{col}" stroke-width="{w}"' + (' stroke-dasharray="2.2 2.4"' if 'd' in stili else '')
        riemp = ' fill="%s"' % (col if 'pieno' in stili else (FILL if 'f' in stili else 'none'))
        if 'pieno' in stili:
            tratto = ''
        if tag == 'path':
            parti.append(f'<path d="{g}"{tratto}{riemp}/>')
        elif tag == 'circle':
            parti.append(f'<circle cx="{g[0]}" cy="{g[1]}" r="{g[2]}"{tratto}{riemp}/>')
        elif tag == 'rect':
            parti.append(f'<rect x="{g[0]}" y="{g[1]}" width="{g[2]}" height="{g[3]}" rx="{g[4]}"{tratto}{riemp}/>')
        elif tag == 'text':
            parti.append(f'<text x="{g[0]}" y="{g[1]}" font-family="Segoe UI, Arial, sans-serif" font-size="{g[3]}" '
                         f'font-weight="700" text-anchor="middle" fill="{col}">{g[2]}</text>')
    parti.append('</svg>')
    return ''.join(parti)


def main():
    OUT.mkdir(exist_ok=True)
    vecchie = sorted(p.stem for p in (R / 'icons').glob('*.svg'))
    manca = [n for n in vecchie if n not in I]
    if manca:
        raise SystemExit(f'Mancano: {manca}')
    for n, el in I.items():
        (OUT / f'{n}.svg').write_text(svg(n, el), encoding='utf-8')
    gruppi = {'Disegno': ['line', 'rect', 'rect_center', 'circle', 'arc3', 'arc_tangent', 'slot', 'polygon', 'point', 'text',
                          'construction', 'sketch', 'project', 'dimension', 'measure', 'select'],
              'Modifica': ['offset', 'trim', 'extend', 'fillet', 'chamfer', 'mirror', 'copy', 'move', 'pattern_rect', 'delete', 'cut'],
              'Vincoli': ['c_coincident', 'c_collinear', 'c_parallel', 'c_perpendicular', 'c_tangent', 'c_symmetry', 'c_fix', 'plane_angle'],
              'Lamiera': ['fold', 'flange', 'hem', 'flat', 'refold', 'convert_sheet', 'perforate', 'hole', 'bendtable', 'extrude', 'section'],
              '3D, vista e assiemi': ['box', 'joint', 'explode', 'fastener', 'fit', 'lookat', 'orbit', 'pan', 'zoom', 'search', 'eye',
                                      'home', 'params', 'settings', 'library', 'list'],
              'File e azioni': ['new', 'open', 'save', 'export', 'dxf', 'undo', 'redo', 'finish']}
    nomi_it = {'line': 'Linea', 'rect': 'Rettangolo', 'rect_center': 'Rettangolo dal centro', 'circle': 'Cerchio', 'arc3': 'Arco 3 punti',
               'arc_tangent': 'Arco tangente', 'slot': 'Asola', 'polygon': 'Poligono', 'point': 'Punto', 'text': 'Testo',
               'construction': 'Costruzione', 'sketch': 'Sketch', 'project': 'Su una faccia', 'dimension': 'Quota', 'measure': 'Misura',
               'select': 'Seleziona', 'offset': 'Offset', 'trim': 'Accorcia', 'extend': 'Allunga', 'fillet': 'Raccordo', 'chamfer': 'Smusso',
               'mirror': 'Specchia', 'copy': 'Copia', 'move': 'Sposta', 'pattern_rect': 'Serie', 'delete': 'Elimina', 'cut': 'Taglio',
               'c_coincident': 'Coincidente', 'c_collinear': 'Allineati', 'c_parallel': 'Paralleli', 'c_perpendicular': 'Perpendicolari',
               'c_tangent': 'Tangente', 'c_symmetry': 'Simmetrico', 'c_fix': 'Blocca', 'plane_angle': 'Angolo', 'fold': 'Piega',
               'flange': 'Flangia', 'hem': 'Orlo', 'flat': 'Spiega', 'refold': 'Ripiega', 'convert_sheet': 'Converti in lamiera',
               'perforate': 'Persiane', 'hole': 'Foro', 'bendtable': 'Tabella pieghe', 'extrude': 'Estrudi', 'section': 'Sezione',
               'box': 'Pezzo', 'joint': 'Giunto', 'explode': 'Esploso', 'fastener': 'Viteria', 'fit': 'Inquadra', 'lookat': 'Guarda di fronte',
               'orbit': 'Ruota vista', 'pan': 'Sposta vista', 'zoom': 'Zoom', 'search': 'Cerca', 'eye': 'Vedi attraverso', 'home': 'Home',
               'params': 'Misure', 'settings': 'Impostazioni', 'library': 'Libreria', 'list': 'Elenco', 'new': 'Nuovo', 'open': 'Apri',
               'save': 'Salva', 'export': 'Esporta', 'dxf': 'DXF', 'undo': 'Annulla', 'redo': 'Rifai', 'finish': 'Fine'}
    righe = []
    for g, nomi in gruppi.items():
        celle = ''.join(f'<div class="c"><div class="nome">{nomi_it.get(n, n)}<small>{n}</small></div>'
                        f'<div class="coppia"><span class="lbl">prima</span><img src="../icons/{n}.svg"><img class="g" src="../icons/{n}.svg"></div>'
                        f'<div class="coppia nuova"><span class="lbl">dopo</span><img src="{n}.svg"><img class="g" src="{n}.svg"></div>'
                        f'<div class="scuro"><img class="old" src="../icons/{n}.svg"><img class="new" src="{n}.svg"></div></div>'
                        for n in nomi)
        righe.append(f'<h2>{g}</h2><div class="griglia">{celle}</div>')
    html = f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><title>Icone nuove — confronto</title>
<style>
body {{ font: 13px/1.4 "Segoe UI", system-ui, sans-serif; margin: 24px 32px; background: #F3F5F7; color: #1C2228; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }} p.sotto {{ color: #5B6670; margin: 0 0 18px; }}
h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: .06em; color: #5B6670; margin: 26px 0 10px; }}
.griglia {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 10px; }}
.c {{ background: #fff; border: 1px solid #DDE2E7; border-radius: 10px; padding: 10px 12px; display: grid;
      grid-template-columns: 1fr auto; grid-template-rows: auto auto auto; gap: 6px 10px; align-items: center; }}
.nome {{ grid-column: 1 / -1; font-weight: 600; }} .nome small {{ color: #8A949D; font-weight: 400; margin-left: 6px; }}
.coppia {{ display: flex; align-items: center; gap: 12px; grid-column: 1 / 2; }}
.coppia .lbl {{ width: 34px; color: #8A949D; font-size: 11px; }}
.coppia img {{ width: 24px; height: 24px; }} .coppia img.g {{ width: 40px; height: 40px; }}
.coppia.nuova .lbl {{ color: #2F7DE1; font-weight: 600; }}
.scuro {{ grid-column: 2 / 3; grid-row: 2 / 4; background: #1B2027; border-radius: 8px; padding: 8px 10px; display: grid; gap: 8px; }}
.scuro img {{ width: 24px; height: 24px; filter: invert(.88) hue-rotate(180deg) brightness(1.15); }}
.scuro img.old {{ opacity: .9; }}
</style></head><body>
<h1>Icone nuove — confronto ({len(I)})</h1>
<p class="sotto">Per ogni comando: prima e dopo, alla grandezza della barra (24) e più grandi (40); a destra sul tema scuro (sopra la vecchia, sotto la nuova).</p>
{''.join(righe)}</body></html>'''
    (OUT / 'confronto.html').write_text(html, encoding='utf-8')
    print(f'ok: {len(I)} icone in {OUT}')


if __name__ == '__main__':
    main()
