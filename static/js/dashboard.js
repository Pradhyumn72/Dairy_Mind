/**
 * DairyMind — Dashboard JS
 * ========================
 * All fetch() calls for the dashboard page.
 * Runs after DOM is ready.  Uses native fetch() + Chart.js (loaded via CDN).
 *
 * API endpoints used
 * ------------------
 * GET /api/cattle/?is_active=true            → total active cattle count
 * GET /api/milk/daily-summary/?date=TODAY    → today's milk production
 * GET /api/alerts/?is_resolved=false         → unresolved health alerts
 * GET /api/costs/summary/farm/?month=current → this month's profit
 * GET /api/breeding/due-this-week/           → cows due for breeding
 * GET /api/milk/logs/?date_from=D&date_to=T&ordering=date → 30-day trend
 * GET /api/cattle/?is_active=true&page_size=500 → breed distribution
 * GET /api/milk/top-producers/               → top 5 today's producers
 */

'use strict';

/* ── Helpers ───────────────────────────────────────────────────────────────── */

/** Return YYYY-MM-DD string for a Date object */
function fmtDate(d) {
  return d.toISOString().slice(0, 10);
}

/** Today's date string */
const TODAY = fmtDate(new Date());

/** N days ago */
function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return fmtDate(d);
}

/** Current month/year */
const NOW_MONTH = new Date().getMonth() + 1;
const NOW_YEAR  = new Date().getFullYear();

/** Format a number as Indian INR shorthand (₹1.2L, ₹45K, etc.) */
function fmtINR(value) {
  const abs = Math.abs(value);
  let formatted;
  if (abs >= 100000) {
    formatted = '₹' + (value / 100000).toFixed(1) + 'L';
  } else if (abs >= 1000) {
    formatted = '₹' + (value / 1000).toFixed(1) + 'K';
  } else {
    formatted = '₹' + value.toFixed(0);
  }
  return formatted;
}

/** Get a CSRF token from the cookie (Django default) */
function getCsrfToken() {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : '';
}

/** Shared fetch wrapper — always sends credentials + auth headers */
async function apiFetch(url) {
  const res = await fetch(url, {
    credentials: 'same-origin',
    headers: {
      'Accept':           'application/json',
      'X-Requested-With': 'XMLHttpRequest',
      'X-CSRFToken':      getCsrfToken(),
    },
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status} for ${url}`);
  }
  return res.json();
}

/** Set element text content (null-safe) */
function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

/** Show error state on a stat card */
function setError(id, msg = 'Error') {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = msg;
    el.classList.add('text-danger');
  }
}

/** Hide skeleton and reveal real content */
function revealCard(skeletonId, contentId) {
  const sk = document.getElementById(skeletonId);
  const ct = document.getElementById(contentId);
  if (sk) sk.style.display = 'none';
  if (ct) ct.style.display = '';
}

/** Replace a section's inner HTML with an error panel */
function showSectionError(containerId, message) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `
    <div class="dm-alert dm-alert--danger d-flex align-items-center gap-2" role="alert">
      <i class="bi bi-exclamation-triangle-fill fs-5 flex-shrink-0"></i>
      <div>
        <strong>Failed to load data.</strong><br>
        <small class="text-muted">${message}</small>
      </div>
    </div>`;
}

/* ── Severity helpers ──────────────────────────────────────────────────────── */

const SEVERITY_CONFIG = {
  HIGH:   { cls: 'dm-alert--danger',  icon: 'bi-exclamation-triangle-fill', badge: 'dm-badge--red'   },
  MEDIUM: { cls: 'dm-alert--warning', icon: 'bi-exclamation-circle-fill',   badge: 'dm-badge--amber' },
  LOW:    { cls: 'dm-alert--info',    icon: 'bi-info-circle-fill',           badge: 'dm-badge--blue'  },
};

function severityCfg(sev) {
  return SEVERITY_CONFIG[sev] || SEVERITY_CONFIG.LOW;
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/* STAT CARDS                                                                 */
/* ═══════════════════════════════════════════════════════════════════════════ */

/** Card 1 — Total Active Cattle */
async function loadActiveCattle() {
  try {
    const data = await apiFetch('/api/cattle/?is_active=true&page_size=1');
    // DRF pagination: { count, results }
    const count = data.count !== undefined ? data.count : (data.results ? data.results.length : 0);
    setText('statCattleValue', count);
    revealCard('statCattleSkeleton', 'statCattleContent');
  } catch (err) {
    revealCard('statCattleSkeleton', 'statCattleContent');
    setError('statCattleValue', '—');
    console.warn('[dashboard] cattle count error:', err);
  }
}

/** Card 2 — Today's Total Milk Production */
async function loadDailyMilk() {
  try {
    const data = await apiFetch(`/api/milk/daily-summary/?date=${TODAY}`);
    const litres = Number(data.total_litres || 0).toFixed(1);
    setText('statMilkValue', litres);
    setText('statMilkSub', `${data.cattle_count || 0} cows logged`);
    revealCard('statMilkSkeleton', 'statMilkContent');
  } catch (err) {
    revealCard('statMilkSkeleton', 'statMilkContent');
    setError('statMilkValue', '—');
    console.warn('[dashboard] daily milk error:', err);
  }
}

/** Card 3 — Unresolved Health Alerts */
async function loadHealthAlerts() {
  try {
    const data = await apiFetch('/api/alerts/?is_resolved=false');
    const count = data.count !== undefined ? data.count : 0;
    setText('statAlertsValue', count);
    revealCard('statAlertsSkeleton', 'statAlertsContent');
  } catch (err) {
    revealCard('statAlertsSkeleton', 'statAlertsContent');
    setError('statAlertsValue', '—');
    console.warn('[dashboard] health alerts error:', err);
  }
}

/** Card 4 — This Month's Farm Profit */
async function loadFarmProfit() {
  try {
    const data = await apiFetch(`/api/costs/summary/farm/?month=${NOW_MONTH}&year=${NOW_YEAR}`);
    const profit = Number(data.farm_total_profit || 0);
    const formatted = fmtINR(profit);
    setText('statProfitValue', formatted);
    const subEl = document.getElementById('statProfitSub');
    if (subEl) {
      subEl.textContent = profit >= 0 ? 'This month' : 'Net loss this month';
      subEl.className   = profit >= 0 ? 'dm-stat-card__delta dm-stat-card__delta--up'
                                       : 'dm-stat-card__delta dm-stat-card__delta--down';
    }
    revealCard('statProfitSkeleton', 'statProfitContent');
  } catch (err) {
    revealCard('statProfitSkeleton', 'statProfitContent');
    setError('statProfitValue', '—');
    console.warn('[dashboard] farm profit error:', err);
  }
}

/** Card 5 — Cows Due for Breeding This Week */
async function loadBreedingDue() {
  try {
    const data = await apiFetch('/api/breeding/due-this-week/');
    const count = data.count !== undefined ? data.count : 0;
    setText('statBreedingValue', count);
    if (count > 0) {
      const el = document.getElementById('statBreedingValue');
      if (el) el.classList.add('text-danger');
    }
    revealCard('statBreedingSkeleton', 'statBreedingContent');
  } catch (err) {
    revealCard('statBreedingSkeleton', 'statBreedingContent');
    setError('statBreedingValue', '—');
    console.warn('[dashboard] breeding due error:', err);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/* CHARTS                                                                     */
/* ═══════════════════════════════════════════════════════════════════════════ */

let milkTrendChart = null;
let breedDonutChart = null;

/**
 * Chart 1 — 30-day milk production trend
 * Fetches daily milk logs, groups by date, then renders a line chart.
 */
async function loadMilkTrendChart() {
  const ctx = document.getElementById('milkTrendChart');
  if (!ctx) return;

  const dateFrom = daysAgo(29);  // 30 days including today

  try {
    // Fetch all logs in the window; use page_size=1000 to get everything
    const data = await apiFetch(
      `/api/milk/logs/?date_from=${dateFrom}&date_to=${TODAY}&ordering=date&page_size=1000`
    );

    const logs = data.results || data;

    // Aggregate total_litres per date
    const byDate = {};
    for (const log of logs) {
      byDate[log.date] = (byDate[log.date] || 0) + parseFloat(log.total_litres || 0);
    }

    // Build a full 30-day axis (fill 0 for missing days)
    const labels = [];
    const values = [];
    for (let i = 29; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const key = fmtDate(d);
      labels.push(key.slice(5));  // "MM-DD" label
      values.push(parseFloat((byDate[key] || 0).toFixed(2)));
    }

    // Hide skeleton, reveal canvas
    const wrap = document.getElementById('milkTrendWrap');
    if (wrap) wrap.style.display = '';
    const sk = document.getElementById('milkTrendSkeleton');
    if (sk) sk.style.display = 'none';

    if (milkTrendChart) milkTrendChart.destroy();

    milkTrendChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label:           'Farm Milk (litres)',
          data:            values,
          borderColor:     'rgba(46,133,85,1)',
          backgroundColor: 'rgba(46,133,85,0.10)',
          borderWidth:     2.5,
          pointRadius:     3,
          pointHoverRadius: 6,
          pointBackgroundColor: 'rgba(46,133,85,1)',
          fill:            true,
          tension:         0.4,
        }],
      },
      options: {
        responsive:          true,
        maintainAspectRatio: false,
        interaction:         { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1a4731',
            titleColor:      '#d4f0e1',
            bodyColor:       '#fff',
            padding:         10,
            callbacks: {
              label: ctx => ` ${ctx.parsed.y.toFixed(1)} litres`,
            },
          },
        },
        scales: {
          x: {
            grid:   { display: false },
            ticks:  {
              color:      '#718096',
              font:       { size: 11 },
              maxTicksLimit: 10,
            },
          },
          y: {
            beginAtZero: true,
            grid:  { color: 'rgba(0,0,0,.05)' },
            ticks: {
              color:     '#718096',
              font:      { size: 11 },
              callback:  v => v + ' L',
            },
          },
        },
      },
    });
  } catch (err) {
    showSectionError('milkTrendContainer', err.message);
    console.warn('[dashboard] milk trend chart error:', err);
  }
}

/**
 * Chart 2 — Breed distribution donut
 * Derives breed counts from the active cattle list.
 */
async function loadBreedDonutChart() {
  const ctx = document.getElementById('breedDonutChart');
  if (!ctx) return;

  try {
    const data = await apiFetch('/api/cattle/?is_active=true&page_size=500');
    const cattle = data.results || [];

    // Count breeds
    const breedCount = {};
    for (const c of cattle) {
      const breed = c.breed || 'Unknown';
      breedCount[breed] = (breedCount[breed] || 0) + 1;
    }

    const labels = Object.keys(breedCount);
    const values = Object.values(breedCount);

    // Palette — greens + complementary tones
    const PALETTE = [
      '#2e8555', '#3aaa6e', '#6fcf97', '#d4f0e1',
      '#f5a623', '#3182ce', '#e53e3e', '#805ad5',
      '#0bc5ea', '#f6e05e', '#68d391',
    ];
    const bgColors = labels.map((_, i) => PALETTE[i % PALETTE.length]);

    // Hide skeleton, show canvas
    const sk = document.getElementById('breedDonutSkeleton');
    if (sk) sk.style.display = 'none';
    const wrap = document.getElementById('breedDonutWrap');
    if (wrap) wrap.style.display = '';

    if (breedDonutChart) breedDonutChart.destroy();

    breedDonutChart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data:             values,
          backgroundColor:  bgColors,
          borderColor:      '#ffffff',
          borderWidth:      3,
          hoverBorderWidth: 4,
          hoverOffset:      8,
        }],
      },
      options: {
        responsive:          true,
        maintainAspectRatio: false,
        cutout:              '65%',
        plugins: {
          legend: {
            position:  'bottom',
            labels: {
              padding:   14,
              font:      { size: 12 },
              color:     '#2d3748',
              usePointStyle: true,
              pointStyleWidth: 10,
            },
          },
          tooltip: {
            backgroundColor: '#1a4731',
            titleColor:      '#d4f0e1',
            bodyColor:       '#fff',
            padding:         10,
            callbacks: {
              label: ctx => {
                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                const pct   = ((ctx.parsed / total) * 100).toFixed(1);
                return ` ${ctx.parsed} cattle (${pct}%)`;
              },
            },
          },
        },
      },
    });

    // Legend summary below chart
    const summary = document.getElementById('breedSummary');
    if (summary) {
      summary.innerHTML = labels.map((breed, i) => `
        <span class="dm-badge" style="background:${bgColors[i]}22;color:${bgColors[i]};border:1px solid ${bgColors[i]}44;margin:2px 3px;">
          ${breed}: <strong>${values[i]}</strong>
        </span>`).join('');
    }

  } catch (err) {
    showSectionError('breedDonutContainer', err.message);
    console.warn('[dashboard] breed donut chart error:', err);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/* TABLE — TOP 5 MILK PRODUCERS TODAY                                        */
/* ═══════════════════════════════════════════════════════════════════════════ */

async function loadTopProducers() {
  const tbody = document.getElementById('topProducersTbody');
  const sk    = document.getElementById('topProducersSkeleton');
  if (!tbody) return;

  try {
    // Use today's date for milk log filter ordered by total desc
    const data = await apiFetch(
      `/api/milk/logs/?date=${TODAY}&ordering=-total_litres&page_size=5`
    );
    const logs = data.results || data;

    if (sk) sk.style.display = 'none';
    tbody.style.display = '';

    if (!logs.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="4" class="text-center py-4 text-muted">
            <i class="bi bi-droplet-half me-2"></i>No milk logs recorded yet today.
          </td>
        </tr>`;
      return;
    }

    // Rank & render top 5
    tbody.innerHTML = logs.slice(0, 5).map((log, i) => {
      const tag  = log.cattle_tag_number || log.cattle?.tag_number || '—';
      const name = log.cattle_name       || log.cattle?.name       || '—';
      const total = parseFloat(log.total_litres || 0).toFixed(1);
      const am  = parseFloat(log.morning_litres || 0).toFixed(1);
      const pm  = parseFloat(log.evening_litres || 0).toFixed(1);
      const rankBadge = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `#${i + 1}`;
      return `
        <tr>
          <td class="fw-600 text-center" style="width:48px;">${rankBadge}</td>
          <td>
            <div class="fw-600" style="font-size:.87rem">${name}</div>
            <div class="text-dm-muted" style="font-size:.74rem">${tag}</div>
          </td>
          <td class="text-muted" style="font-size:.82rem">${am}L / ${pm}L</td>
          <td>
            <span class="dm-badge dm-badge--green fw-700" style="font-size:.82rem">
              ${total} L
            </span>
          </td>
        </tr>`;
    }).join('');

  } catch (err) {
    if (sk) sk.style.display = 'none';
    tbody.style.display = '';
    tbody.innerHTML = `
      <tr>
        <td colspan="4" class="text-center py-3 text-danger">
          <i class="bi bi-exclamation-triangle me-1"></i> Failed to load data.
        </td>
      </tr>`;
    console.warn('[dashboard] top producers error:', err);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/* LIST — LATEST 5 HEALTH ALERTS                                             */
/* ═══════════════════════════════════════════════════════════════════════════ */

async function loadLatestAlerts() {
  const container = document.getElementById('latestAlertsContainer');
  const sk        = document.getElementById('latestAlertsSkeleton');
  if (!container) return;

  try {
    // Get latest 5 unresolved alerts (API returns newest-first)
    const data = await apiFetch('/api/alerts/?is_resolved=false&page_size=5');
    const alerts = data.results || [];

    if (sk) sk.style.display = 'none';
    container.style.display = '';

    if (!alerts.length) {
      container.innerHTML = `
        <div class="text-center py-5 text-muted">
          <i class="bi bi-check-circle-fill text-success" style="font-size:2rem"></i>
          <p class="mt-2 mb-0 fw-600">All clear! No unresolved alerts.</p>
        </div>`;
      return;
    }

    container.innerHTML = alerts.slice(0, 5).map(alert => {
      const cfg  = severityCfg(alert.severity || 'LOW');
      const date = alert.alert_date || (alert.created_at || '').slice(0, 10);
      const msg  = alert.message || 'No details available.';
      const tag  = alert.tag_number || '—';
      const name = alert.cattle_name || '—';

      return `
        <div class="dm-alert ${cfg.cls} mb-2 py-2 px-3" role="alert"
             style="border-radius:var(--radius-md);font-size:.85rem;border-left-width:4px;">
          <div class="d-flex align-items-start gap-2 flex-grow-1">
            <i class="bi ${cfg.icon} flex-shrink-0 mt-1" aria-hidden="true"></i>
            <div class="flex-grow-1 min-w-0">
              <div class="d-flex align-items-center justify-content-between gap-2 mb-1">
                <span class="fw-700" style="font-size:.8rem">
                  ${name}
                  <span class="text-muted fw-400">(${tag})</span>
                </span>
                <span class="dm-badge ${cfg.badge} flex-shrink-0">${alert.severity || 'LOW'}</span>
              </div>
              <div class="text-dm-muted" style="font-size:.78rem">
                <i class="bi bi-clock me-1"></i>${date}
                &nbsp;·&nbsp;${alert.alert_type || ''}
              </div>
              <div class="mt-1" style="line-height:1.4">${msg}</div>
            </div>
          </div>
        </div>`;
    }).join('');

  } catch (err) {
    if (sk) sk.style.display = 'none';
    container.style.display = '';
    showSectionError('latestAlertsContainer', err.message);
    console.warn('[dashboard] latest alerts error:', err);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/* BOOT — run all loaders in parallel                                        */
/* ═══════════════════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', function () {
  Promise.allSettled([
    // Stat cards (independent)
    loadActiveCattle(),
    loadDailyMilk(),
    loadHealthAlerts(),
    loadFarmProfit(),
    loadBreedingDue(),

    // Charts
    loadMilkTrendChart(),
    loadBreedDonutChart(),

    // Table & list
    loadTopProducers(),
    loadLatestAlerts(),
  ]).then(results => {
    const failed = results.filter(r => r.status === 'rejected');
    if (failed.length) {
      console.warn('[dashboard] Some loaders failed:', failed.map(r => r.reason));
    }
    console.info('[dashboard] Dashboard load complete.');
  });

  /* ── Live timestamp ──────────────────────────────────────────────────── */
  const clockEl = document.getElementById('dmLiveClock');
  function updateClock() {
    if (!clockEl) return;
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString('en-IN', {
      hour:   '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }
  updateClock();
  setInterval(updateClock, 1000);
});
