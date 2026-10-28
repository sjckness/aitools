# Changelog

## 0.1.5
- **Plan a task** opens an interactive `/sjck-plan` session in a terminal: the planner asks you multiple-choice questions, and once you approve, the plan lands in `.sjck/` and the extension takes over (setting `sjck.plan.interactive`).
- New plans are announced even in a workspace without a previous run, and again on every re-plan; the sjck views open automatically (`sjck.revealOnPlan`).
- *Approve and run* reuses the plan's mode instead of asking again.
- Activates on startup, so it is ready when the first plan appears.
- Real token usage: the run's total sits on the top row of the Graph view (tooltip: types, cache hit, costliest nodes, where the context goes), per-node tokens in the tree. Data comes from the sjck-graph plugin's new token hooks.
- Token figures verified against the totals Claude Code writes itself: subagent output is no longer undercounted, past thinking and system reminders have their own categories, and the run cost is the real one, shown in **euro** (ECB daily rate) next to dollars.

## 0.1.4
- **Mission Control**: a new full panel (`sjck: Open Mission Control`, rocket button, status bar click) with a live animated agent graph — glowing running nodes, flowing edges, pop on validation, pan/zoom/fit — a progress ring, live stats (tokens, tool calls vs budget, agents, inbox, fails), a node drawer (budget, token breakdown, deps, files, open card, diff), an interactive inbox, plan score, critic verdict and an activity timeline. Updates arrive by message, so nothing reloads.
- Planner chat restyled: header, avatars, typing indicator, suggestion chips, focused composer.

## 0.1.1
- New icon: the sjck wordmark with an amber graph node as the dot of the j (Marketplace and activity bar).

## 0.1.0
- First release: graph tree, status bar, Explorer decorations, Run Viewer tab, planner chat, inbox actions, Plan/Run/Stop, notifications.
