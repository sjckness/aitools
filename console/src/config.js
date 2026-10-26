// Console config: ~/.sjck/console.json (SJCK_HOME overrides the folder, used by tests).
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, join, resolve } from 'node:path';

export const DEFAULT_CLAUDE = {
  bin: process.platform === 'win32' ? 'claude.cmd' : 'claude',
  // Non-interactive runs need permissions decided up front; same defaults as evals/run.py.
  args: ['--output-format', 'stream-json', '--verbose', '--permission-mode', 'acceptEdits', '--allowedTools', 'Bash'],
};

export function home() {
  return process.env.SJCK_HOME || join(homedir(), '.sjck');
}

function file() {
  return join(home(), 'console.json');
}

export function projectId(path) {
  return createHash('sha1').update(resolve(path)).digest('hex').slice(0, 10);
}

export function load() {
  let cfg = {};
  try {
    cfg = JSON.parse(readFileSync(file(), 'utf8'));
  } catch {
    cfg = {};
  }
  if (!Array.isArray(cfg.projects)) cfg.projects = [];
  cfg.claude = { ...DEFAULT_CLAUDE, ...(cfg.claude || {}) };
  return cfg;
}

export function save(cfg) {
  mkdirSync(home(), { recursive: true });
  const tmp = file() + '.tmp';
  writeFileSync(tmp, JSON.stringify(cfg, null, 2) + '\n');
  renameSync(tmp, file());
}

export function addProject(path, name) {
  const abs = resolve(path);
  if (!existsSync(abs) || !statSync(abs).isDirectory()) {
    throw new Error(`not a directory: ${abs}`);
  }
  const cfg = load();
  const id = projectId(abs);
  if (!cfg.projects.some((p) => p.id === id)) {
    cfg.projects.push({ id, path: abs, name: name || basename(abs) });
    save(cfg);
  }
  return cfg.projects.find((p) => p.id === id);
}

export function removeProject(pathOrId) {
  const cfg = load();
  const id = cfg.projects.some((p) => p.id === pathOrId) ? pathOrId : projectId(pathOrId);
  const before = cfg.projects.length;
  cfg.projects = cfg.projects.filter((p) => p.id !== id);
  save(cfg);
  return cfg.projects.length < before;
}

export function getProject(id) {
  return load().projects.find((p) => p.id === id) || null;
}
