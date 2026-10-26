// sjck for VS Code: native views over a project's .sjck/ folder.
// Reads the same files as the console and the plugin; writes only what the console writes
// (decision files, change requests through the chat agent, its own logs).
'use strict';
const vscode = require('vscode');
const path = require('path');
const crypto = require('crypto');
const core = require('./src/core');
const model = require('./src/model');

let mods = null;          // shared modules (data, inbox, runner, chat)
let root = null;          // workspace folder with the run
let data = null;          // collect(root)
let inbox = null;
let changed = {};
let runner = null;
let chat = null;
let output = null;
let refreshTimer = null;
let loaded = false;      // first refresh done: later ones may announce a first plan

function workspaceRoot() {
  const folders = vscode.workspace.workspaceFolders || [];
  const withRun = folders.find((f) => require('fs').existsSync(path.join(f.uri.fsPath, '.sjck', 'state.json')));
  return (withRun || folders[0] || {}).uri ? (withRun || folders[0]).uri.fsPath : null;
}

function project() {
  return { id: 'vscode', path: root, name: path.basename(root || '') };
}

function claudeConfig() {
  const c = vscode.workspace.getConfiguration('sjck');
  const bin = c.get('claude.path') || 'claude';
  return { bin: process.platform === 'win32' && bin === 'claude' ? 'claude.cmd' : bin, args: c.get('claude.runArgs') || [] };
}

// ------------------------------------------------------------------ trees
class GraphProvider {
  constructor() { this._e = new vscode.EventEmitter(); this.onDidChangeTreeData = this._e.event; }
  refresh() { this._e.fire(undefined); }
  getTreeItem(el) { return el; }
  getChildren(el) {
    if (!data) return [];
    if (!el) {
      const s = data.state;
      const head = new vscode.TreeItem(s.goal || 'sjck run', vscode.TreeItemCollapsibleState.None);
      head.description = [s.status, s.mode && 'mode ' + s.mode].filter(Boolean).join(' · ');
      head.tooltip = s.mode_reason || '';
      head.iconPath = themeIcon(s.status === 'done' ? 'validated' : s.status);
      head.command = { command: 'sjck.openViewer', title: 'Open Run Viewer' };
      return [head, ...model.levels(data.state.nodes).map((nodes, i) => {
        const t = new vscode.TreeItem(`Level ${i}`, vscode.TreeItemCollapsibleState.Expanded);
        t.description = `${nodes.filter((n) => n.status === 'validated').length}/${nodes.length}`;
        t.contextValue = 'level';
        return Object.assign(t, { nodes });
      })];
    }
    return (el.nodes || []).map((n) => {
      const t = new vscode.TreeItem(`${n.id}  ${n.title || ''}`, vscode.TreeItemCollapsibleState.None);
      t.description = model.nodeDescription(n, data);
      t.tooltip = model.nodeTooltip(n);
      t.iconPath = themeIcon(n.status);
      t.contextValue = `node.${n.status}`;
      const item = Object.assign(t, { nodeId: n.id });
      item.command = { command: 'sjck.openCard', title: 'Open card', arguments: [item] };
      return item;
    });
  }
}

function themeIcon(status) {
  const [id, color] = model.icon(status);
  return new vscode.ThemeIcon(id, new vscode.ThemeColor(color));
}

class InboxProvider {
  constructor() { this._e = new vscode.EventEmitter(); this.onDidChangeTreeData = this._e.event; }
  refresh() { this._e.fire(undefined); }
  getTreeItem(el) { return el; }
  getChildren() {
    if (!data || !inbox) return [];
    const items = [];
    if (data.state.status === 'planned') {
      const t = new vscode.TreeItem('Plan ready for review');
      t.description = data.state.goal || '';
      t.iconPath = themeIcon('planned');
      t.contextValue = 'plan';
      items.push(t);
    }
    for (const c of inbox.crs.slice().reverse()) {
      const t = new vscode.TreeItem(`${c.id}  ${c.summary || ''}`);
      t.description = c.decided ? `decided: ${c.decided}` : `${c.status} · ${c.priority}`;
      t.tooltip = [c.summary, `ops: ${c.ops.join(', ')}`, c.resolution].filter(Boolean).join('\n');
      t.iconPath = new vscode.ThemeIcon(c.status === 'applied' ? 'pass' : c.status === 'rejected' ? 'circle-slash' : 'git-pull-request-draft');
      t.contextValue = c.status === 'proposed' && !c.decided ? 'cr.proposed' : 'cr';
      items.push(Object.assign(t, { itemId: c.id }));
    }
    for (const f of inbox.findings) {
      const t = new vscode.TreeItem(`${f.id}  ${f.what || ''}`);
      t.description = f.decided ? `decided: ${f.decided}` : `${f.severity || ''} · from ${f.from || '?'}`;
      t.tooltip = [f.what, f.file, f.suggested_fix && 'fix: ' + f.suggested_fix].filter(Boolean).join('\n');
      t.iconPath = new vscode.ThemeIcon(f.severity === 'high' ? 'error' : f.severity === 'med' ? 'warning' : 'info');
      t.contextValue = f.decided ? 'finding.decided' : 'finding';
      if (f.file) {
        const [file, line] = String(f.file).split(':');
        const uri = vscode.Uri.file(path.join(root, file));
        t.command = { command: 'vscode.open', title: 'Open', arguments: [uri, line ? { selection: new vscode.Range(+line - 1, 0, +line - 1, 0) } : undefined] };
      }
      items.push(Object.assign(t, { itemId: f.id }));
    }
    return items;
  }
}

// ------------------------------------------------------------------ decorations
class Decorations {
  constructor() { this._e = new vscode.EventEmitter(); this.onDidChangeFileDecorations = this._e.event; this.map = new Map(); }
  update() {
    this.map = vscode.workspace.getConfiguration('sjck').get('decorations') ? model.decorations(data, changed) : new Map();
    this._e.fire(undefined);
  }
  provideFileDecoration(uri) {
    if (!root || uri.scheme !== 'file' || !uri.fsPath.startsWith(root)) return undefined;
    const d = model.decorationFor(this.map, path.relative(root, uri.fsPath));
    return d ? new vscode.FileDecoration(d.badge, d.tooltip, new vscode.ThemeColor(d.color)) : undefined;
  }
}

// ------------------------------------------------------------------ webviews
function nonce() { return crypto.randomBytes(16).toString('base64'); }

let viewerPanel = null;
let viewerTab = 'graph';
function viewerHtml(webview) {
  const n = nonce();
  const csp = `default-src 'none'; img-src ${webview.cspSource} data:; style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; script-src 'nonce-${n}';`;
  const payload = mods.data.embed({ ...data, updated: new Date().toTimeString().slice(0, 8), refresh: 0 });
  return core.viewerTemplate()
    .replace('__DATA__', payload)
    .replace('<script id="data"', `<script>history.replaceState(null,'','#${viewerTab}')</script><script id="data"`)
    .replace('</body>', "<script>(function(){var api=acquireVsCodeApi();document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('[data-tab]');if(b)api.postMessage({tab:b.getAttribute('data-tab')})});})();</script></body>")
    .replace(/<script(?=[ >])/g, `<script nonce="${n}"`)
    .replace('<head>', `<head><meta http-equiv="Content-Security-Policy" content="${csp}">`);
}

function openViewer() {
  if (!data) return vscode.window.showInformationMessage('sjck: no run in this workspace yet.');
  if (viewerPanel) return viewerPanel.reveal();
  viewerPanel = vscode.window.createWebviewPanel('sjck.viewer', 'sjck Run Viewer', vscode.ViewColumn.Active, { enableScripts: true, retainContextWhenHidden: false });
  viewerPanel.webview.html = viewerHtml(viewerPanel.webview);
  viewerPanel.webview.onDidReceiveMessage((m) => { if (m && /^(graph|tokens|findings)$/.test(m.tab)) viewerTab = m.tab; });
  viewerPanel.onDidDispose(() => { viewerPanel = null; });
}

class ChatView {
  resolveWebviewView(view) {
    this.view = view;
    view.webview.options = { enableScripts: true };
    const n = nonce();
    view.webview.html = `<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${n}';">
<style>
body{padding:8px;font:var(--vscode-font-size) var(--vscode-font-family);color:var(--vscode-foreground);display:flex;flex-direction:column;height:100vh;box-sizing:border-box;margin:0}
#msgs{flex:1;overflow:auto;display:flex;flex-direction:column;gap:8px;padding-bottom:8px}
.m{padding:8px 10px;border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.45}
.user{align-self:flex-end;background:var(--vscode-button-background);color:var(--vscode-button-foreground);max-width:90%}
.assistant{background:var(--vscode-editorWidget-background);border:1px solid var(--vscode-widget-border,transparent)}
.tool{font-family:var(--vscode-editor-font-family);font-size:11px;opacity:.75;padding:0 4px}
.err{color:var(--vscode-errorForeground)}
.hint{opacity:.7;margin:auto;text-align:center;padding:16px}
form{display:flex;gap:6px}textarea{flex:1;resize:vertical;min-height:52px;background:var(--vscode-input-background);color:var(--vscode-input-foreground);border:1px solid var(--vscode-input-border,transparent);border-radius:4px;padding:6px;font:inherit}
button{background:var(--vscode-button-background);color:var(--vscode-button-foreground);border:0;border-radius:4px;padding:6px 12px;cursor:pointer}button:disabled{opacity:.5}
</style></head><body>
<div id="msgs" role="log" aria-live="polite"></div>
<form id="f"><label for="t" style="position:absolute;left:-9999px">Message</label><textarea id="t" placeholder="Ask the planner to add, edit or re-run work… (Ctrl+Enter)"></textarea><button id="b" type="submit">Send</button></form>
<script nonce="${n}">
const api=acquireVsCodeApi(),box=document.getElementById('msgs'),t=document.getElementById('t'),b=document.getElementById('b');
function add(m,live){const d=document.createElement('div');d.className='m '+(m.role||'assistant')+(m.error?' err':'');if(live)d.dataset.live='1';d.textContent=m.text;box.appendChild(d);box.scrollTop=box.scrollHeight}
window.addEventListener('message',e=>{const m=e.data;
 if(m.type==='history'){box.innerHTML='';if(!m.messages.length)box.innerHTML='<div class="hint">The planner knows the current run. Agreed changes become change requests the orchestrator applies live.</div>';m.messages.forEach(x=>add(x));b.disabled=m.busy}
 else if(m.type==='message'){const h=box.querySelector('.hint');if(h)h.remove();add(m.message)}
 else if(m.type==='delta'){add(m.kind==='tool'?{role:'tool',text:m.text}:{role:'assistant',text:m.text},true)}
 else if(m.type==='done'){box.querySelectorAll('[data-live]').forEach(x=>x.remove());add(m.message);b.disabled=false}
 else if(m.type==='error'){add({role:'assistant',text:m.text,error:true});b.disabled=false}});
document.getElementById('f').onsubmit=e=>{e.preventDefault();const v=t.value.trim();if(!v)return;b.disabled=true;api.postMessage({type:'send',text:v});t.value=''};
t.onkeydown=e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();document.getElementById('f').requestSubmit()}};
api.postMessage({type:'ready'});
</script></body></html>`;
    view.webview.onDidReceiveMessage((m) => {
      if (!root) return;
      if (m.type === 'ready') this.history();
      if (m.type === 'send') {
        try {
          chat.send(project(), m.text, { ...claudeConfig(), chat: {} });
        } catch (e) {
          view.webview.postMessage({ type: 'error', text: e.message });
        }
      }
    });
  }
  history() {
    if (this.view && root) this.view.webview.postMessage({ type: 'history', ...chat.load(project()), busy: chat.busy.has('vscode') });
  }
  post(msg) { if (this.view) this.view.webview.postMessage(msg); }
}

// ------------------------------------------------------------------ activate
async function activate(context) {
  output = vscode.window.createOutputChannel('sjck');
  root = workspaceRoot();
  try {
    mods = await core.load();
  } catch (e) {
    vscode.window.showErrorMessage(`sjck: ${e.message}`);
    return;
  }
  runner = new mods.runner.Runner();
  chat = new mods.chat.Chat();

  const graph = new GraphProvider();
  const inboxView = new InboxProvider();
  const decos = new Decorations();
  const chatView = new ChatView();
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  status.command = 'workbench.view.extension.sjck';
  status.name = 'sjck';

  const graphTree = vscode.window.createTreeView('sjck.graph', { treeDataProvider: graph, showCollapseAll: true });
  const inboxTree = vscode.window.createTreeView('sjck.inbox', { treeDataProvider: inboxView });
  context.subscriptions.push(output, status, graphTree, inboxTree,
    vscode.window.registerFileDecorationProvider(decos),
    vscode.window.registerWebviewViewProvider('sjck.chat', chatView, { webviewOptions: { retainContextWhenHidden: true } }));

  function refresh() {
    if (!root) return;
    const prev = data || (loaded ? model.EMPTY : null);
    loaded = true;
    data = mods.data.collect(root);
    inbox = data ? mods.inbox.inbox(root, data.findings) : null;
    changed = data ? core.changedByNode(root, data.state.nodes) : {};
    graph.refresh();
    inboxView.refresh();
    decos.update();
    const run = runner.info('vscode');
    vscode.commands.executeCommand('setContext', 'sjck.running', Boolean(run && run.running));
    status.text = model.statusText(data, inbox, run);
    status.tooltip = data ? `${data.state.goal || ''}\nClick to open the sjck views` : 'sjck: no run yet';
    status.show();
    const w = model.waitingCount(inbox);
    inboxTree.badge = w ? { value: w, tooltip: `${w} waiting for you` } : undefined;
    if (viewerPanel && data) viewerPanel.webview.html = viewerHtml(viewerPanel.webview);
    if (vscode.workspace.getConfiguration('sjck').get('notifications')) {
      for (const n of model.changes(prev, data)) {
        if (n.action === 'plan' && vscode.workspace.getConfiguration('sjck').get('revealOnPlan')) {
          vscode.commands.executeCommand('workbench.view.extension.sjck');
        }
        const show = n.level === 'error' ? vscode.window.showErrorMessage : n.level === 'warn' ? vscode.window.showWarningMessage : vscode.window.showInformationMessage;
        const actions = n.action === 'plan' ? ['Review', 'Approve and run'] : ['Open'];
        show(n.text, ...actions).then((a) => {
          if (a === 'Approve and run') vscode.commands.executeCommand('sjck.approvePlan');
          else if (a) openViewer();
        });
      }
    }
  }
  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refresh, 250);
  }

  if (root) {
    const w = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(root, '.sjck/**'));
    w.onDidChange(scheduleRefresh); w.onDidCreate(scheduleRefresh); w.onDidDelete(scheduleRefresh);
    context.subscriptions.push(w);
  }
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((e) => { if (e.affectsConfiguration('sjck')) refresh(); }));

  runner.on('log', (_pid, line) => output.appendLine(line));
  runner.on('end', (_pid, info) => {
    refresh();
    const ok = info.exitCode === 0;
    (ok ? vscode.window.showInformationMessage : vscode.window.showErrorMessage)(`sjck: ${info.kind} ${ok ? 'finished' : 'exited ' + info.exitCode}`, 'Show log')
      .then((a) => { if (a) output.show(true); });
  });
  chat.on('message', (_p, m) => chatView.post({ type: 'message', message: m }));
  chat.on('delta', (_p, d) => chatView.post({ type: 'delta', ...d }));
  chat.on('done', (_p, m) => { chatView.post({ type: 'done', message: m }); scheduleRefresh(); });

  // Planning is a conversation: run `claude "/sjck-plan …"` interactively in a terminal.
  // When the plan is approved it writes .sjck/state.json and the watcher takes over.
  async function planInTerminal() {
    if (!root) return vscode.window.showWarningMessage('sjck: open a folder first.');
    const task = await vscode.window.showInputBox({
      title: 'sjck: plan a task', prompt: 'What should the graph do? The planner will ask you the rest.',
      placeHolder: 'Add load/start/abort services to mission_manager_node', ignoreFocusOut: true,
    });
    if (!task || !task.trim()) return;
    const pick = await vscode.window.showQuickPick([
      { label: 'auto', description: 'let the planner propose' }, { label: 'S', description: 'inline' },
      { label: 'M', description: 'short chain' }, { label: 'L', description: 'parallel DAG' }], { title: 'Mode', ignoreFocusOut: true });
    if (!pick) return;
    const prompt = ['/sjck-plan', task.trim().replace(/\s+/g, ' '), pick.label === 'auto' ? '' : `--mode ${pick.label}`].filter(Boolean).join(' ');
    const { bin } = claudeConfig();
    const win = process.platform === 'win32';
    const term = vscode.window.createTerminal({
      name: 'sjck plan', cwd: root, iconPath: new vscode.ThemeIcon('lightbulb'),
      shellPath: win ? (process.env.ComSpec || 'cmd.exe') : bin,
      shellArgs: win ? ['/d', '/c', bin, prompt] : [prompt],
    });
    context.subscriptions.push(term);
    term.show();
  }

  async function start(kind, preset, presetMode) {
    if (!root) return vscode.window.showWarningMessage('sjck: open a folder first.');
    let task = preset;
    if (task === undefined) {
      task = await vscode.window.showInputBox({
        title: kind === 'plan' ? 'sjck: plan a task' : 'sjck: run',
        prompt: kind === 'plan' ? 'What should the graph do?' : 'Task to run (leave empty to run the approved plan)',
        placeHolder: 'Add load/start/abort services to mission_manager_node',
        ignoreFocusOut: true,
      });
      if (task === undefined) return;
    }
    if (kind === 'plan' && !task.trim()) return vscode.window.showWarningMessage('sjck: write a task to plan.');
    if (presetMode !== undefined) return launch(kind, task, presetMode);
    const pick = await vscode.window.showQuickPick([
      { label: 'auto', description: 'let the kit choose' }, { label: 'S', description: 'inline' },
      { label: 'M', description: 'short chain' }, { label: 'L', description: 'parallel DAG' }], { title: 'Mode', ignoreFocusOut: true });
    if (!pick) return;
    return launch(kind, task, pick.label === 'auto' ? '' : pick.label);
  }

  function launch(kind, task, mode) {
    try {
      output.clear();
      output.show(true);
      runner.start(project(), { task, kind, mode }, claudeConfig());
      refresh();
    } catch (e) {
      vscode.window.showErrorMessage(`sjck: ${e.message}`);
    }
  }

  function decide(kind, action) {
    return (item) => {
      if (!item || !item.itemId) return;
      try {
        mods.inbox.writeDecision(root, { kind, id: item.itemId, action });
        vscode.window.setStatusBarMessage(`sjck: ${action} ${item.itemId} — the orchestrator applies it at its next step`, 4000);
        refresh();
      } catch (e) {
        vscode.window.showErrorMessage(`sjck: ${e.message}`);
      }
    };
  }

  const reg = (id, fn) => context.subscriptions.push(vscode.commands.registerCommand(id, fn));
  reg('sjck.plan', () => (vscode.workspace.getConfiguration('sjck').get('plan.interactive') === false ? start('plan') : planInTerminal()));
  reg('sjck.run', () => start('run'));
  // The approved plan already carries its mode: no second question.
  reg('sjck.approvePlan', () => start('run', '', (data && data.state.mode) || ''));
  reg('sjck.stop', () => { runner.stop('vscode'); });
  reg('sjck.refresh', refresh);
  reg('sjck.openViewer', openViewer);
  reg('sjck.showLog', () => output.show(true));
  reg('sjck.change', () => vscode.commands.executeCommand('sjck.chat.focus'));
  reg('sjck.chatReset', () => {
    try { chat.reset(project()); chatView.history(); } catch (e) { vscode.window.showErrorMessage(`sjck: ${e.message}`); }
  });
  reg('sjck.openCard', async (item) => {
    if (!item || !item.nodeId) return;
    try {
      await vscode.window.showTextDocument(vscode.Uri.file(core.cardPath(root, item.nodeId)), { preview: true });
    } catch {
      vscode.window.showWarningMessage(`sjck: no card for ${item.nodeId} yet.`);
    }
  });
  reg('sjck.nodeDiff', async (item) => {
    if (!item || !item.nodeId) return;
    const files = changed[item.nodeId] || [];
    if (!files.length) return vscode.window.showInformationMessage(`sjck: ${item.nodeId} did not report changed files.`);
    const file = files.length === 1 ? files[0] : await vscode.window.showQuickPick(files, { title: `Files changed by ${item.nodeId}` });
    if (!file) return;
    const uri = vscode.Uri.file(path.join(root, file));
    const gitExt = vscode.extensions.getExtension('vscode.git');
    try {
      const git = (gitExt.isActive ? gitExt.exports : await gitExt.activate()).getAPI(1);
      await vscode.commands.executeCommand('vscode.diff', git.toGitUri(uri, 'HEAD'), uri, `${path.basename(file)} (HEAD ↔ ${item.nodeId})`);
    } catch {
      await vscode.window.showTextDocument(uri);
    }
  });
  reg('sjck.findingAccept', decide('finding', 'accept'));
  reg('sjck.findingDefer', decide('finding', 'defer'));
  reg('sjck.findingReject', decide('finding', 'reject'));
  reg('sjck.crApply', decide('cr', 'apply'));
  reg('sjck.crReject', decide('cr', 'reject'));

  refresh();
}

function deactivate() {
  clearTimeout(refreshTimer);
  if (runner) runner.stop('vscode');
}

module.exports = { activate, deactivate };
