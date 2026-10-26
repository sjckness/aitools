#!/usr/bin/env python3
"""Rigenera .graph/view.html da .graph/state.json.

Modalità:
  --hook          letto da un hook PostToolUse: agisce solo se il file
                  scritto è .graph/state.json, altrimenti esce subito.
  --cwd DIR       root del progetto (default: directory corrente).
  --open          apre il file nel browser dopo averlo generato.
Non fallisce mai in modo rumoroso: un errore qui non deve bloccare Claude.
"""
import html
import json
import os
import sys
import webbrowser

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from state_schema import normalize
except Exception:  # fallback: stato usato così com'è
    normalize = None
try:
    import watchdog
except Exception:  # nessun overlay della usage
    watchdog = None

COLORS = {
    "pending": "#9aa0a6", "running": "#3b82f6", "done": "#a855f7",
    "validated": "#16a34a", "blocked": "#f59e0b", "failed": "#dc2626",
    "done-unverified": "#eab308",
}

PAGE = """<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>graph-kit</title>
<style>
:root{--bg:#fafafa;--fg:#1f2328;--mut:#656d76;--card:#fff;--line:#d0d7de}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--mut:#8d96a0;--card:#161b22;--line:#30363d}}
*{box-sizing:border-box}body{margin:0;padding:16px;background:var(--bg);color:var(--fg);
font:14px/1.5 system-ui,-apple-system,sans-serif;max-width:1100px;margin:auto}
h1{font-size:18px;margin:0 0 4px}.mut{color:var(--mut)}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
.pill{padding:2px 10px;border-radius:999px;color:#fff;font-size:12px}
.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;margin:12px 0;overflow-x:auto}
table{border-collapse:collapse;width:100%}td,th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;font-size:13px}
h2{font-size:14px;margin:0 0 6px}
pre{margin:0;font-size:12px;white-space:pre-wrap}
</style></head><body>
<h1>__GOAL__</h1>
<div class="mut">modalità <b>__MODE__</b> · __REASON__ · stato <b>__STATUS__</b> · aggiornato __UPDATED__</div>
<div class="bar">__COUNTS__</div>
<div class="box"><pre class="mermaid">__MERMAID__</pre></div>
<div class="box"><table><tr><th>id</th><th>titolo</th><th>agente</th><th>stato</th><th>tentativi</th><th>deps</th><th>model/effort</th><th>usage</th><th>drift r/w</th><th>watchdog warn/stop</th></tr>__ROWS__</table></div>
__PANELS__
<div class="box"><b>Log</b><pre>__LOG__</pre></div>
<div class="mut">metriche: __METRICS__</div>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
mermaid.initialize({startOnLoad:true,theme:matchMedia('(prefers-color-scheme: dark)').matches?'dark':'default'});
setTimeout(function(){location.reload()},2000);
</script></body></html>"""


def project_root(args):
    if "--cwd" in args:
        return args[args.index("--cwd") + 1]
    return os.getcwd()


def from_hook():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return None
    path = (data.get("tool_input") or {}).get("file_path", "")
    if not path.replace("\\", "/").endswith(".graph/state.json"):
        return None
    return os.path.dirname(os.path.dirname(os.path.abspath(path)))


def node_label(n):
    title = str(n.get("title", "")).replace('"', "'")[:40]
    return '%s["%s<br/>%s"]' % (n["id"], n["id"], title)


NODATA = '<span class="mut">nessun dato</span>'


def read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if isinstance(o, dict):
                    out.append(o)
    except OSError:
        pass
    return out


def esc(v):
    return html.escape(str(v))


def panel(title, body):
    return '<div class="box"><h2>%s</h2>%s</div>' % (esc(title), body or NODATA)


def table(head, rows):
    if not rows:
        return ""
    return "<table><tr>%s</tr>%s</table>" % (
        "".join("<th>%s</th>" % esc(h) for h in head),
        "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r) for r in rows))


def panels(s, root):
    g = os.path.join(root, ".graph")
    ps = s.get("plan_score")
    body = ""
    if isinstance(ps, dict) and ps:
        body = table(["width", "critical_path", "file_overlap", "avg_card_tokens", "verdict", "reasons"],
                     [[esc(ps.get(k, "")) for k in ("width", "critical_path", "file_overlap",
                                                    "avg_card_tokens", "verdict")]
                      + [esc("; ".join(str(x) for x in (ps.get("reasons") or [])))]])
    out = [panel("Plan score", body)]

    last = {}
    for c in s.get("critic") or []:
        if isinstance(c, dict):
            last[c.get("at", "?")] = c
    out.append(panel("Critico", table(
        ["at", "round", "verdict", "points", "resolution"],
        [[esc(a), esc(c.get("round", "")), esc(c.get("verdict", "")),
          esc("; ".join(str(x) for x in (c.get("points") or []))), esc(c.get("resolution", ""))]
         for a, c in last.items()])))

    fs = read_jsonl(os.path.join(g, "findings.jsonl"))
    cnt = {}
    for f in fs:
        cnt[f.get("status", "?")] = cnt.get(f.get("status", "?"), 0) + 1
    body = ""
    if fs:
        body = ('<div class="mut">%s</div>' % esc(", ".join("%s: %d" % kv for kv in cnt.items()))
                + table(["id", "severity", "kind", "file", "what", "status", "placement"],
                        [[esc(f.get("id", "")), esc(f.get("severity", "")), esc(f.get("kind", "")),
                          esc(f.get("file", "")), esc(str(f.get("what", ""))[:80]),
                          esc(f.get("status", "")), esc(f.get("placement", ""))] for f in fs]))
    out.append(panel("Findings", body))

    ev = read_jsonl(os.path.join(g, "watchdog.jsonl"))[-10:]
    out.append(panel("Watchdog", table(
        ["ts", "node", "kind", "level", "action", "detail"],
        [[esc(e.get("ts", "")), esc(e.get("node", "")), esc(e.get("kind", "")),
          esc(e.get("level", "")), esc(e.get("action", "")), esc(e.get("detail", ""))]
         for e in ev])))
    return "\n".join(out)


def render(root):
    state_path = os.path.join(root, ".graph", "state.json")
    with open(state_path, encoding="utf-8") as f:
        s = json.load(f)
    if normalize is not None:
        try:
            s = normalize(s)
        except Exception:
            pass
    nodes = [n for n in (s.get("nodes") or []) if isinstance(n, dict)]
    if watchdog is not None:
        try:
            with open(os.path.join(root, ".graph", "watchdog_state.json"),
                      encoding="utf-8") as f:
                um = watchdog.usage_map(
                    json.load(f), [n["id"] for n in nodes if "id" in n])
            nodes = [dict(n, usage=um[n["id"]]) if n.get("id") in um else n
                     for n in nodes]
        except Exception:
            pass

    lines = ["flowchart LR"]
    for n in nodes:
        lines.append("  " + node_label(n))
        for d in n.get("deps", []):
            lines.append("  %s --> %s" % (d, n["id"]))
    for n in nodes:
        c = COLORS.get(n.get("status"), "#9aa0a6")
        lines.append("  style %s fill:%s,color:#fff,stroke:%s" % (n["id"], c, c))

    counts = {}
    for n in nodes:
        counts[n.get("status", "?")] = counts.get(n.get("status", "?"), 0) + 1
    pills = "".join(
        '<span class="pill" style="background:%s">%s %d</span>'
        % (COLORS.get(k, "#9aa0a6"), html.escape(k), v) for k, v in counts.items())

    def row(n):
        b = n.get("budget") if isinstance(n.get("budget"), dict) else {}
        u = n.get("usage") if isinstance(n.get("usage"), dict) else {}
        cells = [esc(n.get("id", "")), esc(n.get("title", "")), esc(n.get("agent", "")),
                 '<span class="pill" style="background:%s">%s</span>'
                 % (COLORS.get(n.get("status"), "#9aa0a6"), esc(n.get("status", ""))),
                 esc(n.get("attempts", 0)), esc(", ".join(n.get("deps", []))),
                 esc("%s/%s" % (n.get("model", "inherit"), n.get("effort", "medium"))),
                 esc("%s/%s" % (u.get("tool_calls", 0), b.get("tool_calls", 40))),
                 esc("%s/%s" % (u.get("reads_outside_card", 0), u.get("writes_outside_card", 0))),
                 esc("%s/%s" % (u.get("watchdog_warnings", 0), u.get("watchdog_stops", 0)))]
        return "<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in cells)

    rows = "".join(row(n) for n in nodes)

    import datetime
    out = (PAGE
           .replace("__GOAL__", html.escape(str(s.get("goal", "graph-kit"))))
           .replace("__MODE__", html.escape(str(s.get("mode", "?"))))
           .replace("__REASON__", html.escape(str(s.get("mode_reason", ""))))
           .replace("__STATUS__", html.escape(str(s.get("status", "?"))))
           .replace("__UPDATED__", datetime.datetime.now().strftime("%H:%M:%S"))
           .replace("__COUNTS__", pills)
           .replace("__MERMAID__", html.escape("\n".join(lines)))
           .replace("__ROWS__", rows)
           .replace("__PANELS__", panels(s, root))
           .replace("__LOG__", html.escape("\n".join(s.get("log", [])[-30:])))
           .replace("__METRICS__", html.escape(json.dumps(s.get("metrics", {})))))
    view = os.path.join(root, ".graph", "view.html")
    with open(view, "w", encoding="utf-8") as f:
        f.write(out)
    return view


def main():
    args = sys.argv[1:]
    root = from_hook() if "--hook" in args else project_root(args)
    if not root or not os.path.exists(os.path.join(root, ".graph", "state.json")):
        if "--hook" not in args:
            print("Nessun .graph/state.json trovato in", root)
        return
    try:
        view = render(root)
    except Exception as e:  # stato scritto a metà o JSON non valido
        if "--hook" not in args:
            print("Errore:", e)
        return
    if "--open" in args:
        webbrowser.open("file://" + os.path.abspath(view))
    if "--hook" not in args:
        print(view)


if __name__ == "__main__":
    main()
