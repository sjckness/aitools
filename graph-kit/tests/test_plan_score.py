import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)

import plan_score  # noqa: E402

CARD = "# %s\n## Criteri di accettazione\n- `true` → exit 0\n"


def node(i, deps=(), files=None, **kw):
    n = {"id": i, "title": i, "agent": "implementer", "deps": list(deps),
         "files": files if files is not None else [i.lower() + ".py"],
         "status": "pending", "attempts": 0, "agent_id": ""}
    n.update(kw)
    return n


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.cards = os.path.join(self.root, ".graph", "cards")
        os.makedirs(self.cards)

    def tearDown(self):
        self.tmp.cleanup()

    def run_score(self, nodes, cards=True, text=None):
        if cards:
            for n in nodes:
                with open(os.path.join(self.cards, n["id"] + ".md"), "w") as f:
                    f.write(text if text is not None else CARD % n["id"])
        return plan_score.score({"nodes": nodes}, self.cards)


class TestScore(Base):
    def test_linear(self):
        r = self.run_score([node("T01"), node("T02", ["T01"]),
                            node("T03", ["T02"])])
        self.assertEqual((r["width"], r["critical_path"]), (1, 3))
        self.assertEqual(r["verdict"], "ok")
        self.assertEqual(r["reasons"], [])

    def test_wide(self):
        r = self.run_score([node("T01"), node("T02", ["T01"]),
                            node("T03", ["T01"]), node("T04", ["T01"])])
        self.assertEqual((r["width"], r["critical_path"]), (3, 2))
        self.assertEqual(r["verdict"], "ok")

    def test_overlap(self):
        r = self.run_score([node("T01"),
                            node("T02", ["T01"], ["./x/a.py"]),
                            node("T03", ["T01"], ["x/a.py"])])
        self.assertEqual(r["file_overlap"], 1)
        self.assertEqual(r["verdict"], "reject")
        self.assertTrue(any("T02" in s and "T03" in s for s in r["reasons"]))

    def test_overlap_dir_and_ordered_ok(self):
        r = self.run_score([node("T01", [], ["d/"]),
                            node("T02", ["T01"], ["d/a.py"]),
                            node("T03", [], ["d/b.py"])])
        # solo T01-T03 (dir copre d/b.py); T01-T02 sono ordinati
        self.assertEqual(r["file_overlap"], 1)

    def test_cycle(self):
        r = self.run_score([node("T01", ["T02"]), node("T02", ["T01"])])
        self.assertEqual(r["verdict"], "reject")
        self.assertTrue(any("ciclo" in s for s in r["reasons"]))
        self.assertEqual((r["width"], r["critical_path"]), (0, 0))

    def test_over_budget_card(self):
        n = node("T01", budget={"tool_calls": 40, "context_tokens": 10})
        r = self.run_score([n], text=CARD % ("x" * 400))
        self.assertEqual(r["verdict"], "reject")
        self.assertTrue(any("budget" in s and "T01" in s for s in r["reasons"]))

    def test_no_criteria(self):
        r = self.run_score([node("T01")], text="# T01\n## Obiettivo\nfai\n")
        self.assertEqual(r["verdict"], "reject")
        self.assertTrue(any("criteri" in s for s in r["reasons"]))

    def test_missing_dep(self):
        r = self.run_score([node("T01", ["T99"])])
        self.assertEqual(r["verdict"], "reject")
        self.assertTrue(any("T99" in s for s in r["reasons"]))

    def test_missing_card(self):
        r = self.run_score([node("T01")], cards=False)
        self.assertEqual(r["verdict"], "reject")
        self.assertTrue(any("mancante" in s for s in r["reasons"]))


class TestCli(Base):
    def _run(self):
        return subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "plan_score.py"),
             "--cwd", self.root], capture_output=True, text=True)

    def test_cli_writes_state(self):
        state = {"goal": "g", "mode": "L", "nodes": [node("T01")],
                 "log": ["x"], "metrics": {"subagents": 2}}
        with open(os.path.join(self.root, ".graph", "state.json"), "w") as f:
            json.dump(state, f)
        with open(os.path.join(self.cards, "T01.md"), "w") as f:
            f.write(CARD % "T01")
        p = self._run()
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(os.path.join(self.root, ".graph", "state.json")) as f:
            s = json.load(f)
        self.assertEqual(s["plan_score"]["verdict"], "ok")
        self.assertEqual(s["goal"], "g")
        self.assertEqual(s["log"], ["x"])
        self.assertEqual(json.loads(p.stdout)["verdict"], "ok")

    def test_cli_reject_exit1(self):
        state = {"goal": "g", "nodes": [node("T01")]}
        with open(os.path.join(self.root, ".graph", "state.json"), "w") as f:
            json.dump(state, f)
        self.assertEqual(self._run().returncode, 1)

    def test_cli_missing_state_exit2(self):
        self.assertEqual(self._run().returncode, 2)


if __name__ == "__main__":
    unittest.main()
