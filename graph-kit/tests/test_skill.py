import os
import re
import unittest

SK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "graph-orchestration")


def rd(*p):
    with open(os.path.join(SK, *p), encoding="utf-8") as f:
        return f.read()


def step(text, n):
    m = re.search(r"^## Step %d\b.*?(?=^## |\Z)" % n, text, re.S | re.M)
    assert m, "Step %d mancante" % n
    return m.group(0)


class TestSkill(unittest.TestCase):
    def setUp(self):
        self.skill = rd("SKILL.md")

    def test_length(self):
        self.assertLessEqual(len(self.skill.splitlines()), 180)

    def test_step0_scripts(self):
        s = step(self.skill, 0)
        for k in ("script:", "../../scripts", "aitools-scripts", "plan_score.py"):
            self.assertIn(k, s)

    def test_plan_score_exit2(self):
        self.assertIn("Exit 2", self.skill)

    def test_agent_id_after_launch(self):
        self.assertIn("agent_id", step(self.skill, 3))

    def test_loop_end(self):
        self.assertIn("stallo", step(self.skill, 3))

    def test_usage_cli(self):
        for p in (("SKILL.md",), ("reference", "watchdog.md"), ("reference", "scripts.md")):
            self.assertIn("watchdog.py usage", rd(*p), p)

    def test_attempts(self):
        self.assertNotIn("attempts = 2", self.skill)
        self.assertTrue("attempts >= 2" in self.skill or "attempts ≥ 2" in self.skill)

    def test_findings_sources(self):
        s = step(self.skill, 3)
        self.assertIn("PLAN.json", s)
        self.assertIn("REVIEW.json", s)

    def test_rimanda(self):
        w = rd("reference", "watchdog.md")
        self.assertNotIn("resta bloccato", w)
        lines = [l for l in w.splitlines() if "rimanda" in l]
        self.assertTrue(lines)
        self.assertTrue(any("pending" in l and "deps" in l for l in lines))

    def test_added_nodes_plan_score(self):
        self.assertIn("plan_score", rd("reference", "findings.md"))

    def test_non_interactive(self):
        for p in (("SKILL.md",), ("reference", "findings.md"), ("reference", "critic.md")):
            self.assertIn("non interattiv", rd(*p), p)

    def test_findings_agents(self):
        lines = [l for l in rd("reference", "findings.md").splitlines() if "senza Bash" in l]
        self.assertTrue(lines)
        for l in lines:
            self.assertNotIn("critic", l)


if __name__ == "__main__":
    unittest.main()
