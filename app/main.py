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
FILTRO_PROGETTO = ('Progetto SteelCAD (*.steelcad)',)


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

    def select(self, obj_id, face_index=None):
        return self._call(self._svc.select, obj_id, face_index)

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

    def undo(self):
        return self._call(self._svc.undo)

    def redo(self):
        return self._call(self._svc.redo)

    def new_project(self, kind, values=None):
        return self._call(self._svc.new_project, kind, values)

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

    def open_path(self, path, recover=False):
        return self._call(self._svc.open, path, recover)

    def save(self, save_as=False):
        p = None
        if save_as or self._svc.path is None:
            nome = (self._svc.doc.meta.get('name') or 'progetto') + '.steelcad'
            p = self._dialog(webview.SAVE_DIALOG, FILTRO_PROGETTO, nome)
            if not p:
                return {'ok': False, 'cancelled': True}
        return self._call(self._svc.save, p)

    def export(self, kind):
        ext = {'step': ('STEP (*.step;*.stp)', '.step'), 'dxf': ('DXF di taglio (*.dxf)', '.dxf')}[kind]
        nome = (self._svc.doc.meta.get('name') or 'pezzo') + ext[1]
        p = self._dialog(webview.SAVE_DIALOG, (ext[0],), nome)
        if not p:
            return {'ok': False, 'cancelled': True}
        fn = self._svc.export_step if kind == 'step' else self._svc.export_dxf
        return self._call(fn, p)


def main():
    api = Api()
    file = [a for a in sys.argv[1:] if not a.startswith('--')]
    if file:
        r = api.open_path(file[0])
        if not r['ok']:
            print(r['message'])
    w = webview.create_window('SteelCAD', str(UI), js_api=api, width=1440, height=900, min_size=(1024, 640),
                              background_color='#E8EAED')
    api._window = w

    def chiusura():
        if not api._svc.history.dirty:
            return True
        api.autosave()
        return w.create_confirmation_dialog(
            'SteelCAD', 'Ci sono modifiche non salvate (c’è comunque il salvataggio automatico). Chiudere?')

    w.events.closing += chiusura
    webview.start(http_server=True, debug='--debug' in sys.argv)


if __name__ == '__main__':
    main()
