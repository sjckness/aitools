# Findings e checkpoint

Script: vedi reference/scripts.md. File: `.graph/findings.jsonl`, `.graph/backlog.md`.
Un finding è una cosa notata ma fuori scope per il nodo (la sezione `## Fuori scope`
della card dice cosa non sistemare: va annotato, non toccato).

## Registrazione
- Agenti con Bash: `findings.py add --from <ID> --file P [--line N] --kind bug|smell|debt|doc|loop --severity high|med|low --what T [--fix T]`.
- Agenti senza Bash (scout, planner): mettono `findings` nell'out JSON
  (anche `.graph/out/PLAN.json`); li registri tu con `findings.py add --from <ID>`.
- Aggiorna `metrics.findings`.

## Checkpoint (a fine di OGNI livello del DAG)
1. `findings.py dedupe`; `findings.py list --status open`. Nessun finding → nessun checkpoint.
2. Proponi un posizionamento per ognuno (`set ID proposed --placement P`):
   - `card:<ID>` → aggiungilo a "Correzioni richieste" di un nodo `pending`;
   - `node:<nuovo ID>` → crea un nodo nuovo (card + state.json, rispetta le regole del DAG:
     deps = nodi `validated` con files in overlap); rilancia `plan_score`, `reject` → non avviarlo;
   - `backlog` → rimandato.
   Un finding può anche essere `rejected` (open→rejected) se è rumore.
3. Critico, punto `findings` (reference/critic.md).
4. Sessione non interattiva (`claude -p`, o AskUserQuestion non disponibile): nessuna domanda,
   tutti i proposti → `deferred` in backlog.md, checkpoint registrato. Altrimenti approvazione dell'utente con UNA domanda a scelta multipla (tool AskUserQuestion):
   elenca i finding proposti con il posizionamento, opzioni accetta tutti / modifica / rifiuta.
5. `findings.py set ID accepted|deferred|rejected` (`deferred` per `backlog`). Transizioni:
   open→proposed|rejected; proposed→accepted|deferred|rejected; deferred→proposed
   (exit 2 se non valida).
6. Registra in `state.checkpoints`:
   `{"after_level":N,"findings_proposed":[],"accepted":[],"deferred":[],"rejected":[]}`
   e aggiorna `metrics.findings_accepted`.
7. I `deferred` vanno in `.graph/backlog.md`, una riga per finding:
   `- [F003] (T04, high) what — suggested_fix`. `backlog.md` NON si archivia.

## Eccezione
Un finding `high` che blocca nodi pianificati → checkpoint subito, senza aspettare la
fine del livello.
