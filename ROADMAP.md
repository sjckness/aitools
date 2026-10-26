# Roadmap

## v0.2 — misurare
- [ ] Metriche per run: token per agente, durata, tentativi, modalità scelta
- [ ] Script che aggrega `.graph/archive/*/state.json` in una tabella
- [x] Suite di task di riferimento (S, M, L) per confrontare le versioni

## v0.3 — agenti più forti
- [ ] Validator con checklist per linguaggio (C++/ROS 2, Python, TS)
- [x] Hook che blocca le scritture fuori dai `files` della card
- [ ] Planner che stima il costo del DAG e lo confronta con la modalità M

## v0.4 — token analytics
- [ ] Spec: `docs/specs/v0.4-token-analytics.md` (consumo reale dai transcript, costo, dove si risparmia, baseline senza kit, token visualizer)

## v0.5 — memoria tra run
- [ ] `.graph/lessons.md`: errori ricorrenti del validator, letti dal planner
- [ ] Interfacce estratte dallo scout riusate tra run se il file non è cambiato

## Oltre
- [ ] Job runner per lavori pesanti
- [ ] Multi-macchina (worker con capabilities)
- [ ] Optimizer automatico degli agenti (con eval obbligatoria e approvazione umana)
