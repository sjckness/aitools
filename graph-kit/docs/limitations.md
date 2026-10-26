# Limitazioni note

## Hook
- `tool_input` di MultiEdit: la doc hooks non lo descrive; non fare affidamento su campi di MultiEdit (usare `file_path` solo come best effort).
- `tool_response` per Read, Grep, Glob, Edit: schema non documentato; non parsarlo.
- Flag di errore in `tool_response` di PostToolUse: non esiste; PostToolUse scatta solo su successo, gli errori arrivano via PostToolUseFailure con `error` a formato non stabile (solo la prima riga `Exit code N` e' indicata come chiave).
- `agent_id`/`agent_type` nel thread principale: documentati come presenti dentro un subagente o con `--agent`; assenza nel thread principale non garantita esplicitamente.
- Stdout in chiaro su Pre/PostToolUse: non e' iniettato nel contesto dell'agente; serve JSON `additionalContext`.
- `${CLAUDE_PLUGIN_ROOT}` nella shell Bash dei subagenti: la doc hooks lo documenta solo per i processi hook. L'orchestratore risolve gli script allo Step 0 e li passa nel prompt (`script: <abs>`), con ripiego `${CLAUDE_PLUGIN_ROOT}/scripts`, `~/.claude/aitools-scripts`, `.claude/aitools-scripts`.

## Frontmatter degli agenti
Tutti i campi richiesti (`name`, `description`, `tools`, `model`, `model: fable`, `model: inherit`, `effort`, `effort: xhigh`, `effort: max`, `maxTurns`, `omitClaudeMd`) sono documentati: nessuna riga `no`. Restano queste regole:
- `${CLAUDE_PLUGIN_ROOT}` nella shell dei subagenti: non documentato come disponibile; l'orchestratore risolve gli script allo Step 0 e li passa nel prompt (`script: <abs>`); senza quella riga gli agenti ripiegano su `${CLAUDE_PLUGIN_ROOT}/scripts` (se non vuota), `~/.claude/aitools-scripts/`, `.claude/aitools-scripts/`.
- `effort: xhigh` e `effort: max`: documentati ma "dipendono dal modello"; se il modello non li supporta si usa il livello documentato piu' vicino (`high`).
- Campi non documentati: non vanno nel frontmatter (campi sconosciuti sono ignorati senza errore).

## Watchdog
- Attribuzione degradata: se `agent_id` non coincide con nessun nodo `running`, il watchdog considera solo i nodi `running` con `agent_id` vuoto: uno solo -> quello; piu' d'uno -> unione dei "Puoi modificare", secchio comune `_common` di contatori (la usage va solo ai nodi senza entry propria) e mai livello 2; nessuno -> nessuna azione. Gli agenti con `agent_type` validator, critic, reviewer o planner (anche con prefisso di plugin) e il thread principale (`agent_id` assente) sono ignorati.
- L'uguaglianza tra l'`agent_id` dell'input hook e quello restituito dal tool di lancio non e' documentata. Nella finestra tra il lancio e la scrittura di `agent_id` nel nodo, i nodi lanciati insieme condividono il secchio comune.
- Le scritture fatte via Bash (`sed -i`, redirect, `git checkout`) non sono rilevate come drift ne' come loop di ripristino.
- `install.sh` non installa hook: il watchdog funziona solo col plugin (`hooks/hooks.json`).
- Corse: state.json lo scrive solo `watchdog.py usage`, lanciato dall'orchestratore a nodo completato; il secchio comune e' attribuito a ogni nodo del secchio, quindi le somme in `metrics` possono contarlo piu' volte.
- Gli errori di tool arrivano via `PostToolUseFailure` (formato di `error` non stabile): il loop sull'errore usa i primi 300 caratteri normalizzati. `hooks.json` registra `watchdog.py post` anche su quell'evento.
- I contatori del watchdog si azzerano quando cambia `attempts` del nodo o arriva un agente nuovo (`agent_id` diverso). Il passaggio di `agent_id` da vuoto a un valore non azzera.
- Il conteggio dei comandi Bash e degli errori ripetuti riparte dopo ogni scrittura riuscita con contenuto nuovo (progresso).
