"""STEP di un assieme del cliente → assieme di Radius (29/10: «cosa molto fastidiosa che non posso importare gli
assiemi in STEP»).

Dalla struttura dello STEP (XCAF): ogni pezzo diverso con il suo nome e, per ogni copia, dove sta. I pezzi uguali
ripetuti (la stessa definizione citata più volte) sono un pezzo solo con più copie. Se lo STEP non ha la struttura
(un solo «pezzo» con tanti solidi dentro), ogni solido è un pezzo; i solidi uguali e solo spostati diventano copie
dello stesso pezzo.
"""
from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path

from .step_lamiera import StepError


def _nome(label) -> str:
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDataStd import TDataStd_Name
    n = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), n):
        t = TCollection_AsciiString(n.Get()).ToCString()
        return ''.join(ch for ch in t if unicodedata.category(ch)[0] != 'C').strip()
    return ''


def _vero(nome: str) -> bool:
    """Un nome dato da chi ha disegnato (non «SOLID», «COMPOUND», «Body1» messi dal CAD)."""
    t = (nome or '').strip()
    return bool(t) and not re.fullmatch(r'(SOLID|COMPOUND|SHELL|COMPSOLID|Open CASCADE STEP translator.*|=>.*|Body\d*|Solid\d*|NAUO\d*)', t, re.I)


def _matrice(trsf) -> tuple:
    R = [[trsf.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)]
    T = [trsf.Value(i, 4) for i in (1, 2, 3)]
    return R, T


def leggi(path) -> list:
    """I pezzi dello STEP: [{'nome', 'forma' (TopoDS_Shape nelle coordinate del pezzo), 'copie': [(R, T)]}]."""
    from OCP.collections import Sequence_TDF_Label
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDF import TDF_Label
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    p = Path(path)
    if not p.exists():
        raise StepError(f'Lo STEP non si legge: {p} non c’è.')
    doc = TDocStd_Document(TCollection_ExtendedString('XCAF'))
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    r = STEPCAFControl_Reader()
    r.SetNameMode(True)
    if r.ReadFile(str(p)) != 1 or not r.Transfer(doc):
        raise StepError('Lo STEP non si legge (file rovinato o di un tipo che non conosco).')
    pezzi: dict = {}                                  # etichetta del pezzo → voce

    def giro(label, loc: TopLoc_Location, padre: str = ''):
        figli = Sequence_TDF_Label()
        if label is None:
            tool.GetFreeShapes(figli)
        else:
            tool.GetComponents_s(label, figli)
        for i in range(figli.Length()):
            c = figli.Value(i + 1)
            ref = TDF_Label()
            if tool.IsReference_s(c):
                tool.GetReferredShape_s(c, ref)
            else:
                ref = c
            qui = loc.Multiplied(tool.GetLocation_s(c)) if label is not None else loc   # dove sta questa copia
            nome = next((x for x in (_nome(ref), _nome(c)) if _vero(x)), padre)
            if tool.IsAssembly_s(ref):
                giro(ref, qui, nome)
                continue
            forma = tool.GetShape_s(ref)
            if forma.IsNull():
                continue
            from OCP.TCollection import TCollection_AsciiString
            from OCP.TDF import TDF_Tool
            ent = TCollection_AsciiString()
            TDF_Tool.Entry_s(ref, ent)
            chiave = ent.ToCString()
            voce = pezzi.setdefault(chiave, {'nome': nome, 'forma': forma.Located(TopLoc_Location()),
                                             'copie': []})
            tr = qui.Multiplied(forma.Location()).Transformation()   # con la posizione che la forma ha già nel pezzo
            voce['copie'].append(_matrice(tr))
    giro(None, TopLoc_Location())
    out = [v for v in pezzi.values() if _solidi(v['forma'])]
    if len(out) == 1 and len(out[0]['copie']) == 1 and len(_solidi(out[0]['forma'])) > 1:
        out = _da_solidi(out[0])                       # uno STEP senza struttura: i solidi sono i pezzi
    if not out:
        raise StepError('Nello STEP non c’è nessun solido.')
    return out


def _solidi(forma) -> list:
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    out = []
    ex = TopExp_Explorer(forma, TopAbs_SOLID)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def _da_solidi(voce) -> list:
    """Un pezzo con tanti solidi e nessuna struttura: ogni solido un pezzo; quelli uguali (stesso volume, stessa
    area, stesso ingombro) e solo spostati sono copie dello stesso."""
    import build123d as bd
    R0, T0 = voce['copie'][0]
    gruppi: list = []
    for so in _solidi(voce['forma']):
        s = bd.Solid(so)
        bb = s.bounding_box()
        firma = (round(s.volume, 1), round(s.area, 1), round(bb.size.X, 2), round(bb.size.Y, 2), round(bb.size.Z, 2))
        g = next((x for x in gruppi if x['firma'] == firma), None)
        if g is None:
            g = {'firma': firma, 'forma': so, 'min': bb.min, 'copie': []}
            gruppi.append(g)
        d = bb.min - g['min']
        T = [T0[i] + sum(R0[i][j] * (d.X, d.Y, d.Z)[j] for j in range(3)) for i in range(3)]
        g['copie'].append((R0, T))
    base = voce['nome'] or 'Pezzo'
    return [{'nome': f'{base} {k + 1}', 'forma': g['forma'], 'copie': g['copie']} for k, g in enumerate(gruppi)]


def nome_file(nome: str, usati: set) -> str:
    """Un nome di file pulito e unico per il pezzo."""
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', nome or 'Pezzo').strip(' ._') or 'Pezzo'
    base = base[:60]
    n, out = 1, base
    while out.lower() in usati:
        n += 1
        out = f'{base} ({n})'
    usati.add(out.lower())
    return out


def step_di(forma) -> bytes:
    """La forma di un pezzo come STEP (per tenerla dentro il suo file)."""
    import tempfile

    import build123d as bd
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / 'pezzo.step'
        bd.export_step(bd.Shape.cast(forma), str(f))
        return f.read_bytes()


def ruota_ok(R) -> bool:
    """La matrice è una rotazione (niente specchi né scale strane nello STEP)."""
    det = (R[0][0] * (R[1][1] * R[2][2] - R[1][2] * R[2][1]) - R[0][1] * (R[1][0] * R[2][2] - R[1][2] * R[2][0])
           + R[0][2] * (R[1][0] * R[2][1] - R[1][1] * R[2][0]))
    return math.isclose(det, 1.0, abs_tol=1e-3)


def build_solido(fdef: dict, ctx):
    """La lavorazione «solido_step»: un pezzo dello STEP che non è una lamiera piegata (tubo, profilo, perno,
    fusione): si vede, pesa, va in distinta e nelle tavole; niente sviluppo."""
    import base64
    import tempfile
    import zlib

    import build123d as bd

    from ..errors import FeatureError
    from ..topology import NamedShape
    fid = fdef['id']
    if ctx.body is not None:
        raise FeatureError('Il pezzo da STEP va da solo, come prima lavorazione.', feature=fid)
    try:
        dati = zlib.decompress(base64.b64decode(fdef['dati']))
    except Exception:  # noqa: BLE001
        raise FeatureError('I dati dello STEP nel progetto sono rovinati.', feature=fid) from None
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / 'pezzo.step'
        f.write_bytes(dati)
        try:
            forma = bd.import_step(str(f))
        except Exception as ex:  # noqa: BLE001
            raise FeatureError(f'Lo STEP del pezzo non si legge: {ex}', feature=fid) from None
    solidi = forma.solids() if hasattr(forma, 'solids') else []
    if not solidi:
        raise FeatureError('Nel pezzo importato non c’è un solido.', feature=fid)
    tutto = solidi[0] if len(solidi) == 1 else bd.Compound(children=solidi)
    return NamedShape(tutto.wrapped, {})
