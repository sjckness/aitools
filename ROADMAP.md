# Roadmap

## v0.2 — misurare
- [ ] Metriche per run: token per agente, durata, tentativi, modalità scelta
- [ ] Script che aggrega `.sjck/archive/*/state.json` in una tabella
- [x] Suite di task di riferimento (S, M, L) per confrontare le versioni

## v0.3 — agenti più forti
- [ ] Validator con checklist per linguaggio (C++/ROS 2, Python, TS)
- [x] Hook che blocca le scritture fuori dai `files` della card
- [ ] Planner che stima il costo del DAG e lo confronta con la modalità M

## Console
- [x] Fase 1: daemon, home dei progetti, Plan/Run dal browser, viewer live (`docs/specs/console.md`)
- [x] Fase 2: chat con il planner, approvazioni, notifiche
- [ ] Fase 3: analytics, multi-macchina, app desktop
- [x] Estensione VS Code nativa 0.1.0 (`vscode/`)
- [ ] Pubblicazione su Marketplace VS Code e Open VSX

## Prossimo — live change requests
- [x] `docs/specs/change-requests.md`: `/sjck-change`, CR in `.sjck/changes/`, applicati live da `inbox.py`

## Prossimo — output chat
- [ ] Accanto alla chat del planner (che *cambia* il piano), una chat in sola lettura che *spiega* cosa è stato fatto: "cosa ha cambiato T03?", "perché il validator ha bocciato T02?", "chi ha toccato graph_view.py?"
- [ ] Risponde da `.sjck/` (card, out JSON, `.val.json`, REVIEW.json, findings, watchdog, change request applicati) e dai diff dei nodi, con link a file:riga e al nodo nel grafo
- [ ] Disponibile in console, VS Code (accanto al planner) e come `/sjck-explain` in Claude Code; a fine run genera un riepilogo spiegato
- [ ] Tool limitati a lettura: non scrive né lo stato né change request

## v0.4 — token analytics
- [~] Spec: `docs/specs/v0.4-token-analytics.md` — fatti A (raccolta + categorie stimate) e C (insight); mancano B (costo), D (baseline), curva nel tempo (consumo reale dai transcript, costo, dove si risparmia, baseline senza kit, token visualizer)

## v0.5 — memoria tra run
- [ ] `.sjck/lessons.md`: errori ricorrenti del validator, letti dal planner
- [ ] Interfacce estratte dallo scout riusate tra run se il file non è cambiato

## Oltre
- [ ] Job runner per lavori pesanti
- [ ] Multi-macchina (worker con capabilities)
- [ ] Optimizer automatico degli agenti (con eval obbligatoria e approvazione umana)
