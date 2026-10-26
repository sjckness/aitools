---
name: project-onboard
description: Usa questa skill quando l'utente chiede di "fare onboarding" di un repo, di creare o aggiornare il CLAUDE.md, di mappare l'architettura del progetto, oppure quando inizi un lavoro sostanzioso in un repo che non ha CLAUDE.md (in quel caso proponilo in una riga prima di procedere). Produce un CLAUDE.md corto più file di dettaglio per modulo in .claude/map/.
---
# Project onboarding

Obiettivo: dare a Claude (e a ogni subagente) il MINIMO contesto che evita di
esplorare il repo. Il CLAUDE.md viene caricato in ogni sessione e da ogni
agente: ogni riga ha un costo. Il dettaglio va nei file di mappa, letti solo
quando servono.

## 1. Ricognizione (economica)
- `git ls-files | head -400`, file di build (package.xml, CMakeLists.txt,
  setup.py, pyproject.toml, package.json, Cargo.toml...), README, CI
  (.github/workflows), launch/config.
- Individua i MODULI: package ROS 2, servizi, librerie, app.
- Se i moduli sono più di 4, lancia in parallelo uno `Explore` per gruppo di
  moduli, chiedendo a ciascuno di restituire SOLO lo schema del punto 3
  (massimo ~60 righe per modulo). Altrimenti fallo tu.

## 2. Se esiste già un CLAUDE.md
Non sovrascriverlo: integra. Le righe scritte a mano dall'utente restano
invariate; segnala in chat ciò che ti sembra superato invece di cancellarlo.

## 3. File di mappa: .claude/map/<modulo>.md
Per modulo, solo fatti verificati (con percorso):
- scopo (1 riga)
- entry point e file principali
- interfacce: topic/servizi/azioni ROS (tipo, nome, QoS se non default),
  API pubbliche, endpoint, parametri
- dipendenze verso altri moduli
- come si builda e testa SOLO quel modulo
- trappole note (cose che rompono, ordini di avvio, frame TF...)

## 4. CLAUDE.md (massimo ~120 righe)
```markdown
# <progetto>
<2 righe: cosa fa>

## Comandi
build / test / lint / run, esattamente come si lanciano

## Architettura
<diagramma testuale dei moduli e del flusso dati, 5-15 righe>

## Moduli
| modulo | scopo | dettaglio |
|---|---|---|
| foo | ... | .claude/map/foo.md |

## Convenzioni
stile, naming, dove vanno i test, branch/commit

## Non toccare / attenzione
file generati, config hardware, parametri tarati a mano
```

## 5. Verifica
Esegui davvero i comandi di build/test che hai scritto (almeno uno, il più
veloce). Se un comando non funziona, correggilo o marcalo `(non verificato)`.

## 6. Chiusura
Rispondi con: righe del CLAUDE.md, numero di file di mappa, comandi verificati
e cosa non sei riuscito a determinare (domande per l'utente, massimo 3).
