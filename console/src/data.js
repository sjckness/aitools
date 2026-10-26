// Reads a project's .sjck/ folder. Mirrors sjck-graph/scripts/graph_view.py collect():
// tolerant of missing or malformed files, never throws except for a missing state.
import { readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

export const WORKDIR = '.sjck';
export const WATCHED = [
  'state.json', 'watchdog_state.json', 'findings.jsonl', 'watchdog.jsonl',
  'tokens.json', 'token-report.json',
];
const WHAT_MAX = 80;
const WATCHDOG_MAX = 50;

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, 'utf8'));
  } catch {
    return null;
  }
}

function readJsonl(path, limit = 500) {
  let text;
  try {
    text = readFileSync(path, 'utf8');
  } catch {
    return [];
  }
  const out = [];
  for (const line of text.split('\n')) {
    const s = line.trim();
    if (!s) continue;
    try {
      const o = JSON.parse(s);
      if (o && typeof o === 'object' && !Array.isArray(o)) out.push(o);
    } catch { /* skip malformed line */ }
  }
  return out.slice(-limit);
}

// Same rule as watchdog.usage_map: own entry first, else the shared `_common` bucket.
export function usageMap(wd, ids) {
  const out = {};
  if (!wd || typeof wd !== 'object') return out;
  const common = wd._common;
  const cids = common && typeof common.sig === 'string' ? common.sig.split(',') : [];
  for (const id of ids) {
    const own = wd[id];
    if (own && typeof own.usage === 'object' && own.usage) out[id] = { ...own.usage };
    else if (cids.includes(id) && common && typeof common.usage === 'object') out[id] = { ...common.usage };
  }
  return out;
}

function short(v, n) {
  const s = v == null ? '' : String(v);
  return s.length <= n ? s : s.slice(0, n - 1) + '…';
}

export function collect(root) {
  const g = join(root, WORKDIR);
  const state = readJson(join(g, 'state.json'));
  if (!state || typeof state !== 'object' || Array.isArray(state)) return null;
  let nodes = Array.isArray(state.nodes) ? state.nodes.filter((n) => n && typeof n === 'object') : [];
  const um = usageMap(readJson(join(g, 'watchdog_state.json')), nodes.map((n) => n.id));
  nodes = nodes.map((n) => (um[n.id] ? { ...n, usage: um[n.id] } : n));
  return {
    state: { ...state, nodes },
    tokens: readJson(join(g, 'tokens.json')),
    report: readJson(join(g, 'token-report.json')),
    findings: readJsonl(join(g, 'findings.jsonl')).map((f) => ({ ...f, what: short(f.what, WHAT_MAX) })),
    watchdog: readJsonl(join(g, 'watchdog.jsonl')).slice(-WATCHDOG_MAX),
  };
}

export function summary(root) {
  const d = collect(root);
  if (!d) return { status: 'idle', goal: null, validated: 0, total: 0, updated: null };
  const nodes = d.state.nodes;
  let updated = null;
  try {
    updated = statSync(join(root, WORKDIR, 'state.json')).mtime.toISOString();
  } catch { /* ignore */ }
  return {
    status: d.state.status || 'unknown',
    goal: d.state.goal || null,
    mode: d.state.mode || null,
    validated: nodes.filter((n) => n.status === 'validated').length,
    running: nodes.filter((n) => n.status === 'running').length,
    total: nodes.length,
    findings: d.findings.length,
    updated,
  };
}

// Fingerprint of the watched files: changes whenever any of them is written.
export function fingerprint(root) {
  return WATCHED.map((f) => {
    try {
      const s = statSync(join(root, WORKDIR, f));
      return `${s.mtimeMs}:${s.size}`;
    } catch {
      return '-';
    }
  }).join('|');
}

// JSON safe inside a <script> tag.
export function embed(data) {
  return JSON.stringify(data)
    .replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026')
    .replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
}
