# Schema di stato graph-kit v0.3

Formato di riga: `campo` — tipo — default — significato.
Validatore e default: `graph-kit/scripts/state_schema.py` (`validate`, `normalize`).
Parser delle card: `graph-kit/scripts/cards.py`.

## File in `.graph/`
- `state.json` — stato del run.
- `cards/` — una card `<ID>.md` per nodo.
- `out/` — output degli agenti (`<ID>.json`, `<ID>.val.json`, `PLAN.json`).
- `interfaces/` — interfacce condivise tra nodi.
- `archive/` — run precedenti.
- `findings.jsonl` — findings, un oggetto per riga.
- `watchdog.jsonl` — eventi del watchdog, uno per riga.
- `watchdog_state.json` — stato del watchdog; fonte di verità della usage durante il run.
- `backlog.md` — findings rimandati.

## state.json

Compatibilità: uno stato v0.2 (senza campi v0.3) è valido. I campi v0.3 sono
opzionali; se mancano valgono i default di `normalize()`. Chiavi sconosciute
sono ignorate.

### Campi v0.2
- `goal` — str — obbligatorio nella pratica — obiettivo del run.
- `mode` — "S"|"M"|"L" — - — modalità scelta.
- `mode_reason` — str — "" — motivazione in una riga.
- `status` — str (running|done|failed) — running — stato del run.
- `started` — str ISO-8601 — - — avvio.
- `nodes` — [nodo] — [] — nodi del grafo.
- `log` — [str] — [] — righe "HH:MM evento".
- `metrics` — oggetto — vedi sotto — contatori del run.
- `nodes[].id` — str — obbligatorio — id univoco.
- `nodes[].title` — str — "" — titolo.
- `nodes[].agent` — self|scout|implementer — - — chi esegue.
- `nodes[].deps` — [id] — [] — id di nodi esistenti.
- `nodes[].files` — [str] — [] — file modificabili dal nodo.
- `nodes[].status` — pending|running|done|validated|blocked|failed|done-unverified — pending — stato.
- `nodes[].attempts` — int >= 0 — 0 — tentativi di correzione.
- `nodes[].agent_id` — str — "" — id del subagente.

### Campi v0.3 del nodo
- `model` — haiku|sonnet|opus|fable|inherit — inherit — modello del nodo.
- `effort` — low|medium|high|xhigh|max — medium — effort del nodo.
- `budget` — oggetto — {tool_calls: 40, context_tokens: 2000} — limiti; interi > 0.
- `tool_calls` — int > 0 (in `budget`) — 40 — massimo di tool call del nodo.
- `context_tokens` — int > 0 (in `budget`) — 2000 — massimo di token stimati della card.
- `usage` — oggetto — 5 contatori a 0 — consumi misurati dal watchdog (fonte: `watchdog_state.json`); `nodes[].usage` è copiato da `watchdog.py usage` a nodo completato; interi >= 0.
- `tool_calls` — int >= 0 (in `usage`) — 0 — tool call effettuate.
- `reads_outside_card` — int >= 0 — 0 — letture fuori da "Leggi".
- `writes_outside_card` — int >= 0 — 0 — scritture fuori da "Puoi modificare".
- `watchdog_warnings` — int >= 0 — 0 — richiami di livello 1.
- `watchdog_stops` — int >= 0 — 0 — blocchi di livello 2.
- `assumptions` — [str] — [] — scelte "scelta — motivo" fatte dal nodo.

### Campi v0.3 dello stato
- `plan_score` — oggetto — assente (= non calcolato) — esito di `plan_score.py`.
- `width` — int >= 0 (in `plan_score`) — - — larghezza massima del DAG.
- `critical_path` — int >= 0 — - — lunghezza in nodi del percorso critico.
- `file_overlap` — int >= 0 — - — file condivisi tra nodi paralleli.
- `avg_card_tokens` — numero >= 0 — - — token medi stimati per card (`len/4`).
- `verdict` — ok|reject (in `plan_score`) — - — esito del piano.
- `reasons` — [str] — [] — motivi del rifiuto.
- `critic` — [oggetto] — [] — interventi del critico.
- `at` — plan|findings|failure (in `critic`) — - — punto d'intervento.
- `round` — 1|2 — - — round del protocollo.
- `verdict` — approve|object (in `critic`) — - — risposta del critico.
- `points` — [str] — [] — obiezioni.
- `resolution` — str — "" — come è stata risolta.
- `checkpoints` — [oggetto] — [] — checkpoint dei findings a fine livello.
- `after_level` — int >= 0 — - — livello del DAG appena concluso.
- `findings_proposed` — [id] — [] — findings proposti.
- `accepted` — [id] — [] — findings accettati.
- `deferred` — [id] — [] — findings rimandati.
- `rejected` — [id] — [] — findings rifiutati.
- `metrics` — oggetto — 8 chiavi a 0 — contatori; interi >= 0 (`duration_s` anche float).
- `subagents` — int — 0 — subagenti lanciati.
- `validator_fails` — int — 0 — validazioni fallite.
- `tool_calls` — int (in `metrics`) — 0 — tool call totali.
- `watchdog_warnings` — int (in `metrics`) — 0 — richiami totali.
- `watchdog_stops` — int (in `metrics`) — 0 — blocchi totali.
- `findings` — int (in `metrics`) — 0 — findings registrati.
- `findings_accepted` — int — 0 — findings accettati.
- `duration_s` — numero — 0 — durata in secondi.

## Card `.graph/cards/<ID>.md`
Titolo `# <ID> — <titolo>` e 6 sezioni `## `:
- `## Obiettivo` — cosa fare.
- `## Puoi modificare` — file scrivibili (un percorso per voce, tra backtick).
- `## Leggi` — file leggibili.
- `## Criteri di accettazione` — comando + esito atteso, o condizione sul diff.
- `## Fuori scope` — cosa il nodo NON deve sistemare: va annotato nei findings.
- `## Correzioni richieste` — vuota; compilata coi findings del validator.

## `.graph/out/<ID>.json`
- `id` — str — - — id del nodo.
- `status` — done|blocked|failed — - — esito.
- `changed` — [str] — [] — file toccati.
- `summary` — str — "" — max 3 righe.
- `blockers` — [str] — [] — domande precise se blocked.
- `new_interfaces` — [str] — [] — interfacce create.
- `assumptions` — [str] — [] — "scelta — motivo".
- `findings` — [obj] — assente — solo per agenti senza Bash: campi di `add` senza id/status; li registra l'orchestratore.

Il planner scrive `.graph/out/PLAN.json`.

## `.graph/findings.jsonl`
Un oggetto per riga:
- `id` — str — assegnato — "F001" progressivo.
- `from` — str — - — nodo o agente autore.
- `file` — str — - — file interessato.
- `line` — int — 0 — riga (0 = ignota).
- `kind` — bug|smell|debt|doc|loop — - — tipo.
- `severity` — high|med|low — - — gravità.
- `what` — str — - — descrizione.
- `suggested_fix` — str — "" — correzione suggerita.
- `status` — open|proposed|accepted|deferred|rejected — open — stato.
- `placement` — "" | "card:<ID>" | "node:<ID>" | "backlog" — "" — dove va gestito.
- `duplicates` — [id] — [] — id uniti da `dedupe`.

Transizioni valide: open→proposed|rejected; proposed→accepted|deferred|rejected; deferred→proposed.

### CLI `findings.py` (contratto; implementata da un altro nodo)
- `findings.py [--cwd DIR] add --from ID --file PATH [--line N] --kind K --severity S --what TEXT [--fix TEXT]` — stampa l'id, exit 0; valori non validi → exit 2.
- `findings.py dedupe` — stampa il numero di record uniti.
- `findings.py set ID STATUS [--placement P]` — exit 2 se la transizione non è valida.
- `findings.py list [--status S]` — array JSON.
- Senza `--cwd` la radice è `find_graph_root(cwd)`.

## `.graph/watchdog.jsonl`
Un evento per riga:
- `ts` — str ISO-8601 — - — istante.
- `node` — str — - — id del nodo.
- `tool` — str — - — tool coinvolto.
- `kind` — loop|drift_write|drift_read|budget — - — pattern.
- `level` — 1|2 — - — livello di escalation.
- `action` — warn|block|count — - — azione presa.
- `detail` — str (max 200 caratteri) — "" — dettaglio.
