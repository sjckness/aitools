import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
FIX = os.path.join(HERE, "fixtures")
SCRIPT = os.path.join(SCRIPTS, "graph_view.py")
DEMO = os.path.join(os.path.dirname(os.path.dirname(HERE)), "examples", "demo")
sys.path.insert(0, SCRIPTS)
import graph_view  # noqa: E402


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


class ViewTest(unittest.TestCase):
    """Il viewer rende nel browser: qui si testano i dati raccolti e la pagina generata."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, ".sjck"))
        self.addCleanup(shutil.rmtree, self.d, True)

    def put(self, fixture):
        shutil.copy(os.path.join(FIX, fixture), os.path.join(self.d, ".sjck", "state.json"))

    def write(self, name, lines):
        with open(os.path.join(self.d, ".sjck", name), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def page(self):
        with open(graph_view.render(self.d), encoding="utf-8") as f:
            return f.read()

    def test_v02(self):
        self.put("state_v02.json")
        data = graph_view.collect(self.d)
        ids = [n["id"] for n in data["state"]["nodes"]]
        self.assertEqual(ids, [n["id"] for n in load("state_v02.json")["nodes"]])
        self.assertEqual(data["findings"], [])
        self.assertEqual(data["watchdog"], [])
        self.assertIsNone(data["tokens"])
        h = self.page()
        self.assertNotIn("__DATA__", h)
        for i in ids:
            self.assertIn(i, h)

    def test_v03(self):
        self.put("state_v03.json")
        st = load("state_v03.json")
        findings = [
            {"id": "F001", "severity": "high", "kind": "bug", "file": "a.py",
             "what": "x" * 200, "status": "accepted", "placement": "card:T02"},
            {"id": "F002", "severity": "low", "kind": "doc", "file": "b.py",
             "what": "<b>y</b></script>", "status": "deferred", "placement": "backlog"},
        ]
        events = [{"ts": "2026-10-26T10:0%d:00" % i, "node": "T02", "tool": "Read",
                   "kind": k, "level": 1, "action": "warn", "detail": "d"}
                  for i, k in enumerate(["loop", "drift_read", "budget"])]
        self.write("findings.jsonl", [json.dumps(f) for f in findings])
        self.write("watchdog.jsonl", [json.dumps(e) for e in events])
        data = graph_view.collect(self.d)
        by_id = {n["id"]: n for n in data["state"]["nodes"]}
        for n in st["nodes"]:
            self.assertEqual(by_id[n["id"]]["model"], n["model"])
            self.assertEqual(by_id[n["id"]]["effort"], n["effort"])
            self.assertEqual(by_id[n["id"]]["usage"]["tool_calls"], n["usage"]["tool_calls"])
        self.assertEqual([f["id"] for f in data["findings"]], ["F001", "F002"])
        self.assertLessEqual(len(data["findings"][0]["what"]), graph_view.WHAT_MAX)
        self.assertEqual(data["watchdog"][-1]["kind"], "budget")
        self.assertEqual(data["state"]["critic"][-1]["verdict"], st["critic"][-1]["verdict"])
        self.assertEqual(data["state"]["plan_score"]["verdict"], st["plan_score"]["verdict"])
        h = self.page()
        self.assertNotIn("x" * 100, h)
        self.assertNotIn("<b>y", h)            # il testo non può rompere la pagina
        self.assertEqual(h.count("</script>"), 2)  # solo i due tag del template

    def test_usage_from_watchdog_state(self):
        z = {"tool_calls": 0, "reads_outside_card": 0, "writes_outside_card": 0,
             "watchdog_warnings": 0, "watchdog_stops": 0}
        nodes = [{"id": i, "title": i, "status": "running", "agent": "implementer",
                  "attempts": 0, "deps": [], "budget": {"tool_calls": 40},
                  "usage": dict(z)} for i in ("T1", "T2", "T3")]
        with open(os.path.join(self.d, ".sjck", "state.json"), "w") as f:
            json.dump({"goal": "g", "status": "running", "nodes": nodes}, f)
        wp = os.path.join(self.d, ".sjck", "watchdog_state.json")
        with open(wp, "w") as f:
            json.dump({"T1": {"sig": "0:a", "usage": dict(z, tool_calls=7)},
                       "_common": {"sig": "T2,T3", "usage": dict(z, tool_calls=5)}}, f)
        calls = {n["id"]: n["usage"]["tool_calls"] for n in graph_view.collect(self.d)["state"]["nodes"]}
        self.assertEqual(calls, {"T1": 7, "T2": 5, "T3": 5})
        with open(wp, "w") as f:
            f.write("{oops")
        calls = {n["id"]: n["usage"]["tool_calls"] for n in graph_view.collect(self.d)["state"]["nodes"]}
        self.assertEqual(calls, {"T1": 0, "T2": 0, "T3": 0})

    def test_invalid_jsonl_skipped(self):
        self.put("state_v03.json")
        self.write("findings.jsonl", ["{non json", json.dumps(
            {"id": "F009", "severity": "low", "kind": "bug", "file": "f", "what": "w",
             "status": "open", "placement": ""}), "[1,2]"])
        self.write("watchdog.jsonl", ["garbage"])
        data = graph_view.collect(self.d)
        self.assertEqual([f["id"] for f in data["findings"]], ["F009"])
        self.assertEqual(data["watchdog"], [])

    def test_missing_state(self):
        with self.assertRaises(ValueError):
            graph_view.collect(self.d)

    def test_demo_renders(self):
        if not os.path.isdir(os.path.join(DEMO, ".sjck")):
            self.skipTest("demo assente")
        d = os.path.join(self.d, "demo")
        shutil.copytree(DEMO, d)
        data = graph_view.collect(d)
        self.assertIsNotNone(data["tokens"])
        self.assertTrue(data["findings"])

    def test_cli_and_hook(self):
        self.put("state_v03.json")
        r = subprocess.run([sys.executable, SCRIPT, "--cwd", self.d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), os.path.join(self.d, ".sjck", "view.html"))
        os.remove(os.path.join(self.d, ".sjck", "view.html"))
        r = subprocess.run([sys.executable, SCRIPT, "--hook"], capture_output=True, text=True,
                           input=json.dumps({"tool_input": {"file_path": os.path.join(self.d, "x.py")}}))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertFalse(os.path.exists(os.path.join(self.d, ".sjck", "view.html")))
        r = subprocess.run([sys.executable, SCRIPT, "--hook"], capture_output=True, text=True,
                           input=json.dumps({"tool_input": {"file_path": os.path.join(self.d, ".sjck", "state.json")}}))
        self.assertEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(self.d, ".sjck", "view.html")))


if __name__ == "__main__":
    unittest.main()
