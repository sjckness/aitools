// sjck console HTTP server: localhost only, token required, no dependencies.
import { randomBytes, timingSafeEqual } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as config from './config.js';
import { collect, embed, fingerprint, summary } from './data.js';
import { Runner } from './runner.js';
import { Chat } from './chat.js';
import { inbox, writeDecision } from './inbox.js';
import { diff, push, snapshot } from './notify.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const UI = join(HERE, '..', 'ui');
const MAX_BODY = 64 * 1024;

function viewerTemplate() {
  // Packaged copy first (npm), then the repo's Run Viewer (development checkout).
  for (const p of [join(UI, 'viewer.html'), join(HERE, '..', '..', 'sjck-graph', 'scripts', 'viewer.html')]) {
    if (existsSync(p)) return readFileSync(p, 'utf8');
  }
  throw new Error('viewer.html not found');
}

function send(res, code, body, type = 'application/json; charset=utf-8', extra = {}) {
  const data = typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body);
  res.writeHead(code, {
    'content-type': type,
    'cache-control': 'no-store',
    'x-content-type-options': 'nosniff',
    'referrer-policy': 'no-referrer',
    ...extra,
  });
  res.end(data);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > MAX_BODY) {
        reject(new Error('body too large'));
        req.destroy();
      } else chunks.push(c);
    });
    req.on('end', () => {
      try {
        resolve(chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {});
      } catch {
        reject(new Error('invalid JSON'));
      }
    });
    req.on('error', reject);
  });
}

function cookieToken(req) {
  const m = /(?:^|;\s*)sjck_token=([a-f0-9]+)/.exec(req.headers.cookie || '');
  return m ? m[1] : null;
}

function same(a, b) {
  if (!a || !b || a.length !== b.length) return false;
  return timingSafeEqual(Buffer.from(a), Buffer.from(b));
}

export function createConsole({ host = '127.0.0.1', port = 7777, token = randomBytes(24).toString('hex'), pollMs = 1000, notifyMs = 2000 } = {}) {
  const runner = new Runner();
  const chat = new Chat();
  const globalStreams = new Set();
  const snaps = new Map();
  let notifyTimer = null;
  const streams = new Map(); // projectId -> Set<res>
  let timer = null;
  const prints = new Map();

  function broadcast(projectId, event, data) {
    for (const res of streams.get(projectId) || []) {
      res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
    }
  }
  runner.on('log', (pid, line) => broadcast(pid, 'log', { line }));
  runner.on('end', (pid, info) => {
    broadcast(pid, 'run', info);
    const p = config.getProject(pid);
    notify({ level: info.exitCode === 0 ? 'info' : 'error', title: `${p ? p.name : pid}: console ${info.kind} ${info.exitCode === 0 ? 'finished' : 'exited ' + info.exitCode}`, body: info.task || '', project: pid });
  });
  chat.on('message', (pid, m) => broadcast(pid, 'chat', { type: 'message', message: m }));
  chat.on('delta', (pid, d) => broadcast(pid, 'chat', { type: 'delta', ...d }));
  chat.on('done', (pid, m) => broadcast(pid, 'chat', { type: 'done', message: m }));

  function notify(n) {
    for (const res of globalStreams) res.write(`event: notify\ndata: ${JSON.stringify(n)}\n\n`);
    const hook = config.load().notify && config.load().notify.webhook;
    if (hook) push(hook, n);
  }

  function watchAll() {
    for (const p of config.load().projects) {
      let cur;
      try {
        cur = snapshot(p.path);
      } catch {
        continue;
      }
      for (const n of diff(snaps.get(p.id), cur, p.name)) notify({ ...n, project: p.id });
      snaps.set(p.id, cur);
    }
  }

  function poll() {
    for (const pid of streams.keys()) {
      const p = config.getProject(pid);
      if (!p) continue;
      const fp = fingerprint(p.path);
      if (prints.get(pid) !== fp) {
        const first = !prints.has(pid);
        prints.set(pid, fp);
        if (!first) broadcast(pid, 'data', { at: Date.now() });
      }
    }
  }

  function allowedHost(req) {
    const h = (req.headers.host || '').toLowerCase();
    const p = server.address() && server.address().port;
    return [`127.0.0.1:${p}`, `localhost:${p}`, `[::1]:${p}`, `${host}:${p}`.toLowerCase()].includes(h);
  }

  function authed(req, url) {
    return same(cookieToken(req), token) || same(req.headers['x-sjck-token'], token) || same(url.searchParams.get('token'), token);
  }

  async function handle(req, res) {
    const url = new URL(req.url, 'http://local');
    if (!allowedHost(req)) return send(res, 421, { error: 'host not allowed' });
    if (!authed(req, url)) {
      return send(res, 401, '<!doctype html><meta charset="utf-8"><title>sjck</title><p style="font:16px system-ui;padding:24px">Open the console with the link printed by <code>sjck serve</code>.</p>', 'text/html; charset=utf-8');
    }
    const cookie = { 'set-cookie': `sjck_token=${token}; HttpOnly; SameSite=Strict; Path=/` };
    const path = url.pathname;

    if (req.method === 'GET' && path === '/') {
      if (url.searchParams.has('token')) return send(res, 302, '', 'text/plain', { ...cookie, location: '/' });
      return send(res, 200, readFileSync(join(UI, 'index.html')), 'text/html; charset=utf-8', cookie);
    }

    let m = /^\/p\/([a-f0-9]{10})\/view$/.exec(path);
    if (req.method === 'GET' && m) {
      const p = config.getProject(m[1]);
      if (!p) return send(res, 404, { error: 'unknown project' });
      const data = collect(p.path);
      if (!data) {
        return send(res, 200, '<!doctype html><meta charset="utf-8"><body style="margin:0;background:#0B0E13;color:#8B95A5;font:14px system-ui;display:grid;place-items:center;height:100vh"><p>No run yet in this project. Start one from the Task panel.</p>', 'text/html; charset=utf-8');
      }
      const page = viewerTemplate().replace('__DATA__', embed({ ...data, updated: new Date().toTimeString().slice(0, 8), refresh: 0 }));
      return send(res, 200, page, 'text/html; charset=utf-8');
    }

    if (path === '/api/projects' && req.method === 'GET') {
      const cfg = config.load();
      return send(res, 200, cfg.projects.map((p) => ({ ...p, ...summary(p.path), run: runner.info(p.id) && { ...runner.info(p.id), lines: undefined } })));
    }
    if (path === '/api/projects' && req.method === 'POST') {
      try {
        const body = await readBody(req);
        return send(res, 201, config.addProject(String(body.path || ''), body.name));
      } catch (e) {
        return send(res, 400, { error: e.message });
      }
    }

    if (path === '/api/events' && req.method === 'GET') {
      res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-store', connection: 'keep-alive' });
      res.write('event: hello\ndata: {}\n\n');
      globalStreams.add(res);
      const ping = setInterval(() => res.write(': ping\n\n'), 25000);
      req.on('close', () => { clearInterval(ping); globalStreams.delete(res); });
      return undefined;
    }

    m = /^\/api\/projects\/([a-f0-9]{10})(\/[a-z/]+)?$/.exec(path);
    if (!m) return send(res, 404, { error: 'not found' });
    const p = config.getProject(m[1]);
    if (!p) return send(res, 404, { error: 'unknown project' });
    const sub = m[2] || '';

    if (sub === '' && req.method === 'DELETE') {
      if (runner.get(p.id) && !runner.get(p.id).ended) return send(res, 409, { error: 'stop the active run first' });
      return send(res, 200, { removed: config.removeProject(p.id) });
    }
    if (sub === '' && req.method === 'GET') return send(res, 200, { ...p, ...summary(p.path) });
    if (sub === '/data' && req.method === 'GET') return send(res, 200, collect(p.path) || { state: null });
    if (sub === '/run' && req.method === 'GET') return send(res, 200, runner.info(p.id) || {});
    if (sub === '/runs' && req.method === 'POST') {
      try {
        const body = await readBody(req);
        return send(res, 201, runner.start(p, body, config.load().claude));
      } catch (e) {
        return send(res, 400, { error: e.message });
      }
    }
    if (sub === '/runs/stop' && req.method === 'POST') return send(res, 200, { stopped: runner.stop(p.id) });
    if (sub === '/inbox' && req.method === 'GET') {
      const d = collect(p.path);
      return send(res, 200, { ...inbox(p.path, d ? d.findings : []), status: d ? d.state.status : 'idle' });
    }
    if (sub === '/decisions' && req.method === 'POST') {
      try {
        return send(res, 201, writeDecision(p.path, await readBody(req)));
      } catch (e) {
        return send(res, 400, { error: e.message });
      }
    }
    if (sub === '/chat' && req.method === 'GET') return send(res, 200, { ...chat.load(p), busy: chat.busy.has(p.id) });
    if (sub === '/chat' && req.method === 'POST') {
      try {
        const body = await readBody(req);
        return send(res, 202, chat.send(p, body.message, config.load().claude));
      } catch (e) {
        return send(res, 400, { error: e.message });
      }
    }
    if (sub === '/chat/reset' && req.method === 'POST') {
      try {
        chat.reset(p);
        return send(res, 200, { ok: true });
      } catch (e) {
        return send(res, 409, { error: e.message });
      }
    }
    if (sub === '/events' && req.method === 'GET') {
      res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-store', connection: 'keep-alive' });
      res.write(`event: hello\ndata: ${JSON.stringify({ run: runner.info(p.id) })}\n\n`);
      if (!streams.has(p.id)) streams.set(p.id, new Set());
      streams.get(p.id).add(res);
      const ping = setInterval(() => res.write(': ping\n\n'), 25000);
      req.on('close', () => {
        clearInterval(ping);
        streams.get(p.id)?.delete(res);
        if (!streams.get(p.id)?.size) {
          streams.delete(p.id);
          prints.delete(p.id);
        }
      });
      return undefined;
    }
    return send(res, 405, { error: 'method not allowed' });
  }

  const server = createServer((req, res) => {
    handle(req, res).catch((e) => send(res, 500, { error: e.message }));
  });

  return {
    server,
    runner,
    chat,
    token,
    notify,
    listen() {
      return new Promise((resolve, reject) => {
        server.once('error', reject);
        server.listen(port, host, () => {
          timer = setInterval(poll, pollMs);
          timer.unref();
          watchAll();
          notifyTimer = setInterval(watchAll, notifyMs);
          notifyTimer.unref();
          const a = server.address();
          const h = host === '127.0.0.1' || host === '::1' ? 'localhost' : host;
          resolve(`http://${h}:${a.port}/?token=${token}`);
        });
      });
    },
    close() {
      clearInterval(timer);
      clearInterval(notifyTimer);
      for (const r of globalStreams) r.end();
      for (const set of streams.values()) for (const r of set) r.end();
      for (const pid of runner.runs.keys()) runner.stop(pid);
      return new Promise((r) => server.close(() => r()));
    },
  };
}
