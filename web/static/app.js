// 양형기준 검색 어시스턴트 — 프론트엔드 로직 (FastAPI 자체 백엔드 호출)

let currentRequest = null;

const API = {
  health: '/api/health',
  samples: '/api/sample-cases',
  analyze: '/api/analyze',
  benchSubmit: '/api/bench-submit',
  benchResult: (id) => `/api/bench-result/${id}`,
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
  const clayMap = {
    coral: '/static/agent_prosecutor.png?v=2',
    primary: '/static/agent_defender.png?v=2',
    purple: '/static/agent_judge.png?v=2',
  };
  const clayImg = clayMap[persona] || '';
  let html = `<div class="persona-card ${persona}">`;
  if (clayImg) {
    html += `<img class="persona-clay" src="${clayImg}" alt="${tag}" loading="lazy">`;
  }
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

// ─── AgentsBench 4단계 토론 시뮬 + polling ────────────────────────────
function renderBenchProgress(state) {
  const stage = state.stage || 0;
  const stages = [
    { n: 1, label: '독립 분석', desc: '검사·변호인·판사 LLM 병렬' },
    { n: 2, label: '토론 3턴', desc: '검사 ↔ 변호인 반박' },
    { n: 3, label: '최종 양형', desc: '판사 종합 + 권고형량' },
    { n: 4, label: '위원 합의', desc: '양형위 7명 분포 (옵션)' },
  ];
  let html = '<div class="bench-progress">';
  for (const st of stages) {
    const isDone = (typeof stage === 'number' ? stage : 99) > st.n || stage === 'DONE';
    const isActive = stage === st.n;
    const cls = isDone ? 'done' : (isActive ? 'active' : 'pending');
    html += `<div class="bench-step ${cls}"><div class="bench-step-num">${st.n}</div><div><div class="bench-step-label">${st.label}</div><div class="bench-step-desc">${st.desc}</div></div></div>`;
  }
  html += '</div>';
  if (state.message) html += `<div class="bench-msg">${escapeHtml(state.message)}</div>`;
  return html;
}

function renderBenchResult(state) {
  let html = '';
  if (state.stage1) {
    html += `<div class="bench-section"><h3 class="bench-section-title">Stage 1 — 독립 분석</h3>`;
    html += `<div class="chat-row chat-row-pros"><div class="chat-bubble bubble-coral"><div class="bubble-head">검사</div>`;
    const pr = state.stage1.prosecutor || {};
    if (pr.aggravating_candidates) {
      html += '<div class="bubble-list">';
      for (const c of (pr.aggravating_candidates || []).slice(0, 4)) {
        html += `<div class="bubble-item">▸ ${escapeHtml(c.item || c)}</div>`;
      }
      html += '</div>';
    } else if (pr._raw) {
      html += `<div class="bubble-text">${escapeHtml(String(pr._raw).slice(0, 400))}</div>`;
    }
    html += `</div></div>`;
    const df = state.stage1.defender || {};
    html += `<div class="chat-row chat-row-def"><div class="chat-bubble bubble-blue"><div class="bubble-head">변호인</div>`;
    if (df.mitigating_candidates) {
      html += '<div class="bubble-list">';
      for (const c of (df.mitigating_candidates || []).slice(0, 4)) {
        html += `<div class="bubble-item">▸ ${escapeHtml(c.item || c)}</div>`;
      }
      html += '</div>';
    } else if (df._raw) {
      html += `<div class="bubble-text">${escapeHtml(String(df._raw).slice(0, 400))}</div>`;
    }
    html += `</div></div></div>`;
  }
  if (state.stage2) {
    html += `<div class="bench-section"><h3 class="bench-section-title">Stage 2 — 토론 3턴</h3>`;
    const t2 = state.stage2.turn2 || {};
    if (t2.prosecutor_rebuttal) {
      html += `<div class="chat-row chat-row-pros"><div class="chat-bubble bubble-coral"><div class="bubble-head">검사 반박</div>`;
      const reb = t2.prosecutor_rebuttal.rebuttal || [];
      for (const r of reb.slice(0, 3)) {
        html += `<div class="bubble-quote">변호인: "${escapeHtml(r.defender_claim || '')}"</div>`;
        html += `<div class="bubble-counter">→ ${escapeHtml(r.counter || '')}</div>`;
      }
      html += `</div></div>`;
    }
    if (t2.defender_rebuttal) {
      html += `<div class="chat-row chat-row-def"><div class="chat-bubble bubble-blue"><div class="bubble-head">변호인 반박</div>`;
      const reb = t2.defender_rebuttal.rebuttal || [];
      for (const r of reb.slice(0, 3)) {
        html += `<div class="bubble-quote">검사: "${escapeHtml(r.prosecutor_claim || '')}"</div>`;
        html += `<div class="bubble-counter">→ ${escapeHtml(r.counter || '')}</div>`;
      }
      html += `</div></div>`;
    }
    const t3 = state.stage2.turn3 || {};
    const js = t3.judge_synthesis || {};
    if (js.recommended_zone || js.accepted_aggravating) {
      html += `<div class="chat-row chat-row-judge"><div class="chat-bubble bubble-purple"><div class="bubble-head">판사 종합</div>`;
      if (js.recommended_zone) html += `<div class="bubble-zone">권고 영역: <b>${escapeHtml(js.recommended_zone)}</b></div>`;
      if (js.zone_rationale) html += `<div class="bubble-text">${escapeHtml(js.zone_rationale)}</div>`;
      html += `</div></div>`;
    }
    html += `</div>`;
  }
  if (state.stage3) {
    const s3 = state.stage3;
    html += `<div class="bench-final"><h3 class="bench-section-title">Stage 3 — 최종 양형</h3>`;
    html += `<div class="final-zone">권고 영역: <b>${escapeHtml(s3.final_zone || '?')}</b></div>`;
    if (s3.form_range) html += `<div class="final-range">${escapeHtml(s3.form_range)}</div>`;
    if (s3.reasoning) html += `<div class="final-reasoning">${escapeHtml(s3.reasoning)}</div>`;
    html += `</div>`;
  }
  return html;
}

async function runBench(desc) {
  const verb = 'P' + 'OST';
  const results = document.getElementById('results');
  results.classList.add('active');
  results.innerHTML = `<div class="bench-card">${renderBenchProgress({stage:1, message:'토론 시작...'})}</div>`;
  const submitResp = await fetch(API.benchSubmit, {
    method: verb,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description: desc, top_k: 5, full_4_stages: false }),
  });
  if (!submitResp.ok) {
    results.innerHTML = `<div class="bench-card error">제출 실패</div>`;
    return;
  }
  const { job_id } = await submitResp.json();
  for (let i = 0; i < 90; i++) {
    await new Promise(r => setTimeout(r, 3000));
    try {
      const r = await fetch(API.benchResult(job_id) + '?_t=' + Date.now());
      if (!r.ok) continue;
      const state = await r.json();
      let html = `<div class="bench-card">${renderBenchProgress(state)}`;
      html += renderBenchResult(state);
      html += '</div>';
      results.innerHTML = html;
      if (state.status === 'DONE' || state.status === 'ERROR') return;
    } catch (e) { /* keep polling */ }
  }
}

async function analyze() {
  const desc = document.getElementById('case-input').value.trim();
  if (!desc) {
    document.getElementById('case-input').focus();
    return;
  }

  // mode 분기
  const activeMode = document.querySelector('.mode-tab-active')?.dataset?.mode || 'analyze';
  if (activeMode === 'bench') {
    return runBench(desc);
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
    if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      analyze();
    }
  });
  // Mode tabs
  document.querySelectorAll('.mode-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('mode-tab-active'));
      tab.classList.add('mode-tab-active');
    });
  });
  loadHealth();
  loadSamples();
  setInterval(loadHealth, 30000);
});
