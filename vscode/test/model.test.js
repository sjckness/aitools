'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const { test } = require('node:test');
const m = require('../src/model');
const core = require('../src/core');

const DEMO = path.join(__dirname, '..', '..', 'examples', 'demo');

test('levels follow deps and survive cycles', () => {
  const L = m.levels([{ id: 'A', deps: [] }, { id: 'B', deps: ['A'] }, { id: 'C', deps: ['A', 'X'] }, { id: 'D', deps: ['B', 'C'] }]);
  assert.deepEqual(L.map((l) => l.map((n) => n.id)), [['A'], ['B', 'C'], ['D']]);
  const cyc = m.levels([{ id: 'A', deps: ['B'] }, { id: 'B', deps: ['A'] }]);
  assert.equal(cyc.flat().length, 2);
});

test('demo data: descriptions, status bar, decorations', async () => {
  const { data, inbox } = await core.load();
  const d = data.collect(DEMO);
  const t02 = d.state.nodes.find((n) => n.id === 'T02');
  assert.equal(m.nodeDescription(t02, d), 'running · opus/high · 51/60 calls · attempt 2 · 71k');
  const ib = inbox.inbox(DEMO, d.findings);
  const s = m.statusText(d, ib, null);
  assert.match(s, /^\$\(sync~spin\) sjck 4\/9 · T02 T05/);
  const dec = m.decorations(
    { state: { nodes: [{ id: 'T1', status: 'running', files: ['src/a.py', 'pkg/'] }, { id: 'T2', status: 'validated' }, { id: 'T3', status: 'failed', files: ['src/a.py'] }] } },
    { T2: ['src/a.py', 'docs/x.md'] });
  assert.equal(m.decorationFor(dec, 'src/a.py').badge, '●', 'running wins');
  assert.equal(m.decorationFor(dec, 'pkg/deep/file.py').node, 'T1', 'folder entries cover files below');
  assert.equal(m.decorationFor(dec, './docs/x.md').badge, '✓');
  assert.equal(m.decorationFor(dec, 'other.py'), null);
});

test('changes produce notifications once', () => {
  const a = { state: { status: 'running', nodes: [{ id: 'T1', status: 'running', title: 'x' }] } };
  const b = { state: { status: 'failed', nodes: [{ id: 'T1', status: 'failed', title: 'x' }] } };
  assert.deepEqual(m.changes(a, b).map((n) => n.text), ['sjck: T1 failed — x', 'sjck: run failed']);
  assert.deepEqual(m.changes(b, b), []);
  assert.deepEqual(m.changes(null, b), []);
});

test('core helpers', () => {
  assert.throws(() => core.cardPath('/r', '../x'), /invalid node id/);
  assert.match(core.viewerTemplate(), /__DATA__/);
  assert.deepEqual(core.changedByNode(DEMO, [{ id: 'T00' }]), {});
});
