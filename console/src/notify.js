// Watches every registered project and turns state changes into notifications:
// shown in the browser (SSE) and, if configured, pushed to a webhook such as ntfy.sh.
import { collect } from './data.js';
import { changes } from './inbox.js';

// Compare two snapshots of a project and return the notifications to send.
export function diff(prev, cur, name) {
  if (!prev || !cur) return [];
  const out = [];
  const pn = new Map(prev.nodes.map((n) => [n.id, n.status]));
  for (const n of cur.nodes) {
    if (n.status === 'failed' && pn.get(n.id) !== 'failed') {
      out.push({ level: 'error', title: `${name}: ${n.id} failed`, body: n.title || '' });
    }
    if (n.status === 'blocked' && pn.get(n.id) !== 'blocked') {
      out.push({ level: 'warn', title: `${name}: ${n.id} needs you`, body: `${n.title || ''} is blocked` });
    }
  }
  if (cur.status !== prev.status && ['done', 'failed', 'planned'].includes(cur.status)) {
    const label = { done: 'run finished', failed: 'run failed', planned: 'plan ready for review' }[cur.status];
    out.push({ level: cur.status === 'failed' ? 'error' : 'info', title: `${name}: ${label}`, body: cur.goal || '' });
  }
  const newFindings = cur.findings.filter((f) => !prev.findings.includes(f));
  if (newFindings.length) {
    out.push({ level: 'info', title: `${name}: ${newFindings.length} new finding${newFindings.length > 1 ? 's' : ''}`, body: 'Waiting for your decision in the Inbox' });
  }
  const newCrs = cur.crs.filter((c) => !prev.crs.includes(c));
  if (newCrs.length) {
    out.push({ level: 'info', title: `${name}: change request ${newCrs.join(', ')}`, body: 'Proposed from the planner chat' });
  }
  return out;
}

export function snapshot(root) {
  const d = collect(root);
  return {
    status: d ? d.state.status : 'idle',
    goal: d ? d.state.goal : null,
    nodes: d ? d.state.nodes.map((n) => ({ id: n.id, title: n.title, status: n.status })) : [],
    findings: d ? d.findings.filter((f) => ['open', 'proposed'].includes(f.status || 'open')).map((f) => f.id) : [],
    crs: changes(root).filter((c) => c.status === 'proposed').map((c) => c.id),
  };
}

export async function push(webhook, n) {
  if (!webhook || !/^https?:\/\//.test(webhook)) return false;
  try {
    const r = await fetch(webhook, {
      method: 'POST',
      headers: { Title: n.title.replace(/[^\x20-\x7e]/g, '?'), Priority: n.level === 'error' ? 'high' : 'default', Tags: 'sjck' },
      body: n.body || n.title,
      signal: AbortSignal.timeout(5000),
    });
    return r.ok;
  } catch {
    return false;
  }
}
