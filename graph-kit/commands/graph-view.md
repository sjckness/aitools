---
description: Genera e apre il visualizzatore live del grafo (.graph/view.html).
---
Esegui: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/graph_view.py" --cwd "$PWD" --open`
Se `${CLAUDE_PLUGIN_ROOT}` è vuoto, cerca graph_view.py sotto
~/.claude/plugins/ e usa quel percorso.
Rispondi solo con il percorso del file generato e: "si aggiorna da solo ogni 2 s".
