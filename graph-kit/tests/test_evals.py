import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


def find_evals():
    d = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.isfile(os.path.join(d, "evals", "run.py")):
            return os.path.join(d, "evals")
        parent = os.path.dirname(d)
        if parent == d:
            raise RuntimeError("evals/ non trovata")
        d = parent


EVALS = find_evals()
RUN = os.path.join(EVALS, "run.py")
COMPARE = os.path.join(EVALS, "compare.py")


def sh(*args):
    p = subprocess.run([sys.executable] + list(args), stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, universal_newlines=True)
    return p.returncode, p.stdout


def make_task(tasks, tid, solved, meta=None):
    d = os.path.join(tasks, tid)
    os.makedirs(os.path.join(d, "repo"))
    with open(os.path.join(d, "task.md"), "w") as f:
        f.write("fai qualcosa\n")
    with open(os.path.join(d, "check.sh"), "w") as f:
        f.write("exit %d\n" % (0 if solved else 1))
    with open(os.path.join(d, "repo", "a.txt"), "w") as f:
        f.write("x\n")
    with open(os.path.join(d, "meta.json"), "w") as f:
        if meta is None:
            meta = json.dumps({"id": tid, "size": "S", "tags": [], "traps": []})
        f.write(meta)


class TestEvals(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.tasks = os.path.join(self.tmp, "tasks")
        os.makedirs(self.tasks)

    def test_dry_run_real_tasks(self):
        rc, out = sh(RUN, "--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.count("OK "), 6, out)

    def test_dry_run_already_solved(self):
        make_task(self.tasks, "gia_fatta", solved=True)
        rc, out = sh(RUN, "--dry-run", "--tasks-dir", self.tasks)
        self.assertNotEqual(rc, 0)
        self.assertIn("gia_fatta", out)
        self.assertIn("KO", out)

    def test_invalid_meta(self):
        make_task(self.tasks, "rotta", solved=False, meta="{non json")
        rc, out = sh(RUN, "--dry-run", "--tasks-dir", self.tasks)
        self.assertNotEqual(rc, 0)
        self.assertIn("KO rotta", out)

    def test_real_mode(self):
        make_task(self.tasks, "t1", solved=False)
        res = os.path.join(self.tmp, "out", "r.json")
        rc, out = sh(RUN, "--tasks-dir", self.tasks, "--cmd", "true {task}", "--out", res)
        self.assertEqual(rc, 0, out)
        with open(res) as f:
            doc = json.load(f)
        r = doc["results"][0]
        for k in ("id", "size", "tags", "success", "cmd_exit", "check_exit",
                  "duration_s", "metrics", "plan_score", "error"):
            self.assertIn(k, r)
        self.assertFalse(r["success"])
        self.assertEqual(r["cmd_exit"], 0)
        self.assertEqual(r["check_exit"], 1)
        self.assertEqual(r["metrics"]["tool_calls"], 0)
        self.assertEqual(doc["totals"]["tasks"], 1)
        self.assertEqual(doc["totals"]["successes"], 0)

    def test_compare(self):
        def res(path, ids, ok):
            doc = {"results": [{"id": i, "success": ok, "duration_s": 3.0,
                                "metrics": {"tool_calls": 5, "validator_fails": 1,
                                            "watchdog_warnings": 1, "watchdog_stops": 1,
                                            "findings": 2}} for i in ids],
                   "totals": {}}
            with open(path, "w") as f:
                json.dump(doc, f)
        a, b = os.path.join(self.tmp, "a.json"), os.path.join(self.tmp, "b.json")
        res(a, ["uno", "due"], False)
        res(b, ["due", "tre"], True)
        rc, out = sh(COMPARE, a, b)
        self.assertEqual(rc, 0, out)
        for s in ("uno", "due", "tre", "TOTALE", "—"):
            self.assertIn(s, out)
        rc, _ = sh(COMPARE, a, os.path.join(self.tmp, "nope.json"))
        self.assertEqual(rc, 2)

    def _run_rec(self, *extra):
        make_task(self.tasks, "t1", solved=True)
        rec = os.path.join(self.tmp, "rec.py")
        log = os.path.join(self.tmp, "argv.json")
        with open(rec, "w") as f:
            f.write("import json, sys\njson.dump(sys.argv[1:], open(%r, 'w'))\n" % log)
        out = os.path.join(self.tmp, "res", "r.json")
        rc, o = sh(RUN, "--tasks-dir", self.tasks, "--cmd",
                   "%s %s {task}" % (sys.executable, rec), "--out", out, *extra)
        with open(out) as f:
            doc = json.load(f)
        argv = None
        if os.path.isfile(log):
            with open(log) as f:
                argv = json.load(f)
        return rc, o, doc, argv

    def test_default_flags(self):
        rc, o, doc, argv = self._run_rec("--flags=--verbose")
        self.assertEqual(rc, 0, o)
        pd = argv[argv.index("--plugin-dir") + 1]
        self.assertTrue(os.path.isabs(pd))
        self.assertTrue(pd.endswith("graph-kit"), pd)
        self.assertTrue(os.path.isfile(os.path.join(pd, ".claude-plugin", "plugin.json")))
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "acceptEdits")
        self.assertEqual(argv[argv.index("--allowedTools") + 1], "Bash")
        self.assertEqual(argv[-1], "--verbose")
        self.assertIn("--plugin-dir", doc["flags"])

    def test_no_default_flags(self):
        rc, o, doc, argv = self._run_rec("--no-default-flags")
        self.assertEqual(rc, 0, o)
        self.assertNotIn("--plugin-dir", argv)
        self.assertNotIn("--plugin-dir", doc["flags"])


if __name__ == "__main__":
    unittest.main()
