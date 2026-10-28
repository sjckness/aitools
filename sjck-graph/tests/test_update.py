import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "update.py")
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import update  # noqa: E402


@unittest.skipIf(os.name == "nt", "fake executables are shell scripts")
class UpdateTest(unittest.TestCase):
    """update.py con `claude` e `code` finti nel PATH e la release finta."""

    def setUp(self):
        self.bin = tempfile.mkdtemp(prefix="sjck-bin-")
        self.log = os.path.join(self.bin, "calls.log")
        self._fake("claude", 'echo "claude $*" >> "%s"' % self.log)
        self._fake("code", 'echo "code $*" >> "%s"\n'
                           'case "$1" in --list-extensions) echo "sjckness.sjck@0.1.4";; esac' % self.log)
        self.env = dict(os.environ, PATH=self.bin + os.pathsep + "/usr/bin:/bin")
        self.orig = (update.latest_release, update.update_vscode)
        update.latest_release = lambda: {"tag": "vscode-v0.1.5", "url": "u", "published": "2026-10-28",
                                         "assets": ["sjck.vsix", "sjck-console.tgz", "sjck-0.1.5.vsix"], "vscode": "0.1.5"}
        self.vsix = []
        update.update_vscode = lambda ed: (self.vsix.append(ed), (True, ""))[1]
        self.old_path = os.environ["PATH"]
        os.environ["PATH"] = self.env["PATH"]

    def tearDown(self):
        update.latest_release, update.update_vscode = self.orig
        os.environ["PATH"] = self.old_path
        shutil.rmtree(self.bin, ignore_errors=True)

    def _fake(self, name, body):
        p = os.path.join(self.bin, name)
        with open(p, "w") as f:
            f.write("#!/bin/sh\n" + body + "\nexit 0\n")
        os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)

    def _calls(self):
        try:
            return open(self.log).read().splitlines()
        except OSError:
            return []

    def test_check_changes_nothing(self):
        st = update.status()
        self.assertEqual((st["vscode"]["installed"], st["vscode"]["latest"], st["vscode"]["behind"]), ("0.1.4", "0.1.5", True))
        self.assertEqual(update.main(["--check"]), 0)
        self.assertEqual(self.vsix, [])
        self.assertFalse([c for c in self._calls() if "plugin" in c or "--install-extension" in c])

    def test_update_plugins_and_extension(self):
        self.assertEqual(update.main(["--only", "plugins", "--only", "vscode"]), 0)
        calls = self._calls()
        self.assertIn("claude plugin marketplace update sjck", calls)
        self.assertIn("claude plugin update sjck-graph@sjck", calls)
        self.assertIn("claude plugin update sjck-onboard@sjck", calls)
        self.assertEqual(self.vsix, ["code"])

    def test_extension_up_to_date_is_skipped(self):
        update.latest_release = lambda: {"tag": "t", "url": "u", "published": "", "assets": ["sjck-0.1.4.vsix"], "vscode": "0.1.4"}
        update.main(["--only", "vscode"])
        self.assertEqual(self.vsix, [])

    def test_versions(self):
        self.assertLess(update.vtuple("0.1.4"), update.vtuple("0.1.10"))
        self.assertIsNone(update.vtuple("x"))

    def test_cli_runs(self):
        r = subprocess.run([sys.executable, SCRIPT, "--help-unknown", "--check"], capture_output=True, text=True,
                           env=dict(self.env, SJCK_REPO="sjckness/does-not-exist-xyz"), timeout=60)
        # Senza rete o con repo inesistente: messaggio chiaro, nessun traceback.
        self.assertNotIn("Traceback", r.stderr)
