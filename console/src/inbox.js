// Inbox for the console: lists change requests and findings waiting for a decision,
// and writes decision files. The orchestrator applies them (sjck-graph/scripts/inbox.py),
// so the console never edits state.json, findings.jsonl or CR files itself.
import { randomBytes } from 'node:crypto';
import { mkdirSync, readdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { WORKDIR } from './data.js';

const ACTIONS = { finding: ['accept', 'defer', 'reject'], cr: ['apply', 'reject'] };
const IDS = { finding: /^F\d{1,6}$/, cr: /^CR-\d{3,6}$/ };

function readJsonDir(dir, prefix) {
  let names = [];
  try {
    names = readdirSync(dir).filter((n) => n.startsWith(prefix) && n.endsWith('.json')).sort();
  } catch {
    return [];
  }
  const out = [];
  for (const n of names) {
    try {
      const o = JSON.parse(readFileSync(join(dir, n), 'utf8'));
      if (o && typeof o === 'object' && !Array.isArray(o)) out.push(o);
    } catch { /* skip */ }
  }
  return out;
}

export function changes(root) {
  return readJsonDir(join(root, WORKDIR, 'changes'), 'CR-').map((c) => ({
    id: c.id, summary: c.summary, priority: c.priority || 'normal', status: c.status || 'proposed',
    created: c.created, resolution: c.resolution, ops: Array.isArray(c.ops) ? c.ops.map((o) => o.op) : [],
    rerun: (c.impact && c.impact.rerun) || [],
  }));
}

export function decisions(root, status) {
  const all = readJsonDir(join(root, WORKDIR, 'decisions'), 'D-');
  return status ? all.filter((d) => (d.status || 'new') === status) : all;
}

export function writeDecision(root, { kind, id, action, placement, note }) {
  if (!ACTIONS[kind]) throw new Error('kind must be finding or cr');
  if (!IDS[kind].test(String(id || ''))) throw new Error(`invalid ${kind} id`);
  if (!ACTIONS[kind].includes(action)) throw new Error(`action must be one of ${ACTIONS[kind].join(', ')}`);
  if (placement != null && !/^(backlog|(card|node):[A-Za-z0-9_-]{1,32})$/.test(String(placement))) {
    throw new Error('invalid placement');
  }
  const dup = decisions(root, 'new').find((d) => d.target && d.target.kind === kind && d.target.id === id);
  if (dup) throw new Error(`a decision on ${id} is already waiting for the orchestrator`);
  const dir = join(root, WORKDIR, 'decisions');
  mkdirSync(dir, { recursive: true });
  const did = `D-${Date.now()}-${randomBytes(3).toString('hex')}`;
  const rec = {
    id: did, target: { kind, id }, action, status: 'new', created: new Date().toISOString(), author: 'console',
    ...(placement ? { placement } : {}), ...(note ? { note: String(note).slice(0, 500) } : {}),
  };
  const tmp = join(dir, `.${did}.tmp`);
  writeFileSync(tmp, JSON.stringify(rec, null, 2) + '\n');
  renameSync(tmp, join(dir, `${did}.json`));
  return rec;
}

// What needs a human: proposed/open findings, CRs not yet applied, and decisions in flight.
export function inbox(root, findings) {
  const waiting = new Map(decisions(root, 'new').map((d) => [`${d.target?.kind}:${d.target?.id}`, d.action]));
  return {
    findings: (findings || []).filter((f) => ['open', 'proposed'].includes(f.status || 'open'))
      .map((f) => ({ ...f, decided: waiting.get(`finding:${f.id}`) || null })),
    crs: changes(root).map((c) => ({ ...c, decided: waiting.get(`cr:${c.id}`) || null })),
  };
}
