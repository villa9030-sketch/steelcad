r"""Server di prova: l'interfaccia nel browser (http://127.0.0.1:PORTA/?dev), stesso motore.

Serve per i test automatici con un browser invisibile e per provare senza la
finestra desktop. Le finestre "Apri/Salva" qui non ci sono: si usa la cartella
indicata con --cartella.

    .venv\Scripts\python.exe app\dev_server.py --porta 5077 --cartella C:\tmp\prove
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import Api  # noqa: E402

UI = Path(__file__).resolve().parent / 'ui'


class ApiProva(Api):
    """Come quella vera, ma i percorsi dei file sono fissi nella cartella di prova."""

    def __init__(self, cartella: Path):
        super().__init__()
        self._dir = cartella

    def _dialog(self, kind, filtri, nome=''):
        if 'steelcad' in filtri[0] and not nome:
            prog = sorted(self._dir.glob('*.steelcad'))
            return str(prog[0]) if prog else None
        return str(self._dir / nome)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--porta', type=int, default=5077)
    ap.add_argument('--cartella', default=str(Path.cwd()))
    a = ap.parse_args()
    cartella = Path(a.cartella)
    cartella.mkdir(parents=True, exist_ok=True)
    api = ApiProva(cartella)

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *x, **kw):
            super().__init__(*x, directory=str(UI), **kw)

        def log_message(self, *x):
            pass

        def do_POST(self):
            nome = self.path.removeprefix('/api/')
            fn = getattr(api, nome, None)
            if nome.startswith('_') or not callable(fn):
                self.send_error(404)
                return
            args = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'[]')
            body = json.dumps(fn(*args)).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(('127.0.0.1', a.porta), H)
    print(f'http://127.0.0.1:{a.porta}/?dev', flush=True)
    srv.serve_forever()


if __name__ == '__main__':
    main()
