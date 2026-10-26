# Critico (agente `critic`, read-only)

Tre punti d'intervento (campo `at` in `state.critic`):
- `plan`: solo modalità L, dopo uno `plan_score` con `verdict: ok`. Proposta = il DAG.
- `findings`: posizionamento dei findings accettati al checkpoint (vedi reference/findings.md).
- `failure`: un nodo `failed`, PRIMA di chiedere all'utente. Proposta = come gestirlo.

Input al critico: SOLO la proposta + il plan_score (o i findings in questione) + il goal.
Mai codice, mai la conversazione. Indica nel prompt quali file `.graph/` può leggere.
Risposta: `{"verdict":"approve|object","points":[...],"alternative":"..."}`.

## Protocollo (max 2 round)
1. Round 1: invii la proposta. `approve` → procedi.
2. `object` → valuti i punti: se sono fondati, correggi la proposta; altrimenti scrivi
   le controdeduzioni. Round 2: reinvii proposta (corretta) + controdeduzioni.
3. Sessione non interattiva: dopo il round 2 vale la proposta dell'orchestratore; annotalo nel
   log e in `resolution` ("non interattivo: proposta dell'orchestratore").
   Altrimenti, se dopo il round 2 il disaccordo resta → chiedi all'utente presentando le due
   posizioni, ciascuna in max 3 righe. Decide l'utente.

## Registrazione
Ogni round è un oggetto in `state.critic`:
`{"at":"plan|findings|failure","round":1|2,"verdict":"approve|object","points":[],"resolution":""}`
`resolution` descrive come si è chiuso (es. "piano corretto", "utente: opzione A").
Conta il lancio nei `metrics.subagents`. Un `object` non blocca il run da solo: conta
il protocollo, non il parere.
