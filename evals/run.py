#!/usr/bin/env python3
"""Eval harness: lancia le task di evals/tasks e raccoglie i risultati.

Solo standard library. Vedi evals/README.md.
"""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
METRIC_KEYS = ["subagents", "validator_fails", "tool_calls", "watchdog_warnings",
               "watchdog_stops", "findings", "findings_accepted", "duration_s"]
TRAPS = {"rabbit_hole", "out_of_scope_bug"}
SIZES = {"S", "M", "L"}
DEFAULT_CMD = 'claude -p "/sjck-run {task}"'
PLUGIN_DIR = os.path.join(os.path.dirname(HERE), "sjck-graph")


def default_flags():
    """Flag di default: plugin del checkout, permessi non interattivi."""
    return ("--plugin-dir %s --permission-mode acceptEdits --allowedTools Bash"
            % shlex.quote(PLUGIN_DIR))


def load_meta(task_dir):
    """Ritorna (meta, errore). Valida struttura e meta.json."""
    name = os.path.basename(os.path.normpath(task_dir))
    for f in ("task.md", "check.sh", "meta.json"):
        if not os.path.isfile(os.path.join(task_dir, f)):
            return None, "manca " + f
    if not os.path.isdir(os.path.join(task_dir, "repo")):
        return None, "manca repo/"
    try:
        with open(os.path.join(task_dir, "meta.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, ValueError) as e:
        return None, "meta.json non valido: %s" % e
    if not isinstance(meta, dict):
        return None, "meta.json non valido: non e' un oggetto"
    if meta.get("id") != name:
        return None, "meta.json: id %r diverso dalla cartella %r" % (meta.get("id"), name)
    if meta.get("size") not in SIZES:
        return None, "meta.json: size deve essere S|M|L"
    if not isinstance(meta.get("tags"), list):
        return None, "meta.json: tags deve essere una lista"
    traps = meta.get("traps", [])
    if not isinstance(traps, list) or not set(traps) <= TRAPS:
        return None, "meta.json: traps deve essere sottoinsieme di %s" % sorted(TRAPS)
    return meta, None


def list_tasks(tasks_dir, only):
    if not os.path.isdir(tasks_dir):
        return []
    names = sorted(d for d in os.listdir(tasks_dir)
                   if os.path.isdir(os.path.join(tasks_dir, d)))
    if only:
        names = [n for n in names if n in only]
    return names


def run_check(task_dir, workdir):
    p = subprocess.run(["bash", os.path.join(os.path.abspath(task_dir), "check.sh")],
                       cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       universal_newlines=True, timeout=300)
    return p.returncode


def dry_run(tasks_dir, only):
    ok_all = True
    names = list_tasks(tasks_dir, only)
    if not names:
        print("KO: nessuna task trovata in %s" % tasks_dir)
        return 1
    for name in names:
        tdir = os.path.join(tasks_dir, name)
        meta, err = load_meta(tdir)
        if err:
            print("KO %s: %s" % (name, err))
            ok_all = False
            continue
        tmp = tempfile.mkdtemp(prefix="evals-dry-")
        try:
            work = os.path.join(tmp, "repo")
            shutil.copytree(os.path.join(tdir, "repo"), work)
            try:
                rc = run_check(tdir, work)
            except subprocess.TimeoutExpired:
                print("KO %s: check.sh in timeout" % name)
                ok_all = False
                continue
            if rc == 0:
                print("KO %s: già risolta (check.sh exit 0 sulla fixture)" % name)
                ok_all = False
            else:
                print("OK %s" % name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok_all else 1


def git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, universal_newlines=True)


def read_state(work):
    path = os.path.join(work, ".sjck", "state.json")
    if not os.path.isfile(path):
        return {}, None
    try:
        with open(path, encoding="utf-8") as fh:
            st = json.load(fh)
        return (st if isinstance(st, dict) else {}), None
    except (OSError, ValueError) as e:
        return {}, "state.json illeggibile: %s" % e


def norm_metrics(raw):
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for k in METRIC_KEYS:
        v = raw.get(k, 0)
        out[k] = v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0
    return out


def run_task(tasks_dir, name, cmd_tpl, flags, timeout, keep):
    # flags = stringa effettiva (default + extra), gia' composta da main()
    tdir = os.path.join(tasks_dir, name)
    meta, err = load_meta(tdir)
    rec = {"id": name, "size": (meta or {}).get("size"), "tags": (meta or {}).get("tags", []),
           "success": False, "cmd_exit": None, "check_exit": None, "duration_s": 0.0,
           "metrics": norm_metrics({}), "plan_score": None, "error": err}
    if err:
        return rec
    tmp = tempfile.mkdtemp(prefix="evals-run-")
    work = os.path.join(tmp, "repo")
    try:
        shutil.copytree(os.path.join(tdir, "repo"), work)
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=evals", "-c", "user.email=evals@localhost",
                      "commit", "-q", "-m", "initial"]):
            r = git(args, work)
            if r.returncode != 0:
                rec["error"] = "git %s fallito: %s" % (args[0], r.stdout.strip())
                return rec
        task_file = os.path.abspath(os.path.join(tdir, "task.md"))
        with open(task_file, encoding="utf-8") as fh:
            task_text = fh.read().strip()
        argv = [a.replace("{task_file}", task_file).replace("{task}", task_text)
                for a in shlex.split(cmd_tpl)]
        argv += shlex.split(flags or "")
        t0 = time.time()
        try:
            p = subprocess.run(argv, cwd=work, timeout=timeout,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               universal_newlines=True)
            rec["cmd_exit"] = p.returncode
        except subprocess.TimeoutExpired:
            rec["error"] = "timeout dopo %ss" % timeout
        except OSError as e:
            rec["error"] = "comando non eseguibile: %s" % e
        rec["duration_s"] = round(time.time() - t0, 2)
        try:
            rec["check_exit"] = run_check(tdir, work)
        except subprocess.TimeoutExpired:
            rec["error"] = (rec["error"] + "; " if rec["error"] else "") + "check.sh in timeout"
        rec["success"] = rec["check_exit"] == 0
        st, serr = read_state(work)
        rec["metrics"] = norm_metrics(st.get("metrics"))
        ps = st.get("plan_score")
        rec["plan_score"] = ps if isinstance(ps, dict) else None
        if serr and not rec["error"]:
            rec["error"] = serr
        return rec
    finally:
        if keep:
            print("copia mantenuta: " + work, file=sys.stderr)
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def totals(results):
    t = {"tasks": len(results), "successes": sum(1 for r in results if r["success"]),
         "tool_calls": 0, "duration_s": 0.0, "validator_fails": 0,
         "watchdog_warnings": 0, "watchdog_stops": 0, "findings": 0}
    for r in results:
        t["duration_s"] += r["duration_s"]
        for k in ("tool_calls", "validator_fails", "watchdog_warnings",
                  "watchdog_stops", "findings"):
            t[k] += r["metrics"].get(k, 0)
    t["duration_s"] = round(t["duration_s"], 2)
    return t


def main(argv=None):
    ap = argparse.ArgumentParser(description="Esegue le task di eval.")
    ap.add_argument("--dry-run", action="store_true",
                    help="valida le fixture senza lanciare Claude")
    ap.add_argument("--tasks-dir", default=os.path.join(HERE, "tasks"))
    ap.add_argument("--task", action="append", default=[], help="id task (ripetibile)")
    ap.add_argument("--cmd", default=DEFAULT_CMD,
                    help="comando; {task}=testo di task.md, {task_file}=suo percorso")
    ap.add_argument("--flags", default="", help="flag extra aggiunti dopo i default")
    ap.add_argument("--no-default-flags", action="store_true",
                    help="non aggiunge --plugin-dir/--permission-mode/--allowedTools")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--out", default=None)
    ap.add_argument("--keep", action="store_true", help="non cancella le copie")
    a = ap.parse_args(argv)

    if a.dry_run:
        return dry_run(a.tasks_dir, a.task)

    names = list_tasks(a.tasks_dir, a.task)
    if not names:
        print("nessuna task trovata in %s" % a.tasks_dir, file=sys.stderr)
        return 1
    parts = [] if a.no_default_flags else [default_flags()]
    if a.flags:
        parts.append(a.flags)
    eff_flags = " ".join(parts)
    results = []
    for n in names:
        r = run_task(a.tasks_dir, n, a.cmd, eff_flags, a.timeout, a.keep)
        print("%s %s" % ("PASS" if r["success"] else "FAIL", n), file=sys.stderr)
        results.append(r)
    doc = {"created": datetime.now().isoformat(timespec="seconds"),
           "cmd": a.cmd, "flags": eff_flags, "results": results, "totals": totals(results)}
    out = a.out
    if not out:
        rdir = os.path.join(HERE, "results")
        os.makedirs(rdir, exist_ok=True)
        out = os.path.join(rdir, datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
