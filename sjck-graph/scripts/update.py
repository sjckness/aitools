#!/usr/bin/env python3
"""Aggiorna sjck all'ultima release su GitHub: plugin, estensione VS Code, console.

  update.py --check   mostra installato vs ultima release, non cambia niente
  update.py           aggiorna quello che è installato ed è indietro
  update.py --json    come --check, in JSON (per lo slash command)

Opzioni: --only plugins|vscode|console (ripetibile), --editor code|cursor|codium.
Env: SJCK_REPO (default sjckness/sjckAI-tools).

Da dove arriva cosa:
  - plugin (sjck-graph, sjck-onboard): dal marketplace `sjck`, che segue il
    repo; si attivano al prossimo avvio di Claude Code;
  - estensione: asset `sjck.vsix` della release, installata col CLI dell'editor;
  - console: asset `sjck-console.tgz` della release, con npm; solo se c'è già.
Solo librerie standard; nessun dato inviato oltre alle richieste di download.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

REPO = os.environ.get("SJCK_REPO", "sjckness/sjckAI-tools")
MARKETPLACE = "sjck"
PLUGINS = ("sjck-graph", "sjck-onboard")
EXT_ID = "sjckness.sjck"
EDITORS = ("code", "cursor", "codium")
HERE = os.path.dirname(os.path.abspath(__file__))


def asset_url(name):
    return "https://github.com/%s/releases/latest/download/%s" % (REPO, name)


def run(cmd, timeout=180):
    """Esegue un comando risolvendo i .cmd di Windows; mai un'eccezione."""
    exe = shutil.which(cmd[0])
    if not exe:
        return False, "%s not found" % cmd[0]
    try:
        r = subprocess.run([exe] + cmd[1:], capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e:  # timeout, permessi...
        return False, str(e)


def vtuple(v):
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", str(v or ""))
    return tuple(int(x or 0) for x in m.groups()) if m else None


def latest_release():
    req = urllib.request.Request("https://api.github.com/repos/%s/releases/latest" % REPO,
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "sjck-update"})
    with urllib.request.urlopen(req, timeout=15) as r:
        rel = json.load(r)
    assets = [a.get("name", "") for a in rel.get("assets") or []]
    ext = None
    for a in assets:  # sjck-0.1.5.vsix -> 0.1.5
        m = re.fullmatch(r"sjck-(\d+\.\d+\.\d+)\.vsix", a)
        if m:
            ext = m.group(1)
    if not ext:  # tag vscode-v0.1.5
        m = re.search(r"vscode-v(\d+\.\d+\.\d+)", rel.get("tag_name") or "")
        ext = m.group(1) if m else None
    return {"tag": rel.get("tag_name"), "url": rel.get("html_url"), "published": rel.get("published_at"),
            "assets": assets, "vscode": ext}


def plugin_version():
    try:
        with open(os.path.join(HERE, "..", ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            return json.load(f).get("version")
    except Exception:
        return None


def editor_with_ext(prefer=None):
    """(editor, versione installata o None) del primo editor col CLI disponibile."""
    order = [prefer] if prefer else []
    order += [e for e in EDITORS if e != prefer]
    first = None
    for e in order:
        if not shutil.which(e):
            continue
        ok, out = run([e, "--list-extensions", "--show-versions"], timeout=60)
        if not ok:
            continue
        first = first or e
        for line in out.splitlines():
            if line.lower().startswith(EXT_ID + "@"):
                return e, line.split("@", 1)[1].strip()
    return first, None


def console_version():
    if not shutil.which("sjck"):
        return None
    ok, out = run(["npm", "ls", "-g", "sjck", "--depth=0", "--json"], timeout=60)
    try:
        return json.loads(out)["dependencies"]["sjck"]["version"]
    except Exception:
        return "installed"


def status(prefer_editor=None):
    rel = latest_release()
    editor, ext = editor_with_ext(prefer_editor)
    return {
        "release": rel,
        "plugin": {"installed": plugin_version()},
        "vscode": {"editor": editor, "installed": ext, "latest": rel["vscode"],
                   "behind": bool(ext and rel["vscode"] and vtuple(ext) < vtuple(rel["vscode"]))},
        "console": {"installed": console_version(), "available": "sjck-console.tgz" in rel["assets"]},
    }


def update_plugins():
    run(["claude", "plugin", "marketplace", "update", MARKETPLACE])
    res = []
    for p in PLUGINS:
        ok, out = run(["claude", "plugin", "update", "%s@%s" % (p, MARKETPLACE)])
        if not ok and re.search(r"not installed|not found", out, re.I):
            continue  # plugin non installato: non lo installiamo di nascosto
        res.append((p, ok or bool(re.search(r"already|up to date|latest", out, re.I)), out.splitlines()[-1:] or [""]))
    return res


def update_vscode(editor):
    tmp = tempfile.mkdtemp(prefix="sjck-")
    path = os.path.join(tmp, "sjck.vsix")
    try:
        req = urllib.request.Request(asset_url("sjck.vsix"), headers={"User-Agent": "sjck-update"})
        with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
            shutil.copyfileobj(r, f)
        return run([editor, "--install-extension", path, "--force"])
    except Exception as e:
        return False, str(e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def update_console():
    return run(["npm", "i", "-g", asset_url("sjck-console.tgz")], timeout=300)


def main(argv):
    only = [argv[i + 1] for i, a in enumerate(argv) if a == "--only" and i + 1 < len(argv)] or ["plugins", "vscode", "console"]
    editor = argv[argv.index("--editor") + 1] if "--editor" in argv and argv.index("--editor") + 1 < len(argv) else None
    try:
        st = status(editor)
    except Exception as e:
        print("sjck-update: can't reach GitHub (%s). Nothing changed." % e)
        return 1
    if "--json" in argv:
        print(json.dumps(st, indent=1))
        return 0
    rel, vs, co = st["release"], st["vscode"], st["console"]
    print("latest release: %s (%s)\n  %s" % (rel["tag"], (rel["published"] or "")[:10], rel["url"]))
    print("  plugin sjck-graph  installed %s (follows the repo)" % (st["plugin"]["installed"] or "?"))
    print("  VS Code extension  %s -> %s%s" % (vs["installed"] or "not installed", vs["latest"] or "?",
          "" if vs["editor"] else "  (no code/cursor/codium CLI)"))
    print("  console            %s" % (co["installed"] or "not installed"))
    if "--check" in argv:
        return 0

    restart = reload = False
    if "plugins" in only:
        print("\n-> plugins")
        for p, ok, last in update_plugins():
            print("  %s %s %s" % ("ok" if ok else "FAIL", p, "" if ok else last[0]))
            restart = restart or ok
    if "vscode" in only:
        if not vs["editor"]:
            print("\n-> VS Code extension: skipped (no editor CLI on PATH)")
        elif vs["installed"] and not vs["behind"]:
            print("\n-> VS Code extension: already %s" % vs["installed"])
        else:
            ok, out = update_vscode(vs["editor"])
            print("\n-> VS Code extension (%s): %s" % (vs["editor"], "ok" if ok else "FAIL " + (out.splitlines()[-1:] or [""])[0]))
            reload = ok
    if "console" in only:
        if not co["installed"]:
            print("\n-> console: not installed, skipped (install: see README)")
        elif not co["available"]:
            print("\n-> console: no package in this release, skipped")
        else:
            ok, out = update_console()
            print("\n-> console: %s" % ("ok" if ok else "FAIL " + (out.splitlines()[-1:] or [""])[0]))
    print()
    if restart:
        print("Restart Claude Code to load the updated plugins.")
    if reload:
        print("Reload the VS Code window (Developer: Reload Window).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
