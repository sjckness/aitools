#!/usr/bin/env python3
"""Findings del grafo: `.graph/findings.jsonl`, un oggetto JSON per riga.

Record: id ("F001" progressivo), from, file, line (int, 0 = ignota),
kind (bug|smell|debt|doc|loop), severity (high|med|low), what,
suggested_fix, status (open|proposed|accepted|deferred|rejected),
placement ("" | "card:<ID>" | "node:<ID>" | "backlog"), duplicates ([id]).

Transizioni: open->proposed|rejected; proposed->accepted|deferred|rejected;
deferred->proposed.

CLI (la radice e' --cwd, altrimenti find_graph_root(cwd), altrimenti cwd):
  findings.py [--cwd DIR] add --from ID --file PATH [--line N] --kind K
                          --severity S --what TEXT [--fix TEXT]   # stampa l'id
  findings.py [--cwd DIR] dedupe                      # stampa i record uniti
  findings.py [--cwd DIR] set ID STATUS [--placement P]  # exit 2 se non valido
  findings.py [--cwd DIR] list [--status S]           # array JSON
Valori non validi o transizioni non valide: messaggio su stderr, exit 2.
"""
import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state_schema  # noqa: E402

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

KINDS = ("bug", "smell", "debt", "doc", "loop")
SEVERITIES = ("high", "med", "low")
STATUSES = ("open", "proposed", "accepted", "deferred", "rejected")
TRANSITIONS = {
    "open": ("proposed", "rejected"),
    "proposed": ("accepted", "deferred", "rejected"),
    "deferred": ("proposed",),
}
_SEV_RANK = {"low": 0, "med": 1, "high": 2}
_PLACEMENT_RE = re.compile(r"^(card|node):.+$")


def _path(root):
    return os.path.join(root, ".graph", "findings.jsonl")


def _read(root, warn=True):
    """Ritorna (record validi, righe non valide invariate)."""
    p = _path(root)
    if not os.path.isfile(p):
        return [], []
    out, bad = [], []
    with open(p, encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                r = None
            if isinstance(r, dict) and isinstance(r.get("id"), str):
                out.append(r)
            else:
                bad.append(line)
                if warn:
                    print("findings.jsonl:%d: riga non valida, ignorata" % n,
                          file=sys.stderr)
    return out, bad


def load(root):
    return _read(root)[0]


def _write_all(root, records, extra=()):
    p = _path(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp.%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        for line in extra:
            f.write(line + "\n")
    os.replace(tmp, p)


class _Lock:
    def __init__(self, root):
        d = os.path.join(root, ".graph")
        os.makedirs(d, exist_ok=True)
        self.path = os.path.join(d, "findings.lock")
        self.f = None

    def __enter__(self):
        if fcntl:
            self.f = open(self.path, "w")
            fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        if self.f:
            fcntl.flock(self.f, fcntl.LOCK_UN)
            self.f.close()


def _num(fid):
    try:
        return int(str(fid)[1:])
    except ValueError:
        return 0


def _valid_placement(p):
    return p in ("", "backlog") or bool(_PLACEMENT_RE.match(p))


def add(root, **campi):
    """Aggiunge un finding; ritorna l'id. Campi: from_/from, file, line, kind,
    severity, what, suggested_fix (o fix). ValueError se non validi."""
    author = campi.get("from", campi.get("from_", ""))
    kind = campi.get("kind")
    sev = campi.get("severity")
    if kind not in KINDS:
        raise ValueError("kind non valido: %r" % (kind,))
    if sev not in SEVERITIES:
        raise ValueError("severity non valida: %r" % (sev,))
    try:
        line = int(campi.get("line") or 0)
    except (TypeError, ValueError):
        raise ValueError("line non valida: %r" % (campi.get("line"),))
    if line < 0:
        raise ValueError("line non valida: %r" % line)
    fix = campi.get("suggested_fix", campi.get("fix", "")) or ""
    with _Lock(root):
        recs = load(root)
        nxt = max([_num(r.get("id", "")) for r in recs] + [0]) + 1
        fid = "F%03d" % nxt
        rec = {"id": fid, "from": author, "file": campi.get("file", ""),
               "line": line, "kind": kind, "severity": sev,
               "what": campi.get("what", ""), "suggested_fix": fix,
               "status": "open", "placement": "", "duplicates": []}
        with open(_path(root), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return fid


def _sim(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _is_dup(a, b):
    if os.path.normpath(a.get("file", "")) != os.path.normpath(b.get("file", "")):
        return False
    s = _sim(a.get("what", ""), b.get("what", ""))
    la, lb = a.get("line", 0), b.get("line", 0)
    if la == 0 or lb == 0:
        return s >= 0.8
    return abs(la - lb) <= 5 and s >= 0.6


def dedupe(root):
    """Unisce i duplicati tra i record open/proposed; ritorna quanti ne ha rimossi."""
    with _Lock(root):
        recs, bad = _read(root)
        recs_sorted = sorted(range(len(recs)), key=lambda i: _num(recs[i].get("id", "")))
        removed = set()
        for ii, i in enumerate(recs_sorted):
            a = recs[i]
            if i in removed or a.get("status") not in ("open", "proposed"):
                continue
            for j in recs_sorted[ii + 1:]:
                b = recs[j]
                if j in removed or b.get("status") not in ("open", "proposed"):
                    continue
                if _is_dup(a, b):
                    if _SEV_RANK.get(b.get("severity"), 0) > _SEV_RANK.get(a.get("severity"), 0):
                        a["severity"] = b["severity"]
                    a["duplicates"] = list(a.get("duplicates", [])) + [b["id"]] + \
                        [d for d in b.get("duplicates", [])]
                    removed.add(j)
        if removed:
            _write_all(root, [r for k, r in enumerate(recs) if k not in removed], bad)
        return len(removed)


def set_status(root, fid, status, placement=None):
    """Cambia stato (e opzionalmente placement). ValueError se non valido."""
    if status not in STATUSES:
        raise ValueError("status non valido: %r" % (status,))
    if placement is not None and not _valid_placement(placement):
        raise ValueError("placement non valido: %r" % (placement,))
    with _Lock(root):
        recs, bad = _read(root)
        for r in recs:
            if r["id"] == fid:
                if status not in TRANSITIONS.get(r.get("status"), ()):
                    raise ValueError("transizione non valida: %s -> %s"
                                     % (r.get("status"), status))
                r["status"] = status
                if placement is not None:
                    r["placement"] = placement
                _write_all(root, recs, bad)
                return
        raise ValueError("id inesistente: %s" % fid)


def _root(cwd):
    if cwd:
        return os.path.abspath(cwd)
    start = os.getcwd()
    try:
        r = state_schema.find_graph_root(start)
    except Exception:
        r = None
    return r or start


def main(argv=None):
    ap = argparse.ArgumentParser(prog="findings.py")
    ap.add_argument("--cwd")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--from", dest="from_", required=True)
    a.add_argument("--file", required=True)
    a.add_argument("--line", type=int, default=0)
    a.add_argument("--kind", required=True)
    a.add_argument("--severity", required=True)
    a.add_argument("--what", required=True)
    a.add_argument("--fix", default="")
    sub.add_parser("dedupe")
    s = sub.add_parser("set")
    s.add_argument("id")
    s.add_argument("status")
    s.add_argument("--placement")
    l = sub.add_parser("list")
    l.add_argument("--status")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    root = _root(args.cwd)
    try:
        if args.cmd == "add":
            print(add(root, **{"from": args.from_, "file": args.file,
                               "line": args.line, "kind": args.kind,
                               "severity": args.severity, "what": args.what,
                               "suggested_fix": args.fix}))
        elif args.cmd == "dedupe":
            print(dedupe(root))
        elif args.cmd == "set":
            set_status(root, args.id, args.status, args.placement)
        else:
            recs = load(root)
            if args.status:
                recs = [r for r in recs if r.get("status") == args.status]
            print(json.dumps(recs, ensure_ascii=False, indent=2))
    except ValueError as e:
        print("errore: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
