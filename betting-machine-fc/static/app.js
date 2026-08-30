// FC Betting Machine — Web Dashboard Client Application

let activeMarketFilter = 'all';
let allPicksData = [];
let allMatchesData = [];
let currentConfig = null;

// Initialize on DOM loaded
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initFilters();
  initTrackerFilters();
  initScanButton();
  initBacktestForm();
  initSimForm();
  initSettingsForm();
  initModal();

  loadConfig();
  loadPicks();
  loadMatches();
  loadTracker();
  initSettlement();
});

// Tab Switching
function initTabs() {
  const tabs = document.querySelectorAll('.tab-btn[data-tab]');
  tabs.forEach(btn => {
    btn.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const targetId = `tab-${btn.dataset.tab}`;
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.add('active');
    });
  });
}

// Banner Helper
function showBanner(message, isError = false) {
  const banner = document.getElementById('status-banner');
  const msgEl = document.getElementById('status-message');
  banner.className = `status-banner ${isError ? 'status-error' : ''}`;
  msgEl.textContent = message;
  banner.classList.remove('hidden');
}

document.getElementById('btn-close-banner')?.addEventListener('click', () => {
  document.getElementById('status-banner').classList.add('hidden');
});

// Load Configuration
async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    if (!res.ok) return;
    currentConfig = await res.json();

    // Populate settings form
    document.getElementById('cfg-data-source').value = currentConfig.data_source || '1xbit';
    document.getElementById('cfg-min-odds').value = currentConfig.filters?.min_odds ?? 1.66;
    document.getElementById('cfg-min-ev').value = currentConfig.filters?.min_ev ?? 0.0;
    document.getElementById('cfg-max-ah').value = currentConfig.filters?.max_ah_abs_line ?? 1.5;
  } catch (err) {
    console.error('Error loading config:', err);
  }
}

// Live Picks Loading & Filtering
async function loadPicks() {
  try {
    const minEv = document.getElementById('filter-min-ev')?.value || '0.02';
    const sortBy = document.getElementById('filter-sort')?.value || 'rank_score';
    const maxOdds = document.getElementById('filter-max-odds')?.value;

    let url = `/api/picks?min_odds=1.66&min_ev=${minEv}&sort_by=${sortBy}&sort_order=desc`;
    if (maxOdds) url += `&max_odds=${maxOdds}`;

    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to fetch picks');
    const data = await res.json();

    allPicksData = data.picks || [];
    renderSummary(data.summary);
    populateLeagueFilter(data.summary?.leagues || []);
    renderPicks();
  } catch (err) {
    console.error('Error loading picks:', err);
    showBanner('Error loading picks from server', true);
  }
}

function renderSummary(summary) {
  if (!summary) return;
  document.getElementById('kpi-qualified-picks').textContent = summary.qualified_picks ?? '-';

  if (summary.last_scan_time) {
    const d = new Date(summary.last_scan_time);
    document.getElementById('last-sync-text').textContent = `Last scanned: ${d.toLocaleTimeString()}`;
  } else {
    document.getElementById('last-sync-text').textContent = 'Last scanned: Cached live snapshot';
  }
}

const COUNTRY_MAP = {
  'Argentina Championship': 'Argentina',
  'Australia Championship': 'Australia',
  'Austrian 2': 'Austria',
  'Bolivia Cup': 'Bolivia',
  'Botswana Championship': 'Botswana',
  'Cambodia Championship': 'Cambodia',
  'Cambodia Super Cup': 'Cambodia',
  'Chile Championship': 'Chile',
  'Club Friendlies': 'Other',
  'Colombia Championship': 'Colombia',
  'Coppa Italia': 'Italy',
  'Dominican Republic Championship': 'Dominican Republic',
  'Finland Championship U21': 'Finland',
  'Georgia Championship': 'Georgia',
  'German Cup U19': 'Germany',
  'Israel Championship U19': 'Israel',
  'Italy Cup': 'Italy',
  'Kyrgyzstan Championship': 'Kyrgyzstan',
  'Lithuania Championship': 'Lithuania',
  'Mozambique Championship': 'Mozambique',
  'Nicaragua Championship': 'Nicaragua',
  'Oman Professional League': 'Oman',
  'Paraguay Championship': 'Paraguay',
  'Peru Championship': 'Peru',
  'Poland Championship': 'Poland',
  'Prague Championship': 'Czech Republic',
  'Republic of Malawi': 'Malawi',
  'Republic of North Macedonia Championship U19': 'Republic of North Macedonia',
  'Russian Championship': 'Russia',
  'Rwanda Super Cup': 'Rwanda',
  'Saudi Arabia Championship U21': 'Saudi Arabia',
  'Scotland Championship': 'Scotland',
  'Serbia Championship U19': 'Serbia',
  'Simon Bolivar Cup': 'Bolivia',
  'Slovenian Championship U19': 'Slovenia',
  'Switzerland Championship': 'Switzerland',
  'UAE Championship U23': 'UAE'
};

function splitLeague(l) {
  const idx = l.indexOf('.');
  if (idx > 0) {
    const country = l.slice(0, idx).trim();
    return { country: COUNTRY_MAP[country] || country, label: l.slice(idx + 1).trim() };
  }
  const country = COUNTRY_MAP[l.trim()] || 'Other';
  const label = country === 'Other' ? l.trim() : l.trim().replace(new RegExp('^' + country + '\\s*'), '').trim() || l.trim();
  return { country, label };
}

function populateLeagueFilter(leagues) {
  const select = document.getElementById('filter-league');
  const currentVal = select.value;
  select.innerHTML = '<option value="all">All Leagues</option>';
  const groups = {};
  leagues.forEach(l => {
    const { country, label } = splitLeague(l);
    (groups[country] = groups[country] || []).push({ full: l, label });
  });
  Object.keys(groups).sort((a, b) => a.localeCompare(b)).forEach(country => {
    const og = document.createElement('optgroup');
    og.label = country;
    groups[country].sort((a, b) => a.label.localeCompare(b.label)).forEach(item => {
      const opt = document.createElement('option');
      opt.value = item.full;
      opt.textContent = item.label;
      if (item.full === currentVal) opt.selected = true;
      og.appendChild(opt);
    });
    select.appendChild(og);
  });
}

function renderPicks() {
  const container = document.getElementById('picks-container');
  const emptyState = document.getElementById('picks-empty');
  const searchQ = document.getElementById('filter-search')?.value.toLowerCase().trim();
  const selectedLeague = document.getElementById('filter-league')?.value;

  container.innerHTML = '';

  const filtered = allPicksData.filter(p => {
    if (activeMarketFilter !== 'all' && p.market !== activeMarketFilter) return false;
    if (selectedLeague && selectedLeague !== 'all' && (!p.league || !p.league.toLowerCase().includes(selectedLeague.toLowerCase()))) return false;
    if (searchQ) {
      const m = (p.match || '').toLowerCase();
      const pick = (p.pick || '').toLowerCase();
      const l = (p.league || '').toLowerCase();
      if (!m.includes(searchQ) && !pick.includes(searchQ) && !l.includes(searchQ)) return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    emptyState.classList.remove('hidden');
    return;
  }
  emptyState.classList.add('hidden');

  filtered.forEach(p => {
    const card = document.createElement('div');
    card.className = 'pick-card';

    const marketClass = `badge-${p.market || '1x2'}`;

    card.innerHTML = `
      <div>
        <div class="pick-card-header"><span class="market-badge ${marketClass}">${p.market ? p.market.toUpperCase() : 'BET'}</span><span class="lock-badge">🔒 LOCKED</span></div>
        <div class="match-title">${p.match || 'Match'}</div>
        <div class="pick-meta">${p.league || 'Football League'}</div>
        <div class="pick-kickoff">${formatKickoff(p.start_ts)}</div>
        <div class="pick-selection-box">
          <span class="pick-name">${p.pick}</span>
          <span class="pick-odds">${p.odds.toFixed(3)}</span>
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

function formatKickoff(ts) {
  if (!ts) return '';
  const d = new Date(Number(ts) * 1000);
  if (isNaN(d.getTime())) return '';
  const dateStr = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  const timeStr = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  return `🗓️ ${dateStr} · ${timeStr}`;
}

async function loadTracker() {
  try {
    const res = await fetch('/api/tracker');
    if (!res.ok) throw new Error('Failed to load ROI tracker');
    const data = await res.json();
    const s = data.summary || {};
    document.getElementById('kpi-locked').textContent = s.locked_picks ?? 0;
    document.getElementById('kpi-settled').textContent = s.settled_picks ?? 0;
    const roi = s.roi_pct || 0;
    const roiEl = document.getElementById('kpi-roi');
    roiEl.textContent = `${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%`;
    roiEl.className = `kpi-val ${roi >= 0 ? 'text-emerald' : 'text-rose'}`;
    document.getElementById('tracker-locked').textContent = s.locked_picks ?? 0;
    document.getElementById('tracker-record').textContent = `${s.wins || 0}–${s.losses || 0}`;
    document.getElementById('tracker-pushes').textContent = `${s.pushes || 0} pushes`;
    document.getElementById('tracker-profit').textContent = `${(s.profit_units || 0).toFixed(2)}u`;
    document.getElementById('tracker-roi').textContent = `${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%`;

    trackerData = data;
    renderTracker();
  } catch (err) {
    showBanner(err.message, true);
  }
}

let marketSortDir = 'asc';
let trackerData = { locked: [], settled: [] };

function renderTracker() {
  const marketFilter = document.getElementById('tracker-filter-market')?.value || 'all';
  const statusFilter = document.getElementById('tracker-filter-status')?.value || 'all';
  const sortVal = document.getElementById('tracker-sort')?.value || 'date_desc';

  let rows = [...(trackerData.locked || []), ...(trackerData.settled || [])];

  if (marketFilter !== 'all') {
    rows = rows.filter(b => (b.market || '').toLowerCase() === marketFilter.toLowerCase());
  }
  if (statusFilter === 'locked') {
    rows = rows.filter(b => !b.settled);
  } else if (statusFilter === 'settled') {
    rows = rows.filter(b => b.settled);
  }

  const marketRank = { '1x2': 0, 'ah': 1, 'ou': 2, 'btts': 3, '': 9 };
  const dir = marketSortDir === 'asc' ? 1 : -1;
  switch (sortVal) {
    case 'market':
      rows.sort((a, b) => {
        const d = (marketRank[(a.market || '').toLowerCase()] ?? 9) - (marketRank[(b.market || '').toLowerCase()] ?? 9);
        return d !== 0 ? dir * d : dir * (a.match || '').localeCompare(b.match || '');
      });
      break;
    case 'odds_desc':
      rows.sort((a, b) => (Number(b.odds || 0) - Number(a.odds || 0)));
      break;
    case 'odds_asc':
      rows.sort((a, b) => (Number(a.odds || 0) - Number(b.odds || 0)));
      break;
    case 'date_asc':
      rows.sort((a, b) => (Number(a.start_ts || 0) - Number(b.start_ts || 0)));
      break;
    default:
      rows.sort((a, b) => (Number(b.start_ts || 0) - Number(a.start_ts || 0)));
  }

  const tbody = document.getElementById('tracker-table');
  tbody.innerHTML = rows.length ? rows.map((b) => {
    const dt = b.start_ts ? new Date(Number(b.start_ts) * 1000).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '-';
    const result = !b.settled ? 'Pending' : b.won === 1 ? 'Won' : b.won === 0 ? 'Lost' : 'Push';
    return `<tr><td>${b.settled ? 'Settled' : '🔒 Locked'}</td><td>${dt}</td><td>${b.match || '-'}</td><td>${(b.market || '').toUpperCase()}</td><td>${b.pick || '-'}</td><td>${Number(b.odds || 0).toFixed(2)}</td><td>${result}${b.settled ? ` (${Number(b.profit || 0).toFixed(2)}u)` : ''}</td></tr>`;
  }).join('') : '<tr><td colspan="7" class="text-center text-muted">No locked picks yet. Run a live scan first.</td></tr>';
}

function initTrackerFilters() {
  document.getElementById('tracker-filter-market')?.addEventListener('change', renderTracker);
  document.getElementById('tracker-filter-status')?.addEventListener('change', renderTracker);
  document.getElementById('tracker-sort')?.addEventListener('change', () => {
    const ind = document.getElementById('market-sort-indicator');
    if (ind) ind.textContent = '';
    renderTracker();
  });
  document.getElementById('th-market')?.addEventListener('click', () => {
    marketSortDir = marketSortDir === 'asc' ? 'desc' : 'asc';
    document.getElementById('tracker-sort').value = 'market';
    const ind = document.getElementById('market-sort-indicator');
    if (ind) ind.textContent = marketSortDir === 'asc' ? '▲' : '▼';
    renderTracker();
  });
}

function initSettlement() {
  const run = async () => {
    try {
      const res = await fetch('/api/settle', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Settlement failed');
      showBanner(`✅ Settlement refreshed: ${data.settled_now || 0} picks updated.`);
      await loadTracker();
    } catch (err) {
      showBanner(err.message, true);
    }
  };
  document.getElementById('btn-settle')?.addEventListener('click', run);
  document.getElementById('btn-settle-tracker')?.addEventListener('click', run);
}

function initFilters() {
  // Market Pill filters
  const pills = document.querySelectorAll('#market-pills .pill');
  pills.forEach(pill => {
    pill.addEventListener('click', () => {
      pills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      activeMarketFilter = pill.dataset.market;
      renderPicks();
    });
  });

  document.getElementById('filter-league')?.addEventListener('change', renderPicks);
  document.getElementById('filter-min-ev')?.addEventListener('change', loadPicks);
  document.getElementById('filter-sort')?.addEventListener('change', loadPicks);
  document.getElementById('filter-max-odds')?.addEventListener('input', loadPicks);
  document.getElementById('filter-search')?.addEventListener('input', renderPicks);
}

// Live Scanner Integration
function initScanButton() {
  const btn = document.getElementById('btn-scan');
  const spinner = document.getElementById('scan-spinner');
  const btnText = document.getElementById('scan-btn-text');

  btn.addEventListener('click', async () => {
    btn.disabled = true;
    spinner.classList.remove('hidden');
    btnText.textContent = 'Scanning 1xbit LineFeed...';
    showBanner('Triggered live scan on 1xbit LineFeed. Scraping live match odds...');

    try {
      const res = await fetch('/api/scan', { method: 'POST' });
      const data = await res.json();

      // Poll status
      const pollInterval = setInterval(async () => {
        try {
          const statusRes = await fetch('/api/scan/status');
          const state = await statusRes.json();
          if (!state.is_running) {
            clearInterval(pollInterval);
            btn.disabled = false;
            spinner.classList.add('hidden');
            btnText.textContent = '📡 Run Live Scan';

            if (state.error) {
              showBanner(`Scan failed: ${state.error}`, true);
            } else {
              showBanner(`✅ Scan complete! Evaluated ${state.last_scan_count} matches with ${state.last_scan_picks} qualified picks.`);
              loadPicks();
              loadMatches();
            }
          } else {
            showBanner(state.progress || 'Scanning active matches...');
          }
        } catch (e) {
          clearInterval(pollInterval);
          btn.disabled = false;
          spinner.classList.add('hidden');
          btnText.textContent = '📡 Run Live Scan';
        }
      }, 1500);
    } catch (err) {
      btn.disabled = false;
      spinner.classList.add('hidden');
      btnText.textContent = '📡 Run Live Scan';
      showBanner(`Scan trigger error: ${err.message}`, true);
    }
  });
}

// Matches & Matrices Explorer
async function loadMatches() {
  try {
    const res = await fetch('/api/matches');
    if (!res.ok) return;
    const data = await res.json();
    allMatchesData = data.matches || [];
    renderMatches();
  } catch (err) {
    console.error('Error loading matches:', err);
  }
}

document.getElementById('btn-refresh-matches')?.addEventListener('click', loadMatches);

function renderMatches() {
  const container = document.getElementById('matches-container');
  if (!container) return;
  container.innerHTML = '';

  if (allMatchesData.length === 0) {
    container.innerHTML = '<div class="card text-muted">No fixtures loaded yet. Run a live scan to populate fixtures.</div>';
    return;
  }

  allMatchesData.forEach((m, idx) => {
    const info = m.info || {};
    const card = document.createElement('div');
    card.className = 'match-card';

    const scoresHtml = (m.top_scores || []).map(s => 
      `<span class="score-chip">${s.score} (${(s.prob * 100).toFixed(1)}%)</span>`
    ).join('');

    card.innerHTML = `
      <div class="pick-card-header">
        <span class="league-badge">${info.league || 'League'}</span>
        <span class="market-badge badge-ou">Total λ: ${m.lambdas?.total || '-'}</span>
      </div>
      <div class="match-card-teams">⚽ ${info.home || 'Home'} vs ${info.away || 'Away'}</div>
      <div class="lambda-badges">
        <span class="lambda-pill">Home λ: <strong>${m.lambdas?.home || '-'}</strong></span>
        <span class="lambda-pill">Away λ: <strong>${m.lambdas?.away || '-'}</strong></span>
        <span class="lambda-pill">BTTS: <strong>${m.probs ? (m.probs.btts * 100).toFixed(1) + '%' : '-'}</strong></span>
      </div>
      <div class="top-scores-row">${scoresHtml}</div>
      <button class="btn btn-secondary btn-block" onclick="openMatchModal(${idx})">🔍 Inspect Full Valuation</button>
    `;
    container.appendChild(card);
  });
}

// Modal handling
function initModal() {
  document.getElementById('btn-close-modal')?.addEventListener('click', () => {
    document.getElementById('match-modal').classList.add('hidden');
  });
}

window.openMatchModal = function(idx) {
  const m = allMatchesData[idx];
  if (!m) return;

  const info = m.info || {};
  document.getElementById('modal-match-title').textContent = `${info.home} vs ${info.away}`;
  document.getElementById('modal-league-badge').textContent = info.league || 'Football';

  document.getElementById('modal-lh').textContent = m.lambdas?.home || '-';
  document.getElementById('modal-la').textContent = m.lambdas?.away || '-';
  document.getElementById('modal-ltot').textContent = m.lambdas?.total || '-';
  document.getElementById('modal-btts').textContent = m.probs ? `${(m.probs.btts * 100).toFixed(1)}%` : '-';

  const scoresContainer = document.getElementById('modal-scores-grid');
  scoresContainer.innerHTML = (m.top_scores || []).map(s => 
    `<span class="score-chip">${s.score} &rarr; ${(s.prob * 100).toFixed(1)}%</span>`
  ).join('');

  const tbody = document.getElementById('modal-markets-tbody');
  tbody.innerHTML = '';

  const picks = m.picks || [];
  if (picks.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No picks meeting positive EV threshold for this match</td></tr>';
  } else {
    picks.forEach(p => {
      const tr = document.createElement('tr');
      const fairOdds = p.probability > 0 ? (1.0 / p.probability).toFixed(3) : '-';
      tr.innerHTML = `
        <td><strong>${p.pick}</strong> (${p.market.toUpperCase()})</td>
        <td>${(p.probability * 100).toFixed(1)}%</td>
        <td>${fairOdds}</td>
        <td><strong>${p.odds.toFixed(3)}</strong></td>
        <td class="text-emerald font-bold">+${(p.ev * 100).toFixed(1)}%</td>
      `;
      tbody.appendChild(tr);
    });
  }

  document.getElementById('match-modal').classList.remove('hidden');
};

// Backtest Lab
function initBacktestForm() {
  const form = document.getElementById('backtest-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-run-backtest');
    btn.disabled = true;
    btn.textContent = '⏳ Running Simulation...';

    const payload = {
      league: document.getElementById('bt-league').value,
      season: document.getElementById('bt-season').value,
      min_odds: parseFloat(document.getElementById('bt-min-odds').value) || 1.66,
      min_ev: parseFloat(document.getElementById('bt-min-ev').value) || 0.02,
      market_filter: document.getElementById('bt-market').value,
    };

    try {
      const res = await fetch('/api/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error((await res.json()).detail || 'Backtest failed');
      const data = await res.json();
      renderBacktestResults(data);
    } catch (err) {
      showBanner(`Backtest error: ${err.message}`, true);
    } finally {
      btn.disabled = false;
      btn.textContent = '🧪 Run Backtest';
    }
  });
}

function renderBacktestResults(data) {
  document.getElementById('bt-val-bets').textContent = data.total_bets ?? 0;
  document.getElementById('bt-sub-matches').textContent = `${data.total_matches} matches evaluated`;

  document.getElementById('bt-val-hitrate').textContent = `${data.hit_rate_pct ?? 0}%`;
  document.getElementById('bt-sub-wins').textContent = `${data.total_wins} winning bets`;

  const profit = data.total_profit_units ?? 0;
  const profitEl = document.getElementById('bt-val-profit');
  profitEl.textContent = `${profit >= 0 ? '+' : ''}${profit.toFixed(2)} u`;
  profitEl.className = `kpi-val ${profit >= 0 ? 'text-emerald' : 'text-rose'}`;

  const roi = data.roi_pct ?? 0;
  const roiEl = document.getElementById('bt-val-roi');
  roiEl.textContent = `${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%`;
  roiEl.className = `kpi-val ${roi >= 0 ? 'text-emerald' : 'text-rose'}`;
  document.getElementById('bt-sub-avg-odds').textContent = `Avg odds: ${(data.avg_odds || 0).toFixed(2)}`;

  // Render Table Breakdown
  const tbody = document.getElementById('bt-breakdown-tbody');
  tbody.innerHTML = '';
  const breakdown = data.market_breakdown || {};
  if (Object.keys(breakdown).length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No qualified bets in this dataset</td></tr>';
  } else {
    for (const [m, st] of Object.entries(breakdown)) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${m.toUpperCase()}</strong></td>
        <td>${st.bets}</td>
        <td>${st.wins}</td>
        <td>${st.hit_rate_pct}%</td>
        <td>${st.avg_odds}</td>
        <td class="${st.profit_units >= 0 ? 'text-emerald' : 'text-rose'}">${st.profit_units >= 0 ? '+' : ''}${st.profit_units} u</td>
        <td class="${st.roi_pct >= 0 ? 'text-emerald' : 'text-rose'}">${st.roi_pct >= 0 ? '+' : ''}${st.roi_pct}%</td>
      `;
      tbody.appendChild(tr);
    }
  }

  // Draw Equity Curve
  drawEquityChart(data.equity_curve || [0]);
}

function drawEquityChart(curve) {
  const canvas = document.getElementById('equity-chart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);

  if (curve.length < 2) return;

  const minVal = Math.min(0, ...curve);
  const maxVal = Math.max(0.1, ...curve);
  const range = maxVal - minVal || 1;

  const padding = 30;
  const plotW = w - padding * 2;
  const plotH = h - padding * 2;

  const getY = (v) => padding + plotH - ((v - minVal) / range) * plotH;
  const getX = (idx) => padding + (idx / (curve.length - 1)) * plotW;

  // Zero line
  const zeroY = getY(0);
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(padding, zeroY);
  ctx.lineTo(w - padding, zeroY);
  ctx.stroke();
  ctx.setLineDash([]);

  // Plot Curve
  ctx.beginPath();
  ctx.moveTo(getX(0), getY(curve[0]));
  for (let i = 1; i < curve.length; i++) {
    ctx.lineTo(getX(i), getY(curve[i]));
  }
  ctx.strokeStyle = curve[curve.length - 1] >= 0 ? '#10b981' : '#f43f5e';
  ctx.lineWidth = 3;
  ctx.stroke();

  // Draw end value label
  ctx.fillStyle = '#ffffff';
  ctx.font = '12px "JetBrains Mono"';
  ctx.fillText(`End: ${curve[curve.length - 1]} u`, w - padding - 70, getY(curve[curve.length - 1]) - 10);
}

// Monte Carlo Simulator
function initSimForm() {
  const form = document.getElementById('sim-form');
  if (!form) return;

  const probInput = document.getElementById('sim-prob');
  const oddsInput = document.getElementById('sim-odds');
  const evCalc = document.getElementById('sim-ev-calc');

  function updateEvCalc() {
    const p = parseFloat(probInput.value) || 0;
    const o = parseFloat(oddsInput.value) || 0;
    const e = p * o - 1.0;
    evCalc.textContent = `Calculated EV: ${e >= 0 ? '+' : ''}${(e * 100).toFixed(1)}%`;
    evCalc.className = e >= 0 ? 'text-emerald' : 'text-rose';
  }

  probInput?.addEventListener('input', updateEvCalc);
  oddsInput?.addEventListener('input', updateEvCalc);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-run-sim');
    btn.disabled = true;
    btn.textContent = '⏳ Simulating...';

    const payload = {
      bankroll: parseFloat(document.getElementById('sim-bankroll').value) || 1000,
      strategy: document.getElementById('sim-strategy').value,
      odds: parseFloat(document.getElementById('sim-odds').value) || 1.95,
      probability: parseFloat(document.getElementById('sim-prob').value) || 0.58,
      rounds: parseInt(document.getElementById('sim-rounds').value) || 250,
      iterations: parseInt(document.getElementById('sim-iterations').value) || 1000,
    };

    try {
      const res = await fetch('/api/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Simulation failed');
      const data = await res.json();
      renderSimResults(data, payload.bankroll);
    } catch (err) {
      showBanner(`Simulation error: ${err.message}`, true);
    } finally {
      btn.disabled = false;
      btn.textContent = '🎲 Run Simulation';
    }
  });
}

function renderSimResults(data, initialBank) {
  document.getElementById('sim-val-median').textContent = `$${(data.median || 0).toLocaleString()}`;
  document.getElementById('sim-val-p5').textContent = `$${(data.p5_worst || 0).toLocaleString()}`;
  document.getElementById('sim-val-p95').textContent = `$${(data.p95_best || 0).toLocaleString()}`;
  document.getElementById('sim-val-ruin').textContent = `${data.ruin_pct ?? 0}%`;

  drawSimTrajectories(data.sample_trajectories || [], initialBank);
}

function drawSimTrajectories(trajectories, initialBank) {
  const canvas = document.getElementById('sim-chart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);
  if (trajectories.length === 0) return;

  let allVals = [initialBank];
  trajectories.forEach(t => allVals.push(...t));
  const minVal = Math.min(...allVals);
  const maxVal = Math.max(...allVals);
  const range = maxVal - minVal || 1;

  const padding = 30;
  const plotW = w - padding * 2;
  const plotH = h - padding * 2;

  const getY = (v) => padding + plotH - ((v - minVal) / range) * plotH;
  const getX = (idx, len) => padding + (idx / (len - 1)) * plotW;

  // Baseline initial capital
  const initY = getY(initialBank);
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(padding, initY);
  ctx.lineTo(w - padding, initY);
  ctx.stroke();
  ctx.setLineDash([]);

  const colors = ['#10b981', '#06b6d4', '#3b82f6', '#a855f7', '#f59e0b'];

  trajectories.forEach((traj, i) => {
    ctx.beginPath();
    ctx.moveTo(getX(0, traj.length), getY(traj[0]));
    for (let j = 1; j < traj.length; j++) {
      ctx.lineTo(getX(j, traj.length), getY(traj[j]));
    }
    ctx.strokeStyle = colors[i % colors.length];
    ctx.lineWidth = 2;
    ctx.stroke();
  });
}

// Settings Form
function initSettingsForm() {
  const form = document.getElementById('settings-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-save-cfg');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    const payload = {
      data_source: document.getElementById('cfg-data-source').value,
      filters: {
        min_odds: Math.max(parseFloat(document.getElementById('cfg-min-odds').value) || 1.66, 1.66),
        min_ev: parseFloat(document.getElementById('cfg-min-ev').value) || 0.0,
        max_ah_abs_line: parseFloat(document.getElementById('cfg-max-ah').value) || 2.0,
      },
      markets: ['1x2', 'ah', 'ou', 'btts'],
      output: 'picks.json',
      tracking_unit: 1.0,
    };

    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Failed to save configuration');
      showBanner('✅ Configuration updated successfully!');
      loadConfig();
      loadPicks();
    } catch (err) {
      showBanner(`Save error: ${err.message}`, true);
    } finally {
      btn.disabled = false;
      btn.textContent = '💾 Save Configuration';
    }
  });
}
