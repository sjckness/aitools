"""Plan score sjck-graph v0.3 (sezione A): metriche e verdetto sul DAG.

Solo standard library, Python 3.9+.

API:
    score(state, cards_dir) -> {"width", "critical_path", "file_overlap",
                                "avg_card_tokens", "verdict", "reasons"}
  - width: massimo numero di nodi con lo stesso livello topologico
    (livello = 1 + max livello delle deps; radici = 1).
  - critical_path: nodi del cammino piu' lungo.
  - file_overlap: coppie di nodi senza relazione antenato/discendente che
    condividono almeno un file (una voce terminante con "/" copre la dir).
  - avg_card_tokens: media arrotondata di len(testo)//4 sulle card esistenti.
  - verdict: "reject" se reasons non e' vuota (ciclo, dep inesistente,
    overlap, card mancante, card oltre budget.context_tokens, card senza
    criteri di accettazione), altrimenti "ok".
  Con un ciclo width e critical_path valgono 0.

CLI:
    python3 plan_score.py --cwd DIR
  Legge DIR/.sjck/state.json, calcola con DIR/.sjck/cards, scrive
  `plan_score` nello stato (altri campi preservati) e stampa il JSON.
  Exit code: 0 = ok, 1 = reject, 2 = stato mancante o non leggibile.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import state_schema  # noqa: E402
from cards import count_criteria  # noqa: E402


def _norm(p):
    is_dir = p.endswith("/")
    n = os.path.normpath(p)
    if n.startswith("./"):
        n = n[2:]
    return n, is_dir


def _covers(a, b):
    """True se la voce a (path, is_dir) copre la voce b."""
    (pa, da), (pb, _) = a, b
    if pa == pb:
        return True
    return da and pb.startswith(pa.rstrip("/") + "/")


def _shared(fa, fb):
    for a in fa:
        for b in fb:
            if _covers(a, b):
                return b[0]
            if _covers(b, a):
                return a[0]
    return None


def _find_cycle(ids, deps):
    color = {}
    stack = []

    def dfs(u):
        color[u] = 1
        stack.append(u)
        for v in deps[u]:
            if color.get(v) == 1:
                return stack[stack.index(v):] + [v]
            if v not in color:
                r = dfs(v)
                if r:
                    return r
        stack.pop()
        color[u] = 2
        return None

    for i in ids:
        if i not in color:
            r = dfs(i)
            if r:
                return r
    return None


def score(state, cards_dir):
    st = state_schema.normalize(state)
    nodes = [n for n in st.get("nodes", []) if isinstance(n, dict) and "id" in n]
    ids = [n["id"] for n in nodes]
    idset = set(ids)
    by_id = {n["id"]: n for n in nodes}
    reasons = []
    deps = {}
    for n in nodes:
        ds = []
        for d in n.get("deps", []) or []:
            if d in idset:
                ds.append(d)
            else:
                reasons.append("dep inesistente: %s dipende da %s" % (n["id"], d))
        deps[n["id"]] = ds

    cyc = _find_cycle(ids, deps)
    width = cp = overlap = 0
    if cyc:
        reasons.append("ciclo: " + " → ".join(cyc))
    else:
        level = {}

        def lv(u):
            if u not in level:
                level[u] = 1 + max([lv(d) for d in deps[u]] or [0])
            return level[u]

        for i in ids:
            lv(i)
        counts = {}
        for v in level.values():
            counts[v] = counts.get(v, 0) + 1
        width = max(counts.values()) if counts else 0
        cp = max(level.values()) if level else 0

        anc = {}

        def ancestors(u):
            if u not in anc:
                s = set()
                for d in deps[u]:
                    s.add(d)
                    s |= ancestors(d)
                anc[u] = s
            return anc[u]

        files = {i: [_norm(f) for f in by_id[i].get("files", []) or []]
                 for i in ids}
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                a, b = ids[x], ids[y]
                if a in ancestors(b) or b in ancestors(a):
                    continue
                f = _shared(files[a], files[b])
                if f is not None:
                    overlap += 1
                    reasons.append("overlap: %s e %s condividono %s" % (a, b, f))

    tokens = []
    for i in ids:
        path = os.path.join(cards_dir, i + ".md")
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            reasons.append("card mancante: %s" % i)
            continue
        t = len(text) // 4
        tokens.append(t)
        budget = by_id[i].get("budget", {}).get("context_tokens")
        if isinstance(budget, int) and t > budget:
            reasons.append("card oltre budget: %s (%d > %d token)" % (i, t, budget))
        if count_criteria(text) == 0:
            reasons.append("card senza criteri di accettazione: %s" % i)

    avg = int(round(sum(tokens) / float(len(tokens)))) if tokens else 0
    return {"width": width, "critical_path": cp, "file_overlap": overlap,
            "avg_card_tokens": avg,
            "verdict": "reject" if reasons else "ok", "reasons": reasons}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Calcola il plan_score")
    ap.add_argument("--cwd", default=".")
    args = ap.parse_args(argv)
    state = state_schema.load_state(args.cwd)
    if not isinstance(state, dict):
        print("stato mancante o non leggibile: %s/.sjck/state.json" % args.cwd,
              file=sys.stderr)
        return 2
    res = score(state, os.path.join(args.cwd, ".sjck", "cards"))
    state["plan_score"] = res
    state_schema.save_state(args.cwd, state)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if res["verdict"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
