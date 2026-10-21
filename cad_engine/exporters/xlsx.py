"""Un file Excel (.xlsx) semplice, senza librerie: più fogli, intestazione in grassetto, larghezze delle colonne,
numeri come numeri (si sommano in Excel). Il formato è uno zip di XML (Office Open XML, ECMA-376)."""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


def _col(i: int) -> str:
    s = ''
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _cella(rif: str, v, stile: int) -> str:
    if v is None or v == '':
        return f'<c r="{rif}" s="{stile}"/>' if stile else ''
    if isinstance(v, bool):
        v = 'sì' if v else 'no'
    if isinstance(v, (int, float)):
        return f'<c r="{rif}" s="{stile or 2}"><v>{round(float(v), 6):g}</v></c>' if isinstance(v, float) else \
            f'<c r="{rif}" s="{stile}"><v>{v}</v></c>'
    return f'<c r="{rif}" t="inlineStr" s="{stile}"><is><t xml:space="preserve">{escape(str(v))}</t></is></c>'


def _foglio(righe: list, larghezze: list, intestazioni: set) -> str:
    cols = ''.join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(larghezze))
    xs = []
    for r, riga in enumerate(righe):
        stile = 1 if r in intestazioni else 0
        celle = ''.join(_cella(f'{_col(c)}{r + 1}', v, stile) for c, v in enumerate(riga))
        xs.append(f'<row r="{r + 1}">{celle}</row>')
    blocca = ('<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
              'state="frozen"/></sheetView></sheetViews>') if 0 in intestazioni else ''
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'{blocca}<cols>{cols}</cols><sheetData>{"".join(xs)}</sheetData></worksheet>')


def scrivi(path, fogli: list) -> Path:
    """fogli: [(nome, righe, larghezze, righe_intestazione)] — righe = liste di valori (testo o numeri)."""
    path = Path(path)
    nomi = [f[0][:31] for f in fogli]
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
          + ''.join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    for i in range(len(fogli))) + '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
          + ''.join(f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(nomi))
          + '</sheets></workbook>')
    wbrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              + ''.join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                        f'relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(fogli)))
              + f'<Relationship Id="rId{len(fogli) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                'relationships/styles" Target="styles.xml"/></Relationships>')
    # stili: 0 normale, 1 intestazione (grassetto, fondo grigio), 2 numero con due decimali
    stili = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts>'
             '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
             '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
             '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
             '<fill><patternFill patternType="solid"><fgColor rgb="FFE4E7EB"/></patternFill></fill></fills>'
             '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
             '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
             '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
             '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
             '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
             '</styleSheet>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ct)
        z.writestr('_rels/.rels', rels)
        z.writestr('xl/workbook.xml', wb)
        z.writestr('xl/_rels/workbook.xml.rels', wbrels)
        z.writestr('xl/styles.xml', stili)
        for i, (nome, righe, larghezze, intest) in enumerate(fogli):
            z.writestr(f'xl/worksheets/sheet{i + 1}.xml', _foglio(righe, larghezze, set(intest)))
    return path
