document.addEventListener('DOMContentLoaded', () => {
  const messagesContainer = document.getElementById('chat-messages');
  const chatForm = document.getElementById('chat-form');
  const chatInput = document.getElementById('chat-input');
  const quickRepliesContainer = document.getElementById('quick-replies');
  const btnUpload = document.getElementById('btn-upload');
  const fileInput = document.getElementById('file-input');
  const btnSend = document.getElementById('btn-send');

  let state = {
    step: 'ASK_MEMBER_ID',
    member_id: null,
    claim_category: null,
    files: [],          // now an array of File objects
    extracted_text: null,
    extracted_fields: null,
    initial_trace: null,
    claim_id: null
  };

  const categories = ["CONSULTATION", "DIAGNOSTIC", "PHARMACY", "DENTAL", "VISION", "ALTERNATIVE_MEDICINE"];

  // Helper to add a message to the chat
  function addMessage(text, sender = 'bot', isHtml = false) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-message ${sender}`;
    
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    
    if (isHtml) {
      bubble.innerHTML = text;
    } else {
      bubble.textContent = text;
    }
    
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

  function clearQuickReplies() {
    quickRepliesContainer.innerHTML = '';
  }

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

  // File upload handler
  btnUpload.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0 && state.step === 'ASK_DOCUMENT') {
      state.files = Array.from(e.target.files);
      const names = state.files.map(f => f.name).join(', ');
      addMessage(`📎 ${names}`, 'user');
      handleStepAdvance();
    }
  });

  // Main Form Submit
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;
    
    chatInput.value = '';
    addMessage(text, 'user');
    
    if (state.step === 'ASK_MEMBER_ID') {
      state.member_id = text;
      handleStepAdvance();
    } else if (state.step === 'REVIEW') {
      // shouldn't normally submit text here, but just in case
    }
  });

  // State Machine logic
  async function handleStepAdvance() {
    clearQuickReplies();
    
    if (state.step === 'ASK_MEMBER_ID') {
      toggleInput(false);
      const loadingBubble = addMessage(`Verifying member ID...`, 'bot');
      
      try {
        const response = await fetch(`/api/policy/coverage/${state.member_id}`);
        if (!response.ok) {
          throw new Error("Not found");
        }
        const data = await response.json();
        const memberName = data.name || state.member_id;
        
        loadingBubble.remove();
        state.step = 'ASK_CATEGORY';
        
        setTimeout(() => {
          addMessage(`Welcome back, ${memberName}! What category is this claim for?`);
          addQuickReplies(categories.map(c => ({ label: c.replace('_', ' '), value: c })), (val) => {
            state.claim_category = val;
            handleStepAdvance();
          });
        }, 500);
      } catch (err) {
        loadingBubble.remove();
        addMessage(`Sorry, I couldn't find a member with ID "${state.member_id}". Please try another one.`, 'bot');
        state.member_id = null;
        toggleInput(true);
        chatInput.focus();
      }
      
    } else if (state.step === 'ASK_CATEGORY') {
      state.step = 'ASK_DOCUMENT';
      setTimeout(() => {
        addMessage(`Great! Please upload your medical document(s) (invoice, bill, prescription). You can select multiple files at once.`);
        toggleInput(false, true); // disable text, show upload
      }, 500);
      
    } else if (state.step === 'ASK_DOCUMENT') {
      state.step = 'EXTRACTING';
      toggleInput(false, false);
      await startExtraction();
    }
  }

  async function startExtraction() {
    const formData = new FormData();
    formData.append('member_id', state.member_id);
    formData.append('claim_category', state.claim_category);
    // Append every file under the same field name "files" so FastAPI receives a list
    state.files.forEach(f => formData.append('files', f));
    
    const label = state.files.length === 1
      ? state.files[0].name
      : `${state.files.length} documents`;
    addMessage(`Processing ${label}...`, 'bot');
    
    try {
      const response = await fetch('/api/claims/extract', {
        method: 'POST',
        body: formData
      });
      if (!response.ok) throw new Error("Server error");
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      
      let extractionSuccess = false;
      let lastBubble = null;
      
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        let parts = buffer.split("\n\n");
        buffer = parts.pop();
        
        for (const part of parts) {
          if (part.startsWith("data: ")) {
            const dataStr = part.slice(6);
            try {
              const data = JSON.parse(dataStr);
              
              if (!data.is_final) {
                if (data.data) {
                  let info = "";
                  try {
                    info = JSON.stringify(data.data, null, 2);
                  } catch(e) {}
                  addMessage(`⏳ ${data.message}<br><pre style="font-size: 0.75rem; background: var(--bg-base); padding: 0.5rem; border-radius: var(--radius-sm); color: var(--text-muted); margin-top: 0.5rem; white-space: pre-wrap;">${info}</pre>`, 'bot', true);
                  lastBubble = null;
                } else {
                  if (lastBubble) { lastBubble.innerHTML = `⏳ ${data.message}`; }
                  else { lastBubble = addMessage(`⏳ ${data.message}`, 'bot', true); }
                }
              } else if (data.phase === 'complete') {
                if (lastBubble) lastBubble.textContent = `✅ Document extracted!`;
                
                state.extracted_text = data.data.text;
                state.extracted_fields = data.data.extracted_fields;
                state.initial_trace = data.data.trace;
                state.claim_id = data.data.trace.claim_id;
                
                state.step = 'REVIEW';
                showReviewCard();
                extractionSuccess = true;
              } else if (data.phase === 'error') {
                addMessage(`❌ Extraction failed: ${data.message}`, 'bot');
                state.step = 'ASK_DOCUMENT';
                toggleInput(false, true); // Allow re-upload
              }
            } catch(e) {}
          }
        }
      }
    } catch(err) {
      addMessage(`❌ Network error during extraction.`, 'bot');
      state.step = 'ASK_DOCUMENT';
      toggleInput(false, true);
    }
  }

  function showReviewCard() {
    const fields = state.extracted_fields || {};
    let dateVal = fields["Date"] || fields["Treatment Date"] || "";
    if (dateVal && !dateVal.match(/^\d{4}-\d{2}-\d{2}$/)) {
      const d = new Date(dateVal);
      if(!isNaN(d.getTime())) dateVal = d.toISOString().split('T')[0];
      else dateVal = "";
    }
    
    let amountVal = fields["Total Amount"] || fields["Claimed Amount"] || "";
    amountVal = amountVal.toString().replace(/[^0-9.]/g, '');

    const cardHtml = `
      <div class="review-card">
        <h4 style="margin-bottom: 0.5rem; font-size: 0.9rem;">Review Details</h4>
        <div class="form-group">
          <label>Treatment Date</label>
          <input type="date" id="review_date" value="${dateVal}" />
        </div>
        <div class="form-group">
          <label>Hospital/Clinic</label>
          <input type="text" id="review_hospital" value="${fields["Hospital Name"] || fields["Doctor Name"] || ""}" />
        </div>
        <div class="form-group">
          <label>Claimed Amount (INR)</label>
          <input type="number" id="review_amount" step="0.01" value="${amountVal}" />
        </div>
        <div class="form-group">
          <label>Bill Total (Extracted)</label>
          <input type="number" id="review_bill_total" step="0.01" value="${amountVal}" />
        </div>
        <button id="btn-confirm-review" style="width:100%; padding: 0.5rem; background: var(--status-approved); color: white; border: none; border-radius: var(--radius-sm); cursor: pointer; font-weight: 600; margin-top: 0.5rem;">Confirm & Submit</button>
      </div>
    `;
    
    addMessage(cardHtml, 'bot', true);
    
    // Attach event listener after adding to DOM
    setTimeout(() => {
      document.getElementById('btn-confirm-review').addEventListener('click', async () => {
        // Disable inputs
        document.getElementById('review_date').disabled = true;
        document.getElementById('review_hospital').disabled = true;
        document.getElementById('review_amount').disabled = true;
        document.getElementById('review_bill_total').disabled = true;
        document.getElementById('btn-confirm-review').style.display = 'none';
        
        addMessage(`Looks good! Please process it.`, 'user');
        
        state.step = 'PROCESSING';
        
        const date = document.getElementById('review_date').value;
        const amount = document.getElementById('review_amount').value;
        const hospital = document.getElementById('review_hospital').value;
        const bill_total = document.getElementById('review_bill_total').value;
        
        if (state.extracted_fields) {
          state.extracted_fields["Total Amount"] = bill_total;
        } else {
          state.extracted_fields = { "Total Amount": bill_total };
        }
        
        await startProcessing(date, amount, hospital);
      });
    }, 100);
  }

  async function startProcessing(date, amount, hospital) {
    addMessage(`Running policy evaluation...`, 'bot');
    
    const payload = {
      claim_id: state.claim_id,
      member_id: state.member_id,
      claim_category: state.claim_category,
      treatment_date: date,
      claimed_amount: parseFloat(amount) || 0.0,
      hospital_name: hospital,
      extracted_text: state.extracted_text,
      extracted_fields: state.extracted_fields,
      initial_trace: state.initial_trace
    };
    
    try {
      const response = await fetch('/api/claims/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error("Server error");
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let lastBubble = null;
      
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        let parts = buffer.split("\n\n");
        buffer = parts.pop();
        
        for (const part of parts) {
          if (part.startsWith("data: ")) {
            const dataStr = part.slice(6);
            try {
              const data = JSON.parse(dataStr);
              
              if (!data.is_final) {
                if (data.data) {
                  let info = "";
                  try {
                    info = JSON.stringify(data.data, null, 2);
                  } catch(e) {}
                  addMessage(`⏳ ${data.message}<br><pre style="font-size: 0.75rem; background: var(--bg-base); padding: 0.5rem; border-radius: var(--radius-sm); color: var(--text-muted); margin-top: 0.5rem; white-space: pre-wrap;">${info}</pre>`, 'bot', true);
                  lastBubble = null;
                } else {
                  if (lastBubble) { lastBubble.innerHTML = `⏳ ${data.message}`; }
                  else { lastBubble = addMessage(`⏳ ${data.message}`, 'bot', true); }
                }
              } else {
                if (data.phase === 'complete') {
                  const decision = data.data;
                  const color = decision.decision === 'APPROVED' ? 'var(--status-approved)' : 
                                decision.decision === 'REJECTED' ? 'var(--status-rejected)' : 'var(--status-partial)';
                  
                  const summaryHtml = `
                    <div style="border-left: 4px solid ${color}; padding-left: 1rem; margin-top: 0.5rem;">
                      <div style="font-weight: 700; color: ${color}; font-size: 1.1rem;">${decision.decision}</div>
                      <div style="margin-top: 0.25rem;">Approved: <b>₹${decision.approved_amount}</b></div>
                      <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem;">Reasons: ${decision.reasons.join(', ') || 'None'}</div>
                    </div>
                  `;
                  if (lastBubble) lastBubble.remove();
                  addMessage(`✅ Processing complete! Here is the decision:<br/>${summaryHtml}`, 'bot', true);
                  
                  setTimeout(() => {
                    addMessage(`You will be redirected to the dashboard shortly.`, 'bot');
                    setTimeout(() => window.location.href = '/', 3000);
                  }, 1000);
                } else if (data.phase === 'error') {
                  if (lastBubble) lastBubble.remove();
                  addMessage(`❌ Processing failed: ${data.message}`, 'bot');
                  // We stay here so user sees the error
                }
              }
            } catch(e) {}
          }
        }
      }
    } catch (err) {
      addMessage(`❌ Network error during processing.`, 'bot');
    }
  }

  // Initialize
  setTimeout(() => {
    addMessage(`Hi! I'm your Plum HQ assistant. I can help you submit a new claim.`);
    setTimeout(() => {
      addMessage(`Please enter your Member ID (e.g. EMP001).`);
      toggleInput(true);
      chatInput.focus();
    }, 800);
  }, 500);
});
