// Launches headless Claude Code runs (`claude -p "/sjck-plan …"`) for a project and
// turns their stream-json output into readable log lines.
import { spawn } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { createWriteStream, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { WORKDIR } from './data.js';

const COMMANDS = { plan: '/sjck-plan', run: '/sjck-run' };
const MAX_LINES = 400;

// One readable line per meaningful stream-json event; null to skip.
export function describe(evt) {
  if (!evt || typeof evt !== 'object') return null;
  if (evt.type === 'system' && evt.subtype === 'init') return `session ${evt.session_id || ''} started`;
  if (evt.type === 'assistant' && evt.message && Array.isArray(evt.message.content)) {
    const parts = [];
    for (const c of evt.message.content) {
      if (c.type === 'text' && c.text && c.text.trim()) parts.push(c.text.trim());
      else if (c.type === 'tool_use') {
        const i = c.input || {};
        const arg = i.file_path || i.command || i.pattern || i.description || i.subagent_type || '';
        parts.push(`→ ${c.name}${arg ? ' ' + String(arg).slice(0, 120) : ''}`);
      }
    }
    return parts.length ? parts.join('\n') : null;
  }
  if (evt.type === 'result') {
    const ok = !evt.is_error;
    const secs = evt.duration_ms ? ` in ${Math.round(evt.duration_ms / 1000)} s` : '';
    return `${ok ? 'done' : 'error'}${secs}${evt.result && !ok ? ': ' + String(evt.result).slice(0, 300) : ''}`;
  }
  return null;
}

export class Runner extends EventEmitter {
  constructor() {
    super();
    this.runs = new Map(); // projectId -> run
  }

  get(projectId) {
    return this.runs.get(projectId) || null;
  }

  info(projectId) {
    const r = this.get(projectId);
    if (!r) return null;
    const { id, kind, task, started, ended, exitCode, lines } = r;
    return { id, kind, task, started, ended, exitCode, running: !ended, lines };
  }

  start(project, { task, kind = 'plan', mode }, claude) {
    const prev = this.get(project.id);
    if (prev && !prev.ended) throw new Error('a run is already active for this project');
    if (!COMMANDS[kind]) throw new Error(`unknown kind: ${kind}`);
    const text = String(task || '').trim();
    if (!text && kind === 'plan') throw new Error('task is required');
    if (text.length > 4000) throw new Error('task too long');
    const prompt = [COMMANDS[kind], text, mode && /^[SML]$/.test(mode) ? `--mode ${mode}` : '']
      .filter(Boolean).join(' ');

    const dir = join(project.path, WORKDIR, 'console', 'runs');
    mkdirSync(dir, { recursive: true });
    const id = new Date().toISOString().replace(/[:.]/g, '-');
    const log = createWriteStream(join(dir, `${id}.jsonl`));
    const args = ['-p', prompt, ...(claude.args || [])];
    const run = { id, kind, task: text, started: new Date().toISOString(), ended: null, exitCode: null, lines: [] };
    this.runs.set(project.id, run);

    let child;
    try {
      child = spawn(claude.bin, args, {
        cwd: project.path,
        shell: process.platform === 'win32', // claude.cmd needs a shell on Windows
        stdio: ['ignore', 'pipe', 'pipe'],
        env: process.env,
      });
    } catch (e) {
      this._finish(project.id, run, log, -1, `could not start ${claude.bin}: ${e.message}`);
      return this.info(project.id);
    }
    run.child = child;
    this._line(project.id, run, `$ ${claude.bin} -p "${prompt}"`);

    let buf = '';
    child.stdout.on('data', (chunk) => {
      log.write(chunk);
      buf += chunk;
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const raw = buf.slice(0, i).trim();
        buf = buf.slice(i + 1);
        if (!raw) continue;
        let line;
        try {
          line = describe(JSON.parse(raw));
        } catch {
          line = raw.slice(0, 500); // plain text output
        }
        if (line) this._line(project.id, run, line);
      }
    });
    child.stderr.on('data', (chunk) => this._line(project.id, run, String(chunk).trim().slice(0, 500)));
    child.on('error', (e) => this._finish(project.id, run, log, -1, `could not start ${claude.bin}: ${e.message}`));
    child.on('close', (code) => this._finish(project.id, run, log, code));
    return this.info(project.id);
  }

  stop(projectId) {
    const r = this.get(projectId);
    if (!r || r.ended || !r.child) return false;
    r.child.kill('SIGTERM');
    return true;
  }

  _line(projectId, run, text) {
    if (!text) return;
    for (const l of String(text).split('\n')) {
      run.lines.push(l);
      if (run.lines.length > MAX_LINES) run.lines.shift();
      this.emit('log', projectId, l);
    }
  }

  _finish(projectId, run, log, code, msg) {
    if (run.ended) return;
    if (msg) this._line(projectId, run, msg);
    run.ended = new Date().toISOString();
    run.exitCode = code;
    delete run.child;
    log.end();
    this._line(projectId, run, `exit ${code}`);
    this.emit('end', projectId, this.info(projectId));
  }
}
