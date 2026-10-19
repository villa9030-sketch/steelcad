"""Import di uno sviluppo da DXF/DWG: analisi del file (contorni, linee di piega, anteprima) e creazione del
progetto con la lamiera piegata. I dati di piega (spessore, raggio, K) li dà l'utente: non si inventano."""
from __future__ import annotations

from pathlib import Path

from cad_engine import materials
from cad_engine.errors import SteelCADError
from cad_engine.importers import dxf_import as I


def _num(v, nome: str, obbligatorio: bool = True):
    if v in (None, ''):
        if obbligatorio:
            raise SteelCADError(f'Scrivi {nome}.', code='dato_mancante')
        return None
    try:
        return float(str(v).replace(',', '.'))
    except ValueError:
        raise SteelCADError(f'{nome[0].upper() + nome[1:]}: "{v}" non è un numero.', code='dato') from None


def _primo(*valori):
    """Il primo valore scritto (0 compreso: un angolo 0 è un errore da segnalare, non un 90)."""
    for v in valori:
        if v is not None and str(v).strip() != '':
            return v
    return None


class ImportMixin:
    _import = None                    # l'ultima Analisi letta

    def import_dxf(self, path: str) -> dict:
        """Legge il file e propone il contorno del pezzo; l'anteprima ha i giri cliccabili."""
        try:
            an = I.leggi(path)
            if not an.giri:
                raise SteelCADError('Nel disegno non ci sono contorni chiusi: non c’è uno sviluppo da importare'
                                    + (f' ({an.aperti} tratti non si chiudono).' if an.aperti else '.'), code='import')
            self._import = an
            prev = I.anteprima_svg(an)
            out = {'file': str(Path(path)), 'name': Path(path).stem, 'svg': prev['svg'], 'giri': prev['giri'],
                   'scelto': an.scelto, 'spessore': an.spessore, 'materiale': an.materiale, 'aperti': an.aperti,
                   'pieghe_tot': len(an.pieghe), 'materiali': [{'code': m.code, 'name': m.description}
                                                              for m in materials.CATALOG.values()],
                   'rules': self._rules()}
            if an.scelto is not None:
                out['giro'] = self._info_giro(an, an.scelto)
            return {'ok': True, **out}
        except SteelCADError as ex:
            return {'ok': False, 'message': ex.message}
        except Exception as ex:  # noqa: BLE001
            from app.service import _err
            return _err(ex)

    @staticmethod
    def _info_giro(an, giro: int) -> dict:
        utili = I.pieghe_utili(an, giro)
        g = an.giri[giro]
        xs, ys = [p[0] for p in g.poligono], [p[1] for p in g.poligono]
        return {'index': giro, 'size': [max(xs) - min(xs), max(ys) - min(ys)], 'tagli': len(I.tagli(an, giro)),
                'pieghe': [an.pieghe.index(t) for t in utili],
                'lunghezze': [round(((t.dati[1][0] - t.dati[0][0]) ** 2 + (t.dati[1][1] - t.dati[0][1]) ** 2) ** .5, 2) for t in utili]}

    def _giro(self, giro) -> int:
        try:
            g = int(giro)
        except (TypeError, ValueError):
            g = -1
        if not 0 <= g < len(self._import.giri):
            raise SteelCADError('Quel contorno non c’è.', code='giro')
        return g

    def import_dxf_giro(self, giro: int) -> dict:
        if self._import is None:
            return {'ok': False, 'message': 'Prima scegli il file da importare.'}
        try:
            return {'ok': True, 'giro': self._info_giro(self._import, self._giro(giro))}
        except SteelCADError as ex:
            return {'ok': False, 'message': ex.message}
        except Exception as ex:  # noqa: BLE001
            from app.service import _err
            return _err(ex)

    def import_dxf_create(self, giro: int, params: dict) -> dict:
        """Crea il progetto dal contorno scelto. params: name, material, thickness, radius, method, k, bd90,
        angle, direction, bends [{angle, direction}] (una per linea di piega utile, nello stesso ordine)."""
        if self._import is None:
            return {'ok': False, 'message': 'Prima scegli il file da importare.'}
        try:
            p = self._con_default(params or {}, ('radius', 'k', 'bd90'))
            metodo = p.get('method') or 'k'
            doc, rep = I.costruisci(
                self._import, self._giro(giro), _num(p.get('thickness'), 'lo spessore'), _num(p.get('radius'), 'il raggio interno di piega'),
                _num(p.get('k'), 'il K-factor', metodo == 'k'), p.get('material') or 'S235', (p.get('name') or '').strip(),
                _num(_primo(p.get('angle'), 90), 'l’angolo'), p.get('direction') or 'up',
                [{'angle': _num(_primo(b.get('angle'), p.get('angle'), 90), 'l’angolo'), 'direction': b.get('direction') or p.get('direction') or 'up'}
                 for b in (p.get('bends') or [])],
                metodo, _num(p.get('bd90'), 'la deduzione a 90°', metodo == 'bd90'))
            doc.meta['importato_da'] = self._import.file
            self._set(doc)
            self.path = None
            self.blank = False
            self.asm = None
            self._asm_ritorno = None
            msg = (f'Importato: {rep["flange"]} flange da {rep["pieghe"]} linee di piega.' if rep['flange']
                   else 'Importato come lamiera piana.')
            return {'ok': True, 'state': self.state(), 'message': msg, 'avvisi': rep['avvisi'],
                    'area_dxf': rep['area_dxf'], 'area_pezzo': rep['area_pezzo']}
        except SteelCADError as ex:
            return {'ok': False, 'message': ex.message}
        except Exception as ex:  # noqa: BLE001
            from app.service import _err
            return _err(ex)
