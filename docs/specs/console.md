# Spec — sjck console

A cross-platform (Linux, macOS, Windows) local app that runs on the **host PC**
where your repos live, and that you use from the browser. It starts, watches
and steers sjck runs across all your projects. The Claude Code plugins stay the
engine; the console is a second door onto the same `.sjck/` files.

```
host PC ── sjck daemon (Node) ── claude -p … (headless runs, chat)
              │   reads/watches <project>/.sjck/ for every registered project
              └── http://127.0.0.1:7777/?token=…   ← the console UI
```

## Why Node
Everyone who runs Claude Code already has Node, so `npm i -g` works the same on
every OS. The MVP uses **no runtime dependencies** (only Node's standard
library): nothing to audit, nothing to break. The existing Python scripts stay
where they are; the console reads the same files they write.

## Principles
- **Single writer stays true.** The orchestrator (the Claude session running the
  graph) is the only writer of `state.json`. The console writes only: its own
  config (`~/.sjck/console.json`), run logs (`<project>/.sjck/console/`), and —
  from phase 2 — change requests (`.sjck/changes/`) and decisions
  (`.sjck/decisions/`), which the orchestrator picks up.
- **Local by default.** Binds to `127.0.0.1`. Every request needs the random
  token generated at start (printed in the URL). No CORS. Remote access is the
  user's choice through a private network (e.g. Tailscale), never public.
- **Claude through the CLI.** Runs and chat use `claude -p` with the user's own
  Claude Code login: no API keys in the console. Flags used (verified against
  the CLI reference): `-p`, `--output-format stream-json --verbose`,
  `--session-id <uuid>` / `--resume <id>`, `--permission-mode`, `--tools`,
  `--allowedTools`, `--plugin-dir`. The exact command is configurable.

## Phase 1 — MVP (this version)
CLI:
- `sjck serve [--port 7777] [--host 127.0.0.1] [--no-open]` — start the daemon,
  open the browser.
- `sjck add [path]`, `sjck remove <path|id>`, `sjck list` — manage projects.
  `sjck serve` in a repo that isn't registered offers to add it.
API (JSON, token required):
- `GET /api/projects` — projects with a one-line status each (goal, status,
  validated/total nodes, last update).
- `GET /api/projects/:id/data` — the same data the Run Viewer uses
  (state, findings, watchdog, tokens, report), cleaned like `graph_view.collect`.
- `GET /api/projects/:id/events` — Server-Sent Events: `data` when anything in
  `.sjck/` changes (debounced), `log` lines from console-launched runs.
- `POST /api/projects/:id/runs` `{task, kind: "plan"|"run", mode?}` — launches
  `claude -p "/sjck-plan …"` or `"/sjck-run …"` in the project directory,
  streams its output to the run log; one console-launched run per project.
- `POST /api/projects/:id/runs/stop` — stops it.
UI:
- **Home**: project cards with live status; "Add project" with a path field.
- **Project**: the Run Viewer (Graph / Tokens / Findings), updated live through
  SSE instead of page reloads, plus a **Task** panel: write a task, choose
  Plan or Run, start, see the streamed log, stop.

## Phase 2 — steering
- Chat with the planner in the page (`sjck-change` skill, headless, resumed by
  session id, tools limited to reads + writing `.sjck/changes/`).
- Buttons: accept/defer/reject findings, apply/reject change requests, approve
  a `planned` plan — written as decision files the orchestrator applies.
- Phone notifications (failed node, decision needed, run done).

## Phase 3 — scale
- Analytics across runs and projects (tokens, cost, failure rates per agent).
- Multi-machine: every PC runs the daemon; one console lists the others as
  workers with capabilities (cuda, ros2, hw) and routes nodes to them.
- Optional desktop shell (Tauri) around the same web UI: tray icon, native
  notifications.

## Tests (MVP)
`node --test` on: config add/remove, project status summary, data collection
(including malformed files), path traversal and token checks on the API, SSE
change notification, run launcher with a fake `claude` command.
