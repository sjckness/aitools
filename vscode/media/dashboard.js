// sjck Mission Control webview. Receives {type:'data', data, inbox, changed, run} and posts actions back.
(function () {
  'use strict';
  const api = typeof acquireVsCodeApi === 'function' ? acquireVsCodeApi() : { postMessage() {}, getState() {}, setState() {} };
  const app = document.getElementById('app');
  const send = (m) => api.postMessage(m);

  const COL = { validated: 'var(--ok)', running: 'var(--run)', done: 'var(--done)', pending: 'var(--pend)', planned: 'var(--plan)', failed: 'var(--fail)', blocked: 'var(--block)', 'done-unverified': 'var(--unv)', idle: 'var(--pend)' };
  const SEV = { high: 'var(--fail)', med: 'var(--block)', low: 'var(--plan)' };
  const CAT = ['#f5b544', '#60a5fa', '#a78bfa', '#3ddc97', '#ff7a59', '#22d3ee', '#f472b6', '#94a3b8'];
  const NW = 210, NH = 92, CW = 280, RH = 112, PAD = 40;

  const I = {
    check: '<path d="M4 8.5l2.5 2.5L12 5.5"/>',
    spin: '<path d="M8 2a6 6 0 1 1-6 6"/>',
    x: '<path d="M5 5l6 6M11 5l-6 6"/>',
    warn: '<path d="M8 3l5.5 10h-11z"/><path d="M8 7v2.5M8 11.4v.1"/>',
    dot: '<circle cx="8" cy="8" r="4.5"/>',
    q: '<circle cx="8" cy="8" r="5.5"/><path d="M6.6 6.5a1.5 1.5 0 1 1 2 1.4c-.4.2-.6.5-.6.9v.4M8 11.2v.1"/>',
    play: '<path d="M5 3.5l7 4.5-7 4.5z"/>',
    stop: '<rect x="4" y="4" width="8" height="8" rx="1.5"/>',
    bulb: '<path d="M6 12.5h4M6.5 14h3M8 2a4 4 0 0 0-2.4 7.2c.5.4.9.9.9 1.6V11h3v-.2c0-.7.4-1.2.9-1.6A4 4 0 0 0 8 2z"/>',
    chat: '<path d="M3 4.5A1.5 1.5 0 0 1 4.5 3h7A1.5 1.5 0 0 1 13 4.5v5A1.5 1.5 0 0 1 11.5 11H7l-3 2.5V11h.5"/>',
    log: '<path d="M3 4h10M3 8h10M3 12h6"/>',
    graph: '<circle cx="4" cy="4" r="1.6"/><circle cx="12" cy="8" r="1.6"/><circle cx="4" cy="12" r="1.6"/><path d="M5.5 4.5l5 3M5.5 11.5l5-3"/>',
    fit: '<path d="M3 6V3h3M10 3h3v3M13 10v3h-3M6 13H3v-3"/>',
    plus: '<path d="M8 3.5v9M3.5 8h9"/>',
    minus: '<path d="M3.5 8h9"/>',
    file: '<path d="M4 2h5l3 3v9H4z"/><path d="M9 2v3h3"/>',
    diff: '<path d="M5 2v8M2 5h6M8 14h6"/>',
    tok: '<path d="M8 2l5 3v6l-5 3-5-3V5z"/>',
    tool: '<path d="M10 2.5a3 3 0 0 0-3.4 4L2.5 10.6 5.4 13.5l4.1-4.1a3 3 0 0 0 4-3.4L11.6 8 9.4 7.6 9 5.4z"/>',
    bot: '<rect x="3" y="5" width="10" height="8" rx="2"/><path d="M8 2.5V5M6 9v.1M10 9v.1"/>',
    inbox: '<path d="M2.5 9.5l1.8-5.5h7.4l1.8 5.5V13h-11z"/><path d="M2.5 9.5H6l.8 1.5h2.4l.8-1.5h3.5"/>',
    clock: '<circle cx="8" cy="8" r="5.5"/><path d="M8 5v3.2l2 1.3"/>',
  };
  const ico = (n, cls) => `<svg class="${cls || ''}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${I[n] || ''}</svg>`;
  const STI = { validated: 'check', running: 'spin', failed: 'x', blocked: 'warn', 'done-unverified': 'q', done: 'check' };
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const k = (n) => (n == null ? '–' : n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'k' : String(n));

  let S = null;            // last message
  let sel = (api.getState() || {}).sel || null;
  let view = { x: 0, y: 0, k: 1 };
  let userMoved = false;
  let prevStatus = {};
  let built = false;
  let timer = null;

  // ------------------------------------------------------------ layout
  function levels(nodes) {
    const by = new Map(nodes.map((n) => [n.id, n]));
    const depth = new Map();
    const d = (id, seen) => {
      if (depth.has(id)) return depth.get(id);
      if (seen.has(id)) return 0;
      seen.add(id);
      let v = 0;
      for (const p of (by.get(id) || {}).deps || []) if (by.has(p)) v = Math.max(v, d(p, seen) + 1);
      depth.set(id, v);
      return v;
    };
    const out = [];
    for (const n of nodes) (out[d(n.id, new Set())] = out[d(n.id, new Set())] || []).push(n);
    return out.filter(Boolean);
  }

  function layout(nodes) {
    const lv = levels(nodes);
    const maxRows = Math.max(1, ...lv.map((l) => l.length));
    const pos = {};
    lv.forEach((col, i) => col.forEach((n, j) => {
      pos[n.id] = { x: PAD + i * CW, y: PAD + 26 + (j + (maxRows - col.length) / 2) * RH, lvl: i };
    }));
    return { pos, lv, w: PAD * 2 + (lv.length - 1) * CW + NW, h: PAD * 2 + 26 + maxRows * RH };
  }

  // ------------------------------------------------------------ helpers
  function tokensOf(id) {
    const t = S.data.tokens && S.data.tokens.by_node && S.data.tokens.by_node[id];
    return t ? (t.total != null ? t.total : (t.input || 0) + (t.output || 0)) : null;
  }
  function elapsed(iso) {
    const t = Date.parse(iso);
    if (!t) return '–';
    let s = Math.max(0, Math.floor((Date.now() - t) / 1000));
    const h = Math.floor(s / 3600); s -= h * 3600;
    const m = Math.floor(s / 60); s -= m * 60;
    return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m ${String(s).padStart(2, '0')}s`;
  }
  function countUp(el, to) {
    const from = +el.dataset.v || 0;
    el.dataset.v = to;
    if (from === to || matchMedia('(prefers-reduced-motion: reduce)').matches) { el.textContent = el.dataset.fmt === 'k' ? k(to) : to; return; }
    const t0 = performance.now(), dur = 900;
    const step = (t) => {
      const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3), v = Math.round(from + (to - from) * e);
      el.textContent = el.dataset.fmt === 'k' ? k(v) : v;
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  // ------------------------------------------------------------ empty
  function renderEmpty() {
    built = false;
    const busy = S.run && S.run.running;
    app.innerHTML = `<div class="void"><div>
      <div class="orb"></div>
      <h1>${busy ? 'Planning…' : 'Nothing in orbit yet'}</h1>
      <p>${busy ? 'Claude is shaping the graph. It will land here live.' : 'Plan a task and watch the agent graph come alive.'}</p>
      <div class="actions">
        <button class="btn primary" data-cmd="plan">${ico('bulb')}Plan a task</button>
        <button class="btn" data-cmd="run">${ico('play')}Run</button>
        <button class="btn" data-cmd="chat">${ico('chat')}Planner chat</button>
      </div></div></div>`;
  }

  // ------------------------------------------------------------ shell
  function build() {
    built = true;
    userMoved = false;
    app.innerHTML = `
      <header class="hero" id="hero">
        <div class="ring"><svg width="92" height="92" viewBox="0 0 92 92">
          <defs><linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffd98a"/><stop offset=".5" stop-color="#f5b544"/><stop offset="1" stop-color="#ff7a59"/></linearGradient></defs>
          <circle class="trk" cx="46" cy="46" r="40" fill="none" stroke-width="7"/>
          <circle class="bar" id="ringBar" cx="46" cy="46" r="40" fill="none" stroke-width="7" stroke-dasharray="251.3" stroke-dashoffset="251.3"/></svg>
          <div class="lbl"><div><div class="pct" id="pct">0%</div><div class="sub" id="pctSub">0/0</div></div></div></div>
        <div style="min-width:0">
          <div class="brand"><b>sjck</b> mission control</div>
          <div class="goal" id="goal"></div>
          <div class="chips" id="chips"></div>
        </div>
        <div class="actions" id="heroActs"></div>
      </header>
      <section class="stats" id="stats"></section>
      <section class="main">
        <div class="panel graph">
          <div class="ph"><h3>${ico('graph')} Agent graph <span class="n" id="gcount"></span></h3><span class="chip" id="mode"></span></div>
          <div class="stage" id="stage">
            <div class="world" id="world"><svg class="edges" id="edges"></svg></div>
            <div class="legend">${['validated', 'running', 'pending', 'failed', 'blocked'].map((s) => `<span><i style="background:${COL[s]}"></i>${s}</span>`).join('')}</div>
            <div class="zoom"><button data-z="in" title="Zoom in">${ico('plus')}</button><button data-z="out" title="Zoom out">${ico('minus')}</button><button data-z="fit" title="Fit">${ico('fit')}</button></div>
          </div>
        </div>
        <aside class="side" id="side"></aside>
      </section>
      <div class="scrim" id="scrim"></div>
      <aside class="drawer" id="drawer"></aside>`;
    wireStage();
  }

  // ------------------------------------------------------------ hero + stats
  function renderHero() {
    const st = S.data.state, nodes = st.nodes;
    const v = nodes.filter((n) => n.status === 'validated').length;
    const pct = nodes.length ? Math.round((v / nodes.length) * 100) : 0;
    document.getElementById('ringBar').style.strokeDashoffset = String(251.3 * (1 - pct / 100));
    document.getElementById('pct').textContent = pct + '%';
    document.getElementById('pctSub').textContent = `${v}/${nodes.length} nodes`;
    document.getElementById('goal').textContent = st.goal || 'sjck run';
    const running = st.status === 'running' || (S.run && S.run.running);
    document.getElementById('hero').classList.toggle('is-running', running);
    const status = st.status || 'idle';
    document.getElementById('chips').innerHTML =
      `<span class="chip st ${running ? 'live' : ''}" style="--c:${COL[status] || 'var(--fg2)'}"><i class="dot"></i>${esc(status)}</span>` +
      (st.mode ? `<span class="chip" title="${esc(st.mode_reason || '')}">mode ${esc(st.mode)}</span>` : '') +
      (st.started ? `<span class="chip">${ico('clock', '').replace('<svg', '<svg width="12" height="12"')}<span id="elapsed">${elapsed(st.started)}</span></span>` : '') +
      (st.plan_score && st.plan_score.verdict ? `<span class="chip st" style="--c:${st.plan_score.verdict === 'ok' ? 'var(--ok)' : st.plan_score.verdict === 'reject' ? 'var(--fail)' : 'var(--block)'}">plan ${esc(st.plan_score.verdict)}</span>` : '');
    const acts = [];
    if (st.status === 'planned') acts.push(`<button class="btn primary" data-cmd="approvePlan">${ico('play')}Approve & run</button>`);
    if (S.run && S.run.running) acts.push(`<button class="btn danger" data-cmd="stop">${ico('stop')}Stop</button>`);
    else if (st.status !== 'planned') acts.push(`<button class="btn primary" data-cmd="run">${ico('play')}Run</button>`);
    acts.push(`<button class="btn" data-cmd="plan">${ico('bulb')}Plan</button>`, `<button class="btn" data-cmd="chat">${ico('chat')}Chat</button>`, `<button class="btn" data-cmd="log" title="Run log">${ico('log')}</button>`);
    document.getElementById('heroActs').innerHTML = acts.join('');
    clearInterval(timer);
    if (st.started && st.status === 'running') timer = setInterval(() => { const e = document.getElementById('elapsed'); if (e) e.textContent = elapsed(st.started); }, 1000);
  }

  function renderStats() {
    const st = S.data.state, m = st.metrics || {}, nodes = st.nodes;
    const tt = (S.data.tokens && S.data.tokens.totals) || {};
    const calls = m.tool_calls != null ? m.tool_calls : nodes.reduce((a, n) => a + ((n.usage && n.usage.tool_calls) || 0), 0);
    const budget = nodes.reduce((a, n) => a + ((n.budget && n.budget.tool_calls) || 0), 0);
    const waiting = (S.inbox ? S.inbox.findings.filter((f) => !f.decided).length + S.inbox.crs.filter((c) => c.status === 'proposed' && !c.decided).length : 0);
    const running = nodes.filter((n) => n.status === 'running').length;
    const tot = tt.total || 0;
    const seg = (x, c) => (tot && x ? `<i style="width:${(x / tot) * 100}%;background:${c}"></i>` : '');
    const tiles = [
      { k: 'Tokens', v: tot, fmt: 'k', g: 'tok', meter: seg(tt.input, CAT[0]) + seg(tt.output, CAT[1]) + seg(tt.cache_read, CAT[2]), title: `input ${k(tt.input)} · output ${k(tt.output)} · cache ${k(tt.cache_read)}` },
      { k: 'Tool calls', v: calls, g: 'tool', small: budget ? `/ ${budget}` : '', meter: budget ? `<i style="width:${Math.min(100, (calls / budget) * 100)}%;background:var(--accent)"></i>` : '' },
      { k: 'Agents live', v: running, g: 'bot', small: m.subagents != null ? `· ${m.subagents} spawned` : '', hot: running > 0 },
      { k: 'Waiting for you', v: waiting, g: 'inbox', hot: waiting > 0 },
      { k: 'Validator fails', v: m.validator_fails || 0, g: 'x', small: m.watchdog_warnings ? `· ${m.watchdog_warnings} watchdog` : '' },
    ];
    const box = document.getElementById('stats');
    if (box.children.length !== tiles.length) {
      box.innerHTML = tiles.map((t, i) => `<div class="stat" data-i="${i}">${ico(t.g, 'glyph')}<div class="k">${t.k}</div><div class="v"><span class="num" data-fmt="${t.fmt || ''}">0</span><small></small></div><div class="meter"></div></div>`).join('');
    }
    tiles.forEach((t, i) => {
      const el = box.children[i];
      el.classList.toggle('hot', !!t.hot);
      el.title = t.title || '';
      countUp(el.querySelector('.num'), t.v || 0);
      el.querySelector('small').textContent = t.small || '';
      const mt = el.querySelector('.meter');
      mt.style.display = t.meter ? '' : 'none';
      mt.innerHTML = t.meter || '';
    });
  }

  // ------------------------------------------------------------ graph
  function renderGraph() {
    const nodes = S.data.state.nodes;
    const L = layout(nodes);
    const world = document.getElementById('world');
    const edges = document.getElementById('edges');
    world.style.width = L.w + 'px';
    world.style.height = L.h + 'px';
    edges.setAttribute('width', L.w);
    edges.setAttribute('height', L.h);
    document.getElementById('gcount').textContent = `${nodes.length} nodes · ${L.lv.length} levels`;
    const mode = document.getElementById('mode');
    mode.textContent = S.data.state.mode ? `mode ${S.data.state.mode}` : 'graph';

    world.querySelectorAll('.lvl').forEach((e) => e.remove());
    L.lv.forEach((_, i) => {
      const t = document.createElement('div');
      t.className = 'lvl';
      t.style.left = PAD + i * CW + 'px';
      t.style.top = PAD - 6 + 'px';
      t.textContent = `level ${i}`;
      world.appendChild(t);
    });

    const by = new Map(nodes.map((n) => [n.id, n]));
    let paths = '';
    for (const n of nodes) {
      for (const d of n.deps || []) {
        const a = L.pos[d], b = L.pos[n.id];
        if (!a || !b) continue;
        const x1 = a.x + NW, y1 = a.y + NH / 2 - 8, x2 = b.x, y2 = b.y + NH / 2 - 8, mx = (x1 + x2) / 2;
        const src = by.get(d).status;
        const cls = n.status === 'running' ? 'live' : n.status === 'failed' || n.status === 'blocked' ? 'bad' : src === 'validated' ? 'ok' : '';
        paths += `<path class="edge ${cls}" d="M${x1} ${y1} C${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}"/>`;
      }
    }
    edges.innerHTML = paths;

    const seen = new Set();
    for (const n of nodes) {
      seen.add(n.id);
      let el = world.querySelector(`.node[data-id="${CSS.escape(n.id)}"]`);
      if (!el) {
        el = document.createElement('div');
        el.dataset.id = n.id;
        world.appendChild(el);
      }
      const p = L.pos[n.id];
      el.style.left = p.x + 'px';
      el.style.top = p.y + 'px';
      const b = n.budget && n.budget.tool_calls, u = (n.usage && n.usage.tool_calls) || 0;
      const frac = b ? Math.min(1, u / b) : n.status === 'validated' ? 1 : 0;
      const tok = tokensOf(n.id);
      el.className = `node ${n.status || 'pending'}${sel === n.id ? ' sel' : ''}`;
      el.title = `${n.id} — ${n.title || ''}`;
      el.innerHTML = `
        <div class="top"><span class="id">${esc(n.id)}${n.attempts ? ` · try ${n.attempts + 1}` : ''}</span>${ico(STI[n.status] || 'dot', 'ico')}</div>
        <div class="t">${esc(n.title || n.agent || '')}</div>
        <div class="meta">${n.model && n.model !== 'inherit' ? `<span class="m">${esc(n.model)}${n.effort ? '/' + esc(n.effort) : ''}</span>` : ''}${b ? `<span>${u}/${b}</span>` : ''}${tok ? `<span>${k(tok)} tok</span>` : ''}</div>
        <div class="bud"><i class="${frac >= 0.8 && n.status === 'running' ? 'warn' : ''}" style="width:${frac * 100}%"></i></div>`;
      const was = prevStatus[n.id];
      if (was && was !== n.status && n.status === 'validated') { el.classList.add('pop'); setTimeout(() => el.classList.remove('pop'), 700); }
      prevStatus[n.id] = n.status;
    }
    world.querySelectorAll('.node').forEach((e) => { if (!seen.has(e.dataset.id)) e.remove(); });
    if (!userMoved) fit(false, L);
  }

  // ------------------------------------------------------------ pan / zoom
  function apply(anim) {
    const w = document.getElementById('world');
    w.classList.toggle('anim', !!anim);
    w.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.k})`;
  }
  function fit(anim, L) {
    const stage = document.getElementById('stage');
    if (!stage) return;
    L = L || layout(S.data.state.nodes);
    const sw = stage.clientWidth, sh = stage.clientHeight - 30;
    if (!sw || !sh) return;
    view.k = Math.max(0.35, Math.min(1.25, Math.min(sw / L.w, sh / L.h)));
    view.x = (sw - L.w * view.k) / 2;
    view.y = Math.max(0, (sh - L.h * view.k) / 2);
    apply(anim);
  }
  function zoomAt(f, cx, cy) {
    const nk = Math.max(0.3, Math.min(2.2, view.k * f));
    view.x = cx - ((cx - view.x) * nk) / view.k;
    view.y = cy - ((cy - view.y) * nk) / view.k;
    view.k = nk;
    userMoved = true;
    apply(false);
  }
  function wireStage() {
    const stage = document.getElementById('stage');
    let drag = null;
    stage.addEventListener('pointerdown', (e) => {
      if (e.target.closest('.node, .zoom')) return;
      drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
      stage.setPointerCapture(e.pointerId);
      stage.classList.add('drag');
    });
    stage.addEventListener('pointermove', (e) => {
      if (!drag) return;
      view.x = drag.vx + e.clientX - drag.x;
      view.y = drag.vy + e.clientY - drag.y;
      userMoved = true;
      apply(false);
    });
    const end = () => { drag = null; stage.classList.remove('drag'); };
    stage.addEventListener('pointerup', end);
    stage.addEventListener('pointercancel', end);
    stage.addEventListener('wheel', (e) => {
      e.preventDefault();
      const r = stage.getBoundingClientRect();
      zoomAt(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    new ResizeObserver(() => { if (!userMoved && S && S.data) fit(false); }).observe(stage);
  }

  // ------------------------------------------------------------ side panels
  function renderSide() {
    const st = S.data.state, inbox = S.inbox || { findings: [], crs: [] };
    const out = [];
    if (st.status === 'planned') {
      out.push(`<div class="plancard"><h4>Plan ready for review</h4><p>${st.nodes.length} nodes across ${levels(st.nodes).length} levels. Approve to start the run.</p>
        <div class="actions" style="justify-content:flex-start"><button class="btn primary sm" data-cmd="approvePlan">${ico('play')}Approve & run</button><button class="btn sm" data-cmd="chat">${ico('chat')}Discuss</button></div></div>`);
    }
    const waiting = [];
    for (const c of inbox.crs.slice().reverse()) {
      const open = c.status === 'proposed' && !c.decided;
      waiting.push(`<div class="item" style="--c:${open ? 'var(--plan)' : 'var(--fg3)'}"><i class="sev"></i><div>
        <div class="w">${esc(c.id)} · ${esc(c.summary || 'change request')}</div><div class="s">${esc((c.ops || []).join(', '))}</div>
        ${open ? `<div class="acts"><button class="btn sm" data-dec="cr:${esc(c.id)}:apply">${ico('check')}Apply</button><button class="btn sm" data-dec="cr:${esc(c.id)}:reject">${ico('x')}Reject</button></div>` : `<div class="done-tag">${esc(c.decided ? 'decided: ' + c.decided : c.status)}</div>`}</div></div>`);
    }
    for (const f of inbox.findings) {
      waiting.push(`<div class="item" style="--c:${SEV[f.severity] || 'var(--fg3)'}"><i class="sev"></i><div>
        <div class="w">${esc(f.what || f.id)}</div><div class="s">${esc(f.id)} · ${esc(f.kind || '')} · from ${esc(f.from || '?')}${f.file ? ` · <span class="tag link" data-file="${esc(f.file)}">${esc(f.file)}</span>` : ''}</div>
        ${f.decided || (f.status && f.status !== 'proposed') ? `<div class="done-tag">${esc(f.decided ? 'decided: ' + f.decided : f.status)}</div>` : `<div class="acts"><button class="btn sm" data-dec="finding:${esc(f.id)}:accept">${ico('check')}Accept</button><button class="btn sm" data-dec="finding:${esc(f.id)}:defer">${ico('clock')}Later</button><button class="btn sm" data-dec="finding:${esc(f.id)}:reject">${ico('x')}Reject</button></div>`}</div></div>`);
    }
    const nOpen = inbox.findings.filter((f) => !f.decided && (!f.status || f.status === 'proposed')).length + inbox.crs.filter((c) => c.status === 'proposed' && !c.decided).length;
    out.push(`<div class="panel"><div class="ph"><h3>${ico('inbox')} Inbox <span class="n">${nOpen || ''}</span></h3></div><div class="list">${waiting.join('') || '<div class="empty">Nothing waiting for you ✦</div>'}</div></div>`);

    const ps = st.plan_score;
    if (ps) {
      const crit = (st.critic || []).slice(-1)[0];
      out.push(`<div class="panel"><div class="ph"><h3>Plan score</h3></div><div class="score">
        <div><b>${ps.width ?? '–'}</b><span>width</span></div><div><b>${ps.critical_path ?? '–'}</b><span>critical</span></div><div><b style="color:${ps.file_overlap ? 'var(--block)' : 'var(--ok)'}">${ps.file_overlap ?? '–'}</b><span>overlap</span></div></div>
        ${crit ? `<div class="critic"><span class="chip st" style="--c:${crit.verdict === 'approve' ? 'var(--ok)' : 'var(--block)'}">critic ${esc(crit.verdict)} · r${esc(crit.round)}</span> ${esc(crit.resolution || (crit.points || []).join('; '))}</div>` : ''}</div>`);
    }

    const evs = [];
    for (const line of (st.log || []).slice().reverse().slice(0, 30)) {
      const m = /^(\d\d:\d\d)\s+(?:([A-Z]+\d+)\s+)?(.*)$/.exec(line) || [];
      const txt = m[3] || line;
      const c = /fail|error/i.test(txt) ? 'var(--fail)' : /watchdog|nudge|budget/i.test(txt) ? 'var(--block)' : /validated|done/i.test(txt) ? 'var(--ok)' : 'var(--accent)';
      evs.push(`<div class="ev" style="--c:${c}"><i class="b"></i><span class="tm">${esc(m[1] || '')}</span><span class="x">${m[2] ? `<span class="nid">${esc(m[2])}</span>` : ''}${esc(txt)}</span></div>`);
    }
    out.push(`<div class="panel"><div class="ph"><h3>${ico('clock')} Activity</h3></div><div class="tl">${evs.join('') || '<div class="empty">No events yet</div>'}</div></div>`);
    document.getElementById('side').innerHTML = out.join('');
  }

  // ------------------------------------------------------------ drawer
  function renderDrawer() {
    const dr = document.getElementById('drawer'), scrim = document.getElementById('scrim');
    const n = sel && S.data.state.nodes.find((x) => x.id === sel);
    dr.classList.toggle('on', !!n);
    scrim.classList.toggle('on', !!n);
    document.querySelectorAll('.node').forEach((e) => e.classList.toggle('sel', e.dataset.id === sel));
    if (!n) return;
    dr.style.setProperty('--c', COL[n.status] || 'var(--pend)');
    const b = n.budget && n.budget.tool_calls, u = (n.usage && n.usage.tool_calls) || 0;
    const t = S.data.tokens && S.data.tokens.by_node && S.data.tokens.by_node[n.id];
    const cats = t && t.categories ? Object.entries(t.categories).filter(([, v]) => v > 0) : [];
    const ct = cats.reduce((a, [, v]) => a + v, 0);
    const changed = (S.changed && S.changed[n.id]) || [];
    const dependents = S.data.state.nodes.filter((x) => (x.deps || []).includes(n.id)).map((x) => x.id);
    const tag = (id) => `<span class="tag link" data-node="${esc(id)}">${esc(id)}</span>`;
    dr.innerHTML = `
      <div class="dh"><button class="x" data-close title="Close">${ico('x')}</button>
        <div class="id">${esc(n.id)} · ${esc(n.agent || 'agent')}</div><h2>${esc(n.title || n.id)}</h2>
        <div class="chips"><span class="chip st ${n.status === 'running' ? 'live' : ''}" style="--c:${COL[n.status] || 'var(--fg2)'}"><i class="dot"></i>${esc(n.status)}</span>
        ${n.model ? `<span class="chip">${esc(n.model)}${n.effort ? ' / ' + esc(n.effort) : ''}</span>` : ''}${n.attempts ? `<span class="chip">attempt ${n.attempts + 1}</span>` : ''}</div></div>
      <div class="db">
        <div class="sec kv"><div><b>${u}${b ? `<small style="color:var(--fg3)"> / ${b}</small>` : ''}</b><span>tool calls</span></div><div><b>${k(t && t.total)}</b><span>tokens</span></div></div>
        ${b ? `<div class="sec"><h5>Budget</h5><div class="bigbar"><i style="width:${Math.min(100, (u / b) * 100)}%"></i></div></div>` : ''}
        ${cats.length ? `<div class="sec"><h5>Where the tokens went</h5><div class="stack">${cats.map(([, v], i) => `<i style="width:${(v / ct) * 100}%;background:${CAT[i % CAT.length]}"></i>`).join('')}</div>
          <div class="stackl">${cats.map(([c, v], i) => `<span><i style="background:${CAT[i % CAT.length]}"></i>${esc(c.replace(/_/g, ' '))} ${k(v)}</span>`).join('')}</div></div>` : ''}
        ${(n.deps || []).length ? `<div class="sec"><h5>After</h5><div class="tags">${n.deps.map(tag).join('')}</div></div>` : ''}
        ${dependents.length ? `<div class="sec"><h5>Unblocks</h5><div class="tags">${dependents.map(tag).join('')}</div></div>` : ''}
        ${(n.files || []).length ? `<div class="sec"><h5>Card files</h5><div class="tags">${n.files.map((f) => `<span class="tag link" data-file="${esc(f)}">${esc(f)}</span>`).join('')}</div></div>` : ''}
        ${changed.length ? `<div class="sec"><h5>Changed</h5><div class="tags">${changed.map((f) => `<span class="tag link" data-file="${esc(f)}">${esc(f)}</span>`).join('')}</div></div>` : ''}
        ${(n.assumptions || []).length ? `<div class="sec"><h5>Assumptions</h5><ul class="as">${n.assumptions.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></div>` : ''}
      </div>
      <div class="df"><button class="btn primary" data-card="${esc(n.id)}">${ico('file')}Open card</button>${changed.length ? `<button class="btn" data-diff="${esc(n.id)}">${ico('diff')}Show diff</button>` : ''}</div>`;
  }
  function select(id) {
    sel = id;
    api.setState({ sel });
    renderDrawer();
  }

  // ------------------------------------------------------------ events
  document.addEventListener('click', (e) => {
    const t = e.target.closest('[data-cmd],[data-dec],[data-card],[data-diff],[data-file],[data-node],[data-close],[data-z],.node,#scrim');
    if (!t) return;
    if (t.dataset.cmd) send({ type: 'command', name: t.dataset.cmd });
    else if (t.dataset.dec) {
      const [kind, id, action] = t.dataset.dec.split(':');
      t.closest('.acts').innerHTML = `<div class="done-tag">${esc(action)} — sent</div>`;
      send({ type: 'decide', kind, id, action });
    } else if (t.dataset.card) send({ type: 'openCard', id: t.dataset.card });
    else if (t.dataset.diff) send({ type: 'nodeDiff', id: t.dataset.diff });
    else if (t.dataset.file) send({ type: 'openFile', file: t.dataset.file });
    else if (t.dataset.node) select(t.dataset.node);
    else if (t.dataset.z) {
      const st = document.getElementById('stage');
      if (t.dataset.z === 'fit') { userMoved = false; fit(true); } else zoomAt(t.dataset.z === 'in' ? 1.2 : 1 / 1.2, st.clientWidth / 2, st.clientHeight / 2);
    } else if (t.classList.contains('node')) select(sel === t.dataset.id ? null : t.dataset.id);
    else select(null);
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && sel) select(null); });

  function render() {
    if (!S || !S.data) return renderEmpty();
    if (!built) build();
    renderHero();
    renderStats();
    renderGraph();
    renderSide();
    renderDrawer();
  }

  window.addEventListener('message', (e) => {
    const m = e.data;
    if (m && m.type === 'data') { S = m; render(); }
  });
  window.__sjckRender = (m) => { S = m; render(); }; // used by the preview harness
  send({ type: 'ready' });
})();
