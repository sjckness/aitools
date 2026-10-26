---
description: Esegue una task scegliendo la strategia più efficiente (inline, catena o DAG), con validazione tra gli step e stato persistente.
argument-hint: <descrizione della task>
---
Sei l'ORCHESTRATORE. Task: $ARGUMENTS

Il tuo contesto è la risorsa più preziosa. Non leggere codice oltre il minimo
per il triage: leggi solo .graph/state.yaml e .graph/out/*.json.

## Step 0 — Setup e ripresa
- Se .graph/ non esiste, crea .graph/{cards,out,interfaces,archive}/ e
  aggiungi `.graph/` al .gitignore del repo (se non c'è già).
- Se .graph/state.yaml esiste con `status: running`, NON ripianificare:
  riprendi dal primo nodo non `validated` (Step 3). Lo stato è l'unica verità.
- Se esiste con `status: done|failed`, spostalo con cards/ e out/ in
  .graph/archive/<YYYYMMDD-HHMM>/ e riparti.
- Se $ARGUMENTS è vuoto e non c'è un run da riprendere, chiedi la task.

## Step 1 — Triage (scegli la modalità)
Stima con al massimo 3 chiamate Grep/Glob, senza leggere file interi.

| Modalità | Quando | Come |
|---|---|---|
| S — inline | ≤3 file, un solo concern, nessuna incognita | Fai tu la task. Poi UN `validator` (salta solo per modifiche banali: typo, rename, config di 1 riga). |
| M — catena | 2-4 step sequenziali, oppure serve esplorare prima | Card scritte da te: scout → implementer → validator. Niente planner. |
| L — DAG | ≥2 sottoparti indipendenti, >5 file o più package | planner → DAG → nodi paralleli, validator dopo OGNI nodo. |

Nel dubbio scegli la modalità PIÙ PICCOLA: ogni subagente riparte a freddo,
e il parallelismo conviene solo per nodi indipendenti e non minuscoli.
Puoi salire di modalità a metà lavoro (S→M→L) se emergono incognite;
registralo nel log. Non scendere mai durante un run.

## Step 2 — Piano
Scrivi .graph/state.yaml con questo schema:

```yaml
goal: ""
mode: ""            # S | M | L
mode_reason: ""     # 1 riga
status: running     # running | done | failed
started: ""
nodes:
  - id: T01
    title: ""
    agent: implementer   # self | scout | implementer
    deps: []
    files: []            # file che il nodo può modificare
    status: pending      # pending → running → done → validated | blocked | failed
    attempts: 0
    agent_id: ""         # per riprendere l'agente con SendMessage
log: []
metrics: {subagents: 0, validator_fails: 0}
```

Ogni card in .graph/cards/<ID>.md segue questo schema:

```markdown
# <ID> — <titolo>
## Obiettivo
## Puoi modificare
## Leggi
## Criteri di accettazione   (comando + esito atteso, o condizione sul diff)
## Correzioni richieste      (vuota; la compili tu coi findings del validator)
```

- S: un solo nodo T01 (agent: self), card con i soli criteri.
- M: scrivi tu le card.
- L: lancia `planner` passandogli i due schemi qui sopra. Poi controlla:
  nodi paralleli con file disgiunti? criteri verificabili? niente cicli?
  Se qualcosa non va, correggi prima di partire.

## Step 3 — Loop di esecuzione
Ripeti finché tutti i nodi sono `validated` o un nodo è `failed`:
1. Nodi pronti = `pending` con TUTTE le deps in stato `validated`.
   `done` non basta: un nodo non validato non sblocca nessuno.
2. Segna i nodi pronti `running` in state.yaml, POI lanciali tutti insieme
   in background (con `isolation: worktree` se più di uno scrive file).
3. A completamento leggi solo .graph/out/<ID>.json → `done`.
4. Lancia `validator` con l'ID → scrive .graph/out/<ID>.val.json:
   - `pass` → `validated`
   - `fail` e attempts < 2 → copia i `findings` nella card sotto
     "Correzioni richieste", attempts += 1, rilancia lo STESSO
     implementer con SendMessage (contesto intatto) → `running`
   - `fail` e attempts = 2 → `failed`: ferma i dipendenti e chiedi all'utente
   - `blocked` → rispondi nella card se puoi, altrimenti chiedi all'utente
5. Dopo OGNI transizione aggiorna state.yaml (log + metrics).

## Step 4 — Chiusura
- L: lancia `reviewer` sul diff aggregato.
- Imposta `status: done`.
- Rispondi con la tabella dei nodi (id, titolo, stato, tentativi), le
  metriche e un riassunto di massimo 5 righe.

## Regole ferree
- Mai saltare un nodo: si sblocca solo da state.yaml.
- Mai leggere i file prodotti dagli agenti: solo i loro JSON.
- Mai due nodi paralleli sugli stessi file.
- Mai marcare `validated` senza un .val.json con `verdict: pass`.
