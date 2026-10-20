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
Come in AutoCAD: tra tutto quello che sta entro 11 pixel dal mouse vince il più vicino (con un piccolo
vantaggio per estremi, centri e incroci); sul punto compare il simbolo dell'aggancio (arancio) e accanto
al cursore il nome. Ogni aggancio resta un vincolo: se cambi il disegno, il punto lo segue.

| Simbolo | Aggancio | Vincolo |
|---|---|---|
| quadrato | estremo / punto esistente, origine | lo stesso punto |
| cerchio | centro di cerchio o arco | lo stesso punto |
| X | incrocio linea-linea, linea-cerchio, cerchio-cerchio | sulla linea / sul cerchio, tutti e due |
| triangolo | metà di una linea | simmetria |
| rombo | quadrante (in cima, in fondo, a destra, a sinistra) | sul cerchio + allineato al centro |
| cerchio con linea | tangente dal punto prima a un cerchio/arco (Linea) | tangenza |
| ⊥ | perpendicolare dal punto prima a una linea (Linea) | sulla linea + perpendicolare |
| clessidra | sulla linea / sulla guida / sul cerchio (solo se non c'è altro) | sulla linea / sul cerchio |
| + verde tratteggiato | puntamento: stessa X e/o stessa Y di un punto del disegno | verticale / orizzontale con quel punto |

Se non c'è niente da agganciare: orizzontale/verticale rispetto al punto prima (entro 7 pixel dalla sua
orizzontale/verticale), poi la griglia, il cui passo cambia con lo zoom. **F9** (o la casella nel pannello)
spegne e riaccende l'aggancio alla griglia: spento, il punto va esattamente dove clicchi.

Così un'asola si fa anche a mano: due cerchi, due linee dai quadranti (o tangenti, se i cerchi sono
diversi), poi Taglia le metà interne (resta un contorno chiuso con gli stessi punti).

## Come si presenta il disegno
- Gli strumenti stanno nella scheda **SKETCH** della barra in alto, che compare quando entri nel disegno.
- Nel pannello a destra (al posto delle Proprietà): in alto **dove stai disegnando**
  e **cosa fare adesso** (verde: contorni chiusi, pronto; giallo: cosa manca), poi *1 · Disegna*
  (Linea, Rettangolo, Cerchio, Offset, Quota, Seleziona, con il tasto accanto), i comandi sulla
  selezione quando c'è, *2 · Quando hai finito di disegnare* (Togli materiale / Crea lamiera…, attivi
  solo quando c'è un contorno chiuso), la legenda dei colori, Mostra il pezzo 3D ed Esci.
- Nella vista resta solo il disegno, con una riga d'aiuto in basso per lo strumento scelto; delle
  viste resta Adatta.
- Colori: blu = contorno (si taglia), grigio tratteggiato = guida, arancio = bordo del pezzo.
- Le quote si vedono sempre, anche sulle facce e sullo sviluppo (solo quelle dello sketch aperto);
  clic su una quota per cambiarla. Le distanze "all'indietro" si leggono senza il meno.
- Su una faccia: X verso destra e Y verso l'alto come la vedi, (0;0) nell'angolo in basso a sinistra
  della faccia; l'inquadratura prende la faccia intera.

## Arco, poligono, raccordo, smusso (scheda SKETCH)
- **Arco**: clic sul punto di partenza, su un punto dove passa, sul punto di arrivo. Quota: il raggio.
- **Poligono** (tasto P): il numero di lati nella casella in basso (si cambia cliccandola), poi clic sul
  centro e su un vertice. Vertici su un cerchio di costruzione, lati uguali; quote: diametro e posizione.
- **Raccordo**: clic sullo spigolo (il punto dove si incontrano due linee, anche se sta sull'origine),
  oppure, come AutoCAD, clic sulla prima e sulla seconda linea; poi il raggio nella casella + Invio.
  L'arco è tangente alle due linee, che si accorciano; quota R modificabile. Con due linee che non si
  toccano, si allungano/accorciano fino a incontrarsi (resta la parte dove hai cliccato); **raggio 0** le
  unisce in uno spigolo vivo. Resta attivo per un altro spigolo; Esc annulla la scelta.
- **Smusso**: come il raccordo, con la misura sui due lati.
- Sugli **spigoli del pezzo** (bordi arancio, disegnando su una faccia) raccordo e smusso arrotondano il
  pezzo vero: tolgono la punta o, sugli spigoli verso dentro, aggiungono materiale (vedi SHEETMETAL.md).

## Vedi attraverso (tasto V)
Disegnando su una faccia del pezzo, **Vedi attraverso** (scheda SKETCH → Vista, o tasto **V**) proietta sulla
faccia i bordi e i fori di tutte le facce parallele, dietro e davanti, in azzurro tratteggiato (il pezzo si vede in
trasparenza). Ci si aggancia come ai bordi arancio: punti, centri e quadranti dei fori, linee. Serve per riprendere
i fori di una flangia su quella di fronte (stesso asse) o per vedere cosa si toglie rifilando. Di nuovo V: le linee
proiettate spariscono, quello che hai disegnato agganciato a loro resta (i punti diventano punti fissi).
Sempre, senza bisogno di V, compaiono in arancio le sagome delle parti a pochi mm davanti alla faccia (es. la
testata di un profilo che arriva a 1 mm dalla parete).

## Asola (tasto K)
Clic sul primo centro, clic sul secondo (o scrivi l'interasse + Invio), poi muovi il mouse per la
larghezza e clicca (o scrivi la larghezza + Invio). Quote: interasse e raggio (R); le due teste
restano uguali e tangenti ai lati.

## La casella di comando
In alto nella vista, quando serve una misura, compare una casella che dice cosa scrivere: con la
Linea "lunghezza, oppure lunghezza<angolo", col Rettangolo "larghezza x altezza" (es. `100x50`), col
Cerchio "diametro", con l'Offset "distanza". Si può scrivere subito (anche senza cliccarla) o
cliccarla e cambiare il numero; Invio conferma.

## Angolo scritto e bordi del pezzo
- Con la Linea, dopo il primo punto: `100` + Invio = lunghezza nella direzione del mouse;
  `100<30` + Invio = lunghezza 100 a 30° dall'asse X (antiorario, `100<-30` orario). Accanto al
  cursore si vede sempre lunghezza e angolo. L'angolo scritto resta vincolato (guida orizzontale
  corta + quota d'angolo), anche se poi cambi la lunghezza.
- Sketch su una faccia o sullo sviluppo: i bordi del pezzo ci sono già, come guide fisse
  ("bordo del pezzo"). Ci si aggancia e ci si fa l'offset.

## Comandi sulla selezione
- **Offset** (tasto O o pulsante, anche senza niente selezionato), come in AutoCAD: in alto nella
  vista compare la casella con la distanza (l'ultima, già selezionata: scrivi sopra) → Invio → clic
  sulla linea (o sul cerchio) da copiare: una sola, quella cliccata → muovi il mouse: l'anteprima va
  dalla parte dove sei → clic. Resta attivo per un'altra linea; la distanza si cambia nella casella
  anche a metà; Esc finisce. Per un contorno intero: prima selezionalo (Seleziona, doppio clic su un
  lato), poi O. La distanza diventa un parametro (off1…).
  - ogni lato nuovo è parallelo al suo;
  - una guida corta a 90° con il segno lo tiene dalla parte scelta, quindi non si rovescia
    anche se l'originale cambia molto;
  - per i cerchi, il diametro nuovo è il diametro vecchio ± 2 × off.
- **Taglia** (tasto T), come in AutoCAD: passa col mouse sul pezzo da togliere (diventa rosso) e
  clicca. Si taglia fino alle intersezioni più vicine con tutto il resto (linee, guide, bordi del pezzo,
  cerchi, archi), da una parte e dall'altra del clic; se l'oggetto non incontra niente si cancella. Un
  cerchio tagliato diventa un arco (il diametro diventa raggio). I punti nuovi restano legati alla linea
  che ha tagliato; la lunghezza della linea tagliata, che non vale più, si toglie. Resta attivo; Esc torna
  a Seleziona.
- **Allunga** (tasto A): passa vicino all'estremità di una linea (si vede l'allungamento tratteggiato) e
  clicca: arriva alla prima linea, cerchio o arco che incontra andando dritta. Il punto resta legato a
  quello che ha raggiunto.
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
