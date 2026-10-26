// Copies the shared modules and the Run Viewer into lib/ so the packaged extension is self-contained.
'use strict';
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..', '..');
const lib = path.join(__dirname, '..', 'lib');
fs.rmSync(lib, { recursive: true, force: true });
fs.mkdirSync(path.join(lib, 'console'), { recursive: true });
for (const f of ['data.js', 'inbox.js', 'runner.js', 'chat.js']) {
  fs.copyFileSync(path.join(root, 'console', 'src', f), path.join(lib, 'console', f));
}
fs.writeFileSync(path.join(lib, 'console', 'package.json'), '{"type":"module"}\n');
fs.copyFileSync(path.join(root, 'sjck-graph', 'scripts', 'viewer.html'), path.join(lib, 'viewer.html'));
console.log('lib/ synced');
