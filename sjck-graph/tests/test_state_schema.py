import copy
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import cards  # noqa: E402
import state_schema as s  # noqa: E402


def fx(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return json.load(f)


CARD = """# T01 — Titolo
## Obiettivo
Fai X.
## Puoi modificare
- `a/b.py` (nuovo)
- c/d.py, note
## Leggi
* `docs/x.md` — sezione 2
## Criteri di accettazione (comandi)
- [ ] `pytest` -> exit 0
1. diff pulito
## Fuori scope
- non toccare Y
## Correzioni richieste
"""


class StateTests(unittest.TestCase):
    def test_v02_valid(self):
        self.assertEqual(s.validate(fx("state_v02.json")), [])

    def test_v03_valid(self):
        self.assertEqual(s.validate(fx("state_v03.json")), [])

    def test_bad_model(self):
        st = fx("state_v03.json")
        st["nodes"][0]["model"] = "gpt"
        e = s.validate(st)
        self.assertTrue(any(x.startswith("nodes[0].model: atteso uno tra") for x in e), e)

    def test_budget_string(self):
        st = fx("state_v03.json")
        st["nodes"][0]["budget"]["tool_calls"] = "40"
        self.assertTrue(any("nodes[0].budget.tool_calls" in x for x in s.validate(st)))

    def test_negative_metric(self):
        st = fx("state_v03.json")
        st["metrics"]["findings"] = -1
        self.assertTrue(any("metrics.findings" in x for x in s.validate(st)))

    def test_bad_critic_verdict(self):
        st = fx("state_v03.json")
        st["critic"][0]["verdict"] = "maybe"
        self.assertTrue(any("critic[0].verdict" in x for x in s.validate(st)))

    def test_missing_dep(self):
        st = fx("state_v02.json")
        st["nodes"][1]["deps"] = ["T99"]
        self.assertTrue(any("deps[0]" in x for x in s.validate(st)))

    def test_duplicate_id(self):
        st = fx("state_v02.json")
        st["nodes"][1]["id"] = "T01"
        self.assertTrue(any("duplicato" in x for x in s.validate(st)))

    def test_duration_float_ok_and_unknown_keys(self):
        st = fx("state_v03.json")
        st["extra"] = 1
        self.assertEqual(s.validate(st), [])

    def test_normalize(self):
        st = fx("state_v02.json")
        orig = copy.deepcopy(st)
        n = s.normalize(st)
        self.assertEqual(st, orig)
        nd = n["nodes"][0]
        self.assertEqual(nd["model"], "inherit")
        self.assertEqual(nd["effort"], "medium")
        self.assertEqual(nd["budget"], {"tool_calls": 40, "context_tokens": 2000})
        self.assertEqual(nd["assumptions"], [])
        self.assertEqual(set(nd["usage"]), set(s.NODE_DEFAULTS["usage"]))
        self.assertEqual(n["critic"], [])
        self.assertTrue(set(s.METRIC_KEYS) <= set(n["metrics"]))
        self.assertNotIn("plan_score", n)
        self.assertEqual(s.validate(n), [])

    def test_save_load_roundtrip(self):
        st = fx("state_v03.json")
        with tempfile.TemporaryDirectory() as d:
            s.save_state(d, st)
            self.assertEqual(s.load_state(d), st)
            with open(os.path.join(d, ".sjck", "state.json"), encoding="utf-8") as f:
                self.assertTrue(f.read().endswith("}\n"))

    def test_load_broken(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(s.load_state(d))
            os.makedirs(os.path.join(d, ".sjck"))
            with open(os.path.join(d, ".sjck", "state.json"), "w") as f:
                f.write("{rotto")
            self.assertIsNone(s.load_state(d))

    def test_find_graph_root(self):
        old = os.environ.pop("SJCK_ROOT", None)
        try:
            with tempfile.TemporaryDirectory() as d:
                d = os.path.realpath(d)
                s.save_state(d, {"goal": "g", "nodes": []})
                sub = os.path.join(d, "a", "b")
                os.makedirs(sub)
                self.assertEqual(s.find_graph_root(sub), d)
                os.environ["SJCK_ROOT"] = "/x/y"
                self.assertEqual(s.find_graph_root(sub), "/x/y")
        finally:
            os.environ.pop("SJCK_ROOT", None)
            if old is not None:
                os.environ["SJCK_ROOT"] = old


class CardTests(unittest.TestCase):
    def test_parse_card(self):
        p = cards.parse_card(CARD)
        self.assertEqual(list(p), list(cards.SECTIONS))
        self.assertEqual(p["Obiettivo"], "Fai X.")

    def test_section_paths(self):
        self.assertEqual(cards.section_paths(CARD, "Puoi modificare"), ["a/b.py", "c/d.py"])
        self.assertEqual(cards.section_paths(CARD, "Leggi"), ["docs/x.md"])
        self.assertEqual(cards.section_items(CARD, "Inesistente"), [])

    def test_count_criteria(self):
        self.assertEqual(cards.count_criteria(CARD), 2)


if __name__ == "__main__":
    unittest.main()
