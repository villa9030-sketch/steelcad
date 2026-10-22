# Icone

Le icone SVG di questa cartella sono disegnate per SteelCAD (stile «acciaio»: pezzi in acciaio satinato, in blu
quello che fa il comando; schizzo a tratto blu con maniglie bianche; vincoli in grigio col simbolo blu).

Non si modificano a mano: si generano con

    python tools/icone_acciaio.py

che scrive `app/ui/icons_nuove/acciaio/*.svg` (da copiare qui) e la pagina di controllo `app/ui/icons_nuove/acciaio.html`.
Per un comando nuovo: aggiungere l'icona in `tools/icone_acciaio.py` con le stesse regole e rigenerare.

Fino al 23/10/2026 qui c'erano le icone di SolidCraft (MIT / Apache-2.0); sono state tutte sostituite.
