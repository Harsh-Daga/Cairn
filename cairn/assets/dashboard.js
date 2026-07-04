/* Cairn dashboard — Surveyor's Field Notebook (Part 18). Vanilla JS. */
'use strict';

const state = { days: 30, charts: {}, sortKey: 'started_at', sortDir: -1, allSessions: [], config: {}, watch: true, jobs: [], diagnosticsSummary: {} };

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
/* Sanitized HTML assignment — every dynamic injection routes here. */
function setHTML(el, html) {
  if (!el) return;
  if (window.DOMPurify) { el.innerHTML = window.DOMPurify.sanitize(html); return; }
  el.textContent = String(html ?? '');
}
/* DOMPurify drops orphan <tr> nodes — wrap in <table> before sanitize. */
function setTableBody(el, rowsHtml) {
  if (!el) return;
  el.textContent = '';
  if (!rowsHtml) return;
  const wrapped = `<table><tbody>${rowsHtml}</tbody></table>`;
  const host = document.createElement('div');
  host.innerHTML = window.DOMPurify
    ? window.DOMPurify.sanitize(wrapped)
    : wrapped;
  const body = host.querySelector('tbody');
  if (!body) return;
  while (body.firstChild) el.appendChild(body.firstChild);
}
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

/* Region series map (18.1 / 18.5). Order = bottom(bedrock) → top. */
const REGION_ORDER = ['system','tool_schema','tool_result','retrieved','user','assistant_history'];
const REGION_HUE = { system:'--copper', tool_schema:'--patina', tool_result:'--ochre', retrieved:'--cinder', user:'--copper', assistant_history:'--malachite' };
const REGION_LABEL = { system:'system prompt', tool_schema:'tool schema', tool_result:'tool results', retrieved:'retrieved', user:'user', assistant_history:'assistant history' };
function hue(r, light) { const base = cssVar(REGION_HUE[r]||'--cinder'); return light ? shade(base, 28) : base; }
function shade(hex, pct) {
  const h = hex.replace('#',''); if (h.length<6) return hex;
  const n = parseInt(h,16); let r=(n>>16)&255,g=(n>>8)&255,b=n&255;
  r=Math.min(255,Math.max(0,r+pct)); g=Math.min(255,Math.max(0,g+pct)); b=Math.min(255,Math.max(0,b+pct));
  return '#'+((1<<24)+(r<<16)+(g<<8)+b).toString(16).slice(1);
}

/* ── Formatters ───────────────────────────────────────────────── */
function fmtCost(n) { if (n==null) return 'N/A'; const v = Number(n); if (!Number.isFinite(v)) return 'N/A'; return v>=1?`$${v.toFixed(2)}`:`$${v.toFixed(4)}`; }
function fmtTokens(n) { if (n==null) return 'N/A'; const v = Number(n); if (!Number.isFinite(v)) return 'N/A'; if (v>=1e6) return `${(v/1e6).toFixed(2)}M`; if (v>=1e3) return `${(v/1e3).toFixed(1)}K`; return String(v); }
function asNum(n) { const v = Number(n); return Number.isFinite(v) ? v : null; }
function isoWeekToDate(weekStr) {
  const m = /^(\d{4})-W(\d{2})$/.exec(String(weekStr || ''));
  if (!m) return weekStr;
  const year = +m[1], week = +m[2];
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const dow = jan4.getUTCDay() || 7;
  const monday = new Date(jan4);
  monday.setUTCDate(jan4.getUTCDate() - dow + 1 + (week - 1) * 7);
  return monday.toISOString().slice(0, 10);
}
function wasteBarValue(entry) {
  const tokens = asNum(entry?.tokens) ?? 0;
  const events = asNum(entry?.events) ?? 0;
  return tokens > 0 ? tokens : events;
}
function wasteBarTooltip(entry) {
  const tokens = asNum(entry?.tokens) ?? 0;
  const events = asNum(entry?.events) ?? 0;
  if (tokens > 0) return `${fmtTokens(tokens)} tok · ${events} events`;
  if (events > 0) return `${events} events (no per-event token data)`;
  return '0';
}
function fmtDate(iso) { if (!iso) return '—'; return new Date(iso).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}); }
function badge(s) { return `<span class="source-badge">${esc(s)}</span>`; }

function confidenceChip(method, errPct) {
  if (!method || method === 'exact' || errPct == null) return '';
  const v = Number(errPct);
  if (!Number.isFinite(v)) return '';
  return `<span class="confidence-chip" title="estimation via ${esc(method)}">±${Math.round(v)}% est.</span>`;
}
function withChip(valHtml, conf) {
  if (!conf) return valHtml;
  return `${valHtml}${confidenceChip(conf.estimation_method, conf.estimation_error_pct)}`;
}
function followNarrativeHref(href) {
  const h = String(href || '').replace(/^#/, '');
  const pageMap = { insights: 'insights', optimizations: 'optimize', optimize: 'optimize', sessions: 'sessions', context: 'context', behavior: 'behavior', quality: 'quality' };
  const page = pageMap[h] || h;
  if (typeof PAGES !== 'undefined' && PAGES[page]) { navTo(page); return; }
  if (h === 'sessions' && typeof navTo === 'function') navTo('sessions');
}
function renderNarrativeHero(narrative) {
  const box = $('#narrative-hero'), headline = $('#narrative-headline'), sents = $('#narrative-sentences'), cta = $('#narrative-cta');
  if (!box || !narrative || !narrative.headline) { if (box) box.hidden = true; return; }
  box.hidden = false;
  if (headline) headline.textContent = narrative.headline;
  if (sents) {
    sents.textContent = '';
    (narrative.sentences || []).forEach(s => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'narrative-link';
      btn.textContent = s.text || '';
      btn.addEventListener('click', () => followNarrativeHref(s.href || '#sessions'));
      sents.appendChild(btn);
    });
  }
  if (cta) {
    cta.textContent = narrative.cta || 'Review';
    cta.onclick = () => followNarrativeHref(narrative.cta_href || '#insights');
  }
}

/* ── API + actions ────────────────────────────────────────────── */
async function api(path, params={}) {
  const q = new URLSearchParams({ days: state.days, _t: String(Date.now()), ...params });
  const res = await fetch(`${path}?${q}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}
async function postJSON(path, body) {
  const res = await fetch(path, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body||{}) });
  return res.json();
}

function toast(msg, kind='') {
  const el = document.createElement('div'); el.className = `toast ${kind}`; setHTML(el, msg);
  $('#toast-stack').appendChild(el);
  setTimeout(() => { el.style.opacity='0'; setTimeout(()=>el.remove(),300); }, 4200);
}

/* Action button: idle → spinner+verb → restore. Returns restore fn. */
function actionState(btn, verb) {
  if (!btn) return () => {};
  btn.disabled = true;
  const orig = btn.innerHTML;
  setHTML(btn, `<span class="spinner"></span>${esc(verb)}`);
  return () => { btn.disabled = false; setHTML(btn, orig); };
}
function addJob(label, promise) {
  const job = { label, started: Date.now(), done: false };
  state.jobs.unshift(job); renderActionPanel();
  promise.then(r => { job.done = true; job.result = r; renderActionPanel(); return r; })
         .catch(e => { job.done = true; job.error = String(e.message||e); renderActionPanel(); });
  return promise;
}
function renderActionPanel() {
  const body = $('#action-panel-body');
  if (!state.jobs.length) { setHTML(body, '<div class="ap-row"><div class="ap-title" style="color:var(--cinder)">No jobs yet.</div></div>'); return; }
  setHTML(body, state.jobs.slice(0,8).map(j => `
    <div class="ap-row">
      <div class="ap-title">${j.done ? '' : '<span class="spinner"></span>'}${esc(j.label)}</div>
      <div class="ap-tail">${esc(j.error ? ('error: '+j.error) : (j.result ? JSON.stringify(j.result).slice(0,240) : 'running…'))}</div>
    </div>`).join(''));
}

/* ── Chart.js defaults (sparse, no gridlines, contour shows through) ── */
function configureChartDefaults() {
  if (!window.Chart) return;
  Chart.defaults.color = cssVar('--ash') || '#5B6068';
  Chart.defaults.borderColor = cssVar('--quartz-vein') || '#3A4049';
  Chart.defaults.font.family = '"JetBrains Mono", ui-monospace, monospace';
  Chart.defaults.font.size = 11;
  Chart.defaults.plugins.legend.display = false;
  Chart.defaults.plugins.tooltip.enabled = false;
  Chart.defaults.plugins.tooltip.external = externalTooltip;
}
function externalTooltip(ctx) {
  const tip = $('#chart-tip'); if (!ctx || !ctx.tooltip) return;
  const t = ctx.tooltip; if (t.opacity === 0) { tip.style.opacity = 0; return; }
  const lines = t.dataPoints.map(p => `<span class="tip-label">${esc(p.dataset.label||p.label)}</span><span class="tip-val">${esc(p.formattedValue||p.raw)}</span>`);
  setHTML(tip, lines.join(''));
  const rect = ctx.chart.canvas.getBoundingClientRect();
  tip.style.opacity = 1;
  tip.style.left = (rect.left + window.pageXOffset + t.caretX + 10) + 'px';
  tip.style.top = (rect.top + window.pageYOffset + t.caretY - 10) + 'px';
}
const NOGRID = { display:false };
function timeScale() { return { type:'time', time:{ unit:'day', tooltipFormat:'MMM d', displayFormats:{ day:'MMM d' } }, grid:NOGRID, border:NOGRID, ticks:{ color:cssVar('--ash'), maxTicksLimit:8, maxRotation:0 } }; }
function yScale(max) { return { beginAtZero:true, min:0, ...(max?{max}:{}), grid:NOGRID, border:NOGRID, ticks:{ color:cssVar('--ash'), maxTicksLimit:6 } }; }
const ANIM = { duration: 360, easing:'easeOutCubic' };
let COPPER = '#D08C4F';
function baseOpts(extra={}) {
  return { responsive:true, maintainAspectRatio:false, animation:ANIM,
    plugins:{ legend:{display:false}, tooltip:{ callbacks: extra.tooltip||{} } },
    scales: extra.scales || { x:timeScale(), y:yScale() } };
}
function destroyChart(id){ if(state.charts[id]){ state.charts[id].destroy(); delete state.charts[id]; } }
function mountCanvas(container) { container.textContent=''; const c=document.createElement('canvas'); container.appendChild(c); return c.getContext('2d'); }
function noData(el, msg) { setHTML(el, `<div class="empty-state"><span class="cairn-glyph es-glyph"><span class="stone base"></span><span class="stone mid"></span><span class="stone top"></span></span><p>${esc(msg)}</p><button class="ghost-btn" data-action="sync">Sync now</button></div>`); }

/* ── Chart builders ───────────────────────────────────────────── */
function seriesColor(i){ const p=[COPPER,cssVar('--patina'),cssVar('--ochre'),cssVar('--lapis'),cssVar('--malachite'),cssVar('--cinder'),cssVar('--cinnabar')]; return p[i%p.length]; }
function buildLine(id, containerId, series, opts) {
  destroyChart(id); const c = $(`#${containerId}`); if (!c) return null;
  if (!series.length || series.every(s=>s.data.every(p=>p.y==null))) { noData(c,'No data in selected period'); return null; }
  const ctx = mountCanvas(c); const ch = new Chart(ctx, { type:'line', data:{datasets:series}, options:opts });
  state.charts[id]=ch; return ch;
}
function dailyCostSeries(dailyCost) {
  const models=[...new Set(dailyCost.flatMap(d=>Object.keys(d.by_model||{})))];
  return models.map((m,i)=>({ label:m, data:dailyCost.map(d=>({x:d.day,y:d.by_model?.[m]??null})),
    spanGaps:false, borderColor: i===0?COPPER:seriesColor(i), backgroundColor: (i===0?COPPER:seriesColor(i))+'22',
    fill:false, tension:.3, pointRadius:ctx=>ctx.parsed?.y>0?3:0, pointHoverRadius:5, borderWidth:2 }));
}
function renderLegend(elId, series) {
  const el=$(`#${elId}`); if(!el) return;
  setHTML(el, series.map(s=>{ const c=typeof s.borderColor==='string'?s.borderColor:COPPER;
    return `<span class="legend-item"><span class="legend-line" style="background:${c}"></span>${esc(s.label)}</span>`; }).join(''));
}
function buildDailyCost(dailyCost, id, cid, legendId) {
  const series=dailyCostSeries(dailyCost);
  buildLine(id, cid, series, baseOpts({ tooltip:{ label:ctx=>ctx.parsed.y==null?'no data':`$${ctx.parsed.y.toFixed(4)}` } }));
  if (legendId) renderLegend(legendId, series);
}
function buildTokenChart(dailyTokens, id, cid, stacked, legendId) {
  const mk=(k,label,color)=>({ label, data:dailyTokens.map(d=>({x:d.day,y:d[k]??null})), spanGaps:false,
    borderColor:color, backgroundColor:color+(stacked?'AA':'22'), fill:stacked, tension:.3, stack:stacked?'t':undefined,
    pointRadius:0, pointHoverRadius:4, borderWidth:2 });
  const series=[mk('input','input',COPPER),mk('output','output',cssVar('--malachite')),mk('cache_read','cache',cssVar('--lapis'))];
  buildLine(id, cid, series, baseOpts({ scales:{ x:timeScale(), y:stacked?{...yScale(),stacked:true}:yScale() }, tooltip:{ label:ctx=>`${ctx.dataset.label}: ${fmtTokens(ctx.parsed.y)}` } }));
  if (legendId) renderLegend(legendId, series);
}
function buildWaste(wasteByCat, id, cid) {
  destroyChart(id); const c=$(`#${cid}`); if(!c) return;
  const ordered=Object.keys(wasteByCat||{}).filter(k=>wasteBarValue(wasteByCat[k])>0)
    .sort((a,b)=>wasteBarValue(wasteByCat[b])-wasteBarValue(wasteByCat[a]));
  if (!ordered.length) { noData(c,'No waste detected in selected period'); return; }
  const ctx=mountCanvas(c);
  state.charts[id]=new Chart(ctx,{ type:'bar', data:{ labels:ordered.map(k=>k.replace(/_/g,' ')),
    datasets:[{ data:ordered.map(k=>wasteBarValue(wasteByCat[k])), backgroundColor:ordered.map((_,i)=>seriesColor(i)+'BB'), borderColor:ordered.map((_,i)=>seriesColor(i)), borderWidth:1, borderRadius:4, barPercentage:.92 }] },
    options:{ indexAxis:'y', responsive:true, maintainAspectRatio:false, animation:ANIM,
      plugins:{ legend:{display:false}, tooltip:{ callbacks:{ label:ctx=>wasteBarTooltip(wasteByCat[ordered[ctx.dataIndex]]) } } },
      scales:{ x:{...yScale(),grid:NOGRID,border:NOGRID,ticks:{color:cssVar('--ash'),callback:v=>fmtTokens(v)}}, y:{grid:NOGRID,border:NOGRID,ticks:{color:cssVar('--cinder')}} } } });
}
function buildContextPressure(pressure, id, cid) {
  const c=$(`#${cid}`); if(!c) return;
  const pts=(pressure||[]).map(d=>({x:d.day,y:d.mean_peak_pct??null})).filter(p=>p.y!=null);
  if (!pts.length) { noData(c,'No context pressure data. Run sync/backfill after token-bearing sessions.'); return; }
  const series=[{ label:'mean peak %', data:pts, borderColor:COPPER, backgroundColor:COPPER+'22', fill:true, spanGaps:false, tension:.3, pointRadius:3, borderWidth:2 },
    { label:'85% threshold', data:pts.map(p=>({x:p.x,y:85})), borderColor:cssVar('--cinnabar'), borderDash:[6,4], pointRadius:0, fill:false, borderWidth:1.5 }];
  buildLine(id, cid, series, baseOpts({ scales:{ x:timeScale(), y:yScale(100) }, tooltip:{ label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%` } }));
}
function buildDrift(behavior, id, cid) {
  const drift=(behavior.drift||[]).map(d=>({x:d.started_at||d.run_id,y:asNum(d.distance), meta:d}));
  const anom=(behavior.anomalies||[]).map(a=>({x:a.started_at||a.run_id,y:asNum(a.distance), meta:a}));
  const c=$(`#${cid}`); if(!c) return;
  if (!drift.length && !anom.length) { noData(c,'No drift signals in range.'); return; }
  const useTime = [...drift, ...anom].every(p=>p.x && (String(p.x).includes('T') || /^\d{4}-\d{2}-\d{2}/.test(String(p.x))));
  const series=[{ label:'distance', data:drift, borderColor:COPPER, spanGaps:true, pointRadius:4, borderWidth:2, fill:false },
    { label:'anomaly', data:anom, borderColor:cssVar('--cinnabar'), backgroundColor:cssVar('--cinnabar'), pointRadius:5, showLine:false }];
  destroyChart(id); const ctx=mountCanvas(c);
  state.charts[id]=new Chart(ctx,{ type:'line', data:{datasets:series}, options: baseOpts({
    scales:{ x: useTime ? timeScale() : {type:'category',grid:NOGRID,border:NOGRID,ticks:{color:cssVar('--ash'),maxTicksLimit:8,maxRotation:0}},
      y:yScale() },
    tooltip:{ label:ctx=>{
      const m=ctx.raw?.meta;
      const head=m?.started_at?fmtDate(m.started_at):(m?.run_id?m.run_id.slice(0,8):ctx.label);
      return `${head}: D=${ctx.parsed.y?.toFixed(2)}`;
    } } }) });
}
function buildRebilling(recoverable, id, cid) {
  const weeks=(recoverable.weeks||[]).map(w=>({x:isoWeekToDate(w.week),y:asNum(w.cost_usd)})).filter(p=>p.x);
  buildLine(id, cid, [{ label:'recoverable $/wk', data:weeks, borderColor:COPPER, backgroundColor:COPPER+'22', fill:true, spanGaps:false, tension:.3, pointRadius:3, borderWidth:2 }],
    baseOpts({ tooltip:{ label:ctx=>ctx.parsed.y==null?'no data':`$${ctx.parsed.y.toFixed(2)}/wk` } }));
}
function buildCps(outcomes, id, cid) {
  const sess=(outcomes.sessions||[]).filter(s=>s.cost_per_success!=null);
  const data=sess.map(s=>({x:s.started_at||s.run_id,y:asNum(s.cost_per_success)})).filter(p=>p.y!=null);
  const c=$(`#${cid}`); if(!c) return;
  if (!data.length) { noData(c,'No cost-per-success data. Requires commits + has_cost sessions.'); return; }
  destroyChart(id); const ctx=mountCanvas(c);
  state.charts[id]=new Chart(ctx,{ type:'line', data:{datasets:[{ label:'cost per success', data, borderColor:cssVar('--malachite'), backgroundColor:cssVar('--malachite')+'22', fill:false, tension:.3, pointRadius:3, borderWidth:2 }] },
    options: baseOpts({ scales:{ x:timeScale(), y:yScale() }, tooltip:{ label:ctx=>`$${Number(ctx.parsed.y).toFixed(2)}` } }) });
}

/* ── Stratigraphic rendering (18.1) — 3 places ────────────────── */
/* Place 2: strata-spark 16x24 from a run's token mix. */
function strataSpark(s) {
  const mix=[['cache',s.cache_read_tokens||0,'--lapis'],['system',s.input_tokens||s.total_input_tokens||0,'--copper'],
             ['assistant',s.output_tokens||s.total_output_tokens||0,'--malachite'],['waste',s.waste_tokens||0,'--cinnabar']];
  const total=mix.reduce((a,[,v])=>a+Math.max(0,v),0);
  if (!total) return `<span class="strata-spark" title="no token mix"><span class="sp" style="background:var(--granite);height:100%"></span></span>`;
  return `<span class="strata-spark" title="${esc(mix.map(([k,v])=>`${k}:${v}`).join(' '))}">${
    mix.filter(([,v])=>v>0).map(([k,v,h])=>`<span class="sp" style="background:var(${h});height:${(v/total*100).toFixed(1)}%"></span>`).join('')}</span>`;
}
/* Place 1: full stratigraphic column from profile regions over turns. */
function strataColumn(regions, maxTurn) {
  if (!regions || !regions.length) return `<div class="empty-state"><span class="cairn-glyph es-glyph"><span class="stone base"></span><span class="stone mid"></span><span class="stone top"></span></span><p>No context regions recorded for this run.</p></div>`;
  const W=620, H=260, pad=28, turns=Math.max(maxTurn||1,...regions.map(r=>r.last_seen_turn));
  const colW=(W-2*pad)/turns, barW=Math.max(3,colW-2);
  const stacks=[]; for(let t=1;t<=turns;t++){ const st=stackFor(regions,t); if(st.length) stacks.push({t,st,total:st.reduce((a,r)=>a+r.tokens,0)}); }
  const maxStack=Math.max(1,...stacks.map(s=>s.total));
  let rects='';
  stacks.forEach(({t,st})=>{ let y=H-pad; const x=pad+(t-1)*colW+colW/2-barW/2;
    st.forEach(r=>{ const h=Math.max(1,(r.tokens/maxStack)*(H-2*pad));
      rects+=`<rect x="${x.toFixed(1)}" y="${(y-h).toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" fill="${hue(r.region,false)}" stroke="${cssVar('--quartz-vein')}" stroke-width="1"/>`;
      rects+=`<rect x="${x.toFixed(1)}" y="${(y-h).toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(1,h*0.35).toFixed(1)}" fill="${hue(r.region,true)}" opacity="0.45"/>`;
      if(r.first_turn<r.last_seen_turn && r.last_seen_turn===t){ rects+=`<line x1="${x.toFixed(1)}" y1="${(y-h).toFixed(1)}" x2="${(x+barW).toFixed(1)}" y2="${(y-h).toFixed(1)}" stroke="${cssVar('--copper')}" stroke-width="1" opacity="0.7"/>`; }
      y-=h; }); });
  return `<svg class="strata-col-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
    <text x="4" y="16" class="strata-axis">tokens</text>
    <text x="${W-pad}" y="16" class="strata-axis" text-anchor="end">turn ${turns}</text>${rects}</svg>`;
}
function stackFor(regions, t) {
  return REGION_ORDER.map(rname => {
    const rs = regions.filter(r=>r.region===rname && r.first_turn<=t && r.last_seen_turn>=t);
    if(!rs.length) return null;
    const seen=new Set(); let toks=0;
    rs.forEach(r=>{ if(!seen.has(r.content_hash)){ seen.add(r.content_hash); toks+=r.tokens; } });
    return { region:rname, tokens:toks, first_turn:Math.min(...rs.map(r=>r.first_turn)), last_turn:Math.max(...rs.map(r=>r.last_seen_turn)), content_hash:rs[0].content_hash };
  }).filter(Boolean);
}
/* Place 3: context treemap (top-down outcrop map). */
function treemap(cells, container) {
  if (!container) return;
  if (!cells || !cells.length) { setHTML(container, `<div class="empty-state"><p>No context mix to map.</p></div>`); return; }
  const W=container.clientWidth||420, H=container.clientHeight||240;
  const total=cells.reduce((a,c)=>a+c.value,0); if(!total){ setHTML(container,`<div class="empty-state"><p>No context mix to map.</p></div>`); return; }
  const sorted=[...cells].sort((a,b)=>b.value-a.value);
  setHTML(container, sliceDice(sorted,0,0,W,H,total).map(r=>`<div class="tm-cell" style="left:${r.x}px;top:${r.y}px;width:${r.w}px;height:${r.h}px;background:${hue(r.region,false)};opacity:.85">${r.h>22&&r.w>60?`<span style="color:${shade(hue(r.region,false),60)}">${esc(r.region)}</span>`:''}</div>`).join(''));
}
function sliceDice(cells, x, y, w, h, total) {
  if(!cells.length) return []; if(cells.length===1) return [{region:cells[0].region,x,y,w,h}];
  const out=[], horiz=w>=h; let acc=0;
  for(const c of cells){ const len=(c.value/total)*(horiz?w:h);
    out.push({region:c.region, x:horiz?x+acc:x, y:horiz?y:y+acc, w:horiz?len:w, h:horiz?h:len}); acc+=len; }
  return out;
}
function strataLegend() { setHTML($('#strata-legend'), REGION_ORDER.map(r=>`<span class="lg"><span class="sw" style="background:${hue(r,false)}"></span>${esc(REGION_LABEL[r])}</span>`).join('')); }

/* ── D3 radar (behavior) ──────────────────────────────────────── */
function radarChart(container, labels, current, baseline, drift) {
  if (!container) return; setHTML(container,'');
  if (!labels || !current) { setHTML(container, `<div class="empty-state"><p>No fingerprint data in range. Run a sync to compute fingerprints.</p></div>`); return; }
  const W=320,H=320,cx=W/2,cy=H/2,R=110, axes=labels.slice(0,8);
  const svg=d3.select(container).append('svg').attr('width','100%').attr('height','100%').attr('viewBox',`0 0 ${W} ${H}`);
  const max=Math.max(1,...current.slice(0,8),...(baseline||[]).slice(0,8));
  const pt=(i,v)=>{ const a=-Math.PI/2+i*(2*Math.PI/axes.length); return [cx+Math.cos(a)*(v/max)*R, cy+Math.sin(a)*(v/max)*R]; };
  axes.forEach((l,i)=>{ const [x,y]=pt(i,max); svg.append('line').attr('x1',cx).attr('y1',cy).attr('x2',x).attr('y2',y).attr('stroke',cssVar('--quartz-vein')).attr('stroke-width',1);
    svg.append('text').attr('x',x+(x>cx+2?4:x<cx-2?-4:0)).attr('y',y+(y>cy+2?12:y<cy-2?-4:0)).attr('text-anchor',x>cx+2?'start':x<cx-2?'end':'middle').attr('fill',cssVar('--cinder')).attr('font-family','var(--font-mono)').attr('font-size',9).text(l); });
  const poly=(vals,color,fill,fillOp)=>{ const pts=vals.map((v,i)=>pt(i,v).join(',')).join(' ');
    svg.append('polygon').attr('points',pts).attr('stroke',color).attr('stroke-width',1.5).attr('fill',fill).attr('fill-opacity',fillOp); };
  if(baseline) poly(baseline.slice(0,8),cssVar('--patina'),cssVar('--patina'),0.08);
  poly(current.slice(0,8),cssVar('--copper'),cssVar('--copper'),0.22);
  if(drift) svg.append('circle').attr('cx',cx).attr('cy',cy).attr('r',R).attr('fill','none').attr('stroke',cssVar('--cinnabar')).attr('stroke-width',1.5).attr('stroke-dasharray','5 4');
}

/* ── Data notes ───────────────────────────────────────────────── */
function renderDataNotes(notes) {
  const el=$('#data-notes'); if(!notes?.length){ el.textContent=''; return; }
  setHTML(el, notes.map(n=>`<div class="data-note"><span class="data-note-icon">ⓘ</span><div>${esc(n.message||n)}</div></div>`).join(''));
}

/* ── Overview ─────────────────────────────────────────────────── */
async function loadOverview() {
  const [ov, sess, rec] = await Promise.all([api('/api/overview'), api('/api/sessions',{limit:7}), fetch('/api/recoverable?days=30').then(r=>r.json())]);
  renderDataNotes(ov.data_notes);
  renderNarrativeHero(ov.narrative);
  state.diagnosticsSummary = ov.diagnostics_summary || {};
  const k=ov.kpis||{}, sum=ov.summary||{}, recWk=asNum(rec.total_cost_usd);
  const conf = ov.confidence || {};
  const spend = asNum(k.spend) ?? 0;
  const wasteTokens = asNum(k.waste_tokens) ?? asNum(sum.waste_tokens);
  const wastePctRaw = k.waste_pct ?? sum.waste_pct;
  const wastePctNum = wastePctRaw === '<0.01' ? 0 : asNum(wastePctRaw);
  const wasteVal = (wastePctNum != null && wastePctNum >= 0.01) ? `${wastePctRaw}%`
    : (wasteTokens ? fmtTokens(wasteTokens) : `${wastePctRaw ?? 0}%`);
  const wasteSub = (wasteTokens && (wastePctRaw === '<0.01' || (wastePctNum ?? 0) < 0.01))
    ? 'wasted tokens' : 'of total tokens';
  const cards=[['Spend',withChip(fmtCost(spend), conf),`${(spend/Math.max(state.days,1)).toFixed(2)}/day`,cssVar('--copper')],
    ['Tokens',withChip(fmtTokens(k.tokens), conf),'input + output',cssVar('--patina')],
    ['Waste',withChip(wasteVal, conf),wasteSub,cssVar('--cinnabar')],
    ['Recoverable',recWk!=null?`≈$${recWk.toFixed(2)}`:'N/A','per week',cssVar('--malachite')]];
  setHTML($('#kpi-row'), cards.map(([label,val,sub,c])=>`<div class="kpi-card" style="border-left-color:${c}"><div class="watermark">⌬</div><div class="kpi-label">${label}</div><div class="kpi-num">${val}</div><div class="kpi-sub">${sub}</div></div>`).join(''));
  setTableBody($('#recent-sessions tbody'), (sess.sessions||[]).map(s=>recentRow(s)).join(''));
  bindRows('#recent-sessions');
  treemap((ov.by_source||[]).map(s=>({region:s.source,value:asNum(s.sessions)??0})), $('#overview-treemap'));
  const charts = await api('/api/charts');
  buildDailyCost(charts.daily_cost,'ov-cost','chart-overview-cost',null);
  buildWaste(charts.waste_by_category,'ov-waste','chart-overview-waste');
  const projectName = ov.project_name || 'project';
  const plaqueName = $('#plaque-name');
  if (plaqueName) plaqueName.textContent = projectName;
  $('#plaque-meta').textContent = `${(asNum(sum.sessions) ?? 0).toLocaleString()} runs · surveyed just now`;
  if (!(asNum(sum.sessions) ?? 0)) maybeShowOnboarding();
}
function recentRow(s) {
  const tok=s.has_cost?fmtTokens((s.input_tokens||0)+(s.output_tokens||0)):'<span class="td-unavailable">N/A</span>';
  const cost=s.has_cost?fmtCost(s.total_cost):'<span class="td-unavailable">N/A</span>';
  const wp=wastePct(s);
  return `<tr data-run="${esc(s.run_id)}"><td>${fmtDate(s.started_at)}</td><td>${badge(s.source)}</td><td>${strataSpark(s)}</td><td class="text-muted">${s.turns??'—'}</td><td class="td-tokens">${tok}</td><td class="td-cost">${cost}</td><td><div class="waste-mini-bar"><div class="waste-track"><div class="waste-fill ${wp>=10?'high':wp>=3?'medium':''}" style="width:${Math.min(wp,100)}%"></div></div><span class="waste-pct">${wp?wp.toFixed(0)+'%':'0'}</span></div></td></tr>`;
}
function wastePct(s){ const t=(s.input_tokens||0)+(s.output_tokens||0); if(!t||!s.waste_tokens) return 0; return s.waste_tokens/t*100; }
function bindRows(root){ $$(`${root} tbody tr[data-run]`).forEach(tr=>tr.onclick=()=>{ window.location.href=`/session.html?id=${tr.dataset.run}`; }); }

/* ── Context ──────────────────────────────────────────────────── */
async function loadContext() {
  strataLegend();
  const sess = await api('/api/sessions',{limit:50});
  const ranked = (sess.sessions||[]).map(s => ({
    s,
    score: (s.event_count||0) + (s.input_tokens||0) + (s.output_tokens||0) + (s.turns||0) * 10,
  })).sort((a,b)=>b.score-a.score);
  const recent = ranked[0]?.s;
  if (!recent) {
    setHTML($('#context-column'), `<div class="empty-state"><span class="cairn-glyph es-glyph"><span class="stone base"></span><span class="stone mid"></span><span class="stone top"></span></span><p>No sessions to profile yet.</p><button class="ghost-btn" data-action="sync">Sync now</button></div>`);
    setHTML($('#context-treemap'), `<div class="empty-state"><p>No context mix to map.</p><button class="ghost-btn" data-action="sync">Sync now</button></div>`);
    setHTML($('#context-findings'), `<div class="empty-state"><p>Context findings appear after a sync with token-bearing sessions.</p><button class="ghost-btn" data-action="sync">Sync now</button></div>`);
    return;
  }
  const prof = await fetch(`/api/profile/${recent.run_id}`).then(r=>r.json());
  const rec = await fetch('/api/recoverable?days=30').then(r=>r.json());
  setHTML($('#context-column'), strataColumn(prof.regions, prof.regions?Math.max(...prof.regions.map(r=>r.last_seen_turn)):1));
  const agg={}; (prof.regions||[]).forEach(r=>{ agg[r.region]=(agg[r.region]||0)+r.tokens; });
  treemap(Object.entries(agg).map(([region,value])=>({region,value})), $('#context-treemap'));
  const f=(prof.findings||[]);
  setHTML($('#context-findings'), f.length?f.map(x=>`<div class="finding-card severity-${x.severity}"><div class="insight-title">${esc(x.type.replace(/_/g,' ').toLowerCase())} <span class="savings-pill">${fmtTokens(x.tokens)} tok</span></div><div class="insight-text">${esc(x.fix)}</div></div>`).join(''):
    `<div class="empty-state"><p>No re-billing waste detected in this run.</p><button class="ghost-btn" data-action="sync">Re-sync</button></div>`);
  buildRebilling(rec,'rebilling','chart-rebilling');
}

/* ── Behavior ─────────────────────────────────────────────────── */
async function loadBehavior() {
  const b = await api('/api/behavior',{days:30});
  renderDataNotes(b.data_notes);
  radarChart($('#behavior-radar'), b.radar?.labels, b.radar?.current_week, b.radar?.baseline, !!(b.drift&&b.drift.length));
  setHTML($('#behavior-drift-eyebrow'), (b.drift&&b.drift.length)?`<div class="eyebrow drift-eyebrow">DRIFT — ${b.drift.length} session${b.drift.length>1?'s':''} outside χ² threshold</div>`:'');
  buildDrift(b,'drift','chart-drift');
  const axisLabels = b.radar?.labels || [];
  const axisName = (a) => a.axis_label || axisLabels[a.axis] || `axis ${a.axis}`;
  const sig=(b.drift||[]).map(d=>({
    label:`${fmtDate(d.started_at)} · ${d.source||'agent'} · ${(d.kind||'drift').replace(/_/g,' ')}`,
    d:`D²=${asNum(d.d_squared)?.toFixed(2) ?? d.d_squared} (χ² ${asNum(d.threshold)?.toFixed(2) ?? d.threshold})`,
  })).concat((b.gradual||[]).flatMap(g=>g.axes.map(a=>({
    label:`${g.project || 'project'}/${g.model || 'model'} · ${axisName(a)}`,
    d:`weeks outside: ${a.weeks_outside}`,
  }))));
  setHTML($('#behavior-signals'), sig.length?`<div class="eyebrow">signals</div><h2>Drift signals</h2>`+sig.slice(0,10).map(s=>`<div class="finding-card severity-medium"><div class="insight-title">${esc(s.label||s.kind||'drift')}</div><div class="insight-text">${esc(s.d||(`D²=${s.d_squared} threshold=${s.threshold}`))}</div></div>`).join(''):
    `<div class="empty-state"><p>No drift detected. Agents are within baseline behavior.</p><button class="ghost-btn" data-action="context">View context</button></div>`);
}

/* ── Quality / Outcomes ───────────────────────────────────────── */
async function loadQuality() {
  const o = await api('/api/outcomes',{days:30});
  renderDataNotes(o.data_notes);
  const q=o.quality, cps=o.cost_per_success, f=o.funnel;
  setHTML($('#quality-kpis'), [
    ['Quality score', q&&asNum(q.mean)!=null?asNum(q.mean).toFixed(1):'—','mean across runs',cssVar('--copper')],
    ['Cost per success', cps?.cost_per_success!=null?fmtCost(asNum(cps.cost_per_success)):'N/A','per landed commit',cssVar('--malachite')],
    ['Commits landed', f?f.commits_landed:0,`of ${f?f.sessions:0} runs`,cssVar('--patina')],
    ['Passing tests', f?f.passing_tests:0,'build pass',cssVar('--lapis')],
  ].map(([label,val,sub,c])=>`<div class="kpi-card" style="border-left-color:${c}"><div class="watermark">⌬</div><div class="kpi-label">${label}</div><div class="kpi-num">${val}</div><div class="kpi-sub">${sub}</div></div>`).join(''));
  qualityRing($('#quality-ring'), asNum(q&&q.mean) ?? 0);
  buildCps(o,'cps','chart-cps');
  const git=(o.sessions||[]).filter(s=>s.commit_landed).slice(0,10);
  setHTML($('#quality-git'), git.length?`<div class="eyebrow">git signals</div><h2>Surveyor's log</h2><div class="table-wrap"><table class="data-table"><thead><tr><th>Run</th><th>Commit</th><th>Tier</th><th>Quality</th></tr></thead><tbody id="quality-git-body"></tbody></table></div>`:`<div class="empty-state"><p>No commits landed in range. Enable <span class="mono">test_command</span> in Settings → Outcomes to track test outcomes.</p><button class="ghost-btn" data-action="settings">Configure outcomes</button></div>`);
  if (git.length) {
    setTableBody($('#quality-git-body'), git.map(s=>`<tr data-run="${esc(s.run_id)}"><td class="text-muted">${esc(s.run_id.slice(0,8))}</td><td class="mono">${esc((s.commit_sha||'').slice(0,8))}</td><td>${esc(s.tier||'—')}</td><td class="td-tokens">${asNum(s.quality_score)!=null?asNum(s.quality_score).toFixed(1):'—'}</td></tr>`).join(''));
  }
  bindRows('#quality-git');
}
function qualityRing(container, val) {
  if(!container) return; setHTML(container,'');
  const R=58, C=2*Math.PI*R, frac=Math.max(0,Math.min(1,(val||0)/100));
  const svg=d3.select(container).append('svg').attr('width','100%').attr('height','100%').attr('viewBox','0 0 180 180');
  svg.append('circle').attr('cx',90).attr('cy',90).attr('r',R).attr('fill','none').attr('stroke',cssVar('--granite')).attr('stroke-width',8);
  svg.append('circle').attr('cx',90).attr('cy',90).attr('r',R).attr('fill','none').attr('stroke',cssVar('--copper')).attr('stroke-width',8).attr('stroke-linecap','round')
    .attr('stroke-dasharray',C).attr('stroke-dashoffset',C*(1-frac)).attr('transform','rotate(-90 90 90)');
  svg.append('text').attr('x',90).attr('y',98).attr('text-anchor','middle').attr('fill',cssVar('--bone')).attr('font-family','var(--font-display)').attr('font-size',32).text((val||0).toFixed(0));
}

/* ── Charts page ──────────────────────────────────────────────── */
async function loadCharts() {
  const data = await api('/api/charts');
  buildDailyCost(data.daily_cost,'cost-model','chart-cost-model','legend-cost-model');
  buildTokenChart(data.daily_tokens,'tokens-stack','chart-tokens-stack',true,'legend-tokens');
  buildWaste(data.waste_by_category,'waste','chart-waste');
  buildContextPressure(data.context_pressure,'context','chart-context');
}

/* ── Insights ─────────────────────────────────────────────────── */
function insightEvidenceHref(ins) {
  const ev = ins.evidence || {};
  if (ev.run_id) return `/session.html?id=${encodeURIComponent(ev.run_id)}`;
  const act = String(ins.action || '');
  if (act.includes('optimize')) return '#optimize';
  if (act.includes('profile') || act.includes('context')) return '#context';
  if (act.includes('behavior')) return '#behavior';
  if (act.includes('outcomes')) return '#quality';
  return '#sessions';
}
function insightEvidenceLabel(ins) {
  const ev = ins.evidence || {};
  if (ev.run_id) return `View session ${String(ev.run_id).slice(0, 8)} →`;
  if (ins.savings_estimate != null) return 'See evidence →';
  return '';
}
async function loadInsights() {
  const data = await fetch('/api/insights?days=14').then(r=>r.json());
  const ins=(data.insights||[]).slice().sort((a,b)=>{
    const tierOrder = (i) => (i.tier === '2.0' || i.difficulty_aware) ? 0 : 1;
    const t = tierOrder(a) - tierOrder(b);
    if (t) return t;
    return (b.savings_estimate||0) - (a.savings_estimate||0);
  });
  setHTML($('#insights-feed'), ins.length?ins.map(i=>{
    const tierTag = (i.tier === '2.0' || i.difficulty_aware)
      ? `<span class="insight-tier tier-20">difficulty-aware</span>` : `<span class="insight-tier">legacy</span>`;
    const savings = i.savings_estimate ? `<span class="savings-pill">~$${Number(i.savings_estimate).toFixed(2)}/wk</span>` : '';
    const evHref = insightEvidenceHref(i);
    const evLabel = insightEvidenceLabel(i);
    const evLink = evLabel ? `<button type="button" class="insight-evidence-link" data-ev-href="${esc(evHref)}">${esc(evLabel)}</button>` : '';
    return `<div class="insight-card severity-${i.severity||'info'}"><div class="insight-title">${esc(i.title||i.rule||'Insight')}${tierTag}${savings}</div><div class="insight-text">${esc(i.body||'')}</div>${evLink}</div>`;
  }).join(''):
    `<div class="empty-state"><span class="cairn-glyph es-glyph"><span class="stone base"></span><span class="stone mid"></span><span class="stone top"></span></span><h3>No issues detected</h3><p>Your agents are running efficiently in the last 14 days.</p><button class="ghost-btn" data-action="sync">Sync now</button></div>`);
  $$('#insights-feed .insight-evidence-link').forEach(btn => btn.addEventListener('click', () => {
    const href = btn.dataset.evHref || '';
    if (href.startsWith('/session')) { window.location.href = href; return; }
    followNarrativeHref(href);
  }));
  const files=data.top_files||[];
  setHTML($('#top-files'), files.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>File</th><th>Reads</th><th>Edits</th><th>Tokens</th><th>Cost</th></tr></thead><tbody id="top-files-body"></tbody></table></div>`:`<div class="empty-state"><p>File attribution requires Claude Code or Codex sessions with token data.</p><button class="ghost-btn" data-action="sync">Sync now</button></div>`);
  if (files.length) {
    setTableBody($('#top-files-body'), files.map(f=>`<tr><td class="mono" style="font-size:11px">${esc(f.path)}</td><td>${f.reads}</td><td>${f.edits}</td><td class="td-tokens">${f.tokens!=null?fmtTokens(f.tokens):'<span class="td-unavailable">N/A</span>'}</td><td class="td-cost">${f.cost!=null?fmtCost(f.cost):'<span class="td-unavailable">N/A</span>'}</td></tr>`).join(''));
  }
}

/* ── Optimize ─────────────────────────────────────────────────── */
async function loadOptimize() {
  const data = await fetch('/api/optimize').then(r=>r.json());
  const el=$('#optimize-content');
  const opts=data.optimizations||[];
  if (!data.has_run && !(data.proposals||[]).length) {
    setHTML(el, `<div class="empty-state"><span class="cairn-glyph es-glyph"><span class="stone base"></span><span class="stone mid"></span><span class="stone top"></span></span><h3>Find improvements</h3><p>Cairn analyzes sessions and proposes instruction edits to CLAUDE.md, AGENTS.md, and .cursor/rules.</p><button class="btn btn-primary" id="btn-find">Find improvements</button></div>`);
    $('#btn-find')?.addEventListener('click', doOptimizeDryrun);
    return;
  }
  const pending=data.proposals||[];
  let html=`<div class="eyebrow">leaderboard</div><h2>Instruction effectiveness</h2>`;
  if (opts.length) html+=`<div class="panel">${opts.slice(0,12).map(o=>optRow(o)).join('')}</div>`;
  if (pending.length) {
    html+=`<div class="eyebrow" style="margin-top:18px">pending proposals</div><h2>${pending.length} proposal${pending.length>1?'s':''}</h2>`;
    html+=pending.slice(0,8).map(p=>`<div class="opt-card"><div><span class="opt-status-badge pending">pending</span><span class="opt-target">${esc(p.kind)}</span></div>
      <div class="opt-evidence">${esc((p.evidence||'').slice(0,140))}</div>
      <pre class="mono" style="background:var(--anthracite);border-top:1px solid var(--copper);padding:10px;border-radius:8px;overflow-x:auto;font-size:11px;color:var(--bone);margin:8px 0">${esc((p.content||'').slice(0,300))}</pre>
      <button class="btn btn-primary btn-sm" data-apply-pending="${esc(p.entry_id)}">Apply rule</button></div>`).join('');
  }
  setHTML(el, html);
  $$('[data-apply-pending]').forEach(b=>b.addEventListener('click', ()=>doOptimizeApply(b.dataset.applyPending)));
  $$('[data-revert]').forEach(b=>b.addEventListener('click', ()=>doOptimizeRevert(b.dataset.revert)));
  $$('[data-prune]').forEach(b=>b.addEventListener('click', ()=>doOptimizeRevert(b.dataset.prune)));
}
function optRow(o) {
  const before=o.baseline_metric!=null?o.baseline_metric.toFixed(2):'—', after=o.outcome_metric!=null?o.outcome_metric.toFixed(2):'—';
  const delta=(o.outcome_metric!=null&&o.baseline_metric!=null)?(o.outcome_metric-o.baseline_metric):null;
  const sp=(a,b)=>`<svg class="spark" width="40" height="16"><polyline fill="none" stroke="${cssVar('--cinder')}" stroke-width="1.5" points="${sparkPts(b)}"/><polyline fill="none" stroke="${cssVar('--copper')}" stroke-width="1.5" points="${sparkPts(a)}"/></svg>`;
  return `<div class="opt-card ${o.status==='pruned'?'pruned':''}">
    <div style="display:flex;align-items:center;gap:10px"><span class="opt-status-badge ${esc(o.status)}">${esc(o.status)}</span><span class="opt-target">${esc(o.target_file||'')}</span>
    <span style="margin-left:auto;display:flex;align-items:center;gap:8px">${sp(after,before)}<span class="delta-num ${delta&&delta<0?'neg':''}">${delta!=null?(delta>0?'+':'')+delta.toFixed(2):'—'}</span></span></div>
    <div class="opt-evidence" style="margin-top:6px">baseline ${before} → outcome ${after}</div>
    <div style="margin-top:8px;display:flex;gap:8px">
      ${o.status==='applied'?`<button class="btn btn-sm" data-revert="${esc(o.opt_id)}">Revert</button>`:''}
      ${o.status==='applied'?`<button class="btn btn-sm btn-danger" data-prune="${esc(o.opt_id)}">Prune</button>`:''}
    </div></div>`;
}
function sparkPts(series){ if(!Array.isArray(series)) return '0,8 40,8'; const mx=Math.max(...series),mn=Math.min(...series); return series.map((v,i)=>`${(i/(series.length-1||1))*40},${8-((v-mn)/((mx-mn)||1))*8}`).join(' '); }
async function doOptimizeDryrun() {
  const btn=$('#btn-find'); const done=actionState(btn,'Analyzing…');
  const r=await addJob('find improvements', postJSON('/api/action/optimize',{}));
  done();
  toast(r.ok?`Found ${((r.proposals||[]).length)} proposals`:'Analyze failed', r.ok?'':'error');
  loadOptimize();
}
async function doOptimizeApply(ruleId) {
  const r=await postJSON('/api/action/optimize',{apply:true, rule_id:ruleId});
  toast(r.ok?`Applied to CLAUDE.md`:'Apply failed', r.ok?'good':'error');
  if(r.ok) loadOptimize();
}
async function doOptimizeRevert(ruleId) {
  const r=await postJSON('/api/action/optimize',{revert:true, rule_id:ruleId});
  toast(r.ok?'Reverted rule':'Revert failed', r.ok?'good':'error');
  if(r.ok) loadOptimize();
}

/* ── Sessions ─────────────────────────────────────────────────── */
async function loadSessions() {
  const data = await api('/api/sessions',{limit:200});
  state.allSessions=data.sessions||[];
  setTableBody($('#all-sessions tbody'), sortSessions(state.allSessions).map(s=>{
    const tok=s.has_cost?fmtTokens((s.input_tokens||0)+(s.output_tokens||0)):'<span class="td-unavailable">N/A</span>';
    const cost=s.has_cost?fmtCost(s.total_cost):'<span class="td-unavailable">N/A</span>';
    const wp=wastePct(s);
    return `<tr data-run="${esc(s.run_id)}"><td>${fmtDate(s.started_at)}</td><td>${badge(s.source)}</td><td>${strataSpark(s)}</td><td class="text-muted">${s.turns??'—'}</td><td class="td-tokens">${tok}</td><td class="td-cost">${cost}</td><td><div class="waste-mini-bar"><div class="waste-track"><div class="waste-fill ${wp>=10?'high':wp>=3?'medium':''}" style="width:${Math.min(wp,100)}%"></div></div><span class="waste-pct">${wp?wp.toFixed(0)+'%':'0'}</span></div></td><td>${s.tool_errors||0}</td><td class="text-muted">${esc(s.model||'—')}</td><td class="text-muted">${esc(s.project||'—')}</td><td><button class="ghost-btn btn-export" data-export="${esc(s.run_id)}" title="Export scrubbed HTML">Export</button></td></tr>`;
  }).join(''));
  bindRows('#all-sessions');
  $$('#all-sessions .btn-export').forEach(btn=>btn.addEventListener('click',(e)=>{ e.stopPropagation(); exportSession(btn.dataset.export, btn); }));
}
function sortSessions(rows){ const k=state.sortKey,d=state.sortDir; return [...rows].sort((a,b)=>{ let av=a[k],bv=b[k]; if(k==='tokens'){av=(a.input_tokens||0)+(a.output_tokens||0);bv=(b.input_tokens||0)+(b.output_tokens||0);} if(av==null)av=''; if(bv==null)bv=''; return (typeof av==='string'?av.localeCompare(bv):av-bv)*d; }); }

/* ── Search ───────────────────────────────────────────────────── */
function highlight(text,q){ if(!q) return esc(text); const re=new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')})`,'gi'); return esc(text).replace(re,'<mark>$1</mark>'); }
let searchTimer=null;
async function doSearch() {
  const q=$('#search-input').value.trim(), el=$('#search-results');
  if(!q){ el.textContent=''; return; }
  el.textContent=''; const spin=document.createElement('span'); spin.className='spinner'; el.appendChild(spin);
  const data=await api('/api/search',{q});
  el.textContent='';
  if(!data.results?.length){ setHTML(el,`<div class="empty-state"><h3>No results</h3><p>No events matched "${esc(q)}" in the selected period.</p><button class="ghost-btn" data-action="clear-search">Clear search</button></div>`); return; }
  setHTML(el, data.results.map(r=>`<div class="search-result" data-run="${esc(r.run_id)}"><div class="search-result-meta">${badge(r.source)} ${fmtDate(r.started_at)} ${r.cost!=null?`<span class="source-badge">${fmtCost(r.cost)}</span>`:''}</div><div class="search-result-excerpt">${highlight(r.excerpt||'',q)}</div></div>`).join(''));
  $$('.search-result').forEach(e=>e.addEventListener('click',()=>{ window.location.href=`/session.html?id=${e.dataset.run}`; }));
}

async function exportSession(runId, btn) {
  const done = btn ? actionState(btn, 'Exporting…') : () => {};
  try {
    const res = await postJSON('/api/action/share', { run_id: runId });
    if (!res.ok || !res.html) { toast('Export failed', 'error'); return; }
    const blob = new Blob([res.html], { type: 'text/html' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `cairn-session-${runId.slice(0, 8)}.html`;
    a.click();
    URL.revokeObjectURL(a.href);
    toast('Exported scrubbed HTML', 'good');
  } catch (e) { toast('Export failed: ' + e.message, 'error'); }
  finally { done(); }
}

/* ── Settings ─────────────────────────────────────────────────── */
async function loadSettings() {
  const data = await fetch('/api/config').then(r=>r.json());
  state.config = data.config||{};
  const sections=[['agents','Agents',['sources','paths','rescan']],['pricing','Pricing',['overrides','edit_table']],
    ['outcomes','Outcomes',['test_command','build_command','git']],['optimize','Optimize',['auto','backend','holdout','prune_threshold']],
    ['budgets','Budgets',['daily_usd','weekly_usd','daily_tokens','weekly_tokens']],['mcp','MCP',['client','auto_install']],['data','Data',['ledger','re_ingest','clear']]];
  let html='';
  for(const [key,title,keys] of sections) html+=`<div class="settings-section"><h2>${title}</h2>${keys.map(k=>settingsRow(key,k,(state.config[key]||{})[k])).join('')}</div>`;
  html+=`<div class="settings-section"><h2>Actions</h2>
    <div class="settings-row"><div><div class="sr-label">Rescan agents</div><div class="sr-help">re-detect agent history</div></div><button class="ghost-btn" id="btn-rescan">Rescan</button></div>
    <div class="settings-row"><div><div class="sr-label">Backfill / re-ingest</div><div class="sr-help">recompute rollups</div></div><button class="ghost-btn" id="btn-backfill">Backfill</button></div>
    <div class="settings-row"><div><div class="sr-label">Budget check</div><div class="sr-help">run the gate, show pass/fail</div></div><button class="ghost-btn" id="btn-check">Run check</button></div>
    <div class="settings-row"><div><div class="sr-label">Install MCP</div><div class="sr-help">cursor · claude · codex</div></div><div><button class="ghost-btn" data-mcp="cursor">cursor</button> <button class="ghost-btn" data-mcp="claude">claude</button> <button class="ghost-btn" data-mcp="codex">codex</button></div></div>
    <div class="settings-row"><div><div class="sr-label">Pick a folder to scan</div><div class="sr-help">open a project</div></div><button class="ghost-btn" id="btn-pick">Pick folder</button></div>
    <div class="settings-row"><div><div class="sr-label">Reset to defaults</div><div class="sr-help">clears config.toml</div></div><button class="ghost-btn" id="btn-reset">Reset to defaults</button></div>
  </div>`;
  setHTML($('#settings-content'), html);
  bindSettings();
}
function settingsRow(section,key,val) {
  if(key==='auto' || key==='auto_install' || key==='git' || key==='re_ingest' || key==='clear' || key==='ledger') {
    const on = (val === undefined && key === 'auto_install') ? true
      : (val === true || val === 'true' || String(val).toLowerCase() === 'true');
    return `<div class="settings-row"><div class="sr-label">${esc(key)}</div><label class="stone-switch ${on?'on':''}" data-section="${section}" data-key="${key}"><span class="track"></span>${on?'on':'off'}</label></div>`;
  }
  return `<div class="settings-row"><div class="sr-label">${esc(key)}</div><input type="text" data-section="${section}" data-key="${key}" value="${esc(val??'')}"></div>`;
}
function bindSettings() {
  $$('#settings-content input').forEach(inp=>inp.addEventListener('change', ()=>saveSetting(inp.dataset.section, inp.dataset.key, inp.value)));
  $$('#settings-content .stone-switch').forEach(sw=>sw.addEventListener('click', ()=>{
    const on=!sw.classList.contains('on'); sw.classList.toggle('on',on); setHTML(sw,`<span class="track"></span>${on?'on':'off'}`);
    saveSetting(sw.dataset.section, sw.dataset.key, on);
  }));
  $('#btn-rescan')?.addEventListener('click', async (e)=>{ const done=actionState(e.target,'Scanning…'); await addJob('rescan', fetch('/api/setup/scan').then(x=>x.json())); done(); toast('Rescan complete'); });
  $('#btn-backfill')?.addEventListener('click', async (e)=>{ const done=actionState(e.target,'Backfilling…'); await addJob('backfill', postJSON('/api/action/backfill',{})); done(); toast('Backfill complete','good'); });
  $('#btn-check')?.addEventListener('click', async (e)=>{ const done=actionState(e.target,'Checking…'); const r=await postJSON('/api/action/check',{}); done(); toast(r.pass?'Check passed':'Check failed: '+(r.reasons||[]).join('; '), r.pass?'good':'error'); });
  $('#btn-pick')?.addEventListener('click', pickFolder);
  $('#btn-reset')?.addEventListener('click', async ()=>{ await postJSON('/api/config',{}); toast('Reset to defaults','good'); loadSettings(); });
  $$('[data-mcp]').forEach(b=>b.addEventListener('click', async ()=>{ const r=await postJSON('/api/action/mcp_install',{client:b.dataset.mcp}); toast(`MCP config ready for ${b.dataset.mcp}`,'good'); addJob('mcp install '+b.dataset.mcp, Promise.resolve(r)); }));
}
async function saveSetting(section,key,value) {
  const cfg=state.config; cfg[section]=cfg[section]||{}; cfg[section][key]=value;
  try { await postJSON('/api/config', cfg); toast('saved','good'); }
  catch(e){ toast('Save failed: '+e.message,'error'); }
}

/* ── First-run onboarding ─────────────────────────────────────── */
let onboardingShown=false;
async function maybeShowOnboarding() {
  if (localStorage.getItem('cairn-onboarded')==='1' || onboardingShown) return;
  onboardingShown=true;
  const scan = await fetch('/api/setup/scan').then(r=>r.json()).catch(()=>({agents:[],total_sessions:0}));
  const mount=$('#onboard-mount');
  const agents=scan.agents||[];
  const log = agents.length ? agents.map(a=>`✓ ${a.source} — ${a.sessions_seen} session${a.sessions_seen===1?'':'s'} (${a.path||'detected'})`).join('\n') : 'scanning… no agent history found yet';
  const picker = !agents.length ? `<div class="supported-list">supported: claude-code · codex · cursor · aider · goose · opencode · hermes</div>
    <button class="btn btn-primary" id="onboard-pick">Pick a folder to scan</button>` : '';
  setHTML(mount, `<div class="onboard"><div class="onboard-card">
    <span class="cairn-glyph es-glyph"><span class="stone base"></span><span class="stone mid"></span><span class="stone top"></span></span>
    <h1>Cairn is mapping your agents.</h1>
    <p>Live detection log:</p>
    <div class="detect-log" id="detect-log">${esc(log)}</div>
    ${picker}
    <div class="onboard-steps">
      <div class="onboard-step">Sync your agent history into the local ledger.</div>
      <div class="onboard-step">Open the dashboard to read spend, waste, and drift.</div>
      <div class="onboard-step">Apply optimize rules to lower re-billing.</div>
    </div>
    <button class="btn btn-primary" id="onboard-start">Start</button>
  </div></div>`);
  $('#onboard-start')?.addEventListener('click', ()=>{ localStorage.setItem('cairn-onboarded','1'); mount.textContent=''; doSync(); });
  $('#onboard-pick')?.addEventListener('click', pickFolder);
  if (agents.length) { setTimeout(()=>{ localStorage.setItem('cairn-onboarded','1'); }, 300); }
}

/* ── Sync + actions ───────────────────────────────────────────── */
async function doSync() {
  const btn=$('#btn-sync'); const done=actionState(btn,'Syncing…');
  const r=await addJob('sync', postJSON('/api/action/sync',{}));
  done();
  toast(r.ok?`Synced ${r.inserted||0} sessions`:'Sync failed', r.ok?'good':'error');
  onMetricsUpdated();
}
function pickFolder() {
  const inp=document.createElement('input'); inp.type='file'; inp.webkitdirectory=true; inp.style.display='none';
  inp.addEventListener('change', ()=>{ if(inp.files[0]) toast(`Picked ${inp.files[0].webkitRelativePath||inp.files[0].name}`); doSync(); });
  document.body.appendChild(inp); inp.click(); inp.remove();
}

/* ── Gauge ────────────────────────────────────────────────────── */
async function loadGauge() {
  try { const g=await fetch('/api/gauge').then(r=>r.json());
    const used=g.total_tokens||0, limit=g.limit;
    if(!used && !limit){ $('#gauge-widget').style.display='none'; return; }
    $('#gauge-widget').style.display='block';
    const pct=limit?Math.min(100,used/limit*100):0;
    const fill=$('#gauge-fill'); fill.style.width=`${pct}%`; fill.classList.toggle('warn',pct>80);
    $('#gauge-value').textContent = limit?`${fmtTokens(used)} / ${fmtTokens(limit)}`:`${fmtTokens(used)} tok · no limit`;
    $('#gauge-label').textContent = `plan window · ${g.window_hours||5}h${g.exceeded?' · exceeded':''}`;
  } catch { $('#gauge-widget').style.display='none'; }
}

/* ── Nav ──────────────────────────────────────────────────────── */
const PAGES = { overview:loadOverview, context:loadContext, behavior:loadBehavior, quality:loadQuality, charts:loadCharts, insights:loadInsights, optimize:loadOptimize, sessions:loadSessions, settings:loadSettings };
function navTo(page) {
  $$('#nav .nav-item').forEach(b=>b.classList.toggle('active', b.dataset.page===page));
  $$('.page').forEach(p=>p.classList.remove('active'));
  $(`#page-${page}`).classList.add('active');
  requestAnimationFrame(()=>Object.values(state.charts).forEach(c=>c?.resize?.()));
  PAGES[page]?.();
}
function setupNav(){ $$('#nav .nav-item').forEach(b=>b.addEventListener('click',()=>navTo(b.dataset.page))); }

async function refreshAll(){
  try { await Promise.all([loadOverview(), loadGauge()]); }
  catch (e) { console.warn('refresh failed', e); }
}
function refreshActivePage() {
  const page = document.querySelector('#nav .nav-item.active')?.dataset.page;
  if (page && page !== 'overview' && PAGES[page]) PAGES[page]();
}
function onMetricsUpdated() { refreshAll(); refreshActivePage(); }
async function verifyProjectRoot() {
  try {
    const scan = await fetch('/api/setup/scan', { cache: 'no-store' }).then(r => r.json());
    const root = scan.project_root || '';
    const prev = localStorage.getItem('cairn-project-root');
    if (prev && root && prev !== root) onMetricsUpdated();
    if (root) localStorage.setItem('cairn-project-root', root);
  } catch { /* optional */ }
}

/* ── Init ─────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  COPPER = cssVar('--copper') || COPPER;
  configureChartDefaults();
  setupNav();
  const sidebar=$('#sidebar');
  if(localStorage.getItem('cairn-rail')==='collapsed') sidebar.classList.add('collapsed');
  $('#rail-toggle')?.addEventListener('click', ()=>{ sidebar.classList.toggle('collapsed'); localStorage.setItem('cairn-rail', sidebar.classList.contains('collapsed')?'collapsed':'expanded'); });
  $('#btn-sync')?.addEventListener('click', doSync);
  $('#btn-actions')?.addEventListener('click', ()=>$('#action-panel').classList.toggle('open'));
  document.addEventListener('click', (e)=>{ if(!e.target.closest('#action-panel') && !e.target.closest('#btn-actions')) $('#action-panel').classList.remove('open'); });
  // delegated next-action buttons in empty/error states (DOMPurify keeps data-*)
  document.addEventListener('click', (e)=>{ const btn=e.target.closest('[data-action]'); if(!btn) return;
    const a=btn.dataset.action;
    if(a==='sync') doSync();
    else if(a==='settings') navTo('settings');
    else if(a==='sessions') navTo('sessions');
    else if(a==='context') navTo('context');
    else if(a==='behavior') navTo('behavior');
    else if(a==='clear-search'){ $('#search-input').value=''; $('#search-results').textContent=''; }
  });
  const wt=$('#watch-toggle'); const watchOn=localStorage.getItem('cairn-watch')!=='0'; wt.classList.toggle('on',watchOn); state.watch=watchOn;
  wt.addEventListener('click', ()=>{ state.watch=!state.watch; wt.classList.toggle('on',state.watch); localStorage.setItem('cairn-watch', state.watch?'1':'0'); setupSSE(); });
  $$('#all-sessions th').forEach((th,i)=>{ const key=['started_at','source',null,'turns','tokens','total_cost','waste_tokens','tool_errors','model','project'][i]; if(!key)return;
    th.addEventListener('click', ()=>{ if(state.sortKey===key) state.sortDir*=-1; else {state.sortKey=key; state.sortDir=-1;} $$('#all-sessions th').forEach(t=>t.classList.remove('sorted')); th.classList.add('sorted'); loadSessions(); }); });
  $('#search-input')?.addEventListener('input', ()=>{ clearTimeout(searchTimer); searchTimer=setTimeout(doSearch, 240); });
  requestAnimationFrame(()=>document.body.classList.add('ready'));
  verifyProjectRoot().then(() => refreshAll());
  setupSSE();
  maybeMcpAutoInstall();
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') onMetricsUpdated();
  });
  window.addEventListener('pageshow', (e) => {
    if (e.persisted) onMetricsUpdated();
  });
});

async function maybeMcpAutoInstall() {
  if (localStorage.getItem('cairn-mcp-auto') === '1') return;
  try {
    const r = await postJSON('/api/action/mcp_auto_install', {});
    if (r.installed?.length) {
      localStorage.setItem('cairn-mcp-auto', '1');
      const name = r.installed[0];
      const label = name.charAt(0).toUpperCase() + name.slice(1);
      toast(`MCP installed for ${label}`, 'good');
    }
  } catch { /* optional */ }
}
let es=null;
function setupSSE(){ if(es) es.close(); if(!state.watch) return; try { es=new EventSource('/v2/events');
  es.addEventListener('metrics-updated', onMetricsUpdated);
  es.addEventListener('optimize-proposals', ()=>loadOptimize());
} catch {} }
