#!/usr/bin/env bash
# Installazione senza plugin: copia agenti e comandi in un progetto o globalmente.
#   curl -fsSL https://raw.githubusercontent.com/sjckness/aitools/main/install.sh | bash            # progetto corrente
#   curl -fsSL https://raw.githubusercontent.com/sjckness/aitools/main/install.sh | bash -s -- -g  # globale (~/.claude)
set -euo pipefail

REPO="${GRAPH_KIT_REPO:-sjckness/aitools}"
REF="${GRAPH_KIT_REF:-main}"
DEST="./.claude"
[[ "${1:-}" == "-g" || "${1:-}" == "--global" ]] && DEST="$HOME/.claude"

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$REF" | tar -xz -C "$tmp"
root="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -1)"

copy() {  # copia un file facendo backup se esiste ed è diverso
  mkdir -p "$(dirname "$2")"
  [[ -e "$2" ]] && ! cmp -s "$1" "$2" && cp "$2" "$2.bak"
  cp "$1" "$2"
}

for plugin in graph-kit project-onboard; do
  src="$root/$plugin"
  [[ -d "$src" ]] || continue
  for d in agents commands; do
    [[ -d "$src/$d" ]] || continue
    for f in "$src/$d"/*.md; do copy "$f" "$DEST/$d/$(basename "$f")"; done
  done
  if [[ -d "$src/skills" ]]; then
    (cd "$src/skills" && find . -type f) | while read -r f; do
      copy "$src/skills/$f" "$DEST/skills/$f"
    done
  fi
  if [[ -d "$src/scripts" ]]; then
    for f in "$src/scripts"/*; do copy "$f" "$DEST/aitools-scripts/$(basename "$f")"; done
  fi
done

# senza plugin ${CLAUDE_PLUGIN_ROOT} non esiste: punta /graph-view allo script copiato
gv="$DEST/commands/graph-view.md"
[[ -f "$gv" ]] && sed -i.tmp "s#\${CLAUDE_PLUGIN_ROOT}/scripts#$DEST/aitools-scripts#" "$gv" && rm -f "$gv.tmp"

echo "aitools installato in $DEST"
echo "Comandi: /onboard, /run-graph <task>, /graph-status, /graph-view"
