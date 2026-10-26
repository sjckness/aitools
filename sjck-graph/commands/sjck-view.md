---
description: Genera e apre il visualizzatore live del grafo (.sjck/view.html).
---
Esegui: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/graph_view.py" --cwd "$PWD" --open`
Se `${CLAUDE_PLUGIN_ROOT}` è vuoto, usa `~/.claude/sjck-scripts/graph_view.py`, poi
`.claude/sjck-scripts/graph_view.py`, infine cerca graph_view.py sotto
`~/.claude/plugins/` e usa quel percorso.
Rispondi solo con il percorso del file generato e: "si aggiorna da solo ogni 2 s".
