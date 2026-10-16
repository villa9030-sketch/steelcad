# Disegno (modalità sketch)

Si entra da Nuovo → Da zero, da "Disegna su questa faccia" o con un clic su uno sketch nell'albero.
Vista di fronte al piano, con la griglia. In alto la barra, in basso lo stato e l'aiuto.

## Strumenti
| Tasto | Strumento | Come |
|---|---|---|
| L | Linea | clic sui punti; mentre disegni scrivi la lunghezza + Invio; clic sul primo punto per chiudere; Esc per finire |
| R | Rettangolo | due angoli |
| C | Cerchio | centro, poi il bordo o il diametro scritto |
| S | Seleziona | clic, Maiusc+clic, doppio clic = tutto il contorno, finestra trascinando, Ctrl+A |
| D | Quota | clic su linea = lunghezza; su cerchio = diametro; due punti = orizzontale/verticale/allineata; punto + linea = distanza dalla linea |
| X | Costruzione | acceso: quello che disegni diventa una guida (tratteggiata, non si taglia) |

La finestra trascinata da sinistra a destra prende ciò che sta dentro del tutto; da destra a
sinistra prende anche ciò che tocca.

## Agganci
- Punti esistenti e origine: il punto è lo stesso.
- Metà di una linea: il punto resta a metà (vincolo di simmetria).
- Incrocio di due linee: il punto resta sull'incrocio (due vincoli "sulla linea").
- Lungo una guida: il punto resta sulla guida.
- Orizzontale e verticale rispetto al punto prima.
- Griglia: il passo cambia con lo zoom.

Se sposti una guida, i fori agganciati la seguono.

## Comandi sulla selezione
- **Offset**: distanza e verso, con l'anteprima. La distanza diventa un parametro (off1…).
  - ogni lato nuovo è parallelo al suo;
  - una guida corta a 90° con il segno lo tiene dalla parte scelta, quindi non si rovescia
    anche se l'originale cambia molto;
  - per i cerchi, il diametro nuovo è il diametro vecchio ± 2 × off.
- **Specchia**: poi clic sulla linea asse (anche una guida). I punti nuovi sono simmetrici ai
  loro, quindi seguono l'originale.
- **Copia / Sposta**: clic sul punto di partenza e su quello di arrivo, oppure scrivi la distanza.
  - la copia ha le stesse quote e un passo fisso dall'originale;
  - Sposta muove solo la selezione e aggiorna le quote di posizione.
- **Serie**: colonne × righe con passo X/Y, originale compreso. I passi diventano parametri
  (px1, py1): li cambi e la serie segue.
- **↔ Costruzione**: da normale a guida e viceversa.
- **Elimina** (Canc).

## Quote
- Ogni forma nasce con le sue quote.
- Quelle doppie si tolgono da sole; una quota aggiunta a mano che è già decisa dalle altre viene
  rifiutata con il motivo.
- Delle guide si vede solo la distanza che conta; di offset e serie si vede la misura una volta sola.
