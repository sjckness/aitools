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
      head.description = [s.status, s.mode && 'mode ' + s.mode, model.runTokens(data)].filter(Boolean).join(' · ');
      head.tooltip = [s.mode_reason, model.tokensTooltip(data)].filter(Boolean).join('\n\n');
      head.iconPath = themeIcon(s.status === 'done' ? 'validated' : s.status);
      head.command = { command: 'sjck.openDashboard', title: 'Open Mission Control' };
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

// Mission Control: a full panel fed by postMessage, so updates animate instead of reloading.
let dash = null;
let ext = null;
function dashPayload() {
  const run = runner ? runner.info('vscode') : null;
  return { type: 'data', data, inbox, changed, run: run ? { running: Boolean(run.running), kind: run.kind } : null };
}
function postDashboard() { if (dash) dash.webview.postMessage(dashPayload()); }
function openDashboard() {
  if (dash) return dash.reveal();
  const media = vscode.Uri.joinPath(ext.extensionUri, 'media');
  dash = vscode.window.createWebviewPanel('sjck.dashboard', 'sjck Mission Control', vscode.ViewColumn.Active,
    { enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [media] });
  dash.iconPath = vscode.Uri.joinPath(media, 'sjck.svg');
  const w = dash.webview;
  const n = nonce();
  const css = w.asWebviewUri(vscode.Uri.joinPath(media, 'dashboard.css'));
  const js = w.asWebviewUri(vscode.Uri.joinPath(media, 'dashboard.js'));
  w.html = `<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${w.cspSource} data:; style-src ${w.cspSource} 'unsafe-inline'; script-src 'nonce-${n}';">
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="${css}"><title>sjck Mission Control</title></head>
<body><div class="bgfx"></div><main id="app"></main><script nonce="${n}" src="${js}"></script></body></html>`;
  w.onDidReceiveMessage((m) => {
    if (!m || typeof m.type !== 'string') return;
    const id = typeof m.id === 'string' && /^[A-Za-z0-9_-]{1,32}$/.test(m.id) ? m.id : null;
    if (m.type === 'ready') postDashboard();
    else if (m.type === 'command') {
      const cmd = { plan: 'sjck.plan', run: 'sjck.run', stop: 'sjck.stop', approvePlan: 'sjck.approvePlan', chat: 'sjck.chat.focus', log: 'sjck.showLog', viewer: 'sjck.openViewer' }[m.name];
      if (cmd) vscode.commands.executeCommand(cmd);
    } else if (m.type === 'openCard' && id) vscode.commands.executeCommand('sjck.openCard', { nodeId: id });
    else if (m.type === 'nodeDiff' && id) vscode.commands.executeCommand('sjck.nodeDiff', { nodeId: id });
    else if (m.type === 'decide' && id && /^(finding|cr)$/.test(m.kind)) {
      const ok = m.kind === 'finding' ? ['accept', 'defer', 'reject'] : ['apply', 'reject'];
      if (ok.includes(m.action)) vscode.commands.executeCommand(`sjck.${m.kind === 'cr' ? 'cr' : 'finding'}${m.action[0].toUpperCase()}${m.action.slice(1)}`, { itemId: id });
    } else if (m.type === 'openFile' && root && typeof m.file === 'string') {
      const [file, line] = m.file.split(':');
      const abs = path.resolve(root, file);
      if (!abs.startsWith(root + path.sep)) return;
      vscode.window.showTextDocument(vscode.Uri.file(abs), line && +line ? { selection: new vscode.Range(+line - 1, 0, +line - 1, 0) } : {})
        .then(undefined, () => vscode.window.showWarningMessage(`sjck: cannot open ${file}`));
    }
  });
  dash.onDidDispose(() => { dash = null; });
}

class ChatView {
  resolveWebviewView(view) {
    this.view = view;
    view.webview.options = { enableScripts: true };
    const n = nonce();
    view.webview.html = `<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${n}';">
<style>
:root{--acc:#f5b544;--acc2:#ff7a59;--line:var(--vscode-widget-border,rgba(127,127,127,.18))}
body.vscode-light{--acc:#d98a00}
*{box-sizing:border-box}
body{margin:0;padding:0;font:var(--vscode-font-size) var(--vscode-font-family);color:var(--vscode-foreground);display:flex;flex-direction:column;height:100vh}
header{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,rgba(245,181,68,.10),transparent)}
.logo{width:22px;height:22px;border-radius:7px;display:grid;place-items:center;font:700 11px var(--vscode-editor-font-family);color:#1a1205;background:linear-gradient(135deg,var(--acc),var(--acc2));box-shadow:0 0 14px rgba(245,160,60,.45)}
header b{font-size:12px}header span{font-size:11px;opacity:.6;margin-left:auto}
#msgs{flex:1;overflow:auto;display:flex;flex-direction:column;gap:10px;padding:12px}
.row{display:flex;gap:8px;align-items:flex-end;animation:in .3s both}
@keyframes in{from{opacity:0;transform:translateY(6px)}}
.row.user{justify-content:flex-end}
.av{width:20px;height:20px;border-radius:50%;flex:none;display:grid;place-items:center;font:700 9px var(--vscode-editor-font-family);color:#1a1205;background:linear-gradient(135deg,var(--acc),var(--acc2))}
.m{padding:9px 12px;border-radius:14px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.5;max-width:88%}
.user .m{background:linear-gradient(135deg,var(--acc),var(--acc2));color:#1a1205;border-bottom-right-radius:4px;font-weight:500}
.assistant .m{background:var(--vscode-editorWidget-background);border:1px solid var(--line);border-bottom-left-radius:4px}
.tool{font:11px var(--vscode-editor-font-family);opacity:.7;padding:2px 10px 2px 28px;display:flex;gap:6px;align-items:center;animation:in .2s both}
.tool::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--acc);box-shadow:0 0 8px var(--acc)}
.err .m{border-color:var(--vscode-errorForeground);color:var(--vscode-errorForeground)}
.typing{display:flex;gap:4px;padding:12px 14px}.typing i{width:6px;height:6px;border-radius:50%;background:var(--acc);animation:b 1.2s infinite}.typing i:nth-child(2){animation-delay:.15s}.typing i:nth-child(3){animation-delay:.3s}
@keyframes b{0%,60%,100%{opacity:.25;transform:none}30%{opacity:1;transform:translateY(-3px)}}
.hint{margin:auto;text-align:center;padding:12px;max-width:260px}
.orb{width:46px;height:46px;border-radius:50%;margin:0 auto 12px;background:radial-gradient(circle at 35% 30%,#ffd98a,var(--acc) 45%,var(--acc2) 80%);filter:drop-shadow(0 0 16px rgba(245,160,60,.5));animation:fl 4s ease-in-out infinite}
@keyframes fl{50%{transform:translateY(-4px)}}
.hint p{opacity:.7;margin:0 0 12px;line-height:1.5}
.sugg{display:flex;flex-direction:column;gap:6px}
.sugg button{background:transparent;color:var(--vscode-foreground);border:1px solid var(--line);border-radius:10px;padding:7px 10px;text-align:left;cursor:pointer;font:inherit;font-size:12px}
.sugg button:hover{border-color:var(--acc)}
form{margin:10px;border:1px solid var(--line);border-radius:14px;background:var(--vscode-input-background);padding:6px;display:flex;flex-direction:column;gap:6px;transition:border-color .2s,box-shadow .2s}
form:focus-within{border-color:var(--acc);box-shadow:0 0 0 3px rgba(245,181,68,.15)}
textarea{border:0;outline:0;resize:none;min-height:44px;max-height:180px;background:transparent;color:var(--vscode-input-foreground);padding:4px 6px;font:inherit}
.bar{display:flex;align-items:center;justify-content:space-between;font-size:10.5px;opacity:.85}.bar span{opacity:.6;padding-left:6px}
button#b{background:linear-gradient(135deg,var(--acc),var(--acc2));color:#1a1205;border:0;border-radius:9px;padding:5px 12px;cursor:pointer;font-weight:600}
button#b:disabled{opacity:.4;cursor:default}
</style></head><body>
<header><div class="logo">sj</div><b>Planner</b><span>live run</span></header>
<div id="msgs" role="log" aria-live="polite"></div>
<form id="f"><label for="t" style="position:absolute;left:-9999px">Message</label><textarea id="t" rows="2" placeholder="Ask the planner to add, edit or re-run work…"></textarea><div class="bar"><span>Ctrl+Enter to send</span><button id="b" type="submit">Send ↑</button></div></form>
<script nonce="${n}">
const api=acquireVsCodeApi(),box=document.getElementById('msgs'),t=document.getElementById('t'),b=document.getElementById('b');
const HINT='<div class="hint"><div class="orb"></div><p>The planner knows the current run. Agreed changes become change requests the orchestrator applies live.</p><div class="sugg"><button>Why did the last node fail?</button><button>Add a node that writes tests for the new code</button><button>Re-run the slowest node with a bigger budget</button></div></div>';
function typing(on){let e=box.querySelector('.typing-row');if(on&&!e){e=document.createElement('div');e.className='row assistant typing-row';e.innerHTML='<div class="av">sj</div><div class="m typing"><i></i><i></i><i></i></div>';box.appendChild(e)}else if(!on&&e)e.remove();if(on)box.appendChild(e);box.scrollTop=box.scrollHeight}
function add(m,live){if(m.role==='tool'){const d=document.createElement('div');d.className='tool';if(live)d.dataset.live='1';d.textContent=m.text;box.appendChild(d)}else{const r=document.createElement('div');r.className='row '+(m.role||'assistant')+(m.error?' err':'');if(live)r.dataset.live='1';if(m.role!=='user'){const a=document.createElement('div');a.className='av';a.textContent='sj';r.appendChild(a)}const d=document.createElement('div');d.className='m';d.textContent=m.text;r.appendChild(d);box.appendChild(r)}const ty=box.querySelector('.typing-row');if(ty)box.appendChild(ty);box.scrollTop=box.scrollHeight}
window.addEventListener('message',e=>{const m=e.data;
 if(m.type==='history'){box.innerHTML='';if(!m.messages.length)box.innerHTML=HINT;m.messages.forEach(x=>add(x));b.disabled=m.busy;typing(m.busy)}
 else if(m.type==='message'){const h=box.querySelector('.hint');if(h)h.remove();add(m.message);if(m.message.role==='user')typing(true)}
 else if(m.type==='delta'){add(m.kind==='tool'?{role:'tool',text:m.text}:{role:'assistant',text:m.text},true)}
 else if(m.type==='done'){box.querySelectorAll('[data-live]').forEach(x=>x.remove());typing(false);add(m.message);b.disabled=false}
 else if(m.type==='error'){typing(false);add({role:'assistant',text:m.text,error:true});b.disabled=false}});
box.addEventListener('click',e=>{const s=e.target.closest('.sugg button');if(s){t.value=s.textContent;t.focus()}});
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
  ext = context;
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
  status.command = 'sjck.openDashboard';
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
    status.tooltip = data ? `${data.state.goal || ''}\nClick to open Mission Control` : 'sjck: open Mission Control';
    status.show();
    const w = model.waitingCount(inbox);
    inboxTree.badge = w ? { value: w, tooltip: `${w} waiting for you` } : undefined;
    if (viewerPanel && data) viewerPanel.webview.html = viewerHtml(viewerPanel.webview);
    postDashboard();
    if (vscode.workspace.getConfiguration('sjck').get('notifications')) {
      for (const n of model.changes(prev, data)) {
        if (n.action === 'plan' && vscode.workspace.getConfiguration('sjck').get('revealOnPlan')) {
          vscode.commands.executeCommand('workbench.view.extension.sjck');
        }
        const show = n.level === 'error' ? vscode.window.showErrorMessage : n.level === 'warn' ? vscode.window.showWarningMessage : vscode.window.showInformationMessage;
        const actions = n.action === 'plan' ? ['Review', 'Approve and run'] : ['Open'];
        show(n.text, ...actions).then((a) => {
          if (a === 'Approve and run') vscode.commands.executeCommand('sjck.approvePlan');
          else if (a) openDashboard();
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
  reg('sjck.openDashboard', openDashboard);
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
