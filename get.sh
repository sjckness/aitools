#!/usr/bin/env bash
# sjck installer for Linux and macOS — no clone needed.
#   curl -fsSL https://raw.githubusercontent.com/sjckness/sjckAI-tools/main/get.sh | bash
# Options (after `bash -s --`): --no-vscode, --no-plugins. Env: SJCK_REF=v0.4.0 to pin a release.
set -euo pipefail

REPO="${SJCK_REPO:-sjckness/sjckAI-tools}"
REF="${SJCK_REF:-latest}"
if [[ "$REF" == latest ]]; then URL="https://github.com/$REPO/releases/latest/download/sjck-console.tgz"
else URL="https://github.com/$REPO/releases/download/$REF/sjck-console.tgz"; fi

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

say "sjck installer"

command -v node >/dev/null || fail "Node.js 20+ is required: https://nodejs.org (or: nvm install 20)"
major="$(node -p 'process.versions.node.split(".")[0]')"
(( major >= 20 )) || fail "Node.js $major found, 20+ is required"

if ! command -v claude >/dev/null; then
  say "→ Claude Code not found, installing it with npm"
  npm i -g @anthropic-ai/claude-code || fail "could not install Claude Code; see https://code.claude.com"
  echo "  run \`claude\` once to log in, then run this installer again if plugins fail"
fi

say "→ sjck console ($REF)"
if ! npm i -g "$URL"; then
  echo "  npm could not write to its global folder. Use a Node version manager (nvm, fnm)"
  echo "  or set a user prefix:  npm config set prefix ~/.local  (and add ~/.local/bin to PATH)"
  fail "console install failed"
fi

command -v sjck >/dev/null || fail "installed, but \`sjck\` is not on PATH: add \"$(npm prefix -g)/bin\" to PATH"
sjck setup "$@"
