#!/usr/bin/env node
// Stand-in for `claude -p …` in tests: prints a few stream-json events and exits.
const prompt = process.argv[process.argv.indexOf('-p') + 1];
const out = (o) => process.stdout.write(JSON.stringify(o) + '\n');
out({ type: 'system', subtype: 'init', session_id: 'fake-session' });
out({ type: 'assistant', message: { content: [{ type: 'text', text: `got: ${prompt}` }] } });
out({ type: 'assistant', message: { content: [{ type: 'tool_use', name: 'Read', input: { file_path: '.sjck/state.json' } }] } });
if (process.env.FAKE_SLOW) {
  setTimeout(() => out({ type: 'result', is_error: false, duration_ms: 5000 }), 5000);
} else {
  out({ type: 'result', is_error: false, duration_ms: 1200 });
}
