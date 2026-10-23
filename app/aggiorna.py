"""Aggiornamento automatico (23/10): all'avvio Radius guarda su GitHub se c'è una versione più nuova; se l'utente dice
«Aggiorna», scarica il Setup nuovo e lo lancia in modo silenzioso: il Setup chiude Radius, rimpiazza i file e lo riapre.

Solo per Radius installato (python/ incorporato accanto ad app/): dalla cartella di sviluppo non si controlla niente.
Le versioni si pubblicano come «release» GitHub col tag vX.Y.Z e il file Radius-Setup-X.Y.Z.exe allegato.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO = 'villa9030-sketch/steelcad'
API = f'https://api.github.com/repos/{REPO}/releases/latest'


def installato() -> bool:
    exe = Path(sys.executable).resolve()
    return exe.parent.name.lower() == 'python' and (exe.parent.parent / 'app' / 'main.py').is_file()


def _numeri(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r'\d+', v)[:3])


def controlla(attuale: str, timeout: float = 6.0) -> dict:
    """{'ok': True, 'nuova': '0.9.1', 'url': ..., 'mb': 230, 'note': ...} oppure {'ok': True, 'nuova': None}."""
    if not installato() and not os.environ.get('RADIUS_PROVA_AGGIORNA'):
        return {'ok': True, 'nuova': None, 'motivo': 'sviluppo'}
    try:
        req = urllib.request.Request(API, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Radius'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rel = json.loads(r.read().decode('utf-8'))
    except Exception as e:  # noqa: BLE001 - niente rete o GitHub giù: si riprova al prossimo avvio
        return {'ok': False, 'message': f'Controllo aggiornamenti non riuscito: {e}'}
    tag = rel.get('tag_name') or ''
    if not tag or _numeri(tag) <= _numeri(attuale):
        return {'ok': True, 'nuova': None}
    setup = next((a for a in rel.get('assets') or [] if re.match(r'Radius-Setup-.*\.exe$', a.get('name') or '', re.I)), None)
    if not setup:
        return {'ok': True, 'nuova': None}
    return {'ok': True, 'nuova': tag.lstrip('vV'), 'url': setup['browser_download_url'], 'mb': round(setup.get('size', 0) / 1e6),
            'note': (rel.get('body') or '').strip()[:600]}


def installa(url: str) -> dict:
    """Scarica il Setup e lo avvia (silenzioso, con la barra di avanzamento). Il Setup chiude Radius da solo."""
    if not re.match(rf'^https://github\.com/{re.escape(REPO)}/releases/download/[^\s]+/Radius-Setup-[\w.\-]+\.exe$', url or ''):
        return {'ok': False, 'message': 'Indirizzo dell’aggiornamento non valido.'}
    dest = Path(tempfile.gettempdir()) / url.rsplit('/', 1)[-1]
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Radius'})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, 'wb') as fh:
            while True:
                blocco = r.read(1 << 20)
                if not blocco:
                    break
                fh.write(blocco)
    except Exception as e:  # noqa: BLE001
        return {'ok': False, 'message': f'Download dell’aggiornamento non riuscito: {e}'}
    subprocess.Popen([str(dest), '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS'],
                     creationflags=getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0),
                     close_fds=True)
    return {'ok': True, 'message': 'Aggiornamento avviato: Radius si chiude e si riapre da solo.'}
