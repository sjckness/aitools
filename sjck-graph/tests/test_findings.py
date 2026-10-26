import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)
import findings  # noqa: E402

F = os.path.join(SCRIPTS, "findings.py")


def cli(d, *args):
    p = subprocess.run([sys.executable, F, "--cwd", d] + list(args),
                       capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr


def mk(d, line=10, file="a.py", sev="high", what="off by one nel parser", frm="T01"):
    return findings.add(d, **{"from": frm, "file": file, "line": line,
                              "kind": "bug", "severity": sev, "what": what})


class T(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = self._t.name

    def tearDown(self):
        self._t.cleanup()

    def test_progressive_ids(self):
        self.assertEqual(mk(self.d), "F001")
        self.assertEqual(mk(self.d), "F002")
        r = findings.load(self.d)[0]
        self.assertEqual(r["status"], "open")
        self.assertEqual(r["placement"], "")
        self.assertEqual(r["duplicates"], [])

    def test_invalid_values_exit2(self):
        rc, _, _ = cli(self.d, "add", "--from", "T", "--file", "a", "--kind", "nope",
                       "--severity", "low", "--what", "x")
        self.assertEqual(rc, 2)
        rc, _, _ = cli(self.d, "add", "--from", "T", "--file", "a", "--kind", "bug",
                       "--severity", "huge", "--what", "x")
        self.assertEqual(rc, 2)
        self.assertEqual(findings.load(self.d), [])

    def test_dedupe_merges(self):
        mk(self.d, 10, sev="low")
        mk(self.d, 13, sev="high", what="off-by-one nel parser")
        self.assertEqual(findings.dedupe(self.d), 1)
        recs = findings.load(self.d)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["id"], "F001")
        self.assertEqual(recs[0]["severity"], "high")
        self.assertEqual(recs[0]["duplicates"], ["F002"])

    def test_dedupe_not_merged(self):
        mk(self.d, 10)
        mk(self.d, 20, what="off-by-one nel parser")
        mk(self.d, 10, file="b.py", what="off-by-one nel parser")
        self.assertEqual(findings.dedupe(self.d), 0)
        self.assertEqual(len(findings.load(self.d)), 3)

    def test_dedupe_line_zero_needs_high_similarity(self):
        mk(self.d, 0, what="off by one nel parser")
        mk(self.d, 3, what="off by one nel parsers")
        mk(self.d, 0, what="completamente diverso ma poco")
        self.assertEqual(findings.dedupe(self.d), 1)

    def test_valid_transitions(self):
        for path in (["proposed", "accepted"], ["proposed", "deferred", "proposed"],
                     ["proposed", "rejected"], ["rejected"]):
            d = tempfile.mkdtemp(dir=self.d)
            fid = mk(d)
            for st in path:
                findings.set_status(d, fid, st)
            self.assertEqual(findings.load(d)[0]["status"], path[-1])

    def test_invalid_transitions(self):
        fid = mk(self.d)
        with self.assertRaises(ValueError):
            findings.set_status(self.d, fid, "accepted")
        findings.set_status(self.d, fid, "rejected")
        with self.assertRaises(ValueError):
            findings.set_status(self.d, fid, "proposed")
        with self.assertRaises(ValueError):
            findings.set_status(self.d, "F099", "proposed")
        rc, _, err = cli(self.d, "set", fid, "open")
        self.assertEqual(rc, 2)
        self.assertTrue(err)

    def test_list_status_and_placement_cli(self):
        rc, out, _ = cli(self.d, "add", "--from", "T01", "--file", "a.py", "--line", "10",
                         "--kind", "bug", "--severity", "high", "--what", "off by one nel parser",
                         "--fix", "usa <=")
        self.assertEqual((rc, out), (0, "F001"))
        mk(self.d, 13, sev="med", what="off-by-one nel parser", frm="T02")
        self.assertEqual(cli(self.d, "dedupe")[1], "1")
        self.assertEqual(cli(self.d, "set", "F001", "accepted")[0], 2)
        self.assertEqual(cli(self.d, "set", "F001", "proposed")[0], 0)
        self.assertEqual(cli(self.d, "set", "F001", "accepted", "--placement", "card:T03")[0], 0)
        self.assertEqual(cli(self.d, "set", "F001", "accepted", "--placement", "boh")[0], 2)
        rc, out, _ = cli(self.d, "list", "--status", "accepted")
        arr = json.loads(out)
        self.assertEqual(len(arr), 1)
        self.assertEqual(arr[0]["placement"], "card:T03")
        self.assertEqual(arr[0]["duplicates"], ["F002"])
        self.assertEqual(arr[0]["severity"], "high")
        self.assertEqual(json.loads(cli(self.d, "list", "--status", "open")[1]), [])

    def test_load_tolerates_bad_lines(self):
        mk(self.d)
        p = os.path.join(self.d, ".sjck", "findings.jsonl")
        with open(p, "a", encoding="utf-8") as f:
            f.write("{non json\n[1,2]\n")
        r2 = dict(findings.load(self.d)[0], id="F002")
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(r2) + "\n")
        rc, out, _ = cli(self.d, "add", "--from", "T01", "--file", "b.py",
                         "--kind", "bug", "--severity", "low", "--what", "x")
        self.assertEqual((rc, out), (0, "F003"))
        rc, out, err = cli(self.d, "list")
        self.assertEqual(rc, 0)
        self.assertEqual(len(json.loads(out)), 3)
        self.assertIn("riga non valida", err)
        rc, _, _ = cli(self.d, "set", "F001", "rejected")
        self.assertEqual(rc, 0)
        with open(p, encoding="utf-8") as f:
            txt = f.read()
        self.assertIn("{non json", txt)
        self.assertIn("[1,2]", txt)


if __name__ == "__main__":
    unittest.main()
