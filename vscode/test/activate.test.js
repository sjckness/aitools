'use strict';
// Activates the extension against a minimal fake `vscode` module: checks wiring, not looks.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const Module = require('node:module');
const { test } = require('node:test');

const DEMO = path.join(__dirname, '..', '..', 'examples', 'demo');
const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'sjck-vscode-'));
fs.cpSync(path.join(DEMO, '.sjck'), path.join(ws, '.sjck'), { recursive: true });
fs.mkdirSync(path.join(ws, '.sjck', 'out'), { recursive: true });
fs.writeFileSync(path.join(ws, '.sjck', 'out', 'T01.json'), JSON.stringify({ id: 'T01', changed: ['sjck-graph/scripts/plan_score.py'] }));

const rec = { commands: {}, trees: {}, decoProvider: null, status: null, panels: [], context: {}, messages: [] };
class Emitter { constructor() { this.l = []; this.event = (f) => this.l.push(f); } fire(v) { this.l.forEach((f) => f(v)); } }
class TreeItem { constructor(label, state) { this.label = label; this.collapsibleState = state; } }
const vscode = {
  EventEmitter: Emitter, TreeItem, TreeItemCollapsibleState: { None: 0, Collapsed: 1, Expanded: 2 },
  ThemeIcon: class { constructor(id, color) { this.id = id; this.color = color; } },
  ThemeColor: class { constructor(id) { this.id = id; } },
  FileDecoration: class { constructor(badge, tooltip, color) { Object.assign(this, { badge, tooltip, color }); } },
  Range: class { constructor(...a) { this.a = a; } },
  RelativePattern: class { constructor(b, p) { this.base = b; this.pattern = p; } },
  StatusBarAlignment: { Left: 1 }, ViewColumn: { Active: -1 },
  Uri: { file: (p) => ({ scheme: 'file', fsPath: p }) },
  workspace: {
    workspaceFolders: [{ uri: { fsPath: ws } }],
    getConfiguration: () => ({ get: (k) => ({ decorations: true, notifications: true, revealOnPlan: true, 'plan.interactive': true, 'claude.path': 'claude', 'claude.runArgs': [] }[k]) }),
    createFileSystemWatcher: () => ({ onDidChange() {}, onDidCreate() {}, onDidDelete() {}, dispose() {} }),
    onDidChangeConfiguration: () => ({ dispose() {} }),
  },
  window: {
    createOutputChannel: () => ({ appendLine() {}, clear() {}, show() {}, dispose() {} }),
    createStatusBarItem: () => (rec.status = { show() {}, dispose() {} }),
    createTreeView: (id, o) => (rec.trees[id] = { provider: o.treeDataProvider, dispose() {} }),
    registerFileDecorationProvider: (p) => { rec.decoProvider = p; return { dispose() {} }; },
    registerWebviewViewProvider: () => ({ dispose() {} }),
    createTerminal: (o) => { rec.terminal = o; return { show() {}, dispose() {} }; },
    showInputBox: async () => 'make a pacman minigame',
    showQuickPick: async (items) => items[3],
    createWebviewPanel: () => {
      const p = { webview: { html: '', cspSource: 'vscode-resource:', onDidReceiveMessage() {} }, onDidDispose() {}, reveal() {} };
      rec.panels.push(p);
      return p;
    },
    showInformationMessage: async (m) => { rec.messages.push(m); },
    showWarningMessage: async (m) => { rec.messages.push(m); },
    showErrorMessage: async (m) => { rec.messages.push(m); },
    setStatusBarMessage: (m) => rec.messages.push(m),
  },
  commands: {
    registerCommand: (id, fn) => { rec.commands[id] = fn; return { dispose() {} }; },
    executeCommand: async () => {},
  },
  extensions: { getExtension: () => null },
};
const origResolve = Module._resolveFilename;
Module._resolveFilename = function (req, ...rest) {
  return req === 'vscode' ? 'vscode' : origResolve.call(this, req, ...rest);
};
require.cache.vscode = { id: 'vscode', filename: 'vscode', loaded: true, exports: vscode };

test('activate wires views, status bar, decorations, viewer and inbox actions', async () => {
  const ext = require('../extension');
  const context = { subscriptions: [] };
  await ext.activate(context);

  for (const c of ['sjck.plan', 'sjck.run', 'sjck.stop', 'sjck.openViewer', 'sjck.nodeDiff', 'sjck.findingAccept', 'sjck.crApply', 'sjck.approvePlan']) {
    assert.equal(typeof rec.commands[c], 'function', c);
  }
  const pkg = require('../package.json');
  for (const c of pkg.contributes.commands) assert.ok(rec.commands[c.command], `${c.command} declared but not registered`);

  assert.match(rec.status.text, /sjck 4\/9/);
  const graph = rec.trees['sjck.graph'].provider;
  const top = graph.getChildren();
  assert.equal(top[0].label, 'Implement docs/specs/v0.3.md');
  assert.equal(top.length, 1 + 4, 'goal + 4 levels');
  const level1 = graph.getChildren(top[2]);
  assert.ok(level1.some((n) => n.contextValue === 'node.running' && n.nodeId === 'T02'));

  const inbox = rec.trees['sjck.inbox'].provider.getChildren();
  const f = inbox.find((i) => i.contextValue === 'finding');
  assert.ok(f, 'a finding waiting for a decision');
  rec.commands['sjck.findingDefer'](f);
  const dec = fs.readdirSync(path.join(ws, '.sjck', 'decisions'));
  assert.equal(dec.length, 1);
  assert.equal(JSON.parse(fs.readFileSync(path.join(ws, '.sjck', 'decisions', dec[0]), 'utf8')).action, 'defer');

  const d = rec.decoProvider.provideFileDecoration(vscode.Uri.file(path.join(ws, 'sjck-graph', 'scripts', 'plan_score.py')));
  assert.equal(d.badge, '✓');
  assert.equal(rec.decoProvider.provideFileDecoration(vscode.Uri.file('/elsewhere/x.py')), undefined);

  rec.commands['sjck.openViewer']();
  const html = rec.panels[0].webview.html;
  assert.ok(!html.includes('__DATA__'));
  assert.match(html, /Content-Security-Policy/);
  const scripts = html.match(/<script[^>]*>/g);
  assert.ok(scripts.length >= 3 && scripts.every((s) => /nonce="/.test(s)), 'every script carries the nonce');

  await rec.commands['sjck.plan']();
  assert.equal(rec.terminal.cwd, ws, 'planner chat runs in the workspace');
  const argv = rec.terminal.shellArgs;
  assert.equal(argv[argv.length - 1], '/sjck-plan make a pacman minigame --mode L', 'interactive /sjck-plan, prompt as one argument');

  ext.deactivate();
  fs.rmSync(ws, { recursive: true, force: true });
});
