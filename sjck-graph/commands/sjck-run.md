---
description: Avvia o riprende un run a grafo. Accetta override come "--mode M" o "usa solo scout e validator".
argument-hint: <task> [--mode S|M|L] [agenti da usare]
---
Usa la skill `sjck-orchestration` per questa task, rispettando ogni
override indicato: $ARGUMENTS

Se $ARGUMENTS è vuoto, riprendi il run in corso in .sjck/state.json;
se non ce n'è uno, chiedi la task.
