// Copies the Run Viewer from the plugin into the npm package (runs on `npm pack` / `npm publish`).
import { copyFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
copyFileSync(join(here, '..', '..', 'sjck-graph', 'scripts', 'viewer.html'), join(here, '..', 'ui', 'viewer.html'));
console.log('ui/viewer.html synced from sjck-graph');
