// Loads the shared sjck modules (ESM, from the console) into the CommonJS extension.
// Packaged extension: ./lib/console ; development checkout: ../../console/src.
'use strict';
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

function base() {
  for (const p of [path.join(__dirname, '..', 'lib', 'console'), path.join(__dirname, '..', '..', 'console', 'src')]) {
    if (fs.existsSync(path.join(p, 'data.js'))) return p;
  }
  throw new Error('sjck core modules not found (run `npm run sync` in vscode/)');
}

let cache = null;
async function load() {
  if (cache) return cache;
  const b = base();
  const imp = (f) => import(pathToFileURL(path.join(b, f)).href);
  const [data, inbox, runner, chat] = await Promise.all([imp('data.js'), imp('inbox.js'), imp('runner.js'), imp('chat.js')]);
  cache = { data, inbox, runner, chat };
  return cache;
}

function viewerTemplate() {
  for (const p of [path.join(__dirname, '..', 'lib', 'viewer.html'), path.join(__dirname, '..', '..', 'sjck-graph', 'scripts', 'viewer.html')]) {
    if (fs.existsSync(p)) return fs.readFileSync(p, 'utf8');
  }
  throw new Error('viewer.html not found');
}

// Files each validated node reported as changed (.sjck/out/<ID>.json "changed").
function changedByNode(root, nodes) {
  const out = {};
  for (const n of nodes) {
    try {
      const o = JSON.parse(fs.readFileSync(path.join(root, '.sjck', 'out', n.id + '.json'), 'utf8'));
      if (Array.isArray(o.changed)) out[n.id] = o.changed.filter((x) => typeof x === 'string');
    } catch { /* no output yet */ }
  }
  return out;
}

function cardPath(root, id) {
  if (!/^[A-Za-z0-9_-]{1,32}$/.test(id)) throw new Error('invalid node id');
  return path.join(root, '.sjck', 'cards', id + '.md');
}

module.exports = { load, viewerTemplate, changedByNode, cardPath };
