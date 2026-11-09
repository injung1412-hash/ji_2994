'use strict';
/* 산업연관표 분석 웹앱 — 화면 동작 (계산은 worker.js → model.py) */
const $ = (id) => document.getElementById(id);
const LEVELS = ['basic', 'small', 'mid', 'large'];
const LEVEL_LABEL = { basic: '기본부문(380)', small: '통합소분류(165)', mid: '통합중분류(83)', large: '통합대분류(33)' };
const FILES = {
  basic: './data/io-2023-basic.xlsx', small: './data/io-2023-small.xlsx',
  mid: './data/io-2023-mid.xlsx', large: './data/io-2023-large.xlsx',
  cls: './data/classification-2020.xlsx', stats: './data/io-2023-stats.xlsx',
};
const FD_ITEMS = ['최종수요계', '소비', '민간소비지출', '정부소비지출', '투자', '민간고정자본형성', '정부고정자본형성', '재고증감', '귀중품순취득', '수출'];

const state = {
  worker: null, nextId: 0, pending: new Map(),
  loaded: {}, aux: null, active: null, tab: 'explorer',
  cache: {}, basket: [], simResult: null, clsRows: null, busy: false,
};

/* ---------------- 공통 유틸 ---------------- */
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k != null) e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
}
function fmt(v, d = 0) {
  if (v == null || v === '' || Number.isNaN(Number(v))) return '–';
  return Number(v).toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d });
}
const fmtAuto = (v) => (v == null ? '–' : Math.abs(v) >= 100 ? fmt(v, 0) : Math.abs(v) >= 1 ? fmt(v, 3) : fmt(v, 4));
function korMoney(mil) { // 백만원 → 사람이 읽기 쉬운 표기
  if (mil == null) return '';
  const a = Math.abs(mil);
  if (a >= 1e6) return '≈ ' + fmt(mil / 1e6, 2) + '조원';
  if (a >= 100) return '≈ ' + fmt(mil / 100, 1) + '억원';
  return '≈ ' + fmt(mil * 100, 0) + '만원';
}
function debounce(f, ms = 200) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => f(...a), ms); }; }
function setStatus(id, text, kind) { const e = $(id); if (!e) return; e.textContent = text; e.dataset.kind = kind || ''; }
function needLevel(statusId) {
  if (state.active) return true;
  if (statusId) setStatus(statusId, '먼저 위의 「자료 불러오기」에서 투입산출표를 불러오세요.');
  return false;
}
const sectorsOf = (key) => (state.loaded[key] ? state.loaded[key].sectors : []);

/* ---------------- Worker 호출 ---------------- */
function startWorker() {
  state.worker = new Worker('./worker.js');
  state.worker.onmessage = ({ data: d }) => {
    if (d.type === 'status') { setStatus('status', d.text); if (d.pct != null) progress(d.pct); return; }
    const p = state.pending.get(d.id); if (!p) return;
    state.pending.delete(d.id);
    d.ok ? p.resolve(d.result) : p.reject(new Error(d.error));
  };
  state.worker.onerror = (e) => {
    for (const p of state.pending.values()) p.reject(new Error(e.message || 'Worker 실행 오류'));
    state.pending.clear();
  };
}
function call(fn, args = [], buffers = null) {
  if (!state.worker) startWorker();
  return new Promise((resolve, reject) => {
    const id = ++state.nextId;
    state.pending.set(id, { resolve, reject });
    const transfer = (buffers || []).filter((b) => b instanceof ArrayBuffer);
    state.worker.postMessage({ id, fn, args, buffers }, transfer);
  });
}
function progress(p) { $('progress-bar').style.width = Math.max(0, Math.min(100, p)) + '%'; }

async function fetchBuf(url, label, p0, p1) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(label + ' 내려받기 실패 (HTTP ' + res.status + ')');
  const total = Number(res.headers.get('content-length')) || 0;
  if (!res.body || !total) return await res.arrayBuffer();
  const reader = res.body.getReader(); const chunks = []; let got = 0;
  for (;;) {
    const { done, value } = await reader.read(); if (done) break;
    chunks.push(value); got += value.length;
    setStatus('status', label + ' 내려받는 중… ' + Math.round(got / total * 100) + '%');
    progress(p0 + (p1 - p0) * got / total);
  }
  const out = new Uint8Array(got); let o = 0;
  for (const c of chunks) { out.set(c, o); o += c.length; }
  return out.buffer;
}

/* ---------------- 불러오기 ---------------- */
async function ensureAux() {
  if (state.aux) return;
  const cls = await fetchBuf(FILES.cls, '부문분류표', 30, 33);
  const stats = await fetchBuf(FILES.stats, '통계표', 33, 36);
  setStatus('status', '부문분류표·통계표 읽는 중…');
  state.aux = await call('load_aux', [], [cls, stats]);
}
async function loadLevel(key, buffer, sourceLabel) {
  const btn = document.querySelector('.load-btn[data-level="' + key + '"]');
  setCard(btn, 'loading', '불러오는 중…');
  try {
    await ensureAux();
    if (!buffer) buffer = await fetchBuf(FILES[key], LEVEL_LABEL[key] + ' 엑셀', 36, 70);
    setStatus('status', LEVEL_LABEL[key] + ' 12개 시트 읽기·계수 검증 중… (기본부문은 수십 초 걸릴 수 있음)');
    progress(80);
    const info = await call('load_level', [key], [buffer]);
    info.source = sourceLabel || FILES[key];
    state.loaded[key] = info; state.cache[key] = {};
    setCard(btn, 'done', info.check.passed ? '검증 통과' : '확인 필요');
    progress(100);
    const ck = info.check;
    setStatus('status', LEVEL_LABEL[key] + ' 준비 완료 · ' + info.n + '개 부문 · ' + info.sheets.length + '개 시트 · '
      + (ck.passed ? '원표 계수 대조 통과(최대 오차 ' + ck.max_coef_residual.toExponential(1) + ')' : '⚠ 원표 대조 차이 있음(⑩ 검증 참조)'));
    setActive(key);
    return true;
  } catch (e) {
    setStatus('status', '불러오기 실패: ' + e.message + ' — 인터넷 연결을 확인하고 새로고침 후 다시 시도하세요.');
    setCard(btn, 'error', '다시 시도');
    progress(0);
    return false;
  }
}
function setCard(btn, st, text) {
  if (!btn) return;
  btn.dataset.state = st;
  const t = btn.querySelector('.lv-state'); if (t) t.textContent = text;
}
function setBusy(b) {
  state.busy = b;
  document.querySelectorAll('.load-btn, #load-all, .quick-load').forEach((x) => { x.disabled = b; });
  $('upload-file').disabled = b;
}
async function loadAll() {
  if (state.busy) return; setBusy(true);
  for (const k of ['large', 'mid', 'small', 'basic']) {
    if (state.loaded[k]) continue;
    if (!(await loadLevel(k))) break;
  }
  if (Object.keys(state.loaded).length === 4) setStatus('status', '4개 분류 모두 준비 완료 — 왼쪽에서 분석 기준 분류와 화면을 고르세요.');
  setBusy(false);
}
document.querySelectorAll('.lv-glyph').forEach((g) => {
  const n = Number(g.dataset.n); const frag = document.createDocumentFragment();
  for (let i = 0; i < n; i++) frag.append(document.createElement('i'));
  g.append(frag);
});
document.querySelectorAll('.quick-load').forEach((b) => b.addEventListener('click', async () => {
  if (b.dataset.level === 'all') return loadAll();
  if (state.busy) return; setBusy(true); await loadLevel(b.dataset.level); setBusy(false);
}));
document.querySelectorAll('.load-btn[data-level]').forEach((b) => b.addEventListener('click', async () => {
  if (state.busy) return; setBusy(true);
  await loadLevel(b.dataset.level); setBusy(false);
}));
$('load-all').addEventListener('click', loadAll);
$('upload-file').addEventListener('change', async (e) => {
  const f = e.target.files[0]; if (!f || state.busy) return;
  setBusy(true);
  await loadLevel($('upload-level').value, await f.arrayBuffer(), '사용자 파일: ' + f.name);
  setBusy(false); e.target.value = '';
});

function setActive(key) {
  state.active = key;
  document.body.classList.add('has-data');
  document.querySelectorAll('#level-seg button').forEach((b) => {
    b.disabled = !state.loaded[b.dataset.level];
    b.setAttribute('aria-pressed', b.dataset.level === key ? 'true' : 'false');
  });
  $('seg-empty').textContent = '현재: ' + LEVEL_LABEL[key] + ' · 불러온 분류만 고를 수 있습니다.';
  $('level-badges').replaceChildren(...LEVELS.filter((k) => state.loaded[k]).map((k) =>
    el('span', { class: 'badge' + (state.loaded[k].check.passed ? ' ok' : ''), text: LEVEL_LABEL[k] })));
  state.basket = []; renderBasket(); $('sim-result').hidden = true;
  fillExplorerDatasets();
  ['ex-dataset', 'ex-sheet', 'ex-mode', 'ex-search', 'ex-item', 'ex-filter', 'cl-q'].forEach((id) => { $(id).disabled = false; });
  refreshPickers();
  renderTab();
  fillHero();
  renderLevelSummary();
}
async function fillHero() {
  try {
    const d = await getCached('structure', 'structure', [state.active]);
    const m = Object.fromEntries(d.macro.map((x) => [x.name, x.value]));
    const t = (v) => fmt(v, 1);
    $('hero-z').textContent = t(m['중간투입']);
    $('hero-va').textContent = t(m['부가가치']);
    $('hero-x').textContent = t(m['총산출']); $('hero-x2').textContent = t(m['총산출']);
    $('hero-f').textContent = t(m['총공급(=총수요)'] - m['중간투입']);
    $('hero-note').textContent = '수입 ' + t(m['수입']) + '조원 · 총공급 ' + t(m['총공급(=총수요)']) + '조원 · 부가가치율 ' + t(m['부가가치율'])
      + '% · 중간투입률 ' + t(m['중간투입률']) + '%';
    $('hero-src').textContent = '불러온 원표로 계산';
  } catch (e) { /* 구조도 갱신 실패는 분석에 영향 없음 */ }
}
document.querySelectorAll('#level-seg button').forEach((b) => b.addEventListener('click', () => {
  if (state.loaded[b.dataset.level] && b.dataset.level !== state.active) setActive(b.dataset.level);
}));

/* ---------------- 탭 ---------------- */
document.querySelectorAll('.tabs [role=tab]').forEach((b) => b.addEventListener('click', () => {
  state.tab = b.dataset.tab;
  document.querySelectorAll('.tabs [role=tab]').forEach((x) => x.setAttribute('aria-selected', x === b ? 'true' : 'false'));
  document.querySelectorAll('.tab').forEach((s) => { s.hidden = s.id !== 'tab-' + state.tab; });
  const panel = $('tab-' + state.tab); const top = panel.getBoundingClientRect().top;
  if (top < 0 || top > window.innerHeight * 0.6) panel.scrollIntoView({ block: 'start', behavior: 'smooth' });
  renderTab();
}));
function renderTab() {
  const t = state.tab;
  if (t === 'explorer') return state.active && !$('ex-sheet').options.length ? fillExplorerDatasets() : null;
  if (t === 'classify') return runClassify();
  if (t === 'structure') return renderStructure();
  if (t === 'linkage') return renderLinkage();
  if (t === 'mult') return renderMult();
  if (t === 'fd') return renderFd();
  if (t === 'verify') return renderVerifyLevels();
  if (t === 'price') return syncPriceDefaults();
  return null;
}

/* ---------------- 공통 표(정렬·CSV) ---------------- */
function makeTable(table, cols, rows, opts = {}) {
  table._cols = cols; table._rows = rows; table._opts = opts;
  if (opts.sort && !table._sort) table._sort = opts.sort;
  drawTable(table);
}
function drawTable(table) {
  const cols = table._cols; let rows = table._rows.slice(); const opts = table._opts || {};
  if (opts.filter) rows = rows.filter(opts.filter);
  const s = table._sort;
  if (s) {
    const c = cols.find((x) => x.key === s.key);
    rows.sort((a, b) => {
      const va = a[s.key], vb = b[s.key];
      if (va == null) return 1; if (vb == null) return -1;
      const r = c && c.num ? va - vb : String(va).localeCompare(String(vb), 'ko');
      return s.dir === 'asc' ? r : -r;
    });
  }
  const thead = el('thead', null, el('tr', null, cols.map((c) => {
    const th = el('th', { class: (c.num ? 'num ' : '') + (opts.nosort ? '' : 'sortable'), scope: 'col', title: c.title || null }, c.label);
    if (s && s.key === c.key) th.setAttribute('aria-sort', s.dir === 'asc' ? 'ascending' : 'descending');
    if (!opts.nosort) th.addEventListener('click', () => {
      table._sort = { key: c.key, dir: s && s.key === c.key && s.dir === 'desc' ? 'asc' : 'desc' };
      if (!c.num && (!s || s.key !== c.key)) table._sort.dir = 'asc';
      drawTable(table);
    });
    return th;
  })));
  const tbody = el('tbody', null, rows.map((r) => el('tr', { class: (opts.rowClass && opts.rowClass(r)) || null },
    cols.map((c) => {
      const v = r[c.key];
      const txt = c.fmt ? c.fmt(v, r) : c.num ? fmt(v, c.d ?? 0) : (v ?? '');
      return el('td', { class: [(c.num ? 'num' : ''), c.cls ? c.cls(v, r) : ''].join(' ').trim() || null }, txt);
    }))));
  const cap = table.querySelector('caption');
  table.replaceChildren(...(cap ? [cap] : []), thead, tbody);
}
function csvCell(v) {
  let s = v == null ? '' : String(v);
  if (typeof v !== 'number' && /^[=+\-@]/.test(s)) s = "'" + s;
  return '"' + s.replaceAll('"', '""') + '"';
}
document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-csv]'); if (!b) return;
  const t = $(b.dataset.csv); if (!t || !t._rows) return;
  const cols = t._cols;
  const lines = [cols.map((c) => csvCell(c.label)).join(','), ...t._rows.map((r) => cols.map((c) => csvCell(r[c.key])).join(','))];
  const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = el('a', { href: url, download: 'io-2023-' + (state.active || '') + '-' + b.dataset.csv + '.csv' });
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});

/* ---------------- 막대그래프·툴팁 ---------------- */
const tip = $('tooltip');
function showTip(e, html) { tip.innerHTML = html; tip.hidden = false; moveTip(e); }
function moveTip(e) {
  const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
  const y = Math.min(e.clientY + 14, window.innerHeight - tip.offsetHeight - 8);
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
function hideTip() { tip.hidden = true; }
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function renderBars(box, items, { unit = '', d = 0, inner = null, innerLabel = '', outerLabel = '' } = {}) {
  if (!items.length) { box.replaceChildren(el('p', { class: 'muted', text: '표시할 항목이 없습니다.' })); return; }
  const maxPos = Math.max(0, ...items.map((i) => Math.max(i.value, inner ? i[inner] || 0 : 0)));
  const maxNeg = Math.max(0, ...items.map((i) => -Math.min(i.value, inner ? i[inner] || 0 : 0)));
  const span = (maxPos + maxNeg) || 1; const zero = maxNeg / span * 100;
  const rows = items.map((i) => {
    const track = el('div', { class: 'track' });
    if (maxNeg > 0) track.append(el('div', { class: 'zero', style: 'left:' + zero + '%' }));
    const add = (v, cls) => {
      if (!v) return; const w = Math.abs(v) / span * 100;
      track.append(el('div', { class: 'fill' + (v < 0 ? ' neg' : '') + (cls ? ' ' + cls : ''),
        style: (v < 0 ? 'left:' + (zero - w) : 'left:' + zero) + '%;width:' + Math.max(w, 0.3) + '%' }));
    };
    if (inner) { add(i.value, 'soft'); add(i[inner]); } else add(i.value);
    const row = el('div', { class: 'bar' }, el('span', { class: 'lbl', title: i.label, text: i.label }), track,
      el('span', { class: 'val', text: fmt(i.value, d) + (unit ? ' ' + unit : '') }));
    row.addEventListener('mousemove', (e) => showTip(e, '<b>' + esc(i.label) + '</b><br>' + (outerLabel || '값') + ': ' + fmt(i.value, d) + ' ' + unit
      + (inner ? '<br>' + innerLabel + ': ' + fmt(i[inner], d) + ' ' + unit : '') + (i.extra ? '<br>' + i.extra : '')));
    row.addEventListener('mouseleave', hideTip);
    return row;
  });
  const hasPos = maxPos > 0, hasNeg = maxNeg > 0;
  const sw = (pos, neg) => [hasPos ? el('i', { style: 'background:var(' + pos + ')' }) : null, hasNeg ? el('i', { style: 'background:var(' + neg + ')' }) : null];
  const legend = inner ? el('div', { class: 'legend' },
    el('span', null, ...sw('--data', '--neg'), innerLabel),
    el('span', null, ...sw('--data-soft', '--neg-soft'), outerLabel),
    hasPos && hasNeg ? el('span', { text: '(파랑=증가, 빨강=감소)' }) : null) : null;
  box.replaceChildren(...(legend ? [legend] : []), ...rows);
}

/* ---------------- 부문 선택기 ---------------- */
const pickers = [];
function bindPicker(qId, selId, onChange, opts = {}) {
  const q = $(qId), sel = $(selId);
  const p = { q, sel, onChange, opts };
  p.fill = (keep) => {
    const list = opts.list ? opts.list() : sectorsOf(state.active);
    const t = q.value.trim().toLowerCase();
    const cur = keep || sel.value;
    const shown = list.filter((s) => !t || (s.code + ' ' + s.name).toLowerCase().includes(t));
    sel.replaceChildren(...shown.map((s) => el('option', { value: s.code, text: s.code + ' ' + s.name })));
    if (shown.some((s) => s.code === cur)) sel.value = cur;
  };
  q.addEventListener('input', () => { p.fill(); if (onChange && sel.value) onChange(sel.value); });
  sel.addEventListener('change', () => onChange && onChange(sel.value));
  pickers.push(p); return p;
}
function refreshPickers() { pickers.forEach((p) => { if (!p.opts.list) { p.q.value = ''; p.fill(); } }); }
function findSector(keywords, key = state.active) {
  const list = sectorsOf(key);
  for (const k of keywords) { const s = list.find((x) => x.name.includes(k) || x.code === k); if (s) return s.code; }
  return list[0] && list[0].code;
}

/* ================= ① 원자료 탐색 ================= */
function fillExplorerDatasets() {
  const ds = $('ex-dataset'); const cur = ds.value;
  const opts = LEVELS.filter((k) => state.loaded[k]).map((k) => el('option', { value: k, text: '투입산출표 — ' + LEVEL_LABEL[k] }));
  if (state.aux) {
    opts.push(el('option', { value: 'stats', text: '별첨 통계표 20종 (2020~2023 시계열)' }));
    opts.push(el('option', { value: 'cls', text: '2020 기준년 상품분류표(부문분류)' }));
  }
  ds.replaceChildren(...opts);
  const keepAux = (cur === 'stats' || cur === 'cls');
  ds.value = keepAux ? cur : (state.active || 'stats');
  fillExplorerSheets();
}
function fillExplorerSheets() {
  const ds = $('ex-dataset').value; const sh = $('ex-sheet');
  let sheets = [];
  if (state.loaded[ds]) sheets = state.loaded[ds].sheets;
  else if (ds === 'stats') sheets = state.aux.stats_sheets.filter((s) => s !== '목차');
  else if (ds === 'cls') sheets = ['부문분류'];
  sh.replaceChildren(...sheets.map((s) => el('option', { value: s, text: s })));
  const io = !!state.loaded[ds];
  $('ex-pick').hidden = !io; $('ex-mode').disabled = !io;
  $('ex-search').value = ''; $('ex-filter').value = '';
  state.exSel = null;
  explore();
}
let exSeq = 0;
async function explore() {
  const ds = $('ex-dataset').value, sheet = $('ex-sheet').value, mode = $('ex-mode').value;
  if (!ds || !sheet) return;
  const seq = ++exSeq;
  try {
    const d = await call('explore', [ds, sheet, mode, state.exSel]);
    if (seq !== exSeq) return;
    state.ex = d;
    if (d.mode === 'grid') return renderGrid(d);
    if (d.mode === 'cls') return renderClsTable(d.rows);
    state.exSel = d.selected;
    fillExItems();
    $('ex-unit').textContent = '단위: ' + d.unit + ' · 각 셀의 단위는 표의 「단위」 열 참조';
    $('ex-caption').textContent = sheet + ' / ' + (d.mode === 'row' ? '행 ' : '열 ') + d.selected + ' ' + d.name + ' — ' + d.title;
    renderExCells();
  } catch (e) { $('ex-caption').textContent = '오류: ' + e.message; }
}
function fillExItems() {
  const d = state.ex; const list = d.mode === 'row' ? d.rows : d.cols;
  const t = $('ex-search').value.trim().toLowerCase();
  const shown = list.filter((r) => !t || (r.code + ' ' + r.name).toLowerCase().includes(t));
  $('ex-item').replaceChildren(...shown.map((r) => el('option', { value: r.code, text: r.code + ' ' + r.name })));
  if (shown.some((r) => r.code === d.selected)) $('ex-item').value = d.selected;
}
function renderExCells() {
  const d = state.ex; const t = $('ex-filter').value.trim().toLowerCase();
  const table = $('ex-table');
  makeTable(table, [
    { key: 'code', label: d.mode === 'row' ? '열 코드' : '행 코드' },
    { key: 'name', label: d.mode === 'row' ? '열 이름' : '행 이름' },
    { key: 'value', label: '원자료 값', num: true, fmt: (v) => (v == null ? '빈 셀' : typeof v === 'number' ? fmtAuto(v) : v) },
    { key: 'unit', label: '단위' },
  ], d.cells, { filter: (r) => !t || (r.code + ' ' + r.name).toLowerCase().includes(t), nosort: false });
}
function renderGrid(d) {
  $('ex-unit').textContent = '단위: ' + d.unit + ' (통계표 원문 그대로, 2020~2023년 당해년 가격)';
  $('ex-caption').textContent = d.title;
  const t = $('ex-filter').value.trim().toLowerCase();
  const rows = d.grid.filter((r) => !t || r.join(' ').toLowerCase().includes(t));
  const table = $('ex-table'); const cap = table.querySelector('caption');
  table._rows = null;
  table.replaceChildren(cap, el('tbody', null, rows.map((r) => el('tr', null, r.map((v) =>
    el('td', { class: typeof v === 'number' ? 'num' : null }, typeof v === 'number' ? fmtAuto(v) : v))))));
}
function renderClsTable(rows) {
  $('ex-unit').textContent = '코드 체계: 기본부문 4자리 · 통합소분류 3자리 · 통합중분류 2자리 · 통합대분류 알파벳(A~T, 제조업 C01~C14)';
  $('ex-caption').textContent = '2020 기준년 상품분류(투입산출표) — 380개 기본부문';
  const t = $('ex-filter').value.trim().toLowerCase();
  makeTable($('ex-table'), clsCols(), rows, { filter: (r) => !t || Object.values(r).join(' ').toLowerCase().includes(t) });
}
function clsCols(extra = []) {
  return [
    { key: 'basic', label: '기본부문' }, { key: 'basic_name', label: '기본부문명' },
    { key: 'small', label: '소분류' }, { key: 'small_name', label: '소분류명' },
    { key: 'mid', label: '중분류' }, { key: 'mid_name', label: '중분류명' },
    { key: 'large', label: '대분류' }, { key: 'large_name', label: '대분류명' }, ...extra,
  ];
}
$('ex-dataset').addEventListener('change', fillExplorerSheets);
$('ex-sheet').addEventListener('change', () => { state.exSel = null; $('ex-search').value = ''; explore(); });
$('ex-mode').addEventListener('change', () => { state.exSel = null; $('ex-search').value = ''; explore(); });
$('ex-item').addEventListener('change', () => { state.exSel = $('ex-item').value; explore(); });
$('ex-search').addEventListener('input', () => {
  fillExItems();
  const v = $('ex-item').value;
  if (v && v !== state.exSel) { state.exSel = v; explore(); }
});
$('ex-filter').addEventListener('input', () => {
  const d = state.ex; if (!d) return;
  if (d.mode === 'grid') renderGrid(d); else if (d.mode === 'cls') renderClsTable(d.rows); else renderExCells();
});

/* ================= ② 부문분류 검색 ================= */
const runClassify = debounce(async () => {
  if (!state.aux) { $('cl-count').textContent = '자료를 하나 이상 불러오면 부문분류표가 함께 로드됩니다.'; return; }
  const q = $('cl-q').value;
  const d = await call('search', [q]);
  const extra = [];
  for (const k of LEVELS) if (state.loaded[k]) extra.push({ key: k + '_x', label: LEVEL_LABEL[k].replace(/\(.*\)/, '') + ' 산출(백만원)', num: true });
  $('cl-count').textContent = (q ? '「' + q + '」 검색 결과 ' : '전체 ') + d.rows.length + '개 기본부문'
    + (d.rows.length >= 400 ? ' (최대 400개 표시)' : '') + ' · 산출액은 해당 행이 속한 각 분류 부문의 2023년 총산출';
  makeTable($('cl-table'), clsCols(extra), d.rows);
}, 250);
$('cl-q').addEventListener('input', runClassify);

/* ================= ③ 경제·산업구조 ================= */
const ST_METRICS = [
  ['output', '총산출', '백만원', 0], ['output_share', '총산출 구성비', '%', 2], ['va', '부가가치', '백만원', 0],
  ['va_share', '부가가치 구성비', '%', 2], ['va_rate', '부가가치율', '%', 1], ['int_rate', '중간투입률', '%', 1],
  ['dom_rate', '국산화율', '%', 1], ['imp_dep', '수입의존도', '%', 1], ['export_rate', '수출률', '%', 1],
  ['import_rate', '수입률', '%', 1], ['int_dem_rate', '중간수요율', '%', 1], ['wage_share', '피용자보수 비중(부가가치 중)', '%', 1],
  ['exports', '수출액', '백만원', 0], ['imports', '수입액(수입계)', '백만원', 0],
];
$('st-metric').replaceChildren(...ST_METRICS.map(([k, l, u]) => el('option', { value: k, text: l + ' (' + u + ')' })));
async function getCached(name, fn, args) {
  const c = state.cache[state.active] || (state.cache[state.active] = {});
  const key = name + JSON.stringify(args);
  if (!c[key]) c[key] = await call(fn, args);
  return c[key];
}
async function renderStructure() {
  if (!needLevel()) { $('macro').replaceChildren(el('p', { class: 'muted', text: '자료를 먼저 불러오세요.' })); return; }
  const d = await getCached('structure', 'structure', [state.active]);
  $('macro').replaceChildren(...d.macro.map((m) => el('div', { class: 'card' },
    el('span', { class: 'k', text: m.name }), el('span', { class: 'v', text: fmt(m.value, 1) }), el('span', { class: 'u', text: m.unit }))));
  drawStructure(d);
  structureInsight(d);
}
function drawStructure(d) {
  d = d || (state.cache[state.active] || {})['structure' + JSON.stringify([state.active])];
  if (!d) return;
  const [key, label, unit, dd] = ST_METRICS.find((m) => m[0] === $('st-metric').value);
  const q = $('st-q').value.trim().toLowerCase();
  const rows = d.rows.filter((r) => !q || (r.code + ' ' + r.name).toLowerCase().includes(q));
  const top = Number($('st-top').value);
  const sorted = rows.filter((r) => r[key] != null).sort((a, b) => b[key] - a[key]).slice(0, top);
  renderBars($('st-bars'), sorted.map((r) => ({ label: r.code + ' ' + r.name, value: r[key] })), { unit, d: dd, outerLabel: label });
  makeTable($('st-table'), [
    { key: 'code', label: '코드' }, { key: 'name', label: '부문' },
    ...ST_METRICS.map(([k, l, u, n]) => ({ key: k, label: l + ' (' + u + ')', num: true, d: n })),
  ], rows, { sort: { key: 'output', dir: 'desc' } });
}
['st-metric', 'st-top'].forEach((id) => $(id).addEventListener('change', () => drawStructure()));
$('st-q').addEventListener('input', debounce(() => drawStructure(), 150));

/* ================= ④ 투입·배분구조 ================= */
const lkPicker = bindPicker('lk-q', 'lk-sector', () => renderLinkage());
async function renderLinkage() {
  if (!needLevel()) return;
  if (!$('lk-sector').value) lkPicker.fill(findSector(['반도체', '컴퓨터', '집적회로']));
  const code = $('lk-sector').value; if (!code) return;
  const d = await call('linkage', [state.active, code]);
  const s = d.summary;
  const cards = [
    ['총산출', s.output, '백만원', 0, korMoney(s.output)], ['부가가치율', s.va_rate, '%', 1], ['중간투입률', s.int_rate, '%', 1],
    ['국산화율', s.dom_rate, '%', 1], ['수입의존도', s.imp_dep, '%', 1], ['중간수요율', s.int_dem_rate, '%', 1],
    ['수입률(수입÷총공급)', s.import_rate, '%', 1], ['생산유발계수', s.prod_mult, '배', 3],
    ['영향력계수(후방)', s.influence, '평균=1', 3], ['감응도계수(전방)', s.sensitivity, '평균=1', 3],
  ];
  $('lk-cards').replaceChildren(...cards.map(([k, v, u, n, sub]) => el('div', { class: 'card' },
    el('span', { class: 'k', text: k }), el('span', { class: 'v', text: fmt(v, n) }), el('span', { class: 'u', text: u + (sub ? ' ' + sub : '') }))));
  makeTable($('lk-in'), [
    { key: 'code', label: '코드' }, { key: 'name', label: '투입 상품' },
    { key: 'total', label: '투입액 계', num: true }, { key: 'domestic', label: '국산', num: true }, { key: 'imported', label: '수입', num: true },
    { key: 'coef', label: '투입계수 A', num: true, d: 4 }, { key: 'dcoef', label: '국산 Aᵈ', num: true, d: 4 },
  ], d.inputs);
  makeTable($('lk-va'), [{ key: 'name', label: '부가가치 항목' }, { key: 'value', label: '금액(백만원)', num: true },
    { key: 'coef', label: '부가가치계수(÷총투입)', num: true, d: 4 }], d.va, { nosort: true });
  makeTable($('lk-out'), [
    { key: 'code', label: '코드' }, { key: 'name', label: '구입 부문' }, { key: 'total', label: '판매액 계', num: true },
    { key: 'domestic', label: '국산', num: true }, { key: 'imported', label: '수입', num: true }, { key: 'share', label: '총수요 대비 %', num: true, d: 2 },
  ], d.sales);
  makeTable($('lk-fd'), [{ key: 'name', label: '최종수요 항목' }, { key: 'total', label: '계(백만원)', num: true },
    { key: 'domestic', label: '국산', num: true }, { key: 'imported', label: '수입', num: true }, { key: 'share', label: '총수요 대비 %', num: true, d: 2 }], d.fd, { nosort: true });
  linkageInsight(d);
}

/* ================= ⑤ 유발계수·연관도 ================= */
async function renderMult() {
  if (!needLevel()) return;
  const d = await getCached('mult', 'multipliers', [state.active]);
  $('mu-emp-note').textContent = !d.employment ? '취업·고용유발계수: 통합대분류를 함께 불러오면 계산됩니다(통계표 16·17의 대분류 취업자 수 사용).'
    : d.employment_exact ? '취업·고용유발계수(명/10억원): 통계표의 2023년 대분류별 취업자·임금근로자 수로 계산한 정확한 값입니다.'
      : '취업·고용유발계수(명/10억원): 이 분류에는 부문별 취업자 자료가 없어, 소속 대분류의 취업계수를 같게 적용한 근사치입니다.';
  drawScatter(d.rows);
  multInsight(d);
  const quads = ['Ⅰ 전·후방 모두 높음', 'Ⅱ 전방연쇄형(감응도↑)', 'Ⅲ 독립형(모두 낮음)', 'Ⅳ 후방연쇄형(영향력↑)'];
  $('mu-quad').replaceChildren(...quads.map((q) => {
    const m = d.rows.filter((r) => r.quadrant === q && !r.zero).sort((a, b) => b.output - a.output);
    return el('div', null, el('b', { text: q + ' — ' + m.length + '개' }), m.slice(0, 5).map((r) => r.name).join(', ') + (m.length > 5 ? ' 등' : ''));
  }));
  drawMultTable(d);
}
function drawMultTable(d) {
  d = d || (state.cache[state.active] || {})['mult' + JSON.stringify([state.active])]; if (!d) return;
  const q = $('mu-q').value.trim().toLowerCase();
  const cols = [
    { key: 'code', label: '코드' }, { key: 'name', label: '부문' },
    { key: 'prod', label: '생산유발계수', num: true, d: 3 }, { key: 'va', label: '부가가치유발계수', num: true, d: 3 },
    { key: 'imp', label: '수입유발계수', num: true, d: 3 },
    { key: 'influence', label: '영향력계수', num: true, d: 3 }, { key: 'sensitivity', label: '감응도계수', num: true, d: 3 },
    { key: 'quadrant', label: '유형' },
  ];
  if (d.employment) cols.push({ key: 'emp_coef', label: '취업계수(명/10억원)', num: true, d: 2 },
    { key: 'emp', label: '취업유발계수(명/10억원)', num: true, d: 2 }, { key: 'wage', label: '고용유발계수(명/10억원)', num: true, d: 2 });
  cols.push({ key: 'output', label: '총산출(백만원)', num: true });
  makeTable($('mu-table'), cols, d.rows, { sort: { key: 'prod', dir: 'desc' },
    filter: (r) => !q || (r.code + ' ' + r.name).toLowerCase().includes(q),
    rowClass: (r) => (r.zero ? 'sub' : null) });
}
$('mu-q').addEventListener('input', debounce(() => drawMultTable(), 150));
function drawScatter(rows) {
  const data = rows.filter((r) => !r.zero);
  const W = 560, H = 420, m = { l: 48, r: 16, t: 16, b: 40 };
  const xs = data.map((r) => r.influence), ys = data.map((r) => r.sensitivity);
  const x0 = Math.min(0.5, ...xs) * 0.95, x1 = Math.max(1.5, ...xs) * 1.03;
  const y0 = Math.min(0.5, ...ys) * 0.95, y1 = Math.max(1.5, ...ys) * 1.03;
  const X = (v) => m.l + (v - x0) / (x1 - x0) * (W - m.l - m.r);
  const Y = (v) => H - m.b - (v - y0) / (y1 - y0) * (H - m.t - m.b);
  const maxO = Math.max(...data.map((r) => r.output));
  const NS = 'http://www.w3.org/2000/svg';
  const s = (tag, a) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(a || {})) e.setAttribute(k, v); return e; };
  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': '영향력계수와 감응도계수 산점도' });
  for (let i = 0; i <= 4; i++) {
    const vx = x0 + (x1 - x0) * i / 4, vy = y0 + (y1 - y0) * i / 4;
    svg.append(s('line', { class: 'axis', x1: X(vx), x2: X(vx), y1: m.t, y2: H - m.b }), s('line', { class: 'axis', x1: m.l, x2: W - m.r, y1: Y(vy), y2: Y(vy) }));
    const tx = s('text', { x: X(vx), y: H - m.b + 16, 'text-anchor': 'middle' }); tx.textContent = vx.toFixed(2); svg.append(tx);
    const ty = s('text', { x: m.l - 6, y: Y(vy) + 4, 'text-anchor': 'end' }); ty.textContent = vy.toFixed(2); svg.append(ty);
  }
  svg.append(s('line', { class: 'ref', x1: X(1), x2: X(1), y1: m.t, y2: H - m.b }), s('line', { class: 'ref', x1: m.l, x2: W - m.r, y1: Y(1), y2: Y(1) }));
  const lab = (t, x, y, a) => { const e = s('text', { class: 'qlabel', x, y, 'text-anchor': a }); e.textContent = t; svg.append(e); };
  lab('Ⅰ', W - m.r - 6, m.t + 14, 'end'); lab('Ⅱ', m.l + 6, m.t + 14, 'start'); lab('Ⅲ', m.l + 6, H - m.b - 8, 'start'); lab('Ⅳ', W - m.r - 6, H - m.b - 8, 'end');
  const xl = s('text', { x: (W + m.l) / 2, y: H - 6, 'text-anchor': 'middle' }); xl.textContent = '영향력계수(후방연쇄) →'; svg.append(xl);
  const yl = s('text', { x: 12, y: (H - m.b + m.t) / 2, 'text-anchor': 'middle', transform: `rotate(-90 12 ${(H - m.b + m.t) / 2})` }); yl.textContent = '감응도계수(전방연쇄) →'; svg.append(yl);
  const sel = $('mu-q').value.trim().toLowerCase();
  data.sort((a, b) => b.output - a.output).forEach((r) => {
    const hit = sel && (r.code + ' ' + r.name).toLowerCase().includes(sel);
    const c = s('circle', { class: 'dot' + (hit ? ' sel' : ''), cx: X(r.influence), cy: Y(r.sensitivity), r: 4 + 10 * Math.sqrt(r.output / maxO) });
    c.addEventListener('mousemove', (e) => showTip(e, '<b>' + esc(r.code + ' ' + r.name) + '</b><br>영향력 ' + fmt(r.influence, 3) + ' · 감응도 ' + fmt(r.sensitivity, 3)
      + '<br>생산유발계수 ' + fmt(r.prod, 3) + '<br>' + esc(r.quadrant)));
    c.addEventListener('mouseleave', hideTip);
    svg.append(c);
  });
  $('mu-scatter').replaceChildren(svg);
}
$('mu-q').addEventListener('input', debounce(() => { const d = (state.cache[state.active] || {})['mult' + JSON.stringify([state.active])]; if (d) drawScatter(d.rows); }, 200));

/* ================= ⑥ 최종수요 항목별 ================= */
$('fd-item').replaceChildren(...FD_ITEMS.map((n) => el('option', { value: n, text: n })));
async function renderFd() {
  if (!needLevel()) return;
  const item = $('fd-item').value;
  const d = await call('fd_effects', [state.active, item]);
  fdInsight(d);
  const cols = [
    { key: 'name', label: '최종수요 항목' },
    { key: 'fd_domestic', label: '국산 최종수요(백만원)', num: true }, { key: 'fd_total', label: '국산+수입(백만원)', num: true },
    { key: 'prod', label: '생산유발액', num: true }, { key: 'prod_coef', label: '생산유발계수', num: true, d: 3 }, { key: 'prod_dep', label: '생산유발의존도(%)', num: true, d: 1 },
    { key: 'va', label: '부가가치유발액', num: true }, { key: 'va_coef', label: '부가가치유발계수', num: true, d: 3 }, { key: 'va_dep', label: '부가가치유발의존도(%)', num: true, d: 1 },
    { key: 'imp', label: '수입유발액', num: true }, { key: 'imp_coef', label: '수입유발계수', num: true, d: 3 }, { key: 'imp_dep', label: '수입유발의존도(%)', num: true, d: 1 },
  ];
  if (d.employment) cols.push({ key: 'emp_coef', label: '취업유발계수(명/10억원)' + (d.employment_exact ? '' : '*'), num: true, d: 2 },
    { key: 'wage_coef', label: '고용유발계수(명/10억원)' + (d.employment_exact ? '' : '*'), num: true, d: 2 },
    { key: 'emp_dep', label: '취업유발비중(%)', num: true, d: 1 });
  makeTable($('fd-table'), cols, d.items, { nosort: true, rowClass: (r) => (r.name === '최종수요계' ? 'total' : r.sub ? 'sub' : null) });
  renderBars($('fd-bars'), d.sector.slice(0, 15).map((r) => ({ label: r.code + ' ' + r.name, value: r.prod, direct: r.fd })),
    { unit: '백만원', inner: 'direct', innerLabel: '해당 부문 국산 최종수요(직접)', outerLabel: '생산유발액(직접+간접)' });
  const scols = [{ key: 'code', label: '코드' }, { key: 'name', label: '부문' }, { key: 'fd', label: item + ' 국산(백만원)', num: true },
    { key: 'prod', label: '생산유발액', num: true }, { key: 'va', label: '부가가치유발액', num: true }, { key: 'imp', label: '수입유발액', num: true }];
  if (d.employment) scols.push({ key: 'emp', label: '취업유발(명)' + (d.employment_exact ? '' : '*'), num: true });
  makeTable($('fd-sector'), scols, d.sector, { sort: { key: 'prod', dir: 'desc' } });
}
$('fd-item').addEventListener('change', renderFd);

/* ================= ⑦ 수요충격 시뮬레이터 ================= */
bindPicker('sim-q', 'sim-sector', null);
function renderBasket() {
  const ul = $('sim-basket');
  ul.replaceChildren(...state.basket.map((s, i) => el('li', null,
    el('span', { text: s.code + ' ' + s.name + ' : ' + (s.amount > 0 ? '+' : '') + fmt(s.amount, 0) + ' 백만원 (' + korMoney(s.amount) + ')' }),
    el('button', { type: 'button', class: 'ghost', onclick: () => { state.basket.splice(i, 1); invalidateSim(); renderBasket(); } }, '삭제'))));
  setStatus('sim-status', state.basket.length ? state.basket.length + '개 입력 · 「파급효과 계산」을 누르세요. (분석 기준: ' + LEVEL_LABEL[state.active] + ')' : '시나리오를 추가하세요.');
}
function invalidateSim() { state.simResult = null; $('sim-result').hidden = true; }
$('sim-form').addEventListener('submit', (e) => {
  e.preventDefault();
  if (!needLevel('sim-status')) return;
  const code = $('sim-sector').value; const amount = Number($('sim-amount').value);
  const s = sectorsOf(state.active).find((x) => x.code === code);
  if (!s || !Number.isFinite(amount) || amount === 0) { setStatus('sim-status', '부문을 고르고 0이 아닌 금액을 입력하세요.'); return; }
  state.basket.push({ code, name: s.name, amount }); invalidateSim(); renderBasket();
});
$('sim-clear').addEventListener('click', () => { state.basket = []; invalidateSim(); renderBasket(); });
$('sim-example').addEventListener('click', () => {
  if (!needLevel('sim-status')) return;
  const code = { basic: '3102', small: '310', mid: '31', large: 'C09' }[state.active];
  const s = sectorsOf(state.active).find((x) => x.code === code);
  state.basket = [{ code, name: s.name, amount: -1000000 }];
  document.querySelector('input[name=sim-mode][value=domestic]').checked = true;
  invalidateSim(); renderBasket();
});
document.querySelectorAll('input[name=sim-mode]').forEach((r) => r.addEventListener('change', invalidateSim));
$('sim-run').addEventListener('click', async () => {
  if (!needLevel('sim-status')) return;
  if (!state.basket.length) { setStatus('sim-status', '시나리오를 먼저 추가하세요.'); return; }
  const mode = document.querySelector('input[name=sim-mode]:checked').value;
  const payload = JSON.stringify({ shocks: state.basket.map(({ code, amount }) => ({ code, amount })), mode });
  $('sim-run').disabled = true; setStatus('sim-status', '계산 중…');
  try {
    const r = await call('simulate', [state.active, payload]);
    state.simResult = r; drawSim(r);
    setStatus('sim-status', '계산 완료 · ' + r.label + ' 기준 · 검산(부가가치+수입 − 입력액) 오차 ' + fmt(r.check, 6) + ' 백만원');
  } catch (e) { invalidateSim(); setStatus('sim-status', '계산 실패: ' + e.message); } finally { $('sim-run').disabled = false; }
});
function drawSim(r) {
  $('sim-result').hidden = false;
  simInsight(r);
  const t = r.totals; const star = r.employment && !r.employment_exact ? '*' : '';
  const cards = [
    ['입력한 최종수요 변화', t.input, '백만원'],
    ...(r.mode === 'total' ? [['그중 국산품(파급 대상)', t.demand, '백만원'], ['수입 완제품(직접 수입)', t.directImports, '백만원']] : []),
    ['생산유발액(직접+간접)', t.production, '백만원'], ['직접효과', t.direct, '백만원'], ['간접효과', t.indirect, '백만원'],
    ['생산유발 배수', t.prod_multiplier, '배', 3],
    ['부가가치유발액', t.valueAdded, '백만원'], ...t.va_items.map((v) => ['  └ ' + v.name, v.value, '백만원']),
    ['수입유발액', t.imports, '백만원'],
  ];
  if (r.employment) cards.push(['취업유발' + star, t.emp, '명', 1], ['고용유발(임금근로자)' + star, t.wageEmp, '명', 1]);
  const KEY = ['생산유발액(직접+간접)', '부가가치유발액', '수입유발액', '취업유발' + star];
  $('sim-cards').replaceChildren(...cards.map(([k, v, u, n]) => el('div', { class: KEY.includes(k) ? 'card key' : 'card' }, el('span', { class: 'k', text: k }),
    el('span', { class: 'v', text: fmt(v, n ?? 0) }), el('span', { class: 'u', text: u + (u === '백만원' ? ' ' + korMoney(v) : '') }))));
  $('sim-note').textContent = (r.employment ? (r.employment_exact ? '취업·고용유발은 통계표의 대분류 취업자 수 기준 정확값.' : '* 취업·고용유발은 소속 대분류 취업계수를 적용한 근사치(통합대분류에서 계산하면 정확값).')
    : '취업·고용유발은 통합대분류를 함께 불러오면 계산됩니다.') + ' 부가가치유발액 + 수입유발액 = 입력액 (최종수요 1원은 국내 부가가치 또는 수입으로 모두 귀착).';
  renderBars($('sim-bars'), r.rows.slice(0, 15).map((x) => ({ label: x.code + ' ' + x.name, value: x.production, direct: x.demand })),
    { unit: '백만원', inner: 'direct', innerLabel: '직접효과(해당 부문 수요 변화)', outerLabel: '생산유발액(직접+간접)' });
  const cols = [{ key: 'code', label: '코드' }, { key: 'name', label: '부문' }, { key: 'demand', label: '국산 수요 변화', num: true },
    { key: 'production', label: '생산유발액', num: true }, { key: 'indirect', label: '간접효과', num: true },
    { key: 'valueAdded', label: '부가가치유발액', num: true }, { key: 'wage', label: '피용자보수 유발', num: true }, { key: 'imports', label: '수입유발액', num: true }];
  if (r.employment) cols.push({ key: 'emp', label: '취업유발(명)' + star, num: true, d: 1 }, { key: 'wageEmp', label: '고용유발(명)' + star, num: true, d: 1 });
  makeTable($('sim-table'), cols, r.rows, { sort: null });
}

/* ================= ⑧ 가격파급효과 ================= */
const prPicker = bindPicker('pr-q', 'pr-sector', null);
function syncPriceDefaults() {
  if (!needLevel('pr-status')) return;
  const mode = $('pr-mode').value;
  $('pr-item-wrap').hidden = mode !== 'va';
  $('pr-sector-wrap').hidden = mode === 'va'; $('pr-q-wrap').hidden = mode === 'va';
  if (mode === 'va') return;
  const want = mode === 'import' ? ['원유', '석탄, 원유', '광산품'] : ['화력', '전력', '전력, 가스'];
  if (!$('pr-q').value) prPicker.fill(findSector(want));
}
$('pr-mode').addEventListener('change', () => { $('pr-q').value = ''; prPicker.fill(); syncPriceDefaults(); });
$('pr-run').addEventListener('click', async () => {
  if (!needLevel('pr-status')) return;
  const mode = $('pr-mode').value; const rate = Number($('pr-rate').value);
  if (!Number.isFinite(rate)) { setStatus('pr-status', '상승률을 숫자로 입력하세요.'); return; }
  const payload = { mode, rate };
  if (mode === 'va') payload.item = $('pr-item').value; else payload.code = $('pr-sector').value;
  setStatus('pr-status', '계산 중…');
  try {
    const r = await call('price', [state.active, JSON.stringify(payload)]);
    $('pr-result').hidden = false;
    setStatus('pr-status', r.label + ' — ' + LEVEL_LABEL[state.active] + ' 기준 계산 완료');
    const ix = r.indices;
    $('pr-cards').replaceChildren(...[
      ['소비자물가 영향(가계소비 가중)', ix.consumer], ['생산자물가 영향(총산출 가중)', ix.producer], ['최종수요 가중 평균', ix.final],
    ].map(([k, v], i) => el('div', { class: i === 0 ? 'card key' : 'card' }, el('span', { class: 'k', text: k }), el('span', { class: 'v', text: fmt(v, 3) }), el('span', { class: 'u', text: '% 상승' }))));
    priceInsight(r);
    renderBars($('pr-bars'), r.rows.slice(0, 20).map((x) => ({ label: x.code + ' ' + x.name, value: x.dp })), { unit: '%', d: 3, outerLabel: '가격 상승률' });
    makeTable($('pr-table'), [{ key: 'code', label: '코드' }, { key: 'name', label: '부문' },
      { key: 'dp', label: '가격 상승률(%)', num: true, d: 4 }, { key: 'output', label: '총산출(백만원)', num: true }], r.rows);
  } catch (e) { setStatus('pr-status', '계산 실패: ' + e.message); }
});

/* ================= ⑨ 분류수준 비교 ================= */
async function clsList() {
  if (!state.clsRows && state.aux) state.clsRows = (await call('explore', ['cls', null, null, null])).rows;
  return state.clsRows || [];
}
const cpPicker = bindPicker('cp-q', 'cp-sector', null, { list: () => (state.clsRows || []).map((r) => ({ code: r.basic, name: r.basic_name })) });
document.querySelector('[data-tab=compare]').addEventListener('click', async () => {
  if (!state.aux) { setStatus('cp-status', '먼저 자료를 불러오세요.'); return; }
  await clsList(); if (!$('cp-sector').options.length) { cpPicker.fill('3102'); }
});
$('cp-run').addEventListener('click', async () => {
  if (!state.aux) { setStatus('cp-status', '먼저 자료를 불러오세요.'); return; }
  await clsList(); if (!$('cp-sector').value) cpPicker.fill('3102');
  const code = $('cp-sector').value; const amt = Number($('cp-amount').value);
  if (!Number.isFinite(amt) || amt === 0) { setStatus('cp-status', '0이 아닌 수요충격 금액을 입력하세요.'); return; }
  try {
    const d = await call('compare', [code, amt]);
    const b = d.basic;
    $('cp-path').replaceChildren(el('span', { text: '기본 ' + b.basic + ' ' + b.basic_name }), el('i', { text: '⊂' }),
      el('span', { text: '소 ' + b.small + ' ' + b.small_name }), el('i', { text: '⊂' }), el('span', { text: '중 ' + b.mid + ' ' + b.mid_name }),
      el('i', { text: '⊂' }), el('span', { text: '대 ' + b.large + ' ' + b.large_name }));
    const rows = d.levels.map((r) => ({ ...r, label: r.label + (r.loaded ? '' : ' (미로드)') }));
    const cols = [{ key: 'label', label: '분류' }, { key: 'code', label: '코드' }, { key: 'name', label: '해당 부문' },
      { key: 'output', label: '총산출(백만원)', num: true }, { key: 'va_rate', label: '부가가치율(%)', num: true, d: 1 },
      { key: 'imp_dep', label: '수입의존도(%)', num: true, d: 1 }, { key: 'prod', label: '생산유발계수', num: true, d: 3 },
      { key: 'va', label: '부가가치유발계수', num: true, d: 3 }, { key: 'imp', label: '수입유발계수', num: true, d: 3 },
      { key: 'influence', label: '영향력', num: true, d: 3 }, { key: 'sensitivity', label: '감응도', num: true, d: 3 },
      { key: 'sim_prod', label: '충격→생산유발(백만원)', num: true }, { key: 'sim_va', label: '→부가가치유발', num: true },
      { key: 'sim_imp', label: '→수입유발', num: true }];
    if (d.levels.some((r) => r.sim_emp != null)) cols.push({ key: 'sim_emp', label: '→취업유발(명)', num: true, d: 1 });
    makeTable($('cp-table'), cols, rows, { nosort: true });
    const base = d.levels.find((r) => r.loaded);
    const msgs = [];
    if (d.members.small) msgs.push('이 기본부문은 산출액 기준으로 소분류의 ' + fmt(d.members.small.share, 1) + '%, 중분류의 ' + fmt(d.members.mid.share, 1)
      + '%, 대분류의 ' + fmt(d.members.large.share, 1) + '%를 차지합니다(대분류 구성 기본부문 ' + d.members.large.count + '개).');
    const loaded = d.levels.filter((r) => r.loaded);
    if (loaded.length >= 2) {
      const lo = loaded[0], hi = loaded[loaded.length - 1];
      msgs.push('같은 ' + fmt(amt, 0) + '백만원 충격의 생산유발액은 ' + lo.label + ' ' + fmt(lo.sim_prod, 0) + ' → ' + hi.label + ' ' + fmt(hi.sim_prod, 0)
        + '백만원으로 ' + fmt((hi.sim_prod / lo.sim_prod - 1) * 100, 1) + '% 차이가 납니다. 차이는 상위 분류가 다른 투입구조를 가진 부문을 평균해서 생기는 집계 편의입니다.');
    } else if (base) msgs.push('두 개 이상의 분류를 불러오면 분류수준별 차이를 비교할 수 있습니다.');
    $('cp-note').textContent = msgs.join(' ');
    setStatus('cp-status', '비교 완료');
  } catch (e) { setStatus('cp-status', '계산 실패: ' + e.message); }
});

/* ================= ⑩ 검증 ================= */
function renderVerifyLevels() {
  const box = $('vf-levels');
  const ks = LEVELS.filter((k) => state.loaded[k]);
  if (!ks.length) { box.replaceChildren(el('p', { class: 'muted', text: '불러온 분류가 없습니다.' })); return; }
  box.replaceChildren(...ks.map((k) => {
    const c = state.loaded[k].check;
    const rows = [...Object.entries(c.identities).map(([n, v]) => ({ n, v, u: '백만원', ok: v < 0.5 })),
      ...Object.entries(c.coefficients).filter(([, v]) => v != null).map(([n, v]) => ({ n, v, u: n.includes('상대') ? '상대오차' : '계수 절대오차', ok: v < 1e-6 }))];
    const t = el('table');
    makeTable(t, [{ key: 'n', label: '검사 항목' }, { key: 'v', label: '최대 오차', num: true, fmt: (v) => (v === 0 ? '0' : v.toExponential(2)) },
      { key: 'u', label: '단위' }, { key: 'ok', label: '판정', fmt: (v) => (v ? '통과' : '확인 필요'), cls: (v) => (v ? 'ok' : 'bad') }], rows, { nosort: true });
    return el('details', { open: k === state.active }, el('summary', null, LEVEL_LABEL[k] + ' — ' + (c.passed ? '통과' : '확인 필요') + ' · 자료: ' + state.loaded[k].source
      + (state.loaded[k].zero_output.length ? ' · 산출액 0 부문: ' + state.loaded[k].zero_output.join(', ') : '')), el('div', { class: 'scroll' }, t));
  }));
}
$('vf-cons').addEventListener('click', async () => {
  const d = await call('consistency');
  if (!d.pairs.length) { $('vf-cons-table').replaceChildren(el('caption', { text: '두 개 이상의 분류를 불러오면 검사할 수 있습니다.' })); return; }
  const keys = Object.keys(d.pairs[0].diff);
  makeTable($('vf-cons-table'), [{ key: 'fine', label: '하위 분류' }, { key: 'coarse', label: '상위 분류' },
    ...keys.map((k) => ({ key: k, label: k + ' 최대차(백만원)', num: true })), { key: 'passed', label: '판정', fmt: (v) => (v ? '일치' : '불일치'), cls: (v) => (v ? 'ok' : 'bad') }],
  d.pairs.map((p) => ({ ...p, ...p.diff })), { nosort: true });
});
let pressData = null;
$('vf-press').addEventListener('click', async () => {
  if (!state.loaded.large) { setStatus('vf-press-summary', '통합대분류(33)를 먼저 불러오세요.'); return; }
  setStatus('vf-press-summary', '계산 중…');
  try { pressData = await call('press_check'); drawPress(); } catch (e) { setStatus('vf-press-summary', '실패: ' + e.message); }
});
$('vf-only-fail').addEventListener('change', drawPress);
function drawPress() {
  if (!pressData) return;
  const d = pressData; const only = $('vf-only-fail').checked;
  setStatus('vf-press-summary', '총 ' + d.total + '개 항목 중 ' + d.ok + '개 일치(공표 자릿수 기준) · 나머지 ' + (d.total - d.ok) + '개는 아래 「설명」 참조');
  makeTable($('vf-press-table'), [{ key: 'table', label: '대상' }, { key: 'label', label: '항목' }, { key: 'unit', label: '단위' },
    { key: 'official', label: '공표값', num: true, fmt: (v) => Number(v).toLocaleString('ko-KR', { maximumFractionDigits: 3 }) }, { key: 'computed', label: '앱 계산값', num: true, fmt: (v) => fmt(v, 4) },
    { key: 'status', label: '판정', cls: (v) => (v === '일치' ? 'ok' : v === '반올림 차이' ? 'warn' : 'bad') }, { key: 'note', label: '설명', cls: () => 'wrap' }],
  d.checks, { filter: (r) => !only || !r.ok });
}

/* ================= 핵심 요약 상자 ================= */
// cards: [{ k: '항목 이름', v: '핵심값', t: 설명(문자열 또는 [문자열|{b}] 배열) }]
function insight(id, title, cards, sub) {
  const box = $(id); if (!box) return;
  const part = (p) => (typeof p === 'string' ? p : el('b', { text: p.b }));
  const items = cards.filter(Boolean).map((c) => el('div', { class: 'ins-card' + (c.tone ? ' ' + c.tone : '') },
    el('span', { class: 'ins-k', text: c.k }),
    el('span', { class: 'ins-v', text: c.v }),
    c.t ? el('span', { class: 'ins-t' }, ...[].concat(c.t).filter((x) => x !== '' && x != null).map(part)) : null));
  box.replaceChildren(el('div', { class: 'insight-head' }, el('span', { class: 'insight-title', text: title }), sub ? el('span', { class: 'insight-sub', text: sub }) : null),
    el('div', { class: 'ins-grid' }, items));
  box.hidden = false;
}
const jo = (v) => fmt(v / 1e6, 1) + '조원';
const pc = (v, d = 1) => fmt(v, d) + '%';
const MIN_SHARE = 0.1; // 극값은 산출 비중 0.1% 이상 부문 중에서 고름(아주 작은 부문의 이상값 배제)
const big = (rows) => rows.filter((r) => (r.output_share ?? 100) >= MIN_SHARE && r.output > 0);
const topBy = (rows, k, n = 1, asc = false) => rows.filter((r) => r[k] != null).sort((a, b) => (asc ? a[k] - b[k] : b[k] - a[k])).slice(0, n);
const nm = (r) => r.name;
// 받침에 맞는 조사(이/가 등)
function josa(word, withBatchim, without) {
  const c = String(word).trim().slice(-1).charCodeAt(0);
  if (c >= 0xac00 && c <= 0xd7a3) return word + ((c - 0xac00) % 28 ? withBatchim : without);
  return word + withBatchim + '(' + without + ')';
}
function bigM(rows) {
  const live = rows.filter((r) => !r.zero && r.output > 0);
  const tot = live.reduce((a, r) => a + r.output, 0);
  return live.filter((r) => r.output / tot * 100 >= MIN_SHARE);
}
const QUADS = ['Ⅰ 전·후방 모두 높음', 'Ⅱ 전방연쇄형(감응도↑)', 'Ⅲ 독립형(모두 낮음)', 'Ⅳ 후방연쇄형(영향력↑)'];
const K = (v) => korMoney(Math.abs(v)).replace('≈ ', '');

async function renderLevelSummary() {
  const key = state.active; if (!key) return;
  try {
    const [st, mu, fd] = await Promise.all([getCached('structure', 'structure', [key]), getCached('mult', 'multipliers', [key]),
      getCached('fd', 'fd_effects', [key, '최종수요계'])]);
    if (key !== state.active) return;
    const m = Object.fromEntries(st.macro.map((x) => [x.name, x.value]));
    const rows = st.rows;
    const byOut = topBy(rows, 'output', 3);
    const share3 = byOut.reduce((a, r) => a + r.output_share, 0);
    const mrows = mu.rows.filter((r) => !r.zero);
    const meanProd = mrows.reduce((a, r) => a + r.prod, 0) / mrows.length;
    const pMax = topBy(bigM(mrows), 'prod')[0];
    const q1 = mrows.filter((r) => r.quadrant === QUADS[0]).sort((a, b) => b.output - a.output);
    const impMax = topBy(big(rows), 'imp_dep')[0]; const expMax = topBy(big(rows), 'export_rate')[0];
    const items = fd.items.filter((i) => ['소비', '투자', '수출'].includes(i.name));
    const byProd = items.slice().sort((a, b) => b.prod_coef - a.prod_coef);
    const cards = [
      { k: '경제 규모', v: '총산출 ' + fmt(m['총산출'], 1) + '조원', t: [rows.length + '개 부문 · 부가가치 ', { b: fmt(m['부가가치'], 1) + '조원' }, ' · 부가가치율 ' + pc(m['부가가치율'])] },
      { k: '산출 1위 산업', v: byOut[0].name, t: ['전체 산출의 ', { b: pc(byOut[0].output_share) }, ' · 상위 3개(' + byOut.slice(1).map(nm).join(', ') + ' 포함) ', { b: pc(share3) }] },
      { k: '생산유발계수 1위', v: pMax.name + ' ' + fmt(pMax.prod, 3) + '배', t: ['최종수요 1원당 생산유발 · 부문 평균 ', { b: fmt(meanProd, 3) + '배' }] },
      { k: '핵심 연관산업 (Ⅰ유형)', v: q1.length + '개 부문', t: ['전·후방 연쇄가 모두 큼 · ', { b: q1.slice(0, 3).map(nm).join(', ') }, q1.length > 3 ? ' 등' : ''] },
      { k: '수입의존도 1위', v: impMax.name + ' ' + pc(impMax.imp_dep), t: ['수입 중간재 ÷ 총투입 · 전산업 ', { b: pc(m['수입의존도(수입 중간투입률)']) }] },
      { k: '수출률 1위', v: expMax.name + ' ' + pc(expMax.export_rate), t: ['수출액 ÷ 총산출 · 전산업 ', { b: pc(m['수출률']) }] },
      { k: '최종수요별 생산유발', v: byProd[0].name + ' ' + fmt(byProd[0].prod_coef, 3), t: ['생산유발계수 ', { b: byProd.map((i) => i.name + ' ' + fmt(i.prod_coef, 3)).join(' > ') }] },
    ];
    if (fd.employment) {
      const byEmp = items.slice().sort((a, b) => b.emp_coef - a.emp_coef);
      const eMax = topBy(bigM(mrows), 'emp')[0];
      cards.push({ k: '일자리 창출', v: byEmp[0].name + ' ' + fmt(byEmp[0].emp_coef, 1) + '명', t: ['10억원당 취업유발 ', { b: byEmp.map((i) => i.name + ' ' + fmt(i.emp_coef, 1)).join(' > ') },
        ' · 부문 1위 ' + eMax.name + ' ' + fmt(eMax.emp, 1) + '명' + (mu.employment_exact ? '' : '(근사치)')] });
    }
    if (!fd.employment) {
      const vaMax = topBy(big(rows), 'va_rate')[0];
      cards.push({ k: '부가가치율 1위', v: vaMax.name + ' ' + pc(vaMax.va_rate), t: ['부가가치 ÷ 총투입 · 전산업 ', { b: pc(m['부가가치율']) }] });
    }
    insight('lv-insight', LEVEL_LABEL[key] + ' 핵심 요약', cards, '2023년 · 극값은 산출 비중 ' + MIN_SHARE + '% 이상 부문 중');
  } catch (e) { /* 요약 실패는 분석에 영향 없음 */ }
}

function structureInsight(d) {
  const b = big(d.rows);
  const vaMax = topBy(b, 'va_rate')[0], vaMin = topBy(b, 'va_rate', 1, true)[0];
  const intMax = topBy(b, 'int_rate')[0], domMin = topBy(b.filter((r) => r.int_in > 0), 'dom_rate', 1, true)[0];
  const exp3 = topBy(b, 'export_rate', 3);
  insight('st-insight', '핵심 요약', [
    { k: '부가가치율 1위', v: vaMax.name + ' ' + pc(vaMax.va_rate), t: ['최저는 ', { b: vaMin.name + ' ' + pc(vaMin.va_rate) }] },
    { k: '중간투입률 1위', v: intMax.name + ' ' + pc(intMax.int_rate), t: '생산액 대부분이 원재료·서비스 구입비' },
    { k: '국산화율 최저', v: domMin.name + ' ' + pc(domMin.dom_rate), t: '중간재를 수입에 가장 많이 의존' },
    { k: '수출률 1위', v: exp3[0].name + ' ' + pc(exp3[0].export_rate), t: ['2·3위 ', { b: exp3.slice(1).map((r) => r.name + ' ' + pc(r.export_rate)).join(', ') }] },
  ], LEVEL_LABEL[state.active] + ' · 산출 비중 ' + MIN_SHARE + '% 이상 부문 중');
}

async function linkageInsight(d) {
  const s = d.summary;
  const mu = await getCached('mult', 'multipliers', [state.active]);
  const live = mu.rows.filter((r) => !r.zero).sort((a, b) => b.prod - a.prod);
  const rank = live.findIndex((r) => r.code === d.code) + 1;
  const inp = d.inputs.find((r) => r.code !== d.code) || d.inputs[0];
  const self = d.inputs.find((r) => r.code === d.code);
  const buyer = d.sales.find((r) => r.code !== d.code) || d.sales[0];
  const fdTop = d.fd.slice().sort((a, b) => b.total - a.total)[0];
  const quad = (mu.rows.find((r) => r.code === d.code) || {}).quadrant;
  insight('lk-insight', d.name + ' 핵심 요약', [
    { k: '투입 구조', v: '중간투입 ' + pc(s.int_rate), t: ['부가가치 ', { b: pc(s.va_rate) }, ' · 중간재 국산화율 ' + pc(s.dom_rate) + ' · 총산출 ' + jo(s.output)] },
    inp ? { k: '최대 투입 상품', v: inp.name, t: ['투입계수 ', { b: fmt(inp.coef, 3) }, self && self.total > inp.total ? ' · 자기 부문 제품(' + fmt(self.coef, 3) + ') 다음' : ''] } : null,
    { k: '최대 판매처', v: buyer ? buyer.name : '—', t: ['생산물의 ', { b: pc(s.int_dem_rate) }, '가 중간재 · 최종수요는 ' + josa(fdTop.name, '이', '가') + ' 최대'] },
    { k: '생산유발계수', v: fmt(s.prod_mult, 3) + '배', t: [live.length + '개 부문 중 ', { b: rank + '위' }, quad ? ' · ' + quad : ''] },
  ], LEVEL_LABEL[state.active]);
}

function multInsight(d) {
  const r = d.rows.filter((x) => !x.zero);
  const rb = bigM(d.rows);
  const p3 = topBy(rb, 'prod', 3), vaMax = topBy(rb, 'va')[0], impMax = topBy(rb, 'imp')[0];
  const cnt = QUADS.map((q) => [q.split(' ')[0], r.filter((x) => x.quadrant === q).length]);
  const cards = [
    { k: '생산유발계수 1위', v: p3[0].name + ' ' + fmt(p3[0].prod, 3), t: ['2·3위 ', { b: p3.slice(1).map((x) => x.name + ' ' + fmt(x.prod, 3)).join(', ') }] },
    { k: '부가가치유발계수 1위', v: vaMax.name + ' ' + fmt(vaMax.va, 3), t: '수요 1원 중 국내에 남는 부가가치가 가장 큼' },
    { k: '수입유발계수 1위', v: impMax.name + ' ' + fmt(impMax.imp, 3), t: '수요의 국외 유출(수입)이 가장 큼' },
    { k: '산업 유형', v: 'Ⅰ유형 ' + cnt[0][1] + '개', t: ['전·후방 모두 큰 핵심산업 · ', { b: cnt.slice(1).map(([q, n]) => q + ' ' + n + '개').join(' · ') }] },
  ];
  if (d.employment) {
    const e = rb.filter((x) => x.emp > 0);
    const eMax = topBy(e, 'emp')[0], eMin = topBy(e, 'emp', 1, true)[0];
    cards.push({ k: '취업유발계수 1위', v: eMax.name + ' ' + fmt(eMax.emp, 1) + '명', t: ['10억원당 · 최저 ', { b: eMin.name + ' ' + fmt(eMin.emp, 1) + '명' }, d.employment_exact ? '' : ' · 근사치'] });
  }
  insight('mu-insight', '핵심 요약', cards, LEVEL_LABEL[state.active] + ' · 계수 극값은 산출 비중 ' + MIN_SHARE + '% 이상 부문 중');
}

function fdInsight(d) {
  const it = d.items.filter((i) => ['소비', '투자', '수출'].includes(i.name));
  const by = (k) => it.slice().sort((a, b) => b[k] - a[k]);
  const order = (k, dd) => by(k).map((i) => i.name + ' ' + fmt(i[k], dd)).join(' > ');
  const cards = [
    { k: '생산유발계수 1위', v: by('prod_coef')[0].name + ' ' + fmt(by('prod_coef')[0].prod_coef, 3), t: [{ b: order('prod_coef', 3) }] },
    { k: '부가가치유발계수 1위', v: by('va_coef')[0].name + ' ' + fmt(by('va_coef')[0].va_coef, 3), t: [{ b: order('va_coef', 3) }] },
    { k: '수입유발계수 1위', v: by('imp_coef')[0].name + ' ' + fmt(by('imp_coef')[0].imp_coef, 3), t: [{ b: order('imp_coef', 3) }] },
    { k: '생산유발 기여 1위', v: by('prod_dep')[0].name + ' ' + pc(by('prod_dep')[0].prod_dep), t: ['전체 생산유발액 중 비중 · ', { b: it.map((i) => i.name + ' ' + pc(i.prod_dep)).join(' · ') }] },
  ];
  if (d.employment) cards.push({ k: '일자리 창출 1위', v: by('emp_coef')[0].name + ' ' + fmt(by('emp_coef')[0].emp_coef, 1) + '명', t: ['10억원당 · ', { b: order('emp_coef', 1) }, d.employment_exact ? '' : ' · 근사치'] });
  insight('fd-insight', '핵심 요약', cards, LEVEL_LABEL[state.active] + ' · 국산 최종수요 기준');
}

function simInsight(r) {
  const t = r.totals;
  const ind = r.rows.filter((x) => !x.demand).sort((a, b) => Math.abs(b.indirect) - Math.abs(a.indirect)).slice(0, 3);
  const dir = t.input < 0 ? '감소' : '증가'; const tone = t.input < 0 ? 'down' : 'up';
  const cards = [
    { k: '생산 유발', v: K(t.production) + ' ' + dir, tone, t: ['입력 ' + K(t.input) + ' × 배수 ', { b: fmt(t.prod_multiplier, 3) }, ' · 간접효과 ' + K(t.indirect)] },
    { k: '부가가치 유발', v: K(t.valueAdded) + ' ' + dir, tone, t: ['입력액의 ', { b: pc(t.valueAdded / t.input * 100) }, '가 국내 소득으로'] },
    { k: '수입 유발', v: K(t.imports) + ' ' + dir, tone, t: ['입력액의 ', { b: pc(t.imports / t.input * 100) }, ' · 부가가치 + 수입 = 입력액'] },
    ind.length ? { k: '간접효과가 큰 부문', v: ind[0].name, t: ['다음으로 ', { b: ind.slice(1).map(nm).join(', ') }] } : null,
  ];
  if (r.employment) cards.push({ k: '일자리', v: fmt(Math.abs(t.emp), 0) + '명 ' + dir, tone, t: ['임금근로자 ', { b: fmt(Math.abs(t.wageEmp), 0) + '명' }, r.employment_exact ? '' : ' · 근사치'] });
  insight('sim-insight', '결과 요약', cards, r.label + ' 기준');
}

function priceInsight(r) {
  const t3 = r.rows.filter((x) => Math.abs(x.dp) > 0).slice(0, 3);
  insight('pr-insight', '결과 요약', [
    { k: '소비자물가 영향', v: '+' + fmt(r.indices.consumer, 3) + '%', tone: 'down', t: ['가계소비 구성비 가중 · ', { b: r.label }] },
    { k: '생산자물가 영향', v: '+' + fmt(r.indices.producer, 3) + '%', tone: 'down', t: '총산출 가중 평균' },
    { k: '가장 크게 오르는 부문', v: t3[0].name + ' +' + fmt(t3[0].dp, 2) + '%', t: ['다음으로 ', { b: t3.slice(1).map((x) => x.name + ' +' + fmt(x.dp, 2) + '%').join(', ') }] },
  ], LEVEL_LABEL[state.active] + ' 기준 · 비용 100% 전가·수요 불변 가정의 최대치');
}

/* ---------------- 시작 ---------------- */
renderBasket();
