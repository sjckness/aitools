# Changelog

## 0.2.2 — 2026-10-26
- Nuova skill e comando `/graph-plan`: pianificazione guidata con domande mirate, alternative con stime di token e tempo, checklist di ottimizzazione e piano `planned` pronto per `/run-graph`.
- `graph-orchestration` esegue un piano `planned` senza rifare triage e planner, rispettando modello, effort e budget per nodo; per task grandi e vaghe suggerisce `/graph-plan`.
- Run Viewer: stato `planned` in ambra.

## 0.2.1 — 2026-10-26
- Nuovo Run Viewer (`.graph/view.html`): una pagina con viste Grafo, Token e Findings, tema scuro, leggibile da telefono, nessuna libreria esterna (niente più Mermaid).
- Il viewer legge in modo opzionale `tokens.json`, `token-report.json`, `findings.jsonl` e `watchdog.jsonl`; con uno stato v0.2 mostra solo il grafo.
- Scrittura atomica della pagina; si ricarica da sola solo mentre il run è in corso.
- Demo in `examples/demo/` e README con screenshot.

## 0.2.0 — 2026-10-26
- graph-kit: la logica è ora una skill (`graph-orchestration`) che Claude attiva da solo per task grandi; `/run-graph` resta come scorciatoia.
- graph-kit: override dell'utente su modalità e agenti (`--mode M`, "usa solo implementer e validator").
- graph-kit: stato in `.graph/state.json`; visualizzatore live `.graph/view.html` aggiornato da hook, comando `/graph-view`.
- Nuovo plugin `project-onboard`: `/onboard` genera CLAUDE.md compatto + `.claude/map/<modulo>.md`.

## 0.1.0 — 2026-10-26
- Prima versione: triage S/M/L, planner, scout, implementer, validator, reviewer.
- Stato persistente in `.graph/state.yaml` con ripresa automatica.
- Installazione come plugin Claude Code o via `install.sh`.
