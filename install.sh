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

mkdir -p "$DEST"
abs_dest="$(cd "$DEST" && pwd)"

copy() {  # copia un file; .bak solo se la destinazione esiste e differisce dal contenuto finale
  mkdir -p "$(dirname "$2")"
  local stage; stage="$(mktemp "$tmp/stage.XXXXXX")"
  cp "$1" "$stage"
  # senza plugin ${CLAUDE_PLUGIN_ROOT} non esiste: punta agli script copiati (percorso assoluto)
  if [[ "$2" == *.md ]]; then
    sed "s#\${CLAUDE_PLUGIN_ROOT}/scripts#$abs_dest/aitools-scripts#g" "$stage" > "$stage.out" && mv "$stage.out" "$stage"
  fi
  [[ -e "$2" ]] && ! cmp -s "$stage" "$2" && cp "$2" "$2.bak"
  cp "$stage" "$2"
  rm -f "$stage"
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
    for f in "$src/scripts"/*; do [[ -f "$f" ]] && copy "$f" "$DEST/aitools-scripts/$(basename "$f")"; done
  fi
done

echo "aitools installato in $DEST"
echo "Comandi: /onboard, /run-graph <task>, /graph-status, /graph-view, /graph-eval"
