'use strict';

const getCsrf = () => { const m = document.cookie.match(/csrftoken=([^;]+)/); return m ? m[1] : ''; };
const api = async (url, opts={}) => {
  const res = await fetch(url, {
    headers: { 'Accept': 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf(), ...(opts.headers||{}) },
    ...opts
  });
  if(!res.ok) throw new Error(await res.text());
  return res.json();
};

const showToast = (msg, isError=false) => {
  const t = document.getElementById('bmToast');
  t.className = `toast text-white border-0 ${isError ? 'bg-danger' : 'bg-success'}`;
  document.getElementById('bmToastMsg').textContent = msg;
  document.getElementById('bmToastIcon').className = isError ? 'bi bi-exclamation-triangle-fill fs-5' : 'bi bi-check-circle-fill fs-5';
  bootstrap.Toast.getOrCreateInstance(t).show();
};

let activeCattle = [];

/* ── Boot ────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', async () => {
  try {
    const cRes = await api('/api/cattle/?is_active=true&page_size=500');
    activeCattle = cRes.results || [];
    
    // Populate dropdowns
    const opts = '<option value="">Select cattle...</option>' + activeCattle.map(c => `<option value="${c.id}">${c.name} (${c.tag_number})</option>`).join('');
    document.querySelectorAll('.cattle-select-options, #predCattleSelect').forEach(el => el.innerHTML = opts);
    
    await Promise.allSettled([
      loadOverview(),
      loadHeatCycles(),
      loadAIEvents(),
      loadPregnancies()
    ]);
  } catch(e) { console.error('Boot error:', e); }
});

/* ── Sec 1: Overview ─────────────────────────────────────────────────────── */
async function loadOverview() {
  try {
    const [pregRes, dueRes, heatRes, aiRes] = await Promise.allSettled([
      api('/api/breeding/pregnancy/?is_active=true'),
      api('/api/breeding/due-this-week/'),
      api('/api/breeding/heat-cycles/?date_from=' + new Date(Date.now()-7*864e5).toISOString().slice(0,10)),
      api('/api/breeding/ai/?outcome=PENDING')
    ]);
    
    const countP = pregRes.value?.count || 0;
    const countD = dueRes.value?.count || 0;
    const countH = heatRes.value?.count || 0;
    const countA = aiRes.value?.count || 0;

    document.getElementById('overviewStrip').innerHTML = `
      <div class="bm-stat-card"><div class="bm-stat-icon" style="background:#fff0f6;color:#c0396e">🐄</div><div><div class="bm-stat-val">${countP}</div><div class="bm-stat-lbl">Pregnant Cattle</div></div></div>
      <div class="bm-stat-card"><div class="bm-stat-icon" style="background:#fffaf0;color:#c05621">🚨</div><div><div class="bm-stat-val">${countD}</div><div class="bm-stat-lbl">Calvings This Week</div></div></div>
      <div class="bm-stat-card"><div class="bm-stat-icon" style="background:#fffff0;color:#975a16">🔥</div><div><div class="bm-stat-val">${countH}</div><div class="bm-stat-lbl">In Heat (7d)</div></div></div>
      <div class="bm-stat-card"><div class="bm-stat-icon" style="background:#f0f7ff;color:#2b6cb0">💉</div><div><div class="bm-stat-val">${countA}</div><div class="bm-stat-lbl">Pending AI Outcomes</div></div></div>
    `;
  } catch(e) { console.error(e); }
}

/* ── Sec 2: Heat Cycles ──────────────────────────────────────────────────── */
async function loadHeatCycles() {
  // Simple grouping approach for demo - fetch logs, get latest per cattle, and try to fetch predict for active ones
  // A production app would have a dedicated endpoint for this table
  try {
    const logs = (await api('/api/breeding/heat-cycles/?page_size=200')).results || [];
    const latest = {};
    logs.forEach(l => {
      if(!latest[l.cattle_id] || latest[l.cattle_id].observed_date < l.observed_date) latest[l.cattle_id] = l;
    });

    const rows = await Promise.all(Object.values(latest).map(async l => {
      const p = await api(`/api/breeding/cattle/${l.cattle_id}/predict-breeding/`).catch(() => ({}));
      const nextDate = p.predicted_next_heat;
      
      let badge = '<span class="dm-badge dm-badge--gray">OK</span>';
      let hl = '';
      if(nextDate) {
        const diff = (new Date(nextDate) - new Date()) / 864e5;
        if(diff >= 0 && diff <= 3) {
          badge = '<span class="dm-badge dm-badge--amber">UPCOMING</span>';
          hl = 'row-highlight';
        } else if (diff < 0 && diff > -2) {
          badge = '<span class="dm-badge dm-badge--red">IN HEAT</span>';
          hl = 'row-highlight';
        }
      }

      return `<tr class="${hl}">
        <td><div class="fw-700">${l.cattle_tag}</div></td>
        <td>${l.observed_date}</td>
        <td>${p.avg_cycle_length_days ? p.avg_cycle_length_days.toFixed(1) : '—'}</td>
        <td>${nextDate || '—'}</td>
        <td>${badge}</td>
        <td><button class="dm-btn dm-btn--sm dm-btn--outline" onclick="document.querySelector('#formHeatLog [name=cattle_id]').value=${l.cattle_id};new bootstrap.Modal('#modalHeatLog').show()">+ Log</button></td>
      </tr>`;
    }));
    
    document.getElementById('heatTbody').innerHTML = rows.length ? rows.join('') : '<tr><td colspan="6" class="text-center py-3 text-muted">No heat cycles recorded</td></tr>';
  } catch(e) { console.error(e); }
}

/* ── Sec 3: AI Events ────────────────────────────────────────────────────── */
async function loadAIEvents() {
  try {
    const ais = (await api('/api/breeding/ai/')).results || [];
    const html = ais.map(a => {
      let b = `<span class="dm-badge dm-badge--gray">${a.outcome}</span>`;
      if(a.outcome==='CONFIRMED_PREGNANT') b = `<span class="dm-badge dm-badge--green">PREGNANT</span>`;
      if(a.outcome==='FAILED') b = `<span class="dm-badge dm-badge--red">FAILED</span>`;
      
      let act = '';
      if(a.outcome==='PENDING') {
        act = `<select class="form-select form-select-sm d-inline-block w-auto" onchange="updateAI(${a.id}, this.value)">
          <option value="">Update...</option>
          <option value="CONFIRMED_PREGNANT">Confirmed Pregnant</option>
          <option value="FAILED">Failed</option>
        </select>`;
      }
      return `<tr>
        <td><div class="fw-700">${a.cattle_tag}</div></td>
        <td>${a.ai_date}</td>
        <td>${a.semen_bull_name} <small class="text-muted">(${a.semen_batch_id})</small></td>
        <td>${a.technician_name}</td>
        <td>${b}</td>
        <td>${act}</td>
      </tr>`;
    }).join('');
    document.getElementById('aiTbody').innerHTML = html || '<tr><td colspan="6" class="text-center py-3 text-muted">No AI records</td></tr>';
  } catch(e) { console.error(e); }
}

window.updateAI = async (id, outcome) => {
  if(!outcome) return;
  try {
    await api(`/api/breeding/ai/${id}/mark-outcome/`, { method: 'POST', body: JSON.stringify({outcome}) });
    showToast('AI Outcome updated');
    loadAIEvents();
    if(outcome==='CONFIRMED_PREGNANT') loadPregnancies();
  } catch(e) { showToast('Error updating AI', true); }
}

/* ── Sec 4: Pregnancies ──────────────────────────────────────────────────── */
async function loadPregnancies() {
  try {
    const pregs = (await api('/api/breeding/pregnancy/?is_active=true')).results || [];
    const html = pregs.map(p => {
      const d = p.days_until_calving;
      const bCls = (d!==null && d<14) ? 'preg-days-soon' : 'preg-days-ok';
      return `<div class="preg-card">
        <div class="preg-card-title">
          <span>${p.cattle_tag}</span>
          <span class="preg-days-badge ${bCls}">${d!==null ? d+' days left' : 'Overdue'}</span>
        </div>
        <div class="preg-meta">Due: <strong>${p.expected_calving_date}</strong></div>
        <div class="preg-progress-wrap">
          <div class="preg-progress-bar" style="width:${p.gestation_progress_percent}%"></div>
        </div>
        <div class="preg-progress-lbl"><span>Progress</span><span>${p.gestation_progress_percent}%</span></div>
        <button class="dm-btn dm-btn--sm dm-btn--outline w-100 mt-3" onclick="document.getElementById('calvPregId').value=${p.id};new bootstrap.Modal('#modalCalving').show()">Record Calving</button>
      </div>`;
    }).join('');
    document.getElementById('pregGrid').innerHTML = html || '<div class="text-muted w-100 p-4">No active pregnancies</div>';
  } catch(e) { console.error(e); }
}

/* ── Sec 5: Predictions ──────────────────────────────────────────────────── */
document.getElementById('predCattleSelect').addEventListener('change', async function() {
  const cid = this.value;
  const pWindow = document.getElementById('predWindowPanel');
  const pSucc   = document.getElementById('predSuccessPanel');
  
  if(!cid) {
    pWindow.innerHTML = '<div class="text-center text-muted py-4">Select cattle</div>';
    pSucc.innerHTML = '<div class="text-center text-muted py-4">Select cattle</div>';
    return;
  }
  
  pWindow.innerHTML = '<div class="spinner-border spinner-border-sm text-success m-3"></div> Loading...';
  pSucc.innerHTML = '<div class="spinner-border spinner-border-sm text-success m-3"></div> Loading...';

  try {
    const [wRes, sRes] = await Promise.allSettled([
      api(`/api/breeding/cattle/${cid}/predict-breeding/`),
      api(`/api/breeding/cattle/${cid}/ai-success-prob/`)
    ]);

    // Window
    if(wRes.value && !wRes.value.error) {
      const d = wRes.value;
      let badge = 'bg-secondary';
      if(d.confidence==='HIGH') badge='bg-success';
      if(d.confidence==='MEDIUM') badge='bg-warning text-dark';
      
      pWindow.innerHTML = `
        <h5 class="fw-700 mb-4"><i class="bi bi-calendar-check me-2 text-dm-green"></i>Best Breeding Window</h5>
        <div class="mb-3">Predicted Next Heat: <strong>${d.predicted_next_heat}</strong></div>
        <div class="mb-3">Best AI Date: <strong class="fs-5 text-dm-green">${d.best_ai_date}</strong></div>
        <div class="mb-3">Time Window: <span class="badge bg-light text-dark border">${(d.optimal_window_start||'').replace('T',' ')} – ${(d.optimal_window_end||'').replace('T',' ')}</span></div>
        <div>Confidence: <span class="badge ${badge}">${d.confidence}</span> <small class="text-muted ms-2">(${d.cycles_analyzed} cycles)</small></div>
      `;
    } else {
      pWindow.innerHTML = `<div class="alert alert-warning">Insufficient heat cycle history to predict window.</div>`;
    }

    // Success
    if(sRes.value && !sRes.value.error) {
      const d = sRes.value;
      const pct = d.success_percent || 0;
      let col = '#e53e3e';
      if(pct > 65) col = '#38a169';
      else if(pct >= 40) col = '#dd6b20';
      
      const factors = (d.key_factors||[]).map(f => `<li>${f}</li>`).join('');
      
      pSucc.innerHTML = `
        <h5 class="fw-700 mb-4 text-center">AI Success Probability</h5>
        <div class="gauge-wrap" style="--gauge-deg:${pct*3.6}deg;--gauge-color:${col}">
          <div class="gauge-circle"><div class="gauge-inner"><span class="gauge-val" style="color:${col}">${pct}%</span><span class="gauge-lbl">${d.confidence}</span></div></div>
        </div>
        <p class="text-center fw-600 mb-3" style="color:${col}">${d.recommendation||''}</p>
        <ul class="text-muted" style="font-size:.85rem;padding-left:1.5rem">${factors}</ul>
      `;
    } else {
      pSucc.innerHTML = `<div class="alert alert-warning">Could not calculate success probability.</div>`;
    }
  } catch(e) {
    pWindow.innerHTML = `<div class="text-danger">Error loading predictions</div>`;
  }
});


/* ── Form Submissions ────────────────────────────────────────────────────── */
document.getElementById('formHeatLog').addEventListener('submit', async function(e) {
  e.preventDefault();
  try {
    const body = Object.fromEntries(new FormData(this).entries());
    await api('/api/breeding/heat-cycles/', { method: 'POST', body: JSON.stringify(body) });
    bootstrap.Modal.getInstance(document.getElementById('modalHeatLog')).hide();
    this.reset(); showToast('Heat logged successfully');
    loadHeatCycles(); loadOverview();
  } catch(err) { showToast('Error logging heat', true); }
});

document.getElementById('formAI').addEventListener('submit', async function(e) {
  e.preventDefault();
  try {
    const body = Object.fromEntries(new FormData(this).entries());
    await api('/api/breeding/ai/', { method: 'POST', body: JSON.stringify(body) });
    bootstrap.Modal.getInstance(document.getElementById('modalAI')).hide();
    this.reset(); showToast('AI Event recorded');
    loadAIEvents(); loadOverview();
  } catch(err) { showToast('Error recording AI', true); }
});

document.getElementById('formCalving').addEventListener('submit', async function(e) {
  e.preventDefault();
  try {
    const data = Object.fromEntries(new FormData(this).entries());
    const id = data.pregnancy_id; delete data.pregnancy_id;
    await api(`/api/breeding/pregnancy/${id}/record-calving/`, { method: 'POST', body: JSON.stringify(data) });
    bootstrap.Modal.getInstance(document.getElementById('modalCalving')).hide();
    this.reset(); showToast('Calving recorded');
    loadPregnancies(); loadOverview();
  } catch(err) { showToast('Error recording calving', true); }
});
