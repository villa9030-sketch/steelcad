# Tavole

**Tavole** (scheda LAMIERA/PIASTRA/ASSIEME, o File → Tavole) apre l'anteprima dei fogli con i campi del cartiglio;
**Esporta PDF** (una pagina per foglio) o **Esporta DXF** (fogli affiancati, layer: contorno, nascoste, tangenti,
piega, quote, testo, cornice, cartiglio, tabella).

- **Pezzo**: vista di fronte, dall'alto (sotto) e da sinistra (a destra) in proiezione europea (ISO E), più
  un'isometrica fuori scala nello spazio libero. Linee nascoste tratteggiate. Quote d'ingombro su ogni vista; note dei
  fori raggruppate per diametro (`4× Ø8`), con filettature (`M6 (preforo Ø5)`), svasature e inserti presi dagli sketch.
  Scala normalizzata scelta da sola (10:1 … 1:50), scritta nel cartiglio.
- **Sviluppo** (lamiere): contorno, linee di piega rosse con flangia/verso/angolo/raggio, quote d'ingombro e la
  **tabella pieghe** (flangia, lunghezza esterna, angolo, verso, raggio, K, larghezza).
- **Assieme**: fronte e alto, isometrica con i **palloncini** numerati e la **distinta** (posizione, descrizione,
  quantità, materiale, spessore, peso). Con "anche le tavole di tutti i pezzi" si ottengono in un file solo
  assieme + pezzo + sviluppo di ogni componente, numerati `N-1`, `N-2`… e con i fogli `n/totale`.
- **Cartiglio** (180 × 50 in basso a destra): azienda, titolo, numero disegno, materiale, spessore/massa, disegnatore,
  data, scala, revisione, foglio, proiezione. Azienda e disegnatore si ricordano per le prossime tavole; numero,
  revisione e note si salvano nel progetto.
- Il PDF è scritto direttamente (Helvetica, vettoriale), senza librerie in più.

Limiti: quote automatiche solo d'ingombro e dei fori; niente editor della tavola (spostare/aggiungere quote) né
sezioni o dettagli ingranditi.
