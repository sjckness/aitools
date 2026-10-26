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
sys.path.insert(0, SCRIPTS)
import graph_view  # noqa: E402


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


class ViewTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, ".graph"))
        self.addCleanup(shutil.rmtree, self.d, True)

    def put(self, fixture):
        shutil.copy(os.path.join(FIX, fixture), os.path.join(self.d, ".graph", "state.json"))

    def write(self, name, lines):
        with open(os.path.join(self.d, ".graph", name), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def html(self):
        with open(graph_view.render(self.d), encoding="utf-8") as f:
            return f.read()

    def test_v02(self):
        self.put("state_v02.json")
        h = self.html()
        self.assertEqual(h.count("nessun dato"), 4)
        for n in load("state_v02.json")["nodes"]:
            self.assertIn(n["id"], h)

    def test_v03(self):
        self.put("state_v03.json")
        st = load("state_v03.json")
        findings = [
            {"id": "F001", "severity": "high", "kind": "bug", "file": "a.py",
             "what": "x" * 200, "status": "accepted", "placement": "card:T02"},
            {"id": "F002", "severity": "low", "kind": "doc", "file": "b.py",
             "what": "<b>y</b>", "status": "deferred", "placement": "backlog"},
        ]
        events = [{"ts": "2026-10-26T10:0%d:00" % i, "node": "T02", "tool": "Read",
                   "kind": k, "level": 1, "action": "warn", "detail": "d"}
                  for i, k in enumerate(["loop", "drift_read", "budget"])]
        self.write("findings.jsonl", [json.dumps(f) for f in findings])
        self.write("watchdog.jsonl", [json.dumps(e) for e in events])
        h = self.html()
        self.assertNotIn("nessun dato", h)
        for n in st["nodes"]:
            self.assertIn(n["model"], h)
            self.assertIn(n["effort"], h)
            self.assertIn("%s/%s" % (n["usage"]["tool_calls"], n["budget"]["tool_calls"]), h)
        for f in findings:
            self.assertIn(f["id"], h)
            self.assertIn(f["status"], h)
        self.assertNotIn("x" * 100, h)
        self.assertNotIn("<b>y</b>", h)
        self.assertIn("&lt;b&gt;y", h)
        self.assertIn(events[-1]["kind"], h)
        self.assertIn(st["critic"][-1]["verdict"], h)
        self.assertIn(st["plan_score"]["verdict"], h)

    def test_usage_from_watchdog_state(self):
        z = {"tool_calls": 0, "reads_outside_card": 0, "writes_outside_card": 0,
             "watchdog_warnings": 0, "watchdog_stops": 0}
        nodes = [{"id": i, "title": i, "status": "running", "agent": "implementer",
                  "attempts": 0, "deps": [], "budget": {"tool_calls": 40},
                  "usage": dict(z)} for i in ("T1", "T2", "T3")]
        with open(os.path.join(self.d, ".graph", "state.json"), "w") as f:
            json.dump({"goal": "g", "status": "running", "nodes": nodes}, f)
        wp = os.path.join(self.d, ".graph", "watchdog_state.json")
        with open(wp, "w") as f:
            json.dump({"T1": {"sig": "0:a", "usage": dict(z, tool_calls=7)},
                       "_common": {"sig": "T2,T3", "usage": dict(z, tool_calls=5)}}, f)
        h = self.html()
        self.assertEqual(h.count("7/40"), 1)
        self.assertEqual(h.count("5/40"), 2)
        with open(wp, "w") as f:
            f.write("{oops")
        h = self.html()
        self.assertIn("0/40", h)
        self.assertNotIn("7/40", h)

    def test_invalid_jsonl_skipped(self):
        self.put("state_v03.json")
        self.write("findings.jsonl", ["{non json", json.dumps(
            {"id": "F009", "severity": "low", "kind": "bug", "file": "f", "what": "w",
             "status": "open", "placement": ""}), "[1,2]"])
        self.write("watchdog.jsonl", ["garbage"])
        h = self.html()
        self.assertIn("F009", h)

    def test_cli_and_hook(self):
        self.put("state_v03.json")
        r = subprocess.run([sys.executable, SCRIPT, "--cwd", self.d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), os.path.join(self.d, ".graph", "view.html"))
        os.remove(os.path.join(self.d, ".graph", "view.html"))
        r = subprocess.run([sys.executable, SCRIPT, "--hook"], capture_output=True, text=True,
                           input=json.dumps({"tool_input": {"file_path": os.path.join(self.d, "x.py")}}))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertFalse(os.path.exists(os.path.join(self.d, ".graph", "view.html")))


if __name__ == "__main__":
    unittest.main()
