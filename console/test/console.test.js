import assert from 'node:assert/strict';
import { chmodSync, cpSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { after, before, describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const DEMO = join(HERE, '..', '..', 'examples', 'demo');
const FAKE = join(HERE, 'fake-claude.js');
const tmp = mkdtempSync(join(tmpdir(), 'sjck-console-'));
process.env.SJCK_HOME = join(tmp, 'home');

const config = await import('../src/config.js');
const data = await import('../src/data.js');
const { describe: describeEvt } = await import('../src/runner.js');
const { createConsole } = await import('../src/server.js');

after(() => rmSync(tmp, { recursive: true, force: true }));

function project(name, withDemo) {
  const dir = join(tmp, name);
  mkdirSync(dir, { recursive: true });
  if (withDemo) cpSync(join(DEMO, '.sjck'), join(dir, '.sjck'), { recursive: true });
  return dir;
}

describe('config', () => {
  test('add, list, remove', () => {
    const dir = project('cfg');
    const p = config.addProject(dir);
    assert.equal(p.id, config.projectId(dir));
    assert.equal(config.addProject(dir).id, p.id, 'adding twice keeps one entry');
    assert.equal(config.load().projects.filter((x) => x.id === p.id).length, 1);
    assert.ok(config.removeProject(p.id));
    assert.equal(config.getProject(p.id), null);
  });
  test('rejects a missing folder', () => {
    assert.throws(() => config.addProject(join(tmp, 'nope')), /not a directory/);
  });
});

describe('data', () => {
  test('demo project', () => {
    const dir = project('demo', true);
    const d = data.collect(dir);
    assert.equal(d.state.goal, 'Implement docs/specs/v0.3.md');
    assert.ok(d.tokens && d.findings.length === 4);
    const s = data.summary(dir);
    assert.equal(s.validated, 4);
    assert.equal(s.total, 9);
  });
  test('no state, malformed files', () => {
    const dir = project('broken');
    assert.equal(data.collect(dir), null);
    assert.equal(data.summary(dir).status, 'idle');
    mkdirSync(join(dir, '.sjck'));
    writeFileSync(join(dir, '.sjck', 'state.json'), '{"status":"running","nodes":[{"id":"T1","usage":{"tool_calls":0}}]}');
    writeFileSync(join(dir, '.sjck', 'findings.jsonl'), 'nope\n[1]\n{"id":"F1","what":"' + 'x'.repeat(200) + '"}\n');
    writeFileSync(join(dir, '.sjck', 'watchdog_state.json'), '{"_common":{"sig":"T1","usage":{"tool_calls":5}}}');
    const d = data.collect(dir);
    assert.equal(d.findings.length, 1);
    assert.ok(d.findings[0].what.length <= 80);
    assert.equal(d.state.nodes[0].usage.tool_calls, 5);
  });
  test('embed cannot break out of a script tag', () => {
    const s = data.embed({ x: '</script><b>&' });
    assert.ok(!s.includes('<') && !s.includes('>') && !s.includes('&'));
    assert.deepEqual(JSON.parse(s), { x: '</script><b>&' });
  });
});

describe('runner', () => {
  test('describe stream-json events', () => {
    assert.equal(describeEvt({ type: 'assistant', message: { content: [{ type: 'tool_use', name: 'Edit', input: { file_path: 'a.py' } }] } }), '→ Edit a.py');
    assert.match(describeEvt({ type: 'result', is_error: false, duration_ms: 3000 }), /^done in 3 s/);
    assert.equal(describeEvt({ type: 'user' }), null);
  });
});

describe('server', () => {
  let c, base, url, dir, pid;
  before(async () => {
    chmodSync(FAKE, 0o755);
    dir = project('srv', true);
    pid = config.addProject(dir).id;
    const cfg = config.load();
    cfg.claude = { bin: FAKE, args: [] };
    config.save(cfg);
    c = createConsole({ port: 0, pollMs: 50 });
    url = await c.listen();
    base = url.split('/?')[0];
  });
  after(() => c.close());

  const get = (path, opts = {}) => fetch(base + path, { redirect: 'manual', ...opts });
  const auth = (opts = {}) => ({ ...opts, headers: { 'x-sjck-token': c.token, 'content-type': 'application/json', ...(opts.headers || {}) } });

  test('token required', async () => {
    assert.equal((await get('/api/projects')).status, 401);
    assert.equal((await get('/api/projects', { headers: { 'x-sjck-token': 'wrong' } })).status, 401);
    const r = await get('/?token=' + c.token);
    assert.equal(r.status, 302);
    assert.match(r.headers.get('set-cookie'), /sjck_token=[a-f0-9]+; HttpOnly; SameSite=Strict/);
  });

  test('foreign Host header refused (DNS rebinding)', async () => {
    const { request } = await import('node:http');
    const port = new URL(base).port;
    const status = await new Promise((resolve) => {
      request({ host: '127.0.0.1', port, path: '/api/projects', headers: { host: 'evil.example:' + port, 'x-sjck-token': c.token } },
        (res) => resolve(res.statusCode)).end();
    });
    assert.equal(status, 421);
  });

  test('projects, data and viewer', async () => {
    const ps = await (await get('/api/projects', auth())).json();
    const p = ps.find((x) => x.id === pid);
    assert.equal(p.total, 9);
    const d = await (await get(`/api/projects/${pid}/data`, auth())).json();
    assert.equal(d.findings.length, 4);
    const html = await (await get(`/p/${pid}/view`, auth())).text();
    assert.ok(!html.includes('__DATA__') && html.includes('Implement docs/specs/v0.3.md'));
    assert.equal((await get('/api/projects/0000000000/data', auth())).status, 404);
    assert.equal((await get('/p/../../etc/passwd', auth())).status, 404);
  });

  test('add project rejects bad input', async () => {
    const r = await get('/api/projects', auth({ method: 'POST', body: JSON.stringify({ path: join(tmp, 'missing') }) }));
    assert.equal(r.status, 400);
    const r2 = await get('/api/projects', auth({ method: 'POST', body: 'not json' }));
    assert.equal(r2.status, 400);
  });

  test('SSE: data event on change, run log streamed', async () => {
    const ctrl = new AbortController();
    const res = await get(`/api/projects/${pid}/events`, auth({ signal: ctrl.signal }));
    const reader = res.body.getReader();
    const seen = [];
    const done = (async () => {
      let buf = '';
      for (;;) {
        const { value, done: d } = await reader.read();
        if (d) break;
        buf += new TextDecoder().decode(value);
        let i;
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const block = buf.slice(0, i);
          buf = buf.slice(i + 2);
          const ev = /event: (\w+)/.exec(block);
          if (ev) seen.push([ev[1], block]);
          if (seen.some((s) => s[0] === 'run')) return;
        }
      }
    })();
    await new Promise((r) => setTimeout(r, 150));
    writeFileSync(join(dir, '.sjck', 'findings.jsonl'), '{"id":"F9","what":"new"}\n');
    await new Promise((r) => setTimeout(r, 200));
    const run = await (await get(`/api/projects/${pid}/runs`, auth({ method: 'POST', body: JSON.stringify({ task: 'add a service', kind: 'plan' }) }))).json();
    assert.equal(run.kind, 'plan');
    await Promise.race([done, new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 5000))]);
    ctrl.abort();
    const kinds = seen.map((s) => s[0]);
    assert.ok(kinds.includes('hello') && kinds.includes('data') && kinds.includes('log') && kinds.includes('run'), kinds.join(','));
    const logs = seen.filter((s) => s[0] === 'log').map((s) => s[1]).join('\n');
    assert.match(logs, /got: \/sjck-plan add a service/);
    assert.match(logs, /→ Read \.sjck\/state\.json/);
  });

  test('run validation and stop', async () => {
    const empty = await get(`/api/projects/${pid}/runs`, auth({ method: 'POST', body: JSON.stringify({ task: '', kind: 'plan' }) }));
    assert.equal(empty.status, 400);
    const bad = await get(`/api/projects/${pid}/runs`, auth({ method: 'POST', body: JSON.stringify({ task: 'x', kind: 'rm -rf' }) }));
    assert.equal(bad.status, 400);
    process.env.FAKE_SLOW = '1';
    const ok = await get(`/api/projects/${pid}/runs`, auth({ method: 'POST', body: JSON.stringify({ task: 'slow', kind: 'run', mode: 'M' }) }));
    delete process.env.FAKE_SLOW;
    assert.equal(ok.status, 201);
    const busy = await get(`/api/projects/${pid}/runs`, auth({ method: 'POST', body: JSON.stringify({ task: 'again', kind: 'plan' }) }));
    assert.equal(busy.status, 400);
    const st = await (await get(`/api/projects/${pid}/runs/stop`, auth({ method: 'POST' }))).json();
    assert.equal(st.stopped, true);
    await new Promise((r) => setTimeout(r, 300));
    const info = await (await get(`/api/projects/${pid}/run`, auth())).json();
    assert.equal(info.running, false);
    assert.match(info.lines.join('\n'), /--mode M/);
  });
});
