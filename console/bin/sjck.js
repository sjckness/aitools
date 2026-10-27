#!/usr/bin/env node
// sjck — local console for sjck agent-graph runs.
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { createInterface } from 'node:readline/promises';
import * as config from '../src/config.js';
import { summary, WORKDIR } from '../src/data.js';
import { createConsole } from '../src/server.js';
import * as setup from '../src/setup.js';

const HELP = `sjck console

Usage:
  sjck setup [--no-plugins] [--no-vscode]                 check requirements, install plugins and VS Code extension
  sjck doctor                                             check that everything is installed
  sjck vscode [--editor code|cursor|codium]               install or update the VS Code extension
  sjck update                                             update console, plugins and extension
  sjck serve [--port 7777] [--host 127.0.0.1] [--no-open]   start the console
  sjck add [path] [--name NAME]                           register a project (default: current folder)
  sjck remove <path|id>                                   unregister a project
  sjck list                                               list projects and their status

The console listens on localhost only and requires the token in the printed link.
Config: ${join(config.home(), 'console.json')}`;

function flag(args, name, fallback) {
  const i = args.indexOf(name);
  return i >= 0 && i + 1 < args.length ? args[i + 1] : fallback;
}

function openBrowser(url) {
  const cmd = process.platform === 'darwin' ? 'open' : process.platform === 'win32' ? 'cmd' : 'xdg-open';
  const args = process.platform === 'win32' ? ['/c', 'start', '""', url] : [url];
  try {
    spawn(cmd, args, { stdio: 'ignore', detached: true }).on('error', () => {}).unref();
  } catch { /* no browser: the link is printed anyway */ }
}

async function maybeRegisterCwd() {
  const cwd = process.cwd();
  const known = config.load().projects.some((p) => p.id === config.projectId(cwd));
  const looksLikeProject = existsSync(join(cwd, '.git')) || existsSync(join(cwd, WORKDIR));
  if (known || !looksLikeProject || !process.stdin.isTTY) return;
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const ans = (await rl.question(`Add ${cwd} to the console? [Y/n] `)).trim().toLowerCase();
  rl.close();
  if (ans === '' || ans === 'y' || ans === 'yes') config.addProject(cwd);
}

async function main() {
  const [cmd = 'help', ...args] = process.argv.slice(2);
  if (cmd === 'setup') {
    process.exitCode = (await setup.setup(args)) ? 0 : 1;
  } else if (cmd === 'doctor') {
    process.exitCode = setup.doctor() ? 0 : 1;
  } else if (cmd === 'vscode') {
    process.exitCode = (await setup.installVscode(flag(args, '--editor', 'code'))) ? 0 : 1;
  } else if (cmd === 'update') {
    console.log('→ console');
    const r = setup.run('npm', ['i', '-g', setup.assetUrl('sjck-console.tgz')]);
    if (!r.ok) console.log('  ✗ npm install failed; see the output above');
    process.exitCode = (await setup.setup(args)) && r.ok ? 0 : 1;
  } else if (cmd === 'serve') {
    await maybeRegisterCwd();
    const host = flag(args, '--host', '127.0.0.1');
    if (!['127.0.0.1', 'localhost', '::1'].includes(host)) {
      console.warn(`warning: listening on ${host} exposes the console beyond this machine. Use only on a private network.`);
    }
    const c = createConsole({ host, port: Number(flag(args, '--port', 7777)) });
    const url = await c.listen();
    console.log(`sjck console running: ${url}\nCtrl+C to stop.`);
    if (!args.includes('--no-open')) openBrowser(url);
    const stop = async () => {
      await c.close();
      process.exit(0);
    };
    process.on('SIGINT', stop);
    process.on('SIGTERM', stop);
  } else if (cmd === 'add') {
    const path = args[0] && !args[0].startsWith('--') ? args[0] : '.';
    const p = config.addProject(resolve(path), flag(args, '--name'));
    console.log(`added ${p.name} (${p.id}) ${p.path}`);
  } else if (cmd === 'remove') {
    if (!args[0]) throw new Error('usage: sjck remove <path|id>');
    console.log(config.removeProject(args[0]) ? 'removed' : 'not found');
  } else if (cmd === 'list') {
    const ps = config.load().projects;
    if (!ps.length) console.log('No projects yet: run `sjck add` inside a repo.');
    for (const p of ps) {
      const s = summary(p.path);
      console.log(`${p.id}  ${p.name.padEnd(24)} ${s.status.padEnd(9)} ${s.validated}/${s.total}  ${s.goal || ''}`);
    }
  } else {
    console.log(HELP);
  }
}

main().catch((e) => {
  console.error(`sjck: ${e.message}`);
  process.exit(1);
});
