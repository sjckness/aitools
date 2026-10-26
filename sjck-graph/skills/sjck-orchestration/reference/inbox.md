# Inbox: change requests and console decisions

Two sources write into the inbox while a run is going; neither touches
`state.json`:
- the `sjck-change` session (`/sjck-change`, also the chat in the console) →
  `.sjck/changes/CR-NNN.json`;
- the console's approval buttons → `.sjck/decisions/D-*.json`.

You are the only one who turns them into state changes, with `inbox.py`.

## At every transition
1. `python3 "<script>"/inbox.py pending --cwd "$PWD"` → `{crs, decisions, blocking}`.
2. `decisions` not empty → `inbox.py decisions --apply`. Log one line per
   decision; `invalid` ones go in the log with their error, never stop the run.
   A decision `apply` on a CR only marks it `accepted`: apply it in step 3.
3. CRs, in the order given (`now` first):
   - `now` → do not launch new nodes until it is resolved (running nodes go on).
   - `next` → resolve before the next launch.
   - `normal` → resolve at the end of the current level.
   - `inbox.py apply <CR> --dry-run` first. If the CR adds or removes nodes,
     re-runs a validated node, or has a `kit_change`, show the dry-run line and
     the plan score to `sjck-critic` (`at: plan`, same 2-round rule). Object
     twice → ask the user (non-interactive session: leave the CR `proposed`
     and log it).
   - `inbox.py apply <CR>`: exit 0 applied → RE-READ state.json (it changed),
     log it; exit 1 rejected (reason in the CR) → log it; exit 3 waits for a
     running node → retry at the next transition.
4. Re-run nodes are back to `pending`; their old output is in
   `.sjck/out/<ID>.prev.json`. Normal scheduling picks them up.

## Rules
- Never edit a CR or decision file by hand, never apply one twice.
- `kit_change` never alters the running kit: `apply` writes it to
  `.sjck/kit-proposals/`; list them in the final summary.
- A plan the console approves is just a `/sjck-run` on a `planned` state: no
  decision file is involved.
