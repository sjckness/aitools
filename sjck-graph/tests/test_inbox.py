import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import findings  # noqa: E402
import inbox  # noqa: E402


def card(title, files=("a.py",)):
    return ("# %s\n## Obiettivo\nDo it.\n## Puoi modificare\n%s\n"
            "## Criteri di accettazione\n- [ ] `pytest` passes\n" % (title, "\n".join("- `%s`" % f for f in files)))


class InboxTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        g = os.path.join(self.root, ".sjck")
        os.makedirs(os.path.join(g, "cards"))
        os.makedirs(os.path.join(g, "out"))
        nodes = [
            {"id": "T1", "title": "base", "deps": [], "files": ["a.py"], "status": "validated"},
            {"id": "T2", "title": "mid", "deps": ["T1"], "files": ["b.py"], "status": "validated"},
            {"id": "T3", "title": "busy", "deps": ["T1"], "files": ["c.py"], "status": "running"},
            {"id": "T4", "title": "late", "deps": ["T2"], "files": ["d.py"], "status": "pending"},
        ]
        for n in nodes:
            with open(os.path.join(g, "cards", n["id"] + ".md"), "w") as f:
                f.write(card(n["title"], n["files"]))
        with open(os.path.join(g, "out", "T2.json"), "w") as f:
            f.write('{"id":"T2","status":"done"}')
        with open(os.path.join(g, "state.json"), "w") as f:
            json.dump({"goal": "g", "status": "running", "nodes": nodes, "log": []}, f)

    def cr(self, ops, cid=None, **kw):
        cid = cid or inbox.next_id(self.root)
        cr = {"id": cid, "summary": "test", "priority": "normal", "status": "proposed", "ops": ops}
        cr.update(kw)
        p = os.path.join(self.root, ".sjck", "changes", cid + ".json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump(cr, f)
        return cid

    def apply(self, cid, **kw):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = inbox.apply(self.root, cid, **kw)
        return code, buf.getvalue()

    def raw(self):
        with open(os.path.join(self.root, ".sjck", "state.json")) as f:
            return f.read()

    def state(self):
        with open(os.path.join(self.root, ".sjck", "state.json")) as f:
            return {n["id"]: n for n in json.load(f)["nodes"]}

    def crfile(self, cid):
        with open(os.path.join(self.root, ".sjck", "changes", cid + ".json")) as f:
            return json.load(f)

    def test_validate(self):
        self.assertTrue(inbox.validate({"id": "x"}))
        self.assertIn("ops must be a non-empty list", inbox.validate({"id": "CR-001", "summary": "s", "ops": []}))
        errs = inbox.validate({"id": "CR-001", "summary": "s", "ops": [
            {"op": "set", "id": "T1", "fields": {"status": "validated"}},
            {"op": "kit_change", "target": "../../etc/passwd", "patch": "x"},
            {"op": "nope"}]})
        self.assertEqual(len(errs), 3)

    def test_next_id_and_pending_order(self):
        self.assertEqual(inbox.next_id(self.root), "CR-001")
        self.cr([{"op": "rerun", "id": "T4"}], priority="normal")
        self.cr([{"op": "rerun", "id": "T4"}], priority="now")
        p = inbox.pending(self.root)
        self.assertEqual([c["id"] for c in p["crs"]], ["CR-002", "CR-001"])
        self.assertTrue(p["blocking"])

    def test_add_node_and_dep(self):
        cid = self.cr([{"op": "add_node", "node": {"id": "T5", "title": "new", "deps": ["T2"], "files": ["e.py"]},
                        "card": card("new", ["e.py"])},
                       {"op": "add_dep", "id": "T4", "dep": "T5"}])
        code, out = self.apply(cid)
        self.assertEqual(code, 0, out)
        s = self.state()
        self.assertEqual(s["T5"]["status"], "pending")
        self.assertIn("T5", s["T4"]["deps"])
        self.assertTrue(os.path.exists(os.path.join(self.root, ".sjck", "cards", "T5.md")))
        self.assertEqual(self.crfile(cid)["status"], "applied")

    def test_rerun_cascades_and_keeps_old_output(self):
        cid = self.cr([{"op": "edit_card", "id": "T2", "card": card("mid v2", ["b.py"])}])
        code, out = self.apply(cid)
        self.assertEqual(code, 0, out)
        s = self.state()
        self.assertEqual(s["T2"]["status"], "pending")
        self.assertEqual(s["T1"]["status"], "validated")
        self.assertTrue(os.path.exists(os.path.join(self.root, ".sjck", "out", "T2.prev.json")))
        self.assertEqual(self.crfile(cid)["impact"]["rerun"], ["T2", "T4"])

    def test_running_node_waits(self):
        cid = self.cr([{"op": "set", "id": "T3", "fields": {"model": "opus"}}])
        code, out = self.apply(cid)
        self.assertEqual(code, 3, out)
        self.assertEqual(self.crfile(cid)["status"], "proposed")
        cid2 = self.cr([{"op": "rerun", "id": "T1"}])  # T3 depends on T1 and is running
        self.assertEqual(self.apply(cid2)[0], 3)

    def test_plan_score_reject_rolls_back(self):
        cid = self.cr([{"op": "add_node", "node": {"id": "T5", "deps": ["T1"], "files": ["c.py"]},
                        "card": "# no criteria\n## Obiettivo\nx\n"}])
        before = self.raw()
        code, out = self.apply(cid)
        self.assertEqual(code, 1, out)
        self.assertIn("plan score reject", self.crfile(cid)["resolution"])
        self.assertEqual(self.raw(), before)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".sjck", "cards", "T5.md")))

    def test_dry_run_changes_nothing(self):
        cid = self.cr([{"op": "remove_node", "id": "T4"}])
        before = self.raw()
        code, out = self.apply(cid, dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("would apply", out)
        self.assertEqual(self.raw(), before)
        self.assertEqual(self.crfile(cid)["status"], "proposed")

    def test_remove_rules(self):
        self.assertEqual(self.apply(self.cr([{"op": "remove_node", "id": "T2"}]))[0], 1)  # validated
        self.assertEqual(self.apply(self.cr([{"op": "remove_node", "id": "T4"}]))[0], 0)
        self.assertNotIn("T4", self.state())

    def test_kit_change_is_only_a_proposal(self):
        cid = self.cr([{"op": "kit_change", "target": "agents/sjck-validator.md", "patch": "add a ROS check"}])
        self.assertEqual(self.apply(cid)[0], 0)
        self.assertTrue(os.path.exists(os.path.join(self.root, ".sjck", "kit-proposals", cid + "-1.md")))

    def test_accept_finding_via_cr_and_decisions(self):
        f1 = findings.add(self.root, **{"from": "T2", "file": "x.py", "kind": "bug", "severity": "med", "what": "w1"})
        f2 = findings.add(self.root, **{"from": "T2", "file": "y.py", "kind": "doc", "severity": "low", "what": "w2"})
        f3 = findings.add(self.root, **{"from": "T2", "file": "z.py", "kind": "doc", "severity": "low", "what": "w3"})
        cid = self.cr([{"op": "add_node", "node": {"id": "T6", "deps": [], "files": ["x.py"]}, "card": card("fix", ["x.py"])},
                       {"op": "accept_finding", "finding": f1, "as_node": "T6"}])
        self.assertEqual(self.apply(cid)[0], 0)
        recs = {r["id"]: r for r in findings.load(self.root)}
        self.assertEqual((recs[f1]["status"], recs[f1]["placement"]), ("accepted", "node:T6"))
        cid2 = self.cr([{"op": "rerun", "id": "T4"}])
        ddir = os.path.join(self.root, ".sjck", "decisions")
        os.makedirs(ddir)
        for i, (t, a) in enumerate([({"kind": "finding", "id": f2}, "defer"), ({"kind": "finding", "id": f3}, "reject"),
                                    ({"kind": "cr", "id": cid2}, "reject"), ({"kind": "finding", "id": "F999"}, "accept"),
                                    ({"kind": "cr", "id": cid2}, "explode")]):
            with open(os.path.join(ddir, "D-%d.json" % i), "w") as f:
                json.dump({"id": "D-%d" % i, "target": t, "action": a, "status": "new"}, f)
        res = inbox.apply_decisions(self.root)
        self.assertEqual([r["status"] for r in res], ["applied", "applied", "applied", "invalid", "invalid"])
        recs = {r["id"]: r for r in findings.load(self.root)}
        self.assertEqual((recs[f2]["status"], recs[f2]["placement"]), ("deferred", "backlog"))
        self.assertEqual(recs[f3]["status"], "rejected")
        self.assertEqual(self.crfile(cid2)["status"], "rejected")
        self.assertEqual(inbox.load_decisions(self.root), [])

    def test_cli(self):
        self.cr([{"op": "rerun", "id": "T4"}])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(inbox.main(["--cwd", self.root, "pending"]), 0)
        self.assertEqual(json.loads(buf.getvalue())["crs"][0]["id"], "CR-001")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(inbox.main(["--cwd", self.root, "apply", "CR-404"]), 2)


if __name__ == "__main__":
    unittest.main()
