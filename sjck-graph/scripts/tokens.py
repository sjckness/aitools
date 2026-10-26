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
file nella card / fuori card, output dei tool, messaggi dei subagenti, system)
sono STIMATE: l'input reale di ogni turno viene diviso in proporzione al
contenuto visibile nel contesto (caratteri/4); `system` è il resto.
Scrive anche .sjck/token-report.json con gli insight (dove si risparmia,
dove si spreca), conservando un eventuale confronto con la baseline.

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


CATS = ("system", "card", "interfaces", "file_read_in_card", "file_read_outside_card",
        "tool_output", "agent_messages", "other")
AGENT_TOOLS = ("Task", "Agent")


def _est(v):
    """Stima grezza in token (caratteri / 4) di un contenuto qualsiasi."""
    if isinstance(v, str):
        return len(v) // 4
    if isinstance(v, list):
        return sum(_est(x) for x in v)
    if isinstance(v, dict):
        if "text" in v:
            return _est(v.get("text"))
        if "content" in v:
            return _est(v.get("content"))
        if v.get("type") == "image":
            return 1500
        try:
            return len(json.dumps(v)) // 4
        except Exception:
            return 0
    return 0


def _norm(p):
    p = str(p or "").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def classify(tool, inp, card_files, root=""):
    """Categoria del risultato di un tool, in base al tool e al file letto."""
    if tool in AGENT_TOOLS:
        return "agent_messages"
    if tool in ("Read", "NotebookRead"):
        fp = _norm((inp or {}).get("file_path") or (inp or {}).get("notebook_path"))
        if root:
            r = _norm(root).rstrip("/") + "/"
            if fp.startswith(r):
                fp = fp[len(r):]
        if ".sjck/cards/" in fp:
            return "card"
        if ".sjck/interfaces/" in fp:
            return "interfaces"
        for f in card_files or ():
            f = _norm(f).rstrip("/")
            if f and (fp == f or fp.startswith(f + "/") or fp.endswith("/" + f)):
                return "file_read_in_card"
        return "file_read_outside_card"
    return "tool_output"


def parse_transcript(path, card_files=(), root=""):
    """Somma la usage dei messaggi assistant di un transcript e la divide per categoria.

    In streaming lo stesso messaggio compare su più righe con lo stesso
    `message.id`: vale l'ultima riga, così niente doppi conteggi.

    Categorie (stimate): il contesto viene ricostruito blocco per blocco
    (caratteri/4) e l'input reale di ogni turno (input + cache) viene diviso
    in proporzione a ciò che c'era nel contesto in quel momento; la parte non
    spiegata dai blocchi visibili va a `system` (prompt di sistema, agenti,
    CLAUDE.md, definizioni dei tool). Una compattazione azzera il contesto.
    Ritorna anche `heavy`: i 5 risultati di tool più grandi (tool, categoria,
    file, token stimati), senza contenuto.
    """
    by_msg = {}
    order = []
    snap = {}          # message id -> contesto stimato prima della risposta
    ctx = {c: 0 for c in CATS}
    tools = {}         # tool_use id -> (nome, input)
    heavy = []
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
            if evt.get("isCompactSummary") or (evt.get("type") == "system" and evt.get("subtype") == "compact_boundary"):
                ctx = {c: 0 for c in CATS}
            msg = evt.get("message")
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            content = msg.get("content")
            if role == "user" or evt.get("type") == "user":
                if isinstance(content, str):
                    ctx["other"] += _est(content)
                elif isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "tool_result":
                            name, tin = tools.get(b.get("tool_use_id"), ("?", {}))
                            cat = classify(name, tin, card_files, root)
                            size = _est(b.get("content"))
                            ctx[cat] += size
                            fp = (tin or {}).get("file_path") or ""
                            heavy.append((size, name, cat, _norm(fp)[-120:]))
                        else:
                            ctx["other"] += _est(b)
                continue
            if role not in (None, "assistant") or evt.get("type") not in (None, "assistant"):
                continue
            usage = msg.get("usage")
            mid = msg.get("id") or evt.get("requestId") or "line-%d" % n
            if isinstance(usage, dict):
                if mid not in by_msg:
                    order.append(mid)
                    snap[mid] = dict(ctx)
                by_msg[mid] = {
                    "model": msg.get("model") if isinstance(msg.get("model"), str) else "unknown",
                    **{k: _int(usage.get(USAGE_FIELDS[k])) for k in KEYS},
                }
            # La risposta resta nel contesto dei turni successivi.
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        tools[b.get("id")] = (b.get("name") or "?", b.get("input") if isinstance(b.get("input"), dict) else {})
                        ctx["other"] += _est(b.get("input"))
                    elif isinstance(b, dict) and b.get("type") == "text":
                        ctx["other"] += _est(b.get("text"))
            ts = evt.get("timestamp")
            if isinstance(ts, str):
                first = first or ts
                last = ts
    out = {k: 0 for k in KEYS}
    cats = {c: 0.0 for c in CATS}
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
        real_in = u["input"] + u["cache_read"] + u["cache_creation"]
        seen = snap.get(mid) or {}
        est = sum(seen.get(c, 0) for c in CATS if c != "system")
        if real_in <= 0:
            continue
        scale = min(1.0, real_in / est) if est else 0.0
        for c in CATS:
            if c != "system":
                cats[c] += seen.get(c, 0) * scale
        cats["system"] += real_in - est * scale
    for m in models.values():
        m["total"] = sum(m[k] for k in KEYS)
    out["total"] = sum(out[k] for k in KEYS)
    out["turns"] = len(order)
    out["models"] = models
    out["categories"] = {c: int(round(v)) for c, v in cats.items() if round(v)}
    heavy.sort(key=lambda h: -h[0])
    out["heavy"] = [{"tokens": h[0], "tool": h[1], "category": h[2], "file": h[3]} for h in heavy[:5] if h[0]]
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
    state = read_json(os.path.join(root, ".sjck", "state.json"), {}) or {}
    files_of = {n.get("id"): n.get("files") or [] for n in state.get("nodes", []) if isinstance(n, dict)}
    by_node = {}
    by_model = {}
    heavy = []
    totals = {k: 0 for k in KEYS}
    for path, meta in src.items():
        if not isinstance(meta, dict):
            continue
        label = meta.get("label") or "unattributed"
        r = parse_transcript(path, files_of.get(label, ()), root)
        if not r or not r["turns"]:
            continue
        e = by_node.setdefault(label, {k: 0 for k in KEYS})
        e.setdefault("turns", 0)
        e.setdefault("agents", 0)
        e.setdefault("models", {})
        e.setdefault("categories", {})
        for k in KEYS:
            e[k] += r[k]
            totals[k] += r[k]
        e["turns"] += r["turns"]
        if meta.get("kind") == "agent":
            e["agents"] += 1
        for c, v in r["categories"].items():
            e["categories"][c] = e["categories"].get(c, 0) + v
        for h in r["heavy"]:
            heavy.append(dict(h, node=label))
        for name, m in r["models"].items():
            e["models"][name] = e["models"].get(name, 0) + m["total"]
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
    heavy.sort(key=lambda h: -h["tokens"])
    return {
        "source": "transcripts",
        "categories_estimated": True,
        "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "totals": totals,
        "cost": prev.get("cost") if isinstance(prev, dict) else None,
        "by_node": by_node,
        "by_model": by_model,
        "heavy": heavy[:5],
    }


def _k(n):
    return "%dk" % round(n / 1000) if n >= 1000 else str(int(n))


def analyze(tokens_data, state):
    """Dove si risparmia e dove si spreca: lista di insight per il Run Viewer.

    Ogni insight: {kind, node, tokens, saving_estimate, title, suggestion}.
    saving_estimate > 0 = token che si potevano risparmiare; < 0 = risparmio
    già ottenuto (mostrato in verde).
    """
    nodes = {n.get("id"): n for n in (state or {}).get("nodes", []) if isinstance(n, dict)}
    bn = tokens_data.get("by_node") or {}
    out = []
    for nid, e in bn.items():
        n = nodes.get(nid) or {}
        cats = e.get("categories") or {}
        inp = e.get("input", 0) + e.get("cache_read", 0) + e.get("cache_creation", 0)
        if not inp:
            continue
        # Card povere: il nodo esplora file che non erano nella card.
        outside = cats.get("file_read_outside_card", 0)
        if nid not in ("ORCH", "PLAN", "unattributed") and outside > 0.2 * inp and outside > 5000:
            out.append({"kind": "card", "node": nid, "tokens": outside, "saving_estimate": int(outside * 0.7),
                        "title": "%s reads files outside its card (%s, %d%% of its input)" % (nid, _k(outside), round(outside / inp * 100)),
                        "suggestion": "Add the files it needed to the card's files list or extract an interface: the next run skips the exploration."})
        # Cache: un agente che non riusa la cache paga tutto il contesto ogni turno.
        hit = e.get("cache_read", 0) / inp
        if e.get("turns", 0) >= 4 and hit < 0.5:
            out.append({"kind": "cache", "node": nid, "tokens": inp, "saving_estimate": int(inp * (0.5 - hit) * 0.9),
                        "title": "%s cache hit only %d%%" % (nid, round(hit * 100)),
                        "suggestion": "Context changes at the top each turn (e.g. edited files re-read early): keep the card and stable instructions first."})
        # Spreco: nodi falliti o con tentativi ripetuti.
        att = n.get("attempts") or 0
        if n.get("status") in ("failed", "blocked") or att:
            share = e.get("total", 0) if n.get("status") in ("failed", "blocked") else int(e.get("total", 0) * att / (att + 1))
            if share:
                out.append({"kind": "waste", "node": nid, "tokens": share, "saving_estimate": share,
                            "title": "%s: %s spent on %s" % (nid, _k(share), "a failed node" if n.get("status") in ("failed", "blocked") else "%d retried attempt(s)" % att),
                            "suggestion": "Check the validator feedback: a sharper acceptance criterion in the card usually removes the retry."})
        # Modello: opus su un nodo piccolo approvato al primo colpo.
        big = sum(v for m, v in (e.get("models") or {}).items() if "opus" in m)
        if big and n.get("status") == "validated" and not att and len(n.get("files") or []) <= 2:
            out.append({"kind": "model", "node": nid, "tokens": big, "saving_estimate": int(big * 0.4),
                        "title": "%s used opus on a small node that passed first time" % nid,
                        "suggestion": "Next time plan it with sonnet/medium; keep opus for nodes many others depend on."})
    # Il guadagno del contratto: l'orchestratore riceve JSON, non i file.
    orch = bn.get("ORCH") or {}
    sub_reads = sum((e.get("categories") or {}).get("file_read_in_card", 0) for k2, e in bn.items() if k2 not in ("ORCH", "PLAN"))
    msgs = (orch.get("categories") or {}).get("agent_messages", 0)
    if sub_reads and msgs < sub_reads:
        out.append({"kind": "contract", "node": "ORCH", "tokens": msgs, "saving_estimate": -(sub_reads - msgs), "good": True,
                    "title": "Orchestrator context kept small: agent reports %s vs %s of files read by the nodes" % (_k(msgs), _k(sub_reads)),
                    "suggestion": "This is what the node contract saves compared to one agent reading everything."})
    for h in tokens_data.get("heavy") or []:
        if h.get("tokens", 0) >= 8000:
            out.append({"kind": "heavy", "node": h.get("node"), "tokens": h["tokens"], "saving_estimate": int(h["tokens"] * 0.5),
                        "title": "Largest tool output: %s %s (%s, ~%s)" % (h.get("tool"), h.get("file") or "", h.get("category"), _k(h["tokens"])),
                        "suggestion": "Read a range (offset/limit) or grep first instead of the whole output."})
    out.sort(key=lambda i: -abs(i.get("saving_estimate") or 0))
    return {"insights": out[:8], "estimated": True}


def refresh(root):
    data = build(root)
    write_json(os.path.join(root, ".sjck", "tokens.json"), data)
    rp = os.path.join(root, ".sjck", "token-report.json")
    prev = read_json(rp, {}) or {}
    report = analyze(data, read_json(os.path.join(root, ".sjck", "state.json"), {}) or {})
    if isinstance(prev, dict) and prev.get("compare"):
        report["compare"] = prev["compare"]  # confronto con la baseline (evals), se esiste
    write_json(rp, report)
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
