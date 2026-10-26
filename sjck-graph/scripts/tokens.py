#!/usr/bin/env python3
"""Token reali di un run sjck-graph -> .sjck/tokens.json (v0.4, parte A minima).

Legge i transcript di Claude Code (JSONL) e somma la `usage` dei messaggi
dell'assistente: input, output, cache_read, cache_creation, per modello.

Fonti:
  - transcript della sessione principale (`transcript_path` dell'hook Stop):
    attribuito a ORCH durante un run, a PLAN se lo stato è "planned";
  - transcript dei subagenti (`agent_transcript_path` dell'hook SubagentStop):
    attribuiti al nodo con lo stesso `agent_id` in state.json, oppure all'unico
    nodo running senza agent_id; altrimenti a `unattributed`.
Le fonti già viste restano in .sjck/token-sources.json, così ogni ricalcolo
riparte dai transcript (idempotente) e tokens.json si aggiorna a fine di ogni
nodo e a fine di ogni turno, mai a ogni tool call.

Privacy: legge solo i campi `usage`, `model`, `id` e `timestamp`; non copia
mai testo dei messaggi o contenuto dei file.

Il formato dei transcript non è un contratto stabile: righe malformate o campi
sconosciuti vengono ignorati. Le categorie di contesto (card, interfacce,
letture fuori card…) non sono ancora calcolate: ogni nodo riporta invece la
suddivisione per tipo di token (`types`).

Uso:
  tokens.py --hook            dall'hook Stop/SubagentStop (JSON su stdin)
  tokens.py [--cwd DIR]       ricalcola dalle fonti registrate
  tokens.py --add PATH LABEL  registra un transcript a mano e ricalcola
Non fallisce mai in modo rumoroso: un errore qui non deve bloccare Claude.
"""
import datetime
import json
import os
import sys
import tempfile

KEYS = ("input", "output", "cache_read", "cache_creation")
USAGE_FIELDS = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cache_read_input_tokens",
    "cache_creation": "cache_creation_input_tokens",
}


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def parse_transcript(path):
    """Somma la usage dei messaggi assistant di un transcript.

    In streaming lo stesso messaggio compare su più righe con lo stesso
    `message.id`: vale l'ultima riga, così niente doppi conteggi.
    Ritorna {input, output, cache_read, cache_creation, total, turns, models,
    first, last} oppure None se il file non è leggibile.
    """
    by_msg = {}
    order = []
    first = last = None
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    with f:
        for n, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except ValueError:
                continue
            if not isinstance(evt, dict):
                continue
            msg = evt.get("message")
            if not isinstance(msg, dict) or msg.get("role") not in (None, "assistant"):
                continue
            if evt.get("type") not in (None, "assistant"):
                continue
            usage = msg.get("usage")
            if not isinstance(usage, dict):
                continue
            mid = msg.get("id") or evt.get("requestId") or "line-%d" % n
            if mid not in by_msg:
                order.append(mid)
            by_msg[mid] = {
                "model": msg.get("model") if isinstance(msg.get("model"), str) else "unknown",
                **{k: _int(usage.get(USAGE_FIELDS[k])) for k in KEYS},
            }
            ts = evt.get("timestamp")
            if isinstance(ts, str):
                first = first or ts
                last = ts
    out = {k: 0 for k in KEYS}
    models = {}
    for mid in order:
        u = by_msg[mid]
        if u["model"] == "<synthetic>":
            continue
        for k in KEYS:
            out[k] += u[k]
        m = models.setdefault(u["model"], {k: 0 for k in KEYS})
        for k in KEYS:
            m[k] += u[k]
    for m in models.values():
        m["total"] = sum(m[k] for k in KEYS)
    out["total"] = sum(out[k] for k in KEYS)
    out["turns"] = len(order)
    out["models"] = models
    out["first"] = first
    out["last"] = last
    return out


def node_for_agent(state, agent_id):
    """Nodo di un subagente: stesso agent_id, oppure l'unico running senza agent_id."""
    nodes = [n for n in (state or {}).get("nodes", []) if isinstance(n, dict)]
    if agent_id:
        for n in nodes:
            if n.get("agent_id") == agent_id:
                return n.get("id")
    free = [n for n in nodes if n.get("status") == "running" and not n.get("agent_id")]
    if len(free) == 1:
        return free[0].get("id")
    return "unattributed"


def sources_path(root):
    return os.path.join(root, ".sjck", "token-sources.json")


def add_source(root, path, label, kind):
    """Registra un transcript. La prima etichetta vince (un subagente non cambia nodo)."""
    sp = sources_path(root)
    src = read_json(sp, {})
    if not isinstance(src, dict):
        src = {}
    if path not in src:
        src[path] = {"label": label, "kind": kind}
        write_json(sp, src)
    return src


def build(root):
    """Ricalcola tokens.json dalle fonti registrate."""
    src = read_json(sources_path(root), {}) or {}
    by_node = {}
    by_model = {}
    totals = {k: 0 for k in KEYS}
    for path, meta in src.items():
        if not isinstance(meta, dict):
            continue
        r = parse_transcript(path)
        if not r or not r["turns"]:
            continue
        label = meta.get("label") or "unattributed"
        e = by_node.setdefault(label, {k: 0 for k in KEYS})
        e.setdefault("turns", 0)
        e.setdefault("agents", 0)
        e.setdefault("models", {})
        for k in KEYS:
            e[k] += r[k]
            totals[k] += r[k]
        e["turns"] += r["turns"]
        if meta.get("kind") == "agent":
            e["agents"] += 1
        for name, m in r["models"].items():
            em = e["models"].setdefault(name, 0)
            e["models"][name] = em + m["total"]
            bm = by_model.setdefault(name, {k: 0 for k in KEYS})
            for k in KEYS:
                bm[k] += m[k]
    for e in by_node.values():
        e["total"] = sum(e[k] for k in KEYS)
        e["types"] = {k: e[k] for k in KEYS}
    for m in by_model.values():
        m["total"] = sum(m[k] for k in KEYS)
    totals["total"] = sum(totals[k] for k in KEYS)
    prev = read_json(os.path.join(root, ".sjck", "tokens.json"), {}) or {}
    return {
        "source": "transcripts",
        "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "totals": totals,
        "cost": prev.get("cost") if isinstance(prev, dict) else None,
        "by_node": by_node,
        "by_model": by_model,
    }


def refresh(root):
    data = build(root)
    write_json(os.path.join(root, ".sjck", "tokens.json"), data)
    # Il Run Viewer statico si rigenera solo se esiste già (/sjck-view).
    if os.path.exists(os.path.join(root, ".sjck", "view.html")):
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import graph_view
            graph_view.render(root)
        except Exception:
            pass
    return data


def from_hook(inp):
    root = inp.get("cwd") or os.getcwd()
    state = read_json(os.path.join(root, ".sjck", "state.json"))
    if not isinstance(state, dict):
        return None  # nessun run sjck qui: niente da fare
    event = inp.get("hook_event_name") or ""
    if event == "SubagentStop" or inp.get("agent_transcript_path"):
        path = inp.get("agent_transcript_path")
        if not path:
            return None
        add_source(root, path, node_for_agent(state, inp.get("agent_id")), "agent")
    else:
        path = inp.get("transcript_path")
        if not path:
            return None
        add_source(root, path, "PLAN" if state.get("status") == "planned" else "ORCH", "main")
    return refresh(root)


def main(argv):
    try:
        if "--hook" in argv:
            raw = sys.stdin.read()
            from_hook(json.loads(raw) if raw.strip() else {})
            return 0
        root = os.getcwd()
        if "--cwd" in argv:
            root = argv[argv.index("--cwd") + 1]
        if "--add" in argv:
            i = argv.index("--add")
            add_source(root, os.path.abspath(argv[i + 1]), argv[i + 2], "manual")
        data = refresh(root)
        t = data["totals"]
        print("tokens: %d total (input %d, output %d, cache read %d, cache write %d), %d nodes"
              % (t["total"], t["input"], t["output"], t["cache_read"], t["cache_creation"], len(data["by_node"])))
        return 0
    except Exception as e:  # mai bloccare Claude
        if "--hook" not in argv:
            print("tokens: %s" % e, file=sys.stderr)
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
