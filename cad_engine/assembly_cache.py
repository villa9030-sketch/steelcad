"""I pezzi dell'assieme già costruiti, tenuti su disco (18/11, carrello di Stefano: aprire l'assieme ricostruiva ogni
pezzo da capo, 12–15 s ogni volta).

Si tiene la forma (formato binario di OpenCascade), i nomi delle facce (per gli accoppiamenti), peso/ingombro e i
dati della distinta. Il nome del file viene dal contenuto esatto del pezzo e dalla versione del programma: se il pezzo
cambia anche di un decimale, o se Radius si aggiorna, il nome è un altro e il pezzo si ricostruisce. Il risultato
completo della ricostruzione (sviluppo, pieghe…) si fa solo quando qualcuno lo chiede (tavole, apri il pezzo).

Non si tengono i pezzi che leggono altri file (STEP, DXF, altri pezzi): se cambia quel file il pezzo cambierebbe
senza che cambi il suo.
"""
from __future__ import annotations

import hashlib
import os
import pickle
from pathlib import Path

_VERSIONE: str | None = None
_ESTERNI = (b'.step', b'.stp', b'.dxf', b'.dwg', b'.steelcad', b'.igs', b'.iges')


def cartella() -> Path:
    base = os.environ.get('STEELCAD_HOME') or os.path.join(os.environ.get('APPDATA') or str(Path.home()), 'SteelCAD')
    return Path(base) / 'pezzi-costruiti'


def _versione() -> str:
    """Il motore com'è adesso: il contenuto di tutti i suoi file .py (cambia a ogni aggiornamento)."""
    global _VERSIONE
    if _VERSIONE is None:
        h = hashlib.sha256()
        radice = Path(__file__).resolve().parent
        for f in sorted(radice.rglob('*.py')):
            h.update(str(f.relative_to(radice)).encode())
            h.update(f.read_bytes())
        _VERSIONE = h.hexdigest()[:16]
    return _VERSIONE


def chiave(p: Path) -> str | None:
    try:
        dati = p.read_bytes()
    except OSError:
        return None
    basso = dati.lower()
    if any(e in basso for e in _ESTERNI):
        return None
    return hashlib.sha256(dati + _versione().encode()).hexdigest()


def leggi(k: str):
    """(forma, nomi, extra) o None."""
    try:
        from OCP.BinTools import BinTools
        from OCP.TopoDS import TopoDS, TopoDS_Shape
        f = cartella() / f'{k}.brep'
        m = cartella() / f'{k}.pkl'
        if not (f.is_file() and m.is_file()):
            return None
        dato = pickle.loads(m.read_bytes())
        if dato.get('chiave') != k:
            return None
        forma = TopoDS_Shape()
        if not BinTools.Read_s(forma, str(f)) or forma.IsNull():
            return None
        mappa = _mappa_facce(forma)
        if mappa.Extent() != dato['facce']:
            return None
        nomi = {n: [TopoDS.Face(mappa.FindKey(i + 1)) for i in idx] for n, idx in dato['nomi'].items()}
        os.utime(m)                                          # usato adesso: resta tra gli ultimi
        return forma, nomi, dato['extra']
    except Exception:  # noqa: BLE001 - un file rovinato: si ricostruisce e basta
        return None


def scrivi(k: str, forma, nomi: dict, extra: dict) -> None:
    try:
        from OCP.BinTools import BinTools
        cart = cartella()
        cart.mkdir(parents=True, exist_ok=True)
        mappa = _mappa_facce(forma)
        idx = {}
        for n, facce in nomi.items():
            ii = [mappa.FindIndex(fc) - 1 for fc in facce]
            idx[n] = [i for i in ii if i >= 0]
        tmp = cart / f'{k}.brep.tmp'
        if not BinTools.Write_s(forma, str(tmp)):
            return
        os.replace(tmp, cart / f'{k}.brep')
        (cart / f'{k}.pkl').write_bytes(pickle.dumps({'chiave': k, 'facce': mappa.Extent(), 'nomi': idx,
                                                      'extra': extra}))
        tutti = sorted(cart.glob('*.pkl'), key=lambda x: x.stat().st_mtime)
        for vecchio in tutti[:-300]:                          # gli ultimi 300 pezzi bastano
            vecchio.unlink(missing_ok=True)
            vecchio.with_suffix('.brep').unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 - se non si riesce a scrivere, pazienza: la prossima volta si ricostruisce
        pass


def _mappa_facce(forma):
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp

    from .topology.naming import TopTools_IndexedMapOfShape
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(forma, TopAbs_FACE, m)
    return m
