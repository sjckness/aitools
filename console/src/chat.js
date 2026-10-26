// Chat with the planner (sjck-change skill) through headless Claude Code.
// One conversation per project, resumed by session id; the agent can only read and
// write change requests into .sjck/changes/.
import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { WORKDIR } from './data.js';
import { describe } from './runner.js';

const MAX_MSG = 4000;
const MAX_HISTORY = 200;

export function chatArgs({ message, sessionId, resume, claude }) {
  const chat = claude.chat || {};
  return [
    '-p', resume ? message : `/sjck-change ${message}`,
    ...(resume ? ['--resume', sessionId] : ['--session-id', sessionId]),
    '--output-format', 'stream-json', '--verbose',
    '--permission-mode', 'default',
    '--tools', chat.tools || 'Read,Glob,Grep,Write,Skill',
    '--allowedTools', 'Read', 'Glob', 'Grep', 'Skill', 'Write(./.sjck/changes/**)',
    ...(chat.model ? ['--model', chat.model] : []),
    ...(chat.extraArgs || []),
  ];
}

export class Chat extends EventEmitter {
  constructor() {
    super();
    this.busy = new Set();
  }

  file(project) {
    return join(project.path, WORKDIR, 'console', 'chat.json');
  }

  load(project) {
    try {
      const c = JSON.parse(readFileSync(this.file(project), 'utf8'));
      if (c && Array.isArray(c.messages)) return c;
    } catch { /* new chat */ }
    return { sessionId: null, messages: [] };
  }

  save(project, c) {
    const f = this.file(project);
    mkdirSync(join(project.path, WORKDIR, 'console'), { recursive: true });
    c.messages = c.messages.slice(-MAX_HISTORY);
    writeFileSync(f + '.tmp', JSON.stringify(c, null, 2));
    renameSync(f + '.tmp', f);
  }

  reset(project) {
    if (this.busy.has(project.id)) throw new Error('wait for the current answer');
    this.save(project, { sessionId: null, messages: [] });
  }

  send(project, message, claude) {
    const text = String(message || '').trim();
    if (!text) throw new Error('empty message');
    if (text.length > MAX_MSG) throw new Error('message too long');
    if (this.busy.has(project.id)) throw new Error('the planner is still answering');
    const c = this.load(project);
    const resume = Boolean(c.sessionId);
    if (!c.sessionId) c.sessionId = randomUUID();
    const user = { role: 'user', text, at: new Date().toISOString() };
    c.messages.push(user);
    this.save(project, c);
    this.busy.add(project.id);
    this.emit('message', project.id, user);

    const args = chatArgs({ message: text, sessionId: c.sessionId, resume, claude });
    let child;
    const parts = [];
    const finish = (err) => {
      if (!this.busy.has(project.id)) return;
      this.busy.delete(project.id);
      const cur = this.load(project);
      const reply = { role: 'assistant', text: parts.join('\n\n') || (err ? `(${err})` : '(no answer)'), at: new Date().toISOString(), error: err || undefined };
      cur.messages.push(reply);
      this.save(project, cur);
      this.emit('done', project.id, reply);
    };
    try {
      child = spawn(claude.bin, args, { cwd: project.path, shell: process.platform === 'win32', stdio: ['ignore', 'pipe', 'pipe'] });
    } catch (e) {
      finish(`could not start ${claude.bin}: ${e.message}`);
      return user;
    }
    let buf = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => {
      buf += chunk;
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const raw = buf.slice(0, i).trim();
        buf = buf.slice(i + 1);
        if (!raw) continue;
        let evt;
        try {
          evt = JSON.parse(raw);
        } catch {
          continue;
        }
        if (evt.type === 'assistant' && evt.message && Array.isArray(evt.message.content)) {
          for (const b of evt.message.content) {
            if (b.type === 'text' && b.text && b.text.trim()) {
              parts.push(b.text.trim());
              this.emit('delta', project.id, { kind: 'text', text: b.text.trim() });
            } else if (b.type === 'tool_use') {
              this.emit('delta', project.id, { kind: 'tool', text: describe({ type: 'assistant', message: { content: [b] } }) });
            }
          }
        } else if (evt.type === 'result' && evt.is_error && evt.result) {
          parts.push(`(error: ${String(evt.result).slice(0, 300)})`);
        }
      }
    });
    child.stderr.on('data', (d) => { stderr += d; });
    child.on('error', (e) => finish(`could not start ${claude.bin}: ${e.message}`));
    child.on('close', (code) => finish(code === 0 ? null : (stderr.trim().split('\n').pop() || `exit ${code}`).slice(0, 300)));
    return user;
  }
}
