# Script e campi di stato v0.3

## Dove sono gli script
Come lo Step 0 della skill: `<script>` = prima cartella che contiene `plan_score.py`
(`test -f`), resa assoluta, tra `${CLAUDE_PLUGIN_ROOT}/scripts` (se espanso o non vuota in Bash),
`<base dir della skill>/../../scripts`, `~/.claude/aitools-scripts`, `.claude/aitools-scripts`.
Log `HH:MM script: <abs>`; nessuna → fermati. Nel prompt di OGNI agente metti `script: <abs>`.
Gli agenti con Bash usano quel valore; se manca: `${CLAUDE_PLUGIN_ROOT}/scripts` (se non vuota),
poi `~/.claude/aitools-scripts`, poi `.claude/aitools-scripts`. Python 3 standard library.

## plan_score.py
`python3 "<script>/plan_score.py" --cwd "$PWD"` — scrive `plan_score` in state.json e
stampa il JSON. Exit 0 = `ok`, 1 = `reject`, 2 = stato illeggibile o script mancante (python esce 2 se il file non esiste):
fermati, non avviare il loop, ricontrolla lo Step 0.
Rifiuta: ciclo, dep inesistente, overlap di file tra nodi paralleli, card mancante,
card oltre `budget.context_tokens`, card senza criteri.

## findings.py / watchdog.py
Vedi reference/findings.md e reference/watchdog.md.

## watchdog.py usage
`python3 "<script>"/watchdog.py usage --cwd "$PWD"` (default `--cwd .`): a nodo completato
scrive `nodes[].usage` in state.json (da watchdog_state.json) e le somme `tool_calls`,
`watchdog_warnings`, `watchdog_stops` in `metrics`; stampa `{"<id>": usage}`. Stato
illeggibile → exit 2. Dopo averlo lanciato rileggi state.json.

## Schema del nodo (aggiunte v0.3)
`model` (haiku|sonnet|opus|fable|inherit, def. inherit), `effort`
(low|medium|high|xhigh|max, def. medium), `budget` ({tool_calls:40, context_tokens:2000}),
`usage` (tool_calls, reads_outside_card, writes_outside_card, watchdog_warnings,
watchdog_stops: scritti da `watchdog.py usage`), `assumptions` ([str], copiate dall'out JSON).
Tabella indicativa (la compila il planner): scout haiku/low 20/1500; implementer facile
sonnet/medium 40/2000; medio sonnet/high 60/3000; difficile opus/high 80/4000;
validator sonnet/high 40/2000.

## Campi dello stato scritti da te
- `plan_score`: {width, critical_path, file_overlap, avg_card_tokens, verdict, reasons}.
- `critic`: [{at, round, verdict, points, resolution}] (reference/critic.md).
- `checkpoints`: [{after_level, findings_proposed, accepted, deferred, rejected}].
- `metrics`: subagents, validator_fails, tool_calls, watchdog_warnings, watchdog_stops,
  findings, findings_accepted, duration_s.
Riferimento completo: docs/state-schema.md del plugin.

## Lancio con override
Passa `model` ed `effort` del nodo come parametri del lancio (hanno priorità sul
frontmatter dell'agente; valgono anche a SendMessage). Ripieghi: con
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` il modello non è sovrascrivibile; `CLAUDE_CODE_EFFORT_LEVEL`
ha precedenza sull'effort; `xhigh`/`max` dipendono dal modello (ripiego `high`).
Il budget non ha parametro di lancio: scrivilo nel prompt ("max N tool call").
