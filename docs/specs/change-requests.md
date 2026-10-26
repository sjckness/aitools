# Spec — live change requests (`/sjck-change`)

Goal: while a run is going, the user can open a **separate conversation** with a
planning agent, discuss additions or changes (to the plan, to a card, to an
agent, to the planner itself), and have them **merged into the live run** by the
orchestrator — without stopping the run and without two writers racing on
`state.json`.

## Principles
- **One writer.** Only the orchestrator writes `.sjck/state.json` and the cards
  of nodes already launched. The change session writes ONLY under
  `.sjck/changes/`. This is what makes "live" safe.
- **Changes are proposals until applied.** A change request (CR) is a file with
  a lifecycle; the orchestrator applies it at a safe point, after impact
  analysis and (for non-trivial ones) the critic.
- **Cheap polling.** The orchestrator checks the inbox only at transitions it
  already makes (node done/validated, level end): one `Glob` on
  `.sjck/changes/*.json`, no extra agents when the inbox is empty.
- **Minimal context still applies.** The change session reads `state.json`,
  the relevant cards and the spec, not the code, unless the user asks.

## A. The change session — `/sjck-change`
New command + skill `sjck-change`, meant to run in a **second Claude Code
session** in the same repo (a second terminal, or the desktop app).
1. Reads `.sjck/state.json` (and `plan_score`, findings, backlog) and shows a
   short status: running/validated/pending nodes, current level.
2. Converses with the user. Can propose: new nodes, edits to pending cards,
   changes to `model`/`effort`/`budget`, removing or reordering pending nodes,
   accepting backlog findings into the plan, changes to an agent definition or
   to the planner/skill text (these are **kit changes**, see D).
3. For each proposal it computes and shows the **impact** before writing:
   - which nodes are touched and in which state they are;
   - what must be re-run (a validated node whose files or criteria change →
     it and every node that depends on it go back to `pending`);
   - plan score before/after (`plan_score.py` on a scratch copy);
   - rough token/time delta, using the same estimates as `sjck-planning`.
4. When the user agrees, writes `.sjck/changes/CR-<NNN>.json` (schema in B)
   with `status: "proposed"`. It never edits `state.json` or launched cards.
5. Can be reopened at any time; it shows the CRs it wrote and their status.

## B. CR file schema
```json
{
  "id": "CR-003",
  "created": "ISO-8601",
  "author": "user+sjck-change",
  "priority": "normal|next|now",
  "summary": "one line",
  "ops": [
    {"op": "add_node", "node": {"id": "T09", "...": "state.json node fields"},
     "card": "markdown of the card"},
    {"op": "edit_card", "id": "T06", "patch": "unified diff or full new card"},
    {"op": "set", "id": "T06", "fields": {"model": "opus", "effort": "high"}},
    {"op": "remove_node", "id": "T07"},
    {"op": "add_dep", "id": "T08", "dep": "T09"},
    {"op": "rerun", "id": "T03", "reason": "criteria changed"},
    {"op": "accept_finding", "finding": "F02", "as_node": "T10"},
    {"op": "kit_change", "target": "agents/sjck-validator.md", "patch": "..."}
  ],
  "impact": {"rerun": ["T03", "T06"], "plan_score_after": {}, "est_tokens": [0, 0]},
  "status": "proposed|accepted|applied|rejected|superseded",
  "resolution": "filled by the orchestrator"
}
```
Validator: `sjck-graph/scripts/changes.py validate CR.json` (stdlib only),
plus `apply --dry-run` that prints the resulting state diff.

## C. The orchestrator side (skill `sjck-orchestration`)
At every transition, and at level end:
1. `Glob .sjck/changes/*.json` with `status: proposed`. Empty → continue.
2. `priority: now` → stop launching new nodes until the CR is resolved
   (running nodes keep going). `next` → apply before the next launch.
   `normal` → apply at the end of the current level.
3. Impact check against the **current** state (it may have moved since the CR
   was written): a CR that touches a node now `running` waits for it to finish;
   one that conflicts with a newer CR → `superseded`, ask the user.
4. Non-trivial CRs (any `add_node`, `remove_node`, `rerun` of a validated node,
   `kit_change`) go to `sjck-critic` with the plan score before/after.
   Disagreement after 2 rounds → the user decides.
5. Apply atomically: update `state.json`, write/modify cards, mark re-run nodes
   `pending` (keeping their old output in `.sjck/out/<ID>.prev.json`), re-run
   `plan_score.py`; on `reject`, roll back and mark the CR `rejected` with the
   reasons.
6. Log `HH:MM CR-003 applied: +T09, rerun T03,T06` and set the CR `applied`.

## D. Kit changes (agents, planner, skills)
A `kit_change` never modifies the installed plugin of the running session.
It is written as a patch to the **repo** of the kit (when the run is inside the
kit repo) or saved to `.sjck/kit-proposals/` otherwise, and listed in the final
summary as "proposed kit improvements". Rationale: changing the rules of the
orchestrator mid-run makes the run non-reproducible. The user applies them
after the run (and ideally runs `/sjck-eval` before and after).

## E. Run Viewer
- New "Changes" panel: CRs with id, summary, priority, status, re-run nodes.
- Nodes added by a CR show a small `CR-003` tag; nodes reset to `pending` by a
  CR show "rerun" instead of the attempt counter.
- The header shows "1 change pending" when the inbox is not empty.

## F. Tests
- `changes.py`: validate/apply on fixtures (add, edit, remove, rerun cascade,
  conflict with a running node, rollback on plan_score reject).
- Skill text: the polling rule, the single-writer rule, priorities.
- Viewer: renders CRs, with and without the changes folder.

## Out of scope
Real-time push into the orchestrator (it polls at transitions; with
`priority: now` the worst-case delay is one node). Multi-user editing.
Approving CRs from the viewer (comes with the local control server).
