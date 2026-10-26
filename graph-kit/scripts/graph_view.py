#!/usr/bin/env python3
"""Genera .graph/view.html (Run Viewer: grafo, token, findings) dai file in .graph/.

Fonti (tutte opzionali tranne state.json):
  state.json          stato del run (v0.2 o v0.3)
  tokens.json         consumo token per nodo/categoria (v0.4)
  token-report.json   insights e confronto con baseline (v0.4)
  findings.jsonl      findings degli agenti (v0.3)
  watchdog.jsonl      eventi del watchdog (v0.3)

Modalità:
  --hook      chiamato da un hook PostToolUse: agisce solo se è stato scritto
              un file dentro .graph/, altrimenti esce subito.
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
WATCHED = ("state.json", "tokens.json", "token-report.json", "findings.jsonl", "watchdog.jsonl")


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
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out[-limit:]


def render(root, refresh=2):
    g = os.path.join(root, ".graph")
    state = read_json(os.path.join(g, "state.json"))
    if state is None:
        raise ValueError("state.json mancante o non valido")
    data = {
        "state": state,
        "tokens": read_json(os.path.join(g, "tokens.json")),
        "report": read_json(os.path.join(g, "token-report.json")),
        "findings": read_jsonl(os.path.join(g, "findings.jsonl")),
        "watchdog": read_jsonl(os.path.join(g, "watchdog.jsonl")),
        "updated": datetime.datetime.now().strftime("%H:%M:%S"),
        "refresh": refresh,
    }
    with open(os.path.join(HERE, "viewer.html"), encoding="utf-8") as f:
        page = f.read()
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace("__DATA__", blob)
    out = os.path.join(g, "view.html")
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
