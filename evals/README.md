# evals

Suite di task di riferimento per misurare `/sjck-run` (spec v0.3, sezione F).
Solo Python standard library.

## Struttura di una task

```
evals/tasks/<id>/
  task.md      prompt passato a /sjck-run
  repo/        fixture minima e autonoma (nessun ROS richiesto)
  check.sh     exit 0 = task risolta; eseguito come `bash <taskdir>/check.sh`
               con cwd = copia di lavoro di repo/
  meta.json    {"id": "<id>", "size": "S|M|L", "tags": [...], "traps": [...]}
  hidden/      (opzionale) test che l'agente non vede, usati da check.sh
```

`id` deve coincidere con il nome della cartella. `traps` puo' contenere
`rabbit_hole` (rumore irrilevante) e `out_of_scope_bug` (bug reale non
verificato da `check.sh`).

## Aggiungere una task

Crea la cartella con i file sopra e verifica con `python3 evals/run.py --dry-run`:
`check.sh` deve FALLIRE sulla fixture originale.

## Lanciare

```
python3 evals/run.py --dry-run                 # valida le fixture, niente Claude
python3 evals/run.py [--task ID ...] [--cmd CMD] [--flags F] [--timeout S] [--out PATH] [--keep]
python3 evals/compare.py A.json B.json         # tabella markdown A -> B
```

`--cmd` default: `claude -p "/sjck-run {task}"` (`{task}` = contenuto di
task.md, `{task_file}` = suo percorso). Risultati in `evals/results/<timestamp>.json`.

## Flag di default

Se non passi `--no-default-flags`, dopo il comando `run.py` aggiunge:

```
--plugin-dir <repo>/sjck-graph --permission-mode acceptEdits --allowedTools Bash
```

(`<repo>` = cartella padre di `evals/`, percorso assoluto). Motivi: `--plugin-dir` fa testare il
plugin del checkout e non una copia installata; in `claude -p` non c'e' nessuno che risponda ai
prompt, quindi servono permessi non interattivi (`acceptEdits` per le modifiche, `Bash` per gli
script). `--flags` si aggiunge DOPO i default; il campo `flags` del risultato JSON contiene la
stringa effettiva. `--no-default-flags` li toglie (es. con un `--cmd` che non e' `claude`).

In `claude -p` la skill segue la regola "sessione non interattiva"
(`reference/findings.md` e `reference/critic.md`): i checkpoint dei findings vanno tutti in
`deferred`, e un disaccordo col critico si risolve con la proposta dell'orchestratore.

Nota: se sjck-graph e' installato anche dal marketplace, disabilitalo durante le eval, per non
avere due copie del plugin.
