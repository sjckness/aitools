#!/usr/bin/env python3
"""Watchdog graph-kit: hook PreToolUse / PostToolUse. Solo standard library.

Invocazione (JSON dell'hook su stdin, vedi hooks/hooks.json):
    python3 watchdog.py pre     # PreToolUse, tutti i tool
    python3 watchdog.py post    # PostToolUse (e PostToolUseFailure), tutti i tool

Attribuzione a un nodo `running` di .graph/state.json (in ordine):
  1. `agent_id` assente o vuoto -> thread principale, nessuna azione;
  2. `agent_type` (testo dopo l'ultimo ":") in {validator, critic, reviewer,
     planner} -> nessuna azione, niente output ne' scrittura;
  3. `agent_id` uguale a `agent_id` di un nodo running -> quel nodo;
  4. altrimenti contano solo i nodi running con `agent_id` vuoto: uno -> quello;
     piu' d'uno -> drift_write sull'unione dei "Puoi modificare", contatori nel
     secchio `_common`, mai livello 2; nessuno -> nessuna azione.

Reset dei contatori: `sig` della entry = "<attempts>:<agent_id>". Si azzera se
cambia `attempts` o se l'agent_id salvato e' non vuoto e diverso dall'attuale;
da "" a un valore si aggiorna solo la sig (stessa entry). Sig vecchia senza ":"
vale "<attempts>:". Nel secchio comune la sig e' l'elenco degli id ordinati.

Pattern rilevati:
  loop        stesso comando Bash >= 3 volte; stesso output d'errore (primi 300
              caratteri normalizzati) >= 3 volte; dopo Write/Edit lo sha1 del
              file torna a un valore gia' visto diverso dall'ultimo. Dopo una
              Write/Edit riuscita con sha1 nuovo (progresso) `cmds` ed `errs`
              tornano vuoti, cosi' il ciclo modifica -> test non scala.
  drift_write Write/Edit/MultiEdit/NotebookEdit fuori da "Puoi modificare":
              deny subito in pre, writes_outside_card += 1.
  drift_read  Read/Grep/Glob fuori da Leggi + Puoi modificare: solo conteggio
              (reads_outside_card += 1, evento con action "count").
  budget      ogni pre del nodo: tool_calls += 1; oltre budget.tool_calls
              livello 1; oltre il 125% livello 2.
I percorsi sotto `.graph/` sono sempre ignorati (mai drift, mai loop).

Livelli:
  1  messaggio all'agente (`additionalContext`, senza bloccare) con Obiettivo
     della card, pattern e invito ad annotare in findings; watchdog_warnings += 1.
  2  pattern dello stesso tipo ripetuto dopo il livello 1, o budget > 125%:
     ogni pre del nodo e' negata, tranne Write/Edit di .graph/out/<ID>.json e
     .graph/findings.jsonl, Read/Grep/Glob sotto .graph/ e Bash con
     `findings.py add`. watchdog_stops += 1 alla transizione.

File scritti (sotto <radice>/.graph/):
  watchdog_state.json  fonte di verita' (contatori, storici, livelli per nodo)
  watchdog.jsonl       eventi {ts,node,tool,kind,level,action,detail}
Gli hook pre/post NON scrivono mai state.json. Lo scrive solo la modalita'
`usage`, lanciata dall'orchestratore a nodo completato:
    python3 watchdog.py usage --cwd DIR     # default --cwd .
  legge DIR/.graph/state.json (manca/illeggibile: stderr, exit 2) e
  watchdog_state.json (manca/illeggibile: {}), sotto il lock di quest'ultimo;
  per ogni nodo in usage_map copia la usage in nodes[].usage (entry propria
  prevale su `_common`, che vale per gli id nella sua sig), poi
  metrics.tool_calls / watchdog_warnings / watchdog_stops = somme dei nodi;
  salva solo se cambia qualcosa; stampa su stdout {"<id>": usage}; exit 0.

Ogni errore interno -> exit 0 senza output. Solo i deny intenzionali bloccano.
"""
import fnmatch
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cards  # noqa: E402
import state_schema  # noqa: E402

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
READ_TOOLS = ("Read", "Grep", "Glob")
COMMON = "_common"
IGNORED_AGENT_TYPES = ("validator", "critic", "reviewer", "planner")


def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _new_entry(sig):
    return {"sig": sig, "usage": {k: 0 for k in state_schema.USAGE_KEYS},
            "cmds": {}, "errs": {}, "files": {}, "l1": [], "l2": False}


class Ctx(object):
    pass


def _target_path(ti):
    for k in ("file_path", "notebook_path", "path"):
        v = ti.get(k)
        if isinstance(v, str) and v:
            return v
    p = ti.get("pattern")
    if isinstance(p, str) and os.path.isabs(p):
        return p
    return None


def _under(path, base):
    return path == base or path.startswith(base.rstrip(os.sep) + os.sep)


def _paths(raw, cwd, root):
    """Ritorna (candidati, ignorato)."""
    ab = os.path.normpath(raw if os.path.isabs(raw) else os.path.join(cwd, raw))
    if _under(ab, cwd):
        rel = os.path.relpath(ab, cwd)
    elif _under(ab, root):
        rel = os.path.relpath(ab, root)
    else:
        rel = ab
    ignored = (rel.split(os.sep)[0] == ".graph"
               or _under(ab, os.path.join(root, ".graph"))
               or _under(ab, os.path.join(cwd, ".graph")))
    return [rel, ab], ignored, ab


def _match(entry, cands):
    e = entry.strip()
    while e.startswith("./"):
        e = e[2:]
    if not e:
        return False
    if any(c in e for c in "*?["):
        return any(fnmatch.fnmatch(c, e) for c in cands)
    if e.endswith("/"):
        return any(c.startswith(e) or c + "/" == e for c in cands)
    return any(c == e for c in cands)


def _sha1(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    except OSError:
        return None


def _load_card(root, nid):
    try:
        with open(os.path.join(root, ".graph", "cards", nid + ".md"),
                  encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


class Watchdog(object):
    def __init__(self, mode, inp, root, st, running):
        self.mode, self.inp, self.root = mode, inp, root
        self.cwd = os.path.abspath(inp.get("cwd") or os.getcwd())
        self.tool = inp.get("tool_name") or ""
        ti = inp.get("tool_input")
        self.ti = ti if isinstance(ti, dict) else {}
        self.st, self.running = st, running
        self.warns, self.deny = [], None
        self.touched = False
        self.events = []

    # ---- attribuzione
    def attribute(self):
        aid = self.inp.get("agent_id")
        if not aid or not isinstance(aid, str):
            return None
        at = self.inp.get("agent_type")
        if isinstance(at, str) and \
                at.rsplit(":", 1)[-1] in IGNORED_AGENT_TYPES:
            return None
        for n in self.running:
            if n.get("agent_id") and n.get("agent_id") == aid:
                return [n]
        free = [n for n in self.running if not n.get("agent_id")]
        return free or None

    # ---- eventi / livelli
    def event(self, node, kind, level, action, detail):
        self.events.append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "node": node,
            "tool": self.tool, "kind": kind, "level": level,
            "action": action, "detail": _norm(detail)[:200]})

    def objective(self):
        out = []
        for n in self.nodes:
            t = _load_card(self.root, n["id"])
            if t:
                out.append(_norm(cards.parse_card(t).get("Obiettivo", "")))
        return " | ".join(o for o in out if o)[:300]

    def escalate(self, kind, detail, force_l2=False):
        e = self.entry
        if (kind in e["l1"] or force_l2) and self.can_l2:
            if not e["l2"]:
                e["l2"] = True
                e["usage"]["watchdog_stops"] += 1
                if kind not in e["l1"]:
                    e["l1"].append(kind)
                self.event(self.label, kind, 2, "block", detail)
                self.deny = (
                    "Watchdog livello 2 sul nodo %s: %s. Ogni tool call del "
                    "nodo e' negata tranne la scrittura di .graph/out/%s.json "
                    "e .graph/findings.jsonl. Chiudi con status \"blocked\" e "
                    "descrivi il problema in `blockers`."
                    % (self.label, detail, self.label))
            return True
        if kind not in e["l1"]:
            e["l1"].append(kind)
            e["usage"]["watchdog_warnings"] += 1
            self.event(self.label, kind, 1, "warn", detail)
            self.warns.append(
                "Watchdog livello 1 (nodo %s): rilevato %s. Obiettivo della "
                "card: %s. Indicazione: se non riguarda l'obiettivo, annotalo in findings e "
                "prosegui."
                % (self.label, detail, self.objective()))
            return True
        return False

    # ---- allowlist livello 2
    def l2_allowed(self):
        t = self.tool
        nid = self.label
        if t == "Bash":
            return "findings.py add" in str(self.ti.get("command", ""))
        raw = _target_path(self.ti)
        if raw is None:
            return False
        cands, ignored, ab = _paths(raw, self.cwd, self.root)
        if t in ("Write", "Edit"):
            g = os.path.join(self.root, ".graph")
            return ab in (os.path.join(g, "out", nid + ".json"),
                          os.path.join(g, "findings.jsonl")) or \
                cands[0] in (".graph/out/%s.json" % nid, ".graph/findings.jsonl")
        if t in READ_TOOLS:
            return ignored
        return False

    # ---- elaborazione
    def run(self):
        self.nodes = self.attribute()
        if not self.nodes:
            return
        multi = len(self.nodes) > 1
        self.can_l2 = not multi
        self.label = COMMON if multi else self.nodes[0]["id"]
        self.ids = [n["id"] for n in self.nodes]
        if multi:
            sig = ",".join(sorted(self.ids))
        else:
            sig = "%s:%s" % (self.nodes[0].get("attempts", 0),
                             self.nodes[0].get("agent_id") or "")
        wd = self.wd
        e = wd.get(self.label)
        if not isinstance(e, dict):
            e = None
        elif e.get("sig") != sig:
            if multi:
                e = None
            else:
                old = str(e.get("sig", ""))
                if ":" not in old:
                    old += ":"
                oatt, oaid = old.split(":", 1)
                att, aid = sig.split(":", 1)
                if oatt != att or (oaid and oaid != aid):
                    e = None
                else:
                    e["sig"] = sig
        if e is None:
            e = _new_entry(sig)
        wd[self.label] = e
        for k in state_schema.USAGE_KEYS:
            e["usage"].setdefault(k, 0)
        self.entry = e
        before = json.dumps(e, sort_keys=True)
        if self.mode == "pre":
            self.pre()
        else:
            self.post()
        self.changed = json.dumps(e, sort_keys=True) != before

    def budget_limit(self):
        vals = []
        for n in self.nodes:
            b = n.get("budget")
            v = b.get("tool_calls") if isinstance(b, dict) else None
            vals.append(v if isinstance(v, int) and v > 0 else 40)
        return max(vals)

    def pre(self):
        e, t = self.entry, self.tool
        e["usage"]["tool_calls"] += 1
        if e["l2"]:
            if not self.l2_allowed():
                self.deny = (
                    "Watchdog livello 2 sul nodo %s: tool call negata. "
                    "Chiudi con status \"blocked\" scrivendo "
                    ".graph/out/%s.json e descrivi il problema in `blockers`."
                    % (self.label, self.label))
            return
        calls, limit = e["usage"]["tool_calls"], self.budget_limit()
        if calls > limit * 1.25:
            self.escalate("budget", "tool_calls %d oltre il 125%% del budget %d"
                          % (calls, limit), force_l2=True)
        elif calls > limit:
            self.escalate("budget", "tool_calls %d oltre il budget %d"
                          % (calls, limit))
        if self.deny:
            return
        if t == "Bash":
            cmd = _norm(str(self.ti.get("command", "")))
            if cmd:
                e["cmds"][cmd] = e["cmds"].get(cmd, 0) + 1
                if e["cmds"][cmd] >= 3:
                    if self.escalate("loop", "comando ripetuto %d volte: %s"
                                     % (e["cmds"][cmd], cmd)):
                        e["cmds"] = {}
                    if self.deny:
                        return
        if t in WRITE_TOOLS or t in READ_TOOLS:
            self.drift()

    def card_lists(self):
        write, read = [], []
        found = False
        for n in self.nodes:
            txt = _load_card(self.root, n["id"])
            if txt is None:
                continue
            found = True
            w = cards.section_paths(txt, "Puoi modificare")
            write += w
            read += w + cards.section_paths(txt, "Leggi")
        return found, write, read

    def drift(self):
        raw = _target_path(self.ti)
        if raw is None:
            return
        cands, ignored, ab = _paths(raw, self.cwd, self.root)
        if ignored:
            return
        e, t = self.entry, self.tool
        found, write, read = self.card_lists()
        if t in WRITE_TOOLS:
            if found and not any(_match(x, cands) for x in write):
                e["usage"]["writes_outside_card"] += 1
                self.event(self.label, "drift_write", 1, "block", cands[0])
                self.deny = ("Watchdog (nodo %s): scrittura su %s fuori da "
                             "\"Puoi modificare\" della card. Se serve, "
                             "annotalo in findings." % (self.label, cands[0]))
                return
            h = _sha1(ab)
            if h is not None and ab not in e["files"]:
                e["files"][ab] = {"last": h, "seen": [h]}
        elif found and not any(_match(x, cands) for x in read):
            if t != "Read" and not os.path.splitext(raw)[1]:
                # Grep/Glob su una directory: ok se contiene voci della card
                d = cands[0].rstrip("/") + "/"
                if any(_match(x, cands) or x.lstrip("./").startswith(d)
                       for x in read):
                    return
            e["usage"]["reads_outside_card"] += 1
            self.event(self.label, "drift_read", 1, "count", cands[0])

    def post(self):
        e, t = self.entry, self.tool
        if e["l2"]:
            return
        text = None
        if self.inp.get("error"):
            text = str(self.inp.get("error"))
        elif t == "Bash":
            tr = self.inp.get("tool_response")
            if isinstance(tr, dict) and tr.get("stderr"):
                text = str(tr.get("stderr"))
        if text and _norm(text):
            k = _norm(text)[:300]
            e["errs"][k] = e["errs"].get(k, 0) + 1
            if e["errs"][k] >= 3:
                if self.escalate("loop", "stesso errore ripetuto %d volte: %s"
                                 % (e["errs"][k], k[:80])):
                    e["errs"] = {}
        if t in WRITE_TOOLS and not self.inp.get("error"):
            raw = _target_path(self.ti)
            if raw is None:
                return
            cands, ignored, ab = _paths(raw, self.cwd, self.root)
            if ignored:
                return
            h = _sha1(ab)
            if h is None:
                return
            f = e["files"].setdefault(ab, {"last": None, "seen": []})
            if f["last"] is not None and h != f["last"] and h in f["seen"]:
                self.escalate("loop", "file %s riportato a uno stato gia' visto"
                              % cands[0])
            if h not in f["seen"]:
                f["seen"].append(h)
                e["cmds"], e["errs"] = {}, {}
            f["last"] = h


def _lock(path):
    f = open(path, "a+")
    if fcntl is not None:
        try:
            fcntl.flock(f, fcntl.LOCK_EX)
        except OSError:
            pass
    return f


def usage_map(wd, ids):
    """{id: usage}: entry propria, altrimenti `_common` se l'id e' nella sua sig."""
    out = {}
    common = wd.get(COMMON) if isinstance(wd, dict) else None
    cids = []
    if isinstance(common, dict) and isinstance(common.get("sig"), str):
        cids = common["sig"].split(",")
    for i in ids:
        own = wd.get(i) if isinstance(wd, dict) else None
        if isinstance(own, dict) and isinstance(own.get("usage"), dict):
            out[i] = dict(own["usage"])
        elif i in cids and isinstance(common.get("usage"), dict):
            out[i] = dict(common["usage"])
    return out


def usage_cmd(argv):
    cwd = "."
    if "--cwd" in argv:
        k = argv.index("--cwd")
        if k + 1 < len(argv):
            cwd = argv[k + 1]
    root = os.path.abspath(cwd)
    try:
        st = state_schema.load_state(root)
    except Exception as ex:
        sys.stderr.write("watchdog usage: stato illeggibile: %s\n" % ex)
        return 2
    if not isinstance(st, dict):
        sys.stderr.write("watchdog usage: .graph/state.json mancante o "
                         "illeggibile in %s\n" % root)
        return 2
    gdir = os.path.join(root, ".graph")
    lf = _lock(os.path.join(gdir, "watchdog_state.json"))
    try:
        lf.seek(0)
        try:
            wd = json.loads(lf.read() or "{}")
        except ValueError:
            wd = {}
        if not isinstance(wd, dict):
            wd = {}
        nodes = [n for n in st.get("nodes", []) or []
                 if isinstance(n, dict) and isinstance(n.get("id"), str)]
        um = usage_map(wd, [n["id"] for n in nodes])
        changed = False
        for n in nodes:
            if n["id"] in um and n.get("usage") != um[n["id"]]:
                n["usage"] = dict(um[n["id"]])
                changed = True
        m = st.get("metrics")
        if not isinstance(m, dict):
            m = {}
        for k in ("tool_calls", "watchdog_warnings", "watchdog_stops"):
            tot = 0
            for n in nodes:
                u = n.get("usage")
                v = u.get(k, 0) if isinstance(u, dict) else 0
                tot += v if isinstance(v, int) else 0
            if m.get(k) != tot:
                m[k] = tot
                changed = True
        if changed:
            st["metrics"] = m
            state_schema.save_state(root, st)
    finally:
        lf.close()
    sys.stdout.write(json.dumps(um, ensure_ascii=False) + "\n")
    return 0


def _emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def main(argv):
    mode = argv[1] if len(argv) > 1 else ""
    if mode not in ("pre", "post"):
        return
    try:
        inp = json.loads(sys.stdin.read())
    except ValueError:
        return
    if not isinstance(inp, dict):
        return
    cwd = inp.get("cwd") if isinstance(inp.get("cwd"), str) else os.getcwd()
    root = state_schema.find_graph_root(cwd)
    if not root:
        return
    st = state_schema.load_state(root)
    if not isinstance(st, dict):
        return
    running = [n for n in st.get("nodes", []) or []
               if isinstance(n, dict) and n.get("status") == "running"
               and isinstance(n.get("id"), str)]
    if not running:
        return
    w = Watchdog(mode, inp, root, st, running)
    if not w.attribute():
        return
    gdir = os.path.join(root, ".graph")
    lf = _lock(os.path.join(gdir, "watchdog_state.json"))
    try:
        lf.seek(0)
        try:
            wd = json.loads(lf.read() or "{}")
        except ValueError:
            wd = {}
        if not isinstance(wd, dict):
            wd = {}
        w.wd = wd
        w.run()
        lf.seek(0)
        lf.truncate()
        lf.write(json.dumps(wd, indent=1, ensure_ascii=False))
        lf.flush()
        if w.events:
            with open(os.path.join(gdir, "watchdog.jsonl"), "a",
                      encoding="utf-8") as ev:
                for x in w.events:
                    ev.write(json.dumps(x, ensure_ascii=False) + "\n")
    finally:
        lf.close()
    if w.deny and mode == "pre":
        _emit({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": w.deny}})
    elif w.warns or w.deny:
        name = inp.get("hook_event_name") or (
            "PreToolUse" if mode == "pre" else "PostToolUse")
        _emit({"hookSpecificOutput": {
            "hookEventName": name,
            "additionalContext": " ".join(w.warns or [w.deny])}})


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "usage":
        sys.exit(usage_cmd(sys.argv))
    try:
        main(sys.argv)
    except BaseException:
        pass
    sys.exit(0)
