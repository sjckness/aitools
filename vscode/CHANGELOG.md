# Changelog

## 0.2.0
- **Plan a task** opens an interactive `/sjck-plan` session in a terminal: the planner asks you multiple-choice questions, and once you approve, the plan lands in `.sjck/` and the extension takes over (setting `sjck.plan.interactive`).
- New plans are announced even in a workspace without a previous run, and again on every re-plan; the sjck views open automatically (`sjck.revealOnPlan`).
- *Approve and run* reuses the plan's mode instead of asking again.
- Activates on startup, so it is ready when the first plan appears.
- Real token usage: the run's total sits on the top row of the Graph view (tooltip: types, cache hit, costliest nodes), per-node tokens in the tree. Data comes from the sjck-graph plugin's new token hooks.

## 0.1.1
- New icon: the sjck wordmark with an amber graph node as the dot of the j (Marketplace and activity bar).

## 0.1.0
- First release: graph tree, status bar, Explorer decorations, Run Viewer tab, planner chat, inbox actions, Plan/Run/Stop, notifications.
