# Changelog

## 0.2.0 — 2026-10-26
- graph-kit: la logica è ora una skill (`graph-orchestration`) che Claude attiva da solo per task grandi; `/run-graph` resta come scorciatoia.
- graph-kit: override dell'utente su modalità e agenti (`--mode M`, "usa solo implementer e validator").
- graph-kit: stato in `.graph/state.json`; visualizzatore live `.graph/view.html` aggiornato da hook, comando `/graph-view`.
- Nuovo plugin `project-onboard`: `/onboard` genera CLAUDE.md compatto + `.claude/map/<modulo>.md`.

## 0.1.0 — 2026-10-26
- Prima versione: triage S/M/L, planner, scout, implementer, validator, reviewer.
- Stato persistente in `.graph/state.yaml` con ripresa automatica.
- Installazione come plugin Claude Code o via `install.sh`.
