#!/usr/bin/env python3
"""Confronta due risultati di evals/run.py: tabella markdown su stdout."""
import json
import sys


def load(path):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return {r["id"]: r for r in doc["results"]}, doc.get("totals", {})


def wd(r):
    m = r.get("metrics", {})
    return m.get("watchdog_warnings", 0) + m.get("watchdog_stops", 0)


COLS = [
    ("successo", lambda r: "sì" if r.get("success") else "no"),
    ("tool_calls", lambda r: r.get("metrics", {}).get("tool_calls", 0)),
    ("duration_s", lambda r: round(r.get("duration_s", 0), 1)),
    ("validator_fails", lambda r: r.get("metrics", {}).get("validator_fails", 0)),
    ("watchdog", wd),
    ("findings", lambda r: r.get("metrics", {}).get("findings", 0)),
]


def cell(fn, a, b):
    return "%s → %s" % (fn(a) if a is not None else "—", fn(b) if b is not None else "—")


def main(argv):
    if len(argv) != 3:
        print("uso: compare.py A.json B.json", file=sys.stderr)
        return 2
    try:
        ra, ta = load(argv[1])
        rb, tb = load(argv[2])
    except (OSError, ValueError, KeyError, TypeError) as e:
        print("file non leggibile: %s" % e, file=sys.stderr)
        return 2
    print("| task | " + " | ".join(c[0] for c in COLS) + " |")
    print("|" + "---|" * (len(COLS) + 1))
    for tid in sorted(set(ra) | set(rb)):
        a, b = ra.get(tid), rb.get(tid)
        print("| %s | %s |" % (tid, " | ".join(cell(fn, a, b) for _, fn in COLS)))

    def tot(rs, t):
        v = list(rs.values())
        return {
            "successo": "%d/%d" % (sum(1 for r in v if r.get("success")), len(v)),
            "tool_calls": sum(r.get("metrics", {}).get("tool_calls", 0) for r in v),
            "duration_s": round(sum(r.get("duration_s", 0) for r in v), 1),
            "validator_fails": sum(r.get("metrics", {}).get("validator_fails", 0) for r in v),
            "watchdog": sum(wd(r) for r in v),
            "findings": sum(r.get("metrics", {}).get("findings", 0) for r in v),
        }
    xa, xb = tot(ra, ta), tot(rb, tb)
    print("| **TOTALE** | %s |" % " | ".join("%s → %s" % (xa[c], xb[c]) for c, _ in COLS))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
