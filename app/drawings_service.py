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
        out = {'azienda': '', 'disegnatore': '', 'numero': '', 'revisione': 'A', 'note': '', 'formato': 'A3',
               'scala_fissa': 'auto', 'quote_fori': 'sì'}
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
        # le file di aste uguali a passo costante (sbarre, ripiani): per gruppo, parallele
        file = []
        for st in result.structures:
            gruppi = {}
            for m in st.members:
                d = (m.end - m.start).normalized()
                chiave = (m.group, round(abs(d.X), 3), round(abs(d.Y), 3), round(abs(d.Z), 3), round(m.length, 1))
                gruppi.setdefault(chiave, []).append(((m.start + m.end) * 0.5, m))
            for (gruppo, *_), lista in gruppi.items():
                if len(lista) >= 3:
                    m0 = lista[0][1]
                    file.append({'assi': [(p.X, p.Y, p.Z) for p, _ in lista], 'nome': gruppo or 'aste',
                                 'profilo': m0.profile.name, 'larghezza': min(m0.profile.width, m0.profile.height)})
        fogli = [D.tavola_pezzo(forma, {**base, 'foglio': f'{n0}/{tot}'}, {}, formato, file_passo=file)]
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
        sezione = str(campi.get('sezione') or '').upper()
        sezione = sezione if sezione in ('X', 'Y') else ''
        tot = tot or ((2 if sheet else 1) + (1 if sezione else 0))
        fogli = [D.tavola_pezzo(result.body.shape, self._campi_pezzo(doc, result, campi, n0, tot), D.etichette_fori(doc), formato,
                                quote_mano=doc.meta.get('quote') or [])]
        if sezione:
            c = self._campi_pezzo(doc, result, campi, n0 + 1, tot)
            c['titolo'] = c['titolo'] + ' — sezione A-A'
            fogli.append(D.tavola_sezione(result.body.shape, c, sezione, formato))
            n0 += 1
        if sheet is not None and getattr(sheet, 'bend_rows', None) is not None:
            r_, k_ = sheet.tech.get('radius'), sheet.tech.get('k')
            pieg = [[str(x['n']), x.get('label') or f'P{x["n"]}', D.fmt(round(x['length'], 1)), f'{D.fmt(round(x["angle"], 2))}°', x.get('verso', '—'),
                     D.fmt(r_) if r_ is not None else '', D.fmt(k_) if k_ is not None else '',
                     D.fmt(round(x['correction'], 3)) if x['correction'] is not None else ''] for x in sheet.bend_rows]
            c = self._campi_pezzo(doc, result, campi, n0 + 1, tot)
            c['titolo'] = c['titolo'] + ' — sviluppo'
            fogli.append(D.tavola_sviluppo(sheet, c, pieg, formato))
        elif sheet is not None:
            pieg = [[str(i), g.fid, D.fmt(g.length), f'{D.fmt(g.bend.angle)}°', 'su' if g.direction == 'up' else 'giù',
                     D.fmt(g.bend.r), D.fmt(round(g.bend.k, 3)), D.fmt(round(g.u1 - g.u0, 2))] for i, g in enumerate(sheet.in_ordine(), 1)]
            c = self._campi_pezzo(doc, result, campi, n0 + 1, tot)
            c['titolo'] = c['titolo'] + ' — sviluppo'
            fogli.append(D.tavola_sviluppo(sheet, c, pieg, formato))
        return fogli

    def _fogli(self, campi: dict, tutte: bool = False) -> list:
        """Le tavole; le stesse (progetto non cambiato, stessi campi) si ricordano: l'anteprima e poi il salvataggio
        le facevano due volte (22/10: «perché ci vuole così tanto a crearle»)."""
        chiave = (getattr(self, 'scene_version', 0), id(getattr(self, 'asm', None)), id(getattr(self, 'result', None)),
                  json.dumps(campi, sort_keys=True, default=str), bool(tutte))
        gia = getattr(self, '_tavole_fatte', None)
        if gia is not None and gia[0] == chiave:
            return gia[1]
        # impaginate sempre in A2 e poi scalate tali e quali sul foglio scelto
        formato = campi.get('formato') if campi.get('formato') in D.FORMATI else 'A3'
        fogli = [D.in_formato(f, formato) for f in self._fogli_nuovi({**campi, 'formato': 'A2'}, tutte)]
        self._tavole_fatte = (chiave, fogli)
        return fogli

    def _fogli_nuovi(self, campi: dict, tutte: bool = False) -> list:
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
        distinta = [[str(k + 1), (f'{r["acquisto"].get("descrizione") or r["name"]} (acquisto'
                                   + (f', {r["acquisto"]["codice"]}' if r['acquisto'].get('codice') else '') + ')')
                     if r.get('acquisto') else r['name'], str(r['qty']), '—' if r.get('acquisto') else r['material'],
                     f'{D.fmt(r["thickness"])} mm' if r['thickness'] and not r.get('acquisto') else '',
                     D.fmt(round(r['mass_tot'], 3))] for k, r in enumerate(righe)]
        def fogli_di(part):         # lamiera: pezzo + sviluppo; struttura: viste + distinta di taglio
            res = part.result
            return 2 if getattr(res.body, 'sheet', None) or (res.body is None and res.structures) else 1
        tot_pezzi = sum(fogli_di(self.asm_parts[r['file']]) for r in righe if not r.get('acquisto')) if tutte else 0
        esploso = len(forme) > 1                       # la vista esplosa: come si monta
        tot = 1 + int(esploso) + tot_pezzi
        massa = sum(r['mass_tot'] for r in righe)
        ca = {**campi, 'titolo': self.asm.name, 'materiale': ', '.join(sorted({r['material'] for r in righe if not r.get('acquisto')})),
              'spessore_massa': f'{D.fmt(round(massa, 3))} kg', 'data': D.oggi(), 'foglio': f'1/{tot}'}
        fogli = [D.tavola_assieme(forme, ca, distinta, formato)]
        if esploso:
            ce = {**ca, 'titolo': f'{self.asm.name} — esploso', 'foglio': f'2/{tot}'}
            fogli.append(D.tavola_esploso(forme, ce, distinta, self._ordine_montaggio(pos), formato,
                                          figli=self._viti_esploso()))
        if tutte:
            n = 2 + int(esploso)
            for k, r in enumerate(righe):
                if r.get('acquisto'):
                    continue                           # si compra: niente disegno
                p = self.asm_parts[r['file']]
                cp = {**campi, 'numero': f'{campi.get("numero") or self.asm.name}-{k + 1}'}
                nuovi = self._fogli_pezzo(p.doc, p.result, cp, formato, n, tot)
                n += len(nuovi)
                fogli += nuovi
        return fogli

    def _viti_esploso(self) -> list:
        """Per la vista esplosa, per ogni copia (nell'ordine delle forme): None, oppure (indice del pezzo in cui va,
        direzione in cui si sfila, quanto) per i pezzi piccoli infilati in un foro (foro su foro, cono su cono):
        viti, perni, boccole. Si sfilano dalla parte della testa (la parte più larga)."""
        import numpy as np

        from cad_engine import assembly as A
        ist = [i for i in self.asm.instances if i['file'] in self.asm_parts]
        indice = {i['id']: k for k, i in enumerate(ist)}
        dim = {}
        for i in ist:
            sh = A.placed_shape(self.asm_parts[i['file']], i['R'], i['T'])
            b = sh.bounding_box()
            dim[i['id']] = (max(b.size.X, b.size.Y, b.size.Z), sh)
        out = [None] * len(ist)
        for i in ist:
            # bloccati su un pezzo più grande (lamelle saldate nell'anta): nell'esploso vanno insieme a lui
            blocco = next((m for m in self.asm.mates if not m.get('off') and m['type'] == 'blocca'
                           and i['id'] in (m['a']['inst'], m['b']['inst'])
                           and (m['b']['inst'] if m['a']['inst'] == i['id'] else m['a']['inst']) in indice
                           and dim[i['id']][0] < dim[m['b']['inst'] if m['a']['inst'] == i['id'] else m['a']['inst']][0]), None)
            if blocco is not None:
                altro = blocco['b']['inst'] if blocco['a']['inst'] == i['id'] else blocco['a']['inst']
                out[indice[i['id']]] = (indice[altro], [0.0, 0.0, 0.0], 0.0)
                continue
            mie = [m for m in self.asm.mates if not m.get('off') and m['type'] in ('asse', 'cono')
                   and i['id'] in (m['a']['inst'], m['b']['inst'])]
            for m in mie:
                altro = m['b']['inst'] if m['a']['inst'] == i['id'] else m['a']['inst']
                if altro not in indice or dim[i['id']][0] > 0.5 * dim[altro][0]:
                    continue                                   # non è un pezzo piccolo infilato nell'altro
                ref = m['a'] if m['a']['inst'] == altro else m['b']
                ia = self.asm.instance(altro)
                try:
                    info = A.resolve_ref(self.asm_parts[ia['file']], ref)
                except Exception:  # noqa: BLE001
                    continue
                R, T = np.array(ia['R'], dtype=float), np.array(ia['T'], dtype=float)
                p, a = R @ np.array(info['p']) + T, R @ np.array(info['n'])
                a = a / np.linalg.norm(a)
                # la testa: l'estremità dove il pezzo è più largo attorno all'asse
                pts = [np.array(tuple(v)) for v in dim[i['id']][1].vertices()]
                if not pts:
                    continue
                tt = [float(np.dot(q - p, a)) for q in pts]
                lo, hi = min(tt), max(tt)
                larg = lambda sel: max([float(np.linalg.norm((q - p) - np.dot(q - p, a) * a)) for q, t in zip(pts, tt) if sel(t)] or [0])  # noqa: E731
                verso = 1.0 if larg(lambda t: t > hi - 0.25 * (hi - lo)) >= larg(lambda t: t < lo + 0.25 * (hi - lo)) else -1.0
                out[indice[i['id']]] = (indice[altro], (a * verso).tolist(), 1.6 * dim[i['id']][0] + 15)
                break
        return out

    def _ordine_montaggio(self, pos: dict) -> list:
        """L'ordine di montaggio dagli accoppiamenti: prima il pezzo fermo e quelli attaccati a lui (come li mette a
        posto il calcolo), poi gli altri gruppi di pezzi accoppiati tra loro. Le copie uguali messe nello stesso
        modo sullo stesso pezzo (le viti) sono una riga sola, con quante sono."""
        from cad_engine import assembly as A
        ist = {i['id']: i for i in self.asm.instances}
        nome = lambda iid: f'pos. {pos.get(ist[iid]["file"], "?")} {ist[iid].get("name") or iid}'  # noqa: E731
        tipo_di = lambda iid: f'pos. {pos.get(ist[iid]["file"], "?")} {Path(ist[iid]["file"]).stem}'  # noqa: E731
        mates = [m for m in self.asm.mates if not m.get('off')]
        fatti, passi = [], []

        def dim_di(iid):
            try:
                b = self.asm_parts[ist[iid]['file']].shape
                import build123d as bd
                bb = bd.Shape.cast(b).bounding_box()
                return max(bb.size.X, bb.size.Y, bb.size.Z)
            except Exception:  # noqa: BLE001
                return 0.0

        def cresci():
            while True:
                nuovo = None
                for i in self.asm.instances:
                    if i['id'] in fatti:
                        continue
                    con = [m for m in mates if i['id'] in (m['a']['inst'], m['b']['inst'])
                           and ({m['a']['inst'], m['b']['inst']} - {i['id']}) <= set(fatti)]
                    if con:
                        nuovo = (i['id'], con)
                        break
                if nuovo is None:
                    return
                iid, con = nuovo
                fatti.append(iid)
                altri = tuple(sorted({m['a']['inst'] if m['b']['inst'] == iid else m['b']['inst'] for m in con}))
                tipi = tuple(sorted({A.MATE_TYPES.get(m['type'], m['type']) for m in con}))
                passi.append(('su', iid, altri, tipi))

        def radice(iid, testo):
            fatti.append(iid)
            passi.append(('base', iid, testo, ()))
            cresci()
        # i gruppi di pezzi accoppiati tra loro, dal più grande: si comincia dalla struttura, non da un rinforzo
        gruppo = {i['id']: i['id'] for i in self.asm.instances}

        def capo(x):
            while gruppo[x] != x:
                gruppo[x] = gruppo[gruppo[x]]
                x = gruppo[x]
            return x
        for m in mates:
            a, b = m['a']['inst'], m['b']['inst']
            if a in gruppo and b in gruppo:
                gruppo[capo(a)] = capo(b)
        gruppi = {}
        for i in self.asm.instances:
            gruppi.setdefault(capo(i['id']), []).append(i['id'])
        legami = lambda x: sum(1 for m in mates if x in (m['a']['inst'], m['b']['inst']))  # noqa: E731
        primo = True
        fisso = next((i['id'] for i in self.asm.instances if i.get('fixed')), None)
        if fisso is not None and len(gruppi.get(capo(fisso), [])) == 1:
            radice(fisso, 'è la base, sta ferma')            # il pezzo fermo per primo, anche senza accoppiamenti
            primo = False
        for membri in sorted((g for g in gruppi.values() if len(g) > 1), key=len, reverse=True):
            fermo = next((x for x in membri if ist[x].get('fixed')), None)
            r = fermo or max(membri, key=lambda x: (dim_di(x), legami(x)))
            radice(r, 'è la base' + (', sta ferma' if fermo else '') if primo else
                   'gruppo a parte: si monta a sé, poi si porta al suo posto')
            primo = False
        for i in self.asm.instances:
            if i['id'] not in fatti:
                fatti.append(i['id'])
                passi.append(('base', i['id'], 'al suo posto (senza accoppiamenti)', ()))
        # le viti: stesse copie, stesso pezzo, stessi accoppiamenti → una riga «× n»
        righe, visti = [], {}
        for kind, iid, altri, tipi in passi:
            if kind == 'su':
                chiave = (ist[iid]['file'], altri, tipi)
                if chiave in visti:
                    righe[visti[chiave]][1] += 1
                    continue
                visti[chiave] = len(righe)
                righe.append([kind, 1, iid, altri, tipi])
            else:
                righe.append([kind, 1, iid, altri, tipi])
        out = []
        for k, (kind, n, iid, altri, tipi) in enumerate(righe, 1):
            if kind == 'base':
                out.append(f'{k}. {nome(iid)}: {altri}')
            else:
                chi = f'{tipo_di(iid)} × {n}' if n > 1 else nome(iid)
                out.append(f'{k}. {chi} su {", ".join(nome(x) for x in altri)}: {", ".join(tipi)}')
        return out

    def drawing_preview(self, campi: dict | None = None, tutte: bool = False) -> dict:
        try:
            fogli = self._fogli(campi or self.drawing_fields()['fields'], tutte)
            return {'ok': True, 'sheets': [{'title': f.titolo, 'svg': D.to_svg(f), 'size': f.size} for f in fogli]}
        except SteelCADError as ex:
            return {'ok': False, 'message': ex.message}
        except Exception as ex:  # noqa: BLE001
            from app.service import _err
            return _err(ex)

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
        except Exception as ex:  # noqa: BLE001
            from app.service import _err
            return _err(ex)
