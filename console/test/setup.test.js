import assert from 'node:assert/strict';
import { test } from 'node:test';
import { assetUrl, atLeast, parseVersion } from '../src/setup.js';

test('parseVersion reads common version strings', () => {
  assert.deepEqual(parseVersion('v20.11.1'), [20, 11]);
  assert.deepEqual(parseVersion('Python 3.9.18'), [3, 9]);
  assert.deepEqual(parseVersion('2.0.14 (Claude Code)'), [2, 0]);
  assert.equal(parseVersion(''), null);
});

test('atLeast compares major/minor', () => {
  assert.ok(atLeast([3, 9], [3, 9]));
  assert.ok(atLeast([4, 0], [3, 9]));
  assert.ok(!atLeast([3, 8], [3, 9]));
  assert.ok(!atLeast(null, [3, 9]));
});

test('assetUrl points at stable release assets', () => {
  assert.equal(assetUrl('sjck.vsix', 'latest', 'a/b'), 'https://github.com/a/b/releases/latest/download/sjck.vsix');
  assert.equal(assetUrl('sjck.vsix', 'v1.0.0', 'a/b'), 'https://github.com/a/b/releases/download/v1.0.0/sjck.vsix');
});
