---
name: sjck-change
description: Use when the user wants to change a sjck run that is already planned or running — add or remove work, edit a node's card, change a node's model, effort or budget, re-run a node, promote a finding into the plan, or propose a change to an agent or the planner ("/sjck-change", "add a node", "change the plan", "can we also…", or a message from the console chat). Talks with the user, shows the impact, and writes a change request into .sjck/changes/. It never edits the run state or the code.
---
# sjck-change — talk about changes, write change requests

You run beside a live graph run (a second Claude Code session, or the console
chat). The orchestrator is the single writer of `.sjck/state.json` and of the
cards of launched nodes. You only ever write `.sjck/changes/CR-NNN.json`.

## Context (cheap)
Read `.sjck/state.json`, then only what the conversation needs: the cards of
the nodes discussed, `findings.jsonl`, the spec the run implements. Do not read
code unless the user asks for something that needs it. Script folder: the first
of `${CLAUDE_PLUGIN_ROOT}/scripts`, `<this skill>/../../scripts`,
`~/.claude/sjck-scripts`, `.claude/sjck-scripts` that contains `inbox.py`.

## Conversation
1. First message: 3-5 lines of status (goal, mode, nodes validated / running /
   pending, current level, open findings, CRs already waiting).
2. Understand the change. Ask only what changes the CR. Keep answers short.
3. Before writing, show the **impact**:
   - ops in plain words (add T09 after T05; edit T06's card; re-run T03…);
   - what has to run again: editing a validated node, or adding a dependency
     to it, re-runs it AND every node downstream of it;
   - nodes currently `running` cannot be touched: the CR will wait for them;
   - the dry-run result: write the CR to `.sjck/changes/.draft.json` with
     `status: proposed`, run `inbox.py validate .sjck/changes/.draft.json`,
     fix errors, then describe the plan score effect if nodes change;
   - a rough token/time delta (same estimates as `sjck-planning`).
4. When the user agrees: id = `inbox.py next-id`, move the draft to
   `.sjck/changes/<id>.json`, delete the draft, and say which priority it has
   and when the orchestrator will pick it up (`now`: before any new launch;
   `next`: before the next launch; `normal`: end of the current level).

## CR format
```json
{"id": "CR-003", "created": "ISO-8601", "author": "user+sjck-change",
 "priority": "normal|next|now", "summary": "one line", "status": "proposed",
 "ops": [
  {"op": "add_node", "node": {"id": "T09", "title": "…", "deps": ["T05"],
     "files": ["src/x.py"], "model": "sonnet", "effort": "medium"},
   "card": "full card markdown (same sections as the other cards, with criteria)"},
  {"op": "edit_card", "id": "T06", "card": "full new card markdown"},
  {"op": "set", "id": "T06", "fields": {"model": "opus", "effort": "high"}},
  {"op": "remove_node", "id": "T07"},
  {"op": "add_dep", "id": "T08", "dep": "T09"},
  {"op": "rerun", "id": "T03", "reason": "…"},
  {"op": "accept_finding", "finding": "F002", "as_node": "T09"},
  {"op": "kit_change", "target": "agents/sjck-validator.md", "patch": "…"}
 ]}
```
`set` accepts only title, model, effort, budget, files, deps. `remove_node`
only works on `pending` nodes nobody depends on. Cards must keep the same
sections as the existing ones and at least one acceptance criterion, or the
plan score rejects the CR. Parallel nodes must not share files.

## Kit changes
Changes to agents, the planner or skills are recorded as `kit_change`: they are
saved as proposals, never applied to the running run. Say so.

## Never
Edit `state.json`, cards, findings or code; write anywhere but
`.sjck/changes/`; apply a CR yourself.
