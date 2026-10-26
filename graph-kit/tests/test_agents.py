import os
import re
import unittest

AGENTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agents")

# Prima colonna delle righe `no` di .graph/interfaces/cc-subagents.md: nessuna riga `no`.
UNSUPPORTED = set()

EXPECTED = {
    "planner": ("opus", "high"),
    "scout": ("haiku", "low"),
    "implementer": ("sonnet", "medium"),
    "validator": ("sonnet", "high"),
    "reviewer": ("opus", "high"),
    "critic": ("fable", "high"),
}
FALLBACK = {"xhigh": "high", "max": "high"}


def parse(name):
    with open(os.path.join(AGENTS, name + ".md"), encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "frontmatter mancante in " + name
    fm = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm


def text(name):
    with open(os.path.join(AGENTS, name + ".md"), encoding="utf-8") as f:
        return f.read()


class TestAgents(unittest.TestCase):
    def test_defaults(self):
        for name, (model, effort) in EXPECTED.items():
            with self.subTest(agent=name):
                fm = parse(name)
                self.assertEqual(fm["name"], name)
                self.assertTrue(fm.get("description"))
                self.assertEqual(fm.get("model"), model)
                self.assertEqual(fm.get("effort"), effort)

    def test_unsupported_absent_or_fallback(self):
        for name in EXPECTED:
            fm = parse(name)
            for key, val in fm.items():
                self.assertNotIn(key, UNSUPPORTED, name)
                self.assertNotIn(f"{key}: {val}", UNSUPPORTED, name)
                if key == "effort":
                    self.assertNotIn(val, FALLBACK, name)

    def test_max_turns(self):
        for name in ("scout", "implementer", "validator", "critic"):
            with self.subTest(agent=name):
                self.assertTrue(re.fullmatch(r"\d+", parse(name).get("maxTurns", "")))
        self.assertGreaterEqual(int(parse("implementer")["maxTurns"]), 100)
        self.assertLessEqual(int(parse("critic")["maxTurns"]), 5)

    def test_omit_claude_md(self):
        for name in EXPECTED:
            with self.subTest(agent=name):
                expect = "true" if name in ("scout", "implementer") else None
                self.assertEqual(parse(name).get("omitClaudeMd"), expect)

    def test_critic(self):
        fm = parse("critic")
        self.assertEqual(fm["tools"], "Read, Grep")
        with open(os.path.join(AGENTS, "critic.md"), encoding="utf-8") as f:
            self.assertIn('"verdict"', f.read())

    def test_tools_unchanged(self):
        self.assertEqual(parse("planner")["tools"], "Read, Grep, Glob, Write")
        self.assertEqual(parse("scout")["tools"], "Read, Grep, Glob, Write")
        self.assertEqual(parse("implementer")["tools"], "Read, Edit, Write, Bash, Grep, Glob")
        self.assertEqual(parse("validator")["tools"], "Read, Grep, Glob, Bash")
        self.assertEqual(parse("reviewer")["tools"], "Read, Grep, Bash")

    def test_script_path_from_prompt(self):
        for name in ("implementer", "validator", "reviewer"):
            with self.subTest(agent=name):
                t = text(name)
                for s in ("script:", "<script>/findings.py",
                          "${CLAUDE_PLUGIN_ROOT}/scripts", "aitools-scripts"):
                    self.assertIn(s, t)

    def test_reviewer_from_review(self):
        t = text("reviewer")
        self.assertIn("--from REVIEW", t)
        self.assertNotIn("--from <ID>", t)

    def test_assumptions_in_outputs(self):
        for name in ("validator", "reviewer"):
            self.assertIn('"assumptions"', text(name))

    def test_planner_findings_format(self):
        self.assertIn('"kind":"bug|smell|debt|doc|loop"', text("planner"))

    def test_critic_out_of_scope(self):
        self.assertIn("fuori scope", text("critic"))

    def test_graph_view_fallback(self):
        with open(os.path.join(AGENTS, "..", "commands", "graph-view.md"),
                  encoding="utf-8") as f:
            t = f.read()
        self.assertIn("aitools-scripts/graph_view.py", t)
        self.assertIn("~/.claude/plugins/", t)


if __name__ == "__main__":
    unittest.main()
