// Pure functions that turn a project's .sjck data into what VS Code shows.
// No `vscode` import here, so everything is unit-testable with plain Node.
'use strict';

const STATUS_ICON = {
  validated: ['pass-filled', 'testing.iconPassed'],
  running: ['sync~spin', 'charts.blue'],
  done: ['circle-filled', 'charts.purple'],
  pending: ['circle-outline', 'disabledForeground'],
  planned: ['circle-outline', 'charts.yellow'],
  failed: ['error', 'testing.iconFailed'],
  blocked: ['warning', 'list.warningForeground'],
  'done-unverified': ['question', 'charts.yellow'],
};

function icon(status) {
  return STATUS_ICON[status] || ['circle-outline', 'disabledForeground'];
}

// Topological levels, robust to unknown deps and cycles.
function levels(nodes) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const depth = new Map();
  function d(id, seen) {
    if (depth.has(id)) return depth.get(id);
    if (seen.has(id)) return 0;
    seen.add(id);
    let v = 0;
    for (const p of (byId.get(id) || {}).deps || []) if (byId.has(p)) v = Math.max(v, d(p, seen) + 1);
    depth.set(id, v);
    return v;
  }
  const out = [];
  for (const n of nodes) {
    const v = d(n.id, new Set());
    (out[v] = out[v] || []).push(n);
  }
  return out.filter(Boolean);
}

function k(n) {
  if (n == null) return null;
  return n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'k' : String(n);
}

function nodeTokens(data, id) {
  const t = data && data.tokens && data.tokens.by_node && data.tokens.by_node[id];
  return t ? (t.total != null ? t.total : (t.input || 0) + (t.output || 0)) : null;
}

// One line under each node in the tree.
function nodeDescription(n, data) {
  const parts = [n.status];
  if (n.model && n.model !== 'inherit') parts.push(n.model + (n.effort ? '/' + n.effort : ''));
  const b = n.budget && n.budget.tool_calls;
  const u = n.usage && n.usage.tool_calls;
  if (b) parts.push(`${u || 0}/${b} calls`);
  if (n.attempts) parts.push(`attempt ${n.attempts + 1}`);
  const t = k(nodeTokens(data, n.id));
  if (t) parts.push(t);
  return parts.join(' · ');
}

function nodeTooltip(n) {
  const lines = [`${n.id} — ${n.title || ''}`, `status: ${n.status}`];
  if (n.deps && n.deps.length) lines.push(`after: ${n.deps.join(', ')}`);
  if (n.files && n.files.length) lines.push(`files: ${n.files.join(', ')}`);
  if (n.assumptions && n.assumptions.length) lines.push(`assumptions: ${n.assumptions.join('; ')}`);
  return lines.join('\n');
}

function waitingCount(inbox) {
  if (!inbox) return 0;
  return inbox.findings.filter((f) => !f.decided).length +
    inbox.crs.filter((c) => c.status === 'proposed' && !c.decided).length;
}

function statusText(data, inbox, run) {
  if (!data) return run && run.running ? `$(sync~spin) sjck ${run.kind}` : '$(type-hierarchy) sjck';
  const nodes = data.state.nodes;
  const v = nodes.filter((n) => n.status === 'validated').length;
  const running = nodes.filter((n) => n.status === 'running').map((n) => n.id);
  const failed = nodes.some((n) => n.status === 'failed');
  const head = failed ? '$(error)' : running.length || (run && run.running) ? '$(sync~spin)' : data.state.status === 'done' ? '$(pass-filled)' : '$(type-hierarchy)';
  const parts = [`${head} sjck ${v}/${nodes.length}`];
  if (running.length) parts.push(running.slice(0, 3).join(' ') + (running.length > 3 ? '…' : ''));
  if (data.state.status === 'planned') parts.push('plan ready');
  const w = waitingCount(inbox);
  if (w) parts.push(`$(inbox) ${w}`);
  return parts.join(' · ');
}

function norm(p) {
  return String(p || '').replace(/\\/g, '/').replace(/^\.\//, '').replace(/\/+$/, '');
}

// relative path -> {badge, tooltip, color, node}; running wins over validated.
function decorations(data, changedByNode) {
  const out = new Map();
  if (!data) return out;
  const put = (path, dec) => {
    const p = norm(path);
    if (!p || p.includes('*')) return;
    const prev = out.get(p);
    if (!prev || dec.rank > prev.rank) out.set(p, dec);
  };
  for (const n of data.state.nodes) {
    if (n.status === 'running') {
      for (const f of n.files || []) put(f, { badge: '●', tooltip: `sjck: ${n.id} is working on this`, color: 'charts.blue', node: n.id, rank: 3 });
    } else if (n.status === 'failed' || n.status === 'blocked') {
      for (const f of n.files || []) put(f, { badge: '!', tooltip: `sjck: ${n.id} ${n.status}`, color: 'list.warningForeground', node: n.id, rank: 2 });
    } else if (n.status === 'validated') {
      for (const f of (changedByNode && changedByNode[n.id]) || []) put(f, { badge: '✓', tooltip: `sjck: changed by ${n.id} (validated)`, color: 'testing.iconPassed', node: n.id, rank: 1 });
    }
  }
  return out;
}

// Decoration for a file or, for folders listed in a card (`src/`), any file below it.
function decorationFor(map, rel) {
  const p = norm(rel);
  if (map.has(p)) return map.get(p);
  let best = null;
  for (const [k2, v] of map) if (p.startsWith(k2 + '/') && (!best || v.rank > best.rank)) best = v;
  return best;
}

// Notifications worth showing when a project moves from `prev` to `cur`.
function changes(prev, cur) {
  if (!prev || !cur) return [];
  const out = [];
  const before = new Map(prev.state.nodes.map((n) => [n.id, n.status]));
  for (const n of cur.state.nodes) {
    const was = before.get(n.id);
    if (n.status === was) continue;
    if (n.status === 'failed') out.push({ level: 'error', text: `sjck: ${n.id} failed — ${n.title || ''}` });
    else if (n.status === 'blocked') out.push({ level: 'warn', text: `sjck: ${n.id} needs you — ${n.title || ''}` });
  }
  if (prev.state.status !== cur.state.status) {
    if (cur.state.status === 'done') out.push({ level: 'info', text: 'sjck: run finished' });
    if (cur.state.status === 'failed') out.push({ level: 'error', text: 'sjck: run failed' });
    if (cur.state.status === 'planned') out.push({ level: 'info', text: 'sjck: plan ready for review', action: 'plan' });
  }
  return out;
}

module.exports = { levels, icon, nodeDescription, nodeTooltip, statusText, waitingCount, decorations, decorationFor, changes, norm, k };
