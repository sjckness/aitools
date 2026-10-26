#!/usr/bin/env python3
"""Genera .graph/view.html (Run Viewer: grafo, token, findings) dai file in .graph/.

Fonti (tutte opzionali tranne state.json):
  state.json            stato del run (v0.2 o v0.3, normalizzato con state_schema)
  watchdog_state.json   usage live per nodo scritta dal watchdog (sovrapposta allo stato)
  findings.jsonl        findings degli agenti
  watchdog.jsonl        eventi del watchdog
  tokens.json           consumo token per nodo/categoria (v0.4)
  token-report.json     insights e confronto con baseline (v0.4)

Il rendering avviene nel browser (viewer.html); questo script raccoglie e
pulisce i dati (`collect`) e li incorpora nella pagina (`render`).

Modalità:
  --hook      chiamato da un hook PostToolUse: agisce solo se è stato scritto
              un file osservato dentro .graph/, altrimenti esce subito.
  --cwd DIR   root del progetto (default: directory corrente).
  --open      apre la pagina nel browser.
  --refresh N secondi tra un aggiornamento e l'altro (default 2; 0 = mai).
Non fallisce mai in modo rumoroso: un errore qui non deve bloccare Claude.
"""
import datetime
import json
import os
import sys
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    from state_schema import normalize
except Exception:  # fallback: stato usato così com'è
    normalize = None
try:
    import watchdog
except Exception:  # nessun overlay della usage
    watchdog = None

WATCHED = ("state.json", "tokens.json", "token-report.json", "findings.jsonl", "watchdog.jsonl")
WHAT_MAX = 80        # lunghezza massima del testo di un finding nella pagina
WATCHDOG_MAX = 50    # eventi del watchdog incorporati


def arg(args, name, default=None):
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default


def from_hook():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return None
    path = ((data.get("tool_input") or {}).get("file_path") or "").replace("\\", "/")
    if "/.graph/" not in path or os.path.basename(path) not in WATCHED:
        return None
    return path.rsplit("/.graph/", 1)[0] or "/"


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def read_jsonl(path, limit=500):
    """Righe JSON valide che siano oggetti; il resto viene ignorato."""
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if isinstance(o, dict):
                    out.append(o)
    except OSError:
        pass
    return out[-limit:]


def _short(v, n):
    s = "" if v is None else str(v)
    return s if len(s) <= n else s[: n - 1] + "…"


def collect(root):
    """Dati puliti per il viewer. Solleva ValueError se state.json manca o non è valido."""
    g = os.path.join(root, ".graph")
    state = read_json(os.path.join(g, "state.json"))
    if not isinstance(state, dict):
        raise ValueError("state.json mancante o non valido")
    if normalize is not None:
        try:
            state = normalize(state)
        except Exception:
            pass
    nodes = [n for n in (state.get("nodes") or []) if isinstance(n, dict)]
    if watchdog is not None:
        wd = read_json(os.path.join(g, "watchdog_state.json"))
        if isinstance(wd, dict):
            try:
                um = watchdog.usage_map(wd, [n["id"] for n in nodes if "id" in n])
                nodes = [dict(n, usage=um[n["id"]]) if n.get("id") in um else n for n in nodes]
            except Exception:
                pass
    state = dict(state, nodes=nodes)

    findings = []
    for f in read_jsonl(os.path.join(g, "findings.jsonl")):
        f = dict(f)
        f["what"] = _short(f.get("what"), WHAT_MAX)
        findings.append(f)

    return {
        "state": state,
        "tokens": read_json(os.path.join(g, "tokens.json")),
        "report": read_json(os.path.join(g, "token-report.json")),
        "findings": findings,
        "watchdog": read_jsonl(os.path.join(g, "watchdog.jsonl"))[-WATCHDOG_MAX:],
    }


def embed(data):
    """JSON sicuro dentro <script>: niente '</', '<!--' o separatori di riga che rompono la pagina."""
    s = json.dumps(data, ensure_ascii=False)
    return (s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
             .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def render(root, refresh=2):
    data = collect(root)
    data["updated"] = datetime.datetime.now().strftime("%H:%M:%S")
    data["refresh"] = refresh
    with open(os.path.join(HERE, "viewer.html"), encoding="utf-8") as f:
        page = f.read()
    page = page.replace("__DATA__", embed(data))
    out = os.path.join(root, ".graph", "view.html")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(page)
    os.replace(tmp, out)  # scrittura atomica: il browser non legge mai un file a metà
    return out


def main():
    args = sys.argv[1:]
    hook = "--hook" in args
    root = from_hook() if hook else arg(args, "--cwd", os.getcwd())
    if not root or not os.path.exists(os.path.join(root, ".graph", "state.json")):
        if not hook:
            print("Nessun .graph/state.json trovato in", root)
        return
    try:
        view = render(root, int(arg(args, "--refresh", 2)))
    except Exception as e:
        if not hook:
            print("Errore:", e)
        return
    if "--open" in args:
        webbrowser.open("file://" + os.path.abspath(view))
    if not hook:
        print(view)


if __name__ == "__main__":
    main()
