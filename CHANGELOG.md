# Changelog

## 0.3.1 — 2026-10-26 · rebranding sjck
- Marketplace `sjck` (repo `sjckness/sjckAI-tools`); plugin `graph-kit` → `sjck-graph`, `project-onboard` → `sjck-onboard`.
- Comandi: `/sjck-run`, `/sjck-plan`, `/sjck-status`, `/sjck-view`, `/sjck-eval`, `/sjck-onboard`.
- Skill: `sjck-orchestration`, `sjck-planning`, `sjck-onboarding`. Agenti: `sjck-planner`, `sjck-scout`, `sjck-implementer`, `sjck-validator`, `sjck-reviewer`, `sjck-critic` (niente conflitti con agenti di altri plugin).
- Cartella di lavoro `.sjck/` al posto di `.graph/`; script installati in `~/.claude/sjck-scripts`; variabili `SJCK_REPO`, `SJCK_REF`.
- Watchdog: riconosce i ruoli degli agenti anche con il prefisso `sjck-`.
- Migrazione: `/plugin uninstall graph-kit@aitools` e `project-onboard@aitools`, poi `/plugin marketplace add sjckness/sjckAI-tools` e installa i nuovi. Un run in corso in `.graph/` si riprende rinominando la cartella in `.sjck/`.

## 0.3.0 — 2026-10-26
- graph-kit: schema di stato v0.3 (`docs/state-schema.md`) con validazione in `scripts/state_schema.py`.
- graph-kit: plan score del DAG (`scripts/plan_score.py`): larghezza per livello, percorso critico, overlap di file, token per card; `reject` (exit 1) impedisce l'avvio ed è rilanciato sui nodi aggiunti a run avviato.
- graph-kit: watchdog a hook (livelli 1-2 nel plugin, livello 3 all'orchestratore); blocca le scritture fuori dai `files` della card. Attribuzione per `agent_id`; gli `agent_type` validator, critic, reviewer, planner sono ignorati; il ciclo modifica→test non scala (le scritture con contenuto nuovo azzerano i contatori di comandi ed errori). La usage è in `watchdog_state.json` e `watchdog.py usage` la copia in `state.json` a nodo completato.
- graph-kit: la skill risolve gli script allo Step 0 e li passa agli agenti con `script: <abs>`; exit 2 di plan_score = stato illeggibile o script mancante; il livello 3 "rimanda" non blocca il run; nelle sessioni non interattive niente domande (findings in backlog `deferred`, altrimenti run `failed`).
- graph-kit: findings (`.graph/findings.jsonl`, `scripts/findings.py`) con backlog e checkpoint a fine livello; `assumptions` nell'out JSON degli agenti.
- graph-kit: agente `critic` read-only (model `fable`, effort `high`) che approva o contesta piani e findings senza leggere codice.
- graph-kit: `model`, `effort` e budget per nodo.
- Eval harness `evals/` e comando `/graph-eval`: usa il plugin del checkout (`--plugin-dir`) e permessi non interattivi di default (`--no-default-flags` per toglierli).
- `install.sh`: copia solo file regolari; crea il `.bak` solo se l'utente ha modificato il file installato.
- graph-kit: il Run Viewer della 0.2.1 integrato con i campi v0.3 (modello/effort, budget, usage live da `watchdog_state.json`, eventi del watchdog, critico, plan score); `graph_view.collect()` prepara e pulisce i dati, il rendering avviene nel browser.
- Integrati anche `/graph-plan` (0.2.2) e la demo `examples/demo/`.
- graph-kit: `docs/limitations.md` con le limitazioni note.

### Limiti noti / da fare
- `attempts` conta ancora i fail del validator e le riprese "rispondi"; contatore `resumes` separato non introdotto (findings[8]).
- Il campo `findings` di `.val.json`/`REVIEW.json` non è rinominato; la risposta del critic non ha `assumptions` (findings[9], spec_gaps[1]).
- `view.html` non si rigenera sulle scritture di watchdog.py, plan_score.py, findings.py (findings[10]).
- `install.sh` non copia `docs/` (state-schema.md, limitations.md) citati dalla skill (findings[12] punto 3).
- Nodi in worktree: l'out JSON resta nel worktree e il validator non ha Write per `.val.json` (findings[14]).
- Eval: nessun esito per trap (rabbit_hole, out_of_scope_bug); compare.py vede solo i totali (spec_gaps[4]).
- Tra il lancio e la scrittura di `agent_id` i nodi lanciati insieme condividono il secchio comune; l'uguaglianza tra `agent_id` dell'hook e del tool di lancio non è documentata (residuo di spec_gaps[3]).
- Formato di REVIEW.json in reviewer.md (`pass|fail`, findings stringhe) diverso da quello usato nell'ultima review (`ok|issues`, oggetti, `spec_gaps`, `checks`).

## 0.2.2 — 2026-10-26
- Nuova skill e comando `/graph-plan`: pianificazione guidata con domande mirate, alternative con stime di token e tempo, checklist di ottimizzazione e piano `planned` pronto per `/run-graph`.
- `graph-orchestration` esegue un piano `planned` senza rifare triage e planner, rispettando modello, effort e budget per nodo; per task grandi e vaghe suggerisce `/graph-plan`.
- Run Viewer: stato `planned` in ambra.

## 0.2.1 — 2026-10-26
- Nuovo Run Viewer (`.graph/view.html`): una pagina con viste Grafo, Token e Findings, tema scuro, leggibile da telefono, nessuna libreria esterna (niente più Mermaid).
- Il viewer legge in modo opzionale `tokens.json`, `token-report.json`, `findings.jsonl` e `watchdog.jsonl`; con uno stato v0.2 mostra solo il grafo.
- Scrittura atomica della pagina; si ricarica da sola solo mentre il run è in corso.
- Demo in `examples/demo/` e README con screenshot.

## 0.2.0 — 2026-10-26
- graph-kit: la logica è ora una skill (`graph-orchestration`) che Claude attiva da solo per task grandi; `/run-graph` resta come scorciatoia.
- graph-kit: override dell'utente su modalità e agenti (`--mode M`, "usa solo implementer e validator").
- graph-kit: stato in `.graph/state.json`; visualizzatore live `.graph/view.html` aggiornato da hook, comando `/graph-view`.
- Nuovo plugin `project-onboard`: `/onboard` genera CLAUDE.md compatto + `.claude/map/<modulo>.md`.

## 0.1.0 — 2026-10-26
- Prima versione: triage S/M/L, planner, scout, implementer, validator, reviewer.
- Stato persistente in `.graph/state.yaml` con ripresa automatica.
- Installazione come plugin Claude Code o via `install.sh`.
