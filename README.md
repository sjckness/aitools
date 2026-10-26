# aitools

Raccolta di tool per agenti AI. Primo tool: **graph-kit**.

## graph-kit

Orchestrazione a grafo per gli agenti di Claude Code.
Una task entra, il kit sceglie da solo quanti agenti servono, li fa lavorare
in parallelo dove possibile e non lascia passare un errore da uno step al successivo.

## Installazione

**Come plugin (consigliato)**, dentro Claude Code:

    /plugin marketplace add sjckness/aitools
    /plugin install graph-kit@aitools

Aggiornamento: `/plugin marketplace update aitools`.

**Senza plugin**, dal terminale nella root del progetto:

    curl -fsSL https://raw.githubusercontent.com/sjckness/aitools/main/install.sh | bash

Aggiungi `-s -- -g` per installarlo in `~/.claude` e averlo in tutti i progetti.

## Uso

    /run-graph aggiungi i servizi load/start/abort al mission_manager_node
    /graph-status

Se è installato come plugin, i comandi possono apparire anche come
`/graph-kit:run-graph` e `/graph-kit:graph-status`.

## Come funziona

    triage ──► S: inline ─────────────────► validator ─► fine
           ├─► M: scout ► impl ► validator ─────────────► fine
           └─► L: planner ► DAG ► [impl ► validator]×N ► reviewer ► fine
                                    ▲          │ fail (max 2)
                                    └──────────┘

- `.graph/state.yaml` è l'unica fonte di verità: il run riprende da lì se si interrompe.
- Un nodo sblocca i successivi solo con un `.val.json` con `verdict: pass`.
- Gli agenti si passano file in `.graph/`, non riassunti in chat.

| Agente | Modello | Contesto |
|---|---|---|
| planner | opus | repo (una volta) |
| scout | haiku | card |
| implementer | sonnet | card + file elencati |
| validator | sonnet | card + out.json + diff |
| reviewer | opus | diff aggregato |

## Contribuire
Ogni modifica a un agente va con una riga in `CHANGELOG.md` e, se possibile,
con le metriche di un run prima/dopo (`metrics` in state.yaml).
Vedi `ROADMAP.md`.
