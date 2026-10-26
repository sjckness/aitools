"""Schema di stato sjck-graph v0.3: validazione, default, I/O atomico.

Solo standard library, Python 3.9+.
"""
import copy
import json
import os
import subprocess
import tempfile

ENUMS = {
    "node_status": ("pending", "running", "done", "validated", "blocked",
                    "failed", "done-unverified"),
    "agent": ("self", "scout", "implementer"),
    "model": ("haiku", "sonnet", "opus", "fable", "inherit"),
    "effort": ("low", "medium", "high", "xhigh", "max"),
    "plan_verdict": ("ok", "reject"),
    "critic_at": ("plan", "findings", "failure"),
    "critic_verdict": ("approve", "object"),
    "critic_round": (1, 2),
}

USAGE_KEYS = ("tool_calls", "reads_outside_card", "writes_outside_card",
              "watchdog_warnings", "watchdog_stops")

METRIC_KEYS = ("subagents", "validator_fails", "tool_calls",
               "watchdog_warnings", "watchdog_stops", "findings",
               "findings_accepted", "duration_s")

NODE_DEFAULTS = {
    "model": "inherit",
    "effort": "medium",
    "budget": {"tool_calls": 40, "context_tokens": 2000},
    "usage": {k: 0 for k in USAGE_KEYS},
    "assumptions": [],
}


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _enum(errs, path, val, name):
    allowed = ENUMS[name]
    if isinstance(val, bool) or val not in allowed:
        errs.append("%s: atteso uno tra %s, trovato %r"
                    % (path, "|".join(str(a) for a in allowed), val))


def _num_min(errs, path, val, minimum, allow_float=False):
    ok = _is_num(val) if allow_float else _is_int(val)
    if not ok:
        errs.append("%s: atteso %s, trovato %r"
                    % (path, "numero" if allow_float else "intero", val))
    elif val < minimum:
        errs.append("%s: atteso valore >= %s, trovato %r" % (path, minimum, val))


def _type(errs, path, val, typ, label):
    if not isinstance(val, typ) or isinstance(val, bool):
        errs.append("%s: atteso %s, trovato %r" % (path, label, val))
        return False
    return True


def _str_list(errs, path, val):
    if not _type(errs, path, val, list, "lista"):
        return
    for i, x in enumerate(val):
        if not isinstance(x, str):
            errs.append("%s[%d]: atteso stringa, trovato %r" % (path, i, x))


def _counters(errs, path, val, keys, minimum, float_keys=()):
    if not _type(errs, path, val, dict, "oggetto"):
        return
    for k in keys:
        if k in val:
            _num_min(errs, "%s.%s" % (path, k), val[k], minimum, k in float_keys)


def _validate_node(errs, i, n):
    p = "nodes[%d]" % i
    if not isinstance(n, dict):
        errs.append("%s: atteso oggetto, trovato %r" % (p, n))
        return
    if "id" in n:
        _type(errs, p + ".id", n["id"], str, "stringa")
    else:
        errs.append(p + ".id: campo mancante")
    if "title" in n:
        _type(errs, p + ".title", n["title"], str, "stringa")
    if "agent" in n:
        _enum(errs, p + ".agent", n["agent"], "agent")
    if "status" in n:
        _enum(errs, p + ".status", n["status"], "node_status")
    if "deps" in n:
        _str_list(errs, p + ".deps", n["deps"])
    if "files" in n:
        _str_list(errs, p + ".files", n["files"])
    if "attempts" in n:
        _num_min(errs, p + ".attempts", n["attempts"], 0)
    if "agent_id" in n:
        _type(errs, p + ".agent_id", n["agent_id"], str, "stringa")
    if "model" in n:
        _enum(errs, p + ".model", n["model"], "model")
    if "effort" in n:
        _enum(errs, p + ".effort", n["effort"], "effort")
    if "budget" in n:
        _counters(errs, p + ".budget", n["budget"],
                  ("tool_calls", "context_tokens"), 1)
    if "usage" in n:
        _counters(errs, p + ".usage", n["usage"], USAGE_KEYS, 0)
    if "assumptions" in n:
        _str_list(errs, p + ".assumptions", n["assumptions"])


def _validate_plan_score(errs, ps):
    p = "plan_score"
    if not _type(errs, p, ps, dict, "oggetto"):
        return
    for k in ("width", "critical_path", "file_overlap", "avg_card_tokens"):
        if k in ps:
            _num_min(errs, "%s.%s" % (p, k), ps[k], 0, True)
    if "verdict" in ps:
        _enum(errs, p + ".verdict", ps["verdict"], "plan_verdict")
    if "reasons" in ps:
        _str_list(errs, p + ".reasons", ps["reasons"])


def _validate_critic(errs, critic):
    if not _type(errs, "critic", critic, list, "lista"):
        return
    for i, c in enumerate(critic):
        p = "critic[%d]" % i
        if not _type(errs, p, c, dict, "oggetto"):
            continue
        if "at" in c:
            _enum(errs, p + ".at", c["at"], "critic_at")
        if "round" in c:
            _enum(errs, p + ".round", c["round"], "critic_round")
        if "verdict" in c:
            _enum(errs, p + ".verdict", c["verdict"], "critic_verdict")
        if "points" in c:
            _str_list(errs, p + ".points", c["points"])
        if "resolution" in c:
            _type(errs, p + ".resolution", c["resolution"], str, "stringa")


def _validate_checkpoints(errs, cps):
    if not _type(errs, "checkpoints", cps, list, "lista"):
        return
    for i, c in enumerate(cps):
        p = "checkpoints[%d]" % i
        if not _type(errs, p, c, dict, "oggetto"):
            continue
        if "after_level" in c:
            _num_min(errs, p + ".after_level", c["after_level"], 0)
        for k in ("findings_proposed", "accepted", "deferred", "rejected"):
            if k in c:
                _str_list(errs, "%s.%s" % (p, k), c[k])


def validate(state):
    """Ritorna la lista di errori ("<percorso>: <problema>"); [] se valido."""
    errs = []
    if not isinstance(state, dict):
        return ["$: atteso oggetto, trovato %r" % (state,)]
    for k in ("goal", "mode", "mode_reason", "status", "started"):
        if k in state:
            _type(errs, k, state[k], str, "stringa")
    if "log" in state:
        _str_list(errs, "log", state["log"])
    nodes = state.get("nodes", [])
    if not isinstance(nodes, list):
        errs.append("nodes: atteso lista, trovato %r" % (nodes,))
        nodes = []
    ids = set()
    for i, n in enumerate(nodes):
        _validate_node(errs, i, n)
        nid = n.get("id") if isinstance(n, dict) else None
        if isinstance(nid, str):
            if nid in ids:
                errs.append("nodes[%d].id: id duplicato %r" % (i, nid))
            ids.add(nid)
    for i, n in enumerate(nodes):
        deps = n.get("deps") if isinstance(n, dict) else None
        if isinstance(deps, list):
            for j, d in enumerate(deps):
                if isinstance(d, str) and d not in ids:
                    errs.append("nodes[%d].deps[%d]: dipendenza inesistente %r"
                                % (i, j, d))
    if "plan_score" in state:
        _validate_plan_score(errs, state["plan_score"])
    if "critic" in state:
        _validate_critic(errs, state["critic"])
    if "checkpoints" in state:
        _validate_checkpoints(errs, state["checkpoints"])
    if "metrics" in state:
        _counters(errs, "metrics", state["metrics"], METRIC_KEYS, 0,
                  float_keys=("duration_s",))
    return errs


def normalize(state):
    """Copia profonda con i default v0.3 per i campi mancanti."""
    st = copy.deepcopy(state)
    for n in st.get("nodes", []) or []:
        if not isinstance(n, dict):
            continue
        for k, v in NODE_DEFAULTS.items():
            if k not in n:
                n[k] = copy.deepcopy(v)
            elif isinstance(v, dict) and isinstance(n[k], dict):
                for kk, vv in v.items():
                    n[k].setdefault(kk, vv)
    st.setdefault("critic", [])
    st.setdefault("checkpoints", [])
    m = st.get("metrics")
    if not isinstance(m, dict):
        m = {}
        st["metrics"] = m
    for k in METRIC_KEYS:
        m.setdefault(k, 0)
    return st


def _state_path(root):
    return os.path.join(root, ".sjck", "state.json")


def load_state(root):
    try:
        with open(_state_path(root), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_state(root, state):
    path = _state_path(root)
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".state.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def find_graph_root(start):
    try:
        env = os.environ.get("SJCK_ROOT")
        if env:
            return env
        cur = os.path.abspath(start)
        if os.path.isfile(cur):
            cur = os.path.dirname(cur)
        d = cur
        while True:
            if os.path.isfile(_state_path(d)):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                cwd=cur, capture_output=True, text=True, timeout=1)
            if r.returncode == 0 and r.stdout.strip():
                root = os.path.dirname(r.stdout.strip())
                if os.path.isfile(_state_path(root)):
                    return root
        except Exception:
            pass
    except Exception:
        pass
    return None
