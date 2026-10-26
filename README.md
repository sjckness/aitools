# aitools

Plugin per Claude Code che rendono gli agenti più autonomi, economici e affidabili.

| Plugin | Cosa fa |
|---|---|
| **graph-kit** | Orchestrazione a grafo: triage automatico S/M/L, agenti in parallelo, validazione tra gli step, stato persistente, visualizzatore live. |
| **project-onboard** | Genera un `CLAUDE.md` compatto e una mappa per moduli, così Claude capisce il progetto senza esplorarlo ogni volta. |

## Installazione

Dentro Claude Code, una volta per macchina:

    /plugin marketplace add sjckness/aitools
    /plugin install graph-kit@aitools
    /plugin install project-onboard@aitools

Aggiornamento: `/plugin marketplace update aitools`.

## Flusso consigliato in un progetto nuovo

    /onboard                      # una volta: CLAUDE.md + .claude/map/
    <chiedi la task normalmente>  # per task grandi Claude usa il grafo da solo
    /graph-view                   # opzionale: segui il grafo nel browser

## graph-kit

Si attiva **da solo** per task di sviluppo non banali (è una skill), oppure
esplicitamente:

    /run-graph aggiungi i servizi load/start/abort al mission_manager_node
    /run-graph refactor del logger --mode M
    /run-graph fix del parser, usa solo implementer e validator
    /graph-status
    /graph-view
    /graph-eval --dry-run

`/graph-eval` lancia l'eval harness (`evals/run.py`) per confrontare le versioni. Carica il plugin del checkout con `--plugin-dir` e usa permessi non interattivi di default (`--no-default-flags` li toglie).
Gli override (`--mode`, agenti da usare) hanno sempre la precedenza sul triage.
Se tolgo il validator, i nodi finiscono `done-unverified` invece di `validated`.

    triage ──► S: inline ─────────────────► validator ─► fine
           ├─► M: scout ► impl ► validator ─────────────► fine
           └─► L: planner ► DAG ► [impl ► validator]×N ► reviewer ► fine
                                    ▲          │ fail (max 2)
                                    └──────────┘

- `.graph/state.json` è l'unica fonte di verità: il run riprende da lì se si interrompe.
- Un nodo sblocca i successivi solo con un `.val.json` con `verdict: pass`.
- Gli agenti si passano file in `.graph/`, non riassunti in chat.
- Il visualizzatore `.graph/view.html` viene rigenerato da un hook a ogni
  scrittura dello stato e si ricarica da solo ogni 2 secondi.

| Agente | Modello | Effort | Contesto |
|---|---|---|---|
| planner | opus | high | repo (una volta) |
| scout | haiku | low | card |
| implementer | sonnet | medium | card + file elencati |
| validator | sonnet | high | card + out.json + diff |
| reviewer | opus | high | diff aggregato |
| critic | fable | high | proposta + plan score/findings + goal (mai codice) |

**Plan score.** Prima di eseguire, `plan_score.py` calcola metriche del DAG
(larghezza per livello, percorso critico, overlap di file tra nodi paralleli, token
per card). Se il verdetto è `reject` il run non parte; viene rilanciato sui nodi
aggiunti a run avviato.

**Watchdog.** Hook del plugin: livello 1 richiama l'agente e blocca le scritture
fuori dai `files` della card; livello 2 interviene se il pattern si ripete o il
budget supera il 125%; livello 3 tocca all'orchestratore, che decide sul nodo bloccato.
Gli hook attribuiscono ogni chiamata al nodo tramite `agent_id` (validator, critic,
reviewer, planner sono ignorati). La usage sta in `.graph/watchdog_state.json` e,
a nodo completato, `watchdog.py usage` la copia in `state.json`.

**Findings e backlog.** Gli agenti annotano cose fuori scope in `.graph/findings.jsonl`
invece di implementarle; a fine di ogni livello l'orchestratore fa dedupe e
propone cosa spostare nel backlog.

**Critico.** `critic` valuta in sola lettura piani, findings e nodi falliti e
risponde approve o object, con un modello diverso dall'orchestratore.

Schema di stato: `graph-kit/docs/state-schema.md`. Limiti noti: `graph-kit/docs/limitations.md`.

## project-onboard

    /onboard
    /onboard solo f1tenth_behavior

Produce `CLAUDE.md` (≤ ~120 righe, caricato in ogni sessione) e
`.claude/map/<modulo>.md` (letti solo quando servono). Non sovrascrive le righe
scritte a mano, e verifica davvero i comandi di build/test che documenta.

## Installazione senza plugin

    curl -fsSL https://raw.githubusercontent.com/sjckness/aitools/main/install.sh | bash

Aggiungi `-s -- -g` per installare in `~/.claude`. In questa modalità non ci sono hook (richiedono il plugin): né watchdog né
aggiornamento live del visualizzatore. Usa `/graph-view` quando vuoi vederlo.

## Contribuire
Ogni modifica va con una riga in `CHANGELOG.md` e, se possibile, con le
metriche di un run prima/dopo (`metrics` in state.json). Vedi `ROADMAP.md`.
