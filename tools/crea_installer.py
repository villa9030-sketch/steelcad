"""L'installer di Radius per Windows (23/10): un Setup.exe che non chiede niente a chi lo usa (niente Python da
installare, niente permessi di amministratore).

Come si fa:
1. Python «incorporabile» ufficiale (stessa versione del .venv) in build/Radius/python;
2. dentro, le librerie del .venv (stessa versione e stessa architettura: si copiano), senza quelle dei test;
3. accanto, il programma (app/, cad_engine/);
4. Inno Setup impacchetta tutto in dist/Radius-Setup-<versione>.exe: installa in %LOCALAPPDATA%\\Programs\\Radius,
   icona sul desktop e nel menu Start, doppio clic sui .steelcad, disinstallazione da «App installate».
   Un aggiornamento è lo stesso Setup più nuovo: chiude Radius se è aperto, rimpiazza i file e lo riapre.

    python tools/crea_installer.py
"""
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
STAGE = BUILD / 'Radius'
DIST = ROOT / 'dist'
VENV = ROOT / '.venv'
ISCC = Path.home() / 'AppData/Local/Programs/Inno Setup 6/ISCC.exe'
# le librerie che servono solo per i test o per installare pacchetti; jedi e parso (5.600 file: il completamento del
# codice di IPython, a Radius non serve) e playwright con le sue (le prove nel browser): l'installazione era 9 minuti
FUORI = re.compile(r'^(pip|pytest|_pytest|pluggy|iniconfig|py\.py|jedi|parso|playwright|pyee|greenlet)([-_.].*)?$', re.I)

# la prova vera col Python impacchettato: una lamiera con una piega, il 3D, il DXF di taglio
PROVA = '''
import sys, tempfile, pathlib, os
os.environ['STEELCAD_HOME'] = tempfile.mkdtemp()
sys.path[:0] = ['.', 'app']
from app.service import Service
s = Service()
assert s.new_project('lamiera', {'name': 'Prova', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.4})['ok']
assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
assert s.scene()['objects'][0]['positions']
d = pathlib.Path(tempfile.mkdtemp())
r = s.export_dxf(str(d / 'p.dxf'))
assert r['ok'], r
print('pezzo, 3D e DXF ok')
'''


def versione_python() -> str:
    cfg = (VENV / 'pyvenv.cfg').read_text(encoding='utf-8')
    return re.search(r'^version\s*=\s*([\d.]+)', cfg, re.M).group(1)


def versione_app() -> str:
    testo = (ROOT / 'cad_engine' / '__init__.py').read_text(encoding='utf-8')
    return re.search(r"__version__\s*=\s*'([^']+)'", testo).group(1)


def python_incorporabile(ver: str) -> Path:
    zipf = BUILD / 'cache' / f'python-{ver}-embed-amd64.zip'
    if not zipf.is_file():
        zipf.parent.mkdir(parents=True, exist_ok=True)
        url = f'https://www.python.org/ftp/python/{ver}/python-{ver}-embed-amd64.zip'
        print('scarico', url)
        urllib.request.urlretrieve(url, zipf)
    return zipf


def copia(src: Path, dst: Path, salta=()):
    def ignora(cartella, nomi):
        return [n for n in nomi if n == '__pycache__' or n in salta]
    shutil.copytree(src, dst, ignore=ignora)


def prepara(ver_py: str):
    if STAGE.exists():
        shutil.rmtree(STAGE)
    py = STAGE / 'python'
    py.mkdir(parents=True)
    with zipfile.ZipFile(python_incorporabile(ver_py)) as z:
        z.extractall(py)
    # i percorsi: la libreria standard, le librerie, il programma (app/ come cartella degli script, e la radice per cad_engine)
    pth = next(py.glob('python*._pth'))
    zipstd = next(py.glob('python*.zip')).name
    pth.write_text(f'{zipstd}\n.\nLib\\site-packages\n..\n..\\app\nimport site\n', encoding='utf-8')
    sp = py / 'Lib' / 'site-packages'
    sp.mkdir(parents=True)
    for p in (VENV / 'Lib' / 'site-packages').iterdir():
        if FUORI.match(p.name) or p.name == '__pycache__':
            continue
        if p.is_dir():
            shutil.copytree(p, sp / p.name, ignore=shutil.ignore_patterns('__pycache__', 'tests'))
        else:
            shutil.copy2(p, sp / p.name)
    copia(ROOT / 'app', STAGE / 'app', salta=('icons_nuove',))
    copia(ROOT / 'cad_engine', STAGE / 'cad_engine')
    # le librerie di questa installazione: tools/aggiorna_installato.py copia solo il codice finché non cambiano
    import hashlib
    (STAGE / 'requisiti.sha1').write_text(hashlib.sha1((ROOT / 'requirements.txt').read_bytes()).hexdigest())
    # le librerie compilate in anticipo: la prima apertura non deve aspettare
    subprocess.run([str(py / 'python.exe'), '-m', 'compileall', '-q', '-j', '2', str(STAGE / 'app'), str(STAGE / 'cad_engine')],
                   check=False)


ISS = r'''#define Ver "{ver}"
[Setup]
AppId={{{{6C1E7A52-6F2B-4D57-9C8E-2A5F2B6D9A31}}
AppName=Radius
AppVersion={{#Ver}}
AppVerName=Radius {{#Ver}}
AppPublisher=Radius
AppPublisherURL=https://github.com/villa9030-sketch/steelcad
DefaultDirName={{localappdata}}\Programs\Radius
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir={dist}
OutputBaseFilename=Radius-Setup-{{#Ver}}
SetupIconFile={stage}\app\ui\img\radius.ico
UninstallDisplayIcon={{app}}\app\ui\img\radius.ico
UninstallDisplayName=Radius
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
ChangesAssociations=yes

[Languages]
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktop"; Description: "Icona sul desktop"; GroupDescription: "Icone:"

[InstallDelete]
; un aggiornamento rimpiazza tutto il programma (niente file vecchi rimasti); i lavori dell'utente stanno altrove
Type: filesandordirs; Name: "{{app}}\app"
Type: filesandordirs; Name: "{{app}}\cad_engine"
Type: filesandordirs; Name: "{{app}}\python"

[UninstallDelete]
; aggiorna_installato.py (28/10) rimette app e cad_engine senza passare dal Setup: si tolgono comunque tutti
Type: filesandordirs; Name: "{{app}}\app"
Type: filesandordirs; Name: "{{app}}\cad_engine"
Type: files; Name: "{{app}}\requisiti.sha1"

[Files]
Source: "{stage}\*"; DestDir: "{{app}}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{{autoprograms}}\Radius"; Filename: "{{app}}\python\pythonw.exe"; Parameters: """{{app}}\app\main.py"""; WorkingDir: "{{app}}"; IconFilename: "{{app}}\app\ui\img\radius.ico"; AppUserModelID: "Radius.App"
Name: "{{autodesktop}}\Radius"; Filename: "{{app}}\python\pythonw.exe"; Parameters: """{{app}}\app\main.py"""; WorkingDir: "{{app}}"; IconFilename: "{{app}}\app\ui\img\radius.ico"; AppUserModelID: "Radius.App"; Tasks: desktop

[Registry]
Root: HKCU; Subkey: "Software\Classes\.steelcad"; ValueType: string; ValueData: "Radius.Pezzo"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.steelcad-asm"; ValueType: string; ValueData: "Radius.Assieme"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Radius.Pezzo"; ValueType: string; ValueData: "Pezzo Radius"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Radius.Pezzo\DefaultIcon"; ValueType: string; ValueData: "{{app}}\app\ui\img\radius.ico"
Root: HKCU; Subkey: "Software\Classes\Radius.Pezzo\shell\open\command"; ValueType: string; ValueData: """{{app}}\python\pythonw.exe"" ""{{app}}\app\main.py"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\Radius.Assieme"; ValueType: string; ValueData: "Assieme Radius"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Radius.Assieme\DefaultIcon"; ValueType: string; ValueData: "{{app}}\app\ui\img\radius.ico"
Root: HKCU; Subkey: "Software\Classes\Radius.Assieme\shell\open\command"; ValueType: string; ValueData: """{{app}}\python\pythonw.exe"" ""{{app}}\app\main.py"" ""%1"""

[Run]
; dopo l'installazione (anche quella silenziosa dell'aggiornamento automatico) Radius si riapre
Filename: "{{app}}\python\pythonw.exe"; Parameters: """{{app}}\app\main.py"""; WorkingDir: "{{app}}"; Description: "Apri Radius"; Flags: nowait postinstall
'''


def main():
    ver_py, ver = versione_python(), versione_app()
    print(f'Radius {ver}, Python {ver_py}')
    prepara(ver_py)
    # prova: il Python impacchettato trova tutto?
    r = subprocess.run([str(STAGE / 'python' / 'python.exe'), '-c',
                        'import build123d, OCP, planegcs, ezdxf, webview, scipy, clr; import cad_engine; print("librerie ok")'],
                       capture_output=True, text=True, cwd=str(STAGE))
    print(r.stdout.strip() or r.stderr.strip()[-2000:])
    if r.returncode:
        raise SystemExit('il Python impacchettato non trova le librerie')
    r = subprocess.run([str(STAGE / 'python' / 'python.exe'), '-c', PROVA], capture_output=True, text=True, cwd=str(STAGE))
    print(r.stdout.strip() or r.stderr.strip()[-2000:])
    if r.returncode:
        raise SystemExit('il Python impacchettato non fa un pezzo')
    print('file da installare:', sum(1 for x in STAGE.rglob('*') if x.is_file()))
    DIST.mkdir(exist_ok=True)
    iss = BUILD / 'radius.iss'
    iss.write_text(ISS.format(ver=ver, dist=DIST, stage=STAGE), encoding='utf-8-sig')
    subprocess.run([str(ISCC), '/Q', str(iss)], check=True)
    out = DIST / f'Radius-Setup-{ver}.exe'
    print('fatto:', out, f'{out.stat().st_size / 1e6:.0f} MB')


if __name__ == '__main__':
    main()
