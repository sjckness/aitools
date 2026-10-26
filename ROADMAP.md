# Roadmap

## v0.2 — misurare
- [ ] Metriche per run: token per agente, durata, tentativi, modalità scelta
- [ ] Script che aggrega `.graph/archive/*/state.json` in una tabella
- [x] Suite di task di riferimento (S, M, L) per confrontare le versioni

## v0.3 — agenti più forti
- [ ] Validator con checklist per linguaggio (C++/ROS 2, Python, TS)
- [x] Hook che blocca le scritture fuori dai `files` della card
- [ ] Planner che stima il costo del DAG e lo confronta con la modalità M

## v0.4 — memoria tra run
- [ ] Multi-macchina
- [ ] Job runner
- [ ] Optimizer automatico
- [ ] `.graph/lessons.md`: errori ricorrenti del validator, letti dal planner
- [ ] Interfacce estratte dallo scout riusate tra run se il file non è cambiato
