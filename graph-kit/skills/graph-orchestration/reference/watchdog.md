# Watchdog (hook del plugin) e livello 3

Gli hook `watchdog.py pre|post` misurano ogni nodo `running` e scrivono eventi in `.graph/watchdog.jsonl` e contatori
in `watchdog_state.json`; NON scrivono state.json. A nodo completato lanci tu
`python3 "<script>"/watchdog.py usage --cwd "$PWD"`, che porta `usage` in state.json.
- Livello 1: richiamo all'agente (`watchdog_warnings` += 1), non blocca.
- Livello 2: pattern ripetuto dopo il livello 1, o budget > 125%: le tool call del
  nodo sono negate (restano permessi l'out JSON e `findings.py add`); `watchdog_stops` += 1.
  L'agente chiude `blocked`.
- Senza plugin (install.sh) il watchdog non c'è. Limiti noti: docs/limitations.md
  (Bash non rilevato; attribuzione degradata con più nodi running).

## Livello 3 (tocca a te)
Un nodo chiuso `blocked` dopo un livello 2 (evento in `.graph/watchdog.jsonl` per quel
nodo, oppure `usage.watchdog_stops > 0`). Scegli UNA via e annotala nel `log`:
- rimanda: nuovo nodo N `pending` (card più stretta; deps = nodi `validated` con files in
  overlap con N); vecchio nodo O: `deps += [N]`, `status: pending`, `agent_id: ""`, rimando a N in
  "Correzioni richieste", `attempts` invariato. O riparte con un agente nuovo (contatori nuovi).
  Rilancia plan_score: `reject` → non avviarli;
- rispondi: scrivi la risposta in `## Correzioni richieste` e riprendi lo STESSO agente
  con SendMessage (attempts += 1);
- ripianifica: lancia il planner sui nodi rimanenti.
Se nessuna è praticabile → utente (e, per `failed`, critico `failure` prima).

## Metriche
A nodo completato lanci `watchdog.py usage --cwd "$PWD"`: scrive `nodes[].usage` e in `metrics`
`tool_calls`, `watchdog_warnings`, `watchdog_stops` come somme; poi rileggi state.json.
I contatori di un nodo si azzerano quando cambia `attempts` o l'`agent_id` (agente nuovo);
da `agent_id` vuoto a un valore restano. Il nodo si attribuisce per `agent_id`.
