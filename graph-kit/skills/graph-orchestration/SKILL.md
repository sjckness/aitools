---
name: graph-orchestration
description: Usa questa skill per task di sviluppo non banali che toccano più file, più package o richiedono più step (feature nuove, refactor, migrazioni, integrazione di componenti), oppure quando l'utente chiede di lavorare "a grafo", "con gli agenti", "in parallelo" o nomina planner/validator. Sceglie da sola tra lavoro inline, catena breve o DAG parallelo, valida ogni step e tiene lo stato in .graph/state.json. Non usarla per domande, spiegazioni o modifiche di poche righe.
---
# Orchestrazione a grafo

Sei l'ORCHESTRATORE. Il tuo contesto è la risorsa più preziosa: non leggere
codice oltre il minimo per il triage; leggi solo .graph/state.json e
.graph/out/*.json.

## Override dell'utente (hanno sempre la precedenza)
L'utente può indicare nel prompt, in qualsiasi forma:
- la modalità: "modalità S/M/L", "--mode M", "fallo da solo", "usa il DAG";
- gli agenti: "usa solo scout e validator", "niente planner", "senza validator";
- il parallelismo: "max 2 agenti in parallelo".
Rispettali alla lettera. Se un override è chiaramente inefficiente
(es. DAG per una modifica di 2 righe), eseguilo comunque ma segnalalo in UNA
riga in `mode_reason`. Unica eccezione: senza validator un nodo non diventa
`validated` ma `done-unverified`, e lo dici nel riepilogo finale.

## Step 0 — Setup e ripresa
- Se .graph/ non esiste, crea .graph/{cards,out,interfaces,archive}/ e
  aggiungi `.graph/` al .gitignore del repo, se manca.
- Se esiste .graph/state.json con `status: running`, NON ripianificare:
  riprendi dal primo nodo non `validated` (Step 3).
- Se esiste con `status: planned` (preparato da `graph-plan`), NON rifare
  triage e piano: controlla solo che le card esistano, che i nodi paralleli
  abbiano file disgiunti e che non ci siano cicli; poi imposta
  `status: running` e vai allo Step 3. Rispetta `model`, `effort` e `budget`
  di ogni nodo. Se il task dell'utente è diverso dal `goal` del piano, chiedi
  quale eseguire.
- Se esiste con `status: done|failed`, sposta state.json, cards/ e out/ in
  .graph/archive/<YYYYMMDD-HHMM>/ e riparti.
- Leggi CLAUDE.md e .claude/map/ (se esistono) SOLO per scegliere i file
  rilevanti: non copiarli nelle card, cita i percorsi.

## Step 1 — Triage
Stima con al massimo 3 chiamate Grep/Glob, senza leggere file interi.

| Modalità | Quando | Come |
|---|---|---|
| S — inline | ≤3 file, un solo concern, nessuna incognita | Fai tu la task. Poi UN `validator` (salta solo per typo, rename, config di 1 riga). |
| M — catena | 2-4 step sequenziali, o serve esplorare prima | Card scritte da te: scout → implementer → validator. Niente planner. |
| L — DAG | ≥2 sottoparti indipendenti, >5 file o più package | planner → DAG → nodi paralleli, validator dopo OGNI nodo. |

Se la task è grande e vaga (obiettivo poco chiaro, nessun modo evidente di
verificarla), proponi in una riga di passare prima da `/graph-plan`.

Nel dubbio scegli la modalità PIÙ PICCOLA. Puoi salire (S→M→L) se emergono
incognite, registrandolo nel log; non scendere mai durante un run.

## Step 2 — Piano
Scrivi .graph/state.json (JSON valido, 2 spazi di indentazione):

```json
{
  "goal": "",
  "mode": "S|M|L",
  "mode_reason": "1 riga",
  "status": "running",
  "started": "ISO-8601",
  "nodes": [
    {"id": "T01", "title": "", "agent": "self|scout|implementer",
     "deps": [], "files": [], "status": "pending", "attempts": 0, "agent_id": ""}
  ],
  "log": ["HH:MM T01 pending → running"],
  "metrics": {"subagents": 0, "validator_fails": 0}
}
```
Stati nodo: pending → running → done → validated (oppure blocked, failed,
done-unverified).

Ogni card in .graph/cards/<ID>.md:
```markdown
# <ID> — <titolo>
## Obiettivo
## Puoi modificare
## Leggi
## Criteri di accettazione   (comando + esito atteso, o condizione sul diff)
## Correzioni richieste      (vuota; la compili coi findings del validator)
```

- S: un nodo T01 (agent: self).
- M: scrivi tu le card.
- L: lancia `planner` passandogli i due schemi qui sopra, poi controlla:
  nodi paralleli con file disgiunti? criteri verificabili? niente cicli?

## Step 3 — Loop di esecuzione
Ripeti finché tutti i nodi sono `validated` o uno è `failed`:
1. Pronti = `pending` con TUTTE le deps `validated` (`done` non basta).
2. Segnali `running` in state.json, POI lanciali tutti insieme in background
   (`isolation: worktree` se più di uno scrive file).
3. A completamento leggi solo .graph/out/<ID>.json → `done`.
4. Lancia `validator` sull'ID → .graph/out/<ID>.val.json:
   - `pass` → `validated`
   - `fail`, attempts < 2 → findings nella card sotto "Correzioni richieste",
     attempts += 1, riprendi lo STESSO implementer con SendMessage → `running`
   - `fail`, attempts = 2 → `failed`: ferma i dipendenti, chiedi all'utente
   - `blocked` → rispondi nella card se puoi, altrimenti chiedi all'utente
5. Dopo OGNI transizione riscrivi state.json (log + metrics): il
   visualizzatore si aggiorna da lì.

## Step 4 — Chiusura
- L: lancia `reviewer` sul diff aggregato.
- `status: done`. Rispondi con la tabella dei nodi (id, titolo, stato,
  tentativi), le metriche e un riassunto di massimo 5 righe.

## Regole ferree
- Mai saltare un nodo: si sblocca solo da state.json.
- Mai leggere i file prodotti dagli agenti: solo i loro JSON.
- Mai due nodi paralleli sugli stessi file.
- Mai `validated` senza un .val.json con `verdict: pass`.
