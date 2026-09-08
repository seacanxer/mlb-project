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
          <div><span>All legs profit*</span><strong>${slip.model_joint_probability ? `${(Number(slip.model_joint_probability) * 100).toFixed(1)}%` : '—'}</strong></div>
        </div>
        <p class="parlay-rationale">${escapeHtml(slip.rationale)}</p>
        <p class="text-muted">*Uncalibrated estimate assuming independence. Pushes and half outcomes mean this is not the chance of a profitable slip. No fill below tier thresholds.</p>
      </article>
    `;
  }).join('') || '<div class="empty-state"><h3>No parlay slips available</h3><p>Run a live scan to populate qualified O/U and AH candidates.</p></div>';
}

function renderParlayTracking(tracking) {
  const summary = tracking.summary || {};
  window._parlayTracking = tracking;
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
  const slips = window._parlaySlips || [];
  const showAll = window._parlayShowAll === true;
  const visible = showAll ? slips : slips.slice(0, 5);
  body.innerHTML = visible.map(slip => `
    <tr>
      <td>${formatWibTimestamp(slip.generated_at)}</td>
      <td><strong>${escapeHtml(slip.label || slip.tier)}</strong><br><small>${slip.source === 'ai_reviewed' ? 'AI + Framework' : 'Framework'}</small></td>
      <td>${slip.leg_count || 0}</td>
      <td>${Number(slip.combined_odds || 0).toFixed(2)}</td>
      <td><span class="status-badge ${escapeHtml(slip.status)}">${escapeHtml(String(slip.status || '').toUpperCase())}</span></td>
      <td>${slip.profit == null ? '—' : `${Number(slip.profit).toFixed(2)}u`}</td>
      <td><button class="btn btn-secondary btn-sm" onclick="openParlayModal(${slip.id})">👁 View</button></td>
    </tr>`).join('') || '<tr><td colspan="7" class="text-muted">No generated parlays yet.</td></tr>';
  const seeMore = document.getElementById('btn-parlay-see-more');
  if (seeMore) {
    const hidden = slips.length - visible.length;
    seeMore.style.display = slips.length > 5 ? 'inline-block' : 'none';
    seeMore.textContent = showAll ? 'Tutup' : `Lihat semua parlay (${slips.length})`;
  }
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

async function lockParlay() {
  const button = document.getElementById('btn-lock-parlay');
  if (button) { button.disabled = true; button.textContent = '⏳ Locking…'; }
  try {
    const res = await fetch('/api/parlay-picks/lock', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to lock parlay');
    const created = (data.saved || []).filter(item => item.created).length;
    showBanner(created ? `${created} parlay slip locked.` : 'Slip already locked (duplicate match-set).');
    await loadParlays('refresh');
  } catch (err) {
    showBanner(`Lock failed: ${err.message}`, true);
  } finally {
    if (button) { button.disabled = false; button.textContent = '🔒 Lock Parlay'; }
  }
}

function initParlay() {
  document.getElementById('btn-refresh-parlay')?.addEventListener('click', () => loadParlays('refresh'));
  document.getElementById('btn-generate-parlay')?.addEventListener('click', () => loadParlays('framework'));
  document.getElementById('btn-ai-parlay')?.addEventListener('click', () => loadParlays('ai'));
  document.getElementById('btn-lock-parlay')?.addEventListener('click', lockParlay);
  document.getElementById('btn-settle-parlay')?.addEventListener('click', settleParlays);
  document.getElementById('btn-parlay-see-more')?.addEventListener('click', () => {
    window._parlayShowAll = !(window._parlayShowAll === true);
    if (window._parlayTracking) renderParlayTracking(window._parlayTracking);
  });
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
    document.getElementById('cfg-min-odds').value = currentConfig.filters?.min_odds ?? 1.50;
    document.getElementById('cfg-min-ev').value = currentConfig.filters?.min_ev ?? 0.0;
    document.getElementById('cfg-max-ah').value = currentConfig.filters?.max_ah_abs_line ?? 1.5;

    // Update odds floor display
    const minOdds = currentConfig.filters?.min_odds ?? 1.50;
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

    const cfgOdds = currentConfig?.filters?.min_odds ?? 1.50;
    let url = `/api/picks?min_odds=${cfgOdds}&min_ev=${minEv}&sort_by=${sortBy}&sort_order=desc&limit=200`;
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

    const tier = p.tier || (p.is_top_pick ? 'top_pick' : (p.is_watch ? 'watch' : 'official'));
    const signalLabel = tier === 'top_pick' ? '🔥 TOP PICK' : (tier === 'watch' ? '👁 WATCH' : '✅ OFFICIAL');
    const signalClass = tier === 'top_pick' ? 'top-pick-badge' : (tier === 'watch' ? 'watch-badge' : 'official-badge');
    card.classList.toggle('top-pick-card', tier === 'top_pick');
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

let trackerDateFilter = null;

async function loadTracker() {
  try {
    const dateVal = document.getElementById('tracker-date-filter')?.value;
    let url = '/api/tracker';
    if (dateVal) {
      url += `?date=${dateVal}`;
    }
    const res = await fetch(url);
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
    renderDailySummary(data.daily_summary || null);
    renderMarketPerformance();
    loadKpiFeedback();
    loadCrosscheck();
  } catch (err) {
    showBanner(err.message, true);
  }
}

function renderDailySummary(daily) {
  const dateEl = document.getElementById('daily-summary-date');
  const settledEl = document.getElementById('daily-summary-settled');
  const winsEl = document.getElementById('daily-summary-wins');
  const lossesEl = document.getElementById('daily-summary-losses');
  const pushesEl = document.getElementById('daily-summary-pushes');
  const profitEl = document.getElementById('daily-summary-profit');
  const winrateEl = document.getElementById('daily-summary-winrate');
  const roiEl = document.getElementById('daily-summary-roi');
  if (!daily || !daily.date) {
    dateEl.textContent = 'No filter';
    settledEl.textContent = '0';
    winsEl.textContent = '0';
    lossesEl.textContent = '0';
    pushesEl.textContent = '0';
    profitEl.textContent = '0.00u';
    if (winrateEl) winrateEl.textContent = '0.0%';
    if (roiEl) roiEl.textContent = '0.0%';
    return;
  }
  dateEl.textContent = daily.date;
  const settled = daily.settled || 0;
  const wins = daily.wins || 0;
  const losses = daily.losses || 0;
  const pushes = daily.pushes || 0;
  const profit = daily.profit_units || 0;
  settledEl.textContent = settled;
  winsEl.textContent = wins;
  lossesEl.textContent = losses;
  pushesEl.textContent = pushes;
  profitEl.textContent = `${profit >= 0 ? '+' : ''}${profit.toFixed(2)}u`;
  profitEl.className = `kpi-val ${profit >= 0 ? 'text-emerald' : 'text-rose'}`;
  const decided = wins + losses;
  const winRate = decided > 0 ? (wins / decided * 100) : 0;
  if (winrateEl) winrateEl.textContent = winRate.toFixed(1) + '%';
  const roi = settled > 0 ? (profit / settled * 100) : 0;
  if (roiEl) {
    roiEl.textContent = (roi >= 0 ? '+' : '') + roi.toFixed(1) + '%';
    roiEl.className = `kpi-val ${roi >= 0 ? 'text-emerald' : 'text-rose'}`;
  }
}

async function loadKpiFeedback() {
  const tbody = document.getElementById('kpi-feedback-rows');
  try {
    const res = await fetch('/api/kpis/coverage');
    if (!res.ok) throw new Error('kpi fetch failed');
    const data = await res.json();
    const rows = (data.rows || []).slice(0, 50);
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">Belum ada data KPI.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => {
      const rec = `${r.wins}-${r.losses}${r.pushes ? '-' + r.pushes : ''}`;
      const roi = r.roi_pct || 0;
      const cls = roi >= 0 ? 'text-emerald' : 'text-rose';
      return `<tr>
        <td>${r.coverage}</td>
        <td>${r.market || '-'}</td>
        <td>${r.odds_band || '-'}</td>
        <td>${r.settled}</td>
        <td>${rec}</td>
        <td>${((r.win_rate || 0) * 100).toFixed(1)}%</td>
        <td>${(r.profit || 0).toFixed(2)}u</td>
        <td class="${cls}">${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%</td>
      </tr>`;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">Error: ${err.message}</td></tr>`;
  }
}

async function loadCrosscheck() {
  const tbody = document.getElementById('crosscheck-rows');
  const meta = document.getElementById('crosscheck-meta');
  try {
    const res = await fetch('/api/crosscheck?limit=30');
    if (!res.ok) throw new Error('crosscheck fetch failed');
    const data = await res.json();
    const rows = data.results || data.rows || data.board || [];
    const counts = data.summary || {};
    if (meta) meta.textContent = `Agree: ${counts.agree ?? '-'} · Disagree: ${counts.disagree ?? '-'} · No FS: ${counts.no_fs ?? '-'} · Generated ${data.generated_at || '-'}`;
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">Belum ada data cross-check.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => {
      const verdict = (r.verdict || 'no_fs').toLowerCase();
      const rec = r.recommendation || {};
      const cls = verdict === 'agree' ? 'text-emerald' : verdict === 'disagree' ? 'text-rose' : 'text-muted';
      const label = verdict === 'agree' ? '✅ Agree' : verdict === 'disagree' ? '⚠️ Disagree' : '—';
      return `<tr>
        <td><strong>${r.home || r.match || ''} vs ${r.away || ''}</strong></td>
        <td class="text-muted small">${r.league || ''}</td>
        <td>${r.fs_ou_line ?? '-'}</td>
        <td>${r.fs_ou_over_odds ?? '-'}</td>
        <td>${r.xbit_ou_over_odds ?? rec.odds ?? '-'}</td>
        <td>${r.fs_ah_line ?? '-'}</td>
        <td>${r.xbit_ah_line ?? '-'}</td>
        <td class="${cls}">${label}</td>
      </tr>`;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">Error: ${err.message}</td></tr>`;
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

  // Date filter
  const dateInput = document.getElementById('tracker-date-filter');
  if (dateInput) {
    dateInput.addEventListener('change', () => {
      loadTracker();
    });
  }
  const todayBtn = document.getElementById('btn-tracker-today');
  if (todayBtn) {
    todayBtn.addEventListener('click', () => {
      const now = new Date();
      const year = now.getFullYear();
      const month = String(now.getMonth() + 1).padStart(2, '0');
      const day = String(now.getDate()).padStart(2, '0');
      dateInput.value = `${year}-${month}-${day}`;
      loadTracker();
    });
  }
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
  const auditEl = document.getElementById('modal-quality-note');
  if (auditEl) auditEl.textContent = `${m.model?.formula_version || 'Unknown version'} · ${m.model?.lambda_source || 'Unknown source'} · ${m.model?.coverage_status || 'Unknown coverage'} · Uncalibrated estimate. EV stress uses ±10% scoring-rate scenarios, not a confidence interval.`;
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

    const picks = m.qualified_picks || [];
  if (picks.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No picks meeting positive EV threshold for this match</td></tr>';
  } else {
    picks.forEach(p => {
      const tr = document.createElement('tr');
      const fairOdds = p.fair_odds ? Number(p.fair_odds).toFixed(3) : '—';
      const status = (p.selection_status || 'shadow').replace('_', ' ').toUpperCase();
      tr.innerHTML = `
        <td><strong>${p.pick}</strong> (${p.market.toUpperCase()})<br><small class="text-muted">${status} · ${p.lambda_source || 'unknown source'}</small></td>
        <td>${(p.probability * 100).toFixed(1)}%</td>
        <td>${fairOdds}</td>
        <td><strong>${p.odds.toFixed(3)}</strong></td>
        <td class="text-emerald font-bold">${(p.ev * 100).toFixed(1)}%<br><small>Stress: ${(p.stress_ev * 100).toFixed(1)}%</small></td>
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
        min_odds: Math.max(parseFloat(document.getElementById('cfg-min-odds').value) || 1.50, 1.50),
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


// ---------------------------------------------------------------------------
// Market Intel (PRD v2) — texas-style board
// ---------------------------------------------------------------------------
let allIntel = [];

function wib(ts) {
  if (!ts) return '-';
  const d = new Date(ts * 1000);
  return d.toLocaleString('en-GB', { timeZone: 'Asia/Jakarta', hour12: false, weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function intelDecisionBadge(decision) {
  const colorMap = {
    'BET': 'badge-green', 'WATCH': 'badge-amber', 'SHADOW': 'badge-blue',
    'NO BET': 'badge-gray', 'UNSUPPORTED': 'badge-red',
  };
  return `<span class="badge ${colorMap[decision] || 'badge-gray'}">${decision}</span>`;
}

function mvtBadge(pct) {
  if (pct === null || pct === undefined) return '<span class="text-muted">—</span>';
  const dir = pct > 0 ? '↑' : (pct < 0 ? '↓' : '→');
  const color = pct > 0 ? '#ef4444' : (pct < 0 ? '#22c55e' : '#9ca3af');
  return `<span style="color:${color}">${dir} ${Math.abs(pct).toFixed(2)}%</span>`;
}

function populateIntelDecisionFilter(items) {
  const sel = document.getElementById('intel-filter-decision');
  if (!sel) return;
  const current = sel.value;
  const counts = {};
  items.forEach(i => { const d = i.decision || 'NO BET'; counts[d] = (counts[d] || 0) + 1; });
  const order = ['BET', 'WATCH', 'SHADOW', 'NO BET', 'UNSUPPORTED'];
  const keys = Object.keys(counts).sort((a, b) => {
    const ia = order.indexOf(a), ib = order.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
  sel.innerHTML = '<option value="all">All Decisions</option>' + keys.map(k =>
    `<option value="${k}">${k} (${counts[k]})</option>`).join('');
  sel.value = current;
}

async function loadIntel() {
  const decision = document.getElementById('intel-filter-decision')?.value || 'all';
  const league = document.getElementById('intel-filter-league')?.value || 'all';
  const search = (document.getElementById('intel-filter-search')?.value || '').trim().toLowerCase();
  let url = '/api/intel?limit=2000';
  if (decision && decision !== 'all') url += `&decision=${encodeURIComponent(decision)}`;
  if (league && league !== 'all') url += `&league=${encodeURIComponent(league)}`;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error('intel fetch failed');
    const data = await res.json();
    allIntel = data.board || [];
    if (search) allIntel = allIntel.filter(i => (i.home + ' ' + i.away + ' ' + (i.league||'')).toLowerCase().includes(search));
    const w = { 'BET': 0, 'WATCH': 1, 'SHADOW': 2, 'NO BET': 3, 'UNSUPPORTED': 4 };
    allIntel.sort((a, b) => (w[a.decision] ?? 9) - (w[b.decision] ?? 9));
    const meta = document.getElementById('intel-meta');
    if (meta) {
      const gen = data.generated_at ? new Date(data.generated_at).toLocaleString('en-GB', { timeZone: 'Asia/Jakarta' }) : '-';
      meta.textContent = `Board: ${data.count} matches · Generated ${gen} · Single-bookmaker reference (WATCH/SHADOW max)`;
    }
    populateIntelLeagueFilter(allIntel);
    populateIntelDecisionFilter(allIntel);
    renderIntel();
  } catch (err) {
    console.error('intel error', err);
    document.getElementById('intel-tbody').innerHTML = `<tr><td colspan="11" class="text-muted">Error loading intel board: ${err.message}</td></tr>`;
  }
}

function populateIntelLeagueFilter(items) {
  const sel = document.getElementById('intel-filter-league');
  if (!sel) return;
  const current = sel.value;
  const leagues = [...new Set(items.map(i => i.league).filter(Boolean))].sort();
  sel.innerHTML = '<option value="all">All Leagues</option>' + leagues.map(l => `<option value="${l}">${l}</option>`).join('');
  sel.value = current;
}

function renderIntel() {
  const tbody = document.getElementById('intel-tbody');
  const empty = document.getElementById('intel-empty');
  if (!allIntel.length) {
    tbody.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  tbody.innerHTML = allIntel.map(i => {
    const ou = i.main_ou || {};
    const ah = i.main_ah || {};
    const rec = i.recommendation || {};
    const mov = ou.over_mvt_pct !== undefined ? `${mvtBadge(ou.over_mvt_pct)} / ${mvtBadge(ou.under_mvt_pct)}` : '<span class="text-muted">—</span>';
    return `<tr>
      <td>${wib(i.start_ts)}</td>
      <td class="text-muted small">${i.league || '-'}</td>
      <td><strong>${i.home} vs ${i.away}</strong></td>
      <td>${i.lambdas?.total ?? '-'}</td>
      <td>${ou.line != null ? `O/U ${ou.line} (${ou.over_odds}/${ou.under_odds})` : '-'}</td>
      <td>${mov}</td>
      <td>${ah.home_line != null ? `AH ${ah.home_line} @ ${ah.home_odds}` : '-'}</td>
      <td>${rec.pick ? `${rec.pick} @ ${rec.odds} (EV ${(rec.ev*100).toFixed(1)}%)` : '<span class="text-muted">—</span>'}</td>
      <td>${intelDecisionBadge(i.decision)}</td>
      <td class="small text-muted">${i.decide_reason || ''}</td>
      <td><button class="btn btn-sm" onclick="openIntelModal('${i.match_id}')">View</button></td>
    </tr>`;
  }).join('');
}

async function openIntelModal(matchId) {
  try {
    const res = await fetch(`/api/intel/match/${encodeURIComponent(matchId)}`);
    if (!res.ok) throw new Error('detail fetch failed');
    const i = await res.json();
    const ctx = i.context || [];
    const history = i.history || [];
    const ctxHtml = ctx.length ? ctx.map(c => `<div class="intel-note"><strong>${c.confidence}</strong> — ${c.note}<br><span class="text-muted small">${c.source||'no source'} · ${c.author||'?'} · ${c.created_at||''}</span></div>`).join('') : '<p class="text-muted">Belum ada context.</p>';
    const histHtml = history.length ? history.slice(-8).map(h => `<div class="text-muted small">${h.observed_at} · ${h.market} ${h.line} ${h.side} @ ${h.odds}</div>`).join('') : '<p class="text-muted">Belum ada snapshot.</p>';
    const html = `
      <div class="intel-detail">
        <h3>${i.home} vs ${i.away} <span class="text-muted">(${i.league})</span></h3>
        <p>Kickoff: ${wib(i.start_ts)} WIB · Coverage: <strong>${i.coverage}</strong> (${i.data_grade})</p>
        <div class="kpi-grid small">
          <div class="kpi-card"><div class="kpi-label">Model</div><div class="kpi-val">${i.lambdas?.total}</div><div class="kpi-sub">Total goals</div></div>
          <div class="kpi-card"><div class="kpi-label">Home</div><div class="kpi-val">${i.lambdas?.home}</div><div class="kpi-sub">λ home</div></div>
          <div class="kpi-card"><div class="kpi-label">Away</div><div class="kpi-val">${i.lambdas?.away}</div><div class="kpi-sub">λ away</div></div>
          <div class="kpi-card"><div class="kpi-label">1X2</div><div class="kpi-val small">${(i.probs?.home*100).toFixed(0)}/${(i.probs?.draw*100).toFixed(0)}/${(i.probs?.away*100).toFixed(0)}</div><div class="kpi-sub">H/D/A %</div></div>
        </div>
        <h4>Rekomendasi</h4>
        ${i.recommendation ? `<p><strong>${i.recommendation.pick}</strong> @ ${i.recommendation.odds} · EV ${(i.recommendation.ev*100).toFixed(1)}% · prob ${(i.recommendation.prob*100).toFixed(0)}%</p>` : '<p class="text-muted">Tidak ada line defensif memenuhi gate.</p>'}
        ${intelDecisionBadge(i.decision)} <span class="text-muted small">${i.decide_reason}</span>
        <h4>Odds Movement (snapshot terakhir)</h4>
        <div class="intel-hist">${histHtml}</div>
        <h4>Context</h4>
        <div class="intel-notes">${ctxHtml}</div>
        <div class="intel-add-note">
          <textarea id="intel-note-text" class="form-input" placeholder="Tambah context: lineup, absensi, motivasi, dll."></textarea>
          <button class="btn btn-sm" onclick="addIntelNote('${i.match_id}')">Simpan Context</button>
        </div>
      </div>`;
    const modal = document.getElementById('match-modal');
    const body = modal.querySelector('.modal-card');
    body.innerHTML = `<div class="modal-header"><h2>Market Intel</h2><button id="btn-close-modal" class="modal-close-btn">&times;</button></div>` + html;
    modal.classList.remove('hidden');
    document.getElementById('btn-close-modal')?.addEventListener('click', () => modal.classList.add('hidden'));
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.add('hidden'); });
  } catch (err) {
    console.error('intel modal error', err);
    showBanner('Error buka detail: ' + err.message, true);
  }
}

async function addIntelNote(matchId) {
  const text = document.getElementById('intel-note-text')?.value?.trim();
  if (!text) { showBanner('Isi note dulu', true); return; }
  try {
    const res = await fetch('/api/intel/context', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ match_id: matchId, note: text, source: 'manual', confidence: 'medium', author: 'Tuan' }),
    });
    if (!res.ok) throw new Error('context save failed');
    showBanner('✅ Context tersimpan');
    loadIntel();
    openIntelModal(matchId);
  } catch (err) {
    showBanner('Error simpan context: ' + err.message, true);
  }
}

function initIntelTab() {
  document.getElementById('btn-refresh-intel')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-refresh-intel');
    btn.disabled = true;
    btn.textContent = 'Scanning...';
    try {
      const res = await fetch('/api/intel/refresh', { method: 'POST' });
      if (!res.ok) throw new Error('refresh trigger failed');
      showBanner('📡 Intel scan dimulai...');
      let tries = 0;
      const t = setInterval(async () => {
        tries++;
        const s = await (await fetch('/api/intel/status')).json();
        if (!s.running || tries > 120) {
          clearInterval(t);
          btn.disabled = false;
          btn.textContent = '↻ Refresh';
          if (s.error) showBanner('Intel scan error: ' + s.error, true);
          else showBanner('✅ Intel board selesai di-refresh');
          loadIntel();
        }
      }, 2500);
    } catch (err) {
      btn.disabled = false;
      btn.textContent = '↻ Refresh';
      showBanner('Gagal trigger intel scan: ' + err.message, true);
    }
  });
  document.getElementById('intel-filter-decision')?.addEventListener('change', loadIntel);
  document.getElementById('intel-filter-league')?.addEventListener('change', loadIntel);
  document.getElementById('intel-filter-search')?.addEventListener('input', debounce(loadIntel, 400));
}

// wire up tab loaders
const _origInitTabs = initTabs;
initTabs = function () {
  _origInitTabs();
  initIntelTab();
  initPrediction();
};

// ============================================================================
// MATCH PREDICTION INSIGHT CARD
// ============================================================================

let _predFixtures = [];
let _predScoreMatrix = null;  // cached for client-side AH/OU recomputation
let _predData = null;

function initPrediction() {
  const select = document.getElementById('pred-fixture-select');
  const computeBtn = document.getElementById('btn-pred-compute');
  const resetBtn = document.getElementById('btn-pred-reset');

  if (!select || !computeBtn) return;

  // Load fixtures when prediction tab is first opened
  document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.dataset.tab === 'prediction' && _predFixtures.length === 0) {
        loadPredictionFixtures();
      }
    });
  });

  // Fixture selection
  select.addEventListener('change', () => {
    const key = select.value;
    computeBtn.disabled = !key;
    if (key) {
      const fix = _predFixtures.find(f => f.fixture_key === key);
      showFixtureInfo(fix);
      // Auto-compute on selection
      computePrediction(key);
    } else {
      document.getElementById('pred-fixture-info')?.classList.add('hidden');
      document.getElementById('pred-empty-state')?.classList.remove('hidden');
      document.getElementById('pred-card-container')?.classList.add('hidden');
    }
  });

  // Compute button
  computeBtn.addEventListener('click', () => {
    const key = select.value;
    if (key) computePrediction(key);
  });

  // Reset button
  resetBtn?.addEventListener('click', () => {
    document.getElementById('pred-beta').value = 0;
    document.getElementById('pred-beta-val').textContent = '0.00';
    document.getElementById('pred-home-adv').value = 1.08;
    document.getElementById('pred-home-adv-val').textContent = '1.08';
    document.getElementById('pred-adj-home').value = 1.00;
    document.getElementById('pred-adj-home-val').textContent = '1.00';
    document.getElementById('pred-adj-away').value = 1.00;
    document.getElementById('pred-adj-away-val').textContent = '1.00';
    document.getElementById('pred-rho').value = -0.13;
    document.getElementById('pred-rho-val').textContent = '-0.13';
    document.getElementById('pred-adj-home-reason').value = '';
    document.getElementById('pred-adj-away-reason').value = '';
    const key = select.value;
    if (key) computePrediction(key);
  });

  // Wire up slider live value displays
  const sliders = [
    ['pred-beta', 'pred-beta-val', v => parseFloat(v).toFixed(2)],
    ['pred-home-adv', 'pred-home-adv-val', v => parseFloat(v).toFixed(2)],
    ['pred-adj-home', 'pred-adj-home-val', v => parseFloat(v).toFixed(2)],
    ['pred-adj-away', 'pred-adj-away-val', v => parseFloat(v).toFixed(2)],
    ['pred-rho', 'pred-rho-val', v => parseFloat(v).toFixed(2)],
  ];
  sliders.forEach(([sliderId, valId, fmt]) => {
    const slider = document.getElementById(sliderId);
    const valEl = document.getElementById(valId);
    if (slider && valEl) {
      slider.addEventListener('input', () => { valEl.textContent = fmt(slider.value); });
    }
  });

  // Wire up AH/OU line dropdowns for client-side recomputation
  document.getElementById('pred-ah-line')?.addEventListener('change', () => {
    if (_predScoreMatrix) updateAHFromMatrix();
  });
  document.getElementById('pred-ou-line')?.addEventListener('change', () => {
    if (_predScoreMatrix) updateOUFromMatrix();
  });
}

async function loadPredictionFixtures() {
  try {
    const res = await fetch('/api/prediction/fixtures');
    if (!res.ok) throw new Error('Failed to load fixtures');
    const data = await res.json();
    _predFixtures = data.fixtures || [];
    const select = document.getElementById('pred-fixture-select');
    if (!select) return;
    select.innerHTML = '<option value="">— Choose a fixture —</option>';
    _predFixtures.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f.fixture_key;
      const time = f.start_ts ? new Date(f.start_ts * 1000).toLocaleString('en-GB', {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
      }) : '';
      const grade = f.data_grade ? ` [${f.data_grade}]` : '';
      opt.textContent = `${f.home} vs ${f.away} — ${f.league}${grade} · ${time}`;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error('Failed to load prediction fixtures:', err);
    showBanner('Failed to load fixtures for prediction: ' + err.message, true);
  }
}

function showFixtureInfo(fix) {
  const info = document.getElementById('pred-fixture-info');
  if (!info || !fix) return;
  info.classList.remove('hidden');
  document.getElementById('pred-league-badge').textContent = fix.league || '';
  const covBadge = document.getElementById('pred-coverage-badge');
  covBadge.textContent = fix.coverage || '';
  covBadge.className = 'badge ' + (fix.coverage === 'full' ? 'badge-emerald' : fix.coverage === 'shadow' ? 'badge-amber' : 'badge-dim');
  const kickoff = document.getElementById('pred-kickoff');
  if (fix.start_ts) {
    kickoff.textContent = new Date(fix.start_ts * 1000).toLocaleString('en-GB', {
      weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
  }
}

async function computePrediction(fixtureKey) {
  const container = document.getElementById('pred-card-container');
  const empty = document.getElementById('pred-empty-state');
  const computeBtn = document.getElementById('btn-pred-compute');

  if (computeBtn) {
    computeBtn.disabled = true;
    computeBtn.textContent = '⏳ Computing…';
  }
  container?.classList.add('pred-loading');

  try {
    const body = {
      fixture_key: fixtureKey,
      beta_squad: parseFloat(document.getElementById('pred-beta')?.value || 0),
      home_advantage: null,
      manual_adj_home: parseFloat(document.getElementById('pred-adj-home')?.value || 1.0),
      manual_adj_away: parseFloat(document.getElementById('pred-adj-away')?.value || 1.0),
      adj_reason_home: document.getElementById('pred-adj-home-reason')?.value || null,
      adj_reason_away: document.getElementById('pred-adj-away-reason')?.value || null,
      rho: parseFloat(document.getElementById('pred-rho')?.value || -0.13),
    };

    const res = await fetch('/api/prediction/compute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Prediction compute failed');
    }

    const data = await res.json();
    _predData = data;
    _predScoreMatrix = data.score_matrix;

    empty?.classList.add('hidden');
    container?.classList.remove('hidden');
    renderPredictionCard(data);

  } catch (err) {
    showBanner('Prediction error: ' + err.message, true);
  } finally {
    container?.classList.remove('pred-loading');
    if (computeBtn) {
      computeBtn.disabled = !document.getElementById('pred-fixture-select')?.value;
      computeBtn.textContent = '🔄 Compute Prediction';
    }
  }
}

function renderPredictionCard(data) {
  // Match header
  const info = data.match_info || {};
  document.getElementById('pred-home-name').textContent = info.home || 'Home';
  document.getElementById('pred-away-name').textContent = info.away || 'Away';
  document.getElementById('pred-home-lambda').textContent = `λ ${data.lambdas?.home?.toFixed(2) || '—'}`;
  document.getElementById('pred-away-lambda').textContent = `λ ${data.lambdas?.away?.toFixed(2) || '—'}`;

  // Model badges
  const meta = data.model_meta || {};
  const badgesEl = document.getElementById('pred-model-badges');
  badgesEl.innerHTML = '';
  const badges = [
    { text: data.decision_reason || 'Uncalibrated model estimate', cls: 'badge-amber' },
    { text: meta.formula_version || '', cls: 'badge-dim' },
    { text: meta.lambda_source || '', cls: 'badge-cyan' },
    { text: `Grade ${meta.data_grade || '?'}`, cls: meta.data_grade === 'A' ? 'badge-emerald' : 'badge-amber' },
    { text: meta.coverage_status || '', cls: meta.coverage_status === 'full' ? 'badge-emerald' : 'badge-amber' },
  ];
  badges.forEach(b => {
    if (!b.text) return;
    const span = document.createElement('span');
    span.className = `badge ${b.cls}`;
    span.textContent = b.text;
    badgesEl.appendChild(span);
  });

  // 1X2 Probability Bar
  const ox = data.one_x_two || {};
  const hp = Math.round((ox.home || 0) * 100);
  const dp = Math.round((ox.draw || 0) * 100);
  const ap = 100 - hp - dp;
  const barHome = document.getElementById('pred-bar-home');
  const barDraw = document.getElementById('pred-bar-draw');
  const barAway = document.getElementById('pred-bar-away');
  barHome.style.width = `${hp}%`;
  barHome.querySelector('.prob-pct').textContent = `${hp}%`;
  barDraw.style.width = `${dp}%`;
  barDraw.querySelector('.prob-pct').textContent = `${dp}%`;
  barAway.style.width = `${ap}%`;
  barAway.querySelector('.prob-pct').textContent = `${ap}%`;

  // Key Metrics
  const xgDiff = data.xg_diff || 0;
  document.getElementById('pred-xg-diff').textContent = (xgDiff > 0 ? '+' : '') + xgDiff.toFixed(2);
  document.getElementById('pred-xg-diff').style.color = xgDiff > 0 ? 'var(--emerald)' : xgDiff < 0 ? 'var(--blue)' : 'var(--text-muted)';
  document.getElementById('pred-favorite').textContent = `Favorit: ${data.favorite || '—'}`;
  document.getElementById('pred-total-goals').textContent = (data.total_goals || 0).toFixed(2);
  const btts = data.btts || {};
  document.getElementById('pred-btts-pct').textContent = `${Math.round((btts.yes || 0) * 100)}%`;
  document.getElementById('pred-btts-rec').textContent = `Rec: ${data.recommended?.btts || '—'}`;

  // Market Recommendations
  const rec = data.recommended || {};

  // 1X2
  document.getElementById('pred-rec-1x2').textContent = rec['1x2'] || '—';
  const rec1x2Prob = ox[rec['1x2']?.toLowerCase()] || 0;
  document.getElementById('pred-rec-1x2-prob').textContent = `${(rec1x2Prob * 100).toFixed(1)}%`;

  // AH — set dropdown to recommended line and compute
  if (rec.ah) {
    const ahSelect = document.getElementById('pred-ah-line');
    if (ahSelect) {
      ahSelect.value = String(rec.ah.line || 0);
    }
  }
  updateAHFromMatrix();

  // OU — set dropdown and compute
  if (rec.ou) {
    const ouSelect = document.getElementById('pred-ou-line');
    if (ouSelect) ouSelect.value = String(rec.ou.line || 2.5);
  }
  updateOUFromMatrix();

  // BTTS
  document.getElementById('pred-rec-btts').textContent = rec.btts || '—';
  document.getElementById('pred-btts-yes').textContent = `${(btts.yes * 100).toFixed(1)}%`;
  document.getElementById('pred-btts-no').textContent = `${(btts.no * 100).toFixed(1)}%`;

  // Score Matrix Heatmap
  renderScoreMatrix(data.score_matrix);

  // Top Scores Pills
  renderTopScores(data.top_scores || []);
}

function renderScoreMatrix(matrix) {
  const container = document.getElementById('pred-score-matrix');
  if (!container || !matrix || !matrix.length) return;
  container.innerHTML = '';
  const n = matrix.length;
  container.style.gridTemplateColumns = `36px repeat(${n}, minmax(28px, 1fr))`;

  // Find max probability for color scaling
  let maxProb = 0;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      if (matrix[i][j] > maxProb) maxProb = matrix[i][j];
    }
  }

  // Corner cell
  const corner = document.createElement('div');
  corner.className = 'pred-matrix-cell corner-cell';
  corner.textContent = 'H\\A';
  container.appendChild(corner);

  // Column headers (away goals)
  for (let j = 0; j < n; j++) {
    const header = document.createElement('div');
    header.className = 'pred-matrix-cell header-cell';
    header.textContent = j;
    container.appendChild(header);
  }

  // Rows
  for (let i = 0; i < n; i++) {
    // Row header (home goals)
    const rowHeader = document.createElement('div');
    rowHeader.className = 'pred-matrix-cell header-cell';
    rowHeader.textContent = i;
    container.appendChild(rowHeader);

    for (let j = 0; j < n; j++) {
      const cell = document.createElement('div');
      cell.className = 'pred-matrix-cell';
      const prob = matrix[i][j];
      const pct = (prob * 100).toFixed(1);
      cell.textContent = pct;
      cell.title = `${i}-${j}: ${(prob * 100).toFixed(2)}%`;

      // Heatmap coloring
      const intensity = maxProb > 0 ? prob / maxProb : 0;
      if (i > j) {
        // Home win: green
        cell.style.background = `rgba(16, 185, 129, ${0.05 + intensity * 0.6})`;
        cell.style.color = intensity > 0.5 ? '#fff' : 'var(--text-muted)';
      } else if (i === j) {
        // Draw: gray
        cell.style.background = `rgba(107, 114, 128, ${0.1 + intensity * 0.5})`;
        cell.style.color = intensity > 0.5 ? '#fff' : 'var(--text-muted)';
      } else {
        // Away win: blue
        cell.style.background = `rgba(59, 130, 246, ${0.05 + intensity * 0.6})`;
        cell.style.color = intensity > 0.5 ? '#fff' : 'var(--text-muted)';
      }

      container.appendChild(cell);
    }
  }
}

function renderTopScores(topScores) {
  const container = document.getElementById('pred-top-scores-pills');
  if (!container) return;
  container.innerHTML = '';
  topScores.forEach(s => {
    const pill = document.createElement('div');
    pill.className = 'pred-score-pill';
    pill.innerHTML = `${escapeHtml(s.score)} <span class="pill-pct">${(s.prob * 100).toFixed(1)}%</span>`;
    container.appendChild(pill);
  });
}

// ---------------------------------------------------------------------------
// Client-side AH/OU recomputation from cached score matrix
// No backend roundtrip — instant updates when dropdown changes
// ---------------------------------------------------------------------------

function clientComputeAH(matrix, side, line) {
  if (!matrix || !matrix.length) return { win: 0, push: 0, lose: 0 };
  const n = matrix.length;
  const frac = Math.abs(line) % 0.5;

  // Quarter line: split into two adjacent lines
  if (frac > 0.01 && frac < 0.49) {
    const lo = Math.floor(line * 2) / 2.0;
    const hi = Math.ceil(line * 2) / 2.0;
    const r1 = _clientAHSingle(matrix, side, lo);
    const r2 = _clientAHSingle(matrix, side, hi);
    return {
      win: (r1.win + r2.win) / 2,
      push: (r1.push + r2.push) / 2,
      lose: (r1.lose + r2.lose) / 2,
    };
  }
  return _clientAHSingle(matrix, side, line);
}

function _clientAHSingle(matrix, side, line) {
  const n = matrix.length;
  let win = 0, push = 0, lose = 0;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const p = matrix[i][j];
      const diff = side === 'home' ? (i - j) + line : (j - i) + line;
      if (diff > 1e-9) win += p;
      else if (Math.abs(diff) <= 1e-9) push += p;
      else lose += p;
    }
  }
  return { win, push, lose };
}

function clientComputeOU(matrix, line) {
  if (!matrix || !matrix.length) return { over: 0, under: 0 };
  const n = matrix.length;
  let over = 0, under = 0, push = 0;
  const lines = Math.abs(line * 2 - Math.round(line * 2)) < 1e-9 ? [line] : [line - 0.25, line + 0.25];
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      for (const leg of lines) {
        const p = matrix[i][j] / lines.length;
        if (i + j > leg) over += p;
        else if (i + j < leg) under += p;
        else push += p;
      }
    }
  }
  return { over, under, push };
}

function updateAHFromMatrix() {
  if (!_predScoreMatrix) return;
  const lineStr = document.getElementById('pred-ah-line')?.value || '0';
  const line = parseFloat(lineStr);

  const homeResult = clientComputeAH(_predScoreMatrix, 'home', line);
  const awayResult = clientComputeAH(_predScoreMatrix, 'away', -line);

  const homePct = (homeResult.win * 100).toFixed(1);
  const pushPct = (homeResult.push * 100).toFixed(1);
  const awayPct = (homeResult.lose * 100).toFixed(1);

  document.getElementById('pred-ah-home-win').textContent = `${homePct}%`;
  document.getElementById('pred-ah-push').textContent = `${pushPct}%`;
  document.getElementById('pred-ah-away-win').textContent = `${awayPct}%`;

  // Determine recommendation
  const best = homeResult.win > homeResult.lose ? 'Home' : 'Away';
  const bestPct = homeResult.win > homeResult.lose ? homePct : awayPct;
  const recEl = document.getElementById('pred-rec-ah');
  const approved = (_predData?.qualified_picks || []).find(p => p.market === 'ah');
  recEl.textContent = approved ? `${approved.pick} @ ${approved.odds}` : 'NO BET';
  recEl.style.color = `var(--${best === 'Home' ? 'emerald' : 'blue'})`;
}

function updateOUFromMatrix() {
  if (!_predScoreMatrix) return;
  const lineStr = document.getElementById('pred-ou-line')?.value || '2.5';
  const line = parseFloat(lineStr);

  const result = clientComputeOU(_predScoreMatrix, line);
  const overPct = (result.over * 100).toFixed(1);
  const underPct = (result.under * 100).toFixed(1);

  document.getElementById('pred-ou-over').textContent = `${overPct}%`;
  document.getElementById('pred-ou-under').textContent = `${underPct}%`;

  const best = result.over > result.under ? 'Over' : 'Under';
  const bestPct = best === 'Over' ? overPct : underPct;
  const recEl = document.getElementById('pred-rec-ou');
  const approved = (_predData?.qualified_picks || []).find(p => p.market === 'ou');
  recEl.textContent = approved ? `${approved.pick} @ ${approved.odds}` : 'NO BET';
  const pushEl = document.getElementById('pred-ou-push');
  if (pushEl) pushEl.textContent = `${(result.push * 100).toFixed(1)}%`;
  recEl.style.color = `var(--${best === 'Over' ? 'amber' : 'cyan'})`;
}
