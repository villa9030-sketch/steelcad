"""SteelCAD: la finestra desktop.

    .venv\\Scripts\\python.exe app\\main.py [progetto.steelcad]

La finestra è una pagina locale (app/ui) dentro WebView2; il motore gira qui in
Python. Il ponte (Api) espone solo metodi: il progetto vive in attributi
privati, così pywebview non prova a esplorare gli oggetti del kernel.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import webview

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.service import Service  # noqa: E402

UI = Path(__file__).resolve().parent / 'ui' / 'index.html'
FILTRO_PROGETTO = ('Progetto SteelCAD (*.steelcad;*.steelcad-asm)', 'Pezzo (*.steelcad)', 'Assieme (*.steelcad-asm)')
FILTRO_PEZZO = ('Pezzo SteelCAD (*.steelcad)',)
FILTRO_ASSIEME = ('Assieme SteelCAD (*.steelcad-asm)',)
FILTRO_DISEGNO = ('Disegno (*.dxf;*.dwg)', 'DXF (*.dxf)', 'DWG (*.dwg)')


def _tipo_file(file_type: str) -> tuple[str, str]:
    """Come webview.util.parse_file_type, ma l'estensione può avere il trattino (.steelcad-asm): quella di
    pywebview accetta solo lettere e cifre, e la finestra Apri (e Salva di un assieme) andava in errore."""
    import re
    m = re.search(r'^([\w ]+)\((\*(?:\.(?:[\w-]+|\*))*(?:;\*(?:\.(?:[\w-]+|\*))*)*)\)$', file_type)
    if m:
        return m.group(1).rstrip(), m.group(2)
    raise ValueError(f'{file_type} is not a valid file filter')


def _filtri_col_trattino():
    """Il controllo dei filtri si sostituisce dove pywebview lo usa: window.py lo importa subito, la parte
    Windows (winforms) quando parte la finestra, prendendolo da webview.util."""
    import webview.util
    import webview.window
    webview.util.parse_file_type = _tipo_file
    webview.window.parse_file_type = _tipo_file
    winforms = sys.modules.get('webview.platforms.winforms')
    if winforms is not None:
        winforms.parse_file_type = _tipo_file


_filtri_col_trattino()


class Api:
    def __init__(self):
        self._svc = Service()
        self._lock = threading.Lock()
        self._window = None

    def _call(self, fn, *a, **kw):
        with self._lock:
            return fn(*a, **kw)

    # lettura
    def state(self):
        return self._call(self._svc.state)

    def scene(self):
        return self._call(self._svc.scene)

    def select(self, obj_id, face_index=None, face_name=None):
        return self._call(self._svc.select, obj_id, face_index, face_name)

    def profile_suggestions(self):
        return self._svc.profile_suggestions()

    # modifiche
    def set_parameter(self, name, value):
        return self._call(self._svc.set_parameter, name, value)

    def set_dimension(self, sketch_id, dim_id, value):
        return self._call(self._svc.set_dimension, sketch_id, dim_id, value)

    def edit_member(self, obj_id, fields, whole_group=False):
        return self._call(self._svc.edit_member, obj_id, fields, whole_group)

    def add_member(self, st_id, from_key, to_key=None, direction=None, length=None, profile=None, group=None):
        return self._call(self._svc.add_member, st_id, from_key, to_key, direction, length, profile, group)

    def delete_members(self, obj_ids):
        return self._call(self._svc.delete_members, obj_ids)

    def set_joint(self, st_id, key, spec):
        return self._call(self._svc.set_joint, st_id, key, spec)

    def move_node(self, st_id, key, values):
        return self._call(self._svc.move_node, st_id, key, values)

    def add_flange(self, fid, edge, fields, parent=None):
        return self._call(self._svc.add_flange, fid, edge, fields, parent)

    def edit_flange(self, fid, flid, fields):
        return self._call(self._svc.edit_flange, fid, flid, fields)

    def delete_flange(self, fid, flid):
        return self._call(self._svc.delete_flange, fid, flid)

    def add_flange_hole(self, fid, flid, u, v, d):
        return self._call(self._svc.add_flange_hole, fid, flid, u, v, d)

    def delete_flange_hole(self, fid, flid, index):
        return self._call(self._svc.delete_flange_hole, fid, flid, index)

    def set_sheet_tech(self, fid, fields):
        return self._call(self._svc.set_sheet_tech, fid, fields)

    def set_tip_corners(self, fid, mode):
        return self._call(self._svc.set_tip_corners, fid, mode)

    def extend_over_tab(self, fid, flid):
        return self._call(self._svc.extend_over_tab, fid, flid)

    def sketch_hole_type(self, sid, eids, spec):
        return self._call(self._svc.sketch_hole_type, sid, eids, spec)

    def auto_tabs(self, fid, flid, n, w, gioco, sporgenza=0):
        return self._call(self._svc.auto_tabs, fid, flid, n, w, gioco, sporgenza)

    def sheet_fold(self, sid, angle, direction='up', flip=False, bump=None):
        return self._call(self._svc.sheet_fold, sid, angle, direction, flip, bump)

    def edit_fold(self, fid, foid, fields):
        return self._call(self._svc.edit_fold, fid, foid, fields)

    def delete_fold(self, fid, foid):
        return self._call(self._svc.delete_fold, fid, foid)

    def sketch_xray(self, sid, on):
        return self._call(self._svc.sketch_xray, sid, on)

    def sheet_tab(self, sid):
        return self._call(self._svc.sheet_tab, sid)

    def contour_flange(self, sid):
        return self._call(self._svc.contour_flange, sid)

    def set_end_tab(self, fid, flid, end, on, gap=0):
        return self._call(self._svc.set_end_tab, fid, flid, end, on, gap)

    def set_corner(self, fid, flid, other, mode, gap=0):
        return self._call(self._svc.set_corner, fid, flid, other, mode, gap)

    def set_shape_edge(self, fid, key, scelta):
        return self._call(self._svc.set_shape_edge, fid, key, scelta)

    def structure_template_apply(self, st_id, values):
        return self._call(self._svc.structure_template_apply, st_id, values)

    def sketch_on_face(self, face_name):
        return self._call(self._svc.sketch_on_face, face_name)

    def sketch_close(self, sid):
        return self._call(self._svc.sketch_close, sid)

    def sketch_on_flat(self, fid=None):
        return self._call(self._svc.sketch_on_flat, fid)

    def sketch_view(self, sid):
        return self._call(self._svc.sketch_view, sid)

    def sketch_add_polyline(self, sid, pts, closed, construction=False, angles=None):
        return self._call(self._svc.sketch_add_polyline, sid, pts, closed, construction, angles)

    def sketch_add_rectangle(self, sid, p0, p1, construction=False):
        return self._call(self._svc.sketch_add_rectangle, sid, p0, p1, construction)

    def sketch_add_circle(self, sid, center, r, construction=False):
        return self._call(self._svc.sketch_add_circle, sid, center, r, construction)

    def sketch_add_slot(self, sid, c1, c2, r, construction=False):
        return self._call(self._svc.sketch_add_slot, sid, c1, c2, r, construction)

    def sketch_add_arc3(self, sid, p1, p2, p3, construction=False):
        return self._call(self._svc.sketch_add_arc3, sid, p1, p2, p3, construction)

    def sketch_add_polygon(self, sid, center, vertex, n, construction=False):
        return self._call(self._svc.sketch_add_polygon, sid, center, vertex, n, construction)

    def sketch_fillet(self, sid, pid, r):
        return self._call(self._svc.sketch_fillet, sid, pid, r)

    def sketch_fillet_lines(self, sid, l1, l2, c1, c2, r):
        return self._call(self._svc.sketch_fillet_lines, sid, l1, l2, c1, c2, r)

    def sketch_chamfer_lines(self, sid, l1, l2, c1, c2, d):
        return self._call(self._svc.sketch_chamfer_lines, sid, l1, l2, c1, c2, d)

    def sketch_chamfer(self, sid, pid, d):
        return self._call(self._svc.sketch_chamfer, sid, pid, d)

    def set_bend_default(self, values):
        return self._call(self._svc.set_bend_default, values)

    def sheet_rules(self):
        return self._call(self._svc.sheet_rules)

    def save_sheet_rule(self, fid, name):
        return self._call(self._svc.save_sheet_rule, fid, name)

    def delete_sheet_rule(self, name):
        return self._call(self._svc.delete_sheet_rule, name)

    def apply_sheet_rule(self, fid, name):
        return self._call(self._svc.apply_sheet_rule, fid, name)

    def sketch_construction(self, sid, eids, flag):
        return self._call(self._svc.sketch_construction, sid, eids, flag)

    def sketch_offset_preview(self, sid, eids, dist, side):
        return self._call(self._svc.sketch_offset_preview, sid, eids, dist, side)

    def sketch_offset_side(self, sid, eids, dist, point):
        return self._call(self._svc.sketch_offset_side, sid, eids, dist, point)

    def sketch_offset(self, sid, eids, dist, side):
        return self._call(self._svc.sketch_offset, sid, eids, dist, side)

    def sketch_trim_preview(self, sid, eid, click):
        return self._call(self._svc.sketch_trim_preview, sid, eid, click)

    def sketch_trim(self, sid, eid, click):
        return self._call(self._svc.sketch_trim, sid, eid, click)

    def sketch_extend_preview(self, sid, eid, click):
        return self._call(self._svc.sketch_extend_preview, sid, eid, click)

    def sketch_extend(self, sid, eid, click):
        return self._call(self._svc.sketch_extend, sid, eid, click)

    def sketch_mirror(self, sid, eids, axis):
        return self._call(self._svc.sketch_mirror, sid, eids, axis)

    def sketch_copy(self, sid, eids, dx, dy):
        return self._call(self._svc.sketch_copy, sid, eids, dx, dy)

    def sketch_move(self, sid, eids, dx, dy):
        return self._call(self._svc.sketch_move, sid, eids, dx, dy)

    def sketch_pattern(self, sid, eids, cols, px, rows, py):
        return self._call(self._svc.sketch_pattern, sid, eids, cols, px, rows, py)

    def sketch_dimension(self, sid, kind, refs):
        return self._call(self._svc.sketch_dimension, sid, kind, refs)

    def sketch_delete(self, sid, eids):
        return self._call(self._svc.sketch_delete, sid, eids)

    def create_from_sketch(self, sid, kind, values):
        return self._call(self._svc.create_from_sketch, sid, kind, values)

    def undo(self):
        return self._call(self._svc.undo)

    def redo(self):
        return self._call(self._svc.redo)

    def new_project(self, kind, values=None):
        return self._call(self._svc.new_project, kind, values)

    def home_info(self):
        return self._call(self._svc.home_info)

    def recover_unsaved(self):
        return self._call(self._svc.recover_unsaved)

    def forget_recent(self, path):
        return self._call(self._svc.forget_recent, path)

    # prepara per il laser / l'officina: i file scelti, insieme, nella cartella del lavoro
    def prepara_info(self):
        return self._call(self._svc.prepara_info)

    def prepara(self, cartella, scelte, campi=None):
        return self._call(self._svc.prepara, cartella, scelte, campi)

    def scegli_cartella(self):
        r = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not r:
            return {'ok': False, 'cancelled': True}
        return {'ok': True, 'cartella': r if isinstance(r, str) else r[0]}

    def apri_cartella(self, path):
        import os
        try:
            os.startfile(path)                      # Esplora risorse sulla cartella appena salvata
            return {'ok': True}
        except OSError as ex:
            return {'ok': False, 'message': str(ex)}

    def fori_info(self, face_name=None):
        return self._call(self._svc.fori_info, face_name)

    def fori_guidati(self, face_name, spec):
        return self._call(self._svc.fori_guidati, face_name, spec)

    def new_project_preview(self, kind, values=None):
        return self._call(self._svc.new_project_preview, kind, values)

    def save_thumbnail(self, path, data_url):
        return self._call(self._svc.save_thumbnail, path, data_url)

    # import di uno sviluppo da DXF/DWG
    def import_dxf_dialog(self):
        p = self._dialog(webview.OPEN_DIALOG, FILTRO_DISEGNO)
        if not p:
            return {'ok': False, 'cancelled': True}
        return self._call(self._svc.import_dxf, p)

    def import_dxf(self, path):
        return self._call(self._svc.import_dxf, path)

    def import_dxf_giro(self, giro):
        return self._call(self._svc.import_dxf_giro, giro)

    def import_dxf_create(self, giro, params):
        return self._call(self._svc.import_dxf_create, giro, params)

    # assiemi
    def new_assembly(self, name='Assieme'):
        return self._call(self._svc.new_assembly, name)

    def asm_insert_dialog(self):
        p = self._dialog(webview.OPEN_DIALOG, FILTRO_PEZZO)
        if not p:
            return {'ok': False, 'cancelled': True}
        return self._call(self._svc.asm_insert, p)

    def asm_insert(self, path):
        return self._call(self._svc.asm_insert, path)

    def asm_remove(self, iid):
        return self._call(self._svc.asm_remove, iid)

    def asm_move(self, iid, dx, dy, dz):
        return self._call(self._svc.asm_move, iid, dx, dy, dz)

    def asm_rotate(self, iid, axis, deg):
        return self._call(self._svc.asm_rotate, iid, axis, deg)

    def asm_rotate_all(self, axis, deg):
        return self._call(self._svc.asm_rotate_all, axis, deg)

    def asm_set(self, iid, fields):
        return self._call(self._svc.asm_set, iid, fields)

    def asm_add_mate(self, kind, a, b, offset=0, flip=False, a2=None, b2=None):
        return self._call(self._svc.asm_add_mate, kind, a, b, offset, flip, a2, b2)

    def asm_edit_mate(self, mid, fields):
        return self._call(self._svc.asm_edit_mate, mid, fields)

    def asm_delete_mate(self, mid):
        return self._call(self._svc.asm_delete_mate, mid)

    def asm_interferences(self):
        return self._call(self._svc.asm_interferences)

    def asm_tabs(self, iid, face, n, w, gioco, sporgenza=0):
        return self._call(self._svc.asm_tabs, iid, face, n, w, gioco, sporgenza)

    def drawing_fields(self):
        return self._call(self._svc.drawing_fields)

    def drawing_preview(self, campi=None, tutte=False):
        return self._call(self._svc.drawing_preview, campi, tutte)

    def export_drawings_dialog(self, fmt, campi, tutte=False):
        nome = ((self._svc.asm.name if self._svc.asm is not None else self._svc.doc.meta.get('name')) or 'tavole') + '_tavole'
        filtro = ('PDF (*.pdf)',) if fmt == 'pdf' else ('DXF (*.dxf)',)
        p = self._dialog(webview.SAVE_DIALOG, filtro, nome + ('.pdf' if fmt == 'pdf' else '.dxf'))
        if not p:
            return {'ok': False, 'cancelled': True}
        return self._call(self._svc.export_drawings, p, campi, tutte)

    def asm_open_part(self, iid):
        return self._call(self._svc.asm_open_part, iid)

    def asm_new_part(self, iid, face_index, nome=''):
        return self._call(self._svc.asm_new_part, iid, face_index, nome)

    def asm_back(self):
        return self._call(self._svc.asm_back)

    def set_titlebar(self, colore):
        _barra_titolo(getattr(self, '_window', None), colore if isinstance(colore, str) and len(colore) == 7 else '#101215')
        return {'ok': True}

    def autosave(self):
        return self._call(self._svc.autosave)

    # file, con le finestre di Windows
    def _dialog(self, kind, filtri, nome=''):
        r = self._window.create_file_dialog(kind, save_filename=nome, file_types=filtri)
        if not r:
            return None
        return r if isinstance(r, str) else r[0]

    def open_dialog(self):
        p = self._dialog(webview.OPEN_DIALOG, FILTRO_PROGETTO)
        if not p:
            return {'ok': False, 'cancelled': True}
        if self._svc.recovery_available(p):
            return {'ok': False, 'recovery': True, 'path': p}
        return self._call(self._svc.open, p)

    def open_recent(self, path):
        if self._svc.recovery_available(path):
            return {'ok': False, 'recovery': True, 'path': path}
        return self._call(self._svc.open, path)

    def open_path(self, path, recover=False):
        return self._call(self._svc.open, path, recover)

    def save(self, save_as=False):
        p = None
        if save_as or self._svc.path is None:
            if self._svc.asm is not None:
                p = self._dialog(webview.SAVE_DIALOG, FILTRO_ASSIEME, (self._svc.asm.name or 'assieme') + '.steelcad-asm')
                if not p:
                    return {'ok': False, 'cancelled': True}
                return self._call(self._svc.save, p)
            nome = (self._svc.doc.meta.get('name') or 'progetto') + '.steelcad'
            p = self._dialog(webview.SAVE_DIALOG, FILTRO_PEZZO, nome)
            if not p:
                return {'ok': False, 'cancelled': True}
        return self._call(self._svc.save, p)

    def export(self, kind):
        ext = {'step': ('STEP (*.step;*.stp)', '.step'), 'dxf': ('DXF di taglio (*.dxf)', '.dxf'),
               'bendtable': ('Tabella pieghe (*.csv)', '_pieghe.csv')}[kind]
        if self._svc.asm is not None and kind != 'step':
            return {'ok': False, 'message': 'Il DXF e la tabella pieghe si fanno per ogni pezzo: apri il pezzo dall’assieme.'}
        nome = ((self._svc.asm.name if self._svc.asm is not None else self._svc.doc.meta.get('name')) or 'pezzo') + ext[1]
        p = self._dialog(webview.SAVE_DIALOG, (ext[0],), nome)
        if not p:
            return {'ok': False, 'cancelled': True}
        fn = {'step': self._svc.export_step, 'dxf': self._svc.export_dxf, 'bendtable': self._svc.export_bend_table}[kind]
        return self._call(fn, p)


ICONA = Path(__file__).resolve().parent / 'ui' / 'img' / 'steelcad.ico'


def _app_windows():
    """Per Windows SteelCAD è un'applicazione a sé, non "Python": nella barra delle applicazioni ha la sua icona e
    non si raggruppa con altri programmi Python."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('SteelCAD.App')
    except Exception:  # noqa: BLE001 - è solo l'aspetto nella barra
        pass


def _barra_titolo(window, colore: str = '#101215'):
    """La barra del titolo di Windows scura, come la barra in alto dell'app (niente striscia bianca sopra):
    modo scuro su Windows 10/11; su Windows 11 anche il colore esatto. Bordi, aggancio ai lati e doppio clic
    restano quelli di Windows."""
    if sys.platform != 'win32' or window is None or getattr(window, 'native', None) is None:
        return
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = wintypes.HWND(int(str(window.native.Handle)))
        dwm = ctypes.windll.dwmapi
        uno = ctypes.c_int(1)
        for attr in (20, 19):              # DWMWA_USE_IMMERSIVE_DARK_MODE (19 sulle versioni di Windows 10 più vecchie)
            if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(uno), ctypes.sizeof(uno)) == 0:
                break
        r, g, b = int(colore[1:3], 16), int(colore[3:5], 16), int(colore[5:7], 16)
        rif = ctypes.c_int(r | (g << 8) | (b << 16))                   # COLORREF 0x00BBGGRR
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(rif), 4)      # DWMWA_CAPTION_COLOR (solo Windows 11)
        bianco = ctypes.c_int(0x00F1EDE9)
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(bianco), 4)   # DWMWA_TEXT_COLOR (solo Windows 11)
        # la barra si ridisegna subito (se no cambia solo al prossimo clic fuori e dentro la finestra)
        ctypes.windll.user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
    except Exception:  # noqa: BLE001 - è solo l'aspetto
        pass


def main():
    _app_windows()
    api = Api()
    file = [a for a in sys.argv[1:] if not a.startswith('--')]
    if file:
        r = api.open_path(file[0])
        if not r['ok']:
            print(r['message'])
    w = webview.create_window('SteelCAD', str(UI), js_api=api, width=1440, height=900, min_size=(1024, 640),
                              background_color='#16191D')
    api._window = w

    def chiusura():
        if not api._svc.history.dirty:
            return True
        api.autosave()
        return w.create_confirmation_dialog(
            'SteelCAD', 'Ci sono modifiche non salvate (c’è comunque il salvataggio automatico). Chiudere?')

    w.events.closing += chiusura
    w.events.shown += lambda: _barra_titolo(w)
    webview.start(http_server=True, debug='--debug' in sys.argv, icon=str(ICONA) if ICONA.is_file() else None)


if __name__ == '__main__':
    main()
