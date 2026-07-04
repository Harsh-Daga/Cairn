/* Cairn session detail — 3-panel flight recorder (Part 16). Vanilla JS + D3. */
'use strict';

const params = new URLSearchParams(location.search);
const runId = params.get('id');
let data = null, selectedTurn = 0, activeTab = 'turns', drawerTab = 'strata';
let profile = null, graphSim = null;

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
/* Sanitized HTML assignment — every dynamic injection routes here. */
function setHTML(el, html) { if (!el) return; if (window.DOMPurify) { el.innerHTML = window.DOMPurify.sanitize(html); return; } el.textContent = String(html ?? ''); }
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function shade(hex,pct){const h=hex.replace('#','');if(h.length<6)return hex;const n=parseInt(h,16);let r=(n>>16)&255,g=(n>>8)&255,b=n&255;r=Math.min(255,Math.max(0,r+pct));g=Math.min(255,Math.max(0,g+pct));b=Math.min(255,Math.max(0,b+pct));return '#'+((1<<24)+(r<<16)+(g<<8)+b).toString(16).slice(1);}

const REGION_ORDER = ['system','tool_schema','tool_result','retrieved','user','assistant_history'];
const REGION_HUE = { system:'--copper', tool_schema:'--patina', tool_result:'--ochre', retrieved:'--cinder', user:'--copper', assistant_history:'--malachite' };
function hue(r, light) { const base = cssVar(REGION_HUE[r]||'--cinder'); return light ? shade(base, 28) : base; }

function fmtCost(n){return n!=null?`$${Number(n).toFixed(4)}`:'N/A';}
function fmtTokens(n){if(n==null)return 'N/A';if(n>=1e6)return `${(n/1e6).toFixed(2)}M`;if(n>=1e3)return `${(n/1e3).toFixed(1)}K`;return String(n);}
function fmtDate(iso){if(!iso)return '—';return new Date(iso).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});}
function badge(s){return `<span class="source-badge">${esc(s)}</span>`;}
function toolColor(n){return ['read','edit','bash','search','delete','sub_agent'].includes(n)?n:'other';}
function toast(msg,kind=''){const el=document.createElement('div');el.className=`toast ${kind}`;setHTML(el,msg);$('#toast-stack').appendChild(el);setTimeout(()=>{el.style.opacity='0';setTimeout(()=>el.remove(),300);},4200);}

function centerBody() {
  let el = $('#center-body');
  if (!el) {
    const center = $('#center');
    if (!center) return null;
    el = document.createElement('div');
    el.id = 'center-body';
    center.appendChild(el);
  }
  return el;
}

function seqForEventId(eventId) {
  if (eventId == null || !data) return null;
  const all = (data.turns || []).flatMap(t => t.events || []);
  const hit = all.find(e => e.event_id === eventId || e.seq === eventId);
  return hit ? hit.seq : null;
}

function renderIdealPathPanel(diag, ideal) {
  const savings = Number(diag.ideal_path_savings_tokens || 0);
  if (!ideal || savings <= 0) return '';
  const reads = ideal.reads_actual ?? 0;
  const edited = (ideal.edited || []).length;
  const idealReads = ideal.reads_ideal ?? 0;
  return `<div class="ideal-path-panel"><span class="label">Ideal path</span>read ${reads} files; the ${edited} you edited were reachable in ${idealReads}</div>`;
}

function renderTrajectoryTimeline(diag) {
  const events = (data.turns || []).flatMap(t => t.events || []).filter(e => e.type === 'tool_call' || e.type === 'tool_result');
  if (!events.length) return '<div class="autopsy-sub">No tool events for trajectory.</div>';
  const failSeq = seqForEventId(diag.failure_origin_event_id);
  const cascadeSeq = seqForEventId(diag.cascade_root_event_id);
  const blastTokens = Number(diag.cascade_blast_tokens || 0);
  const W = Math.max(420, events.length * 28 + 40), H = 56, pad = 20;
  const step = events.length > 1 ? (W - 2 * pad) / (events.length - 1) : 0;
  let cascadeEnd = events.length - 1;
  if (cascadeSeq != null && blastTokens > 0) {
    let acc = 0;
    let startIdx = events.findIndex(e => e.seq === cascadeSeq);
    if (startIdx < 0) startIdx = 0;
    for (let i = startIdx; i < events.length; i++) {
      acc += Number(events[i].waste_tokens || 0) + Number(events[i].input_tokens || 0);
      cascadeEnd = i;
      if (acc >= blastTokens) break;
    }
  }
  let svg = `<svg class="trajectory-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">`;
  svg += `<line class="trajectory-track" x1="${pad}" y1="${H/2}" x2="${W-pad}" y2="${H/2}"/>`;
  if (cascadeSeq != null) {
    const i0 = events.findIndex(e => e.seq === cascadeSeq);
    const i1 = cascadeEnd;
    if (i0 >= 0 && i1 >= i0) {
      const x0 = pad + i0 * step;
      const x1 = pad + i1 * step + 8;
      svg += `<rect class="trajectory-cascade" x="${x0.toFixed(1)}" y="12" width="${Math.max(8, x1 - x0).toFixed(1)}" height="${H-24}" rx="4"/>`;
    }
  }
  events.forEach((e, i) => {
    const x = pad + i * step;
    let cls = 'trajectory-dot normal';
    if (failSeq != null && e.seq === failSeq) cls = 'trajectory-dot failure';
    else if (cascadeSeq != null && e.seq === cascadeSeq) cls = 'trajectory-dot cascade-root';
    svg += `<circle class="${cls}" cx="${x.toFixed(1)}" cy="${H/2}" r="5"/>`;
  });
  svg += '</svg>';
  return `<div class="trajectory-wrap">${svg}<div class="trajectory-legend"><span>failure origin</span><span>cascade root</span><span>blast radius</span></div></div>`;
}

function renderAutopsy() {
  const mount = $('#autopsy-mount');
  if (!mount || !data) return;
  const diag = data.diagnostics;
  const nEvents = data.event_count_for_diagnosis ?? (data.run?.event_count || 0);
  if (!diag) {
    setHTML(mount, `<div class="autopsy-panel"><div class="right-title">Session autopsy</div><p class="autopsy-sub">Not enough signal to diagnose this session — ${nEvents} event${nEvents === 1 ? '' : 's'}.</p></div>`);
    return;
  }
  const conf = data.confidence || {};
  const confNote = (conf.estimation_method && conf.estimation_method !== 'exact' && conf.estimation_error_pct != null)
    ? `<span class="confidence-chip">±${Math.round(conf.estimation_error_pct)}% est.</span>` : '';
  const label = (diag.outcome_label || 'unknown').replace(/_/g, ' ');
  const primary = diag.primary_category ? diag.primary_category.replace(/_/g, ' ') : null;
  const secondary = diag.secondary_category ? diag.secondary_category.replace(/_/g, ' ') : null;
  let badges = `<span class="diag-badge outcome">${esc(label)}</span>`;
  if (primary) badges += `<span class="diag-badge category">${esc(primary)}</span>`;
  if (secondary) badges += `<span class="diag-badge category">${esc(secondary)}</span>`;
  const narrative = data.narrative ? `<p class="autopsy-sub">${esc(data.narrative)}</p>` : '';
  const agentBar = renderAgentCostBar(data.agents);
  const timeline = renderTrajectoryTimeline(diag);
  const ideal = renderIdealPathPanel(diag, data.ideal_path);
  const rewind = data.rewind_suggestion;
  const rewindHtml = rewind ? `<div class="ideal-path-panel"><span class="label">Rewind suggestion</span><code>${esc(rewind.command || '')}</code><div style="margin-top:6px;color:var(--cinder);font-size:10.5px">${esc(rewind.note || '')}</div></div>` : '';
  setHTML(mount, `<div class="autopsy-panel"><div class="right-title">Session autopsy ${confNote}</div>${narrative}${agentBar}<div class="autopsy-badges">${badges}</div>${timeline}${ideal}${rewindHtml}</div>`);
}

function renderAgentCostBar(agents) {
  if (!agents || agents.length <= 1) return '';
  const totalCost = agents.reduce((a, g) => a + Number(g.cost_estimate || 0), 0);
  const subagents = agents.filter(g => g.agent_lane === 'subagent' || g.agent_lane === 'sidechain');
  const subCost = subagents.reduce((a, g) => a + Number(g.cost_estimate || 0), 0);
  const subPct = totalCost > 0 ? Math.round((subCost / totalCost) * 100) : null;
  const colors = ['var(--copper)', 'var(--patina)', 'var(--ochre)', 'var(--malachite)', 'var(--cinnabar)'];
  const barW = 100 / agents.length;
  let segments = '';
  agents.forEach((g, i) => {
    const label = `${g.agent_lane || 'agent'} · ${fmtTokens(g.tokens)}`;
    segments += `<div class="agent-cost-seg" style="width:${barW}%;background:${colors[i % colors.length]}" data-tip="${esc(label)} · ${fmtCost(g.cost_estimate)}"></div>`;
  });
  const caption = subPct != null
    ? `${subagents.length} subagents · ${subPct}% of session cost`
    : `${agents.length} agents · token split shown`;
  return `<div class="chart-card agent-cost-card"><div class="chart-card-title">Cost by agent</div><div class="agent-cost-bar">${segments}</div><div class="agent-cost-caption">${esc(caption)}</div></div>`;
}

async function load() {
  if (!runId) { document.body.textContent = 'No session id'; return; }
  try {
    data = await fetch(`/api/session/${runId}`).then(r => r.json());
    if (data.error) { setHTML($('.session-app'), `<div class="empty-block">Session not found.<br><a href="/" style="color:var(--copper)">Back to dashboard</a></div>`); return; }
    profile = await fetch(`/api/profile/${runId}`).then(r => r.json()).catch(() => null);
    render();
  } catch (e) { setHTML($('.session-app'), `<div class="empty-block">Couldn't load session: ${esc(e.message)}<br>Close other agents holding the ledger lock and retry.</div>`); }
}

/* ── Stratigraphic column (SVG) for the run ───────────────────── */
function stackFor(regions, t) {
  return REGION_ORDER.map(rn => {
    const rs = regions.filter(r => r.region === rn && r.first_turn <= t && r.last_seen_turn >= t);
    if (!rs.length) return null;
    const seen = new Set(); let toks = 0;
    rs.forEach(r => { if (!seen.has(r.content_hash)) { seen.add(r.content_hash); toks += r.tokens; } });
    return { region: rn, tokens: toks, first_turn: Math.min(...rs.map(r => r.first_turn)), last_turn: Math.max(...rs.map(r => r.last_seen_turn)), content_hash: rs[0].content_hash };
  }).filter(Boolean);
}
function strataColumnSVG(regions, maxTurn, W, H) {
  if (!regions || !regions.length) return `<div class="empty-block">No context regions for this run.</div>`;
  const pad = 24, turns = Math.max(maxTurn || 1, ...regions.map(r => r.last_seen_turn));
  const colW = (W - 2 * pad) / turns, barW = Math.max(3, colW - 2);
  const stacks = []; for (let t = 1; t <= turns; t++) { const st = stackFor(regions, t); if (st.length) stacks.push({ t, st, total: st.reduce((a, r) => a + r.tokens, 0) }); }
  const maxStack = Math.max(1, ...stacks.map(s => s.total));
  let rects = '';
  stacks.forEach(({ t, st }) => { let y = H - pad; const x = pad + (t - 1) * colW + colW / 2 - barW / 2;
    st.forEach(r => { const h = Math.max(1, (r.tokens / maxStack) * (H - 2 * pad));
      rects += `<rect x="${x.toFixed(1)}" y="${(y-h).toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" fill="${hue(r.region,false)}" stroke="${cssVar('--quartz-vein')}" stroke-width="1"/>`;
      rects += `<rect x="${x.toFixed(1)}" y="${(y-h).toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(1,h*0.35).toFixed(1)}" fill="${hue(r.region,true)}" opacity="0.45"/>`;
      if (r.first_turn < r.last_seen_turn && r.last_seen_turn === t) rects += `<line x1="${x.toFixed(1)}" y1="${(y-h).toFixed(1)}" x2="${(x+barW).toFixed(1)}" y2="${(y-h).toFixed(1)}" stroke="${cssVar('--copper')}" stroke-width="1" opacity="0.7"/>`;
      y -= h; }); });
  return `<svg class="drawer-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet"><text x="4" y="14" fill="${cssVar('--ash')}" font-size="9" font-family="var(--font-mono)">tokens</text><text x="${W-pad}" y="14" text-anchor="end" fill="${cssVar('--ash')}" font-size="9" font-family="var(--font-mono)">turn ${turns}</text>${rects}</svg>`;
}

/* ── Radar (D3) ───────────────────────────────────────────────── */
function radarInto(container, labels, current, baseline, drift) {
  setHTML(container, '');
  if (!labels || !current) { setHTML(container, `<div class="empty-block">No fingerprint for this session.</div>`); return; }
  const W = 280, H = 280, cx = W/2, cy = H/2, R = 96, axes = labels.slice(0, 8);
  const svg = d3.select(container).append('svg').attr('width', '100%').attr('height', H).attr('viewBox', `0 0 ${W} ${H}`);
  const max = Math.max(1, ...current.slice(0, 8), ...(baseline || []).slice(0, 8));
  const pt = (i, v) => { const a = -Math.PI/2 + i*(2*Math.PI/axes.length); return [cx + Math.cos(a)*(v/max)*R, cy + Math.sin(a)*(v/max)*R]; };
  axes.forEach((l, i) => { const [x, y] = pt(i, max); svg.append('line').attr('x1', cx).attr('y1', cy).attr('x2', x).attr('y2', y).attr('stroke', cssVar('--quartz-vein')).attr('stroke-width', 1);
    svg.append('text').attr('x', x + (x > cx+2 ? 4 : x < cx-2 ? -4 : 0)).attr('y', y + (y > cy+2 ? 11 : y < cy-2 ? -3 : 0)).attr('text-anchor', x > cx+2 ? 'start' : x < cx-2 ? 'end' : 'middle').attr('fill', cssVar('--cinder')).attr('font-family', 'var(--font-mono)').attr('font-size', 8).text(l); });
  const poly = (vals, color, fill, op) => { const pts = vals.map((v, i) => pt(i, v).join(',')).join(' '); svg.append('polygon').attr('points', pts).attr('stroke', color).attr('stroke-width', 1.5).attr('fill', fill).attr('fill-opacity', op); };
  if (baseline) poly(baseline.slice(0, 8), cssVar('--patina'), cssVar('--patina'), 0.08);
  poly(current.slice(0, 8), cssVar('--copper'), cssVar('--copper'), 0.22);
  if (drift) svg.append('circle').attr('cx', cx).attr('cy', cy).attr('r', R).attr('fill', 'none').attr('stroke', cssVar('--cinnabar')).attr('stroke-width', 1.5).attr('stroke-dasharray', '5 4');
}

/* ── Topbar ───────────────────────────────────────────────────── */
function renderTopbar() {
  const r = data.run;
  setHTML($('#session-topbar-meta'), `${badge(r.source)} <span class="mono">${esc(r.model || '—')}</span> <span>${fmtDate(r.started_at)}</span> <span>${r.event_count || 0} events</span> <span class="mono">${fmtCost(r.total_cost)}</span>`);
  $('#btn-export')?.addEventListener('click', async () => {
    try { const res = await fetch('/api/action/share', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_id: runId }) }).then(r => r.json());
      if (res.ok && res.html) { const blob = new Blob([res.html], { type: 'text/html' }); const u = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = u; a.download = `cairn-session-${runId.slice(0,8)}.html`; a.click(); URL.revokeObjectURL(u); toast('Exported scrubbed HTML', 'good'); }
      else toast('Export failed: ' + (res.error || 'unknown'), 'error');
    } catch (e) { toast('Export failed: ' + e.message, 'error'); }
  });
}

/* ── Left sidebar ─────────────────────────────────────────────── */
const LEFT_TABS = ['turns','tools','files','graph','waste','context','fingerprint'];
function renderSidebar() {
  const r = data.run, hasCost = r.has_cost;
  const usage = hasCost ? `${fmtTokens(r.total_input_tokens)} in<br>${fmtTokens(r.total_output_tokens)} out<br>${fmtTokens(r.cache_read_tokens || 0)} cache<br><strong style="color:var(--bone)">${fmtCost(r.total_cost)}</strong>` : `<span class="na">N/A tokens — ${esc(r.source)} doesn't expose usage</span>`;
  setHTML($('#sidebar'), `
    <div class="session-head">${badge(r.source)}<div class="session-model">${esc(r.model || '—')}</div><div class="session-ts">${fmtDate(r.started_at)}</div><div class="session-usage">${usage}</div></div>
    <div class="tab-row">${LEFT_TABS.map(t => `<button class="${activeTab===t?'active':''}" data-tab="${t}">${t}</button>`).join('')}</div>
    <div class="turn-list" id="sidebar-list"></div>`);
  $$('.tab-row button').forEach(b => b.onclick = () => { activeTab = b.dataset.tab; $$('.tab-row button').forEach(x => x.classList.toggle('active', x.dataset.tab === activeTab)); renderSidebarList(); renderCenter(); renderDetail(); });
  renderSidebarList();
}
function renderSidebarList() {
  const el = $('#sidebar-list');
  if (activeTab === 'turns') {
    const turns = data.turns || [];
    if (!turns.length) { setHTML(el, '<div class="list-empty">No turns</div>'); return; }
    setHTML(el, turns.map((t, i) => {
      const dots = (t.events || []).filter(e => e.type === 'tool_call').map(e => `<span class="tool-dot ${toolColor(e.tool_norm_name)}"></span>`).join('');
      return `<div class="turn-item ${i===selectedTurn?'active':''}" data-turn="${i}"><div class="turn-item-header"><span class="turn-num">Turn ${i+1}</span><span class="turn-tools">${dots || '<span class="turn-tokens">—</span>'}</span></div><div class="turn-preview">${esc(t.preview || '(no prompt)')}</div><div class="turn-tokens">${t.tool_count} tools · ${fmtTokens(t.input_tokens)} tok</div></div>`;
    }).join(''));
    $$('.turn-item').forEach(it => it.onclick = () => { selectedTurn = +it.dataset.turn; render(); });
  } else if (activeTab === 'tools') {
    const tools = []; (data.turns || []).forEach((t, i) => t.events.filter(e => e.type === 'tool_call').forEach(e => tools.push({ ...e, _turn: i })));
    if (!tools.length) { setHTML(el, '<div class="list-empty">No tool calls</div>'); return; }
    setHTML(el, tools.map(e => `<div class="turn-item" data-seq="${e.seq}"><div class="turn-item-header"><span class="turn-num">T${e._turn+1}</span><span class="tool-dot ${toolColor(e.tool_norm_name)}"></span></div><div class="turn-preview" style="font-family:var(--font-mono);color:var(--cinder)">${esc(e.tool_name || e.tool_norm_name || 'tool')}</div><div class="turn-tokens">${esc(e.path_rel || '')}</div></div>`).join(''));
  } else if (activeTab === 'files') {
    const files = data.files || [];
    if (!files.length) { setHTML(el, '<div class="list-empty">No files touched</div>'); return; }
    setHTML(el, files.map(f => `<div class="turn-item"><div class="turn-preview" style="font-family:var(--font-mono);color:var(--cinder)">${esc(f.path.split('/').pop())}</div><div class="turn-tokens">${f.reads} reads · ${f.edits} edits</div></div>`).join(''));
  } else if (activeTab === 'waste') {
    const w = data.waste_events || [];
    if (!w.length) { setHTML(el, '<div class="list-empty">No waste tagged</div>'); return; }
    setHTML(el, w.map(e => `<div class="turn-item"><div class="turn-preview" style="color:var(--ochre)">${esc((e.waste_category||'').replace(/_/g,' '))}</div><div class="turn-tokens">seq ${e.seq} · ${e.waste_tokens || 0} tok</div></div>`).join(''));
  } else { setHTML(el, `<div class="list-empty">${activeTab} shown in center →</div>`); }
}

/* ── Center ───────────────────────────────────────────────────── */
function renderCenter() {
  const body = centerBody();
  if (activeTab === 'graph') { if (body) body.textContent = ''; return renderGraphPanel($('#center'), true); }
  if (activeTab === 'context') { if (body) body.textContent = ''; return renderContextCenter(); }
  if (activeTab === 'fingerprint') { if (body) body.textContent = ''; return renderFingerprintCenter(); }
  const turns = data.turns || [], turn = turns[selectedTurn], center = body || $('#center');
  if (!turn) { setHTML(center, '<div class="empty-block">No turns in this session.</div>'); return; }
  let html = `<div class="run-plaque"><span class="mono">${badge(data.run.source)}</span><span class="mono">${esc(data.run.model||'—')}</span><span>${fmtDate(data.run.started_at)}</span><span>${data.run.event_count||0} events</span><span class="mono">${fmtCost(data.run.total_cost)}</span></div>`;
  html += `<div class="turn-detail"><div class="turn-header"><div class="turn-title">Turn ${selectedTurn+1} of ${turns.length}</div><div class="turn-usage"><div class="usage-item input"><div class="usage-label">In</div><div class="usage-value">${fmtTokens(turn.input_tokens)}</div></div><div class="usage-item output"><div class="usage-label">Out</div><div class="usage-value">${fmtTokens(turn.output_tokens)}</div></div></div></div>`;
  html += `<div class="prompt-block user"><div class="prompt-label">User</div>${esc(turn.user_text || '(empty)')}</div>`;
  for (const e of turn.events) {
    if (e.type === 'assistant_message') {
      const text = e.text_inline || '', truncated = text.length > 600;
      html += `<div class="prompt-block assistant"><div class="prompt-label">Assistant</div><span class="asst-text">${esc(text.slice(0, 600))}</span>${truncated ? ` <button class="expand-toggle" data-expand="asst">Show more</button>` : ''}</div>`;
    }
    if (e.type === 'tool_call') {
      const id = `tc-${e.seq}`, isErr = turn.events.some(x => x.seq === e.seq && x.tool_is_error), waste = e.waste_category, tokens = e.input_tokens || e.output_tokens || 0, tc = toolColor(e.tool_norm_name);
      html += `<div class="tool-call-item"><div class="tool-call-header" data-toggle="${id}"><span class="tool-type-dot" style="background:var(--${tc==='other'?'granite':tc})"></span><span class="tool-name-tag">${esc(e.tool_norm_name || e.tool_name || 'tool')}</span><span class="tool-path-tag">${esc(e.path_rel || '')}</span>${tokens ? `<span class="tool-tokens">${fmtTokens(tokens)}</span>` : ''}${isErr ? '<span class="tool-error-badge">error</span>' : ''}${waste ? `<span class="tool-waste-badge">${esc(waste.replace(/_/g,' '))}</span>` : ''}</div><div class="tool-call-body" id="${id}"></div></div>`;
    }
  }
  html += `</div>`;
  setHTML(center, html);
  $$('.tool-call-header').forEach(h => h.onclick = () => {
    const body = document.getElementById(h.dataset.toggle); if (!body) return;
    const expanded = body.classList.toggle('expanded');
    if (expanded && !body.dataset.loaded) {
      const seq = h.dataset.toggle.replace('tc-', '');
      const result = turn.events.find(e => e.type === 'tool_result' && String(e.seq) === seq) || turn.events.find(e => e.type === 'tool_result');
      body.textContent = result?.text_inline ? result.text_inline.slice(0, 2400) : '(no result text captured)';
      body.dataset.loaded = '1';
    }
  });
  $$('[data-expand="asst"]').forEach(b => b.onclick = () => {
    const span = b.previousElementSibling; if (!span) return;
    const full = turn.events.find(e => e.type === 'assistant_message')?.text_inline || '';
    if (b.textContent === 'Show more') { span.textContent = full; b.textContent = 'Show less'; } else { span.textContent = full.slice(0, 600); b.textContent = 'Show more'; }
  });
}
function renderContextCenter() {
  const center = centerBody() || $('#center');
  const regions = profile?.regions || [];
  const rebilled = (profile?.rebilling?.tokens) || 0;
  const agg = {}; regions.forEach(r => { agg[r.region] = (agg[r.region] || 0) + r.tokens; });
  const cells = Object.entries(agg).map(([region, value]) => ({ region, value }));
  let html = `<div class="run-plaque"><span>CONTEXT PROFILE</span><span class="mono">${regions.length} regions</span><span class="mono">re-billed ${fmtTokens(rebilled)} tok</span></div>`;
  html += `<div class="turn-detail"><div class="right-title">Region mix — this turn</div><div id="ctx-treemap" style="height:200px;background:var(--anthracite);border:1px solid var(--quartz-vein);border-radius:8px;position:relative"></div>`;
  const pers = regions.filter(r => r.first_turn < r.last_seen_turn);
  html += `<div class="right-title" style="margin-top:14px">Re-billed blocks (${pers.length})</div><div style="font-family:var(--font-mono);font-size:11px;color:var(--cinder)">${pers.length ? pers.slice(0, 12).map(r => `<div style="padding:4px 0;border-bottom:1px solid var(--quartz-vein)">${esc(r.region)} · ${fmtTokens(r.tokens)} tok · turns ${r.first_turn}→${r.last_seen_turn}</div>`).join('') : '<div>None — no content re-sent verbatim across turns.</div>'}</div></div>`;
  setHTML(center, html);
  treemapInto($('#ctx-treemap'), cells, $('#ctx-treemap').clientWidth || 420, 200);
}
function renderFingerprintCenter() {
  const center = centerBody() || $('#center'), fp = data.fingerprint || {};
  let html = `<div class="run-plaque"><span>FINGERPRINT</span><span class="mono">baseline n=${fp.baseline_n ?? 0}</span><span class="mono">distance=${fp.distance ?? '—'}</span></div>`;
  html += `<div class="turn-detail"><div class="right-title">This session vs project baseline</div><div id="fp-radar" style="height:300px"></div>`;
  const verdict = fp.drift ? `<span class="fp-verdict drift">DRIFT — D²=${fp.d_squared} exceeds χ² threshold ${fp.threshold}</span>` : (fp.distance != null ? `<span class="fp-verdict ok">Within baseline (D=${fp.distance})</span>` : `<span class="fp-verdict">Insufficient baseline for drift verdict</span>`);
  html += `<div style="margin-top:10px">${verdict}</div></div>`;
  setHTML(center, html);
  radarInto($('#fp-radar'), fp.labels, fp.vector, fp.baseline_mean, !!fp.drift);
}

/* ── Right drawer ─────────────────────────────────────────────── */
const DRAWER_TABS = ['strata','graph','fingerprint','waste'];
function renderDetail() {
  const r = $('#detail');
  let html = `<div class="nav-turns"><button class="btn btn-sm" id="prev-turn" ${selectedTurn===0?'disabled':''}>← Prev</button><button class="btn btn-sm" id="next-turn" ${selectedTurn>=(data.turns||[]).length-1?'disabled':''}>Next →</button></div>`;
  html += `<div class="drawer-tabs">${DRAWER_TABS.map(t => `<button class="${drawerTab===t?'active':''}" data-drawer="${t}">${t}</button>`).join('')}</div>`;
  html += `<div class="drawer-body" id="drawer-body"></div>`;
  setHTML(r, html);
  $$('.drawer-tabs button').forEach(b => b.onclick = () => { drawerTab = b.dataset.drawer; renderDrawerBody(); $$('.drawer-tabs button').forEach(x => x.classList.toggle('active', x.dataset.drawer === drawerTab)); });
  renderDrawerBody();
  $('#prev-turn')?.addEventListener('click', () => { if (selectedTurn > 0) { selectedTurn--; render(); } });
  $('#next-turn')?.addEventListener('click', () => { if (selectedTurn < (data.turns||[]).length - 1) { selectedTurn++; render(); } });
}
function renderDrawerBody() {
  const body = $('#drawer-body'); if (!body) return;
  if (drawerTab === 'strata') {
    const regions = profile?.regions || [];
    const maxTurn = profile?.regions ? Math.max(...profile.regions.map(r => r.last_seen_turn)) : 1;
    setHTML(body, `<div class="right-title">Stratigraphic column</div>${strataColumnSVG(regions, maxTurn, 280, 220)}<div class="right-title" style="margin-top:12px">Legend</div>${REGION_ORDER.map(r => `<div class="right-file"><span class="tool-dot" style="background:${hue(r,false)}"></span>${esc(r.replace(/_/g,' '))}</div>`).join('')}`);
  } else if (drawerTab === 'graph') {
    setHTML(body, `<div class="right-title">Turn × file graph</div><div id="drawer-graph" style="height:280px"></div>`);
    renderGraphPanel($('#drawer-graph'), false);
  } else if (drawerTab === 'fingerprint') {
    const fp = data.fingerprint || {};
    setHTML(body, `<div class="right-title">Fingerprint</div><div id="drawer-radar" style="height:240px"></div>
      <div class="metric-row" style="margin-top:8px"><span class="k">Mahalanobis D</span><span class="v">${fp.distance ?? '—'}</span></div>
      <div class="metric-row"><span class="k">D²</span><span class="v">${fp.d_squared ?? '—'}</span></div>
      <div class="metric-row"><span class="k">threshold (χ²)</span><span class="v">${fp.threshold ?? '—'}</span></div>
      <div class="metric-row"><span class="k">verdict</span><span class="v" style="color:${fp.drift?'var(--cinnabar)':'var(--malachite)'}">${fp.drift ? 'drift' : (fp.distance != null ? 'ok' : 'n/a')}</span></div>`);
    radarInto($('#drawer-radar'), fp.labels, fp.vector, fp.baseline_mean, !!fp.drift);
  } else if (drawerTab === 'waste') {
    const w = data.waste_events || [], f = profile?.findings || [];
    let inner = `<div class="right-title">Waste findings</div>${w.length ? w.map(e => `<div class="waste-item"><div class="cat">${esc((e.waste_category||'').replace(/_/g,' '))}</div><div class="meta">${e.waste_tokens || 0} tokens · seq ${e.seq}</div></div>`).join('') : '<div class="right-empty">No waste tagged in this session.</div>'}`;
    if (f.length) inner += `<div class="right-title" style="margin-top:14px">Context findings</div>${f.map(x => `<div class="waste-item"><div class="cat">${esc(x.type.replace(/_/g,' ').toLowerCase())}</div><div class="meta">${fmtTokens(x.tokens)} tok · ${esc(x.fix)}</div></div>`).join('')}`;
    setHTML(body, inner);
  }
}

/* ── Treemap helper ───────────────────────────────────────────── */
function treemapInto(container, cells, W, H) {
  if (!container) return;
  if (!cells || !cells.length) { setHTML(container, '<div class="empty-block">No mix.</div>'); return; }
  const total = cells.reduce((a, c) => a + c.value, 0); if (!total) { setHTML(container, '<div class="empty-block">No mix.</div>'); return; }
  const sorted = [...cells].sort((a, b) => b.value - a.value);
  setHTML(container, sliceDice(sorted, 0, 0, W, H, total).map(r => `<div style="position:absolute;left:${r.x}px;top:${r.y}px;width:${r.w}px;height:${r.h}px;background:${hue(r.region,false)};opacity:.85;border:1px solid var(--quartz-vein)"></div>`).join(''));
}
function sliceDice(cells, x, y, w, h, total) {
  if (!cells.length) return []; if (cells.length === 1) return [{ region: cells[0].region, x, y, w, h }];
  const out = [], horiz = w >= h; let acc = 0;
  for (const c of cells) { const len = (c.value / total) * (horiz ? w : h); out.push({ region: c.region, x: horiz ? x + acc : x, y: horiz ? y : y + acc, w: horiz ? len : w, h: horiz ? h : len }); acc += len; }
  return out;
}

/* ── D3 force graph (cairn-stone glyphs) ──────────────────────── */
function renderGraphPanel(container, full) {
  if (!container) return;
  const tag = full ? 'f' : 's';
  setHTML(container, `<div class="graph-wrap" id="gwrap-${tag}" style="${full?'height:calc(100vh - 104px)':'height:100%'}"><div class="graph-controls"><button id="g-fit-${tag}">Fit</button><button id="g-zin-${tag}">+</button><button id="g-zout-${tag}">−</button></div><div class="graph-legend"><span class="legend-item"><span class="tool-dot" style="background:var(--patina)"></span>turn</span><span class="legend-item"><span class="tool-dot" style="background:var(--copper)"></span>edited file</span><span class="legend-item"><span class="tool-dot" style="background:var(--granite)"></span>read file</span></div></div>`);
  const gwrap = $(`#gwrap-${tag}`);
  const graph = data.graph || {}, nodes = graph.nodes || [], edges = graph.edges || [];
  if (!nodes.length) { setHTML(gwrap, '<div class="empty-block">No graph data for this session.</div>'); return; }
  const width = gwrap.clientWidth || 700, height = gwrap.clientHeight || 420;
  const svg = d3.select(gwrap).append('svg').attr('width', '100%').attr('height', '100%').attr('viewBox', `0 0 ${width} ${height}`);
  const g = svg.append('g');
  const zoom = d3.zoom().scaleExtent([0.3, 3]).on('zoom', e => g.attr('transform', e.transform));
  svg.call(zoom);
  const N = nodes.map(n => ({ ...n })), E = edges.map(e => ({ ...e }));
  const linkColor = k => ({ read: cssVar('--patina'), edit: cssVar('--copper'), temporal: cssVar('--quartz-vein') }[k] || cssVar('--quartz-vein'));
  graphSim = d3.forceSimulation(N).force('link', d3.forceLink(E).id(d => d.id).distance(d => d.kind === 'temporal' ? 130 : 85)).force('charge', d3.forceManyBody().strength(-280)).force('center', d3.forceCenter(width/2, height/2)).force('collision', d3.forceCollide(52));
  const link = g.append('g').selectAll('line').data(E).enter().append('line').attr('class', 'graph-link')
    .attr('stroke', d => linkColor(d.kind)).attr('stroke-width', d => d.kind === 'temporal' ? 1 : 2).attr('stroke-dasharray', d => d.kind === 'temporal' ? '5 4' : null);
  const node = g.append('g').selectAll('g').data(N).enter().append('g').attr('class', 'graph-node')
    .call(d3.drag().on('start', (e, d) => { if (!e.active) graphSim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }).on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; }).on('end', (e, d) => { if (!e.active) graphSim.alphaTarget(0); d.fx = null; d.fy = null; }));
  node.filter(d => d.type === 'turn').append('rect').attr('width', 140).attr('height', 44).attr('x', -70).attr('y', -22).attr('rx', 8).attr('fill', cssVar('--shale')).attr('stroke', cssVar('--patina')).attr('stroke-width', 1.5);
  node.filter(d => d.type === 'file').append('rect').attr('width', 110).attr('height', 36).attr('x', -55).attr('y', -18).attr('rx', 6).attr('fill', cssVar('--shale')).attr('stroke', d => d.edits > 0 ? cssVar('--copper') : cssVar('--granite')).attr('stroke-width', 1.5);
  node.append('text').attr('text-anchor', 'middle').attr('dy', '-0.1em').attr('fill', cssVar('--bone')).attr('font-size', 10).attr('font-family', 'var(--font-mono)').text(d => (d.label || d.id).slice(0, 20));
  node.filter(d => d.type === 'turn' && (d.tokens > 0 || d.tool_count > 0)).append('text').attr('text-anchor', 'middle').attr('dy', '1.3em').attr('fill', cssVar('--cinder')).attr('font-size', 8).attr('font-family', 'var(--font-mono)').text(d => `${d.tool_count} tools${d.tokens > 0 ? ' · ' + (d.tokens/1000).toFixed(1) + 'K' : ''}`);
  node.on('click', (e, d) => { if (d.type === 'turn') { selectedTurn = +d.id.replace('turn-', ''); activeTab = 'turns'; render(); } });
  graphSim.on('tick', () => { link.attr('x1', d => d.source.x).attr('y1', d => d.source.y).attr('x2', d => d.target.x).attr('y2', d => d.target.y); node.attr('transform', d => `translate(${d.x},${d.y})`); });
  $(`#g-fit-${tag}`)?.addEventListener('click', () => svg.transition().duration(360).call(zoom.transform, d3.zoomIdentity));
  $(`#g-zin-${tag}`)?.addEventListener('click', () => svg.transition().call(zoom.scaleBy, 1.4));
  $(`#g-zout-${tag}`)?.addEventListener('click', () => svg.transition().call(zoom.scaleBy, 1/1.4));
}

/* ── Render all ───────────────────────────────────────────────── */
function render() { renderTopbar(); renderAutopsy(); renderSidebar(); renderCenter(); renderDetail(); }
window.addEventListener('resize', () => { if (graphSim) graphSim.alpha(0.3).restart(); });
requestAnimationFrame(() => document.body.classList.add('ready'));
load();
