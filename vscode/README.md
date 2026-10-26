# sjck for VS Code

Watch and steer [sjck](https://github.com/sjckness/sjckAI-tools) agent-graph runs
without leaving the editor.

- **Graph view** in the activity bar: levels and nodes with live status, model and
  effort, tool calls against budget, attempts and tokens. Click a node to open its
  card; on finished nodes, open the diff of the files they changed.
- **Status bar**: `sjck 4/9 · T02 T05 · 2 waiting`, always visible.
- **Explorer decorations**: `●` on files a running node is working on, `!` on files
  of a failed or blocked node, `✓` on files changed by a validated node.
- **Run Viewer** in an editor tab (Graph, Tokens, Findings), updated live.
- **Planner chat** in the sidebar: ask for additions, edits or re-runs while the run
  goes on. Agreed changes become change requests the orchestrator applies live.
- **Inbox**: approve or reject change requests, accept / defer / reject findings,
  approve a plan and run it — one click each.
- **Plan / Run / Stop** from the view title or the command palette (`sjck:`), with the
  run log in the *sjck* output channel.
- **Notifications** when a node fails or blocks, a run ends or a plan is ready.

## Requirements
- [Claude Code](https://code.claude.com) with the `sjck-graph` plugin:
  `/plugin marketplace add sjckness/sjckAI-tools` then `/plugin install sjck-graph@sjck`.
- Python 3 (used by the plugin's scripts).

## How it works
The extension reads the project's `.sjck/` folder, like the plugin and the
[sjck console](https://github.com/sjckness/sjckAI-tools#sjck-console). It never
writes the run state: approvals are decision files and changes are change requests,
both applied by the orchestrator, which stays the single writer.

Plan and Run use `claude -p` with your own Claude Code login. Non-interactive runs
must decide permissions up front: by default they may edit files and use Bash in
this workspace (`sjck.claude.runArgs`). The planner chat can only read files and
write change requests.

## Settings
| Setting | Default | |
|---|---|---|
| `sjck.claude.path` | `claude` | Claude Code CLI |
| `sjck.claude.runArgs` | stream-json, acceptEdits, Bash | flags for Plan and Run |
| `sjck.decorations` | `true` | Explorer badges |
| `sjck.notifications` | `true` | pop-up notifications |
