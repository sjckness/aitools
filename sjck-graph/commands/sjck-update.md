---
description: Update sjck to the latest GitHub release (plugins, VS Code extension, console). Pass "check" to only compare versions.
argument-hint: "[check] [--only plugins|vscode|console] [--editor code|cursor|codium]"
---
Script: `"${CLAUDE_PLUGIN_ROOT}/scripts/update.py"`. Se `${CLAUDE_PLUGIN_ROOT}` è vuoto,
cerca update.py sotto `~/.claude/plugins/` e usa quel percorso. Su Windows usa
`python` se `python3` non esiste.

1. Esegui `python3 <script> --check` e mostra all'utente l'esito così com'è
   (ultima release, cosa è installato).
2. Se gli argomenti contengono `check`, fermati qui.
3. Altrimenti esegui `python3 <script> $ARGUMENTS` (senza la parola `check`;
   passa `--only`/`--editor` se presenti) con un timeout di 10 minuti.
4. Rispondi in poche righe: cosa è stato aggiornato, cosa è fallito con il
   motivo, e i passi finali che lo script stampa (riavviare Claude Code per i
   plugin, ricaricare la finestra di VS Code per l'estensione).

Non modificare file del progetto e non lanciare agenti. Se GitHub non è
raggiungibile, dillo in una riga.
