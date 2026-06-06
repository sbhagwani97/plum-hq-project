/**
 * dashboard.js
 * Fetches claims from /api/claims and renders the dashboard.
 */

const API_BASE = '';  // same origin

// ── Boot Screen Logic ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const bootScreen = document.getElementById('boot-screen');
  if (!bootScreen) return;

  // Only show the boot screen once per session
  if (!sessionStorage.getItem('plum_boot_shown')) {
    sessionStorage.setItem('plum_boot_shown', 'true');
    // Hide after 1.8 seconds
    setTimeout(() => {
      bootScreen.classList.add('hidden');
    }, 1800);
  } else {
    // Already shown this session, hide immediately
    bootScreen.style.display = 'none';
  }
});

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
    CONSULTATION:       '<i class="fa-solid fa-stethoscope"></i> Consultation',
    DIAGNOSTIC:         '<i class="fa-solid fa-microscope"></i> Diagnostic',
    PHARMACY:           '<i class="fa-solid fa-pills"></i> Pharmacy',
    DENTAL:             '<i class="fa-solid fa-tooth"></i> Dental',
    VISION:             '<i class="fa-solid fa-eye"></i> Vision',
    ALTERNATIVE_MEDICINE: '<i class="fa-solid fa-leaf"></i> Alt. Medicine',
  };
  return labels[cat] ?? cat;
}

function decisionLabel(decision, status) {
  if (!decision) return status ?? 'PENDING';
  return decision;
}

// ── Animated counter ──────────────────────────────────────────────────────────

function animateCounter(element, target) {
  const duration = 600;
  const startTime = performance.now();
  const startVal = 0;

  element.classList.add('animated');

  function tick(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    // Ease out cubic
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.round(startVal + (target - startVal) * eased);
    element.textContent = current;
    if (progress < 1) requestAnimationFrame(tick);
  }

  if (target === 0) {
    element.textContent = '0';
  } else {
    requestAnimationFrame(tick);
  }
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
  const map = {
    total:         'stat-total',
    approved:      'stat-approved',
    partial:       'stat-partial',
    rejected:      'stat-rejected',
    manual_review: 'stat-manual',
    pending:       'stat-pending',
  };
  for (const [key, id] of Object.entries(map)) {
    const el = document.getElementById(id);
    if (el) animateCounter(el, stats[key]);
  }
}

// ── Row builder ───────────────────────────────────────────────────────────────

function buildRow(claim, index) {
  const displayDecision = decisionLabel(claim.decision, claim.status);
  const badgeClass = `badge-${displayDecision.toLowerCase()}`;

  const fragment = document.createDocumentFragment();

  // Main Row
  const tr = document.createElement('tr');
  tr.className = 'row-enter';
  tr.style.animationDelay = `${0.4 + index * 0.04}s`;
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

  // Expanded Row
  const expandTr = document.createElement('tr');
  expandTr.className = 'expand-row';
  expandTr.style.display = 'none';

  let reasonsHtml = '<em style="color: var(--text-muted);">No reasons provided.</em>';
  if (claim.reasons && claim.reasons.length > 0) {
    reasonsHtml = `<ul style="margin: 0; padding-left: 1.5rem; color: var(--text-primary); font-size: 0.875rem;">
      ${claim.reasons.map(r => `<li style="margin-bottom: 0.25rem;">${r}</li>`).join('')}
    </ul>`;
  }

  expandTr.innerHTML = `
    <td colspan="7">
      <div class="expand-content">
        <div style="flex: 1;">
          <h4 style="margin-top: 0; margin-bottom: 0.75rem; font-size: 0.78rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600;">Decision Reasoning</h4>
          ${reasonsHtml}
        </div>
        <div>
          <button class="btn-trace"><i class="fa-solid fa-timeline"></i> View Full Trace</button>
        </div>
      </div>
    </td>
  `;

  // Toggle Logic
  tr.addEventListener('click', () => {
    if (expandTr.style.display === 'none') {
      expandTr.style.display = 'table-row';
      tr.style.backgroundColor = 'var(--bg-elevated)';
    } else {
      expandTr.style.display = 'none';
      tr.style.backgroundColor = '';
    }
  });

  // Wiring up Trace Modal button
  const traceBtn = expandTr.querySelector('.btn-trace');
  if (traceBtn) {
    traceBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      openTraceModal(claim.claim_id);
    });
  }

  fragment.appendChild(tr);
  fragment.appendChild(expandTr);
  return fragment;
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

  for (let i = 0; i < claims.length; i++) {
    tbody.appendChild(buildRow(claims[i], i));
  }

  if (countEl) countEl.textContent = `${claims.length} claims`;
}

// ── Trace Modal Logic ─────────────────────────────────────────────────────────

async function openTraceModal(claimId) {
  const modal = document.getElementById('trace-modal');
  const timeline = document.getElementById('trace-timeline');
  const claimIdSpan = document.getElementById('trace-claim-id');

  if (!modal || !timeline) return;

  modal.classList.add('is-open');
  claimIdSpan.textContent = claimId;
  timeline.innerHTML = '<span class="spinner"></span> Loading trace...';

  try {
    const res = await fetch(`${API_BASE}/api/claims/${claimId}/trace`);
    if (!res.ok) throw new Error('Failed to load trace');

    const traceData = await res.json();
    timeline.innerHTML = '';

    // Check if trace has agents
    if (!traceData.agents || traceData.agents.length === 0) {
      timeline.innerHTML = '<div style="padding: 1rem; color: var(--text-muted);">No trace found for this claim.</div>';
      return;
    }

    for (const step of traceData.agents) {
      const item = document.createElement('div');
      item.className = 'trace-step';

      let outJson = '';
      try {
        if (typeof step.output === 'object') {
          outJson = JSON.stringify(step.output, null, 2);
        } else if (typeof step.output === 'string') {
          outJson = JSON.stringify(JSON.parse(step.output), null, 2);
        } else {
          outJson = String(step.output);
        }
      } catch (e) { outJson = step.output; }

      item.innerHTML = `
        <div class="trace-step-header">
          ${step.agent}
          <span class="trace-step-duration">${step.duration_ms}ms</span>
        </div>
        <pre class="trace-step-output">${outJson}</pre>
      `;
      timeline.appendChild(item);
    }

  } catch (err) {
    timeline.innerHTML = `<span style="color: var(--status-rejected);">⚠️ ${err.message}</span>`;
  }
}

function closeTraceModal() {
  const modal = document.getElementById('trace-modal');
  if (modal) modal.classList.remove('is-open');
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
    const res = await fetch(`${API_BASE}/api/claims`);
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const claims = await res.json();

    renderClaims(claims);
    updateStats(computeStats(claims));
  } catch (err) {
    console.error('Failed to load claims:', err);
    showError(`Could not load claims. ${err.message}`);
  }
}

// ── Member Lookup ─────────────────────────────────────────────────────────────

async function handleMemberSearch() {
  const input = document.getElementById('member-search-input');
  const resultDiv = document.getElementById('member-lookup-result');
  const memberId = input.value.trim().toUpperCase();

  if (!memberId) return;

  resultDiv.style.display = 'block';
  resultDiv.innerHTML = '<span class="spinner"></span>Checking eligibility...';

  try {
    const res = await fetch(`${API_BASE}/api/policy/coverage/${memberId}`);
    if (!res.ok) {
      if (res.status === 404) throw new Error('Member not found in policy');
      throw new Error(`Server error: ${res.status}`);
    }

    const data = await res.json();
    const { eligibility, policy_limits } = data;

    let reasonsHtml = '';
    if (eligibility.reasons && eligibility.reasons.length > 0) {
      reasonsHtml = `<ul style="color: var(--status-rejected); margin-top: 0.5rem; padding-left: 1.5rem; font-size: 0.85rem;">
        ${eligibility.reasons.map(r => `<li>${r}</li>`).join('')}
      </ul>`;
    }

    resultDiv.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: flex-start;">
        <div>
          <div style="font-weight: 700; color: var(--text-primary); font-size: 1.1rem;">${data.name} <span class="claim-id" style="margin-left: 0.5rem;">${data.member_id}</span></div>
          <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.25rem;">Relationship: ${data.relationship}</div>
        </div>
        <span class="badge ${eligibility.is_valid ? 'badge-approved' : 'badge-rejected'}">
          ${eligibility.is_valid ? 'ELIGIBLE' : 'INELIGIBLE'}
        </span>
      </div>
      ${reasonsHtml}
      <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--border-subtle); display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem;">
        <div>
          <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;">Sum Insured</div>
          <div style="font-weight: 600;">${formatINR(policy_limits.sum_insured_per_employee)}</div>
        </div>
        <div>
          <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;">Annual OPD Limit</div>
          <div style="font-weight: 600;">${formatINR(policy_limits.annual_opd_limit)}</div>
        </div>
        <div>
          <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;">Per Claim Limit</div>
          <div style="font-weight: 600;">${formatINR(policy_limits.per_claim_limit)}</div>
        </div>
      </div>
    `;

  } catch (err) {
    resultDiv.innerHTML = `<span style="color: var(--status-rejected);">⚠️ ${err.message}</span>`;
  }
}

// ── Document Verification ─────────────────────────────────────────────────────

async function handleDocUpload() {
  const fileInput = document.getElementById('doc-upload-input');
  const resultDiv = document.getElementById('doc-verify-result');
  const file = fileInput.files[0];

  if (!file) return;

  resultDiv.style.display = 'block';
  resultDiv.innerHTML = '<span class="spinner"></span>Extracting and verifying document...';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`${API_BASE}/api/claims/verify-docs`, {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      throw new Error(`Server error: ${res.status}`);
    }

    const data = await res.json();
    if (data.error) throw new Error(data.error);

    const { verification, extracted_text_preview } = data;

    const fieldsHtml = Object.entries(verification.key_fields || {}).map(([key, val]) => `
      <div style="margin-bottom: 0.5rem;">
        <span style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">${key}</span>
        <div style="font-weight: 500;">${val}</div>
      </div>
    `).join('');

    resultDiv.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
        <div style="font-weight: 700; font-size: 1.1rem;">Type: ${verification.document_type}</div>
      </div>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; border-top: 1px solid var(--border-subtle); padding-top: 1rem;">
        ${fieldsHtml}
      </div>
      <div style="margin-top: 1rem; border-top: 1px solid var(--border-subtle); padding-top: 1rem;">
        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.5rem; text-transform: uppercase;">Raw Text Preview</div>
        <pre style="font-size: 0.8rem; background: var(--bg-base); padding: 0.5rem; border-radius: var(--radius-sm); overflow-x: auto; max-height: 150px; overflow-y: auto; color: var(--text-primary);">${extracted_text_preview}</pre>
      </div>
    `;

  } catch (err) {
    resultDiv.innerHTML = `<span style="color: var(--status-rejected);">⚠️ ${err.message}</span>`;
  }
}

// ── Sidebar Toggle ────────────────────────────────────────────────────────────

function initSidebar() {
  const toggle = document.getElementById('sidebar-toggle');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');

  if (toggle && sidebar && overlay) {
    toggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      overlay.classList.toggle('active');
    });

    overlay.addEventListener('click', () => {
      sidebar.classList.remove('open');
      overlay.classList.remove('active');
    });
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadClaims();
  initSidebar();

  // Modal close handlers
  const closeBtn = document.getElementById('close-modal');
  const backdrop = document.getElementById('modal-backdrop');

  if (closeBtn) {
    closeBtn.addEventListener('click', closeTraceModal);
  }
  if (backdrop) {
    backdrop.addEventListener('click', closeTraceModal);
  }

  // Close modal on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeTraceModal();
  });

  // Member search
  const searchBtn = document.getElementById('member-search-btn');
  const searchInput = document.getElementById('member-search-input');

  if (searchBtn) {
    searchBtn.addEventListener('click', handleMemberSearch);
  }

  if (searchInput) {
    searchInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') handleMemberSearch();
    });
  }

  // Doc upload
  const docUploadBtn = document.getElementById('doc-upload-btn');
  if (docUploadBtn) {
    docUploadBtn.addEventListener('click', handleDocUpload);
  }

  // DB clear
  const dbClearBtn = document.getElementById('db-clear-btn');
  if (dbClearBtn) {
    dbClearBtn.addEventListener('click', async () => {
      if (!confirm("Are you sure you want to clear all claims? This cannot be undone.")) return;
      try {
        const res = await fetch(`${API_BASE}/api/claims/clear`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to clear database');
        loadClaims();
      } catch (err) {
        alert(err.message);
      }
    });
  }
});
