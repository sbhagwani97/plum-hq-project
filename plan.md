# Plum HQ — AI Claims Processing System: Implementation Plan

## Problem Summary

Build an AI-powered pipeline that accepts health insurance claim submissions (member info + documents), verifies documents, extracts structured data via LLMs, applies policy rules, and produces an explainable decision (`APPROVED`, `PARTIAL`, `REJECTED`, `MANUAL_REVIEW`) with a confidence score and full audit trace.

---

## Approach: Progressive Co-Development (Backend + UI)

> **Focus order**: Progressive vertical slices. Each phase delivers backend components/endpoints and the corresponding UI, allowing user-facing and programmatic testing side-by-side.

The system will be a **multi-agent pipeline** (bonus points) utilizing the `deepagents` SDK. Each agent has a narrow, testable responsibility. The orchestrator manages failures gracefully, ensuring that localized issues do not halt the entire system.

---

## Open Questions / User Comment Space

> **📝 YOUR NOTES HERE** — Overall architecture preferences:
> *Do you want a monorepo or separate repos for backend/frontend? Any preference on cloud provider for deployment?* I want mono repo for this project.
> *LLM Model source* It will be langchain/langgraph based ChatTogether implementation.
> *Any specific agent framework* It will be deepagent architecture with sub agents performing various isolated tasks as per langchain documentation.

---

## Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend | **Python / FastAPI** | Async-native, great for LLM calls, fast to build |
| LLM | **Together AI** via **LangChain** | Flexible model routing, managed inference, LangChain ecosystem |
| Agent Framework | **`deepagents`** SDK (PyPI) | LangChain's agent harness with native subagent spawning, context management, streaming, and LangGraph runtime underneath |
| Database | **SQLite** (dev) → **PostgreSQL** (prod) | Structured claim storage, easy to run locally |
| ~~Task Queue~~ | ~~Celery~~ — **removed** | LangGraph manages async orchestration natively; FastAPI `async/await` handles the rest. No external broker needed. |
| Document Storage | Local filesystem (dev) → S3-compatible | PDF/image uploads |
| Frontend | **HTML + Vanilla CSS & JS** | Simple, fast, lightweight, served directly by FastAPI |

---

## System Architecture: Deep Agents SDK

The `deepagents` package (`pip install deepagents`) is LangChain's agent harness — a single `create_deep_agent()` call gives you a fully configured agent with built-in:
- **Subagent spawning** via a `task` tool (each sub-agent runs in its own isolated context window)
- **Context compression** — automatically summarises history and offloads large results to a virtual filesystem
- **Streaming** — typed event projections per agent and per subagent
- **LangGraph runtime** underneath — durable execution, human-in-the-loop pauses

### How it maps to our pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│  ROOT AGENT  (create_deep_agent, Together AI model)                  │
│  Orchestrates the full claims pipeline, owns ClaimTrace              │
│                                                                      │
│  Built-in `task` tool spawns SUBAGENTS for isolated work:           │
│                                                                      │
│   [task] MemberValidator      → pure rules, no LLM, fast            │
│   [task] DocumentVerifier     → LLM vision: type check + quality    │
│   [task] DocumentExtractor    → LLM vision: structured extraction   │
│   [task] DecisionAgent        → LLM + policy engine → final decision│
│                                                                      │
│  PolicyEngine runs in-process (pure Python, no LLM, no subagent)   │
└──────────────────────────────────────────────────────────────────────┘
```

Model string format for Together AI:
```python
agent = create_deep_agent(
    model="together:meta-llama/Llama-3.3-70B-Instruct-Turbo",  # or any Together model
    tools=[...],
    system_prompt="You are a claims processing orchestrator...",
)
```

Each subagent:
- Gets its own `create_deep_agent()` instance with a focused system prompt
- Accepts a typed Pydantic input, returns a typed Pydantic output
- Failures are caught by `agent_guard` wrapper — pipeline continues with degraded confidence
- Appends its result to the shared `ClaimTrace`

---

## Proposed Components (Backend Phase)

---

### Component 1: Project Setup & Data Models

**Goal**: Establish the foundational types the entire pipeline depends on. Everything downstream consumes these contracts.

#### `backend/models/claim.py`

Core Pydantic models:

- `ClaimSubmission` — input from the user: `member_id`, `policy_id`, `claim_category`, `claimed_amount`, `treatment_date`, `documents[]`
- `DocumentInput` — `file_id`, `file_name`, `file_path`, `mime_type`
- `ClaimDecision` — `decision` (enum), `approved_amount`, `confidence_score`, `reasons[]`, `trace`
- `ClaimTrace` — ordered list of `TraceEntry` (agent name, status, output, error if any, timestamp)
- `DecisionEnum` — `APPROVED | PARTIAL | REJECTED | MANUAL_REVIEW`

> **📝 YOUR NOTES HERE** — Data model preferences:
> *e.g., Should `ClaimTrace` be stored in DB alongside the decision? Do you want versioned claim submissions?*
>
> ```
> [Your comments here]
> ```

---

### Component 2: Policy Engine

**Goal**: A pure, deterministic rule engine that reads `policy_terms.json` and evaluates any claim against all applicable rules. No LLM involved — this must be 100% testable and auditable.

#### `backend/policy/loader.py`

- Loads and parses `policy_terms.json` at startup
- Exposes typed `PolicyConfig` dataclass
- Validates member existence and policy active status

#### `backend/policy/engine.py`

Rules the engine applies (in order):

1. **Member validation** — is the `member_id` in the policy roster? Is the policy `ACTIVE`?
2. **Submission deadline** — was the claim submitted within 30 days of treatment?
3. **Minimum claim amount** — is it above ₹500?
4. **Waiting period** — initial 30-day, pre-existing 365-day, condition-specific (e.g., diabetes: 90 days)
5. **Coverage check** — is the `claim_category` covered at all?
6. **Exclusions** — does the diagnosis/treatment match any exclusion list?
7. **Pre-authorization** — does this claim type/amount require pre-auth? Was it provided?
8. **Sub-limit check** — does the claimed amount exceed the category sub-limit?
9. **Per-claim limit** — does the claimed amount exceed ₹5,000?
10. **Annual OPD limit** — does the YTD total + this claim exceed ₹50,000?
11. **Family floater** — if a dependent, does the combined claim exceed ₹1,50,000?
12. **Network hospital discount** — apply 20% discount if hospital is in the network list
13. **Co-pay** — apply category-specific co-pay percentage
14. **Fraud thresholds** — same-day claims > 2, monthly claims > 6, high-value > ₹25,000 → `MANUAL_REVIEW`

Returns: `PolicyDecision(approved_amount, adjustments[], rejection_reasons[], flags[], confidence)`

> **📝 YOUR NOTES HERE** — Policy engine approach:
> *e.g., Should the engine short-circuit on first rejection or run all rules and collect all reasons? Should fraud checks run in parallel?*
>
> ```
> [Your comments here]
> ```

#### `backend/policy/tests/test_engine.py`

Unit tests covering all 12 test cases' policy-layer expectations (TC004–TC012). These tests run against the engine directly with mocked document extraction output, no LLM needed.

---

### Component 3: Agent — Member Validator

**Goal**: Synchronous check (no LLM). Confirms the member exists, the policy is active, and the claimant is eligible.

#### `backend/agents/member_validator.py`

- Input: `member_id`, `policy_id`, `treatment_date`
- Output: `MemberValidationResult(valid, member_record, error_code, message)`
- Checks: member in roster, `join_date` vs `treatment_date` for initial waiting period

> **📝 YOUR NOTES HERE** — Member validator:
> *No notes needed unless you want to add external member lookup (e.g., HR system integration).*
>
> ```
> [Your comments here]
> ```

---

### Component 4: Agent — Document Verifier

**Goal**: Verify that the correct document types have been uploaded for the given `claim_category`, and that documents are readable and consistent with each other. This is the **earliest gate** — runs before extraction.

#### `backend/agents/document_verifier.py`

Two sub-checks:

**A. Type Check (rule-based)**
- Reads required/optional doc types from `policy_terms.json → document_requirements`
- Compares uploaded doc types against requirements
- If wrong type: returns specific error `"You uploaded a PRESCRIPTION where a HOSPITAL_BILL is required"`

**B. Quality + Cross-Document Consistency Check (LLM)**
- Uses Gemini Vision to assess readability of each document image/PDF
- If a doc is unreadable: asks member to re-upload that specific file (TC002 behavior)
- After extraction: checks that patient names across all documents match the member on file (TC003 behavior)

- Input: `DocumentInput[]`, `claim_category`, `member_name`
- Output: `DocVerificationResult(passed, errors[], warnings[], doc_classifications[])`

> **📝 YOUR NOTES HERE** — Document verifier:
> *e.g., Should the LLM classify the document type itself (to catch wrong uploads), or do we trust the `actual_type` field from the frontend? Should we do classification-first before rule-based check?*
>
> ```
> [Your comments here]
> ```

---

### Component 5: Agent — Document Extractor

**Goal**: Extract structured data from each uploaded document using a **two-tier parsing strategy**. Start cheap and fast with a local parser; escalate to an LLM vision model only when needed.

#### `backend/agents/document_extractor.py`

---

#### Tier 1 — Local Parser (`local_parser`)

For any file that can be converted to plain text without an LLM:

| Format | Tool |
|---|---|
| `.txt`, `.md` | Read directly |
| `.docx` | `python-docx` |
| `.pptx` | `python-pptx` |
| `.pdf` (digital/searchable) | `pdfplumber` or `pypdf` |

**Flow:**
1. Attempt text extraction using the appropriate local library
2. If extracted text is **non-empty and passes a minimum length heuristic** → proceed to structured field parsing (regex + simple NLP, no LLM)
3. If extracted text is **empty, too short, or garbled** (e.g., a scanned PDF returning `\x00` bytes or <50 chars) → escalate to Tier 2

---

#### Tier 2 — Advanced Vision Parser (`advanced_parser`)

Triggered for:
- Images (`.jpg`, `.jpeg`, `.png`, `.webp`, `.tiff`)
- PDFs where Tier 1 returned empty or unreadable content (scanned / handwritten)

**Flow:**
1. Convert PDF pages to images if needed (`pdf2image` / `pymupdf`)
2. Send image(s) to the Together AI vision model via LangChain
3. Prompt the model to extract structured fields as JSON (structured output / function calling)
4. Confidence score per field: `HIGH` / `MEDIUM` / `LOW`
5. Unextractable fields → `null` + `extraction_note` (e.g., `"rubber stamp obscured amount"`)

---

#### Extraction Schemas (Pydantic models, used by both tiers)

- `ExtractedPrescription` — doctor name/reg, patient name, date, diagnosis, medicines, tests ordered
- `ExtractedHospitalBill` — hospital name, bill number, date, patient name, line items + amounts, total
- `ExtractedLabReport` — lab name, sample date, report date, tests + results + normal ranges
- `ExtractedPharmacyBill` — pharmacy name, drug license, medicines (name, batch, qty, amount), net total

---

#### Common extraction behaviors (both tiers)

- Medical shorthand expansion: `HTN → Hypertension`, `T2DM → Type 2 Diabetes Mellitus`
- Doctor registration number validation against known state formats (`KA/XXXXX/YYYY`, etc.)
- For multi-page PDFs: process each page separately, aggregate line items
- Result always includes: `parser_used` (`local` or `advanced`), `confidence_score`, `extraction_notes[]`

> **📝 YOUR NOTES HERE** — Document extractor:
> *e.g., Which vision model on Together AI for the advanced parser (Llama Vision, Qwen-VL, etc.)? Should Tier 1 local parsing attempt any regex-based field extraction before giving up, or just check if text is non-empty?*
>
> ```
> [Your comments here]
> ```



---

### Component 6: Agent — Decision Agent

**Goal**: Combines the policy engine output and extracted document data to produce the final `ClaimDecision`. Uses LLM for diagnosis-to-exclusion matching (fuzzy), but wraps with deterministic rules for hard limits.

#### `backend/agents/decision_agent.py`

Decision logic flow:

1. If document verification failed → return early with `DOC_ERROR`, no decision
2. Run policy engine with extracted data → get `PolicyDecision`
3. Use LLM to fuzzy-match diagnosis to waiting periods / exclusions (e.g., "Morbid Obesity" → "Obesity treatment" exclusion)
4. Aggregate: if any hard rejection → `REJECTED`; if partial items excluded → `PARTIAL`; if fraud flags → `MANUAL_REVIEW`; else → `APPROVED`
5. Compute final `approved_amount` applying network discount and co-pay in correct order
6. Set `confidence_score` based on:
   - Number of LOW-confidence extracted fields
   - Number of degraded/failed agents in pipeline
   - Whether all documents were readable

Output: `ClaimDecision` (full schema with trace)

> **📝 YOUR NOTES HERE** — Decision agent:
> *e.g., Should the LLM be used for the final decision explanation text, or should explanations be template-driven? Do you want a separate "fraud detection agent" vs integrating fraud scoring into the decision agent?*
>
> ```
> [Your comments here]
> ```

---

### Component 7: Claim Orchestrator

**Goal**: Coordinates the agent pipeline, handles per-agent failures gracefully, and builds the full `ClaimTrace`.

#### `backend/orchestrator/pipeline.py`

```python
async def process_claim(submission: ClaimSubmission) -> ClaimDecision:
    trace = ClaimTrace()

    with agent_guard("member_validator"):
        member_result = await member_validator.run(...)
        trace.append(member_result)

    with agent_guard("doc_verifier"):
        doc_result = await doc_verifier.run(...)
        trace.append(doc_result)
        if doc_result.has_blocking_errors:
            return early_exit(doc_result, trace)  # TC001, TC002, TC003

    with agent_guard("doc_extractor"):
        extraction = await doc_extractor.run(...)
        trace.append(extraction)

    with agent_guard("decision_agent"):
        decision = await decision_agent.run(...)
        trace.append(decision)

    return finalize(decision, trace)
```

`agent_guard` context manager:
- Catches any exception from an agent
- Logs it to trace as `status=FAILED`
- Reduces confidence score
- Continues pipeline (TC011 behavior)

> **📝 YOUR NOTES HERE** — Orchestrator:
> *e.g., Should the orchestrator store intermediate agent results to a DB for resume-on-failure? Should agents run in parallel where possible (e.g., member validation + doc verification simultaneously)?*
>
> ```
> [Your comments here]
> ```

---

### Component 8: REST API

**Goal**: Expose the pipeline via a clean HTTP API. FastAPI with async endpoints.

#### `backend/api/routes/claims.py`

| Method | Path | Description |
|---|---|---|
| `POST` | `/claims/submit` | Accept multipart form: member_id, policy_id, claim_category, treatment_date, claimed_amount + document files |
| `GET` | `/claims/{claim_id}` | Retrieve a stored claim decision + full trace |
| `GET` | `/claims/{claim_id}/trace` | Retrieve only the trace for a claim |
| `GET` | `/members/{member_id}/claims` | List claims for a member |
| `POST` | `/claims/test` | Accept JSON (no file upload) — for running test_cases.json scenarios |

#### `backend/api/routes/policy.py`

| Method | Path | Description |
|---|---|---|
| `GET` | `/policy/members` | List all members |
| `GET` | `/policy/coverage` | Return coverage summary |

> **📝 YOUR NOTES HERE** — API design:
> *e.g., Should `/claims/submit` be synchronous (wait for full pipeline) or return a `claim_id` immediately and poll for status? Async might be better UX for slow LLM calls.*
>
> ```
> [Your comments here]
> ```

---

### Component 9: Persistence Layer

**Goal**: Store claims, decisions, and traces so they can be retrieved and audited.

#### `backend/db/models.py`

SQLAlchemy models:
- `ClaimRecord` — all submission fields + `status`, `created_at`
- `ClaimDecisionRecord` — `decision`, `approved_amount`, `confidence_score`, `reasons_json`, `trace_json`
- `DocumentRecord` — `file_id`, `claim_id`, `doc_type`, `file_path`, `extraction_json`

#### `backend/db/repository.py`

CRUD operations for claims. Uses async SQLAlchemy.

> **📝 YOUR NOTES HERE** — Persistence:
> *e.g., Is SQLite fine for the demo, or should we use PostgreSQL from the start? Should traces be stored as JSONB (Postgres) or just serialized JSON strings?*
>
> ```
> [Your comments here]
> ```

---

### Component 10: Observability / Tracing

**Goal**: Every claim decision must be fully reconstructible from logs. Evaluator (Plum team) will look at this closely (20% of score).

#### `backend/tracing/trace_builder.py`

`ClaimTrace` structure:

```json
{
  "claim_id": "CLM_001",
  "submitted_at": "2024-11-01T10:00:00Z",
  "agents": [
    {
      "agent": "member_validator",
      "status": "SUCCESS",
      "output": { "member": "Rajesh Kumar", "eligible": true },
      "duration_ms": 5,
      "timestamp": "..."
    },
    {
      "agent": "doc_extractor",
      "status": "DEGRADED",
      "output": { "fields_extracted": 8, "low_confidence_fields": ["doctor_registration"] },
      "error": null,
      "confidence_impact": -0.05,
      "timestamp": "..."
    }
  ],
  "final_decision": "APPROVED",
  "confidence_score": 0.87,
  "approved_amount": 1350,
  "reasons": ["10% co-pay applied on consultation"]
}
```

> **📝 YOUR NOTES HERE** — Observability:
> *e.g., Should traces also be emitted to a structured logging system (e.g., JSON logs to stdout for cloud log aggregation)? Any preference on trace format?*
>
> ```
> [Your comments here]
> ```

---

### Component 11: Test Suite

**Goal**: Every component has tests. The 12 test cases from `test_cases.json` are runnable via a single command.

#### `backend/tests/test_policy_engine.py`
Unit tests for each policy rule — isolated, no LLM, deterministic.

#### `backend/tests/test_orchestrator.py`
Integration tests running all 12 test cases. LLM calls mocked with fixture responses for determinism.

#### `backend/tests/test_document_extractor.py`
Tests using sample document images. Validates structured output schema.

#### `backend/eval/run_eval.py`
Script that runs all 12 test cases against the live system and produces the Eval Report (`eval_report.md`).

> **📝 YOUR NOTES HERE** — Testing strategy:
> *e.g., Should we use `pytest` + `pytest-asyncio`? Do you want contract tests (pact-style) for agent interfaces? Any CI/CD preferences?*
>
> ```
> [Your comments here]
> ```

---

## Frontend (HTML + CSS + Vanilla JS)

The UI will be a single-page application built using pure HTML, Vanilla CSS, and modern JavaScript. It will be served directly by the FastAPI backend under `/` (main page) and static assets under `/static` to ensure a unified local setup.

The UI will have:
- **Claim submission form** — member selector, category, date, amount, document upload (drag & drop, multi-file)
- **Decision review page** — decision badge, approved amount, reasons list, expandable full trace timeline
- **Claims list** — paginated history per member

---

## Execution Order (Progressive Phases)

### Phase 1: Environment, Basic API & Dashboard Layout
* **Backend**:
  * Set up monorepo directory structure (`backend/` and `frontend/`).
  * Initialize backend dependencies (`FastAPI`, `pydantic`, `deepagents` SDK, etc.).
  * Define core data models (`backend/models/claim.py`).
  * Implement initial `/health` status and mock claim submit endpoints.
* **Frontend**:
  * Set up directory structure for static files in `backend/static/` and `backend/templates/`.
  * Design visual foundation (`index.css` design system: harmonized HSL colors, modern fonts, dark/light theme tokens).
  * Build the main layout/navigation shell (`index.html`).
  * Build a simple mock claims dashboard page displaying history list.
* **Testable Deliverable**:
  * Launch backend and frontend locally. Verify frontend shell runs and successfully displays mock claims by contacting the backend health endpoint.

### Phase 2: Policy Engine & Member Validation
* **Backend**:
  * Implement `backend/policy/loader.py` to load and validate `policy_terms.json`.
  * Build the pure Python deterministic `PolicyEngine` (`backend/policy/engine.py`) covering waiting periods, exclusions, limits, etc.
  * Build Member Validator Agent (`backend/agents/member_validator.py`) and write policy engine unit tests.
  * Expose REST endpoints: `GET /policy/members` and `GET /policy/coverage`.
* **Frontend**:
  * Create a Member lookup / Eligibility check screen.
  * Fetch roster from `GET /policy/members`.
  * Provide input form for treatment date and claim category.
  * Connect to Policy Engine logic to instantly show waiting period status and category eligibility.
* **Testable Deliverable**:
  * User can select a member on the UI, choose a category, and verify whether the policy engine flags them as eligible or ineligible (e.g. waiting periods, category covered/excluded), matching the raw policy rules.

### Phase 3: Two-Tier Document Parsing & Verification UI
* **Backend**:
  * Implement Document Verifier Agent (validates MIME types & file formats against policy requirements).
  * Implement Document Extractor Agent:
    * Tier 1 local parser (`pdfplumber`/`python-docx`/`python-pptx` or direct TXT read).
    * Tier 2 vision-based LLM parser configuration (Together AI Llama vision model) for scanned PDFs and image files.
  * Expose a temporary endpoint `POST /claims/verify-docs` to process files and return structured extraction JSON, `parser_used`, and confidence scores.
* **Frontend**:
  * Create an interactive Document Upload & Verification screen.
  * Implement drag-and-drop file uploader with type validation.
  * Connect uploader to `POST /claims/verify-docs`.
  * Display the extracted structured fields side-by-side with confidence highlights (color-coded badges for `HIGH`/`MEDIUM`/`LOW` fields) and indicators of which parsing tier was used (`local_parser` or `advanced_parser`).
* **Testable Deliverable**:
  * User can drag and drop a clean PDF (processed via Tier 1) vs a scanned image (processed via Tier 2 LLM) and visually inspect the extracted fields, confidence tags, and the exact parsing tier.

### Phase 4: Claims Orchestration, DB Persistence & End-to-End Decisioning
* **Backend**:
  * Implement the core `ClaimOrchestrator` (`backend/orchestrator/pipeline.py`) to chain all agents together.
  * Implement `agent_guard` error handling wrapper to handle subagent failures gracefully without crashing.
  * Implement Decision Agent (`backend/agents/decision_agent.py`) combining rule-based policy results and fuzzy LLM exclusion checks.
  * Set up database models and Repository (SQLAlchemy + SQLite) to store claim submissions and final decisions.
  * Expose full `POST /claims/submit` and `GET /claims/{claim_id}` endpoints.
* **Frontend**:
  * Connect the multi-step claim submission form:
    1. Select Member & Info.
    2. Upload Documents & Preview Extraction.
    3. Submit Claim (with active loading/processing state).
  * Create the Claim Decision Review screen:
    * Render decision status badges (`APPROVED`, `PARTIAL`, `REJECTED`, `MANUAL_REVIEW`).
    * Display financial calculations (discounts, co-pay adjustments, approved amount vs claimed amount).
    * Show lists of specific policy adjustments and reasons.
* **Testable Deliverable**:
  * Submit a full claim through the UI. Verify that the claim is written to the database, processed through the orchestrator, and returns a detailed decision screen.

### Phase 5: Trace Builder & Observability Timeline
* **Backend**:
  * Complete Trace Builder (`backend/tracing/trace_builder.py`) to construct the detailed `ClaimTrace` JSON.
  * Persist the claim trace in the SQLite database.
  * Expose `GET /claims/{claim_id}/trace` endpoint.
* **Frontend**:
  * Build the visual Audit Trace Timeline:
    * Render a clean step-by-step accordion list on the Decision Review screen showing each agent run (e.g. `member_validator` success, `doc_verifier` warning, `doc_extractor` stats, `decision_agent` reasoning).
    * Display agent status, latency (ms), confidence impacts, and warning/error details.
  * Add a simple Claims history/list view showing all historical claim submissions and their status.
* **Testable Deliverable**:
  * View any historical claim and expand its visual trace timeline, verifying that latency and agent logs are displayed correctly, showing the "how" behind the claim decision.

### Phase 6: Automated Evaluation & Polish
* **Backend**:
  * Finalize all integration tests for the orchestrator.
  * Implement `backend/eval/run_eval.py` to run all 12 test cases from `test_cases.json`.
  * Execute evaluation suite and auto-generate `eval_report.md` summarizing pass/fail metrics.
* **Frontend + Documentation**:
  * Refine the user interface (smooth transitions, visual touch-ups, dark mode aesthetics).
  * Write the Architecture Document (`architecture.md`).
* **Testable Deliverable**:
  * Run `pytest` and `run_eval.py` to confirm all 12 test cases behave correctly. Deliver a polished frontend displaying the exact system behavior.

---

## Verification Plan

### Automated Tests
```bash
# Unit tests
pytest backend/tests/ -v

# Eval report (all 12 test cases)
python backend/eval/run_eval.py
```

### Manual Verification
- Run the full server locally, submit each test case through the UI
- Verify trace output matches expected behavior for TC001–TC012
- Verify TC011 (graceful degradation) by simulating a component failure

---

## Key Design Decisions & Trade-offs

| Decision | Choice | Rationale | Trade-off |
|---|---|---|---|
| LLM for doc extraction | Gemini Vision | Handles handwriting, images, PDFs natively | Latency ~2–5s per doc; can cache |
| Policy engine is pure rules | No LLM for hard rules | 100% testable, auditable, deterministic | Need fuzzy matching for diagnosis → exclusion mapping |
| Graceful degradation | `agent_guard` context manager | TC011 requirement; prevents cascading failures | Decision may be less accurate with degraded agents |
| Multi-agent architecture | Separate agents vs monolith | Bonus points; clean responsibility separation; easier to test | More code, more interfaces to maintain |
| Early exit on doc errors | Before extraction/decision | TC001–TC003; fast feedback to member | Two separate pipeline paths to maintain |
