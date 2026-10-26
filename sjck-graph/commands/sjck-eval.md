---
description: Lancia l'eval harness (evals/run.py) e, se richiesto, confronta due risultati.
argument-hint: [--dry-run] [--task ID] [--cmd CMD] [--flags F] [--no-default-flags] [--out PATH]
---
Se `evals/run.py` non esiste nella directory corrente, dillo e fermati
(va lanciato dalla root del repo sjck).
Altrimenti esegui: `python3 evals/run.py $ARGUMENTS`
Se l'utente chiede un confronto, esegui poi `python3 evals/compare.py A.json B.json`
con i due file di `evals/results/` indicati.
Per default run.py aggiunge `--plugin-dir <repo>/sjck-graph --permission-mode acceptEdits
--allowedTools Bash` (plugin del checkout, permessi non interattivi); `--no-default-flags` li toglie.
Rispondi con l'output (righe OK/KO, percorso del risultato o tabella).
