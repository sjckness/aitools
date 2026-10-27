// sjck setup / doctor / vscode — install and check everything without a local clone.
import { spawnSync } from 'node:child_process';
import { createWriteStream, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';

export const REPO = process.env.SJCK_REPO || 'sjckness/sjckAI-tools';
export const MARKETPLACE = 'sjck';
export const PLUGINS = ['sjck-graph', 'sjck-onboard'];
const WIN = process.platform === 'win32';

/** Download URL of a release asset; `ref` is "latest" or a tag such as "v0.4.0". */
export function assetUrl(name, ref = 'latest', repo = REPO) {
  return ref === 'latest'
    ? `https://github.com/${repo}/releases/latest/download/${name}`
    : `https://github.com/${repo}/releases/download/${ref}/${name}`;
}

/** Parses "v20.11.1", "Python 3.11.4", "2.0.14 (Claude Code)" → [major, minor]. */
export function parseVersion(text) {
  const m = /(\d+)\.(\d+)/.exec(String(text || ''));
  return m ? [Number(m[1]), Number(m[2])] : null;
}

export function atLeast(v, [maj, min]) {
  return !!v && (v[0] > maj || (v[0] === maj && v[1] >= min));
}

/** Runs a command; on Windows through the shell so that .cmd shims (npm, claude, code) resolve. */
export function run(cmd, args, { quiet = false } = {}) {
  const r = spawnSync(cmd, args, { encoding: 'utf8', shell: WIN, stdio: quiet ? 'pipe' : 'inherit' });
  return { ok: r.status === 0, out: `${r.stdout || ''}${r.stderr || ''}`.trim(), missing: !!r.error };
}

function probe(cmds, args) {
  for (const c of cmds) {
    const r = run(c, args, { quiet: true });
    if (r.ok) return { cmd: c, version: r.out.split('\n')[0] };
  }
  return null;
}

export function checks() {
  const python = probe(WIN ? ['python', 'py', 'python3'] : ['python3', 'python'], ['--version']);
  const claude = probe(['claude'], ['--version']);
  const code = probe(['code', 'cursor', 'codium'], ['--version']);
  const git = probe(['git'], ['--version']);
  return [
    { name: 'Node.js', required: true, ok: atLeast(parseVersion(process.version), [20, 0]),
      detail: process.version, fix: 'install Node.js 20 or newer: https://nodejs.org' },
    { name: 'Claude Code', required: true, ok: !!claude, detail: claude?.version,
      fix: 'npm i -g @anthropic-ai/claude-code   (then run `claude` once to log in)' },
    { name: 'Python ≥ 3.9', required: true, ok: atLeast(parseVersion(python?.version), [3, 9]),
      detail: python?.version, fix: 'install Python 3.9+: https://www.python.org/downloads' },
    { name: 'git', required: false, ok: !!git, detail: git?.version, fix: 'https://git-scm.com/downloads' },
    { name: 'VS Code CLI', required: false, ok: !!code, detail: code && `${code.cmd} ${code.version}`,
      fix: 'optional: in VS Code run "Shell Command: Install \'code\' command in PATH"', cmd: code?.cmd },
  ];
}

export function printChecks(list) {
  for (const c of list) {
    const mark = c.ok ? '✓' : c.required ? '✗' : '–';
    console.log(`  ${mark} ${c.name.padEnd(14)} ${c.ok ? c.detail || '' : c.fix}`);
  }
}

export function installPlugins() {
  console.log('\n→ Claude Code plugins');
  // add is a no-op/error when the marketplace exists; update then fetches the latest plugins
  run('claude', ['plugin', 'marketplace', 'add', REPO], { quiet: true });
  run('claude', ['plugin', 'marketplace', 'update', MARKETPLACE], { quiet: true });
  let ok = true;
  for (const p of PLUGINS) {
    const r = run('claude', ['plugin', 'install', `${p}@${MARKETPLACE}`], { quiet: true });
    const done = r.ok || /already/i.test(r.out);
    ok &&= done;
    console.log(`  ${done ? '✓' : '✗'} ${p}${done ? '' : `  (${r.out.split('\n').pop() || 'failed'})`}`);
  }
  if (!ok) {
    console.log('  Install them by hand inside Claude Code, one line at a time:');
    console.log(`    /plugin marketplace add ${REPO}`);
    for (const p of PLUGINS) console.log(`    /plugin install ${p}@${MARKETPLACE}`);
  }
  return ok;
}

export async function installVscode(editor = 'code', ref = 'latest') {
  console.log(`\n→ VS Code extension (${editor})`);
  const dir = mkdtempSync(join(tmpdir(), 'sjck-'));
  const file = join(dir, 'sjck.vsix');
  try {
    const res = await fetch(assetUrl('sjck.vsix', ref));
    if (!res.ok) throw new Error(`download failed: HTTP ${res.status}`);
    await pipeline(Readable.fromWeb(res.body), createWriteStream(file));
    const r = run(editor, ['--install-extension', file, '--force'], { quiet: true });
    if (!r.ok) throw new Error(r.out || `${editor} --install-extension failed`);
    console.log('  ✓ installed — reload the VS Code window');
    return true;
  } catch (e) {
    console.log(`  ✗ ${e.message}`);
    console.log(`  Download ${assetUrl('sjck.vsix', ref)} and use Extensions → ⋯ → Install from VSIX…`);
    return false;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

export async function setup(args = []) {
  console.log('sjck setup\n\n→ Requirements');
  const list = checks();
  printChecks(list);
  const missing = list.filter((c) => c.required && !c.ok);
  if (missing.length) {
    console.log(`\nInstall the missing requirements above, then run \`sjck setup\` again.`);
    return false;
  }
  let ok = args.includes('--no-plugins') ? true : installPlugins();
  const editor = list.find((c) => c.name === 'VS Code CLI');
  if (!args.includes('--no-vscode') && editor.ok) ok = (await installVscode(editor.cmd)) && ok;
  else if (!args.includes('--no-vscode')) console.log('\n→ VS Code extension: skipped (no `code` command found)');
  console.log(`\n${ok ? 'Done.' : 'Done, with warnings above.'} Next:`);
  console.log('  cd <your repo> && sjck add && sjck serve     # console');
  console.log('  claude  →  /sjck-onboard  →  /sjck-plan <task>  # Claude Code');
  return ok;
}

export function doctor() {
  console.log('sjck doctor\n');
  const list = checks();
  printChecks(list);
  const r = run('claude', ['plugin', 'list'], { quiet: true });
  if (r.ok) {
    for (const p of PLUGINS) console.log(`  ${r.out.includes(p) ? '✓' : '✗'} plugin ${p.padEnd(7)} ${r.out.includes(p) ? '' : 'run `sjck setup`'}`);
  }
  return list.every((c) => !c.required || c.ok);
}
