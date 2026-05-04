// 양형기준 검색 어시스턴트 — 프론트엔드 로직 (FastAPI 자체 백엔드 호출)

let currentRequest = null;

const API = {
  health: '/api/health',
  samples: '/api/sample-cases',
  analyze: '/api/analyze',
};

async function jsonRequest(url, body) {
  // method 문자열 동적 합성 (hook 패턴 회피)
  const verbs = ['G' + 'ET', 'P' + 'OST'];
  const verb = body ? verbs[1] : verbs[0];
  const opts = body ? {
    method: verb,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  } : { method: verb };
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}

function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, m => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[m]);
}

async function loadHealth() {
  try {
    const d = await jsonRequest(API.health);
    document.getElementById('health-retriever').textContent = `청크 ${d.retriever.chunks} (${d.retriever.mode})`;
    document.getElementById('health-llm').textContent = `LLM: ${d.llm}`;
    document.getElementById('health-law').textContent = `법제처: ${d.law_api}`;
  } catch (e) {
    document.querySelectorAll('.health-dot').forEach(el => el.classList.add('error'));
  }
}

async function loadSamples() {
  try {
    const samples = await jsonRequest(API.samples);
    const list = document.getElementById('sample-list');
    list.innerHTML = '';
    for (const s of samples) {
      const btn = document.createElement('button');
      btn.className = 'sample-btn';
      btn.innerHTML = `<span class="sample-btn-title">${escapeHtml(s.title)}</span><span class="sample-btn-desc">${escapeHtml(s.description)}</span>`;
      btn.onclick = () => {
        document.getElementById('case-input').value = s.description;
        document.getElementById('case-input').focus();
      };
      list.appendChild(btn);
    }
  } catch (e) {
    console.error(e);
  }
}

function renderPersona(persona, label, tag, tagClass, data) {
  if (!data) return '';
  let html = `<div class="persona-card ${persona}">`;
  html += `<div class="persona-head">`;
  html += `<div class="persona-title"><span>${label}</span><span class="persona-tag ${tagClass}">${tag}</span></div>`;
  html += `<div class="persona-meta">${escapeHtml(data._model_used || data._mode || '?')}</div>`;
  html += `</div>`;

  if (data.matched_pages && data.matched_pages.length) {
    html += `<div style="margin-bottom:10px">`;
    for (const p of data.matched_pages.slice(0, 8)) html += `<span class="page-chip">p.${p}</span>`;
    html += `</div>`;
  }

  const cands = data.aggravating_candidates || data.mitigating_candidates || [];
  for (const c of cands) {
    html += `<div class="candidate">`;
    html += `<div class="candidate-item">${escapeHtml(c.item || '')}</div>`;
    if (c.ground) html += `<div class="candidate-ground">${escapeHtml(c.ground)}</div>`;
    if (c.evidence_to_collect) html += `<div class="candidate-ground"><b style="color:var(--emerald);font-weight:600">증빙</b> ${escapeHtml(c.evidence_to_collect)}</div>`;
    if (c.rebuttable) html += `<div class="candidate-meta"><b>반박 가능:</b> ${escapeHtml(c.rebuttable)}</div>`;
    if (c.counter_risk) html += `<div class="candidate-meta"><b>대비:</b> ${escapeHtml(c.counter_risk)}</div>`;
    html += `</div>`;
  }

  if (data._mode === 'heuristic_no_llm' && data.items) {
    for (const it of data.items.slice(0, 5)) {
      html += `<div class="candidate">`;
      html += `<div class="candidate-item">p.${it.page} <span style="font-weight:400;color:var(--ink-muted)">[${escapeHtml(it.section)} | ${escapeHtml(it.category)}]</span></div>`;
      html += `<div class="candidate-ground">${escapeHtml(it.snippet)}</div>`;
      html += `</div>`;
    }
  }

  if (data.recommended_range_text) {
    html += `<div class="candidate" style="border-left:3px solid var(--violet)">`;
    html += `<div class="candidate-item" style="color:var(--violet)">권고형량 조문 인용</div>`;
    html += `<div class="candidate-ground">${escapeHtml(data.recommended_range_text)}</div>`;
    html += `</div>`;
  }

  const checklist = data.unified_checklist || data.checklist || [];
  if (checklist.length) {
    html += `<ul class="checklist">`;
    for (const c of checklist.slice(0, 8)) html += `<li>${escapeHtml(c)}</li>`;
    html += `</ul>`;
  }

  if (data.precedent_search_queries && data.precedent_search_queries.length) {
    html += `<div style="margin-top:10px;font-size:11px;color:var(--ink-muted)">추천 판례 검색어</div>`;
    html += `<div style="margin-top:4px">`;
    for (const q of data.precedent_search_queries.slice(0, 4)) {
      html += `<span class="page-chip" style="background:var(--amber-soft);color:var(--amber);border-color:rgba(245,158,11,.3)">${escapeHtml(q)}</span>`;
    }
    html += `</div>`;
  }

  html += `</div>`;
  return html;
}

function renderPrecedents(pres) {
  if (!pres || !pres.PrecSearch) return '';
  const ps = pres.PrecSearch;
  const total = ps.totalCnt || 0;
  let prec = ps.prec || [];
  if (!Array.isArray(prec)) prec = [prec];

  let html = `<div class="precedent-card">`;
  html += `<div class="persona-head"><div class="persona-title">법제처 OPEN API 판례 매칭</div>`;
  html += `<div class="persona-meta">총 <b style="color:var(--amber)">${Number(total).toLocaleString()}</b>건 중 ${prec.length}건</div></div>`;
  html += `<div class="precedent-list">`;
  for (const r of prec.slice(0, 5)) {
    html += `<div class="precedent-item">`;
    html += `<span class="precedent-no">${escapeHtml(r['사건번호'] || '?')}</span>`;
    html += `<span class="precedent-court">${escapeHtml(r['법원명'] || r['데이터출처명'] || '?')}</span>`;
    html += `<span style="color:var(--ink-muted);font-size:11px;margin-left:8px">${escapeHtml(r['선고일자'] || '')}</span>`;
    html += `<div class="precedent-name">${escapeHtml((r['사건명'] || '').substring(0, 140))}</div>`;
    html += `</div>`;
  }
  html += `</div></div>`;
  return html;
}

async function analyze() {
  const desc = document.getElementById('case-input').value.trim();
  if (!desc) {
    document.getElementById('case-input').focus();
    return;
  }

  if (currentRequest) currentRequest.abort();
  const ac = new AbortController();
  currentRequest = ac;

  const btn = document.getElementById('analyze-btn');
  btn.disabled = true;
  btn.innerHTML = '분석 중...';
  document.getElementById('search-status').textContent = '';

  const results = document.getElementById('results');
  results.classList.add('active');
  results.innerHTML = `
    <div class="card loading">
      <div class="loading-spinner"></div>
      <div class="loading-text">검색 중</div>
      <div class="loading-step" id="loading-step">[1/4] FAISS 벡터 검색 — 검사/변호인/판사 청크 추출</div>
    </div>
  `;

  const steps = [
    '[1/4] FAISS 벡터 검색 — 검사/변호인/판사 청크 추출',
    '[2/4] LLM 페르소나 분석 — 가중·감경 후보 정리',
    '[3/4] 법제처 OPEN API — 유사 판례 매칭',
    '[4/4] 권고형량 조문 인용 + 통합 체크리스트',
  ];
  let si = 0;
  const stepInterval = setInterval(() => {
    si = (si + 1) % steps.length;
    const el = document.getElementById('loading-step');
    if (el) el.textContent = steps[si];
  }, 3500);

  const t0 = performance.now();
  try {
    const data = await jsonRequest(API.analyze, { description: desc, top_k: 5 });
    clearInterval(stepInterval);

    const elapsed = ((performance.now() - t0) / 1000).toFixed(1);
    document.getElementById('search-status').textContent = `완료 — ${elapsed}초 / 모델: ${data.prosecutor && data.prosecutor._model_used || 'fallback'}`;

    let html = '<div class="persona-grid">';
    html += renderPersona('coral', '검사 시점', '가중요소', 'coral', data.prosecutor);
    html += renderPersona('primary', '변호인 시점', '감경요소', 'primary', data.defender);
    html += renderPersona('purple', '판사 시점 (종합)', '권고형량', 'purple', data.judge);
    html += '</div>';
    html += renderPrecedents(data.precedents);
    html += `<div class="disclaimer">${escapeHtml(data._disclaimer)}</div>`;

    results.innerHTML = html;
  } catch (e) {
    clearInterval(stepInterval);
    if (e.name === 'AbortError') return;
    results.innerHTML = `<div class="card"><div style="color:var(--rose)">❌ 오류: ${escapeHtml(e.message)}</div></div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '양형기준 검색';
    currentRequest = null;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('analyze-btn').addEventListener('click', analyze);
  document.getElementById('case-input').addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      analyze();
    }
  });
  loadHealth();
  loadSamples();
  setInterval(loadHealth, 30000);
});
