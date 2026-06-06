document.addEventListener('DOMContentLoaded', () => {
  const messagesContainer = document.getElementById('chat-messages');
  const chatForm = document.getElementById('chat-form');
  const chatInput = document.getElementById('chat-input');
  const quickRepliesContainer = document.getElementById('quick-replies');
  const btnUpload = document.getElementById('btn-upload');
  const fileInput = document.getElementById('file-input');
  const btnSend = document.getElementById('btn-send');

  // ── Policy document requirements (mirrors policy_terms.json) ─────────────
  const REQUIRED_DOCS = {
    'CONSULTATION':         ['PRESCRIPTION', 'HOSPITAL_BILL'],
    'DIAGNOSTIC':           ['PRESCRIPTION', 'DIAGNOSTIC_REPORT', 'HOSPITAL_BILL'],
    'PHARMACY':             ['PRESCRIPTION', 'PHARMACY_BILL'],
    'DENTAL':               ['HOSPITAL_BILL'],
    'VISION':               ['PRESCRIPTION', 'HOSPITAL_BILL'],
    'ALTERNATIVE_MEDICINE': ['PRESCRIPTION', 'HOSPITAL_BILL'],
  };

  // Short labels shown in the checklist and confirmation bubbles
  const DOC_LABELS = {
    'PRESCRIPTION':      "Doctor's Prescription",
    'HOSPITAL_BILL':     'Hospital / Clinic Bill',
    'DIAGNOSTIC_REPORT': 'Diagnostic / Lab Report',
    'PHARMACY_BILL':     'Pharmacy Bill',
  };

  // Longer hints shown when asking the user to upload each document
  const DOC_HINTS = {
    'PRESCRIPTION':      'Rx slip from your doctor listing the diagnosis and medicines',
    'HOSPITAL_BILL':     'Invoice or receipt issued by the hospital or clinic',
    'DIAGNOSTIC_REPORT': 'Lab report, blood test result, scan or X-ray report',
    'PHARMACY_BILL':     'Chemist / pharmacy bill with medicine names, batch numbers and amounts',
  };

  const categories = [
    'CONSULTATION', 'DIAGNOSTIC', 'PHARMACY',
    'DENTAL', 'VISION', 'ALTERNATIVE_MEDICINE',
  ];

  // ── State ─────────────────────────────────────────────────────────────────
  let state = {
    step: 'ASK_MEMBER_ID',
    member_id: null,
    claim_category: null,

    // Document collection
    required_docs: [],    // e.g. ['PRESCRIPTION', 'PHARMACY_BILL']
    collected_docs: [],   // [{file, filename, doc_type, extracted_text, key_fields}]
    current_doc_idx: 0,   // which required doc we're currently asking for

    // Populated after full extraction pipeline runs
    extracted_text: null,
    extracted_fields: null,
    initial_trace: null,
    claim_id: null,
  };

  // ── UI helpers ────────────────────────────────────────────────────────────
  function addMessage(text, sender = 'bot', isHtml = false) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-message ${sender}`;
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    if (isHtml) { bubble.innerHTML = text; } else { bubble.textContent = text; }
    msgDiv.appendChild(bubble);
    messagesContainer.appendChild(msgDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    return bubble;
  }

  function addTypingIndicator() {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'chat-message bot typing';
    msgDiv.innerHTML = `
      <div class="chat-bubble typing-indicator">
        <span></span><span></span><span></span>
      </div>
    `;
    messagesContainer.appendChild(msgDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    return msgDiv;
  }

  function clearQuickReplies() { quickRepliesContainer.innerHTML = ''; }

  function addQuickReplies(replies, onSelect) {
    clearQuickReplies();
    replies.forEach(reply => {
      const btn = document.createElement('button');
      btn.className = 'quick-reply-btn';
      btn.textContent = reply.label;
      btn.onclick = () => {
        clearQuickReplies();
        addMessage(reply.label, 'user');
        onSelect(reply.value);
      };
      quickRepliesContainer.appendChild(btn);
    });
  }

  function toggleInput(enabled, showUpload = false) {
    chatInput.disabled = !enabled;
    btnSend.disabled = !enabled;
    btnUpload.style.display = showUpload ? 'flex' : 'none';
  }

  // ── File upload handler ───────────────────────────────────────────────────
  btnUpload.addEventListener('click', () => {
    fileInput.value = '';   // allow re-selecting the same file
    fileInput.click();
  });

  fileInput.addEventListener('change', async (e) => {
    if (e.target.files.length === 0) return;
    if (state.step !== 'ASK_DOC') return;

    const file = e.target.files[0];
    addMessage(`📎 ${file.name}`, 'user');
    toggleInput(false, false);   // disable while parsing
    await parseAndStoreDoc(file);
  });

  // ── Text input (member ID only) ───────────────────────────────────────────
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;
    chatInput.value = '';
    addMessage(text, 'user');
    if (state.step === 'ASK_MEMBER_ID') {
      state.member_id = text;
      handleStepAdvance();
    }
  });

  // ── State machine ─────────────────────────────────────────────────────────
  async function handleStepAdvance() {
    clearQuickReplies();

    // ── 1. Validate member ID ───────────────────────────────────────────────
    if (state.step === 'ASK_MEMBER_ID') {
      toggleInput(false);
      const loadingBubble = addMessage('Verifying member ID…', 'bot');

      try {
        const res = await fetch(`/api/policy/coverage/${state.member_id}`);
        if (!res.ok) throw new Error('Not found');
        const data = await res.json();
        const memberName = data.name || state.member_id;

        loadingBubble.remove();
        state.step = 'ASK_CATEGORY';

        setTimeout(() => {
          addMessage(`Welcome back, ${memberName}! What category is this claim for?`);
          addQuickReplies(
            categories.map(c => ({ label: c.replace(/_/g, ' '), value: c })),
            (val) => { state.claim_category = val; handleStepAdvance(); }
          );
        }, 500);
      } catch {
        loadingBubble.remove();
        addMessage(`Sorry, I couldn't find a member with ID "${state.member_id}". Please try another one.`);
        state.member_id = null;
        toggleInput(true);
        chatInput.focus();
      }

    // ── 2. Category chosen → show required docs ─────────────────────────────
    } else if (state.step === 'ASK_CATEGORY') {
      state.required_docs  = REQUIRED_DOCS[state.claim_category] || [];
      state.collected_docs = [];
      state.current_doc_idx = 0;

      const categoryLabel = state.claim_category.replace(/_/g, ' ');
      const total = state.required_docs.length;

      // Build a numbered checklist of required documents
      const listItems = state.required_docs
        .map((type, i) =>
          `<li style="margin-bottom:0.4rem;">
             <strong>${DOC_LABELS[type] || type}</strong>
             <span style="color:var(--text-muted);font-size:0.82rem;"> — ${DOC_HINTS[type] || ''}</span>
           </li>`
        ).join('');

      setTimeout(() => {
        addMessage(
          `For a <strong>${categoryLabel}</strong> claim, you'll need to upload
           <strong>${total} document${total > 1 ? 's' : ''}</strong>:<br>
           <ol style="margin:0.6rem 0 0 1rem;padding:0;">${listItems}</ol><br>
           Let's go through them one at a time.`,
          'bot', true
        );
        state.step = 'ASK_DOC';
        setTimeout(() => askForCurrentDoc(), 800);
      }, 500);

    // ── 3. All docs collected → run full extraction pipeline ────────────────
    } else if (state.step === 'ALL_DOCS_READY') {
      state.step = 'EXTRACTING';
      await startExtraction();
    }
  }

  // ── Ask for the Nth required document ─────────────────────────────────────
  function askForCurrentDoc() {
    const idx   = state.current_doc_idx;
    const type  = state.required_docs[idx];
    const label = DOC_LABELS[type] || type;
    const hint  = DOC_HINTS[type]  || '';
    const total = state.required_docs.length;

    addMessage(
      `<strong>Document ${idx + 1} of ${total}:</strong>
       Please upload your <strong>${label}</strong>.<br>
       <span style="color:var(--text-muted);font-size:0.85rem;">${hint}</span>
       <button class="inline-upload-btn" style="
         display:inline-flex;align-items:center;gap:0.4rem;margin-top:0.65rem;
         padding:0.5rem 1rem;background:var(--accent-subtle);color:var(--accent-primary);
         border:1px solid var(--accent-primary);border-radius:9999px;cursor:pointer;
         font-size:0.82rem;font-weight:600;font-family:inherit;
         transition:background 0.15s,transform 0.15s;">
         <i class="fa-solid fa-paperclip"></i> Choose File
       </button>`,
      'bot', true
    );

    // Wire the inline button to the hidden file input
    const allBtns = messagesContainer.querySelectorAll('.inline-upload-btn');
    const inlineBtn = allBtns[allBtns.length - 1];
    if (inlineBtn) {
      inlineBtn.addEventListener('click', () => {
        fileInput.value = '';
        fileInput.click();
      });
    }

    toggleInput(false, false);   // keep bottom bar hidden, upload is inline now
  }

  // ── Parse a single uploaded document via /claims/parse-doc ───────────────
  async function parseAndStoreDoc(file) {
    const expectedType  = state.required_docs[state.current_doc_idx];
    const expectedLabel = DOC_LABELS[expectedType] || expectedType;
    const typingEl = addTypingIndicator();

    try {
      const formData = new FormData();
      formData.append('file', file);
      // Send member_id so the backend can detect name mismatches early
      if (state.member_id) {
        formData.append('member_id', state.member_id);
      }

      const res = await fetch('/api/claims/parse-doc', { method: 'POST', body: formData });
      typingEl.remove();

      if (!res.ok) throw new Error('Server error');
      const result = await res.json();
      if (result.error) throw new Error(result.error);

      const detectedType  = result.doc_type;
      const detectedLabel = DOC_LABELS[detectedType] || detectedType.replace(/_/g, ' ');

      // Show 3–4 key fields as a compact table
      const topFields = Object.entries(result.key_fields || {}).slice(0, 4);
      const fieldsHtml = topFields.length
        ? `<table style="margin-top:0.5rem;font-size:0.8rem;border-collapse:collapse;">
             ${topFields.map(([k, v]) =>
               `<tr>
                  <td style="color:var(--text-muted);padding-right:1rem;padding-bottom:0.2rem;">${k}</td>
                  <td style="padding-bottom:0.2rem;">${v}</td>
                </tr>`
             ).join('')}
           </table>`
        : '';

      // Warn if the detected type differs from what was expected
      const typeMismatch = detectedType !== 'UNKNOWN' && detectedType !== expectedType;
      const typeMismatchHtml = typeMismatch
        ? `<div style="margin-top:0.4rem;color:var(--status-partial);font-size:0.82rem;">
             ⚠️ This looks like a <strong>${detectedLabel}</strong>,
             but we expected a <strong>${expectedLabel}</strong>.
             It will be stored as-is — the final check will flag any missing documents.
           </div>`
        : '';

      // ── Early name-mismatch → block and offer re-upload / restart ────
      if (result.name_mismatch) {
        const nm = result.name_mismatch;
        const nameMismatchHtml = `
          <div style="margin-top:0.6rem;padding:0.6rem 0.8rem;background:var(--status-rejected-bg);
                      border:1px solid var(--status-rejected);border-radius:var(--radius-sm);
                      color:var(--status-rejected);font-size:0.82rem;line-height:1.45;">
            <i class="fa-solid fa-triangle-exclamation"></i> <strong>Name Mismatch:</strong> ${nm.message}
          </div>`;

        addMessage(
          `⚠️ <strong>${file.name}</strong> parsed.<br>
           Detected: <strong>${detectedLabel}</strong>
           ${nameMismatchHtml}
           ${fieldsHtml}`,
          'bot', true
        );

        // Do NOT store the doc or advance — offer recovery options
        toggleInput(false, false);
        addQuickReplies([
          { label: '\u00a0Re-upload this document',  value: 'REUPLOAD' },
          { label: '\u00a0Ok, lets try again...',        value: 'RESTART' },
        ], (choice) => {
          if (choice === 'REUPLOAD') {
            // Re-ask for the same document slot
            setTimeout(() => askForCurrentDoc(), 300);
          } else {
            // Full restart
            state.step            = 'ASK_MEMBER_ID';
            state.member_id       = null;
            state.claim_category  = null;
            state.required_docs   = [];
            state.collected_docs  = [];
            state.current_doc_idx = 0;
            state.extracted_text  = null;
            state.extracted_fields = null;
            state.initial_trace   = null;
            state.claim_id        = null;

            addMessage("No problem! Let's start fresh.", 'bot');
            setTimeout(() => {
              addMessage('Please enter your Member ID (e.g. EMP001).');
              toggleInput(true);
              chatInput.focus();
            }, 600);
          }
        });
        return;   // ← exit early, skip normal doc storage
      }

      addMessage(
        `✅ <strong>${file.name}</strong> parsed.<br>
         Detected: <strong>${detectedLabel}</strong>
         ${typeMismatchHtml}
         ${fieldsHtml}`,
        'bot', true
      );

      // Store the doc in state
      state.collected_docs.push({
        file,
        filename:       file.name,
        doc_type:       detectedType,
        extracted_text: result.extracted_text,
        key_fields:     result.key_fields,
      });

      state.current_doc_idx++;

      if (state.current_doc_idx >= state.required_docs.length) {
        // All required documents collected
        setTimeout(() => showAllDocsCollected(), 800);
      } else {
        // Ask for the next document
        setTimeout(() => askForCurrentDoc(), 800);
      }

    } catch (err) {
      typingEl.remove();
      addMessage(`❌ Failed to parse document: ${err.message}. Please try uploading again.`, 'bot');
      toggleInput(false, true);   // re-show upload button
    }
  }

  // ── Summary card once all docs are in ────────────────────────────────────
  function showAllDocsCollected() {
    const docList = state.collected_docs
      .map(d => {
        const label = DOC_LABELS[d.doc_type] || d.doc_type.replace(/_/g, ' ');
        return `<li style="margin-bottom:0.3rem;">✅ <strong>${label}</strong> — ${d.filename}</li>`;
      })
      .join('');

    addMessage(
      `All required documents received!<br>
       <ul style="margin:0.5rem 0 0 1rem;padding:0;">${docList}</ul><br>
       Running extraction and policy verification…`,
      'bot', true
    );

    state.step = 'ALL_DOCS_READY';
    handleStepAdvance();
  }

  // ── Full extraction pipeline (SSE stream) ─────────────────────────────────
  async function startExtraction() {
    const formData = new FormData();
    formData.append('member_id',      state.member_id);
    formData.append('claim_category', state.claim_category);
    state.collected_docs.forEach(d => formData.append('files', d.file));

    let lastBubble = null;

    try {
      const response = await fetch('/api/claims/extract', { method: 'POST', body: formData });
      if (!response.ok) throw new Error('Server error');

      const reader  = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer    = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();

        for (const part of parts) {
          if (!part.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(part.slice(6));

            if (!data.is_final) {
              if (data.data) {
                addMessage(
                  `⏳ ${data.message}<br>
                   <pre style="font-size:0.75rem;background:var(--bg-base);padding:0.5rem;
                               border-radius:var(--radius-sm);color:var(--text-muted);
                               margin-top:0.5rem;white-space:pre-wrap;">
                     ${JSON.stringify(data.data, null, 2)}
                   </pre>`,
                  'bot', true
                );
                lastBubble = null;
              } else {
                if (lastBubble) { lastBubble.innerHTML = `⏳ ${data.message}`; }
                else { lastBubble = addMessage(`⏳ ${data.message}`, 'bot', true); }
              }

            } else if (data.phase === 'complete') {
              if (lastBubble) lastBubble.textContent = '✅ Documents verified!';

              state.extracted_text   = data.data.text;
              state.extracted_fields = data.data.extracted_fields;
              state.initial_trace    = data.data.trace;
              state.claim_id         = data.data.trace.claim_id;

              state.step = 'REVIEW';
              showReviewCard();

            } else if (data.phase === 'error') {
              if (lastBubble) lastBubble.remove();
              addMessage(`❌ ${data.message}`, 'bot');
              // Let user restart doc collection for this category
              state.step = 'ASK_DOC';
              state.collected_docs  = [];
              state.current_doc_idx = 0;
              setTimeout(() => {
                addMessage('Please re-upload the required documents.', 'bot');
                askForCurrentDoc();
              }, 600);
            }
          } catch { /* ignore malformed SSE frames */ }
        }
      }
    } catch (err) {
      addMessage(`❌ Network error during extraction.`, 'bot');
      // Allow restart
      state.step = 'ASK_DOC';
      state.collected_docs  = [];
      state.current_doc_idx = 0;
      setTimeout(() => askForCurrentDoc(), 800);
    }
  }

  // ── Review card ───────────────────────────────────────────────────────────
  function showReviewCard() {
    const fields = state.extracted_fields || {};
    let dateVal = fields['Date'] || fields['Treatment Date'] || '';
    if (dateVal && !dateVal.match(/^\d{4}-\d{2}-\d{2}$/)) {
      const d = new Date(dateVal);
      if (!isNaN(d.getTime())) dateVal = d.toISOString().split('T')[0];
      else dateVal = '';
    }

    let amountVal = (fields['Total Amount'] || fields['Claimed Amount'] || '').toString().replace(/[^0-9.]/g, '');

    const cardHtml = `
      <div class="review-card">
        <h4 style="margin-bottom:0.5rem;font-size:0.9rem;">Review Details</h4>
        <div class="form-group">
          <label>Treatment Date</label>
          <input type="date" id="review_date" value="${dateVal}" />
        </div>
        <div class="form-group">
          <label>Hospital / Clinic</label>
          <input type="text" id="review_hospital"
                 value="${fields['Hospital Name'] || fields['Doctor Name'] || ''}" />
        </div>
        <div class="form-group">
          <label>Claimed Amount (INR)</label>
          <input type="number" id="review_amount" step="0.01" value="${amountVal}" />
        </div>
        <div class="form-group">
          <label>Bill Total (Extracted)</label>
          <input type="number" id="review_bill_total" step="0.01" value="${amountVal}" />
        </div>
        <button id="btn-confirm-review"
                style="width:100%;padding:0.5rem;background:var(--status-approved);
                       color:white;border:none;border-radius:var(--radius-sm);
                       cursor:pointer;font-weight:600;margin-top:0.5rem;">
          Confirm &amp; Submit
        </button>
      </div>
    `;
    addMessage(cardHtml, 'bot', true);

    setTimeout(() => {
      document.getElementById('btn-confirm-review').addEventListener('click', async () => {
        document.getElementById('review_date').disabled       = true;
        document.getElementById('review_hospital').disabled   = true;
        document.getElementById('review_amount').disabled     = true;
        document.getElementById('review_bill_total').disabled = true;
        document.getElementById('btn-confirm-review').style.display = 'none';

        addMessage('Looks good! Please process it.', 'user');
        state.step = 'PROCESSING';

        const date      = document.getElementById('review_date').value;
        const amount    = document.getElementById('review_amount').value;
        const hospital  = document.getElementById('review_hospital').value;
        const billTotal = document.getElementById('review_bill_total').value;

        if (state.extracted_fields) {
          state.extracted_fields['Total Amount'] = billTotal;
        } else {
          state.extracted_fields = { 'Total Amount': billTotal };
        }

        await startProcessing(date, amount, hospital);
      });
    }, 100);
  }

  // ── Processing pipeline (SSE stream) ─────────────────────────────────────
  async function startProcessing(date, amount, hospital) {
    addMessage('Running policy evaluation…', 'bot');

    const payload = {
      claim_id:        state.claim_id,
      member_id:       state.member_id,
      claim_category:  state.claim_category,
      treatment_date:  date,
      claimed_amount:  parseFloat(amount) || 0.0,
      hospital_name:   hospital,
      extracted_text:  state.extracted_text,
      extracted_fields: state.extracted_fields,
      initial_trace:   state.initial_trace,
    };

    try {
      const response = await fetch('/api/claims/process', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(payload),
      });
      if (!response.ok) throw new Error('Server error');

      const reader  = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer    = '';
      let lastBubble = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();

        for (const part of parts) {
          if (!part.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(part.slice(6));

            if (!data.is_final) {
              if (data.data) {
                addMessage(
                  `⏳ ${data.message}<br>
                   <pre style="font-size:0.75rem;background:var(--bg-base);padding:0.5rem;
                               border-radius:var(--radius-sm);color:var(--text-muted);
                               margin-top:0.5rem;white-space:pre-wrap;">
                     ${JSON.stringify(data.data, null, 2)}
                   </pre>`,
                  'bot', true
                );
                lastBubble = null;
              } else {
                if (lastBubble) { lastBubble.innerHTML = `⏳ ${data.message}`; }
                else { lastBubble = addMessage(`⏳ ${data.message}`, 'bot', true); }
              }

            } else if (data.phase === 'complete') {
              const decision = data.data;
              const color = decision.decision === 'APPROVED' ? 'var(--status-approved)'
                          : decision.decision === 'REJECTED' ? 'var(--status-rejected)'
                          : 'var(--status-partial)';

              const summaryHtml = `
                <div style="border-left:4px solid ${color};padding-left:1rem;margin-top:0.5rem;">
                  <div style="font-weight:700;color:${color};font-size:1.1rem;">${decision.decision}</div>
                  <div style="margin-top:0.25rem;">Approved: <b>₹${decision.approved_amount}</b></div>
                  <div style="font-size:0.8rem;color:var(--text-muted);margin-top:0.25rem;">
                    Reasons: ${decision.reasons.join(', ') || 'None'}
                  </div>
                </div>
              `;
              if (lastBubble) lastBubble.remove();
              addMessage(`✅ Processing complete! Here is the decision:<br/>${summaryHtml}`, 'bot', true);

              setTimeout(() => {
                addMessage('You will be redirected to the dashboard shortly.', 'bot');
                setTimeout(() => window.location.href = '/', 3000);
              }, 1000);

            } else if (data.phase === 'error') {
              if (lastBubble) lastBubble.remove();
              addMessage(`❌ Processing failed: ${data.message}`, 'bot');
            }
          } catch { /* ignore malformed frames */ }
        }
      }
    } catch (err) {
      addMessage('❌ Network error during processing.', 'bot');
    }
  }

  // ── Boot ──────────────────────────────────────────────────────────────────
  setTimeout(() => {
    addMessage("Hi! I'm your Plum HQ assistant. I can help you submit a new claim.");
    setTimeout(() => {
      addMessage('Please enter your Member ID (e.g. EMP001).');
      toggleInput(true);
      chatInput.focus();
    }, 800);
  }, 500);
});
