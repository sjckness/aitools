---
description: Plan a task for sjck-graph before running it — an interactive chat (multiple-choice questions, alternatives with estimates, optimizations), then the plan is handed to the VS Code extension or /sjck-run.
argument-hint: <task o percorso di una spec> [--mode S|M|L]
---
Usa la skill `sjck-planning` per questa task: $ARGUMENTS
Pianifica in modo interattivo: ogni scelta che cambia il piano passa
dall'utente tramite AskUserQuestion. Non eseguire il piano: dopo
l'approvazione scrivi le card e per ultimo .sjck/state.json con status
"planned" e planned_at; l'estensione VS Code lo prende in carico da lì.
