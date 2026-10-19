"""Tavole dal servizio: anteprima ed esportazione (PDF, DXF) del pezzo, dello sviluppo e dell'assieme.

I dati fissi del cartiglio (azienda, disegnatore) si ricordano in un file accanto ai recenti; numero disegno e
revisione si salvano nel progetto (meta["disegno"]).
"""
from __future__ import annotations

import json
from pathlib import Path

from cad_engine import drawings as D
from cad_engine.errors import SteelCADError

FISSI = ('azienda', 'disegnatore')


def _file_cartiglio() -> Path:
    from app.service import _recent_file
    return _recent_file().with_name('cartiglio.json')


def _leggi_fissi() -> dict:
    try:
        return {k: str(v) for k, v in json.loads(_file_cartiglio().read_text(encoding='utf-8')).items() if k in FISSI}
    except (OSError, ValueError):
        return {}


def _scrivi_fissi(d: dict):
    try:
        f = _file_cartiglio()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({k: d.get(k, '') for k in FISSI}, ensure_ascii=False, indent=1), encoding='utf-8')
    except OSError:
        pass


class DrawingsMixin:
    def drawing_fields(self) -> dict:
        """I campi del cartiglio da proporre: i fissi ricordati + quelli del progetto."""
        out = {'azienda': '', 'disegnatore': '', 'numero': '', 'revisione': 'A', 'note': '', 'formato': 'A3'}
        out.update(_leggi_fissi())
        if self.asm is None:
            out.update({k: v for k, v in (self.doc.meta.get('disegno') or {}).items() if k in out})
        return {'ok': True, 'fields': out, 'assembly': self.asm is not None}

    def _campi_pezzo(self, doc, result, campi: dict, n: int, tot: int) -> dict:
        from cad_engine.analysis import properties
        sheet = getattr(result.body, 'sheet', None) if result.body is not None else None
        massa = properties(result.body.shape, doc.material)['mass_kg'] if result.body is not None else 0
        sp = f'sp. {D.fmt(sheet.thickness)} mm · ' if sheet else ''
        return {**campi, 'titolo': doc.meta.get('name') or 'Pezzo', 'materiale': doc.material,
                'spessore_massa': f'{sp}{D.fmt(round(massa, 3))} kg', 'data': D.oggi(), 'foglio': f'{n}/{tot}'}

    def _fogli_struttura(self, doc, result, campi: dict, formato: str, n0: int = 1, tot: int | None = None) -> list:
        """Una struttura in tubolare: le viste dell'insieme con gli ingombri, poi la distinta di taglio."""
        from OCP.BRep import BRep_Builder
        from OCP.TopoDS import TopoDS_Compound
        from cad_engine.structures import cut_list
        forma = TopoDS_Compound()
        b = BRep_Builder()
        b.MakeCompound(forma)
        for st in result.structures:
            for m in st.members:
                b.Add(forma, m.solid.wrapped)
        cl = cut_list(result.structures)
        tot = tot or 2
        base = {**campi, 'titolo': doc.meta.get('name') or 'Struttura', 'materiale': doc.material,
                'spessore_massa': f'{D.fmt(round(cl["kg"], 2))} kg', 'data': D.oggi()}
        fogli = [D.tavola_pezzo(forma, {**base, 'foglio': f'{n0}/{tot}'}, {}, formato)]
        righe = [[str(i), r['profile'], D.fmt(r['length_mm']), ' / '.join(r['cuts']), str(r['qty']),
                  ', '.join(r['groups']), D.fmt(round(r['kg_each'], 2)), D.fmt(round(r['kg_total'], 2))]
                 for i, r in enumerate(cl['rows'], 1)]
        totali = [[t['profile'], str(t['pieces']), D.fmt(round(t['total_length_mm'] / 1000, 2)), D.fmt(round(t['kg'], 2))]
                  for t in cl['totals']]
        fogli.append(D.tavola_taglio({**base, 'titolo': base['titolo'] + ' — distinta di taglio',
                                      'foglio': f'{n0 + 1}/{tot}'}, righe, totali, formato))
        return fogli

    def _fogli_pezzo(self, doc, result, campi: dict, formato: str, n0: int = 1, tot: int | None = None) -> list:
        if result.body is None and result.structures and any(st.members for st in result.structures):
            return self._fogli_struttura(doc, result, campi, formato, n0, tot)
        if result.body is None:
            raise SteelCADError('Il progetto non ha un pezzo da mettere in tavola.')
        sheet = getattr(result.body, 'sheet', None)
        tot = tot or (2 if sheet else 1)
        fogli = [D.tavola_pezzo(result.body.shape, self._campi_pezzo(doc, result, campi, n0, tot), D.etichette_fori(doc), formato)]
        if sheet is not None and getattr(sheet, 'bend_rows', None) is not None:
            r_, k_ = sheet.tech.get('radius'), sheet.tech.get('k')
            pieg = [[str(x['n']), f'P{x["n"]}', D.fmt(round(x['length'], 1)), f'{D.fmt(round(x["angle"], 2))}°', '—',
                     D.fmt(r_) if r_ is not None else '', D.fmt(k_) if k_ is not None else '',
                     D.fmt(round(x['correction'], 3)) if x['correction'] is not None else ''] for x in sheet.bend_rows]
            c = self._campi_pezzo(doc, result, campi, n0 + 1, tot)
            c['titolo'] = c['titolo'] + ' — sviluppo'
            fogli.append(D.tavola_sviluppo(sheet, c, pieg, formato))
        elif sheet is not None:
            pieg = [[str(i), g.fid, D.fmt(g.length), f'{D.fmt(g.bend.angle)}°', 'su' if g.direction == 'up' else 'giù',
                     D.fmt(g.bend.r), D.fmt(round(g.bend.k, 3)), D.fmt(round(g.u1 - g.u0, 2))] for i, g in enumerate(sheet.flanges, 1)]
            c = self._campi_pezzo(doc, result, campi, n0 + 1, tot)
            c['titolo'] = c['titolo'] + ' — sviluppo'
            fogli.append(D.tavola_sviluppo(sheet, c, pieg, formato))
        return fogli

    def _fogli(self, campi: dict, tutte: bool = False) -> list:
        formato = campi.get('formato') if campi.get('formato') in D.FORMATI else 'A3'
        if self.asm is None:
            return self._fogli_pezzo(self.doc, self.result, campi, formato)
        from cad_engine import assembly as A
        righe = A.bom(self.asm, self.asm_parts)
        pos = {r['file']: k + 1 for k, r in enumerate(righe)}
        forme = [(pos[i['file']], A.placed_shape(self.asm_parts[i['file']], i['R'], i['T']))
                 for i in self.asm.instances if i['file'] in self.asm_parts]
        if not forme:
            raise SteelCADError('L’assieme è vuoto.')
        distinta = [[str(k + 1), r['name'], str(r['qty']), r['material'], f'{D.fmt(r["thickness"])} mm' if r['thickness'] else '',
                     D.fmt(round(r['mass_tot'], 3))] for k, r in enumerate(righe)]
        def fogli_di(part):         # lamiera: pezzo + sviluppo; struttura: viste + distinta di taglio
            res = part.result
            return 2 if getattr(res.body, 'sheet', None) or (res.body is None and res.structures) else 1
        tot_pezzi = sum(fogli_di(self.asm_parts[r['file']]) for r in righe) if tutte else 0
        tot = 1 + tot_pezzi
        massa = sum(r['mass_tot'] for r in righe)
        ca = {**campi, 'titolo': self.asm.name, 'materiale': ', '.join(sorted({r['material'] for r in righe})),
              'spessore_massa': f'{D.fmt(round(massa, 3))} kg', 'data': D.oggi(), 'foglio': f'1/{tot}'}
        fogli = [D.tavola_assieme(forme, ca, distinta, formato)]
        if tutte:
            n = 2
            for k, r in enumerate(righe):
                p = self.asm_parts[r['file']]
                cp = {**campi, 'numero': f'{campi.get("numero") or self.asm.name}-{k + 1}'}
                nuovi = self._fogli_pezzo(p.doc, p.result, cp, formato, n, tot)
                n += len(nuovi)
                fogli += nuovi
        return fogli

    def drawing_preview(self, campi: dict | None = None, tutte: bool = False) -> dict:
        try:
            fogli = self._fogli(campi or self.drawing_fields()['fields'], tutte)
            return {'ok': True, 'sheets': [{'title': f.titolo, 'svg': D.to_svg(f), 'size': f.size} for f in fogli]}
        except SteelCADError as ex:
            return {'ok': False, 'message': ex.message}

    def export_drawings(self, path: str, campi: dict, tutte: bool = False) -> dict:
        """PDF (una pagina per foglio) o DXF (fogli affiancati), secondo l'estensione."""
        try:
            fogli = self._fogli(campi, tutte)
            p = Path(path)
            if p.suffix.lower() == '.dxf':
                D.to_dxf(fogli, p)
            else:
                if p.suffix.lower() != '.pdf':
                    p = p.with_suffix('.pdf')
                D.to_pdf(fogli, p)
            _scrivi_fissi(campi)
            if self.asm is None:
                self.doc.meta['disegno'] = {k: campi.get(k, '') for k in ('numero', 'revisione', 'note', 'formato')}
            return {'ok': True, 'path': str(p), 'message': f'Tavole salvate: {len(fogli)} fogli in {p.name}.'}
        except SteelCADError as ex:
            return {'ok': False, 'message': ex.message}
