import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "watchdog.py")
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import watchdog  # noqa: E402
USAGE = ("tool_calls", "reads_outside_card", "writes_outside_card",
         "watchdog_warnings", "watchdog_stops")

CARD = """# T1 — prova

## Obiettivo
Fare la cosa giusta nel modo giusto.

## Puoi modificare
- `src/a.py`
- `pkg/`

## Leggi
- `docs/x.md`

## Criteri di accettazione
- ok

## Fuori scope
- niente

## Correzioni richieste
"""


def node(nid, status="running", **kw):
    n = {"id": nid, "title": nid, "status=": 0}
    n.pop("status=")
    n.update({"status": status, "agent_id": "A-" + nid, "attempts": 0})
    n.update(kw)
    return n


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, ".graph", "cards"))
        os.makedirs(os.path.join(self.d, "src"))
        self.write_state([node("T1")])
        with open(os.path.join(self.d, ".graph", "cards", "T1.md"), "w") as f:
            f.write(CARD)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def write_state(self, nodes):
        with open(os.path.join(self.d, ".graph", "state.json"), "w") as f:
            json.dump({"goal": "g", "status": "running", "nodes": nodes}, f)

    def state(self):
        with open(os.path.join(self.d, ".graph", "state.json")) as f:
            return json.load(f)

    def usage(self, i=0):
        nid = self.state()["nodes"][i]["id"]
        with open(os.path.join(self.d, ".graph", "watchdog_state.json")) as f:
            return watchdog.usage_map(json.load(f), [nid])[nid]

    def events(self):
        p = os.path.join(self.d, ".graph", "watchdog.jsonl")
        if not os.path.exists(p):
            return []
        with open(p) as f:
            return [json.loads(x) for x in f if x.strip()]

    def run_hook(self, mode, tool, ti, aid="A-T1", extra=None, cwd=None):
        inp = {"cwd": cwd or self.d, "tool_name": tool, "tool_input": ti,
               "hook_event_name": "PreToolUse" if mode == "pre" else "PostToolUse"}
        if aid:
            inp["agent_id"] = aid
        inp.update(extra or {})
        return self.raw(mode, json.dumps(inp))

    def raw(self, mode, text):
        env = dict(os.environ)
        env.pop("GRAPH_KIT_ROOT", None)
        r = subprocess.run([sys.executable, SCRIPT, mode], input=text,
                           capture_output=True, text=True, cwd=self.d, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def pre(self, tool, ti, **kw):
        return self.run_hook("pre", tool, ti, **kw)

    def post(self, tool, ti, **kw):
        return self.run_hook("post", tool, ti, **kw)

    def bash(self, cmd):
        return self.pre("Bash", {"command": cmd})

    @staticmethod
    def decision(out):
        return (out or {}).get("hookSpecificOutput", {}).get("permissionDecision")

    @staticmethod
    def context(out):
        return (out or {}).get("hookSpecificOutput", {}).get("additionalContext")

    def check_contract(self):
        u = self.usage()
        for k in USAGE:
            self.assertIsInstance(u[k], int)
        for e in self.events():
            self.assertTrue(
                {"ts", "node", "tool", "kind", "level", "action", "detail"} <= set(e))
            self.assertIn(e["kind"], ("loop", "drift_write", "drift_read", "budget"))
            self.assertIn(e["level"], (1, 2))
            self.assertIn(e["action"], ("warn", "block", "count"))
            self.assertLessEqual(len(e["detail"]), 200)

    def p(self, rel):
        return os.path.join(self.d, rel)


class TestWatchdog(Base):
    def test_loop_cmd(self):
        self.assertIsNone(self.bash("make   test"))
        self.assertIsNone(self.bash(" make test "))
        out = self.bash("make test")
        ctx = self.context(out)
        self.assertIn("Fare la cosa giusta", ctx)
        self.assertIn("se non riguarda l'obiettivo, annotalo in findings e prosegui", ctx)
        self.assertEqual(self.usage()["watchdog_warnings"], 1)
        self.assertEqual(self.usage()["tool_calls"], 3)
        ev = self.events()
        self.assertEqual((ev[0]["kind"], ev[0]["level"], ev[0]["action"]),
                         ("loop", 1, "warn"))
        # ripetuto dopo il richiamo -> livello 2
        for _ in range(2):
            self.assertIsNone(self.decision(self.bash("make test")))
        out = self.bash("make test")
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("blocked", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(self.usage()["watchdog_stops"], 1)
        self.check_contract()

    def test_loop_err(self):
        err = {"error": "Exit code 1\nboom   boom"}
        self.assertIsNone(self.post("Bash", {"command": "a"}, extra=err))
        self.assertIsNone(self.post("Bash", {"command": "b"}, extra=err))
        out = self.post("Bash", {"command": "c"}, extra=err)
        self.assertIn("errore", self.context(out))
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertEqual(self.usage()["watchdog_warnings"], 1)
        self.assertEqual(self.events()[0]["kind"], "loop")
        self.check_contract()

    def test_loop_err_stderr(self):
        tr = {"tool_response": {"stdout": "", "stderr": "bad thing"}}
        for _ in range(2):
            self.post("Bash", {"command": "x"}, extra=tr)
        out = self.post("Bash", {"command": "y"}, extra=tr)
        self.assertIsNotNone(self.context(out))

    def test_loop_revert(self):
        f = self.p("src/a.py")
        ti = {"file_path": f}
        with open(f, "w") as fh:
            fh.write("A")
        self.assertIsNone(self.pre("Write", ti))
        with open(f, "w") as fh:
            fh.write("B")
        self.assertIsNone(self.post("Write", ti))
        with open(f, "w") as fh:
            fh.write("A")
        out = self.post("Write", ti)
        self.assertIn("riportato", self.context(out))
        self.assertEqual(self.events()[0]["kind"], "loop")
        self.check_contract()

    def test_drift_write(self):
        out = self.pre("Write", {"file_path": self.p("other.py")})
        self.assertEqual(self.decision(out), "deny")
        self.assertEqual(self.usage()["writes_outside_card"], 1)
        ev = self.events()
        self.assertEqual((ev[0]["kind"], ev[0]["action"]), ("drift_write", "block"))
        for rel in ("src/a.py", "pkg/sub/m.py"):
            self.assertIsNone(self.pre("Edit", {"file_path": self.p(rel)}))
        self.assertEqual(self.usage()["writes_outside_card"], 1)
        self.check_contract()

    def test_drift_write_relative_and_glob(self):
        with open(self.p(".graph/cards/T1.md"), "w") as f:
            f.write(CARD.replace("- `pkg/`", "- `lib/*.py`"))
        self.assertIsNone(self.pre("Write", {"file_path": "lib/x.py"}))
        out = self.pre("Write", {"file_path": self.p("lib/sub/x.txt")})
        self.assertEqual(self.decision(out), "deny")

    def test_drift_read(self):
        self.assertIsNone(self.pre("Read", {"file_path": self.p("docs/x.md")}))
        self.assertIsNone(self.pre("Read", {"file_path": self.p("src/a.py")}))
        self.assertEqual(self.usage()["reads_outside_card"], 0)
        out = self.pre("Read", {"file_path": self.p("secret.txt")})
        self.assertIsNone(out)
        self.assertEqual(self.usage()["reads_outside_card"], 1)
        ev = self.events()
        self.assertEqual((ev[0]["kind"], ev[0]["action"]), ("drift_read", "count"))
        self.check_contract()

    def test_budget(self):
        n = node("T1", budget={"tool_calls": 4, "context_tokens": 2000})
        self.write_state([n])
        for _ in range(4):
            self.assertIsNone(self.pre("Read", {"file_path": self.p("src/a.py")}))
        out = self.pre("Read", {"file_path": self.p("src/a.py")})  # 5 > 4
        self.assertIn("budget", self.context(out))
        self.assertEqual(self.usage()["watchdog_warnings"], 1)
        # 6 e 7: oltre budget ma sotto il 125%? 4*1.25=5 -> la 6 supera
        out = self.pre("Read", {"file_path": self.p("src/a.py")})
        self.assertEqual(self.decision(out), "deny")
        self.assertEqual(self.usage()["watchdog_stops"], 1)
        ev = self.events()
        self.assertEqual([(e["kind"], e["level"]) for e in ev],
                         [("budget", 1), ("budget", 2)])
        self.check_contract()

    def test_level2(self):
        self.write_state([node("T1", budget={"tool_calls": 1, "context_tokens": 2000})])
        for _ in range(3):
            self.pre("Read", {"file_path": self.p("src/a.py")})
        self.assertEqual(self.usage()["watchdog_stops"], 1)
        deny = lambda t, ti: self.decision(self.pre(t, ti)) == "deny"
        self.assertTrue(deny("Bash", {"command": "ls"}))
        self.assertTrue(deny("Write", {"file_path": self.p("src/a.py")}))
        self.assertTrue(deny("Read", {"file_path": self.p("src/a.py")}))
        out = self.pre("Bash", {"command": "ls"})
        self.assertIn("blocked", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertFalse(deny("Write", {"file_path": self.p(".graph/out/T1.json")}))
        self.assertFalse(deny("Edit", {"file_path": self.p(".graph/findings.jsonl")}))
        self.assertTrue(deny("Write", {"file_path": self.p(".graph/out/T2.json")}))
        self.assertFalse(deny("Read", {"file_path": self.p(".graph/cards/T1.md")}))
        self.assertFalse(deny("Grep", {"pattern": "x", "path": self.p(".graph")}))
        self.assertFalse(deny("Bash", {"command": "python3 findings.py add --from T1"}))
        self.assertEqual(self.usage()["watchdog_stops"], 1)  # solo alla transizione
        self.check_contract()

    def test_graph_dir(self):
        for _ in range(5):
            self.assertIsNone(self.pre("Write", {"file_path": self.p(".graph/out/T1.json")}))
            self.assertIsNone(self.post("Write", {"file_path": self.p(".graph/out/T1.json")}))
        self.assertIsNone(self.pre("Write", {"file_path": ".graph/findings.jsonl"}))
        self.assertIsNone(self.pre("Read", {"file_path": self.p(".graph/state.json")}))
        self.assertEqual(self.events(), [])
        u = self.usage()
        self.assertEqual((u["writes_outside_card"], u["reads_outside_card"],
                          u["watchdog_warnings"]), (0, 0, 0))

    def test_attribution(self):
        # agent_id assente: thread principale, nessuna azione
        self.assertIsNone(self.pre("Write", {"file_path": self.p("zz.py")}, aid=None))
        self.assertNotIn("usage", self.state()["nodes"][0])
        # agent_id sconosciuto, unico nodo running gia' registrato: nessuna azione
        self.assertIsNone(self.pre("Write", {"file_path": self.p("zz.py")}, aid="other"))
        self.assertNotIn("usage", self.state()["nodes"][0])
        # nodo senza agent_id: lo prende l'unico nodo libero
        self.write_state([node("T1", agent_id="")])
        out = self.pre("Write", {"file_path": self.p("zz.py")}, aid="other")
        self.assertEqual(self.decision(out), "deny")
        # due nodi running: si sceglie per agent_id
        with open(self.p(".graph/cards/T2.md"), "w") as f:
            f.write(CARD.replace("`src/a.py`", "`src/b.py`"))
        self.write_state([node("T1"), node("T2")])
        self.assertIsNone(self.pre("Write", {"file_path": self.p("src/b.py")}, aid="A-T2"))
        self.assertEqual(self.decision(
            self.pre("Write", {"file_path": self.p("src/b.py")}, aid="A-T1")), "deny")
        # piu' nodi liberi non distinguibili: unione, nessun livello 2
        self.write_state([node("T1", agent_id=""), node("T2", agent_id="")])
        self.assertIsNone(self.pre("Write", {"file_path": self.p("src/b.py")}, aid="zz"))
        self.assertEqual(self.decision(
            self.pre("Write", {"file_path": self.p("q.py")}, aid="zz")), "deny")

    def two_cards(self):
        with open(self.p(".graph/cards/T2.md"), "w") as f:
            f.write(CARD.replace("`src/a.py`", "`src/b.py`"))

    def wd_state(self):
        with open(self.p(".graph/watchdog_state.json")) as f:
            return json.load(f)

    def test_ignored_agent_types(self):
        for at in ("graph-kit:validator", "critic", "graph-kit:reviewer", "planner"):
            ex = {"agent_type": at}
            self.assertIsNone(self.pre("Write", {"file_path": self.p("zz.py")},
                                       aid="V", extra=ex))
        self.assertFalse(os.path.exists(self.p(".graph/watchdog_state.json")))
        for _ in range(60):
            out = self.pre("Read", {"file_path": self.p("src/a.py")}, aid="V",
                           extra={"agent_type": "graph-kit:validator"})
            self.assertNotEqual(self.decision(out), "deny")
        self.assertNotIn("usage", self.state()["nodes"][0])
        self.assertFalse(os.path.exists(self.p(".graph/watchdog_state.json")))
        self.pre("Read", {"file_path": self.p("src/a.py")})
        self.assertEqual(self.usage()["tool_calls"], 1)
        self.assertEqual(list(self.wd_state()), ["T1"])

    def test_parallel_registered_and_new(self):
        self.two_cards()
        self.write_state([node("T04"), node("T05", agent_id="")])
        with open(self.p(".graph/cards/T04.md"), "w") as f:
            f.write(CARD)
        with open(self.p(".graph/cards/T05.md"), "w") as f:
            f.write(CARD.replace("`src/a.py`", "`src/b.py`"))
        for _ in range(5):
            self.pre("Read", {"file_path": self.p("src/a.py")}, aid="A-T04")
        out = self.pre("Write", {"file_path": self.p("src/a.py")}, aid="A-T05")
        self.assertEqual(self.decision(out), "deny")
        self.assertEqual(self.usage(0)["tool_calls"], 5)
        self.assertEqual(self.usage(1)["tool_calls"], 1)

    def test_unknown_agent_all_registered(self):
        self.two_cards()
        self.write_state([node("T1"), node("T2")])
        self.assertIsNone(self.pre("Write", {"file_path": self.p("zz.py")}, aid="zz"))
        self.assertFalse(os.path.exists(self.p(".graph/watchdog_state.json")))

    def test_common_bucket_keeps_own_usage(self):
        self.two_cards()
        self.write_state([node("T1", agent_id="")])
        for _ in range(3):
            self.pre("Read", {"file_path": self.p("src/a.py")}, aid="X")
        self.write_state([node("T1", agent_id="", usage=self.usage()),
                          node("T2", agent_id="")])
        out = self.pre("Read", {"file_path": self.p("src/a.py")}, aid="X")
        self.assertIsNone(out)
        self.assertEqual(self.usage(0)["tool_calls"], 3)
        self.assertEqual(self.usage(1)["tool_calls"], 1)
        self.assertFalse(self.wd_state()["_common"]["l2"])

    def test_edit_test_cycle_no_escalation(self):
        f = self.p("src/a.py")
        ti = {"file_path": f}
        with open(f, "w") as fh:
            fh.write("v0")
        cmd = {"command": "python3 -m unittest discover -s tests"}
        tr = {"tool_response": {"stdout": "", "stderr": "FAILED (failures=1)"}}
        for i in range(1, 7):
            self.assertIsNone(self.pre("Edit", ti))
            with open(f, "w") as fh:
                fh.write("v%d" % i)
            self.assertIsNone(self.post("Edit", ti))
            self.assertIsNone(self.pre("Bash", cmd))
            self.assertIsNone(self.post("Bash", cmd, extra=tr))
        self.assertEqual(self.usage()["watchdog_warnings"], 0)
        self.assertEqual(self.usage()["watchdog_stops"], 0)
        self.assertEqual(self.events(), [])

    def test_relaunch_new_agent_resets(self):
        self.write_state([node("T1", agent_id="A1",
                               budget={"tool_calls": 1, "context_tokens": 2000})])
        for _ in range(3):
            self.pre("Read", {"file_path": self.p("src/a.py")}, aid="A1")
        self.assertEqual(self.usage()["watchdog_stops"], 1)
        self.write_state([node("T1", agent_id="",
                               budget={"tool_calls": 1, "context_tokens": 2000})])
        out = self.pre("Read", {"file_path": self.p("src/a.py")}, aid="A2")
        self.assertNotEqual(self.decision(out), "deny")
        self.write_state([node("T1", agent_id="A2",
                               budget={"tool_calls": 1, "context_tokens": 2000})])
        self.pre("Read", {"file_path": self.p("src/a.py")}, aid="A2")
        self.assertGreater(self.usage()["tool_calls"], 1)

    def test_no_state(self):
        os.remove(self.p(".graph/state.json"))
        self.assertIsNone(self.pre("Write", {"file_path": self.p("x.py")}))
        self.assertEqual(sorted(os.listdir(self.p(".graph"))), ["cards"])

    def test_no_running(self):
        self.write_state([node("T1", status="pending"), node("T2", status="done")])
        self.assertIsNone(self.pre("Write", {"file_path": self.p("x.py")}))
        self.assertEqual(sorted(os.listdir(self.p(".graph"))), ["cards", "state.json"])

    def test_bad_stdin(self):
        for text in ("non json", "", "[1,2]", "null"):
            self.assertIsNone(self.raw("pre", text))
            self.assertIsNone(self.raw("post", text))
        self.assertIsNone(self.raw("bogus", "{}"))
        self.assertEqual(sorted(os.listdir(self.p(".graph"))), ["cards", "state.json"])
        self.assertIsNone(self.raw("pre", json.dumps({"cwd": self.d, "tool_name": 3,
                                                       "tool_input": "x", "agent_id": "A-T1"})))

    def test_hooks_never_write_state(self):
        sp = self.p(".graph/state.json")
        with open(sp) as f:
            before = f.read()
        m0 = os.stat(sp).st_mtime_ns
        self.pre("Read", {"file_path": self.p("zz.py")})
        for _ in range(3):
            self.bash("echo x")           # warn livello 1
        self.assertEqual(self.decision(
            self.pre("Write", {"file_path": self.p("zz.py")})), "deny")  # drift_write
        for _ in range(3):
            self.bash("echo x")           # livello 2
        self.assertTrue(self.wd_state()["T1"]["l2"])
        self.post("Bash", {"command": "echo x"})
        with open(sp) as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(os.stat(sp).st_mtime_ns, m0)

    def run_usage(self, d=None):
        return subprocess.run([sys.executable, SCRIPT, "usage", "--cwd", d or self.d],
                              capture_output=True, text=True)

    def test_usage_cli(self):
        self.two_cards()
        self.write_state([node("T1"), node("T2", agent_id="A-T2")])
        for _ in range(2):
            self.pre("Read", {"file_path": self.p("src/a.py")}, aid="A-T1")
        for _ in range(3):
            self.pre("Read", {"file_path": self.p("src/b.py")}, aid="A-T2")
        wd = self.wd_state()
        com = {"sig": "T1,T2", "usage": {k: 4 for k in USAGE}}
        wd["_common"] = com
        with open(self.p(".graph/watchdog_state.json"), "w") as f:
            json.dump(wd, f)
        st = self.state()
        st["metrics"] = {"other": 9, "tool_calls": 0}
        st["log"] = ["x"]
        with open(self.p(".graph/state.json"), "w") as f:
            json.dump(st, f)
        r = self.run_usage()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(json.loads(r.stdout)), ["T1", "T2"])
        s = self.state()
        self.assertEqual(s["nodes"][0]["usage"]["tool_calls"], 2)
        self.assertEqual(s["nodes"][1]["usage"]["tool_calls"], 3)
        self.assertEqual(s["metrics"]["tool_calls"], 5)
        self.assertEqual(s["metrics"]["other"], 9)
        self.assertEqual(s["goal"], "g")
        self.assertEqual(s["log"], ["x"])
        # senza entry propria di T2 vale _common
        del wd["T2"]
        with open(self.p(".graph/watchdog_state.json"), "w") as f:
            json.dump(wd, f)
        self.assertEqual(self.run_usage().returncode, 0)
        s = self.state()
        self.assertEqual(s["nodes"][1]["usage"]["tool_calls"], 4)
        self.assertEqual(s["metrics"]["tool_calls"], 6)
        self.assertEqual(s["metrics"]["watchdog_warnings"], 4)
        os.remove(self.p(".graph/state.json"))
        self.assertEqual(self.run_usage().returncode, 2)

    def test_timing(self):
        self.write_state([node("T%d" % i, status="running" if i == 1 else "pending")
                          for i in range(1, 11)])
        self.pre("Read", {"file_path": self.p("src/a.py")})  # riscaldamento
        times = []
        for i in range(6):
            for mode in ("pre", "post"):
                t0 = time.perf_counter()
                self.run_hook(mode, "Bash", {"command": "echo %d" % i})
                times.append(time.perf_counter() - t0)
        self.assertGreaterEqual(len(times), 10)
        self.assertLess(max(times), 0.1, times)


if __name__ == "__main__":
    unittest.main()
