/**
 * dashboard.js
 * Phase 1: Fetches mock claims from /api/claims/mock and renders the dashboard.
 */

const API_BASE = '';  // same origin

// ── Formatters ────────────────────────────────────────────────────────────────

function formatINR(amount) {
  if (amount == null) return '—';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);
}

function formatDate(isoString) {
  if (!isoString) return '—';
  const d = new Date(isoString);
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

function initials(name) {
  return name
    .split(' ')
    .slice(0, 2)
    .map(p => p[0])
    .join('')
    .toUpperCase();
}

function categoryLabel(cat) {
  const labels = {
    CONSULTATION:       '🩺 Consultation',
    DIAGNOSTIC:         '🔬 Diagnostic',
    PHARMACY:           '💊 Pharmacy',
    DENTAL:             '🦷 Dental',
    VISION:             '👁 Vision',
    ALTERNATIVE_MEDICINE: '🌿 Alt. Medicine',
  };
  return labels[cat] ?? cat;
}

function decisionLabel(decision, status) {
  if (!decision) return status ?? 'PENDING';
  return decision;
}

// ── Stats computation ─────────────────────────────────────────────────────────

function computeStats(claims) {
  const stats = {
    total:        claims.length,
    approved:     0,
    partial:      0,
    rejected:     0,
    manual_review: 0,
    pending:      0,
  };
  for (const c of claims) {
    const key = (c.decision ?? c.status ?? '').toLowerCase().replace(' ', '_');
    if (key in stats) stats[key]++;
    else if (c.status === 'PENDING' || c.status === 'PROCESSING') stats.pending++;
  }
  return stats;
}

function updateStats(stats) {
  const els = {
    total:         document.getElementById('stat-total'),
    approved:      document.getElementById('stat-approved'),
    partial:       document.getElementById('stat-partial'),
    rejected:      document.getElementById('stat-rejected'),
    manual_review: document.getElementById('stat-manual'),
    pending:       document.getElementById('stat-pending'),
  };
  if (els.total)         els.total.textContent         = stats.total;
  if (els.approved)      els.approved.textContent      = stats.approved;
  if (els.partial)       els.partial.textContent       = stats.partial;
  if (els.rejected)      els.rejected.textContent      = stats.rejected;
  if (els.manual_review) els.manual_review.textContent = stats.manual_review;
  if (els.pending)       els.pending.textContent       = stats.pending;
}

// ── Row builder ───────────────────────────────────────────────────────────────

function buildRow(claim) {
  const displayDecision = decisionLabel(claim.decision, claim.status);
  const badgeClass = `badge-${displayDecision.toLowerCase()}`;

  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td><span class="claim-id">${claim.claim_id}</span></td>
    <td>
      <div class="member-cell">
        <div class="member-avatar">${initials(claim.member_name)}</div>
        <div>
          <div class="member-name">${claim.member_name}</div>
          <div class="member-id">${claim.member_id}</div>
        </div>
      </div>
    </td>
    <td><span class="category-pill">${categoryLabel(claim.claim_category)}</span></td>
    <td class="amount-col">
      <div class="claimed-amount">${formatINR(claim.claimed_amount)}</div>
      ${claim.approved_amount != null
        ? `<div class="approved-amount">↳ ${formatINR(claim.approved_amount)} approved</div>`
        : ''}
    </td>
    <td><span class="badge ${badgeClass}">${displayDecision.replace('_', ' ')}</span></td>
    <td>${formatDate(claim.treatment_date)}</td>
    <td>${formatDate(claim.submitted_at)}</td>
  `;
  return tr;
}

// ── Render ────────────────────────────────────────────────────────────────────

function renderClaims(claims) {
  const tbody = document.getElementById('claims-tbody');
  const countEl = document.getElementById('claims-count');
  if (!tbody) return;

  tbody.innerHTML = '';

  if (!claims.length) {
    tbody.innerHTML = `
      <tr class="state-row">
        <td colspan="7">No claims found.</td>
      </tr>`;
    return;
  }

  for (const claim of claims) {
    tbody.appendChild(buildRow(claim));
  }

  if (countEl) countEl.textContent = `${claims.length} claims`;
}

function showLoading() {
  const tbody = document.getElementById('claims-tbody');
  if (tbody) {
    tbody.innerHTML = `
      <tr class="state-row">
        <td colspan="7"><span class="spinner"></span>Loading claims…</td>
      </tr>`;
  }
}

function showError(message) {
  const tbody = document.getElementById('claims-tbody');
  if (tbody) {
    tbody.innerHTML = `
      <tr class="state-row">
        <td colspan="7">⚠️ ${message}</td>
      </tr>`;
  }
}

// ── Fetch ─────────────────────────────────────────────────────────────────────

async function loadClaims() {
  showLoading();
  try {
    const res = await fetch(`${API_BASE}/api/claims/mock`);
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const claims = await res.json();

    renderClaims(claims);
    updateStats(computeStats(claims));
  } catch (err) {
    console.error('Failed to load claims:', err);
    showError(`Could not load claims. ${err.message}`);
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', loadClaims);
