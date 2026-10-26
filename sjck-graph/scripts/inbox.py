#!/usr/bin/env python3
"""Inbox of a running graph: change requests and console decisions.

Only the orchestrator runs the commands that change state (`apply`,
`decisions --apply`): it stays the single writer of `.sjck/state.json`.
The `sjck-change` session and the console only WRITE files into the inbox:

  .sjck/changes/CR-NNN.json     change requests (status proposed|accepted|...)
  .sjck/decisions/D-*.json      decisions taken in the console
                                (findings accept/defer/reject, CR apply/reject)

CLI (root = --cwd, else find_graph_root(cwd), else cwd):
  inbox.py [--cwd DIR] pending                 # JSON: CRs to handle + new decisions
  inbox.py [--cwd DIR] validate CR.json        # exit 1 with errors
  inbox.py [--cwd DIR] next-id                 # next free CR id
  inbox.py [--cwd DIR] apply CR-ID [--dry-run] # exit 0 applied, 1 rejected, 3 must wait
  inbox.py [--cwd DIR] decisions [--apply]     # list new decisions / apply them
Python 3.9+, standard library only.
"""
import argparse
import copy
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import state_schema  # noqa: E402
import plan_score  # noqa: E402
import findings as findings_mod  # noqa: E402

CR_STATUSES = ("proposed", "accepted", "applied", "rejected", "superseded")
PRIORITIES = ("normal", "next", "now")
OPS = ("add_node", "edit_card", "set", "remove_node", "add_dep", "rerun",
       "accept_finding", "kit_change")
SETTABLE = ("title", "model", "effort", "budget", "files", "deps")
DECISION_ACTIONS = {"finding": ("accept", "defer", "reject"), "cr": ("apply", "reject")}
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
CR_RE = re.compile(r"^CR-\d{3,}$")
BUSY = ("running",)
DONE = ("validated", "done", "done-unverified", "failed", "blocked")


class Wait(Exception):
    """The CR touches a node that is running: retry after it finishes."""


def _g(root, *p):
    return os.path.join(root, ".sjck", *p)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------- validation
def validate(cr):
    errs = []
    if not isinstance(cr, dict):
        return ["CR is not an object"]
    if not CR_RE.match(str(cr.get("id", ""))):
        errs.append("id must look like CR-001")
    if cr.get("status", "proposed") not in CR_STATUSES:
        errs.append("invalid status")
    if cr.get("priority", "normal") not in PRIORITIES:
        errs.append("priority must be one of %s" % "|".join(PRIORITIES))
    if not str(cr.get("summary", "")).strip():
        errs.append("summary is required")
    ops = cr.get("ops")
    if not isinstance(ops, list) or not ops:
        return errs + ["ops must be a non-empty list"]
    for i, op in enumerate(ops):
        p = "ops[%d]" % i
        if not isinstance(op, dict) or op.get("op") not in OPS:
            errs.append("%s: unknown op" % p)
            continue
        k = op["op"]
        if k == "add_node":
            n = op.get("node")
            if not isinstance(n, dict) or not ID_RE.match(str(n.get("id", ""))):
                errs.append("%s: node.id missing or invalid" % p)
            if not isinstance(op.get("card"), str) or not op["card"].strip():
                errs.append("%s: card text required" % p)
        elif k in ("edit_card", "set", "remove_node", "add_dep", "rerun"):
            if not ID_RE.match(str(op.get("id", ""))):
                errs.append("%s: id missing or invalid" % p)
            if k == "edit_card" and not isinstance(op.get("card"), str):
                errs.append("%s: card (full new text) required" % p)
            if k == "set":
                f = op.get("fields")
                if not isinstance(f, dict) or not f:
                    errs.append("%s: fields required" % p)
                elif set(f) - set(SETTABLE):
                    errs.append("%s: only %s can be set" % (p, ", ".join(SETTABLE)))
            if k == "add_dep" and not ID_RE.match(str(op.get("dep", ""))):
                errs.append("%s: dep missing or invalid" % p)
        elif k == "accept_finding":
            if not re.match(r"^F\d+$", str(op.get("finding", ""))):
                errs.append("%s: finding id required" % p)
            if not ID_RE.match(str(op.get("as_node", ""))):
                errs.append("%s: as_node required" % p)
        elif k == "kit_change":
            t = str(op.get("target", ""))
            if not t or ".." in t or t.startswith("/"):
                errs.append("%s: target must be a relative path inside the kit" % p)
            if not isinstance(op.get("patch"), str):
                errs.append("%s: patch text required" % p)
    return errs


# ---------------------------------------------------------------- listing
def load_crs(root):
    out = []
    for p in sorted(glob.glob(_g(root, "changes", "CR-*.json"))):
        cr = _read_json(p)
        if isinstance(cr, dict):
            cr["_path"] = p
            out.append(cr)
    return out


def next_id(root):
    nums = [int(m.group(1)) for cr in load_crs(root)
            for m in [re.match(r"^CR-(\d+)$", str(cr.get("id", "")))] if m]
    for p in glob.glob(_g(root, "changes", "CR-*.json")):
        m = re.match(r"^CR-(\d+)\.json$", os.path.basename(p))
        if m:
            nums.append(int(m.group(1)))
    return "CR-%03d" % (max(nums) + 1 if nums else 1)


def load_decisions(root, status="new"):
    out = []
    for p in sorted(glob.glob(_g(root, "decisions", "D-*.json"))):
        d = _read_json(p)
        if isinstance(d, dict) and (status is None or d.get("status", "new") == status):
            d["_path"] = p
            out.append(d)
    return out


def pending(root):
    rank = {"now": 0, "next": 1, "normal": 2}
    crs = [c for c in load_crs(root) if c.get("status", "proposed") in ("proposed", "accepted")]
    crs.sort(key=lambda c: (rank.get(c.get("priority", "normal"), 2), c.get("id", "")))
    return {
        "crs": [{k: c.get(k) for k in ("id", "priority", "status", "summary")} for c in crs],
        "decisions": [{k: d.get(k) for k in ("id", "target", "action")} for d in load_decisions(root)],
        "blocking": any(c.get("priority") == "now" for c in crs),
    }


# ---------------------------------------------------------------- apply
def _dependents(nodes, start):
    out, frontier = set(), {start}
    while frontier:
        nxt = set()
        for n in nodes:
            if set(n.get("deps") or []) & frontier and n["id"] not in out:
                nxt.add(n["id"])
        out |= nxt
        frontier = nxt
    return out


def plan(root, cr):
    """Apply cr in memory. Returns (new_state, card_writes{id:text}, kit_files, rerun_ids, notes)."""
    raw = state_schema.load_state(root)
    if not isinstance(raw, dict):
        raise ValueError("no readable .sjck/state.json")
    st = state_schema.normalize(raw)
    nodes = st["nodes"]
    by_id = {n["id"]: n for n in nodes}
    cards, kit, rerun, notes = {}, [], set(), []

    def node(i):
        if i not in by_id:
            raise ValueError("unknown node %s" % i)
        return by_id[i]

    def editable(i):
        n = node(i)
        if n.get("status") in BUSY:
            raise Wait("%s is running" % i)
        return n

    for op in cr["ops"]:
        k = op["op"]
        if k == "add_node":
            n = dict(op["node"])
            if n["id"] in by_id:
                raise ValueError("node %s already exists" % n["id"])
            n.setdefault("title", n["id"])
            n.setdefault("agent", "implementer")
            n.setdefault("deps", [])
            n.setdefault("files", [])
            n.update(status="pending", attempts=0, agent_id="")
            for d in n["deps"]:
                node(d)
            n = state_schema.normalize({"nodes": [n]})["nodes"][0]
            nodes.append(n)
            by_id[n["id"]] = n
            cards[n["id"]] = op["card"]
            notes.append("+%s" % n["id"])
        elif k == "edit_card":
            n = editable(op["id"])
            if n.get("status") in DONE:
                rerun.add(n["id"])
            cards[n["id"]] = op["card"]
            notes.append("card %s" % n["id"])
        elif k == "set":
            n = editable(op["id"])
            for d in op["fields"].get("deps", []):
                node(d)
            n.update(copy.deepcopy(op["fields"]))
            notes.append("set %s" % n["id"])
        elif k == "remove_node":
            n = editable(op["id"])
            if n.get("status") != "pending":
                raise ValueError("only pending nodes can be removed (%s is %s)" % (n["id"], n.get("status")))
            users = [m["id"] for m in nodes if n["id"] in (m.get("deps") or [])]
            if users:
                raise ValueError("%s is a dependency of %s" % (n["id"], ", ".join(users)))
            nodes.remove(n)
            del by_id[n["id"]]
            notes.append("-%s" % n["id"])
        elif k == "add_dep":
            n = editable(op["id"])
            node(op["dep"])
            if op["dep"] not in n["deps"]:
                n["deps"].append(op["dep"])
            if n.get("status") in DONE:
                rerun.add(n["id"])
            notes.append("%s→%s" % (op["dep"], n["id"]))
        elif k == "rerun":
            editable(op["id"])
            rerun.add(op["id"])
        elif k == "accept_finding":
            if op["as_node"] not in by_id:
                raise ValueError("accept_finding: add node %s in the same CR first" % op["as_node"])
            notes.append("%s→%s" % (op["finding"], op["as_node"]))
        elif k == "kit_change":
            kit.append(op)
            notes.append("kit:%s" % op["target"])

    # cascade: a re-run node invalidates everything downstream that already ran
    for i in list(rerun):
        rerun |= _dependents(nodes, i)
    for i in rerun:
        n = by_id.get(i)
        if not n:
            continue
        if n.get("status") in BUSY:
            raise Wait("%s is running and would need a re-run" % i)
        if n.get("status") != "pending":
            n.update(status="pending", attempts=0, agent_id="")
    if rerun:
        notes.append("rerun " + ",".join(sorted(rerun)))
    return st, cards, kit, sorted(rerun), notes


def _score(root, st, cards):
    tmp = tempfile.mkdtemp(prefix="sjck-cards-")
    try:
        src = _g(root, "cards")
        if os.path.isdir(src):
            for f in os.listdir(src):
                shutil.copy(os.path.join(src, f), tmp)
        for i, text in cards.items():
            with open(os.path.join(tmp, i + ".md"), "w", encoding="utf-8") as f:
                f.write(text)
        return plan_score.score(st, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _set_cr(cr, **kw):
    path = cr.pop("_path")
    cr.update(kw)
    _write_json(path, cr)
    cr["_path"] = path


def apply(root, cr_id, dry_run=False):
    """0 applied (or would apply), 1 rejected, 3 must wait. Prints a one-line summary."""
    cr = next((c for c in load_crs(root) if c.get("id") == cr_id), None)
    if cr is None:
        raise ValueError("unknown CR %s" % cr_id)
    if cr.get("status", "proposed") not in ("proposed", "accepted"):
        raise ValueError("%s is %s" % (cr_id, cr.get("status")))
    errs = validate(cr)
    if errs:
        if not dry_run:
            _set_cr(cr, status="rejected", resolution="invalid: " + "; ".join(errs))
        print("%s rejected: %s" % (cr_id, "; ".join(errs)))
        return 1
    try:
        st, cards, kit, rerun, notes = plan(root, cr)
    except Wait as e:
        print("%s waits: %s" % (cr_id, e))
        return 3
    except ValueError as e:
        if not dry_run:
            _set_cr(cr, status="rejected", resolution=str(e))
        print("%s rejected: %s" % (cr_id, e))
        return 1
    ps = _score(root, st, cards)
    if ps.get("verdict") == "reject":
        msg = "plan score reject: " + "; ".join(ps.get("reasons", []))
        if not dry_run:
            _set_cr(cr, status="rejected", resolution=msg)
        print("%s rejected: %s" % (cr_id, msg))
        return 1
    summary = "%s %s: %s" % (cr_id, "would apply" if dry_run else "applied", ", ".join(notes) or "no-op")
    if dry_run:
        print(summary)
        return 0
    # side effects, in an order that keeps the state consistent if interrupted
    out = _g(root, "out")
    for i in rerun:
        prev = os.path.join(out, i + ".json")
        if os.path.exists(prev):
            os.replace(prev, os.path.join(out, i + ".prev.json"))
    for i, text in cards.items():
        p = _g(root, "cards", i + ".md")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
    for k, op in enumerate(kit, 1):
        p = _g(root, "kit-proposals", "%s-%d.md" % (cr_id, k))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("# %s — %s\n\ntarget: `%s`\n\n```\n%s\n```\n" % (cr_id, cr.get("summary", ""), op["target"], op["patch"]))
    for op in cr["ops"]:
        if op["op"] == "accept_finding":
            _accept_finding(root, op["finding"], "node:" + op["as_node"])
    st["plan_score"] = ps
    st.setdefault("log", []).append("%s %s" % (time.strftime("%H:%M"), summary))
    state_schema.save_state(root, st)
    _set_cr(cr, status="applied", resolution=summary, applied=_now(), impact={"rerun": rerun})
    print(summary)
    return 0


# ---------------------------------------------------------------- decisions
def _accept_finding(root, fid, placement=None):
    recs = {r["id"]: r for r in findings_mod.load(root)}
    if fid not in recs:
        raise ValueError("unknown finding %s" % fid)
    st = recs[fid].get("status")
    if st == "accepted":
        return
    if st in ("open", "deferred"):
        findings_mod.set_status(root, fid, "proposed")
    findings_mod.set_status(root, fid, "accepted", placement)


def _decide_finding(root, fid, action, placement=None):
    if action == "accept":
        return _accept_finding(root, fid, placement or None)
    recs = {r["id"]: r for r in findings_mod.load(root)}
    if fid not in recs:
        raise ValueError("unknown finding %s" % fid)
    target = "deferred" if action == "defer" else "rejected"
    if recs[fid].get("status") == "open" and target == "deferred":
        findings_mod.set_status(root, fid, "proposed")
    findings_mod.set_status(root, fid, target, "backlog" if target == "deferred" else None)


def apply_decisions(root):
    done = []
    for d in load_decisions(root):
        path = d.pop("_path")
        t = d.get("target") or {}
        kind, tid, action = t.get("kind"), str(t.get("id", "")), d.get("action")
        try:
            if action not in DECISION_ACTIONS.get(kind, ()):
                raise ValueError("invalid action %r for %r" % (action, kind))
            if kind == "finding":
                _decide_finding(root, tid, action, d.get("placement"))
            else:
                cr = next((c for c in load_crs(root) if c.get("id") == tid), None)
                if cr is None or cr.get("status") not in ("proposed", "accepted"):
                    raise ValueError("CR %s is not open" % tid)
                if action == "reject":
                    _set_cr(cr, status="rejected", resolution="rejected from the console" + (": " + d["note"] if d.get("note") else ""))
                else:
                    _set_cr(cr, status="accepted")
            d.update(status="applied", applied=_now())
        except ValueError as e:
            d.update(status="invalid", error=str(e))
        _write_json(path, d)
        done.append({k: d.get(k) for k in ("id", "target", "action", "status", "error")})
    return done


# ---------------------------------------------------------------- CLI
def _root(cwd):
    if cwd:
        return os.path.abspath(cwd)
    try:
        r = state_schema.find_graph_root(os.getcwd())
    except Exception:
        r = None
    return r or os.getcwd()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="inbox.py")
    ap.add_argument("--cwd")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pending")
    sub.add_parser("next-id")
    v = sub.add_parser("validate")
    v.add_argument("file")
    a = sub.add_parser("apply")
    a.add_argument("id")
    a.add_argument("--dry-run", action="store_true")
    d = sub.add_parser("decisions")
    d.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    root = _root(args.cwd)
    try:
        if args.cmd == "pending":
            print(json.dumps(pending(root)))
        elif args.cmd == "next-id":
            print(next_id(root))
        elif args.cmd == "validate":
            errs = validate(_read_json(args.file))
            for e in errs:
                print(e, file=sys.stderr)
            return 1 if errs else 0
        elif args.cmd == "apply":
            return apply(root, args.id, args.dry_run)
        elif args.cmd == "decisions":
            print(json.dumps(apply_decisions(root) if args.apply else
                             [{k: x.get(k) for k in ("id", "target", "action")} for x in load_decisions(root)]))
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
