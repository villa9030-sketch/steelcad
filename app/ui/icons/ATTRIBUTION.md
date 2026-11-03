# Icone

Le icone SVG di questa cartella sono disegnate per Radius (stile «piatto», 03/11/2026): tratto da 1,75 px
arrotondato nel colore del testo (`currentColor`) e un solo dettaglio pieno nel colore di accento
(`var(--accento-icona)`: blu, o il colore della modalità nella barra dei comandi).

Non si modificano a mano: si generano con

    python tools/icone_piatte.py

che scrive questi `*.svg`, `app/ui/icone.js` (le stesse come simboli in linea: l'app le usa al posto delle
<img>) e la tavola di controllo `app/ui/icons_nuove/tavola_piatte.html`.
Per un comando nuovo: aggiungere l'icona in `tools/icone_piatte.py` con le stesse regole e rigenerare.

Prima c'erano le icone «acciaio» (tools/icone_acciaio.py, 23/10) e, fino al 23/10, quelle di SolidCraft.
