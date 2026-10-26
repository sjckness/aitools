import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import tokens  # noqa: E402


def line(mid, model, inp, out, cr=0, cc=0, ts="2026-10-26T21:00:00Z", text="secret"):
    return json.dumps({
        "type": "assistant", "timestamp": ts, "requestId": "req-" + mid,
        "message": {"id": mid, "role": "assistant", "model": model,
                    "content": [{"type": "text", "text": text}],
                    "usage": {"input_tokens": inp, "output_tokens": out,
                              "cache_read_input_tokens": cr, "cache_creation_input_tokens": cc}},
    })


class TokensTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sjck-tokens-")
        os.makedirs(os.path.join(self.root, ".sjck"))
        self.state = {"goal": "g", "status": "running", "nodes": [
            {"id": "T01", "status": "running", "agent_id": "agent-a"},
            {"id": "T02", "status": "running", "agent_id": ""},
            {"id": "T03", "status": "pending", "agent_id": ""}]}
        self._write_state()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write_state(self):
        with open(os.path.join(self.root, ".sjck", "state.json"), "w") as f:
            json.dump(self.state, f)

    def _transcript(self, name, lines):
        p = os.path.join(self.root, name)
        with open(p, "w") as f:
            f.write("\n".join(lines) + "\n")
        return p

    def test_streaming_lines_count_once_and_garbage_is_ignored(self):
        p = self._transcript("main.jsonl", [
            json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}),
            line("m1", "claude-opus", 10, 1, 100, 5),
            line("m1", "claude-opus", 10, 20, 100, 5),  # same message, final usage
            "{not json",
            line("m2", "claude-sonnet", 3, 7, 50, 0),
            line("m3", "<synthetic>", 999, 999),
        ])
        r = tokens.parse_transcript(p)
        self.assertEqual(r["turns"], 3)
        self.assertEqual((r["input"], r["output"], r["cache_read"], r["cache_creation"]), (13, 27, 150, 5))
        self.assertEqual(r["total"], 195)
        self.assertEqual(r["models"]["claude-opus"]["total"], 135)
        self.assertIsNone(tokens.parse_transcript(os.path.join(self.root, "missing.jsonl")))

    def test_agent_mapping(self):
        self.assertEqual(tokens.node_for_agent(self.state, "agent-a"), "T01")
        self.assertEqual(tokens.node_for_agent(self.state, "agent-new"), "T02", "only running node without agent_id")
        self.state["nodes"][2]["status"] = "running"
        self.assertEqual(tokens.node_for_agent(self.state, "agent-x"), "unattributed")

    def test_hooks_build_tokens_json_without_message_text(self):
        main = self._transcript("main.jsonl", [line("o1", "claude-opus", 5, 5, 40, 10)])
        sub = self._transcript("agent-a.jsonl", [line("s1", "claude-sonnet", 2, 8, 20, 0), line("s2", "claude-sonnet", 1, 4, 30, 0)])
        tokens.from_hook({"hook_event_name": "SubagentStop", "cwd": self.root, "agent_id": "agent-a",
                          "agent_transcript_path": sub, "transcript_path": main})
        data = tokens.from_hook({"hook_event_name": "Stop", "cwd": self.root, "transcript_path": main})
        self.assertEqual(data["by_node"]["T01"]["total"], 65)
        self.assertEqual(data["by_node"]["T01"]["agents"], 1)
        self.assertEqual(data["by_node"]["ORCH"]["total"], 60)
        self.assertEqual(data["totals"]["total"], 125)
        self.assertEqual(data["by_node"]["T01"]["types"]["cache_read"], 50)
        with open(os.path.join(self.root, ".sjck", "tokens.json")) as f:
            raw = f.read()
        self.assertNotIn("secret", raw)
        # Idempotent: a second Stop on the same transcript does not double count.
        again = tokens.from_hook({"hook_event_name": "Stop", "cwd": self.root, "transcript_path": main})
        self.assertEqual(again["totals"]["total"], 125)

    def test_planning_session_is_labelled_plan(self):
        self.state["status"] = "planned"
        self._write_state()
        main = self._transcript("plan.jsonl", [line("p1", "claude-opus", 1, 2, 3, 4)])
        data = tokens.from_hook({"hook_event_name": "Stop", "cwd": self.root, "transcript_path": main})
        self.assertEqual(list(data["by_node"]), ["PLAN"])

    def test_no_run_no_file(self):
        empty = tempfile.mkdtemp()
        try:
            self.assertIsNone(tokens.from_hook({"hook_event_name": "Stop", "cwd": empty, "transcript_path": "x"}))
            self.assertFalse(os.path.exists(os.path.join(empty, ".sjck")))
        finally:
            shutil.rmtree(empty)

    def test_cli_recompute(self):
        p = self._transcript("manual.jsonl", [line("x", "claude-haiku", 1, 1)])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(tokens.main(["--cwd", self.root, "--add", p, "T03"]), 0)
        self.assertIn("2 total", buf.getvalue())


def tool_use(mid, tid, name, inp):
    return json.dumps({"type": "assistant", "message": {"id": mid, "role": "assistant", "model": "claude-sonnet",
                       "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}})


def tool_result(tid, chars):
    return json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": "x" * chars}]}})


class CategoriesTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sjck-cats-")
        os.makedirs(os.path.join(self.root, ".sjck"))
        self.state = {"goal": "g", "status": "running", "nodes": [
            {"id": "T01", "status": "validated", "agent_id": "a1", "files": ["src/game/"], "attempts": 1}]}
        with open(os.path.join(self.root, ".sjck", "state.json"), "w") as f:
            json.dump(self.state, f)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _sub(self):
        lines = [
            json.dumps({"type": "user", "message": {"role": "user", "content": "do T01"}}),
            tool_use("a", "t1", "Read", {"file_path": os.path.join(self.root, ".sjck/cards/T01.md")}),
            line("a", "claude-sonnet", 10, 5, 0, 1000),
            tool_result("t1", 4000),        # card ~1000
            tool_use("b", "t2", "Read", {"file_path": "./src/game/ghost.js"}),
            line("b", "claude-sonnet", 10, 5, 1000, 2000),
            tool_result("t2", 40000),       # in card ~10000
            tool_use("c", "t3", "Read", {"file_path": "src/util/math.js"}),
            line("c", "claude-sonnet", 10, 5, 3000, 10000),
            tool_result("t3", 80000),       # outside ~20000
            tool_use("d", "t4", "Bash", {"command": "npm test"}),
            line("d", "claude-sonnet", 10, 5, 13000, 20000),
            tool_result("t4", 8000),        # tool output ~2000
            line("e", "claude-sonnet", 10, 5, 33000, 2000),
        ]
        p = os.path.join(self.root, "a1.jsonl")
        with open(p, "w") as f:
            f.write("\n".join(lines) + "\n")
        return p

    def test_categories_add_up_and_classify_reads(self):
        r = tokens.parse_transcript(self._sub(), ["src/game/"], self.root)
        cats = r["categories"]
        real_in = r["input"] + r["cache_read"] + r["cache_creation"]
        self.assertAlmostEqual(sum(cats.values()), real_in, delta=len(cats))
        self.assertGreater(cats["file_read_outside_card"], cats["file_read_in_card"])
        self.assertGreater(cats["file_read_in_card"], cats["card"])
        self.assertIn("tool_output", cats)
        self.assertIn("system", cats)
        self.assertEqual(r["heavy"][0]["category"], "file_read_outside_card")
        self.assertEqual(r["heavy"][0]["file"], "src/util/math.js")

    def test_compaction_resets_context(self):
        p = self._sub()
        with open(p, "a") as f:
            f.write(json.dumps({"type": "user", "isCompactSummary": True, "message": {"role": "user", "content": "summary"}}) + "\n")
            f.write(line("z", "claude-sonnet", 100, 5, 0, 0) + "\n")
        before = tokens.parse_transcript(self._sub(), ["src/game/"], self.root)["categories"]
        after = tokens.parse_transcript(p, ["src/game/"], self.root)["categories"]
        self.assertEqual(after["file_read_outside_card"], before["file_read_outside_card"], "post-compaction turn adds no reads")

    def test_report_insights(self):
        tokens.from_hook({"hook_event_name": "SubagentStop", "cwd": self.root, "agent_id": "a1", "agent_transcript_path": self._sub()})
        with open(os.path.join(self.root, ".sjck", "token-report.json")) as f:
            rep = json.load(f)
        kinds = {i["kind"] for i in rep["insights"]}
        self.assertIn("card", kinds, "outside-card reads flagged")
        self.assertIn("waste", kinds, "retried attempt flagged")
        self.assertIn("heavy", kinds)
        with open(os.path.join(self.root, ".sjck", "tokens.json")) as f:
            data = json.load(f)
        self.assertTrue(data["categories_estimated"])
        self.assertIn("file_read_outside_card", data["by_node"]["T01"]["categories"])


if __name__ == "__main__":
    unittest.main()
