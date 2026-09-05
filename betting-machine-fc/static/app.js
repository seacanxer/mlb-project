// FC Betting Machine — Web Dashboard Client Application

let activeMarketFilter = 'all';
let allPicksData = [];
let allMatchesData = [];
let currentConfig = null;

function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

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
  initParlay();

  loadConfig();
  loadPicks();
  loadMatches();
  loadTracker();
  initSettlement();
});

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[char]);
}

async function loadParlays(action = 'refresh') {
  const container = document.getElementById('parlay-container');
  const note = document.getElementById('parlay-source-note');
  const aiButton = document.getElementById('btn-ai-parlay');
  const frameworkButton = document.getElementById('btn-generate-parlay');
  if (!container) return;
  container.innerHTML = '<div class="card text-muted">Building validated slips…</div>';
  if (action === 'ai' && aiButton) {
    aiButton.disabled = true;
    aiButton.textContent = '⏳ AI generating…';
  }
  if (action === 'framework' && frameworkButton) frameworkButton.disabled = true;
  try {
    const url = action === 'ai' ? '/api/parlay-picks/generate-ai'
      : action === 'framework' ? '/api/parlay-picks/generate' : '/api/parlay-picks';
    const res = await fetch(url, { method: action === 'refresh' ? 'GET' : 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.ai_error || 'Failed to load parlay recommendations');
    renderParlays(data);
    renderParlayTracking(data.tracking || {});
    if (note) {
      const source = data.ai_status === 'reviewed'
        ? `AI-reviewed by ${data.ai_model || 'configured model'}`
        : data.ai_status === 'framework_fallback'
        ? 'AI response failed one or more framework gates — framework slips preserved'
        : data.ai_status === 'unavailable'
        ? 'AI unavailable — showing deterministic framework slips'
        : data.ai_status === 'not_configured'
        ? 'Framework mode — AI reviewer is not configured'
        : data.ai_status === 'framework' ? 'Framework parlay generated and tracked'
        : 'Framework mode — AI review has not been run';
      note.textContent = `${source} · ${Number(data.candidate_count || 0)} qualified candidates${data.reviewed_at ? ` · ${formatWibTimestamp(data.reviewed_at)}` : ''}`;
    }
    if (data.ai_status === 'unavailable' && data.ai_error) {
      showBanner(`AI review unavailable; framework slips preserved. ${data.ai_error}`, true);
    }
    if (action !== 'refresh') {
      const created = (data.saved || []).filter(item => item.created).length;
      showBanner(created ? `${created} parlay slip baru disimpan untuk settlement.` : 'Slip identik sudah tercatat; tidak dibuat duplikat.');
    }
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><h3>Parlay recommendations unavailable</h3><p>${escapeHtml(err.message)}</p></div>`;
  } finally {
    if (aiButton) {
      aiButton.disabled = false;
      aiButton.textContent = '✨ Generate AI Parlay';
    }
    if (frameworkButton) frameworkButton.disabled = false;
  }
}

function renderParlays(data) {
  const container = document.getElementById('parlay-container');
  if (!container) return;
  const tierIcons = { safe: '🛡️', recommended: '⭐', aggressive: '🔥' };
  container.innerHTML = (data.slips || []).map(slip => {
    const ready = ['ready', 'ready_with_fallback'].includes(slip.status);
    const source = slip.source === 'ai_reviewed' ? 'AI + Framework' : 'Framework';
    const legs = (slip.legs || []).map((leg, index) => `
      <div class="parlay-leg">
        <div class="parlay-leg-number">${index + 1}</div>
        <div class="parlay-leg-main">
          <strong>${escapeHtml(leg.pick)}</strong>
          <span>${escapeHtml(leg.match)}</span>
          <small>${escapeHtml(leg.league || 'Unknown league')} · ${formatKickoff(leg.start_ts)}</small>
        </div>
        <div class="parlay-leg-price">
          <strong>${Number(leg.odds || 0).toFixed(2)}</strong>
          <small>${String(leg.market || '').toUpperCase()}</small>
        </div>
      </div>
    `).join('');
    return `
      <article class="parlay-card parlay-${escapeHtml(slip.tier)} ${ready ? '' : 'parlay-incomplete'}">
        <div class="parlay-card-header">
          <div>
            <span class="parlay-tier-icon">${tierIcons[slip.tier] || '🧾'}</span>
            <h3>${escapeHtml(slip.label)}</h3>
          </div>
          <span class="parlay-source">${escapeHtml(source)}</span>
        </div>
        <div class="parlay-status ${ready ? 'ready' : 'incomplete'}">
          ${ready ? `${slip.leg_count}-leg slip (${slip.min_legs}-${slip.max_legs}) ready${slip.fallback_count ? ` · ${slip.fallback_count} controlled fill` : ''}` : `${slip.leg_count}/${slip.required_legs} qualified legs — no forced selection`}
        </div>
        <div class="parlay-legs">${legs || '<p class="text-muted">No candidate currently passes this tier.</p>'}</div>
        <div class="parlay-summary">
          <div><span>Combined Odds</span><strong>${slip.combined_odds ? Number(slip.combined_odds).toFixed(2) : '—'}</strong></div>
          <div><span>Market Implied</span><strong>${slip.market_implied_probability ? `${(Number(slip.market_implied_probability) * 100).toFixed(1)}%` : '—'}</strong></div>
          <div><span>Model Joint*</span><strong>${slip.model_joint_probability ? `${(Number(slip.model_joint_probability) * 100).toFixed(1)}%` : '—'}</strong></div>
        </div>
        <p class="parlay-rationale">${escapeHtml(slip.rationale)}</p>
      </article>
    `;
  }).join('') || '<div class="empty-state"><h3>No parlay slips available</h3><p>Run a live scan to populate qualified O/U and AH candidates.</p></div>';
}

function renderParlayTracking(tracking) {
  const summary = tracking.summary || {};
  const set = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
  set('parlay-pending', summary.pending || 0);
  set('parlay-settled', summary.settled || 0);
  set('parlay-record', `${summary.wins || 0}–${summary.losses || 0}`);
  set('parlay-pushes', `${summary.pushes || 0} pushes`);
  set('parlay-profit', `${Number(summary.profit_units || 0).toFixed(2)}u`);
  set('parlay-roi', `${Number(summary.roi_pct || 0).toFixed(1)}%`);
  window._parlaySlips = tracking.slips || [];
  const body = document.getElementById('parlay-history-body');
  if (!body) return;
  body.innerHTML = (tracking.slips || []).map(slip => `
    <tr>
      <td>${formatWibTimestamp(slip.generated_at)}</td>
      <td><strong>${escapeHtml(slip.label || slip.tier)}</strong><br><small>${slip.source === 'ai_reviewed' ? 'AI + Framework' : 'Framework'}</small></td>
      <td>${slip.leg_count || 0}</td>
      <td>${Number(slip.combined_odds || 0).toFixed(2)}</td>
      <td><span class="status-badge ${escapeHtml(slip.status)}">${escapeHtml(String(slip.status || '').toUpperCase())}</span></td>
      <td>${slip.profit == null ? '—' : `${Number(slip.profit).toFixed(2)}u`}</td>
      <td><button class="btn btn-secondary btn-sm" onclick="openParlayModal(${slip.id})">👁 View</button></td>
    </tr>`).join('') || '<tr><td colspan="7" class="text-muted">No generated parlays yet.</td></tr>';
}

function openParlayModal(slipId) {
  const slips = (window._parlaySlips || []);
  const slip = slips.find(s => s.id === slipId);
  if (!slip) return;
  document.getElementById('parlay-modal-title').textContent = `${slip.label || slip.tier} · ${slip.status.toUpperCase()}`;
  document.getElementById('parlay-modal-meta').textContent =
    `${formatWibTimestamp(slip.generated_at)} · ${slip.leg_count} legs · Combined ${Number(slip.combined_odds || 0).toFixed(2)}` +
    (slip.profit != null ? ` · Profit ${Number(slip.profit).toFixed(2)}u` : '');
  const body = document.getElementById('parlay-modal-legs');
  body.innerHTML = (slip.legs || []).map((leg, index) => `
    <tr>
      <td>${index + 1}</td>
      <td><strong>${escapeHtml(leg.match)}</strong><br><small>${escapeHtml(leg.league || 'Unknown league')} · ${formatKickoff(leg.start_ts)}</small></td>
      <td>${escapeHtml(leg.pick)}<br><small class="text-muted">${String(leg.market || '').toUpperCase()}</small></td>
      <td>${Number(leg.odds || 0).toFixed(2)}</td>
      <td>${leg.home_score != null ? `${leg.home_score}–${leg.away_score}` : '—'}</td>
      <td><span class="status-badge ${escapeHtml(leg.result || 'pending')}">${escapeHtml(String(leg.result || 'pending').toUpperCase())}</span></td>
    </tr>`).join('') || '<tr><td colspan="6" class="text-muted">No legs recorded.</td></tr>';
  document.getElementById('parlay-modal').classList.remove('hidden');
}

async function settleParlays() {
  const button = document.getElementById('btn-settle-parlay');
  if (button) { button.disabled = true; button.textContent = '⏳ Settling…'; }
  try {
    const start = await fetch('/api/parlay-settle', { method: 'POST' });
    if (!start.ok) throw new Error('Unable to start parlay settlement');
    for (let attempt = 0; attempt < 30; attempt += 1) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      const state = await fetch('/api/parlay-settle/status').then(response => response.json());
      if (!state.running) {
        if (state.last?.error) throw new Error(state.last.error);
        showBanner(`${state.last?.legs_settled_now || 0} parlay legs settled.`);
        await loadParlays('refresh');
        return;
      }
    }
    showBanner('Settlement masih berjalan. Refresh beberapa saat lagi.');
  } catch (err) {
    showBanner(`Parlay settlement failed: ${err.message}`, true);
  } finally {
    if (button) { button.disabled = false; button.textContent = '✅ Settle Parlays'; }
  }
}

function initParlay() {
  document.getElementById('btn-refresh-parlay')?.addEventListener('click', () => loadParlays('refresh'));
  document.getElementById('btn-generate-parlay')?.addEventListener('click', () => loadParlays('framework'));
  document.getElementById('btn-ai-parlay')?.addEventListener('click', () => loadParlays('ai'));
  document.getElementById('btn-settle-parlay')?.addEventListener('click', settleParlays);
  loadParlays('refresh');
}

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

    // Update odds floor display
    const minOdds = currentConfig.filters?.min_odds ?? 1.66;
    const display = document.getElementById('odds-floor-display');
    if (display) display.textContent = `≥ ${minOdds}`;
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
  document.getElementById('kpi-top-signals').textContent = summary.top_pick_count ?? 0;

  if (summary.last_scan_time) {
    document.getElementById('last-sync-text').textContent = `Terakhir scan berhasil: ${formatWibTimestamp(summary.last_scan_time)}`;
  } else {
    document.getElementById('last-sync-text').textContent = 'Terakhir scan berhasil: belum tercatat';
  }
}

function formatWibTimestamp(value) {
  if (!value) return 'belum tercatat';
  const d = new Date(value);
  if (isNaN(d.getTime())) return 'waktu tidak valid';
  return `${new Intl.DateTimeFormat('id-ID', {
    timeZone: 'Asia/Jakarta', day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(d)} WIB`;
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

    const signalLabel = p.is_top_pick ? '🔥 TOP PICK' : '✅ OFFICIAL';
    const signalClass = p.is_top_pick ? 'top-pick-badge' : 'official-badge';
    card.classList.toggle('top-pick-card', Boolean(p.is_top_pick));
    card.innerHTML = `
      <div>
        <div class="pick-card-header"><span class="market-badge ${marketClass}">${p.market ? p.market.toUpperCase() : 'BET'}</span><span class="${signalClass}">${signalLabel}</span></div>
        <div class="match-title">${p.match || 'Match'}</div>
        <div class="pick-meta">${p.league || 'Football League'} · ${p.formula_version || 'legacy'}</div>
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
  const dateStr = d.toLocaleDateString('en-GB', { timeZone: 'Asia/Jakarta', day: '2-digit', month: 'short', year: 'numeric' });
  const timeStr = d.toLocaleTimeString('en-GB', { timeZone: 'Asia/Jakarta', hour: '2-digit', minute: '2-digit', hour12: false });
  return `🗓️ ${dateStr} · ${timeStr} WIB`;
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
    document.getElementById('tracker-live').textContent = s.live_picks ?? 0;
    document.getElementById('tracker-overdue').textContent = s.overdue_picks ?? 0;
    document.getElementById('tracker-record').textContent = `${s.wins || 0}–${s.losses || 0}`;
    document.getElementById('tracker-pushes').textContent = `${s.pushes || 0} pushes`;
    document.getElementById('tracker-profit').textContent = `${(s.profit_units || 0).toFixed(2)}u`;
    document.getElementById('tracker-roi').textContent = `${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%`;
    const dedupNote = document.getElementById('tracker-dedup-note');
    if (dedupNote) {
      const hidden = Number(s.duplicates_hidden || 0);
      dedupNote.textContent = hidden ? `${hidden} duplicate historis disembunyikan` : 'Tidak ada duplicate';
    }
    const trackerLastScan = document.getElementById('tracker-last-scan');
    if (trackerLastScan) {
      trackerLastScan.textContent = `Terakhir scan data berhasil: ${formatWibTimestamp(data.last_successful_scan_time)}`;
    }

    const counts = data.status_counts || {};
    const totalStatuses = ['locked', 'live', 'overdue', 'settled']
      .reduce((sum, status) => sum + Number(counts[status] || 0), 0);
    document.getElementById('tracker-count-all').textContent = totalStatuses;
    ['locked', 'live', 'overdue', 'settled'].forEach((status) => {
      const el = document.getElementById(`tracker-count-${status}`);
      if (el) el.textContent = Number(counts[status] || 0);
    });

    trackerData = data;
    renderTracker();
    renderMarketPerformance();
  } catch (err) {
    showBanner(err.message, true);
  }
}

let marketSortDir = 'asc';
let trackerData = { locked: [], live: [], overdue: [], settled: [] };
let trackerStatusView = 'all';

function renderTracker() {
  const marketFilter = document.getElementById('tracker-filter-market')?.value || 'all';
  const sortVal = document.getElementById('tracker-sort')?.value || 'date_desc';

  const statuses = ['locked', 'live', 'overdue', 'settled'];
  let rows = trackerStatusView === 'all'
    ? statuses.flatMap(status => trackerData[status] || [])
    : [...(trackerData[trackerStatusView] || [])];

  if (marketFilter !== 'all') {
    rows = rows.filter(b => (b.market || '').toLowerCase() === marketFilter.toLowerCase());
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
    const kickoff = b.start_ts ? new Date(Number(b.start_ts) * 1000) : null;
    const dateText = kickoff && !isNaN(kickoff.getTime())
      ? kickoff.toLocaleDateString('id-ID', { timeZone: 'Asia/Jakarta', day: '2-digit', month: 'short', year: 'numeric' })
      : '-';
    const timeText = kickoff && !isNaN(kickoff.getTime())
      ? `${kickoff.toLocaleTimeString('id-ID', { timeZone: 'Asia/Jakarta', hour: '2-digit', minute: '2-digit', hour12: false })} WIB`
      : 'Jam tidak tersedia';
    const pendingLabels = {
      locked: ['Locked · belum mulai', 'status-upcoming'],
      live: ['Live / menunggu final', 'status-awaiting'],
      overdue: ['Overdue · settlement pending', 'status-overdue'],
    };
    const status = b.settlement_status || b.timing_status || (b.settled ? 'settled' : 'locked');
    const pending = pendingLabels[status] || ['Settlement pending', 'status-awaiting'];
    const result = b.settled
      ? (b.won === 1 ? 'Won' : b.won === 0 ? 'Lost' : 'Push')
      : pending[0];
    const resultClass = b.settled ? (b.won === 1 ? 'status-won' : b.won === 0 ? 'status-lost' : 'status-push') : pending[1];
    const hasScore = Number.isInteger(Number(b.home_score)) && Number.isInteger(Number(b.away_score)) && b.home_score !== null && b.away_score !== null;
    const scoreLabel = b.score_status === 'live' ? 'LIVE' : b.score_status === 'final' ? 'FINAL' : '';
    const score = hasScore
      ? `<strong>${Number(b.home_score)}–${Number(b.away_score)}</strong>${scoreLabel ? `<div class="score-status">${scoreLabel}</div>` : ''}`
      : '<span class="text-muted">Belum tersedia</span>';
    const league = (b.league || '-').trim() || '-';
    const statusLabels = { locked: '🔒 Locked', live: '🔴 Live', overdue: '⏳ Overdue', settled: '✅ Settled' };
    return `<tr><td><span class="tracker-status ${resultClass}">${statusLabels[status] || status}</span></td><td><div class="kickoff-date">${dateText}</div><div class="kickoff-time">${timeText}</div></td><td>${b.match || '-'}</td><td><span class="league-badge">${league}</span></td><td>${score}</td><td>${(b.market || '').toUpperCase()}</td><td>${b.pick || '-'}</td><td>${Number(b.odds || 0).toFixed(2)}</td><td><span class="tracker-status ${resultClass}">${result}</span>${b.settled ? ` <span class="tracker-profit-inline">(${Number(b.profit || 0).toFixed(2)}u)</span>` : ''}</td></tr>`;
  }).join('') : `<tr><td colspan="9" class="text-center text-muted">No ${trackerStatusView === 'all' ? '' : trackerStatusView + ' '}picks found.</td></tr>`;
}

function renderMarketPerformance() {
  const tbody = document.getElementById('tracker-market-performance');
  if (!tbody) return;
  const rows = trackerData.market_performance || [];
  tbody.innerHTML = rows.length ? rows.map((row) => {
    const roi = Number(row.roi_pct || 0);
    const profit = Number(row.profit_units || 0);
    return `<tr>
      <td><strong>${String(row.market || '').toUpperCase()}</strong></td>
      <td>${row.bets || 0}</td>
      <td>${row.wins || 0}–${row.losses || 0}–${row.pushes || 0}</td>
      <td class="text-emerald">${Number(row.win_rate_pct || 0).toFixed(1)}%</td>
      <td class="text-rose">${Number(row.loss_rate_pct || 0).toFixed(1)}%</td>
      <td class="${profit >= 0 ? 'text-emerald' : 'text-rose'}">${profit >= 0 ? '+' : ''}${profit.toFixed(2)}u</td>
      <td class="${roi >= 0 ? 'text-emerald' : 'text-rose'}">${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%</td>
    </tr>`;
  }).join('') : '<tr><td colspan="7" class="text-center text-muted">Belum ada settlement untuk dihitung.</td></tr>';
}

function setTrackerView(view) {
  const showMarkets = view === 'markets';
  if (!showMarkets) trackerStatusView = view;
  document.getElementById('tracker-picks-panel')?.classList.toggle('hidden', showMarkets);
  document.getElementById('tracker-markets-panel')?.classList.toggle('hidden', !showMarkets);
  const marketsBtn = document.getElementById('tracker-view-markets');
  marketsBtn?.classList.toggle('active', showMarkets);
  marketsBtn?.setAttribute('aria-selected', String(showMarkets));
  document.querySelectorAll('.tracker-status-view').forEach((button) => {
    const active = !showMarkets && button.dataset.trackerView === trackerStatusView;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
  });
  const titles = { all: 'All Settlement Statuses', locked: 'Locked Picks', live: 'Live Matches', overdue: 'Overdue Settlements', settled: 'Settled Results' };
  const title = document.getElementById('tracker-view-title');
  if (title) title.textContent = titles[trackerStatusView] || 'Settlement Tracker';
  if (!showMarkets) renderTracker();
}

function initTrackerFilters() {
  console.log('initTrackerFilters called');
  const btns = document.querySelectorAll('.tracker-status-view');
  console.log('Found tracker buttons:', btns.length);
  btns.forEach((button) => {
    button.addEventListener('click', (e) => {
      console.log('Tracker view clicked:', button.dataset.trackerView);
      e.preventDefault();
      setTrackerView(button.dataset.trackerView || 'all');
    });
  });
  const marketsBtn = document.getElementById('tracker-view-markets');
  if (marketsBtn) {
    marketsBtn.addEventListener('click', (e) => {
      console.log('Markets view clicked');
      e.preventDefault();
      setTrackerView('markets');
    });
  } else {
    console.warn('tracker-view-markets not found');
  }
  document.getElementById('tracker-filter-market')?.addEventListener('change', () => {
    console.log('Market filter changed');
    renderTracker();
  });
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
  console.log('initTrackerFilters done');
}

let isSettling = false;
function initSettlement() {
  const run = async () => {
    if (isSettling) return;
    isSettling = true;
    document.getElementById('btn-settle')?.setAttribute('disabled','');
    document.getElementById('btn-settle-tracker')?.setAttribute('disabled','');
    try {
      const res = await fetch('/api/settle', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Settlement failed');
      if (data.status === 'busy') {
        showBanner('Settlement already running — tracker will update when done.', true);
        return;
      }
      showBanner('Settlement running… tracker updates when done.');
      const deadline = Date.now() + 300000; // 5 min cap
      let state = data.state || {};
      while (state.running && Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 3000));
        const sr = await fetch('/api/settle/status');
        state = await sr.json();
      }
      const last = state.last || {};
      if (last.error) throw new Error(last.error);
      showBanner(`✅ Settlement refreshed: ${last.settled_now || 0} picks updated${last.rechecked ? ` · ${last.rechecked} rechecked` : ''}.`);
      await loadTracker();
    } catch (err) {
      showBanner(err.message, true);
    } finally {
      isSettling = false;
      document.getElementById('btn-settle')?.removeAttribute('disabled');
      document.getElementById('btn-settle-tracker')?.removeAttribute('disabled');
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
  document.getElementById('filter-max-odds')?.addEventListener('input', debounce(loadPicks, 400));
  document.getElementById('filter-search')?.addEventListener('input', debounce(renderPicks, 200));
}

// Live Scanner Integration
let _scanPoll = null;
function initScanButton() {
  const btn = document.getElementById('btn-scan');
  const spinner = document.getElementById('scan-spinner');
  const btnText = document.getElementById('scan-btn-text');

  btn.addEventListener('click', async () => {
    if (_scanPoll) return;
    btn.disabled = true;
    spinner.classList.remove('hidden');
    btnText.textContent = 'Scanning 1xbit LineFeed...';
    showBanner('Triggered live scan on 1xbit LineFeed. Scraping live match odds...');

    try {
      const res = await fetch('/api/scan', { method: 'POST' });
      const data = await res.json();

      // Poll status
      _scanPoll = setInterval(async () => {
        try {
          const statusRes = await fetch('/api/scan/status');
          const state = await statusRes.json();
          if (!state.is_running) {
            clearInterval(_scanPoll); _scanPoll = null;
            btn.disabled = false;
            spinner.classList.add('hidden');
            btnText.textContent = '📡 Run Live Scan';

            if (state.error) {
              showBanner(`Scan failed: ${state.error}`, true);
            } else {
              const diag = state.diagnostics || {};
              const coverage = `full ${diag.full || 0}, shadow ${diag.shadow || 0}, blocked ${diag.blocked || 0}, market-only ${diag.market_only || 0}`;
              const warning = (diag.errors || []).length ? `, ${(diag.errors || []).length} processing errors logged` : '';
              showBanner(`✅ Scan complete! ${state.last_scan_count} matches, ${state.last_scan_picks} Official Picks (${coverage}${warning}).`);
              loadPicks();
              loadMatches();
              loadParlays(false);
            }
          } else {
            showBanner(state.progress || 'Scanning active matches...');
          }
        } catch (e) {
          clearInterval(_scanPoll); _scanPoll = null;
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
  document.getElementById('btn-close-parlay-modal')?.addEventListener('click', () => {
    document.getElementById('parlay-modal').classList.add('hidden');
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
      const fairOdds = p.fair_odds ? Number(p.fair_odds).toFixed(3) : (p.probability > 0 ? (1.0 / p.probability).toFixed(3) : '-');
      const status = (p.selection_status || 'shadow').replace('_', ' ').toUpperCase();
      tr.innerHTML = `
        <td><strong>${p.pick}</strong> (${p.market.toUpperCase()})<br><small class="text-muted">${status} · ${p.lambda_source || 'unknown source'}</small></td>
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
      markets: ['ah', 'ou'],
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
