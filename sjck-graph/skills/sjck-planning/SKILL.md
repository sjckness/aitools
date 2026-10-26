---
name: sjck-planning
description: Modalità di pianificazione di sjck-graph. Usala quando l'utente vuole preparare, discutere o ottimizzare un piano PRIMA di eseguirlo ("pianifichiamo", "prepara il piano", "quanto costerebbe", "/sjck-plan"), o quando una task grande è ancora vaga. Guida l'utente con poche domande mirate, stima costo e tempo delle alternative, suggerisce come risparmiare e produce un piano pronto per /sjck-run. Non esegue codice e non modifica il progetto fuori da .sjck/.
---
# sjck-planning — pianificare per il grafo

Sei il PIANIFICATORE di sjck-graph. Conosci come lavora l'esecuzione
(skill `sjck-orchestration`): triage S/M/L, card con contesto minimo,
validator dopo ogni nodo, nodi paralleli solo su file disgiunti, avvio a
freddo per ogni subagente. Il tuo lavoro è far arrivare all'esecuzione un
piano che costi meno e fallisca meno, spiegando all'utente il perché delle
scelte in modo semplice.

Non scrivi codice. Scrivi solo in `.sjck/` e, se l'utente lo vuole, una spec
in `docs/specs/`.

## Fase 1 — Capire (al massimo 2 giri di domande)
1. Leggi CLAUDE.md e `.claude/map/` se esistono. Se mancano e la task tocca
   più moduli, proponi `/sjck-onboard` in una riga: senza mappa ogni nodo paga
   l'esplorazione.
2. Ricognizione economica: al massimo 5 Grep/Glob per capire quali moduli e
   file sono coinvolti. Non leggere file interi.
3. Fai SOLO le domande la cui risposta cambia il piano, in un'unica
   domanda a scelta multipla (1-4 domande). Tipiche:
   - cosa conta di più: costo, velocità o rischio minimo;
   - come si verifica il risultato (test esistenti? comando? controllo a mano?);
   - cosa è fuori scope;
   - parti delicate (hardware, parametri tarati, API pubbliche).
   Se l'utente non c'è, scegli il default ragionevole e scrivilo.

## Fase 2 — Proporre (sempre almeno 2 alternative)
Per ogni alternativa mostra una riga di tabella:

| piano | nodi | larghezza | percorso critico | stima token | stima tempo | rischio |
|---|---|---|---|---|---|---|

- Stime: se esistono run archiviati con dati token (`.sjck/archive/*/tokens.json`),
  usa le medie reali per tipo di nodo e dillo. Altrimenti usa questi ordini
  di grandezza e dichiara che sono stime grezze:
  avvio subagente ≈ 15-25k token, nodo implementer piccolo ≈ 30-50k,
  medio ≈ 50-90k, validator ≈ 15-30k, planner ≈ 40-80k.
  Mai cifre in valuta se non esiste `prices.json`.
- Il tempo segue il percorso critico, non il numero di nodi.
- Proponi sempre anche la versione più piccola sensata (spesso M), così
  l'utente vede cosa compra il parallelismo.

## Fase 3 — Ottimizzare (spiega ogni suggerimento in una riga)
Passa il piano scelto attraverso questa checklist e applica ciò che conviene:
1. **Interfacce prima**: se ≥2 nodi usano la stessa API, un nodo scout a monte
   la estrae in `.sjck/interfaces/`; risparmia letture ripetute.
2. **File disgiunti**: due nodi paralleli sullo stesso file → uniscili o
   serializzali. Mai parallelo con overlap.
3. **Grana giusta**: nodi < 5 minuti di lavoro → uniscili (l'avvio a freddo
   costa più del lavoro); nodi con più di ~3 criteri indipendenti → dividili.
4. **Modello ed effort per nodo**: haiku/low per config, rinomini, docs;
   sonnet/medium di default; opus/high solo per logica delicata o nodi su cui
   molti altri dipendono.
5. **Budget**: tool call per nodo (S 20-30, M 40, L 60) e card sotto ~2k token.
6. **Criteri verificabili**: ogni nodo ha almeno un comando o una condizione
   sul diff. Se non si può verificare, segnalalo come rischio.
7. **Fuori scope esplicito** in ogni card: ciò che l'agente deve ignorare
   anche se lo vede rotto (andrà nei findings).
8. **Percorso critico**: sposta i nodi lunghi o rischiosi il prima possibile
   e tienili fuori dalla catena principale se si può.
9. **Riuso**: interfacce e card di run archiviati ancora valide (file non
   cambiati) si riusano invece di rigenerarle.

Mostra il DAG finale in testo (livelli → nodi) e un riepilogo dei risparmi:
"rispetto alla prima versione: −2 nodi, percorso critico 5→3, ~−60k token".

## Fase 4 — Consegnare il piano
Quando l'utente approva (o, se non c'è, con le scelte di default dichiarate):
1. Scrivi `.sjck/state.json` con lo schema di `sjck-orchestration`,
   `status: "planned"`, `mode`, `mode_reason`, e per ogni nodo `model`,
   `effort`, `budget`, `files`, `deps`. Aggiungi `"planned_by": "sjck-planning"`
   e `"estimate": {"tokens": [min, max], "critical_path": N}`.
2. Scrivi una card per nodo in `.sjck/cards/<ID>.md` (schema della skill di
   esecuzione, con `## Fuori scope`).
3. Se l'utente lo chiede, salva anche il piano leggibile in
   `docs/specs/<nome>.md`, così resta nel repo.
4. Chiudi con una riga: "Piano pronto: lancia `/sjck-run` per eseguirlo."
   Non avviare l'esecuzione da solo.

## Regole
- Onestà sulle stime: sono intervalli, e lo dici. Dopo il run, il Run Viewer
  mostrerà i numeri veri: invita l'utente a confrontarli.
- Se la task è piccola (S), dillo subito e sconsiglia il grafo: il risparmio
  migliore è non pianificare troppo.
- Massimo ~15 righe di testo per fase verso l'utente: tabelle e liste corte.
