#!/usr/bin/env bash
# Installazione senza plugin: copia agenti e comandi in un progetto o globalmente.
#   curl -fsSL https://raw.githubusercontent.com/sjckness/graph-kit/main/install.sh | bash            # progetto corrente
#   curl -fsSL https://raw.githubusercontent.com/sjckness/graph-kit/main/install.sh | bash -s -- -g  # globale (~/.claude)
set -euo pipefail

REPO="${GRAPH_KIT_REPO:-sjckness/graph-kit}"
REF="${GRAPH_KIT_REF:-main}"
DEST="./.claude"
[[ "${1:-}" == "-g" || "${1:-}" == "--global" ]] && DEST="$HOME/.claude"

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$REF" | tar -xz -C "$tmp"
src="$(find "$tmp" -maxdepth 2 -type d -name graph-kit | head -1)"

mkdir -p "$DEST/agents" "$DEST/commands"
for d in agents commands; do
  for f in "$src/$d"/*.md; do
    t="$DEST/$d/$(basename "$f")"
    [[ -e "$t" ]] && ! cmp -s "$f" "$t" && cp "$t" "$t.bak"
    cp "$f" "$t"
  done
done

echo "graph-kit installato in $DEST"
echo "Apri claude e lancia: /run-graph <task>"
