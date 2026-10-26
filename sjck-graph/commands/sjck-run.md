---
description: Start or resume a graph run. Accepts overrides like "--mode M" or "only use scout and validator".
argument-hint: <task> [--mode S|M|L] [agenti da usare]
---
Usa la skill `sjck-orchestration` per questa task, rispettando ogni
override indicato: $ARGUMENTS

Se $ARGUMENTS è vuoto, riprendi il run in corso in .sjck/state.json;
se non ce n'è uno, chiedi la task.
