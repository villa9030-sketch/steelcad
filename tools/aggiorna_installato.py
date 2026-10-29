"""Aggiorna il Radius installato su questo PC col codice della cartella del progetto, senza rifare l'installer (28/10:
«non puoi creare delle patch? ogni volta devi reinstallare tutto?»).

Si copiano solo app/ e cad_engine/ (pochi MB): Python e le librerie dell'installato restano quelli. Se requirements.txt
è cambiato dall'ultima installazione, le librerie vanno aggiornate: allora serve l'installer (tools/crea_installer.py).
Radius, se è aperto, si chiude (prima fa il suo salvataggio automatico ogni minuto) e si riapre aggiornato.

    python tools/aggiorna_installato.py
"""
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Radius'
CARTELLE = ('app', 'cad_engine')
SALTA = shutil.ignore_patterns('__pycache__', 'icons_nuove')


def _impronta_requisiti() -> str:
    return hashlib.sha1((ROOT / 'requirements.txt').read_bytes()).hexdigest()


def _processi_radius() -> list:
    """I Radius installati aperti (pythonw di DEST)."""
    ps = (f"Get-CimInstance Win32_Process | Where-Object {{ $_.Name -like 'python*' -and $_.CommandLine -like '*{DEST}\\app\\main.py*' }} "
          "| ForEach-Object { $_.ProcessId }")
    r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True)
    return [int(x) for x in r.stdout.split() if x.strip().isdigit()]


def main():
    if not (DEST / 'python' / 'pythonw.exe').is_file():
        raise SystemExit(f'Radius non è installato in {DEST}: prima l’installer (tools/crea_installer.py).')
    segno = DEST / 'requisiti.sha1'
    if segno.is_file() and segno.read_text().strip() != _impronta_requisiti():
        raise SystemExit('requirements.txt è cambiato: le librerie vanno aggiornate, serve l’installer (tools/crea_installer.py).')
    aperti = _processi_radius()
    for pid in aperti:
        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True)
    if aperti:
        time.sleep(1.5)
    t0 = time.time()
    for c in CARTELLE:
        nuova, vecchia = DEST / (c + '.nuova'), DEST / c
        if nuova.exists():
            shutil.rmtree(nuova)
        shutil.copytree(ROOT / c, nuova, ignore=SALTA)
        if vecchia.exists():
            shutil.rmtree(vecchia)
        nuova.rename(vecchia)
    segno.write_text(_impronta_requisiti())
    try:                                         # compilato in anticipo: la prima apertura non aspetta
        subprocess.run([str(DEST / 'python' / 'python.exe'), '-m', 'compileall', '-q', str(DEST / 'app'), str(DEST / 'cad_engine')],
                       capture_output=True)
    except OSError:
        pass
    print(f'aggiornato in {time.time() - t0:.1f} s')
    if aperti or '--apri' in sys.argv:
        subprocess.Popen([str(DEST / 'python' / 'pythonw.exe'), str(DEST / 'app' / 'main.py')], cwd=str(DEST),
                         creationflags=getattr(subprocess, 'DETACHED_PROCESS', 0), close_fds=True)
        print('Radius riaperto')


if __name__ == '__main__':
    main()
